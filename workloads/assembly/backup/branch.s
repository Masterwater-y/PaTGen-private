// 使用 // 注释
.global branch_test
branch_test:
    // 保存寄存器
    stp x19, x20, [sp, #-48]!
    stp x21, x22, [sp, #16]
    stp x23, x24, [sp, #32]

    // 参数: x0=迭代次数, x1=阈值
    mov x19, x0          // 迭代次数存入x19
    mov w20, w1          // 阈值存入w20

    // 初始化LCG参数
    ldr w21, =12345      // 随机数种子
    ldr w22, =1103515245 // 乘法因子a
    ldr w23, =12345      // 增量c
    ldr w24, =0x7FFFFFFF // 模数m=2^31-1

loop:
    subs x19, x19, #1    // 递减迭代次数
    b.lt end             // 若x19 < 0，结束循环

    // 生成随机数: w21 = (a * w21 + c) mod m
    mul w25, w22, w21    // a * 当前种子
    add w25, w25, w23    // 加c
    and w21, w25, w24    // 取模得到新种子

    // 比较随机数与阈值
    cmp w21, w20
    b.gt jump_label      // 若随机数 > 阈值，跳转

    // 不跳转分支（空操作）
    b cont

jump_label:
    // 跳转分支（空操作）
    nop                  // 使用nop指令更清晰

cont:
    b loop               // 继续循环

end:
    // 恢复寄存器并返回
    ldp x23, x24, [sp, #32]
    ldp x21, x22, [sp, #16]
    ldp x19, x20, [sp], #48
    ret
