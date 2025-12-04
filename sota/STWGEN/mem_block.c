#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <signal.h>
#include <time.h>

volatile sig_atomic_t running = 1;
void* memory_block = NULL;
size_t current_allocated = 0;

// 信号处理函数
void sig_handler(int signum) {
    running = 0;
}

// 读取内存配置文件（单位MB）
double* read_memory_profile(const char* filename, int* count) {
    FILE* fp = fopen(filename, "r");
    if (!fp) {
        perror("Failed to open memory profile");
        return NULL;
    }

    double* values = NULL;
    double value;
    int capacity = 0;
    *count = 0;
    char line[256];

    while (fgets(line, sizeof(line), fp)) {
        if (sscanf(line, "%lf", &value) != 1)
            continue;

        if (*count >= capacity) {
            capacity = capacity ? capacity*2 : 128;
            double* temp = realloc(values, capacity * sizeof(double));
            if (!temp) {
                fclose(fp);
                free(values);
                return NULL;
            }
            values = temp;
        }
        values[(*count)++] = value;
    }

    fclose(fp);
    return values;
}

// 调整内存分配（直接使用目标值）
void adjust_memory(size_t target_mb) {
    size_t target_bytes = target_mb * 1024 * 1024;
    if (current_allocated == 0) {
        if (target_bytes > 0) {
            memory_block = malloc(target_bytes);
            memset(memory_block, 0, target_bytes);
        }
    } else {
        if (target_bytes == 0) {
            free(memory_block);
            memory_block = NULL;
        } else {
            void* new_block = realloc(memory_block, target_bytes);
            if (new_block) {
                memory_block = new_block;
                if (target_bytes > current_allocated) {
                    memset((char*)memory_block + current_allocated, 0, 
                          target_bytes - current_allocated);
                }
            }
        }
    }
    
    current_allocated = target_bytes;
}

int main(int argc, char** argv) {
    if (argc != 2) {
        fprintf(stderr, "Usage: %s <memory_profile.txt>\n", argv[0]);
        return 1;
    }

    signal(SIGINT, sig_handler);
    signal(SIGTERM, sig_handler);

    // 读取内存配置文件
    int num_steps;
    double* profile = read_memory_profile(argv[1], &num_steps);
    if (!profile || num_steps == 0) {
        fprintf(stderr, "Invalid memory profile\n");
        return 1;
    }

    struct timespec ts = {.tv_sec = 1, .tv_nsec = 0};
    
    for (int i = 0; i < num_steps && running; ++i) {
        adjust_memory((size_t)profile[i]);
        nanosleep(&ts, NULL);
    }

    // 清理
    if (memory_block) free(memory_block);
    free(profile);
    return 0;
}
