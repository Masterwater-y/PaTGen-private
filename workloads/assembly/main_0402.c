#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include "cJSON.h"
#include <pthread.h>
#include <string.h>
#include <sys/mman.h>
#include <sched.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <stdint.h>  // 定义uint32_t等标准类型

#define BLOCK_SIZE 4096  // 对齐的IO块大小
#define TIME_PER_ITER 0.1 // 每个迭代对应0.02秒
extern void access_memory_block(long N, long STRIDE);
extern void add_block(long iterations);
extern void div_block(long iterations);
extern void sleep_n(unsigned int seconds);
/*
void access_memory_block(long iters, long stride, long buffer_size) {
    void *buffer;
    // 分配对齐的内存块，对齐到4096字节，大小为buffer_size
    if (posix_memalign(&buffer, 4096, buffer_size) != 0) {
        return; // 分配失败时直接返回
    }

    volatile char *volatile_buf = (volatile char *)buffer;
    unsigned int mask = buffer_size - 1; // 计算掩码
    long offset = 0;

    for (long i = 0; i < iters; i++) {
        // 读取32位数据，使用volatile防止优化
        volatile uint32_t *ptr = (volatile uint32_t *)(volatile_buf + offset);
        uint32_t val = *ptr; // 实际内存访问

        offset += stride;    // 更新偏移量
        offset &= mask;      // 限制在缓冲区范围内
    }

    free(buffer); // 释放分配的内存
}
*/
void disk_io(int iterations) {
    // 生成唯一文件名：进程ID + 线程ID
    char tempfile[64];
    snprintf(tempfile, sizeof(tempfile), "diskio_%d_%lu.tmp", 
            getpid(), (unsigned long)pthread_self());

    // 创建线程专用文件（O_EXCL确保原子创建）
    int fd = open(tempfile, O_WRONLY | O_CREAT | O_TRUNC | O_EXCL | O_DIRECT, 0666);
    if (fd == -1) {
        fprintf(stderr, "文件创建失败: %s (%s)\n", tempfile, strerror(errno));
        return;
    }

    // 分配对齐缓冲区
    char* buf;
    const size_t block_size = 4 * 1024;  // 4KB对齐块
    if (posix_memalign((void**)&buf, block_size, block_size) != 0) {
        close(fd);
        return;
    }
    memset(buf, 0, block_size);

    // 时间控制逻辑
    const double total_time = iterations * TIME_PER_ITER;  // 每个迭代0.02秒
    struct timespec start, now;
    clock_gettime(CLOCK_MONOTONIC, &start);
    
    do {
        // 循环写入同一位置（避免文件膨胀）
        lseek(fd, 0, SEEK_SET);
        if (write(fd, buf, block_size) != block_size) {
            perror("写入失败");
            break;
        }
        fdatasync(fd);  // 强制落盘
        
        clock_gettime(CLOCK_MONOTONIC, &now);
    } while((now.tv_sec - start.tv_sec) + 
           (now.tv_nsec - start.tv_nsec) * 1e-9 < total_time);

    // 清理线程独占资源
    free(buf);
    close(fd);
    remove(tempfile);  // 删除线程专用文件
}
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
    size_t alloc_size;  // 新增全局内存利用率
    struct timespec start_time; // 新增：记录开始时间
    struct timespec end_time;   // 新增：记录结束时间

} ThreadData;
static pthread_barrier_t barrier;
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
        else if (strcmp(blocks[idx].type, "sleep_block") == 0) {
            blocks[idx].iterations = cJSON_GetNumberValue(cJSON_GetObjectItem(current_block, "iterations"));
        } 

        idx++;
    }
    return blocks;
}



void execute_blocks(BlockConfig* blocks, int block_count, int thread_rank ) {
    for (int i = 0; i < block_count; ++i) {
        if (thread_rank < blocks[i].rank) {  // 仅在满足条件时执行
            if (strcmp(blocks[i].type, "memory_block") == 0) {
                access_memory_block(blocks[i].iterations, blocks[i].stride);
                //access_memory_block(blocks[i].iterations, blocks[i].stride, 256*1024*1024/blocks[i].rank);
            } 
            else if (strcmp(blocks[i].type, "sleep_block") == 0) {
                sleep_n(blocks[i].iterations);
            } 
            else if (strcmp(blocks[i].type, "div_block") == 0) {
                div_block(blocks[i].iterations);
            }
            else if (strcmp(blocks[i].type, "add_block") == 0) {
                add_block(blocks[i].iterations);
            }else if (strcmp(blocks[i].type, "disk_block") == 0) {
                disk_io(blocks[i].iterations);
            }
        }
        // 所有线程在此同步，无论是否执行当前block
        pthread_barrier_wait(&barrier);

    }
}
// 新增结构体用于传递线程参数
typedef struct {
    int cpu_core;       // 绑定的CPU核心
    size_t buffer_size;  // 每个线程分配的缓冲区大小
} FlushThreadData;

// 多线程版本的缓存刷新函数
void* flush_thread(void* arg) {
    FlushThreadData* data = (FlushThreadData*)arg;
    
    // 绑定CPU核心
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(data->cpu_core, &cpuset);
    if (pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset) != 0) {
        perror("无法绑定核心");
        return NULL;
    }

    // 分配对齐的内存缓冲区（使用与主程序相同的对齐方式）
    char* buffer;
    const size_t alignment = sysconf(_SC_PAGESIZE);
    if (posix_memalign((void**)&buffer, alignment, data->buffer_size) != 0) {
        fprintf(stderr, "线程%d: 内存分配失败\n", data->cpu_core);
        return NULL;
    }

    // 写入整个缓冲区以触发缓存替换
    const size_t stride = 64; // 缓存行大小对齐的步长
    for (size_t offset = 0; offset < data->buffer_size; offset += stride) {
        memset(buffer + offset, 0, stride); 
    }

    free(buffer);
    return NULL;
}
// 修改后的flush_cache函数，参数为总缓冲区大小
void flush_cache(size_t buffer_size) {
    const int RANK = sysconf(_SC_NPROCESSORS_ONLN); // 获取当前CPU核心数
    pthread_t threads[RANK];
    FlushThreadData thread_data[RANK];
    // 创建并启动线程
    for (int i = 0; i < RANK; ++i) {
        thread_data[i] = (FlushThreadData){
            .cpu_core = i,
            .buffer_size = buffer_size
        };
        pthread_create(&threads[i], NULL, flush_thread, &thread_data[i]);
    }

    // 等待所有线程完成
    for (int i = 0; i < RANK; ++i) {
        pthread_join(threads[i], NULL);
    }
}
void* thread_main(void* arg) {
    ThreadData* data = (ThreadData*)arg;
    
    // 绑定CPU核心

    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(data->cpu_core, &cpuset);
    if (pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset) != 0) {
        perror("无法绑定核心");
        exit(EXIT_FAILURE);
    }
    size_t alloc_size =  data->alloc_size;
    //size_t alloc_size =  0;
    if (alloc_size>0){
        void *mem_block = mmap(NULL, alloc_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
            if (mem_block == MAP_FAILED) {
                perror("mmap失败");
                return NULL;
            }
        const size_t page_size = sysconf(_SC_PAGESIZE);
        for (size_t offset = 0; offset < alloc_size; offset += page_size) {
            memset((char*)mem_block + offset, 0, 1);
        }
        pthread_barrier_wait(&barrier);
        // 强制物理内存提交（COW机制下实际占用）
        //printf("正在初始化内存...\n");
        sleep(1); 
        clock_gettime(CLOCK_REALTIME, &data->start_time);
        execute_blocks(data->blocks, data->block_count,  data->cpu_core);
        clock_gettime(CLOCK_REALTIME, &data->end_time);
        //pthread_barrier_wait(&barrier);
        sleep(1); 
        madvise(mem_block, alloc_size, MADV_DONTNEED); 
        munmap(mem_block, alloc_size);               // 解除映射
    }else{
        sleep(1); 
        clock_gettime(CLOCK_REALTIME, &data->start_time);
        execute_blocks(data->blocks, data->block_count,  data->cpu_core);
        clock_gettime(CLOCK_REALTIME, &data->end_time);
        sleep(1); 
    }
    


    return NULL;
}

int main(int argc, char **argv) {
    if (argc != 2) {
        printf("用法: %s <config.json>\n", argv[0]);
        return 1;
    }

    int RANK = 96;
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
    // 计算每个线程的内存分配量
    const size_t total_mem = (size_t)(mem_size->valueint) * 1024 * 1024 * 1024; // MB转字节
    const size_t per_thread_mem = (size_t)(total_mem * mem_util->valuedouble) / RANK;
    int block_count = 0;
    cJSON* blocks_array = cJSON_GetObjectItemCaseSensitive(config, "blocks");
    BlockConfig* blocks = parse_config(blocks_array, &block_count);
    
    // 初始化屏障
    if (pthread_barrier_init(&barrier, NULL, RANK) != 0) {
        fprintf(stderr, "屏障初始化失败\n");
        return 1;
    }
    // 创建线程
    pthread_t threads[RANK];
    ThreadData thread_data[RANK];
    //flush_cache(1024*1024);
    for (int i = 0; i < RANK; i++) {

        thread_data[i] = (ThreadData){
            .blocks = blocks,
            .block_count = block_count,
            .cpu_core = i % RANK,
            .alloc_size = per_thread_mem
        };
        pthread_create(&threads[i], NULL, thread_main, &thread_data[i]);
    }

    // 等待所有线程完成
    for (int i = 0; i < RANK; i++) {
        pthread_join(threads[i], NULL);
    }
    pthread_barrier_destroy(&barrier);
    if (RANK > 0) { 
    // 控制台输出
    printf("%ld\n", 
            thread_data[0].start_time.tv_sec);
    printf("%ld\n",
            thread_data[0].end_time.tv_sec);

    // 文件输出
    FILE *fp = fopen("execution_timing.log", "w");
    if (fp) {
        fprintf(fp, "%ld\n", 
                thread_data[0].start_time.tv_sec);
        fprintf(fp, "%ld\n",
                thread_data[0].end_time.tv_sec);
        fclose(fp);
    } else {
        perror("无法写入时间统计文件");
    }
}
    // 清理资源
    free(blocks);
    cJSON_Delete(config);
    free(json_str);
    
    return 0;
}
