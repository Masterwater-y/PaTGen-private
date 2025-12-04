import os
import sys
from collectors.common.communicate_constants import *
import pandas as pd
import socket

class Connection:
    def __init__(self) -> None:
        self.m_closed = True # 连接是否关闭
        
        self.m_name = None
        self.m_ip = None
        self.m_port = None
        self.m_fd = None
        
        self.m_unread_content = ''
    
    def close(self):
        self.m_closed = True
        
        self.m_name = None
        self.m_ip = None
        self.m_port = None
        if self.m_fd is not None:
            print(f'[Connection]: close fd')
            self.m_fd.close()
        self.m_fd = None
        
    def send_to_fd(self, msg):
        '''
        向对方发送信息
        '''
        if self.m_fd is None:
            print('[Connection] Error: fd is none, cannot send msg')
        # msg += 'EOF'
        type = None
        if isinstance(msg, bytes):
            type = 0
            send_bytes = msg
        else:
            type = 1
            send_bytes = msg.encode()
        # print(f'[Connection] Debug: send msg and bytes length: {len(msg), len(send_bytes)}')
        self.m_fd.send(len(send_bytes).to_bytes(32, 'big'))
        self.m_fd.send(type.to_bytes(32, 'big'))
        
        for begin_idx in range(0, len(send_bytes), 4096):
            self.m_fd.send(send_bytes[begin_idx: begin_idx+4096])
        
    def receive_from_fd(self):
        '''
        从对方端接收信息，直到接收到完整的信息或者连接关闭
        如果(1)对方关闭连接，(2)Connection 被 close: 抛出异常，由调用者处理
        '''
        # print(f'[Connection] Debug: begin receive data.')
        ret_data = None
        cnt = 1
        
        while not self.m_closed:
            try:                    
                # print(f'[Connection] Debug: wait for receive.')
                msg_len = int.from_bytes(self.m_fd.recv(32), 'big')
                type = int.from_bytes(self.m_fd.recv(32), 'big')
                block_len = max(4096, int(msg_len / 10))
                recv_bytes = b''
                while len(recv_bytes) < msg_len:
                    ret_byte = self.m_fd.recv(block_len)
                    cnt += 1
                    if ret_byte == b'' or ret_byte is None:
                        raise Exception('node close connection')
                    recv_bytes += ret_byte
                    # print(f'[Connection] Debug: receive bytes len {len(recv_bytes)}.')
                # json_data += ret
                if type == 1:
                    ret_data = recv_bytes.decode()
                else:
                    ret_data = recv_bytes
                break
                # if 'EOF' in ret:
                #     json_datas = json_data.split('EOF')
                #     json_data, self.m_unread_content = json_datas[0], json_datas[1]
                #     break
            except socket.timeout:
                # print('[Connector]: timeout for receiving')   
                pass
        print(f'[Connection] Debug: receive msg and bytes len {len(ret_data), len(recv_bytes)}.')
        return ret_data
    
    def connect_node(self):
        '''
        连接指定的 node 结点
        '''
        conn_fd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conn_fd.connect((self.m_ip, self.m_port))
        conn_fd.settimeout(5)
        self.m_fd = conn_fd
        return conn_fd
    