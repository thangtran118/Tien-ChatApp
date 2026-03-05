import sys
import socket
import threading
import json
import base64
import os
from datetime import datetime, timezone, timedelta
import cv2
import pyaudio
from PIL import Image
import io
import queue
import time
import wave
import pygame
import tempfile

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QListWidget, QListWidgetItem,
    QFrame, QScrollArea, QFileDialog, QMessageBox,
    QInputDialog, QDialog, QGridLayout, QAbstractItemView, QStackedWidget
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QObject
from PyQt6.QtGui import QFont, QPixmap, QImage, QKeyEvent
from firebase_service import load_room_history, load_private_history

if len(sys.argv) < 3:
    _app = QApplication(sys.argv)
    QMessageBox.critical(None, "Error", "Missing login info. Please login first.")
    sys.exit(1)

USER_EMAIL = sys.argv[1]
ID_TOKEN   = sys.argv[2]

# ── Media settings ──
VIDEO_WIDTH    = 320
VIDEO_HEIGHT   = 240
VIDEO_QUALITY  = 30
VIDEO_FPS_DELAY= 0.05
AUDIO_RATE     = 44100
AUDIO_CHANNELS = 1
AUDIO_FORMAT   = pyaudio.paInt16
AUDIO_CHUNK    = 1024

# ── Theme ──
BG_MAIN    = "#1c1c1c"
BG_CHAT    = "#252526"
BG_SIDE    = "#1e1e1e"
BG_MSG     = "#2d2d2d"
BG_MSG_ME  = "#005c4b"
FG_TEXT    = "#e0e0e0"
FG_DIM     = "#888888"
ACCENT_BLUE   = "#007ACC"
ACCENT_GREEN  = "#25D366"
ACCENT_RED    = "#E74856"
ACCENT_PURPLE = "#A200FF"
ACCENT_ORANGE = "#f39c12"

STYLE_MAIN = f"""
    QMainWindow, QWidget {{ background-color: {BG_MAIN}; color: {FG_TEXT}; font-family: 'Segoe UI'; font-size: 10pt; }}
    QScrollBar:vertical {{ background: {BG_SIDE}; width: 6px; border-radius: 3px; }}
    QScrollBar::handle:vertical {{ background: #444; border-radius: 3px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
    QListWidget {{ background: {BG_SIDE}; border: none; outline: none; color: {FG_TEXT}; }}
    QListWidget::item {{ padding: 8px 10px; border-radius: 6px; }}
    QListWidget::item:selected {{ background: {ACCENT_BLUE}; color: white; }}
    QListWidget::item:hover {{ background: #2a2a2a; }}
    QSplitter::handle {{ background: #333; width: 1px; }}
    QLineEdit {{
        background: {BG_MSG}; color: {FG_TEXT};
        border: 1px solid #3a3a3a; border-radius: 8px; padding: 6px 12px;
    }}
    QLineEdit:focus {{ border: 1px solid {ACCENT_BLUE}; }}
    QTextEdit {{
        background: {BG_MSG}; color: {FG_TEXT};
        border: 1px solid #3a3a3a; border-radius: 8px; padding: 6px 10px;
    }}
    QPushButton {{
        background: {ACCENT_BLUE}; color: white;
        border: none; border-radius: 6px; padding: 6px 14px;
    }}
    QPushButton:hover {{ background: #1a8fdb; }}
    QPushButton:pressed {{ background: #005a9e; }}
    QPushButton:disabled {{ background: #444; color: #888; }}
"""

# ─────────────────────────────────────────────────────────────
#  Network Worker Thread
# ─────────────────────────────────────────────────────────────
class NetworkWorker(QThread):
    message_received = pyqtSignal(dict)
    disconnected     = pyqtSignal()

    def __init__(self, sock):
        super().__init__()
        self.sock = sock
        self._running = True

    def run(self):
        buffer  = ""
        decoder = json.JSONDecoder()
        try:
            while self._running:
                try:
                    data = self.sock.recv(1024 * 1024 * 4)
                    if not data:
                        break
                    buffer += data.decode('utf-8', errors='ignore')
                    while buffer:
                        buffer = buffer.lstrip()
                        try:
                            obj, idx = decoder.raw_decode(buffer)
                            buffer   = buffer[idx:]
                            self.message_received.emit(obj)
                        except ValueError:
                            break
                except Exception as e:
                    print("Receiver error:", e)
                    break
        finally:
            self.disconnected.emit()

    def stop(self):
        self._running = False


# ─────────────────────────────────────────────────────────────
#  Message Bubble Widget
# ─────────────────────────────────────────────────────────────
class MessageBubble(QFrame):
    def __init__(self, sender, message, timestamp,
                 is_me=False, is_private=False, is_system=False, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QFrame { background: transparent; border: none; }")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(0)

        if is_system:
            lbl = QLabel(f"⚙  {message}")
            lbl.setStyleSheet(f"color: {FG_DIM}; font-size: 9pt; background: transparent;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setWordWrap(True)
            layout.addWidget(lbl)
            return

        bubble = QFrame()
        bubble.setMaximumWidth(480)
        bl = QVBoxLayout(bubble)
        bl.setContentsMargins(10, 6, 10, 6)
        bl.setSpacing(2)

        if is_me:
            bg, sc = BG_MSG_ME, "#a8d9c8"
        elif is_private:
            bg, sc = "#2d1f40", "#c89ef5"
        else:
            bg, sc = BG_MSG, ACCENT_BLUE

        bubble.setStyleSheet(f"QFrame {{ background: {bg}; border-radius: 10px; }}")

        if not is_me:
            sl = QLabel(sender)
            sl.setStyleSheet(f"color: {sc}; font-weight: bold; font-size: 9pt; background: transparent;")
            bl.addWidget(sl)

        ml = QLabel(message)
        ml.setWordWrap(True)
        ml.setStyleSheet(f"color: {FG_TEXT}; background: transparent; font-size: 10pt;")
        ml.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bl.addWidget(ml)

        tl = QLabel(timestamp)
        tl.setStyleSheet(f"color: {FG_DIM}; font-size: 8pt; background: transparent;")
        tl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        bl.addWidget(tl)

        if is_me:
            layout.addStretch()
            layout.addWidget(bubble)
        else:
            layout.addWidget(bubble)
            layout.addStretch()


# ─────────────────────────────────────────────────────────────
#  File / Voice Bubble Widget
# ─────────────────────────────────────────────────────────────
class FileBubble(QFrame):
    def __init__(self, sender, filename, file_bytes, is_voice, timestamp,
                 is_me=False, on_play=None, on_download=None, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QFrame { background: transparent; border: none; }")
        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 2, 8, 2)

        bubble = QFrame()
        bubble.setMaximumWidth(420)
        bl = QVBoxLayout(bubble)
        bl.setContentsMargins(10, 8, 10, 8)
        bl.setSpacing(4)

        bg = BG_MSG_ME if is_me else BG_MSG
        bubble.setStyleSheet(f"QFrame {{ background: {bg}; border-radius: 10px; }}")

        if not is_me:
            sl = QLabel(sender)
            sl.setStyleSheet(f"color: {ACCENT_BLUE}; font-weight: bold; font-size: 9pt; background: transparent;")
            bl.addWidget(sl)

        if is_voice:
            il = QLabel("🎤  Voice Message")
        else:
            il = QLabel(f"📎  {filename}")
            il.setWordWrap(True)
        il.setStyleSheet(f"color: {FG_TEXT}; background: transparent; font-size: 10pt;")
        bl.addWidget(il)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        if is_voice and on_play:
            pb = QPushButton("▶ Play")
            pb.setFixedHeight(28)
            pb.setStyleSheet("QPushButton { background: #2d89ef; color: white; border-radius: 5px; font-size: 9pt; padding: 0 10px; border: none; } QPushButton:hover { background: #1a78de; }")
            pb.clicked.connect(lambda: on_play(file_bytes))
            btn_row.addWidget(pb)

        if on_download:
            db = QPushButton("⬇ Download")
            db.setFixedHeight(28)
            db.setStyleSheet("QPushButton { background: #107c10; color: white; border-radius: 5px; font-size: 9pt; padding: 0 10px; border: none; } QPushButton:hover { background: #0d6b0d; }")
            db.clicked.connect(lambda: on_download(filename, file_bytes))
            btn_row.addWidget(db)

        btn_row.addStretch()
        bl.addLayout(btn_row)

        tl = QLabel(timestamp)
        tl.setStyleSheet(f"color: {FG_DIM}; font-size: 8pt; background: transparent;")
        tl.setAlignment(Qt.AlignmentFlag.AlignRight)
        bl.addWidget(tl)

        if is_me:
            outer.addStretch()
            outer.addWidget(bubble)
        else:
            outer.addWidget(bubble)
            outer.addStretch()


# ─────────────────────────────────────────────────────────────
#  Scrollable Chat Area
# ─────────────────────────────────────────────────────────────
class ChatArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setStyleSheet(f"QScrollArea {{ background: {BG_CHAT}; border: none; }}")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._container = QWidget()
        self._container.setStyleSheet(f"background: {BG_CHAT};")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(0, 8, 0, 8)
        self._layout.setSpacing(2)
        self._layout.addStretch()
        self.setWidget(self._container)

        self._want_scroll_bottom = False
        self.verticalScrollBar().rangeChanged.connect(self._on_range_changed)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll_value_changed)

    def _on_range_changed(self, _min, _max):
        """Fires whenever content height changes; scrolls to bottom if requested."""
        if self._want_scroll_bottom:
            self.verticalScrollBar().setValue(_max)

    def _on_scroll_value_changed(self, value):
        """If user scrolls away from bottom, stop auto-scrolling."""
        sb = self.verticalScrollBar()
        if value < sb.maximum() - 30:
            self._want_scroll_bottom = False

    def add_widget(self, widget):
        """Add widget and scroll to bottom (for real-time messages)."""
        self._want_scroll_bottom = True
        self._layout.insertWidget(self._layout.count() - 1, widget)

    def add_widget_direct(self, widget):
        """Add widget immediately without deferring (for history loading)."""
        self._layout.insertWidget(self._layout.count() - 1, widget)

    def clear(self):
        self._want_scroll_bottom = False
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def scroll_to_bottom(self):
        """Call after bulk history load to scroll once layout has settled."""
        self._want_scroll_bottom = True
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def _scroll_to_bottom(self):
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())


# ─────────────────────────────────────────────────────────────
#  Text Edit with Enter-to-Send
# ─────────────────────────────────────────────────────────────
class EnterTextEdit(QTextEdit):
    enter_pressed = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.enter_pressed.emit()
        else:
            super().keyPressEvent(event)


# ─────────────────────────────────────────────────────────────
#  Main Client Window
# ─────────────────────────────────────────────────────────────
class SimplifiedClient(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Chat")
        self.resize(1100, 700)
        self.setStyleSheet(STYLE_MAIN)
        self.setMinimumSize(800, 500)

        pygame.mixer.init()

        self.sock        = None
        self.username    = USER_EMAIL
        self.connected   = False
        self.net_worker  = None

        self.current_room      = 'General'
        self.private_chat_user = None
        self.private_history   = {}
        self.group_history     = {}

        self.in_call        = False
        self.call_peer      = None
        self.call_type      = None
        self.is_group_call  = False
        self.call_window    = None
        self.call_video_label = None

        self.video_capture       = None
        self.video_send_thread   = None
        self.video_display_thread= None
        self.video_display_queue = queue.Queue(maxsize=8)
        self.audio_interface     = None
        self.audio_stream_in     = None
        self.audio_stream_out    = None
        self.audio_send_thread   = None
        self.audio_play_thread   = None
        self.audio_play_queue    = queue.Queue(maxsize=50)
        self.call_stop_event     = threading.Event()

        self.is_recording    = False
        self.audio_frames    = []
        self.temp_audio_file = os.path.join(os.path.expanduser('~'), 'temp_voice_msg.wav')
        self.rec_interface   = None
        self.rec_stream      = None
        self.rec_thread      = None

        self.download_folder = os.path.join(os.path.expanduser('~'), 'ChatDownloads')
        os.makedirs(self.download_folder, exist_ok=True)

        self._setup_login_screen()
        self._center_window()

    # ── Window helpers ──────────────────────────────────────

    def _center_window(self):
        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - self.width()) // 2,
                  (screen.height() - self.height()) // 2)

    # ── Login Screen ────────────────────────────────────────

    def _setup_login_screen(self):
        self.stacked = QStackedWidget()
        self.setCentralWidget(self.stacked)

        page = QWidget()
        page.setStyleSheet(f"background: {BG_MAIN};")
        outer = QVBoxLayout(page)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setFixedWidth(380)
        card.setStyleSheet(f"QFrame {{ background: #1e1e2e; border: 1px solid #3a3a5c; border-radius: 12px; }}")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(36, 32, 36, 32)
        cl.setSpacing(0)

        title = QLabel("💬  Secure Chat")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {ACCENT_BLUE}; border: none; background: transparent;")
        cl.addWidget(title)

        sub = QLabel("Connect to server")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(f"color: {FG_DIM}; font-size: 9pt; border: none; background: transparent;")
        cl.addWidget(sub)
        cl.addSpacing(24)

        def _field(label_text, default=""):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color: {FG_DIM}; font-size: 9pt; border: none; background: transparent;")
            cl.addWidget(lbl)
            cl.addSpacing(4)
            entry = QLineEdit(default)
            entry.setFixedHeight(38)
            cl.addWidget(entry)
            cl.addSpacing(14)
            return entry

        self.host_entry = _field("SERVER HOST", "127.0.0.1")
        self.port_entry = _field("SERVER PORT", "5555")

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {ACCENT_RED}; font-size: 9pt; border: none; background: transparent;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(self.status_label)
        cl.addSpacing(6)

        btn = QPushButton("🔗  Connect")
        btn.setFixedHeight(42)
        btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        btn.setStyleSheet(f"QPushButton {{ background: {ACCENT_BLUE}; color: white; border-radius: 8px; border: none; }} QPushButton:hover {{ background: #1a8fdb; }}")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self.connect_to_server)
        self.port_entry.returnPressed.connect(self.connect_to_server)
        cl.addWidget(btn)

        user_lbl = QLabel(f"Logged in as: {self.username}")
        user_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        user_lbl.setStyleSheet(f"color: {ACCENT_GREEN}; font-size: 9pt; border: none; background: transparent; margin-top: 12px;")
        cl.addWidget(user_lbl)

        outer.addWidget(card)
        self.stacked.addWidget(page)

    # ── Chat UI Setup ────────────────────────────────────────

    def _setup_chat_ui(self):
        page = QWidget()
        main = QHBoxLayout(page)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # ── Sidebar ──
        sidebar = QFrame()
        sidebar.setFixedWidth(240)
        sidebar.setStyleSheet(f"QFrame {{ background: {BG_SIDE}; border-right: 1px solid #2a2a2a; }}")
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(0, 0, 0, 0)
        sb.setSpacing(0)

        user_bar = QFrame()
        user_bar.setFixedHeight(56)
        user_bar.setStyleSheet("background: #161616; border-bottom: 1px solid #2a2a2a;")
        ub = QHBoxLayout(user_bar)
        ub.setContentsMargins(12, 0, 12, 0)
        av = QLabel("👤")
        av.setStyleSheet("font-size: 18pt; background: transparent;")
        ub.addWidget(av)
        nl = QLabel(self.username.split("@")[0])
        nl.setStyleSheet(f"color: {ACCENT_GREEN}; font-weight: bold; font-size: 10pt; background: transparent;")
        ub.addWidget(nl, 1)
        sb.addWidget(user_bar)

        users_lbl = QLabel("  🟢 Online Users")
        users_lbl.setFixedHeight(28)
        users_lbl.setStyleSheet(f"color: {FG_DIM}; font-size: 8pt; font-weight: bold; background: #161616; border-bottom: 1px solid #2a2a2a;")
        sb.addWidget(users_lbl)

        self.users_list = QListWidget()
        self.users_list.setMaximumHeight(160)
        self.users_list.setStyleSheet(f"QListWidget {{ background: {BG_SIDE}; border: none; }} QListWidget::item {{ padding: 7px 12px; color: {FG_TEXT}; }} QListWidget::item:selected {{ background: {ACCENT_PURPLE}; color: white; border-radius: 4px; }} QListWidget::item:hover {{ background: #2a2a2a; }}")
        self.users_list.itemDoubleClicked.connect(self._on_user_double_click)
        sb.addWidget(self.users_list)

        rooms_lbl = QLabel("  🏢 Chat Rooms")
        rooms_lbl.setFixedHeight(28)
        rooms_lbl.setStyleSheet(f"color: {FG_DIM}; font-size: 8pt; font-weight: bold; background: #161616; border-bottom: 1px solid #2a2a2a; border-top: 1px solid #2a2a2a;")
        sb.addWidget(rooms_lbl)

        self.rooms_list = QListWidget()
        self.rooms_list.setStyleSheet(f"QListWidget {{ background: {BG_SIDE}; border: none; }} QListWidget::item {{ padding: 7px 12px; color: {FG_TEXT}; }} QListWidget::item:selected {{ background: {ACCENT_BLUE}; color: white; border-radius: 4px; }} QListWidget::item:hover {{ background: #2a2a2a; }}")
        self.rooms_list.addItem("General")
        self.rooms_list.itemClicked.connect(self._on_room_clicked)
        sb.addWidget(self.rooms_list, 1)

        cr_btn = QPushButton("➕  New Room")
        cr_btn.setFixedHeight(36)
        cr_btn.setStyleSheet(f"QPushButton {{ background: #2a2a2a; color: {FG_TEXT}; border: none; border-top: 1px solid #333; font-size: 9pt; }} QPushButton:hover {{ background: #333; }}")
        cr_btn.clicked.connect(self.create_room)
        sb.addWidget(cr_btn)

        main.addWidget(sidebar)

        # ── Chat Panel ──
        chat_panel = QWidget()
        chat_panel.setStyleSheet(f"background: {BG_CHAT};")
        cp = QVBoxLayout(chat_panel)
        cp.setContentsMargins(0, 0, 0, 0)
        cp.setSpacing(0)

        # Header
        self.header_bar = QFrame()
        self.header_bar.setFixedHeight(52)
        self.header_bar.setStyleSheet("background: #1a1a2e; border-bottom: 1px solid #2a2a2a;")
        hb = QHBoxLayout(self.header_bar)
        hb.setContentsMargins(16, 0, 12, 0)

        self.chat_title = QLabel("# General")
        self.chat_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.chat_title.setStyleSheet(f"color: {FG_TEXT}; background: transparent;")
        hb.addWidget(self.chat_title, 1)

        self.btn_priv_voice = self._call_btn("Voice", ACCENT_ORANGE,  lambda: self.initiate_call('private', 'voice'))
        self.btn_priv_video = self._call_btn("Video", "#8e44ad",       lambda: self.initiate_call('private', 'video'))
        self.btn_grp_voice  = self._call_btn("Voice", ACCENT_ORANGE,  lambda: self.initiate_call('group', 'voice'))
        self.btn_grp_video  = self._call_btn("Video", "#8e44ad",       lambda: self.initiate_call('group', 'video'))
        self.btn_end_call   = self._call_btn("End Call", ACCENT_RED,   self.end_call)

        for b in [self.btn_priv_voice, self.btn_priv_video,
                  self.btn_grp_voice,  self.btn_grp_video, self.btn_end_call]:
            hb.addWidget(b)
            b.hide()

        cp.addWidget(self.header_bar)

        self.chat_area = ChatArea()
        cp.addWidget(self.chat_area, 1)

        # Input bar (outer wrapper: toolbar + text row)
        input_wrapper = QFrame()
        input_wrapper.setStyleSheet("background: #1e1e1e; border-top: 1px solid #2a2a2a;")
        input_wrapper_layout = QVBoxLayout(input_wrapper)
        input_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        input_wrapper_layout.setSpacing(0)

        # ── Toolbar row (File, Emoji, Voice) ──
        toolbar = QFrame()
        toolbar.setFixedHeight(36)
        toolbar.setStyleSheet("background: #181818; border-bottom: 1px solid #2a2a2a;")
        tb_lay = QHBoxLayout(toolbar)
        tb_lay.setContentsMargins(10, 4, 10, 4)
        tb_lay.setSpacing(4)

        def _tool_btn(label, slot):
            b = QPushButton(label)
            b.setFixedHeight(26)
            b.setFont(QFont("Segoe UI Emoji", 10))
            b.setStyleSheet(f"""
                QPushButton {{
                    background: #2a2a2a; color: {FG_TEXT};
                    border: none; border-radius: 5px; padding: 0 10px;
                    font-size: 10pt;
                }}
                QPushButton:hover {{ background: #3a3a3a; }}
            """)
            b.clicked.connect(slot)
            return b

        self.voice_btn = QPushButton("🎤  Voice")
        self.voice_btn.setFixedHeight(26)
        self.voice_btn.setFont(QFont("Segoe UI Emoji", 10))
        self.voice_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT_BLUE}; color: white;
                border: none; border-radius: 5px; padding: 0 10px; font-size: 10pt;
            }}
            QPushButton:hover {{ background: #1a8fdb; }}
        """)
        self.voice_btn.clicked.connect(self.toggle_recording)

        tb_lay.addWidget(self.voice_btn)
        tb_lay.addWidget(_tool_btn("📎  File", self.send_file))
        tb_lay.addWidget(_tool_btn("😊  Emoji", self.open_emoji_picker))
        tb_lay.addStretch()

        input_wrapper_layout.addWidget(toolbar)

        # ── Text + Send row ──
        text_row = QFrame()
        text_row.setStyleSheet("background: #1e1e1e;")
        tr_lay = QHBoxLayout(text_row)
        tr_lay.setContentsMargins(10, 6, 10, 6)
        tr_lay.setSpacing(8)

        self.message_entry = EnterTextEdit()
        self.message_entry.setPlaceholderText("Type a message... (Enter to send, Shift+Enter for newline)")
        self.message_entry.setFixedHeight(48)
        self.message_entry.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_MSG}; color: {FG_TEXT};
                border: 1px solid #3a3a3a; border-radius: 10px;
                padding: 6px 12px; font-size: 10pt;
            }}
        """)
        self.message_entry.enter_pressed.connect(self.send_message)
        tr_lay.addWidget(self.message_entry, 1)

        send_btn = QPushButton("Send ▶")
        send_btn.setFixedSize(80, 48)
        send_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT_GREEN}; color: #111;
                border-radius: 10px; border: none;
            }}
            QPushButton:hover {{ background: #1fb855; }}
            QPushButton:pressed {{ background: #179e42; }}
        """)
        send_btn.clicked.connect(self.send_message)
        tr_lay.addWidget(send_btn)

        input_wrapper_layout.addWidget(text_row)

        cp.addWidget(input_wrapper)
        main.addWidget(chat_panel, 1)

        self.stacked.addWidget(page)
        self.stacked.setCurrentIndex(1)

        self.rooms_list.setCurrentRow(0)
        self._on_room_clicked(self.rooms_list.item(0))

    def _call_btn(self, text, color, slot):
        b = QPushButton(text)
        b.setFixedHeight(30)
        b.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"""
            QPushButton {{
                background: {color}; color: white;
                border-radius: 6px; border: none;
                padding: 0 12px; font-size: 9pt;
            }}
            QPushButton:hover {{ background: {color}dd; }}
            QPushButton:pressed {{ background: {color}99; }}
        """)
        b.clicked.connect(slot)
        return b

    def _update_call_buttons(self):
        for b in [self.btn_priv_voice, self.btn_priv_video,
                  self.btn_grp_voice,  self.btn_grp_video, self.btn_end_call]:
            b.hide()
        self.voice_btn.setEnabled(not self.in_call)
        if self.in_call:
            self.btn_end_call.show()
        elif self.private_chat_user:
            self.btn_priv_voice.show()
            self.btn_priv_video.show()
        elif self.current_room:
            self.btn_grp_voice.show()
            self.btn_grp_video.show()

    # ── Networking ───────────────────────────────────────────

    def connect_to_server(self):
        host     = self.host_entry.text().strip()
        port_str = self.port_entry.text().strip()
        self.status_label.setText("Connecting...")
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((host, int(port_str)))
            self.sock.send(USER_EMAIL.encode('utf-8'))
            self.connected = True

            self.net_worker = NetworkWorker(self.sock)
            self.net_worker.message_received.connect(self.process_message)
            self.net_worker.disconnected.connect(self._on_disconnected)
            self.net_worker.start()

            self._setup_chat_ui()
        except Exception as e:
            self.status_label.setText(f"Failed: {e}")

    def _on_disconnected(self):
        self.connected = False
        self.display_system_message("Disconnected from server.")

    def _send_json(self, data):
        try:
            self.sock.send((json.dumps(data) + "\n").encode('utf-8'))
        except Exception as e:
            print("Send JSON error:", e)

    # ── Message Processing ───────────────────────────────────

    def process_message(self, msg):
        t = msg.get('type')

        if t == 'welcome':
            self.display_system_message(msg.get('message', ''))
            for room in msg.get('rooms', []):
                if room not in [self.rooms_list.item(i).text() for i in range(self.rooms_list.count())]:
                    self.rooms_list.addItem(room)

        elif t == 'chat':
            ts = self.convert_timestamp(msg.get('timestamp'))
            if msg.get('room') == self.current_room and not self.private_chat_user:
                self.display_message(msg.get('sender'), msg.get('message'), ts)

        elif t == 'private':
            sender = msg.get('sender')
            ts     = self.convert_timestamp(msg.get('timestamp'))
            if self.private_chat_user == sender:
                self.display_private_message(sender, msg.get('message'), ts)
            else:
                self.display_system_message(f"🔒 New private message from {sender}")

        elif t == 'file':
            sender    = msg.get('sender')
            filename  = msg.get('filename')
            filedata  = msg.get('filedata')
            filetype  = msg.get('filetype')
            ts        = self.convert_timestamp(msg.get('timestamp'))
            room      = msg.get('room')
            recipient = msg.get('recipient')
            if room:
                if room == self.current_room and not self.private_chat_user:
                    self.receive_file(sender, filename, filedata, filetype, ts)
                else:
                    self.display_system_message(f"📁 New file in room {room}")
            elif recipient:
                if self.private_chat_user == sender:
                    self.receive_file(sender, filename, filedata, filetype, ts)
                else:
                    self.display_system_message(f"🔒 New private file from {sender}")

        elif t == 'client_list':
            self.users_list.clear()
            for u in msg.get('clients', []):
                if u != self.username:
                    self.users_list.addItem(u)

        elif t == 'room_created':
            room = msg.get('room_name')
            if room not in [self.rooms_list.item(i).text() for i in range(self.rooms_list.count())]:
                self.rooms_list.addItem(room)
            self.display_system_message(f"Room '{room}' created")

        elif t == 'call_request':
            sender, call_type = msg.get('sender'), msg.get('call_type')
            QTimer.singleShot(0, lambda: self.handle_call_request(sender, call_type))
        elif t == 'group_call_request':
            room, caller, call_type = msg.get('room'), msg.get('caller'), msg.get('call_type')
            QTimer.singleShot(0, lambda: self.handle_group_call_request(room, caller, call_type))
        elif t == 'call_response':
            responder, accepted, call_type = msg.get('responder'), msg.get('accepted'), msg.get('call_type', 'video')
            QTimer.singleShot(0, lambda: self.handle_call_response(responder, accepted, call_type))
        elif t == 'call_data':
            sender = msg.get('sender')
            if sender == self.username:
                return
            if msg.get('data_type') == 'video':
                try:
                    fb = base64.b64decode(msg.get('data'))
                    try: self.video_display_queue.put_nowait(fb)
                    except queue.Full: pass
                except Exception as e:
                    print("Video decode error:", e)
            elif msg.get('data_type') == 'audio':
                try:
                    ab = base64.b64decode(msg.get('data'))
                    try: self.audio_play_queue.put_nowait(ab)
                    except queue.Full: pass
                except Exception as e:
                    print("Audio decode error:", e)
        elif t == 'call_ended':
            peer = msg.get('peer', '')
            QTimer.singleShot(0, lambda: self._on_remote_call_ended(peer))

    # ── Display Helpers ──────────────────────────────────────

    def display_message(self, sender, message, timestamp):
        b = MessageBubble(sender, message, timestamp, is_me=(sender == self.username))
        QTimer.singleShot(0, lambda: self.chat_area.add_widget(b))

    def display_private_message(self, sender, message, timestamp):
        b = MessageBubble(sender, message, timestamp, is_me=(sender == self.username), is_private=True)
        QTimer.singleShot(0, lambda: self.chat_area.add_widget(b))

    def display_system_message(self, message):
        b = MessageBubble(None, message, None, is_system=True)
        QTimer.singleShot(0, lambda: self.chat_area.add_widget(b))

    def display_file_message(self, sender, filename, file_bytes, is_voice, timestamp):
        b = FileBubble(sender, filename, file_bytes, is_voice, timestamp,
                       is_me=(sender == self.username),
                       on_play=self.play_voice if is_voice else None,
                       on_download=self.download_file)
        QTimer.singleShot(0, lambda: self.chat_area.add_widget(b))

    # ── Sending ──────────────────────────────────────────────

    def send_message(self):
        message = self.message_entry.toPlainText().strip()
        if not message:
            return
        ts = datetime.now().strftime('%H:%M:%S')
        try:
            if self.private_chat_user:
                self._send_json({'type': 'private', 'recipient': self.private_chat_user, 'message': message})
                self.display_private_message(self.username, message, ts)
            else:
                self._send_json({'type': 'chat', 'room': self.current_room, 'message': message})
                self.display_message(self.username, message, ts)
            self.message_entry.clear()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to send: {e}")

    def send_file(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Select file to send")
        if not filepath:
            return
        try:
            if os.path.getsize(filepath) > 20 * 1024 * 1024:
                QMessageBox.warning(self, "Error", "File size must be <20MB")
                return
            with open(filepath, 'rb') as f:
                file_bytes = f.read()
            filedata = base64.b64encode(file_bytes).decode('utf-8')
            filename = os.path.basename(filepath)
            filetype = os.path.splitext(filename)[1].lower()
            data = {'type': 'file', 'filename': filename, 'filedata': filedata, 'filetype': filetype}
            if self.private_chat_user:
                data['recipient'] = self.private_chat_user
            else:
                data['room'] = self.current_room
            self._send_json(data)
            is_voice = (filetype == '.wav' and filename.startswith('voice_msg_'))
            self.display_file_message(self.username, filename, file_bytes, is_voice,
                                      datetime.now().strftime('%H:%M:%S'))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"File send failed: {e}")

    def receive_file(self, sender, filename, filedata, filetype, timestamp):
        try:
            file_bytes = base64.b64decode(filedata)
            is_voice   = (filetype == '.wav' and filename.startswith('voice_msg_'))
            self.display_file_message(sender, filename, file_bytes, is_voice, timestamp)
        except Exception as e:
            self.display_system_message(f"Error receiving file: {e}")

    def play_voice(self, file_bytes):
        try:
            pygame.mixer.music.stop()
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            tmp.write(file_bytes)
            tmp.close()
            pygame.mixer.music.load(tmp.name)
            pygame.mixer.music.play()
        except Exception as e:
            self.display_system_message(f"Error playing voice: {e}")

    def download_file(self, filename, file_bytes):
        try:
            save_path, _ = QFileDialog.getSaveFileName(self, "Save File", filename)
            if save_path:
                with open(save_path, 'wb') as f:
                    f.write(file_bytes)
                self.display_system_message(f"File saved to {save_path}")
        except Exception as e:
            self.display_system_message(f"Download error: {e}")

    # ── Emoji ────────────────────────────────────────────────

    def open_emoji_picker(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Emoji")
        dlg.setStyleSheet(f"background: #1e1e1e; color: {FG_TEXT};")
        grid = QGridLayout(dlg)
        grid.setSpacing(4)
        grid.setContentsMargins(8, 8, 8, 8)
        emojis = ["😀","😁","😂","🤣","😊","😍","🥰","😘",
                  "😎","🤔","😭","😡","🔥","👍","👎","👏",
                  "🙏","❤️","💔","🎉","✨","🌸","🌈","💯"]
        cols = 8
        for i, e in enumerate(emojis):
            b = QPushButton(e)
            b.setFixedSize(52, 52)
            b.setFont(QFont("Segoe UI Emoji", 20))
            b.setStyleSheet("QPushButton { background: #2a2a2a; border: none; border-radius: 8px; } QPushButton:hover { background: #3a3a3a; }")
            b.clicked.connect(lambda _, em=e: (self.message_entry.insertPlainText(em), dlg.accept()))
            grid.addWidget(b, i // cols, i % cols)
        dlg.adjustSize()
        dlg.exec()

    # ── Room / User ──────────────────────────────────────────

    def _on_room_clicked(self, item):
        if not item:
            return
        room = item.text()
        self.current_room      = room
        self.private_chat_user = None
        self.chat_title.setText(f"# {room}")
        self.chat_title.setStyleSheet(f"color: {FG_TEXT}; background: transparent;")
        self.chat_area.clear()
        try:
            for msg in load_room_history(room):
                sender   = msg.get("sender")
                ts       = self.convert_timestamp(msg.get("timestamp"))
                content  = msg.get("content")
                filename = msg.get("filename")
                filedata = msg.get("filedata")
                filetype = msg.get("filetype")
                if content:
                    b = MessageBubble(sender, content, ts, is_me=(sender == self.username))
                    self.chat_area.add_widget_direct(b)
                elif filename and filedata:
                    fb       = base64.b64decode(filedata)
                    is_voice = (filetype == ".wav" and filename.startswith("voice_msg_"))
                    b = FileBubble(sender, filename, fb, is_voice, ts,
                                   is_me=(sender == self.username),
                                   on_play=self.play_voice if is_voice else None,
                                   on_download=self.download_file)
                    self.chat_area.add_widget_direct(b)
        except Exception as e:
            print("Load history error:", e)
        sys_b = MessageBubble(None, f"Switched to room: {room}", None, is_system=True)
        self.chat_area.add_widget_direct(sys_b)
        self._update_call_buttons()
        self.chat_area.scroll_to_bottom()

    def _on_user_double_click(self, item):
        user = item.text()
        self.current_room      = None
        self.private_chat_user = user
        self.chat_title.setText(f"🔒  {user}")
        self.chat_title.setStyleSheet(f"color: {ACCENT_PURPLE}; background: transparent;")
        self.chat_area.clear()
        try:
            for msg in load_private_history(self.username, user):
                sender   = msg.get("sender")
                ts       = self.convert_timestamp(msg.get("timestamp"))
                content  = msg.get("content")
                filename = msg.get("filename")
                filedata = msg.get("filedata")
                filetype = msg.get("filetype")
                if content:
                    b = MessageBubble(sender, content, ts,
                                      is_me=(sender == self.username), is_private=True)
                    self.chat_area.add_widget_direct(b)
                elif filename and filedata:
                    fb       = base64.b64decode(filedata)
                    is_voice = (filetype == ".wav" and filename.startswith("voice_msg_"))
                    b = FileBubble(sender, filename, fb, is_voice, ts,
                                   is_me=(sender == self.username),
                                   on_play=self.play_voice if is_voice else None,
                                   on_download=self.download_file)
                    self.chat_area.add_widget_direct(b)
        except Exception as e:
            print("Private history load error:", e)
        sys_b = MessageBubble(None, f"Private chat with {user} started", None, is_system=True)
        self.chat_area.add_widget_direct(sys_b)
        self._update_call_buttons()
        self.chat_area.scroll_to_bottom()

    def create_room(self):
        name, ok = QInputDialog.getText(self, "Create Room", "Enter room name:")
        if ok and name:
            self._send_json({'type': 'create_room', 'room_name': name})

    def convert_timestamp(self, raw_ts):
        try:
            if not raw_ts:
                return datetime.now().strftime('%H:%M:%S')
            dt = datetime.fromisoformat(str(raw_ts))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone(timedelta(hours=7))).strftime('%H:%M:%S')
        except Exception:
            return datetime.now().strftime('%H:%M:%S')

    # ── Voice Recording ──────────────────────────────────────

    def toggle_recording(self):
        if self.in_call:
            QMessageBox.warning(self, "Busy", "Cannot record while in a call.")
            return
        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()

    def start_recording(self):
        self.is_recording = True
        self.audio_frames = []
        self.voice_btn.setText("🔴")
        self.voice_btn.setStyleSheet(f"QPushButton {{ background: {ACCENT_RED}; color: white; border-radius: 20px; font-size: 14pt; border: none; }}")
        self.display_system_message("Recording... Click 🔴 to stop and send.")
        try:
            self.rec_interface = pyaudio.PyAudio()
            self.rec_stream    = self.rec_interface.open(
                format=AUDIO_FORMAT, channels=AUDIO_CHANNELS, rate=AUDIO_RATE,
                input=True, frames_per_buffer=AUDIO_CHUNK,
                stream_callback=self._audio_callback)
            self.rec_stream.start_stream()
            self.rec_thread = threading.Thread(target=self._recording_loop, daemon=True)
            self.rec_thread.start()
        except Exception as e:
            self.is_recording = False
            self.voice_btn.setText("🎤")
            self.voice_btn.setStyleSheet(f"QPushButton {{ background: {ACCENT_BLUE}; color: white; border-radius: 20px; font-size: 14pt; border: none; }}")
            QMessageBox.critical(self, "Audio Error", f"Could not start recording: {e}")

    def _audio_callback(self, in_data, frame_count, time_info, status):
        if self.is_recording:
            self.audio_frames.append(in_data)
        return (in_data, pyaudio.paContinue)

    def _recording_loop(self):
        while self.is_recording:
            time.sleep(0.1)
        if self.rec_stream and self.rec_stream.is_active():
            self.rec_stream.stop_stream()
            self.rec_stream.close()
        self.rec_stream = None

    def stop_recording(self):
        if not self.is_recording:
            return
        self.is_recording = False
        self.voice_btn.setText("🎤")
        self.voice_btn.setStyleSheet(f"QPushButton {{ background: {ACCENT_BLUE}; color: white; border-radius: 20px; font-size: 14pt; border: none; }}")
        self.display_system_message("Voice message stopped. Sending...")
        if self.rec_thread:
            self.rec_thread.join(timeout=1.0)
            self.rec_thread = None
        if not self.audio_frames:
            self.display_system_message("Recording too short or failed.")
            if self.rec_interface: self.rec_interface.terminate(); self.rec_interface = None
            return
        try:
            sw = self.rec_interface.get_sample_size(AUDIO_FORMAT)
            with wave.open(self.temp_audio_file, 'wb') as wf:
                wf.setnchannels(AUDIO_CHANNELS)
                wf.setsampwidth(sw)
                wf.setframerate(AUDIO_RATE)
                wf.writeframes(b''.join(self.audio_frames))
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save audio: {e}")
            if self.rec_interface: self.rec_interface.terminate(); self.rec_interface = None
            return
        self._send_voice_message_file(self.temp_audio_file)
        if self.rec_interface: self.rec_interface.terminate(); self.rec_interface = None
        try: os.remove(self.temp_audio_file)
        except: pass

    def _send_voice_message_file(self, filepath):
        try:
            if os.path.getsize(filepath) > 20 * 1024 * 1024:
                QMessageBox.warning(self, "Error", "Voice message file size must be <20MB")
                return
            with open(filepath, 'rb') as f:
                file_bytes = f.read()
            filedata = base64.b64encode(file_bytes).decode('utf-8')
            filename = f"voice_msg_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
            data = {'type': 'file', 'filename': filename, 'filedata': filedata, 'filetype': '.wav'}
            if self.private_chat_user:
                data['recipient'] = self.private_chat_user
            else:
                data['room'] = self.current_room
            self._send_json(data)
            self.display_file_message(self.username, filename, file_bytes, True,
                                      datetime.now().strftime('%H:%M:%S'))
        except Exception as e:
            QMessageBox.critical(self, "Send Error", f"Voice message send failed: {e}")

    # ── Calling ──────────────────────────────────────────────

    def initiate_call(self, target_type, call_type):
        if self.in_call:
            QMessageBox.warning(self, "Warning", "Already in an active call.")
            return
        if target_type == 'private':
            if not self.private_chat_user:
                QMessageBox.information(self, "Info", "Double-click a user to start a private chat first.")
                return
            self._send_json({'type': 'call_request', 'recipient': self.private_chat_user, 'call_type': call_type})
            self.call_peer     = self.private_chat_user
            self.is_group_call = False
            self.display_system_message(f"Calling {self.private_chat_user}... ({call_type})")
        else:
            if not self.current_room:
                QMessageBox.information(self, "Info", "Select a room to start a group call.")
                return
            self._send_json({'type': 'group_call_request', 'room': self.current_room,
                             'caller': self.username, 'call_type': call_type})
            self.call_peer     = self.current_room
            self.is_group_call = True
            self.display_system_message(f"Initiating Group Call in {self.current_room} ({call_type})...")
            self._start_call_internal(self.current_room, call_type, is_group=True)
        self._update_call_buttons()

    def handle_call_request(self, caller, call_type):
        if self.in_call:
            self._send_json({'type': 'call_response', 'caller': caller, 'accepted': False, 'call_type': call_type})
            return
        resp = QMessageBox.question(self, "Incoming Call", f"{caller} is calling you ({call_type}). Accept?")
        accepted = (resp == QMessageBox.StandardButton.Yes)
        self._send_json({'type': 'call_response', 'caller': caller, 'responder': self.username,
                         'accepted': accepted, 'call_type': call_type})
        if accepted:
            self.call_peer     = caller
            self.is_group_call = False
            QTimer.singleShot(200, lambda: self._start_call_internal(caller, call_type, is_group=False))
        self._update_call_buttons()

    def handle_group_call_request(self, room, caller, call_type):
        if self.in_call or caller == self.username:
            return
        resp = QMessageBox.question(self, "Incoming Group Call",
                                    f"{caller} started a {call_type} call in '{room}'. Join?")
        if resp == QMessageBox.StandardButton.Yes:
            self.call_peer     = room
            self.is_group_call = True
            QTimer.singleShot(200, lambda: self._start_call_internal(room, call_type, is_group=True))
        self._update_call_buttons()

    def handle_call_response(self, responder, accepted, call_type):
        if accepted:
            self.display_system_message(f"{responder} accepted the call")
            self.call_peer     = responder
            self.is_group_call = False
            self._start_call_internal(responder, call_type, is_group=False)
        else:
            self.display_system_message(f"{responder} rejected the call")
        self._update_call_buttons()

    def _on_remote_call_ended(self, peer):
        self.display_system_message(f"Call with {peer} ended")
        self._stop_call_internal()
        self._update_call_buttons()

    def end_call(self):
        if not self.in_call:
            return
        if self.is_group_call:
            self._send_json({'type': 'end_call', 'is_group': True, 'room': self.call_peer})
        else:
            self._send_json({'type': 'end_call', 'is_group': False})
        self._stop_call_internal()
        self.display_system_message("You ended the call")
        self._update_call_buttons()

    def _start_call_internal(self, peer, call_type, is_group):
        if self.in_call:
            return
        self.in_call        = True
        self.call_peer      = peer
        self.call_type      = call_type
        self.is_group_call  = is_group
        self.call_stop_event.clear()

        if call_type in ('voice', 'video', 'both'):
            try:
                self.audio_interface  = pyaudio.PyAudio()
                self.audio_stream_in  = self.audio_interface.open(
                    format=AUDIO_FORMAT, channels=AUDIO_CHANNELS, rate=AUDIO_RATE,
                    input=True, frames_per_buffer=AUDIO_CHUNK)
                self.audio_stream_out = self.audio_interface.open(
                    format=AUDIO_FORMAT, channels=AUDIO_CHANNELS, rate=AUDIO_RATE,
                    output=True, frames_per_buffer=AUDIO_CHUNK)
                self.audio_send_thread = threading.Thread(target=self._audio_send_loop, daemon=True)
                self.audio_send_thread.start()
                self.audio_play_thread = threading.Thread(target=self._audio_play_loop, daemon=True)
                self.audio_play_thread.start()
            except Exception as e:
                print("Audio init error:", e)

        if call_type in ('video', 'both'):
            try:
                self.video_capture = cv2.VideoCapture(0)
                self.video_capture.set(cv2.CAP_PROP_FRAME_WIDTH,  VIDEO_WIDTH)
                self.video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, VIDEO_HEIGHT)
            except Exception as e:
                print("Video capture init error:", e)
                self.video_capture = None
            if self.video_capture and self.video_capture.isOpened():
                self.video_send_thread    = threading.Thread(target=self._video_send_loop,    daemon=True)
                self.video_display_thread = threading.Thread(target=self._video_display_loop, daemon=True)
                self.video_send_thread.start()
                self.video_display_thread.start()

        QTimer.singleShot(0, self._open_call_window)
        self._update_call_buttons()

    def _stop_call_internal(self):
        if not self.in_call and not self.call_stop_event.is_set():
            return

        # 1. Signal all media threads to stop
        self.call_stop_event.set()
        self.in_call       = False
        self.call_peer     = None
        self.call_type     = None
        self.is_group_call = False

        # 2. Close call window safely on main thread
        if self.call_window:
            try:
                self.call_window.close()
            except Exception:
                pass
            self.call_window = None

        # 3. Clear queues so blocked threads can exit
        with self.video_display_queue.mutex: self.video_display_queue.queue.clear()
        with self.audio_play_queue.mutex:    self.audio_play_queue.queue.clear()

        # 4. Release PyAudio/cv2 in a background thread to avoid blocking UI
        #    and to avoid race with audio loops still reading
        def _cleanup():
            time.sleep(0.3)  # wait for audio loops to notice stop_event
            try:
                if self.audio_stream_in:
                    try: self.audio_stream_in.stop_stream()
                    except: pass
                    try: self.audio_stream_in.close()
                    except: pass
            except: pass
            try:
                if self.audio_stream_out:
                    try: self.audio_stream_out.stop_stream()
                    except: pass
                    try: self.audio_stream_out.close()
                    except: pass
            except: pass
            try:
                if self.audio_interface:
                    self.audio_interface.terminate()
            except: pass
            try:
                if self.video_capture:
                    self.video_capture.release()
            except: pass
            self.audio_stream_in  = None
            self.audio_stream_out = None
            self.audio_interface  = None
            self.video_capture    = None

        threading.Thread(target=_cleanup, daemon=True).start()

    # ── Media Loops ──────────────────────────────────────────

    def _video_send_loop(self):
        while not self.call_stop_event.is_set() and self.video_capture and self.video_capture.isOpened():
            ret, frame = self.video_capture.read()
            if not ret: time.sleep(0.02); continue
            frame = cv2.resize(frame, (VIDEO_WIDTH, VIDEO_HEIGHT))
            ok, enc = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), VIDEO_QUALITY])
            if not ok: continue
            b64 = base64.b64encode(enc.tobytes()).decode('utf-8')
            payload = {'type': 'call_data', 'data': b64, 'data_type': 'video', 'sender': self.username}
            payload['room' if self.is_group_call else 'peer'] = self.call_peer
            try: self._send_json(payload)
            except Exception as e: print("Video send error:", e); break
            time.sleep(VIDEO_FPS_DELAY)

    def _audio_send_loop(self):
        while not self.call_stop_event.is_set():
            stream = self.audio_stream_in
            if not stream:
                time.sleep(0.02)
                continue
            try:
                data = stream.read(AUDIO_CHUNK, exception_on_overflow=False)
                if self.call_stop_event.is_set():
                    break
                b64  = base64.b64encode(data).decode('utf-8')
                payload = {'type': 'call_data', 'data': b64, 'data_type': 'audio', 'sender': self.username}
                payload['room' if self.is_group_call else 'peer'] = self.call_peer
                self._send_json(payload)
            except Exception as e:
                if self.call_stop_event.is_set():
                    break
                print("Audio send lag/error:", e)
                continue

    def _audio_play_loop(self):
        while not self.call_stop_event.is_set():
            try:
                audio_bytes = self.audio_play_queue.get(timeout=0.3)
            except queue.Empty:
                continue
            if self.call_stop_event.is_set():
                break
            stream = self.audio_stream_out
            if stream:
                try:
                    stream.write(audio_bytes, exception_on_underflow=False)
                except Exception:
                    pass

    def _video_display_loop(self):
        while not self.call_stop_event.is_set():
            try:
                frame_bytes = self.video_display_queue.get(timeout=0.5)
            except queue.Empty: continue
            try:
                img  = Image.open(io.BytesIO(frame_bytes)).convert('RGB')
                data = img.tobytes('raw', 'RGB')
                qimg = QImage(data, img.width, img.height, QImage.Format.Format_RGB888)
                pixmap = QPixmap.fromImage(qimg)
            except Exception as e: print("Display frame decode error:", e); continue
            if self.call_video_label and self.call_window:
                QTimer.singleShot(0, lambda p=pixmap: self._update_video_frame(p))

    def _update_video_frame(self, pixmap):
        try:
            if self.call_video_label and self.in_call:
                self.call_video_label.setPixmap(
                    pixmap.scaled(self.call_video_label.size(),
                                  Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation))
        except Exception: pass

    # ── Call Window ──────────────────────────────────────────

    def _open_call_window(self):
        try:
            peer_info = f"Group: {self.call_peer}" if self.is_group_call else self.call_peer
            self.call_window = QDialog(self)
            self.call_window.setWindowTitle(f"Active Call: {peer_info}")
            self.call_window.setStyleSheet(f"background: {BG_SIDE}; color: {FG_TEXT};")
            self.call_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            self.call_window.rejected.connect(self.end_call)

            lay = QVBoxLayout(self.call_window)
            lay.setContentsMargins(16, 16, 16, 16)
            lay.setSpacing(10)

            tl = QLabel(f"📞  {peer_info}  ({self.call_type.upper()})")
            tl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
            tl.setStyleSheet(f"color: {ACCENT_BLUE}; background: transparent;")
            tl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(tl)

            if self.call_type in ('video', 'both'):
                self.call_window.resize(360, 300)
                self.call_video_label = QLabel("Waiting for video stream...")
                self.call_video_label.setFixedSize(320, 240)
                self.call_video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.call_video_label.setStyleSheet("background: black; color: white; border-radius: 8px;")
                lay.addWidget(self.call_video_label, alignment=Qt.AlignmentFlag.AlignCenter)
            else:
                self.call_window.resize(300, 140)
                self.call_video_label = None
                al = QLabel("🎧  Audio Call Active")
                al.setAlignment(Qt.AlignmentFlag.AlignCenter)
                al.setStyleSheet(f"color: {FG_TEXT}; font-size: 11pt; background: transparent;")
                lay.addWidget(al)

            eb = QPushButton("🛑  End Call")
            eb.setFixedHeight(38)
            eb.setStyleSheet(f"QPushButton {{ background: {ACCENT_RED}; color: white; border-radius: 8px; border: none; font-weight: bold; }} QPushButton:hover {{ background: #c0392b; }}")
            eb.clicked.connect(self.end_call)
            lay.addWidget(eb)

            self.call_window.show()
        except Exception as e:
            print("Call window error:", e)

    # ── Cleanup ──────────────────────────────────────────────

    def closeEvent(self, event):
        try:
            if self.in_call:       self.end_call()
            if self.is_recording:  self.is_recording = False
            if self.net_worker:    self.net_worker.stop()
            if self.sock:
                try: self.sock.close()
                except: pass
        except: pass
        event.accept()


# ── Entry Point ──────────────────────────────────────────────
if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = SimplifiedClient()
    window.show()
    sys.exit(app.exec())
