.section .text
.global disk_io
disk_io:
    // ==================== 序言 ====================
    // 保存寄存器状态
    stp x29, x30, [sp, #-64]!
    stp x19, x20, [sp, #16]
    stp x21, x22, [sp, #32]
    stp x23, x24, [sp, #48]
    mov x29, sp

    // ==================== 参数处理 ====================
    mov w19, w0                   // 保存iterations到w19
    mov w24, #0                   // 错误状态寄存器

    // ==================== 内存分配 ====================
    // mmap分配4096字节对齐内存
    mov x0, #0                    // 地址
    mov x1, #4096                 // 大小
    mov w2, #3                    // PROT_READ|PROT_WRITE
    mov w3, #0x22                 // MAP_PRIVATE|MAP_ANONYMOUS
    mov x4, #-1                   // fd
    mov x5, #0                    // offset
    mov x8, #222                  // mmap系统调用号
    svc #0
    cmp x0, #-4096
    b.lo 1f
    // 错误处理：内存分配失败
    mov w24, #0x1000              // 错误代码
    b .final_error
1:
    mov x20, x0                   // 保存缓冲区地址到x20

    // ==================== 文件操作 ====================
    // 生成唯一文件名（基于PID）
    mov x8, #172                  // getpid系统调用
    svc #0
    adrp x1, filename_fmt
    add x1, x1, :lo12:filename_fmt
    adrp x2, filename_buf
    add x2, x2, :lo12:filename_buf
    mov w3, w0
    bl snprintf

    // 打开文件（带O_DIRECT）
    mov x0, #-100                 // AT_FDCWD
    adrp x1, filename_buf
    add x1, x1, :lo12:filename_buf
    mov x2, #0x4042               // O_RDWR|O_CREAT|O_DIRECT
    mov x3, #0x1B6                // 权限0666
    mov x8, #56                   // openat
    svc #0
    cmp x0, #0
    b.gt 2f
    // 错误处理：文件打开失败
    mov w24, #0x2000
    b .cleanup_mmap
2:
    mov x21, x0                   // 保存文件描述符

    // ==================== I/O 循环 ====================
    mov w22, #0                   // 循环计数器
.io_loop:
    cmp w22, w19
    b.ge .cleanup_file

    // 写入操作
    mov x0, x21                   // fd
    mov x1, x20                   // buf
    mov x2, #4096                 // 大小
    mov x8, #64                   // write
    svc #0
    cmp x0, #4096
    b.eq 3f
    // 错误处理：写入失败
    mov w24, #0x3000
    bl .debug_print
    b .cleanup_file
3:

    // 读取操作 
    mov x0, x21                   // fd
    mov x1, x20                   // buf
    mov x2, #4096                 // 大小
    mov x8, #63                   // read
    svc #0
    cmp x0, #4096
    b.eq 4f
    // 错误处理：读取失败
    mov w24, #0x4000
    bl .debug_print
    b .cleanup_file
4:

    // 进度更新
    add w22, w22, #1
    b .io_loop

    // ==================== 清理操作 ====================
.cleanup_file:
    // 关闭文件
    mov x0, x21
    mov x8, #57                   // close
    svc #0

    // 删除临时文件
    adrp x0, filename_buf
    add x0, x0, :lo12:filename_buf
    mov x8, #87                   // unlink
    svc #0

.cleanup_mmap:
    // 释放内存
    mov x0, x20
    mov x1, #4096
    mov x8, #215                  // munmap
    svc #0

.final_error:
    // 错误状态处理
    cmp w24, #0
    b.eq 5f
    adrp x0, error_fmt
    add x0, x0, :lo12:error_fmt
    mov w1, w24
    bl printf
5:

    // ==================== 收尾 ====================
    ldp x23, x24, [sp, #48]
    ldp x21, x22, [sp, #32]
    ldp x19, x20, [sp, #16]
    ldp x29, x30, [sp], #64
    ret

    // ==================== 调试工具 ====================
.debug_print:
    // 寄存器保存
    stp x0, x1, [sp, #-16]!
    stp x2, x3, [sp, #-16]!
    
    adrp x0, debug_fmt
    add x0, x0, :lo12:debug_fmt
    mov x1, x8                    // 系统调用号
    mov x2, x0                    // 返回值
    bl printf
    
    ldp x2, x3, [sp], #16
    ldp x0, x1, [sp], #16
    ret

.section .rodata
filename_fmt:
    .asciz "/tmp/disk_io_%d.tmp"
error_fmt:
    .asciz "Critical error occurred: 0x%04x\n"
debug_fmt:
    .asciz "DEBUG: syscall %ld returned %ld\n"

.section .bss
.lcomm filename_buf, 64

// 对齐检查（编译时验证）
.align 12
