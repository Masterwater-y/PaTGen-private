import os
import csv
import threading
from workload_runner.Runner import Runner
from workload_runner.common import returnTime, run_command, save_json
import pandas as pd

class TracieRunner(Runner):
    def __init__(self, result_dir = None):
        super().__init__()
        self.mName = 'Tracie'
        self.mParamSet = None
        self.result_dir = result_dir
        self.input_dir = 'sota/Tracie/'
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
                param_set = eval(row['params'])
                param_sets.append(param_set)
        return param_sets

    def PreStart(self,param_set):
        pass
        

        
    @returnTime    
    def Start(self, param_set):
        params_str = " ".join([str(p) for p in param_set[1:]])
        command = 'cd {cwd}/workloads/tracie/rodinia; ./bin/linux/omp/{program} {params}'.format(
            cwd=os.getcwd(),
            program=param_set[0],
            params=params_str
        )
        run_command(command)
    
    def GetWorkloadBeginEndTime(self):
        return None
    
