import os
import csv
import re

from workload_runner.align import filter_performance_data
import pandas as pd
import numpy as np

from workload_runner.common import *    
class Runner:
    def __init__(self):
        self.mName = None
        self.mParamSet = None
        self.result_dir = None
        self.job_dir = None
        self.time_record_dir = None
        self.perf_dir = None
        self.input_dir = None
        self.phase_aware = False
        self.time_record = []
        self.target_path = None
        self.sample_dir = None


    def PreStart(self,param_set):
        pass

    def Start(self, param_set):
        pass
    
    def GetPerformanceResult(self):
        pass
    
    def GetWorkloadBeginEndTime(self):
        return None
    
    def GetBenchmarkInfo(self):
        return (self.mPerformanceMeaning, self.mPerformanceUnit)
    
    def StartAndSaveTime(self, param_set):
        for dir in [self.result_dir, self.perf_dir, self.time_record_dir]:
            if not os.path.exists(dir):
                os.makedirs(dir)
        if param_set is not None:
            self.mParamSet = param_set
            self.PreStart(param_set)
        times = self.Start(param_set)
        
        tmp = self.GetWorkloadBeginEndTime()
        if tmp is not None:
            times = tmp
        print(f'finish times={times}')
        tmp = [self.mName, param_set, times[0], times[1], times[1]-times[0]]
        self.time_record.append(tmp)
        return times
    
    def SaveTimeRecord(self):
        time_record_file = os.path.join(self.time_record_dir, 'time_record.csv')
        with open(time_record_file, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            # 写入表头，包含持续时间列
            writer.writerow(["Workload", "Param Set", "Start Time", "End Time", "Duration"])
            for info in self.time_record:
                writer.writerow(info)
    


    def FilterPefData(self):
        filter_performance_data(self.result_dir)

    def Evaluate(self):
        target_path = self.target_path

        result_path = os.path.join(self.result_dir,'final_aggregations.csv')
        sim_path = os.path.join(self.result_dir,'simulation.csv')
        res_df = pd.read_csv(result_path)
        target_df = pd.read_csv(target_path)
        sim_df = evaluate_results(res_df,target_df)
        sim_df.to_csv(sim_path, float_format='%.4f')
    
    def PhaseEvalute(self):
        target_df = pd.read_csv(os.path.join(self.sample_dir, 'aggr.csv'))
        phase_df = pd.read_csv(os.path.join(self.result_dir, 'time_record', 'phase_time.csv'))
        tmp_dir = os.path.join(self.result_dir, 'tmp')
        if not os.path.exists(tmp_dir):
            os.mkdir(tmp_dir)
        durations = phase_df['duration'].dropna().astype(float)
        durations = durations.apply(lambda d: max(1, int(round(d))))
        metric_dir = os.path.join(self.result_dir, 'final_result')
        metric = pd.read_csv(f"{metric_dir}/metric_0.csv")
        sim_path = os.path.join(self.result_dir,'phase_sim.csv')
        # 验证原始数据总行数
        total_rows = len(metric)
        print(f"原始数据总行数: {total_rows}")

        # 按照durations分割数据
        split_data = []
        start_idx = 1
        phase_results=[]
        for duration in durations:
            
            end_idx = start_idx + duration
            if end_idx > total_rows:
                print(f"警告: 持续时间 {duration} 超出了数据范围，已调整为可用范围")
                end_idx = total_rows

            phase_data = metric.iloc[start_idx:end_idx]
            
            phase_stats = {
                'cpu_util': phase_data['cpu_util'].mean(),
                'mem_util': phase_data['mem_util'].mean(),
                'disk_util': phase_data['disk_util'].mean(),
                'duration': len(phase_data),
                'CPI': phase_data['cycles'].sum() / phase_data['instructions'].sum(),
                'MPKI': phase_data['ll-misses/'].sum() / phase_data['instructions'].sum() * 1000,
                'power': phase_data['power'].sum()
            }
            phase_results.append(phase_stats)
            start_idx = end_idx
        result_df = pd.DataFrame(phase_results)
        result_df.to_csv(os.path.join(tmp_dir,'aggr.csv'))
        sim_df = evaluate_results(result_df,target_df)

        sim_df.to_csv(sim_path, float_format='%.4f')
    '''def Evaluate(self):
        # 定义需要计算的列及其类型

        target_path = self.target_path

        result_path = os.path.join(self.result_dir,'final_aggregations.csv')
        sim_path = os.path.join(self.result_dir,'simulation.csv')
        #percentage_cols = ['cpu_util', 'mem_util', 'disk_util']
        #non_percentage_cols = ['duration', 'CPI', 'MPKI', 'power']
        if not os.path.exists(target_path):
            print('no target')
            return None
        mapping ={
            'cpu_util': (lambda t,r: r*100 , 'relative'),
            'mem_util': (lambda t,r: r*t['mem_capacity']/t['mem_size']*100 , 'relative'),
            'disk_util': (lambda t,r: r*100 , 'relative'),
            'duration': (None, 'relative'),
            'CPI': (None, 'relative'),
            'MPKI': (None, 'relative'),
            'power': (None, 'relative'),
        }
        sim_df = pd.DataFrame()

        
        res_df = pd.read_csv(result_path)
        target_df = pd.read_csv(target_path)

        res_processed = res_df.copy()
        for col in mapping.keys():
            transformer, _ = mapping[col]
            if transformer:
                # 带上下文的数据转换（使用目标数据和结果数据）
                res_processed[col] = res_df.apply(
                    lambda row: transformer(target_df.loc[row.name], row[col]),
                    axis=1
                )
        similarity_strategy = {
            col: (calculate_absolute_similarity if sim_type == 'absolute' 
                else calculate_relative_similarity)
            for col, (_, sim_type) in mapping.items()
        }

        sim_data = {}
        for col, strategy in similarity_strategy.items():
            # 获取对齐后的数据对
            res_values = res_processed[col]
            target_values = target_df[col]
            
            # 执行相似度计算
            sim_values = [
                strategy(res, target) 
                for res, target in zip(res_values, target_values)
            ]
            sim_data[f"{col}"] = sim_values
            
        # 计算平均误差并添加行
        sim_df = pd.DataFrame(sim_data, index=res_df.index)  # 关键修复：转换为DataFrame

        # 添加平均行（使用loc避免类型问题）
        avg_row = pd.DataFrame(sim_df.mean(axis=0).to_dict(), index=['Average'])
        sim_df = pd.concat([sim_df, avg_row])

        # 保存结果（添加格式控制）
        sim_df.to_csv(sim_path, float_format='%.4f')
        

        return sim_df'''
    

    def FixPhase(self, metric, target, phase):
        # 检查输入列表是否为空或长度不一致
        if isinstance(target, pd.Series):
            target = target.tolist()
        if isinstance(phase, pd.Series):
            phase = phase.tolist()
        if not target or not phase or len(target) != len(phase):
            raise ValueError("target and phase must be non-empty lists of the same length")
        
        # 初始化结果列表和起始时间
        new_rows = []
        current_time = metric['time'].iloc[0]  # 起始时间使用第一行的时间值
        current_idx = 0  # 当前处理的原始数据索引
        total_rows = len(metric)  # 原始数据总行数
        
        # 遍历每一对 target 和 phase
        for i in range(len(target)):
            t = target[i]
            p = phase[i]
            k = min(t, p)  # 需要复制的行数
            
            # 阶段1: 复制 min(t, p) 行
            for _ in range(k):
                if current_idx >= total_rows:
                    break  # 如果超出数据范围则停止
                
                # 复制当前行并更新时间为连续值
                row = metric.iloc[current_idx].copy()
                row['time'] = current_time
                new_rows.append(row)
                
                # 更新时间和索引
                current_time += 1
                current_idx += 1
            
            # 阶段2: 处理多出的行
            if t > p:  # 需要重复最后一行 (t-p) 次
                if new_rows:  # 确保已经有复制的行
                    last_row = new_rows[-1].copy()
                    for _ in range(t - p):
                        last_row['time'] = current_time
                        new_rows.append(last_row.copy())
                        current_time += 1
            elif t < p:  # 需要跳过 (p-t) 行
                skip = min(p - t, total_rows - current_idx)  # 计算实际可跳过的行数
                current_idx += skip
        
        # 创建新的 DataFrame
        new_df = pd.DataFrame(new_rows, columns=metric.columns)
        new_df['time'] = new_df['time'].astype(int)
        new_df = new_df.reset_index(drop=True)
        return new_df
    

    def CalcSerialSim(self):
        import pandas as pd
        import matplotlib.pyplot as plt
        import os
        from dtw import dtw
        from scipy.stats import pearsonr,spearmanr
        from fastdtw import fastdtw
        from scipy.spatial.distance import euclidean
        origin_dir = self.sample_dir
        metric_dir = os.path.join(self.result_dir, 'final_result')
        result_dir = os.path.join(self.result_dir, 'serial')
        df_aggr = pd.read_csv(os.path.join(origin_dir, 'aggr.csv'))

        # 提取duration列作为阶段分界线（绝对坐标）
        durations = df_aggr['duration'].dropna().astype(float)
        durations = durations.apply(lambda d: max(1, int(round(d))))
        if not durations.empty:
            cumulative = durations.cumsum().values - 1  # 计算累积和并减一
            boundaries = cumulative.tolist()
        else:
            boundaries = []
        os.makedirs(result_dir, exist_ok=True)
        # 配置参数
        COMPARE_COLS = ['CPI', 'MPKI']  # 需要对比的列
        PLOT_ROWS = 3   # 可视化行数（根据列数调整）
        PLOT_COLS = 1   # 可视化列数
        # 获取文件列表
        metric_files = [f for f in os.listdir(metric_dir) if f.startswith("metric_")]
        
        # 初始化结果存储    
        variance_results = []
        for filename in metric_files:
            # 读取文件对
            file_id = filename.split("_")[-1].split(".")[0]
            df_origin = pd.read_csv(f"{origin_dir}/metric_{file_id}.csv")
            df_processed = pd.read_csv(f"{metric_dir}/metric_{file_id}.csv")
            if self.phase_aware:
                phase_df = pd.read_csv(os.path.join(self.result_dir, 'time_record','phase_time.csv'))
                phase_durations = phase_df['duration'].dropna().astype(float)
                phase_durations = phase_durations.apply(lambda d: max(1, int(round(d))))
                df_processed = self.FixPhase(df_processed,durations,phase_durations)
            else:   
                # 对齐数据长度
                min_length = min(len(df_origin), len(df_processed))
                df_origin = df_origin.iloc[:min_length]
                df_processed = df_processed.iloc[:min_length]

            for col in COMPARE_COLS:
                df_origin[col] = smooth_isolated_outliers(df_origin[col])
                df_processed[col] = smooth_isolated_outliers(df_processed[col])
            df_processed.to_csv(f"{metric_dir}/phase_adjust_{file_id}.csv",index=False)
            # 创建可视化画布
            plt.figure(figsize=(12, 6 * PLOT_ROWS))
            
            # 遍历每个需要对比的列
            metrics = {'sample': self.sample_index}  # 更名为metrics更贴切
            for idx, col in enumerate(COMPARE_COLS, 1):
                # 计算MSE和Pearson
                print('len1:',len(df_origin[col]),len(df_processed[col]))
                mse = ((df_origin[col] - df_processed[col])**2).mean()
                pearson, _ = pearsonr(df_origin[col], df_processed[col])
                spearman, _ = spearmanr(df_origin[col], df_processed[col])
                metrics[f'{col}_m'] = mse
                metrics[f'{col}_p'] = pearson
                metrics[f'{col}_s'] = spearman
                # 计算DTW
                dtw_distance = dtw(
                    df_origin[col].values.reshape(-1,1), 
                    df_processed[col].values.reshape(-1,1),
                    keep_internals=True
                ).distance
                metrics[f'{col}_d'] = dtw_distance


                # ------------ 代表性得分计算结束 ------------

                # 绘制趋势对比
                ax = plt.subplot(PLOT_ROWS, PLOT_COLS, idx)
        
                # 绘制指标曲线
                ax.plot(df_origin[col], label='Real', alpha=0.8)
                ax.plot(df_processed[col], label='Proxy', alpha=0.6)
                
                # 绘制阶段分界线
                if len(boundaries)>1:
                    for d in boundaries:
                        if d < len(df_origin[col]):  # 检查边界有效性
                            ax.axvline(x=d, color='red', linestyle='--', linewidth=1.2)
                
                ax.set_title(f"{col} Trend ")
                ax.set_ylabel(col)
                ax.legend()
            
            # 保存可视化结果
            plt.tight_layout()
            plt.savefig(f"{result_dir}/comparison_{file_id}.png")
            plt.close()
            # 记录方差结果


            epsilon = 1e-10  # 避免除零错误
            NMSE = (
                (((df_origin['CPI'] - df_processed['CPI']) / (df_origin['CPI'] + epsilon))**2 + 
                ((df_origin['MPKI'] - df_processed['MPKI']) / (df_origin['MPKI'] + epsilon))**2)
            ).mean() / 2
            metrics['NMSE'] = NMSE 
            
            # 计算同时考虑CPI和MPKI的MDTW
            full_data = np.array([df_origin['CPI'].values, df_origin['MPKI'].values]).T
            processed_data = np.array([df_processed['CPI'].values, df_processed['MPKI'].values]).T
            
            # 确保数据长度大于1，否则fastdtw会报错
            if len(full_data) > 1 and len(processed_data) > 1:
                distance, _ = fastdtw(full_data, processed_data, dist=euclidean)
                metrics['mdtw'] = distance
            else:
                metrics['mdtw'] = np.nan

            full_data = np.array([df_origin['CPI'].values, df_origin['MPKI'].values])
            sub_data = np.array([df_processed['CPI'].values, df_processed['MPKI'].values])
            #sub_data = np.array([df_processed['CPI'].values, df_processed['MPKI'].values])

            # 转置使 CPI 和 MPKI 成为列
            #sub_data_transposed = sub_data.T

            # 保存为 CSV 文件
            #np.savetxt('sub_data.csv', sub_data_transposed, delimiter=',', header='CPI,MPKI', comments='')
            # 计算 BenchSet_full 的均值向量 mean_full
            mean_full = np.mean(full_data, axis=1).reshape(-1, 1)  # 按列求均值，再转置成列向量形式用于计算余弦相似度
            # 计算 BenchSet_sub 的均值向量 mean_sub
            mean_sub = np.mean(sub_data, axis=1).reshape(-1, 1)
            #print(mean_full,mean_sub)
            #print(mean_full,mean_sub)
            # 计算 BenchSet_full 的标准差向量 std_full
            std_full = np.std(full_data, axis=1).reshape(-1, 1)
            # 计算 BenchSet_sub 的标准差向量 std_sub
            std_sub = np.std(sub_data, axis=1).reshape(-1, 1)

            # 计算 US：均值向量的余弦相似度
            numerator_us = np.dot(mean_full.T, mean_sub)[0, 0]
            denominator_us = np.linalg.norm(mean_full) * np.linalg.norm(mean_sub)
            US = numerator_us / denominator_us

            # 计算 DS：标准差向量的余弦相似度
            numerator_ds = np.dot(std_full.T, std_sub)[0, 0]
            denominator_ds = np.linalg.norm(std_full) * np.linalg.norm(std_sub)
            DS = numerator_ds / denominator_ds

            # 计算 RS：US 和 DS 的几何均值
            RS = np.sqrt(US * DS)
            metrics['RS'] = RS
            
            variance_results.append(metrics)
        # 生成方差报告
        report_df = pd.DataFrame(variance_results)
        report_df.to_csv(f"{result_dir}/variance_report.csv", index=False)
        print(f"Generated {len(metric_files)} comparisons in {result_dir}")

    def generate_final_reports(self):
        """
        合并 self.job_dir 目录下所有 iter{i} 目录中的 variance_report.csv 文件，
        并在最后添加一行统计每列的均值。
        新增功能：将iter{i}目录下的phase_sim.csv和simulation.csv的Averge行分别整合到final_phase_sim.csv和overall_sim.csv
        """
        # 获取 job_dir 路径
        job_dir = self.job_dir
        
        # 查找所有符合 iter{i} 格式的目录
        iter_dirs = []
        for item in os.listdir(job_dir):
            item_path = os.path.join(job_dir, item)
            if os.path.isdir(item_path) and re.match(r'iter\d+', item):
                iter_dirs.append(item_path)
        
        # 如果没有找到符合条件的目录，返回空
        if not iter_dirs:
            print("没有找到 iter{i} 格式的目录")
            return
        
        # 存储所有 variance_report.csv 的 DataFrame
        all_variance_dfs = []
        
        # 存储所有 phase_sim.csv 的 Average 行
        all_phase_avg_rows = []
        
        # 存储所有 simulation.csv 的 Average 行
        all_simulation_avg_rows = []
        
        # 遍历每个 iter{i} 目录，查找并读取相关 CSV 文件
        for iter_dir in iter_dirs:
            # 处理 variance_report.csv
            serial_dir = os.path.join(iter_dir, 'serial')
            variance_csv_path = os.path.join(serial_dir, 'variance_report.csv')
            
            if os.path.exists(variance_csv_path):
                try:
                    # 读取 CSV 文件，不使用索引
                    df = pd.read_csv(variance_csv_path)
                    all_variance_dfs.append(df)
                except Exception as e:
                    print(f"读取 {variance_csv_path} 时出错: {e}")
            
            # 处理 phase_sim.csv
            phase_csv_path = os.path.join(iter_dir, 'phase_sim.csv')
            
            if os.path.exists(phase_csv_path):
                try:
                    # 读取 CSV 文件，获取 Average 行
                    df = pd.read_csv(phase_csv_path)
                    # 查找 Average 行
                    avg_row = df[df.iloc[:, 0] == 'Average']
                    if not avg_row.empty:
                        # 获取迭代编号
                        iter_num = re.search(r'iter(\d+)', iter_dir).group(1)
                        # 将第一列的标签从 'Average' 替换为迭代编号
                        avg_row.iloc[0, 0] = iter_num
                        # 重命名第一列为 'sample'
                        avg_row = avg_row.rename(columns={avg_row.columns[0]: 'sample'})
                        all_phase_avg_rows.append(avg_row)
                    var_row = df[df.iloc[:, 0] == 'Variance']
                    if not var_row.empty:
                        # 提取 Variance 行中的 CPI 和 MPKI 列
                        cpi_var = var_row['CPI'].values[0]
                        mpki_var = var_row['MPKI'].values[0]
                        
                        # 添加新列到 avg_row
                        avg_row['CPI_var'] = cpi_var
                        avg_row['MPKI_var'] = mpki_var
                    else:
                        print(f"{phase_csv_path} 中未找到 Average 行")
                except Exception as e:
                    print(f"读取 {phase_csv_path} 时出错: {e}")
            
            # 处理 simulation.csv
            simulation_csv_path = os.path.join(iter_dir, 'simulation.csv')
            
            if os.path.exists(simulation_csv_path):
                try:
                    # 读取 CSV 文件，获取 Average 行
                    df = pd.read_csv(simulation_csv_path)
                    # 查找 Average 行
                    avg_row = df[df.iloc[:, 0] == 'Average']
                    if not avg_row.empty:
                        # 获取迭代编号
                        iter_num = re.search(r'iter(\d+)', iter_dir).group(1)
                        # 将第一列的标签从 'Average' 替换为迭代编号
                        avg_row.iloc[0, 0] = iter_num
                        # 重命名第一列为 'sample'
                        avg_row = avg_row.rename(columns={avg_row.columns[0]: 'sample'})
                        all_simulation_avg_rows.append(avg_row)
                    else:
                        print(f"{simulation_csv_path} 中未找到 Average 行")
                except Exception as e:
                    print(f"读取 {simulation_csv_path} 时出错: {e}")
        
        # 处理 variance_report.csv 部分
        if all_variance_dfs:
            # 合并所有 variance_report.csv 的 DataFrame
            merged_variance_df = pd.concat(all_variance_dfs, ignore_index=True)
            
            # 计算每列的均值（除了 'sample' 列）
            numeric_cols = merged_variance_df.columns.drop('sample')
            mean_values = merged_variance_df[numeric_cols].mean()
            
            # 创建包含均值的新行
            mean_row = pd.DataFrame({'sample': ['mean']})
            for col in numeric_cols:
                mean_row[col] = mean_values[col]
            
            # 按 sample 列排序（均值行暂不参与排序）
            sorted_merged_variance_df = merged_variance_df.sort_values(by='sample', ignore_index=True)
            
            # 将均值行添加到排序后的 DataFrame 末尾
            final_variance_df = pd.concat([sorted_merged_variance_df, mean_row], ignore_index=True)
            
            # 保存合并后的 DataFrame 到 CSV 文件
            output_variance_path = os.path.join(job_dir, 'final_serial_report.csv')
            final_variance_df.to_csv(output_variance_path, index=False)
            
            print(f"已将合并后的 variance_report.csv 保存到: {output_variance_path}")
        else:
            print("没有找到 variance_report.csv 文件")
        
        # 处理 phase_sim.csv 部分
        if all_phase_avg_rows:
            # 合并所有 phase_sim.csv 的 Average 行
            final_phase_df = pd.concat(all_phase_avg_rows, ignore_index=True)
            
            # 计算平均值行
            numeric_cols = final_phase_df.columns.drop('sample')
            phase_mean_values = final_phase_df[numeric_cols].mean()
            
            # 创建平均值行
            mean_phase_row = pd.DataFrame({'sample': ['Average']})
            for col in numeric_cols:
                mean_phase_row[col] = phase_mean_values[col]
            
            # 添加平均值行到 DataFrame
            final_phase_df = pd.concat([final_phase_df, mean_phase_row], ignore_index=True)
            
            # 按 sample 列排序，将 Average 行放在最后
            final_phase_df = final_phase_df.sort_values(
                by='sample', 
                key=lambda x: x.str.replace('Average', 'zAverage'),  # 将 Average 移到最后
                ignore_index=True
            )
            
            # 保存合并后的 DataFrame 到 CSV 文件
            output_phase_path = os.path.join(job_dir, 'final_phase_sim.csv')
            final_phase_df.to_csv(output_phase_path, index=False)
            
            print(f"已将合并后的 phase_sim.csv 的数据保存到: {output_phase_path}")
        else:
            print("没有找到 phase_sim.csv 文件或其中未包含 Average 行")
        
        # 处理 simulation.csv 部分
        if all_simulation_avg_rows:
            # 合并所有 simulation.csv 的 Average 行
            final_simulation_df = pd.concat(all_simulation_avg_rows, ignore_index=True)
            
            # 计算平均值行
            numeric_cols = final_simulation_df.columns.drop('sample')
            simulation_mean_values = final_simulation_df[numeric_cols].mean()
            
            # 创建平均值行
            mean_simulation_row = pd.DataFrame({'sample': ['Average']})
            for col in numeric_cols:
                mean_simulation_row[col] = simulation_mean_values[col]
            
            # 添加平均值行到 DataFrame
            final_simulation_df = pd.concat([final_simulation_df, mean_simulation_row], ignore_index=True)
            
            # 按 sample 列排序，将 Average 行放在最后
            final_simulation_df = final_simulation_df.sort_values(
                by='sample', 
                key=lambda x: x.str.replace('Average', 'zAverage'),  # 将 Average 移到最后
                ignore_index=True
            )
            
            # 保存合并后的 DataFrame 到 CSV 文件
            output_simulation_path = os.path.join(job_dir, 'overall_sim.csv')
            final_simulation_df.to_csv(output_simulation_path, index=False)
            
            print(f"已将合并后的 simulation.csv 的数据保存到: {output_simulation_path}")
        else:
            print("没有找到 simulation.csv 文件或其中未包含 Average 行")
        
        # 返回三个输出文件的路径
        return (output_variance_path if all_variance_dfs else None, 
                output_phase_path if all_phase_avg_rows else None,
                output_simulation_path if all_simulation_avg_rows else None)
    
    def generate_cost_report(self,cost_csv):
        cost_df = pd.DataFrame(cost_csv)
        cost_csv_path = os.path.join(self.job_dir, 'generate_cost.csv')
        cost_df.to_csv(cost_csv_path, index=False)
