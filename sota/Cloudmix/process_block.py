import ast
import pandas as pd
cpu_cores = 96
mem_capacity = 256
def process_csv(file_path):
    res = pd.DataFrame()
    try:
        df = pd.read_csv(file_path)
        # 排除 'workload' 列
        res['param_set'] = df['param_set']
        def process_param_set(row):
            param_list = ast.literal_eval(row['param_set'])
            param_list[0][2] = int(param_list[0][2] / row['duration'])
            return str(param_list)
        def get_row_mem(row):
                param_list = ast.literal_eval(row['param_set'])
                return param_list[0][-1]/1024
        def get_row_cpu(row):
                param_list = ast.literal_eval(row['param_set'])
                return param_list[0][0]
        res['param_set'] = df.apply(process_param_set, axis=1)
        # 将 'cycles_sum' 列除以 'duration' 列
        res['cpu_util'] = df.apply(get_row_cpu, axis=1)
        res['mem_util'] = df.apply(get_row_mem, axis=1)
        res['cycles'] = df['cycles_sum'] / df['duration']
        res['instructions'] = df['instructions_sum'] / df['duration']
        res['ll-misses'] = df['ll-misses_sum'] / df['duration']

        columns_to_convert = ['cpu_util', 'mem_util','cycles','instructions','ll-misses']
        for col in columns_to_convert:
            if col in res.columns:
                res[col] = res[col].astype(int)
        return res
    except FileNotFoundError:
        print("错误: 文件未找到!")
    except KeyError:
        print("错误: 数据框中缺少必要的列!")
    except Exception as e:
        print(f"错误: 发生了一个未知错误: {e}")
    return None


if __name__ == "__main__":
    file_path = 'temp.csv'
    result = process_csv(file_path)
    if result is not None:
        result.to_csv('block.csv',index=False)
    