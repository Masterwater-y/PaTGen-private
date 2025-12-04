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
//extern void access_memory_block(long N, long STRIDE);
extern void add_block(long iterations);
extern void div_block(long iterations);
extern void sleep_n(unsigned int seconds);

void access_memory_block(volatile char* buffer, size_t buffer_size, long iterations, size_t stride) {
    const size_t cache_line_size = 64;

    size_t offset = 0;
    for (long i = 0; i < iterations; ++i) {

        offset = (offset + stride) % buffer_size;
        char value = buffer[offset]; 
        (void)value;
        asm volatile("" ::: "memory"); // 编译器屏障
    }
}


typedef struct {
    char type[20];
    long iterations;
    long stride;
    int rank;
    long long mem_size;  // 新增内存大小参数（单位：字节）
    int start_thread;  // 新增：起始线程编号
    int end_thread;    // 新增：结束线程编号
} BlockConfig;

typedef struct {
    BlockConfig* blocks;
    int block_count;
    int cpu_core;
    
    struct timespec start_time;
    struct timespec end_time;
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
    int current_start = 0; // 动态计算起始位置
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
            cJSON* mem_size = cJSON_GetObjectItem(current_block, "mem_size");
            if (mem_size) {
                blocks[idx].mem_size = (long long) mem_size->valueint * 1024 * 1024;; // 假设配置单位为MB
            } else {
                blocks[idx].mem_size = 256 * 1024 * 1024; // 默认256MB
            }
        } 
        else if (strcmp(blocks[idx].type, "sleep_block") == 0) {
            blocks[idx].iterations = cJSON_GetNumberValue(cJSON_GetObjectItem(current_block, "iterations"));
        } 
        blocks[idx].start_thread = current_start;
        blocks[idx].end_thread = current_start + blocks[idx].rank - 1;
        current_start += blocks[idx].rank; // 更新下一个block的起始位置
        idx++;
    }
    return blocks;
}



void execute_blocks(ThreadData* data) {
    BlockConfig* blocks = data->blocks;
    int block_count = data->block_count;
    int thread_id = data->cpu_core;
            printf("thread=%d \n",thread_id);
    for (int i = 0; i < block_count; ++i) {

        if (thread_id >= blocks[i].start_thread && 
            thread_id <= blocks[i].end_thread) {  // 仅在满足条件时执行

            if (strcmp(blocks[i].type, "memory_block") == 0) {
                size_t per_thread_mem = (blocks[i].mem_size / blocks[i].rank) & ~(BLOCK_SIZE-1);
                
                // 分配线程专属内存
                void* thread_mem = NULL;
                if (posix_memalign(&thread_mem, BLOCK_SIZE, per_thread_mem) != 0) {
                    fprintf(stderr, "线程%d 内存分配失败: %zu MB\n", 
                           thread_id, per_thread_mem/(1024*1024));
                    continue;
                }
                // 初始化内存（可选）
                memset(thread_mem, 0, per_thread_mem);
                access_memory_block((volatile char*)thread_mem, 
                                    per_thread_mem,
                                  blocks[i].iterations, 
                                  blocks[i].stride);
            }
            else if (strcmp(blocks[i].type, "div_block") == 0) {
                div_block(blocks[i].iterations);
            }
            else if (strcmp(blocks[i].type, "add_block") == 0) {
                add_block(blocks[i].iterations);
            }
        }


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
    clock_gettime(CLOCK_REALTIME, &data->start_time);
    execute_blocks(data);
    clock_gettime(CLOCK_REALTIME, &data->end_time);


    


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
        thread_data[i] = (ThreadData){
            .blocks = blocks,
            .block_count = block_count,
            .cpu_core = i % RANK,
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
