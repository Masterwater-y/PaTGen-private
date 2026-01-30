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
        {'type': 'ineq', 'fun': lambda x: 84 - np.sum(x * rank)}
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


'''def constrained_optimization_new(block_feature, targets):
    CPI_target = targets['CPI']
    MPKI_target = targets['MPKI']
    d_target = targets['duration']
    ins_target = targets['instruction']

    cycle = block_feature['cycle'].astype(float)
    instruction = block_feature['instruction'].astype(float)
    cache_miss = block_feature['ll_miss'].astype(float)
    rank = block_feature['rank']
    duration = block_feature['duration'].astype(float)
    block_type = np.array(block_feature['type'])

    sqrt_mask = (block_type == "sqrt")
    calc_mask = (block_type== "sqrt") | (block_type == "add") | (block_type == "div") 
    # duration 对齐
    ratio = d_target / duration
    ratio[calc_mask] = ratio[calc_mask] * 0.7
    cycle = cycle * ratio
    instruction = instruction * ratio
    cache_miss = cache_miss * ratio
    duration = duration * ratio

    N = len(cycle)
    x0 = np.ones(N)

    # 经验点：threads -> instruction scale （你给的点）
    sqrt_points = np.array([1, 2, 4, 8, 12, 16], dtype=float)
    sqrt_scales = np.array([1.0, 1.2, 2.4, 4.0, 5.5, 7.0], dtype=float)

    # 拟合仿射模型 scale(t) ≈ a + b * t
    # 若希望更稳健，可以加截断使 a+b*t >= small_eps
    A = np.vstack([np.ones_like(sqrt_points), sqrt_points]).T
    coeff, *_ = np.linalg.lstsq(A, sqrt_scales, rcond=None)
    a_fit, b_fit = coeff[0], coeff[1]

    # 为数值稳健，确保预测非负
    def instr_scale_from_threads(t):
        val = a_fit + b_fit * t
        # 下限裁剪，避免负值（保持凸性不受影响）
        return np.maximum(val, 1e-6)

    def objective(x, rank, block_type):
        w = x  # 线性变量（所有块用同一变量 w_i）

        # scaled cycle: 对所有块均线性
        scaled_cycle = cycle * w

        # scaled instruction:
        scaled_instruction = np.zeros_like(instruction)
        for i in range(N):
            if block_type[i] == 'sqrt':
                t = w[i]
                scale = instr_scale_from_threads(t)  # 这里是仿射拟合结果，关于 w 是线性
                scaled_instruction[i] = instruction[i] * scale
            else:
                # 线性缩放（其他类型）
                scaled_instruction[i] = instruction[i] * w[i]

        # cache_miss 特殊逻辑（保留你之前的约定）
        is_special_type = np.isin(block_type, ['div', 'add', 'sqrt'])
        scaled_cache_miss = cache_miss * np.where(is_special_type, 1, w)

        total_cycle = np.sum(scaled_cycle)
        total_instruction = np.sum(scaled_instruction)
        total_cache_miss = np.sum(scaled_cache_miss)

        if total_instruction == 0:
            return np.inf

        lambda_l1 = 0.01
        l1_penalty = lambda_l1 * np.sum(np.abs(w))

        cycle_target = ins_target * CPI_target
        llc_target = ins_target * MPKI_target / 1000.0

        return (
            lambda_l1 * l1_penalty
            + ((total_cycle - cycle_target) / cycle_target) ** 2
            + ((total_cache_miss - llc_target) / llc_target) ** 2
            + ((total_instruction - ins_target) / ins_target) ** 2
        )

    # 约束：rank 线性约束
    constraints = [{'type': 'ineq', 'fun': lambda x: 84.0 - np.sum(x * rank)}]

    bounds = [(0.0, None)] * N

    result = minimize(
        objective,
        x0,
        method='SLSQP',
        args=(rank, block_type),
        bounds=bounds,
        constraints=constraints,
        options={'maxiter': 5000, 'ftol': 1e-6}
    )

    return result, ratio'''

def constrained_optimization_new(block_feature, targets, balance_ratio):
    CPI_target = targets['CPI']
    MPKI_target = targets['MPKI']
    d_target = targets['duration']
    ins_target = targets['instruction']

    cycle = block_feature['cycle'].astype(float)
    instruction = block_feature['instruction'].astype(float)
    cache_miss = block_feature['ll_miss'].astype(float)
    rank = block_feature['rank']
    duration = block_feature['duration'].astype(float)
    block_type = np.array(block_feature['type'])

    # 类型 mask
    calc_mask = np.isin(block_type, ["sqrt", "add", "div"])

    # duration 对齐
    ratio = d_target / duration
    ratio[calc_mask] = ratio[calc_mask] * balance_ratio

    # 初始 scale（非常关键）
    cycle = cycle * ratio
    instruction = instruction * ratio
    cache_miss = cache_miss * ratio
    duration = duration * ratio

    N = len(cycle)
    x0 = np.ones(N)

    # sqrt threads vs instruction scaling
    sqrt_points = np.array([1, 2, 4, 8, 12, 16], dtype=float)
    sqrt_scales = np.array([1.0, 1.2, 2.4, 4.0, 5.5, 7.0], dtype=float)
    A = np.vstack([np.ones_like(sqrt_points), sqrt_points]).T
    coeff, *_ = np.linalg.lstsq(A, sqrt_scales, rcond=None)
    a_fit, b_fit = coeff[0], coeff[1]

    def instr_scale_from_threads(t):
        return max(a_fit + b_fit * t, 1e-6)

    # ------- 目标函数 --------
    def objective(x, rank, block_type):
        w = x

        scaled_cycle = cycle * w

        scaled_instruction = np.zeros_like(instruction)
        for i in range(N):
            if block_type[i] == "sqrt":
                scaled_instruction[i] = instruction[i] * instr_scale_from_threads(w[i])
            else:
                scaled_instruction[i] = instruction[i] * w[i]

        is_special_type = np.isin(block_type, ['div', 'add', 'sqrt'])
        scaled_cache_miss = cache_miss * np.where(is_special_type, 1, w)

        total_cycle = np.sum(scaled_cycle)
        total_instruction = np.sum(scaled_instruction)
        total_cache_miss = np.sum(scaled_cache_miss)

        if total_instruction == 0:
            return np.inf

        cycle_target = ins_target * CPI_target
        llc_target = ins_target * MPKI_target / 1000.0

        return (
            ((total_cycle - cycle_target) / cycle_target) ** 2 +
            ((total_cache_miss - llc_target) / llc_target) ** 2 +
            ((total_instruction - ins_target) / ins_target) ** 2
        )

    constraints = [{'type': 'ineq', 'fun': lambda x: 84.0 - np.sum(x * rank)}]
    bounds = [(0.0, None)] * N

    res = minimize(
        objective,
        x0,
        args=(rank, block_type),
        method='SLSQP',
        bounds=bounds,
        constraints=constraints,
        options={'maxiter': 5000, 'ftol': 1e-6}
    )

    # ---- 返回模板聚合值 ----
    w_opt = res.x
    total_cycle = np.sum(cycle * w_opt)
    total_instruction = np.sum(instruction * w_opt)
    total_llmiss = np.sum(cache_miss * w_opt)

    aggr = {
        "CPI": total_cycle / total_instruction,
        "MPKI": total_llmiss * 1000 / total_instruction,
        "cycle": total_cycle,
        "instruction": total_instruction,
        "llmiss": total_llmiss,
        "duration": np.max(duration * w_opt),
    }

    return res, ratio, aggr


def fit_thread_to_instr_scale():
    sqrt_points = np.array([1, 2, 4, 8, 12, 16], dtype=float)
    sqrt_scales = np.array([1.0, 1.2, 2.4, 4.0, 5.5, 7.0], dtype=float)
    A = np.vstack([np.ones_like(sqrt_points), sqrt_points]).T
    coeff, *_ = np.linalg.lstsq(A, sqrt_scales, rcond=None)
    a_fit, b_fit = coeff[0], coeff[1]
    return a_fit, b_fit

a_fit_global, b_fit_global = fit_thread_to_instr_scale()

def instr_scale_from_threads_continuous(t):
    # affine mapping a + b * t, clipped at small positive
    return np.maximum(a_fit_global + b_fit_global * t, 1e-6)


# -------------------------
# 第一层：求 w_opt（线程/指令缩放因子），但不改变每块相对时间比（交由第二层）
# -------------------------
def solve_thread_scaling(block_feature, targets, rank_cap=84.0):
    """
    输入 block_feature 字典（与原来格式兼容），targets 字典。
    返回：result (scipy OptimizeResult), ratio (d_target / duration 原始)
    注意：此函数在内部对所有原始指标做 ratio 对齐（保持与你目前 pipeline 接口一致），
    但**不会**在本阶段改变每个块的 duration 的相对份额（那由第二层 c_i 控制）。
    """
    CPI_target = float(targets['CPI'])
    MPKI_target = float(targets['MPKI'])
    d_target = float(targets['duration'])
    ins_target = float(targets['instruction'])

    # 原始数组（和你当前代码一致）
    cycle_raw = np.array(block_feature['cycle'], dtype=float)
    instruction_raw = np.array(block_feature['instruction'], dtype=float)
    llmiss_raw = np.array(block_feature['ll_miss'], dtype=float)
    rank = np.array(block_feature['rank'], dtype=float)
    duration_raw = np.array(block_feature['duration'], dtype=float)
    block_type = np.array(block_feature['type'])

    # duration 对齐（保持接口一致）：把 baseline 对齐到阶段时长（你原来做的）
    # ratio 是用于 generate_block_details 的基础因子（后面我们会乘以 c_i）
    ratio = d_target / np.maximum(duration_raw, 1e-9)

    # aligned baseline quantities (表示“如果一个块跑满 phase 的 baseline 值”)
    cycle0 = cycle_raw * ratio
    instr0 = instruction_raw * ratio
    miss0 = llmiss_raw * ratio
    duration0 = duration_raw * ratio  # 这一项表示 baseline 时长（通常等于 d_target）

    # 防止 division by zero
    instr0_nonzero = np.maximum(instr0, 1.0)
    miss_rate0 = miss0 / instr0_nonzero  # miss per instruction, 物理意义稳定

    N = len(cycle0)
    x0 = np.ones(N)

    # objective: 和你原先类似，但把 cache_miss 视作 miss_rate * scaled_instruction（物理合理）
    cycle_target = ins_target * CPI_target
    llc_target = ins_target * MPKI_target / 1000.0

    lambda_l1 = 0.01

    def objective_w(x):
        w = np.maximum(x, 0.0)  # enforce non-negativity inside objective for numeric stability

        # scaled cycle: for non-sqrt, linear w; for sqrt use affine instr scaling then convert to cycles similarly
        scaled_cycle = np.zeros(N)
        scaled_instruction = np.zeros(N)

        for i in range(N):
            if block_type[i] == 'sqrt':
                # treat w[i] as thread count factor for sqrt -> use instr_scale_from_threads_continuous
                scale = instr_scale_from_threads_continuous(w[i])
                scaled_instruction[i] = instr0[i] * scale
                scaled_cycle[i] = cycle0[i] * scale
            else:
                # other types: linear scaling with w
                scaled_instruction[i] = instr0[i] * w[i]
                scaled_cycle[i] = cycle0[i] * w[i]

        # scaled miss uses miss_rate0 * scaled_instruction (so compute-only blocks with near-zero miss_rate stay near zero)
        scaled_miss = miss_rate0 * scaled_instruction

        total_cycle = np.sum(scaled_cycle)
        total_instruction = np.sum(scaled_instruction)
        total_miss = np.sum(scaled_miss)

        if total_instruction <= 0:
            return np.inf

        l1_pen = lambda_l1 * np.sum(np.abs(w))

        return (
            l1_pen
            + ((total_cycle - cycle_target) / max(cycle_target, 1e-9)) ** 2
            + ((total_miss - llc_target) / max(llc_target, 1e-9)) ** 2
            + ((total_instruction - ins_target) / max(ins_target, 1e-9)) ** 2
        )

    # rank 约束（线性不等式）
    cons = [{'type': 'ineq', 'fun': lambda x: rank_cap - np.sum(np.maximum(x, 0.0) * rank)}]
    bounds = [(0.0, None)] * N

    res = minimize(objective_w, x0, method='SLSQP', bounds=bounds, constraints=cons,
                   options={'maxiter': 5000, 'ftol': 1e-6})

    # 返回结果以及 ratio（保留与之前接口一致）
    return res, ratio


# -------------------------
# 第二层：在已知 w_opt 情况下，求 duration_scale c（每个块的相对于 d_target 的时长占比因子）
# 约束：0 <= c_i <= 1, sum(c_i) >= 1 （并行覆盖满），每个块真实时长 = c_i * d_target（<= d_target）
# 注意：我们使用 aligned baseline instr0/cycle0/miss0，再乘以 w_effect * c_i 来得到最终量
# -------------------------
def solve_duration_allocation(block_feature, w_opt, ratio, targets, eps_c=1e-6):
    """
    输入：
      block_feature: 原始字典
      w_opt: 第一层得到的线程缩放向量（可为 res.x）
      ratio: 上游的 ratio（d_target / duration_raw）
      targets: dict
    返回：
      c_opt: 每个块的 duration_scale c_i（范围 [eps_c, 1]），并且你在调用 generate_block_details 时应使用 C_val = ratio * c_i
    """
    CPI_target = float(targets['CPI'])
    MPKI_target = float(targets['MPKI'])
    d_target = float(targets['duration'])
    ins_target = float(targets['instruction'])

    # 原始数组
    cycle_raw = np.array(block_feature['cycle'], dtype=float)
    instruction_raw = np.array(block_feature['instruction'], dtype=float)
    llmiss_raw = np.array(block_feature['ll_miss'], dtype=float)
    duration_raw = np.array(block_feature['duration'], dtype=float)
    block_type = np.array(block_feature['type'])

    # aligned baseline (同第一层)
    ratio_arr = ratio  # ratio 是标量或数组；你原来是标量 d_target/duration（每元素），但在之前代码是数组
    # If ratio is scalar or array, ensure shape:
    if np.isscalar(ratio_arr):
        ratio_arr = np.full_like(duration_raw, float(ratio_arr), dtype=float)
    else:
        ratio_arr = np.array(ratio_arr, dtype=float)

    cycle0 = cycle_raw * ratio_arr
    instr0 = instruction_raw * ratio_arr
    miss0 = llmiss_raw * ratio_arr
    # duration0 is typically equal to d_target (if ratio = d_target / duration_raw), but keep general
    duration0 = duration_raw * ratio_arr

    N = len(instr0)
    w_vec = np.maximum(np.array(w_opt), 0.0)

    # compute per-block instr scaling due to w_vec (same mapping as in first stage)
    instr_scale_vec = np.ones(N, dtype=float)
    for i in range(N):
        if block_type[i] == 'sqrt':
            instr_scale_vec[i] = instr_scale_from_threads_continuous(w_vec[i])
        else:
            instr_scale_vec[i] = w_vec[i]

    # adjusted per-block base rates after thread-scale but before duration allocation
    instr_after_w = instr0 * instr_scale_vec   # 这是“如果每个块都运行满 baseline duration0 时的 instruction”
    cycle_after_w = cycle0 * instr_scale_vec
    # miss rate per instruction (基于 aligned baseline)
    instr_nonzero = np.maximum(instr0, 1.0)
    miss_rate0 = miss0 / instr_nonzero

    # Now introduce c variables: final scaled_instruction_i = instr_after_w[i] * (c_i * d_target / duration0[i])
    # But to keep linearity in c, we define c_i as fraction of d_target relative to baseline duration0:
    # final_instruction_i = instr_rate_i_after_w * final_duration_i
    # where instr_rate_i_after_w = instr_after_w[i] / duration0[i]  (instr per second after w)
    # and final_duration_i = c_i * d_target
    # => final_instruction_i = (instr_after_w[i]/duration0[i]) * (c_i * d_target)
    # To avoid dividing by zero, handle duration0 small.
    duration0_nonzero = np.maximum(duration0, 1e-9)
    instr_rate_after_w = instr_after_w / duration0_nonzero   # instr per second after w
    cycle_rate_after_w = cycle_after_w / duration0_nonzero   # cycles per second after w
    miss_rate_per_instr = miss_rate0  # miss per instr

    # The variables we optimize are c (size N), with bounds [eps_c, 1.0]
    c0 = np.minimum(np.ones(N), np.maximum(eps_c, duration0 / np.maximum(d_target, 1e-9)))  # warm start: baseline fraction
    bounds = [(eps_c, 1.0) for _ in range(N)]

    # Constraints:
    #  1) sum of final durations must be >= d_target  -> sum(c_i * d_target) >= d_target  -> sum(c_i) >= 1
    #  2) each final duration <= d_target  -> c_i <= 1  (handled by bounds)
    cons = [
        {'type': 'ineq', 'fun': lambda c: np.sum(c) - 1.0}  # sum(c) >= 1
    ]

    cycle_target = ins_target * CPI_target
    llc_target = ins_target * MPKI_target / 1000.0

    def objective_c(c):
        # c is vector of fractions; final durations = c * d_target
        final_duration = c * d_target
        scaled_instruction = np.dot(instr_rate_after_w, final_duration)  # sum instr
        scaled_cycle = np.dot(cycle_rate_after_w, final_duration)
        scaled_miss = np.dot((miss_rate_per_instr * instr_rate_after_w), final_duration)  # miss_rate_per_instr * instr_rate * final_duration = miss

        # prevent degenerate
        if scaled_instruction <= 0:
            return np.inf

        a = ((scaled_cycle - cycle_target) / max(cycle_target, 1e-9)) ** 2
        b = ((scaled_miss - llc_target) / max(llc_target, 1e-9)) ** 2
        cterm = ((scaled_instruction - ins_target) / max(ins_target, 1e-9)) ** 2

        # optional small regularizer to keep durations near baseline
        reg = 1e-4 * np.sum((final_duration - duration0) ** 2) / max(1.0, np.sum(duration0**2))

        return a + b + cterm + reg

    res = minimize(objective_c, c0, method='SLSQP', bounds=bounds, constraints=cons,
                   options={'maxiter': 3000, 'ftol': 1e-8})

    # res.x is the vector c (each in [eps_c,1]), note: C_val to pass into generate_block_details should be ratio * c_i
    c_opt = np.clip(res.x, eps_c, 1.0)
    return res, c_opt


# -------------------------
# 高层封装：两层顺序求解，返回与原接口类似的结果
# -------------------------
def constrained_optimization_two_layer(block_feature, targets, rank_cap=84.0):
    # 第一层
    res_w, ratio = solve_thread_scaling(block_feature, targets, rank_cap=rank_cap)
    w_opt = np.maximum(res_w.x, 0.0)

    # 第二层：基于 w_opt 求 c_opt
    res_c, c_opt = solve_duration_allocation(block_feature, w_opt, ratio, targets)

    # 返回形式：第一元素与原来保持相似（把 w 的结果当作最主要返回值），并额外返回 c_opt
    # 为最小改动，返回 (res_w, ratio, c_opt) ；如果你调用处希望与原来兼容，可只使用 res_w, ratio
    return res_w, ratio, c_opt, res_c

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
        scale = target['duration'] / block['duration']

        # 放缩 template 中的 duration（假设 block['template'][2] 是 duration）
        if 'template' in block and len(block['template']) >= 3:
            block['template'][2] = int(block['template'][2] * scale)

        for key in ['cycles', 'instructions', 'llmiss', 'iters']:
            if key in block:
                block[key] = block[key] * scale
        block['delay'] = 0
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
'''
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
'''
import random
import numpy as np
from typing import List, Dict, Tuple


'''def optimize_block_schedule_ga(
    blocks: List[Dict],
    perf_targets: List[Dict],
    population_size: int = 60,
    generations: int = 300,
    crossover_rate: float = 0.9,
    mutation_rate: float = 0.3,
    elite_k: int = 2,
    w_level: float = 1.0,
    w_shape: float = 0.5,
) -> Dict:
    """
    Anchor–Offset GA for block scheduling optimization
    """

    N = len(blocks)
    T = len(perf_targets)
    eps = 1e-10

    # ===============================
    # Target CPI / MPKI
    # ===============================
    target_CPI = np.array([
        p['cycle'] / (p['instruction'] + eps)
        for p in perf_targets
    ])
    target_MPKI = np.array([
        p['llmiss'] * 1000 / (p['instruction'] + eps)
        for p in perf_targets
    ])

    # ===============================
    # Individual representation
    # ===============================
    # individual = {
    #   "anchor": int,
    #   "offsets": List[int]
    # }

    def decode(ind):
        """anchor-offset -> absolute delays"""
        delays = [0] * N
        a = ind["anchor"]
        delays[a] = T - blocks[a]['duration']

        for i in range(N):
            if i == a:
                continue
            d = delays[a] + ind["offsets"][i]
            delays[i] = max(0, min(d, T - blocks[i]['duration']))
        return delays

    # ===============================
    # Fitness evaluation
    # ===============================
    def evaluate(ind):
        delays = decode(ind)

        cycle_t = np.zeros(T)
        instr_t = np.zeros(T)
        miss_t = np.zeros(T)

        for i in range(N):
            s = delays[i]
            e = min(s + blocks[i]['duration'], T)
            if s < e:
                cycle_t[s:e] += blocks[i]['cycles'] / blocks[i]['duration']
                instr_t[s:e] += blocks[i]['instructions'] / blocks[i]['duration']
                miss_t[s:e] += blocks[i]['llmiss'] / blocks[i]['duration']

        CPI = cycle_t / (instr_t + eps)
        MPKI = miss_t * 1000 / (instr_t + eps)

        # ---- level error
        lvl_err = (
            np.mean(((CPI - target_CPI) / (target_CPI + eps)) ** 2) +
            np.mean(((MPKI - target_MPKI) / (target_MPKI + eps)) ** 2)
        )

        # ---- shape error (1st-order difference)
        dCPI = np.diff(CPI)
        dCPI_t = np.diff(target_CPI)
        dMPKI = np.diff(MPKI)
        dMPKI_t = np.diff(target_MPKI)

        shp_err = (
            np.mean((dCPI - dCPI_t) ** 2) +
            np.mean((dMPKI - dMPKI_t) ** 2)
        )

        return - (w_level * lvl_err + w_shape * shp_err)

    # ===============================
    # Initialization
    # ===============================
    def random_individual():
        anchor = random.randint(0, N - 1)
        offsets = []
        for i in range(N):
            if i == anchor:
                offsets.append(0)
            else:
                offsets.append(random.randint(-T // 2, T // 2))
        return {"anchor": anchor, "offsets": offsets}

    population = [random_individual() for _ in range(population_size)]

    # ===============================
    # Selection
    # ===============================
    def tournament(pop, k=3):
        cand = random.sample(pop, k)
        return max(cand, key=evaluate)

    # ===============================
    # Crossover
    # ===============================
    def crossover(p1, p2):
        if random.random() > crossover_rate:
            return p1.copy(), p2.copy()

        c = random.randint(1, N - 1)
        child1 = {
            "anchor": p1["anchor"],
            "offsets": p1["offsets"][:c] + p2["offsets"][c:]
        }
        child2 = {
            "anchor": p2["anchor"],
            "offsets": p2["offsets"][:c] + p1["offsets"][c:]
        }

        if random.random() < 0.3:
            child1["anchor"] = random.randint(0, N - 1)
        if random.random() < 0.3:
            child2["anchor"] = random.randint(0, N - 1)

        return child1, child2

    # ===============================
    # Mutation (structure-aware)
    # ===============================
    def mutate(ind):
        # local offset mutation
        for i in range(N):
            if random.random() < mutation_rate:
                ind["offsets"][i] += random.choice([-2, -1, 1, 2])

        # block alignment mutation
        if random.random() < 0.2:
            i, j = random.sample(range(N), 2)
            ind["offsets"][i] = ind["offsets"][j] + random.randint(-3, 3)

        # anchor shift
        if random.random() < 0.1:
            ind["anchor"] = random.randint(0, N - 1)

        return ind

    # ===============================
    # GA main loop
    # ===============================
    best_ind = None
    best_fit = -1e18

    fitness_hist = []
    avg_hist = []
    std_hist = []

    for g in range(generations):
        fits = [evaluate(ind) for ind in population]

        idx = int(np.argmax(fits))
        if fits[idx] > best_fit:
            best_fit = fits[idx]
            best_ind = population[idx]

        fitness_hist.append(-best_fit)
        avg_hist.append(-np.mean(fits))
        std_hist.append(np.std(fits))

        # elitism
        elites = sorted(population, key=evaluate, reverse=True)[:elite_k]
        new_pop = [e.copy() for e in elites]

        while len(new_pop) < population_size:
            p1 = tournament(population)
            p2 = tournament(population)
            c1, c2 = crossover(p1, p2)
            new_pop.append(mutate(c1))
            if len(new_pop) < population_size:
                new_pop.append(mutate(c2))

        population = new_pop

    # ===============================
    # Final decode & metrics
    # ===============================
    delays = decode(best_ind)

    cycle_t = np.zeros(T)
    instr_t = np.zeros(T)
    miss_t = np.zeros(T)

    for i in range(N):
        s = delays[i]
        e = min(s + blocks[i]['duration'], T)
        if s < e:
            cycle_t[s:e] += blocks[i]['cycles'] / blocks[i]['duration']
            instr_t[s:e] += blocks[i]['instructions'] / blocks[i]['duration']
            miss_t[s:e] += blocks[i]['llmiss'] / blocks[i]['duration']

    CPI = cycle_t / (instr_t + eps)
    MPKI = miss_t * 1000 / (instr_t + eps)

    return {
        "success": True,
        "objective_value": -best_fit,
        "delays": delays,
        "CPI": CPI,
        "MPKI": MPKI,
        "target_CPI": target_CPI,
        "target_MPKI": target_MPKI,
        "fitness_history": fitness_hist,
        "convergence_data": {
            "generations": list(range(generations)),
            "best_objective": fitness_hist,
            "avg_objective": avg_hist,
            "std_fitness": std_hist
        }
    }'''



def optimize_block_schedule_ga(
    blocks: List[Dict],
    perf_targets: List[Dict],
    population_size: int = 60,
    generations: int = 300,
    crossover_rate: float = 0.9,
    mutation_rate: float = 0.3,
    elite_k: int = 2,
    # ===== loss weights =====
    w_level: float = 1.0,
    w_shape: float = 0.5,
    w_order: float = 0.5,
) -> Dict:

    eps = 1e-10
    N = len(blocks)
    T = len(perf_targets)

    # ======================================================
    # Target metrics
    # ======================================================
    target_CPI = np.array([
        p['cycle'] / (p['instruction'] + eps)
        for p in perf_targets
    ])
    target_MPKI = np.array([
        p['llmiss'] * 1000 / (p['instruction'] + eps)
        for p in perf_targets
    ])

    # ======================================================
    # Anchor–Offset decoding
    # ======================================================
    def decode(ind):
        delays = [0] * N
        a = ind["anchor"]
        delays[a] = T - blocks[a]["duration"]

        for i in range(N):
            if i == a:
                continue
            d = delays[a] + ind["offsets"][i]
            delays[i] = max(0, min(d, T - blocks[i]["duration"]))
        return delays

    # ======================================================
    # Fitness (KEY PART)
    # ======================================================
    def evaluate(ind):
        delays = decode(ind)

        cycle_t = np.zeros(T)
        instr_t = np.zeros(T)
        miss_t = np.zeros(T)

        for i in range(N):
            s = delays[i]
            e = min(s + blocks[i]["duration"], T)
            if s < e:
                cycle_t[s:e] += blocks[i]["cycles"] / blocks[i]["duration"]
                instr_t[s:e] += blocks[i]["instructions"] / blocks[i]["duration"]
                miss_t[s:e] += blocks[i]["llmiss"] / blocks[i]["duration"]

        CPI = cycle_t / (instr_t + eps)
        MPKI = miss_t * 1000 / (instr_t + eps)

        # =========================
        # 1) Level loss (NMSE-like)
        # =========================
        L_level = (
            np.mean(((CPI - target_CPI) / (target_CPI + eps)) ** 2) +
            np.mean(((MPKI - target_MPKI) / (target_MPKI + eps)) ** 2)
        )

        # =========================
        # 2) Shape loss (Pearson / mDTW surrogate)
        # =========================
        dCPI = np.diff(CPI)
        dCPI_t = np.diff(target_CPI)
        dMPKI = np.diff(MPKI)
        dMPKI_t = np.diff(target_MPKI)

        # (a) first-order trend matching
        L_shape = (
            np.mean((dCPI - dCPI_t) ** 2) +
            np.mean((dMPKI - dMPKI_t) ** 2)
        )

        # (b) normalized shape alignment (≈ Pearson → 1)
        def norm(x):
            return (x - np.mean(x)) / (np.std(x) + eps)

        CPI_n = norm(CPI)
        CPI_tn = norm(target_CPI)
        MPKI_n = norm(MPKI)
        MPKI_tn = norm(target_MPKI)

        L_shape += (
            np.mean((CPI_n - CPI_tn) ** 2) +
            np.mean((MPKI_n - MPKI_tn) ** 2)
        )

        # =========================
        # 3) Order loss (Spearman surrogate)
        # =========================
        sign = np.sign
        L_order = (
            np.mean((sign(dCPI) - sign(dCPI_t)) ** 2) +
            np.mean((sign(dMPKI) - sign(dMPKI_t)) ** 2)
        )

        total_loss = (
            w_level * L_level +
            w_shape * L_shape +
            w_order * L_order
        )

        return -total_loss

    # ======================================================
    # Initialization
    # ======================================================
    def random_individual():
        anchor = random.randint(0, N - 1)
        offsets = []
        for i in range(N):
            offsets.append(0 if i == anchor else random.randint(-T // 2, T // 2))
        return {"anchor": anchor, "offsets": offsets}

    population = [random_individual() for _ in range(population_size)]

    # ======================================================
    # GA operators
    # ======================================================
    def tournament(pop, k=3):
        cand = random.sample(pop, k)
        return max(cand, key=evaluate)

    def crossover(p1, p2):
        if random.random() > crossover_rate:
            return p1.copy(), p2.copy()

        c = random.randint(1, N - 1)
        c1 = {
            "anchor": p1["anchor"],
            "offsets": p1["offsets"][:c] + p2["offsets"][c:]
        }
        c2 = {
            "anchor": p2["anchor"],
            "offsets": p2["offsets"][:c] + p1["offsets"][c:]
        }

        if random.random() < 0.3:
            c1["anchor"] = random.randint(0, N - 1)
        if random.random() < 0.3:
            c2["anchor"] = random.randint(0, N - 1)

        return c1, c2

    def mutate(ind):
        for i in range(N):
            if random.random() < mutation_rate:
                ind["offsets"][i] += random.choice([-2, -1, 1, 2])

        # block alignment mutation
        if random.random() < 0.2:
            i, j = random.sample(range(N), 2)
            ind["offsets"][i] = ind["offsets"][j] + random.randint(-3, 3)

        if random.random() < 0.1:
            ind["anchor"] = random.randint(0, N - 1)

        return ind

    # ======================================================
    # Main loop
    # ======================================================
    best_ind = None
    best_fit = -1e18

    fitness_hist = []
    avg_hist = []
    std_hist = []

    for g in range(generations):
        fits = [evaluate(ind) for ind in population]

        idx = int(np.argmax(fits))
        if fits[idx] > best_fit:
            best_fit = fits[idx]
            best_ind = population[idx]

        fitness_hist.append(-best_fit)
        avg_hist.append(-np.mean(fits))
        std_hist.append(np.std(fits))

        elites = sorted(population, key=evaluate, reverse=True)[:elite_k]
        new_pop = [e.copy() for e in elites]

        while len(new_pop) < population_size:
            p1 = tournament(population)
            p2 = tournament(population)
            c1, c2 = crossover(p1, p2)
            new_pop.append(mutate(c1))
            if len(new_pop) < population_size:
                new_pop.append(mutate(c2))

        population = new_pop

    # ======================================================
    # Final decode & metrics
    # ======================================================
    delays = decode(best_ind)

    cycle_t = np.zeros(T)
    instr_t = np.zeros(T)
    miss_t = np.zeros(T)

    for i in range(N):
        s = delays[i]
        e = min(s + blocks[i]["duration"], T)
        if s < e:
            cycle_t[s:e] += blocks[i]["cycles"] / blocks[i]["duration"]
            instr_t[s:e] += blocks[i]["instructions"] / blocks[i]["duration"]
            miss_t[s:e] += blocks[i]["llmiss"] / blocks[i]["duration"]

    CPI = cycle_t / (instr_t + eps)
    MPKI = miss_t * 1000 / (instr_t + eps)

    return {
        "success": True,
        "objective_value": -best_fit,
        "delays": delays,
        "CPI": CPI,
        "MPKI": MPKI,
        "target_CPI": target_CPI,
        "target_MPKI": target_MPKI,
        "fitness_history": fitness_hist,
        "convergence_data": {
            "generations": list(range(generations)),
            "best_objective": fitness_hist,
            "avg_objective": avg_hist,
            "std_fitness": std_hist
        }
    }

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
'''def instruction_optimized(aggr_df,targets,mask):
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
'''
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

'''
def instruction_optimized(aggr_df, targets, mask, max_expand_ratio=8):
    CPI_target = targets['CPI']
    MPKI_target = targets['MPKI']

    CPI = aggr_df['CPI']
    MPKI = aggr_df['MPKI']
    instruction = aggr_df['instruction']

    N = len(CPI)
    x0 = np.ones(N)
    bounds = []
    for m in mask:
        if m:
            bounds.append((1.0, max_expand_ratio))  # 可放大
        else:
            bounds.append((1.0, 1.0))  # 不允许变化

    def objective(s):
        scaled_cycle = CPI * instruction * s
        scaled_instruction = instruction * s
        scaled_cache_miss = MPKI * instruction * s / 1000

        total_cycle = scaled_cycle.sum()
        total_inst = scaled_instruction.sum()
        total_miss = scaled_cache_miss.sum()

        CPI_actual = total_cycle / total_inst
        MPKI_actual = (total_miss / total_inst) * 1000

        return (CPI_actual - CPI_target)**2 + (MPKI_actual - MPKI_target)**2

    result = minimize(
        objective,
        x0,
        method='SLSQP',
        bounds=bounds,
        options={'maxiter': 8000, 'ftol': 1e-8}
    )

    return result.x

'''

def optimize_threads_and_scaling(aggr_df, targets, mask,
                                 max_thread_expand=8.0,
                                 max_s=3.0,
                                 w_t=1.0,    # 权重: 惩罚 t 的偏离
                                 w_s=1.0):   # 权重: 惩罚 s 的偏离
    """
    联合优化线程扩展因子 t_i (>=1) 和 全局微调因子 s_i，返回 t, s arrays。
    - aggr_df: DataFrame, 必须含 'CPI','MPKI','instruction','duration'
    - targets: dict-like with 'CPI' and 'MPKI'
    - mask: boolean array (len=N)，True 表示该阶段允许 t_i > 1（低 IPS）
    - max_thread_expand: 每个允许扩展的阶段 t_i 的上界
    - max_s: s_i 的上界
    - w_t, w_s: 正则化权重（越大越不愿改变）
    返回: t (N,), s (N,), result (OptimizeResult)
    """

    CPI = aggr_df['CPI'].values.astype(float)
    MPKI = aggr_df['MPKI'].values.astype(float)
    instr0 = aggr_df['instruction'].values.astype(float)
    N = len(CPI)

    target_CPI = float(targets['CPI'])
    target_MPKI = float(targets['MPKI'])

    # 变量顺序：x = [t_0, t_1, ..., t_{N-1}, s_0, s_1, ..., s_{N-1}]
    x0 = np.ones(2 * N)

    # 构造 bounds
    bounds = []
    for i in range(N):
        if mask[i]:
            bounds.append((1.0, float(max_thread_expand)))  # t_i 可扩展
        else:
            bounds.append((1.0, 1.0))  # t_i 固定为1
    for i in range(N):
        bounds.append((0.5, float(max_s)))  # s_i 下界 0.5，避免负或太小

    # 目标：尽量保持 t,s 接近1（最小扰动）
    def objective(x):
        t = x[0:N]
        s = x[N:2*N]
        # 惩罚项（可加权）
        pen_t = w_t * np.sum((t - 1.0) ** 2)
        pen_s = w_s * np.sum((s - 1.0) ** 2)
        return pen_t + pen_s

    # 约束：两个等式，全局 CPI 与 MPKI
    def constraint_CPI(x):
        t = x[0:N]
        s = x[N:2*N]
        instr = instr0 * t * s
        total_cycle = np.sum(CPI * instr)
        total_inst = np.sum(instr)
        # 返回实际CPI - targetCPI -> 约束为0
        return total_cycle / total_inst - target_CPI

    def constraint_MPKI(x):
        t = x[0:N]
        s = x[N:2*N]
        instr = instr0 * t * s
        total_ll = np.sum(MPKI * instr / 1000.0)
        total_inst = np.sum(instr)
        # 注意： MPKI = 1000 * total_ll / total_inst, 这里返回实际 - target
        return (total_ll * 1000.0) / total_inst - target_MPKI

    constraints = [
        {'type': 'eq', 'fun': constraint_CPI},
        {'type': 'eq', 'fun': constraint_MPKI}
    ]

    # 初始点智能化：对于被 mask 的段，给一个小扩容初值以便可行
    for i in range(N):
        if mask[i]:
            # 以使每段指令数达到 duration*some_rate 作为近似初值（简单处理）
            x0[i] = 1.0 + min(1.0, max_thread_expand / 10.0)  # 不要太极端
        else:
            x0[i] = 1.0
    # s 初始仍为1
    x0[N:2*N] = 1.0

    # 求解
    result = minimize(
        objective,
        x0,
        method='SLSQP',
        bounds=bounds,
        constraints=constraints,
        options={'maxiter': 5000, 'ftol': 1e-9, 'disp': False}
    )

    if not result.success:
        # 如果严格等式约束难以同时满足，尝试放松优化器策略：先求一个次优可行解
        # 这里尝试用 Nelder-Mead 作为退路（无约束，只用带罚项的目标）
        x0_nm = x0.copy()
        def penalized_obj(x):
            # 罚函数：把两个误差平方加入目标
            t = x[0:N]; s = x[N:2*N]
            instr = instr0 * t * s
            total_cycle = np.sum(CPI * instr); total_inst = np.sum(instr)
            total_ll = np.sum(MPKI * instr / 1000.0)
            cpi_err = (total_cycle / total_inst - target_CPI)**2
            mpki_err = ((total_ll * 1000.0) / total_inst - target_MPKI)**2
            # 惩罚系数取较大，确保尽量靠近约束
            penalty = 1e6 * (cpi_err + mpki_err)
            return objective(x) + penalty

        nm_res = minimize(
            penalized_obj,
            x0_nm,
            method='Nelder-Mead',
            options={'maxiter': 20000, 'fatol': 1e-6, 'xatol':1e-6}
        )
        if nm_res.success:
            x_sol = nm_res.x
        else:
            # 最后退化：只返回 t=1, s按全局统一缩放（避免崩溃）
            x_sol = np.ones(2*N)
            # 简单统一缩放 s_global 令总inst保持，或按比例缩放 cycles->CPI_target（保守）
    else:
        x_sol = result.x

    t_opt = x_sol[0:N]
    s_opt = x_sol[N:2*N]
    return t_opt, s_opt, result


def generate_block_details_new2(param_set, W, C, block_feature):
    details = []
    # ensure arrays
    cycles_arr = np.array(block_feature['cycle'], dtype=float)
    instr_arr = np.array(block_feature['instruction'], dtype=float)
    miss_arr = np.array(block_feature['ll_miss'], dtype=float)
    dur_arr = np.array(block_feature['duration'], dtype=float)

    for index, item in enumerate(param_set):
        block = item[0]
        original_rank = int(block[0])
        block_type = block[1]

        W_val = float(W[index])
        C_val = float(C[index])  # C_val now interpreted as "duration fraction relative to d_target" or as you expect

        # compute rank (threads) and iter_scale same as original logic
        rank = int(original_rank * W_val) + 1
        if rank <= 0:
            rank = 1
        iter_scale = (W_val * original_rank) / float(rank)

        # scaled_duration: use base duration from block_feature, scale by C_val and iter_scale
        base_duration = float(dur_arr[index])
        scaled_duration = base_duration * C_val * iter_scale

        # scaled cycles/instructions: follow your prior approach
        # use rank/original_rank factor to account for integer rank change
        rank_factor = float(rank) / float(original_rank) if original_rank > 0 else 1.0
        base_scale = C_val * iter_scale

        scaled_cycles = cycles_arr[index] * base_scale * rank_factor
        scaled_instructions = instr_arr[index] * base_scale * rank_factor

        if block_type in ['div', 'add', 'sqrt']:
            scaled_llmiss = miss_arr[index] * base_scale
        else:
            scaled_llmiss = miss_arr[index] * base_scale * rank_factor

        block_CPI = scaled_cycles / max(scaled_instructions, 1e-9)
        block_MPKI = (scaled_llmiss * 1000.0) / max(scaled_instructions, 1e-9)

        modified_block = copy.deepcopy(block)
        modified_block[0] = rank
        # 保持你原来行为：scaled template field (第三 field) 也按比例放缩为整数
        try:
            modified_block[2] = int(modified_block[2] * C_val * iter_scale)
        except Exception:
            # 如果模板格式不同，仍保留原值
            pass

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
            'duration': scaled_duration,
            'block_CPI': block_CPI,
            'block_MPKI': block_MPKI,
            'template': modified_block,
            'delay': delay
        }
        details.append(block_detail)

    return details


def generate_block_details_new(param_sets, w_opt, ratio, block_feature, balance_ratio):
    details = []

    cycle_arr = block_feature['cycle']
    instr_arr = block_feature['instruction']
    llm_arr = block_feature['ll_miss']
    dur_arr = block_feature['duration']
    type_arr = block_feature['type']
    rank_arr = block_feature['rank']

    calc_types = ['sqrt', 'add', 'div']

    for index, ps in enumerate(param_sets):
        block = ps[0]
        original_rank = int(block[0])
        block_type = block[1]

        W_val = float(w_opt[index])

        # -------- effective duration ratio --------
        if block_type in calc_types:
            C_val = float(ratio[index] * balance_ratio)
        else:
            C_val = float(ratio[index])

        # ---------- scale construction ----------
        scale = W_val
        rank = int(original_rank * scale) + 1
        iter_scale = scale * original_rank / rank

        # -------- duration must be >= 1ms (or 1 unit) --------
        if dur_arr[index] * C_val * iter_scale < 1:
            continue

        # -------- scaled metrics --------
        scaled_cycles = float(cycle_arr[index] * C_val * (rank / original_rank) * iter_scale)
        scaled_instructions = float(instr_arr[index] * C_val * (rank / original_rank) * iter_scale)

        # llmiss special rule
        if block_type in calc_types:
            scaled_llmiss = float(llm_arr[index] * C_val * iter_scale)
        else:
            scaled_llmiss = float(llm_arr[index] * C_val * (rank / original_rank) * iter_scale)

        scaled_duration = float(dur_arr[index] * C_val * iter_scale)

        # ---- construct template ----
        modified_block = block.copy()
        modified_block[0] = rank
        modified_block[2] = int(modified_block[2] * C_val * iter_scale)
        delay = 0
        modified_block.append(delay)

        block_detail = {
            'original_rank': original_rank,
            'W': W_val,
            'C': C_val,
            'rank': rank,
            'iter_scale_factor': float(iter_scale),
            'cycles': scaled_cycles,
            'instructions': scaled_instructions,
            'llmiss': scaled_llmiss,
            'duration': int(scaled_duration),                       # ⬅ 保持原版 int
            'block_CPI': scaled_cycles / scaled_instructions,
            'block_MPKI': (scaled_llmiss * 1000.0) / scaled_instructions,
            'template': modified_block,
            'delay': 0
        }

        details.append(block_detail)

    return details



def modify_instruction(aggr_df, global_targets, threshold=6e10, info=False,
                       max_thread_expand=8.0, max_s=3.0, w_t=1.0, w_s=1.0):
    """
    替代原 modify_instruction：不直接覆盖 instruction，而是求 t_i,s_i，然后返回应用后的 df。
    """
    df = aggr_df.copy()
    df['ips'] = df['instruction'] / df['duration']

    # mask 标记需要额外线程的阶段（ips < threshold）
    mask = (df['ips'].values < threshold)

    targets = {
        "CPI": global_targets.iloc[0]["CPI"],
        "MPKI": global_targets.iloc[0]["MPKI"],
    }

    # 联合优化 t 和 s
    t_opt, s_opt, opt_res = optimize_threads_and_scaling(
        df, targets, mask,
        max_thread_expand=max_thread_expand,
        max_s=max_s,
        w_t=w_t, w_s=w_s
    )

    # 应用 t 和 s（最终 instruction）
    instr0 = df['instruction'].values.astype(float)
    instr_final = instr0 * t_opt * s_opt
    df['instruction'] = instr_final

    # 可选：把 thread_count estimate 也返回或保存（例如 thread_count = ceil(instr_final / (duration * per_thread_ipc_target))）
    # 但这里仅应用 instruction 数量

    # 验证全局指标
    CPI = df['CPI'].values
    MPKI = df['MPKI'].values
    total_cycle = np.sum(CPI * instr_final)
    total_ll = np.sum(MPKI * instr_final / 1000.0)
    total_inst = np.sum(instr_final)

    adjusted_CPI = total_cycle / total_inst
    adjusted_MPKI = (total_ll * 1000.0) / total_inst

    if info:
        print(f"调整后的总体 CPI:  {adjusted_CPI:.4f} (目标 {targets['CPI']:.4f})")
        print(f"调整后的总体 MPKI: {adjusted_MPKI:.4f} (目标 {targets['MPKI']:.4f})")
        print("opt success:", opt_res.success, "message:", getattr(opt_res, "message", ""))

    return df


def fit_phase(block_feature, targets, max_iter=10):
    balance_ratio = 1      
    lr = 0.1                

    w1, w2, w3 = 1.0, 1.0, 0.2  # 三个指标的权重，可调

    best_err = 1e9
    best_state = None

    for k in range(max_iter):
        result, ratio, aggr = constrained_optimization_new(
            block_feature, targets, balance_ratio
        )

        cpi_pred = aggr["CPI"]
        mpki_pred = aggr["MPKI"]
        ins_pred = aggr["instruction"]

        cpi_tgt = targets["CPI"]
        mpki_tgt = targets["MPKI"]
        ins_tgt = targets["instruction"]

        # ---- 组合误差 ----
        err = (
            w1 * ((cpi_pred - cpi_tgt) / cpi_tgt) ** 2 +
            w2 * ((mpki_pred - mpki_tgt) / mpki_tgt) ** 2 +
            w3 * ((ins_pred - ins_tgt) / ins_tgt) ** 2
        )

        print(f"[iter {k}] balance_ratio={balance_ratio:.4f}, CPI={cpi_pred:.3f}, MPKI={mpki_pred:.3f}, err={err:.5f}")

        # 保存 best
        if err < best_err:
            best_err = err
            best_state = (balance_ratio, result)
        else:
            # 若误差反弹 → 收敛
            break

        # ---- 根据误差方向调整 balance_ratio ----
        # MPKI 偏低 → mem 不够 → 降低计算类比例
        if mpki_pred < mpki_tgt:
            balance_ratio *= (1 - lr)
        else:
            balance_ratio *= (1 + lr)
        balance_ratio = max(0.0, min(balance_ratio, 1.0))
    print("Converged balance_ratio =", best_state[0])
    return best_state[1], ratio, best_state[0]



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

'''tmp_df = aggr_df.copy()
optimal_threshold, min_error = find_optimal_threshold(tmp_df, global_targets)

aggr_df = modify_instruction(aggr_df,global_targets,threshold=optimal_threshold,info = True)
print("threshold=",optimal_threshold)'''
#aggr_df = modify_instruction(aggr_df,global_targets,info=True)
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
    #result,ratio= constrained_optimization_two_layer(block_feature,targets)
    
    #result ,ratio= constrained_optimization_fixed_special(block_feature,targets)
    #w_opt = result.x
    #result , ratio= constrained_optimization_new(block_feature,targets)
    result , ratio, balance_ratio= fit_phase(block_feature,targets, max_iter=10)
    w_opt = result.x
    block_list= generate_block_details_new(param_sets,w_opt,ratio,block_feature,balance_ratio)
    #block_list = generate_block_details(param_sets,w_opt,ratio,block_feature)
    '''res_w, ratio, c_opt, res_c = constrained_optimization_two_layer(block_feature, targets)
    w_opt = res_w.x
    C_for_generate = ratio * c_opt
    block_list = generate_block_details_new(param_sets, w_opt, C_for_generate, block_feature)'''
    #block_list = generate_block_details(param_sets,w_opt,ratio,block_feature)
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
    if args.delay_iters and len(block_list)>1:
        tmp = optimize_block_schedule_ga(block_list,perf_targets,generations=args.delay_iters)
        delay = tmp['delays']
        for j in range(len(delay)):
            block_list[j]['delay']=delay[j]
    
    all_block_lists.append(block_list)
    if result_dir is not None and tmp is not None:
        # 可视化并保存图片
        visualize_convergence(tmp, output_file=f"{GA_dir}/convergence_plot{i}.png", show_plot=False)

        # 保存收敛过程数据到CSV文件
        save_convergence_data(tmp, output_file=f"{GA_dir}/convergence_data{i}.csv")
    #block_list = calc_delay(block_list,targets['duration'])
    template, aggr= generate_template(block_list=block_list)

    #template, aggr, detail= generate_template(param_sets,w_opt,ratio,block_feature)
    #print(template)

    if template is not None:
        res.append(template)

    print(aggr)

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



