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
#include <stdint.h>

#define BLOCK_SIZE 4096
#define TIME_PER_ITER 0.1
extern void add_block(long iterations);
extern void div_block(long iterations);

void ari_block(int iterations, int chain_depth) {
    uint64_t sum_parallel[4] = {0};
    volatile uint64_t sum_chain = 0;
    volatile uint64_t dummy;

    for (int i = 0; i < iterations; ++i) {
        volatile uint64_t temp = i;
        for (int d=0; d<chain_depth; d++) {
            temp = (temp << (d%4)) + (d ^ 0x3F);
        }
        sum_chain += temp;
    }
    dummy = sum_parallel[0] + sum_parallel[1] 
          + sum_parallel[2] + sum_parallel[3] + sum_chain;
}

void access_memory_block(volatile char* buffer, size_t buffer_size, long iterations, size_t stride, size_t* offset) {
    const size_t cache_line_size = 64;
    for (long i = 0; i < iterations; ++i) {
        *offset = (*offset + stride) % buffer_size;
        char value = buffer[*offset]; 
        (void)value;
        asm volatile("" ::: "memory"); // 编译器屏障
    }

}

void disk_io(int iterations) {
    char tempfile[64];
    snprintf(tempfile, sizeof(tempfile), "diskio_%d_%lu.tmp", getpid(), (unsigned long)pthread_self());

    int fd = open(tempfile, O_WRONLY | O_CREAT | O_TRUNC | O_EXCL | O_DIRECT, 0666);
    if (fd == -1) {
        fprintf(stderr, "文件创建失败: %s (%s)\n", tempfile, strerror(errno));
        return;
    }

    char* buf;
    const size_t block_size = 4 * 1024;
    if (posix_memalign((void**)&buf, block_size, block_size) != 0) {
        close(fd);
        return;
    }
    memset(buf, 0, block_size);

    const double total_time = iterations * TIME_PER_ITER;
    struct timespec start, now;
    clock_gettime(CLOCK_MONOTONIC, &start);
    
    do {
        lseek(fd, 0, SEEK_SET);
        if (write(fd, buf, block_size) != block_size) {
            perror("写入失败");
            break;
        }
        fdatasync(fd);
        
        clock_gettime(CLOCK_MONOTONIC, &now);
    } while((now.tv_sec - start.tv_sec) + (now.tv_nsec - start.tv_nsec) * 1e-9 < total_time);

    free(buf);
    close(fd);
    remove(tempfile);
}

typedef struct {
    char type[20];
    long iterations;
    long stride;
    int s_thread;
    int rank;
    int factor;
} BlockConfig;

typedef struct {
    BlockConfig* blocks;
    int num_blocks;
} BlockGroup;

typedef struct {
    BlockGroup* groups;
    int num_groups;
    int cpu_core;
    size_t alloc_size;
    void* mem_block;
    size_t mem_offset;
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

BlockConfig* parse_group_config(cJSON* group_json, int num_blocks) {
    BlockConfig* blocks = malloc(num_blocks * sizeof(BlockConfig));
    int s_thread = 0;

    for (int i = 0; i < num_blocks; ++i) {
        cJSON* block_json = cJSON_GetArrayItem(group_json, i);
        strncpy(blocks[i].type, cJSON_GetStringValue(cJSON_GetObjectItem(block_json, "type")), sizeof(blocks[i].type) - 1);
        blocks[i].iterations = cJSON_GetNumberValue(cJSON_GetObjectItem(block_json, "iterations"));
        blocks[i].rank = cJSON_GetNumberValue(cJSON_GetObjectItem(block_json, "rank"));
        blocks[i].s_thread = s_thread;
        s_thread += blocks[i].rank;

        if (strcmp(blocks[i].type, "memory_block") == 0) {
            blocks[i].stride = cJSON_GetNumberValue(cJSON_GetObjectItem(block_json, "stride"));
        } else if (strcmp(blocks[i].type, "ari_block") == 0) {
            blocks[i].factor = cJSON_GetNumberValue(cJSON_GetObjectItem(block_json, "factor"));
        }
    }
    return blocks;
}



void* thread_main(void* arg) {
    ThreadData* data = (ThreadData*)arg;
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(data->cpu_core, &cpuset);
    if (pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset) != 0) {
        perror("无法绑定核心");
        exit(EXIT_FAILURE);
    }
    size_t alloc_size = data->alloc_size;
    if (alloc_size > 0) {
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

    }
    pthread_barrier_wait(&barrier);
    clock_gettime(CLOCK_REALTIME, &data->start_time);

    
    for (int stage = 0; stage < data->num_groups; ++stage) {

        BlockGroup group = data->groups[stage];
        for (int i = 0; i < group.num_blocks; ++i) {
            BlockConfig block = group.blocks[i];
            if (data->cpu_core >= block.s_thread && data->cpu_core < block.s_thread + block.rank) {
                printf("cpu=%d, type=%s \n", data->cpu_core, block.type);
                if (strcmp(block.type, "memory_block") == 0) {
                    access_memory_block((volatile char*)data->mem_block, data->alloc_size, block.iterations, block.stride, &data->mem_offset);
                    printf("core%d access finish\n",data->cpu_core);
                } else if (strcmp(block.type, "div_block") == 0) {
                    div_block(block.iterations);
                    printf("core%d div finish\n",data->cpu_core);
                } else if (strcmp(block.type, "add_block") == 0) {
                    add_block(block.iterations);
                } else if (strcmp(block.type, "ari_block") == 0) {
                    ari_block(block.iterations, block.factor);
                } else if (strcmp(block.type, "disk_block") == 0) {
                    disk_io(block.iterations);
                }
            }
        }
        pthread_barrier_wait(&barrier);
    }

    clock_gettime(CLOCK_REALTIME, &data->end_time);
    if (alloc_size > 0) {
        madvise(data->mem_block, data->alloc_size, MADV_DONTNEED);
        munmap(data->mem_block, data->alloc_size);
    }
    return NULL;
}

int main(int argc, char **argv) {
    if (argc != 2) {
        printf("用法: %s <config.json>\n", argv[0]);
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
        cJSON_Delete(config);
        return 1;
    }

    cJSON* mem_util = cJSON_GetObjectItemCaseSensitive(global, "memory_util");
    cJSON* mem_size = cJSON_GetObjectItemCaseSensitive(global, "memory_size");
    size_t total_mem = (size_t)mem_size->valueint * 1024 * 1024 * 1024;
    size_t per_thread_mem = (size_t)(total_mem * mem_util->valuedouble) / sysconf(_SC_NPROCESSORS_ONLN);

    cJSON* blocks_array = cJSON_GetObjectItemCaseSensitive(config, "blocks");
    int num_groups = cJSON_GetArraySize(blocks_array);
    printf("num_groups= %d\n",num_groups);
    BlockGroup* groups = malloc(num_groups * sizeof(BlockGroup));

    for (int i = 0; i < num_groups; ++i) {
        cJSON* group_json = cJSON_GetArrayItem(blocks_array, i);
        int num_blocks = cJSON_GetArraySize(group_json);
        groups[i].blocks = parse_group_config(group_json, num_blocks);
        groups[i].num_blocks = num_blocks;
        printf("groups[i].num_blocks= %d\n",groups[i].num_blocks);
        
    }

    int RANK = sysconf(_SC_NPROCESSORS_ONLN);

    pthread_barrier_init(&barrier, NULL, RANK);

    pthread_t threads[RANK];
    ThreadData thread_data[RANK];

    for (int i = 0; i < RANK; ++i) {
        thread_data[i] = (ThreadData){
            .groups = groups,
            .num_groups = num_groups,
            .cpu_core = i,
            .alloc_size = per_thread_mem,
            .mem_offset = 0
        };
        pthread_create(&threads[i], NULL, thread_main, &thread_data[i]);
    }

    for (int i = 0; i < RANK; ++i) {
        pthread_join(threads[i], NULL);
    }

    pthread_barrier_destroy(&barrier);
    printf("%ld\n%ld\n", thread_data[0].start_time.tv_sec, thread_data[0].end_time.tv_sec);

    FILE *fp = fopen("execution_timing.log", "w");
    if (fp) {
        fprintf(fp, "%ld\n%ld\n", thread_data[0].start_time.tv_sec, thread_data[0].end_time.tv_sec);
        fclose(fp);
    }

    for (int i = 0; i < num_groups; ++i) {
        free(groups[i].blocks);
    }
    free(groups);
    free(json_str);
    cJSON_Delete(config);

    return 0;
}
