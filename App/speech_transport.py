"""LaunchServices owns speech permissions; a private socket carries transient IPC."""
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time


class SpeechProcess:
    def __init__(self, helper):
        self.bundle = Path(helper).parents[2]
        self.stopped = threading.Event()
        self.lock = threading.Lock()
        self.connection = None

    def send(self, command):
        with self.lock:
            if self.connection is not None and not self.stopped.is_set():
                self.connection.sendall((command+'\n').encode())

    def cancel(self):
        self.stopped.set()
        with self.lock:
            if self.connection is not None:
                try:self.connection.shutdown(socket.SHUT_RDWR)
                except OSError:pass

    def events(self, command):
        if self.stopped.is_set():return
        # Short paths fit macOS sockaddr_un; TemporaryDirectory is mode 0700.
        # Only socket metadata exists on disk, never audio or transcript content.
        with tempfile.TemporaryDirectory(prefix='face-speech-', dir='/tmp') as folder:
            path = str(Path(folder)/'ipc')
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                server.bind(path); server.listen(1); server.settimeout(.1)
                process = subprocess.Popen(['/usr/bin/open', '-n', '-g', '-W', str(self.bundle),
                    '--args', '--socket', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                connection = None
                try:
                    deadline = time.monotonic()+10
                    while not self.stopped.is_set():
                        try:
                            connection, _ = server.accept()
                            break
                        except socket.timeout:
                            if process.poll() is not None or time.monotonic() > deadline:
                                raise ValueError('Speech app could not launch. Rebuild with python3 tools/build_dictation.py.')
                    if connection is None:return
                    with self.lock:self.connection = connection
                    if self.stopped.is_set():return
                    self.send(command)
                    with connection.makefile('r', encoding='utf-8') as stream:
                        while not self.stopped.is_set():
                            line = stream.readline(65537)
                            if not line:break
                            if len(line) > 65536:
                                raise ValueError('Speech provider exceeded its message limit')
                            yield json.loads(line)
                finally:
                    self.cancel()  # EOF shuts down the app, including during setup.
                    with self.lock:self.connection = None
                    if connection is not None:connection.close()
                    try:process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.terminate(); process.wait(timeout=2)
