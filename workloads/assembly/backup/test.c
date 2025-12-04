#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/mman.h>

#define TARGET_UTIL_PERCENT 80   // 目标内存利用率（如80%）
#define HOLD_DURATION 60         // 内存占用保持时间（秒）

int main() {
    // 获取系统总内存（单位：MiB）
    long total_mem_mib = 0;
    FILE *meminfo = fopen("/proc/meminfo", "r");
    if (meminfo) {
        char line[256];
        while (fgets(line, sizeof(line), meminfo)) {
            if (strstr(line, "MemTotal")) {
                sscanf(line, "MemTotal: %ld kB", &total_mem_mib);
                total_mem_mib /= 1024;  // 转换为MiB
                break;
            }
        }
        fclose(meminfo);
    } else {
        perror("无法读取/proc/meminfo");
        return EXIT_FAILURE;
    }

    // 计算需要分配的内存大小
    size_t target_mem_mib = (total_mem_mib * TARGET_UTIL_PERCENT) / 100;
    size_t alloc_size = target_mem_mib * 1024 * 1024;  // 转换为字节

    printf("系统总内存: %ld MiB\n", total_mem_mib);
    printf("尝试占用 %.2f MiB 内存 (目标利用率 %d%%)\n", 
           (double)target_mem_mib, TARGET_UTIL_PERCENT);

    // 分配内存
    printf("alloc_size %ld",alloc_size);
    void *mem_block = malloc(alloc_size);
    if (!mem_block) {
        perror("内存分配失败");
        return EXIT_FAILURE;
    }

    // 强制物理内存提交（COW机制下实际占用）
    printf("正在初始化内存...\n");
    memset(mem_block, 0, alloc_size);

    // 锁定内存防止被交换（需要root权限）
    /*
    if (mlock(mem_block, alloc_size) == 0) {
        printf("内存已锁定到物理RAM\n");
    } else {
        perror("警告: 无法锁定内存");
    }*/

    printf("内存占用完成，保持 %d 秒...\n", HOLD_DURATION);
    printf("此时可用工具（如htop）观察内存利用率\n");
    
    // 保持内存占用
    sleep(HOLD_DURATION);

    // 释放资源
    printf("释放内存...\n");
    munlock(mem_block, alloc_size);
    free(mem_block);

    printf("操作完成\n");
    return EXIT_SUCCESS;
}
