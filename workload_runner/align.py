import os
import pandas as pd
import csv

CACHE_COL='L1-dcache-load-misses'

def calculate_metrics_base(data):
    """解耦后的基础指标计算"""
    try:
        required_columns = ['time','cpu_idle', 'MemAvailable', 'MemTotal', 'cycles', 'instructions',
                          'L1-dcache-load-misses', 'util', 'rMB/s', 'wMB/s',
                          'branch-misses', 'branches','armv8_pmuv3_0/ll_cache_miss/']
        for col in required_columns:
            if col not in data.columns:
                raise KeyError(f"Missing required column: {col}")

        new_data = pd.DataFrame()
        new_data['time'] = data['time']
        new_data['cpu_util'] = 1 - data['cpu_idle']
        new_data['mem_util'] = 1 - data['MemAvailable'].div(data['MemTotal'], fill_value=1)
        new_data['cycles'] = data['cycles']
        new_data['instructions'] = data['instructions']
        new_data['L1-misses'] = data['L1-dcache-load-misses']
        new_data['ll-misses/'] = data['armv8_pmuv3_0/ll_cache_miss/']
        new_data['power'] = data['power']
        new_data['CPI'] = data['cycles'].div(data['instructions'], fill_value=1)
        new_data['MPKI'] = (data['armv8_pmuv3_0/ll_cache_miss/'] * 1000).div(data['instructions'], fill_value=1)
        new_data['MPKI_L1'] = (data['L1-dcache-load-misses'] * 1000).div(data['instructions'], fill_value=1)
        new_data['disk_util'] = data['util']
        new_data['branches'] =  data['branches']
        new_data['branch-misses'] =  data['branch-misses']
        new_data['branch-misses-ratio'] = (data['branch-misses']).div(data['branches'], fill_value=1)

        # 清理无效值
        #for col in new_data.columns:
        #    new_data[col] = new_data[col].replace([float('inf'), float('-inf')], 0).fillna(0)
            
        return new_data

    except Exception as e:
        print(f"指标计算错误: {str(e)}")
        return None

def get_metric_base(data):
    """将required_column转换为对应的列名"""
    required_columns = ['time', 'cpu_idle', 'MemAvailable', 'MemTotal', 'cycles', 'instructions',
                        'L1-dcache-load-misses', 'util', 'rMB/s', 'wMB/s',
                        'branch-misses', 'branches', 'armv8_pmuv3_0/ll_cache_miss/']
    
    # 检查必要列是否存在
    for col in required_columns:
        if col not in data.columns:
            raise KeyError(f"Missing required column: {col}")
    # 计算基础利用率指标
    new_data = pd.DataFrame()
    new_data['cpu_util'] = 1 - data['cpu_idle']
    new_data['mem_util'] = 1 - data['MemAvailable'].div(data['MemTotal'], fill_value=1)
    # 基础列映射（直接复制的列）
    base_columns = {
        'time': 'time',
        'cycles': 'cycles',
        'instructions': 'instructions',
        'L1-dcache-load-misses': 'L1-misses',
        'armv8_pmuv3_0/ll_cache_miss/': 'll-misses/',
        'power':'power',
        'util': 'disk_util',
        'branches': 'branches',
        'branch-misses': 'branch-misses'
    }
    
    # 构建基础数据

    for src_col, tgt_col in base_columns.items():
        new_data[tgt_col] = data[src_col]

    return new_data


def calc_metrics(data):
    """基于基础数据计算需要复杂计算的列"""
    new_data = data.copy()
    
    # 计算派生指标
    new_data['CPI'] = data['cycles'].div(data['instructions'], fill_value=1)
    new_data['MPKI'] = (data['ll-misses/'] * 1000).div(data['instructions'], fill_value=1)
    new_data['MPKI_L1'] = (data['L1-misses'] * 1000).div(data['instructions'], fill_value=1)
    new_data['branch-misses-ratio'] = data['branch-misses'].div(data['branches'], fill_value=1)
    column_order = ['time', 'cpu_util', 'mem_util', 'disk_util', 'cycles', 'instructions', 
                    'L1-misses', 'll-misses/', 'CPI','MPKI','MPKI_L1','power','branches', 'branch-misses','branch-misses-ratio']
    new_data = new_data[column_order]
    return new_data

def calculate_aggregations(metric_data):
    """基于填充后的指标数据计算聚合"""
    try:
        metric_data_without_time = metric_data.drop(columns=['time'], errors='ignore')
        # 计算基础聚合
        aggregations = metric_data_without_time.agg(['max', 'min', 'mean', 'median', 'sum'])
        
        # 计算最终行
        sum_cycles = aggregations.loc['sum', 'cycles']
        sum_instructions = aggregations.loc['sum', 'instructions']
        sum_L1_misses = aggregations.loc['sum', 'L1-misses']
        sum_ll_misses = aggregations.loc['sum', 'll-misses/']
        sum_power = aggregations.loc['sum', 'power']
        sum_branches = aggregations.loc['sum', 'branches']
        sum_branch_miss = aggregations.loc['sum', 'branch-misses']

        sum_instructions = sum_instructions if sum_instructions != 0 else 1e-10
        final_row = aggregations.loc['mean'].copy()
        final_row['cycles'] = sum_cycles
        final_row['instructions'] = sum_instructions
        final_row['L1-misses'] = sum_L1_misses
        final_row['ll-misses/'] = sum_ll_misses

        final_row['CPI'] = sum_cycles / sum_instructions
        final_row['MPKI'] = (sum_ll_misses * 1000) / sum_instructions
        final_row['MPKI_L1'] = (sum_L1_misses * 1000) / sum_instructions
        final_row['branches'] = sum_branches
        final_row['branch-misses'] = sum_branch_miss
        final_row['branch-misses-ratio'] = (sum_branch_miss * 1000) / sum_branches
        final_df = pd.DataFrame([final_row], index=['final'])
        aggregations = pd.concat([aggregations, final_df])
        
        return aggregations.reset_index().rename(columns={'index': 'aggr_type'})

    except Exception as e:
        print(f"聚合计算错误: {str(e)}")
        return None

def fill_zero_with_previous(df, columns):
    """指标数据零值填充"""
    df_filled = df.copy().sort_values('time')
    for col in columns:
        if col not in df_filled.columns:
            continue
        df_filled[col] = df_filled[col].ffill().bfill()
    return df_filled

def check_zero_values(df, check_columns):
    """检查指标数据零值"""
    na_rows = []
    if df.empty:
        return na_rows
    for col in check_columns:
        if col not in df.columns:
            continue
        na_mask = df[col].isna()
        if na_mask.any():
            records = df.loc[na_mask, ['time', col]].to_dict('records')
            na_rows.append( (col, records) )
    return na_rows

def filter_performance_data(result_dir):
    """主处理流程"""
    # 初始化路径
    timestamp_file = os.path.join(result_dir, 'time_record/time_record.csv')
    performance_file = os.path.join(result_dir, 'perf/perf_200.csv')
    
    # 读取时间记录
    timestamps = []
    with open(timestamp_file, 'r') as f:
        reader = csv.reader(f)
        next(reader)  # Skip header
        for row in reader:
            timestamps.append( (row[0], row[1], int(row[2]), int(row[3]), int(row[4])) )

    # 读取性能数据
    performance_df = pd.read_csv(performance_file)

    missing_reports = []
    zero_reports = []
    
    # 处理每个时间段
    for idx, (workload, param_set, start, end, duration) in enumerate(timestamps):
        # 生成路径
        metric_path = os.path.join(result_dir, f'final_result/metric_{idx}.csv')
        perf_path = os.path.join(result_dir, f'final_result/perf_{idx}.csv')
        aggr_path = os.path.join(result_dir, f'final_result/aggr_{idx}.csv')
        second_path = os.path.join(result_dir, f'final_result/second_{idx}.csv')
        
        # 筛选原始数据
        filtered = performance_df[
            (performance_df['time'] >= start) & 
            (performance_df['time'] <= end)
        ].copy()
        
        if filtered.empty:
            print(f"警告: 时间段 {start}-{end} 无数据")
            continue
            
        # 生成基础指标
        metrics = get_metric_base(filtered)  # 跳过首行
        if metrics is None:
            continue
            
        # 零值检测
        zero_issues = check_zero_values(metrics, [
            'cpu_util', 'mem_util', 'cycles', 'instructions',
            'L1-misses', 'll-misses/' ,'disk_util', 'power'
        ])
        if zero_issues:
            zero_reports.append( (metric_path, zero_issues) )
        filled_metrics = metrics
        # 零值填充
        filled_metrics = fill_zero_with_previous(metrics, [
            'cpu_util', 'mem_util', 'cycles', 'instructions',
            'L1-misses', 'll-misses/', 'disk_util', 'power'
        ])
        filled_metrics = calc_metrics(filled_metrics)
        second_targets = aggr_second_targets(filled_metrics,N=2)
        aggr_data = calculate_aggregations(filled_metrics)
        
        # 保存结果
        os.makedirs(os.path.dirname(metric_path), exist_ok=True)
        filled_metrics.to_csv(metric_path, index=False)
        if second_targets is not None:
            second_targets.to_csv(second_path,index=False)
        filtered.to_csv(perf_path, index=False)
        if aggr_data is not None:
            aggr_data.to_csv(aggr_path, index=False)

    # 生成聚合报告（保持不变）
    generate_aggregation_report(result_dir, timestamps)
    # 生成数据质量报告（保持不变）
    generate_quality_report(result_dir, missing_reports, zero_reports)


def aggr_second_targets(filled_metrics, N):
    """
    对filled_metrics每N个点进行一次聚合，最后一组不足N个点时duration为实际数量
    
    参数:
    filled_metrics (DataFrame): 包含性能指标的DataFrame
    N (int): 聚合的点数量
    
    返回:
    DataFrame: 聚合后的性能数据
    """
    if filled_metrics.empty:
        return None
    
    # 创建聚合结果列表
    aggregated_rows = []
    
    # 按N个点进行分组聚合
    for i in range(0, len(filled_metrics), N):
        group = filled_metrics.iloc[i:i+N]
        actual_size = len(group)  # 实际组大小，处理最后一组不足N的情况
        
        # 计算聚合指标
        duration = actual_size  # 使用实际组大小作为duration
        # 使用第一行的值作为聚合后的基础值
        first_row = group.iloc[0]
        cpu_util = first_row['cpu_util']
        mem_util = first_row['mem_util']
        disk_util = first_row['disk_util']
        power = first_row['power']
        mem_capacity = 64
        mem_size = 256
        
        # 计算总和指标
        total_instructions = group['instructions'].sum()
        total_cycles = group['cycles'].sum()
        total_L1_misses = group['L1-misses'].sum()
        total_ll_misses = group['ll-misses/'].sum()
        
        # 计算CPI和MPKI
        cpi = total_cycles / total_instructions if total_instructions > 0 else 0
        mpki = (total_L1_misses + total_ll_misses) / (total_instructions / 1000) if total_instructions > 0 else 0
        
        # 添加聚合行
        aggregated_rows.append({
            'duration': duration,
            'cpu_util': cpu_util,
            'mem_util': mem_util,
            'CPI': cpi,
            'MPKI': mpki,
            'disk_util': disk_util,
            'power': power,
            'mem_capacity': mem_capacity,
            'mem_size': mem_size,
            'instruction': total_instructions
        })
    
    # 创建聚合后的DataFrame
    return pd.DataFrame(aggregated_rows)

def generate_aggregation_report(result_dir, timestamps):
    """生成聚合结果总报告"""
    # 生成 block_aggr.csv
    block_aggr_path = os.path.join(result_dir, 'block_aggr.csv')
    aggr_dir = os.path.join(result_dir, 'final_result')
    
    with open(block_aggr_path, 'w', newline='') as f_out:
        writer = csv.writer(f_out)
        writer.writerow([
            'workload', 'param_set', 'start', 'end', 'duration', 
            'cpu_util', 'mem_util', 'disk_util',
            'cycles_sum', 'instructions_sum',
            'L1-misses_sum', 'll-misses_sum', 'power_sum','CPI','MPKI'
        ])
        
        for idx, (workload, param_set, start, end, duration) in enumerate(timestamps):
            aggr_file = os.path.join(aggr_dir, f'aggr_{idx}.csv')
            values = extract_aggr_values(aggr_file)
            writer.writerow([
                workload, param_set, start, end, duration, 
                values[0], values[1], values[2],
                values[3], values[4], values[5], values[6], values[7], values[8], values[9]
            ])
    
    # 生成 final_aggregations.csv
    final_aggr_path = os.path.join(result_dir, 'final_aggregations.csv')
    all_final = []
    
    for idx in range(len(timestamps)):
        aggr_file = os.path.join(aggr_dir, f'aggr_{idx}.csv')
        if os.path.exists(aggr_file):
            df = pd.read_csv(aggr_file)
            final_row = df[df['aggr_type'] == 'final']
            if not final_row.empty:
                final_row = final_row.iloc[0].to_dict()
                final_row['duration'] = timestamps[idx][4]
                all_final.append(final_row)
    if all_final:
        final_df = pd.DataFrame(all_final)
        # 格式化数值列
        int_cols = ['cycles', 'instructions', 'L1-misses', 'll-misses/', 'duration']
        float_cols = ['cpu_util', 'mem_util', 'CPI', 'MPKI', 'MPKI_L1', 'disk_util']
        for col in int_cols:
            if col in final_df:
                final_df[col] = final_df[col].fillna(0).astype(int)
        for col in float_cols:
            if col in final_df:
                final_df[col] = final_df[col].round(3)
        final_df.to_csv(final_aggr_path, index=False)

def generate_quality_report(result_dir, missing_reports, zero_reports):
    """生成数据质量报告"""
    report_path = os.path.join(result_dir, 'data_quality_report.txt')
    
    with open(report_path, 'w', encoding='utf-8') as f:
        # 时间连续性报告
        f.write("=== 时间连续性检查 ===\n\n")
        if not missing_reports:
            f.write("所有时间序列完整，无缺失时间点\n\n")
        else:
            for file_path, missing in missing_reports:
                f.write(f"文件: {file_path}\n")
                if not missing:
                    f.write("  时间序列完整\n")
                    continue
                
                # 分组显示连续缺失
                groups = []
                current_group = [missing[0]]
                for t in missing[1:]:
                    if t == current_group[-1] + 1:
                        current_group.append(t)
                    else:
                        groups.append(current_group)
                        current_group = [t]
                groups.append(current_group)
                
                for group in groups:
                    if len(group) == 1:
                        f.write(f"  缺失时间点: {group[0]}\n")
                    else:
                        f.write(f"  连续缺失从 {group[0]} 到 {group[-1]} (共{len(group)}个)\n")
                f.write("\n")
        
        # 零值报告
        f.write("\n=== 零值检测报告 ===\n\n")
        if not zero_reports:
            f.write("未检测到关键指标零值\n")
        else:
            for file_path, issues in zero_reports:
                f.write(f"文件: {file_path}\n")
                for col, records in issues:
                    f.write(f"  列: {col}\n")
                    for record in records[:3]:  # 显示前3个零值记录
                        f.write(f"    时间: {record['time']}  值: {record[col]:.4f}\n")
                    if len(records) > 3:
                        f.write(f"    ...(共{len(records)}个零值)\n")
                f.write("\n")
def extract_final_rows(result_dir):
    final_result_dir = os.path.join(result_dir, 'final_result')
    
    # 读取时间记录文件以获取duration
    timestamp_file = os.path.join(result_dir, 'time_record/time_record.csv')
    durations = []
    try:
        with open(timestamp_file, 'r') as f:
            reader = csv.reader(f)
            next(reader)  # 跳过表头
            for row in reader:
                start = int(row[2])
                end = int(row[3])
                duration = end - start
                durations.append(duration)
    except Exception as e:
        print(f"读取时间记录文件失败: {e}")
        return

    # 获取所有aggr文件并按数字顺序排序
    aggr_files = sorted(
        [f for f in os.listdir(final_result_dir) if f.startswith('aggr_') and f.endswith('.csv')],
        key=lambda x: int(x.split('_')[1].split('.')[0])
    )
    
    final_rows = []
    for idx, aggr_file in enumerate(aggr_files):
        file_path = os.path.join(final_result_dir, aggr_file)
        df = pd.read_csv(file_path)
        # 提取final行
        final_row = df[df['aggr_type'] == 'final']
        if not final_row.empty:
            # 添加duration列（根据文件顺序匹配时间记录）
            duration_value = durations[idx] if idx < len(durations) else 0
            final_row = final_row.copy()  # 避免SettingWithCopyWarning
            final_row['duration'] = duration_value
            final_rows.append(final_row)
    
    if final_rows:
        combined_final = pd.concat(final_rows, ignore_index=True)
        
        # ========== 新增格式化逻辑 ==========
        # 定义需要转换为整数的列
        integer_columns = [
            'cycles', 'instructions', 
            'L1-misses', 'll-misses/',
            'duration'
        ]
        
        # 定义需要保留2位小数的列
        float_columns = [
            'cpu_util', 'mem_util', 
            'CPI', 'MPKI', 'MPKI_L1','disk_util',
            'rMB/s', 'wMB/s', 
            'branch-misses-ratio'
        ]
        
        # 过滤实际存在的列
        existing_int_cols = [col for col in integer_columns if col in combined_final.columns]
        existing_float_cols = [col for col in float_columns if col in combined_final.columns]
        
        # 转换整数类型
        for col in existing_int_cols:
            combined_final[col] = combined_final[col].fillna(0).astype(int)
        
        # 保留两位小数
        for col in existing_float_cols:
            combined_final[col] = combined_final[col].round(3)
        # ========== 格式化结束 ==========
        
        # 生成输出文件名（放在result_dir下）
        output_file = os.path.join(result_dir, 'final_aggregations.csv')
        combined_final.to_csv(output_file, index=False)
        print(f"Final行已保存到: {output_file}")
    else:
        print("未找到任何final行数据")



def extract_aggr_values(aggr_filepath):
    """从aggr文件中提取sum行的特定列值"""
    sum_values = {
        'cycles': 'N/A',
        'instructions': 'N/A',
        'L1-misses': 'N/A',
        'll-misses/': 'N/A'
    }
    mean_values = {
        'cpu_util_mean': 'N/A',
        'mem_util_mean': 'N/A',
        'disk_util_mean': 'N/A'
    }
    if os.path.exists(aggr_filepath):
        try:
            with open(aggr_filepath, 'r') as f_aggr:
                reader = csv.DictReader(f_aggr)
                for row in reader:
                    aggr_type = row.get('aggr_type', '')
                    if aggr_type == 'sum':
                        # 提取性能指标
                        sum_values['cycles'] = float(row.get('cycles', 0))
                        sum_values['instructions'] = float(row.get('instructions', 0))
                        sum_values['L1-misses'] = float(row.get('L1-misses', 0))
                        sum_values['ll-misses/'] = float(row.get('ll-misses/', 0))
                        sum_values['power'] = row.get('power', 'N/A')
                    elif aggr_type == 'mean':
                        # 提取资源利用率
                        mean_values['cpu_util_mean'] = row.get('cpu_util', 'N/A')
                        mean_values['mem_util_mean'] = row.get('mem_util', 'N/A')
                        mean_values['disk_util_mean'] = row.get('disk_util', 'N/A')
                        
        except Exception as e:
            print(f"处理文件 {aggr_filepath} 时出错: {e}")
    return (
        mean_values['cpu_util_mean'],
        mean_values['mem_util_mean'],
        mean_values['disk_util_mean'],
        sum_values['cycles'],
        sum_values['instructions'],
        sum_values['L1-misses'],
        sum_values['ll-misses/'],
        sum_values['power'],
        int(sum_values['cycles'])/int(sum_values['instructions']),
        int(sum_values['ll-misses/'])*1000/int(sum_values['instructions'])
    )


if __name__ == "__main__":
    result_dir = '../result/20250606-171221/'
    filter_performance_data(result_dir)
