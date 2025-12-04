import pandas as pd
from ast import literal_eval
from collections import defaultdict
import psutil

def get_mem_usage():
    mem = psutil.virtual_memory()
    return mem.percent

class RWBAnalyzer:
    def __init__(self, csv_path):
        self.df = pd.read_csv(csv_path, converters={'param_set': literal_eval})
        self.mem_rwbs = []
        self.cpu_rwbs = []
        
        for _, row in self.df.iterrows():
            params = row['param_set'][0]
            rwb_type = params[1]
            metadata = {
                'iterations': params[2],
                'mem_usage': row['mem_util'],
                'cpu_usage': row['cpu_util'],
                'cycles': row['cycles'],
                'instructions': row['instructions'],
                'llc_misses': row['ll-misses'],
                'template' : row['param_set']
            }
            
            if rwb_type == 'mem':
                self.mem_rwbs.append(metadata)
            elif rwb_type in ('div', 'add'):
                self.cpu_rwbs.append(metadata)
        


    def optimal_rwb_combination(self, rwbs, capacity, target, resource_type):
        # 初始化动态规划表：记录每个容量下的最佳值（最接近target）、资源使用量和组合
        dp = [{
            'value': None,          # 当前容量下能达到的指标值（instructions或llc_misses）
            'resource': float('inf'), # 当前容量下的资源使用量（越小越好）
            'counts': defaultdict(int)
        } for _ in range(capacity + 1)]
        dp[0]['value'] = 0          # 初始状态：资源使用量为0时，指标值为0
        dp[0]['resource'] = 0

        # 动态规划过程：填充dp表
        for w in range(capacity + 1):
            for idx, rwb in enumerate(rwbs):
                res_needed = rwb[resource_type]
                if res_needed > w:  # 资源不足，跳过
                    continue
                prev_state = dp[w - res_needed]
                if prev_state['value'] is None:  # 前序状态不可达，跳过
                    continue

                # 计算新的指标值
                value = rwb['instructions'] if resource_type == 'cpu_usage' else rwb['llc_misses']
                new_value = prev_state['value'] + value
                new_resource = prev_state['resource'] + res_needed  # 此时new_resource应等于w

                # 计算与target的绝对差
                current_diff = abs(new_value - target)
                existing_diff = abs(dp[w]['value'] - target) if dp[w]['value'] is not None else float('inf')

                # 更新条件：差距更小，或差距相同但资源更少
                if (current_diff < existing_diff) or \
                (current_diff == existing_diff and new_resource < dp[w]['resource']):
                    dp[w] = {
                        'value': new_value,
                        'resource': new_resource,
                        'counts': prev_state['counts'].copy()
                    }
                    dp[w]['counts'][idx] += 1

        # 确定候选的w范围
        if resource_type == 'cpu_usage':
            candidate_ws = [capacity]
        else:
            candidate_ws = [capacity]
            #candidate_ws = range(capacity + 1)

        # 寻找最佳组合：在候选容量中选择最接近target的条目
        best_diff = float('inf')
        best_w = -1
        for w in candidate_ws:
            if dp[w]['value'] is None:
                continue
            current_diff = abs(dp[w]['value'] - target)
            # 处理初始best_w为-1的情况
            if best_w == -1:
                best_diff = current_diff
                best_w = w
            else:
                existing_diff = abs(dp[best_w]['value'] - target)
                if (current_diff < best_diff) or \
                (current_diff == best_diff and dp[w]['resource'] < dp[best_w]['resource']):
                    best_diff = current_diff
                    best_w = w

        # 处理无解情况
        if best_w == -1 or dp[best_w]['value'] is None:
            return [], 0

        best_combination = dp[best_w]

        # 构建返回结果
        combination = []
        total_value = best_combination['value']
        for idx, count in best_combination['counts'].items():
            if count > 0:
                rwb = rwbs[idx]
                combination.append({
                    'rwb': rwb,
                    'count': count,
                    'resource_usage': count * rwb[resource_type],
                    'achieved_value': count * (rwb['instructions'] if resource_type == 'cpu_usage' else rwb['llc_misses'])
                })
        
        return combination, total_value


    def generate_script(self, C_CPU, C_Memory, T_CPI, T_MAI):
        l_seg = C_CPU * 2.6e9
        T_Inst = int(l_seg / T_CPI)
        T_MA = int(T_Inst * T_MAI / 1000)

        # 内存组合（允许不严格）
        mem_combination, achieved_ma = self.optimal_rwb_combination(
            self.mem_rwbs, C_Memory, T_MA, 'mem_usage'
        )
        print(mem_combination)
        # 计算剩余CPU资源
        used_cpu_by_mem = sum(item['count'] * item['rwb']['cpu_usage'] for item in mem_combination)
        used_inst_by_mem = sum(item['count'] * item['rwb']['instructions'] for item in mem_combination)
        
        # 验证CPU资源不超限
        if used_cpu_by_mem > C_CPU:
            raise ValueError("内存型RWB已超出CPU核心限制")
        
        remaining_cpu = C_CPU - used_cpu_by_mem
        remaining_inst = max(T_Inst - used_inst_by_mem, 0)  # 保证非负

        print('remain_inst=',remaining_inst)
        # CPU组合（严格匹配）
        cpu_combination, achieved_inst = self.optimal_rwb_combination(
            self.cpu_rwbs, remaining_cpu, remaining_inst, 'cpu_usage'
        )

        # 计算结果指标
        total_cpu = used_cpu_by_mem + sum(item['count'] * item['rwb']['cpu_usage'] for item in cpu_combination)
        total_mem = sum(item['count'] * item['rwb']['mem_usage'] for item in mem_combination)
        total_inst = sum(item['count'] * item['rwb']['instructions'] for item in mem_combination + cpu_combination)
        total_ma = sum(item['count'] * item['rwb']['llc_misses'] for item in mem_combination + cpu_combination)

        return {
            'memory': mem_combination,
            'cpu': cpu_combination,
            'metrics': {
                'cpu_usage': total_cpu,
                'mem_usage': total_mem,
                'achieved_inst': total_inst,
                'achieved_ma': total_ma,
                'cpi': l_seg / total_inst if total_inst else 0,
                'mai': (total_ma * 1000) / total_inst if total_inst else 0,
                'target_cycle': l_seg,
                'target_inst': T_Inst,
                'target_ma': T_MA
            }
        }

    def generate_template(self, script, duration):
        res = []
        for item in script['memory'] + script['cpu']:
            temp = item['rwb']['template'][0].copy()
            temp[2] = int(temp[2] * duration)
            res.extend([temp] * item['count'])
        return res

if __name__ == "__main__":
    analyzer = RWBAnalyzer('block.csv')
    target_df = pd.read_csv('./targets.csv')
    results = []
    cores = 96

    for task_id, row in target_df.iterrows():
        mem_capacity = row['mem_capacity']
        mem_size = row['mem_size']
        C_CPU = int(row['cpu_util']/100 * cores)


        C_Memory = int((row['mem_util'] * mem_size - get_mem_usage() * mem_capacity)/100)
        print(f'C_mem={C_Memory}')
        script = analyzer.generate_script(C_CPU, C_Memory, row['CPI'], row['MPKI'])
        template = analyzer.generate_template(script, row['duration'])
        print(script)
        results.append({'param_set': template})

    pd.DataFrame(results).to_csv('param_sets.csv', index=False)
