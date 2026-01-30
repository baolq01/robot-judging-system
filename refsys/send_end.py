import sys
import socket
import struct
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import threading
import time
import random

# 网络配置
BLUE_BROADCAST_ADDR = '192.168.1.105'
RED_BROADCAST_ADDR = '192.168.1.103'

# BLUE_BROADCAST_ADDR = '192.168.1.100'
# RED_BROADCAST_ADDR = '192.168.1.103'
LOCAL_BROADCAST_ADDR = '192.168.1.100'
PORT = 8888  # 假设端口为8888

# 按钮配置
BUTTON_CONFIG = {
    'blue': [
        ('撤销操作', 0xA0, 0),
        ('黑球得分', 0x01, 1),    # 写代号 黑1 绿2 红3 蓝4
        ('绿球得分', 0x01, 2),    
        ('红球得分', 0x01, 3),    
        ('蓝球得分', 0x01, 4),    
        ('扫码成功', 0x05, 0),    
        ('上台阶成功', 0x03, 0),#default 0 需要在QT界面输入具体分数  
        ('攻城得分', 0x02, 0)    
    ],
    'red': [
        ('撤销操作', 0xA0, 0),
        ('黑球得分', 0x01, 1),    # 写代号 黑1 绿2 红3 蓝4
        ('绿球得分', 0x01, 2),    
        ('红球得分', 0x01, 3),    
        ('蓝球得分', 0x01, 4),    
        ('扫码成功', 0x05, 0),    
        ('上台阶成功', 0x03, 0),#default 0 需要在QT界面输入具体分数  
        ('攻城得分', 0x02, 0)  
    ]
}



class SendThread(QThread):
    """发送线程"""
    data_sent = pyqtSignal(bytes, str)  # 发送数据和目标地址
    # 添加一个槽函数，用于接收时间更新
    update_time_signal = pyqtSignal(int)  # 用于在线程内部使用信号槽，但这里我们不需要信号，我们直接定义槽函数
    radseed = [0, 0, 0, 0]  # 用于记录四个阶段的随机奖励值
    
    def __init__(self):
        super().__init__()
        self.running = True
        self.current_time_ms = 240000  # 当前剩余时间，毫秒
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
    def run(self):
        bonus_packet = None
        """发送心跳包"""
        while self.running:
            # 发送默认心跳包给双方
            time_seconds = self.current_time_ms
            default_packet = self.build_packet(0, 0xB0, int(time_seconds/100))
            self.send_packet(default_packet, BLUE_BROADCAST_ADDR)
            self.send_packet(default_packet, RED_BROADCAST_ADDR)
            time.sleep(0.05)  # 20Hz
            print("心跳包发送，剩余时间:", time_seconds/1000)
            print("self.radseed:", self.radseed)
    
            #发送赏金包给双方
            #分4个阶段给予不同奖励，对应int(time_seconds/1000)的范围
            if(int(time_seconds/1000) > 180 and int(time_seconds/1000) < 240):
                if(self.radseed[0] == 0):
                    self.radseed[0] = random.randint(1, 4)
                    bonus_packet = self.build_bonus_packet(self.radseed[0])
                    self.send_packet(bonus_packet, BLUE_BROADCAST_ADDR)
                    self.send_packet(bonus_packet, RED_BROADCAST_ADDR)
            elif(int(time_seconds/1000) > 120 and int(time_seconds/1000) <= 180):
                if(self.radseed[1] == 0):
                    self.radseed[1] = random.randint(1, 4)
                    bonus_packet = self.build_bonus_packet(self.radseed[1])
                    self.send_packet(bonus_packet, BLUE_BROADCAST_ADDR)
                    self.send_packet(bonus_packet, RED_BROADCAST_ADDR)
            elif(int(time_seconds/1000) > 60 and int(time_seconds/1000) <= 120):
                if(self.radseed[2] == 0):
                    self.radseed[2] = random.randint(1, 4)
                    bonus_packet = self.build_bonus_packet(self.radseed[2])
                    self.send_packet(bonus_packet, BLUE_BROADCAST_ADDR)
                    self.send_packet(bonus_packet, RED_BROADCAST_ADDR)
            elif(int(time_seconds/1000) > 0 and int(time_seconds/1000) <= 60):
                if(self.radseed[3] == 0):
                    self.radseed[3] = random.randint(1, 4)
                    bonus_packet = self.build_bonus_packet(self.radseed[3])  
                    self.send_packet(bonus_packet, BLUE_BROADCAST_ADDR)
                    self.send_packet(bonus_packet, RED_BROADCAST_ADDR)
            elif(int(time_seconds/1000) == 0 or int(time_seconds/1000) >= 240):
                self.radseed[0] = 0
                self.radseed[1] = 0
                self.radseed[2] = 0
                self.radseed[3] = 0
                bonus_packet = self.build_bonus_packet(0)
                self.send_packet(bonus_packet, BLUE_BROADCAST_ADDR)
                self.send_packet(bonus_packet, RED_BROADCAST_ADDR)


    # 添加槽函数，用于更新当前剩余时间
    @pyqtSlot(int)
    def update_time(self, time_ms):
        self.current_time_ms = time_ms
            
    def send_packet(self, packet, address):
        """发送数据包"""
        try:
            self.sock.sendto(packet, (address, PORT))
            self.data_sent.emit(packet, address)
        except Exception as e:
            #print(f"发送失败: {e}")
            pass
            
    def build_packet(self, byte1, byte2, value):
        """构建数据包：0xAF + (byte1, byte2, byte3, byte4) + 0xBF"""
        # 使用 >B B B B B 格式，分别对应0xAF, byte1, byte2, byte3, byte4, 0xBF
        byte3 = (value >> 8) & 0xFF  # 高8位
        byte4 = value & 0xFF         # 低8
        return struct.pack('>BBBBBB', 0xAF, byte1, byte2, byte3, byte4, 0xBF)
    
    def build_start_match_packet(self):
        """构建开始比赛数据包：byte2高4位为0x2"""
        # byte1=0表示全局，byte2高4位为0x2表示开始比赛，低4位可以为0
        return self.build_packet(0, 0x20, 0x0000)  # 0x20表示高4位为2
    
    def build_prepare_match_packet(self):
        """构建准备比赛数据包：byte2高4位为0x1"""
        return self.build_packet(0, 0x10, 0x0000)  # 0x10表示高4位为1    
    
    def build_end_match_packet(self):
        """构建结束比赛数据包：byte2高4位为0x3"""
        return self.build_packet(0, 0x30, 0x0000)  # 0x30表示高4位为3
    
    def build_pause_packet(self):
        """构建暂停比赛数据包（如果需要）"""
        # 协议中没有明确暂停，可以根据需要定义
        return self.build_packet(0, 0x00, 0x0000)  # 使用保留字段
    
    def build_bonus_packet(self,value):
        """构建奖励数据包：byte2为0x04"""
        return self.build_packet(0, 0x04, value)
    
    def stop(self):
        self.running = False
        self.radseed[0] = 0

class ScoreButton(QPushButton):
    """自定义按钮类，支持点击后禁用"""
    def __init__(self, text, byte2, value, parent=None):
        super().__init__(text, parent)
        self.byte2 = byte2
        self.value = value
        self.clicked_count = 0
        self.max_clicks = 1 if byte2 in [0x05, 0x03] else float('inf')  # 扫码和上台阶只能点一次
        
    def click(self):
        if self.clicked_count < self.max_clicks:
            super().click()
            self.clicked_count += 1
            if self.clicked_count >= self.max_clicks:
                self.setEnabled(False)
                self.setStyleSheet("background-color: gray; color: white;")

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.init_ui()
        self.send_thread = SendThread()
        self.send_thread.data_sent.connect(self.on_data_sent)
        self.send_thread.start()
        
        # 计时器
        self.total_time = 4 * 60 * 1000  # 4分钟，单位毫秒
        self.current_time = self.total_time
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_timer)
        self.timer_interval = 1000  # 1秒
        
    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle('比赛计分系统')
        self.setGeometry(100, 100, 1200, 800)
        
        # 中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        
        # 计时器显示
        timer_layout = QHBoxLayout()
        self.time_label = QLabel('04:00')
        self.time_label.setAlignment(Qt.AlignCenter)
        self.time_label.setStyleSheet("font-size: 48px; font-weight: bold;")
        timer_layout.addWidget(self.time_label)
        main_layout.addLayout(timer_layout)
        
        # 控制按钮
        control_layout = QHBoxLayout()
        self.start_btn = QPushButton('开始比赛！')
        self.prepare_btn = QPushButton('三分钟准备')
        self.pause_btn = QPushButton('暂停比赛')
        self.end_btn = QPushButton('结束比赛')
        
        # 设置按钮样式
        for btn in [self.start_btn, self.prepare_btn, self.pause_btn, self.end_btn]:
            btn.setStyleSheet("font-size: 16px; padding: 10px;")
            btn.setMinimumHeight(50)
        
        control_layout.addWidget(self.start_btn)
        control_layout.addWidget(self.prepare_btn)
        control_layout.addWidget(self.pause_btn)
        control_layout.addWidget(self.end_btn)
        main_layout.addLayout(control_layout)
        
        # 连接控制按钮信号
        self.start_btn.clicked.connect(self.start_match)
        self.prepare_btn.clicked.connect(self.prepare_match)
        self.pause_btn.clicked.connect(self.pause_match)
        self.end_btn.clicked.connect(self.end_match)
        
        # 得分区域
        score_layout = QHBoxLayout()
        
        # 蓝方区域
        blue_widget = QWidget()
        blue_widget.setStyleSheet("background-color: #E6F3FF;")
        blue_layout = QVBoxLayout(blue_widget)
        blue_layout.addWidget(QLabel('蓝方', alignment=Qt.AlignCenter))
        blue_layout.addStretch()
        
        # 蓝方按钮
        self.blue_buttons = []
        for text, byte2, value in BUTTON_CONFIG['blue']:
            btn = ScoreButton(text, byte2, value)
            btn.clicked.connect(lambda checked, b=btn, side='blue': 
                               self.on_score_button_clicked(b, side))
            btn.setStyleSheet("""
                QPushButton {
                    font-size: 14px;
                    padding: 8px;
                    margin: 2px;
                    background-color: #4A90E2;
                    color: white;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #357AE8;
                }
                QPushButton:disabled {
                    background-color: gray;
                }
            """)
            blue_layout.addWidget(btn)
            self.blue_buttons.append(btn)
        
        blue_layout.addStretch()
        score_layout.addWidget(blue_widget, 1)
        
        # 红方区域
        red_widget = QWidget()
        red_widget.setStyleSheet("background-color: #FFE6E6;")
        red_layout = QVBoxLayout(red_widget)
        red_layout.addWidget(QLabel('红方', alignment=Qt.AlignCenter))
        red_layout.addStretch()
        
        # 红方按钮
        self.red_buttons = []
        for text, byte2, value in BUTTON_CONFIG['red']:
            btn = ScoreButton(text, byte2, value)
            btn.clicked.connect(lambda checked, b=btn, side='red': 
                               self.on_score_button_clicked(b, side))
            btn.setStyleSheet("""
                QPushButton {
                    font-size: 14px;
                    padding: 8px;
                    margin: 2px;
                    background-color: #E74C3C;
                    color: white;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #C0392B;
                }
                QPushButton:disabled {
                    background-color: gray;
                }
            """)
            red_layout.addWidget(btn)
            self.red_buttons.append(btn)
        
        red_layout.addStretch()
        score_layout.addWidget(red_widget, 1)
        
        main_layout.addLayout(score_layout, 1)
        
        # 状态栏
        self.statusBar().showMessage('就绪')

    def on_score_button_clicked(self, button, side):
        """得分按钮点击处理"""
        # 如果是上台阶按钮（byte2=0x03），弹出输入框
        if button.byte2 == 0x03:  # 上台阶得分
            self.show_capture_count_dialog(button, side)
        else:
            # 其他按钮按原逻辑处理
            self.send_score_packet(button, side)
    
    def show_capture_count_dialog(self,button, side):
        """显示上台阶得分输入对话框"""

        dialog = QDialog(self)
        dialog.setWindowTitle(f'{side}方 - 上台阶得分')
        dialog.setFixedSize(300, 150)
        
        layout = QVBoxLayout()
        
        # 输入框和标签
        label = QLabel("请输入攻城有效小球数量:")
        layout.addWidget(label)
        
        spin_box = QSpinBox()
        spin_box.setRange(0, 99)  # 设置范围，可以根据需要调整
        spin_box.setValue(1)  # 默认值
        layout.addWidget(spin_box)
        
        # 按钮布局
        button_layout = QHBoxLayout()
        ok_button = QPushButton("确定")
        cancel_button = QPushButton("取消")
        
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        
        # 连接信号
        ok_button.clicked.connect(lambda: self.on_capture_count_confirmed(button, side, spin_box.value(), dialog))
        cancel_button.clicked.connect(dialog.reject)
        
        dialog.exec_()
    
    def on_capture_count_confirmed(self, button, side, count, dialog):
        """攻城小球数量确认"""
        # 关闭对话框
        dialog.accept()
        
        # 发送数据包，使用输入的count作为value
        byte1 = 1 if side == 'blue' else 2  # 1:蓝方, 2:红方
        packet = self.send_thread.build_packet(byte1, button.byte2, count)
        
        address = BLUE_BROADCAST_ADDR if side == 'blue' else RED_BROADCAST_ADDR
        self.send_thread.send_packet(packet, address)
        
        # 更新按钮文本显示小球数量（可选）
        button.setText(f'上台阶成功 ({count})')
        
        # 更新状态栏
        self.statusBar().showMessage(f'{side}方上台阶翻倍加成: {count}个小球', 2000)
        #更新按钮颜色
        button.setStyleSheet("background-color: gray; color: white;")

    def send_score_packet(self, button, side):
        """发送得分数据包"""
        byte1 = 1 if side == 'blue' else 2  # 1:蓝方, 2:红方
        packet = self.send_thread.build_packet(byte1, button.byte2, button.value)
        
        address = BLUE_BROADCAST_ADDR if side == 'blue' else RED_BROADCAST_ADDR
        self.send_thread.send_packet(packet, address)
        
        # 更新按钮状态
        if button.byte2 in [0x05, 0x03]:  # 扫码
            button.setEnabled(False)
            button.setStyleSheet("background-color: gray; color: white;")
    
    def start_match(self):
        """开始比赛"""
        self.current_time = 4 * 60 * 1000  # 4分钟
        self.update_timer_display()
        self.timer.start(self.timer_interval)
        self.is_match_started = True
        packet = self.send_thread.build_start_match_packet()
        self.send_thread.send_packet(packet, BLUE_BROADCAST_ADDR)
        self.send_thread.send_packet(packet, RED_BROADCAST_ADDR)
        #self.statusBar().showMessage('比赛已开始')
        self.statusBar().showMessage('比赛已开始')
    
    def prepare_match(self):
        """三分钟准备"""
        packet = self.send_thread.build_prepare_match_packet()
        self.send_thread.send_packet(packet, BLUE_BROADCAST_ADDR)
        self.send_thread.send_packet(packet, RED_BROADCAST_ADDR)
        
        self.current_time = 3 * 60 * 1000  # 3分钟
        self.update_timer_display()
        self.timer.start(self.timer_interval)
        self.statusBar().showMessage('三分钟准备')
    
    def pause_match(self):
        """暂停比赛"""
        if self.timer.isActive():
            self.timer.stop()
            self.statusBar().showMessage('比赛已暂停')
        else:
            self.timer.start(self.timer_interval)
            self.statusBar().showMessage('比赛继续')
    
    def end_match(self):
        """结束比赛"""
        packet = self.send_thread.build_end_match_packet()
        self.send_thread.send_packet(packet, BLUE_BROADCAST_ADDR)
        self.send_thread.send_packet(packet, RED_BROADCAST_ADDR)
        self.timer.stop()
        self.current_time = self.total_time
        self.update_timer_display()
        self.radseed = [0, 0, 0, 0]  # 重置随机奖励值
        # 手动调用一次计时器更新
        self.send_thread.update_time(self.current_time)
    
        
        # 重置所有按钮
        self.reset_all_buttons()
        self.statusBar().showMessage('比赛已结束')
    
    def reset_all_buttons(self):
        """重置所有按钮状态"""
        for btn in self.blue_buttons + self.red_buttons:
            btn.setEnabled(True)
            btn.clicked_count = 0
            if btn.byte2 == 1:  # 基础得分
                btn.setStyleSheet("""
                    QPushButton {
                        font-size: 14px;
                        padding: 8px;
                        margin: 2px;
                        background-color: #4A90E2;
                        color: white;
                        border-radius: 5px;
                    }
                """)
            elif btn.byte2 == 2:  # 攻击得分
                btn.setStyleSheet("""
                    QPushButton {
                        font-size: 14px;
                        padding: 8px;
                        margin: 2px;
                        background-color: #4A90E2;
                        color: white;
                        border-radius: 5px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        font-size: 14px;
                        padding: 8px;
                        margin: 2px;
                        background-color: #4A90E2;
                        color: white;
                        border-radius: 5px;
                    }
                """)
    
    def update_timer(self):
        """更新计时器"""
        if self.current_time > 0:
            self.current_time -= 1000
            self.update_timer_display()

            # 直接更新线程中的时间信息
            self.send_thread.update_time(self.current_time)

        else:
            self.timer.stop()
            self.send_thread.update_time(0)
            self.end_match()
    
    def update_timer_display(self):
        """更新计时器显示"""
        minutes = self.current_time // 60000
        seconds = (self.current_time % 60000) // 1000
        self.time_label.setText(f'{minutes:02d}:{seconds:02d}')
        
        # 颜色变化
        if self.current_time < 60000:  # 最后1分钟变红色
            self.time_label.setStyleSheet("font-size: 48px; font-weight: bold; color: red;")
        elif self.current_time < 180000:  # 最后3分钟变橙色
            self.time_label.setStyleSheet("font-size: 48px; font-weight: bold; color: orange;")
        else:
            self.time_label.setStyleSheet("font-size: 48px; font-weight: bold; color: black;")
    
    def on_data_sent(self, packet, address):
        """数据发送成功回调"""
        hex_str = ' '.join(f'{b:02X}' for b in packet)
        self.statusBar().showMessage(f'已发送到 {address}: {hex_str}', 1000)
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        self.send_thread.stop()
        self.send_thread.wait()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # 设置中文字体
    font = QFont('Microsoft YaHei', 10)
    app.setFont(font)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())