import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from fitter import Fitter
from scipy import stats
import os

def parse_fitter_params(params, dist_name):
    """统一处理不同版本Fitter的参数格式"""
    if isinstance(params, dict):
        return params.get('arg', ()), params.get('loc', 0), params.get('scale', 1)
    else:
        # 按标准顺序 (shape, loc, scale) 解析
        if dist_name in ['gamma', 'weibull_min']:
            if len(params) >= 3:
                return params[:1], params[1], params[2]
        elif dist_name == 'lognorm':
            # lognorm的特殊参数格式 (s, loc, scale)
            return (params[0],), params[1], params[2]
        return params, 0, 1

# 文件路径检查
csv_path = 'targets.csv'
if not os.path.exists(csv_path):
    raise FileNotFoundError(f"CSV文件应放置于: {os.path.abspath(csv_path)}")

df = pd.read_csv(csv_path)

for column in df.columns:
    data = df[column].dropna()
    
    # 增强数据有效性检查
    if len(data) < 3 or data.nunique() == 1:
        print(f"列 '{column}': 数据无效，跳过分析")
        continue
    
    plt.figure(figsize=(10,6))
    sns.histplot(data, kde=False, stat='density', label='Histogram')
    
    # 选择更稳定的分布列表
    distributions = ['norm', 'expon', 'gamma', 'lognorm', 'weibull_min']
    f = Fitter(data, distributions=distributions)
    f.fit()
    
    best_dist_name = None
    if f.fitted_param:
        try:
            best_dist_name = list(f.get_best().keys())[0]
            params = f.fitted_param[best_dist_name]
            
            # 参数解析
            args, loc, scale = parse_fitter_params(params, best_dist_name)
            
            # 生成PDF曲线
            x = np.linspace(data.min(), data.max(), 1000)
            dist = getattr(stats, best_dist_name)
            
            # 动态参数传递
            if best_dist_name in ['gamma', 'weibull_min', 'lognorm']:
                pdf = dist.pdf(x, *args, loc=loc, scale=scale)
            else:
                pdf = dist.pdf(x, loc=loc, scale=scale)
                
            plt.plot(x, pdf, label=f'Best Fit: {best_dist_name}', lw=2)
            print(f"[成功] 列 {column}: {best_dist_name} 参数 {params}")
            
        except Exception as e:
            print(f"[失败] 列 {column}: {str(e)}")
            best_dist_name = None
    
    # 降级到KDE
    if not best_dist_name:
        sns.kdeplot(data, label='KDE', lw=2)
    
    plt.title(f'Distribution Analysis: {column}')
    plt.legend()
    plt.show()
