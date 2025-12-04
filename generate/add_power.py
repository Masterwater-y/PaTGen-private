import pandas as pd

# 定义线性转换函数
def calculate_power(util):
    """
    根据CPU利用率计算功耗值
    参数:
        util (float): 0-0.8范围的CPU利用率
    
    返回:
        float: 280-380范围的功耗值
    """
    util_clipped = max(0, min(util/100, 0.8))  # 限制输入范围
    return 280 + (util_clipped / 0.8) * 100

# 读取CSV文件（请替换为实际文件路径）
input_file = "full_targets.csv"
output_file = "temp.csv"
T_total = 200
# 读取数据并处理
df = pd.read_csv(input_file)
df['T_total'] = T_total
df['power'] = df['cpu_util_percent'].apply(calculate_power)

# 保存结果（保留所有原始列）
df.to_csv(output_file, index=False)

print(f"处理完成，结果已保存至 {output_file}")