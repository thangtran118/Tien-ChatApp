import subprocess
import sys
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFrame, QMessageBox
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect
from PyQt6.QtGui import QFont, QColor, QPalette
from firebase_client import firebase_login, firebase_register


class LoginWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CHAT LOGIN")
        self.setFixedSize(440, 520)
        self.setStyleSheet("background-color: #0f0f1a;")
        self._build_ui()
        self._center_window()

    def _center_window(self):
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(35, 40, 35, 40)
        layout.setSpacing(0)

        # Card frame
        card = QFrame(self)
        card.setStyleSheet("""
            QFrame {
                background-color: #151528;
                border: 2px solid #6c5ce7;
                border-radius: 12px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(40, 35, 40, 35)
        card_layout.setSpacing(0)

        # Title
        title = QLabel("💬 CHAT LOGIN")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        title.setStyleSheet("color: #00f7ff; border: none; background: transparent;")
        card_layout.addWidget(title)

        subtitle = QLabel("Enter your account...")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setFont(QFont("Segoe UI", 10))
        subtitle.setStyleSheet("color: #aaaaaa; border: none; background: transparent; margin-bottom: 20px;")
        card_layout.addWidget(subtitle)
        card_layout.addSpacing(15)

        # Email label
        email_label = QLabel("EMAIL")
        email_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        email_label.setStyleSheet("color: #6c5ce7; border: none; background: transparent;")
        card_layout.addWidget(email_label)
        card_layout.addSpacing(5)

        # Email input
        self.email_entry = QLineEdit()
        self.email_entry.setPlaceholderText("your@email.com")
        self.email_entry.setFont(QFont("Consolas", 11))
        self.email_entry.setFixedHeight(42)
        self.email_entry.setStyleSheet("""
            QLineEdit {
                background-color: #1f1f35;
                color: #00f7ff;
                border: 1px solid #2d2d50;
                border-radius: 6px;
                padding: 0 12px;
            }
            QLineEdit:focus {
                border: 1px solid #6c5ce7;
            }
        """)
        card_layout.addWidget(self.email_entry)
        card_layout.addSpacing(16)

        # Password label
        pwd_label = QLabel("PASSWORD")
        pwd_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        pwd_label.setStyleSheet("color: #6c5ce7; border: none; background: transparent;")
        card_layout.addWidget(pwd_label)
        card_layout.addSpacing(5)

        # Password input
        self.password_entry = QLineEdit()
        self.password_entry.setPlaceholderText("••••••••")
        self.password_entry.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_entry.setFont(QFont("Consolas", 11))
        self.password_entry.setFixedHeight(42)
        self.password_entry.setStyleSheet("""
            QLineEdit {
                background-color: #1f1f35;
                color: #00f7ff;
                border: 1px solid #2d2d50;
                border-radius: 6px;
                padding: 0 12px;
            }
            QLineEdit:focus {
                border: 1px solid #6c5ce7;
            }
        """)
        self.password_entry.returnPressed.connect(self.handle_login)
        card_layout.addWidget(self.password_entry)
        card_layout.addSpacing(24)

        # Login button
        self.login_btn = QPushButton("LOGIN")
        self.login_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.login_btn.setFixedHeight(44)
        self.login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c5ce7;
                color: white;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #7d6bff;
            }
            QPushButton:pressed {
                background-color: #4834d4;
            }
        """)
        self.login_btn.clicked.connect(self.handle_login)
        card_layout.addWidget(self.login_btn)
        card_layout.addSpacing(10)

        # Register button
        self.register_btn = QPushButton("REGISTER")
        self.register_btn.setFont(QFont("Segoe UI", 10))
        self.register_btn.setFixedHeight(42)
        self.register_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.register_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #00f7ff;
                border: 1px solid #00f7ff;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #00f7ff;
                color: #151528;
            }
            QPushButton:pressed {
                background-color: #00c3cc;
            }
        """)
        self.register_btn.clicked.connect(self.handle_register)
        card_layout.addWidget(self.register_btn)

        layout.addWidget(card)

    def handle_login(self):
        email = self.email_entry.text().strip()
        password = self.password_entry.text().strip()

        if not email or not password:
            QMessageBox.warning(self, "Missing", "Please enter email and password")
            return

        try:
            user = firebase_login(email, password)
            id_token = user["idToken"]
            user_email = user["email"]

            self.close()

            subprocess.Popen([
                sys.executable,
                "Chat_Client.py",
                user_email,
                id_token
            ])

        except Exception as e:
            QMessageBox.critical(self, "Login Failed", str(e))

    def handle_register(self):
        email = self.email_entry.text().strip()
        password = self.password_entry.text().strip()

        if not email or not password:
            QMessageBox.warning(self, "Missing", "Please enter email and password")
            return

        try:
            firebase_register(email, password)
            QMessageBox.information(self, "Success", "Register OK. You can login now.")
        except Exception as e:
            QMessageBox.critical(self, "Register Failed", str(e))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = LoginWindow()
    window.show()
    sys.exit(app.exec())

