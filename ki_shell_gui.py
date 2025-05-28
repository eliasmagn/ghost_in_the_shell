import sys
import os
import threading
import socket
import json
import select
import time
import random

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QListWidget, QListWidgetItem, QMessageBox
)
from PySide6.QtCore import Qt, QTimer

import docker
import pty

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

class PendingCommand:
    def __init__(self, session, command, from_skill):
        self.session = session
        self.command = command
        self.from_skill = from_skill  # socket object
        self.status = "pending"
        self.output = ""

class KIShellApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Human-in-the-Loop Shell (KI Terminal Control)")
        self.setGeometry(100, 100, 1000, 700)
        self.pending_commands = []
        self.docker_sessions = {}  # session -> (pty_fd, pid, container)
        self.setup_ui()
        self.timer = QTimer()
        self.quote_overlay = QLabel(self)
        self.quote_overlay.setStyleSheet(
            "background: rgba(20,20,20, 200); color: #66ffff; font-size: 16px; border-radius:10px; padding: 10px;"
        )
        self.quote_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.quote_overlay.setVisible(False)
        self.quote_overlay.setFixedHeight(40)
        self.quote_overlay.raise_()

        self.quote_timer = QTimer()
        self.quote_timer.setSingleShot(True)
        self.quote_timer.timeout.connect(lambda: self.quote_overlay.setVisible(False))

        self.timer.timeout.connect(self.refresh_pending_list)
        self.timer.start(1000)
        threading.Thread(target=self.socket_server, daemon=True).start()

    def setup_ui(self):
        main = QWidget()
        v = QVBoxLayout()
        main.setLayout(v)

        # Pending commands
        self.pending_list = QListWidget()
        v.addWidget(QLabel("Ausstehende Kommandos von AnythingLLM:"))
        v.addWidget(self.pending_list, 1)

        h = QHBoxLayout()
        self.approve_btn = QPushButton("Bestätigen & Ausführen")
        self.reject_btn = QPushButton("Ablehnen")
        self.term_btn = QPushButton("Terminal anzeigen")
        h.addWidget(self.approve_btn)
        h.addWidget(self.reject_btn)
        h.addWidget(self.term_btn)
        v.addLayout(h)

        self.terminal_output = QTextEdit()
        self.terminal_output.setReadOnly(True)
        v.addWidget(QLabel("Terminalausgabe:"))
        v.addWidget(self.terminal_output, 2)

        self.setCentralWidget(main)
        self.resizeEvent = self.adjust_quote_overlay
        self.approve_btn.clicked.connect(self.approve_selected)
        self.reject_btn.clicked.connect(self.reject_selected)
        self.term_btn.clicked.connect(self.show_terminal_selected)

    def refresh_pending_list(self):
        self.pending_list.clear()
        for cmd in self.pending_commands:
            item = QListWidgetItem(f"Session: {cmd.session} | Kommando: {cmd.command} | Status: {cmd.status}")
            self.pending_list.addItem(item)

    def get_selected(self):
        idx = self.pending_list.currentRow()
        if idx < 0 or idx >= len(self.pending_commands):
            return None
        return self.pending_commands[idx]

    def approve_selected(self):
        cmd = self.get_selected()
        if not cmd or cmd.status != "pending":
            return
        output, ok = self.run_command_in_docker(cmd.session, cmd.command)
        cmd.output = output
        cmd.status = "approved"
        self.terminal_output.setPlainText(output)
        self.show_quote(random.choice(GITS_QUOTES))
       # Antwort zurück an Skill
        try:
            answer = {
                "session": cmd.session,
                "status": "approved",
                "output": output
            }
            send_json(cmd.from_skill, answer)
        except Exception as e:
            print("Antwort an Skill fehlgeschlagen:", e)

    def reject_selected(self):
        cmd = self.get_selected()
        if not cmd or cmd.status != "pending":
            return
        cmd.status = "rejected"
        self.show_quote(random.choice(GITS_QUOTES))
        try:
            answer = {
                "session": cmd.session,
                "status": "rejected",
                "output": ""
            }
            send_json(cmd.from_skill, answer)
        except Exception as e:
            print("Antwort an Skill fehlgeschlagen:", e)

    def show_terminal_selected(self):
        cmd = self.get_selected()
        if not cmd or cmd.status == "pending":
            QMessageBox.warning(self, "Nicht möglich", "Bitte zuerst ausführen.")
            return
        self.terminal_output.setPlainText(cmd.output)

    def run_command_in_docker(self, session, command):
        # Falls Session/Container existiert: weiterverwenden, sonst starten
        if session not in self.docker_sessions:
            # Neues Container mit /bin/bash
            container = docker_client.containers.run(
                "ubuntu:24.04", "/bin/bash", tty=True, stdin_open=True, detach=True, remove=True
            )
            pid, fd = pty.fork()
            if pid == 0:
                os.execvp("docker", ["docker", "exec", "-it", container.id, "/bin/bash"])
            self.docker_sessions[session] = (fd, pid, container)
            time.sleep(1)  # Gebe dem PTY Zeit für Bash

        fd, pid, container = self.docker_sessions[session]
        # Schreibe Befehl rein
        os.write(fd, (command + "\n").encode())
        # Lese Output für max 3 Sekunden (vereinfachtes Capturing)
        output = b""
        t0 = time.time()
        while time.time() - t0 < 3:
            r, _, _ = select.select([fd], [], [], 0.2)
            if fd in r:
                try:
                    data = os.read(fd, 4096)
                    if not data: break
                    output += data
                except OSError:
                    break
            else:
                break
        return output.decode(errors="ignore"), True

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
            cmd = PendingCommand(session, command, conn)
            self.pending_commands.append(cmd)
            while cmd.status == "pending":
                time.sleep(0.2)
            time.sleep(1)
            try:
                conn.close()
            except:
                pass
        except Exception as e:
            print("Fehler beim Handle Skill:", e)

    GITS_QUOTES = [
        "The net is vast and infinite.",
        "If we all reacted the same way, we'd be predictable, and there's always more than one way to view a situation.",
        "Your effort to remain what you are is what limits you.",
        "I am connected to a vast network, of which I myself am a part.",
        "What we see now is like a dim image in a mirror.",
        "I guess once you start doubting, there's no end to it."
    ]

    def show_quote(self, txt):
        self.quote_overlay.setText(txt)
        self.adjust_quote_overlay()
        self.quote_overlay.setVisible(True)
        self.quote_timer.start(3200)  # Anzeige für 3,2 Sekunden

    def adjust_quote_overlay(self, event=None):
        # Always keep at bottom-center
        w = self.width()
        h = self.height()
        self.quote_overlay.setGeometry(
            int(w/2 - self.quote_overlay.width()/2),
            h - 60,
            w - 40, 40
        )


def send_json(sock, obj):
    msg = json.dumps(obj).encode() + b"\n"
    sock.sendall(msg)

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

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = KIShellApp()
    win.show()
    app.exec()
