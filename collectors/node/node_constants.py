from constants import *
import os
import configparser
import json


# 读取配置文件
conf = configparser.ConfigParser()
conf.read(f"{WORK_DIR}/conf/global.conf")
DEFAULT_CONCAT_METHOD = conf.get("collectors", "default_concat_method")
SUBCOLLECTOR_DEFAULT_CONCAT_METHOD = conf.get("collectors", "subcollector_default_concat_method")
MAX_COLLECTED_TIME = int(conf.get("collectors", "max_collected_time"))
BLKTRACE_INTERVAL = int(conf.get("collectors", "blktrace_interval"))
MSPROF_INTERVAL = int(conf.get("collectors", "msprof_interval"))


# 如果用户没有指定网卡和磁盘，流量最大的网卡和磁盘作为主网卡和主磁盘
if conf.get("collectors", "main_network") == "auto":
    MAIN_NET_INTERFACE = os.popen("ip route | grep default | awk '{print $5}' | head -n 1").read().strip() 
else:
    MAIN_NET_INTERFACE = conf.get("collectors", "main_network")
if conf.get("collectors", "main_disk") == "auto":
    MAIN_DISK = os.popen("cat /proc/diskstats | grep -e 'sd\\|vd\\|hd' | sort -nrk 14 | head -n 1 | awk '{{print $3}}'").read().strip()
else:
    MAIN_DISK = conf.get("collectors", "main_disk")

NODE_ID = os.popen(f"ip addr | grep {MAIN_NET_INTERFACE} | grep inet | awk '{{print $2}}'").read().strip().replace("/24", "")
CORE_NUM = int(os.popen("cat /proc/cpuinfo  | grep processor | wc -l").read())


NUMA_ZONE_NUM = int(os.popen("numactl --hardware | grep cpus | wc -l").read().strip()) # NUMA zone数量

COMM_PORT = conf.get('connections', 'port')

with open(f"{WORK_DIR}/conf/pmu_events.json", 'r') as json_file:
    json_str = json_file.read()
PMU_EVENTS = json.loads(json_str)

with open(f"{WORK_DIR}/conf/ibmc.json", 'r') as json_file:
    json_str = json_file.read()
IBMC_INFO = json.loads(json_str)
GPU_NUM = int(os.popen("nvidia-smi -L | wc -l").read().strip())

