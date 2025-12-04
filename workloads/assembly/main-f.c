#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include "cJSON.h"
#include <pthread.h>
#include <string.h>
#include <sys/mman.h>
#include <sched.h>
#include <unistd.h>
#include <time.h>
#include <string.h>
#define RANK 90

extern void access_memory_block(long N, long STRIDE);
extern void add_block(long iterations);
extern void div_block(long iterations);
extern void sleep_n(unsigned int seconds);

typedef struct {
    char type[20];
    long iterations;
    long stride;
    int rank;
} BlockConfig;

typedef struct {
    BlockConfig* blocks;
    int block_count;
    int cpu_core;
    int thread_rank;
} ExecuteThreadData;

typedef struct {
    int index;

    size_t alloc_size;
} AllocThreadData;

typedef struct {
    void* mem_block;
    size_t alloc_size;
} AllocInfo;

typedef struct {
    void* mem_block;    
    size_t total_size;   // 新增总内存大小
    int thread_id;       // 新增线程ID
     
} ThreadInitData;
static struct timespec program_start;
AllocInfo alloc_info[RANK]; // 全局内存分配信息

char* read_config_file(const char* filename) {
    FILE* fp = fopen(filename, "r");
    if (!fp) return NULL;
    
    fseek(fp, 0, SEEK_END);
    long len = ftell(fp);
    fseek(fp, 0, SEEK_SET);
    
    char* buf = malloc(len + 1);
    fread(buf, 1, len, fp);
    buf[len] = '\0';
    fclose(fp);
    return buf;
}

BlockConfig* parse_config(const cJSON* root, int* block_count) {
    *block_count = cJSON_GetArraySize(root);
    BlockConfig* blocks = malloc(*block_count * sizeof(BlockConfig));
    
    int idx = 0;
    cJSON* current_block = NULL;
    cJSON_ArrayForEach(current_block, root) {
        strncpy(blocks[idx].type, 
               cJSON_GetStringValue(cJSON_GetObjectItem(current_block, "type")),
               sizeof(blocks[idx].type) - 1);
        blocks[idx].iterations = cJSON_GetNumberValue(cJSON_GetObjectItem(current_block, "iterations"));
        blocks[idx].rank = cJSON_GetNumberValue(cJSON_GetObjectItem(current_block, "rank"));
        if (strcmp(blocks[idx].type, "memory_block") == 0) {
            blocks[idx].stride = cJSON_GetNumberValue(cJSON_GetObjectItem(current_block, "stride"));
        } 
        idx++;
    }
    return blocks;
}

void execute_blocks(BlockConfig* blocks, int block_count, int thread_rank) {
    for (int i = 0; i < block_count; ++i) {
        printf("执行块 %d: 类型=%s, 迭代次数=%ld\n", 
              i+1, blocks[i].type, blocks[i].iterations);
        if (thread_rank >= blocks[i].rank) {
            continue;
        }
        if (strcmp(blocks[i].type, "memory_block") == 0) {
            access_memory_block(blocks[i].iterations, blocks[i].stride);
        } 
        else if (strcmp(blocks[i].type, "sleep_block") == 0) {
            sleep_n(blocks[i].iterations);
        } 
        else if (strcmp(blocks[i].type, "div_block") == 0) {
            div_block(blocks[i].iterations);
        }
        else if (strcmp(blocks[i].type, "add_block") == 0) {
            add_block(blocks[i].iterations);
        }
    }
}

void* alloc_thread_main(void* arg) {
    AllocThreadData* data = (AllocThreadData*)arg;
    int index = data->index;
    size_t alloc_size = data->alloc_size;
    free(data);

    void* mem_block = mmap(NULL, alloc_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (mem_block == MAP_FAILED) {
        perror("mmap失败");
        return NULL;
    }

    // 初始化内存，触发物理分配
    const size_t page_size = sysconf(_SC_PAGESIZE);
    for (size_t offset = 0; offset < alloc_size; offset += page_size) {
        memset((char*)mem_block + offset, 0, 1);
    }

    // 保存分配信息
    alloc_info[index].mem_block = mem_block;
    alloc_info[index].alloc_size = alloc_size;

    return NULL;
}

void* execute_thread_main(void* arg) {
    ExecuteThreadData* data = (ExecuteThreadData*)arg;
    
    // 绑定CPU核心
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(data->cpu_core, &cpuset);
    if (pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset) != 0) {
        perror("无法绑定核心");
        exit(EXIT_FAILURE);
    }

    execute_blocks(data->blocks, data->block_count, data->thread_rank);

    return NULL;
}

void* free_thread_main(void* arg) {
    int index = *(int*)arg;
    free(arg);
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(index, &cpuset);
    if (pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset) != 0) {
        perror("无法绑定核心");
        exit(EXIT_FAILURE);
    }
    /*if (alloc_info[index].mem_block != NULL) {
        //madvise(alloc_info[index].mem_block, alloc_info[index].alloc_size, MADV_DONTNEED);

        munmap(alloc_info[index].mem_block, alloc_info[index].alloc_size);
        alloc_info[index].mem_block = NULL;
    }
    char buf[64];
    int len = snprintf(buf, sizeof(buf), "finish %d\n", index);
    write(STDOUT_FILENO, buf, len);*/
    if (alloc_info[index].mem_block != NULL) {
        //struct timespec start, end;
        
        // 记录 munmap 开始时间
        //clock_gettime(CLOCK_MONOTONIC, &start);
        madvise(alloc_info[index].mem_block, alloc_info[index].alloc_size, MADV_DONTNEED); 
        //munmap(alloc_info[index].mem_block, alloc_info[index].alloc_size);
        // 记录 munmap 结束时间
        //clock_gettime(CLOCK_MONOTONIC, &end);
        alloc_info[index].mem_block = NULL;

        // 计算相对程序启动的时间（单位：纳秒）
        /*
        double start_sec = (start.tv_sec - program_start.tv_sec) + 
                          (start.tv_nsec - program_start.tv_nsec) / 1e9;
        double end_sec = (end.tv_sec - program_start.tv_sec) + 
                        (end.tv_nsec - program_start.tv_nsec) / 1e9;
        double elapsed_sec = end_sec - start_sec;

        // 无锁输出时间戳和耗时
         char buf[256];
        int len = snprintf(buf, sizeof(buf), 
            "Thread %d: munmap start=%.6f s, end=%.6f s, elapsed=%.6f s\n",
            index, start_sec, end_sec, elapsed_sec);
        write(STDOUT_FILENO, buf, len);*/

    }
    return NULL;
}

void* init_thread_main(void* arg) {
    ThreadInitData* data = (ThreadInitData*)arg;
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(data->thread_id, &cpuset);
    if (pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset) != 0) {
        perror("无法绑定核心");
        exit(EXIT_FAILURE);
    }
    // 在线程内部计算页数范围
    const size_t page_size = sysconf(_SC_PAGESIZE);
    const size_t total_pages = data->total_size / page_size;
    
    // 计算本线程处理的页数范围
    const size_t pages_per_thread = (total_pages + RANK - 1) / RANK;
    const size_t start_page = data->thread_id * pages_per_thread;
    size_t end_page = start_page + pages_per_thread;
    
    // 处理最后一个线程的边界
    if (end_page > total_pages || data->thread_id == RANK - 1) {
        end_page = total_pages;
    }

    // 转换为字节偏移量
    const size_t start_offset = start_page * page_size;
    const size_t end_offset = end_page * page_size;
    printf("%ld %ld \n",start_offset,end_offset);
    // 初始化内存区域
    char* base = (char*)data->mem_block;
    for (size_t offset = start_offset; offset < end_offset; offset += page_size) {
        size_t remain = end_offset - offset;
        memset(base + offset, 0, remain < page_size ? remain : page_size);
    }

    free(data);
    return NULL;
}

int main(int argc, char **argv) {
    if (argc != 2) {
        printf("用法: %s  <config.json>\n", argv[0]);
        return 1;
    }

    char* json_str = read_config_file(argv[1]);
    if (!json_str) {
        fprintf(stderr, "错误: 无法读取配置文件\n");
        return 1;
    }

    cJSON* config = cJSON_Parse(json_str);
    if (!config) {
        fprintf(stderr, "错误: 无效的JSON格式\n");
        free(json_str);
        return 1;
    }

    cJSON* global = cJSON_GetObjectItemCaseSensitive(config, "global");
    if (!global) {
        fprintf(stderr, "错误: 缺少global配置\n");
        free(json_str);
        return 1;
    }

    cJSON* mem_util = cJSON_GetObjectItemCaseSensitive(global, "memory_util");
    cJSON* mem_size = cJSON_GetObjectItemCaseSensitive(global, "memory_size");
    const size_t total_mem = (size_t)(cJSON_GetNumberValue(mem_size)) * 1024 * 1024 * 1024;
    const size_t per_thread_mem = (size_t)(total_mem * cJSON_GetNumberValue(mem_util)) / RANK;

    int block_count = 0;
    cJSON* blocks_array = cJSON_GetObjectItemCaseSensitive(config, "blocks");
    BlockConfig* blocks = parse_config(blocks_array, &block_count);

    // 阶段一：内存分配
    
    pthread_t alloc_threads[RANK];
    for (int i = 0; i < RANK; i++) {
        AllocThreadData* data = malloc(sizeof(AllocThreadData));
        data->index = i;
        data->alloc_size = per_thread_mem;
        pthread_create(&alloc_threads[i], NULL, alloc_thread_main, data);
    }
    for (int i = 0; i < RANK; i++) {
        pthread_join(alloc_threads[i], NULL);
    }
    /*
    size_t alloc_size=(size_t)(total_mem * cJSON_GetNumberValue(mem_util));
   
    void* mem_block = mmap(NULL, alloc_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (mem_block == MAP_FAILED) {
        perror("mmap失败");
        return NULL;
    }
    madvise(mem_block, alloc_size, MADV_POPULATE_WRITE);*/
    printf("alloc finsh\n");
    /*
    pthread_t init_threads[RANK];


    for (int i = 0; i < RANK; i++) {
        ThreadInitData* data = malloc(sizeof(ThreadInitData));
        data->mem_block = mem_block;
        data->total_size = alloc_size;
        data->thread_id = i;
        pthread_create(&init_threads[i], NULL, init_thread_main, data);
    }

    // 等待初始化完成
    for (int i = 0; i < RANK; i++) {
        pthread_join(init_threads[i], NULL);
    }*/
    printf("access finish\n");
    // 阶段二：执行逻辑块
    pthread_t execute_threads[RANK];
    ExecuteThreadData execute_data[RANK];
    for (int i = 0; i < RANK; i++) {
        execute_data[i] = (ExecuteThreadData){
            .blocks = blocks,
            .block_count = block_count,
            .cpu_core = i % RANK,
            .thread_rank = i
        };
        pthread_create(&execute_threads[i], NULL, execute_thread_main, &execute_data[i]);
    }


    // 阶段三：内存释放
    printf("release start\n");
    /*
    madvise(mem_block, alloc_size, MADV_DONTNEED);
    munmap(mem_block, alloc_size);*/
    /*
    for (int index = 0; index <RANK ; index++){
        if (alloc_info[index].mem_block != NULL) {
            //madvise(alloc_info[index].mem_block, alloc_info[index].alloc_size, MADV_DONTNEED);
            munmap(alloc_info[index].mem_block, alloc_info[index].alloc_size);
            printf("index=%d \n",index);
            alloc_info[index].mem_block = NULL;
        }
    }*/

    pthread_t free_threads[RANK];
    for (int i = 0; i < RANK; i++) {
        int* index = malloc(sizeof(int));
        *index = i;
        pthread_create(&free_threads[i], NULL, free_thread_main, index);
    }
    for (int i = 0; i < RANK; i++) {
        pthread_join(free_threads[i], NULL);
    }
    printf("release finsh\n");
    // 清理资源
    free(blocks);
    cJSON_Delete(config);
    free(json_str);
    
    return 0;
}