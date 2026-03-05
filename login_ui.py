import subprocess
import sys
import tkinter as tk
from tkinter import messagebox
from firebase_client import firebase_login, firebase_register




# ================== FUNCTIONS ================== #


def handle_login():
    email = email_entry.get().strip()
    password = password_entry.get().strip()


    if not email or not password:
        messagebox.showwarning("Missing", "Please enter email and password")
        return


    try:
        user = firebase_login(email, password)


        global ID_TOKEN, USER_EMAIL
        ID_TOKEN = user["idToken"]
        USER_EMAIL = user["email"]


        root.destroy()


        subprocess.Popen([
            sys.executable,
            "chat_client.py",
            USER_EMAIL,
            ID_TOKEN
        ])


    except Exception as e:
        messagebox.showerror("Login failed", str(e))




def handle_register():
    email = email_entry.get().strip()
    password = password_entry.get().strip()


    if not email or not password:
        messagebox.showwarning("Missing", "Please enter email and password")
        return


    try:
        firebase_register(email, password)
        messagebox.showinfo("Success", "Register OK. You can login now.")
    except Exception as e:
        messagebox.showerror("Register failed", str(e))




# ================== UI ================== #


root = tk.Tk()
root.title("CHAT LOGIN")
root.geometry("440x500")
root.configure(bg="#0f0f1a")
root.resizable(False, False)
root.eval('tk::PlaceWindow . center')


# Card container
card = tk.Frame(root, bg="#151528", highlightbackground="#6c5ce7",
                highlightthickness=2)
card.place(relx=0.5, rely=0.5, anchor="center",
           width=370, height=420)


# Title
tk.Label(
    card,
    text="⚔ CHAT LOGIN ⚔",
    font=("Segoe UI", 20, "bold"),
    fg="#00f7ff",
    bg="#151528"
).pack(pady=(35, 10))


tk.Label(
    card,
    text="Enter your account...",
    font=("Segoe UI", 10),
    fg="#aaaaaa",
    bg="#151528"
).pack(pady=(0, 25))




# ===== Email =====
tk.Label(
    card,
    text="EMAIL",
    font=("Segoe UI", 9, "bold"),
    fg="#6c5ce7",
    bg="#151528",
    anchor="w"
).pack(fill="x", padx=45)


email_entry = tk.Entry(
    card,
    font=("Consolas", 11),
    bg="#1f1f35",
    fg="#00f7ff",
    insertbackground="#00f7ff",
    relief="flat"
)
email_entry.pack(padx=45, pady=(5, 18), ipady=8, fill="x")




# ===== Password =====
tk.Label(
    card,
    text="PASSWORD",
    font=("Segoe UI", 9, "bold"),
    fg="#6c5ce7",
    bg="#151528",
    anchor="w"
).pack(fill="x", padx=45)


password_entry = tk.Entry(
    card,
    show="*",
    font=("Consolas", 11),
    bg="#1f1f35",
    fg="#00f7ff",
    insertbackground="#00f7ff",
    relief="flat"
)
password_entry.pack(padx=45, pady=(5, 25), ipady=8, fill="x")




# ===== Buttons =====
login_btn = tk.Button(
    card,
    text="LOGIN",
    font=("Segoe UI", 11, "bold"),
    bg="#6c5ce7",
    fg="white",
    activebackground="#4834d4",
    activeforeground="white",
    relief="flat",
    command=handle_login
)
login_btn.pack(padx=45, ipady=9, fill="x")


register_btn = tk.Button(
    card,
    text="REGISTER",
    font=("Segoe UI", 10),
    bg="#00f7ff",
    fg="#151528",
    activebackground="#00c3cc",
    activeforeground="#151528",
    relief="flat",
    command=handle_register
)
register_btn.pack(padx=45, pady=12, ipady=8, fill="x")




# ===== Hover Effects =====
def on_enter(e, btn, color):
    btn['background'] = color


def on_leave(e, btn, color):
    btn['background'] = color




login_btn.bind("<Enter>", lambda e: on_enter(e, login_btn, "#7d6bff"))
login_btn.bind("<Leave>", lambda e: on_leave(e, login_btn, "#6c5ce7"))


register_btn.bind("<Enter>", lambda e: on_enter(e, register_btn, "#00d2d8"))
register_btn.bind("<Leave>", lambda e: on_leave(e, register_btn, "#00f7ff"))


root.mainloop()

