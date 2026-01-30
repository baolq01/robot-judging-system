import pygame
import socket
import threading
import time
import struct
from enum import IntEnum
import os
import sys

# 网络配置
BROADCAST_PORT = 8888
# 根据你的说明，这是目标IP
BLUE_TARGET_ADDR = '192.168.1.105'  # 蓝方目标
RED_TARGET_ADDR = '192.168.1.103'   # 红方目标

# 颜色定义
BLUE = (30, 144, 255)
RED = (220, 20, 60)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (200, 200, 200)
DARK_BLUE = (0, 0, 139)
DARK_RED = (139, 0, 0)
GREEN = (0, 200, 0)
YELLOW = (255, 215, 0)
PURPLE = (128, 0, 128)
LIGHT_GREEN = (144, 238, 144)
LIGHT_RED = (255, 182, 193)
LIGHT_BLUE = (173, 216, 230)
DARK_GREEN = (0, 100, 0)
ORANGE = (255, 165, 0)
DARK_GRAY = (100, 100, 100)

# 目标类型
class TargetType(IntEnum):
    UNSPECIFIED = 0
    BLUE_TEAM = 1
    RED_TEAM = 2

# 操作类型
class ActionType(IntEnum):
    DO_NOTHING = 0x00
    BASIC_SCORE = 0x01
    ATTACK_SCORE = 0x02
    TECH_SCORE = 0x03
    UNDO = 0xA0
    RESET = 0xFF

class Button:
    """自定义按钮类"""
    def __init__(self, x, y, width, height, text, normal_color, hover_color=None, click_color=None, enabled=True, font_size=24):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.normal_color = normal_color
        self.hover_color = hover_color or normal_color
        self.click_color = click_color or normal_color
        self.enabled = enabled
        self.clicked = False
        self.hovered = False
        
        # 使用支持中文的字体
        self.font = self.get_chinese_font(font_size)
    
    def get_chinese_font(self, size):
        """获取支持中文的字体"""
        # 尝试多种中文字体
        font_paths = [
            "C:/Windows/Fonts/simhei.ttf",  # Windows 黑体
            "C:/Windows/Fonts/msyh.ttc",    # Windows 微软雅黑
            "/System/Library/Fonts/PingFang.ttc",  # macOS
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",  # Linux
            "simhei.ttf",  # 当前目录下的字体文件
        ]
        
        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    return pygame.font.Font(font_path, size)
                except:
                    continue
        
        # 如果都找不到，使用默认字体（可能不支持中文）
        print("警告: 未找到中文字体，中文显示可能不正常")
        return pygame.font.Font(None, size)
    
    def draw(self, screen):
        if not self.enabled:
            # 禁用状态
            color = DARK_GRAY
            text_color = (100, 100, 100)
        elif self.clicked:
            # 点击状态
            color = self.click_color
            text_color = WHITE
        elif self.hovered:
            # 悬停状态
            color = self.hover_color
            text_color = WHITE
        else:
            # 正常状态
            color = self.normal_color
            text_color = BLACK
        
        # 绘制按钮背景
        pygame.draw.rect(screen, color, self.rect, border_radius=8)
        pygame.draw.rect(screen, BLACK, self.rect, 2, border_radius=8)
        
        # 绘制按钮文字（支持多行）
        lines = self.text.split('\n')
        total_height = len(lines) * self.font.get_height()
        start_y = self.rect.centery - total_height // 2 + self.font.get_height() // 2
        
        for i, line in enumerate(lines):
            if line.strip():  # 跳过空行
                text_surf = self.font.render(line, True, text_color)
                text_rect = text_surf.get_rect(center=(self.rect.centerx, 
                                                     start_y + i * self.font.get_height()))
                screen.blit(text_surf, text_rect)
    
    def is_clicked(self, pos):
        if not self.enabled:
            return False
        return self.rect.collidepoint(pos)
    
    def update_hover(self, pos):
        self.hovered = self.rect.collidepoint(pos) and self.enabled
    
    def set_enabled(self, enabled):
        self.enabled = enabled
    
    def set_clicked(self, clicked):
        if self.enabled:
            self.clicked = clicked
            return True
        return False

class ScoreControlApp:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((1200, 800), pygame.RESIZABLE)
        pygame.display.set_caption("比赛得分控制系统 - 发送端")
        
        # 使用支持中文的字体
        self.title_font = self.get_chinese_font(36)
        self.timer_font = self.get_chinese_font(64)
        self.button_font = self.get_chinese_font(24)
        
        # 网络初始化
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
        # 游戏状态
        self.running = True
        self.match_started = False
        self.match_paused = False
        self.match_ended = False
        
        # 时间控制
        self.total_time = 4 * 60  # 4分钟，单位秒
        self.remaining_time = self.total_time
        self.last_time_update = time.time()
        
        # 初始化按钮列表
        self.control_buttons = []  # 控制按钮（开始、暂停等）
        self.blue_buttons = []     # 蓝方得分按钮
        self.red_buttons = []      # 红方得分按钮
        
        # 创建按钮
        self.create_buttons()
        
        # 按钮状态记录（用于撤销功能）
        self.last_blue_action = None  # (button_index, packet_data)
        self.last_red_action = None   # (button_index, packet_data)
        
        # 特殊状态
        self.blue_qr_scanned = False
        self.blue_stair_climbed = False
        self.red_qr_scanned = False
        self.red_stair_climbed = False
        
        # 心跳发送线程
        self.heartbeat_running = True
        self.heartbeat_thread = threading.Thread(target=self.heartbeat_sender, daemon=True)
        self.heartbeat_thread.start()
        
        # 最后操作时间（用于心跳控制）
        self.last_action_time = time.time()
        
        # 当前选择的目标
        self.selected_target = None  # 用于包编辑功能
    
    def get_chinese_font(self, size):
        """获取支持中文的字体"""
        font_paths = [
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/msyh.ttc",
            "/System/Library/Fonts/PingFang.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "simhei.ttf",
        ]
        
        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    return pygame.font.Font(font_path, size)
                except:
                    continue
        
        print("警告: 未找到中文字体，使用默认字体")
        return pygame.font.Font(None, size)
    
    def create_packet(self, target: TargetType, action: ActionType, value: int) -> bytes:
        """
        创建数据包
        格式: 0xBF (4字节数据) 0xBF
        4字节数据: target(1字节) action(1字节) value_high(1字节) value_low(1字节)
        """
        # 验证value范围 (0-65535)
        if value < 0 or value > 0xFFFF:
            raise ValueError(f"Value {value} out of range (0-65535)")
        
        # 将value拆分为两个字节
        value_high = (value >> 8) & 0xFF
        value_low = value & 0xFF
        
        # 构建数据包
        packet = bytearray()
        packet.append(0xBF)  # 包头
        packet.append(target.value)  # 目标
        packet.append(action.value)  # 操作类型
        packet.append(value_high)  # value高字节
        packet.append(value_low)   # value低字节
        packet.append(0xBF)  # 包尾
        
        print(f"创建数据包: 目标={target.name}({target.value}), "
              f"操作={action.name}({action.value:02X}), "
              f"值={value}(0x{value_high:02X}{value_low:02X})")
        
        return bytes(packet)
    
    def send_packet(self, target_addr: str, packet: bytes):
        """发送数据包到指定地址"""
        try:
            self.socket.sendto(packet, (target_addr, BROADCAST_PORT))
            print(f"发送数据包到 {target_addr}:{BROADCAST_PORT}")
            
            # 更新最后操作时间
            self.last_action_time = time.time()
            
        except Exception as e:
            print(f"发送失败: {e}")
    
    def send_to_target(self, target: TargetType, action: ActionType, value: int):
        """发送数据包到指定目标"""
        packet = self.create_packet(target, action, value)
        
        # 根据目标选择地址
        if target == TargetType.BLUE_TEAM:
            self.send_packet(BLUE_TARGET_ADDR, packet)
        elif target == TargetType.RED_TEAM:
            self.send_packet(RED_TARGET_ADDR, packet)
        elif target == TargetType.UNSPECIFIED:
            # 发送给双方
            self.send_packet(BLUE_TARGET_ADDR, packet)
            self.send_packet(RED_TARGET_ADDR, packet)
    
    def create_buttons(self):
        """创建所有按钮"""
        screen_width, screen_height = self.screen.get_size()
        
        # 清除现有按钮
        self.control_buttons.clear()
        self.blue_buttons.clear()
        self.red_buttons.clear()
        
        # 1. 控制按钮（开始、暂停等）
        control_y = 160
        control_width = 180
        control_height = 50
        control_spacing = 15
        
        control_labels = ["开始比赛", "三分钟准备", "暂停比赛", "结束比赛"]
        control_colors = [GREEN, YELLOW, ORANGE, RED]
        control_hover_colors = [LIGHT_GREEN, (255, 255, 150), (255, 200, 100), LIGHT_RED]
        
        total_control_width = len(control_labels) * control_width + (len(control_labels) - 1) * control_spacing
        start_x = (screen_width - total_control_width) // 2
        
        for i, (label, color, hover_color) in enumerate(zip(control_labels, control_colors, control_hover_colors)):
            x = start_x + i * (control_width + control_spacing)
            button = Button(x, control_y, control_width, control_height, label, 
                           color, hover_color, enabled=True, font_size=22)
            self.control_buttons.append(button)
        
        # 2. 蓝方按钮（左侧）
        blue_area_width = screen_width // 2
        blue_center_x = blue_area_width // 2
        
        blue_button_labels = [
            "去除上一步操作", "黑球得分", "绿球得分", "红球得分",
            "蓝球得分", "成功扫描\n二维码", "成功上台阶", "攻城得分"
        ]
        
        blue_button_colors = [
            GRAY, BLACK, DARK_GREEN, RED,
            BLUE, PURPLE, YELLOW, DARK_BLUE
        ]
        
        blue_hover_colors = [
            (220, 220, 220), (50, 50, 50), (0, 150, 0), (255, 100, 100),
            LIGHT_BLUE, (180, 0, 180), (255, 255, 150), (0, 0, 200)
        ]
        
        button_width = 160
        button_height = 70
        button_spacing = 15
        
        blue_start_y = 260
        for i, (label, color, hover_color) in enumerate(zip(blue_button_labels, blue_button_colors, blue_hover_colors)):
            row = i // 2
            col = i % 2
            x = blue_center_x - button_width - button_spacing//2 + col * (button_width + button_spacing)
            y = blue_start_y + row * (button_height + button_spacing)
            
            enabled = True
            button = Button(x, y, button_width, button_height, label, 
                           color, hover_color, enabled=enabled, font_size=20)
            self.blue_buttons.append(button)
        
        # 3. 红方按钮（右侧）
        red_area_start = screen_width // 2
        red_center_x = red_area_start + blue_area_width // 2
        
        red_button_labels = [
            "去除上一步操作", "黑球得分", "绿球得分", "红球得分",
            "蓝球得分", "成功扫描\n二维码", "成功上台阶", "攻城得分"
        ]
        
        red_button_colors = [
            GRAY, BLACK, DARK_GREEN, RED,
            BLUE, PURPLE, YELLOW, DARK_RED
        ]
        
        red_hover_colors = [
            (220, 220, 220), (50, 50, 50), (0, 150, 0), (255, 100, 100),
            LIGHT_BLUE, (180, 0, 180), (255, 255, 150), (200, 0, 0)
        ]
        
        for i, (label, color, hover_color) in enumerate(zip(red_button_labels, red_button_colors, red_hover_colors)):
            row = i // 2
            col = i % 2
            x = red_center_x - button_width - button_spacing//2 + col * (button_width + button_spacing)
            y = blue_start_y + row * (button_height + button_spacing)
            
            enabled = True
            button = Button(x, y, button_width, button_height, label, 
                           color, hover_color, enabled=enabled, font_size=20)
            self.red_buttons.append(button)
    
    def handle_button_click(self, button_index: int, team: TargetType):
        """处理按钮点击事件"""
        if team == TargetType.BLUE_TEAM:
            buttons = self.blue_buttons
            last_action = self.last_blue_action
            qr_scanned = self.blue_qr_scanned
            stair_climbed = self.blue_stair_climbed
        else:
            buttons = self.red_buttons
            last_action = self.last_red_action
            qr_scanned = self.red_qr_scanned
            stair_climbed = self.red_stair_climbed
        
        button = buttons[button_index]
        
        # 根据按钮索引执行不同操作
        if button_index == 0:  # 去除上一步操作
            if last_action:
                # 发送撤销指令
                self.send_to_target(team, ActionType.UNDO, 0)
                print(f"{'蓝方' if team == TargetType.BLUE_TEAM else '红方'} 撤销上一步操作")
                
                # 如果是QR码或上台阶按钮，恢复其可用状态
                if last_action[0] == 5:  # QR码按钮
                    if team == TargetType.BLUE_TEAM:
                        self.blue_qr_scanned = False
                    else:
                        self.red_qr_scanned = False
                    buttons[5].set_enabled(True)
                elif last_action[0] == 6:  # 上台阶按钮
                    if team == TargetType.BLUE_TEAM:
                        self.blue_stair_climbed = False
                    else:
                        self.red_stair_climbed = False
                    buttons[6].set_enabled(True)
                
                # 清空上一步记录
                if team == TargetType.BLUE_TEAM:
                    self.last_blue_action = None
                else:
                    self.last_red_action = None
                
        elif button_index == 5:  # 成功扫描二维码
            if team == TargetType.BLUE_TEAM and not self.blue_qr_scanned:
                self.send_to_target(team, ActionType.TECH_SCORE, 00)  # 扫描QR码不计分
                self.blue_qr_scanned = True
                button.set_enabled(False)
                self.last_blue_action = (button_index, 
                                        self.create_packet(team, ActionType.TECH_SCORE, 00))
            elif team == TargetType.RED_TEAM and not self.red_qr_scanned:
                self.send_to_target(team, ActionType.TECH_SCORE, 00)
                self.red_qr_scanned = True
                button.set_enabled(False)
                self.last_red_action = (button_index, 
                                       self.create_packet(team, ActionType.TECH_SCORE, 50))
                
        elif button_index == 6:  # 成功上台阶
            if team == TargetType.BLUE_TEAM and not self.blue_stair_climbed:
                self.send_to_target(team, ActionType.TECH_SCORE, 100)  # 假设上台阶得100分
                self.blue_stair_climbed = True
                button.set_enabled(False)
                self.last_blue_action = (button_index, 
                                        self.create_packet(team, ActionType.TECH_SCORE, 100))
            elif team == TargetType.RED_TEAM and not self.red_stair_climbed:
                self.send_to_target(team, ActionType.TECH_SCORE, 100)
                self.red_stair_climbed = True
                button.set_enabled(False)
                self.last_red_action = (button_index, 
                                       self.create_packet(team, ActionType.TECH_SCORE, 100))
                
        else:
            # 其他得分按钮
            scores = {
                1: (ActionType.BASIC_SCORE, 2),   # 黑球
                2: (ActionType.BASIC_SCORE, 6),   # 绿球
                3: (ActionType.BASIC_SCORE, 8),   # 红球
                4: (ActionType.BASIC_SCORE, 10),   # 蓝球
                7: (ActionType.ATTACK_SCORE, 10),  # 攻城得分
            }
            
            if button_index in scores:
                action_type, score = scores[button_index]
                self.send_to_target(team, action_type, score)
                
                # 记录上一步操作
                packet = self.create_packet(team, action_type, score)
                if team == TargetType.BLUE_TEAM:
                    self.last_blue_action = (button_index, packet)
                else:
                    self.last_red_action = (button_index, packet)
    
    def handle_control_button(self, button_index: int):
        """处理控制按钮点击"""
        if button_index == 0:  # 开始比赛
            if not self.match_started:
                self.match_started = True
                self.match_paused = False
                self.match_ended = False
                self.last_time_update = time.time()
                print("比赛开始！")
                # 发送开始指令给双方
                self.send_to_target(TargetType.UNSPECIFIED, ActionType.DO_NOTHING, 0)
                
        elif button_index == 1:  # 三分钟准备
            if not self.match_started:
                self.remaining_time = 3 * 60  # 设置为3分钟
                print("三分钟准备开始")
                # 发送准备指令
                self.send_to_target(TargetType.UNSPECIFIED, ActionType.DO_NOTHING, 300)  # 300秒
                
        elif button_index == 2:  # 暂停比赛
            if self.match_started and not self.match_ended:
                self.match_paused = not self.match_paused
                if self.match_paused:
                    print("比赛暂停")
                    # 发送暂停指令
                    self.send_to_target(TargetType.UNSPECIFIED, ActionType.DO_NOTHING, 1)
                else:
                    self.last_time_update = time.time()
                    print("比赛继续")
                    # 发送继续指令
                    self.send_to_target(TargetType.UNSPECIFIED, ActionType.DO_NOTHING, 0)
                    
        elif button_index == 3:  # 结束比赛
            self.match_started = False
            self.match_ended = True
            print("比赛结束")
            # 发送复位指令给双方
            self.send_to_target(TargetType.BLUE_TEAM, ActionType.RESET, 0)
            self.send_to_target(TargetType.RED_TEAM, ActionType.RESET, 0)
            
            # 重置所有特殊状态
            self.blue_qr_scanned = False
            self.blue_stair_climbed = False
            self.red_qr_scanned = False
            self.red_stair_climbed = False
            self.blue_buttons[5].set_enabled(True)
            self.blue_buttons[6].set_enabled(True)
            self.red_buttons[5].set_enabled(True)
            self.red_buttons[6].set_enabled(True)

            # 重置计时器
            self.remaining_time = self.total_time
            self.last_time_update = time.time()
    
    def update_timer(self):
        """更新比赛计时器"""
        if self.match_started and not self.match_paused and not self.match_ended:
            current_time = time.time()
            elapsed = current_time - self.last_time_update
            self.remaining_time -= elapsed
            self.last_time_update = current_time
            
            if self.remaining_time <= 0:
                self.remaining_time = 0
                self.match_ended = True
                print("比赛时间到！")
                # 发送比赛结束指令
                self.send_to_target(TargetType.UNSPECIFIED, ActionType.DO_NOTHING, 0)
    
    def format_time(self, seconds: int) -> str:
        """格式化时间为 MM:SS """
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"
    
    def draw_background(self):
        """绘制背景"""
        screen_width, screen_height = self.screen.get_size()
        
        # 绘制蓝色区域（左侧）
        blue_rect = pygame.Rect(0, 0, screen_width // 2, screen_height)
        pygame.draw.rect(self.screen, (30, 144, 255, 100), blue_rect)
        
        # 绘制红色区域（右侧）
        red_rect = pygame.Rect(screen_width // 2, 0, screen_width // 2, screen_height)
        pygame.draw.rect(self.screen, (220, 20, 60, 100), red_rect)
        
        # 绘制中间分隔线
        pygame.draw.line(self.screen, BLACK, (screen_width // 2, 0), (screen_width // 2, screen_height), 4)
        
        # 绘制标题
        title = "比赛得分控制系统 - 发送端"
        title_surface = self.title_font.render(title, True, BLACK)
        title_rect = title_surface.get_rect(center=(screen_width // 2, 50))
        self.screen.blit(title_surface, title_rect)
        
        # 绘制队伍标签
        blue_label = self.button_font.render("蓝方", True, DARK_BLUE)
        blue_rect = blue_label.get_rect(center=(screen_width // 4, 180))
        self.screen.blit(blue_label, blue_rect)
        
        red_label = self.button_font.render("红方", True, DARK_RED)
        red_rect = red_label.get_rect(center=(screen_width * 3 // 4, 180))
        self.screen.blit(red_label, red_rect)
    
    def draw_timer(self):
        """绘制计时器"""
        screen_width, _ = self.screen.get_size()
        
        # 绘制时间背景框
        time_rect = pygame.Rect(screen_width // 2 - 120, 80, 240, 60)
        pygame.draw.rect(self.screen, WHITE, time_rect, border_radius=10)
        pygame.draw.rect(self.screen, BLACK, time_rect, 3, border_radius=10)
        
        # 绘制时间文字
        time_text = self.format_time(self.remaining_time)
        time_surface = self.timer_font.render(time_text, True, BLACK)
        time_rect_text = time_surface.get_rect(center=(screen_width // 2, 110))
        self.screen.blit(time_surface, time_rect_text)
        
        # 绘制状态指示
        status = ""
        status_color = BLACK
        if self.match_ended:
            status = "比赛结束"
            status_color = RED
        elif self.match_paused:
            status = "比赛暂停"
            status_color = ORANGE
        elif self.match_started:
            status = "比赛中"
            status_color = GREEN
        else:
            status = "等待开始"
            status_color = GRAY
        
        status_surface = self.button_font.render(status, True, status_color)
        status_rect = status_surface.get_rect(center=(screen_width // 2, 140))
        self.screen.blit(status_surface, status_rect)
    
    def heartbeat_sender(self):
        """心跳发送线程，20Hz发送心跳数据包"""
        heartbeat_packet = self.create_packet(TargetType.UNSPECIFIED, ActionType.RESET, 0xFFFF)
        
        while self.heartbeat_running:
            try:
                current_time = time.time()
                
                # 如果1秒内没有按钮操作，发送心跳包
                if current_time - self.last_action_time >= 1.0:
                    # 发送给蓝方
                    self.send_packet(BLUE_TARGET_ADDR, heartbeat_packet)
                    # 发送给红方
                    self.send_packet(RED_TARGET_ADDR, heartbeat_packet)
                
                # 20Hz频率
                time.sleep(1.0 / 20)
                
            except Exception as e:
                print(f"心跳发送错误: {e}")
                time.sleep(0.1)
    
    def draw_packet_info(self):
        """绘制数据包信息"""
        screen_width, screen_height = self.screen.get_size()
        
        # 绘制信息框
        info_rect = pygame.Rect(20, screen_height - 100, screen_width - 40, 80)
        pygame.draw.rect(self.screen, (240, 240, 240), info_rect, border_radius=10)
        pygame.draw.rect(self.screen, BLACK, info_rect, 2, border_radius=10)
        
        # 绘制信息文字
        info_lines = [
            "数据包格式: 0xBF [目标][操作][值高字节][值低字节] 0xBF",
            f"蓝方目标: {BLUE_TARGET_ADDR}:{BROADCAST_PORT}",
            f"红方目标: {RED_TARGET_ADDR}:{BROADCAST_PORT}"
        ]
        
        for i, line in enumerate(info_lines):
            text_surface = self.get_chinese_font(18).render(line, True, BLACK)
            text_rect = text_surface.get_rect(topleft=(info_rect.left + 10, info_rect.top + 10 + i * 25))
            self.screen.blit(text_surface, text_rect)
    
    def run(self):
        """主循环"""
        clock = pygame.time.Clock()
        
        while self.running:
            mouse_pos = pygame.mouse.get_pos()
            
            # 更新按钮悬停状态
            for button in self.control_buttons:
                button.update_hover(mouse_pos)
            for button in self.blue_buttons:
                button.update_hover(mouse_pos)
            for button in self.red_buttons:
                button.update_hover(mouse_pos)
            
            # 处理事件
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    self.heartbeat_running = False
                    
                elif event.type == pygame.VIDEORESIZE:
                    # 窗口大小改变时重新创建按钮
                    self.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                    self.create_buttons()
                    
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # 左键点击
                        # 检查控制按钮
                        for i, button in enumerate(self.control_buttons):
                            if button.is_clicked(event.pos):
                                if button.set_clicked(True):
                                    self.handle_control_button(i)
                        
                        # 检查蓝方按钮
                        for i, button in enumerate(self.blue_buttons):
                            if button.is_clicked(event.pos):
                                if button.set_clicked(True):
                                    self.handle_button_click(i, TargetType.BLUE_TEAM)
                        
                        # 检查红方按钮
                        for i, button in enumerate(self.red_buttons):
                            if button.is_clicked(event.pos):
                                if button.set_clicked(True):
                                    self.handle_button_click(i, TargetType.RED_TEAM)
                
                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1:
                        # 重置所有按钮的点击状态
                        for button in self.control_buttons:
                            button.set_clicked(False)
                        for button in self.blue_buttons:
                            button.set_clicked(False)
                        for button in self.red_buttons:
                            button.set_clicked(False)
            
            # 更新时间
            self.update_timer()
            
            # 绘制界面
            self.screen.fill(WHITE)
            self.draw_background()
            self.draw_timer()
            
            # 绘制按钮
            for button in self.control_buttons:
                button.draw(self.screen)
            for button in self.blue_buttons:
                button.draw(self.screen)
            for button in self.red_buttons:
                button.draw(self.screen)
            
            # 绘制数据包信息
            self.draw_packet_info()
            
            pygame.display.flip()
            clock.tick(60)  # 60 FPS
        
        # 清理资源
        self.socket.close()
        pygame.quit()
        print("程序退出")

if __name__ == "__main__":
    app = ScoreControlApp()
    app.run()