import csv
import os

root_path = 'result/20250322-155747'
time_record_path = f'{root_path}/time_record/time_record.csv'
output_path = f'{root_path}/block_aggr.csv'
aggr_dir = f'{root_path}/final_result'

def extract_aggr_values(aggr_filepath):
    """从aggr文件中提取sum行的性能指标和mean行的资源利用率"""
    # 初始化默认值
    sum_values = {
        'cycles': 'N/A',
        'instructions': 'N/A',
        'L1-misses': 'N/A',
        'll-misses/': 'N/A'
    }
    mean_values = {
        'cpu_util_mean': 'N/A',
        'mem_util_mean': 'N/A'
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
                        mean_values['cpu_util_mean'] = row.get('cpu_util_mean', 'N/A')
                        mean_values['mem_util_mean'] = row.get('mem_util_mean', 'N/A')
        except Exception as e:
            print(f"Error processing {aggr_filepath}: {e}")
    
    return (
        sum_values['cycles'],
        sum_values['instructions'],
        sum_values['L1-misses'],
        sum_values['ll-misses/'],
        mean_values['cpu_util_mean'],
        mean_values['mem_util_mean']
    )

with open(time_record_path, 'r') as f_in, open(output_path, 'w', newline='') as f_out:
    reader = csv.reader(f_in)
    writer = csv.writer(f_out)
    
    # 处理标题行
    headers = next(reader)
    new_headers = headers + [
        'cpu_util_mean',
        'mem_util_mean'
        'cycles_sum',
        'instructions_sum',
        'L1-misses_sum',
        'll-misses_sum',

    ]
    writer.writerow(new_headers)
    
    for row in reader:
        workload = row[0]
        param_set = row[1]
        aggr_filename = f"aggr_{workload}_{param_set}.csv"
        aggr_filepath = os.path.join(aggr_dir, aggr_filename)
        
        # 提取所有指标值
        aggr_values = extract_aggr_values(aggr_filepath)
        
        # 写入新行
        new_row = row + list(aggr_values)
        writer.writerow(new_row)

print("处理完成，结果已保存到:", output_path)
