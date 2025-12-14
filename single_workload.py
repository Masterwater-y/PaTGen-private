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

from workload_runner.BenchBaseRunner import BenchBaseRunner
from workload_runner.HiBenchRunner import HiBenchRunner

from workload_runner.BlockRunner import BlockRunner
from collectors.center.center_api import CenterWorker
import json

from workload_runner.LinearRunner import LinearRunner

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
job_dir = os.path.join('result', current_time_str)
stage_map=['in-memory','webserach','pr','cc','tc','tpcc','tpch','twitter','ycsb','join','kmeans','terasort','nutchindexing','wordcount','xgboost']

for i in range(1):
    all_time_info = []

    #current_time_str = '20251212-151222'
    job_dir = os.path.join('result', current_time_str)
    result_dir = os.path.join(job_dir,f'iter{i}')
    perf_dir = os.path.join(result_dir, 'perf')
    time_record_dir = os.path.join(result_dir, 'time_record')
    runner = BlockRunner(job_dir=job_dir, sample_index=i, normalize_block_duration=True)
    #runner = LinearRunner(job_dir=job_dir, result_dir= result_dir,sample_index=i)
    #runner = HiBenchRunner(job_dir=job_dir, sample_index=i)
    '''runner.GetChangePoint()
    sys.exit()'''
    '''runner.FilterPefData()
    runner.Evaluate()
    runner.CalcSerialSim()'''
    #runner.GetChangePoint()
    #print(runner.GetExtraMetric(30,0.1))
    #sys.exit()
    #param_sets = runner.GetParamSets()
    param_sets=[
        #['web-search',1000,200]
        #['graph','pr']
        #['nutchindexing']
    ]

    '''ranks = [1,2,4,8,12,16,24]
    stride = [i+1 for i in range(12)]
    mem = [16]

    tmp = []
    for i0 in ranks:
        tmp.append([[i0, 'sqrt', 1200000000], 16, 1])
    for i0 in [1]:
        tmp.append([[i0, 'div', 10000000000], 16, 1])
        tmp.append([[i0, 'add', 50000000000], 16, 1])
        for i1 in stride:
            tmp.append([[i0,'mem',10000000000,i1], 16, 1])

    param_sets = tmp
    param_sets = [[[1, 'sqrt', 1200000000], 16, 1]]'''


    ranks = [1,10,20,30,40,50,60]
    stride = [i+1 for i in range(12)]
    mem = [16]

    tmp = []
    for i0 in ranks:
        tmp.append([[i0, 'sqrt', 200000000], 16, 1])
        tmp.append([[i0, 'div', 2000000000], 16, 1])
        tmp.append([[i0, 'add', 10000000000], 16, 1])
        for i1 in stride:
            tmp.append([[i0,'mem',2000000000,i1], 16, 1])

    param_sets = tmp
    #param_sets = [[[1, 'sqrt', 1200000000], 16, 1]]

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

    print(f'iter{i} start alignment')
    runner.FilterPefData()
    runner.GetChangePoint()
    #runner.Evaluate()
    #runner.CalcSerialSim()
center.stop()
