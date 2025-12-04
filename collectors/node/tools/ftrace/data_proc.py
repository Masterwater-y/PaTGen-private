import os
import pandas as pd


def read_data(file_name, collect_time):
    file_len = int(os.popen(f"wc -l {file_name} | awk '{{print $1}}'").read().strip())
    scanned_row = 0
    scanned_timestamp = 0
    step = 1000
    
    result = []
    while(scanned_row < file_len and scanned_timestamp < collect_time):
        content = os.popen(f"tail -n {scanned_row+step} {file_name} | head -n {step}").read().strip()
        rows = content.splitlines()
        tmp_record = {}
        for i in range(len(rows)-1, -1, -1):
            if rows[i].isdigit():
                scanned_timestamp += 1
                tmp_record["time"] = int(rows[i])
                result.append(tmp_record)
                tmp_record = {}
                
            else:
                function_name, function_value = rows[i].split()
                tmp_record[function_name] = int(function_value)        
        
        scanned_row += step
    result.reverse()
    return result
    



def function_trace_cal(collect_time, target_sets, data_type_dict):
    function_trace_info = pd.DataFrame(read_data("data/function_trace", collect_time))
    function_trace_info = function_trace_info.loc[:, function_trace_info.columns[::-1]]
    function_trace_info = function_trace_info.fillna(int(0)).astype(int)
    
    result = pd.DataFrame(columns=["time"])

    for data_set in target_sets:
        if data_set == "mem_cache_hit":
            mem_cache_hit_info = mem_cache_hit_cal(function_trace_info, data_type_dict["mem_cache_hit"])   
            result = pd.merge(result, mem_cache_hit_info, on="time", how="right")     
    return result


def mem_cache_hit_cal(data, data_type):
    result = pd.DataFrame(columns=["time"]+data_type)
    result["time"] = data["time"]
    result["mem_cache_accesses"] = data["mark_page_accessed"] - data["mark_buffer_dirty"]
    result["mem_cache_access_misses"] = data["add_to_page_cache_lru"] - data["account_page_dirtied"]
    result["mem_cache_access_misses"] = result["mem_cache_access_misses"].\
        apply (lambda x: 0 if x < 0 else x)
    result["mem_cache_access_hits"] = result["mem_cache_accesses"] - result["mem_cache_access_misses"]
    result["mem_cache_access_hit_ratio"] = result["mem_cache_access_hits"] / result["mem_cache_accesses"].\
        apply(lambda x: 1 if x > 1 else x)

    return result

