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
        elif block[1]=='sqrt':
            block_type = 'sqrt_block'
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
        "name": "sort",
        "command": f"cd {dir_path}/workloads/sort; ./sort ../data/wiki-1G/ ./output"
    },
    {
        "name": "grep",
        "command": f"cd {dir_path}/workloads/grep; ./grep ../data/wiki-20G/ ./output"
    },
    {
        "name": "md5",
        "command": f"cd {dir_path}/workloads/md5; ./md5 ../data/wiki-20G/ ./output"
    },
    {
        "name": "wordcount",
        "command": f"cd {dir_path}/workloads/wordcount; ./wordcount ../data/wiki-1G/"
    },
    {
        "name": "randsample",
        "command": f"cd {dir_path}/workloads/randsample; ./randsample ../data/wiki-20G/ ./output 0.5"
    },
    {
        "name": "io_load",
        "command": f"cd {dir_path}/workloads/io_load; ./io_load {{}} {{}}"
    },
    {
        "name": "memory",
        "command": f"cd {dir_path}/workloads/memory; ./memory  {{}} {{}} {{}}"
    },
    {
        "name": "memory_stride",
        "command": f"cd {dir_path}/workloads/memory; ./memory_stride  {{}} {{}} {{}}"
    },
    {
        "name": "memory_read",
        "command": f"cd {dir_path}/workloads/memory; ./memory_read  {{}} {{}} {{}}"
    },
        {
        "name": "simple_ioload",
        "command": f"cd {dir_path}/workloads/io_load; ./simple_ioload {{}} {{}}"
    },
    {
        "name": "cpi",
        "command": f"cd {dir_path}/workloads/cpu; ./cpi {{}} {{}} {{}}"
    },
     {
        "name": "branch-miss",
        "command": f"cd {dir_path}/workloads/cpu; ./branch-miss {{}}"
    },
         {
        "name": "normal",
        "command": f"cd {dir_path}/workloads/cpu; ./normal {{}}"
    },
         {
        "name": "hazard",
        "command": f"cd {dir_path}/workloads/cpu; ./hazard {{}}"
    },
             {
        "name": "syscall",
        "command": f"cd {dir_path}/workloads/cpu; ./syscall {{}} {{}}"
    },
    {
        "name":"temp",
        "command": f"cd /home/yhl/google-cluster-data; python3 analyze_temp.py"
    },
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


# 在程序开头添加全局变量和信号处理函数
def signal_handler(sig, frame):
    print("\n⚠️ 捕获到终止信号，正在保存性能数据...")
    try:
        print(1)
        center.pull_node_data()
        nodes2df = center.get_node_data()
        print(nodes2df)
        for name, df in nodes2df.items():
            perf_file = os.path.join(perf_dir, f'perf_{name}.csv')

            df.to_csv(perf_file, index=False)
            print(f"✅ 性能数据已保存至 {perf_file} 文件")
        print('start alignment')
        filter_performance_data(result_dir)
    except Exception as e:
        print(f"❌ 保存失败: {str(e)}")
    finally:
        center.stop()
        sys.exit(0)

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
# 注册信号处理（在 main 逻辑前添加）
#signal.signal(signal.SIGINT, signal_handler)
#signal.signal(signal.SIGTERM, signal_handler)
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
#running_workloads = ['grep','md5','wordcount','randsample']
running_workloads = ['assembly']
workloads_param = {
    'io_load':[[1,1024*1024*1024*32,1],[1,1024*1024*1024,32]],
    'sort':[[1],[16],[64]],
    #'sort':[[1],[2],[4]],
    'grep':[[8],[16]],
    'md5':[[1],[16],[64]],
    'wordcount':[[1],[16],[64]],
    'randsample':[[1],[16],[64]],
    'memory':[[1,1024*1024*1024*128,0.0,500000000],[1,1024*1024*1024*128,0.5,500000000],[1,1024*1024*1024*128,1.0,500000000]],
    'memory_stride':[[1,1024*1024*1024*192,1,5000000000],
                     [8,1024*1024*1024*24,1,5000000000],
                     [32,1024*1024*1024*6,1,5000000000],
                     [64,1024*1024*1024*3,1,5000000000],
                     [1,1024*1024*1024*192,64,5000000000],
                     [8,1024*1024*1024*24,64,5000000000],
                     [32,1024*1024*1024*6,64,5000000000],
                     [64,1024*1024*1024*3,64,5000000000],
                     [1,1024*1024*1024*192,4096,5000000000],
                     [8,1024*1024*1024*24,4096,5000000000],
                     [32,1024*1024*1024*6,4096,5000000000],
                     [64,1024*1024*1024*3,4096,5000000000]
                ],
    'memory_read':[[1,1024*1024*1024*16,1,5000000000],[1,1024*1024*1024*16,4,5000000000],[1,1024*1024*1024*16,16,5000000000],[1,1024*1024*1024*16,64,5000000000],[1,1024*1024*1024*16,128,5000000000],[1,1024*1024*1024*16,256,5000000000],[1,1024*1024*1024*16,512,5000000000]],
    'cpi':[[1,10,100,2000000000],[1,10,1000,2000000000],[1,10,10000,2000000000],
           [1,100,1000,2000000000],[1,1000,1000,2000000000],[1,10000,1000,2000000000]],
    'branch-miss':[[1,1],[1,10],[1,100],
                   [64,1],[64,10],[64,100]],

    'normal':[[1,10000000000],[64,10000000000]],
    'hazard':[[1,10000000000],[2,10000000000],[4,10000000000],[16,10000000000],[64,10000000000]],
    'syscall':[[1,200000000,100],[1,200000000,50],[1,200000000,10],
               [16,200000000,100],[16,200000000,50],[16,200000000,10],
               [64,200000000,100],[64,200000000,50],[64,200000000,10],
               [80,200000000,100],[80,200000000,50],[80,200000000,10]],
    'temp':[[1]],

    #'assembly':[[1,'config1.json'],[1,'config2.json'],[1,'config3.json'],
    #            [32,'config1.json'],[32,'config2.json'],[32,'config3.json'],
    #            [64,'config1.json'],[64,'config2.json'],[64,'config3.json']]
    'assembly':[[1,10000000000,0,1,1.0,'config.json']],
    'stwgen':[[0.8]]
    }


ranks = [i+1 for i in range(1,24,2)]
ranks.append(1)
#ranks = [5]
stride = [i+1 for i in range(12)]
mem = [16]
all_iter=[5000000000]



tmp = [
    [[1, 'div', 32587542843], [1, 'add', 117825556051], [1, 'mem', 5125555237, 12], 16, 1]
    #[[1, 'sqrt', 100000000], 16, 1],
    #[[1, 'sqrt', 500000000], 16, 1],
    #[[1, 'sqrt', 1000000000], 16, 1],
    #[[1, 'add', 147874890313], 16, 1],
    #[[1, 'mem', 2918826081, 12], 16, 1],
    #[[1, 'sqrt', 3429432658], [1, 'add', 147874890313], [1, 'mem', 2918826081, 12], 16, 1]
    #[[1, 'div', 28209932937], [1, 'add', 124863692031], [1, 'mem', 3897358567, 12], 16, 1]
    #[[1, 'div', 10000000000], 16, 1],
    #[[1, 'add', 50000000000], 16, 1],

    #[[36, 'mem', 20000000000, 15], 0, 0.3]
    #[[5, 'div', 6309701845], [12, 'div', 2683517856], [24, 'div', 686100761], [24, 'add', 11127839008], [24, 'disk', 576], [24, 'mem', 12385705132, 32], 128, 0.8353980748966142]
    #[[36, 'mem', 5000000000, 1],128,0.5],
    #[[36, 'mem', 5000000000, 4],128,0.5],
    #[[36, 'mem', 5000000000, 1],64,0.5],
    #[[36, 'mem', 5000000000, 2],64,0.5],
    #[[36, 'mem', 5000000000, 4],64,0.5]
]
'''for i0 in ranks:
    tmp.append([[i0, 'sqrt', 1200000000], 16, 1])
for i0 in [1]:
    tmp.append([[i0, 'div', 10000000000], 16, 1])
    tmp.append([[i0, 'add', 50000000000], 16, 1])
    for i1 in stride:
        tmp.append([[i0,'mem',10000000000,i1], 16, 1])'''

#tmp.append([[1, 'div', 500000000, 16],[1, 'mem', 20000000, 4],[1, 'mem', 460000000, 4],8, 1])
#tmp.append([[1, 'div', 5000000000, 16],[1, 'mem', 200000000, 4],[1, 'mem', 4600000000, 4],8, 1])
#tmp.append([[1, 'mem', 2500000000, 16], 16, 0.5])
#tmp.append([[1, 'mem', 2500000000, 16], 32, 0.5])
workloads_param['assembly'] = tmp
'''tmp=[
[1,1024*1024*1024*128,1,5000000000],
                     [1,1024*1024*1024*128,4,5000000000],
                     [1,1024*1024*1024*128,16,5000000000],
]'''
'''for stride in range(64,4160,64):
    tmp.append([1,1024*1024*1024*128,stride,5000000000])'''

'''workloads_param['memory_stride'] = tmp
print(workloads_param['memory_stride'])'''


current_time_str = datetime.now().strftime("%Y%m%d-%H%M%S")
result_dir = os.path.join('result', current_time_str)
target_dir = os.path.join('generate')
perf_dir = os.path.join(result_dir, 'perf')
time_record_dir = os.path.join(result_dir, 'time_record')

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

'''evaluate('result/20250328-005642',target_dir,[15,55])
sys.exit()'''

timing_log_path = os.path.join('workloads', 'assembly', 'execution_timing.log')
# 遍历每个工作负载
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
#evaluate(result_dir, target_dir)
#MPKI_analysis(result_dir)
