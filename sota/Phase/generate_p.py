import pandas as pd
import ast

def merge_param_sets(param_sets):
    if not param_sets:
        return "[]"
    
    merged_blocks = []  # 存储所有块列表
    trailing_values = []  # 存储尾部数值
    
    try:
        # 解析第一个param_set获取尾部数值
        first_param = ast.literal_eval(param_sets[0])
        if isinstance(first_param, list) and len(first_param) > 0:
            # 分离块列表和尾部数值
            for item in first_param:
                if isinstance(item, list):
                    merged_blocks.append(item)
                else:
                    trailing_values.append(item)
        else:
            return param_sets[0]  # 无效结构直接返回第一个
        
        # 合并后续param_set的块
        for param_str in param_sets[1:]:
            param = ast.literal_eval(param_str)
            if isinstance(param, list) and len(param) > 0:
                for item in param:
                    if isinstance(item, list):
                        merged_blocks.append(item)
                        
        # 构建最终结构：所有块 + 第一个param_set的尾部数值
        merged_list = merged_blocks + trailing_values
        return str(merged_list)
    
    except (SyntaxError, ValueError):
        return param_sets[0]

def adjust_iters(param_set_str, aggr_duration, block_duration):
    """根据duration比例调整固定结构的param_set"""
    if block_duration == 0:
        return param_set_str
    
    ratio = aggr_duration / block_duration
    
    try:
        # 解析字符串为列表
        param_list = ast.literal_eval(param_set_str)

        # 遍历每个子项进行调整
        adjusted = []
        for item in param_list:
            # 处理列表型参数（如[20, 'div', 1e9]）
            if isinstance(item, list):
                for block in item:
                    block[2] = int(block[2] * ratio)

            adjusted.append(item)
            
        return str(adjusted)
    
    except:
        return param_set_str

# 数据加载与预处理
aggr_df = pd.read_csv('stage/aggr.csv')
block_df = pd.read_csv('block.csv').dropna(subset=['CPI', 'MPKI', 'duration'])

# 类型转换
numeric_cols = ['CPI', 'MPKI', 'duration']
block_df[numeric_cols] = block_df[numeric_cols].apply(pd.to_numeric, errors='coerce')

# 列名处理
aggr_renamed = aggr_df[['duration', 'CPI', 'MPKI']].rename(
    columns=lambda x: f"t_{x}" if x in numeric_cols else x
)

result_rows = []

# 主处理逻辑
for _, aggr_row in aggr_df.iterrows():
    # 计算最接近的block行
    distances = (
        (block_df['CPI'] - aggr_row['CPI']).pow(2) +
        (block_df['MPKI'] - aggr_row['MPKI']).pow(2)
    )
    closest = block_df.iloc[distances.idxmin()]
    
    # 参数调整
    adjusted_param = adjust_iters(
        closest['param_set'],
        aggr_row['duration'],
        closest['duration']
    )

    # 构建结果行
    result_rows.append({
        'a_duration': closest['duration'],
        'a_CPI': closest['CPI'],
        'a_MPKI': closest['MPKI'],
        'param_set': adjusted_param
    })

# 合并最终结果
final_df = pd.concat([
    aggr_renamed,
    pd.DataFrame(result_rows)
], axis=1)

# 列顺序调整
output_columns = [
    't_duration', 't_CPI', 't_MPKI',
    'param_set', 'a_duration', 'a_CPI', 'a_MPKI'
]

final_df[output_columns].to_csv('result.csv', index=False)

'''param_sets = final_df[['param_set']].copy()
param_sets.to_csv('param_sets.csv', index=False)'''

param_sets = final_df['param_set'].tolist()
param_sets = merge_param_sets(param_sets)
final_df = pd.DataFrame({'param_set': [param_sets]})
final_df.to_csv('param_sets.csv', index=False)

