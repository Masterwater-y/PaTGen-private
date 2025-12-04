import json
import pandas as pd
import numpy as np
import ast
import csv
from scipy.optimize import minimize
import os
mem_capacity = 256
mem_size = 16

def objective_function(C, block_feature, targets,
                      stable, lambda_l1=0.01):
    # 自动化字段提取系统
    feature_config = {
        'base_features': ['cycle', 'duration', 'instruction', 'll_miss', 'power'],
        'util_features': ['cpu_util', 'disk_util']
    }
    
    # 动态特征整合
    block = {f: block_feature[f] for f in feature_config['base_features'] + feature_config['util_features']}
    
    # 统一化资源利用率计算
    for util in feature_config['util_features']:
        block[util] = block[util] * block['duration']
        stable[util] = stable[util] * stable['duration']
    
    # 自动化总量计算
    total = {}
    for f in feature_config['base_features'] + feature_config['util_features']:
        total[f] = np.dot(C, block[f]) + stable[f]
    
    # 指标计算管道
    epsilon = 1e-10
    metric_pipeline = [
        ('CPI', 'cycle', 'instruction', lambda n, d: n / (d + epsilon)),
        ('MPKI', 'll_miss', 'instruction', lambda n, d: (n / (d + epsilon)) * 1000),
        ('cpu_util', 'cpu_util', 'duration', lambda n, d: n / (d + epsilon)),
        ('disk_util', 'disk_util', 'duration', lambda n, d: n / (d + epsilon)),
        ('power', 'power', 'duration', lambda n, d: n / (d + epsilon)),  # 新增能效指标
    ]
    
    # 统一误差计算
    errors = {}
    '''targets = {
        'CPI': CPI_target,
        'MPKI': MPKI_target,
        'cpu_util': cpu_util_target,
        'disk_util': disk_util_target,
        'power': power_target
    }'''
    
    for name, num, den, formula in metric_pipeline:
        actual = formula(total[num], total[den])
        errors[name] = (actual - targets[name]) / targets[name]
    
    # 动态加权系统
    weight_config = {
        'CPI': 1.5,
        'MPKI': 1.5,
        'cpu_util': 1.5,
        'disk_util': 1.5,
        'power': 1.5  # 新增能效指标权重
    }
    
    # 总损失计算
    total_error = sum(weight_config[name] * (err ** 2) for name, err in errors.items())
    l1_penalty = lambda_l1 * np.sum(np.abs(C))
    
    return total_error + l1_penalty

# 修改后的 constrained_optimization 函数
def constrained_optimization(block_feature,
                            targets, T_total, stable, 
                            fixed_mask=None, x0=None):
    cycle = block_feature['cycle']
    duration = block_feature['duration']
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
        lambda C: objective_function(C, block_feature,
                                    targets, stable),
        x0=C_init,
        method='SLSQP',
        bounds=bounds,
        constraints=constraints,
        options={'maxiter': 5000, 'ftol': 1e-6}
    )
    if not result.success:
        print("优化警告:", result.message)
    return result.x

def read_load_features(file_path, targets, threshold=0.15):
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
        ((targets['cpu_util'] - threshold <= working_data['cpu_util']) & (working_data['cpu_util'] <= targets['cpu_util'] + threshold))
    )
    # 应用过滤并重新合并基准数据
    filtered_data = pd.concat([
        working_data[filter_condition],
        baseline
    ])

    # 内存利用率调整

    adjusted_mem_util = targets['mem_util'] - (baseline['mem_util'].values[0])*mem_capacity/mem_size

    block_feature={
        'cycle': filtered_data['cycles_sum'].values,
        'instruction': filtered_data['instructions_sum'].values,
        'll_miss': filtered_data['ll-misses_sum'].values,
        'duration': filtered_data['duration'].values,
        'cpu_util': filtered_data['cpu_util'].values,
        'disk_util': filtered_data['disk_util'].values,
        'power' : filtered_data['power_sum'].values,
    }

    return (
        block_feature,
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

def generate_tmp(C, param_set, targets):
    result = []
    mem_size = targets['mem_size']
    mem_util = targets['mem_util']
    for i, param in enumerate(param_set):
        param_copy = [param[0].copy()]
        param_copy[0][2] = int(param_copy[0][2] * C[i])
        if param_copy[0][2] <= 0:
            continue
        result.append(param_copy[0])
    if mem_util < 0:
        result.extend([mem_size, 0])
    else:
        result.extend([mem_size, float(mem_util)])
    return result


memory_feature = {
    "blank":{
        "cycle": 0,
        "instruction": 0,
        "ll_miss": 0,
        "duration": 0,
        "cpu_util": 0,
        'disk_util':0,
        "power":0
    }
}

def process_target_values(target_params, file_path):
    # 参数转换和标准化

    targets = {
        'T_total': target_params['T_total'],
        'CPI': target_params['cpi'],
        'MPKI': target_params['mpki'],
        'cpu_util': target_params['cpu_util_percent'] / 100,
        'disk_util': target_params['disk_io_percent'] / 100,
        'mem_size': mem_size,  # 固定值或从参数获取
        'mem_util': target_params['mem_util_percent'] / 100,
        'mem_util_origin': target_params['mem_util_percent'] / 100,
        'power' : target_params['power']
    }

    # 内存特征选择
    mem_select = round(targets['mem_util'], 1)
    
    try:
        #stable = memory_feature[f"{transformed_params['mem_size']}, {mem_select}"]
        stable = memory_feature["blank"]
    except KeyError:
        raise ValueError(f"内存配置 {targets['mem_size']}, {mem_select} 不存在")

    # 持续时间调整
    adjusted_T_total = targets['T_total'] - stable['duration']
    if adjusted_T_total <= 0:
        raise ValueError("总时间不足，至少需要保留基准持续时间")

    # 读取特征数据
    block_feature, adjusted_mem_util,filtered_param_sets = read_load_features(
        file_path, targets

    )
    targets['mem_util'] = adjusted_mem_util

    # 执行优化
    C = constrained_optimization(
        block_feature,
        targets,
        adjusted_T_total,
        stable
    )
    # 第二阶段优化：将C[i]*duration[i] <30的块置零，并重新优化
    threshold = 3
    duration = block_feature['duration']
    duration_array = np.array(duration)
    mask = (C * duration_array) < threshold
    if np.any(mask):
        C_phase2 = constrained_optimization(
            block_feature,
            targets,
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
        C, block_feature,
        stable, targets, param_sets
    )

'''def generate_report(C, block_feature, stable, targets, param_sets):
    # 配置化指标定义系统
    metric_config = {
        'base_metrics': {
            'cycle': {'unit': 'cycles', 'scale': 1},
            'instruction': {'unit': 'count', 'scale': 1},
            'll_miss': {'unit': 'count', 'scale': 1},
            'duration': {'unit': 'seconds', 'scale': 1}
        },
        'util_metrics': {
            'cpu_util': ('cpu_util', lambda x: x * 100),
            'disk_util': ('disk_io', lambda x: x * 100),
        },
        'quality_metrics': {
            'CPI': {
                'numerator': 'cycle',
                'denominator': 'instruction',
                'formula': lambda n, d: n / d
            },
            'MPKI': {
                'numerator': 'll_miss',
                'denominator': 'instruction',
                'formula': lambda n, d: (n / d) * 1000
            }
        }
    }

    # 自动化特征预处理
    def preprocess_features(feature_dict, duration_field):
        processed = {}
        for metric in metric_config['util_metrics']:
            if metric in feature_dict:
                processed[metric] = feature_dict[metric] * feature_dict[duration_field]
        for metric in metric_config['base_metrics']:
            processed[metric] = feature_dict[metric]
        return processed

    # 动态计算总量
    def calculate_totals(C, features, stable):
        totals = {}
        for metric in metric_config['base_metrics']:
            totals[metric] = np.dot(C, features[metric]) + stable.get(metric, 0)
        for metric in metric_config['util_metrics']:
            totals[metric] = np.dot(C, features[metric]) + stable.get(metric, 0)
        return totals

    # 执行预处理
    block_feature_processed = preprocess_features(block_feature, 'duration')
    stable_processed = preprocess_features(stable, 'duration')

    # 计算各项总量
    totals = calculate_totals(C, block_feature_processed, stable_processed)
    print(totals.keys())
    #totals.update(calculate_totals(C, block_feature_processed, stable_processed))

    # 生成模块详情
    modules = [{
        'block_id': i+1,
        'scaling_factor': float(C[i]),
        **{metric: block_feature[metric][i] * C[i] 
           for metric in metric_config['base_metrics']},
        **{metric: block_feature_processed[metric][i] * C[i]
           for metric in metric_config['util_metrics']}
    } for i in range(len(C)) if C[i] > 1e-6]

    # 构建指标计算结果
    epsilon = 1e-10
    metric_results = {}
    
    # 质量指标计算
    for name, config in metric_config['quality_metrics'].items():
        numerator = totals[config['numerator']]
        denominator = totals[config['denominator']] + epsilon
        metric_results[f'{name}_actual'] = config['formula'](numerator, denominator)

    # 资源利用率计算
    for metric, config in metric_config['util_metrics'].items():
        target_name, transform = config['target']
        duration_total = totals['duration'] + epsilon
        actual_value = totals[metric] / duration_total
        metric_results[f'{target_name}_actual'] = transform(actual_value)

    # 自动生成报告结构
    report = {
        # 动态生成目标参数
        **{f'{k}_target': transform(targets[k]) 
           for k, (target_name, transform) in metric_config['util_metrics'].items()},
        
        # 自动生成质量指标目标
        **{f'{k}_target': targets[k] 
           for k in metric_config['quality_metrics']},
        
        # 实际计算结果
        **metric_results,
        
        # 系统参数
        'mem_capacity': param_sets.get('mem_capacity', 0),
        'mem_size': param_sets.get('mem_size', 0),
        
        # 生成配置
        'generated_template': generate_tmp(C, param_sets, targets),
        'modules': modules,
        
        # 基础总量信息
        **{f'total_{k}': v for k, v in totals.items()}
    }
    report.update({
        'T_total_target': targets.get('T_total', 0),
        'T_total_actual': totals['duration']
    })

    return report'''

def generate_report(C, block_feature, stable, targets, param_sets):
    cycle = block_feature['cycle']
    instruction = block_feature['instruction']
    ll_miss = block_feature['ll_miss']
    duration = block_feature['duration']
    power = block_feature['power']
    cpu_util = block_feature['cpu_util']
    disk_util = block_feature['disk_util']

    
    cpu_util = cpu_util * duration
    disk_util = disk_util * duration
    stable['cpu_util'] = stable['cpu_util'] * stable['duration']
    stable['disk_util'] = stable['disk_util'] * stable['duration']
    # 计算实际指标
    total_cycle = np.dot(C, cycle) + stable['cycle']
    total_instruction = np.dot(C, instruction) + stable['instruction']
    total_ll_miss = np.dot(C, ll_miss) + stable['ll_miss']
    total_duration = np.dot(C, duration) + stable['duration']
    total_power = np.dot(C, power) + stable['power']
    # 计算资源利用率
    total_cpu_util = np.dot(C, cpu_util) + stable['cpu_util']
    total_disk_util = np.dot(C, disk_util) + stable['disk_util'] 
    
    epsilon = 1e-10

    modules = [
            {
                'block_id': i+1,
                'scaling_factor': float(C[i]),
                'duration': duration[i] * C[i],
                'cpu_util': cpu_util[i] * C[i],
                'disk_util': disk_util[i] * C[i],
                'cycle': cycle[i] * C[i],         
                'instruction': instruction[i] * C[i],  
                'll_miss': ll_miss[i] * C[i],
                'power' : power[i] * C[i]
            }
            for i in range(len(C)) if C[i] > 1e-6
        ]
    modules.append({
        # 目标参数
        'T_total_target': targets['T_total'],
        'cpu_util_target': targets['cpu_util'] * 100,
        'mem_util_target': targets['mem_util'] * 100,
        'cpi_target': targets['CPI'],
        'mpki_target': targets['MPKI'],
        'disk_io_target': targets['disk_util'] * 100,
        'power_target': targets['power'],
        
        
        # 实际结果
        'T_total_actual': total_duration,
        'cpu_util_actual': (total_cpu_util / total_duration) * 100,
        'mem_util_actual': targets['mem_util'] * 100,  # 直接使用目标值
        'cpi_actual': total_cycle / total_instruction,
        'mpki_actual': (total_ll_miss / total_instruction) * 1000,
        'disk_io_actual': (total_disk_util / total_duration) * 100,
        'power_actual' : total_power / total_duration,

        "total_cycle":total_cycle,
        "total_instruction":total_instruction,
        "total_cachemiss":total_ll_miss,
        "total_power":total_power
    })
    return {
        # 目标参数
        'T_total_target': targets['T_total'],
        'cpu_util_target': targets['cpu_util'] * 100,
        'mem_util_target': targets['mem_util_origin'] * 100,
        'cpi_target': targets['CPI'],
        'mpki_target': targets['MPKI'],
        'disk_io_target': targets['disk_util'] * 100,
        'power_target': targets['power'],
        'mem_capacity':mem_capacity,
        'mem_size':mem_size,
        # 实际结果
        'T_total_actual': total_duration,
        'cpu_util_actual': (total_cpu_util / total_duration) * 100,
        'mem_util_actual': targets['mem_util_origin'] * 100,  # 直接使用目标值
        'cpi_actual': total_cycle / total_instruction,
        'mpki_actual': (total_ll_miss / total_instruction) * 1000,
        'disk_io_actual': (total_disk_util / total_duration) * 100,
        'power_actual' : total_power / total_duration,
        # 生成配置
        'generated_template': generate_tmp(C, param_sets, targets),
        
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
            'power_target': res['power_target'],
            # 实际结果
            'T_total_actual': res['T_total_actual'],
            'cpu_util_actual': res['cpu_util_actual'],
            'cpi_actual': res['cpi_actual'],
            'mpki_actual': res['mpki_actual'],
            'disk_io_actual': res['disk_io_actual'],
            'power_actual': res['power_actual'],
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
        "power_target": ("power_actual", "relative"),
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
