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
from workload_runner.CloudmixRunner import CloudmixRunner
from collectors.center.center_api import CenterWorker
import json
import pandas as pd

def start_collector(warmup=40):
    # 读取配置文件
    config = ConfigParser()
    config.read('conf/global.conf', encoding='utf-8')
    center = CenterWorker()
    time.sleep(warmup)
    print('warm up finish')

    # 配置收集器
    center.m_center_collector.config_collectors({"ibmc_collector": 0, "tau_collector": 0, "slurm_collector": 0})
    center.start_center_collector()
    return center
# 获取当前文件所在目录

dir_path = os.path.dirname(os.path.realpath(__file__))
parent_dir_path = os.path.abspath(os.path.join(dir_path, os.pardir))
sys.path.insert(0, parent_dir_path)
os.chdir(os.path.dirname(os.path.realpath(__file__)))

center = start_collector(0)
current_time_str = datetime.now().strftime("%Y%m%d-%H%M%S")
current_time_str = 'paperdata/cloudmix-1phase'
job_dir = os.path.join(dir_path,'result', current_time_str)
runner = CloudmixRunner(job_dir= job_dir)
'''for i in range(5):
    runner.GetChangePoint(sample_index=i, alg='fixed', args=[1])
sys.exit()'''
generate_costs = []
for i in range(5):
    result_dir = os.path.join(job_dir, f'iter{i}')
    perf_dir = os.path.join(result_dir, 'perf')
    time_record_dir = os.path.join(result_dir, 'time_record')
    print(f'start iter{i} at {result_dir}')
    runner = CloudmixRunner(job_dir= job_dir, sample_index=i)

    '''start_time = time.time()
    param_sets = runner.GetParamSets()
    end_time = time.time()
    elapsed_time = end_time - start_time
    generate_costs.append({
        'iteration': i,
        'generate_cost': elapsed_time
    })
    for param_set in param_sets:
        print(f'param_set={param_set}')
        runner.StartAndSaveTime(param_set)
        time.sleep(1)
    runner.SaveTimeRecord()


    try:
        center.pull_node_data()
        nodes2df = center.get_node_data()
        for name, df in nodes2df.items():
            # 保存 perf 结果
            perf_file = os.path.join(perf_dir, f'perf_{name}.csv')
            df.to_csv(perf_file, index=False)

        #center.stop()
    except:
        print(traceback.print_exc())
        center.stop()
        exit(0)'''

    print(f'iter{i} start alignment')
    runner.FilterPefData()

    runner.Evaluate()
    runner.CalcSerialSim()
    runner.PhaseEvalute()

runner = CloudmixRunner(job_dir= job_dir)
cost_df = pd.DataFrame(generate_costs)
cost_csv_path = os.path.join(runner.job_dir, 'generate_cost.csv')
cost_df.to_csv(cost_csv_path, index=False)
runner.generate_final_reports()
center.stop()