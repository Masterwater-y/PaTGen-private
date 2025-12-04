#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include "cJSON.h"
#include <pthread.h>
#include <string.h>
#include <sys/mman.h>
#include <sched.h>

extern void access_memory_block(long N, long STRIDE);
extern void add_block(long iterations);
extern void div_block(long iterations);

typedef struct {
    char type[20];
    long iterations;
    long stride;
    double add_ratio;
    double div_ratio;
} BlockConfig;

typedef struct {
    BlockConfig* blocks;
    int block_count;
    int cpu_core;
} ThreadData;

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
        else if (strcmp(blocks[idx].type, "arith_block") == 0) {
            blocks[idx].add_ratio = cJSON_GetNumberValue(cJSON_GetObjectItem(current_block, "add_ratio"));
            blocks[idx].div_ratio = cJSON_GetNumberValue(cJSON_GetObjectItem(current_block, "div_ratio"));

            double sum = blocks[idx].add_ratio + blocks[idx].div_ratio;
            if (fabs(sum - 1.0) > 1e-6) {
                fprintf(stderr, "[Block %d] 比例错误: 总和应为1.0 (实际:%.4f)\n", idx+1, sum);
                exit(EXIT_FAILURE);
            }
        }
        idx++;
    }
    return blocks;
}

void execute_arith_block(const BlockConfig* cfg) {
    long add_iter = (long)(cfg->add_ratio * cfg->iterations);
    long div_iter = (long)(cfg->div_ratio * cfg->iterations);
    if (add_iter > 0) add_block(add_iter);
    if (div_iter > 0) div_block(div_iter);
}

void execute_blocks(BlockConfig* blocks, int block_count) {
    for (int i = 0; i < block_count; ++i) {
        printf("执行块 %d: 类型=%s, 迭代次数=%ld\n", 
              i+1, blocks[i].type, blocks[i].iterations);
        
        if (strcmp(blocks[i].type, "memory_block") == 0) {
            access_memory_block(blocks[i].iterations, blocks[i].stride);
        } 
        else if (strcmp(blocks[i].type, "arith_block") == 0) {
            execute_arith_block(&blocks[i]);
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

    execute_blocks(data->blocks, data->block_count);
    return NULL;
}

int main(int argc, char **argv) {
    if (argc != 3) {
        printf("用法: %s RANK <config.json>\n", argv[0]);
        return 1;
    }

    int RANK = atoi(argv[1]);
    char* json_str = read_config_file(argv[2]);
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
    BlockConfig* blocks = parse_config(config, &block_count);
    
    // 创建线程
    pthread_t threads[RANK];
    ThreadData thread_data[RANK];
    
    for (int i = 0; i < RANK; i++) {
        thread_data[i] = (ThreadData){
            .blocks = blocks,
            .block_count = block_count,
            .cpu_core = i % 96
        };
        pthread_create(&threads[i], NULL, thread_main, &thread_data[i]);
    }

    // 等待所有线程完成
    for (int i = 0; i < RANK; i++) {
        pthread_join(threads[i], NULL);
    }

    // 清理资源
    free(blocks);
    cJSON_Delete(config);
    free(json_str);
    
    return 0;
}
