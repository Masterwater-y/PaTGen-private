import signal
import subprocess
import csv
import os
import re
import sys
import time
import traceback
from configparser import ConfigParser
from multiprocessing import Pool
from datetime import datetime
from align import filter_performance_data
from memory_analysis import MPKI_analysis
import json
# 获取当前文件所在目录
dir_path = os.path.dirname(os.path.realpath(__file__))
parent_dir_path = os.path.abspath(os.path.join(dir_path, os.pardir))

sys.path.insert(0, parent_dir_path)

from collectors.center.center_api import CenterWorker

def save_json(file_path,data):
    try:
        with open(file_path, 'w') as file:
            json.dump(data, file, indent=4)
    except FileNotFoundError:
        print("错误: 文件未找到!")
    except json.JSONDecodeError:
        print("错误: 无法解析 JSON 文件!")
    except Exception as e:
        print(f"错误: 发生了一个未知错误: {e}")

def assembly_prestart(data):
    params={
        "global":{
            "memory_util":data[-1],
            "memory_size":data[-2]
        },
        "blocks":[]
    }
    block_num = len(data)-2
    for i in range(block_num):
        block = data[i]

        if block[1]=='mem':
            block_type = 'memory_block'
            iters = block[2]
            stride = block[3]
            params["blocks"].append({
                "type" :block_type,
                "iterations" : iters,
                "stride" : stride
            })
        elif block[1]=='add':
            block_type = 'add_block'
            iters = block[2]
            params["blocks"].append({
                "type" :block_type,
                "iterations" : iters,
            })
        elif block[1]=='div':
            block_type = 'div_block'
            iters = block[2]
            params["blocks"].append({
                "type" :block_type,
                "iterations" : iters,
            })
        elif block[1]=='sleep':
            block_type = 'sleep_block'
            iters = block[2]
            params["blocks"].append({
                "type" :block_type,
                "iterations" : iters,
            })
        elif block[1]=='disk':
            block_type = 'disk_block'
            iters = block[2]
            params["blocks"].append({
                "type" :block_type,
                "iterations" : iters,
            })
        params["blocks"][-1]["rank"] = block[0]

    config_path = './workloads/assembly/config_files/config.json'

    save_json(config_path,params)
# 要执行的命令及对应的工作负载名称
workloads = [
    {
        "name":"assembly",
        "prestart":assembly_prestart,
        "command": f"cd {dir_path}/workloads/assembly; ./main  ./config_files/config.json"
    }
]


def get_templates(file_path):
    # 打开 CSV 文件
    with open(file_path, 'r') as file:
        reader = csv.DictReader(file)
        generated_template_list = []
        for row in reader:
            generated_template = row['generated_template']
            try:
                template_obj = eval(generated_template)
                generated_template_list.append(template_obj)
            except SyntaxError:
                print(f"无法解析 generated_template: {generated_template}")
    return generated_template_list

def calculate_absolute_similarity(result_val, target_val, max_range=100):
    abs_error = abs(result_val - target_val)
    similarity = 1.0 - (abs_error / max_range)
    return max(0.0, similarity)

def calculate_relative_similarity(result_val, target_val):
    if target_val == 0:
        return 1.0 if result_val == 0 else 0.0
    return max(0.0, 1.0 - abs(result_val - target_val) / abs(target_val))

def evaluate(comparison_type, result_dir, target_dir, range=None):
    # Define mappings for each comparison type
    mappings = {
        'target_actual': {
            "T_total_target": ("T_total_actual", None, "relative"),
            "cpu_util_target": ("cpu_util_actual", None, "absolute"),
            "disk_io_target": ("disk_io_actual", None, "absolute"),
            "cpi_target": ("cpi_actual", None, "relative"),
            "mpki_target": ("mpki_actual", None, "relative"),
            "power_target": ("power_actual", None, "relative"),
        },
        'actual_final': {
            "T_total_actual": ("duration", lambda x, td, rd: int(float(x)), "relative"),
            "cpu_util_actual": ("cpu_util", lambda x, td, rd: x * 100, "absolute"),
            "disk_io_actual": ("util", lambda x, td, rd: x * 100, "absolute"),
            "cpi_actual": ("CPI", None, "relative"),
            "mpki_actual": ("MPKI", None, "relative"),
            "power_actual": ("power", None, "relative"),
        },
        'target_final': {
            "T_total_target": ("duration", lambda x, td, rd: int(float(x)), "relative"),
            "cpu_util_target": ("cpu_util", lambda x, td, rd: x * 100, "absolute"),
            "mem_util_target": ("mem_util", lambda x, td, rd: (x * float(td['mem_capacity']) / float(td['mem_size'])) * 100, "absolute"),
            "disk_io_target": ("util", lambda x, td, rd: x * 100, "absolute"),
            "cpi_target": ("CPI", None, "relative"),
            "mpki_target": ("MPKI", None, "relative"),
            "power_target": ("power", None, "relative"),
        }
    }
    mapping = mappings[comparison_type]
    
    # Determine file paths
    if comparison_type == 'target_actual':
        result_file = os.path.join(target_dir, 'results.csv')
        target_file = result_file
    else:
        result_file = os.path.join(result_dir, 'final_aggregations.csv')
        target_file = os.path.join(target_dir, 'results.csv')

    # Read data
    with open(target_file, 'r') as f:
        target_reader = csv.reader(f)
        target_headers = next(target_reader)
        target_rows = list(target_reader)
    
    if comparison_type == 'target_actual':
        result_rows = target_rows
        result_headers = target_headers
    else:
        with open(result_file, 'r') as f:
            result_reader = csv.reader(f)
            result_headers = next(result_reader)
            result_rows = list(result_reader)

    # Apply range
    if range is not None:
        start, end = range
        target_rows = target_rows[start:end]
        result_rows = result_rows[start:end] if comparison_type == 'target_actual' else result_rows[:len(target_rows)]

    # Prepare data dictionaries
    target_data_list = []
    result_data_list = []
    for t_row, r_row in zip(target_rows, result_rows):
        target_data = dict(zip(target_headers, t_row))
        if comparison_type == 'target_actual':
            result_data = dict(zip(result_headers, r_row))
        else:
            result_data = dict(zip(result_headers, r_row))
        target_data_list.append(target_data)
        result_data_list.append(result_data)

    # Calculate similarities
    output_headers = ["Row"] + [f"{col}_sim" for col in mapping.keys()] + ["Overall"]
    output_rows = []
    stats = {col: {"sum": 0, "count": 0} for col in mapping}
    overall_sum = 0

    for idx, (target_data, result_data) in enumerate(zip(target_data_list, result_data_list)):
        similarities = {}
        for target_col, (result_col, convert, error_type) in mapping.items():
            try:
                t_val = float(target_data[target_col])
                r_val = result_data[result_col]
                if convert:
                    r_val = convert(float(r_val), target_data, result_data)
                else:
                    r_val = float(r_val)

                if error_type == 'absolute':
                    sim = calculate_absolute_similarity(r_val, t_val)
                else:
                    sim = calculate_relative_similarity(r_val, t_val)
                similarities[target_col] = round(sim, 4)
                stats[target_col]["sum"] += sim
                stats[target_col]["count"] += 1
            except (KeyError, ValueError):
                similarities[target_col] = "N/A"
        
        valid_sims = [v for v in similarities.values() if isinstance(v, float)]

        overall = sum(valid_sims) / len(valid_sims) if valid_sims else 0
        overall_sum += overall
        output_rows.append({
            "Row": idx + 1,
            **{f"{k}_sim": v for k, v in similarities.items()},
            "Overall": round(overall, 4)
        })

    # Add averages
    avg_row = {"Row": "Average"}
    for col in mapping:
        avg = stats[col]["sum"] / stats[col]["count"] if stats[col]["count"] else "N/A"
        avg_row[f"{col}_sim"] = round(avg, 4) if isinstance(avg, float) else avg
    avg_row["Overall"] = round(overall_sum / len(target_data_list), 4)
    output_rows.append(avg_row)

    # Write output
    output_file = f"{result_dir}/similarity_{comparison_type}.csv"
    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=output_headers)
        writer.writeheader()
        writer.writerows(output_rows)
    print(f"Results saved to {output_file}")


# 定义一个函数来执行命令
def run_command(command):
    try:
        # 执行命令
        subprocess.run(command, shell=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Command '{command}' failed with error: {e}")
        return False

# 用于存储所有工作负载的时间信息
all_time_info = []
running_workloads = ['assembly']
workloads_param = {

    }
tmp = get_templates('./generate/results.csv')

#range = []
workloads_param['assembly'] = tmp



current_time_str = datetime.now().strftime("%Y%m%d-%H%M%S")
result_dir = os.path.join('result', current_time_str)
target_dir = os.path.join('generate')
perf_dir = os.path.join(result_dir, 'perf')
time_record_dir = os.path.join(result_dir, 'time_record')
'''evaluate('target_actual','result/20250412-010825',target_dir)
evaluate('actual_final','result/20250412-010825',target_dir)
evaluate('target_final','result/20250412-010825',target_dir)
sys.exit()'''
# 创建必要的目录
for dir in [result_dir, perf_dir, time_record_dir]:
    if not os.path.exists(dir):
        os.makedirs(dir)
# 初始化时间记录文件
time_record_file = os.path.join(time_record_dir, 'time_record.csv')
if not os.path.exists(time_record_file):
    with open(time_record_file, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Workload", "Param Set", "Start Time", "End Time", "Duration"])



# 切换到当前文件所在目录
os.chdir(os.path.dirname(os.path.realpath(__file__)))

# 读取配置文件
config = ConfigParser()
config.read('conf/global.conf', encoding='utf-8')

# 初始化中心工作器
center = CenterWorker()

# 热身等待
time.sleep(40)
print('warm up finish')

# 配置收集器
center.m_center_collector.config_collectors({"ibmc_collector": 0, "tau_collector": 0, "slurm_collector": 0})

# 启动中心收集器
center.start_center_collector()
# 遍历每个工作负载
timing_log_path = os.path.join('workloads', 'assembly', 'execution_timing.log')
for workload in workloads:
    workload_name = workload["name"]
    if not workload_name in running_workloads:
        continue

    for param_set in workloads_param.get(workload_name, []):
        rank = param_set[0]
        prestart=workload.get('prestart',None)
        if prestart:
            prestart(param_set)
        # 获取可用核心列表（示例使用0~N-1逻辑核心）

        cmd=workload["command"].format(param_set[0])

        # 记录并输出启动时间
        start_time = int(time.time())
        start_str = datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')

        print(f"   Start Time: {start_str}")
        
        try:
            # 使用Pool执行不同的绑定命令
            #with Pool(processes=rank) as pool:
            #    results = pool.map(run_command, commands)
            run_command(cmd)

        except Exception as e:
            print(f"❗ Error running {workload_name}: {str(e)}")
            continue
        
        end_time = int(time.time())
        if os.path.exists(timing_log_path):
            try:
                with open(timing_log_path, 'r') as f:
                    lines = f.read().splitlines()
                    if len(lines) >= 2:
                        # 转换时间戳为整数
                        start_time = int(lines[0].strip())
                        end_time = int(lines[1].strip())
                        print(f"使用日志文件时间戳 | 开始: {start_time} | 结束: {end_time}")
                    else:
                        print("⚠️ 日志文件格式不正确，使用默认时间")
            except ValueError as ve:
                print(f"⛔ 时间戳转换失败: {ve}，使用默认时间")
            except Exception as e:
                print(f"⛔ 读取日志文件失败: {e}，使用默认时间")
        else:
            print("ℹ️ 未找到时间日志文件，使用命令执行时间")
        duration = end_time - start_time
        time_info = [workload_name, param_set, start_time, end_time, duration]
        with open(time_record_file, 'a', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(time_info)
        all_time_info.append(time_info)
        time.sleep(1)

# 创建必要的目录
for dir in [result_dir, perf_dir, time_record_dir]:
    if not os.path.exists(dir):
        os.makedirs(dir)

# 写入 time_record 相关文件
time_record_file = os.path.join(time_record_dir, 'time_record.csv')
time_record_history_file = os.path.join(time_record_dir, 'time_record_history.csv')

with open(time_record_file, 'w', newline='') as csvfile:
    writer = csv.writer(csvfile)
    # 写入表头，包含持续时间列
    writer.writerow(["Workload", "Param Set", "Start Time", "End Time", "Duration"])
    for info in all_time_info:
        writer.writerow(info)

try:
    print(center.pull_node_data())
    nodes2df = center.get_node_data()
    for name, df in nodes2df.items():
        # 保存 perf 结果
        perf_file = os.path.join(perf_dir, f'perf_{name}.csv')
        df.to_csv(perf_file, index=False)

    center.stop()
except:
    print(traceback.print_exc())
    center.stop()
    exit(0)
print('start alignment')
filter_performance_data(result_dir)
evaluate('target_actual',result_dir,target_dir)
evaluate('actual_final',result_dir,target_dir)
evaluate('target_final',result_dir,target_dir)
#MPKI_analysis(result_dir)
