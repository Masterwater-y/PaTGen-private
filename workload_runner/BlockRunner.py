import ast
import os
import csv
import shutil
from workload_runner.Runner import Runner
from workload_runner.common import returnTime, run_command, save_json, smooth_isolated_outliers, stage_divide
import pandas as pd

class BlockRunner(Runner):
    def __init__(self, job_dir = None, sample_index = 0, normalize_block_duration = False):
        super().__init__()
        self.mName = 'block'
        self.mParamSet = None
        self.job_dir = job_dir
        self.sample_index = sample_index
        self.result_dir = os.path.join(job_dir, f'iter{sample_index}')

        self.input_dir = 'sota/Phase/'
        self.perf_dir = os.path.join(self.result_dir, 'perf')
        self.time_record_dir = os.path.join(self.result_dir, 'time_record')
        self.time_record = []
        self.phase_aware = True
        self.normalize_block_duration = normalize_block_duration
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


    def PreStart(self,param_set): #采集block
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
        config_path = './workloads/block/config_files/config.json'

        save_json(config_path,params)

    @returnTime    
    def Start(self, param_set):
        command = f'cd {os.getcwd()}/workloads/block; ./parallel  ./config_files/config.json'
        run_command(command)
    
    def GetWorkloadBeginEndTime(self):
        execute_log = f'{os.getcwd()}/workloads/block/execution_timing.log'
        phase_log = f'{os.getcwd()}/workloads/block/phase_time.csv'

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
                        # 转换时间戳为浮点数，保留亚秒级信息
                        start_time = float(lines[0].strip())
                        end_time = float(lines[1].strip())
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

    def FilterPefData(self):
        super().FilterPefData()
        if self.normalize_block_duration:
            self._normalize_block_aggr()

    def _normalize_block_aggr(self):
        block_aggr_path = os.path.join(self.result_dir, 'block_aggr.csv')
        block_adjust_path = os.path.join(self.result_dir, 'block_aggr_adjust.csv')
        time_record_path = os.path.join(self.time_record_dir, 'time_record.csv')

        if not (os.path.exists(block_aggr_path) and os.path.exists(time_record_path)):
            return

        block_df = pd.read_csv(block_aggr_path)
        if block_df.empty:
            return

        metric_cols = [
            'cycles_sum', 'instructions_sum',
            'L1-misses_sum', 'll-misses_sum', 'power_sum'
        ]
        metric_cols = [col for col in metric_cols if col in block_df.columns]
        if not metric_cols:
            return

        block_df[metric_cols] = block_df[metric_cols].apply(pd.to_numeric, errors='coerce')

        time_df = pd.read_csv(time_record_path)
        if 'Duration' not in time_df.columns:
            return

        durations = pd.to_numeric(time_df['Duration'], errors='coerce')
        if durations.empty:
            return

        limit = min(len(block_df), len(durations))
        for idx in range(limit):
            actual_duration = durations.iloc[idx]
            if pd.isna(actual_duration) or actual_duration <= 0:
                continue
            rate = actual_duration/ int(actual_duration)
            block_df.loc[idx, metric_cols] = block_df.loc[idx, metric_cols] / rate
            param_str = block_df.loc[idx, 'param_set']
            param_obj = ast.literal_eval(param_str)
            param_obj[0][2] = int(param_obj[0][2] / rate )
            block_df.loc[idx, 'param_set'] = str(param_obj)
            block_df.loc[idx, 'duration'] = int(actual_duration)
        block_df['duration'] = block_df['duration'].fillna(0).astype(int)

        block_df.to_csv(block_adjust_path, index=False)
