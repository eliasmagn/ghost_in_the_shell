# Human-in-the-Loop Shell Skill für AnythingLLM

Dieser Skill ermöglicht es, Shell-Befehle aus AnythingLLM in einem Docker-Container auszuführen – aber **nur nach expliziter Freigabe durch den Nutzer** in einer lokalen GUI-App.  
Maximale Sicherheit: Keine KI kann eigenständig kritische Befehle absetzen.

## Funktionsweise

- Skill sendet das gewünschte Kommando und die Session-ID an die lokale Shell-GUI über einen Socket.
- Die App zeigt alle Pending-Kommandos an. Der User kann sie bestätigen oder ablehnen.
- Erst nach Bestätigung wird das Kommando im Docker-Container ausgeführt. Die Ausgabe geht zurück an AnythingLLM.

## Plattformen

- **Linux/Mac:** Kommunikation über Unix Domain Socket (`/tmp/ki_shell.sock`)
- **Windows:** Kommunikation über TCP (`127.0.0.1:8777`)

Die Erkennung geschieht automatisch im Code – keine Einstellung nötig!

## Start

1. **Python-App starten:**  
   ```bash
   python3 ki_shell_gui.py
