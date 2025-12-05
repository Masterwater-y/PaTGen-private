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
from workload_runner.BlockRunner import BlockRunner
from collectors.center.center_api import CenterWorker
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

center = start_collector(40)
current_time_str = datetime.now().strftime("%Y%m%d-%H%M%S")
job_dir = os.path.join('result', current_time_str)
for i in range(1):
    all_time_info = []

    #current_time_str = '20250609-130541'

    result_dir = os.path.join(job_dir,f'iter{i}')
    perf_dir = os.path.join(result_dir, 'perf')
    time_record_dir = os.path.join(result_dir, 'time_record')
    runner = BlockRunner(job_dir = job_dir, sample_index=i)
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
    ]

    '''param_sets = [
        [[[1, 'add', 50000000000,0 ]], 16, 1],
        [[[1, 'add', 4807692307,0 ]], 16, 1]
    ]'''

    ranks = [1,2,4,8,12,16,24]
    ranks.append(1)
    stride = [i+1 for i in range(12)]
    mem = [16]

    tmp = [
        #[[1, 'div', 43740858848], [1, 'add', 96608598066], [1, 'mem', 7480897503, 12], 16, 1]
    ]
    for i0 in ranks:
        tmp.append([[i0, 'sqrt', 1200000000], 16, 1])
    for i0 in [1]:
        tmp.append([[i0, 'div', 10000000000], 16, 1])
        tmp.append([[i0, 'add', 50000000000], 16, 1])
        for i1 in stride:
            tmp.append([[i0,'mem',10000000000,i1], 16, 1])

    param_sets = tmp
    #param_sets = tmp
    '''param_sets = [

       [[[5, 'mem', 1428571419, 12, 0], [1, 'mem', 1447368417, 5, 0], [5, 'add', 14102564102, 0], [4, 'div', 1428571419, 0], [8, 'sqrt', 220000000, 0]], [[7, 'mem', 1298701290, 12, 0], [1, 'mem', 1369863010, 6, 0], [6, 'add', 12820512820, 0], [3, 'div', 1298701290, 0], [29, 'sqrt', 200000000, 0]], [[4, 'mem', 1428571419, 12, 0], [1, 'mem', 1447368417, 8, 0], [5, 'add', 14102564102, 0], [1, 'div', 1428571419, 0], [10, 'sqrt', 220000000, 0]], 16, 1]
    ]'''


    ranks = [i+1 for i in range(1,24,2)]
    ranks.append(1)
    stride = [1,2,3,4,5,6,7,8,9,10,11,12]
    factor = [1,2,3,4,5,6,7,8,9,10]
    mem = [16]
    all_iter=[5000000000]



    '''tmp = []
    for i0 in ranks:
        tmp.append([[i0, 'sqrt', 1200000000], 16, 1])


    for i0 in [1]:
        for mem_size in mem:
            tmp.append([[i0, 'div', 10000000000], mem_size, 1])
            tmp.append([[i0, 'add', 50000000000], mem_size, 1])
            for i1 in stride:
                tmp.append([[i0, 'mem', 10000000000, i1], mem_size, 1])
    param_sets = tmp
    print(param_sets)'''
    '''param_sets = [
        #[[[63, 'div', 7607059438,0]], 16, 1],
        #[[[1, 'div', 7607059430]], 16, 1],
        #[[[3, 'add', 57683430379,0]], 16, 1],
        #[[[1, 'div', 1000000000, 0]], 16, 1],

        #[[[63, 'div', 7607059438,0],[3, 'add', 57683430379,0],[1, 'mem', 7559344755, 12,0]], 16, 1],
        #[[[4, 'add', 57412124162,0]], 8, 1],
        #[[[1, 'mem', 7265183009, 12,0]], 8, 1],
        #[[[64, 'div', 7673991498,0],[4, 'add', 57412124162,0],[1, 'mem', 7265183009, 12,0]], 8, 1],


        [[[16, 'sqrt', 1200000000, 0]], 16, 1],
        [[[32, 'sqrt', 1200000000, 0]], 16, 1],
        [[[48, 'sqrt', 1200000000, 0]], 16, 1],
        [[[64, 'sqrt', 1200000000, 0]], 16, 1],

    ]'''

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
    #runner.GetChangePoint()
    #runner.Evaluate()
    #runner.CalcSerialSim()
center.stop()