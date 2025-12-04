import csv

selected_rows = [0]  # 可修改为需要读取的行索引

module_details_list = []
generated_template_list = []
with open('results.csv', 'r') as file:
    reader = csv.DictReader(file)
    for index, row in enumerate(reader):
        if index in selected_rows:
            # 数据解析部分保持不变
            module_detail_str = row['modules_details']
            generated_template_str = row['generated_template']
            try:
                module_detail = eval(module_detail_str)
                generated_template = eval(generated_template_str)
                module_details_list.append(module_detail)
                generated_template_list.append(generated_template)
            except SyntaxError:
                print(f"无法解析数据: {module_detail_str} 或 {generated_template_str}")

for outer_index, (details, template) in enumerate(zip(module_details_list, generated_template_list)):
    print(f"\n第 {selected_rows[outer_index] + 1} 组数据:")
    
    # 初始化总和统计
    total_cycles = 0
    total_instructions = 0
    total_cachemiss = 0
    
    for inner_index, item in enumerate(details):
        # 判断是否为最后一个汇总块
        is_summary = 'T_total_target' in item
        print(item)
        if not is_summary:
            # 输出block详情
            print(f"  block_id: {item['block_id']}")
            print(f"    scaling_factor: {item['scaling_factor']}")
            print(f"    duration: {item['duration']}")
            print(f"    cpu_util: {item['cpu_util']}%")
            print(f"    disk_util: {item['disk_util']}%") 
            print(f"    cycle: {item['cycle']}")
            print(f"    instruction: {item['instruction']}")
            print(f"    ll_miss: {item['ll_miss']}")
            print(f"    block 具体内容: {template[inner_index]}")  
            print()
        else:
            # 更新后的汇总输出块
            print("\n【系统级指标对比】")
            print(f"▶ 耗时指标 | 目标: {item['T_total_target']}ms  实际: {item['T_total_actual']}ms")
            print(f"▶ CPU利用率 | 目标: {item['cpu_util_target']:.1f}%  实际: {item['cpu_util_actual']:.1f}%")
            print(f"▶ 内存压力 | 目标: {item['mem_util_target']:.1f}%  实际: {item['mem_util_actual']:.1f}%")
            print(f"▶ 磁盘负载 | 目标: {item['disk_io_target']:.1f}%  实际: {item['disk_io_actual']:.1f}%")
            
            print("\n【硬件指标统计】")
            print(f"总CPU周期: {item['total_cycle']:,} cycles")
            print(f"总指令数量: {item['total_instruction']:,} instructions")
            print(f"总缓存缺失: {item['total_cachemiss']:,} misses")
            
            print("\n【执行效率分析】") 
            print(f"CPI效率 | 目标: {item['cpi_target']:.2f}  实际: {item['cpi_actual']:.2f} cycles/inst")
            print(f"缓存失效率 | 目标: {item['mpki_target']:.1f}  实际: {item['mpki_actual']:.1f} MPKI")
 
    print("-" * 50)
