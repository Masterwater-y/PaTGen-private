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
for _, targets_row in aggr_df.iterrows():
    if phase_index is not None:
        if _!=phase_index:
            continue

    instructions = targets_row['duration']*3*10e8
    targets = {
        "cycles":targets_row['CPI']*instructions,
        "ll-misses/":targets_row['MPKI']*instructions/1000,
        "CPI": targets_row['CPI'],
        "MPKI" :targets_row['MPKI'],
        "instruction" :instructions,
        "duration": targets_row['duration']
    }
    print(targets)
    template = synthesize_workload(block_path,target_params=targets)
    res_template = res_template + template


res_template.append(16)
res_template.append(1)
param_sets.append({
    "param_set":str(res_template)
})
pd.DataFrame(param_sets).to_csv('param_sets.csv', index=False)