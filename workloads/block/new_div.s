.global div_block
div_block:
    // x0: 外部迭代次数
    // x1: 每个循环内的UDIV次数（依赖链长度）
    mov x9, x1          // 保存依赖链长度
    mov x1, x0          // 外部循环计数器
    mov x2, 0xFFFFFFFF  // 初始被除数
    mov x3, #2          // 固定除数
    mov x4, x2          // 初始化操作寄存器

.loop_div:
    // 内部依赖链循环
    mov x10, x9         // 当前循环的UDIV次数
.dep_chain:
    udiv x4, x4, x3     // 每次除法结果作为下次输入
    subs x10, x10, #1   // 减少依赖链计数器
    b.gt .dep_chain     // 继续执行依赖链

    subs x1, x1, #1     // 减少外部循环计数器
    b.gt .loop_div      // 继续外部循环
    ret
