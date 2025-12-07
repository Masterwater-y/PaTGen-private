#!/usr/bin/env python3
import json
import sys
import numpy as np
import pandas as pd
import ast
from scipy.optimize import minimize

# ------------------- 辅助与读取 -------------------
def read_load_features(file_path):
    data = pd.read_csv(file_path)
    required_columns = ['param_set', 'duration', 'cycles_sum', 'instructions_sum', 'll-misses_sum']
    for col in required_columns:
        if col not in data.columns:
            raise ValueError(f"CSV文件中缺少{col}列")

    block_feature = {
        'cycle': data['cycles_sum'].values.astype(float),
        'instruction': data['instructions_sum'].values.astype(float),
        'll_miss': data['ll-misses_sum'].values.astype(float),
        'duration': data['duration'].values.astype(float),
        'rank': [],
        'type': []
    }
    param_sets = data['param_set'].apply(ast.literal_eval).tolist()
    for item in param_sets:
        # 这里假设 param_set 的结构为 list, 且第一个元素中包含 rank/type/iters 等
        # 请根据你的 CSV 中 param_set 的真实结构调整下列索引
        try:
            block_feature['rank'].append(item[0][0])
            block_feature['type'].append(item[0][1])
        except Exception:
            block_feature['rank'].append(None)
            block_feature['type'].append(None)

    return block_feature, param_sets

# ------------------- 目标从 duration & freq 推导 -------------------
def derive_targets_from_duration(duration_seconds, cpu_frequency_hz, target_CPI, target_MPKI):
    """
    根据 duration (seconds) 与 CPU 频率 (Hz) 推导目标 cycles/instruction/llmiss
    cycles_target = duration * freq
    instr_target = cycles_target / CPI
    llmiss_target = instr_target * (MPKI / 1000)
    返回 (cycles_target, instr_target, llmiss_target)
    """
    cycles_target = duration_seconds * cpu_frequency_hz
    instr_target = cycles_target / (target_CPI + 1e-12)
    llmiss_target = instr_target * (target_MPKI / 1000.0)
    return cycles_target, instr_target, llmiss_target


def optimize_scales(block_feature, targets,
                    weight_cycles=1.0, weight_instr=1.0, weight_ll=1.0,
                    lambda_reg=1.0, reg_k=8.0,
                    x0=None, maxiter=5000):

    cycles_unit = np.array(block_feature['cycle'], dtype=float)
    instr_unit = np.array(block_feature['instruction'], dtype=float)
    llm_unit = np.array(block_feature['ll_miss'], dtype=float)
    m = cycles_unit.size

    cycles_target = targets['cycles']
    instr_target = targets['instruction']
    llm_target = targets['ll-misses']


    # 避免除零
    def safe_div(a, b):
        return a / (b + 1e-12)

    # ---------- 初始点 ----------
    if x0 is None:
        total_instr_unit = instr_unit.sum()
        if total_instr_unit <= 0:
            x0 = np.ones(m) * 0.1
        else:
            x_scalar = instr_target / (total_instr_unit + 1e-12)
            x0 = np.ones(m) * x_scalar
    else:
        x0 = np.array(x0, dtype=float)
        if x0.size != m:
            x0 = np.ones(m) * (instr_target / (instr_unit.sum() + 1e-12))

    bounds = [(0.0, None) for _ in range(m)]

    # ========== 关键：替换目标函数 ==========
    def obj(x):
        # 预测值 = 单位量 * x
        pred_cycles = np.dot(cycles_unit, x)
        pred_instr = np.dot(instr_unit, x)
        pred_llm   = np.dot(llm_unit, x)

        # 对照版本 B 的相对误差目标函数
        e_cycles = safe_div(pred_cycles - cycles_target, cycles_target)
        e_instr  = safe_div(pred_instr  - instr_target, instr_target)
        e_llm    = safe_div(pred_llm    - llm_target,   llm_target)

        loss = (weight_cycles * e_cycles * e_cycles +
                weight_instr  * e_instr  * e_instr  +
                weight_ll     * e_llm    * e_llm)

        # 原来的正则保持
        reg = lambda_reg * np.sum(x)
        return loss + reg

    # ---------- 调用 SLSQP ----------
    res = minimize(obj, x0, method='SLSQP', bounds=bounds,
                   options={'maxiter': maxiter, 'ftol': 1e-9, 'disp': False})

    if not res.success:
        print("警告：优化未严格收敛:", res.message)

    x_opt = np.maximum(res.x, 0.0)
    return x_opt, res

# ------------------- 主合成函数 -------------------
def synthesize_workload(load_features_file, target_params,
                        weight_cycles=1.0, weight_instr=1.0, weight_ll=1.0,
                        lambda_reg=1.0, reg_k=8.0):
    """
    target_params 应包含:
      - duration (seconds)
      - cpu_frequency_hz (Hz)  # 若没有，会默认使用 2.6 GHz
      - CPI
      - MPKI
    返回 param_sets（按比例缩放后的基本块列表）以及优化信息
    """
    block_feature, param_sets = read_load_features(load_features_file)
    freq = target_params.get('cpu_frequency_hz', 2.6e9)

    # 1) 从 duration 与 freq 推导目标 cycles/instr/llmiss
    cycles_t, instr_t, llm_t = derive_targets_from_duration(
        duration_seconds=target_params['duration'],
        cpu_frequency_hz=freq,
        target_CPI=target_params['CPI'],
        target_MPKI=target_params['MPKI']
    )
    targets = {
        'cycles': cycles_t,
        'instruction': instr_t,
        'll-misses': llm_t
    }
    '''print("=== 推导目标指标 ===")
    print(f"目标周期数 cycles: {cycles_t:.2f}")
    print(f"目标指令数 instruction: {instr_t:.2f}")
    print(f"目标 LLC Miss 数 ll-misses: {llm_t:.2f}")'''

    # 2) 求解 x 向量
    x_opt, res = optimize_scales(block_feature, targets,
                                 weight_cycles=weight_cycles,
                                 weight_instr=weight_instr,
                                 weight_ll=weight_ll,
                                 lambda_reg=lambda_reg, reg_k=reg_k)
    '''print("=== 优化结果 ===")
    print("优化是否成功:", "是" if res.success else "否")
    print("优化信息:", res.message)
    print("非零缩放系数数量:", np.sum(x_opt > 1e-6))
    print("缩放系数平均值:", np.mean(x_opt))'''

    # 3) 构造最终 param_sets
    valid_mask = x_opt > 1e-6
    template_res = []
    total_cycles = total_instr = total_llm = total_duration = 0.0

    for i in np.where(valid_mask)[0]:
        scale = float(x_opt[i])
        total_cycles += block_feature['cycle'][i] * scale
        total_instr += block_feature['instruction'][i] * scale
        total_llm += block_feature['ll_miss'][i] * scale
        total_duration += block_feature['duration'][i] * scale

        entry = param_sets[i][0] if isinstance(param_sets[i], list) and len(param_sets[i])>0 else param_sets[i]
        try:
            entry_copy = list(entry) if isinstance(entry, (list, tuple)) else [entry]
        except Exception:
            entry_copy = [entry]

        if len(entry_copy) > 2 and isinstance(entry_copy[2], (int, float)):
            entry_copy[2] = int(max(1, round(entry_copy[2] * scale)))
        else:
            entry_copy.append(scale)
        template_res.append(entry_copy)

    # 4) 输出预测结果
    print("=== 缩放后指标总计 ===")
    print(f"总周期数 cycles: {total_cycles:.2f}")
    print(f"总指令数 instruction: {total_instr:.2f}")
    print(f"总 LLC Miss 数 ll-misses: {total_llm:.2f}")
    print(f"总 duration: {total_duration:.2f} 秒")
    print(f"目标 CPI: {targets['cycles']/(targets['instruction']+1e-12):.4f}")
    print(f"实际 CPI: {total_cycles/(total_instr+1e-12):.4f}")
    print(f"目标 MPKI: {targets['ll-misses']*1000/(targets['instruction']+1e-12):.4f}")
    print(f"实际 MPKI: {total_llm*1000/(total_instr+1e-12):.4f}\n")

    return template_res, {
        'x_opt': x_opt,
        'opt_result': res,
        'pred_totals': {
            'cycles': total_cycles,
            'instruction': total_instr,
            'll_misses': total_llm,
            'duration': total_duration
        },
        'targets': targets
    }

# ------------------- 脚本入口 -------------------
if __name__ == "__main__":
    block_path = 'block.csv'
    args = sys.argv[1:]
    sample_index = int(args[0]) if len(args) > 0 else 0
    phase_index = int(args[1]) if len(args) > 1 else None

    aggr_df = pd.read_csv(f'stage{sample_index}/aggr.csv')

    res_template_all = []
    opt_infos = []
    for idx, targets_row in aggr_df.iterrows():
        if phase_index is not None and idx != phase_index:
            continue

        duration = float(targets_row['duration'])
        CPI = float(targets_row['CPI'])
        MPKI = float(targets_row['MPKI'])
        freq = float(targets_row['cpu_frequency_hz']) if 'cpu_frequency_hz' in targets_row else 2.6e9

        target_params = {
            'duration': duration,
            'cpu_frequency_hz': freq,
            'CPI': CPI,
            'MPKI': MPKI
        }
        print(f"==== 处理阶段 {idx} ====")
        print("目标参数:", target_params)

        template_res, opt_info = synthesize_workload(block_path, target_params,
                                                     weight_cycles=1.0,
                                                     weight_instr=1.0,
                                                     weight_ll=1.0,
                                                     lambda_reg=0.5,
                                                     reg_k=8.0)
        res_template_all += template_res
        opt_infos.append(opt_info)

    res_template_all_list = []

    for template in res_template_all:
        res_template_all_list.append(template)

    # 添加尾部两个元素 16 和 1
    res_template_all_list.append(16)
    res_template_all_list.append(1)

    # 整体转换成一个字符串，写入 param_set 列
    param_set_str = str(res_template_all_list)

    # 写入 CSV
    pd.DataFrame([{"param_set": param_set_str}]).to_csv('param_sets.csv', index=False, quoting=0)


    print("==== 所有阶段优化完成 ====")
    for i, info in enumerate(opt_infos):
        if not info['opt_result']:
            print(f"阶段 {i}：非零 x 数量 {np.sum(info['x_opt'] > 1e-6)}, 平均 x {np.mean(info['x_opt']):.4f}, 优化成功: {'是' if info['opt_result'].success else '否'}")
