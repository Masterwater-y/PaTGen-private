import csv
import os
import pandas as pd


def MPKI_analysis(result_dir):
    # 定义目录路径，这里假设文件都在当前目录下，你可以根据实际情况修改
    directory = f'{result_dir}/final_result'

    # 用于存储步长和 mean MPKI 的列表
    stride_list = []
    mean_mpki_list = []

    # 遍历目录下的所有文件
    for filename in os.listdir(directory):
        if filename.startswith('aggr_memory_stride_') and filename.endswith('.csv'):
            try:
                # 从文件名中提取步长
                parts = filename.split('[')[1].split(']')[0].split(',')
                stride = int(parts[2])

                # 初始化 mean MPKI 为 None
                mean_mpki = None

                # 打开 CSV 文件
                with open(os.path.join(directory, filename), 'r', encoding='utf-8') as file:
                    reader = csv.reader(file)
                    header = next(reader)  # 读取表头
                    for row in reader:
                        if row[0] == "mean":
                            mean_mpki = float(row[4])

                # 将步长和 mean MPKI 添加到列表中
                if mean_mpki is not None:
                    stride_list.append(stride)
                    mean_mpki_list.append(mean_mpki)
            except (IndexError, ValueError, FileNotFoundError):
                print(f"处理文件 {filename} 时出现错误。")

    # 创建 DataFrame
    data = {'stride': stride_list, 'mean MPKI': mean_mpki_list}
    df = pd.DataFrame(data)
    df = df.sort_values(by='stride')
    # 输出为 CSV 文件
    df.to_csv(os.path.join(directory, 'stride.csv'), index=False)