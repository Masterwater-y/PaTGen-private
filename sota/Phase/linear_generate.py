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

def build_linear_system(block_features, targets, fixed_llmiss_types=['div', 'add']):
    """
    构建线性方程组：求解基本块执行次数 N_j
    参数：
    block_features: 基本块特征字典（cycle, instruction, ll_miss 等）
    targets: 目标指标字典（CPI, MPKI, duration, instruction）
    N0: 基本块初始测量次数（论文中为 1e7）
    返回：
    A: 系数矩阵
    b: 目标向量
    """



    m = len(block_features['instruction'])  # 基本块数量
    q = 2  # 指标数量（CPI 和 MPKI，对应论文中的 metric^i）
    block_types = block_features.get('type', ['unknown'] * m)
    
    # 标记固定LL miss的基本块
    is_fixed = np.array([t in fixed_llmiss_types for t in block_types])

    # 构建方程组：CPI 和 MPKI 约束
    A = np.zeros((q, m))
    b = np.zeros(q)
    
    # 第1个方程：CPI = cycles / instructions
    cycles_per_block = block_features['cycle']
    instructions_per_block = block_features['instruction']
    A[0, :] = cycles_per_block  - targets['CPI'] * instructions_per_block
    b[0] = 0  # CPI目标值需满足 (sum(cycles*N_j/N0)) / (sum(instructions*N_j/N0)) = targets['CPI']
    
    # 第2个方程：MPKI = (ll_misses * 1000) / instructions
    ll_miss_per_block = block_features['ll_miss']
    fixed_ll_miss = np.sum(ll_miss_per_block[is_fixed])
    variable_ll_miss_coeff = np.where(is_fixed, 0, ll_miss_per_block)
    A[1, :] = variable_ll_miss_coeff - targets['MPKI'] * instructions_per_block / 1000
    b[1] = -fixed_ll_miss # 移项到右侧

    # 额外约束：总指令数 = targets['instruction']
    # 转换为：sum(instructions*N_j/N0) = targets['instruction']
    A = np.vstack((A, instructions_per_block))
    b = np.hstack((b, targets['instruction']))
    
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

    #print('block1=',block_feature)
    block_feature['cycle'] = block_feature['cycle']/block_feature['duration']*targets['duration']
    block_feature['instruction'] = block_feature['instruction']/block_feature['duration']*targets['duration']
    block_feature['ll_miss'] = block_feature['ll_miss']/block_feature['duration']*targets['duration']
    for i,item in enumerate(param_sets):
        item[0][2] = item[0][2]/block_feature['duration'][i]*targets['duration']
    block_feature['duration'] = targets['duration']
    #print('block2=',block_feature)

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
    for i in np.where(valid_indices)[0]:
        cycle += block_feature['cycle'][i] * x_optimized[i]
        instruction += block_feature['instruction'][i] * x_optimized[i]
        if block_feature['type'] in ['div','add']:
            llmiss += block_feature['ll_miss'][i] 
        else:
            llmiss += block_feature['ll_miss'][i]* x_optimized[i]
        print(block_feature['cycle'][i],x_optimized[i],block_feature['cycle'][i] * x_optimized[i])
        print(block_feature['instruction'][i],x_optimized[i],block_feature['instruction'][i] * x_optimized[i])
        scale = x_optimized[i]

        param_sets[i][0][0]*=(int(scale)+1)  
        scale = scale / (int(scale)+1)
        param_sets[i][0][2] = int (param_sets[i][0][2]*scale)

    print('all=',cycle, instruction, llmiss)
    optimized_blocks = {
        'param_set': [param_sets[i] for i in np.where(valid_indices)[0]],
        'execution_count': x_optimized[valid_indices],
    }
    return optimized_blocks

block_path = 'block.csv'
target_path = 'linear_target.csv'
#block_feature, param_sets = read_load_features(block_path)
targets_df = pd.read_csv(target_path)
for _, targets_row in targets_df.iterrows():
    targets = {
        "CPI": targets_row['cycles']/targets_row['instructions'],
        "MPKI" :targets_row['ll-misses/']/targets_row['instructions']*1000,
        "instruction" :targets_row['instructions'],
        "duration": targets_row['duration']
    }
    print(targets_row)
    print(synthesize_workload(block_path,target_params=targets))