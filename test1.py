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
import optuna
from workload_runner.MeowRunner import MeowRunner
from collectors.center.center_api import CenterWorker
import json

# 获取当前文件所在目录
dir_path = os.path.dirname(os.path.realpath(__file__))
parent_dir_path = os.path.abspath(os.path.join(dir_path, os.pardir))
sys.path.insert(0, parent_dir_path)
os.chdir(os.path.dirname(os.path.realpath(__file__)))

# 读取配置文件
config = ConfigParser()
config.read('conf/global.conf', encoding='utf-8')
center = CenterWorker()
time.sleep(40)
print('warm up finish')

# 配置收集器
center.m_center_collector.config_collectors({"ibmc_collector": 0, "tau_collector": 0, "slurm_collector": 0})
center.start_center_collector()


def create_objective(runner,center):
    def objective(trial):
        # 在这里可以访问 original_config 和 extra_params
        params=[]
        scale = 10000000
        params.append([
            1,
            'div',
            trial.suggest_int(
                f"block_0_iterations", 
                0,  # 基于原始值浮动
                50
            )*scale,
        ])
        params.append([
            1,
            'add',
            trial.suggest_int(
                f"block_5_iterations", 
                0,  # 基于原始值浮动
                50
            )*scale,
        ])
        params.append([
            1,
            'mem',
            trial.suggest_int(
                f"block_1_iterations", 
                0,  # 基于原始值浮动
                50
            )*scale,
            1
        ])
        params.append([
            1,
            'mem',
            trial.suggest_int(
                f"block_2_iterations", 
                0,  # 基于原始值浮动
                50
            )*scale,
            2
        ])
        params.append([
            1,
            'mem',
            trial.suggest_int(
                f"block_3_iterations", 
                0,  # 基于原始值浮动
                50
            )*scale,
            3
        ])
        params.append([
            1,
            'mem',
            trial.suggest_int(
                f"block_4_iterations", 
                0,  # 基于原始值浮动
                50
            )*scale,
            4
        ])
        params.append(8)
        params.append(1)
        print(f'params={params}')
        runner.StartAndSaveTime(params)
        runner.SaveTimeRecord()
        center.pull_node_data()
        nodes2df = center.get_node_data()

        for name, df in nodes2df.items():
            # 保存 perf 结果
            perf_file = os.path.join(perf_dir, f'perf_{name}.csv')
            print(f'perf_file={perf_file}')
            df.to_csv(perf_file, index=False)

        # 使用 extra_params 进行复杂计算
        runner.FilterPefData()
        cpi, mpki = runner.Evaluate()
        return cpi
    
    return objective


all_time_info = []
current_time_str = datetime.now().strftime("%Y%m%d-%H%M%S")
result_dir = os.path.join('result', current_time_str)
target_dir = os.path.join('generate')
perf_dir = os.path.join(result_dir, 'perf')
time_record_dir = os.path.join(result_dir, 'time_record')



runner = MeowRunner(result_dir = result_dir)
# 创建优化器
study = optuna.create_study(
    directions=["minimize"],
    sampler=optuna.samplers.TPESampler(),
    pruner=optuna.pruners.MedianPruner()
)
# 执行优化
study.optimize(create_objective(runner,center), n_trials=50, n_jobs=1)  # 并行优化
print("Best trial parameters:")
best_trials = study.best_trials

# 输出所有帕累托最优解
print("Pareto Front Solutions:")
for i, trial in enumerate(best_trials):
    print(f"Solution {i+1}:")
    print(f"  Values: CPI Error = {trial.values[0]:.2f}%")
    #print(f"  Values: CPI Error = {trial.values[0]:.2f}%, MPKI Error = {trial.values[1]:.2f}%")
    print(f"  Parameters:", trial.params)
    print("-" * 40)
    
print("Best params:")
center.stop()