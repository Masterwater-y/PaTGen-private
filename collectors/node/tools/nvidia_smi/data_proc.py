import os

from datetime import datetime
from collectors.node.node_constants import GPU_NUM

def read_data(file_name, collect_time):
    '''
    从尾部读取部分文件数据
    :param file_name: 文件路径
    :param collect_time: 需要读取的行数
    :return: 数据列表
    '''
    read_cmd = "tail  -n {} {}".format(collect_time, file_name)
    content = os.popen(read_cmd).read().strip()
    rows = content.splitlines()
    result_list = list()
    
    for row in rows:
        result_list.append(row.split())
    # result_list = np.array(result_list)
    return result_list



def gpu_data_cal(collect_time):
    gpu_data_info = read_data('data/gpu_data', collect_time)
    first = True
    result = list()
    temp_result = []
    
    for i in range(len(gpu_data_info)):
        if gpu_data_info[i][0].startswith("#"):
            continue
        try:
            gpu_idx = int(gpu_data_info[i][2])
        except Exception as e:
            print(e)
            print(gpu_data_info)
        # 第一个记录要从index为0的GPU开始
        if first:
            if gpu_idx == 0:
                first = False
            else:
                continue
            
        date_time = gpu_data_info[i][0]+"-"+gpu_data_info[i][1]
        time_obj = datetime.strptime(date_time, '%Y%m%d-%H:%M:%S')
        timestamp = datetime.timestamp(time_obj)
        
        if gpu_idx == 0:
            # 将一条数据增加到result中
            if len(temp_result) != 0:
                result.append(temp_result)
            temp_result = [timestamp]
        
        gpu_data_info[i] = [-1 if x == "-" else x for x in gpu_data_info[i][3:]]
        temp_result.extend(gpu_data_info[i])
    return result
        
    
