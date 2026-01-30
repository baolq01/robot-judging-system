import sys
import socket
import threading
import time
import random
from datetime import datetime
from collections import deque
import logging
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *


logging.basicConfig(
    level=logging.INFO,  # 设置日志级别
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

class Packet:
    def __init__(self, byte1, byte2, byte3, byte4):
        self.byte1 = byte1
        self.byte2 = byte2
        self.byte3 = byte3
        self.byte4 = byte4
        self.timestamp = 0

class SharedData:
    def __init__(self):
        self.raw_packets = deque(maxlen=200)
        self.score_packets = []
        self.lock = threading.Lock()
        self.current_side = "blue"
        self.score = 0
        self.remaining_time_ms = 240000  # 初始值
        self.game_started = False
        self.game_ended = False
        self.game_paused = False
        self.scan_success = False
        self.tech_boost_count = 0
        self.tech_multiplier = 1.0
        self.current_color = 0
        self.golden_score_active = False
        self.last_bounty_time = None
        self.bounty_active = False
        # 时间完全由心跳包控制
        self.last_heartbeat_time = None
        self.heartbeat_interval = 50  # 心跳包间隔(ms)

class PacketReceiver(QThread):
    data_received = pyqtSignal(object)
    heartbeat_updated = pyqtSignal(int)  # 心跳包更新信号
    
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
                        
                        # 首先处理特殊命令（包括心跳包）
                        self._process_special_commands(packet)
                        
                        # 如果是得分相关数据包，在比赛开始中，添加到得分列表
                        if (packet.byte2 in [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07]) and self.shared_data.remaining_time_ms not in [0,240000]:
                            if packet.byte2 == 0x04:
                                self.shared_data.current_color = (packet.byte3 | packet.byte4)
                            self.shared_data.score_packets.append(packet)
                            self._update_score(packet)
                    
                            
                    self.data_received.emit(packet)
                    
            except socket.timeout:
                # 检查心跳包超时
                self._check_heartbeat_timeout()
                continue
            except Exception as e:
                print(f"接收错误: {e}")

            
                
    def _process_special_commands(self, packet):
        """处理特殊命令"""
        byte2_high = packet.byte2 & 0xF0
        
        # 处理心跳包 - 最高优先级
        if byte2_high == 0xB0:
            # 心跳包，获取剩余时间
            new_remaining_time = ((packet.byte3 << 8) | packet.byte4)*100
            self.shared_data.remaining_time_ms = new_remaining_time
            #print(f"心跳包: 剩余时间 {new_remaining_time} ms")
            self.shared_data.last_heartbeat_time = time.time()
            
            # 发射信号通知UI更新
            self.heartbeat_updated.emit(new_remaining_time)

        # 处理开始结束比赛命令
        elif byte2_high == 0x20:  # 正式开始比赛
            self.shared_data.game_started = True
            self.shared_data.game_ended = False
            self.shared_data.game_paused = False
            self.shared_data.score_packets.clear()
            self.shared_data.scan_success = False
            self.shared_data.tech_boost_count = 0
            self.shared_data.tech_multiplier = 1.0
            self.shared_data.golden_score_active = False
            self.shared_data.bounty_active = False
            
        elif byte2_high == 0x30:  # 结束比赛
            self.shared_data.game_ended = True
            self.shared_data.game_started = False
            self.shared_data.game_paused = False
            self.shared_data.score_packets.clear()
            self.shared_data.scan_success = False
            self.shared_data.tech_boost_count = 0
            self.shared_data.tech_multiplier = 1.0
            self.shared_data.golden_score_active = False
            self.shared_data.bounty_active = False
            self.shared_data.score = 0
            self.shared_data.current_color = 0

        elif byte2_high == 0x10:  # 暂停比赛
            self.shared_data.game_paused = True


            
        # 其他特殊命令
        elif packet.byte2 == 0xA0:  # 撤销
            if self.shared_data.score_packets:
                self.shared_data.score_packets.pop()
                self._recalculate_score()

        # # 根据时间判断游戏状态
        # if new_remaining_time == 0:
        #     self.shared_data.game_ended = True
        #     self.shared_data.game_started = False
        # elif new_remaining_time < 240000 and not self.shared_data.game_ended:
        #     self.shared_data.game_started = True
        #     self.shared_data.game_ended = False
        
       
                
        elif packet.byte2 == 0xFF:  # 强制清空
            self.shared_data.score_packets.clear()
            self.shared_data.score = 0
            self.shared_data.scan_success = False
            self.shared_data.tech_boost_count = 0
            self.shared_data.tech_multiplier = 1.0
            self.shared_data.golden_score_active = False
            self.shared_data.bounty_active = False
            self.shared_data.current_color = 0

        if(packet.byte2 != 0xB0 and packet.byte2 != 0x04 and packet.byte2 not in [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07]):
            logging.info(f"收到特殊命令: byte2={packet.byte2:02X}")
            
    def _check_heartbeat_timeout(self):
        """检查心跳包是否超时"""
        if self.shared_data.last_heartbeat_time:
            time_since_last_heartbeat = (time.time() - self.shared_data.last_heartbeat_time) * 1000  # 转换为ms
            
            # 如果超过2个心跳周期没有收到心跳包，认为连接有问题
            if time_since_last_heartbeat > self.shared_data.heartbeat_interval * 2:
                # 可以在这里添加连接状态的提示
                pass
    
    def _update_score(self, packet):
        """更新得分"""
        logging.info(f"收到得分包: byte2={packet.byte2:02X}, byte3|byte4 ={packet.byte3|packet.byte4:02d}")
        # 然后重新遍历所有包进行计算
        self.shared_data.score = 0 
        self.shared_data.tech_boost_count = 0
        for idx, packet in enumerate(self.shared_data.score_packets):
            if packet.byte2 == 0x03:# 上台阶
                    # 读取技术加成总数
                self.shared_data.tech_boost_count = packet.byte3|packet.byte4 
            elif packet.byte2 == 0x01:  # 基础得分
                color = packet.byte3| packet.byte4
                base_scores = {1: 2, 2: 4, 3: 6, 4: 10}
                base_score = base_scores.get(color, 2) 
                # 检查赏金：在当前包之前查找最近的赏金包
                has_bounty = False
                for prev_idx in range(idx-1, -1, -1):
                    prev_packet = self.shared_data.score_packets[prev_idx]
                    if prev_packet.byte2 == 0x04:
                        bounty_color = prev_packet.byte3 | prev_packet.byte4
                        if bounty_color == color:
                            has_bounty = True
                            #bonus_value = getattr(prev_packet, 'byte5', 0)  # 假设加成值在byte5
                        break
                
                # 检查扫码
                has_scan = False
                for prev_idx in range(idx-1, -1, -1):
                    prev_packet = self.shared_data.score_packets[prev_idx]
                    if prev_packet.byte2 == 0x05:
                        has_scan = True
                            #bonus_value = getattr(prev_packet, 'byte5', 0)  # 假设加成值在byte5
                        break
                
                # 检查技术加成：在当前包之前是否有未消耗的0x03包
                has_tech_boost = False
                # 如果有技术加成包在之前，且还有剩余次数
                if self.shared_data.tech_boost_count > 0:
                    has_tech_boost = True
                    # 消耗一次技术加成次数
                    self.shared_data.tech_boost_count -= 1
                
                # 计算总加成
                bonus = 0
                if has_tech_boost:
                    # 技术加成：100%加成（不和赏金/扫码叠加）
                    bonus = base_score
                    #print(f"技术加成，剩余次数: {self.shared_data.tech_boost_count}")
                    # 消耗一次技术加成次数
                    # 注意：这里需要记录哪个0x01包已经使用了技术加成
                else:
                    if has_bounty and has_scan:
                        bonus = base_score  # 100%加成
                    elif has_bounty or has_scan:
                        bonus = base_score * 0.5  # 50%加成
                    #print(f"赏金加成: {has_bounty}, 扫码加成: {has_scan}, 奖励分数: {bonus}")
                
                total_add = base_score + bonus
                self.shared_data.score += total_add

            elif packet.byte2 == 0x02:  # 攻击得分
                self.shared_data.score += 10

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
        self.time_label = QLabel("等待开始...")
        self.time_label.setAlignment(Qt.AlignCenter)
        font = QFont("Arial", 72, QFont.Bold)
        self.time_label.setFont(font)
        
        # 设置蓝方或红方颜色
        if self.shared_data.current_side == "red":
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
        self.scan_indicator.setFixedSize(70,70)
        self.scan_indicator.setStyleSheet("""
            background-color: transparent;
            color: black;
            font-size: 16px;
            font-weight: bold;
            """)
        
        # 游戏状态指示器
        self.status_label = QLabel("等待开始")
        self.status_label.setAlignment(Qt.AlignCenter)
        status_font = QFont("Arial", 24)
        self.status_label.setFont(status_font)
        
        layout.addWidget(self.time_label)
        layout.addWidget(self.score_label, 1)
        layout.addWidget(self.status_label)
        
        # 底部布局
        bottom_layout = QHBoxLayout()
        bottom_layout.addWidget(self.scan_indicator)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.color_widget)
        bottom_layout.addStretch()
        
        layout.addLayout(bottom_layout)
        self.setLayout(layout)
        
    def start_timer(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(50)  # 每50ms更新一次，更流畅
        
    def update_ui(self):
        with self.shared_data.lock:
            # 更新时间显示（完全依赖心跳包）
            remaining_ms = self.shared_data.remaining_time_ms
            minutes = remaining_ms // 60000
            seconds = (remaining_ms % 60000) // 1000
            milliseconds = remaining_ms % 1000
            
            # 根据游戏状态和游戏时间显示不同格式
            if self.shared_data.game_ended:
                self.time_label.setText("比赛结束")
                self.status_label.setText("比赛结束")
            elif self.shared_data.game_started:
                self.time_label.setText(f"剩余时间 {minutes:02d}:{seconds:02d}")
                self.status_label.setText("比赛进行中")
            elif self.shared_data.game_paused:
                self.time_label.setText(f"准备时间 {minutes:02d}:{seconds:02d}")
                self.status_label.setText("准备阶段")
            
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
                self.scan_indicator.setText("成功扫码")
                self.scan_indicator.setStyleSheet("color: #FFD700; font-size: 100px; font-weight: bold;")
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
        
        # 加载数字图片
        self.number_images = {}
        for i in range(10):
            try:
                self.number_images[i] = QPixmap(f"{i}.png")
                print(f"加载图片: {i}.png")
            except:
                # 如果没有图片文件，就用文字代替
                pass
                
    def start_timer(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(500)  # 每500ms检查一次
        
    def update_ui(self):
        with self.shared_data.lock:
            # 检查是否到达2分钟（由心跳包控制）
            if (self.shared_data.game_started and 
                not self.shared_data.game_ended and
                self.shared_data.remaining_time_ms <= 120000 and
                self.shared_data.remaining_time_ms > 99000 and  # 防抖
                not self.two_min_shown):

                self.two_min_shown = True
                random_number = random.randint(0, 9)
                logging.info("随机数字：",random_number)                
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
            if (self.shared_data.game_ended or 
                not self.shared_data.game_started or
                (self.shared_data.remaining_time_ms > 120000 or self.shared_data.remaining_time_ms <= 99000)):
                self.image_label.clear()
                if self.shared_data.remaining_time_ms > 120000:
                    self.two_min_shown = False
                
    def closeEvent(self, event):
        self.timer.stop()
        super().closeEvent(event)

class ScoreSystemApp:
    def __init__(self):
        self.shared_data = SharedData()
        
        # 创建网络接收线程
        self.receiver = PacketReceiver(self.shared_data)
        
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