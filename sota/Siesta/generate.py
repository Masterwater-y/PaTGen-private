import json
import sys
import numpy as np
import pandas as pd
import ast
from scipy.optimize import minimize  # QP求解依赖
from scipy.linalg import norm  # 误差计算


def read_load_features(file_path):
    # 保持原数据读取逻辑不变，不修改代码块/指标相关逻辑
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
        'rank': [],
        'type': []
    }
    param_sets = data['param_set'].apply(ast.literal_eval).tolist()
    for item in param_sets:
        block_feature['rank'].append(item[0][0])
        block_feature['type'].append(item[0][1])

    return block_feature, param_sets


def build_quadratic_model(block_features, targets, N0=1e7):
    """
    Siesta核心：构建二次优化模型（替代原线性方程组）
    目标：最小化 CPI、MPKI 相对误差的平方和（二次目标）
    约束：执行次数非负 + 总指令数匹配目标
    """
    # 提取基础参数（保持与原代码一致）
    m = len(block_features['instruction'])  # 代码块数量
    cycles_per_block = block_features['cycle']  # 单个代码块周期数（N0次执行）
    instr_per_block = block_features['instruction']  # 单个代码块指令数（N0次执行）
    llmiss_per_block = block_features['ll_miss']  # 单个代码块LLC缺失数（N0次执行）
    
    # 目标指标（从输入参数提取，保持原逻辑）
    target_cpi = targets['CPI']
    target_mpki = targets['MPKI']
    target_total_instr = targets['instruction']  # 目标总指令数

    # --------------------------
    # 1. 二次目标函数：min Σ(相对误差)^2（Siesta核心思想）
    # --------------------------
    def objective(x):
        # x: 各代码块执行次数（变量）
        # 计算实际总指标（需除以N0，还原单次执行的累积值）
        total_cycle = np.sum(cycles_per_block * x) / N0
        total_instr = np.sum(instr_per_block * x) / N0
        total_llmiss = np.sum(llmiss_per_block * x) / N0

        # 计算CPI、MPKI的相对误差（避免除以零）
        cpi_actual = total_cycle / total_instr if total_instr != 0 else 0
        mpki_actual = (total_llmiss / total_instr) * 1000 if total_instr != 0 else 0

        cpi_rel_error = (cpi_actual - target_cpi) / target_cpi if target_cpi != 0 else 0
        mpki_rel_error = (mpki_actual - target_mpki) / target_mpki if target_mpki != 0 else 0

        # 二次目标：最小化相对误差平方和（Siesta论文式5的简化，仅保留CPI、MPKI）
        return cpi_rel_error ** 2 + mpki_rel_error ** 2

    # --------------------------
    # 2. 约束条件：等式约束（总指令数匹配）+ 不等式约束（执行次数非负）
    # --------------------------
    # 等式约束：总指令数 = 目标总指令数（对应Siesta的“计算指标匹配”约束）
    def eq_constraint(x):
        total_instr_actual = np.sum(instr_per_block * x) / N0
        return total_instr_actual - target_total_instr  # 要求结果=0

    # 约束列表（scipy minimize格式）
    constraints = [
        {'type': 'eq', 'fun': eq_constraint}  # 等式约束：总指令数匹配
    ]

    # 变量边界：执行次数x≥0（Siesta要求“非负整数解”，先求连续解再取整）
    bounds = [(0, None) for _ in range(m)]

    return objective, constraints, bounds


def solve_quadratic_program(objective, constraints, bounds, init_x=None):
    """
    Siesta QP求解：用二次规划求解器得到最优执行次数（连续解→整数解）
    """
    # 初始值：若未指定，用“平均分配”初始化（避免空解）
    m = len(bounds)
    if init_x is None:
        init_x = np.ones(m) / m  # 初始均匀分配执行次数

    # --------------------------
    # QP求解：最小化二次目标（Siesta核心步骤）
    # 选择SLSQP求解器（支持等式/不等式约束，适配二次问题）
    # --------------------------
    result = minimize(
        fun=objective,
        x0=init_x,
        method='SLSQP',
        bounds=bounds,
        constraints=constraints,
        tol=1e-6,  # 精度阈值（贴合Siesta的低误差要求）
        options={'maxiter': 1000}  # 迭代次数上限
    )

    if not result.success:
        raise RuntimeError(f"QP求解失败：{result.message}")

    # --------------------------
    # Siesta关键步骤：连续解→整数解（执行次数需为正整数）
    # --------------------------
    x_continuous = result.x
    x_integer = np.round(x_continuous).astype(int)  # 四舍五入取整
    x_integer[x_integer < 0] = 0  # 确保取整后仍非负

    return x_integer, result.fun  # 返回整数解 + 最小目标函数值（误差）


def synthesize_workload(load_features_file, target_params):
    """
    主函数：替换原线性求解为Siesta二次优化求解
    """
    # 1. 读取数据（保持原逻辑）
    block_feature, param_sets = read_load_features(load_features_file)
    N0 = 1e7  # 原代码的“初始测量次数”，保持不变

    # 2. 构建Siesta二次优化模型（核心修改点）
    objective, constraints, bounds = build_quadratic_model(
        block_features=block_feature,
        targets=target_params,
        N0=N0
    )

    # 3. QP求解：得到最优执行次数（整数解）
    x_optimized, min_error = solve_quadratic_program(
        objective=objective,
        constraints=constraints,
        bounds=bounds
    )

    # 4. 结果验证：计算实际CPI、MPKI（保持原输出逻辑，新增误差显示）
    total_cycle = np.sum(block_feature['cycle'] * x_optimized) / N0
    total_instr = np.sum(block_feature['instruction'] * x_optimized) / N0
    total_llmiss = np.sum(block_feature['ll_miss'] * x_optimized) / N0

    actual_cpi = total_cycle / total_instr if total_instr != 0 else 0
    actual_mpki = (total_llmiss / total_instr) * 1000 if total_instr != 0 else 0
    cpi_error = abs(actual_cpi - target_params['CPI']) / target_params['CPI'] * 100
    mpki_error = abs(actual_mpki - target_params['MPKI']) / target_params['MPKI'] * 100

    # 输出Siesta优化结果（新增误差显示，贴合论文“高精度”特性）
    print(f"QP求解完成：最小误差={min_error:.6f}")
    print(f"目标CPI={target_params['CPI']:.4f} → 实际CPI={actual_cpi:.4f}（误差={cpi_error:.2f}%）")
    print(f"目标MPKI={target_params['MPKI']:.4f} → 实际MPKI={actual_mpki:.4f}（误差={mpki_error:.2f}%）")
    print(f"总指令数：目标={target_params['instruction']:.0f} → 实际={total_instr:.0f}")

    # 5. 生成执行计划（保持原逻辑，过滤无效解）
    valid_indices = x_optimized > 1e-6  # 忽略极小值（视为零）
    template_res = []
    for i in np.where(valid_indices)[0]:
        scale = x_optimized[i]
        # 更新代码块参数（执行次数按优化结果缩放）
        param = param_sets[i][0].copy()
        param[2] = int(param[2] * scale)  # 原代码的“执行次数参数”
        template_res.append(param)

    return template_res


# --------------------------
# 后续主逻辑（保持原代码完全不变，仅调用修改后的synthesize_workload）
# --------------------------
if __name__ == "__main__":
    block_path = 'block.csv'
    args = sys.argv[1:]
    sample_index = int(args[0])
    phase_index = None
    if len(args) > 1:
        phase_index = int(args[1])

    aggr_df = pd.read_csv(f'stage{sample_index}/aggr.csv')
    target_path = f'stage{sample_index}/targets.csv'
    targets_df = pd.read_csv(target_path)
    res_template = []

    for _, targets_row in aggr_df.iterrows():
        if phase_index is not None and _ != phase_index:
            continue

        # 保持原目标参数计算逻辑不变
        instructions = targets_row['duration'] * 3 * 10e8
        targets = {
            "CPI": targets_row['CPI'],
            "MPKI": targets_row['MPKI'],
            "instruction": instructions,
            "duration": targets_row['duration']
        }
        print(f"\n=== 处理阶段{_}：目标参数 {targets} ===")
        
        # 调用修改后的Siesta二次优化合成函数
        template = synthesize_workload(block_path, target_params=targets)
        res_template.extend(template)

    # 保持原输出逻辑不变
    res_template.extend([16, 1])
    param_sets = [{"param_set": str(res_template)}]
    pd.DataFrame(param_sets).to_csv('param_sets.csv', index=False)