import pandas as pd
from ast import literal_eval
from collections import defaultdict

import psutil

def get_mem_usage():
    mem = psutil.virtual_memory()
    return mem.percent  # 返回内存利用率百分比
class RWBAnalyzer:
    def __init__(self, csv_path):
        # 解析CSV数据
        self.df = pd.read_csv(csv_path, converters={'param_set': literal_eval})
        self.mem_rwbs = []
        self.cpu_rwbs = []
        
        # 分类内存/CPU型RWB
        for _, row in self.df.iterrows():
            params = row['param_set'][0]
            rwb_type = params[1]
            metadata = {
                'iterations': params[2],  # RWB迭代次数
                'mem_usage': row['mem_util'],   # 内存使用(MB)
                'cpu_usage': row['cpu_util'],   # CPU核心数
                'cycles': row['cycles'],
                'instructions': row['instructions'],
                'llc_misses': row['ll-misses'],
                'template' : row['param_set']
            }
            
            if rwb_type == 'mem':
                self.mem_rwbs.append(metadata)
            elif rwb_type == 'div' or rwb_type == 'add':
                self.cpu_rwbs.append(metadata)

    def optimal_rwb_combination(self, rwbs, capacity, target, resource_type):
        """优化后的组合算法，支持资源使用和精度的平衡"""
        # 初始化动态规划表，记录(最大价值, 最小资源使用)
        dp = [{'value': 0, 'resource': 0, 'counts': defaultdict(int)} for _ in range(capacity + 1)]
        
        # 无限背包算法实现
        for w in range(1, capacity + 1):
            for idx, rwb in enumerate(rwbs):
                res_needed = rwb[resource_type]
                if res_needed > w:
                    continue
                    
                # 计算价值指标
                value = rwb['instructions'] if resource_type == 'cpu_usage' else rwb['llc_misses']
                current_value = dp[w - res_needed]['value'] + value
                current_resource = dp[w - res_needed]['resource'] + res_needed
                
                # 更新策略：优先更高价值，同等价值时选择更少资源
                if (current_value > dp[w]['value'] or 
                    (current_value == dp[w]['value'] and current_resource < dp[w]['resource'])):
                    dp[w] = {
                        'value': current_value,
                        'resource': current_resource,
                        'counts': dp[w - res_needed]['counts'].copy()
                    }
                    dp[w]['counts'][idx] += 1

        # 寻找最优解：最接近目标值的组合
        best_combination = None
        min_error = float('inf')
        for w in range(min(capacity, target), 0, -1):
            error = abs(dp[w]['value'] - target)
            resource_usage = dp[w]['resource']
            
            # 误差计算公式，可调整权重系数
            weighted_error = 0.7 * error + 0.3 * (capacity - resource_usage)
            
            if weighted_error < min_error:
                min_error = weighted_error
                best_combination = dp[w]

        # 构建返回结果
        combination = []
        total_resource = 0
        total_value = 0
        
        for idx, count in best_combination['counts'].items():
            if count > 0:
                rwb = rwbs[idx]
                combination.append({
                    'rwb': rwb,
                    'count': count,
                    'resource_usage': count * rwb[resource_type],
                    'achieved_value': count * (rwb['instructions'] if resource_type == 'cpu_usage' else rwb['llc_misses'])
                })
                total_resource += count * rwb[resource_type]
                total_value += count * (rwb['instructions'] if resource_type == 'cpu_usage' else rwb['llc_misses'])
        
        return combination, total_value

    def generate_script(self, C_CPU, C_Memory, T_CPI, T_MAI):
        """生成工作负载复制脚本"""
        # 计算目标值
        l_seg = C_CPU * 2.9*1e9  # 假设1核心秒=1e9周期
        T_Inst = int(l_seg / T_CPI)
        T_MA = int(T_Inst * T_MAI /1000)

        
        # 第一步：组合内存RWBs
        mem_combination, achieved_ma = self.optimal_rwb_combination(
            self.mem_rwbs, C_Memory, T_MA, 'mem_usage'
        )

        # 计算剩余资源

        # 关键修正点：基于实际选中的组合计算
        used_cpu_by_mem = sum(item['count'] * item['rwb']['cpu_usage'] for item in mem_combination)
        used_inst_by_mem = sum(item['count'] * item['rwb']['instructions'] for item in mem_combination)
        
        remaining_cpu = C_CPU - used_cpu_by_mem
        remaining_inst = T_Inst - used_inst_by_mem

        # 第二步：组合CPU RWBs

        cpu_combination, achieved_inst = self.optimal_rwb_combination(
            self.cpu_rwbs, remaining_cpu, remaining_inst, 'cpu_usage'
        )

        # 最终资源计算
        # 计算总指标
        total_inst = used_inst_by_mem + achieved_inst

        total_ma = achieved_ma + sum(item['count'] * item['rwb']['llc_misses'] for item in cpu_combination)

        # 最终资源计算
        total_cpu = used_cpu_by_mem + sum(item['count'] * item['rwb']['cpu_usage'] for item in cpu_combination)
        total_mem = sum(item['count'] * item['rwb']['mem_usage'] for item in mem_combination)

        
        return {
            'memory': mem_combination,
            'cpu': cpu_combination,
            'metrics': {
                'cpu_usage': total_cpu,
                'mem_usage': total_mem,
                'achieved_inst': total_inst,
                'achieved_ma': total_ma,
                'cpi': l_seg / total_inst if total_inst != 0 else 0,
                'mai': (total_ma * 1000) / total_inst if total_inst != 0 else 0,
                'target_inst': T_Inst,
                'target_ma': T_MA
            }
        }

    def generate_template(self, script, duration):
        res=[]
        comb = script['memory'] + script['cpu']
        for rwb in comb:
            temp = rwb['rwb']['template'][0]
            temp[2] = int(temp[2] * duration)
            for i in range (rwb['count']):
                res.append(temp)
        return res

# 示例使用
if __name__ == "__main__":
    # 示例参数
    analyzer = RWBAnalyzer('block.csv')
    target_path = './targets.csv'
    target_df = pd.read_csv(target_path)
    stable_mem_use = get_mem_usage()
    results = []
    cores = 96



    # 目标参数 (假设值)
    for task_id, row in target_df.iterrows():
        mem_capacity = row['mem_capacity']
        mem_size = row['mem_size']
        C_CPU = int(row['cpu_util']/100 * cores)      # CPU核心数
        C_Memory = int((row['mem_util'] * mem_size - stable_mem_use * mem_capacity)/100 * 1024)
        T_CPI = row['CPI']    # 目标CPI
        T_MAI = row['MPKI']
        duration = row['duration']
        # 生成脚本
        print(C_CPU,C_Memory ,stable_mem_use   )
        script = analyzer.generate_script(C_CPU, C_Memory, T_CPI, T_MAI)
        template = analyzer.generate_template(script,duration)
        results.append({
            'param_set':template
        })
    result_df = pd.DataFrame(results)

    result_df.to_csv('param_sets.csv', index=False)
