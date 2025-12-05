#!/usr/bin/env python3
import sys
import numpy as np
import pandas as pd
import ast
from scipy.optimize import minimize

# ---------- 全局配置（适配缩放系数x：实际运行次数 = int(init_iter * x)） ----------
EPS = 1e-8  # 避免除以零
np.random.seed(0)  # 固定随机种子确保可复现
MAX_SCALE_FACTOR = 100.0  # 缩放系数x上限
MIN_ACTUAL_ITER = 1  # 实际运行次数下限（至少1次）

# ---------- 读取代码块特征（稳定无报错） ----------
def read_load_features(file_path):
    """读取代码块特征：单位性能+初始迭代次数"""
    try:
        data = pd.read_csv(file_path)
    except FileNotFoundError:
        raise FileNotFoundError(f"代码块文件 {file_path} 未找到，请检查路径")

    # 必需列校验（确保CSV格式正确）
    required_cols = ['param_set', 'cycles_sum', 'instructions_sum', 'll-misses_sum']
    missing_cols = [col for col in required_cols if col not in data.columns]
    if missing_cols:
        raise ValueError(f"CSV缺少必需列：{', '.join(missing_cols)}")

    block_feature = {
        # 单位性能（单轮执行指标，论文B矩阵元素）
        'cycle_per_iter': None,
        'instr_per_iter': None,
        'llmiss_per_iter': None,
        # 初始迭代次数（核心：实际运行次数 = int(init_iter * x)）
        'init_iter': [],
        # 辅助信息
        'param_sets': data['param_set'].apply(ast.literal_eval).tolist()
    }

    # 提取初始迭代次数（兼容格式异常）
    for param in block_feature['param_sets']:
        try:
            init_iter = int(param[0][2])  # 假设param结构：[[rank, type, init_iter, ...]]
        except (IndexError, ValueError, TypeError):
            init_iter = int(1e6)  # 格式异常时兜底
        block_feature['init_iter'].append(init_iter)
    block_feature['init_iter'] = np.array(block_feature['init_iter'], dtype=int)

    # 计算单位性能（避免除以0）
    valid_init_iter = np.maximum(block_feature['init_iter'], 1)
    block_feature['cycle_per_iter'] = data['cycles_sum'].astype(float).values / valid_init_iter
    block_feature['instr_per_iter'] = data['instructions_sum'].astype(float).values / valid_init_iter
    block_feature['llmiss_per_iter'] = data['ll-misses_sum'].astype(float).values / valid_init_iter

    return block_feature

# ---------- 计算实际性能（参数传递统一：从target_t获取所有目标指标） ----------
def calculate_actual_metrics(x, block_feature, target_t):
    """
    核心逻辑：
    1. 实际运行次数 = int(init_iter * x)
    2. 总性能 = 单位性能 * 实际运行次数
    3. 误差 = 论文定义的相对误差平方和
    （修复点：从target_t提取所有目标指标，避免变量未定义）
    """
    m = len(x)
    init_iter = block_feature['init_iter']

    # 1. 计算实际运行次数（确保整数且≥1）
    actual_iter = np.round(init_iter * x).astype(int)
    actual_iter = np.maximum(actual_iter, MIN_ACTUAL_ITER)

    # 2. 提取目标指标（从target_t获取，避免NameError）
    target_cycle = target_t[0]    # 目标总周期
    target_instr = target_t[1]    # 目标总指令
    target_llmiss = target_t[2]   # 目标总缓存缺失

    # 3. 计算总性能
    total_cycle = block_feature['cycle_per_iter'] @ actual_iter
    total_instr = block_feature['instr_per_iter'] @ actual_iter
    total_llmiss = block_feature['llmiss_per_iter'] @ actual_iter

    # 4. 计算论文定义的相对误差平方和
    rel_err_sq = []
    for actual, target in [(total_cycle, target_cycle), (total_instr, target_instr), (total_llmiss, target_llmiss)]:
        denom = max(target ** 2, EPS)  # 避免除以0
        rel_err_sq.append((actual - target) ** 2 / denom)

    # 额外计算用户关注的CPI/MPKI/duration误差（基于目标指标反推）
    target_cpi = target_cycle / target_instr if target_instr > EPS else 0.0
    target_mpki = (target_llmiss / target_instr) * 1000 if target_instr > EPS else 0.0
    expected_cpi = total_cycle / total_instr if total_instr > EPS else 0.0
    expected_mpki = (total_llmiss / total_instr) * 1000 if total_instr > EPS else 0.0

    # 相对误差（百分比）
    def rel_err_pct(actual, target):
        return (abs(actual - target) / max(abs(target), EPS)) * 100

    return {
        'actual_iter': actual_iter,
        'rel_err_sq_sum': sum(rel_err_sq),  # 论文目标函数值
        # 用户关注的误差结果
        'cpi_err_pct': rel_err_pct(expected_cpi, target_cpi),
        'mpki_err_pct': rel_err_pct(expected_mpki, target_mpki),
        'instr_err_pct': rel_err_pct(total_instr, target_instr),
        # 中间结果（用于日志）
        'total_cycle': total_cycle, 'total_instr': total_instr, 'total_llmiss': total_llmiss,
        'expected_cpi': expected_cpi, 'expected_mpki': expected_mpki
    }

# ---------- 构建优化模型（参数传递统一） ----------
def build_objective_model(block_feature, target_t):
    """
    优化变量：缩放系数x
    目标函数：min 论文定义的相对误差平方和
    约束：x ≥ 0
    """
    m = len(block_feature['init_iter'])

    # 目标函数（仅依赖传入的block_feature和target_t，无外部变量）
    def objective(x):
        x = np.maximum(x, 0.0)  # 确保x非负
        metrics = calculate_actual_metrics(x, block_feature, target_t)
        return metrics['rel_err_sq_sum']

    # 变量边界（x∈[0, MAX_SCALE_FACTOR]）
    bounds = [(0.0, MAX_SCALE_FACTOR) for _ in range(m)]
    return objective, [], bounds  # 无额外约束

# ---------- 求解缩放系数x（稳定多起点优化） ----------
def solve_scale_factor(objective, bounds):
    """求解缩放系数x，多起点避免局部最优"""
    m = len(bounds)
    if m == 0:
        raise ValueError("无代码块数据，无法求解缩放系数")

    # 初始点集（覆盖合理范围，提升求解成功率）
    initial_guesses = [
        np.ones(m),  # 基准点：x=1.0
        np.random.uniform(0.1, 1.0, size=m),  # 小缩放
        np.random.uniform(1.0, 10.0, size=m)   # 中缩放
    ]

    best_x = None
    best_fun = float('inf')

    for guess_idx, x0 in enumerate(initial_guesses):
        # 确保初始点在边界内
        x0 = np.clip(x0, bounds[0][0] + EPS, bounds[0][1] - EPS)
        res = minimize(
            fun=objective,
            x0=x0,
            method='SLSQP',
            bounds=bounds,
            options={'maxiter': 2000, 'ftol': 1e-9, 'disp': False}
        )

        # 记录最优结果
        if res.success and np.all(res.x >= 0) and res.fun < best_fun:
            best_fun = res.fun
            best_x = res.x.copy()
            print(f"[初始点{guess_idx+1}] 求解成功 | 目标函数值: {res.fun:.6e}")
        else:
            msg = res.message if res.success else f"失败: {res.message[:20]}..."
            print(f"[初始点{guess_idx+1}] {msg} | 目标函数值: {res.fun:.6e}")

    # 兜底逻辑（确保有解）
    if best_x is None:
        best_x = np.ones(m)
        best_fun = objective(best_x)
        print(f"[兜底] 使用默认x=1.0 | 目标函数值: {best_fun:.6e}")

    return best_x, best_fun

# ---------- 主流程（参数传递全链路统一） ----------
def synthesize_workload(block_path, target_params):
    """
    完整流程：
    1. 读特征 → 2. 构建目标向量t → 3. 求解x → 4. 输出误差 → 5. 生成计划
    """
    # 1. 读取代码块特征
    print("\n1. 读取代码块特征")
    block_feature = read_load_features(block_path)
    m = len(block_feature['init_iter'])
    print(f"   加载 {m} 个代码块 | 初始迭代次数范围: {block_feature['init_iter'].min()}~{block_feature['init_iter'].max()}")

    # 2. 构建目标性能向量t（从target_params推导，统一格式）
    print("\n2. 构建目标性能向量t")
    target_duration = target_params['duration']
    target_cpi = target_params['CPI']
    target_mpki = target_params['MPKI']
    # 推导目标总指令（保留原逻辑）
    target_instr = target_duration * 2.6 * 1e9
    # 推导目标总周期、总缓存缺失
    target_cycle = target_instr * target_cpi if target_instr > EPS else 0.0
    target_llmiss = (target_mpki * target_instr) / 1000 if target_instr > EPS else 0.0
    target_t = np.array([target_cycle, target_instr, target_llmiss])  # 统一目标向量格式

    # 打印目标参数（便于调试）
    print(f"   目标CPI: {target_cpi:.6f} | 目标MPKI: {target_mpki:.6f} | 目标duration: {target_duration:.6f}s")
    print(f"   推导目标总指令: {target_instr:.0f} | 目标总周期: {target_cycle:.0f} | 目标总缓存缺失: {target_llmiss:.0f}")

    # 3. 求解缩放系数x
    print("\n3. 求解缩放系数x（实际运行次数 = int(init_iter * x)）")
    objective, _, bounds = build_objective_model(block_feature, target_t)
    best_x, best_fun = solve_scale_factor(objective, bounds)
    print(f"   最优缩放系数x: {np.round(best_x, 4).tolist()}")

    # 4. 计算实际结果与误差（用户关注的核心输出）
    print("\n4. 结果与误差分析")
    metrics = calculate_actual_metrics(best_x, block_feature, target_t)
    print("   " + "="*80)
    print("   📊 预期指标 vs 目标指标（误差百分比）")
    print("   " + "="*80)
    print(f"   {'指标':<12} {'目标值':<20} {'预期值':<20} {'误差':<10}")
    print("   " + "-"*80)
    print(f"   {'CPI':<12} {target_cpi:<20.6f} {metrics['expected_cpi']:<20.6f} {metrics['cpi_err_pct']:<10.2f}%")
    print(f"   {'MPKI':<12} {target_mpki:<20.6f} {metrics['expected_mpki']:<20.6f} {metrics['mpki_err_pct']:<10.2f}%")
    print(f"   {'总指令':<12} {target_instr:<20.0f} {metrics['total_instr']:<20.0f} {metrics['instr_err_pct']:<10.2f}%")
    print("   " + "="*80)

    # 5. 生成执行计划（替换迭代次数）
    print("\n5. 生成执行计划")
    template_res = []
    for param, iter_val in zip(block_feature['param_sets'], metrics['actual_iter']):
        try:
            new_param = list(param[0])  # 提取原始param结构
        except (IndexError, TypeError):
            new_param = [None, 'unknown', 1]  # 格式异常兜底
        # 确保参数长度足够，替换迭代次数
        while len(new_param) < 3:
            new_param.append(1)
        new_param[2] = int(iter_val)  # 实际运行次数（int(init_iter*x)）
        template_res.append(new_param)
    print(f"   生成 {len(template_res)} 个代码块执行计划")

    return template_res, best_x

# ---------- 主程序入口（稳定鲁棒，兼容命令行参数） ----------
if __name__ == "__main__":
    # 命令行参数解析（清晰提示用法）
    if len(sys.argv) < 2:
        print("用法：python generate.py <sample_index> [phase_index]")
        print("  功能：求解缩放系数x，实际运行次数 = int(代码块初始迭代次数 * x)")
        print("  输出：预期CPI/MPKI/总指令与目标值的误差百分比 + 执行计划文件")
        print("  示例：")
        print("    处理所有阶段：python generate.py 1")
        print("    仅处理第0阶段：python generate.py 1 0")
        sys.exit(1)

    # 参数赋值与校验
    try:
        sample_index = int(sys.argv[1])
        phase_index = int(sys.argv[2]) if len(sys.argv) > 2 else None
    except ValueError:
        raise ValueError("参数错误：sample_index和phase_index必须为整数")

    block_path = '../single_rank_block.csv'  # 代码块文件路径（可根据需求修改）
    aggr_path = f'stage{sample_index}/aggr.csv'  # 目标参数文件路径

    # 初始化日志
    print("=" * 80)
    print("MPI程序负载合成工具（稳定版）")
    print(f"核心逻辑：实际运行次数 = int(代码块初始迭代次数 * 缩放系数x)")
    print(f"当前配置：sample_index={sample_index} | phase_index={phase_index if phase_index is not None else '所有'}")
    print("=" * 80)

    # 读取目标参数（aggr.csv）
    try:
        aggr_df = pd.read_csv(aggr_path)
    except FileNotFoundError:
        raise FileNotFoundError(f"目标参数文件 {aggr_path} 未找到，请检查sample_index是否正确")

    # 遍历阶段处理
    res_template = []
    total_phases = len(aggr_df)
    target_phases = [phase_index] if phase_index is not None else range(total_phases)

    for phase_idx in target_phases:
        # 阶段索引校验
        if phase_idx < 0 or phase_idx >= total_phases:
            print(f"\n⚠️  阶段 {phase_idx} 超出范围（共{total_phases}个阶段），跳过")
            continue

        # 提取当前阶段目标参数
        row = aggr_df.iloc[phase_idx]
        try:
            target_params = {
                'duration': row['duration'],
                'CPI': row['CPI'],
                'MPKI': row['MPKI']
            }
        except KeyError as e:
            raise KeyError(f"aggr.csv缺少列：{e}，请检查文件格式")

        # 打印阶段信息
        print(f"\n" + "=" * 60)
        print(f"处理阶段 {phase_idx}/{total_phases-1}")
        print("=" * 60)
        print(f"目标参数：duration={target_params['duration']:.6f}s, CPI={target_params['CPI']:.6f}, MPKI={target_params['MPKI']:.6f}")

        # 合成负载（核心调用，无参数混淆）
        phase_template, best_x = synthesize_workload(block_path, target_params)
        res_template.extend(phase_template)

    # 生成最终执行计划文件
    print(f"\n" + "=" * 60)
    res_template.extend([16, 1])  # 保留原尾部标识（兼容下游工具）
    pd.DataFrame({"param_set": [str(res_template)]}).to_csv('param_sets.csv', index=False, encoding='utf-8')
    print(f"✅ 执行计划文件 'param_sets.csv' 生成完成")
    print(f"📋 有效执行计划条目数：{len(res_template)-2}（不含尾部标识）")
    print("=" * 60)