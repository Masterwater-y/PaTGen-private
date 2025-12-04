import pandas as pd

from collectors.center.center_constants import *

from collectors.center.tools.collector import Collector

from collectors.center.tools.tau.tau_collector import TAUCollector
from collectors.center.tools.ibmc.ibmc_collector import IBMCCollector
from collectors.center.tools.slurm.slurm_collector import SlurmCollector


class CenterCollector(Collector):
    def __init__(self) -> None:
        self.data = {}  
        self.is_collecting = False  # 是否正在执行数据采集
        self.sub_collectors = {"ibmc_collector": IBMCCollector(IBMC_INFO), "tau_collector": TAUCollector(),\
            "slurm_collector": SlurmCollector()}

        # 默认仅采集时序数据
        self.config_collectors(None)
        # self.config_collected_sets(None)

    
    def start_collection(self, interval=1) -> None:
        """启动各个采集器，开始采集数据

        Args:
            interval (int, optional): 采集时间间隔. Defaults to 1.
        """
        if self.is_collecting:
            print("error: start collection fails, collector is running.")
            return
        self.is_collecting = True
        for collector in self.sub_collectors.values():
            if not len(collector.collected_sets) == 0:
                print(f"start collector: {collector.name}")
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
        self.data = {}
        for collector in self.sub_collectors.values():
            if not len(collector.collected_sets) == 0:
                collector.data = {}
                collector.raw_data_proc(data_len)
                self.data[collector.name] = collector.data
        
        
        
    def get_data(self, save_dir:str=None) -> dict:
        """获取数据

        Args:
            save_path (str, optional): 保存数据的路径，默认不保存

        Returns:
            dict: 详细数据
        """
        if save_dir:
            print('save dir', os.path.realpath(save_dir))
            os.system(f"mkdir -p {save_dir}")
            
            if save_dir.startswith('/'):
                target_dir = save_dir
            else:
                target_dir = os.path.abspath('.') + '/' + save_dir
            if not target_dir.endswith('/'):
                target_dir += '/'
            
            for collector_type in self.data:
                if collector_type == "ibmc_collector":
                    self.save_ibmc_data(target_dir)
                elif collector_type == "tau_collector":
                    self.save_tau_data(target_dir)
                elif collector_type == "slurm_collector":
                    self.save_slurm_data(target_dir)
                
        return self.data

    def set_collected_task(self):
        pass
    
    def save_ibmc_data(self, dir_path: str):
        ibmc_data = self.data["ibmc_collector"]
        os.system(f"mkdir -p {dir_path}/ibmc")
        for ip in ibmc_data:
            ibmc_data[ip].to_csv(f"{dir_path}/ibmc/{ip}.csv", index=False)


    def save_tau_data(self, dir_path: str):          
        mpi_func_data = self.data["tau_collector"]["mpi_func"]
        user_events_data = self.data["tau_collector"]["user_events"]
        #print(f'mpi_func_data: {mpi_func_data.keys()}')

        for task_id in mpi_func_data:
            #print(f'{task_id}, mpi_func_data: {mpi_func_data[task_id].keys()}')
            for ip in mpi_func_data[task_id]:
                for rank in mpi_func_data[task_id][ip]:
                    target_dir = f"{dir_path}/tau/{task_id}/{ip}/{rank}"
                    os.system(f'mkdir -p {target_dir}')
                    mpi_func_data[task_id][ip][rank].to_csv(f"{target_dir}/mpi_func.csv", index=False)
                    user_events_data[task_id][ip][rank].to_csv(f"{target_dir}/user_events.csv", index=False)
        
    
    def save_slurm_data(self, dir_path: str):
        slurm_data = self.data["slurm_collector"]
        os.system(f"mkdir -p {dir_path}/slurm")
        slurm_data[ip].to_csv(f"{dir_path}/slurm/slurm.csv", index=False)
