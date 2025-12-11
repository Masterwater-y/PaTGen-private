import os
import csv
import shutil
from workload_runner.Runner import Runner
from workload_runner.common import returnTime, run_command, save_json, smooth_isolated_outliers, stage_divide
import pandas as pd

class PhaseRunner(Runner):
    def __init__(self, job_dir = None, sample_index = 0):
        super().__init__()
        self.mName = 'phase'
        self.mParamSet = None
        self.job_dir = job_dir
        self.sample_index = sample_index
        self.result_dir = os.path.join(job_dir, f'iter{sample_index}')

        self.input_dir = 'sota/Phase/'
        self.perf_dir = os.path.join(self.result_dir, 'perf')
        self.time_record_dir = os.path.join(self.result_dir, 'time_record')
        self.time_record = []
        self.phase_aware = True
        self.sample_dir = os.path.join(self.input_dir,f'stage{self.sample_index}')
        self.target_path = os.path.join(self.sample_dir,'targets.csv')
        self._create_directories()

    def _create_directories(self):
        """创建所有必要的目录"""
        # 收集需要创建的目录路径
        dirs_to_create = [
            self.job_dir,
            self.result_dir,
            self.perf_dir,
            self.time_record_dir,
            self.sample_dir
        ]
        
        # 过滤掉无效路径并创建目录
        for directory in filter(None, dirs_to_create):
            os.makedirs(directory, exist_ok=True)

    def GetParamSets(self):
        # 打开 CSV 文件
        command = f'cd {os.getcwd()}/{self.input_dir}; python3 generate.py --result_dir {self.result_dir} --sample_index {self.sample_index} --delay_iters 50'
        run_command(command)
        param_path = os.path.join(self.input_dir, 'param_sets.csv')
        with open(param_path, 'r') as file:
            reader = csv.DictReader(file)
            param_sets = []
            for row in reader:
                param_set = row['param_set']
                try:
                    template_obj = eval(param_set)
                    param_sets.append(template_obj)
                except SyntaxError:
                    print(f"无法解析 generated_template: {param_set}")
        return param_sets

    '''def PreStart(self,param_set): #采集block
        data = param_set
        params={
            "global":{
                "memory_util":data[-1],
                "memory_size":data[-2]
            },
            "blocks":[]
        }
        block_num = len(data)-2
        for i in range(block_num):
            block = data[i]
            if block[1]=='mem':
                block_type = 'memory_block'
                iters = block[2]
                stride = block[3]
                params["blocks"].append({
                    "type" :block_type,
                    "iterations" : iters,
                    "stride" : stride
                })
            elif block[1]=='add':
                block_type = 'add_block'
                iters = block[2]
                params["blocks"].append({
                    "type" :block_type,
                    "iterations" : iters,
                })
            elif block[1]=='div':
                block_type = 'div_block'
                iters = block[2]
                params["blocks"].append({
                    "type" :block_type,
                    "iterations" : iters,
                })
            elif block[1]=='sqrt':
                block_type = 'sqrt_block'
                iters = block[2]
                params["blocks"].append({
                    "type" :block_type,
                    "iterations" : iters,
                })
            elif block[1]=='ari':
                block_type = 'ari_block'
                iters = block[2]
                factor = block[3]
                params["blocks"].append({
                    "type" :block_type,
                    "iterations" : iters,
                    "factor": factor
                })
            elif block[1]=='sleep':
                block_type = 'sleep_block'
                iters = block[2]
                params["blocks"].append({
                    "type" :block_type,
                    "iterations" : iters,
                })
            elif block[1]=='disk':
                block_type = 'disk_block'
                iters = block[2]
                params["blocks"].append({
                    "type" :block_type,
                    "iterations" : iters,
                })
            params["blocks"][-1]["rank"] = block[0]
            params["blocks"][-1]=[params['blocks'][-1]]
        config_path = './workloads/phase/config_files/config.json'

        save_json(config_path,params)'''
    
    def PreStart(self,param_set):
        data = param_set
        print(data)
        params={
            "global":{
                "memory_util":data[-1],
                "memory_size":data[-2]
            },
            "blocks":[]
        }
        group_num = len(data)-2
        for i in range(group_num):
            group = data[i]
            params["blocks"].append([])
            for block in group:
                if block[1]=='mem':
                    block_type = 'memory_block'
                    iters = block[2]
                    stride = block[3]
                    params["blocks"][-1].append({
                        "type" :block_type,
                        "iterations" : iters,
                        "stride" : stride
                    })
                elif block[1]=='add':
                    block_type = 'add_block'
                    iters = block[2]
                    params["blocks"][-1].append({
                        "type" :block_type,
                        "iterations" : iters,
                    })
                elif block[1]=='div':
                    block_type = 'div_block'
                    iters = block[2]
                    params["blocks"][-1].append({
                        "type" :block_type,
                        "iterations" : iters,
                    })
                elif block[1]=='sqrt':
                    block_type = 'sqrt_block'
                    iters = block[2]
                    params["blocks"][-1].append({
                        "type" :block_type,
                        "iterations" : iters,
                    })
                elif block[1]=='ari':
                    block_type = 'ari_block'
                    iters = block[2]
                    factor = block[3]
                    params["blocks"][-1].append({
                        "type" :block_type,
                        "iterations" : iters,
                        "factor": factor
                    })
                elif block[1]=='sleep':
                    block_type = 'sleep_block'
                    iters = block[2]
                    params["blocks"][-1].append({
                        "type" :block_type,
                        "iterations" : iters,
                    })
                elif block[1]=='disk':
                    block_type = 'disk_block'
                    iters = block[2]
                    params["blocks"][-1].append({
                        "type" :block_type,
                        "iterations" : iters,
                    })
                params["blocks"][-1][-1]["delay"] = block[-1]
                params["blocks"][-1][-1]["rank"] = block[0]

        config_path = './workloads/phase/config_files/config.json'

        save_json(config_path,params)
    

    @returnTime    
    def Start(self, param_set):
        command = f'cd {os.getcwd()}/workloads/phase; ./parallel  ./config_files/config.json'
        run_command(command)
    
    def GetWorkloadBeginEndTime(self):
        execute_log = f'{os.getcwd()}/workloads/phase/execution_timing.log'
        phase_log = f'{os.getcwd()}/workloads/phase/phase_time.csv'

        target_dir = os.path.join(self.result_dir, "time_record")
    
        # 创建目标目录（若不存在）
        os.makedirs(target_dir, exist_ok=True)
        
        try:
            target_phase_log = os.path.join(target_dir, "phase_time.csv")
            shutil.copy2(phase_log, target_phase_log)  # 复制并保留元数据
            print(f"已复制时间日志到: {target_phase_log}")
        except Exception as e:
            print(f"❌ 复制文件失败: {e}")
            return None
        flag = False
        if os.path.exists(execute_log):
            try:
                with open(execute_log, 'r') as f:
                    lines = f.read().splitlines()
                    if len(lines) >= 2:
                        # 转换时间戳为整数
                        start_time = int(lines[0].strip())
                        end_time = int(lines[1].strip())
                        flag = True
                        print(f"使用日志文件时间戳 | 开始: {start_time} | 结束: {end_time}")
                        
                    else:
                        print("⚠️ 日志文件格式不正确，使用默认时间")
            except ValueError as ve:
                print(f"⛔ 时间戳转换失败: {ve}，使用默认时间")
            except Exception as e:
                print(f"⛔ 读取日志文件失败: {e}，使用默认时间")
        else:
            print("ℹ️ 未找到时间日志文件，使用命令执行时间")
        if flag:
            return[start_time, end_time]
        else:
            return None
        
    
    def GetExtraMetric(self,duration,extra_ratio=0.2):
        target_path = os.path.join(self.input_dir, 'targets.csv')
        result_path = os.path.join(self.result_dir, 'final_aggregations.csv')

        if not os.path.exists(target_path):
            print('no target')
            return None

        # 读取数据文件（注意列名需与实际文件匹配，假设列名小写）
        res_df = pd.read_csv(result_path)
        target_df = pd.read_csv(target_path)

        # 计算新列
        # instruction = final.csv的instruction * 1.2
        
        output_df = res_df.copy()  # 基于final.csv创建输出DataFrame
        output_df['instructions'] = res_df['instructions'] * extra_ratio  # 假设列名为'instruction'
        
        # cycle = target.csv的CPI * 前面的instructions - final.csv的cycle
        # 检查target_df是否存在'CPI'列，且res_df是否存在'cycle'列
        if 'CPI' in target_df.columns and 'cycles' in res_df.columns:
            output_df['cycles'] = target_df['CPI'] * res_df['instructions']*(1+extra_ratio) - res_df['cycles']
        else:
            raise ValueError("目标文件或结果文件缺少必要列")
        
        # ll_miss = target.csv的MPKI * instructions / 1000 - final.csv的ll-miss
        if 'MPKI' in target_df.columns and 'll-misses/' in res_df.columns:
            output_df['ll-misses/'] = target_df['MPKI'] * res_df['instructions']*1.2  / 1000 - res_df['ll-misses/']
        else:
            raise ValueError("目标文件或结果文件缺少必要列")
        output_df['duration'] = duration
        output_df=output_df[['cycles','instructions','ll-misses/','duration']]
        output_df.to_csv(f'{self.input_dir}/linear_target.csv',index=False)
        return output_df
    
    def GetChangePoint(self, sample_index, alg='window', args=None):
        import pandas as pd
        import numpy as np
        import shutil
        stage_dir =  os.path.join(self.input_dir,f'stage{sample_index}')
        png_path =  os.path.join(stage_dir,'stage.png')
        metric_path = os.path.join(stage_dir,'metric_0.csv')
        sub_path = os.path.join(stage_dir,'sub')
        data = pd.read_csv(metric_path) 
        if os.path.exists(sub_path):
            shutil.rmtree(sub_path)  # 删除现有目录
        os.makedirs(sub_path)  # 创建空目录
        COMPARE_COLS = ['CPI', 'MPKI']
        for col in COMPARE_COLS:
            data[col] = smooth_isolated_outliers(data[col])
        # 参数配置
        stages = stage_divide(data,alg,args,png_path)
        # 输出结果
        print("负载阶段划分：")
        aggregate_data = [] 
        for i, (start, end) in enumerate(stages):
            if i == len(stages)-1:
                end+=1
            phase_data = data.iloc[start : end]
            file_path = os.path.join(sub_path,f'metric_{i}.csv')
            # 保存CSV（保留列名和索引可选）
            phase_data.to_csv(file_path, index=False)
            print(f"阶段 {i+1}: {start} 至 {end-1}")
            # 计算聚合指标
            cpu_util_mean = phase_data['cpu_util'].mean()
            # 关键修正：计算总和再相除
            sum_cycles = phase_data['cycles'].sum()
            sum_instructions = phase_data['instructions'].sum()
            sum_llc_misses = phase_data['ll-misses/'].sum()
            avg_cpi = phase_data['CPI'].mean()
            avg_mpki = phase_data['MPKI'].mean()
            # 避免除零错误
            if sum_instructions > 0:
                cpi = sum_cycles / sum_instructions
                mpki = (sum_llc_misses * 1000) / sum_instructions
            else:
                cpi = np.nan
                mpki = np.nan
        
            
            aggregate_data.append({
                'duration': end-start,
                'cpu_util': cpu_util_mean*100,
                'mem_util': 30,
                'CPI': cpi,
                'MPKI': mpki,
                'avg_CPI':avg_cpi,
                'avg_MPKI':avg_mpki,
                'disk_util':3,
                'power':280,
                'mem_capacity': 64,
                'mem_size':256,
                'instruction':sum_instructions
            })
        # 计算所有阶段的CPU利用率均值
        all_cpu_util = [item['cpu_util'] for item in aggregate_data]
        average_cpu_util = sum(all_cpu_util) / len(all_cpu_util) if all_cpu_util else 0
        scale_factor = 1
        # 如果平均CPU利用率小于10，则调整指令数
        if average_cpu_util < 20:
            scale_factor = 20 / average_cpu_util
        for item in aggregate_data:
            item['instruction'] *= scale_factor
            item['scale_factor'] =  scale_factor
        aggr_df = pd.DataFrame(aggregate_data)
        aggr_path = os.path.join(stage_dir, 'aggr.csv')
        aggr_df.to_csv(aggr_path, index=False)


    def GetGAConvergencePoint(self):
        from pathlib import Path
        import re
        def detect_convergence_point(data):
            """检测遗传算法数据的收敛点，返回收敛时的迭代代数"""
            # 计算相邻迭代的Best_Objective变化率
            data['delta_obj'] = data['Best_Objective'].diff().abs()
            if not data['Best_Objective'].empty and data['Best_Objective'].shift(1).abs().iloc[0] != 0:
                data['delta_ratio'] = data['delta_obj'] / data['Best_Objective'].shift(1).abs()
            else:
                data['delta_ratio'] = 0  # 处理初始值为0的情况
            
            # 设置收敛阈值（变化率小于0.5%且连续3次迭代）
            CONVERGENCE_THRESHOLD = 0.005
            CONSECUTIVE_ITERATIONS = 3
            
            # 标记可能的收敛点
            data['is_converging'] = data['delta_ratio'] < CONVERGENCE_THRESHOLD
            
            # 检查连续收敛次数
            data['consecutive_converge'] = data['is_converging'].cumsum() - data['is_converging'].cumsum().where(~data['is_converging']).ffill().fillna(0)
            
            # 找到首次满足连续收敛条件的点
            try:
                convergence_index = data[data['consecutive_converge'] >= CONSECUTIVE_ITERATIONS].index[0]
                return data.loc[convergence_index, 'Generation']
            except IndexError:
                # 若未找到收敛点，返回最后一代
                return data['Generation'].iloc[-1]

        def extract_iter_phase_from_path(file_path):
            """从文件路径中提取iter和phase值"""
            # 匹配iter{i}格式
            iter_match = re.search(r'iter(\d+)', file_path)
            iter_value = iter_match.group(1) if iter_match else '0'
            
            # 匹配convergence_data{j}.csv格式
            phase_match = re.search(r'convergence_data(\d+)\.csv', file_path)
            phase_value = phase_match.group(1) if phase_match else '0'
            
            return iter_value, phase_value

        job_dir = Path(self.job_dir)
        if not job_dir.exists():
            raise FileNotFoundError(f"指定目录不存在: {job_dir}")
        
        # 存储所有收敛点信息
        convergence_results = []
        
        # 遍历所有可能的iter目录
        for iter_dir in job_dir.glob("iter*"):
            if not iter_dir.is_dir():
                continue
            
            # 遍历iter目录下的GA文件夹
            ga_dir = iter_dir / "GA"
            if not ga_dir.exists() or not ga_dir.is_dir():
                continue
            
            # 遍历GA文件夹下的所有CSV文件
            for csv_file in ga_dir.glob("convergence_data*.csv"):
                try:
                    # 读取数据
                    data = pd.read_csv(csv_file)
                    
                    # 提取iter和phase
                    iter_i, phase_j = extract_iter_phase_from_path(str(csv_file))
                    
                    # 检测收敛点
                    convergence_gen = detect_convergence_point(data)
                    
                    # 添加到结果列表
                    convergence_results.append({
                        'iter=i': f'iter={iter_i}',
                        'phase=j': f'phase={phase_j}',
                        '收敛点': convergence_gen
                    })
                    
                    print(f"已处理文件: {csv_file.name}, iter={iter_i}, phase={phase_j}, 收敛于第 {convergence_gen} 代")
                    
                except Exception as e:
                    print(f"处理文件 {csv_file.name} 时出错: {e}")
        output_file = os.path.join(self.job_dir, 'GA_convergence.csv')
        # 转换为DataFrame并保存
        if convergence_results:
            results_df = pd.DataFrame(convergence_results)
            results_df.to_csv(output_file, index=False, columns=['iter=i', 'phase=j', '收敛点'])
            print(f"收敛点整合结果已保存至: {output_file}")
            return results_df
        else:
            print("未找到任何收敛点数据")
            return None      

        
