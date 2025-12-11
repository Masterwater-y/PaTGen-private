import os
import csv
from workload_runner.Runner import Runner
from workload_runner.common import returnTime, run_command, save_json, stage_divide, transform_targets
import pandas as pd

class BenchBaseRunner(Runner):
    def __init__(self, job_dir = None, sample_index = 0):
        super().__init__()
        self.mName = 'benchbase'
        self.mParamSet = None
        self.job_dir = job_dir
        self.sample_index = sample_index
        self.result_dir = os.path.join(job_dir, f'iter{sample_index}')
        self.input_dir = 'sota/MINE/'
        self.perf_dir = os.path.join(self.result_dir, 'perf')
        self.stage_dir = os.path.join(self.result_dir, 'stage')
        self.time_record_dir = os.path.join(self.result_dir, 'time_record')
        self.time_record = []
        if not os.path.exists(self.stage_dir):
            os.makedirs(self.stage_dir)

    def GetParamSets(self):
        param_sets=None
        return param_sets

    def PreStart(self,param_set):
        pass

    @returnTime    
    def Start(self, param_set):
        workload = param_set[0]
        command = f'cd {os.getcwd()}/workloads/benchbase/cmd; ./run.sh {workload}'
        run_command(command)
    
    def GetWorkloadBeginEndTime(self):
        return None
    
    def GetChangePoint(self):
        import pandas as pd
        import numpy as np
        metric_path = os.path.join(self.result_dir,'final_result','metric_0.csv')
        sub_path = os.path.join(self.stage_dir,'sub')
        final_aggr = pd.read_csv(os.path.join(self.result_dir,'final_aggregations.csv'))
        target_df = transform_targets(final_aggr)
        target_df.to_csv(os.path.join(self.stage_dir,'targets.csv'))

        if not os.path.exists(sub_path):
            os.makedirs(sub_path)
        png_path =  os.path.join(self.stage_dir,'stage.png')

        data = pd.read_csv(metric_path)
        data.to_csv(os.path.join(self.stage_dir,'metric_0.csv'),index=False)

        stages = stage_divide(data, alg='window',args=None,png_path=png_path)
        # 输出结果
        print("负载阶段划分：")
        aggregate_data = [] 
        for i, (start, end) in enumerate(stages):
            if i == len(stages)-1:
                end+=1
            phase_data = data.iloc[start : end]
            file_path = os.path.join(sub_path,f'metric_{i}.csv')
            # 保存CSV（保留列名和索引可选）
            phase_data.to_csv(file_path, index=False)
            print(f"阶段 {i+1}: {start} 至 {end-1}")
            # 计算聚合指标
            cpu_util_mean = phase_data['cpu_util'].mean()
            # 关键修正：计算总和再相除
            sum_cycles = phase_data['cycles'].sum()
            sum_instructions = phase_data['instructions'].sum()
            sum_llc_misses = phase_data['ll-misses/'].sum()
            avg_cpi = phase_data['CPI'].mean()
            avg_mpki = phase_data['MPKI'].mean()
            # 避免除零错误
            if sum_instructions > 0:
                cpi = sum_cycles / sum_instructions
                mpki = (sum_llc_misses * 1000) / sum_instructions
            else:
                cpi = np.nan
                mpki = np.nan
        
            
            aggregate_data.append({
                'duration': end-start,
                'cpu_util': cpu_util_mean*100,
                'mem_util': 30,
                'CPI': cpi,
                'MPKI': mpki,
                'avg_CPI':avg_cpi,
                'avg_MPKI':avg_mpki,
                'disk_util':3,
                'power':280,
                'mem_capacity': 64,
                'mem_size':256,
                'instruction':sum_instructions
            })
        # 计算所有阶段的CPU利用率均值
        all_cpu_util = [item['cpu_util'] for item in aggregate_data]
        average_cpu_util = sum(all_cpu_util) / len(all_cpu_util) if all_cpu_util else 0
        scale_factor = 1
        # 如果平均CPU利用率小于10，则调整指令数
        if average_cpu_util < 20:
            scale_factor = 20 / average_cpu_util
        for item in aggregate_data:
            item['instruction'] *= scale_factor
            item['scale_factor'] =  scale_factor
        aggr_df = pd.DataFrame(aggregate_data)
        aggr_path = os.path.join(self.stage_dir, 'aggr.csv')
        aggr_df.to_csv(aggr_path, index=False)
       

