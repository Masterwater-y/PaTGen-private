import csv

root_path = 'result/20250320-212816'
GROUP_SIZE = 3  # 用户可以在此处修改分组大小

def get_sum_values(filename):
    """读取aggr文件并提取sum行的四个指标值"""
    with open(filename, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['aggr_type'] == 'sum':
                return {
                    'cycles': float(row['cycles']),
                    'instructions': float(row['instructions']),
                    'L1-misses': float(row['L1-misses']),
                    'LL-misses': float(row['ll-misses/'])
                }
        raise ValueError(f"No 'sum' row found in {filename}")

# 读取time_record.csv
with open(f'{root_path}/time_record/time_record.csv', 'r') as f:
    reader = csv.reader(f)
    header = next(reader)  # 跳过标题行
    rows = [row for row in reader if row]  # 忽略空行

# 按指定分组大小进行分组
groups = [rows[i:i+GROUP_SIZE] for i in range(0, len(rows), GROUP_SIZE)]

# 处理每组数据
results = []
for group_idx, group in enumerate(groups):
    if len(group) < GROUP_SIZE:
        print(f"警告: 第 {group_idx+1} 组不足{GROUP_SIZE}行，跳过")
        continue
    
    # 生成文件名
    files = [
        f"{root_path}/final_result/aggr_assembly_{row[1]}.csv"
        for row in group
    ]
    
    try:
        # 读取所有文件的值
        values = [get_sum_values(f) for f in files]
    except Exception as e:
        print(f"处理第 {group_idx+1} 组时出错: {str(e)}")
        continue
    
    # 计算后面所有文件的总和
    sum_others = {metric: 0.0 for metric in ['cycles', 'instructions', 'L1-misses', 'LL-misses']}
    for value in values[1:]:
        for metric in sum_others:
            sum_others[metric] += value[metric]
    
    # 构建结果数据结构
    result = {
        'group': group_idx + 1,
        'files': files,
        'values': {
            metric: {
                'all_values': [v[metric] for v in values],
                'sum_others': sum_others[metric],
                'diff': sum_others[metric] - values[0][metric],
                'error_rate': abs(sum_others[metric] - values[0][metric]) / values[0][metric] * 100 
                    if values[0][metric] != 0 else float('inf')
            } for metric in ['cycles', 'instructions', 'L1-misses', 'LL-misses']
        }
    }
    results.append(result)

# 格式化输出
for res in results:
    print(f"\n{'='*60}")
    print(f"组别 {res['group']}:")
    for i, file in enumerate(res['files'], 1):
        print(f"文件{i}: {file}")
    
    for metric in ['cycles', 'instructions', 'L1-misses', 'LL-misses']:
        data = res['values'][metric]
        print(f"\n{metric.upper()} 分析:")
        print(f"  Base值 (文件1): {data['all_values'][0]:,.2f}")
        
        # 显示后续文件的值
        for idx, value in enumerate(data['all_values'][1:], 2):
            print(f"  文件{idx} 值: {value:,.2f}")
        
        print(f"  其他文件总和: {data['sum_others']:,.2f}")
        print(f"  差值 (总和 - base): {data['diff']:,.2f}")
        if data['error_rate'] == float('inf'):
            print("  误差率: 分母为零（无法计算）")
        else:
            print(f"  误差率: {data['error_rate']:.2f}%")
    print(f"{'='*60}\n")
