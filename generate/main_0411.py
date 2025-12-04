import json
import pandas as pd
import numpy as np
import ast
import csv
from scipy.optimize import minimize
import os
mem_capacity = 256
mem_size = 16

def objective_function(C, cycle, instruction, cachemiss, duration, cpu_util, disk_util,
                      CPI_target, MPKI_target, cpu_util_target, disk_util_target, stable, lambda_l1=0.01, lambda_penalty=0.00):
    total_cycle = np.dot(C, cycle) + stable['cycle']
    total_instruction = np.dot(C, instruction) + stable['instruction']
    total_cachemiss = np.dot(C, cachemiss) + stable['cachemiss']
    total_duration = np.dot(C, duration) + stable['duration']
    total_cpu_util_num = np.dot(C, cpu_util * duration) + stable['cpu_util'] * stable['duration']
    total_disk_util_num = np.dot(C, disk_util * duration) + stable['disk_util'] * stable['duration']
    
    epsilon = 1e-10
    CPI_actual = total_cycle / (total_instruction + epsilon)
    MPKI_actual = (total_cachemiss / (total_instruction + epsilon)) * 1000
    cpu_util_actual = total_cpu_util_num / (total_duration + epsilon)
    disk_util_actual = total_disk_util_num / (total_duration + epsilon)
    
    CPI_error = (CPI_actual - CPI_target) / CPI_target
    MPKI_error = (MPKI_actual - MPKI_target) / MPKI_target
    cpu_util_error = (cpu_util_actual - cpu_util_target) / cpu_util_target
    disk_util_error = (disk_util_actual - disk_util_target) / disk_util_target
    

    l1_penalty = lambda_l1 * np.sum(np.abs(C))
    violation = np.maximum(30 - C * duration, 0)  # 计算违反量
    active_penalty = np.where(C > 1e-6, 1.0, 0.0)  # 识别非零系数

    duration_penalty = lambda_penalty * np.sum(violation * active_penalty)
    error = 1.5 * CPI_error**2 + 1.5 * MPKI_error**2 +  cpu_util_error**2 +  1.5*disk_util_error**2
    return error + l1_penalty + duration_penalty

# 修改后的 constrained_optimization 函数
def constrained_optimization(cycle, instruction, cachemiss, duration, cpu_util, disk_util,
                            CPI_target, MPKI_target, cpu_util_target, disk_util_target, T_total, stable, 
                            fixed_mask=None, x0=None):
    if fixed_mask is None:
        fixed_mask = np.zeros(len(cycle), dtype=bool)
    if x0 is not None:
        C_init = x0.copy()
        C_init[fixed_mask] = 0.0
    else:
        C_init = np.ones(len(cycle))
        C_init[fixed_mask] = 0.0
    
    bounds = [(0.0, 0.0) if fm else (0.0, None) for fm in fixed_mask]
    
    constraints = ({'type': 'eq', 'fun': lambda C: np.dot(C, duration) - T_total},)
    
    result = minimize(
        lambda C: objective_function(C, cycle, instruction, cachemiss, duration, cpu_util, disk_util,
                                    CPI_target, MPKI_target, cpu_util_target, disk_util_target, stable),
        x0=C_init,
        method='SLSQP',
        bounds=bounds,
        constraints=constraints,
        options={'maxiter': 5000, 'ftol': 1e-6}
    )
    if not result.success:
        print("优化警告:", result.message)
    return result.x

def read_load_features(file_path, mem_util_target, cpu_util_target, threshold=0.15):
    # 读取并验证数据
    data = pd.read_csv(file_path)
    required_columns = ['param_set', 'duration', 'cycles_sum', 'instructions_sum', 'll-misses_sum',
                       'cpu_util', 'disk_util', 'mem_util']
    
    for col in required_columns:
        if col not in data.columns:
            raise ValueError(f"CSV文件中缺少{col}列")
    assert all(data['cpu_util'].between(0, 1)), "CPU利用率数值应在0-1之间"

    # 分离基准数据（最后一行）
    baseline = data.iloc[[-1]]
    working_data = data.iloc[:-1].copy()

    # 解析param_set并提取block类型
    def extract_block_types(param_str):
        try:
            params = ast.literal_eval(param_str)
            return [p[1] for p in params if isinstance(p, list) and len(p) > 1]
        except:
            return []
    
    working_data['block_types'] = working_data['param_set'].apply(extract_block_types)

    # 创建过滤条件
    #threshold = cpu_util_target + threshold
    has_target_blocks = working_data['block_types'].apply(
        lambda types: any(t in ['div', 'add', 'mem', 'disk'] for t in types)
    )
    
    filter_condition = (
        (~has_target_blocks) | 
        ((cpu_util_target - threshold <= working_data['cpu_util']) & (working_data['cpu_util'] <= cpu_util_target + threshold))
    )
    # 应用过滤并重新合并基准数据
    filtered_data = pd.concat([
        working_data[filter_condition],
        baseline
    ])

    # 内存利用率调整
    adjusted_mem_util = mem_util_target - (baseline['mem_util'].values[0])*mem_capacity/mem_size
    return (
        filtered_data['cycles_sum'].values,
        filtered_data['instructions_sum'].values,
        filtered_data['ll-misses_sum'].values,
        filtered_data['duration'].values,
        filtered_data['cpu_util'].values,
        filtered_data['disk_util'].values,
        
        adjusted_mem_util,
        filtered_data['param_set'].apply(ast.literal_eval).tolist()
    )
def read_csv_param_sets(file_path):
    param_sets = []
    with open(file_path, 'r', newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            param_set = ast.literal_eval(row['param_set'])
            param_sets.append(param_set)
    return param_sets

def generate_tmp(C, param_set, duration, adjusted_mem_util, mem_size):
    result = []
    for i, param in enumerate(param_set):
        param_copy = [param[0].copy()]
        param_copy[0][2] = int(param_copy[0][2] * C[i])
        if param_copy[0][2] <= 0:
            continue
        result.append(param_copy[0])
    if adjusted_mem_util < 0:
        result.extend([mem_size, 0])
    else:
        result.extend([mem_size, float(adjusted_mem_util)])
    return result


memory_feature = {
    "blank":{
        "cycle": 0,
        "instruction": 0,
        "cachemiss": 0,
        "duration": 0,
        "cpu_util": 0,
        'disk_util':0
    }
}

def process_target_values(target_params, file_path):
    # 参数转换和标准化

    transformed_params = {
        'T_total': target_params['T_total'],
        'CPI_target': target_params['cpi'],
        'MPKI_target': target_params['mpki'],
        'cpu_util_target': target_params['cpu_util_percent'] / 100,
        'disk_util_target': target_params['disk_io_percent'] / 100,
        'mem_size': mem_size,  # 固定值或从参数获取
        'mem_util_target': target_params['mem_util_percent'] / 100
    }

    # 内存特征选择
    mem_select = round(transformed_params['mem_util_target'], 1)
    
    try:
        #stable = memory_feature[f"{transformed_params['mem_size']}, {mem_select}"]
        stable = memory_feature["blank"]
    except KeyError:
        raise ValueError(f"内存配置 {transformed_params['mem_size']}, {mem_select} 不存在")

    # 持续时间调整
    adjusted_T_total = transformed_params['T_total'] - stable['duration']
    if adjusted_T_total <= 0:
        raise ValueError("总时间不足，至少需要保留基准持续时间")

    # 读取特征数据
    cycle, instruction, cachemiss, duration, cpu_util, disk_util, adjusted_mem_util,filtered_param_sets = read_load_features(
        file_path, transformed_params['mem_util_target'], transformed_params['cpu_util_target']

    )

    # 执行优化
    C = constrained_optimization(
        cycle, instruction, cachemiss, duration, cpu_util, disk_util,
        transformed_params['CPI_target'],
        transformed_params['MPKI_target'],
        transformed_params['cpu_util_target'],
        transformed_params['disk_util_target'],
        adjusted_T_total,
        stable
    )
    # 第二阶段优化：将C[i]*duration[i] <30的块置零，并重新优化
    threshold = 3
    duration_array = np.array(duration)
    mask = (C * duration_array) < threshold
    if np.any(mask):
        C_phase2 = constrained_optimization(
            cycle, instruction, cachemiss, duration, cpu_util, disk_util,
            transformed_params['CPI_target'],
            transformed_params['MPKI_target'],
            transformed_params['cpu_util_target'],
            transformed_params['disk_util_target'],
            adjusted_T_total,
            stable,
            fixed_mask=mask,
            x0=C.copy()
        )
        C = C_phase2
    # 结果后处理
    C = np.maximum(C, 0)
    param_sets = filtered_param_sets 

    # 生成完整报告
    return generate_report(
        C, cycle, instruction, cachemiss, duration, cpu_util, disk_util,
        stable, transformed_params, param_sets, adjusted_mem_util
    )

def generate_report(C, cycle, instruction, cachemiss, duration, cpu_util, disk_util,
                   stable, params, param_sets, adjusted_mem_util):
    # 计算实际指标
    total_cycle = np.dot(C, cycle) + stable['cycle']
    total_instruction = np.dot(C, instruction) + stable['instruction']
    total_cachemiss = np.dot(C, cachemiss) + stable['cachemiss']
    total_duration = np.dot(C, duration) + stable['duration']
    
    # 计算资源利用率
    cpu_util_num = np.dot(C, cpu_util * duration) + stable['cpu_util'] * stable['duration']
    disk_util_num = np.dot(C, disk_util * duration) + stable['disk_util'] * stable['duration']
    
    epsilon = 1e-10

    modules = [
            {
                'block_id': i+1,
                'scaling_factor': float(C[i]),
                'duration': duration[i] * C[i],
                'cpu_util': cpu_util[i] * 100,
                'disk_util': disk_util[i] * 100,
                'cycle': cycle[i] * C[i],         
                'instruction': instruction[i] * C[i],  
                'cachemiss': cachemiss[i] * C[i] 
            }
            for i in range(len(C)) if C[i] > 1e-6
        ]
    modules.append({
        # 目标参数
        'T_total_target': params['T_total'],
        'cpu_util_target': params['cpu_util_target'] * 100,
        'mem_util_target': params['mem_util_target'] * 100,
        'cpi_target': params['CPI_target'],
        'mpki_target': params['MPKI_target'],
        'disk_io_target': params['disk_util_target'] * 100,
        
        
        # 实际结果
        'T_total_actual': total_duration,
        'cpu_util_actual': (cpu_util_num / total_duration) * 100,
        'mem_util_actual': params['mem_util_target'] * 100,  # 直接使用目标值
        'cpi_actual': total_cycle / total_instruction,
        'mpki_actual': (total_cachemiss / total_instruction) * 1000,
        'disk_io_actual': (disk_util_num / total_duration) * 100,

        "total_cycle":total_cycle,
        "total_instruction":total_instruction,
        "total_cachemiss":total_cachemiss,
    })
    return {
        # 目标参数
        'T_total_target': params['T_total'],
        'cpu_util_target': params['cpu_util_target'] * 100,
        'mem_util_target': params['mem_util_target'] * 100,
        'cpi_target': params['CPI_target'],
        'mpki_target': params['MPKI_target'],
        'disk_io_target': params['disk_util_target'] * 100,
        'mem_capacity':mem_capacity,
        'mem_size':mem_size,
        # 实际结果
        'T_total_actual': total_duration,
        'cpu_util_actual': (cpu_util_num / total_duration) * 100,
        'mem_util_actual': params['mem_util_target'] * 100,  # 直接使用目标值
        'cpi_actual': total_cycle / total_instruction,
        'mpki_actual': (total_cachemiss / total_instruction) * 1000,
        'disk_io_actual': (disk_util_num / total_duration) * 100,
        
        # 生成配置
        'generated_template': generate_tmp(C, param_sets, duration, adjusted_mem_util, params['mem_size']),
        
        # 详细模块信息
        'modules': modules
    }


def main(input_csv, block_csv, output_csv):
    # 读取目标参数
    target_df = pd.read_csv(input_csv)
    
    # 处理所有目标组
    results = []
    for _, row in target_df.iterrows():
        '''try:
            result = process_target_values(row.to_dict(), block_csv)
            results.append(result)
        except Exception as e:
            print(f"处理目标组失败: {row.to_dict()}\n错误: {str(e)}")'''
        result = process_target_values(row.to_dict(), block_csv)
        results.append(result)

    # 转换结果为表格格式
    output_data = []
    for res in results:
        output_row = {
            # 目标参数
            'T_total_target': res['T_total_target'],
            'cpu_util_target': res['cpu_util_target'],
            'mem_size':mem_size,
            'mem_capacity':mem_capacity,
            'mem_util_target': res['mem_util_target'],

            'cpi_target': res['cpi_target'],
            'mpki_target': res['mpki_target'],
            'disk_io_target': res['disk_io_target'],
            
            # 实际结果
            'T_total_actual': res['T_total_actual'],
            'cpu_util_actual': res['cpu_util_actual'],
            'cpi_actual': res['cpi_actual'],
            'mpki_actual': res['mpki_actual'],
            'disk_io_actual': res['disk_io_actual'],
            
            # 配置信息
            'generated_template': str(res['generated_template']),
            'modules_count': len(res['modules']) ,
            'modules_details': json.dumps(res['modules'])
        }
        output_data.append(output_row)
    
    # 保存结果
    pd.DataFrame(output_data).to_csv(output_csv, index=False)
    print(f"已生成 {len(output_data)} 组结果到 {output_csv}")

def evaluate(target_dir=None, range=None):
    """评估目标值与实际值的相似度 (仅target_actual模式)"""
    # 设置默认目录为当前工作目录
    target_dir = target_dir or os.getcwd()
    
    # 定义字段映射关系 (目标列 → 实际值列)
    mapping = {
        "T_total_target": ("T_total_actual", "relative"),
        "cpu_util_target": ("cpu_util_actual", "absolute"),
        "disk_io_target": ("disk_io_actual", "absolute"),
        "cpi_target": ("cpi_actual", "relative"),
        "mpki_target": ("mpki_actual", "relative"),
    }

    # 读取目标文件
    target_file = os.path.join(target_dir, 'results.csv')
    try:
        with open(target_file, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except FileNotFoundError:
        print(f"错误：目标文件 {target_file} 不存在")
        return

    # 应用范围过滤
    if isinstance(range, (tuple, list)) and len(range) == 2:
        start, end = range
        rows = rows[start:end]

    # 准备数据结构
    data_pairs = []
    for row in rows:
        data_pairs.append((row, row))  # 使用同一行数据对比目标值和实际值

    # 计算相似度
    output_headers = ["ID"] + [f"{col}_sim" for col in mapping.keys()] + ["Overall"]
    output_rows = []
    stats = {col: {"sum": 0, "count": 0} for col in mapping}
    overall_sum = 0

    for idx, (target_data, result_data) in enumerate(data_pairs, 1):
        similarities = {}
        
        for target_col, (result_col, error_type) in mapping.items():
            try:
                # 提取并转换数值
                t_val = float(target_data[target_col])
                r_val = float(result_data[result_col])
                
                # 计算相似度
                if error_type == 'absolute':
                    # 绝对误差计算：1 - |实际-目标|/量程 (假设百分比格式)
                    sim = 100 * (1 - abs(r_val - t_val)/100)
                else:
                    # 相对误差计算：1 - |实际-目标|/目标
                    sim = 100 * (1 - abs(r_val - t_val)/t_val) if t_val !=0 else 100
                
                # 记录统计信息
                similarities[f"{target_col}_sim"] = round(sim, 2)
                stats[target_col]["sum"] += sim
                stats[target_col]["count"] += 1
                
            except (KeyError, ValueError, ZeroDivisionError) as e:
                similarities[f"{target_col}_sim"] = "N/A"

        # 计算综合评分
        valid_sims = [v for v in similarities.values() 
                     if isinstance(v, (int, float))]
        overall = sum(valid_sims)/len(valid_sims) if valid_sims else 0
        overall_sum += overall
        similarities["Overall"] = round(overall, 2)
        similarities .update({"ID": idx}) 
        output_rows.append(similarities)

    # 添加统计行
    avg_row = {"ID": "Average"}
    for col in mapping:
        if stats[col]["count"] > 0:
            avg = stats[col]["sum"] / stats[col]["count"]
            avg_row[f"{col}_sim"] = round(avg, 2)
        else:
            avg_row[f"{col}_sim"] = "N/A"
    avg_row["Overall"] = round(overall_sum/len(data_pairs), 2)
    output_rows.append(avg_row)

    # 输出结果文件
    output_path = os.path.join(target_dir, "target_actual_evaluation.csv")
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=output_headers)
        writer.writeheader()
        writer.writerows(output_rows)
    
    print(f"评估报告已生成：{output_path}")
    return output_path




if __name__ == "__main__":
    main('targets.csv', 'block.csv', 'results.csv')
    evaluate()  
