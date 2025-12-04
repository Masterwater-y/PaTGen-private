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

from workload_runner.MyRunner import MyRunner
from workload_runner.STWGENRunner import STWGENRunner
from workload_runner.TracieRunner import TracieRunner
from workload_runner.CloudmixRunner import CloudmixRunner
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
        print(block)
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
    },
    {
        "name":"stwgen",
        "command": f"cd {dir_path}/sota/STWGEN; ./mem_block  ./mem_seq.txt"
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

def evaluate(result_dir, target_dir, range=None):
    # 定义属性映射、单位转换函数及误差类型
    mapping = {
        "T_total": ("duration", lambda x: int(float(x)), "relative"),  # 根据需求调整T_total的误差类型
        "cpu_util_percent": ("cpu_util", lambda x: x * 100, "absolute"),
        "mem_util_percent": ("mem_util", lambda x: x * 100, "absolute"),
        "disk_io_percent": ("util", lambda x: x * 100, "absolute"),
        "cpi": ("CPI", None, "relative"),
        "mpki": ("MPKI", None, "relative")
    }

    def calculate_absolute_similarity(result_val, target_val, max_range=100):
        """计算绝对误差相似度（基于最大范围归一化）"""
        abs_error = abs(result_val - target_val)
        similarity = 1.0 - (abs_error / max_range)
        return max(0.0, similarity)  # 相似度不低于0

    def calculate_relative_similarity(result_val, target_val):
        """计算相对误差相似度"""
        if target_val == 0:
            return 1.0 if result_val == 0 else 0.0
        return max(0.0, 1.0 - abs(result_val - target_val) / abs(target_val))

    result_file = os.path.join(result_dir, 'final_aggregations.csv')
    target_file = os.path.join(target_dir, 'targets.csv')

    # 读取数据
    with open(result_file, "r") as f1, open(target_file, "r") as f2:
        result_reader = csv.reader(f1)
        target_reader = csv.reader(f2)
        result_headers = next(result_reader)
        target_headers = next(target_reader)
        result_rows = list(result_reader)
        target_rows = list(target_reader)

        # 根据range参数选择行
        if range is not None:
            start, end = range
            if start < 0 or end >= len(target_rows) or start > end:
                raise ValueError("Invalid range specified.")
            selected_target_rows = target_rows[start:end]
            required_result_rows = end - start
            if len(result_rows) < required_result_rows:
                raise ValueError("Not enough result rows for the specified range.")
            selected_result_rows = result_rows[:required_result_rows]
        else:
            selected_target_rows = target_rows
            selected_result_rows = result_rows

        if len(selected_result_rows) != len(selected_target_rows):
            raise ValueError("Mismatch in number of result and target rows after applying range.")

        # 准备输出
        output_headers = ["Row"] + [f"{col}_sim" for col in mapping.keys()] + ["Overall"]
        output_rows = []

        # 初始化统计各列相似度总和和计数
        stats = {col: {"sum": 0.0, "count": 0} for col in mapping.keys()}
        overall_sum = 0.0
        overall_count = 0

        # 逐行比较
        for row_idx, (result_row, target_row) in enumerate(zip(selected_result_rows, selected_target_rows)):
            result_data = dict(zip(result_headers, result_row))
            target_data = dict(zip(target_headers, target_row))

            similarities = {}
            for target_col, (result_col, convert_func, error_type) in mapping.items():
                try:
                    raw_result = float(result_data[result_col])
                    result_val = convert_func(raw_result) if convert_func else raw_result
                    target_val = float(target_data[target_col])

                    # 根据误差类型选择计算方法
                    if error_type == "absolute":
                        sim = calculate_absolute_similarity(result_val, target_val)
                    elif error_type == "relative":
                        sim = calculate_relative_similarity(result_val, target_val)
                    else:
                        sim = 0.0  # 默认处理

                    similarities[target_col] = round(sim, 4)
                except (KeyError, ValueError) as e:
                    continue

            # 计算当前行总体相似度
            valid_sims = list(similarities.values())
            overall = round(sum(valid_sims) / len(valid_sims), 4) if valid_sims else 0.0

            # 更新统计信息
            for col, sim in similarities.items():
                stats[col]["sum"] += sim
                stats[col]["count"] += 1
            overall_sum += overall
            overall_count += 1

            # 生成输出行
            row_number = row_idx if range is not None else row_idx + 1
            output_row = {"Row": row_number, "Overall": overall}
            output_row.update({f"{col}_sim": similarities.get(col, "N/A") for col in mapping})
            output_rows.append(output_row)

        # 添加平均值行
        average_row = {"Row": "Average"}
        for col in mapping.keys():
            if stats[col]["count"] > 0:
                avg = stats[col]["sum"] / stats[col]["count"]
                average_row[f"{col}_sim"] = round(avg, 4)
            else:
                average_row[f"{col}_sim"] = "N/A"
        average_row["Overall"] = round(overall_sum / overall_count, 4) if overall_count > 0 else 0.0
        output_rows.append(average_row)

        # 计算平均误差
        avg_errors = {}
        for col in mapping.keys():
            if stats[col]["count"] > 0:
                avg_errors[col] = 1 - stats[col]["sum"] / stats[col]["count"]
            else:
                avg_errors[col] = "N/A"
        overall_avg_error = 1 - (overall_sum / overall_count) if overall_count > 0 else 0.0

        # 添加平均相似度行
        avg_sim_row = {"Row": "avg simularity"}
        for col in mapping.keys():
            avg_sim_row[f"{col}_sim"] = average_row[f"{col}_sim"]
        avg_sim_row["Overall"] = average_row["Overall"]
        output_rows.append(avg_sim_row)

        # 添加平均误差行
        avg_error_row = {"Row": "avg error"}
        for col in mapping.keys():
            if isinstance(avg_errors[col], float):
                avg_error_row[f"{col}_sim"] = round(avg_errors[col], 4)
            else:
                avg_error_row[f"{col}_sim"] = avg_errors[col]
        avg_error_row["Overall"] = round(overall_avg_error, 4)
        output_rows.append(avg_error_row)

    # 写入CSV
    with open("similarity.csv", "w+", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=output_headers)
        writer.writeheader()
        writer.writerows(output_rows)
    print(f"similarity数据已保存到similarity.csv")

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


# 用于存储所有工作负载的时间信息






all_time_info = []
current_time_str = datetime.now().strftime("%Y%m%d-%H%M%S")
result_dir = os.path.join('result', current_time_str)
target_dir = os.path.join('generate')
perf_dir = os.path.join(result_dir, 'perf')
time_record_dir = os.path.join(result_dir, 'time_record')



#runner = STWGENRunner(result_dir = result_dir)
runner = MyRunner(result_dir = result_dir)

param_sets = runner.GetParamSets()
for param_set in param_sets:
    runner.StartAndSaveTime(param_set)
    time.sleep(1)
runner.SaveTimeRecord()


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
runner.FilterPefData()
runner.Evaluate()
#evaluate(result_dir, target_dir)
#MPKI_analysis(result_dir)
