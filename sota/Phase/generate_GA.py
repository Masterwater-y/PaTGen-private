import copy
import numpy as np
import pandas as pd
import ast
from pymoo.core.problem import Problem
from pymoo.algorithms.soo.nonconvex.ga import GA
from pymoo.operators.crossover.sbx import SBX
from pymoo.operators.mutation.pm import PM
from pymoo.operators.sampling.rnd import IntegerRandomSampling
from pymoo.optimize import minimize

# ---------------------------
# 原数据读取部分保持不变
# ---------------------------
def read_load_features(file_path):
    data = pd.read_csv(file_path)
    required_columns = ['param_set', 'duration', 'cycles_sum', 'instructions_sum', 'll-misses_sum']
    
    for col in required_columns:
        if col not in data.columns:
            raise ValueError(f"CSV文件中缺少{col}列")

    block_feature = {
        'cycle': data['cycles_sum'].values,
        'instruction': data['instructions_sum'].values,
        'll_miss': data['ll-misses_sum'].values,
        'duration': data['duration'].values,
        'rank': []
    }
    
    param_sets = data['param_set'].apply(ast.literal_eval).tolist()
    for item in param_sets:
        block_feature['rank'].append(item[0][0])
    
    return block_feature, data['param_set'].apply(ast.literal_eval).tolist()

# ---------------------------
# 优化问题类 (pymoo框架)
# ---------------------------
class IntegerResourceProblem(Problem):
    def __init__(self, cycle, instruction, cache_miss, rank, CPI_target, MPKI_target, ins_target):
        # 变量维度（即w的个数）
        n_var = len(cycle)
        
        # 父类初始化：变量全为整数，范围[0,100]
        super().__init__(n_var=n_var,
                         n_obj=1,
                         n_ieq_constr=1,
                         xl=0,
                         xu=96,
                         vtype=int)
        
        # 存储问题参数
        self.cycle = cycle
        self.instruction = instruction
        self.cache_miss = cache_miss
        self.rank = rank
        self.CPI_target = CPI_target
        self.MPKI_target = MPKI_target
        self.ins_target = ins_target

    def _evaluate(self, W, out, *args, **kwargs):
        # 计算各目标项
        total_cycle = np.sum(W * self.cycle, axis=1)
        total_instruction = np.sum(W * self.instruction, axis=1)
        total_cache_miss = np.sum(W * self.cache_miss, axis=1)
        
        # 避免除以零
        valid = total_instruction > 0
        CPI_actual = np.where(valid, total_cycle / total_instruction, np.inf)
        MPKI_actual = np.where(valid, (total_cache_miss / total_instruction) * 1000, np.inf)
        
        # 目标函数
        obj = (CPI_actual - self.CPI_target)**2 + \
              (MPKI_actual - self.MPKI_target)**2
        
        out["F"] = obj.reshape(-1, 1)
        
        # 约束条件：sum(w*rank) <= 96
        resource_usage = np.sum(W * self.rank, axis=1)
        out["G"] = (resource_usage - 96).reshape(-1, 1)

# ---------------------------
# 改造后的优化函数
# ---------------------------
def constrained_optimization(block_feature, targets):
    # 缩放系数计算（保持原逻辑）
    ratio = targets['duration'] / block_feature['duration']
    
    # 缩放特征值
    cycle = block_feature['cycle'] * ratio
    instruction = block_feature['instruction'] * ratio
    cache_miss = block_feature['ll_miss'] * ratio
    
    # 创建优化问题实例
    problem = IntegerResourceProblem(
        cycle=cycle,
        instruction=instruction,
        cache_miss=cache_miss,
        rank=block_feature['rank'],
        CPI_target=targets['CPI'],
        MPKI_target=targets['MPKI'],
        ins_target=targets['instruction']
    )
    
    # 配置遗传算法
    algorithm = GA(
        pop_size=50,
        sampling=IntegerRandomSampling(),
        crossover=SBX(prob=0.9, eta=3.0),
        mutation=PM(prob=0.1, eta=3.0),
        eliminate_duplicates=True
    )
    
    # 执行优化
    result = minimize(
        problem,
        algorithm,
        ('n_gen', 200),
        seed=42,
        verbose=False
    )
    
    return result, ratio

# ---------------------------
# 生成模板函数（需要调整取整逻辑）
# ---------------------------
def generate_template(param_set, W, ratio, block_feature):
    print('block=',block_feature)
    res = None
    aggr = {}
    tmp = copy.deepcopy(param_set)
    cycles_sum = 0
    instruction_sum = 0
    llmiss_sum = 0
    for index, item in enumerate(tmp):
        block = item[0]
        
        # 确保rank为整数（因W和rank都是整数，直接相乘即可）
        rank = int(block[0] * W[index])
        
        if rank > 0:
            if res is None:
                res=[]
            cycles_sum +=block_feature['cycle'][index]
            instruction_sum +=block_feature['instruction'][index]
            llmiss_sum +=block_feature['ll_miss'][index]

            aggr={
                "CPI":cycles_sum/instruction_sum,
                "MPKI":llmiss_sum*1000/instruction_sum
            }
            new_block = copy.deepcopy(block)
            new_block[0] = rank
            new_block[2] = int(new_block[2] * ratio[index])  # 假设ratio是每block的缩放系数
            res.append(new_block)
    
    return res,aggr

# ---------------------------
# 主流程保持不变
# ---------------------------
block_path = './block.csv'
block_feature, param_sets = read_load_features(block_path)
aggr_df = pd.read_csv('stage/aggr.csv')

res = []
aggr_res = []
'''for _, aggr_row in aggr_df.iterrows():
    targets = {
        "CPI": aggr_row['CPI'],
        "MPKI": aggr_row['MPKI'],
        "duration": aggr_row['duration'],
        "instruction": aggr_row['instruction']
    }
    
    result, ratio = constrained_optimization(block_feature, targets)
    w_opt = result.X.astype(int)  # 确保取整
    
    template = generate_template(param_sets, w_opt, ratio)
    if template is not None:
        res.append(template)

res.append(16)
res.append(1)
# 结果保存（根据实际需求调整）
final_df = pd.DataFrame({'param_set': [res]})'''
for _, aggr_row in aggr_df.iterrows():
    targets = {
        "CPI": aggr_row['CPI'],
        "MPKI": aggr_row['MPKI'],
        "duration": aggr_row['duration'],
        "instruction": aggr_row['instruction']
    }
    
    result, ratio = constrained_optimization(block_feature, targets)
    w_opt = result.X.astype(int)  # 确保取整
    
    template,aggr= generate_template(param_sets, w_opt, ratio, block_feature)
    if template is not None:
        res.append([template,16,1])
        aggr_res.append(aggr)



# 结果保存（根据实际需求调整）
final_df = pd.DataFrame({'param_set': res})

final_df.to_csv('param_sets.csv', index=False)
print(aggr_res)