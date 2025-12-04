import os
import json

import pandas as pd




def clock_to_timestamp(target_name, device_name, df):
    device_id = device_name.split("_")[1]
    data_dir = f"./data/raw/{target_name}/{device_name}"
    with open(f"{data_dir}/start_info.{device_id}") as fp:
        start_info =  json.load(fp)
    start_time = int(start_info["collectionTimeBegin"][:-6])
    start_clock = int(start_info["clockMonotonicRaw"][:-9])
    df["time"] = df["time"] - start_clock + start_time
    return df
        

def ddr_timeline_data_cal(target_name, device_name):
    device_id = device_name.split("_")[1]
    data_dir = f"./data/raw/{target_name}/{device_name}"
    with open(f"{data_dir}/timeline/ddr_{device_id}_1.json") as fp:
        ddr_data =  json.load(fp)
        
    result = pd.json_normalize(
        [{
            "time": int(float(item["ts"]) // 1e6),
            f"{device_name}_{item['name']}(mb/s)": float(list(item["args"].values())[0])
        } for item in ddr_data[1:]]
    )
    # 由于Read指标同一条数据会出现两次，因此这里进行去重
    result = result.drop_duplicates()
    result = result.groupby('time').mean().reset_index()
    return result
    

def ai_core_util_cal(target_name, device_name):
    device_id = device_name.split("_")[1]
    data_dir = f"./data/raw/{target_name}/{device_name}"
    with open(f"{data_dir}/timeline/ai_core_utilization_{device_id}_1.json") as fp:
        ai_core_util_data =  json.load(fp)
        
    result = pd.json_normalize(
        [{
            "time": int(float(item["ts"]) // 1e6),
            f"{device_name}_ai{item['name']}_util": float(item["args"]["Utilization(%)"])
        } for item in ai_core_util_data[1:]]
    )
    
    result = result.groupby('time').mean().reset_index()
    return result


def llc_aicpu_cal(target_name, device_name):
    device_id = device_name.split("_")[1]
    data_dir = f"./data/raw/{target_name}/{device_name}"
    with open(f"{data_dir}/timeline/llc_aicpu_{device_id}_1.json") as fp:
        llc_aicpu_data =  json.load(fp)
        
    result = pd.json_normalize(
        [{
            "time": int(float(item["ts"]) // 1e6),
            f"{device_name}_aicpu_{item['name']}_llc_occupation(MB)": float(item["args"]["Capacity(MB)"])
        } for item in llc_aicpu_data[1:]]
    )
    result = result.groupby('time').sum().reset_index()
    return result

def llc_ctrlcpu_cal(target_name, device_name):
    device_id = device_name.split("_")[1]
    data_dir = f"./data/raw/{target_name}/{device_name}"
    with open(f"{data_dir}/timeline/llc_ctrlcpu_{device_id}_1.json") as fp:
        llc_ctrlcpu_data =  json.load(fp)
        
    result = pd.json_normalize(
        [{
            "time": int(float(item["ts"]) // 1e6),
            f"{device_name}_ctrlcpu_{item['name']}_llc_occupation(MB)": float(item["args"]["Capacity(MB)"])
        } for item in llc_ctrlcpu_data[1:]]
    )
    result = result.groupby('time').sum().reset_index()
    return result 


def msprof_serial_data_cal(target_name):
    device_list = os.listdir(f"./data/raw/{target_name}")
    result = pd.DataFrame()
    for device_name in device_list:
        ddr_info = ddr_timeline_data_cal(target_name, device_name)
        ai_core_util_info = ai_core_util_cal(target_name, device_name)
        llc_aicpu_info = llc_aicpu_cal(target_name, device_name)
        llc_ctrlcpu_info = llc_ctrlcpu_cal(target_name, device_name)
        merged_df = pd.merge(ddr_info, ai_core_util_info, on='time', how='inner')
        merged_df = pd.merge(merged_df, llc_aicpu_info, on='time', how='inner')
        merged_df = pd.merge(merged_df, llc_ctrlcpu_info, on='time', how='inner')
        merged_df = clock_to_timestamp(target_name, device_name, merged_df)
        
        if result.empty:
            result = merged_df
        else:
            result = pd.merge(result, merged_df, on="time", how='inner')
    
    result.columns = result.columns.str.replace(" ", "").str.lower()
    return result



def pmu_events_cal(target_name, device_name):
    device_id = device_name.split("_")[1]
    data_dir = f"./data/raw/{target_name}/{device_name}"
    result = pd.DataFrame()
    ai_cpu_pmu_data = pd.read_csv(f"{data_dir}/summary/ai_cpu_pmu_events_{device_id}_1.csv")
    ctrl_cpu_pmu_data = pd.read_csv(f"{data_dir}/summary/ctrl_cpu_pmu_events_{device_id}_1.csv")
    ts_cpu_pmu_data = pd.read_csv(f"{data_dir}/summary/ts_cpu_pmu_events_{device_id}_1.csv")
    result.loc[0, f"{device_name}_aicpu_inst_retired"] = \
        ai_cpu_pmu_data.loc[ai_cpu_pmu_data['Name'] == 'Inst_retired', 'Count'].values[0]
    result.loc[0, f"{device_name}_aicpu_cpu_cycles"] = \
        ai_cpu_pmu_data.loc[ai_cpu_pmu_data['Name'] == 'Cpu_cycles', 'Count'].values[0]
    result.loc[0, f"{device_name}_ctrlcpu_inst_retired"] = \
        ctrl_cpu_pmu_data.loc[ctrl_cpu_pmu_data['Name'] == 'Inst_retired', 'Count'].values[0]
    result.loc[0, f"{device_name}_ctrlcpu_cpu_cycles"] = \
        ctrl_cpu_pmu_data.loc[ctrl_cpu_pmu_data['Name'] == 'Cpu_cycles', 'Count'].values[0]
    result.loc[0, f"{device_name}_tscpu_inst_retired"] = \
        ts_cpu_pmu_data.loc[ts_cpu_pmu_data['Name'] == 'Inst_retired', 'Count'].values[0]
    result.loc[0, f"{device_name}_tscpu_cpu_cycles"] = \
        ts_cpu_pmu_data.loc[ts_cpu_pmu_data['Name'] == 'Cpu_cycles', 'Count'].values[0]
    return result


def aggregate_to_serial(target_name, device_name, df):
    device_id = device_name.split("_")[1]
    data_dir = f"./data/raw/{target_name}/{device_name}"
    with open(f"{data_dir}/start_info.{device_id}") as fp:
        start_info =  json.load(fp)
    with open(f"{data_dir}/end_info.{device_id}") as fp:
        end_info =  json.load(fp)
    start_time = int(start_info["collectionTimeBegin"][:-6])
    end_time = int(end_info["collectionTimeEnd"][:-6])

    time_sequence = range(int(start_time), int(end_time))
    df_filled = pd.DataFrame({"time": time_sequence})
    for col in df.columns:
        if col != "time":
            df_filled[col] = df.loc[0, col]

    return df_filled


def msprof_aggregate_data_cal(target_name):
    device_list = os.listdir(f"./data/raw/{target_name}")
    result = pd.DataFrame()
    for device_name in device_list:
        pmu_events_info = pmu_events_cal(target_name, device_name)
        pmu_events_info = aggregate_to_serial(target_name, device_name, pmu_events_info)
        if result.empty:
            result = pmu_events_info
        else:
            result = pd.merge(result, pmu_events_info, on="time", how='inner')
    return result