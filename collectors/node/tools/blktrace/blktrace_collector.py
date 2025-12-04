import pandas as pd
import time
import os
import math

from collectors.node.tools.collector import Collector
from collectors.node.node_constants import *
from collectors.node.tools.blktrace.data_proc import *


# block io的数据采集工具，目前还没整合到上层的采集器中
class BlktraceCollector(Collector):
    def __init__(self) -> None:
        self.proced_timestamp = 0
        super().__init__(
            name = "blktrace_collector",
            data_type = "aggregate",
            tool_layer = "disk",
            avail_sets = {
                "event_latency": ['Q2Q_min', 'Q2Q_avg', 'Q2Q_max', 'Q2Q_num', 'Q2G_min', 'Q2G_avg', 
                                    'Q2G_max', 'Q2G_num', 'G2I_min', 'G2I_avg', 'G2I_max', 'G2I_num', 
                                    'Q2M_min', 'Q2M_avg', 'Q2M_max', 'Q2M_num', 'I2D_min', 'I2D_avg', 
                                    'I2D_max', 'I2D_num', 'M2D_min', 'M2D_avg', 'M2D_max', 'M2D_num', 
                                    'D2C_min', 'D2C_avg', 'D2C_max', 'D2C_num', 'Q2C_min', 'Q2C_avg', 
                                    'Q2C_max', 'Q2C_num'],
                "event_overhead": ['Q2G_overhead', 'G2I_overhead', 'Q2M_overhead', 'I2D_overhead', 
                                    'D2C_overhead'],
                "device_merge": ["receive_rq_num", "send_rq_num", "merge_ratio", "block_min", "block_avg", 
                                    "block_max", "block_total"],
                "device_seek": ["q2q_seek_num", "q2q_seek_mean", "q2q_seek_median", 
                                "d2d_seek_num", "d2d_seek_mean", "d2d_seek_median"],
                "device_plug": ["plug_num", "plug_time_us", "plug_time_ratio", "ios/unplug", 
                                "ios/unplug(timeout)"],
                "active_request": ["rq_growth"]
            }
        )
    
    def start_collection(self, interval=1):
        cur_dir = os.path.abspath('.')
        os.chdir(os.path.split(os.path.realpath(__file__))[0])
        if not os.path.exists("data/pid"):
            os.system("mkdir -p data/pid")
            os.system("mkdir -p data/raw")
            os.system("mkdir -p data/parse")
        self.end_collection()
        if not len(self.collected_sets) == 0:
            os.system(f"nice -n -20 ./blktrace.sh -d /dev/{MAIN_DISK} \
                -i {BLKTRACE_INTERVAL} -t {MAX_COLLECTED_TIME} > /dev/null &")
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
        os.chdir(os.path.split(os.path.realpath(__file__))[0]+"/data")
        self.get_aggregate_data(data_len)
        self.transfer_aggregate_to_serial()
        os.chdir(cur_dir)
                
    
    def get_aggregate_data(self, data_len):
        target_file_num = math.ceil(data_len / BLKTRACE_INTERVAL)
        count = 0
        # 处理数据
        target_proced_timestamp = None
        for item in sorted(os.listdir("./raw"), reverse=True):
            if count >= target_file_num:
                break
            # 已经处理过blktrace数据不需要生成svg
            if not int(item) <= self.proced_timestamp:
                os.system(f"mkdir -p ./parse/{item}")
                os.system(f"blkparse -D ./raw/{item} -i {MAIN_DISK} -d ./parse/{item}/{MAIN_DISK}.blktrace.bin > /dev/null")
                os.system(f"btt -i ./parse/{item}/{MAIN_DISK}.blktrace.bin -o ./parse/{item}/{MAIN_DISK} > /dev/null")
            # 如果没有文件说明这段blktrace的数据还在采集，因此跳过
            if not os.path.exists(f"./parse/{item}/{MAIN_DISK}.avg"):
                continue
            count += 1
            svg_data = os.popen(f"cat ./parse/{item}/{MAIN_DISK}.avg").read().splitlines()
            svg_file_data = svg_file_cal(svg_data, self.collected_sets, self.avail_sets)
            if target_proced_timestamp is None:
                target_proced_timestamp = int(item)
            svg_file_data.insert(0, "time", item)
            if self.data.empty:
                self.data = svg_file_data
            else:
                self.data = pd.concat([svg_file_data, self.data], ignore_index=True)
        self.proced_timestamp = target_proced_timestamp
        self.data.fillna(0, inplace=True)
        attr_list = ["time"]+[item for sublist in self.avail_sets.values() for item in sublist]
        self.data = self.data.reindex(columns=attr_list)

        if self.data.shape[1] != len(attr_list):
            print(f"Warning: blktrace data length does not match. Data length: {self.data.shape[1]}")
    
    def transfer_aggregate_to_serial(self):
        serial_data = pd.DataFrame()
        for idx, row in self.data.iterrows():
            try:
                time_sequence = range(int(row["time"]), int(self.data.loc[idx+1, "time"]))
            except KeyError:
                time_sequence = range(int(row["time"]), int(row["time"])+BLKTRACE_INTERVAL)
            df_filled = pd.DataFrame({"time": time_sequence})
            for col in self.data.columns:
                if col != "time":
                    df_filled[col] = row[col]
            if serial_data.empty:
                serial_data = df_filled
            else:
                serial_data = pd.concat([serial_data, df_filled], ignore_index=True)
        self.data = serial_data


