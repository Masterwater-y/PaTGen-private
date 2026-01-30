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
    df["MPKI"] = (
        df["armv8_pmuv3_0/ll_cache_miss/"] * 1000 / df["instructions"]
    )
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
    df = df.replace([np.inf, -np.inf], np.nan)
    return df.fillna(df.mean())


# ============================================================
# Step 5: Normalize
# ============================================================
def normalize(df):
    scaler = MinMaxScaler()
    return pd.DataFrame(
        scaler.fit_transform(df),
        columns=df.columns,
        index=df.index
    )


# ============================================================
# Step 6: SGBRT 特征选择
# ============================================================
def select_top_features(df_norm, target="CPI", topN=12):
    X = df_norm.drop(columns=[target])
    y = df_norm[target]

    model = GradientBoostingRegressor(random_state=0)
    model.fit(X, y)

    importance = model.feature_importances_
    feats = sorted(
        zip(X.columns, importance),
        key=lambda x: x[1],
        reverse=True
    )

    return [f[0] for f in feats[:min(topN, len(feats))]]


# ============================================================
# Step 7: ICA
# ============================================================
def apply_ica(df_norm, selected_feats):
    if len(selected_feats) < 2:
        return df_norm[selected_feats]

    ica = FastICA(
        n_components=len(selected_feats),
        random_state=0
    )
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
# Step 9: 显式枚举 K
# ============================================================
def find_best_k(ica_df, agg_df, target_cpi, target_mpki,
                k_min=2, k_max=10):

    best_k, best_err, best_subset = None, 1e9, None

    for k in range(k_min, min(k_max, len(ica_df)) + 1):
        km = KMeans(n_clusters=k, random_state=0)
        labels = km.fit_predict(ica_df)

        reps = []
        for c in range(k):
            idx = np.where(labels == c)[0]
            center = km.cluster_centers_[c]
            dist = np.linalg.norm(
                ica_df.iloc[idx].values - center,
                axis=1
            )
            reps.append(ica_df.index[idx[np.argmin(dist)]])

        _, _, cpi_err, mpki_err = compute_error(
            agg_df, reps, target_cpi, target_mpki
        )

        if cpi_err + mpki_err < best_err:
            best_err = cpi_err + mpki_err
            best_k = k
            best_subset = reps

    return best_k, best_subset


# ============================================================
# run(): 选代表性子集
# ============================================================
def run(target_cpi, target_mpki, exclude_file):

    workloads = load_all_traces("./perfs")
    agg_df = aggregate_workloads(workloads, exclude_file)
    raw_df = agg_df.copy()

    agg_df = fix_columns(agg_df)
    df_norm = normalize(agg_df)

    top_feats = select_top_features(df_norm)
    ica_df = apply_ica(df_norm, top_feats)

    best_k, reps = find_best_k(
        ica_df, raw_df, target_cpi, target_mpki
    )

    avg_cpi, avg_mpki, cpi_err, mpki_err = compute_error(
        raw_df, reps, target_cpi, target_mpki
    )

    return reps, avg_cpi, avg_mpki, cpi_err, mpki_err


# ============================================================
# ⭐ 关键新增：代表性子集 perf 均值
# ============================================================
def compute_subset_perf_means(reps, perf_dir="./perfs"):
    """
    reps 内：
      - 每个 perf 先对时间序列取均值
      - 再对 reps 取均值
    """
    rows = []

    for name in reps:
        path = os.path.join(perf_dir, name)
        if not os.path.exists(path):
            continue

        df = pd.read_csv(path)
        rows.append(df.mean(numeric_only=True))

    if not rows:
        return {}

    return pd.DataFrame(rows).mean().to_dict()


# ============================================================
# Global target（静态）
# ============================================================
def run_global_target(stage_dir, exclude_file, output_csv=None):

    target_df = pd.read_csv(
        os.path.join(stage_dir, "targets.csv")
    )

    results = []

    for _, row in target_df.iterrows():
        reps, avg_cpi, avg_mpki, cpi_err, mpki_err = run(
            row["CPI"], row["MPKI"], exclude_file
        )

        perf_means = compute_subset_perf_means(reps)

        item = {
            "stage": stage_dir,
            "target_CPI": row["CPI"],
            "target_MPKI": row["MPKI"],
            "avg_CPI": avg_cpi,
            "avg_MPKI": avg_mpki,
            "CPI_score": 1.0 - cpi_err,
            "MPKI_score": 1.0 - mpki_err,
            "subset_size": len(reps),
            "subset": ",".join(reps)
        }

        item.update(perf_means)
        results.append(item)

    df = pd.DataFrame(results)
    if output_csv:
        df.to_csv(output_csv, index=False)

    return df


# ============================================================
# 工具：追加均值行
# ============================================================
def append_mean_row(df, label_col=None, label_value="MEAN"):
    row = {
        c: df[c].mean() if pd.api.types.is_numeric_dtype(df[c]) else np.nan
        for c in df.columns
    }
    if label_col in df.columns:
        row[label_col] = label_value

    return pd.concat([df, pd.DataFrame([row])], ignore_index=True)


# ============================================================
# 主入口
# ============================================================
if __name__ == "__main__":

    stage_map = [
        'in-memory','websearch','pr','cc','tc','tpcc','tpch',
        'twitter','ycsb','join','kmeans','terasort',
        'nutchindexing','wordcount','xgboost'
    ]

    global_static_results = []
    start = time.time()

    for i in range(len(stage_map)):
        stage = f"stage{i}"

        df = run_global_target(
            stage_dir=stage,
            exclude_file=f"{stage_map[i]}.csv"
        )
        global_static_results.append(df)

    print("Total time:", time.time() - start)

    pd.concat(global_static_results).pipe(
        append_mean_row, "stage", "MEAN"
    ).to_csv("global.csv", index=False)
