import os
import csv
from workload_runner.Runner import Runner
from workload_runner.common import returnTime, run_command, save_json, transform_targets
import pandas as pd

class CloudSuiteRunner(Runner):
    def __init__(self, job_dir = None, sample_index = 0):
        super().__init__()
        self.mName = 'cloudsuite'
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
        param_sets=[1]
        return param_sets

    def PreStart(self,param_set):
        pass

    @returnTime    
    def Start(self, param_set):
        workload = param_set[0]
        if workload == 'in-memory':
            command = f'docker run --rm --volumes-from movielens-data cloudsuite/in-memory-analytics     /data/ml-latest /data/myratings.csv --driver-memory 16g --executor-memory 16g'
        elif workload == 'graph':
            command = f'docker run --rm --volumes-from twitter-data -e WORKLOAD_NAME={param_set[1]} cloudsuite/graph-analytics \
    --driver-memory 16g --executor-memory 16g'
        elif workload == 'web-search':
            command = f'ssh 222.201.144.198 "docker run --rm --name web_search_client --net host cloudsuite/web-search:client 222.201.144.200 {param_set[1]}  --steady={param_set[2]} --interval-distribution=Uniform --interval-min=500 --interval-max=1500 " '
        run_command(command)
    
    def GetWorkloadBeginEndTime(self):
        return None
    
    def GetChangePoint(self):
        import pandas as pd
        import numpy as np
        from scipy.stats import mannwhitneyu
        from sklearn.cluster import DBSCAN
        import matplotlib.pyplot as plt
        metric_path = os.path.join(self.result_dir,'final_result','metric_0.csv')
        sub_path = os.path.join(self.stage_dir,'sub')
        final_aggr = pd.read_csv(os.path.join(self.result_dir,'final_aggregations.csv'))
        target_df = transform_targets(final_aggr)
        target_df.to_csv(os.path.join(self.stage_dir,'targets.csv'))

        if not os.path.exists(sub_path):
            os.makedirs(sub_path)
        png_path =  os.path.join(self.stage_dir,'stage.png')
        # 参数配置
        WINDOW_SIZE = 10  # 滑动窗口大小
        STEP = 1          # 滑动步长
        SIGNIFICANCE_LEVEL = 0.05  # 显著性水平
        MIN_METRICS = 1     # 触发变点的最小指标数
        CLUSTER_EPS = 2    # 变点合并的聚类半径
        # 读取数据
        data = pd.read_csv(metric_path)
        data.to_csv(os.path.join(self.stage_dir,'metric_0.csv'),index=False)
        timestamps = data['time']
        metrics_df = data[['cpu_util', 'CPI', 'MPKI']]
        # 数据标准化
        metrics_df = (metrics_df - metrics_df.mean()) / metrics_df.std()
        # 检测候选变点
        candidates = []
        for start in range(0, len(metrics_df) - WINDOW_SIZE + 1, STEP):
            end = start + WINDOW_SIZE
            window = metrics_df.iloc[start:end]
            midpoint = start + WINDOW_SIZE // 2
            detected = []
            for metric in ['MPKI']:
                series = window[metric].values
                split = len(series) // 2
                part1, part2 = series[:split], series[split:]
                try:
                    _, p_val = mannwhitneyu(part1, part2, alternative='two-sided')
                except ValueError:
                    p_val = 1.0
                if p_val < SIGNIFICANCE_LEVEL:
                    detected.append(metric)
            if len(detected) >= MIN_METRICS:
                candidates.append(midpoint)
        # 合并邻近变点
        if not candidates:
            print("未检测到变点")
            stages = [(0, len(metrics_df)-1)]
        else:
            candidates = np.array(candidates).reshape(-1, 1)
            clustering = DBSCAN(eps=CLUSTER_EPS, min_samples=1).fit(candidates)
            final_cps = []
            for label in set(clustering.labels_):
                if label == -1:
                    continue
                cluster_points = candidates[clustering.labels_ == label].flatten()
                final_cps.append(int(cluster_points.mean()))
            final_cps = sorted(final_cps)
            # 划分阶段
            stages = []
            prev = 0
            for cp in final_cps:
                stages.append((prev, cp))
                prev = cp
            stages.append((prev, len(metrics_df)-1))
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
        if average_cpu_util < 10:
            scale_factor = 10 / average_cpu_util
        for item in aggregate_data:
            item['instruction'] *= scale_factor
            item['scale_factor'] =  scale_factor
        aggr_df = pd.DataFrame(aggregate_data)
        aggr_path = os.path.join(self.stage_dir, 'aggr.csv')
        aggr_df.to_csv(aggr_path, index=False)
        # 可视化
        plt.figure(figsize=(12, 6))
        for i, metric in enumerate(['cpu_util', 'CPI', 'MPKI'], 1):
            plt.subplot(3, 1, i)
            plt.plot(timestamps, metrics_df[metric], label=metric)
            for cp in final_cps:
                plt.axvline(timestamps[cp], color='r', linestyle='--')
            plt.ylabel(metric)
            plt.legend()
        plt.tight_layout()
        plt.savefig(png_path)

