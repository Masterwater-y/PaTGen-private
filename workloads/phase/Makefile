# Makefile for Proxy Benchmark with cJSON and assembly files

# Compiler and flags
CC = gcc
CFLAGS = -g -Wall -O0 -D_GNU_SOURCE
LDFLAGS = -pthread -lm 
#CFLAGS = -g -Wall -O0 
#LDFLAGS =  
# 设置默认N值（若未通过命令行指定）
N ?= 100

# 将N的值传递给编译选项


# 更新汇编源文件列表
ASMSRC = arithmetic.s
# Assembly files

ASMOBJS = $(ASMSRC:.s=.o)

# C source files and common objects
SRCS = main.c parallel.c cJSON.c
COMMON_OBJS = cJSON.o $(ASMOBJS)

# Target-specific objects
MAIN_OBJS = main.o $(COMMON_OBJS)
PARALLEL_OBJS = parallel.o $(COMMON_OBJS)

# Default target
all: main parallel

# Build both targets
main: $(MAIN_OBJS)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

parallel: $(PARALLEL_OBJS)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

# Compile C files with header dependencies
%.o: %.c cJSON.h
	$(CC) $(CFLAGS) -c $< -o $@

# Assemble .s files to objects
%.o: %.s
	$(CC) $(CFLAGS) -c $< -o $@

# Clean build artifacts
clean:
	rm -f main parallel $(MAIN_OBJS) $(PARALLEL_OBJS)

.PHONY: all clean