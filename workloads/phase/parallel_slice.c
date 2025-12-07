/* modified_workload_runner.c
   在你的原始代码基础上做最小改动，加入 slice-based memory isolation。
   直接替换原文件并编译。
*/

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
#include <stdint.h>  // uint32_t 等
#include <time.h>


#define BLOCK_SIZE 4096  // 对齐的IO块大小
#define TIME_PER_ITER 0.1 // 每个迭代对应0.02秒

extern void add_block(long iterations);
extern void div_block(long iterations);
extern void sqrt_block(long iterations);

/* ---------- 参数：调整隔离强度（可按需修改） ---------- */
#define GAP_BYTES (16UL * 1024 * 1024) // 默认 slice 之间间隔 16MB（可改 32MB/64MB）
/* ----------------------------------------------------- */

void ari_block(int iterations, int chain_depth) {
    uint64_t sum_parallel[4] = {0}; // 并行累加器
    volatile uint64_t sum_chain = 0;         // 串行累加器
    volatile uint64_t dummy;        // 防优化存储
    
    for (int i = 0; i < iterations; ++i) {
        volatile uint64_t temp = i;
        for (int d=0; d<chain_depth; d++) {
            temp = (temp << (d%4)) + (d ^ 0x3F); // 深度依赖链
        }
        sum_chain += temp;

    }
    
    // 强制输出防止优化
    dummy = sum_parallel[0] + sum_parallel[1] 
          + sum_parallel[2] + sum_parallel[3] + sum_chain;
}

/* 新增：按 slice 的内存访问函数（每个 slice 有独立 offset） */
void access_memory_block_slice(volatile char* base, size_t slice_base, size_t slice_size, long iterations, size_t stride, size_t *offset_ptr) {
    const size_t cache_line_size = 64;
    size_t offset = *offset_ptr % slice_size;
    for (long i = 0; i < iterations; ++i) {
        offset = (offset + stride) % slice_size;
        char value = base[slice_base + offset];
        (void)value;
        asm volatile("" ::: "memory");
    }
    *offset_ptr = offset;
}

/* 原来的 access_memory_block 保留（兼容），但主逻辑现在使用 access_memory_block_slice */
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
    snprintf(tempfile, sizeof(tempfile), "diskio_%d_%lu.tmp", 
            getpid(), (unsigned long)pthread_self());

    int fd = open(tempfile, O_WRONLY | O_CREAT | O_TRUNC | O_EXCL | O_DIRECT, 0666);
    if (fd == -1) {
        fprintf(stderr, "文件创建失败: %s (%s)\n", tempfile, strerror(errno));
        return;
    }

    char* buf;
    const size_t block_size = 4 * 1024;  // 4KB对齐块
    if (posix_memalign((void**)&buf, block_size, block_size) != 0) {
        close(fd);
        return;
    }
    memset(buf, 0, block_size);

    const double total_time = iterations * TIME_PER_ITER;  // 每个迭代0.02秒
    struct timespec start, now;
    clock_gettime(CLOCK_MONOTONIC, &start);
    
    do {
        lseek(fd, 0, SEEK_SET);
        if (write(fd, buf, block_size) != block_size) {
            perror("写入失败");
            break;
        }
        fdatasync(fd);  // 强制落盘
        
        clock_gettime(CLOCK_MONOTONIC, &now);
    } while((now.tv_sec - start.tv_sec) + 
           (now.tv_nsec - start.tv_nsec) * 1e-9 < total_time);

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
    int delay;
} BlockConfig;

typedef struct {
    BlockConfig* blocks;
    int num_blocks;
} BlockGroup;

typedef struct {
    BlockConfig block;
    int block_count;
    int cpu_core;
    size_t alloc_size;  // 原先每线程分配大小（字节）
    BlockGroup* groups;
    void* mem_block;    // 指向 slab base（若使用 slice 则为 slab）
    size_t mem_offset;  // 旧单缓冲 offset（兼容）
    struct timespec start_time; 
    struct timespec end_time;   
    int num_groups;
    struct timespec stage_start[100]; 
    struct timespec stage_end[100];

    /* 新增字段 */
    int num_mem_slices;    // 每线程将使用多少个 slice（等于该线程将要执行的 memory_block 数）
    size_t slice_size;     // 每个 slice 的大小（对齐到 cache line）
    size_t *mem_offsets;   // 每个 slice 的 offset（独立）
    int next_slice_idx;    // 轮询选择 slice
    size_t slab_alloc_size; // 实际 mmap 的 slab 大小，用于 munmap
} ThreadData;

static pthread_barrier_t barrier;

/* 读取配置文件 */
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

/* 解析 blocks（与原来一致） */
BlockConfig* parse_config(const cJSON* root, int* block_count) {
    *block_count = cJSON_GetArraySize(root);
    BlockConfig* blocks = malloc(*block_count * sizeof(BlockConfig));
    
    int idx = 0;
    cJSON* current_block = NULL;
    int s_idx = 0;
    cJSON_ArrayForEach(current_block, root) {
        strncpy(blocks[idx].type, 
               cJSON_GetStringValue(cJSON_GetObjectItem(current_block, "type")),
               sizeof(blocks[idx].type) - 1);
        blocks[idx].iterations = cJSON_GetNumberValue(cJSON_GetObjectItem(current_block, "iterations"));
        blocks[idx].rank = cJSON_GetNumberValue(cJSON_GetObjectItem(current_block, "rank"));
        cJSON* delay_item = cJSON_GetObjectItemCaseSensitive(current_block, "delay");
        blocks[idx].delay = cJSON_IsNumber(delay_item) ? delay_item->valuedouble : 0.0;
        blocks[idx].s_thread = s_idx;
        s_idx = s_idx + blocks[idx].rank;
        if (strcmp(blocks[idx].type, "memory_block") == 0) {
            blocks[idx].stride = cJSON_GetNumberValue(cJSON_GetObjectItem(current_block, "stride"));
        } 
        else if (strcmp(blocks[idx].type, "ari_block") == 0) {
            blocks[idx].factor = cJSON_GetNumberValue(cJSON_GetObjectItem(current_block, "factor"));
        }
        else if (strcmp(blocks[idx].type, "sleep_block") == 0) {
            blocks[idx].iterations = cJSON_GetNumberValue(cJSON_GetObjectItem(current_block, "iterations"));
        } 

        idx++;
    }
    return blocks;
}

/* ---------- 执行阶段：当遇到 memory_block 时使用 slice 访问 ---------- */
void execute_blocks(ThreadData* data) {
    BlockGroup* groups = data->groups;
    for (int stage=0; stage<data->num_groups; ++stage){
        BlockConfig* blocks = groups[stage].blocks;
        int thread_rank = data->cpu_core;
        clock_gettime(CLOCK_REALTIME, &data->stage_start[stage]);
        for (int i=0; i<groups[stage].num_blocks; i++){

            BlockConfig block = blocks[i];

            if (thread_rank>=block.s_thread && thread_rank < block.s_thread+block.rank) {  // 仅在满足条件时执行
                if (block.delay > 0) {
                    sleep(block.delay); // 延迟指定秒数
                }
                if (strcmp(block.type, "memory_block") == 0) {
                    if (data->num_mem_slices > 0) {
                        // 选择 slice（轮询）
                        int slice_idx = data->next_slice_idx % data->num_mem_slices;
                        data->next_slice_idx++;

                        size_t per_slot = data->slice_size + GAP_BYTES;
                        size_t slice_base = (size_t)slice_idx * per_slot;

                        // 调用按 slice 的访问（每个 slice 有自己的 offset）
                        access_memory_block_slice((volatile char*)data->mem_block, slice_base, data->slice_size, block.iterations, block.stride, &data->mem_offsets[slice_idx]);
                    } else {
                        // 回退：若未启用 slice（num_mem_slices==0），使用旧逻辑
                        access_memory_block((volatile char*)data->mem_block, data->alloc_size, block.iterations, block.stride, &data->mem_offset);
                    }
                } 

                else if (strcmp(block.type, "div_block") == 0) {
                    div_block(block.iterations);
                }
                else if (strcmp(block.type, "add_block") == 0) {
                    add_block(block.iterations);
            
                }else if (strcmp(block.type, "ari_block") == 0) {
                    ari_block(block.iterations,block.factor);
                }
                else if (strcmp(block.type, "disk_block") == 0) {
                    disk_io(block.iterations);
                }
                else if (strcmp(block.type, "sqrt_block") == 0) {
                    sqrt_block(block.iterations);
                }
                
            }
        }
        pthread_barrier_wait(&barrier);
        clock_gettime(CLOCK_REALTIME, &data->stage_end[stage]);
    }
}

/* ---------- thread_main：分配 slab、初始化 slice offset，执行 blocks ---------- */
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
        // 调整alloc_size为缓存行大小的整数倍（保持原逻辑）
        alloc_size = (alloc_size *64) / (sizeof(size_t)  +64);
        alloc_size = ((alloc_size + cache_line_size - 1) / cache_line_size) * cache_line_size;
        data->alloc_size = alloc_size;

        if (data->num_mem_slices > 0) {
            // 计算每个 slice 大小（尽量均分）
            size_t slice_size = alloc_size / (size_t)data->num_mem_slices;
            if (slice_size < cache_line_size) slice_size = cache_line_size;
            // 对齐 slice_size 到 cache line
            slice_size = ((slice_size + cache_line_size - 1) / cache_line_size) * cache_line_size;
            data->slice_size = slice_size;

            // 为了保证 slices 彼此相隔 GAP_BYTES，按 slot 计算 slab 大小
            size_t per_slot = data->slice_size + GAP_BYTES;
            // 计算 slab 总大小，并对齐到 page
            size_t slab_size = (size_t)data->num_mem_slices * per_slot;
            long page = sysconf(_SC_PAGESIZE);
            size_t slab_alloc = (slab_size + page - 1) & ~(page - 1);
            data->slab_alloc_size = slab_alloc;

            void *slab = mmap(NULL, slab_alloc, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
            if (slab == MAP_FAILED) {
                perror("mmap slab failed");
                return NULL;
            }
            data->mem_block = slab;

            // 触碰每个 slice 的页面以触发物理页分配（只写一处每 cache line）
            volatile char* base = (volatile char*)slab;
            for (int s = 0; s < data->num_mem_slices; ++s) {
                size_t slice_base = (size_t)s * per_slot;
                for (size_t off = 0; off < data->slice_size; off += cache_line_size) {
                    base[slice_base + off] = (char)(s + off);
                }
            }
            // 分配每-slice offset 数组
            data->mem_offsets = malloc(sizeof(size_t) * data->num_mem_slices);
            for (int s = 0; s < data->num_mem_slices; ++s) data->mem_offsets[s] = 0;
            data->next_slice_idx = 0;
        } else {
            // 未启用 slice：按原逻辑分配单一区域
            void *mem_block = mmap(NULL, alloc_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
            if (mem_block == MAP_FAILED) {
                perror("mmap失败");
                return NULL;
            }
            data->mem_block = mem_block;
            // 原来的随机化与逐行访问（保留）
            size_t num_lines = alloc_size / cache_line_size;
            size_t *offsets = malloc(num_lines * sizeof(size_t));
            for (size_t i = 0; i < num_lines; ++i) offsets[i] = i * cache_line_size;
            unsigned seed = data->cpu_core;
            for (size_t i = 0; i < num_lines - 1; i++) {
                size_t j = i + rand_r(&seed) % (num_lines - i);
                size_t tmp = offsets[i];
                offsets[i] = offsets[j];
                offsets[j] = tmp;
            }
            volatile char *ptr = (volatile char *)data->mem_block;
            for (size_t i = 0; i < num_lines; ++i) {
                const size_t offset = offsets[i];
                memset((void*)(ptr + offset), 0, cache_line_size);
                __sync_synchronize();
            }
            free(offsets);
        }

        sqrt_block(10000000);
        pthread_barrier_wait(&barrier);
        sleep(2);
        clock_gettime(CLOCK_REALTIME, &data->start_time);
        execute_blocks(data);
        clock_gettime(CLOCK_REALTIME, &data->end_time);
        sleep(2);

        // cleanup
        if (data->num_mem_slices > 0) {
            if (data->mem_offsets) free(data->mem_offsets);
            if (data->mem_block) munmap(data->mem_block, data->slab_alloc_size);
        } else {
            if (data->mem_block) munmap(data->mem_block, alloc_size);
        }
    }else{
        clock_gettime(CLOCK_REALTIME, &data->start_time);
        execute_blocks(data);
        clock_gettime(CLOCK_REALTIME, &data->end_time);
    }

    return NULL;
}
double ts_to_ms(struct timespec* ts) {
    return ts->tv_sec + ts->tv_nsec / 1e9;
}


/* ---------------- main ---------------- */
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
    const size_t total_mem = (size_t)(mem_size->valueint) * 1024 * 1024 * 1024; // GB->bytes? 你原来是 MB->GB，但我保持你的原写法
    size_t per_thread_mem = (size_t)(total_mem * mem_util->valuedouble) / RANK;

    int block_count = 0;
    cJSON* blocks_array = cJSON_GetObjectItemCaseSensitive(config, "blocks");
    int num_groups = cJSON_GetArraySize(blocks_array);
    BlockGroup* groups = malloc(num_groups * sizeof(BlockGroup));
    for (int i = 0; i < num_groups; ++i) {
        cJSON* group_json = cJSON_GetArrayItem(blocks_array, i);
        int num_blocks = cJSON_GetArraySize(group_json);
        groups[i].blocks = parse_config(group_json, &groups[i].num_blocks);
    }

    // 初始化屏障
    if (pthread_barrier_init(&barrier, NULL, RANK) != 0) {
        fprintf(stderr, "屏障初始化失败\n");
        return 1;
    }

    pthread_t threads[RANK];
    ThreadData thread_data[RANK];
    size_t buffer_size = 1024 * 1024 * 1024;
    if (per_thread_mem == 0){
        per_thread_mem = buffer_size /RANK;
    }

    /* 计算每个线程将要执行的 memory_block 数目，以决定 num_mem_slices */
    int *mem_blocks_per_thread = calloc(RANK, sizeof(int));
    for (int t = 0; t < RANK; ++t) {
        int cnt = 0;
        for (int g = 0; g < num_groups; ++g) {
            BlockConfig* blks = groups[g].blocks;
            for (int b = 0; b < groups[g].num_blocks; ++b) {
                if (strcmp(blks[b].type, "memory_block") == 0) {
                    if (t >= blks[b].s_thread && t < blks[b].s_thread + blks[b].rank) {
                        cnt++;
                    }
                }
            }
        }
        // 如果没有任何 memory_block（cnt==0），保留为0（回退使用单缓冲区）
        mem_blocks_per_thread[t] = cnt;
    }

    /* 创建线程并把 num_mem_slices 放入 thread_data */
    for (int i = 0; i < RANK; i++) { 
        thread_data[i] = (ThreadData){
            .cpu_core = i % RANK,
            .alloc_size = per_thread_mem,
            .mem_offset = 0, // 初始化为0
            .groups = groups,
            .num_groups = num_groups,
            .num_mem_slices = mem_blocks_per_thread[i],
            .slice_size = 0,
            .mem_offsets = NULL,
            .next_slice_idx = 0,
            .slab_alloc_size = 0
        };
        pthread_create(&threads[i], NULL, thread_main, &thread_data[i]);
    }

    for (int i = 0; i < RANK; i++) {
        pthread_join(threads[i], NULL);
    }
    pthread_barrier_destroy(&barrier);

    if (RANK > 0) { 

        
        printf("%ld\n", 
                thread_data[0].start_time.tv_sec);
        printf("%ld\n",
                thread_data[0].end_time.tv_sec);

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

        FILE* fp2 = fopen("phase_time.csv", "w");
        if (fp2) {
            fprintf(fp2, "start_time,end_time,duration\n");
            for (int stage = 0; stage < num_groups; stage++) {
                fprintf(fp2, "%ld,%ld,%ld\n", 
                    thread_data[0].stage_start[stage].tv_sec, 
                    thread_data[0].stage_end[stage].tv_sec,
                    thread_data[0].stage_end[stage].tv_sec - thread_data[0].stage_start[stage].tv_sec);
            }
            fclose(fp2);
        }
    }

    free(mem_blocks_per_thread);
    free(groups);
    cJSON_Delete(config);
    free(json_str);

    return 0;
}
