import os
import csv
import shutil
from workload_runner.Runner import Runner
from workload_runner.common import returnTime, run_command, save_json
import pandas as pd

class SiestaRunner(Runner):
    def __init__(self, job_dir = None, result_dir = None ,sample_index = 0):
        super().__init__()
        self.mName = 'siesta'
        self.mParamSet = None
        self.job_dir = job_dir
        self.sample_index = sample_index
        self.result_dir = result_dir
        self.input_dir = 'sota/Siesta/'
        self.perf_dir = os.path.join(self.result_dir, 'perf')
        self.time_record_dir = os.path.join(self.result_dir, 'time_record')
        self.time_record = []
        self.phase_aware = True
        if self.sample_index is not None:
            self.sample_dir = os.path.join(self.input_dir,f'stage{self.sample_index}')
            self.target_path = os.path.join(self.sample_dir,'targets.csv')
            self.phase_num = 0

            df_aggr = pd.read_csv(os.path.join(self.sample_dir, 'aggr.csv'))
            self.phase_num = df_aggr.shape[0]

    def GetParamSets(self,scale_factor=1, phase_index=None):

        # 打开 CSV 文件
        if phase_index is not None:
            command = f'cd {os.getcwd()}/{self.input_dir}; python3 generate.py {self.sample_index} {phase_index}'
        else:
            command = f'cd {os.getcwd()}/{self.input_dir}; python3 generate.py {self.sample_index}'
        print(command)
        run_command(command)
        param_path = os.path.join(self.input_dir, 'param_sets.csv')
        with open(param_path, 'r') as file:
            reader = csv.DictReader(file)
            param_sets = []
            for row in reader:
                param_set = row['param_set']
                try:
                    template_obj = eval(param_set)
                    for i in range(len(template_obj)-2):
                        template_obj[i][2]*=scale_factor
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
            elif block[1]=='sqrt':
                block_type = 'sqrt_block'
                iters = block[2]
                params["blocks"].append({
                    "type" :block_type,
                    "iterations" : iters,
                })

            params["blocks"][-1]["rank"] = block[0]

        config_path = './workloads/linear/config_files/config.json'
        save_json(config_path,params)

    @returnTime    
    def Start(self, param_set):
        command = f'cd {os.getcwd()}/workloads/linear; ./main  ./config_files/config.json'
        run_command(command)
    
    def GetWorkloadBeginEndTime(self):
        execute_log = f'{os.getcwd()}/workloads/linear/execution_timing.log'
        phase_log = f'{os.getcwd()}/workloads/linear/phase_time.csv'
        flag = False
        target_dir = os.path.join(self.result_dir, "time_record")
        try:
            target_phase_log = os.path.join(target_dir, "phase_time.csv")
            shutil.copy2(phase_log, target_phase_log)  # 复制并保留元数据
            print(f"已复制时间日志到: {target_phase_log}")
        except Exception as e:
            print(f"❌ 复制文件失败: {e}")
            return None
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
        


    def AdjustDuration(self,param_sets,phase_index=None):
        result_path = os.path.join(self.result_dir,'final_aggregations.csv')
        res_df = pd.read_csv(result_path)
        if phase_index is not None:
            df_aggr = pd.read_csv(os.path.join(self.sample_dir, 'aggr.csv'))
            duration= df_aggr['duration'].dropna().astype(int)

            print(duration[phase_index],res_df.iloc[0]['duration'],duration[phase_index] / res_df.iloc[0]['duration'])
            ratio = duration[phase_index] / res_df.iloc[0]['duration']

            param_set = param_sets[0]
            for i in range(len(param_set)-2):
                param_set[i][2] = int(param_set[i][2]*ratio)
            return param_sets

        target_path = self.target_path
        target_df = pd.read_csv(target_path)


        duration_ratios = target_df['duration']/res_df['duration']
        print(target_df.iloc[0]['duration'],res_df.iloc[0]['duration'])
        print(f'duration ratio={duration_ratios.iloc[0]:.4f}')
        for i, ratio in enumerate(duration_ratios):
            param_set = param_sets[i]
            for i in range(len(param_set)-2):
                param_set[i][2] *= ratio
    
        return param_sets
