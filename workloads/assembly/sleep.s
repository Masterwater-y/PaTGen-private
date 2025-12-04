// 文件: sleep.s
.text
.global sleep_n
.type sleep_n, @function

sleep_n:
    // 保存帧指针和返回地址
    stp x29, x30, [sp, #-32]!
    mov x29, sp

    // 在栈上创建timespec结构 (16字节)
    str x0, [sp, #16]       // tv_sec = N (从X0获取参数)
    str xzr, [sp, #24]      // tv_nsec = 0

    // 准备系统调用参数
    add x0, sp, #16         // timespec结构地址
    mov x1, xzr             // rem=NULL

    // 执行nanosleep系统调用
    mov x8, #101            // Linux nanosleep系统调用号
    svc #0

    // 恢复栈和返回
    ldp x29, x30, [sp], #32
    ret
