import os
import time
import pandas as pd

def data_align(perf_path,out_path,log_path):
    with open(log_path,'r') as fp:
        lines = fp.readlines()
        # 获取最后两行
        s_time=int(lines[-2].split(':')[1].strip())
        e_time=int(lines[-1].split(':')[1].strip())
    data = pd.read_csv(perf_path, index_col=0)
    print(data)
    if 'time' not in data.keys():
        return
    data['temp_time'] = pd.to_datetime(data['time'], unit='s')
    start_time = pd.to_datetime(s_time, unit='s')
    end_time = pd.to_datetime(e_time, unit='s')
    filtered_data = data[(data['temp_time'] >= start_time) & (data['temp_time'] <= end_time)].copy()
    filtered_data.drop('temp_time', axis=1, inplace=True)
    filtered_data.to_csv(out_path, index=False)


perf_list=['image_train_i224','image_train_i112','image_train_i224','image_train_i336','image_train_i448','image_train_b2','image_train_b4','image_train_b8','image_train_b16',
        'image_train_d18','image_train_d34','image_train_d50','image_train_d101',
        'time_train_b2','time_train_b4','time_train_b8','time_train_b16','time_train_n4','time_train_n8','time_train_n16','time_train_n32','time_train_l48','time_train_l96']

for file in perf_list:
    data_align('./result/perf.csv',f'./result/{file}.csv',f'./result/{file}.log')

#data_align('./result/perf.csv','./result/image_train_2.csv','./result/image_train_b2.log')
#data_align('./result/perf.csv','./result/time_train_b2.csv','./result/time_train_b2.log')
#data_align('./result/perf.csv','./result/time_train_l48.csv','./result/time_train_l48.log')
#data_align('./result/perf.csv','./result/time_train_n32.csv','./result/time_train_n32.log')

#data_align('./result/image_img_size.csv','./result/image_train_i336.csv','./result/image_train_i336.log')
#data_align('./result/image_img_size.csv','./result/image_train_i448.csv','./result/image_train_i448.log')

#ata_align('./result/perf.csv','./result/time_train_4f.csv',1719078455,1719080160)
#ata_align('./result/perf.csv','./result/time_train_8f.csv',1719080166,1719081847)
