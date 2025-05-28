# Ghost in the Shell Terminal Skill

**A human-in-the-loop terminal skill for AnythingLLM.**

This plugin routes all AI-generated shell commands through a dark-themed GUI. The user can approve or reject each command before it's executed in a persistent Docker container. The GUI supports Docker image selection, allow/deny-all modes, and displays memorable quotes from hacker and cyberpunk movies.

## Features

- **Dark-Theme GUI** with live terminal output
- **Human approval** for every AI command (deny-all mode), or let AI run freely (allow-all)
- **Select Docker image** for the session container
- **Single pending command** for clear workflow
- **Persistent session containers** (per sessionId)
- **Famous hacker/cyberpunk quotes** as easter eggs

## Installation

1. **Clone this folder** into your AnythingLLM `agent-skills` directory.

2. **Set up Python venv (recommended):**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3. **Install requirements:**
    ```bash
    pip install -r requirements.txt
    ```

4. **Ensure Docker is running** and accessible to your user.

## Usage

- Start AnythingLLM Desktop as usual.
- The skill will automatically launch the GUI (`ki_shell_gui.py`) if needed.
- From the AnythingLLM chat, use:
    ```
    {
      "sessionId": "your_session_name",
      "command": "ls -l"
    }
    ```
- In the GUI, approve or reject the pending command, or switch to **Allow All** for automatic execution.

## Development

- The GUI can also be started directly with:
    ```bash
    python3 ki_shell_gui.py
    ```
- All files must be in the same directory for best compatibility.
- **Platform notes:** Uses Unix domain socket on Linux/macOS, TCP socket on Windows.

## License

MIT

---

_“HSAB NI ETIRW I”  ;-)_
