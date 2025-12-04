import copy
import numpy as np
from scipy.optimize import minimize
import pandas as pd
import ast
import os

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


def constrained_optimization(block_feature,targets):
    CPI_target = targets['CPI']
    MPKI_target = targets['MPKI']
    d_target = targets['duration']
    ins_target = targets['instruction']

    cycle = block_feature['cycle']
    instruction = block_feature['instruction']
    cache_miss = block_feature['ll_miss']
    rank = block_feature['rank']
    duration = block_feature['duration']
    block_type = block_feature['type']

    ratio = d_target / duration

    cycle = cycle*ratio
    instruction = instruction * ratio
    cache_miss = cache_miss * ratio
    duration = duration *ratio

    # 变量初始猜测（c_i=1, w_i=1）
    N = len(cycle)
    x0 = np.ones(N)

    # 目标函数
    def objective(x, rank, block_type):
        w = x
        s=w
        '''w_rank = w * rank
        s = np.round(w_rank)
        mask = (w_rank >= 0.1) & (w_rank <= 1)
        s[mask] = 1'''

        scaled_cycle = cycle * s
        scaled_instruction = instruction * s
        
        # 处理cache miss的特殊类型
        is_special_type = np.isin(block_type, ['div', 'add'])
        scaled_cache_miss = cache_miss * np.where(is_special_type, 1, s)
    
        total_cycle = np.sum(scaled_cycle)
        total_instruction = np.sum(scaled_instruction)
        total_cache_miss = np.sum(scaled_cache_miss)
        if total_instruction == 0:
            return np.inf  # 避免除以零
        CPI_actual = total_cycle / total_instruction
        MPKI_actual = (total_cache_miss / total_instruction) * 1000

        return (CPI_actual - CPI_target)**2 + (MPKI_actual - MPKI_target)**2 +((total_instruction-ins_target)/ins_target)**2
    # 约束条件
    constraints = [
        # Rank约束: sum(w_i * rank_i) <= 96
        {'type': 'ineq', 'fun': lambda x: 96 - np.sum(x * rank)}
    ]

    # 变量边界（w_i >=0）
    bounds = [(0, None)]*(N-1) + [(0,2)]

    # 优化求解
    result = minimize(
        objective,
        x0,
        method='SLSQP',
        args=(rank, block_type),
        bounds=bounds,
        constraints=constraints,
        options={'maxiter': 5000, 'ftol': 1e-6}
    )

    return result, ratio

def generate_template(param_set, W, C, block_feature):
    details = []  # 用于收集每个block的详细信息
    res = None
    tmp = copy.deepcopy(param_set)
    cycles_sum = 0
    instruction_sum = 0
    llmiss_sum = 0
    
    for index, item in enumerate(tmp):
        block = item[0]
        original_rank = block[0]
        block_type = block[1]
        W_val = W[index]
        C_val = C[index]
        
        # 计算rank和缩放因子
        
        scale =W_val 
        rank = original_rank*(int(scale)+1)   
        rank_scale = scale / (int(scale)+1) 

        
        if W_val > 1e-2:
            # 计算缩放后的指标
            scaled_cycles = block_feature['cycle'][index] * C_val *(rank/original_rank) * rank_scale
            scaled_instructions = block_feature['instruction'][index] * C_val *(rank/original_rank) * rank_scale
            if block_type in ['div','add']:
                scaled_llmiss = block_feature['ll_miss'][index]* rank_scale
            else:
                scaled_llmiss = block_feature['ll_miss'][index] * C_val *(rank/original_rank) * rank_scale
            scaled_duration =  block_feature['duration'][index] * C_val * rank_scale
            # 累加全局指标
            cycles_sum += scaled_cycles
            instruction_sum += scaled_instructions
            llmiss_sum += scaled_llmiss
            
            # 记录block详细信息
            block_detail = {
                'original_rank': original_rank,
                'W': W_val,
                'C': C_val,
                'scaled_rank': rank,
                'rank_scale_factor': rank_scale,
                'scaled_cycles': scaled_cycles,
                'scaled_instructions': scaled_instructions,
                'scaled_llmiss': scaled_llmiss,
                'scaled_duration':scaled_duration,
                'block_CPI': scaled_cycles / scaled_instructions,
                'block_MPKI': (scaled_llmiss * 1000) / scaled_instructions
            }
            details.append(block_detail)
            
            # 更新模板
            if res is None:
                res = []
            modified_block = copy.deepcopy(block)
            modified_block[0] = rank
            modified_block[2] = int(modified_block[2] * C_val * rank_scale)
            delay = 0
            modified_block.append(delay)
            res.append(modified_block)
    
    # 计算全局指标
    aggr = {
        "CPI": cycles_sum / instruction_sum if instruction_sum != 0 else 0,
        "MPKI": llmiss_sum * 1000 / instruction_sum if instruction_sum != 0 else 0,
        "instruction" : instruction_sum,
        "cycle": cycles_sum,
        "llmiss": llmiss_sum
    }
    
    return res, aggr, details
        


block_path = './block.csv'
block_feature, param_sets = read_load_features(block_path)
aggr_df = pd.read_csv('stage/aggr.csv')

res=[]
aggr_res=[]
all_block_details = []
s={
    "instruction" : 0,
    "cycle": 0,
    "llmiss": 0

}
for _, aggr_row in aggr_df.iterrows():

    targets = {
        "CPI": aggr_row['CPI'],
        "MPKI" :aggr_row['MPKI'],
        "duration":aggr_row['duration'],
        "instruction" :aggr_row['instruction']
        
    }

    #print(targets)
    result ,ratio= constrained_optimization(block_feature,targets)

    w_opt = result.x

    template, aggr, detail= generate_template(param_sets,w_opt,ratio,block_feature)
    #print(template)
    #print(detail)
    if template is not None:
        res.append(template)

    s['instruction']+=aggr['instruction']
    s['cycle']+=aggr['cycle']
    s['llmiss']+=aggr['llmiss']



print(s['instruction'],s['cycle'],s['llmiss'])
print(f'CPI = {s["cycle"]/s["instruction"]}')
print(f'MPKI = {s['llmiss']*1000/s['instruction']}')
    
res.append(16)
res.append(1)
final_df = pd.DataFrame({'param_set': [res]})
final_df.to_csv('param_sets.csv', index=False)

'''for target_id, (_, aggr_row) in enumerate(aggr_df.iterrows()):
    targets = {
        "CPI": aggr_row['CPI'],
        "MPKI": aggr_row['MPKI'],
        "duration": aggr_row['duration'],
        "instruction": aggr_row['instruction']
    }
    
    result, ratio = constrained_optimization(block_feature, targets)
    w_opt = result.x
    os.makedirs('block_detail', exist_ok=True)
    template,aggr,block_details= generate_template(param_sets, w_opt, ratio, block_feature)
    if template is not None:
        res.append([template,16,1])
        aggr_entry = {
            'target_id': target_id,
            'target_CPI': targets['CPI'],
            'target_MPKI': targets['MPKI'],
            'target_duration': targets['duration'],
            'target_instruction': targets['instruction'],
            'actual_CPI': aggr['CPI'],
            'actual_MPKI': aggr['MPKI'],
            'actual_instruction': aggr['instruction']
        }
        aggr_res.append(aggr_entry)
        # 为每个block添加target上下文信息
        if block_details:
            # 添加target上下文信息
            for detail in block_details:
                detail.update({
                    'target_id': target_id,
                    'target_CPI': targets['CPI'],
                    'target_MPKI': targets['MPKI'],
                    'target_duration': targets['duration'],
                    'target_instruction': targets['instruction']
                })
            
            # 构建DataFrame并保存
            details_df = pd.DataFrame(block_details)
            if not details_df.empty:
                # 计算总和
                cycles_sum = details_df['scaled_cycles'].sum()
                instructions_sum = details_df['scaled_instructions'].sum()
                llmiss_sum = details_df['scaled_llmiss'].sum()
                # 构造汇总行
                summary_row = {
                    'original_rank': 'Summary',
                    'W': None,
                    'C': None,
                    'scaled_rank': None,
                    'rank_scale_factor': None,
                    'scaled_cycles': cycles_sum,
                    'scaled_instructions': instructions_sum,
                    'scaled_llmiss': llmiss_sum,
                    'block_CPI': aggr['CPI'],
                    'block_MPKI': aggr['MPKI'],
                    'target_id': target_id,
                    'target_CPI': targets['CPI'],
                    'target_MPKI': targets['MPKI'],
                    'target_duration': targets['duration'],
                    'target_instruction': targets['instruction']
                }
                # 转换为DataFrame并合并
                summary_df = pd.DataFrame([summary_row])
                details_df = pd.concat([details_df, summary_df], ignore_index=True)
            
            filename = f"block_detail/target_{target_id:03d}.csv"  # 使用三位数编号
            details_df.to_csv(filename, index=False)
            print(f"Saved details for target {target_id} to {filename}")



# 结果保存（根据实际需求调整）
final_df = pd.DataFrame({'param_set': res})

final_df.to_csv('param_sets.csv', index=False)
# 保存aggr.csv
if aggr_res:
    aggr_df = pd.DataFrame(aggr_res)
    # 按列排序（可选）
    column_order = [
        'target_id',
        'target_CPI', 'actual_CPI',
        'target_MPKI', 'actual_MPKI', 'actual_instruction',
        'target_duration', 'target_instruction'
    ]
    aggr_df = aggr_df[column_order]
    aggr_df.to_csv('./block_detail/aggr.csv', index=False)
    print(f"Aggregated metrics saved to aggr.csv")
else:
    print("No aggregation data to save.")'''


'''import numpy as np
import pulp  # 导入PuLP库用于线性/整数规划

def solve_block_scheduling(len_i, cycle_i, instruction_i, miss_i, perf_CPI, perf_MPKI):
    """
    求解块调度优化问题
    
    参数:
        len_i: list of int, 每个块的长度
        cycle_i: list of float, 每个块的总周期数
        instruction_i: list of float, 每个块的总指令数
        miss_i: list of float, 每个块的总缓存未命中数
        perf_CPI: list of float, 每个时间点的目标CPI (长度T+1)
        perf_MPKI: list of float, 每个时间点的目标MPKI (长度T+1)
    
    返回:
        dict: 最优的delay_i值
        float: 最小目标函数值
    """
    N = len(len_i)  # 块的数量
    T = len(perf_CPI) - 1  # 最大时间点（从0到T）
    
    # 创建优化问题
    prob = pulp.LpProblem("Block_Scheduling", pulp.LpMinimize)
    
    # 定义决策变量（每个块的起始时间）
    delay_i = [
        pulp.LpVariable(f"delay_{i}", 
                         lowBound=0, 
                         upBound=T - len_i[i], 
                         cat=pulp.LpInteger) 
        for i in range(N)
    ]
    
    # 定义辅助变量（表示块i在时间t是否活跃）
    # 使用整数变量避免分段函数问题
    a = {}
    for i in range(N):
        for t in range(T + 1):
            a[i, t] = pulp.LpVariable(f"a_{i}_{t}", cat=pulp.LpBinary)
    
    # 添加约束：a[i,t] = 1 当且仅当 delay_i <= t < delay_i + len_i
    M = T + 10  # 大M值
    for i in range(N):
        for t in range(T + 1):
            # 约束：t >= delay_i ⇒ a[i,t] = 1
            prob += a[i, t] * M >= t + 1 - delay_i
            
            # 约束：t < delay_i + len_i ⇒ a[i,t] = 1
            prob += (1 - a[i, t]) * M >= delay_i + len_i[i] - t
            
            # 如果允许空闲时间点，可以取消下两行注释
            # prob += a[i, t] <= t + 1 - delay_i
            # prob += a[i, t] <= delay_i + len_i[i] - t
    
    # 定义目标函数
    # 为每个时间点t定义CPI_t和MPKI_t的表达式
    total_err = 0
    for t in range(T + 1):
        # 计算总周期数、指令数和未命中数
        total_cycle_t = pulp.lpSum(a[i, t] * cycle_i[i] for i in range(N))
        total_inst_t = pulp.lpSum(a[i, t] * instruction_i[i] for i in range(N))
        total_miss_t = pulp.lpSum(a[i, t] * miss_i[i] for i in range(N))
        
        # 定义CPI_t和MPKI_t
        # 使用大M方法避免除零错误
        epsilon = 1e-5  # 小常数
        
        # CPI_t = total_cycle_t / (total_inst_t + epsilon)
        # 使用分段线性近似
        CPI_t = total_cycle_t / (total_inst_t + epsilon)
        MPKI_t = 1000 * total_miss_t / (total_inst_t + epsilon)
        
        # 平方差项（使用二次近似）
        err_cpi = (CPI_t - perf_CPI[t])**2
        err_mpki = (MPKI_t - perf_MPKI[t])**2
        
        total_err += err_cpi + err_mpki
    
    # 设置目标函数
    prob += total_err
    
    # 求解问题
    prob.solve(pulp.PULP_CBC_CMD(msg=True))
    
    # 提取结果
    results = {
        i: pulp.value(delay_i[i]) 
        for i in range(N)
    }
    
    return results, pulp.value(prob.objective)

# 示例用法
if __name__ == "__main__":
    # 示例数据（实际应用中替换为真实数据）
    N = 3  # 3个块
    T = 10  # 时间点从0到10
    
    # 块参数
    len_i = [3, 4, 2]          # 每个块的长度
    cycle_i = [100, 150, 80]   # 总周期数
    instruction_i = [50, 75, 40]  # 总指令数
    miss_i = [10, 15, 8]        # 总未命中数
    
    # 目标性能指标（每个时间点CPI和MPKI）
    perf_CPI = [1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0]
    perf_MPKI = [5.0, 5.2, 5.4, 5.6, 5.8, 6.0, 6.0, 6.0, 6.0, 6.0, 6.0]
    
    # 求解问题
    optimal_delays, min_objective = solve_block_scheduling(
        len_i, cycle_i, instruction_i, miss_i, perf_CPI, perf_MPKI
    )
    
    # 输出结果
    print("Optimal delays:")
    for i, delay in optimal_delays.items():
        print(f"Block {i}: delay = {delay}")
    print(f"Minimum objective value: {min_objective}")'''

