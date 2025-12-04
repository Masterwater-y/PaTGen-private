import os
import csv
import shutil
from workload_runner.Runner import Runner
from workload_runner.common import returnTime, run_command, save_json, smooth_isolated_outliers, stage_divide
import pandas as pd

class CloudmixRunner(Runner):
    def __init__(self, job_dir = None, sample_index = 0):
        super().__init__()
        self.mName = 'phase'
        self.mParamSet = None
        self.job_dir = job_dir
        self.sample_index = sample_index
        self.result_dir = os.path.join(job_dir, f'iter{sample_index}')

        self.input_dir = 'sota/Cloudmix/'
        self.perf_dir = os.path.join(self.result_dir, 'perf')
        self.time_record_dir = os.path.join(self.result_dir, 'time_record')
        self.time_record = []
        self.phase_aware = True
        self.sample_dir = os.path.join(self.input_dir,f'stage{self.sample_index}')
        self.target_path = os.path.join(self.sample_dir,'targets.csv')
        self._create_directories()

    def _create_directories(self):
        """创建所有必要的目录"""
        # 收集需要创建的目录路径
        dirs_to_create = [
            self.job_dir,
            self.result_dir,
            self.perf_dir,
            self.time_record_dir,
            self.sample_dir
        ]
        
        # 过滤掉无效路径并创建目录
        for directory in filter(None, dirs_to_create):
            os.makedirs(directory, exist_ok=True)

    def GetParamSets(self):
        # 打开 CSV 文件
        command = f'cd {os.getcwd()}/{self.input_dir}; python3 generate.py {self.sample_index}'
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

    '''def PreStart(self,param_set): #采集block
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
            elif block[1]=='sqrt':
                block_type = 'sqrt_block'
                iters = block[2]
                params["blocks"].append({
                    "type" :block_type,
                    "iterations" : iters,
                })
            elif block[1]=='ari':
                block_type = 'ari_block'
                iters = block[2]
                factor = block[3]
                params["blocks"].append({
                    "type" :block_type,
                    "iterations" : iters,
                    "factor": factor
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
            params["blocks"][-1]=[params['blocks'][-1]]
        config_path = './workloads/phase/config_files/config.json'

        save_json(config_path,params)'''
    
    def PreStart(self,param_set):
        data = param_set
        print(data)
        params={
            "global":{
                "memory_util":data[-1],
                "memory_size":data[-2]
            },
            "blocks":[]
        }
        group_num = len(data)-2
        for i in range(group_num):
            group = data[i]
            params["blocks"].append([])
            for block in group:
                if block[1]=='mem':
                    block_type = 'memory_block'
                    iters = block[2]
                    stride = block[3]
                    params["blocks"][-1].append({
                        "type" :block_type,
                        "iterations" : iters,
                        "stride" : stride
                    })
                elif block[1]=='add':
                    block_type = 'add_block'
                    iters = block[2]
                    params["blocks"][-1].append({
                        "type" :block_type,
                        "iterations" : iters,
                    })
                elif block[1]=='div':
                    block_type = 'div_block'
                    iters = block[2]
                    params["blocks"][-1].append({
                        "type" :block_type,
                        "iterations" : iters,
                    })
                elif block[1]=='sqrt':
                    block_type = 'sqrt_block'
                    iters = block[2]
                    params["blocks"][-1].append({
                        "type" :block_type,
                        "iterations" : iters,
                    })
                params["blocks"][-1][-1]["delay"] = block[-1]
                params["blocks"][-1][-1]["rank"] = block[0]

        config_path = './workloads/cloudmix/config_files/config.json'

        save_json(config_path,params)
    

    @returnTime    
    def Start(self, param_set):
        command = f'cd {os.getcwd()}/workloads/cloudmix; ./parallel  ./config_files/config.json'
        run_command(command)
    
    def GetWorkloadBeginEndTime(self):
        execute_log = f'{os.getcwd()}/workloads/cloudmix/execution_timing.log'
        phase_log = f'{os.getcwd()}/workloads/cloudmix/phase_time.csv'

        target_dir = os.path.join(self.result_dir, "time_record")
    
        # 创建目标目录（若不存在）
        os.makedirs(target_dir, exist_ok=True)
        
        try:
            target_phase_log = os.path.join(target_dir, "phase_time.csv")
            shutil.copy2(phase_log, target_phase_log)  # 复制并保留元数据
            print(f"已复制时间日志到: {target_phase_log}")
        except Exception as e:
            print(f"❌ 复制文件失败: {e}")
            return None
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
        