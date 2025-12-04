#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include "cJSON.h"
#include <pthread.h>
#include <string.h>
#include <sys/mman.h>
#include <sched.h>
#include <unistd.h>

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
    size_t alloc_size;  // 新增全局内存利用率

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
        
        if (strcmp(blocks[idx].type, "memory_block") == 0) {
            blocks[idx].stride = cJSON_GetNumberValue(cJSON_GetObjectItem(current_block, "stride"));
        } 
        else if (strcmp(blocks[idx].type, "sleep_block") == 0) {
            blocks[idx].iterations = cJSON_GetNumberValue(cJSON_GetObjectItem(current_block, "iterations"));
        } 
        else if (strcmp(blocks[idx].type, "add_block") == 0) {
        }
        idx++;
    }
    return blocks;
}



void execute_blocks(BlockConfig* blocks, int block_count) {
    for (int i = 0; i < block_count; ++i) {
        printf("执行块 %d: 类型=%s, 迭代次数=%ld\n", 
              i+1, blocks[i].type, blocks[i].iterations);
        
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
void flush_cache() {
    const size_t buffer_size = 192 * 1024 * 1024; // LLC 大小（假设为 192MB）
    char* buffer = malloc(buffer_size);
    if (buffer) {
        memset(buffer, 0, buffer_size); // 写入操作触发缓存替换
        free(buffer);
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
        // 强制物理内存提交（COW机制下实际占用）
        //printf("正在初始化内存...\n");
        execute_blocks(data->blocks, data->block_count);
        pthread_barrier_wait(&barrier);
        madvise(mem_block, alloc_size, MADV_DONTNEED); 
        munmap(mem_block, alloc_size);               // 解除映射
    }else{
        execute_blocks(data->blocks, data->block_count);
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
    
    for (int i = 0; i < RANK; i++) {
        //flush_cache();
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
    // 清理资源
    free(blocks);
    cJSON_Delete(config);
    free(json_str);
    
    return 0;
}
