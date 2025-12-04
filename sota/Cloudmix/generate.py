from collections import defaultdict
import json
import sys
import numpy as np
from scipy.optimize import nnls  # 非负最小二乘法
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

def build_linear_system(block_features, targets, fixed_llmiss_types=['div', 'add'], N0=1e7):
    """
    构建线性方程组：求解基本块执行次数 N_j
    参数：
    block_features: 基本块特征字典（包含'cycle', 'instruction', 'll_miss'等键）
    targets: 目标指标字典（需包含'CPI', 'MPKI', 'instruction'）
    fixed_llmiss_types: 固定LLC缺失类型的基本块类型列表
    N0: 基本块初始测量次数（论文中为1e7）
    返回：
    A: 系数矩阵
    b: 目标向量
    """
    m = len(block_features['instruction'])  # 基本块数量
    block_types = block_features.get('type', ['unknown'] * m)
    
    # 标记固定LLC缺失的基本块（是否允许其LLC缺失参与变量调整）
    is_fixed = np.array([t in fixed_llmiss_types for t in block_types])
    
    # 指标数量：CPI、MPKI、总指令数约束，共3个方程
    q = 3  
    A = np.zeros((q, m))
    b = np.zeros(q)
    
    # 第1个方程：CPI = (总周期数 / 总指令数) = targets['CPI']
    # 推导：sum(cycle_j * N_j / N0) / sum(instr_j * N_j / N0) = CPI_target
    # 等价于：sum(cycle_j * N_j) - CPI_target * sum(instr_j * N_j) = 0
    cycles = block_features['cycle']
    instrs = block_features['instruction']
    A[0, :] = cycles - targets['CPI'] * instrs
    b[0] = 0  # 等式右侧为0
    
    # 第2个方程：MPKI = (总LLC缺失数 / 总指令数) × 1000 = targets['MPKI']
    # 推导：sum(ll_miss_j * N_j / N0) / (sum(instr_j * N_j / N0)) × 1000 = MPKI_target
    # 等价于：sum(ll_miss_j * N_j) - (MPKI_target / 1000) * sum(instr_j * N_j) = 0
    ll_miss = block_features['ll_miss']
    A[1, :] = ll_miss - (targets['MPKI'] / 1000) * instrs
    b[1] = 0 
    
    # 第3个方程：总指令数约束 sum(instr_j * N_j / N0) = targets['instruction']
    # 推导：sum(instr_j * N_j) = targets['instruction'] * N0
    A[2, :] = instrs
    b[2] = targets['instruction'] # 注意乘以N0
    
    return A, b

def solve_initial_solution(A, b):
    """
    求解初始执行次数 N_j（非负最小二乘）
    """
    # 忽略可能的奇异矩阵警告（论文中通过算法设计保证方程组收敛）
    try:
        x, residuals = nnls(A, b)
    except np.linalg.LinAlgError:
        raise ValueError("线性方程组无解，请检查目标参数或基本块特征")
    return x

def synthesize_workload(load_features_file, target_params):
    """
    主函数：读取基本块特征并合成负载
    参数：
    load_features_file: 基本块特征文件路径（CSV格式）
    target_params: 目标参数字典（CPI, MPKI, duration, instruction）
    返回：
    optimized_blocks: 优化后的基本块执行计划
    """
    # 读取基本块特征
    block_feature, param_sets = read_load_features(load_features_file)
    # 构建线性方程组
    A, b = build_linear_system(block_feature, target_params)
    
    # 求解初始解
    x_initial = solve_initial_solution(A, b)

    x_optimized = x_initial
    # 迭代优化
    #x_optimized = iterate_adjustment(block_feature, x_initial, target_params)
    
    # 生成最终执行计划（过滤执行次数为0的基本块）

    valid_indices = x_optimized > 1e-6  # 忽略极小值（视为零）

    cycle=0
    instruction = 0 
    llmiss=0
    duration = 0

    template_res = []
    for i in np.where(valid_indices)[0]:
        scale = x_optimized[i]
        cycle += block_feature['cycle'][i] * scale
        instruction += block_feature['instruction'][i] * scale
        llmiss += block_feature['ll_miss'][i] * scale
        duration += block_feature['duration'][i] * scale
        template_res.append(param_sets[i][0])
        template_res[-1][2] = int(template_res[-1][2]*scale)
        
    #template_res.append(16)
    #template_res.append(1)
    print(cycle, instruction, llmiss)
    print(f'CPI={cycle/instruction} MPKI={llmiss*1000/instruction} duration={duration}')
    
    return template_res


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

block_path = 'block.csv'
args = sys.argv[1:]
sample_index = int(args[0])
phase_index = None
if len(args)>1:
    phase_index = int(args[1])
aggr_df = pd.read_csv(f'stage{sample_index}/aggr.csv')
target_path = f'stage{sample_index}/targets.csv'
#block_feature, param_sets = read_load_features(block_path)
targets_df = pd.read_csv(target_path)
param_sets = []
res_template = []

phase_sets = []
analyzer = RWBAnalyzer('block.csv')
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
    #template = synthesize_workload(block_path,target_params=targets)
    res_template .append(template)


res_template.append(16)
res_template.append(1)
param_sets.append({
    "param_set":str(res_template)
})
pd.DataFrame(param_sets).to_csv('param_sets.csv', index=False)