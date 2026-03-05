from firebase_service import save_chat_message, save_private_message
import socket
import threading
import json
import sys
from datetime import datetime, timezone

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QListWidget, QPushButton, QTextEdit, QLineEdit,
    QFrame, QSplitter
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QFont


# ================= SERVER CORE ================= #


class ChatServerCore:
    def __init__(self, host='0.0.0.0', port=5555, log_callback=None, update_users_callback=None, update_calls_callback=None):
        self.host = host
        self.port = port
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)


        self.clients = {}
        self.clients_lock = threading.Lock()


        self.rooms = {'General': []}
        self.rooms_lock = threading.Lock()


        self.active_calls = {}


        self.log_callback = log_callback
        self.update_users_callback = update_users_callback
        self.update_calls_callback = update_calls_callback


    def log(self, msg):
        print(msg)
        if self.log_callback:
            self.log_callback(msg)


    def start(self):
        self.server_sock.bind((self.host, self.port))
        self.server_sock.listen()
        self.log(f"[{self.timestamp()}] Server started on {self.host}:{self.port}")


        while True:
            client_sock, addr = self.server_sock.accept()
            threading.Thread(
                target=self.handle_client,
                args=(client_sock, addr),
                daemon=True
            ).start()


    def timestamp(self):
        return datetime.now().strftime('%H:%M:%S')


    # ================= NETWORK ================= #


    def send_json(self, sock, data):
        try:
            sock.send((json.dumps(data) + "\n").encode())
        except:
            pass


    def send_to(self, username, data):
        with self.clients_lock:
            sock = self.clients.get(username)
        if sock:
            self.send_json(sock, data)


    def broadcast(self, data, exclude=None):
        with self.clients_lock:
            for user, sock in list(self.clients.items()):
                if user == exclude:
                    continue
                self.send_json(sock, data)


    # ================= CLIENT HANDLER ================= #


    def handle_client(self, sock, addr):
        username = None
        try:
            username = sock.recv(4096).decode().strip()


            with self.clients_lock:
                if username in self.clients:
                    self.send_json(sock, {'type':'error','message':'Username taken'})
                    sock.close()
                    return
                self.clients[username] = sock


            with self.rooms_lock:
                self.rooms['General'].append(username)


            self.log(f"[{self.timestamp()}] {username} connected from {addr}")
            self.update_users()


            # Báo cho client về danh sách phòng hiện tại
            self.send_json(sock, {'type': 'welcome', 'message': f'Welcome {username}!', 'rooms': list(self.rooms.keys())})


            buffer = ""
            decoder = json.JSONDecoder()


            while True:
                data = sock.recv(1024*1024)
                if not data:
                    break


                buffer += data.decode(errors='ignore')
                while buffer:
                    buffer = buffer.lstrip()
                    try:
                        obj, idx = decoder.raw_decode(buffer)
                        buffer = buffer[idx:]
                        self.process_message(username, obj)
                    except:
                        break


        except Exception as e:
            self.log(f"Error handling {username}: {e}")
        finally:
            self.disconnect(username)


    # ================= MESSAGE PROCESS & ROUTING ================= #

    
    def process_message(self, sender, msg):
        mtype = msg.get('type')
       
        # Đóng dấu danh tính thật của người gửi để các Client khác nhận diện
        msg['sender'] = sender

        timestamp = datetime.now(timezone.utc).isoformat()
        msg['timestamp'] = timestamp
        # ------------------------------------------------------------------
        # PHẦN 1: SERVER THEO DÕI VÀ HIỂN THỊ LOG (Monitor Only)
        # ------------------------------------------------------------------
        if mtype == 'chat':
            room = msg.get('room', 'General')
            content = msg.get('message')

    # Tạo timestamp chuẩn UTC để lưu Firebase
           

            self.log(f"[{self.timestamp()}] {sender} -> {room}: {content}")

            try:
                save_chat_message(
                    sender=sender,
                    content=content,
                    room=room,
                    receiver=None,
                    msg_type="chat",
                    timestamp=timestamp   # 👈 thêm dòng này
        )
            except Exception as e:
             self.log(f"Firebase error: {e}")
    
     
           
        elif mtype == 'private':

            recipient = msg.get('recipient')
            content = msg.get('message')

            self.log(f"[{self.timestamp()}] {sender} -> {recipient} (private): {content}")

            try:
                # Lưu vào collection private_chats riêng
                save_private_message(
                    user1=sender,
                    user2=recipient,
                    sender=sender,
                    content=content
                )

            except Exception as e:
                self.log(f"Firebase error: {e}")
           
        elif mtype == 'file':
            filename = msg.get('filename')
            filedata = msg.get('filedata')
            filetype = msg.get('filetype')
            recipient = msg.get('recipient')
            room = msg.get('room')

            self.log(f"[{self.timestamp()}] {sender} sent file: {filename}")

            try:
                if recipient:
                    save_private_message(
                        user1=sender,
                        user2=recipient,
                        sender=sender,
                        content=None,
                        filename=filename,
                        filedata=filedata,
                        filetype=filetype
                    )
                else:
                    save_chat_message(
                        sender=sender,
                        content=None,
                        room=room,
                        receiver=None,
                        msg_type="file",
                        timestamp=timestamp,
                        filename=filename,
                        filedata=filedata,
                        filetype=filetype
                    )
            except Exception as e:
                self.log(f"Firebase error: {e}")
               
        elif mtype == 'call_request':
            self.log(f"[{self.timestamp()}] {sender} is calling {msg.get('recipient')} ({msg.get('call_type', 'unknown')})")
           
        elif mtype == 'group_call_request':
            room = msg.get('room', 'Unknown')
            self.log(f"[{self.timestamp()}] {sender} started group call in {room}")
            self.active_calls[room] = [sender]
            self.update_calls()
           
        elif mtype == 'end_call':
            self.log(f"[{self.timestamp()}] {sender} ended call")
            self.active_calls.clear() # Đơn giản hóa trạng thái UI
            self.update_calls()
           
        elif mtype == 'create_room':
            room_name = msg.get('room_name')
            if room_name:
                self.log(f"[{self.timestamp()}] {sender} created room: {room_name}")
                with self.rooms_lock:
                    if room_name not in self.rooms:
                        self.rooms[room_name] = []
                self.broadcast({'type': 'room_created', 'room_name': room_name})
            return
           
        # Các mtype như 'call_data', 'call_response' Server sẽ phớt lờ việc log để tránh làm tràn màn hình Console
       


        # ------------------------------------------------------------------
        # PHẦN 2: UNIVERSAL ROUTING (Cho Client tương tác tự do)
        # Server đóng vai trò như Router, chuyển tiếp MỌI THỨ mà Client gửi
        # ------------------------------------------------------------------
        if 'recipient' in msg:
            # Nếu gói tin có khóa 'recipient' -> Định tuyến cá nhân 1-1
            self.send_to(msg['recipient'], msg)
        elif 'peer' in msg:
            # Private call data (audio/video) -> Gửi trực tiếp cho peer
            self.send_to(msg['peer'], msg)
        elif 'caller' in msg and mtype == 'call_response':
            # Call response -> Gửi về cho người gọi
            self.send_to(msg['caller'], msg)
        elif 'room' in msg and mtype == 'call_data':
            # Group call data -> Gửi tới tất cả trong room trừ sender
            self.broadcast(msg, exclude=sender)
        else:
            # Các trường hợp còn lại (Chat Group, Group Call request...) -> Gửi tới những người khác
            self.broadcast(msg, exclude=sender)




    # ================= DISCONNECT ================= #


    def disconnect(self, username):
        if not username:
            return


        with self.clients_lock:
            sock = self.clients.pop(username, None)
            if sock:
                sock.close()


        with self.rooms_lock:
            for room in self.rooms.values():
                if username in room:
                    room.remove(username)


        self.log(f"[{self.timestamp()}] {username} disconnected")
        self.update_users()


    def update_users(self):
        users = list(self.clients.keys())
        if self.update_users_callback:
            self.update_users_callback(users)
           
        # Gửi chuẩn cấu trúc 'client_list' xuống Client để UI của Client cập nhật danh sách
        with self.clients_lock:
            for sock in self.clients.values():
                self.send_json(sock, {
                    'type': 'client_list',
                    'clients': users
                })


    def update_calls(self):
        if self.update_calls_callback:
            self.update_calls_callback(self.active_calls)




# ================= SIGNAL BRIDGE ================= #
# Bridges server callbacks (called from background threads) to Qt signals

class ServerSignals(QObject):
    log_signal          = pyqtSignal(str)
    users_signal        = pyqtSignal(list)
    calls_signal        = pyqtSignal(dict)


# ================= ADMIN GUI ================= #


class ServerAdminGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Chat Server Admin Panel")
        self.resize(1100, 700)
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #1c1c1c; color: #e0e0e0; font-family: 'Segoe UI'; font-size: 10pt; }
            QListWidget { background: #252526; border: 1px solid #333; border-radius: 4px; }
            QListWidget::item { padding: 5px 8px; }
            QListWidget::item:selected { background: #007ACC; color: white; }
            QTextEdit { background: #1e1e1e; color: #d4d4d4; border: 1px solid #333; border-radius: 4px; font-family: 'Consolas', monospace; font-size: 9pt; }
            QLineEdit { background: #2d2d2d; color: #e0e0e0; border: 1px solid #444; border-radius: 4px; padding: 4px 8px; }
            QPushButton { background: #007ACC; color: white; border: none; border-radius: 4px; padding: 6px 14px; }
            QPushButton:hover { background: #1a8fdb; }
            QPushButton#kick { background: #e74856; }
            QPushButton#kick:hover { background: #c0392b; }
            QSplitter::handle { background: #333; }
            QLabel#section { color: #007ACC; font-weight: bold; font-size: 10pt; }
        """)

        self.signals = ServerSignals()
        self.signals.log_signal.connect(self._append_log)
        self.signals.users_signal.connect(self._update_users)
        self.signals.calls_signal.connect(self._update_calls)

        self._build_ui()
        self._start_server()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_lay = QHBoxLayout(central)
        root_lay.setContentsMargins(8, 8, 8, 8)
        root_lay.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left panel ──────────────────────────
        left = QWidget()
        left.setFixedWidth(280)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 6, 0)
        ll.setSpacing(6)

        ul = QLabel("Online Users")
        ul.setObjectName("section")
        ll.addWidget(ul)

        self.user_list = QListWidget()
        ll.addWidget(self.user_list, 2)

        kick_btn = QPushButton("Kick Selected User")
        kick_btn.setObjectName("kick")
        kick_btn.clicked.connect(self.kick_user)
        ll.addWidget(kick_btn)

        cl = QLabel("Active Calls")
        cl.setObjectName("section")
        ll.addWidget(cl)

        self.call_list = QListWidget()
        ll.addWidget(self.call_list, 1)

        splitter.addWidget(left)

        # ── Right panel ─────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(6, 0, 0, 0)
        rl.setSpacing(6)

        log_lbl = QLabel("Server Logs")
        log_lbl.setObjectName("section")
        rl.addWidget(log_lbl)

        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        rl.addWidget(self.log_display, 1)

        # Global message row
        msg_row = QHBoxLayout()
        msg_row.setSpacing(6)
        self.msg_entry = QLineEdit()
        self.msg_entry.setPlaceholderText("Broadcast a global message...")
        self.msg_entry.returnPressed.connect(self.send_global)
        send_btn = QPushButton("Send Global")
        send_btn.clicked.connect(self.send_global)
        msg_row.addWidget(self.msg_entry, 1)
        msg_row.addWidget(send_btn)
        rl.addLayout(msg_row)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        root_lay.addWidget(splitter)

    def _start_server(self):
        self.server = ChatServerCore(
            log_callback=lambda msg: self.signals.log_signal.emit(msg),
            update_users_callback=lambda users: self.signals.users_signal.emit(users),
            update_calls_callback=lambda calls: self.signals.calls_signal.emit(calls),
        )
        threading.Thread(target=self.server.start, daemon=True).start()

    # ── Slot handlers (always on main thread via signals) ──

    def _append_log(self, msg):
        self.log_display.append(msg)
        self.log_display.verticalScrollBar().setValue(
            self.log_display.verticalScrollBar().maximum()
        )

    def _update_users(self, users):
        self.user_list.clear()
        for u in users:
            self.user_list.addItem(u)

    def _update_calls(self, calls):
        self.call_list.clear()
        for room, users in calls.items():
            self.call_list.addItem(f"{room}: {users}")

    def send_global(self):
        msg = self.msg_entry.text().strip()
        if not msg:
            return
        payload = {
            'type': 'chat',
            'sender': '[ADMIN]',
            'message': msg,
            'room': 'General',
            'timestamp': datetime.now().strftime('%H:%M:%S')
        }
        self.server.broadcast(payload)
        self._append_log(f"[SERVER -> GLOBAL]: {msg}")
        self.msg_entry.clear()

    def kick_user(self):
        item = self.user_list.currentItem()
        if not item:
            return
        user = item.text()
        self.server.disconnect(user)
        self._append_log(f"[ADMIN] Kicked {user}")


# ================= RUN ================= #


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = ServerAdminGUI()
    window.show()
    sys.exit(app.exec())



