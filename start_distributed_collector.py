from time import sleep
import sys
import os
import traceback
from configparser import ConfigParser

from workload_runner.common import run_command
dir_path = os.path.dirname(os.path.realpath(__file__))
parent_dir_path = os.path.abspath(os.path.join(dir_path, os.pardir))
sys.path.insert(0, parent_dir_path)
from collectors.center.center_api import CenterWorker
from collectors.node.node_api import NodeWorker


if __name__ == '__main__':
    '''
    执行 python 的命令和含义：
    【python start_distributed_collector.py center】: 启动 center 端
    【python start_distributed_collector.py node】: 启动 node 端
    '''
    os.chdir(os.path.dirname(os.path.realpath(__file__)))
    config = ConfigParser()
    config.read('conf/global.conf', encoding='utf-8')
    if sys.argv[1] == 'center':
        # 启动 center 连接
        center = CenterWorker()
        sleep(40)
        print('warm up finish')
        # 拉取 node 数据
        #center.pull_node_data()
        #print(center.get_node_data())
         
        # 获取 center 数据
        center.m_center_collector.config_collectors({"ibmc_collector": 1, "tau_collector": 0, "slurm_collector": 0})
        #print(center.get_center_data(save_dir='raw_result'))
        center.start_center_collector()      
        try:
            sleep(60)
            print(center.pull_node_data())
            nodes2df=center.get_node_data()
            dir = config.get('outputs', 'perf_output_dir')
            for name, df in nodes2df.items():
                df.to_csv(f'{dir}/perf_{name}.csv',index=False)
            #center.generate_center_data()
            center.stop()
        except:
            print(traceback.print_exc())
            nodes2df=center.get_node_data()
            dir = config.get('outputs', 'perf_output_dir')
            for name, df in nodes2df.items():
                df.to_csv(f'{dir}/perf_{name}.csv',index=False)
            #center.generate_center_data()
            center.stop()
            exit(0)
        
    elif sys.argv[1] == 'node':
        command = f'pkill -f hardware; pkill -f perf'
        run_command(command)
        nodeWorker = NodeWorker()
        nodeWorker.m_node_collector.config_collectors({"ibmc_collector": 1,
                                                       "ftrace_collector": 0, 
                                                       "perf_collector":1,
                                                       "blktrace_collector":0,
                                                       "proc_fs_collector":1,
                                                    #    "msprof_collector":0,
                                                    "nvidia_smi_collector":0
                                                       })
        nodeWorker.start() # blocking
    
    else:
        print('Error: wrong argument')

