import os
import time

from collectors.node.tools.collector import Collector
from collectors.node.node_constants import *
from collectors.node.tools.msprof.data_proc import *

class MsprofCollector(Collector):
    def __init__(self) -> None:
        super().__init__(
            name = "msprof_collector",
            data_type = "serial",
            tool_layer = "npu",
            avail_sets = {
                "ai_core": ["util"],
                "pmu": ["cpu_cycles", "inst_retired"],
                "memory": ["llc_occupation(mb)", "ddr/read(mb/s)", "ddr/write(mb/s)"]
            }
        )
        
        
    def start_collection(self, interval=1):
        cur_dir = os.path.abspath('.')
        os.chdir(os.path.split(os.path.realpath(__file__))[0])
        if not os.path.exists("data/pid"):
            os.system("mkdir -p data/pid")
        self.end_collection()
        os.system(f"nice -n -20 ./msprof.sh -i {MSPROF_INTERVAL} -t {MAX_COLLECTED_TIME} > /dev/null &")
        os.chdir(cur_dir)
        
    def wait_pid_end(self, pid):
        while True:
            exit_code = os.system(f"kill -0 {pid}")
            if not exit_code:
                time.sleep(0.5)
            else:
                break
        
    def end_collection(self):
        cur_dir = os.path.abspath('.')
        os.chdir(os.path.split(os.path.realpath(__file__))[0])
        pid_list = os.listdir('./data/pid')
        for pid_file in pid_list:
            pid = open(f"./data/pid/{pid_file}").read()
            os.system(f'kill {pid}')
            os.remove(f"./data/pid/{pid_file}")
            self.wait_pid_end(pid)
        os.chdir(cur_dir)
        
        

    def raw_data_proc(self, data_len=MAX_COLLECTED_TIME):
        cur_dir = os.path.abspath('.')
        os.chdir(os.path.split(os.path.realpath(__file__))[0])
        self.msprof_data_proc(data_len)
        os.chdir(cur_dir)
        
        
    def msprof_data_proc(self, data_len):
        for item in sorted(os.listdir("./data/raw"), reverse=True):
            if not os.path.isdir(f"./data/raw/{item}"):
                continue
            if len(self.data) > data_len:
                return
            device_name = os.listdir(f"./data/raw/{item}")[0]
            # 如果没有summary文件夹说明这段数据还在采集，因此跳过
            if not os.path.exists(f"./data/raw/{item}/{device_name}/summary"):
                continue
            
            if os.path.exists(f"./data/parse/{item}"):
                # 已经处理过的数据不需要重复处理
                msprof_serial_data = pd.read_csv(f"./data/parse/{item}/serial_data.csv")
                msprof_aggregate_data = pd.read_csv(f"./data/parse/{item}/aggregate_data.csv")
            else:
                os.system(f"mkdir ./data/parse/{item}")
                msprof_serial_data = msprof_serial_data_cal(item)
                msprof_aggregate_data = msprof_aggregate_data_cal(item)
                msprof_serial_data.to_csv(f"./data/parse/{item}/serial_data.csv", index=False)
                msprof_aggregate_data.to_csv(f"./data/parse/{item}/aggregate_data.csv", index=False)
            msprof_data = pd.merge(msprof_serial_data, msprof_aggregate_data, on="time", how="inner")
            
            if self.data.empty:
                self.data = msprof_data
            else:
                self.data = pd.concat([msprof_data, self.data], ignore_index=True)
                
            
    
        
    
        
        
            