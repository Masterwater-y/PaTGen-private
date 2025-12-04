# 整合了 node_server 与 node_collector_api
# 1. node_server 负责接收 center 命令
# 2. node_collector_api 负责执行具体的数据采集任务

import os
import pickle
import pickletools
import traceback
import numpy as np
import pandas as pd
from collectors.node.node_collector import NodeCollector
from collectors.node.node_comm import NodeServer

from collectors.common.communicate_constants import *

class NodeWorker:
    '''
    负责启动 server 和 collector，并向 server 注册 RPC 的 handler 方法
    '''
    def __init__(self) -> None:
        self.m_node_collector = NodeCollector()
        self.m_node_server = NodeServer()
        self.m_node_server.register_request_handler(self.request_handler)

    def start(self):
        self.m_node_server.start()
    
    def request_handler(self, request, connection) -> str:
        ''' 
        处理接收到的命令
        '''
        print(f'[NodeServer]: receive command: {request}')
        
        if request == START_NODE_COLLECTOR:
            self.m_node_collector.start_collection()
            print(f'[NodeServer] start collector')
            return OK
            
        elif request.startswith(GET_SERIAL_DATA):
            df = self.getdata_handler(int(request.split(',')[-1]))
            if df is None:
                print('[NodeWorker]: Get empty data from collector, closing connection to Center Node')
                connection.close()
                return None
            else:
                # print(f'send df: {df.shape} \n {df.head()} \n {df.tail()}')
                return pickle.dumps(df, pickle.HIGHEST_PROTOCOL)
            
        elif request.startswith(GET_NODE_PARAM):
            param_dict = self.getparam_handler()
            if param_dict is None:
                print('[NodeWorker]: Get empty param from collector, closing connection to Center Node')
                connection.close()
                return None
            else:
                return pickle.dumps(param_dict, pickle.HIGHEST_PROTOCOL)
            
        elif request == STOP_NODE_COLLECTOR:
            # 关闭 collector
            print(f'[NodeServer]: stop collector and server')
            self.m_node_collector.end_collection()
            self.m_node_server.stop()
            return OK
            
        else:
            print(f'[NodeServer] Error: receive unknown command: {request}')

    def getdata_handler(self, num) -> pd.DataFrame:
        '''
        处理 center 的 getdata 命令
        '''
        try:
            if num < 0:
                self.m_node_collector.integrate_collector_data()
            else:
                self.m_node_collector.integrate_collector_data(num)
        except:
            print(f'[NodeWorker]: {traceback.format_exc()}')
            self.m_node_collector.end_collection()
            return None
        df = self.m_node_collector.data
        print(f'[getdata handler]: collector data:\n{df.head()}\n{df.tail()}')
        return df

    def getparam_handler(self) -> pd.DataFrame:
        '''
        处理 center 的 getparam 命令
        '''
        param_dict = self.m_node_collector.get_param()
        return param_dict