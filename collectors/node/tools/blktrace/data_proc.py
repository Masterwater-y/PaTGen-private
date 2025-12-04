from ast import Dict, List
import os
import pandas as pd
import re



def svg_file_cal(data, target_sets: List, set_attributes: Dict):
    result = {}
    
    # 确定每一组数据的位置
    split_line_num = []
    for i in range(len(data)):
        if re.search("===", data[i]):
            split_line_num.append(i)
    
    if "event_latency" in target_sets:
        all_device_data = data[split_line_num[0]: split_line_num[1]]
        for event_latency in all_device_data:
            all_device_suffix = ["_min", "_avg", "_max", "_num"]
            if re.match("^\w", event_latency):
                event_latency = event_latency.split()
                event_latency_result = {event_latency[0]+all_device_suffix[i]: event_latency[i+1] 
                                     for i in range(4)}
                result.update(event_latency_result)
        
    if "event_overhead" in target_sets:
        device_overhead_data = data[split_line_num[1]: split_line_num[2]]
        device_overhead_prefix = ["Q2G", "G2I", "Q2M", "I2D", "D2C"]
        for event_overhead in device_overhead_data:
            if re.search("Overall", event_overhead):
                event_overhead = event_overhead.split()
                event_overhead_result = {f"{device_overhead_prefix[i]}_overhead": 
                    float(event_overhead[i+2].strip("%"))/100 for i in range(5)}
                result.update(event_overhead_result)
    if "device_merge" in target_sets:
        device_merge_data = data[split_line_num[2]: split_line_num[3]]
        target_device_merge = None
        for device_merge in device_merge_data:
            if re.search("\(", device_merge):
                target_device_merge = device_merge
        target_device_merge = target_device_merge.split('|')
        device_merge_result = target_device_merge[1].strip().split() + target_device_merge[2].strip().split()
        device_merge_result = {set_attributes["device_merge"][i]: device_merge_result[i] 
                               for i in range(len(device_merge_result))}
        result.update(device_merge_result)
        
        
    if "device_seek" in target_sets:
        q2q_seek_data = data[split_line_num[3]: split_line_num[4]]
        d2d_seek_data = data[split_line_num[4]: split_line_num[5]]
        seek_result = []
        for q2q_seek in q2q_seek_data:
            if re.search("Average", q2q_seek):
                seek_result += q2q_seek.split('|')[1].strip().split()
        for d2d_seek in d2d_seek_data:
            if re.search("Average", d2d_seek):
                seek_result += d2d_seek.split('|')[1].strip().split()
        device_seek_result = {set_attributes["device_seek"][i]: seek_result[i] 
                              for i in range(len(seek_result))}
        result.update(device_seek_result)
        
    if "device_plug" in target_sets:
        device_plug_data = data[split_line_num[5]: split_line_num[6]]
        target_device_plug = None
        unplug = None
        device_plug_result = []
        for device_plug in device_plug_data:
            if re.search("%", device_plug):
                target_device_plug = device_plug
            elif re.search("Average", device_plug):
                unplug = device_plug
        if unplug is None:
            device_plug_result = {set_attributes["device_plug"][i]: 0 for i in range(len(set_attributes["device_plug"]))}
        else:
            target_device_plug = target_device_plug.split('|')
            device_plug_result += target_device_plug[1].replace("(", "").replace(")", "").split()
            device_plug_result.append(float(target_device_plug[2].strip().strip("%"))/100)
            device_plug_result += unplug.split('|')[1].split()
            device_plug_result = {set_attributes["device_plug"][i]: device_plug_result[i] 
                                for i in range(len(device_plug_result))}
        result.update(device_plug_result)
        
    
    if "active_request" in target_sets:
        active_request_data = data[split_line_num[6]: split_line_num[7]]
        target_active_request = None
        for active_request in active_request_data:
            if re.search("\(", active_request):
                target_active_request = active_request
        active_request_result = target_active_request.split('|')[1].strip().split()
        active_request_result = {set_attributes["active_request"][i]: active_request_result[i] 
                              for i in range(len(active_request_result))}
        result.update(active_request_result)
    result = pd.DataFrame(data=result, index=[0])
    return result



