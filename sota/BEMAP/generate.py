import os
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


# ============================================================
# 程序入口
# ============================================================
if __name__ == "__main__":
    target_cpi = 1.007
    target_mpki = 1.303
    exclude_file = "cloudsuite_tc.csv"
    run(target_cpi, target_mpki, exclude_file)
