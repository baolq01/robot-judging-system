import sys
import socket
import threading
import time
import random
from datetime import datetime, timedelta
from collections import deque
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import struct

class Packet:
    def __init__(self, byte1, byte2, byte3, byte4):
        self.byte1 = byte1
        self.byte2 = byte2
        self.byte3 = byte3
        self.byte4 = byte4
        self.timestamp = time.time()

class SharedData:
    def __init__(self):
        self.raw_packets = deque(maxlen=200)
        self.score_packets = []
        self.lock = threading.Lock()
        self.current_side = "blue"  # 默认蓝方
        self.score = 0
        self.remaining_time_ms = 240000  # 4分钟
        self.game_started = False
        self.game_ended = False
        self.scan_success = False
        self.tech_boost_count = 0
        self.tech_multiplier = 1.0
        self.current_color = 0  # 0:背景色, 1:黑, 2:绿, 3:红, 4:蓝
        self.golden_score_active = False
        self.last_bounty_time = None
        self.bounty_active = False
        self.host_remain_time = 240000  # 主机剩余时间，默认4分钟

class PacketReceiver(QThread):
    data_received = pyqtSignal(object)
    
    def __init__(self, shared_data):
        super().__init__()
        self.shared_data = shared_data
        self.running = True
        self.udp_socket = None
        
    def run(self):
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.udp_socket.bind(('', 8888))
        self.udp_socket.settimeout(1)
        
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                if len(data) >= 6 and data[0] == 0xAF and data[5] == 0xBF:
                    packet = Packet(data[1], data[2], data[3], data[4])
                    
                    with self.shared_data.lock:
                        # 添加到原始数据包列表
                        self.shared_data.raw_packets.append(packet)
                        
                        # 处理特殊命令
                        self._process_special_commands(packet)
                        
                        # 如果是得分相关数据包，添加到得分列表
                        if packet.byte2 in [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07]:
                            if packet.byte2 == 0x04:
                                self.shared_data.current_color = (packet.byte3 | packet.byte4)
                            self.shared_data.score_packets.append(packet)
                            self._update_score(packet)
                            
                    self.data_received.emit(packet)
                    
            except socket.timeout:
                continue
            except Exception as e:
                print(f"接收错误: {e}")
                
    def _process_special_commands(self, packet):
        """处理特殊命令"""
        byte2_high = packet.byte2 & 0xF0
    
        if byte2_high == 0xB0:
            # 心跳包，更新剩余时间
            self.shared_data.host_remain_time = (packet.byte3 << 8) | packet.byte4
            self.shared_data.remaining_time_ms = self.shared_data.host_remain_time
        
        if packet.byte2 == 0xA0:  # 撤销
            if self.shared_data.score_packets:
                self.shared_data.score_packets.pop()
                # 需要重新计算得分
                self._recalculate_score()
                
        elif packet.byte2 == 0xFF:  # 强制清空
            self.shared_data.score_packets.clear()
            self.shared_data.score = 0
            self.shared_data.game_started = False
            self.shared_data.game_ended = False
            self.shared_data.scan_success = False
            self.shared_data.tech_boost_count = 0
            self.shared_data.tech_multiplier = 1.0
            self.shared_data.golden_score_active = False
            #self.shared_data.remaining_time_ms = 240000
            self.shared_data.bounty_active = False
            self.shared_data.current_color = 0  # 0:背景色, 1:黑, 2:绿, 3:红, 4:蓝

        elif byte2_high == 0x00:  # 保留字段
            pass
            
        elif byte2_high == 0x10:  # 3分钟倒计时
            #self.shared_data.remaining_time_ms = 180000
            pass
            
        elif byte2_high == 0x20:  # 正式开始比赛
            self.shared_data.game_started = True
            self.shared_data.game_ended = False
            
        elif byte2_high == 0x30:  # 结束比赛
            self.shared_data.game_ended = True
            self.shared_data.game_started = False
            self.shared_data.score_packets.clear()
            self.shared_data.scan_success = False
            self.shared_data.tech_boost_count = 0
            self.shared_data.tech_multiplier = 1.0
            self.shared_data.golden_score_active = False
            self.shared_data.bounty_active = False
            #self.shared_data.remaining_time_ms = 240000
            self.shared_data.score = 0
            self.shared_data.current_color = 0  # 0:背景色, 1:黑, 2:绿, 3:红, 4:蓝
            
    def _update_score(self, packet):
        """更新得分"""
        if packet.byte2 == 0x01:  # 基础得分
            color = (packet.byte3 << 8) | packet.byte4
            base_scores = {1: 2, 2: 4, 3: 6, 4: 10}
            base_score = base_scores.get(color, 2)
            
            # 检查赏金和扫码加成
            bonus = 0
            has_bounty = False
            has_scan = False
                
            # 检查赏金
            for p in reversed(self.shared_data.score_packets):
                if p.byte2 == 0x04 and (self.shared_data.current_color == (p.byte3 | p.byte4)):
                    has_bounty = True
                    break
                        
            # 检查扫码
            has_scan = self.shared_data.scan_success
                
            if has_bounty and has_scan:
                bonus = base_score  # 100%加成
            elif has_bounty or has_scan:
                bonus = base_score * 0.5  # 50%加成
                    
            total_add = base_score + bonus
            
            # 技术加成
            if self.shared_data.tech_boost_count > 0:
                total_add += base_score * 2  # 200%加成
                self.shared_data.tech_boost_count -= 1
                self.shared_data.golden_score_active = (self.shared_data.tech_boost_count > 0)
                
            self.shared_data.score += total_add

            
        elif packet.byte2 == 0x02:  # 攻击得分
            self.shared_data.score += 10
            
        elif packet.byte2 == 0x03:  # 技术
            count = (packet.byte3 << 8) | packet.byte4
            self.shared_data.tech_boost_count = count
            self.shared_data.tech_multiplier = 2.0
            self.shared_data.golden_score_active = True
            
        elif packet.byte2 == 0x04:  # 赏金
            self.shared_data.bounty_active = True
            self.shared_data.last_bounty_time = time.time()
            
        elif packet.byte2 == 0x05:  # 扫码
            self.shared_data.scan_success = True
            
        elif packet.byte2 == 0x06:  # 扣4分
            self.shared_data.score = max(0, self.shared_data.score - 4)
            
        elif packet.byte2 == 0x07:  # 扣10分
            self.shared_data.score = max(0, self.shared_data.score - 10)
            
    def _recalculate_score(self):
        """重新计算得分"""
        self.shared_data.score = 0
        self.shared_data.scan_success = False
        self.shared_data.tech_boost_count = 0
        self.shared_data.tech_multiplier = 1.0
        self.shared_data.golden_score_active = False
        self.shared_data.bounty_active = False
        
        for packet in self.shared_data.score_packets:
            self._update_score(packet)
            
    def stop(self):
        self.running = False
        if self.udp_socket:
            self.udp_socket.close()

class MainWindow(QWidget):
    def __init__(self, shared_data):
        super().__init__()
        self.shared_data = shared_data
        self.init_ui()
        self.start_timer()
        
    def init_ui(self):
        self.setWindowTitle('比赛计分系统')
        self.setStyleSheet("background-color: #f0f0f0;")
        
        # 主布局
        layout = QVBoxLayout()
        
        # 顶部时间显示
        self.time_label = QLabel("剩余时间 04:00")
        self.time_label.setAlignment(Qt.AlignCenter)
        font = QFont("Arial", 72, QFont.Bold)
        self.time_label.setFont(font)
        
        # 设置蓝方或红方颜色
        if self.shared_data.current_side == "blue":
            self.time_label.setStyleSheet("color: #0000FF;")
        else:
            self.time_label.setStyleSheet("color: #FF0000;")
            
        # 中间得分显示
        self.score_label = QLabel("0")
        self.score_label.setAlignment(Qt.AlignCenter)
        score_font = QFont("Arial", 180, QFont.Bold)
        self.score_label.setFont(score_font)
        
        # 当前关注颜色显示
        self.color_widget = QWidget()
        self.color_widget.setFixedSize(200, 100)
        self.color_widget.setStyleSheet("background-color: #f0f0f0; border: 3px solid #000000;")
        
        # 扫码成功标志
        self.scan_indicator = QLabel()
        self.scan_indicator.setFixedSize(40, 40)
        self.scan_indicator.setStyleSheet("background-color: transparent;")
        
        layout.addWidget(self.time_label)
        layout.addWidget(self.score_label, 1)
        
        # 底部布局
        bottom_layout = QHBoxLayout()
        bottom_layout.addWidget(self.scan_indicator)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.color_widget)
        bottom_layout.addStretch()
        
        layout.addLayout(bottom_layout)
        self.setLayout(layout)
        
    def start_timer(self):
        #self.timer = QTimer()
        self.update_ui()
       # self.timer.start(100)  # 每100ms更新一次
        
    def update_ui(self):
        # 更新剩余时间
        with self.shared_data.lock:
                
            minutes = self.shared_data.host_remain_time // 60000
            seconds = (self.shared_data.host_remain_time % 60000) // 1000
            self.time_label.setText(f"剩余时间 {minutes:02d}:{seconds:02d}")
            
            # 更新得分
            self.score_label.setText(str(int(self.shared_data.score)))

                
            # 更新当前关注颜色
            color_map = {
                0: "#f0f0f0",  # 背景色
                1: "#000000",  # 黑色
                2: "#00FF00",  # 绿色
                3: "#FF0000",  # 红色
                4: "#0000FF"   # 蓝色
            }
            color = color_map.get(self.shared_data.current_color, "#f0f0f0")
            self.color_widget.setStyleSheet(f"background-color: {color}; border: 3px solid #000000;")
            
            # 更新扫码成功标志
            if self.shared_data.scan_success:
                self.scan_indicator.setText("▲")
                self.scan_indicator.setStyleSheet("color: #FFD700; font-size: 240px; font-weight: bold;")
            else:
                self.scan_indicator.setText("")
                
    def closeEvent(self, event):
        self.timer.stop()
        super().closeEvent(event)

class SecondWindow(QWidget):
    def __init__(self, shared_data):
        super().__init__()
        self.shared_data = shared_data
        self.init_ui()
        self.start_timer()
        self.two_min_shown = False
        
    def init_ui(self):
        self.setWindowTitle('数字显示窗口')
        self.setStyleSheet("background-color: #000000;")
        
        layout = QVBoxLayout()
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.image_label)
        self.setLayout(layout)
        
        # 加载数字图片（这里需要你有0-9.png图片文件）
        self.number_images = {}
        for i in range(10):
            try:
                self.number_images[i] = QPixmap(f"{i}.png")
            except:
                # 如果没有图片文件，就用文字代替
                pass
                
    def start_timer(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(1000)  # 每秒检查一次
        
    def update_ui(self):
        with self.shared_data.lock:
            # 检查是否到达2分钟
            if (self.shared_data.game_started and 
                not self.shared_data.game_ended and
                self.shared_data.remaining_time_ms <= 120000 and
                not self.two_min_shown):
                
                self.two_min_shown = True
                random_number = random.randint(0, 9)
                
                # 显示随机数图片
                if random_number in self.number_images:
                    pixmap = self.number_images[random_number]
                    pixmap = pixmap.scaled(400, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.image_label.setPixmap(pixmap)
                else:
                    # 如果没有图片，显示文字
                    self.image_label.setText(str(random_number))
                    self.image_label.setStyleSheet("color: #FFFFFF; font-size: 200px; font-weight: bold;")
                    
            # 如果游戏结束或重置，隐藏图片
            if self.shared_data.game_ended or not self.shared_data.game_started:
                self.image_label.clear()
                self.two_min_shown = False
                
    def closeEvent(self, event):
        self.timer.stop()
        super().closeEvent(event)

class ScoreSystemApp:
    def __init__(self):
        self.shared_data = SharedData()
        
        # 创建网络接收线程
        self.receiver = PacketReceiver(self.shared_data)
        self.receiver.data_received.connect(self.on_packet_received)
        
    def start(self):
        # 启动网络接收
        self.receiver.start()
        
        # 创建UI应用
        self.app = QApplication(sys.argv)
        
        # 创建两个窗口
        self.main_window = MainWindow(self.shared_data)
        self.second_window = SecondWindow(self.shared_data)
        
        # 设置窗口大小和位置
        self.main_window.resize(800, 600)
        self.second_window.resize(400, 400)
        
        # 显示窗口
        self.main_window.show()
        self.second_window.show()
        
        # 运行应用
        sys.exit(self.app.exec_())
        
    def on_packet_received(self, packet):
        """处理接收到的数据包"""
        # 这里可以添加额外的处理逻辑
        pass
        
    def cleanup(self):
        """清理资源"""
        self.receiver.stop()
        self.receiver.wait()

def main():
    app = ScoreSystemApp()
    try:
        app.start()
    finally:
        app.cleanup()

if __name__ == '__main__':
    main()