import os
import csv
import threading
from workload_runner.Runner import Runner
from workload_runner.common import returnTime, run_command, save_json
import pandas as pd

class STWGENRunner(Runner):
    def __init__(self, result_dir = None):
        super().__init__()
        self.mName = 'STWGEN'
        self.mParamSet = None
        self.result_dir = result_dir
        self.input_dir = 'sota/STWGEN/'
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
                cpu_seq = eval(row['cpu_seq'])
                mem_seq = eval(row['mem_seq'])
                param_set = [cpu_seq, mem_seq]
                param_sets.append(param_set)
        return param_sets

    def PreStart(self,param_set):
        cpu_seq = param_set[0]
        mem_seq = param_set[1]
        cpu_path = os.path.join(self.input_dir,'cpu_seq.txt')
        mem_path = os.path.join(self.input_dir,'mem_seq.txt')
        with open(cpu_path, 'w+', encoding='utf-8') as f:
            f.writelines(f"{item}\n" for item in cpu_seq)
        with open(mem_path, 'w+', encoding='utf-8') as f:
            f.writelines(f"{item}\n" for item in mem_seq)
        
    def run_executable(self, workload):
        command = f'cd {os.getcwd()}/sota/STWGEN; ./{workload}_block  ./{workload}_seq.txt'
        run_command(command)
        
    @returnTime    
    def Start(self, param_set):
        threads = []
        for exe in ['cpu','mem']:
            thread = threading.Thread(target=self.run_executable, args=(exe,))
            thread.start()
            threads.append(thread)
    
        for thread in threads:
            thread.join()
    
    def GetWorkloadBeginEndTime(self):
        return None
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
    
