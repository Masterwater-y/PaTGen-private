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
extern void sqrt_block(long iterations);

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
    size_t alloc_size;
    void* mem_block;
    struct timespec start_time;
    struct timespec end_time;
    struct timespec* phase_timestamps;
    int phase_count;
    int current_phase;
    int* phases;  // 新增：存储阶段列表
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


// 解析phase.json文件，获取阶段列表
int* parse_phase_config(const char* filename, int* phase_count) {
    FILE* fp = fopen(filename, "r");
    if (!fp) {
        fprintf(stderr, "错误: 无法读取phase配置文件\n");
        return NULL;
    }
    
    // 简单解析JSON数组，假设格式为[num, num, ...]
    fseek(fp, 0, SEEK_END);
    long len = ftell(fp);
    fseek(fp, 0, SEEK_SET);
    
    char* buf = malloc(len + 1);
    fread(buf, 1, len, fp);
    buf[len] = '\0';
    fclose(fp);
    
    cJSON* phase_json = cJSON_Parse(buf);
    free(buf);
    if (!phase_json) {
        fprintf(stderr, "错误: 无效的phase JSON格式\n");
        return NULL;
    }
    
    *phase_count = cJSON_GetArraySize(phase_json);
    int* phases = malloc(*phase_count * sizeof(int));
    
    cJSON* phase_item = NULL;
    int idx = 0;
    cJSON_ArrayForEach(phase_item, phase_json) {
        phases[idx++] = cJSON_GetNumberValue(phase_item);
    }
    
    cJSON_Delete(phase_json);
    return phases;
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



void execute_blocks(ThreadData* data) {
    BlockConfig* blocks = data->blocks;
    int block_count = data->block_count;
    int thread_rank = data->cpu_core;
    clock_gettime(CLOCK_REALTIME, &data->phase_timestamps[0]);
    data->current_phase = 1;
    pthread_barrier_wait(&barrier); // 等待所有线程准备好
    for (int i = 0; i < block_count; ++i) {
        if (thread_rank < blocks[i].rank) {  // 仅在满足条件时执行
            if (strcmp(blocks[i].type, "memory_block") == 0) {
                access_memory_block((volatile char*)data->mem_block, 
                                  data->alloc_size, 
                                  blocks[i].iterations, 
                                  blocks[i].stride);
                //access_memory_block(blocks[i].iterations, blocks[i].stride);
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
            }else if (strcmp(blocks[i].type, "sqrt_block") == 0) {
                sqrt_block(blocks[i].iterations);
            }
        }
        // 所有线程在此同步，无论是否执行当前block
        pthread_barrier_wait(&barrier);
        for (int p = 0; p < data->phase_count; p++) {
            if (i + 1 == data->phases[p]) {
                clock_gettime(CLOCK_REALTIME, &data->phase_timestamps[data->current_phase]);
                data->current_phase++;
                break;
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
    size_t alloc_size =  data->alloc_size;

    if (alloc_size>0){
        const size_t cache_line_size = sysconf(_SC_LEVEL1_DCACHE_LINESIZE);
        // 调整alloc_size为缓存行大小的整数倍
        alloc_size = (alloc_size *64) / (sizeof(size_t)  +64);
        alloc_size = ((alloc_size + cache_line_size - 1) / cache_line_size) * cache_line_size;
        data->alloc_size = alloc_size;
        void *mem_block = mmap(NULL, alloc_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
            if (mem_block == MAP_FAILED) {
                perror("mmap失败");
                return NULL;
            }
        data->mem_block = mem_block;
        
        size_t num_lines = alloc_size / cache_line_size;
        size_t *offsets = malloc(num_lines * sizeof(size_t));
        for (size_t i = 0; i < num_lines; ++i) {
            offsets[i] = i * cache_line_size;
        }

        // 打乱访问顺序以避免预取

        unsigned seed = data->cpu_core;  // 使用核心号作为随机种子
        for (size_t i = 0; i < num_lines - 1; i++) {
            size_t j = i + rand_r(&seed) % (num_lines - i);
            size_t tmp = offsets[i];
            offsets[i] = offsets[j];
            offsets[j] = tmp;
        }

        // 按随机顺序逐行访问内存
        volatile char *ptr = (volatile char *)mem_block;

        for (size_t i = 0; i < num_lines; ++i) {
            const size_t offset = offsets[i];
        
            // 写入并立即读取，防止编译器优化
            memset((void*)(ptr + offset), 0, cache_line_size);
            // 使用硬件内存屏障
            __sync_synchronize();

        }
        pthread_barrier_wait(&barrier);
        sleep(2);
        clock_gettime(CLOCK_REALTIME, &data->start_time);
        execute_blocks(data);
        clock_gettime(CLOCK_REALTIME, &data->end_time);
        sleep(2);
        madvise(mem_block, alloc_size, MADV_DONTNEED); 
        munmap(mem_block, alloc_size);               // 解除映射
        //free(offsets);
    }else{
        clock_gettime(CLOCK_REALTIME, &data->start_time);
        execute_blocks(data);
        clock_gettime(CLOCK_REALTIME, &data->end_time);

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
    size_t per_thread_mem = (size_t)(total_mem * mem_util->valuedouble) / RANK;
    int block_count = 0;
    cJSON* blocks_array = cJSON_GetObjectItemCaseSensitive(config, "blocks");
    BlockConfig* blocks = parse_config(blocks_array, &block_count);
    int* phases = NULL;
    int phase_count = 0;
    if (RANK > 0) {
        phases = parse_phase_config("./config_files/phase.json", &phase_count);
        if (!phases) {
            fprintf(stderr, "错误: 解析phase配置失败\n");
            free(json_str);
            cJSON_Delete(config);
            free(blocks);
            return 1;
        }
    }
    // 初始化屏障
    if (pthread_barrier_init(&barrier, NULL, RANK) != 0) {
        fprintf(stderr, "屏障初始化失败\n");
        return 1;
    }
    // 创建线程
    pthread_t threads[RANK];
    ThreadData thread_data[RANK];
    size_t buffer_size = 1024 * 1024 * 1024;
    if (per_thread_mem == 0){
        per_thread_mem = buffer_size /RANK;
    }
    for (int i = 0; i < RANK; i++) {
        thread_data[i] = (ThreadData){
            .blocks = blocks,
            .block_count = block_count,
            .cpu_core = i % RANK,
            .alloc_size = per_thread_mem,
            .phase_timestamps = NULL,
            .phase_count = phase_count,
            .current_phase = 0,
            .phases = phases  // 所有线程共享phases数组
        };
        // 为每个线程分配时间戳存储
        if (phase_count > 0) {
            thread_data[i].phase_timestamps = malloc((phase_count + 1) * sizeof(struct timespec));
            if (!thread_data[i].phase_timestamps) {
                fprintf(stderr, "内存分配失败\n");
                // 错误处理
                exit(1);
            }
        }
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

        FILE *fp1 = fopen("phase_time.csv", "w");
        if (fp1) {
            fprintf(fp1, "phase,start_time,duration\n");

            for (int i = 0; i < phase_count; i++) {
                long duration = thread_data[0].phase_timestamps[i+1].tv_sec - thread_data[0].phase_timestamps[i].tv_sec;
                fprintf(fp1, "%d,%ld,%ld\n", i, 
                        thread_data[0].phase_timestamps[i].tv_sec,
                        duration);
            }
            fclose(fp1);
        } else {
            perror("无法写入phase.csv文件");
        }
    }
    // 清理资源
    free(blocks);
    cJSON_Delete(config);
    free(json_str);

    return 0;
}
