import os
import time
from collectors.node.tools.collector import Collector
from collectors.node.node_constants import *
from collectors.node.tools.ftrace.data_proc import *


class FtraceCollector(Collector):
    def __init__(self) -> None:
        super().__init__(
            name = "ftrace_collector",
            data_type = "serial",
            tool_layer = "os",
            avail_sets = {
                "mem_cache_hit": ["mem_cache_accesses", "mem_cache_access_hits", 
                                    "mem_cache_access_misses", "mem_cache_access_hit_ratio"]
            }
        )
        self.set_attribute = {
            "mem_cache_hit": "function_trace"
        }
        self.set_functions = {
            "mem_cache_hit": ["mark_page_accessed", "mark_buffer_dirty", "add_to_page_cache_lru", 
                              "account_page_dirtied"]
        }
        self.function_trace_list = []
        self.config_collected_sets()
        
        
    def config_collected_sets(self, targer_sets=None):
        super().config_collected_sets(targer_sets)
        self.function_trace_list = []
        for data_set in self.collected_sets:
            if self.set_attribute[data_set] == "function_trace":
                self.function_trace_list.append(data_set)
        
        
    def start_collection(self, interval=1):
        cur_dir = os.path.abspath('.')
        os.chdir(os.path.split(os.path.realpath(__file__))[0])
        if not os.path.exists("data/pid"):
            os.system("mkdir -p data/pid")
        self.end_collection()
        target_function_list = []
        for data_set in self.collected_sets:
                target_function_list += self.set_functions[data_set]
        
        target_function_list = "\\\\n".join(target_function_list)
        if self.function_trace_list:
            os.system(f"nice -n -20 ./function_trace.sh -t {MAX_COLLECTED_TIME} -i {interval} -e {target_function_list} > /dev/null  &")
        os.chdir(cur_dir)
        
    
    def end_collection(self):
        cur_dir = os.path.abspath('.')
        os.chdir(os.path.split(os.path.realpath(__file__))[0])
        pid_list = os.listdir('./data/pid')
        for pid_file in pid_list:
            pid = open(f"./data/pid/{pid_file}").read()
            os.system(f'kill {pid}')
            os.remove(f"./data/pid/{pid_file}")
            time.sleep(1)
        os.chdir(cur_dir)
        
        
    def raw_data_proc(self, data_len=MAX_COLLECTED_TIME):
        cur_dir = os.path.abspath('.')
        os.chdir(os.path.split(os.path.realpath(__file__))[0])
        if self.function_trace_list:
            function_trace_data = function_trace_cal(data_len, self.function_trace_list, self.avail_sets)
            self.concat_new_data(function_trace_data, is_sub=1)
        os.chdir(cur_dir)