import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
def scaling():
    result_dir = './result/20250411-161052/'
    # 读取数据（假设文件名为data.csv）
    data = pd.read_csv(f"{result_dir}/final_aggregations.csv")

    # 定义需要缩放的列
    scaled_columns = [
        "cycles", "instructions", "L1-misses", "ll-misses/", 
        "power", "branches", "branch-misses"
    ]

    # 计算缩放因子（100秒为基准）
    data["scale"] = 100 / data["duration"]

    # 对指定列进行线性缩放
    for col in scaled_columns:
        data[col] = data[col] * data["scale"]

    # 更新duration为100秒
    data["duration"] = 100

    # 删除临时缩放因子列
    data = data.drop(columns=["scale"])

    # 查看缩放后的数据
    print("缩放后的数据:")
    print(data.head().to_string(float_format="%.1f"))

    # 保存到新文件（可选）
    data.to_csv("scaled_data.csv", index=False)

def analyze():


    # 读取缩放后的数据（假设已保存为scaled_data.csv）
    scaled_data = pd.read_csv("scaled_data.csv")

    # 删除非数值列（aggr_type）
    scaled_numeric = scaled_data.drop(columns=["aggr_type"])

    # 计算相关系数矩阵
    scaled_corr = scaled_numeric.corr()

    # 提取与power的相关系数并按绝对值排序
    scaled_power_corr = scaled_corr["power"]
    scaled_power_corr_sorted = scaled_power_corr.iloc[(-scaled_power_corr.abs()).argsort()]

    print("缩放后各属性与power能耗的相关系数（按绝对值排序）:")
    print(scaled_power_corr_sorted.to_string(float_format="%.3f"))

    # 绘制热图（排除常数列duration）
    plt.figure(figsize=(12, 8))
    sns.heatmap(
        scaled_corr.drop(columns=["duration"]).drop(index=["duration"]),
        annot=True,
        fmt=".2f",
        cmap="coolwarm",
        center=0,
        linewidths=0.5
    )
    plt.title("缩放后变量间相关系数热图")
    plt.tight_layout()
    plt.show()

scaling()
analyze()