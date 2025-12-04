import os
import csv
from workload_runner.Runner import Runner
from workload_runner.common import returnTime, run_command, save_json
import pandas as pd

class MeowRunner(Runner):
    def __init__(self, result_dir = None):
        super().__init__()
        self.mName = 'assembly'
        self.mParamSet = None
        self.result_dir = result_dir
        self.input_dir = 'sota/MINE/'
        self.perf_dir = os.path.join(result_dir, 'perf')
        self.time_record_dir = os.path.join(result_dir, 'time_record')
        self.time_record = []

    def GetParamSets(self):
        # 打开 CSV 文件
        command = f'cd {os.getcwd()}/{self.input_dir}; python3 generate.py'
        run_command(command)
        param_path = os.path.join(self.input_dir, 'param_sets.csv')
        with open(param_path, 'r') as file:
            reader = csv.DictReader(file)
            param_sets = []
            for row in reader:
                param_set = row['param_set']
                try:
                    template_obj = eval(param_set)
                    param_sets.append(template_obj)
                except SyntaxError:
                    print(f"无法解析 generated_template: {param_set}")
        return param_sets

    def PreStart(self,param_set):
        data = param_set
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

    @returnTime    
    def Start(self, param_set):
        command = f'cd {os.getcwd()}/workloads/assembly; ./main  ./config_files/config.json'
        run_command(command)
    
    def GetWorkloadBeginEndTime(self):
        execute_log = f'{os.getcwd()}/workloads/assembly/execution_timing.log'
        flag = False
        if os.path.exists(execute_log):
            try:
                with open(execute_log, 'r') as f:
                    lines = f.read().splitlines()
                    if len(lines) >= 2:
                        # 转换时间戳为整数
                        start_time = int(lines[0].strip())
                        end_time = int(lines[1].strip())
                        flag = True
                        print(f"使用日志文件时间戳 | 开始: {start_time} | 结束: {end_time}")
                        
                    else:
                        print("⚠️ 日志文件格式不正确，使用默认时间")
            except ValueError as ve:
                print(f"⛔ 时间戳转换失败: {ve}，使用默认时间")
            except Exception as e:
                print(f"⛔ 读取日志文件失败: {e}，使用默认时间")
        else:
            print("ℹ️ 未找到时间日志文件，使用命令执行时间")
        if flag:
            return[start_time, end_time]
        else:
            return None
    
    def Evaluate(self):
        targets = {
            "CPI" : 1.5,
            "MPKI": 2.3
        }
        result_path = os.path.join(self.result_dir,'final_aggregations.csv')        
        res_df = pd.read_csv(result_path)
        res = res_df.iloc[-1]

        cpi_value = res['CPI']
        mpki_value = res['MPKI']
        

        cpi_error = abs((cpi_value - targets["CPI"]) / targets["CPI"]) * 100
        mpki_error = abs((mpki_value - targets["MPKI"]) / targets["MPKI"]) * 100
        # 计算综合评分（可根据需求调整权重）


        

        return cpi_error, mpki_error