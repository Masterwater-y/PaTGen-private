from collections import defaultdict
import json
import sys
import numpy as np

import pandas as pd
import ast

def read_load_features(file_path):
    # 读取并验证数据
    data = pd.read_csv(file_path)
    required_columns = ['param_set', 'duration', 'cycles_sum', 'instructions_sum', 'll-misses_sum']
    
    for col in required_columns:
        if col not in data.columns:
            raise ValueError(f"CSV文件中缺少{col}列")


    #
    block_feature={
        'cycle': data['cycles_sum'].values,
        'instruction': data['instructions_sum'].values,
        'll_miss': data['ll-misses_sum'].values,
        'duration': data['duration'].values,
        'rank':[],
        'type':[]
    }
    param_sets = data['param_set'].apply(ast.literal_eval).tolist()
    for item in param_sets:

        block_feature['rank'].append(item[0][0])
        block_feature['type'].append(item[0][1])
        #print(block_feature['rank'])

    return (
        block_feature,
        data['param_set'].apply(ast.literal_eval).tolist()
    )






class RWBAnalyzer:
    def __init__(self, csv_path):
        self.df = pd.read_csv(csv_path, converters={'param_set': ast.literal_eval})
        self.mem_rwbs = []
        self.cpu_rwbs = []
        
        for _, row in self.df.iterrows():

            params = row['param_set'][0]
            params[2] = int(params[2]/row['duration'])
            rwb_type = params[1]
            metadata = {
                'iterations': params[2],
                #'mem_usage': row['mem_util'],
                'cpu_usage': params[0],
                'cycles': int(row['cycles_sum']/row['duration']),
                'instructions': int(row['instructions_sum']/row['duration']),
                'llc_misses': int(row['ll-misses_sum']/row['duration']),
                'template' : params
            }
            
            if rwb_type == 'mem':
                self.mem_rwbs.append(metadata)
            elif rwb_type in ('div', 'add','sqrt'):
                self.cpu_rwbs.append(metadata)
        


    def optimal_rwb_combination(self, rwbs, capacity, target, target_type):
        # 初始化动态规划表：记录每个容量下的最佳值（最接近target）、资源使用量和组合
        dp = [{
            'value': None,          # 当前容量下能达到的指标值（instructions或llc_misses）
            'resource': float('inf'), # 当前容量下的资源使用量（越小越好）
            'counts': defaultdict(int)
        } for _ in range(capacity + 1)]
        dp[0]['value'] = 0          # 初始状态：资源使用量为0时，指标值为0
        dp[0]['resource'] = 0
        resource_type = 'cpu_usage'
        # 动态规划过程：填充dp表
        for w in range(capacity + 1):
            for idx, rwb in enumerate(rwbs):
                res_needed = rwb[resource_type]
                if res_needed > w:  # 资源不足，跳过
                    continue
                prev_state = dp[w - res_needed]
                if prev_state['value'] is None:  # 前序状态不可达，跳过
                    continue

                # 计算新的指标值
                value = rwb['instructions'] if target_type == 'instructions' else rwb['llc_misses']
                #print(rwb['template'],prev_state['value'],value)
                new_value = prev_state['value'] + value
                new_resource = prev_state['resource'] + res_needed  # 此时new_resource应等于w

                # 计算与target的绝对差
                current_diff = abs(new_value - target)
                existing_diff = abs(dp[w]['value'] - target) if dp[w]['value'] is not None else float('inf')

                # 更新条件：差距更小，或差距相同但资源更少
                if (current_diff < existing_diff) or \
                (current_diff == existing_diff and new_resource < dp[w]['resource']):
                    dp[w] = {
                        'value': new_value,
                        'resource': new_resource,
                        'counts': prev_state['counts'].copy()
                    }
                    dp[w]['counts'][idx] += 1

        if target_type == 'instructions':
            candidate_ws = [capacity]
        else:
            candidate_ws = range(capacity+1)
        # 寻找最佳组合：在候选容量中选择最接近target的条目
        best_diff = float('inf')
        best_w = -1
        for w in candidate_ws:
            if dp[w]['value'] is None:
                continue
            current_diff = abs(dp[w]['value'] - target)
            # 处理初始best_w为-1的情况
            if best_w == -1:
                best_diff = current_diff
                best_w = w
            else:
                existing_diff = abs(dp[best_w]['value'] - target)
                if (current_diff < best_diff) or \
                (current_diff == best_diff and dp[w]['resource'] < dp[best_w]['resource']):
                    best_diff = current_diff
                    best_w = w

        # 处理无解情况
        if best_w == -1 or dp[best_w]['value'] is None:
            return [], 0

        best_combination = dp[best_w]

        # 构建返回结果
        combination = []
        total_value = best_combination['value']
        for idx, count in best_combination['counts'].items():
            if count > 0:
                rwb = rwbs[idx]
                combination.append({
                    'rwb': rwb,
                    'count': count,
                    'resource_usage': count * rwb[resource_type],
                    'achieved_value': count * (rwb['instructions'] if target_type == 'instructions' else rwb['llc_misses'])
                })
        
        return combination, total_value


    def generate_script(self, C_CPU = 96, targets = None):
        l_seg = targets['cycles']
        T_Inst = targets['instruction']
        T_MA = targets['ll-misses/']

        # 内存组合（允许不严格）
        mem_combination, achieved_ma = self.optimal_rwb_combination(
            self.mem_rwbs, C_CPU-1, T_MA, 'mem_usage'
        )

        # 计算剩余CPU资源
        used_cpu_by_mem = sum(item['count'] * item['rwb']['cpu_usage'] for item in mem_combination)
        used_inst_by_mem = sum(item['count'] * item['rwb']['instructions'] for item in mem_combination)
        
        # 验证CPU资源不超限
        if used_cpu_by_mem > C_CPU:
            raise ValueError("内存型RWB已超出CPU核心限制")
        
        remaining_cpu = C_CPU - used_cpu_by_mem
        remaining_inst = max(T_Inst - used_inst_by_mem, 0)  # 保证非负


        # CPU组合（严格匹配）
        cpu_combination, achieved_inst = self.optimal_rwb_combination(
            self.cpu_rwbs, remaining_cpu, remaining_inst, 'instructions'
        )

        # 计算结果指标
        total_cpu = used_cpu_by_mem + sum(item['count'] * item['rwb']['cpu_usage'] for item in cpu_combination)
        #total_mem = sum(item['count'] * item['rwb']['mem_usage'] for item in mem_combination)
        total_inst = sum(item['count'] * item['rwb']['instructions'] for item in mem_combination + cpu_combination)
        total_ma = sum(item['count'] * item['rwb']['llc_misses'] for item in mem_combination + cpu_combination)
        total_cycles = sum(item['count'] * item['rwb']['cycles'] for item in mem_combination + cpu_combination)
        return {
            'memory': mem_combination,
            'cpu': cpu_combination,
            'metrics': {
                'cpu_usage': total_cpu,
                #'mem_usage': total_mem,
                'achieved_inst': total_inst,
                'achieved_ma': total_ma,
                'achieved_cycle': total_cycles,
                'cpi': total_cycles / total_inst if total_inst else 0,
                'mai': (total_ma * 1000) / total_inst if total_inst else 0,
                'target_cycle': l_seg,
                'target_inst': T_Inst,
                'target_ma': T_MA,

            }
        }

    def generate_template(self, script, duration):
        res = []
        for item in script['memory'] + script['cpu']:
            temp = item['rwb']['template'].copy()
            temp[2] = int(temp[2] * duration)
            temp[0] = int(temp[0]*item['count'])
            delay=0
            temp.append(delay)
            res.append(temp)
        return res

block_path = '../multi_rank_block.csv'
args = sys.argv[1:]
sample_index = int(args[0])
phase_index = None
if len(args)>1:
    phase_index = int(args[1])
aggr_df = pd.read_csv(f'stage{sample_index}/aggr.csv')
target_path = f'stage{sample_index}/targets.csv'

targets_df = pd.read_csv(target_path)
param_sets = []
res_template = []

phase_sets = []
analyzer = RWBAnalyzer(block_path)
for _, targets_row in aggr_df.iterrows():
    if phase_index is not None:
        if _!=phase_index:
            continue
    cpu_scale = 1 
    instructions = targets_row['instruction']/targets_row['duration']
    targets = {
        "cycles":int(targets_row['CPI']*instructions),
        "ll-misses/":int(targets_row['MPKI']*instructions/1000),
        "CPI": targets_row['CPI'],
        "MPKI" :targets_row['MPKI'],
        "instruction" :instructions,
        "duration": targets_row['duration']
    }
    print(targets)

    #C_CPU = 84
    cpu_freq=2.6*1e9
    C_CPU = int(targets['cycles']/cpu_freq)
    #C_CPU = int(targets_row['cpu_util']*0.01*96)
    if C_CPU<2:
        C_CPU = 2

    script = analyzer.generate_script(C_CPU=C_CPU, targets=targets)

    template = analyzer.generate_template(script, duration = targets_row['duration'])
    res_template.append(template)


res_template.append(16)
res_template.append(1)
param_sets.append({
    "param_set":str(res_template)
})
pd.DataFrame(param_sets).to_csv('param_sets.csv', index=False)