import sys
import os
import subprocess
import socket
import json
import time

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QMessageBox
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl, Qt, QTimer

SOCKET_PATH = '/tmp/ki_shell.sock'
THISDIR = os.path.dirname(os.path.abspath(__file__))

class SuggestionListener(QTimer):
    def __init__(self, gui):
        super().__init__()
        self.gui = gui
        self.setInterval(400)
        self.timeout.connect(self.check)
        self.sock = None
        self.start()
    def check(self):
        if self.sock is None:
            try:
                if os.path.exists(SOCKET_PATH):
                    self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    self.sock.connect(SOCKET_PATH)
            except: self.sock = None
        if self.sock:
            try:
                data = self.sock.recv(4096)
                if data:
                    msg = json.loads(data.decode())
                    if msg.get("type") == "suggestion":
                        self.gui.show_ki_suggestion(msg.get("command"))
            except: pass

class GhostShellGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ghost in the Shell – Human-in-the-Loop Docker Terminal")
        self.setGeometry(120, 60, 1150, 800)
        main = QWidget()
        v = QVBoxLayout(main)

        # --- Docker controls ---
        h_top = QHBoxLayout()
        self.image_label = QLabel("Docker-Image:")
        h_top.addWidget(self.image_label)
        self.image_combo = QComboBox()
        self.image_combo.addItems(["ubuntu:24.04", "python:3.11-slim", "debian:bookworm", "alpine:latest"])
        self.image_combo.setEditable(True)
        h_top.addWidget(self.image_combo)
        self.start_btn = QPushButton("Container starten")
        self.start_btn.clicked.connect(self.start_container)
        h_top.addWidget(self.start_btn)
        self.stop_btn = QPushButton("Container stoppen")
        self.stop_btn.clicked.connect(self.stop_container)
        h_top.addWidget(self.stop_btn)
        h_top.addStretch(1)
        v.addLayout(h_top)
        v.addSpacing(8)
        self.container_status = QLabel("Container: [Gestoppt]")
        v.addWidget(self.container_status)

        # --- Webview terminal ---
        self.web = QWebEngineView()
        frontend_path = os.path.join(THISDIR, "frontend", "index.html")
        self.web.setUrl(QUrl.fromLocalFile(frontend_path))
        v.addWidget(self.web, 4)

        self.setCentralWidget(main)
        self.suggestion_listener = SuggestionListener(self)
        self.current_container = None
        self.update_ui()
        # Backend start
        self.backend_proc = None
        self.backend_image = None

    def show_ki_suggestion(self, cmd):
        self.web.page().runJavaScript(f"window.setKICmd({json.dumps(cmd)})")

    def update_ui(self):
        if self.current_container:
            self.container_status.setText(
                f"Container: Läuft ({self.current_container})"
            )
        else:
            self.container_status.setText("Container: [Gestoppt]")

    def start_container(self):
        image = self.image_combo.currentText().strip()
        if not image:
            QMessageBox.warning(self, "Fehler", "Bitte Docker-Image wählen oder eingeben.")
            return
        self.backend_image = image
        # Start backend subprocess with env vars
        backend_py = os.path.join(os.path.dirname(__file__), "terminal_backend.py")
        env = os.environ.copy()
        env["GHOSTSHELL_IMAGE"] = image
        env["GHOSTSHELL_CONTAINER"] = "ghostshell_main"
        self.backend_proc = subprocess.Popen([sys.executable, backend_py], env=env)
        time.sleep(1.5)
        self.current_container = "ghostshell_main"
        self.update_ui()

    def stop_container(self):
        if self.backend_proc:
            self.backend_proc.terminate()
            self.backend_proc = None
        self.current_container = None
        self.update_ui()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = GhostShellGUI()
    win.show()
    app.exec()
