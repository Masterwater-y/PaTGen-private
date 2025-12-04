# Makefile for Proxy Benchmark with cJSON and assembly files

# Compiler and flags
CC = gcc
CFLAGS = -g -Wall -O0 -D_GNU_SOURCE
LDFLAGS = -pthread -lm 
#CFLAGS = -g -Wall -O0 
#LDFLAGS =  
# Assembly files (假设三个文件是 memory.s、file1.s、file2.s)
ASMSRC = arithmetic.s sleep.s
ASMOBJS = $(ASMSRC:.s=.o)

# C source files
SRCS = main.c cJSON.c
OBJS = $(SRCS:.c=.o) $(ASMOBJS)
TARGET = main

# Default target
all: $(TARGET)

# Link all object files
$(TARGET): $(OBJS)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

# Compile C files with header dependencies
main.o: main.c cJSON.h
	$(CC) $(CFLAGS) -c $< -o $@

cJSON.o: cJSON.c cJSON.h
	$(CC) $(CFLAGS) -c $< -o $@

# Assemble .s files to objects
%.o: %.s
	$(CC) $(CFLAGS) -c $< -o $@

# Clean build artifacts
clean:
	rm -f $(TARGET) $(OBJS)

.PHONY: all clean
