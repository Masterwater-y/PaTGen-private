import os
import pandas as pd
from collectors.node.node_constants import *
from collectors.node.tools.collector import Collector
from collectors.node.tools.ibmc.data_proc import *



POWER_COLLECT_WORK_DIR = os.path.split(os.path.realpath(__file__))[0]

class IBMCCollector(Collector):
    def __init__(self, ibmc_dict):
        super().__init__(
            name = "ibmc_collector",
            data_type = "serial",
            tool_layer = "server",
            avail_sets = {"power": ["time", "power", "cpu_power", "memory_power"]}
        )
        self.ibmc_dict = ibmc_dict
        
    
    def start_collection(self, interval=1):
        cur_dir = os.path.abspath('.')
        os.chdir(os.path.split(os.path.realpath(__file__))[0])
        if not os.path.exists("data/pid"):
            os.system("mkdir -p data/pid")
        self.end_collection()
        os.system(f"nice -n -20 python ibmc_data_collect.py -i \"{self.ibmc_dict}\" -s \"{self.collected_sets}\" \
            -l {interval} -t {MAX_COLLECTED_TIME} &")
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
        
    def power_proc(self, collect_time):
        time_info = collected_time_cal(collect_time)
        power_info = power_cal(collect_time)
        result = [time_info[i]+power_info[i] for i in range(len(time_info))]
        result = pd.DataFrame(result)
        result.columns = self.avail_sets["power"]
        return result


    def raw_data_proc(self, collect_time=MAX_COLLECTED_TIME):
        cur_dir = os.path.abspath('.')
        os.chdir(os.path.split(os.path.realpath(__file__))[0])
        
        for data_set in self.collected_sets:
            if data_set == "power":
                power_data = self.power_proc(collect_time)
                self.concat_new_data(power_data, is_sub=1)
        
        os.chdir(cur_dir)

