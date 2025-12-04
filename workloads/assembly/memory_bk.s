.section .text
.align 4
.globl access_memory_block

// 输入参数：
// x0 - 迭代次数 (N)
// x1 - 步长 (STRIDE, 字节单位)
access_memory_block:
    stp     x29, x30, [sp, #-16]!   // 保存帧指针和返回地址
    mov     x29, sp

    adrp    x3, buffer               // 获取缓冲区高地址位
    add     x3, x3, :lo12:buffer     // 组合完整缓冲区地址
    mov     x2, #0                   // 初始偏移量=0
    mov     x4, #0xFFFFF             // 1MB掩码 (0x100000-1)

.Lloop:
    ldr     w5, [x3, x2]            // 关键内存访问指令
    add     x2, x2, x1              // 增加步长
    and     x2, x2, x4              // 限制在1MB范围内
    subs    x0, x0, #1              // 递减计数器
    b.ne    .Lloop                  // 循环直到x0=0

    ldp     x29, x30, [sp], #16     // 恢复栈帧
    ret

.section .data
.align 12                          // 4KB对齐
buffer:
    .space 1048576               // 1MB缓冲区
