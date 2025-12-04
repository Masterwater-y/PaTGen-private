// --------------------- 加法基本块 ---------------------
.global add_block
add_block:
    // x0: 迭代次数 (每个迭代执行4次ADD指令)
    mov x1, x0          // 将迭代次数存入x1
    mov x2, #0          // 初始化累加器
    mov x3, #1          // 每次加1
.loop_add:
    add x4, x1, x2       // 使用新寄存器
    add x5, x3, x8
    add x1, x1, x2
    add x3, x3, x8
    subs x1, x1, #1     // 递减迭代次数
    bne .loop_add       // 循环直到x1=0
    ret

// --------------------- 乘法基本块 ---------------------
.global mul_block
mul_block:
    // x0: 迭代次数 (每个迭代执行4次MUL指令)
    mov x1, x0          // 存入x1
    mov x2, #1          // 初始值
    mov x3, #2          // 乘数
.loop_mul:
    mul x4, x2, x3      // 执行4次MUL指令
    mul x5, x3, x4
    mul x4, x5, x3
    mul x5, x4, x3
    subs x1, x1, #1
    bne .loop_mul
    ret

// --------------------- 除法基本块 ---------------------
.global div_block
div_block:
    // x0: 迭代次数 (每个迭代执行2次UDIV指令)
    mov x1, x0
    mov x2, 0xFFFFFFFF  // 被除数
    mov x3, #2          // 除数
.loop_div:
    // 4次UDIV指令 (使用不同寄存器和操作数)
    udiv x4, x2, x3             // [1] x4 = 0xFFFFFFFFFFFFFFFF / 3
    udiv x5, x2, x8             // [2] x5 = 0xFFFFFFFFFFFFFFFF / 5
    udiv x6, x2, x3             // [3] 重复除3
    udiv x7, x2, x8             // [4] 重复除5
    subs x1, x1, #1             // 循环计数器递减
    bne .loop_div               // 继续循环
    ret


.global sqrt_block
sqrt_block:
    // x0: 迭代次数
    mov x1, x0                  // 保留 x1 作为外层循环计数器
    fmov d2, #0.5
    fmov d3, #2.0 

.loop_sqrt:
    // 用 .rept 展开 4 次 UDIV 指令（保持严格数据依赖）
    .rept 4                     // 每次循环展开 4 条 UDIV
    fsqrt d2 ,d2       // 结果直接写入 x2，保持依赖链
    .endr

    subs x1, x1, #1             // 外层循环计数器递减
    bne .loop_sqrt               // 继续循环直到 x1=0

    ret

// --------------------- 混合指令基本块 ---------------------
.global mixed_block
mixed_block:
    // x0: 迭代次数 (每个迭代包含多种指令)
    mov x1, x0
    mov x2, #0          // ADD/SUB操作数
    mov x3, #1
    mov x4, 0xFFFFFFFF  // 大数用于除法
.loop_mixed:
    add x2, x2, x3      // ADD
    sub x5, x4, x3      // SUB
    mul x6, x2, x5      // MUL
    udiv x7, x4, x3     // UDIV
    subs x1, x1, #1
    bne .loop_mixed
    ret
