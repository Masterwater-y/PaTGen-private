import numpy as np
import random
import math
import pandas as pd

import psutil

def get_mem_usage():
    mem = psutil.virtual_memory()
    return mem.percent  # 返回内存利用率百分比


class TaskGenerator:
    def __init__(self, avg_cpu, max_cpu, avg_mem, max_mem, duration):
        self.avg_cpu = avg_cpu        # 目标平均CPU使用率（百分比）
        self.max_cpu = max_cpu        # 目标最大CPU使用率
        self.avg_mem = avg_mem        # 目标平均内存使用量（MB）
        self.max_mem = max_mem        # 目标最大内存使用量
        self.duration = duration      # 任务持续时间（秒）
        
        # 内存分配参数校准
        self.mem_overhead = 0.12      # 内存分配开销系数

    def generate_cpu_sequence(self):
        """使用模拟退火算法生成CPU使用序列"""
        def cost_fn(seq):
            avg_dev = abs(np.mean(seq) - self.avg_cpu)/self.avg_cpu
            max_dev = abs(np.max(seq) - self.max_cpu)/self.max_cpu
            return avg_dev + max_dev

        # 初始解：平均值附近的正态分布
        current = np.clip(np.random.normal(
            loc=self.avg_cpu,
            scale=self.avg_cpu/3,
            size=self.duration
        ), 0, 100)
        
        # 模拟退火参数
        T = 1.0
        T_min = 1e-3
        alpha = 0.95
        
        best = current.copy()
        
        while T > T_min:
            # 生成邻域解
            neighbor = np.clip(current + np.random.normal(
                scale=T*self.avg_cpu, 
                size=self.duration
            ), 0, 100)
            
            # 计算成本变化
            delta = cost_fn(neighbor) - cost_fn(current)
            
            # 接受判断
            if delta < 0 or random.random() < math.exp(-delta/T):
                current = neighbor
                if cost_fn(current) < cost_fn(best):
                    best = current.copy()
            
            T *= alpha
        
        return best.round(2)

    def generate_mem_sequence(self):
        """生成内存使用序列（考虑分配开销）"""
        # 计算实际需要分配的内存
        def adj_alloc(target):
            return target * (1 + self.mem_overhead)
        
        # 生成满足最大值的序列
        base = np.full(self.duration, self.avg_mem)
        peaks = int(0.1 * self.duration)  # 10%时间达到峰值
        peak_positions = np.random.choice(
            self.duration, 
            peaks, 
            replace=False
        )
        
        for pos in peak_positions:
            base[pos] = adj_alloc(self.max_mem)
            
        return np.clip(base, 0, adj_alloc(self.max_mem))

    def execute_workload(self, cpu_seq, mem_seq):
        """执行生成的负载（伪代码）"""
        pass

if __name__ == "__main__":
    target_path = './targets.csv'
    target_df = pd.read_csv(target_path)
    stable_mem_use = get_mem_usage()
    # 处理所有目标组
    results = []
    for task_id, row in target_df.iterrows():
        
        mem_adj = (row['mem_util']*0.01 * row['mem_size'] - stable_mem_use*0.01 * row['mem_capacity']) * 1024
        generator = TaskGenerator(
            avg_cpu=row['cpu_util'], 
            max_cpu=row['cpu_util']*1.2,
            avg_mem=mem_adj,
            max_mem=mem_adj,
            duration=int(row['duration'])
        )
        
        # 生成资源序列
        cpu_seq = generator.generate_cpu_sequence()
        mem_seq = generator.generate_mem_sequence()

        # 构建数据行（添加任务ID和所有时间点数据）
        task_row = {
            'task_id': task_id,
            'avg_cpu': row['cpu_util'],
            'avg_mem': mem_adj,
            'cpu_seq': cpu_seq.tolist(),
            'mem_seq': mem_seq.tolist()
        }

        if task_id%5==0:
            print(f'{task_id} generate finished')
        results.append(task_row)

    # 转换为DataFrame并存储
    result_df = pd.DataFrame(results)

    result_df.to_csv('param_sets.csv', index=False)
