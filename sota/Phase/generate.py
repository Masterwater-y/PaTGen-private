import argparse
import copy
import numpy as np
from scipy.optimize import minimize
import pandas as pd
import ast
import os
import sys
from datetime import datetime
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
    #ratio = [1]*len(duration)
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
        is_special_type = np.isin(block_type, ['div', 'add','sqrt'])
        scaled_cache_miss = cache_miss * np.where(is_special_type, 1, s)
    
        total_cycle = np.sum(scaled_cycle)
        total_instruction = np.sum(scaled_instruction)
        total_cache_miss = np.sum(scaled_cache_miss)
        if total_instruction == 0:
            return np.inf  # 避免除以零
        CPI_actual = total_cycle / total_instruction
        MPKI_actual = (total_cache_miss / total_instruction) * 1000
        lambda_l1 = 0.01
        l1_penalty = lambda_l1 * np.sum(np.abs(s))

        cycle_target = ins_target * CPI_target
        llc_target = ins_target * MPKI_target / 1000

        return lambda_l1*l1_penalty+((total_cycle - cycle_target)/cycle_target)**2 + ((total_cache_miss - llc_target)/llc_target)**2 +((total_instruction-ins_target)/ins_target)**2
        #return lambda_l1*l1_penalty+(CPI_actual - CPI_target)**2 + (MPKI_actual - MPKI_target)**2 +((total_instruction-ins_target)/ins_target)**2
        #return (CPI_actual - CPI_target)**2 + (MPKI_actual - MPKI_target)**2
    # 约束条件
    constraints = [
        # Rank约束: sum(w_i * rank_i) <= 96
        {'type': 'ineq', 'fun': lambda x: 72 - np.sum(x * rank)}
    ]

    # 变量边界（w_i >=0）
    #bounds = [(0, None)]*(N-1) + [(0,2)]
    bounds = [(0, None)]*(N)

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



def generate_block_details(param_set, W, C, block_feature):
    details = []    
    for index, item in enumerate(param_set):
        block = item[0]
        original_rank = block[0]
        block_type = block[1]
        W_val = W[index]
        C_val = C[index]
        
        scale = W_val
        rank = int(original_rank * scale) + 1
        iter_scale = scale * original_rank / rank
        
        if block_feature['duration'][index]*C_val*iter_scale >=1:
            # 计算缩放后的指标
            scaled_cycles = block_feature['cycle'][index] * C_val * (rank / original_rank) * iter_scale
            scaled_instructions = block_feature['instruction'][index] * C_val * (rank / original_rank) * iter_scale
            if block_type in ['div', 'add','sqrt']:
                scaled_llmiss = block_feature['ll_miss'][index] * C_val * iter_scale
            else:
                scaled_llmiss = block_feature['ll_miss'][index] * C_val * (rank / original_rank) * iter_scale
            scaled_duration = block_feature['duration'][index] * C_val * iter_scale

            
            # 记录block详细信息
            modified_block = copy.deepcopy(block)
            modified_block[0] = rank
            #modified_block[2] = int(modified_block[2] * C_val * iter_scale)
            modified_block[2] = int(modified_block[2] * C_val * iter_scale)
            delay = 0
            modified_block.append(delay)
            block_detail = {
                'original_rank': original_rank,
                'W': W_val,
                'C': C_val,
                'rank': rank,
                'iter_scale_factor': iter_scale,
                'cycles': scaled_cycles,
                'instructions': scaled_instructions,
                'llmiss': scaled_llmiss,
                'duration': int(scaled_duration),
                'block_CPI': scaled_cycles / scaled_instructions,
                'block_MPKI': (scaled_llmiss * 1000) / scaled_instructions,
                'template':modified_block,
                'delay':0
            }
            details.append(block_detail)
            
    
    return details

def calc_delay(block_list,T):
    #print(f'T={T}')
    cpi_block=[]
    mpki_block=[]
    for block in block_list:
        if block['template'][1] in ['add','div','sqrt']:
            cpi_block.append(block)
        else:
            mpki_block.append(block)
    bias = T/len(mpki_block)
    for i in range(len(mpki_block)):
        block = mpki_block[i]
        if bias*i+block['duration']<T:
            block['template'][-1]=int(bias*i)
        else:
            block['template'][-1] = T-block['duration']
    #print([block['template'][-1] for block in mpki_block])
    return block_list

def process_special_boundaries(block_list, target):

    
    # 检查是否只有一个 block
    if len(block_list) == 1:
        block = block_list[0]
        # 确保 block 和 target 都有 'duration' 键
        if 'duration' in block and 'duration' in target:
            block['template'][2] = block['template'][2] * target['duration'] / block['duration']
            block['duration'] = int(target['duration'])

    return block_list

def generate_template(block_list):
    res=[]
    cycles_sum=0
    instruction_sum=0
    llmiss_sum = 0
    duration_max = 0
    rank_total = 0
    for block in block_list:
        if 'delay' in block.keys():
            block['template'][-1]=block['delay']
        res.append(block['template'])
        cycles_sum += block['cycles']
        instruction_sum += block['instructions']
        llmiss_sum += block['llmiss']
        duration_max = max(duration_max,block['duration'])
        rank_total+=block['rank']
    aggr = {
        "CPI": cycles_sum / instruction_sum if instruction_sum != 0 else 0,
        "MPKI": llmiss_sum * 1000 / instruction_sum if instruction_sum != 0 else 0,
        "instruction" : instruction_sum,
        "cycle": cycles_sum,
        "llmiss": llmiss_sum,
        "duration": duration_max,
        "rank_total":rank_total
    }
    return res,aggr
 
import numpy as np
import random
import json
from typing import List, Dict, Tuple

def optimize_block_schedule_ga(blocks: List[Dict], perf_targets: List[Dict],
                                       population_size: int = 60, generations: int = 300,
                                       crossover_rate: float = 0.8, init_mutation_rate: float = 0.12,
                                       elite_k: int = 3, tournament_size: int = 3,
                                       local_search_iters: int = 2, stagnation_patience: int = 30) -> Dict:
    """
    改进版遗传算法：启发式/分层初始化 + 适应度缓存 + 局部搜索（爬山） + 自适应变异 + 多精英保留
    """
    N = len(blocks)
    T = len(perf_targets)

    # 目标CPI/MPKI
    target_CPI_t = np.array([perf['cycle'] / (perf['instruction'] + 1e-12) for perf in perf_targets])
    target_MPKI_t = np.array([perf['llmiss'] * 1000 / (perf['instruction'] + 1e-12) for perf in perf_targets])

    # 预计算每block的平均率（以便启发式）
    block_rate_score = []
    for b in blocks:
        inst_rate = b['instructions'] / max(1, b['duration'])
        cycle_rate = b['cycles'] / max(1, b['duration'])
        llmiss_rate = b['llmiss'] / max(1, b['duration'])
        # 简单组合评分（可依据应用调整）
        score = cycle_rate / max(1e-6, inst_rate) + 0.1 * llmiss_rate
        block_rate_score.append(score)
    # index 排序（高优先级先放）
    sorted_block_idx = sorted(range(N), key=lambda i: block_rate_score[i], reverse=True)

    # ---------- 初始种群：混合策略 ----------
    def gen_seed_greedy():
        # 贪婪：按时间点从0..T-1放置高评分块，尝试减少当前误差
        delays = [0]*N
        # 先把每个block放到0
        for i in range(N):
            delays[i] = 0
        # 对高评分块尝试把它放到使得局部误差最小的位置
        for idx in sorted_block_idx:
            best_d = delays[idx]
            best_fit = None
            max_delay = max(0, T - blocks[idx]['duration'])
            for d in range(0, max_delay+1, max(1, max(1, max_delay)//5)):  # 采样几个位置而非遍历全部以加速
                delays[idx] = d
                f = evaluate_fitness_cached(delays)  # 使用缓存（下面定义）
                if best_fit is None or f > best_fit:
                    best_fit = f
                    best_d = d
            delays[idx] = best_d
        ensure_constraint(delays)
        return delays

    def gen_latin_hypercube():
        # LHS 风格初始化：对每个 block 按其可行区间均匀采样
        delays = []
        for i in range(N):
            max_d = max(0, T - blocks[i]['duration'])
            if max_d == 0:
                delays.append(0)
            else:
                # 在 [0, max_d] 中做 stratified sample
                k = random.randint(0, max_d)
                delays.append(k)
        ensure_constraint(delays)
        return delays

    def gen_random():
        delays = []
        for i in range(N):
            max_d = max(0, T - blocks[i]['duration'])
            delays.append(random.randint(0, max_d) if max_d>0 else 0)
        ensure_constraint(delays)
        return delays

    # ---------- 适应度缓存 ----------
    fitness_cache = {}
    def individual_key(ind):
        return tuple(int(x) for x in ind)

    def evaluate_fitness_cached(individual: List[int]) -> float:
        k = individual_key(individual)
        if k in fitness_cache:
            return fitness_cache[k]
        val = evaluate_fitness(individual)
        fitness_cache[k] = val
        return val

    # ---------- 评估函数（保持你原先的定义，但用在缓存包装内） ----------
    def evaluate_fitness(individual: List[int]) -> float:
        cycle_t = np.zeros(T)
        instruction_t = np.zeros(T)
        llmiss_t = np.zeros(T)
        for i in range(N):
            start = int(individual[i])
            end = min(start + blocks[i]['duration'], T)
            if start < end:
                duration = blocks[i]['duration']
                cycle_t[start:end] += (blocks[i]['cycles'] / duration)
                instruction_t[start:end] += (blocks[i]['instructions'] / duration)
                llmiss_t[start:end] += (blocks[i]['llmiss'] / duration)
        eps = 1e-12
        CPI_t = cycle_t / (instruction_t + eps)
        MPKI_t = llmiss_t * 1000 / (instruction_t + eps)
        cpi_error = np.sum(((CPI_t - target_CPI_t) / (target_CPI_t + eps))**2)
        mpki_error = np.sum(((MPKI_t - target_MPKI_t) / (target_MPKI_t + eps))**2)
        return - (cpi_error + mpki_error)

    # ---------- 约束修复：优先选择对适应度影响小的改动 ----------
    def ensure_constraint(individual: List[int]) -> None:
        # 如果已有满足则直接返回
        if any(individual[i] + blocks[i]['duration'] == T for i in range(N)):
            return
        # 找出可行块（duration <= T）
        poss = [i for i in range(N) if blocks[i]['duration'] <= T]
        if not poss:
            # 无可行块：将某个（0..N-1）设为最大可能
            if N>0:
                idx = random.randrange(N)
                individual[idx] = max(0, T - blocks[idx]['duration'])
            return
        # 从可行块中选择一个，使得把它设置为结束T-1对适应度代价最小
        best_idx = None
        best_loss = None
        for i in poss:
            old = individual[i]
            candidate = max(0, T - 1 - blocks[i]['duration'])
            individual[i] = candidate
            loss = - evaluate_fitness_cached(individual)  # 目标为负误差
            # 恢复
            individual[i] = old
            if best_loss is None or loss < best_loss:
                best_loss = loss
                best_idx = i
        if best_idx is not None:
            individual[best_idx] = max(0, T - 1 - blocks[best_idx]['duration'])

    # ---------- 局部搜索（微爬山）：对个体做有限步的 +-1 调整 ----------
    def local_search(individual: List[int], iters: int = 2):
        improved = True
        it = 0
        base_fit = evaluate_fitness_cached(individual)
        while it < iters and improved:
            improved = False
            it += 1
            for i in range(N):
                dur = blocks[i]['duration']
                max_d = max(0, T - dur)
                cur = individual[i]
                # try neighbors -1, +1
                for cand in (cur-1, cur+1):
                    if cand < 0 or cand > max_d:
                        continue
                    individual[i] = cand
                    f = evaluate_fitness_cached(individual)
                    if f > base_fit + 1e-12:
                        base_fit = f
                        improved = True
                        break  # accept first improving move
                    else:
                        individual[i] = cur
                if improved:
                    break
        ensure_constraint(individual)
        return individual

    # ---------- 交叉与变异 ----------
    def crossover(parent1: List[int], parent2: List[int]) -> Tuple[List[int], List[int]]:
        if N < 2 or random.random() > crossover_rate:
            return parent1.copy(), parent2.copy()
        # 使用两点交叉（和你原来类似）
        cpoints = sorted(random.sample(range(1, N), min(2, N-1)))
        c1, c2 = cpoints if len(cpoints) == 2 else (cpoints[0], cpoints[0])
        child1 = parent1[:c1] + parent2[c1:c2] + parent1[c2:]
        child2 = parent2[:c1] + parent1[c1:c2] + parent2[c2:]
        # 修复越界
        for i in range(N):
            max_d = max(0, T - blocks[i]['duration'])
            child1[i] = max(0, min(child1[i], max_d))
            child2[i] = max(0, min(child2[i], max_d))
        ensure_constraint(child1)
        ensure_constraint(child2)
        return child1, child2

    def mutate(individual: List[int], mutation_rate: float) -> List[int]:
        for i in range(N):
            if random.random() < mutation_rate:
                max_d = max(0, T - blocks[i]['duration'])
                individual[i] = random.randint(0, max_d) if max_d>0 else 0
        ensure_constraint(individual)
        return individual

    # ---------- 种群初始化混合（随机 + LHS + 贪婪） ----------
    population = []
    # 半随机/分层
    num_greedy = max(2, population_size // 8)
    num_lhs = max(4, population_size // 4)
    num_random = population_size - num_greedy - num_lhs
    # 先清空缓存（确保 evaluate_fitness_cached 可用）
    fitness_cache.clear()
    for _ in range(num_greedy):
        population.append(gen_seed_greedy())
    for _ in range(num_lhs):
        population.append(gen_latin_hypercube())
    for _ in range(num_random):
        population.append(gen_random())

    # ---------- 主循环（带自适应变异和早停） ----------
    best_fitness = float('-inf')
    best_individual = None
    fitness_history = []
    avg_history = []
    std_history = []
    stagnation_counter = 0
    mutation_rate = init_mutation_rate

    for gen in range(generations):
        # 评估种群（使用缓存）
        fitness_vals = [evaluate_fitness_cached(ind) for ind in population]
        # 记录统计
        idx_best = int(np.argmax(fitness_vals))
        gen_best_f = fitness_vals[idx_best]
        gen_best_ind = population[idx_best].copy()
        if gen_best_f > best_fitness + 1e-12:
            best_fitness = gen_best_f
            best_individual = gen_best_ind.copy()
            stagnation_counter = 0
        else:
            stagnation_counter += 1

        fitness_history.append(-best_fitness)
        avg_history.append(-np.mean(fitness_vals))
        std_history.append(np.std(fitness_vals))

        # 自适应变异：若停滞则增加变异，若持续改进则微降
        if stagnation_counter > 0 and stagnation_counter % (max(1, stagnation_patience//3)) == 0:
            mutation_rate = min(0.5, mutation_rate * 1.5)
        else:
            mutation_rate = max(0.02, mutation_rate * 0.995)

        # 精英保留 top K
        ranked_idx = sorted(range(len(population)), key=lambda i: fitness_vals[i], reverse=True)
        elites = [population[i].copy() for i in ranked_idx[:elite_k]]

        # 新种群
        new_pop = elites.copy()

        # steady-state filling with selection + crossover + mutation + local search
        while len(new_pop) < population_size:
            # tournament selection
            def tournament():
                contestants = random.sample(population, min(tournament_size, len(population)))
                return max(contestants, key=lambda ind: evaluate_fitness_cached(ind))
            p1 = tournament().copy()
            p2 = tournament().copy()
            c1, c2 = crossover(p1, p2)
            c1 = mutate(c1, mutation_rate)
            c2 = mutate(c2, mutation_rate)
            # 局部搜索（短）：对孩子做微爬山
            c1 = local_search(c1, iters=local_search_iters)
            c2 = local_search(c2, iters=local_search_iters)
            new_pop.append(c1)
            if len(new_pop) < population_size:
                new_pop.append(c2)

        # 多样性注入：若种群方差太小，则替换一部分为随机个体
        pop_fits = [evaluate_fitness_cached(ind) for ind in new_pop]
        if np.std(pop_fits) < 1e-6:
            # TODO: 更复杂的策略可根据需要实现
            for _ in range(max(1, population_size//10)):
                new_pop[random.randrange(len(new_pop))] = gen_random()

        population = new_pop

        # 早停（可选）：若长期停滞
        if stagnation_counter > stagnation_patience:
            # print(f"Stopping early at gen {gen} due to stagnation.")
            break

    # 计算最终指标
    delays = best_individual
    cycle_t = np.zeros(T); instruction_t = np.zeros(T); llmiss_t = np.zeros(T)
    for i in range(N):
        start = int(delays[i]); end = min(start + blocks[i]['duration'], T)
        if start < end:
            dur = blocks[i]['duration']
            cycle_t[start:end] += (blocks[i]['cycles'] / dur)
            instruction_t[start:end] += (blocks[i]['instructions'] / dur)
            llmiss_t[start:end] += (blocks[i]['llmiss'] / dur)
    eps = 1e-12
    CPI_t = cycle_t / (instruction_t + eps)
    MPKI_t = llmiss_t * 1000 / (instruction_t + eps)

    result = {
        'success': True,
        'objective_value': -best_fitness,
        'delays': delays,
        'CPI': CPI_t,
        'MPKI': MPKI_t,
        'target_CPI': target_CPI_t,
        'target_MPKI': target_MPKI_t,
        'fitness_history': fitness_history,
        'convergence_data': {
            'generations': list(range(len(fitness_history))),
            'best_objective': fitness_history,
            'avg_objective': avg_history,
            'std_fitness': std_history
        },
        'meta': {
            'final_generation': len(fitness_history)-1,
            'stagnation_counter': stagnation_counter,
            'mutation_rate': mutation_rate
        }
    }
    return result

def visualize_convergence(result: Dict, output_file: str = None, show_plot: bool = True):
    """
    可视化遗传算法的收敛过程
    
    参数:
    result: 优化结果字典
    output_file: 图片保存路径，为None则不保存
    show_plot: 是否显示图片
    
    返回:
    无
    """
    import matplotlib.pyplot as plt
    convergence_data = result['convergence_data']
    
    plt.figure(figsize=(12, 5))
    
    plt.subplot(1, 2, 1)
    plt.plot(convergence_data['generations'], convergence_data['best_objective'], label='Best Objective')
    plt.plot(convergence_data['generations'], convergence_data['avg_objective'], label='Average Objective')
    plt.xlabel('Generation')
    plt.ylabel('Objective Value (Lower is Better)')
    plt.title('Convergence Process')
    plt.legend()
    plt.grid(True)
    
    plt.subplot(1, 2, 2)
    plt.plot(convergence_data['generations'], convergence_data['std_fitness'])
    plt.xlabel('Generation')
    plt.ylabel('Standard Deviation')
    plt.title('Population Diversity')
    plt.grid(True)
    
    plt.tight_layout()
    
    if output_file:
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"Convergence plot saved to {output_file}")
    
    if show_plot:
        plt.show()
    else:
        plt.close()

def save_convergence_data(result: Dict, output_file: str):
    """
    将收敛过程数据保存到文件
    
    参数:
    result: 优化结果字典
    output_file: 文件保存路径
    
    返回:
    无
    """
    convergence_data = result['convergence_data']
    
    with open(output_file, 'w') as f:
        # 写入标题行
        f.write("Generation,Best_Objective,Avg_Objective,Fitness_Std\n")
        
        # 写入数据
        for gen, best, avg, std in zip(
            convergence_data['generations'],
            convergence_data['best_objective'],
            convergence_data['avg_objective'],
            convergence_data['std_fitness']
        ):
            f.write(f"{gen},{best},{avg},{std}\n")
    
    print(f"Convergence data saved to {output_file}")
def instruction_optimized(aggr_df,targets,mask):
    CPI_target = targets['CPI']
    MPKI_target = targets['MPKI']
    #increase = targets['duration']

    CPI = aggr_df['CPI']
    MPKI = aggr_df['MPKI']
    instruction = aggr_df['instruction']

    # 变量初始猜测（c_i=1, w_i=1）
    N = len(CPI)
    x0 = np.ones(N)

    # 目标函数
    def objective(x):
        s = x

        scaled_cycle = CPI * instruction * s
        scaled_instruction = instruction * s
        scaled_cache_miss = MPKI * s * instruction /1000
        total_cycle = np.sum(scaled_cycle)
        total_instruction = np.sum(scaled_instruction)
        total_cache_miss = np.sum(scaled_cache_miss)
        if total_instruction == 0:
            return np.inf  # 避免除以零
        CPI_actual = total_cycle / total_instruction
        MPKI_actual = (total_cache_miss / total_instruction) * 1000

        return (CPI_actual - CPI_target)**2 + (MPKI_actual - MPKI_target)**2
        #return (CPI_actual - CPI_target)**2 + (MPKI_actual - MPKI_target)**2
    # 约束条件
    constraints = [
    ]

    # 变量边界（w_i >=0）
    #bounds = [(0, None)]*(N-1) + [(0,2)]
    bounds = [(1.0, 1.0) if m else (1.0, 2.0) for m in mask]

    # 优化求解
    result = minimize(
        objective,
        x0,
        method='SLSQP',
        args=(),
        bounds=bounds,
        constraints=constraints,
        options={'maxiter': 5000, 'ftol': 1e-6}
    )

    return result


def find_optimal_threshold(aggr_df, global_targets, initial_threshold=6e10, step=1e10, search_range=5):
    """
    寻找最优阈值，使得调整后的CPI和MPKI与目标值的差距最小
    
    参数:
    aggr_df: 聚合数据DataFrame
    global_targets: 全局目标DataFrame
    initial_threshold: 初始阈值
    step: 搜索步长
    search_range: 搜索范围（正负方向的步数）
    
    返回:
    最优阈值和对应的误差
    """
    best_threshold = initial_threshold
    best_error = float('inf')
    # 定义目标函数
    def objective(threshold):
        # 使用当前阈值修改指令
        df = aggr_df.copy()
        modified_df = modify_instruction(df, global_targets, threshold)
        
        # 提取性能数据
        CPI = modified_df['CPI']
        MPKI = modified_df['MPKI']
        instruction = modified_df['instruction']
        
        # 获取目标值
        target_cpi = global_targets.iloc[0]['CPI']
        target_mpki = global_targets.iloc[0]['MPKI']
        
        # 计算缩放后的性能指标
        scaled_cycle = CPI * instruction
        scaled_instruction = instruction
        scaled_cache_miss = MPKI * instruction / 1000
        
        # 计算总量
        total_cycle = np.sum(scaled_cycle)
        total_instruction = np.sum(scaled_instruction)
        total_cache_miss = np.sum(scaled_cache_miss)
        
        # 计算调整后的总体CPI和MPKI
        adjusted_CPI = total_cycle / total_instruction
        adjusted_MPKI = (total_cache_miss / total_instruction) * 1000
        
        # 计算与目标值的误差（使用平方和）
        error = (adjusted_CPI - target_cpi) ** 2 + (adjusted_MPKI - target_mpki) ** 2
        return error
    
    # 网格搜索
    for i in range(-search_range, search_range + 1):
        current_threshold = initial_threshold + i * step
        current_error = objective(current_threshold)
        
        if current_error < best_error:
            best_error = current_error
            best_threshold = current_threshold
    
    # 使用优化算法进一步精细化
    
    result = minimize(objective, best_threshold, method='Nelder-Mead')
    refined_threshold = result.x[0]
    
    #refined_threshold = best_threshold
    return refined_threshold, objective(refined_threshold)



def modify_instruction(aggr_df,global_targets,threshold = 6e10, info=False):
    df = aggr_df.copy()
    df['ips'] = df['instruction'] / df['duration']
    mask = df['ips'].values < threshold 
    #print(mask)
    filtered_df = df[mask].copy()
    factor = threshold
    if factor<3e10:
        factor = 3e10
    # 计算需要增加的总量
    original_instructions = filtered_df['instruction'].sum()
    target_instructions = filtered_df['duration'].sum() * factor
    total_increase = target_instructions - original_instructions

    


    df.loc[mask, 'instruction'] = df.loc[mask, 'duration'] * factor
    targets = {
        "CPI":global_targets.iloc[0]['CPI'],
        "MPKI":global_targets.iloc[0]['MPKI'],
    }
    #print(targets)
    result = instruction_optimized(aggr_df,targets,mask)
    #print(result.x)
    s=result.x
     # 提取性能数据
    CPI = df['CPI']
    MPKI = df['MPKI']
    instruction = df['instruction']
    
    # 计算缩放后的性能指标
    scaled_cycle = CPI * instruction * s
    scaled_instruction = instruction * s
    scaled_cache_miss = MPKI * s * instruction/1000
    
    # 计算总量
    total_cycle = np.sum(scaled_cycle)
    total_instruction = np.sum(scaled_instruction)
    total_cache_miss = np.sum(scaled_cache_miss)
    
    # 计算调整后的总体CPI和MPKI
    adjusted_CPI = total_cycle / total_instruction
    adjusted_MPKI = (total_cache_miss / total_instruction) * 1000
    if info:
        print(f"调整后的总体CPI: {adjusted_CPI:.4f} (目标: {targets['CPI']:.4f})")
        print(f"调整后的总体MPKI: {adjusted_MPKI:.4f} (目标: {targets['MPKI']:.4f}")

    df['instruction'] = df['instruction'] * s
    #df.to_csv('./tmp.csv')
    return df
'''def generate_template(param_set, W, C, block_feature):
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
        #rank = original_rank*(int(scale)+1)   
        #rank_scale = scale / (int(scale)+1)      
        rank = int(original_rank*scale)+1  
        iter_scale = scale * original_rank/rank   #iter_scale*rank/original_rank = scale
        if W_val > 1e-2:
            # 计算缩放后的指标
            scaled_cycles = block_feature['cycle'][index] * C_val *(rank/original_rank) * iter_scale
            scaled_instructions = block_feature['instruction'][index] * C_val *(rank/original_rank) * iter_scale
            if block_type in ['div','add']:
                scaled_llmiss = block_feature['ll_miss'][index]* iter_scale
            else:
                scaled_llmiss = block_feature['ll_miss'][index] * C_val *(rank/original_rank) * iter_scale
            scaled_duration =  block_feature['duration'][index] * C_val * iter_scale
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
                'iter_scale_factor': iter_scale,
                'scaled_cycles': scaled_cycles,
                'scaled_instructions': scaled_instructions,
                'scaled_llmiss': scaled_llmiss,
                'scaled_duration':scaled_duration,
                'block_CPI': scaled_cycles / scaled_instructions,
                'block_MPKI': (scaled_llmiss * 1000) / scaled_instructions
            }
            details.append(block_detail)
            
        
            if res is None:
                res = []
            modified_block = copy.deepcopy(block)
            modified_block[0] = rank
            modified_block[2] = int(modified_block[2] * C_val * iter_scale)
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
        

'''



parser = argparse.ArgumentParser(description='运行PhaseRunner任务')

parser.add_argument('--sample_index', type=int, required=True, default=0, help='样本索引')
parser.add_argument('--phase_index', type=int,  help='阶段索引')
parser.add_argument('--result_dir', type=str,  help='结果存放目录')

parser.add_argument('--delay_iters', type=int, default=0, help='GA迭代次数')
args = parser.parse_args()
print(args)
block_path = '../multi_rank_block.csv'
block_feature, param_sets = read_load_features(block_path)

sample_index = args.sample_index
phase_index = args.phase_index
result_dir = args.result_dir

stage_dir = f'stage{sample_index}'
if result_dir:
    GA_dir = f'{result_dir}/GA'
    if not os.path.exists(GA_dir):
        os.makedirs(GA_dir)
aggr_df = pd.read_csv(f'{stage_dir}/aggr.csv')
global_targets = pd.read_csv(f'{stage_dir}/targets.csv')

tmp_df = aggr_df.copy()
optimal_threshold, min_error = find_optimal_threshold(tmp_df, global_targets)

aggr_df = modify_instruction(aggr_df,global_targets,threshold=optimal_threshold,info = True)
print("threshold=",optimal_threshold)

res=[]
aggr_res=[]

s={
    "instruction" : 0,
    "cycle": 0,
    "llmiss": 0,
    "duration":0
}
all_block_lists = []
for i, aggr_row in aggr_df.iterrows():

    if phase_index is not None:
        if i!=phase_index:
            continue
    targets = {
        "CPI": aggr_row['CPI'],
        "MPKI" :aggr_row['MPKI'],
        "duration":aggr_row['duration'],
        "instruction" :aggr_row['instruction']
    }
    
    print(targets)
    result ,ratio= constrained_optimization(block_feature,targets)
    
    w_opt = result.x
    block_list = generate_block_details(param_sets,w_opt,ratio,block_feature)
    #print(block_list)
    metric_df = pd.read_csv(f'stage{sample_index}/sub/metric_{i}.csv')
    perf_targets = metric_df.rename(columns={
        'cycles': 'cycle',
        'instructions': 'instruction',
        'll-misses/': 'llmiss'
    }).loc[:, ['cycle', 'instruction', 'llmiss']].to_dict('records')
    
    # 将数值转换为浮点数
    for target in perf_targets:
        for key in ['cycle', 'instruction', 'llmiss']:
            target[key] = float(target[key])
    



    #result = constrained_optimization(block_list,perf_targets)
    #print(result)
    block_list = process_special_boundaries(block_list,targets)
    tmp = None
    if args.delay_iters:
        tmp = optimize_block_schedule_ga(block_list,perf_targets,generations=args.delay_iters)
        delay = tmp['delays']
        for j in range(len(delay)):
            block_list[j]['delay']=delay[j]
    
    all_block_lists.append(block_list)
    if result_dir is not None and tmp is not None:
        # 可视化并保存图片
        visualize_convergence(tmp, output_file=f"{GA_dir}/convergence_plot{i}.png")

        # 保存收敛过程数据到CSV文件
        save_convergence_data(tmp, output_file=f"{GA_dir}/convergence_data{i}.csv")
    #block_list = calc_delay(block_list,targets['duration'])
    template, aggr= generate_template(block_list=block_list)

    #template, aggr, detail= generate_template(param_sets,w_opt,ratio,block_feature)
    #print(template)

    if template is not None:
        res.append(template)

    s['instruction']+=aggr['instruction']
    s['cycle']+=aggr['cycle']
    s['llmiss']+=aggr['llmiss']
    s['duration']+=aggr['duration']
    print(aggr['rank_total'])

with open('./all_block_lists.json', 'w') as f:
    json.dump(all_block_lists, f, indent=2)


print(s['instruction'],s['cycle'],s['llmiss'])
print(f'CPI = {s["cycle"]/s["instruction"]}')
print(f'MPKI = {s['llmiss']*1000/s['instruction']}')
print(f'duration = {s['duration']}')
    
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



