import os
import sys
import asyncio
import docker
from terminalsrv.server import Server

# Set Docker container name from env or default
CONTAINER = os.environ.get("GHOSTSHELL_CONTAINER", "ghostshell_main")
IMAGE = os.environ.get("GHOSTSHELL_IMAGE", "python:3.11-slim")
PORT = int(os.environ.get("GHOSTSHELL_PORT", 8765))

client = docker.from_env()

# Ensure container is running
def ensure_container():
    try:
        c = client.containers.get(CONTAINER)
        if c.status != "running":
            c.start()
    except docker.errors.NotFound:
        # Create new container
        c = client.containers.run(
            IMAGE, "/bin/bash", tty=True, stdin_open=True, detach=True, name=CONTAINER
        )
    return c

container = ensure_container()

# Patch command to run as docker exec!
def docker_shell_cmd():
    return [
        "docker", "exec", "-it", CONTAINER, "/bin/bash"
    ]

# Monkeypatch terminalsrv to use docker exec instead of /bin/bash
orig_get_shell = Server.get_shell
def get_shell(self, *a, **k):
    return docker_shell_cmd()
Server.get_shell = get_shell

if __name__ == "__main__":
    print(f"[GhostShell BACKEND] Starte Terminal-WebSocket auf Port {PORT}")
    asyncio.run(Server().start(host="127.0.0.1", port=PORT))
