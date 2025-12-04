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
from workload_runner.CloudSuiteRunner import CloudSuiteRunner
from workload_runner.LinearRunner import LinearRunner
from workload_runner.PhaseRunner import PhaseRunner
from workload_runner.MyRunner import MyRunner
from collectors.center.center_api import CenterWorker
import pandas as pd
import json

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
current_time_str = 'paperdata/linear-1phase'
job_dir = os.path.join('result', current_time_str)
generate_costs = []
for i in range(1):
    '''result_dir = os.path.join(job_dir, f'tmp{i}')
    perf_dir = os.path.join(result_dir, 'perf')
    time_record_dir = os.path.join(result_dir, 'time_record')
    runner = LinearRunner(job_dir= job_dir, result_dir=result_dir, sample_index=i)
    phase_num = runner.phase_num

    param_sets = []
    phase_sets=[]
    stage_params = []
    start_time = time.time()


    for phase_index in range(phase_num):
        param_tmp = runner.GetParamSets(scale_factor=1,phase_index=phase_index)
        if len(phase_sets)==0:
            phase_sets.append(len(param_tmp[0])-2)
        else:
            phase_sets.append(phase_sets[-1]+len(param_tmp[0])-2)
        for j in range(1):
            runner = LinearRunner(job_dir= job_dir, result_dir=result_dir, sample_index=i)

            for param_set in param_tmp:
                runner.StartAndSaveTime(param_set)

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
                exit(0)

            runner.FilterPefData()
            param_tmp = runner.AdjustDuration(param_tmp, phase_index=phase_index)

        stage_params.append(param_tmp[0][:-2])
        param_sets.extend(param_tmp[0][:-2])




    param_sets.extend([16,1])
    param_sets = [param_sets]
    end_time = time.time()
    elapsed_time = end_time - start_time
    generate_costs.append({
        'iteration': i,
        'generate_cost': elapsed_time
    })'''
    result_dir = os.path.join(job_dir, f'iter{i}')
    perf_dir = os.path.join(result_dir, 'perf')
    time_record_dir = os.path.join(result_dir, 'time_record')
    runner = LinearRunner(job_dir= job_dir, result_dir=result_dir, sample_index=i)
    '''phase_path = './workloads/linear/config_files/phase.json'
    with open(phase_path, 'w') as f:
        json.dump(phase_sets, f, indent=4)
    for param_set in param_sets:
        print(f'param_set={param_set}')
        time.sleep(1)
        runner.StartAndSaveTime(param_set)

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
cost_df = pd.DataFrame(generate_costs)
cost_csv_path = os.path.join(runner.job_dir, 'generate_cost.csv')
cost_df.to_csv(cost_csv_path, index=False)
runner = LinearRunner(job_dir= job_dir, result_dir='None', sample_index=None)
runner.generate_final_reports()

'''result_dir = os.path.join(job_dir)
perf_dir = os.path.join(result_dir, 'perf')
time_record_dir = os.path.join(result_dir, 'time_record')
runner = LinearRunner(job_dir= job_dir, result_dir=result_dir)
param_sets =[
    [[1, 'div', 433081654], [1, 'add', 946484580], [1, 'mem', 71159070, 12], [1, 'div', 4563135290], [1, 'add', 5701098927], [1, 'mem', 1201632379, 12], 16, 1]
]
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
    exit(0)
runner.FilterPefData()'''
center.stop()