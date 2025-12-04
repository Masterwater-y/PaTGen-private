import csv
import json

# 定义 CSV 文件路径
file_path = 'memory.csv'

memory_feature = {}

try:
    with open(file_path, 'r', newline='') as csvfile:
        reader = csv.reader(csvfile)
        headers = next(reader)

        for row in reader:
            param_set = row[1].strip('"[] ')
            duration = float(row[4])
            cpu_util = float(row[5]) if row[5] else 0.0
            cycles = float(row[7])
            instructions = float(row[8])
            cachemiss = float(row[10])

            memory_feature[param_set] = {
                "cycle": cycles,
                "instruction": instructions,
                "cachemiss": cachemiss,
                "duration": duration,
                "cpu_util": cpu_util
            }

    # 输出转换后的结果
    print(json.dumps(memory_feature, indent=4))

except FileNotFoundError:
    print(f"错误：未找到文件 {file_path}。")
except Exception as e:
    print(f"发生未知错误：{e}")
    