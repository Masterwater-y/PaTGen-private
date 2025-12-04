import pandas as pd
from collectors.node.node_constants import *

from collectors.node.tools.collector import Collector
from collectors.node.tools.ftrace.ftrace_collector import FtraceCollector
from collectors.node.tools.perf.perf_collector import PerfCollector
from collectors.node.tools.proc_fs.proc_fs_collector import ProcFsCollector
from collectors.node.tools.blktrace.blktrace_collector import BlktraceCollector
from collectors.node.tools.ibmc.ibmc_collector import IBMCCollector
from collectors.node.tools.msprof.msprof_collector import MsprofCollector
from collectors.node.tools.nvidia_smi.nvidia_smi_collector import NVidiaSmiCollector


class NodeCollector(Collector):
    def __init__(self) -> None:
        self.data = pd.DataFrame()  # 时序数据
        self.is_collecting = False  # 是否正在执行数据采集
        self.sub_collectors = {"ibmc_collector": IBMCCollector(IBMC_INFO[NODE_ID]), \
            "ftrace_collector": FtraceCollector(), "perf_collector": PerfCollector(), \
            "proc_fs_collector": ProcFsCollector(), "blktrace_collector": BlktraceCollector(), \
            "msprof_collector": MsprofCollector(),"nvidia_smi_collector": NVidiaSmiCollector()}

        # 默认采集所有数据
        self.config_collectors(None)
        # self.config_collected_sets(None)

    
    def start_collection(self, interval=1) -> None:
        """启动各个采集器，开始采集数据

        Args:
            interval (int, optional): 采集时间间隔. Defaults to 1.
        """
        if self.is_collecting:
            print("[NodeCollector]: Error. Start collection fails, collector is running.")
            return
        print(f"[NodeCollector]: target disk: {MAIN_DISK}")
        print(f"[NodeCollector]: target network: {MAIN_NET_INTERFACE}")
        self.is_collecting = True
        for collector in self.sub_collectors.values():
            if not len(collector.collected_sets) == 0:
                print(f"[NodeCollector]: start collector: {collector.name}")
                collector.start_collection(interval)
    
    
    def end_collection(self) -> None:
        """结束各个采集器
        """
        if not self.is_collecting:
            print("error: end collection fails, collector is not running.")
            return
        self.is_collecting = False
        for collector in self.sub_collectors.values():
            if not len(collector.collected_sets) == 0:
                print(f"end collector: {collector.name}")
                collector.end_collection()
            
    def config_collectors(self, target_set_dict:dict=None) -> None:
        """设置各个采集器需要采集的数据集

        Args:
            target_set_dict (dict, optional): 包含各个采集器需要采集的数据集字典, 键值对类型为str-list
            例如{"ftrace_collector": ["mem_cache_hit"]}。默认为None, 表示采集所有数据
        """
        if target_set_dict is None:
            for collector in self.sub_collectors.values():
                collector.config_collected_sets(None) 
        else:
            for collector in self.sub_collectors:
                if collector in target_set_dict and target_set_dict[collector]:
                    self.sub_collectors[collector].config_collected_sets(None)
                else:
                    self.sub_collectors[collector].config_collected_sets([])
    
    
    def integrate_collector_data(self, data_len:int=MAX_COLLECTED_TIME) -> None:
        """整合各采集器的数据到self.data

        Args:
            data_len (int, optional): 数据长度. Defaults to MAX_COLLECTED_TIME.
        """
        self.data = pd.DataFrame()
        for collector in self.sub_collectors.values():
            if not len(collector.collected_sets) == 0:
                collector.data = pd.DataFrame()
                collector.raw_data_proc(data_len)
                self.concat_new_data(collector.data)
        self.data.sort_values(by="time", axis=0, ascending=True, inplace=True)
        
        
    def get_data(self, save_dir:str=None) -> pd.DataFrame:
        """获取数据

        Args:
            save_path (str, optional): 保存数据的路径，默认不保存

        Returns:
            pd.DataFrame: 详细数据
        """
        if save_dir:
            if not os.path.exists(save_dir):
                print("Error: dir path in function \"get_data\" not exists.")
            else:
                if save_dir.startswith('/'):
                    target_dir = save_dir
                else:
                    target_dir = os.path.abspath('.') + '/' + save_dir
                if not target_dir.endswith('/'):
                    target_dir += '/'
                    
                serial_data_file = target_dir+"serial_data.csv"
                
                self.data.to_csv(serial_data_file, index=False) 
        return self.data
            
    def get_param(self) -> pd.DataFrame:
        node_param = [{
            "node_id": NODE_ID,
            "arch": CPU_MICRO_ARCH,
            "core_num": CORE_NUM,
            "target_disk": MAIN_DISK,
            "target_net": MAIN_NET_INTERFACE
        }]
        return node_param
    
    
    def generate_additional_data(self):
        pass
    
    
    
