from configparser import ConfigParser
import os
import pickle
import traceback

from collectors.common.communicate_constants import *
from collectors.center.center_constants import *
import pandas as pd
import threading
import socket

from collectors.common.connection import Connection


class CenterServer:
    '''
    定义主从节点的交互行为
    '''
    def __init__(self) -> None:
        self.m_nodes_info = NODE_INFO
        self.m_node_connections = {} # {name: Connection}
        self.m_send_lk = threading.Lock()
        self.m_data_lk = threading.Lock()
        self.m_nodes_serial_data = {} # {name: df}
        self.m_nodes_param = {} # {name: dict}
        
        self.m_stopped = True
        self.m_thread = None
        
    def connect_nodes(self):
        if not self.m_stopped:
            print("[Center] Error: Center has started")
            return
        self.m_stopped = False
        
        # 连接并启动每个从结点
        for node_info in self.m_nodes_info:
            connection = None
            try:
                # 建立连接
                connection = Connection()
                connection.m_closed = False
                connection.m_name, connection.m_ip, connection.m_port = node_info['name'], node_info['ip'], node_info['port']
                connection.connect_node()
                print(f"[Center]: {connection.m_name} connected")
                
                # 发送启动命令
                self.send_begin_cmd(connection)
                print(f"[Center]: starting {connection.m_name} collector")
                
                self.m_node_connections[node_info['name']] = connection
            except Exception as e:
                print(f'[Center] Error: fail to start connect to {node_info["name"]}, {e}')
                connection.close()
                
    
    def stop(self):
        '''
        停止发送 get 命令，并且向所有 node 发送关闭命令
        '''
        if self.m_stopped:
            print("[Center] Error: Center has stopped")
            return
        
        self.m_stopped = True
        for connection in self.m_node_connections.values():
            try:
                if connection.m_closed:
                    continue 
                res = self.send_stop_cmd(connection)
                print(f'receive {res}')
                if res != OK:
                    print(f"[Center] Error: collector {connection.m_name} stopped failed. error result: {res}")
                else:
                    print(f"[Center]: collector {connection.m_name} stopped")
            except Exception as e:
                print(f'[Center] Error: send stop cmd exception: {e}')
            try:
                connection.close()
            except Exception as e:
                print(f'[Center] Error: stop connection {e}')
        print('[Center]: send stop command to all nodes')
        
        
    def pull_data_from_nodes(self, data_len):
        ret_data = None
        for connection in self.m_node_connections.values():
            if connection.m_closed:
                continue
            try:
                print(f'[Center]: send get command to {connection.m_name} with datalen: {data_len}')
                ret_data = self.send_getdata_cmd(connection, data_len)
                
                self._append_collector_data(connection.m_name, ret_data)
            except socket.timeout:
                print(f'[Center] Error: timeout for receiving data  from node {connection.m_name}')
            except Exception as e:
                print(f'[Center] Error: {traceback.print_exc()}')
                # print(f'[Center] receive json data: {ret_data}')
                connection.close()
                
    def pull_param_from_nodes(self):
        ret_data = None
        for connection in self.m_node_connections.values():
            if connection.m_closed:
                continue
            try:
                print(f'[Center]: send getparam command to {connection.m_name}')
                ret_data = self.send_getparam_cmd(connection)
    
                self._append_node_param(connection.m_name, ret_data)
            except socket.timeout:
                print(f'[Center] Error: timeout for receiving data  from node {connection.m_name}')
            except Exception as e:
                print(f'[Center] Error: {traceback.print_exc()}')
                # print(f'[Center] receive json data: {ret_data}')
                connection.close()
        
    def _append_collector_data(self, node_name, ret_data):
        df = pickle.loads(ret_data)
        self.m_data_lk.acquire(blocking=True)
        
        if node_name not in self.m_nodes_serial_data.keys():
            self.m_nodes_serial_data[node_name] = df
        self.m_nodes_serial_data[node_name] = \
                pd.concat([self.m_nodes_serial_data[node_name], df]).drop_duplicates(subset='time', keep='first').sort_values(by='time').reset_index(drop=True)
        if df is not None:
            print(f'{df.shape} \n {df.head()} \n {df.tail()}')
        self.m_data_lk.release()
        
    def _append_node_param(self, node_name, ret_data):
        param_dict = pickle.loads(ret_data)
        self.m_data_lk.acquire(blocking=True)
        self.m_nodes_param[node_name] = param_dict
        self.m_data_lk.release()
        

       
    def save_nodes_data(self, filename_prefix):
        '''
        保存所有 node 的数据到文件中，文件名以 filename_prefix 为前缀, node 的名称为后缀
        '''
        cur_wd = os.getcwd()
        os.chdir(os.path.dirname(os.path.realpath(__file__)))
        print('cur wd:', os.getcwd())
        self.m_data_lk.acquire(blocking=True)
        
        for name, df in self.m_nodes_serial_data.items():
            df.to_csv(f'../../result/{filename_prefix}_{name}.csv')
        
        self.m_data_lk.release()
        os.chdir(cur_wd)
    
    def get_nodes_data(self, data_len):
        nodes2df = {}
        self.m_data_lk.acquire(blocking=True)
        
        for name, df in self.m_nodes_serial_data.items():
            nodes2df[name] = df.iloc[-data_len:,:].copy().reset_index(drop=True)
            
        self.m_data_lk.release()
        return nodes2df
        
    def clear_nodes_data(self):
        self.m_data_lk.acquire(blocking=True)
        
        for df in self.m_nodes_serial_data.values():
            df.drop(df.index, inplace=True)
        
        self.m_data_lk.release()
    
    def send_begin_cmd(self, connection):
        '''
        发送启动命令，返回结果
        如果对方关闭连接，会抛出异常
        '''
        self.m_send_lk.acquire(blocking=True)
        connection.send_to_fd(START_NODE_COLLECTOR)
        ret = connection.receive_from_fd()
        self.m_send_lk.release()
        return ret
    
    def send_stop_cmd(self, connection):
        self.m_send_lk.acquire(blocking=True)
        connection.send_to_fd(STOP_NODE_COLLECTOR)
        ret = connection.receive_from_fd()
        self.m_send_lk.release()
        return ret
    
    def send_getdata_cmd(self, connection, num):
        self.m_send_lk.acquire(blocking=True)
        connection.send_to_fd(GET_SERIAL_DATA+','+str(num))
        ret = connection.receive_from_fd()
        self.m_send_lk.release()
        return ret
    
    def send_getparam_cmd(self, connection):
        self.m_send_lk.acquire(blocking=True)
        connection.send_to_fd(GET_NODE_PARAM)
        ret = connection.receive_from_fd()
        self.m_send_lk.release()
        return ret