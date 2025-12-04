import configparser
import json

from constants import *



# 读取配置文件
conf = configparser.ConfigParser()
conf.read(f"{WORK_DIR}/conf/global.conf")
DEFAULT_CONCAT_METHOD = conf.get("collectors", "default_concat_method")
SUBCOLLECTOR_DEFAULT_CONCAT_METHOD = conf.get("collectors", "subcollector_default_concat_method")
MAX_COLLECTED_TIME = int(conf.get("collectors", "max_collected_time"))
TAU_PROFILE_PATH = conf.get("collectors", "tau_profile_path")
TASK_ID = conf.get("collectors", "task_id")
PROFILE_PATH = os.path.join(TAU_PROFILE_PATH, f"log.{TASK_ID}")

NODE_IPS = conf.get('connections', 'node_ips').split(',')
COMM_PORT = conf.get('connections', 'port')
NODE_INFO = []
for ip in NODE_IPS:
    NODE_INFO.append({'name':ip.split('.')[-1], 'ip':ip, 'port':int(COMM_PORT)})
    
with open(f"{WORK_DIR}/conf/ibmc.json", 'r') as json_file:
    json_str = json_file.read()
IBMC_INFO = json.loads(json_str)
IBMC_INFO = {key: value for key, value in IBMC_INFO.items() if key in NODE_IPS}
