# -*- coding: utf-8 -*-
"""
小蓝 Q 版 3D 桌宠 —— Windows 桌面 AI 对话 + 实用工具宠物（功能增强版）
=====================================================================
形象：3D 游戏低模风，9 姿态透明图（emotions/），随状态切换。
状态：idle趴着 / stand站立 / waving挥手 / jump跳跃 / failed沮丧 /
      waiting期待 / thinking思考 / running_left左走 / running_right右走 /
      sleep休眠 / alarm告警
实用功能：番茄钟 / 久坐提醒 / 待办清单 / 系统监控(CPU·内存·时间) /
          快捷启动 / 空闲休眠 / 专注陪伴安静 / 休息自动吐泡 / 设置面板
行为智能：基于 GetLastInputInfo 检测全局无操作时长 → 久坐提醒、自动休眠、
          打字活跃时降低动画幅度。
稳定：网络/语音在子线程经信号槽回主线程；可选依赖缺失自动降级。
运行： python main.py
"""
import os
import sys
import json
import math
import ctypes
import random
import threading
import time
import subprocess
from datetime import datetime

import requests
from PyQt5.QtCore import Qt, QTimer, QPoint, QObject, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QMenu, QDialog, QLineEdit,
    QVBoxLayout, QFormLayout, QCheckBox, QComboBox, QDialogButtonBox,
    QTextEdit, QInputDialog, QListWidget, QListWidgetItem,
)
from PyQt5.QtGui import QPixmap, QColor, QPainter, QBitmap, QImage, QFont

# ============================ 可配置参数区 ============================
PET_SIZE        = 340          # 桌宠窗口尺寸 px（放大两倍）
FRAME_RATE      = 100          # 动画帧间隔 ms
CLICK_RADIUS    = 8            # 点击判定移动阈值 px
MAX_HISTORY     = 10           # 对话记忆轮数
API_TIMEOUT     = 30           # API 请求超时秒
BUBBLE_MAX_WIDTH = 160         # 气泡最大宽度（自适应文字，长文换行）
BUBBLE_BG       = "rgba(74,144,226,235)"  # 蓝色气泡（alpha=235）
BUBBLE_FG       = "#ffffff"        # 气泡文字：白色
HOTKEY          = "Ctrl+Alt+V" # 全局录音快捷键
DEFAULT_MODEL   = "deepseek-chat"
DEFAULT_BASE    = "https://api.deepseek.com"
DEFAULT_VOICE   = "zh-CN-XiaoxiaoNeural"
DEFAULT_PROMPT  = "你是一个可爱的Q版桌宠，名字叫小蓝，性格活泼、乐于助人，喜欢聊AI和科技话题。回答简短可爱，中文回复。"

# ---- 8 状态动画（精灵图行映射）----
STATE_TO_ROW = {
    "idle": 0, "running_left": 1, "running_right": 2,
    "waving": 3, "jump": 4, "failed": 5, "waiting": 6, "thinking": 7,
}
# 无精灵图时的身体动画：{状态: (浮动px, 缩放, 频率Hz)}
AVATAR_MOTION = {
    "idle":          (3,  0.02, 1.0),
    "stand":         (2,  0.02, 0.8),
    "waving":        (10, 0.06, 2.0),
    "jump":          (20, 0.10, 3.5),
    "failed":        (5,  0.03, 0.6),
    "waiting":       (6,  0.04, 0.9),
    "thinking":      (7,  0.06, 0.8),
    "running_left":  (0,  0.00, 0.0),
    "running_right": (0,  0.00, 0.0),
    "sleep":         (1,  0.00, 0.0),   # 休眠：几乎不动
    "alarm":         (8,  0.05, 4.0),   # 告警：小幅快抖
}
WALK_STEP       = 6            # 走动每帧横向步长 px
WALK_DISTANCE   = 120          # 一次走动距离 px
WALK_MIN_DELAY  = 9            # 空闲后随机走动：最小延迟 秒
WALK_MAX_DELAY  = 18           # 空闲后随机走动：最大延迟 秒

IDLE_BUBBLE_MIN_DELAY = 60     # 休息时自动吐气泡：最小间隔 秒
IDLE_BUBBLE_MAX_DELAY = 120    # 休息时自动吐气泡：最大间隔 秒
IDLE_BUBBLE_SHOW     = 4000    # 气泡显示时长 ms
IDLE_BUBBLE_TEXTS = [
    "在摸鱼吗？一起看星星吧~",
    "今天也要元气满满哦！",
    "小蓝在呢，随时找我聊天~",
    "你知道 AI 也在偷偷卷吗？",
    "要不要我给你讲个冷笑话？",
    "休息一下，眼睛也要放松哦~",
    "按一下我就能跟我说话啦！",
    "听说 GitHub 今天又火了好几个项目？",
]
# ---- 完整桌宠设定：状态气泡文案 ----
DRAG_TEXTS = ["哇！不要拎我！", "带我去哪里呀", "飘起来咯"]
THINKING_TEXTS = ["在思考问题…", "专注模式开启", "加油，继续写代码！"]
WALK_TEXTS = ["去哪里逛逛好呢", "看看你在做什么", "散步中🚶"]
ALARM_TEXTS = ["时间到啦！", "该起身休息一下咯", "任务完成✨"]
CLICK_TEXTS = ["你来啦！", "嘿嘿，好舒服~", "怎么啦？"]
SLEEP_BUBBLE = "💤 睡着了，轻点唤醒我"

# ---- 实用功能参数 ----
TOMATO_DEFAULT_MIN = 25        # 番茄钟默认 25 分钟
SEDENTARY_DEFAULT_MIN = 45     # 久坐提醒默认 45 分钟
SLEEP_DEFAULT_MIN = 5          # 长时间无操作进入休眠（分钟）
FOCUS_ACTIVE_MS = 4000         # 检测到键盘/鼠标活跃后的安静期 ms
SYS_MONITOR_INTERVAL = 3000    # 系统监控刷新 ms
SYS_MONITOR_SHOW = 4000        # 系统信息气泡显示时长 ms
QUICK_LAUNCH_ITEMS = [         # 快捷启动项：{名称, 命令}
    {"name": "打开项目文件夹", "cmd": r"explorer C:\Users\zyx"},
    {"name": "启动 jupyter",  "cmd": r"cmd /c start jupyter notebook"},
]

AVATAR_FILE = "avatar.png"
EMOTION_DIR = "emotions"              # 3D 神态姿态图目录（透明 PNG）
EMOTION_MAP = {                       # 状态 → 姿态图文件
    "idle": "emo_idle.png",
    "stand": "emo_stand.png",
    "waving": "emo_waving.png",
    "jump": "emo_jump.png",
    "failed": "emo_failed.png",
    "waiting": "emo_waiting.png",
    "thinking": "emo_thinking.png",
    "running_left": "emo_running_left.png",
    "running_right": "emo_running_right.png",
}
# 休眠/告警状态复用已有姿态图
EMOTION_ALIAS = {"sleep": "emo_idle.png", "alarm": "emo_failed.png"}

PET_JSON    = "pet.json"
SHEET_FILE  = "spritesheet.webp"
CONFIG_FILE = "config.json"
TODO_FILE   = "todos.json"
WHISPER_MODEL_ROOT = os.path.join(os.path.expanduser("~"), "whisper-models")
# =====================================================================

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AVATAR_PATH = os.path.join(BASE_DIR, AVATAR_FILE)
PET_JSON_PATH = os.path.join(BASE_DIR, PET_JSON)
SHEET_PATH = os.path.join(BASE_DIR, SHEET_FILE)
CONFIG_PATH = os.path.join(BASE_DIR, CONFIG_FILE)
TODO_PATH = os.path.join(BASE_DIR, TODO_FILE)

# ---- 可选依赖加载 ----
try:
    import pygame
    PYGAME_OK = True
except Exception:
    PYGAME_OK = False
try:
    import edge_tts
    EDGE_OK = True
except Exception:
    EDGE_OK = False
try:
    import pyttsx3
    PYTSX3_OK = True
except Exception:
    PYTSX3_OK = False
try:
    import speech_recognition as sr
    SR_OK = True
except Exception:
    SR_OK = False
try:
    import sounddevice as sd
    import numpy as np
    SD_OK = True
except Exception:
    SD_OK = False
try:
    import PIL.Image
    PIL_OK = True
except Exception:
    PIL_OK = False
try:
    from faster_whisper import WhisperModel
    FW_OK = True
except Exception:
    FW_OK = False


# ============================ Windows 系统工具 ============================
class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_ulong)]


def system_idle_ms():
    """返回系统最近一次输入（键盘/鼠标）至今的毫秒数（全局，GetLastInputInfo）。"""
    try:
        lii = _LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            return int(ctypes.windll.kernel32.GetTickCount() - lii.dwTime)
    except Exception:
        pass
    return 0


def cpu_percent():
    """两次采样 GetSystemTimes 计算 CPU 使用率。"""
    try:
        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLow", ctypes.c_ulong), ("dwHigh", ctypes.c_ulong)]
        ft_idle1, ft_k1, ft_u1 = FILETIME(), FILETIME(), FILETIME()
        ft_idle2, ft_k2, ft_u2 = FILETIME(), FILETIME(), FILETIME()
        GetSystemTimes = ctypes.windll.kernel32.GetSystemTimes
        GetSystemTimes(ctypes.byref(ft_idle1), ctypes.byref(ft_k1), ctypes.byref(ft_u1))
        time.sleep(0.2)
        GetSystemTimes(ctypes.byref(ft_idle2), ctypes.byref(ft_k2), ctypes.byref(ft_u2))
        def tot(f):
            return (f.dwHigh << 32) | f.dwLow
        idle = tot(ft_idle2) - tot(ft_idle1)
        kern = tot(ft_k2) - tot(ft_k1)
        user = tot(ft_u2) - tot(ft_u1)
        total = kern + user
        if total <= 0:
            return 0.0
        return max(0.0, min(100.0, (total - idle) / total * 100.0))
    except Exception:
        return -1.0


def memory_percent():
    """GlobalMemoryStatusEx 返回内存使用率%。"""
    try:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        ms = MEMORYSTATUSEX()
        ms.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
            return float(ms.dwMemoryLoad)
    except Exception:
        pass
    return -1.0


def now_time_str():
    return datetime.now().strftime("%H:%M:%S")


# ============================ 配置 ============================
def default_config():
    return {
        "api_key": "", "base_url": DEFAULT_BASE, "model": DEFAULT_MODEL,
        "system_prompt": DEFAULT_PROMPT,
        "voice_enabled": True, "tts_voice": DEFAULT_VOICE,
        "speech_rate": "+0%", "speech_volume": 1.0,
        # 实用功能开关与参数
        "tomato_min": TOMATO_DEFAULT_MIN,
        "sedentary_enabled": True, "sedentary_min": SEDENTARY_DEFAULT_MIN,
        "sleep_enabled": True, "sleep_min": SLEEP_DEFAULT_MIN,
        "sys_monitor_enabled": False,
        "idle_bubble_enabled": True,
        "focus_quiet": True,
        "quick_launch": QUICK_LAUNCH_ITEMS,
    }


def load_config():
    cfg = default_config()
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k in cfg:
                if k in data:
                    cfg[k] = data[k]
        except Exception as e:
            print("config load error:", e)
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def ensure_config():
    if not os.path.exists(CONFIG_PATH):
        save_config(default_config())


def load_todos():
    if os.path.exists(TODO_PATH):
        try:
            with open(TODO_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_todos(todos):
    with open(TODO_PATH, "w", encoding="utf-8") as f:
        json.dump(todos, f, ensure_ascii=False, indent=2)


# ============================ DeepSeek 客户端 ============================
class DeepSeekClient:
    def __init__(self, cfg):
        self.cfg = cfg

    def chat(self, messages):
        url = self.cfg["base_url"].rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json",
                   "Authorization": "Bearer " + self.cfg.get("api_key", "")}
        body = {"model": self.cfg.get("model", DEFAULT_MODEL), "messages": messages}
        r = requests.post(url, headers=headers, json=body, timeout=API_TIMEOUT)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()


# ============================ 动画器 ============================
class SpriteAnimator(QObject):
    frame_changed = pyqtSignal(QPixmap)

    def __init__(self):
        super().__init__()
        self.state = "idle"
        self.frames = {}
        self.row_map = dict(STATE_TO_ROW)
        self.state_frames = {}
        self.idx = 0
        self.loop_states = {"idle", "running_left", "running_right",
                            "waiting", "thinking", "stand"}
        self._loaded = False
        self._t = 0.0
        self._load()

    def _load(self):
        if PIL_OK and os.path.exists(PET_JSON_PATH) and os.path.exists(SHEET_PATH):
            try:
                self._load_spritesheet()
                return
            except Exception as e:
                print("spritesheet load failed, fallback avatar:", e)
        self._load_avatar()

    def _load_spritesheet(self):
        import PIL.Image
        with open(PET_JSON_PATH, "r", encoding="utf-8") as f:
            meta = json.load(f)
        sheet = PIL.Image.open(SHEET_PATH).convert("RGBA")
        cols, rows = sheet.size
        rows_info = meta.get("states") or meta.get("animations") or meta
        for state, r in self.row_map.items():
            info = rows_info.get(state, {}) if isinstance(rows_info, dict) else {}
            row = info.get("row", info.get("line", info.get("y", r)))
            nframes = info.get("frames", info.get("frame_count",
                             info.get("count", meta.get("frame_count", 11))))
            try:
                row = int(row)
            except Exception:
                row = r
            try:
                nframes = int(nframes)
            except Exception:
                nframes = 11
            width = max(1, cols // nframes)
            pix = []
            for i in range(nframes):
                img = sheet.crop((i * width, row * width, (i + 1) * width, (row + 1) * width))
                img = img.resize((PET_SIZE, PET_SIZE))
                qimg = QImage(img.tobytes("raw", "RGBA"), PET_SIZE, PET_SIZE,
                              PET_SIZE * 4, QImage.Format_RGBA8888)
                qimg.bits()
                pix.append(QPixmap.fromImage(qimg.copy()))
            self.state_frames[state] = pix
        self._loaded = True
        for s in self.row_map:
            if s not in self.state_frames:
                self.state_frames[s] = self.state_frames.get("idle", [])

    def _load_avatar(self):
        self._loaded = False
        base = QPixmap(AVATAR_PATH)
        if base.isNull():
            base = QPixmap(PET_SIZE, PET_SIZE)
            base.fill(QColor(0, 0, 0, 0))
        self.avatar_base = base.scaled(PET_SIZE, PET_SIZE,
                                       Qt.KeepAspectRatio, Qt.SmoothTransformation)
        # 加载 3D 姿态图（透明 PNG）；缺失时回退 avatar.png
        self.emotions = {}
        emo_dir = os.path.join(BASE_DIR, EMOTION_DIR)
        all_map = dict(EMOTION_MAP)
        all_map.update(EMOTION_ALIAS)
        for state, fname in all_map.items():
            path = os.path.join(emo_dir, fname)
            pm = QPixmap(path)
            if not pm.isNull():
                self.emotions[state] = pm.scaled(
                    PET_SIZE, PET_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if not self.emotions:
            self.emotions["idle"] = self.avatar_base

    @property
    def using_spritesheet(self):
        return self._loaded

    def set_state(self, state):
        if state != self.state:
            self.state = state
            self.idx = 0

    def current_pixmap(self):
        if self._loaded:
            fr = self.state_frames.get(self.state) or self.state_frames.get("idle", [])
            if not fr:
                return QPixmap()
            return fr[min(self.idx, len(fr) - 1)]
        base = self.emotions.get(self.state) or self.emotions.get("idle", self.avatar_base)
        _, scale, freq = AVATAR_MOTION.get(self.state, AVATAR_MOTION["idle"])
        k = 1.0 + scale * math.sin(self._t * 2 * math.pi * freq)
        size = max(1, int(PET_SIZE * k))
        pm = base.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        canvas = QPixmap(PET_SIZE, PET_SIZE)
        canvas.fill(QColor(0, 0, 0, 0))
        from PyQt5.QtGui import QPainter as QP
        p = QP(canvas)
        p.drawPixmap((PET_SIZE - size) // 2, (PET_SIZE - size) // 2, pm)
        p.end()
        return canvas

    def advance(self):
        self._t += 0.05
        if self._loaded:
            fr = self.state_frames.get(self.state)
            if fr:
                self.idx = (self.idx + 1) % len(fr)

    def is_loop(self):
        return self.state in self.loop_states


# ============================ 气泡 ============================
class ChatBubble(QWidget):
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.label = QLabel(self)
        self.label.setWordWrap(True)
        self.label.setStyleSheet("color:%s;background:transparent;" % BUBBLE_FG)
        self.label.setMaximumWidth(BUBBLE_MAX_WIDTH)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.addWidget(self.label)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(BUBBLE_BG))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(self.rect(), 16, 16)
        super().paintEvent(event)

    def show_text(self, text, timeout=2500):
        self.label.setText(text)
        self.label.adjustSize()
        self.adjustSize()
        self.show()
        self.raise_()
        self.timer.start(timeout)

    def position_above(self, geo):
        self.move(geo.center().x() - self.width() // 2,
                  geo.top() - self.height() - 6)

    def mousePressEvent(self, e):
        self.hide()
        super().mousePressEvent(e)


class TimeBubble(QWidget):
    """待机常驻时间气泡：半透明白底、细浅灰字，位于头顶上方。"""
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.label = QLabel(self)
        self.label.setStyleSheet("color:#888888;background:transparent;font-size:15px;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.addWidget(self.label)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(255, 255, 255, 160))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(self.rect(), 12, 12)
        super().paintEvent(event)

    def show_time(self, text, geo):
        self.label.setText(text)
        self.label.adjustSize()
        self.adjustSize()
        self.move(geo.center().x() - self.width() // 2, geo.top() - self.height() - 4)
        self.show()
        self.raise_()


# ============================ 语音引擎 ============================
class VoiceEngine(QObject):
    listened = pyqtSignal(str)
    listen_failed = pyqtSignal(str)
    spoken_done = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._stop_lock = threading.Lock()
        self._current_mp3 = None
        self._pygame_ok = PYGAME_OK
        if self._pygame_ok:
            try:
                os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
                pygame.mixer.init()
            except Exception:
                self._pygame_ok = False
        self._whisper = None
        self._whisper_lock = threading.Lock()

    def listen(self, duration=6):
        threading.Thread(target=self._listen_worker, args=(duration,), daemon=True).start()

    def _listen_worker(self, duration):
        try:
            text = self._recognize(duration)
            if text:
                self.listened.emit(text)
            else:
                self.listen_failed.emit("没听清，再说一次吧")
        except Exception as e:
            print("listen error:", e)
            self.listen_failed.emit("录音识别出错啦")

    def _get_whisper(self):
        with self._whisper_lock:
            if self._whisper is None and FW_OK:
                model_dir = os.environ.get("WHISPER_MODEL_DIR", WHISPER_MODEL_ROOT)
                if os.path.isdir(model_dir):
                    self._whisper = WhisperModel(
                        model_dir, device="cpu", compute_type="int8",
                        local_files_only=True)
                else:
                    print("whisper model dir not found:", model_dir)
        return self._whisper

    def _recognize(self, duration):
        model = self._get_whisper()
        if model is not None and SD_OK:
            fs = 16000
            rec = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype="float32")
            sd.wait()
            audio = np.squeeze(rec).astype(np.float32)
            segments, _info = model.transcribe(audio, language="zh", beam_size=1)
            text = "".join(s.text for s in segments).strip()
            if text:
                return text
            raise RuntimeError("whisper no speech detected")
        if not SR_OK:
            raise RuntimeError("无可用识别后端")
        if SD_OK:
            fs = 16000
            rec = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype="int16")
            sd.wait()
            audio = (rec.astype(np.int16)).flatten().tobytes()
            r = sr.Recognizer()
            ad = sr.AudioData(audio, fs, 2)
            return r.recognize_google(ad, language="zh-CN")
        else:
            r = sr.Recognizer()
            with sr.Microphone() as source:
                r.adjust_for_ambient_noise(source)
                audio = r.listen(source, timeout=4, phrase_time_limit=duration)
            return r.recognize_google(audio, language="zh-CN")

    def speak(self, text, voice=DEFAULT_VOICE, rate="+0%", volume=1.0):
        if not text:
            return
        threading.Thread(target=self._speak_worker,
                         args=(text, voice, rate, volume), daemon=True).start()

    def _speak_worker(self, text, voice, rate, volume):
        if EDGE_OK:
            try:
                self._speak_edge(text, voice, rate, volume)
                return
            except Exception as e:
                print("edge-tts failed, fallback pyttsx3:", e)
        if PYTSX3_OK:
            try:
                self._speak_pyttsx3(text, rate)
                return
            except Exception:
                pass
        self.spoken_done.emit()

    def _speak_edge(self, text, voice, rate, volume):
        import asyncio, tempfile
        mp3 = tempfile.mktemp(suffix=".mp3")
        async def gen():
            com = edge_tts.Communicate(text, voice=voice, rate=rate)
            await com.save(mp3)
        asyncio.run(gen())
        with self._stop_lock:
            self._current_mp3 = mp3
        if self._pygame_ok:
            try:
                pygame.mixer.music.stop()
                pygame.mixer.music.load(mp3)
                pygame.mixer.music.set_volume(max(0.0, min(1.0, float(volume or 1))))
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    time.sleep(0.05)
                pygame.mixer.music.unload()
            except Exception as e:
                print("pygame play failed:", e)
        with self._stop_lock:
            self._current_mp3 = None
        try:
            if os.path.exists(mp3):
                os.remove(mp3)
        except Exception:
            pass
        self.spoken_done.emit()

    def _speak_pyttsx3(self, text, rate):
        eng = pyttsx3.init()
        try:
            eng.say(text)
            eng.runAndWait()
        finally:
            try:
                eng.stop()
            except Exception:
                pass
        self.spoken_done.emit()

    def stop(self):
        with self._stop_lock:
            if self._pygame_ok:
                try:
                    pygame.mixer.music.stop()
                except Exception:
                    pass


# ============================ 设置对话框 ============================
class SettingsDialog(QDialog):
    def __init__(self, cfg):
        super().__init__()
        self.setWindowTitle("小蓝 · 设置")
        self.setMinimumWidth(480)
        self.key = QLineEdit(cfg.get("api_key", ""))
        self.key.setEchoMode(QLineEdit.Password)
        self.url = QLineEdit(cfg.get("base_url", DEFAULT_BASE))
        self.model = QLineEdit(cfg.get("model", DEFAULT_MODEL))
        self.voice_on = QCheckBox("启用语音回复")
        self.voice_on.setChecked(bool(cfg.get("voice_enabled", True)))
        self.voice = QComboBox()
        self.voice.setEditable(True)
        self.voice.addItems(["zh-CN-XiaoxiaoNeural", "zh-CN-XiaoyiNeural",
                             "zh-CN-YunxiNeural", "zh-CN-YunyangNeural"])
        self.voice.setCurrentText(cfg.get("tts_voice", DEFAULT_VOICE))
        self.rate = QLineEdit(cfg.get("speech_rate", "+0%"))
        self.prompt = QTextEdit(cfg.get("system_prompt", DEFAULT_PROMPT))
        self.prompt.setMaximumHeight(80)

        # 实用功能设置
        self.tomato = QLineEdit(str(cfg.get("tomato_min", TOMATO_DEFAULT_MIN)))
        self.sedentary_on = QCheckBox("久坐提醒")
        self.sedentary_on.setChecked(bool(cfg.get("sedentary_enabled", True)))
        self.sedentary_min = QLineEdit(str(cfg.get("sedentary_min", SEDENTARY_DEFAULT_MIN)))
        self.sleep_on = QCheckBox("长时间无操作自动休眠")
        self.sleep_on.setChecked(bool(cfg.get("sleep_enabled", True)))
        self.sleep_min = QLineEdit(str(cfg.get("sleep_min", SLEEP_DEFAULT_MIN)))
        self.sysmon_on = QCheckBox("系统监控（气泡显示 CPU/内存/时间）")
        self.sysmon_on.setChecked(bool(cfg.get("sys_monitor_enabled", False)))
        self.idle_bubble_on = QCheckBox("休息时自动吐气泡")
        self.idle_bubble_on.setChecked(bool(cfg.get("idle_bubble_enabled", True)))
        self.focus_on = QCheckBox("专注陪伴（打字时自动安静）")
        self.focus_on.setChecked(bool(cfg.get("focus_quiet", True)))

        form = QFormLayout()
        form.addRow("API Key", self.key)
        form.addRow("Base URL", self.url)
        form.addRow("模型名", self.model)
        form.addRow("语音回复", self.voice_on)
        form.addRow("语音角色", self.voice)
        form.addRow("语速(如 +20%)", self.rate)
        form.addRow("小蓝性格", self.prompt)
        form.addRow("番茄钟时长(分)", self.tomato)
        form.addRow(self.sedentary_on)
        form.addRow("久坐提醒间隔(分)", self.sedentary_min)
        form.addRow(self.sleep_on)
        form.addRow("休眠等待(分)", self.sleep_min)
        form.addRow(self.sysmon_on)
        form.addRow(self.idle_bubble_on)
        form.addRow(self.focus_on)
        btn = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn.accepted.connect(self.accept)
        btn.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(btn)

    def get_cfg(self):
        def num(s, default):
            try:
                return max(1, int(float(s.strip())))
            except Exception:
                return default
        return {
            "api_key": self.key.text().strip(),
            "base_url": self.url.text().strip() or DEFAULT_BASE,
            "model": self.model.text().strip() or DEFAULT_MODEL,
            "system_prompt": self.prompt.toPlainText().strip() or DEFAULT_PROMPT,
            "voice_enabled": self.voice_on.isChecked(),
            "tts_voice": self.voice.currentText().strip() or DEFAULT_VOICE,
            "speech_rate": self.rate.text().strip() or "+0%",
            "speech_volume": 1.0,
            "tomato_min": num(self.tomato.text(), TOMATO_DEFAULT_MIN),
            "sedentary_enabled": self.sedentary_on.isChecked(),
            "sedentary_min": num(self.sedentary_min.text(), SEDENTARY_DEFAULT_MIN),
            "sleep_enabled": self.sleep_on.isChecked(),
            "sleep_min": num(self.sleep_min.text(), SLEEP_DEFAULT_MIN),
            "sys_monitor_enabled": self.sysmon_on.isChecked(),
            "idle_bubble_enabled": self.idle_bubble_on.isChecked(),
            "focus_quiet": self.focus_on.isChecked(),
            "quick_launch": self.cfg_quick_launch,
        }


# ============================ 主窗口：桌宠 ============================
class DesktopPet(QWidget):
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(PET_SIZE, PET_SIZE)

        ensure_config()
        self.cfg = load_config()
        self.history = [{"role": "system", "content": self.cfg["system_prompt"]}]

        self.animator = SpriteAnimator()
        self.avatar_label = QLabel(self)
        self.avatar_label.setGeometry(0, 0, PET_SIZE, PET_SIZE)

        self.bubble = ChatBubble()
        self.time_bubble = TimeBubble()      # 待机常驻时间气泡
        self._hovering = False
        self._drag_bubble_last = 0.0
        self.voice = VoiceEngine()
        self.voice.listened.connect(self.on_voice_text)
        self.voice.listen_failed.connect(self.on_voice_fail)
        self.voice.spoken_done.connect(self.on_speak_done)
        self.client = DeepSeekClient(self.cfg)

        # 实用功能状态
        self.todos = load_todos()
        self._tomato_remain = 0           # 剩余秒
        self._tomato_total = 0            # 总秒
        self._tomato_running = False
        self._sedentary_alerted = False
        self._last_active_ms = 0          # 最近检测到的活动时间戳
        self._focus_quiet_until = 0.0

        # 状态机
        self.state = "idle"
        self.state_since = 0
        self.busy = False
        self.listening = False
        self._base_pos = QPoint()
        self._walked = 0.0
        self._walk_dir = 0

        # 动画定时器
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(FRAME_RATE)

        # 空闲随机走动
        self.walk_timer = QTimer(self)
        self.walk_timer.timeout.connect(self._start_walk)
        self.walk_timer.setSingleShot(True)
        self._schedule_walk()

        # 休息自动吐泡
        self._idle_bubble_timer = QTimer(self)
        self._idle_bubble_timer.timeout.connect(self._maybe_idle_bubble)
        self._idle_bubble_timer.setSingleShot(True)
        self._schedule_idle_bubble()

        # 实用功能定时器
        self.tomato_timer = QTimer(self)
        self.tomato_timer.timeout.connect(self._tomato_tick)
        self.tomato_timer.setInterval(1000)
        self.sedentary_timer = QTimer(self)
        self.sedentary_timer.timeout.connect(self._check_sedentary)
        self.sedentary_timer.setInterval(30000)
        self.sedentary_timer.start()
        self.sleep_timer = QTimer(self)
        self.sleep_timer.timeout.connect(self._check_sleep)
        self.sleep_timer.setInterval(30000)
        self.sleep_timer.start()
        self.sysmon_timer = QTimer(self)
        self.sysmon_timer.timeout.connect(self._maybe_show_sysmon)
        self.sysmon_timer.setInterval(SYS_MONITOR_INTERVAL)
        if self.cfg.get("sys_monitor_enabled", False):
            self.sysmon_timer.start()

        self._drag_start = None
        self._press_pos = QPoint()
        self._place()
        self._base_pos = self.pos()
        self._setup_menu()
        self._setup_hotkey()
        self._set_state("idle")

    # ---------- 状态机 ----------
    def _set_state(self, state):
        self.state = state
        self.state_since = time.time()
        self.animator.set_state(state)
        if state in ("running_left", "running_right"):
            self._walked = 0.0
            self._walk_dir = -1 if state == "running_left" else 1

    def _tick(self):
        self.animator.advance()
        self.avatar_label.setPixmap(self.animator.current_pixmap())
        self._update_mask()
        self._apply_motion()
        if not self.animator.is_loop():
            d = time.time() - self.state_since
            if self.state == "waving" and d > 1.0:
                self._set_state("idle")
            elif self.state == "jump" and d > 1.3:
                self._set_state("idle")
            elif self.state == "failed" and d > 2.0:
                self._set_state("idle")
            elif self.state == "alarm" and d > 2.0:
                self._set_state("idle")
        # 待机常驻时间气泡
        if (self.state == "idle" and not self.busy
                and not self.listening and self._drag_start is None):
            txt = "正在安静休息哦" if self._hovering else datetime.now().strftime("%H:%M")
            self.time_bubble.show_time(txt, self.frameGeometry())
        else:
            self.time_bubble.hide()

    def _apply_motion(self):
        if self._drag_start is not None:
            return
        amp, _scale, freq = AVATAR_MOTION.get(self.state, AVATAR_MOTION["idle"])
        screen = QApplication.primaryScreen().availableGeometry()
        if self.state in ("running_left", "running_right"):
            self._walked += WALK_STEP
            x = self.x() + self._walk_dir * WALK_STEP
            if (x < screen.left() + 10 or
                    x + self.width() > screen.right() - 10 or
                    self._walked >= WALK_DISTANCE):
                self._set_state("idle")
                self._base_pos = self.pos()
            else:
                self.move(x, self.y())
            return
        if amp and self.state != "sleep":
            off = math.sin(self.animator._t * 2 * math.pi * freq) * amp
            self.move(self._base_pos.x(), self._base_pos.y() + int(off))

    # ---------- 空闲走动 ----------
    def _schedule_walk(self):
        delay = random.randint(WALK_MIN_DELAY, WALK_MAX_DELAY)
        self.walk_timer.start(delay * 1000)

    def _start_walk(self):
        if (self.state == "idle" and not self.busy
                and not self.listening and self._drag_start is None):
            direction = random.choice(("running_left", "running_right"))
            self._set_state(direction)
            self.bubble.show_text(random.choice(WALK_TEXTS), timeout=2000)
            self.bubble.position_above(self.frameGeometry())
        self._schedule_walk()

    # ---------- 休息自动吐泡 ----------
    def _schedule_idle_bubble(self):
        delay = random.randint(IDLE_BUBBLE_MIN_DELAY, IDLE_BUBBLE_MAX_DELAY)
        self._idle_bubble_timer.start(delay * 1000)

    def _maybe_idle_bubble(self):
        if (self.cfg.get("idle_bubble_enabled", True)
                and self.state == "idle" and not self.busy
                and not self.listening and self._drag_start is None):
            self.bubble.show_text(random.choice(IDLE_BUBBLE_TEXTS),
                                  timeout=IDLE_BUBBLE_SHOW)
            self.bubble.position_above(self.frameGeometry())
        self._schedule_idle_bubble()

    # ---------- 实用功能：番茄钟 ----------
    def _tomato_tick(self):
        if not self._tomato_running:
            return
        self._tomato_remain -= 1
        if self._tomato_remain <= 0:
            self._tomato_running = False
            self.tomato_timer.stop()
            self._set_state("alarm")           # 告警状态：抖动
            self.bubble.show_text("⏰ " + random.choice(ALARM_TEXTS))
            self.bubble.position_above(self.frameGeometry())
            if self.cfg.get("voice_enabled", True):
                self.voice.speak("番茄时间到啦，休息一下吧")
        else:
            mm, ss = divmod(self._tomato_remain, 60)
            self.bubble.show_text("⏳ 番茄钟 %02d:%02d" % (mm, ss), timeout=1000)
            self.bubble.position_above(self.frameGeometry())

    def start_tomato(self, minutes=None):
        if self._tomato_running:
            self._tomato_running = False
            self.tomato_timer.stop()
            self.bubble.show_text("番茄钟已停止")
            self.bubble.position_above(self.frameGeometry())
            return
        if minutes is None:
            minutes = self.cfg.get("tomato_min", TOMATO_DEFAULT_MIN)
        self._tomato_total = self._tomato_remain = max(1, int(minutes)) * 60
        self._tomato_running = True
        self._set_state("thinking")
        self.tomato_timer.start()
        self.bubble.show_text("🍅 番茄钟开始 %d 分钟" % int(minutes))
        self.bubble.position_above(self.frameGeometry())

    # ---------- 实用功能：久坐提醒 / 休眠 / 专注陪伴 ----------
    def _system_idle_ms(self):
        return system_idle_ms()

    def _check_sedentary(self):
        if not self.cfg.get("sedentary_enabled", True):
            self._sedentary_alerted = False
            return
        idle = self._system_idle_ms()
        limit = int(self.cfg.get("sedentary_min", SEDENTARY_DEFAULT_MIN)) * 60000
        if idle >= limit:
            if not self._sedentary_alerted:
                self._sedentary_alerted = True
                self._set_state("alarm")
                self.bubble.show_text("🪑 " + random.choice(ALARM_TEXTS))
                self.bubble.position_above(self.frameGeometry())
                if self.cfg.get("voice_enabled", True):
                    self.voice.speak("坐很久啦，起来活动一下吧")
        else:
            self._sedentary_alerted = False

    def _check_sleep(self):
        if not self.cfg.get("sleep_enabled", True):
            return
        if self.busy or self.listening:
            return
        idle = self._system_idle_ms()
        limit = int(self.cfg.get("sleep_min", SLEEP_DEFAULT_MIN)) * 60000
        if idle >= limit and self.state not in ("sleep", "alarm"):
            self._set_state("sleep")           # 休眠：趴着不动
            self.bubble.show_text(SLEEP_BUBBLE, timeout=3000)
            self.bubble.position_above(self.frameGeometry())
        elif idle < 5000 and self.state == "sleep":
            self._set_state("idle")            # 唤醒

    def _check_focus(self):
        if not self.cfg.get("focus_quiet", True):
            return
        idle = self._system_idle_ms()
        if idle < FOCUS_ACTIVE_MS:
            self._last_active_ms = int(time.time() * 1000)
            # 用户活跃：若在走动则停下，进入安静站立
            if self.state in ("running_left", "running_right"):
                self._set_state("stand")
        else:
            if self.state == "stand" and int(time.time() * 1000) - self._last_active_ms > 60000:
                self._set_state("idle")

    # ---------- 实用功能：待办 ----------
    def _show_todos(self):
        if not self.todos:
            self.bubble.show_text("📋 暂无待办")
            self.bubble.position_above(self.frameGeometry())
            return
        lines = "\n".join("• " + t for t in self.todos[:8])
        self.bubble.show_text("📋 待办：\n" + lines, timeout=8000)
        self.bubble.position_above(self.frameGeometry())

    def _add_todo(self):
        text, ok = QInputDialog.getText(self, "添加待办", "输入待办事项：")
        if ok and text.strip():
            self.todos.append(text.strip())
            save_todos(self.todos)
            self.bubble.show_text("已添加 ✅ %s" % text.strip()[:20])
            self.bubble.position_above(self.frameGeometry())

    def _remove_todo(self):
        if not self.todos:
            self._show_todos()
            return
        item, ok = QInputDialog.getItem(self, "删除待办", "选择要删除的待办：",
                                        self.todos, 0, False)
        if ok and item:
            self.todos.remove(item)
            save_todos(self.todos)
            self.bubble.show_text("已删除待办")
            self.bubble.position_above(self.frameGeometry())

    # ---------- 实用功能：系统监控 ----------
    def _maybe_show_sysmon(self):
        if not self.cfg.get("sys_monitor_enabled", False):
            return
        if self.busy or self.listening or self._drag_start is not None:
            return
        cpu = cpu_percent()
        mem = memory_percent()
        cpu_s = ("%.0f%%" % cpu) if cpu >= 0 else "--"
        mem_s = ("%.0f%%" % mem) if mem >= 0 else "--"
        text = "📊 系统信息\n时间 %s\nCPU %s  内存 %s" % (now_time_str(), cpu_s, mem_s)
        self.bubble.show_text(text, timeout=SYS_MONITOR_SHOW)
        self.bubble.position_above(self.frameGeometry())

    # ---------- 快捷启动 ----------
    def _quick_launch(self, name=None):
        items = self.cfg.get("quick_launch", QUICK_LAUNCH_ITEMS)
        if not items:
            self.bubble.show_text("未配置快捷启动项")
            self.bubble.position_above(self.frameGeometry())
            return
        if name is None:
            names = [it["name"] for it in items]
            choice, ok = QInputDialog.getItem(self, "快捷启动", "选择要启动的项：",
                                              names, 0, False)
            if not ok:
                return
            for it in items:
                if it["name"] == choice:
                    name = it["name"]
                    cmd = it["cmd"]
                    break
        else:
            for it in items:
                if it["name"] == name:
                    cmd = it["cmd"]
                    break
            else:
                return
        try:
            subprocess.Popen(cmd, shell=True)
            self._set_state("waving")
            self.bubble.show_text("🚀 已启动：%s" % name)
            self.bubble.position_above(self.frameGeometry())
        except Exception as e:
            self.bubble.show_text("启动失败：%s" % e)
            self.bubble.position_above(self.frameGeometry())

    # ---------- 遮罩 ----------
    def _update_mask(self):
        pm = self.avatar_label.pixmap()
        if pm is None or pm.isNull():
            return
        img = pm.toImage().convertToFormat(QImage.Format_ARGB32)
        mask = img.createMaskFromColor(QColor(0, 0, 0, 0).rgba(), Qt.MaskInColor)
        self.setMask(QBitmap.fromImage(mask))

    # ---------- 定位 ----------
    def _place(self):
        s = QApplication.primaryScreen().availableGeometry()
        self.move(s.right() - PET_SIZE - 30, s.bottom() - PET_SIZE - 80)

    # ---------- 鼠标：悬停 / 拖动 / 点击 ----------
    def enterEvent(self, e):
        self._hovering = True
        if self.state == "sleep":
            self._set_state("idle")     # 鼠标移到：打断休眠
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hovering = False
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_start = e.globalPos() - self.frameGeometry().topLeft()
            self._press_pos = e.globalPos()
            if self.state == "sleep":
                self._set_state("idle")

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton and self._drag_start is not None:
            self.move(e.globalPos() - self._drag_start)
            now = time.time()
            if now - self._drag_bubble_last > 2.5:
                self._drag_bubble_last = now
                self.bubble.show_text(random.choice(DRAG_TEXTS), timeout=1500)
                self.bubble.position_above(self.frameGeometry())

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            moved = (e.globalPos() - self._press_pos).manhattanLength()
            self._drag_start = None
            self._base_pos = self.pos()
            if moved < CLICK_RADIUS:
                self._on_click()

    def _on_click(self):
        if self.state == "sleep":
            self._set_state("idle")
            self.bubble.show_text("唔…醒啦", timeout=1500)
            self.bubble.position_above(self.frameGeometry())
            return
        self._set_state("waving")
        self.bubble.show_text(random.choice(CLICK_TEXTS), timeout=2000)
        self.bubble.position_above(self.frameGeometry())
        if self.busy:
            self.bubble.show_text("正在思考呢，稍等一下下~")
            self.bubble.position_above(self.frameGeometry())
            return
        if self.cfg.get("voice_enabled", True) and (FW_OK or SR_OK):
            self.start_listen()
        else:
            self._prompt_text_input()

    # ---------- 文字输入 ----------
    def _prompt_text_input(self):
        import PyQt5.QtWidgets as QW
        text, ok = QW.QInputDialog.getText(self, "和小蓝聊天",
                                           "说点什么…（回车发送）")
        if ok and text.strip():
            self.send_user(text.strip())

    # ---------- 语音 ----------
    def start_listen(self):
        if self.listening:
            return
        self.listening = True
        self._set_state("waiting")
        self.bubble.show_text("我在听…（说几句话）", timeout=8000)
        self.bubble.position_above(self.frameGeometry())
        self.voice.listen()

    def on_voice_text(self, text):
        self.listening = False
        self.bubble.show_text(text, timeout=4000)
        self.bubble.position_above(self.frameGeometry())
        self.send_user(text)

    def on_voice_fail(self, msg):
        self.listening = False
        self._set_state("failed")
        self.bubble.show_text(msg)
        self.bubble.position_above(self.frameGeometry())

    # ---------- 对话 ----------
    def send_user(self, text):
        if self.busy:
            return
        if not self.cfg.get("api_key"):
            self._set_state("failed")
            self.bubble.show_text("还没配置 API Key 哦~\n右键我 → 设置")
            self.bubble.position_above(self.frameGeometry())
            return
        self.busy = True
        self.history.append({"role": "user", "content": text})
        self._trim()
        self._set_state("thinking")
        self.bubble.show_text(random.choice(THINKING_TEXTS), timeout=0)
        self.bubble.position_above(self.frameGeometry())
        msgs = list(self.history)
        threading.Thread(target=self._api_worker, args=(msgs,), daemon=True).start()

    def _api_worker(self, msgs):
        try:
            reply = self.client.chat(msgs)
        except Exception as e:
            print("api error:", e)
            self._api_fail()
            return
        self.history.append({"role": "assistant", "content": reply})
        self._trim()
        self._api_done(reply)

    def _api_done(self, reply):
        QTimer.singleShot(0, lambda: self._show_reply(reply))

    def _show_reply(self, reply):
        self.busy = False
        self._set_state("jump")
        self.bubble.show_text(reply, timeout=8000)
        self.bubble.position_above(self.frameGeometry())
        if self.cfg.get("voice_enabled", True):
            self.voice.speak(reply, self.cfg.get("tts_voice", DEFAULT_VOICE),
                             self.cfg.get("speech_rate", "+0%"), 1.0)

    def _api_fail(self):
        QTimer.singleShot(0, self._show_api_fail)

    def _show_api_fail(self):
        self.busy = False
        self._set_state("failed")
        self.bubble.show_text("网络出错啦，请检查 API 设置")
        self.bubble.position_above(self.frameGeometry())
        if self.cfg.get("voice_enabled", True):
            self.voice.speak("网络出错了，请检查 API 设置")

    def on_speak_done(self):
        if not self.busy and self.state in ("jump", "waving"):
            self._set_state("idle")

    def _trim(self):
        if len(self.history) > MAX_HISTORY + 1:
            self.history = [self.history[0]] + self.history[-MAX_HISTORY:]

    # ---------- 菜单 ----------
    def _setup_menu(self):
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)

    def _show_menu(self, pos):
        m = QMenu(self)
        m.addAction("🎤 语音对话", self.start_listen)
        m.addAction("💬 文字对话", self._prompt_text_input)
        m.addSeparator()
        m.addAction("🍅 番茄钟", lambda: self.start_tomato())
        m.addAction("📋 待办清单", self._show_todos)
        m.addAction("➕ 添加待办", self._add_todo)
        m.addAction("➖ 删除待办", self._remove_todo)
        m.addAction("🚀 快捷启动", lambda: self._quick_launch())
        m.addAction("📊 系统信息", lambda: self._maybe_show_sysmon())
        m.addAction("🔥 AI 热榜", self._open_hotlist)
        m.addSeparator()
        m.addAction("🔄 走两步", lambda: self._set_state(
            random.choice(("running_left", "running_right"))))
        m.addAction("⚙ 设置", self._open_settings)
        m.addAction("🧹 清除对话历史", self._clear_history)
        m.addSeparator()
        m.addAction("🚪 退出程序", self.close)
        m.exec_(self.mapToGlobal(pos))

    def _open_hotlist(self):
        """启动 AI 热榜桌面组件（GitHub / HN / HF 论文多源）"""
        candidates = [
            os.path.join(BASE_DIR, "GitHubAIHotlist.exe"),
            r"C:\Users\zyx\GitHubAIHotlist\GitHubAIHotlist.exe",
        ]
        exe = next((p for p in candidates if os.path.exists(p)), None)
        if exe:
            try:
                subprocess.Popen([exe], cwd=os.path.dirname(exe))
                self._set_state("waving")
                self.bubble.show_text("热榜已打开~ GitHub / HN / HF 论文", timeout=2500)
                self.bubble.position_above(self.frameGeometry())
            except Exception as e:
                self.bubble.show_text("启动失败: " + str(e)[:30], timeout=2500)
                self.bubble.position_above(self.frameGeometry())
        else:
            self.bubble.show_text("找不到热榜组件", timeout=2500)
            self.bubble.position_above(self.frameGeometry())

    def _open_settings(self):
        dlg = SettingsDialog(self.cfg)
        dlg.cfg_quick_launch = self.cfg.get("quick_launch", QUICK_LAUNCH_ITEMS)
        if dlg.exec_():
            self.cfg = dlg.get_cfg()
            save_config(self.cfg)
            self.history = [{"role": "system", "content": self.cfg["system_prompt"]}]
            self.client.cfg = self.cfg
            # 应用功能开关
            if self.cfg.get("sys_monitor_enabled", False):
                self.sysmon_timer.start()
            else:
                self.sysmon_timer.stop()
            self._set_state("waving")
            self.bubble.show_text("设置已保存 ✨")
            self.bubble.position_above(self.frameGeometry())

    def _clear_history(self):
        self.history = [{"role": "system", "content": self.cfg["system_prompt"]}]
        self.bubble.show_text("历史已清除 😊")
        self.bubble.position_above(self.frameGeometry())

    # ---------- 全局热键 ----------
    def _setup_hotkey(self):
        try:
            MOD_ALT, MOD_CONTROL = 0x1, 0x2
            if not ctypes.windll.user32.RegisterHotKey(
                    int(self.winId()), 1, MOD_CONTROL | MOD_ALT, ord("V")):
                print("hotkey register failed")
        except Exception as e:
            print("hotkey setup error:", e)

    def nativeEvent(self, eventType, message):
        try:
            if eventType == "windows_generic_MSG":
                from ctypes import wintypes
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 0x0312 and msg.wParam == 1:
                    self.start_listen()
                    return True, 0
        except Exception:
            pass
        return super().nativeEvent(eventType, message)

    def closeEvent(self, e):
        try:
            ctypes.windll.user32.UnregisterHotKey(int(self.winId()), 1)
        except Exception:
            pass
        self.voice.stop()
        self.bubble.close()
        super().closeEvent(e)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    pet = DesktopPet()
    pet.show()
    sys.exit(app.exec_())
