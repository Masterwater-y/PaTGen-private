import os

from collectors.center.center_constants import *
from collectors.center.center_comm import CenterServer
from collectors.center.center_collector import CenterCollector


    
    
class CenterWorker:
    '''
    负责启动 server 和 collector，并向 server 注册 RPC 的 handler 方法
    '''
    def __init__(self) -> None:
        self.m_center_collector = CenterCollector()
        self.m_center_server = CenterServer()
        # 启动 center server 而且向 collector 发送启动命令
        self.m_center_server.connect_nodes()
    
    def start_center_collector(self):
        self.m_center_collector.start_collection()
        
    def end_center_collector(self):
        self.m_center_collector.end_collection()
        
    def generate_center_data(self, data_len=MAX_COLLECTED_TIME):
        self.m_center_collector.integrate_collector_data(data_len)
        
    def pull_node_data(self, data_len=MAX_COLLECTED_TIME):
        self.m_center_server.pull_data_from_nodes(data_len)
        
    def pull_node_param(self):
        self.m_center_server.pull_param_from_nodes()
    
    def get_center_data(self, save_dir:str=None):
        self.m_center_collector.integrate_collector_data()
        return self.m_center_collector.get_data(save_dir)
    
    def get_node_data(self):
        return self.m_center_server.m_nodes_serial_data
    
    def get_node_param(self):
        return self.m_center_server.m_nodes_param
    
    def config_collectors(self, config_dict):
        self.m_center_collector.config_collectors(config_dict)
    
    def save_center_data(self, data_type="csv", dir_path=None):
        data = self.get_center_data()
        if data_type == "csv":
            if dir_path is None:
                print("[CenterWorker]: fails to save center data. Please give dir path.")
                return
            if not os.path.exists(dir_path):
                print("[CenterWorker]: fails to save center data. Dir path does not exist.")
            if dir_path.startswith('/'):
                target_dir = dir_path
            else:
                target_dir = os.path.abspath('.') + '/' + dir_path
            if not target_dir.endswith('/'):
                target_dir += '/'
            target_file_name = target_dir+f"center.csv"
            self.data.to_csv(target_file_name, index=False) 
            
        elif data_type == "db":
            pass
        
    def save_node_data(self, data_type="csv", dir_path=None):
        data = self.get_node_data()
        if data_type == "csv":
            if dir_path is None:
                print("[CenterWorker]: fails to save node data. Please give dir path.")
                return
            for node_id in data:
                if not os.path.exists(dir_path):
                    print("[CenterWorker]: fails to save node data. Dir path does not exist.")
                if dir_path.startswith('/'):
                    target_dir = dir_path
                else:
                    target_dir = os.path.abspath('.') + '/' + dir_path
                if not target_dir.endswith('/'):
                    target_dir += '/'
                target_file_name = target_dir+f"{node_id}.csv"
                self.data[node_id].to_csv(target_file_name, index=False) 
        
        elif data_type == "db":
            pass
        
        
        
    
    def stop(self):
        self.m_center_server.stop()
        if self.m_center_collector.is_collecting:
            self.end_center_collector()
        
        
        
