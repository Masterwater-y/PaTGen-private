import pandas as pd
import numpy as np
from collectors.node.node_constants import *


# 采集器的父类
class Collector:
    def __init__(self, name:str, tool_layer: str, avail_sets: dict, data_type: str) -> None:
        self.name = name  # 采集器的名称
        self.tool_layer = tool_layer  # 采集的是哪一层级的数据，包括mpi、server、slurm等
        self.avail_sets = avail_sets  # 可采集的指标集，以及该指标集包含的指标名列表
        self.data = pd.DataFrame()  # 采集到的原始数据
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
            
    def concat_new_data(self, new_df, is_sub=0):
        if is_sub:
            concat_method = SUBCOLLECTOR_DEFAULT_CONCAT_METHOD
        else:
            concat_method = DEFAULT_CONCAT_METHOD
        
        if self.data.empty:
            self.data = new_df
        elif concat_method == "left":
            self.data = pd.merge(self.data, new_df, on="time", how="left")
        elif concat_method == "inner":
            self.data = pd.merge(self.data, new_df, on="time", how="inner")
        elif concat_method == "outer":
            self.data = pd.merge(self.data, new_df, on="time", how="outer")
        elif concat_method == "construct":
            # 构造缺失数据函数
            def construct_missing_data(missing_time_stamp, data, columns_name):
                if missing_time_stamp > data["time"][0] and missing_time_stamp < data["time"][len(data)-1]:
                        insert_index = data[data["time"]==missing_time_stamp+1].index.tolist()
                        if insert_index and missing_time_stamp - data["time"][insert_index[0]-1] == 1:
                            insert_index = insert_index[0]
                            insert_value = (data.loc[insert_index-1] + data.loc[insert_index])/2
                            data = pd.DataFrame(np.insert(data.values, insert_index, values=insert_value, axis=0))
                            data.columns = columns_name
                return data
            # 获取所有时间戳
            time_stamp_range = set(self.data["time"]) | set(new_df["time"])
            time_stamp_range.sort() 
            # 执行替换
            for time_stamp in time_stamp_range:
                if time_stamp not in new_df["time"].values:
                    new_df = construct_missing_data(time_stamp, new_df, new_df.columns)
            # 合并数据
            self.data = pd.merge(self.data, new_df, on="time", how="inner")

