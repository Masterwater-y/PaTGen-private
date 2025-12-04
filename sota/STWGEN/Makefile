# 编译器和参数
CC      = gcc
CFLAGS  = -Wall -Wextra -O0
LDFLAGS = -lm

# 目标列表
TARGETS = cpu_block mem_block

# 依赖库配置
cpu_block_LIBS = -lpthread -lrt
mem_block_LIBS = -lm

# 默认构建所有目标
all: $(TARGETS)

# 特殊目标编译规则
cpu_block: cpu_block.c
	$(CC) $(CFLAGS) -o $@ $^ $(cpu_block_LIBS) $(LDFLAGS)

mem_block: mem_block.c
	$(CC) $(CFLAGS) -o $@ $^ $(mem_block_LIBS) $(LDFLAGS)

# 清理命令
clean:
	rm -f $(TARGETS)

# 声明伪目标
.PHONY: all clean
