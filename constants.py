import os
import configparser

WORK_DIR = os.path.split(os.path.realpath(__file__))[0]
NODE_MAX_VALUE_FILE_PATH = WORK_DIR+"/data/node_data_value_range/max_value.json"
NODE_MIN_VALUE_FILE_PATH = WORK_DIR+"/data/node_data_value_range/min_value.json"

CORE_NUM = int(os.popen("cat /proc/cpuinfo  | grep processor | wc -l").read())


# 获取CPU微架构
cpu_arch_info = os.popen("uname -m").read().strip()
if cpu_arch_info == "x86_64":
    cpu_arch_num = os.popen("cat /proc/cpuinfo | grep -v 'model name' | grep 'family\\|model\\|stepping' | sort | uniq | rev | cut -d ':' -f 1").read().splitlines()
    cpu_arch_num = "".join(cpu_arch_num)
elif cpu_arch_info == "aarch64":
    cpu_arch_num = os.popen("cat /proc/cpuinfo | grep 'CPU part' | uniq | cut -d ':' -f 2").read().strip()
cpu_arch_list = {
    "6 58 5 ": "cascade_lake",
    "6 58 6 ": "cascade_lake",
    "6 58 7 ": "cascade_lake",
    "6 58 4 ": "skylake",
    "6 97 1 ":"sandy_bridge",
    "0xd01": "kunpeng920",
    "0xd08": "kunpeng916"
}
CPU_MICRO_ARCH = cpu_arch_list[cpu_arch_num]







