import pandas as pd
import subprocess
import time
import json

import numpy as np
from scipy.stats import mannwhitneyu
from scipy.stats import variation
from sklearn.cluster import DBSCAN
import matplotlib.pyplot as plt
def returnTime(func):
    def wrapperStartBenchmark(self, param_set):
        begin = int(time.time())
        func(self, param_set)
        end = int(time.time())
        return [begin, end]
    return wrapperStartBenchmark

def save_json(file_path,data):
    try:
        with open(file_path, 'w+') as file:
            json.dump(data, file, indent=4)
    except FileNotFoundError:
        print("错误: 文件未找到!")
    except json.JSONDecodeError:
        print("错误: 无法解析 JSON 文件!")
    except Exception as e:
        print(f"错误: 发生了一个未知错误: {e}")

def run_command(command):
    try:
        # 执行命令
        subprocess.run(command, shell=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Command '{command}' failed with error: {e}")
        return False
    
def calculate_absolute_similarity(result_val, target_val, max_range=100):
    if result_val<1:
        result_val *=100
    abs_error = abs(result_val - target_val)
    similarity = 1.0 - (abs_error / max_range)
    return max(0.0, similarity)

def calculate_relative_similarity(result_val, target_val):
    if target_val == 0:
        return 1.0 if result_val == 0 else 0.0
    return max(0.0, 1.0 - abs(result_val - target_val) / abs(target_val))

def calculate_variance(values):
    """计算数值列表的方差，示例：输入[99,98]会转换为[1,2]后计算方差"""
    # 转换为与目标值的差异值（示例逻辑）
    diff_values = [100 - v for v in values]
    # 计算方差
    return np.var(diff_values, ddof=1)  # ddof=1使用样本方差

def calculate_mse_pearson(self, series1, series2):
    """计算MSE和Pearson相关系数"""
    mse = ((series1 - series2)**2).mean()
    pearson = series1.corr(series2)
    return mse, pearson
def calculate_dtw(self, series1, series2):
    """计算动态时间规整距离"""
    from dtw import dtw
    return dtw(
        series1.values.reshape(-1,1), 
        series2.values.reshape(-1,1),
        keep_internals=True
    ).distance


def detect_global_outliers(series, factor=10, force_threshold=10, force_clip=True):
    """
    返回两个 mask：
        mask: 短异常段（> factor*mean）
        force_mask: 大于 force_threshold 的点（是否启用由 force_clip 控制）
    """
    mean_val = series.mean()
    if mean_val == 0:
        return pd.Series([False]*len(series), index=series.index), pd.Series([False]*len(series), index=series.index)

    s = series.values
    mask = (s > factor * mean_val)
    force_mask = (s > force_threshold) if force_clip else np.zeros_like(s, dtype=bool)
    verbose = False
    if verbose:
        for i in range(len(s)):
            if mask[i] or force_mask[i]:
                print(f"Index: {i}, Value: {s[i]}, Mean: {mean_val:.4f}")
    return pd.Series(mask, index=series.index), pd.Series(force_mask, index=series.index)


def suppress_short_outlier_segments(mask, max_len=3):
    """
    取消连续 >= max_len 的异常段标记
    """
    m = mask.copy().values
    N = len(m)
    i = 0

    while i < N:
        if not m[i]:
            i += 1
            continue

        start = i
        while i < N and m[i]:
            i += 1
        end = i - 1

        seg_len = end - start + 1

        if seg_len >= max_len:
            m[start:end+1] = False

    return pd.Series(m, index=mask.index)


def smooth_isolated_outliers(df, target_cols, factor=10, force_threshold=10,
                              force_clip=False, fluctuation_ratio=0.05):
    RELATED_COLS = [
        "cycles", "instructions", "L1-misses", "ll-misses/",
        "CPI", "MPKI", "MPKI_L1",
        "power", "branches", "branch-misses", "branch-misses-ratio"
    ]

    df_new = df.copy()
    short_mask_total = pd.Series(False, index=df.index)
    force_mask_total = pd.Series(False, index=df.index)
    for col in target_cols:
        mask, force_mask = detect_global_outliers(df[col], factor, force_threshold, force_clip)
        short_mask_total |= mask
        force_mask_total |= force_mask

    short_mask_total = short_mask_total & (~force_mask_total)
    to_smooth = suppress_short_outlier_segments(short_mask_total, max_len=4)
    final_mask = to_smooth | force_mask_total
    for col in RELATED_COLS:
        mean_val = df[col].mean()
        std_val = df[col].std()
        noise = np.random.randn(final_mask.sum()) * std_val * fluctuation_ratio
        df_new.loc[final_mask, col] = mean_val + noise

    return df_new

def process_special_boundaries(block_list, target):
    processed_blocks = block_list.copy()
    if len(processed_blocks) == 1:
        block = processed_blocks[0]

        if 'duration' in block and 'duration' in target:
            block['template'][2] = block['template'][2] * target['duration'] / block['duration']
            block['duration'] = target['duration']
    
    return processed_blocks

def transform_targets(final_aggr):
    df = final_aggr
    # 筛选aggr_type为final的行
    final_df = df[df['aggr_type'] == 'final']
    
    # 定义字段映射关系
    column_mapping = {
        'duration': 'duration',
        'cpu_util': 'cpu_util',
        'mem_util': 'mem_util',
        'CPI': 'CPI',
        'MPKI': 'MPKI',
        'disk_util': 'disk_util',
        'power': 'power'
    }
    
    # 创建目标DataFrame
    output_df = final_df.rename(columns=column_mapping)[list(column_mapping.values())]
    
    # 添加缺失的列
    output_df['mem_capacity'] = 256
    output_df['mem_size'] = 16
    
    # 调整列顺序
    output_df = output_df[['duration', 'cpu_util', 'mem_util', 'CPI', 'MPKI', 'disk_util', 'power', 'mem_capacity', 'mem_size']]
    

    return output_df

def calc_target(df):
    total_cycles = df["cycles"].sum()
    total_insts = df["instructions"].sum()
    total_llc_miss = df["ll-misses/"].sum()

    # 避免除零
    if total_insts == 0:
        cpi = 0
        mpki = 0
    else:
        cpi = total_cycles / total_insts
        mpki = total_llc_miss * 1000 / total_insts

    row = {
        "duration": len(df),
        "cpu_util": df["cpu_util"].mean(),
        "mem_util": df["mem_util"].mean(),
        "CPI": cpi,
        "MPKI": mpki,
        "disk_util": df["disk_util"].mean(),
        "power": df["power"].mean(),
        "mem_capacity": 256,   # 固定
        "mem_size": 16         # 固定
    }

    # 返回 DataFrame，方便 to_csv
    return pd.DataFrame([row])

def evaluate_results(res_def, target_def):
    """
    评估结果数据与目标数据的相似度
    
    参数:
    res_def (DataFrame): 结果数据
    target_def (DataFrame): 目标数据
    
    返回:
    DataFrame: 包含相似度计算结果的DataFrame
    """
    # 定义列映射和计算方法
    mapping = {
        'cpu_util': (lambda t, r: r * 100, 'relative'),
        'mem_util': (lambda t, r: r * t['mem_capacity'] / t['mem_size'] * 100, 'relative'),
        'disk_util': (lambda t, r: r * 100, 'relative'),
        'duration': (None, 'relative'),
        'CPI': (None, 'relative'),
        'MPKI': (None, 'relative'),
        'power': (None, 'relative'),
    }
    
    # 处理结果数据
    res_processed = res_def.copy()
    for col in mapping.keys():
        transformer, _ = mapping[col]
        if transformer:
            # 带上下文的数据转换（使用目标数据和结果数据）
            res_processed[col] = res_def.apply(
                lambda row: transformer(target_def.loc[row.name], row[col]),
                axis=1
            )
    
    # 确定相似度计算策略
    similarity_strategy = {
        col: (calculate_absolute_similarity if sim_type == 'absolute' 
              else calculate_relative_similarity)
        for col, (_, sim_type) in mapping.items()
    }
    
    # 计算相似度
    sim_data = {}
    for col, strategy in similarity_strategy.items():
        # 获取对齐后的数据对
        res_values = res_processed[col]
        target_values = target_def[col]
        
        # 执行相似度计算
        sim_values = [
            strategy(res, target) 
            for res, target in zip(res_values, target_values)
        ]
        sim_data[f"{col}"] = sim_values

    
    # 创建结果DataFrame
    sim_df = pd.DataFrame(sim_data, index=res_def.index)
    
    # 添加平均行
    avg_row = pd.DataFrame(sim_df.mean(axis=0).to_dict(), index=['Average'])
    sim_df = pd.concat([sim_df, avg_row])
    var_row = pd.DataFrame(sim_df.var(axis=0).to_dict(), index=['Variance'])
    sim_df = pd.concat([sim_df, var_row])
    return sim_df


def stage_divide(data, alg='window',args=None,png_path = None):
    import ruptures as rpt
    import pandas as pd
    import os
    sample_phase_num = [16,8,3,4,11]
    timestamps = data['time']
    metrics_df = data[['CPI', 'MPKI']]
    
    if alg == 'window':
        WINDOW_SIZE = 20  # 滑动窗口大小
        STEP = 1          # 滑动步长
        SIGNIFICANCE_LEVEL = 0.1 # 显著性水平
        MIN_METRICS = 1     # 触发变点的最小指标数
        CLUSTER_EPS = 2    # 变点合并的聚类半径
        # 读取数据

        metrics_df = (metrics_df - metrics_df.mean()) / metrics_df.std()
        # 检测候选变点
        candidates = []
        for start in range(0, len(metrics_df) - WINDOW_SIZE + 1, STEP):
            end = start + WINDOW_SIZE
            window = metrics_df.iloc[start:end]
            midpoint = start + WINDOW_SIZE // 2
            detected = []
            for metric in ['CPI','MPKI']:
                series = window[metric].values
                split = len(series) // 2
                part1, part2 = series[:split], series[split:]
                try:
                    _, p_val = mannwhitneyu(part1, part2, alternative='two-sided')
                except ValueError:
                    p_val = 1.0
                if p_val < SIGNIFICANCE_LEVEL:
                    detected.append(metric)
            if len(detected) >= MIN_METRICS:
                candidates.append(midpoint)
        # 合并邻近变点
        if not candidates:
            print("未检测到变点")
            stages = [(0, len(metrics_df)-1)]
        else:
            candidates = np.array(candidates).reshape(-1, 1)
            clustering = DBSCAN(eps=CLUSTER_EPS, min_samples=1).fit(candidates)
            final_cps = []
            for label in set(clustering.labels_):
                if label == -1:
                    continue
                cluster_points = candidates[clustering.labels_ == label].flatten()
                final_cps.append(int(cluster_points.mean()))
            final_cps = sorted(final_cps)
            # 划分阶段
            stages = []
            prev = 0
            for cp in final_cps:
                stages.append((prev, cp))
                prev = cp
            stages.append((prev, len(metrics_df)-1))
    elif alg == 'pelt':
        # -----------------------------
        # 1. 从 metrics_df 构造自定义 cost 的 feature 序列
        # -----------------------------
        import numpy as np
        import pandas as pd
        from statsmodels.tsa.stattools import acf
        # metrics_df: shape (N, D)
        raw = metrics_df.values
        N, D = raw.shape
        # 可调参数
        window = args.get("window", min(20,N//10))      # 滑动窗口长度
        use_adf = args.get("use_adf", False) # 是否加ADF（默认关）
        penalty  = args.get("penalty", 3.0)  # PELT的pen



        feat_list = []
        feat_index_map = []   # 记录 feature 对应原始 index（窗口中心）

        # 滑动窗口构造 local features
        for i in range(N - window + 1):
            w = raw[i:i+window]    # shape (window, D)

            row = []
            for d in range(D):
                vec = w[:, d]
                mean = np.nanmean(vec)
                var  = np.nanvar(vec)
                std  = np.sqrt(var) + 1e-8
                cv   = std / (abs(mean) + 1e-8)

                # acf1
                try:
                    acf_val = acf(vec, nlags=1, fft=False)
                    acf1 = float(acf_val[1])
                except:
                    acf1 = 0.0

                row.extend([mean, var, cv, acf1])

            feat_list.append(row)
            feat_index_map.append(i + window - 1)

        feat = np.array(feat_list)     # shape = (N-window+1, 4D)
        M = len(feat)

        # -----------------------------
        # 2. 在 feature 序列上运行 PELT
        # -----------------------------
        algo = rpt.Pelt(model='l2', min_size=max(3, window//2)).fit(feat)
        cps_feat = algo.predict(pen=penalty)
        cps_feat = [cp for cp in cps_feat if cp < M]  # 去掉末尾点

        # 将 feature 时间轴的变点映射回原始时间轴
        cps = [ feat_index_map[cp] for cp in cps_feat if cp < len(feat_index_map) ]
        cps = sorted(list(set(cps)))

        # -----------------------------
        # 3. 构造 stages (与你原来一致)
        # -----------------------------
        print(cps)
        stages = []
        prev = 0
        for cp in cps:
            stages.append((prev, cp))
            prev = cp
        stages.append((prev, N - 1))

        # -----------------------------
        # 4. 画图（保持你原来风格）
        # -----------------------------
        if png_path is not None:
            fig, axes = plt.subplots(metrics_df.shape[1], 1, figsize=(12, 6), sharex=True)
            if metrics_df.shape[1] == 1:
                axes = [axes]

            for i, col in enumerate(metrics_df.columns):
                axes[i].plot(metrics_df[col].values)
                for cp in cps:
                    axes[i].axvline(cp, color="r", linestyle="--")
                axes[i].set_ylabel(col)

            plt.tight_layout()
            plt.savefig(png_path)

        return stages


    elif alg == 'fixed' or alg == 'sync':
        # 读取数据和时间戳
        timestamps = data['time']
        total_samples = len(timestamps)
        
        # 计算总时间（假设时间戳单位为秒）
        if isinstance(timestamps, pd.Series):
            timestamps = timestamps.values
        total_time = timestamps[-1] - timestamps[0]
        
        '''phase_num = args[0]
        phase_time_min = args[1]

        avg_time_per_stage = total_time / phase_num

        
        # 根据计算结果确定阶段划分策略
        if avg_time_per_stage > phase_time_min:
            # 情况1：均分为10个阶段
            interval = total_samples // phase_num
            split_points = [i * interval for i in range(1, phase_num)]
        else:
            # 情况2：每个阶段固定为10秒
            target_time_per_stage = phase_time_min
            num_stages = max(1, int(total_time // target_time_per_stage))  # 至少1个阶段
            split_points = []
            
            # 计算每个10秒对应的样本索引
            for i in range(1, num_stages):
                target_time = timestamps[0] + i * target_time_per_stage
                # 找到最接近目标时间的样本索引
                idx = np.searchsorted(timestamps, target_time)
                if idx < total_samples:
                    split_points.append(idx)'''
        '''phase_time = args[0]

        # 计算阶段数量
        num_stages = max(1, int(total_time // phase_time))  # 至少1个阶段
        split_points = []

        # 计算每个固定时间对应的样本索引
        for i in range(1, num_stages):
            target_time = timestamps[0] + i * phase_time
            # 找到最接近目标时间的样本索引
            idx = np.searchsorted(timestamps, target_time)
            if idx < total_samples:
                split_points.append(idx)'''
        if alg=='fixed':
            phase_num = args[0]
        elif alg=='sync':
            base_path = 'sota/stages/1213final'
            file_name = f"stage{args[0]}/aggr.csv"
            file_path = os.path.join(base_path, file_name)
            df = pd.read_csv(file_path)
            phase_num = int(len(df))
            #phase_num = 10
            print(phase_num)

        # 计算每个阶段的平均时间（仅用于参考，实际分割可能不均匀）
        avg_time_per_stage = total_time / phase_num

        # 直接按阶段数量均分样本
        interval = total_samples // phase_num
        split_points = [i * interval for i in range(1, phase_num)]
        final_cps = split_points

        
        # 生成阶段列表
        stages = []
        prev = 0
        for cp in split_points:
            stages.append((prev, cp))  # 前闭后闭区间
            prev = cp
        stages.append((prev, total_samples - 1))  # 最后一个阶段
    plt.figure(figsize=(12, 6))
    for i, metric in enumerate(['CPI', 'MPKI'], 1):
        plt.subplot(3, 1, i)
        plt.plot(timestamps, metrics_df[metric], label=metric)
        for cp in final_cps:
            plt.axvline(timestamps[cp], color='r', linestyle='--')
        plt.ylabel(metric)
        plt.legend()
    plt.tight_layout()
    plt.savefig(png_path)
    return stages