import sys
import os
import subprocess
import socket
import json
import time
import threading

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QMessageBox, QTextEdit, QCheckBox
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl

SOCKET_PATH = '/tmp/ki_shell.sock'
THISDIR = os.path.dirname(os.path.abspath(__file__))

def debug_log(msg):
    print(f"[GhostShell GUI DEBUG] {msg}")

class GhostShellGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ghost in the Shell – Human-in-the-Loop Docker Terminal")
        self.setGeometry(120, 60, 1200, 850)
        main = QWidget()
        v = QVBoxLayout(main)

        # Debug output widget
        self.debug_output = QTextEdit()
        self.debug_output.setReadOnly(True)
        self.debug_output.setMaximumHeight(90)
        v.addWidget(self.debug_output)

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
        self.allow_all_switch = QCheckBox("Allow All (KI darf direkt tippen)")
        self.allow_all_switch.stateChanged.connect(self.toggle_allow_all)
        h_top.addWidget(self.allow_all_switch)
        self.pause_switch = QCheckBox("Pausiert (KI-Eingaben blockiert)")
        self.pause_switch.stateChanged.connect(self.toggle_pause)
        h_top.addWidget(self.pause_switch)
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

        self.current_container = None
        self.update_ui()

        # Allow/pause logic
        self.allow_all = False
        self.paused = False

        # Backend process
        self.backend_proc = None
        self.backend_image = None

        # Socket server for KI suggestions
        self.socket_server_thread = threading.Thread(target=self.socket_server, daemon=True)
        self.socket_server_thread.start()

    def debug(self, msg):
        self.debug_output.append(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def closeEvent(self, event):
        debug_log("GUI closing, shutting down backend and socket server.")
        if self.backend_proc:
            self.backend_proc.terminate()
        super().closeEvent(event)

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
        backend_py = os.path.join(THISDIR, "terminal_backend.py")
        env = os.environ.copy()
        env["GHOSTSHELL_IMAGE"] = image
        env["GHOSTSHELL_CONTAINER"] = "ghostshell_main"
        env["GHOSTSHELL_PORT"] = "8765"
        try:
            self.backend_proc = subprocess.Popen([sys.executable, backend_py], env=env)
            debug_log(f"Started backend for image: {image}")
            self.debug(f"Backend gestartet für: {image}")
            time.sleep(1.2)
            self.current_container = "ghostshell_main"
        except Exception as e:
            debug_log(f"Fehler beim Start des Backends: {e}")
            self.debug(f"Fehler beim Start des Backends: {e}")
            self.current_container = None
        self.update_ui()

    def stop_container(self):
        if self.backend_proc:
            try:
                self.backend_proc.terminate()
                debug_log("Backend terminated.")
                self.debug("Backend gestoppt.")
            except Exception as e:
                debug_log(f"Fehler beim Stoppen des Backends: {e}")
                self.debug(f"Fehler beim Stoppen: {e}")
            self.backend_proc = None
        self.current_container = None
        self.update_ui()

    def toggle_allow_all(self, state):
        self.allow_all = bool(state)
        self.debug(f"Allow All: {'aktiviert' if self.allow_all else 'deaktiviert'}")

    def toggle_pause(self, state):
        self.paused = bool(state)
        self.debug(f"Pausiert: {'ja' if self.paused else 'nein'}")

    def socket_server(self):
        # Socket für LLM/Skill: empfängt KI-Vorschläge und zeigt sie im Terminal
        if os.path.exists(SOCKET_PATH):
            try:
                os.remove(SOCKET_PATH)
            except Exception:
                pass
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(SOCKET_PATH)
        os.chmod(SOCKET_PATH, 0o600)
        s.listen(5)
        while True:
            try:
                conn, _ = s.accept()
                data = conn.recv(4096)
                if data:
                    req = json.loads(data.decode())
                    cmd = req.get("command")
                    if cmd:
                        self.debug(f"KI Vorschlag: {cmd}")
                        if self.paused:
                            self.debug("Terminal PAUSIERT, Befehl ignoriert.")
                            continue
                        if self.allow_all:
                            # Sofort ins Terminal tippen
                            self.web.page().runJavaScript(
                                f"window.termWrite({json.dumps(cmd + '\\n')})"
                            )
                        else:
                            # Zeige als Vorschlag, User kann übernehmen
                            self.web.page().runJavaScript(
                                f"window.setKICmd({json.dumps(cmd)})"
                            )
                conn.sendall(json.dumps({"status": "ok"}).encode())
                conn.close()
            except Exception as e:
                debug_log(f"Fehler im Socket-Server: {e}")

if __name__ == "__main__":
    debug_log("GUI starting up")
    app = QApplication(sys.argv)
    win = GhostShellGUI()
    win.show()
    app.exec()
