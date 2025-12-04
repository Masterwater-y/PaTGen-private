import os
import pandas as pd
import csv

CACHE_COL='L1-dcache-load-misses'

def calculate_metrics(data):
    new_data = pd.DataFrame()
    try:
        # 检查必要列是否存在
        required_columns = ['time','cpu_idle', 'MemAvailable', 'MemTotal', 'cycles', 'instructions',
                            'L1-dcache-load-misses', 'util', 'rMB/s', 'wMB/s',
                            'branch-misses', 'branches','armv8_pmuv3_0/ll_cache_miss/']
        for col in required_columns:
            if col not in data.columns:
                raise KeyError(f"数据中缺少必要的列: {col}")

        #cache_col='armv8_pmuv3_0/ll_cache_miss/'

        # 计算各项指标
        new_data['time'] = data['time']
        new_data['cpu_util'] = 1 - data['cpu_idle']
        new_data['mem_util'] = 1 - data['MemAvailable'].div(data['MemTotal'], fill_value=1)
        new_data['cycles'] = data['cycles']
        new_data['instructions'] = data['instructions']
        new_data['L1-misses'] = data['L1-dcache-load-misses']
        new_data['ll-misses/'] = data['armv8_pmuv3_0/ll_cache_miss/']
        new_data['CPI'] = data['cycles'].div(data['instructions'], fill_value=1)
        new_data['MPKI'] = (data['armv8_pmuv3_0/ll_cache_miss/'] * 1000).div(data['instructions'], fill_value=1)
        new_data['MPKI_L1'] = (data['L1-dcache-load-misses'] * 1000).div(data['instructions'], fill_value=1)
        new_data['util'] = data['util']
        new_data['rMB/s'] = data['rMB/s']
        new_data['wMB/s'] = data['wMB/s']
        new_data['branch-misses-ratio'] = data['branch-misses'].div(data['branches'], fill_value=1)

        # 验证计算结果，处理无穷大或 NaN 值
        for col in new_data.columns:
            new_data[col] = new_data[col].replace([float('inf'), float('-inf')], 0)
            new_data[col] = new_data[col].fillna(0)

        # 计算聚合值
        aggregations = new_data.agg(['max', 'min', 'mean', 'median', 'sum'])

        # 添加final行
        sum_cycles = aggregations.loc['sum', 'cycles']
        sum_instructions = aggregations.loc['sum', 'instructions']
        sum_L1_misses = aggregations.loc['sum', 'L1-misses']
        sum_ll_misses = aggregations.loc['sum', 'll-misses/']

        # 处理除零情况
        sum_instructions = sum_instructions if sum_instructions != 0 else 1e-10
        final_cpi = sum_cycles / sum_instructions
        final_mpki_l1 = sum_L1_misses * 1000 / sum_instructions
        final_mpki = (sum_ll_misses * 1000) / sum_instructions

        # 创建final行，其他列使用mean值
        final_row = aggregations.loc['mean'].copy()
        final_row['cycles'] = sum_cycles 
        final_row['instructions'] = sum_instructions 
        final_row['L1-misses'] = sum_L1_misses 
        final_row['ll-misses/'] = sum_ll_misses 
        final_row['CPI'] = final_cpi
        final_row['MPKI'] = final_mpki
        final_row['MPKI_L1'] = final_mpki_l1
        # 将final行添加到aggregations
        final_df = pd.DataFrame([final_row], index=['final'])
        aggregations = pd.concat([aggregations, final_df])

        return new_data, aggregations

    except KeyError as e:
        print(e)
        return None, None
    except Exception as e:
        print(f"计算指标时出现错误: {e}")
        return None, None


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
                        sum_values['cycles'] = row.get('cycles', 'N/A')
                        sum_values['instructions'] = row.get('instructions', 'N/A')
                        sum_values['L1-misses'] = row.get('L1-misses', 'N/A')
                        sum_values['ll-misses/'] = row.get('ll-misses/', 'N/A')
                    elif aggr_type == 'mean':
                        # 提取资源利用率
                        mean_values['cpu_util_mean'] = row.get('cpu_util', 'N/A')
                        mean_values['mem_util_mean'] = row.get('mem_util', 'N/A')
                        mean_values['disk_util_mean'] = row.get('util', 'N/A')
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
    )


def fill_zero_with_previous(df, columns):
    """用前向填充处理零值，初始零值用后向填充"""
    df_filled = df.copy().sort_values('time')
    for col in columns:
        if col not in df_filled.columns:
            continue
        # 前向填充
        df_filled[col] = df_filled[col].replace(0, pd.NA).ffill()
        # 后向填充处理初始零值
        df_filled[col] = df_filled[col].bfill().fillna(0)
    return df_filled
def check_missing_times(metric_file):
    """检查metric文件的time列是否有缺失的时间点，返回缺失的列表"""
    try:
        df = pd.read_csv(metric_file)
        if 'time' not in df.columns:
            print(f"文件 {metric_file} 中缺少'time'列")
            return []
        times = df['time'].dropna().astype(int).unique()
        times = sorted(times)
        missing = []
        for i in range(1, len(times)):
            prev = times[i-1]
            current = times[i]
            if current - prev > 1:
                # 记录中间所有缺失的时间
                for t in range(prev + 1, current):
                    missing.append(t)
        return missing
    except Exception as e:
        print(f"检查文件 {metric_file} 时出错: {e}")
        return []
    
def check_zero_values(df, check_columns):
    """检查DataFrame中指定列是否存在0值，返回包含问题的行信息"""
    zero_rows = []
    if df.empty:
        return zero_rows
    for col in check_columns:
        if col not in df.columns:
            continue
        print(col)
        zero_mask = df[col] == 0
        zero_indices = df.index[zero_mask].tolist()
        if zero_indices:
            problematic = df.loc[zero_indices, ['time', col]].to_dict('records')
            zero_rows.append( (col, problematic) )
    print(zero_rows)
    return zero_rows

def filter_performance_data(result_dir):
    timestamp_file = os.path.join(result_dir, 'time_record/time_record.csv')  # 时间戳 CSV 文件
    performance_file = os.path.join(result_dir, 'perf/perf_200.csv')  # 性能数据 CSV 文件
    timestamp_data = []
    with open(timestamp_file, mode='r') as csv_file:
        csv_reader = csv.reader(csv_file)
        next(csv_reader)  # 跳过表头
        for row in csv_reader:
            workload_name = row[0]
            param_set = row[1]
            start, end = int(row[2]), int(row[3])
            timestamp_data.append((workload_name, param_set, start, end))

    performance_df = pd.read_csv(performance_file)
    idx = -1
    missing_reports = []  
    zero_value_reports = []  # 新增：收集零值问题
    check_columns = [
        'cpu_util', 'mem_util', 
        'cycles', 'instructions', 
        'L1-dcache-load-misses', 
        'armv8_pmuv3_0/ll_cache_miss/'
    ]
    for workload_name, param_set, start, end in timestamp_data:
        idx += 1
        metric_file = os.path.join(result_dir, f'final_result/metric_{idx}.csv')
        perf_file = os.path.join(result_dir, f'final_result/perf_{idx}.csv')
        aggr_file = os.path.join(result_dir, f'final_result/aggr_{idx}.csv')
        # 根据时间范围筛选数据
        filtered_data = performance_df[(performance_df.iloc[:, 0] >= start) & (performance_df.iloc[:, 0] <= end)]
        print(filtered_data.head)
         # 新增零值检测
        zero_issues = check_zero_values(filtered_data, check_columns)
        if zero_issues:
            zero_value_reports.append( (perf_file, zero_issues) )
        
        # 继续执行原有填充逻辑
        #filtered_data = fill_zero_with_previous(filtered_data, columns=check_columns)
        
    
        if not filtered_data.empty:
            filtered_data = filtered_data.iloc[1:]
            # 计算指标
            metrics_data, aggr_data = calculate_metrics(filtered_data)
            if metrics_data is not None:
                # 检查保存路径是否存在，如果不存在则创建
                output_dir = os.path.dirname(metric_file)
                if not os.path.exists(output_dir):
                    os.makedirs(output_dir)

                try:
                    filtered_data.to_csv(perf_file, index=False)
                    metrics_data.to_csv(metric_file, index=False)
                    # 重置索引并添加标识列
                    aggr_data = aggr_data.reset_index().rename(columns={'index': 'aggr_type'})
                    aggr_data.to_csv(aggr_file, index=False)
                    print(f"数据已成功保存到 {metric_file}")       
                except Exception as e:
                    print(f"保存数据时出现错误: {e}")



    # 生成 block_aggr.csv
    output_path = os.path.join(result_dir, 'block_aggr.csv')
    aggr_dir = os.path.join(result_dir, 'final_result')
    if not os.path.exists(timestamp_file):
        print(f"错误：找不到文件 {timestamp_file}")
        return

    with open(timestamp_file, 'r') as f_in, open(output_path, 'w', newline='') as f_out:
        reader = csv.reader(f_in)
        writer = csv.writer(f_out)
        
        headers = next(reader)
        new_headers = headers + ['cpu_util','mem_util','disk_util','cycles_sum', 'instructions_sum', 'L1-misses_sum', 'll-misses_sum']
        writer.writerow(new_headers)
        idx=-1
        for row in reader:
            idx+=1
            aggr_filename = f"aggr_{idx}.csv"
            aggr_filepath = os.path.join(aggr_dir, aggr_filename)
            
            aggr_values = extract_aggr_values(aggr_filepath)
            new_row = row + list(aggr_values)
            writer.writerow(new_row)
    extract_final_rows(result_dir)
    print(f"聚合数据已保存到: {output_path}")
    

    report_path = os.path.join(result_dir, 'data_quality_report.txt')
    try:
        with open(report_path, 'w', encoding='utf-8') as f_report:
            # 1. 时间戳缺失报告
            f_report.write("=== 时间戳连续性检查 ===\n\n")
            if missing_reports:
                for file_path, missing in missing_reports:
                    f_report.write(f"文件: {file_path}\n")
                    with open(report_path, 'w', encoding='utf-8') as f_report:
                        # 1. 时间戳缺失报告
                        f_report.write("=== 时间戳连续性检查 ===\n\n")
                        if missing_reports:
                            for file_path, missing in missing_reports:
                                f_report.write(f"文件: {file_path}\n")
                                if not missing:
                                    f_report.write("  无时间戳缺失\n")
                                    continue
                                # --- 分组逻辑开始 ---
                                missing_sorted = sorted(missing)
                                groups = []
                                current_group = [missing_sorted[0]]
                                for t in missing_sorted[1:]:
                                    if t == current_group[-1] + 1:
                                        current_group.append(t)
                                    else:
                                        groups.append(current_group)
                                        current_group = [t]
                                groups.append(current_group)
                                # --- 分组逻辑结束 ---
                                # 写入分组结果
                                for group in groups:
                                    if len(group) == 1:
                                        f_report.write(f"  缺失时间点: {group[0]}\n")
                                    else:
                                        f_report.write(f"  缺失时间点从 {group[0]} 到 {group[-1]}（共 {len(group)} 个）\n")
                                f_report.write("\n")  # 文件间空行
                        else:
                            f_report.write("所有文件的时间戳连续，无缺失。\n")
                        f_report.write("\n" + "="*40 + "\n\n")
            else:
                f_report.write("所有文件的时间戳连续，无缺失。\n")
            f_report.write("\n" + "="*40 + "\n\n")

            # 2. 零值问题报告
            f_report.write("=== 关键指标零值检查 ===\n\n")
            if zero_value_reports:
                for file_path, issues in zero_value_reports:
                    f_report.write(f"文件: {file_path}\n")
                    for col, rows in issues:
                        f_report.write(f"  列名: {col}\n")
                        for row in rows:
                            time = row.get('time', 'N/A')
                            value = row.get(col, 'N/A')
                            f_report.write(f"    时间: {time} | 值: {value}\n")
                    f_report.write("\n")  # 文件间空行
            else:
                f_report.write("所有关键指标列未发现零值。\n")
                
        print(f"\n数据质量报告已保存到: {report_path}")
    except Exception as e:
        print(f"\n写入报告文件时出错: {e}")

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
            'CPI', 'MPKI', 'MPKI_L1','util',
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

if __name__ == "__main__":
    result_dir = './result/20250409-233444/'
    filter_performance_data(result_dir)
