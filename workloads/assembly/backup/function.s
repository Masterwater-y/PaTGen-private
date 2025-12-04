.altmacro
.macro repeat num
    .global __func_\num
    __func_\num:    
        ret

    .if \num > 1
        repeat %(\num - 1)
    .endif
.endm

.section .text
repeat 100

.section .text
.global call_functions
call_functions:
    // 输入参数：
    // x0 = func_count（函数数量，1~1024）
    // x1 = stride（步长，单位：函数个数）
    // x2 = iterations（循环次数）

    // 计算掩码：mask = (func_count * 4) - 1
    lsl x3, x0, #2          // x3 = func_count * 4（每个函数占4字节）
    sub x3, x3, #1          // x3 = mask = (func_count * 4) - 1

    // 加载第一个函数地址
    adrp x4, func0          // 获取func0的页基地址
    add x4, x4, :lo12:func0 // 组合低12位地址，x4 = func0完整地址

loop:
    // 调用当前函数
    blr x4                  // 跳转到x4指向的函数（如func0, func1...）

    // 计算下一个函数地址
    add x4, x4, x1, lsl #2  // x4 += stride * 4（步长转换为字节偏移）
    and x4, x4, x3          // 应用掩码，限制地址在有效范围内

    // 循环控制
    subs x2, x2, #1         // iterations -= 1
    b.ne loop               // 若未完成，继续循环

    ret                     // 返回调用者
