import os
import time
import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.decomposition import FastICA
from sklearn.cluster import KMeans
from sklearn.preprocessing import MinMaxScaler


# ============================================================
# Step 1: 自动读取目录内所有 CSV
# ============================================================
def load_all_traces(folder="./"):
    files = [f for f in os.listdir(folder) if f.endswith(".csv")]
    workloads = {}
    for f in files:
        df = pd.read_csv(os.path.join(folder, f))
        workloads[f] = df
    return workloads


# ============================================================
# Step 2: 计算 CPI & MPKI
# ============================================================
def compute_cpi_mpki(df):
    df = df.copy()
    df["CPI"] = df["cycles"] / df["instructions"]
    df["MPKI"] = df["armv8_pmuv3_0/ll_cache_miss/"] * 1000 / df["instructions"]
    return df


# ============================================================
# Step 3: 每个 workload 聚合成一行
# ============================================================
def aggregate_workloads(workloads, exclude_file):
    agg = []
    names = []

    for name, df in workloads.items():
        if name == exclude_file:
            continue

        df = compute_cpi_mpki(df)
        df_mean = df.mean(numeric_only=True)

        agg.append(df_mean)
        names.append(name)

    agg_df = pd.DataFrame(agg)
    agg_df.index = names
    return agg_df


# ============================================================
# Step 4: 修复列（缺失值填充 + Inf 转 NaN）
# ============================================================
def fix_columns(df):
    df = df.copy()

    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.fillna(df.mean())

    return df


# ============================================================
# Step 5: Normalize
# ============================================================
def normalize(df):
    scaler = MinMaxScaler()
    df_norm = pd.DataFrame(scaler.fit_transform(df), columns=df.columns, index=df.index)
    return df_norm


# ============================================================
# Step 6: SGBRT 特征选择（按 BEMAP）
# ============================================================
def select_top_features(df_norm, target="CPI", topN=12):
    X = df_norm.drop(columns=[target])
    y = df_norm[target]

    model = GradientBoostingRegressor(random_state=0)
    model.fit(X, y)

    importance = model.feature_importances_
    sorted_feats = sorted(zip(X.columns, importance), key=lambda x: x[1], reverse=True)

    top_features = [f[0] for f in sorted_feats[:min(topN, len(sorted_feats))]]
    return top_features


# ============================================================
# Step 7: ICA
# ============================================================
def apply_ica(df_norm, selected_feats):
    if len(selected_feats) < 2:
        return df_norm[selected_feats]

    ica = FastICA(n_components=len(selected_feats), random_state=0)
    X_ica = ica.fit_transform(df_norm[selected_feats])
    cols = [f"ICA_{i+1}" for i in range(len(selected_feats))]
    return pd.DataFrame(X_ica, columns=cols, index=df_norm.index)


# ============================================================
# Step 8: 误差计算
# ============================================================
def compute_error(agg_df, subset, target_cpi, target_mpki):
    subset_df = agg_df.loc[subset]

    avg_cpi = subset_df["CPI"].mean()
    avg_mpki = subset_df["MPKI"].mean()

    cpi_err = abs(avg_cpi - target_cpi) / target_cpi
    mpki_err = abs(avg_mpki - target_mpki) / target_mpki

    return avg_cpi, avg_mpki, cpi_err, mpki_err


# ============================================================
# Step 9: 显式枚举 k，选误差最小的 K
# ============================================================
def find_best_k(ica_df, agg_df, target_cpi, target_mpki, k_min=2, k_max=10):

    best_k = None
    best_err = 1e9
    best_subset = None

    for k in range(k_min, min(k_max, len(ica_df)) + 1):

        km = KMeans(n_clusters=k, random_state=0)
        labels = km.fit_predict(ica_df)

        reps = []

        # 为每个簇挑一个代表
        for c in range(k):
            idx = np.where(labels == c)[0]
            center = km.cluster_centers_[c]
            dist = np.linalg.norm(ica_df.iloc[idx].values - center, axis=1)
            rep = ica_df.index[idx[np.argmin(dist)]]
            reps.append(rep)

        # 计算误差
        _, _, cpi_err, mpki_err = compute_error(agg_df, reps, target_cpi, target_mpki)
        total_err = cpi_err + mpki_err

        # 更新最优 K
        if total_err < best_err:
            best_err = total_err
            best_k = k
            best_subset = reps

    return best_k, best_subset

def compute_serial_similarity(df_origin, df_proxy):
    from scipy.stats import pearsonr, spearmanr
    from dtw import dtw
    from fastdtw import fastdtw
    from scipy.spatial.distance import euclidean

    metrics = {}

    for col in ["CPI", "MPKI"]:
        x = df_origin[col].values
        y = df_proxy[col].values

        metrics[f"{col}_m"] = ((x - y) ** 2).mean()
        metrics[f"{col}_p"] = pearsonr(x, y)[0] if np.std(x) > 0 else np.nan
        metrics[f"{col}_s"] = spearmanr(x, y)[0] if np.std(x) > 0 else np.nan
        metrics[f"{col}_d"] = dtw(
            x.reshape(-1, 1),
            y.reshape(-1, 1)
        ).distance

    # ---------- NMSE ----------
    eps = 1e-10
    NMSE = (
        (((df_origin["CPI"]  - df_proxy["CPI"])  / (df_origin["CPI"]  + eps)) ** 2 +
         ((df_origin["MPKI"] - df_proxy["MPKI"]) / (df_origin["MPKI"] + eps)) ** 2)
    ).mean() / 2
    metrics["NMSE"] = NMSE

    # ---------- MDTW ----------
    full_data  = np.vstack([df_origin["CPI"], df_origin["MPKI"]]).T
    proxy_data = np.vstack([df_proxy["CPI"], df_proxy["MPKI"]]).T

    if len(full_data) > 1:
        metrics["mdtw"], _ = fastdtw(full_data, proxy_data, dist=euclidean)
    else:
        metrics["mdtw"] = np.nan

    # ---------- RS ----------
    mean_full = np.mean(full_data, axis=0).reshape(-1, 1)
    mean_sub  = np.mean(proxy_data, axis=0).reshape(-1, 1)
    std_full  = np.std(full_data, axis=0).reshape(-1, 1)
    std_sub   = np.std(proxy_data, axis=0).reshape(-1, 1)

    US = np.dot(mean_full.T, mean_sub)[0, 0] / (
        np.linalg.norm(mean_full) * np.linalg.norm(mean_sub)
    )
    DS = np.dot(std_full.T, std_sub)[0, 0] / (
        np.linalg.norm(std_full) * np.linalg.norm(std_sub)
    )

    metrics["RS"] = np.sqrt(US * DS)

    return metrics

# ============================================================
# 主流程
# ============================================================
def run(target_cpi, target_mpki, exclude_file):

    print("加载 CSV 文件 ...")
    workloads = load_all_traces("./perfs")

    print("聚合 workload ...")
    agg_df = aggregate_workloads(workloads, exclude_file)
    raw_df = agg_df.copy()

    print("清理 Inf 和缺失值（均值填充）...")
    agg_df = fix_columns(agg_df)

    print("归一化 ...")
    df_norm = normalize(agg_df)

    print("SGBRT 特征选择 ...")
    top_feats = select_top_features(df_norm, target="CPI")

    print("ICA ...")
    ica_df = apply_ica(df_norm, top_feats)

    print("枚举 K 寻找最优代表性子集 ...")
    best_k, reps = find_best_k(ica_df, raw_df, target_cpi, target_mpki)

    print("计算最优误差 ...")
    avg_cpi, avg_mpki, cpi_err, mpki_err = compute_error(raw_df, reps, target_cpi, target_mpki)

    print("\n==================== 最终最优代表性子集 ====================")
    print("最佳 K =", best_k)
    for r in reps:
        print(" -", r)

    print("\n平均 CPI:", avg_cpi)
    print("平均 MPKI:", avg_mpki)
    print("CPI 误差:", cpi_err)
    print("MPKI 误差:", mpki_err)

    return reps, avg_cpi, avg_mpki, cpi_err, mpki_err

def append_mean_row(df, label_col=None, label_value="MEAN"):
    """
    在 DataFrame 最后一行追加一行均值统计
    - 仅对数值列取 mean
    - 非数值列填 NaN
    - 可选：在 label_col 列写入标识（如 stage="MEAN"）
    """
    mean_row = {}

    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            mean_row[col] = df[col].mean()
        else:
            mean_row[col] = np.nan

    if label_col is not None and label_col in df.columns:
        mean_row[label_col] = label_value

    mean_df = pd.DataFrame([mean_row], columns=df.columns)
    return pd.concat([df, mean_df], ignore_index=True)


def run_stage(stage_dir, exclude_file):
    """
    对 stage{i}/aggr.csv 的每一行生成代表性子集
    返回：
      1) stage-level 静态得分
      2) 拼接后的 proxy 时序（CPI / MPKI）
    """
    aggr_df = pd.read_csv(os.path.join(stage_dir, "aggr.csv"))

    cpi_scores, mpki_scores = [], []
    proxy_series = []

    for idx, row in aggr_df.iterrows():
        reps, avg_cpi, avg_mpki, cpi_err, mpki_err = run(
            target_cpi=row["CPI"],
            target_mpki=row["MPKI"],
            exclude_file=exclude_file
        )

        cpi_scores.append(1.0 - cpi_err)
        mpki_scores.append(1.0 - mpki_err)

        # ---------- 构造该 row 对应的 proxy 时序 ----------
        metric_path = os.path.join(stage_dir, "sub", f"metric_{idx}.csv")
        if os.path.exists(metric_path):
            df_origin = pd.read_csv(metric_path)
            df_proxy = build_constant_proxy(df_origin, avg_cpi, avg_mpki)
            proxy_series.append(df_proxy)
    stage_score_df = pd.DataFrame([{
        "stage": stage_dir,
        "num_targets": len(aggr_df),
        "CPI_score": np.mean(cpi_scores),
        "MPKI_score": np.mean(mpki_scores),
    }])

    # 拼接成完整 proxy 时序
    proxy_df = pd.concat(proxy_series, ignore_index=True)

    return stage_score_df, proxy_df

def run_global_serial(stage_dir, proxy_df, output_csv=None):
    """
    基于 run_stage 生成的 proxy 时序
    计算全局时序相似性指标
    """
    origin_path = os.path.join(stage_dir, "metric_0.csv")
    df_origin = pd.read_csv(origin_path)

    min_len = min(len(df_origin), len(proxy_df))
    df_origin = df_origin.iloc[:min_len]
    df_proxy  = proxy_df.iloc[:min_len]

    metrics = compute_serial_similarity(df_origin, df_proxy)
    metrics["stage"] = stage_dir

    serial_df = pd.DataFrame([metrics])

    if output_csv:
        serial_df.to_csv(output_csv, index=False)

    return serial_df

def build_constant_proxy(
    df_origin,
    mean_cpi,
    mean_mpki,
    noise_ratio=0.05,   # 5% 波动
    random_state=0
):
    """
    构造以均值为中心、带小幅随机扰动的 proxy 序列
    """
    rng = np.random.default_rng(random_state)
    n = len(df_origin)

    # 以原始序列的 std 作为噪声尺度（更物理）
    cpi_std = df_origin["CPI"].std()
    mpki_std = df_origin["MPKI"].std()

    # 如果原始本身几乎不波动，给一个极小下限
    cpi_sigma  = noise_ratio * (cpi_std if cpi_std > 1e-6 else mean_cpi)
    mpki_sigma = noise_ratio * (mpki_std if mpki_std > 1e-6 else mean_mpki)

    cpi_noise  = rng.normal(0.0, cpi_sigma,  size=n)
    mpki_noise = rng.normal(0.0, mpki_sigma, size=n)

    return pd.DataFrame({
        "CPI":  mean_cpi  + cpi_noise,
        "MPKI": mean_mpki + mpki_noise
    })
def run_global_target(stage_dir, exclude_file, output_csv=None):
    """
    对 stage{i}/target 文件进行一次代表性子集生成
    输出 CPI / MPKI 得分（1 - error）
    """
    target_path = os.path.join(stage_dir, "targets.csv")
    target_df = pd.read_csv(target_path)

    results = []

    for idx, row in target_df.iterrows():
        target_cpi = row["CPI"]
        target_mpki = row["MPKI"]

        print(f"\n========== Stage {stage_dir} TARGET Row {idx} ==========")
        print(f"Target CPI={target_cpi}, Target MPKI={target_mpki}")

        reps, avg_cpi, avg_mpki, cpi_err, mpki_err = run(
            target_cpi=target_cpi,
            target_mpki=target_mpki,
            exclude_file=exclude_file
        )

        results.append({
            "stage": stage_dir,
            "target_CPI": target_cpi,
            "target_MPKI": target_mpki,
            "avg_CPI": avg_cpi,
            "avg_MPKI": avg_mpki,
            "CPI_score": 1.0 - cpi_err,
            "MPKI_score": 1.0 - mpki_err,
            "subset_size": len(reps),
            "subset": ",".join(reps)
        })

    result_df = pd.DataFrame(results)

    if output_csv is not None:
        result_df.to_csv(output_csv, index=False)

    return result_df

# ============================================================
# 程序入口
# ============================================================
if __name__ == "__main__":

    stage_map = [
        'in-memory','websearch','pr','cc','tc','tpcc','tpch',
        'twitter','ycsb','join','kmeans','terasort',
        'nutchindexing','wordcount','xgboost'
    ]

    phase_results = []
    global_static_results = []
    global_serial_results = []
    start = time.time()
    for i in range(len(stage_map)):
        stage = f"stage{i}"

        # (1) Stage-level
        stage_df, proxy_df = run_stage(
            stage_dir=stage,
            exclude_file=f"{stage_map[i]}.csv"
        )
        phase_results.append(stage_df)

        # (2) Global static (原有)
        global_df = run_global_target(
            stage_dir=stage,
            exclude_file=f"{stage_map[i]}.csv"
        )
        global_static_results.append(global_df)

        # (3) Global serial (新增)
        serial_df = run_global_serial(
            stage_dir=stage,
            proxy_df=proxy_df
        )
        global_serial_results.append(serial_df)
    end = time.time()
    print(end-start)
    pd.concat(phase_results).pipe(append_mean_row, "stage", "MEAN").to_csv("phase.csv", index=False)

    pd.concat(global_static_results).pipe(append_mean_row, "stage", "MEAN").to_csv("global.csv", index=False)

    pd.concat(global_serial_results).pipe(append_mean_row, "stage", "MEAN").to_csv("global_serial.csv", index=False)
