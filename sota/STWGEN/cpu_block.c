#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>
#include <unistd.h>
#include <math.h>
#include <time.h>
#include <errno.h>

typedef struct {
    pthread_mutex_t mutex;
    double current_util;  // 当前CPU利用率
    int total_cores;      // 总核心数
} GlobalControl;

typedef struct {
    GlobalControl* global_ctrl;
    unsigned long loop_base;
    volatile int running;
    int thread_id;
} ThreadParams;

// 计算密集型循环
void compute_loop(unsigned long iterations) {
    volatile double sum = 0.0;
    for (unsigned long i = 0; i < iterations; ++i) {
        sum += sqrt(i + 1);  // 增加计算复杂度
    }
}

// 校准计算循环次数
unsigned long calibrate_compute() {
    struct timespec start, end;
    unsigned long base_loops = 1e6;

    while (1) {
        clock_gettime(CLOCK_MONOTONIC, &start);
        compute_loop(base_loops);
        clock_gettime(CLOCK_MONOTONIC, &end);

        double elapsed = (end.tv_sec - start.tv_sec) +
                       (end.tv_nsec - start.tv_nsec) * 1e-9;
        
        if (elapsed >= 0.95 && elapsed <= 1.05) break;
        base_loops = (unsigned long)(base_loops * (1.0 / elapsed));
    }
    return base_loops;
}

// 工作线程函数
void* cpu_worker(void* arg) {
    ThreadParams* params = (ThreadParams*)arg;
    GlobalControl* ctrl = params->global_ctrl;

    while (params->running) {
        // 获取当前CPU利用率设置
        pthread_mutex_lock(&ctrl->mutex);
        double util = ctrl->current_util;
        pthread_mutex_unlock(&ctrl->mutex);

        // 计算阶段
        if (util > 0.0) {
            compute_loop((unsigned long)(params->loop_base * util));
        }

        // 睡眠阶段
        double sleep_duration = 1.0 - util;
        struct timespec ts = {
            .tv_sec = (time_t)sleep_duration,
            .tv_nsec = (long)((sleep_duration - (time_t)sleep_duration) * 1e9)
        };
        nanosleep(&ts, NULL);
    }
    return NULL;
}

// 读取利用率文件
double* read_util_file(const char* filename, int* count) {
    FILE* fp = fopen(filename, "r");
    if (!fp) {
        perror("fopen");
        return NULL;
    }

    double* utils = NULL;
    char line[256];
    int capacity = 0;
    *count = 0;

    while (fgets(line, sizeof(line), fp)) {
        // 跳过注释和空行
        if (line[0] == '#' || line[0] == '\n') continue;

        char* endptr;
        double value = strtod(line, &endptr);
        value = value / 100;
        // 有效性检查
        if (endptr == line || value <= 0.0 || value >= 1.0) {
            fprintf(stderr, "Invalid value: %s", line);
            continue;
        }

        // 动态扩容
        if (*count >= capacity) {
            capacity = capacity ? capacity * 2 : 128;
            double* temp = realloc(utils, capacity * sizeof(double));
            if (!temp) {
                perror("realloc");
                fclose(fp);
                free(utils);
                return NULL;
            }
            utils = temp;
        }

        utils[(*count)++] = value;
    }

    fclose(fp);
    return utils;
}

int main(int argc, char** argv) {
    if (argc != 2) {
        fprintf(stderr, "Usage: %s <util_file>\n", argv[0]);
        return EXIT_FAILURE;
    }

    // 读取利用率文件
    int util_count;
    double* utils = read_util_file(argv[1], &util_count);
    if (!utils || util_count == 0) {
        fprintf(stderr, "No valid utilization data\n");
        return EXIT_FAILURE;
    }

    // 初始化控制参数
    GlobalControl ctrl = {
        .mutex = PTHREAD_MUTEX_INITIALIZER,
        .total_cores = 96,  // 固定96核心
        .current_util = 0.0
    };

    // 校准计算基准
    unsigned long loop_base = calibrate_compute();

    // 创建96个工作线程
    pthread_t threads[96];
    ThreadParams params[96];
    for (int i = 0; i < 96; ++i) {
        params[i] = (ThreadParams){
            .global_ctrl = &ctrl,
            .loop_base = loop_base,
            .running = 1,
            .thread_id = i
        };

        if (pthread_create(&threads[i], NULL, cpu_worker, &params[i])) {
            perror("pthread_create");
            // 清理已创建线程
            for (int j = 0; j < i; ++j) params[j].running = 0;
            free(utils);
            return EXIT_FAILURE;
        }
    }

    // 主控制循环
    for (int sec = 0; sec < util_count; ++sec) {
        pthread_mutex_lock(&ctrl.mutex);
        ctrl.current_util = utils[sec];
        pthread_mutex_unlock(&ctrl.mutex);
        
        sleep(1);  // 按秒更新
    }

    // 停止所有线程
    for (int i = 0; i < 96; ++i) {
        params[i].running = 0;
        pthread_join(threads[i], NULL);
    }

    free(utils);
    return EXIT_SUCCESS;
}
