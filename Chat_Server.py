from firebase_service import save_chat_message, save_private_message
import socket
import threading
import json
from datetime import datetime, timezone
import tkinter as tk
from tkinter import scrolledtext, messagebox, simpledialog
from tkinter import ttk


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
            recipient = msg.get('recipient')
            room = msg.get('room')

            self.log(f"[{self.timestamp()}] {sender} sent file: {filename}")

            try:
                save_chat_message(
                    sender=sender,
                    content=filename,
                    room=room,
                    receiver=recipient,
                    msg_type="file",
                    timestamp=timestamp
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




# ================= ADMIN GUI ================= #


class ServerAdminGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("🔥 Chat Server Admin Panel")
        self.root.geometry("1100x700")


        main = tk.PanedWindow(root, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True)


        # ===== LEFT PANEL =====
        left = tk.Frame(main)
        main.add(left, width=300)


        tk.Label(left, text="Online Users", font=('Segoe UI', 12, 'bold')).pack(pady=5)
        self.user_list = tk.Listbox(left)
        self.user_list.pack(fill=tk.BOTH, expand=True, padx=5)


        tk.Button(left, text="Kick User", command=self.kick_user).pack(pady=5)


        tk.Label(left, text="Active Calls", font=('Segoe UI', 12, 'bold')).pack(pady=5)
        self.call_list = tk.Listbox(left)
        self.call_list.pack(fill=tk.BOTH, expand=True, padx=5)


        # ===== RIGHT PANEL =====
        right = tk.Frame(main)
        main.add(right)


        tk.Label(right, text="Server Logs", font=('Segoe UI', 12, 'bold')).pack()


        self.log_display = scrolledtext.ScrolledText(right, state=tk.DISABLED)
        self.log_display.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)


        bottom = tk.Frame(right)
        bottom.pack(fill=tk.X)


        self.msg_entry = tk.Entry(bottom)
        self.msg_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)


        tk.Button(bottom, text="Send Global Message", command=self.send_global).pack(side=tk.RIGHT)


        # Start server core
        self.server = ChatServerCore(
            log_callback=self.add_log,
            update_users_callback=self.update_users,
            update_calls_callback=self.update_calls
        )


        threading.Thread(target=self.server.start, daemon=True).start()


    def add_log(self, msg):
        self.root.after(0, lambda: self._append_log(msg))


    def _append_log(self, msg):
        self.log_display.config(state=tk.NORMAL)
        self.log_display.insert(tk.END, msg + "\n")
        self.log_display.config(state=tk.DISABLED)
        self.log_display.see(tk.END)


    def update_users(self, users):
        self.root.after(0, lambda: self._update_users(users))


    def _update_users(self, users):
        self.user_list.delete(0, tk.END)
        for u in users:
            self.user_list.insert(tk.END, u)


    def update_calls(self, calls):
        self.root.after(0, lambda: self._update_calls(calls))


    def _update_calls(self, calls):
        self.call_list.delete(0, tk.END)
        for room, users in calls.items():
            self.call_list.insert(tk.END, f"{room}: {users}")


    def send_global(self):
        msg = self.msg_entry.get().strip()
        if not msg:
            return


        payload = {
            'type':'chat',
            'sender':'[ADMIN SYSTEM]',
            'message':msg,
            'room':'General',
            'timestamp':datetime.now().strftime('%H:%M:%S')
        }


        self.server.broadcast(payload)
        self.add_log(f"[SERVER -> GLOBAL]: {msg}")
        self.msg_entry.delete(0, tk.END)


    def kick_user(self):
        selection = self.user_list.curselection()
        if not selection:
            return


        user = self.user_list.get(selection[0])
        self.server.disconnect(user)
        self.add_log(f"[ADMIN] Kicked {user}")




# ================= RUN ================= #


if __name__ == "__main__":
    root = tk.Tk()
    app = ServerAdminGUI(root)
    root.mainloop()



