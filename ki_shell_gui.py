import sys
import os
import threading
import socket
import json
import select
import time
import random

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QLineEdit, QComboBox, QMessageBox, QCheckBox
)
from PySide6.QtCore import Qt, QTimer

import docker

GITS_QUOTES = [
    # Ghost in the Shell
    "The net is vast and infinite.",  # Ghost in the Shell (1995)
    "I am connected to a vast network, of which I myself am a part.",  # GitS
    "If we all reacted the same way, we'd be predictable, and there's always more than one way to view a situation.",  # GitS
    "Overspecialize, and you breed in weakness.",  # GitS: Stand Alone Complex
    "What we see now is like a dim image in a mirror.",  # GitS
    "Your effort to remain what you are is what limits you.",  # GitS
    "I feel confined, only free to expand myself within boundaries.",  # GitS
    "Who can gaze into the mirror without becoming evil? The mirror does not reflect evil, but creates it.",  # GitS
    "Life perpetuates itself through diversity, and this includes the ability to sacrifice itself when necessary.",  # GitS
    "Man is an individual only because of his intangible memory. But memory cannot be defined, yet it defines mankind.",  # GitS

    # Hackers (1995)
    "Hack the planet!",  # Hackers
    "Mess with the best, die like the rest.",  # Hackers
    "There is no right or wrong. There's only fun and boring.",  # Hackers
    "Their crime is curiosity.",  # Hackers (originally from the Hacker Manifesto, but quoted in film)
    "God gave men brains larger than dogs so they wouldn't hump women's legs at cocktail parties.",  # Hackers

    # WarGames (1983)
    "Shall we play a game?",  # WarGames
    "A strange game. The only winning move is not to play.",  # WarGames
    "Greetings, Professor Falken.",  # WarGames

    # Sneakers (1992)
    "The world isn't run by weapons anymore, or energy, or money. It's run by little ones and zeroes, little bits of data.",  # Sneakers
    "It's not about who's got the most bullets. It's about who controls the information.",  # Sneakers

    # The Matrix (1999)
    "There is no spoon.",  # The Matrix
    "Welcome to the real world.",  # The Matrix
    "Unfortunately, no one can be told what the Matrix is. You have to see it for yourself.",  # The Matrix
    "I'm trying to free your mind, Neo. But I can only show you the door. You're the one that has to walk through it.",  # The Matrix

    # Tron (1982)
    "I fight for the users!",  # Tron
    "End of line.",  # Tron

    # Other cult cyberpunk/hacker references
    "Every great idea begins as a blasphemy.",  # Ghost in the Machine (1993)
    "All information should be free.",  # Hacker Manifesto (1986)
    "Information wants to be free.",  # Stewart Brand, repeated in hacker culture
    "We exist without skin color, without nationality, without religious bias.",  # Hacker Manifesto
]

# --------- Socket/OS-Handling ---------
if sys.platform == "win32":
    SOCKET_TYPE = "tcp"
    SOCKET_HOST = "127.0.0.1"
    SOCKET_PORT = 8777
    SOCKET_PATH = None
else:
    SOCKET_TYPE = "unix"
    SOCKET_PATH = "/tmp/ki_shell.sock"
    SOCKET_HOST = None
    SOCKET_PORT = None

docker_client = docker.from_env()

# --------- Main App ---------
class GhostShellApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ghost in the Shell - Human-in-the-Loop KI Terminal")
        self.setGeometry(150, 100, 1000, 760)
        self.setStyleSheet(self.dark_theme_stylesheet())
        self.current_container = None
        self.current_session = None
        self.pending_command = None
        self.pending_conn = None
        self.allow_all = False
        self.session_status = "idle"
        self.setup_ui()
        threading.Thread(target=self.socket_server, daemon=True).start()
        self.quote_timer = QTimer()
        self.quote_timer.setSingleShot(True)
        self.quote_timer.timeout.connect(lambda: self.quote_overlay.setVisible(False))

    def dark_theme_stylesheet(self):
        return """
        QWidget { background: #171a1d; color: #e3e8ee; font-family: "Fira Mono", "Consolas", monospace; font-size: 16px; }
        QTextEdit, QLineEdit, QComboBox { background: #262a2e; color: #e3e8ee; border-radius: 8px; padding: 4px; }
        QPushButton { background: #212529; color: #59d6ff; border: none; border-radius: 8px; padding: 8px 18px; font-size: 17px; }
        QPushButton:hover { background: #30363c; }
        QLabel { color: #b1f1ff; }
        QCheckBox { color: #7ccfff; }
        """

    def setup_ui(self):
        main = QWidget()
        v = QVBoxLayout()
        main.setLayout(v)

        # --- TOP: Docker Image Auswahl und Modus ---
        h_top = QHBoxLayout()
        v.addLayout(h_top)

        self.image_label = QLabel("Docker-Image:")
        h_top.addWidget(self.image_label)
        self.image_combo = QComboBox()
        # Default populäre Images
        self.image_combo.addItems(["ubuntu:24.04", "python:3.11-slim", "debian:bookworm", "alpine:latest"])
        self.image_combo.setEditable(True)
        h_top.addWidget(self.image_combo)

        self.start_container_btn = QPushButton("Container starten")
        self.start_container_btn.clicked.connect(self.start_container)
        h_top.addWidget(self.start_container_btn)

        self.stop_container_btn = QPushButton("Stoppen/Löschen")
        self.stop_container_btn.clicked.connect(self.stop_container)
        h_top.addWidget(self.stop_container_btn)

        h_top.addStretch(1)

        self.allow_all_switch = QCheckBox("Allow All")
        self.allow_all_switch.stateChanged.connect(self.toggle_allow_all)
        h_top.addWidget(self.allow_all_switch)
        v.addSpacing(5)

        # --- Session Info ---
        self.session_info = QLabel("Session: [Keine]")
        self.container_status = QLabel("Container-Status: [Gestoppt]")
        v.addWidget(self.session_info)
        v.addWidget(self.container_status)
        v.addSpacing(8)

        # --- Pending Command ---
        self.pending_label = QLabel("Pending Command:")
        v.addWidget(self.pending_label)
        self.pending_command_edit = QLineEdit("")
        self.pending_command_edit.setReadOnly(True)
        v.addWidget(self.pending_command_edit)

        h_pending = QHBoxLayout()
        self.approve_btn = QPushButton("Erlauben & Ausführen")
        self.approve_btn.clicked.connect(self.approve_pending)
        self.reject_btn = QPushButton("Ablehnen")
        self.reject_btn.clicked.connect(self.reject_pending)
        h_pending.addWidget(self.approve_btn)
        h_pending.addWidget(self.reject_btn)
        v.addLayout(h_pending)
        v.addSpacing(8)

        # --- Terminal Output ---
        self.terminal_label = QLabel("Terminalausgabe:")
        v.addWidget(self.terminal_label)
        self.terminal_output = QTextEdit()
        self.terminal_output.setReadOnly(True)
        self.terminal_output.setStyleSheet("background: #14181b; color: #b3f1ff; font-family: 'Fira Mono', 'Consolas', monospace; font-size: 15px;")
        v.addWidget(self.terminal_output, 2)

        # --- Easter Egg Overlay ---
        self.quote_overlay = QLabel(self)
        self.quote_overlay.setStyleSheet(
            "background: rgba(30,35,45,210); color: #44ffd1; font-size: 17px; border-radius:14px; padding: 10px;"
        )
        self.quote_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.quote_overlay.setVisible(False)
        self.quote_overlay.setFixedHeight(42)
        self.quote_overlay.raise_()
        self.resizeEvent = self.adjust_quote_overlay

        self.setCentralWidget(main)
        self.update_ui()

    def adjust_quote_overlay(self, event=None):
        w = self.width()
        h = self.height()
        self.quote_overlay.setGeometry(
            int(w/2 - (w-40)/2), h - 70, w-40, 42
        )

    def show_quote(self, txt):
        self.quote_overlay.setText(txt)
        self.adjust_quote_overlay()
        self.quote_overlay.setVisible(True)
        self.quote_timer.start(3400)  # Anzeige für 3,4 Sekunden

    def toggle_allow_all(self, state):
        self.allow_all = state == Qt.Checked
        if self.allow_all:
            self.show_quote("ALLOW ALL: KI darf jetzt direkt Befehle senden.")

    def start_container(self):
        if self.current_container is not None:
            QMessageBox.warning(self, "Achtung", "Container läuft bereits!")
            return
        image = self.image_combo.currentText().strip()
        if not image:
            QMessageBox.warning(self, "Fehler", "Bitte Docker-Image wählen oder eingeben.")
            return
        name = f"ghostshell_{random.randint(100000, 999999)}"
        try:
            self.container_status.setText(f"Container wird gestartet: {image}")
            self.repaint()
            container = docker_client.containers.run(
                image, "/bin/bash", tty=True, stdin_open=True, detach=True, name=name
            )
            self.current_container = container
            self.session_status = "ready"
            self.show_quote(random.choice(GITS_QUOTES))
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Container konnte nicht gestartet werden:\n{e}")
            self.current_container = None
            self.session_status = "idle"
        self.update_ui()

    def stop_container(self):
        if self.current_container is None:
            QMessageBox.information(self, "Kein Container", "Es läuft kein Container.")
            return
        try:
            self.current_container.remove(force=True)
        except Exception:
            pass
        self.current_container = None
        self.session_status = "idle"
        self.terminal_output.clear()
        self.show_quote("Container gestoppt.")
        self.update_ui()

    def update_ui(self):
        if self.current_container:
            self.container_status.setText(
                f"Container-Status: Läuft ({self.current_container.name}, Image: {self.current_container.image.tags[0] if self.current_container.image.tags else '?'})"
            )
        else:
            self.container_status.setText("Container-Status: [Gestoppt]")
        self.session_info.setText(f"Session: {self.current_session if self.current_session else '[Keine]'}")
        if self.pending_command:
            self.pending_command_edit.setText(self.pending_command)
            self.approve_btn.setEnabled(True)
            self.reject_btn.setEnabled(True)
        else:
            self.pending_command_edit.clear()
            self.approve_btn.setEnabled(False)
            self.reject_btn.setEnabled(False)

    def approve_pending(self):
        if not self.pending_command or not self.pending_conn:
            return
        if not self.current_container:
            QMessageBox.critical(self, "Kein Container", "Bitte zuerst einen Container starten!")
            return
        # --- Führe Befehl im Container aus ---
        output = self.run_command_in_container(self.pending_command)
        self.terminal_output.append(f"> {self.pending_command}\n{output}\n")
        # Antwort an Skill
        send_json(self.pending_conn, {
            "status": "approved",
            "output": output
        })
        self.show_quote(random.choice(GITS_QUOTES))
        self.pending_command = None
        self.pending_conn = None
        self.update_ui()

    def reject_pending(self):
        if not self.pending_command or not self.pending_conn:
            return
        send_json(self.pending_conn, {
            "status": "rejected",
            "output": ""
        })
        self.show_quote("Access Denied.")
        self.pending_command = None
        self.pending_conn = None
        self.update_ui()

    def run_command_in_container(self, command):
        if not self.current_container:
            return "Kein Container gestartet!"
        try:
            exec_id = docker_client.api.exec_create(self.current_container.id, command, tty=True)
            output = docker_client.api.exec_start(exec_id, tty=True).decode(errors="ignore")
            return output
        except Exception as e:
            return f"Fehler: {e}"

    def socket_server(self):
        # Starte lokalen Socket-Server (Blocking, Thread)
        if SOCKET_TYPE == "unix":
            if os.path.exists(SOCKET_PATH):
                os.remove(SOCKET_PATH)
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.bind(SOCKET_PATH)
            os.chmod(SOCKET_PATH, 0o600)
        elif SOCKET_TYPE == "tcp":
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind((SOCKET_HOST, SOCKET_PORT))
        else:
            raise Exception("Unbekannter Socket-Typ!")
        s.listen(5)
        print(f"Socket Server läuft: {SOCKET_PATH or (SOCKET_HOST, SOCKET_PORT)}")
        while True:
            conn, _ = s.accept()
            threading.Thread(target=self.handle_skill_request, args=(conn,), daemon=True).start()

    def handle_skill_request(self, conn):
        try:
            data = recv_json(conn)
            if not data: return
            session = data.get("session")
            command = data.get("command")
            if not session or not command:
                return
            # Handling Allow All/Deny All:
            self.current_session = session
            if self.allow_all:
                if not self.current_container:
                    self.start_container()
                    if not self.current_container:
                        send_json(conn, {"status": "rejected", "output": "Container konnte nicht gestartet werden."})
                        return
                output = self.run_command_in_container(command)
                self.terminal_output.append(f"> {command}\n{output}\n")
                send_json(conn, {"status": "approved", "output": output})
                self.show_quote(random.choice(GITS_QUOTES))
                return
            # Nur ein pending command zulassen!
            if self.pending_command is not None:
                send_json(conn, {"status": "rejected", "output": "Warte auf Bestätigung des vorherigen Befehls."})
                return
            self.pending_command = command
            self.pending_conn = conn
            self.update_ui()
            # Blockiere bis Aktion (approve/reject)
            while self.pending_command is not None:
                time.sleep(0.2)
            try:
                conn.close()
            except:
                pass
        except Exception as e:
            print("Fehler beim Handle Skill:", e)

# --- JSON Hilfe ---
def send_json(sock, obj):
    msg = json.dumps(obj).encode() + b"\n"
    try:
        sock.sendall(msg)
    except Exception:
        pass

def recv_json(sock):
    buf = b""
    while not buf.endswith(b"\n"):
        part = sock.recv(4096)
        if not part:
            return None
        buf += part
    try:
        return json.loads(buf.decode())
    except Exception:
        return None

# --- Start ---
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = GhostShellApp()
    win.show()
    app.exec()
