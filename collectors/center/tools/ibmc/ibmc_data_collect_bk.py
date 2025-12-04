import sys
import argparse
import signal
import os
import time
from connector import Connector

def sig_handler(signum, frame):
    global controller
    controller.stop = True


class Controller():
# 实例化一个http连接对象
    def __init__(self, ibmc_dict) -> None:
        self.conn = Connector(**ibmc_dict)
        # 获取X-Auth-Token和resource_id,并保存带session中
        self.conn.connect()
        # 获取机箱集合chassis资源的url
        self.chassis_meta = self.conn.request('GET', self.conn.chassis_base_url).json()
        # 获取指定机箱chassis资源的url
        self.chassis_power_url = self.conn.get_url(self.chassis_meta['Power']['@odata.id'])
        # self.chassis_voltage_url = self.conn.get_url(self.chassis_meta['Voltage']['@odata.id'])
        self.stop = False
        
    
    def get_timestamp(self):
        pass

    def get_power_data(self):
        global address
        power_request = self.conn.request('GET', self.chassis_power_url)
        raw_power_data = power_request.json()
        power = int(raw_power_data['PowerControl'][0]['PowerConsumedWatts'])
        if raw_power_data['PowerControl'][0]['Oem']['Huawei']['PowerMetricsExtended']\
            ['CurrentCPUPowerWatts'] is None:
                cpu_power = -1
                memory_power = -1
        else:
            cpu_power = int(raw_power_data['PowerControl'][0]['Oem']['Huawei']['PowerMetricsExtended']\
                ['CurrentCPUPowerWatts'])
            memory_power = int(raw_power_data['PowerControl'][0]['Oem']['Huawei']['PowerMetricsExtended']\
                ['CurrentMemoryPowerWatts'])
        os.system(f"echo {power} {cpu_power} {memory_power} >> data/{address}/power")
        
    def close(self):
        self.conn.disconnect()


if __name__ == '__main__':
    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGQUIT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)
    parser = argparse.ArgumentParser()
    parser.add_argument('--ibmc','-i',type=str, required=True)
    parser.add_argument('--time','-t',type=int, required=True)
    parser.add_argument('--sets','-s',type=str, required=True)
    parser.add_argument('--interval','-l',type=int, required=True)
    parser.add_argument('--address','-a',type=str, required=True)
    args = parser.parse_args()
    interval = args.interval
    max_time = args.time
    address = args.address
    ibmc_dict = eval(args.ibmc)
    collected_sets = eval(args.sets)
    
    
    os.system(f"echo {os.getpid()} > data/pid/{address}")
    os.system(f"mkdir data/{address}")
    os.system(f"cat /dev/null > data/{address}/power")
    os.system(f"cat /dev/null > data/{address}/time")
    controller = Controller(ibmc_dict)
    collected_time = 0
    last_record_timestamp = 0
    while(not controller.stop and collected_time < max_time):
        start_timestamp = time.time()
        collected_time += interval
        while True:
            try: 
                for data_set in collected_sets:
                    if data_set == "power":
                        controller.get_power_data()
                end_timestamp = time.time()
                if int(end_timestamp) == last_record_timestamp:
                    error = 1 / 0
                last_record_timestamp = int(end_timestamp)
                os.system(f"echo {int(end_timestamp)} >> data/{address}/time")
                sleep_time = interval - end_timestamp + start_timestamp
                if sleep_time < 0:
                    sleep_time = 0
                time.sleep(sleep_time)
                break
            except Exception as e:
                time.sleep(0.2)
            
        
    controller.close()
