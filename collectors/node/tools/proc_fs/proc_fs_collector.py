import pandas as pd
import os

from collectors.node.tools.collector import Collector
from collectors.node.node_constants import *
from collectors.node.tools.proc_fs.data_proc import *



# proc文件系统的数据采集工具
class ProcFsCollector(Collector):
    def __init__(self) -> None:
        network_data_type = os.popen("cat /proc/net/dev | head -n +2 | tail -n 1").read().split("|")
        HARDWARE_USAGE_DATA_TYPE = ["time", "cpu_user","cpu_nice","cpu_sys","cpu_idle","cpu_iowait","cpu_irq","cpu_softirq"]
        HARDWARE_USAGE_DATA_TYPE += os.popen("cat /proc/meminfo | awk '{print $1}' | sed s/://").read().split()
        HARDWARE_USAGE_DATA_TYPE += ["rrqm/s","wrqm/s","r/s","w/s","rMB/s","wMB/s","avgrq-sz","avgqu-sz","await","r-await","w-await","util"]
        HARDWARE_USAGE_DATA_TYPE += ["rx_"+i for i in network_data_type[1].split()] + ["tx_"+i for i in network_data_type[2].split()]
        for i in range(NUMA_ZONE_NUM):
            HARDWARE_USAGE_DATA_TYPE += [f"node{i}_numa_hit", f"node{i}_numa_miss", f"node{i}_numa_foreign",\
                f"node{i}_interleave_hit", f"node{i}_local_node", f"node{i}_other_node"]
        super().__init__(
            name = "proc_fs_collector",
            data_type = "serial",
            tool_layer = "server",
            avail_sets = {"hardware_usage": HARDWARE_USAGE_DATA_TYPE}
        )
    
    def start_collection(self, interval=1):
        cur_dir = os.path.abspath('.')
        os.chdir(os.path.split(os.path.realpath(__file__))[0])
        if not os.path.exists("data/pid"):
            os.system("mkdir -p data/pid")
        self.end_collection()
        for data_set in self.collected_sets:
            if data_set == "hardware_usage":
                os.system(f"nice -n -20 ./hardware_usage.sh -t {MAX_COLLECTED_TIME} -i {interval} -d {MAIN_DISK} -n {MAIN_NET_INTERFACE} &")
        os.chdir(cur_dir)
        
    
    def end_collection(self):
        cur_dir = os.path.abspath('.')
        os.chdir(os.path.split(os.path.realpath(__file__))[0])
        pid_list = os.listdir('./data/pid')
        for pid_file in pid_list:
            pid = open(f"./data/pid/{pid_file}").read()
            os.system(f'kill {pid}')
            os.remove(f"./data/pid/{pid_file}")
        os.chdir(cur_dir)
        
        
    def hardware_usage_proc(self, data_len):
        timestamp = collected_time_cal(data_len)
        cpu_util = cpu_util_cal(data_len)
        mem_util = mem_util_cal(data_len)
        io_stat = io_cal(data_len)
        network_stat = network_cal(data_len)
        numa_stat = numa_cal(data_len)
        
        if not len(cpu_util) == len(timestamp):
            timestamp = timestamp[1:]
            mem_util = mem_util[1:]
            numa_stat = numa_stat[1:]
        result = [timestamp[i]+cpu_util[i]+mem_util[i]+io_stat[i]+network_stat[i]+numa_stat[i]\
            for i in range(len(cpu_util))]
        result = pd.DataFrame(result)
        result.columns = self.avail_sets["hardware_usage"]
        return result
        
        
    def raw_data_proc(self, data_len=MAX_COLLECTED_TIME):
        cur_dir = os.path.abspath('.')
        os.chdir(os.path.split(os.path.realpath(__file__))[0])
        for data_set in self.collected_sets:
            if data_set == "hardware_usage":
                hardware_usage_data = self.hardware_usage_proc(data_len)
                self.concat_new_data(hardware_usage_data, is_sub=1)
                
        os.chdir(cur_dir)
                
                

