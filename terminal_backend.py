import asyncio
import os
import sys
import pty
import docker
import threading
import subprocess
import websockets

DOCKER_IMAGE = os.environ.get("GHOSTSHELL_IMAGE", "ubuntu:24.04")
CONTAINER_NAME = os.environ.get("GHOSTSHELL_CONTAINER", "ghostshell_1")
SHELL = "/bin/bash"

def get_or_create_container(image, name):
    client = docker.from_env()
    try:
        container = client.containers.get(name)
        if container.status != 'running':
            container.start()
        return container
    except docker.errors.NotFound:
        return client.containers.run(
            image,
            command=SHELL,
            tty=True,
            stdin_open=True,
            detach=True,
            name=name
        )

async def handler(websocket, path):
    # Prepare Docker container
    image = os.environ.get("GHOSTSHELL_IMAGE", DOCKER_IMAGE)
    name = os.environ.get("GHOSTSHELL_CONTAINER", CONTAINER_NAME)
    container = get_or_create_container(image, name)

    # Use docker exec to start a PTY inside the running container
    exec_id = container.client.api.exec_create(
        container.id, 
        cmd=SHELL,
        tty=True,
        stdin=True
    )['Id']
    sock = container.client.api.exec_start(exec_id, tty=True, detach=False, socket=True)

    async def read_pty():
        while True:
            await asyncio.sleep(0.01)
            try:
                data = sock.recv(1024)
                if data:
                    await websocket.send(data.decode(errors="ignore"))
            except Exception:
                break

    async def write_pty():
        async for msg in websocket:
            try:
                sock.send(msg.encode())
            except Exception:
                break

    await asyncio.gather(read_pty(), write_pty())
    sock.close()

if __name__ == "__main__":
    # For simplicity, always on localhost:8765
    loop = asyncio.get_event_loop()
    start_server = websockets.serve(handler, '127.0.0.1', 8765)
    loop.run_until_complete(start_server)
    print("GhostShell Terminal backend running on ws://127.0.0.1:8765 (Docker mode)")
    loop.run_forever()
