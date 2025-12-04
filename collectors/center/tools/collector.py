import pandas as pd
import numpy as np
from collectors.center.center_constants import *


# 采集器的父类
class Collector:
    def __init__(self, name:str, tool_layer: str, avail_sets: dict, data_type: str) -> None:
        self.name = name  # 采集器的名称
        self.tool_layer = tool_layer  # 采集的是哪一层级的数据，包括mpi、server、slurm等
        self.avail_sets = avail_sets  # 可采集的指标集，以及该指标集包含的指标名列表
        self.data = {}  # 采集到的原始数据
        self.data_type = data_type  # 采集的数据类型，时序数据还是聚合数据
        self.collected_sets = list(self.avail_sets.keys())  # 需要采集的指标集

    def config_collected_sets(self, targer_sets=None):
        if targer_sets is None:
            self.collected_sets = list(self.avail_sets.keys())
        else:
            if type(targer_sets) is not list: 
                print("error: 'target_sets' in function 'config_collected_sets' should be a list.")
            for data_set in targer_sets:
                if data_set not in self.avail_sets.keys():
                    print(f"error: {data_set} is not legal set in {self.name}.")
            self.collected_sets = targer_sets
    

