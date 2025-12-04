import os
import pandas as pd


# 处理perf采集到的数据
def perf_cal(collect_time, target_set, target_perf_events):
    # 获取perf的启动时间
    perf_time_cmd =f"head -n 1 data/perf_{target_set} | cut -d ' ' -f 4- | xargs -I {{}} date -d \"{{}}\" +%s"
    perf_time = os.popen(perf_time_cmd).read()
    # 取出perf的性能计数器的值
    perf_cmd = f"tail -n +4 data/perf_{target_set} | grep -v '^#' | tail -n {{}} |"\
            .format(len(target_perf_events)*collect_time)+ "awk '{if ($2!=\"#\") print $1, $2}'"
    perf = os.popen(perf_cmd).read().splitlines()
    result = list()

    # 构造出perf的数据，每一秒的数据为一个列表
    count = 0
    while count < len(perf):
        result_one = list()
        result_one.append(int(float(perf[count].split()[0]))+int(perf_time))
        result_one.extend([ info.split()[1].replace(',', '') for info in perf[count:count+len(target_perf_events)] ])
        count = count + len(target_perf_events)
        result.append(list(map(int, result_one)))
    result = pd.DataFrame(result)
    result.columns = ["time"]+target_perf_events
    return result

