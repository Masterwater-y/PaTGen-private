from configparser import ConfigParser
import sys
import threading
import socket
import traceback
import numpy as np

import pandas as pd

from collectors.common.connection import Connection
from collectors.node.node_constants import COMM_PORT

class NodeServer:
    '''
    开一个线程处理新连接
    '''
    def __init__(self) -> None:
        self.m_center_connection = None
        
        self.m_listen_thread = None
        self.m_listen_stopped = True
        
        self.m_request_handler = None # request_handler(request) -> str
    
    def start(self):
        # 开一个线程监听指定端口，连接到达就接收
        if not self.m_listen_stopped:
            print('[NodeServer] Errors: listen thread has started')
            return
        listen_fd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listen_fd.settimeout(30)
        listen_fd.bind(('0.0.0.0', int(COMM_PORT)))
        listen_fd.listen(1)
        print('[NodeServer]: start listen thread')
        while True:
            try:
                self.m_listen_stopped = False
                conn_fd, conn_addr = listen_fd.accept()
                conn_fd.settimeout(10)
                self.m_center_connection = Connection()
                self.m_center_connection.m_closed = False
                self.m_center_connection.m_name = 'center'
                self.m_center_connection.m_fd = conn_fd
            except socket.timeout:
                print('[NodeServer]: waiting for center connection')
                continue
            self.m_listen_thread = threading.Thread(target=self.server_loop)
            self.m_listen_thread.start()
            self.m_listen_thread.join()
                
    def stop(self):
        # 关闭监听，同时关闭连接线程
        if self.m_listen_stopped:
            print('[NodeServer] Errors: listen thread has stopped')
            return
        
        self.m_listen_stopped = True    
        print("[NodeServer]: listen loop stopped")
        
    def server_loop(self):
        while not self.m_listen_stopped:
            try:
                data = self.m_center_connection.receive_from_fd()
                if data == '':
                    print(f'receive data is None')
                    break
                response = self.m_request_handler(data, self.m_center_connection)
                if self.m_center_connection.m_closed is True:
                    print(f'[NodeServer] {sys._getframe().f_lineno}: Close connection by handler')
                    break
                if response is None:
                    response = ''
                self.m_center_connection.send_to_fd(response)
            except Exception as e:
                print(f'[NodeServer] Error: {traceback.print_exc()}')
                break
        print(f'[NodeServer]: close connection')
        self.m_center_connection.close()
                
    def register_request_handler(self, request_handler):
        self.m_request_handler = request_handler