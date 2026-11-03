"""Ortak test araclari: Range destekli yerel HTTP sunucusu (cok baglantili indirme testi icin)."""
from __future__ import annotations

import hashlib
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

_RANGE = re.compile(r"bytes=(\d+)-(\d*)")


class _Handler(BaseHTTPRequestHandler):
    files: dict[str, bytes] = {}
    connections: set = set()
    lock = threading.Lock()

    def log_message(self, *a):  # sessiz
        pass

    def _send(self, head_only: bool) -> None:
        name = self.path.split("?", 1)[0].lstrip("/")
        data = self.files.get(name.split("/")[-1]) if not name.startswith("cd/") else self.files.get(name[3:])
        if data is None:
            self.send_error(404)
            return
        with self.lock:
            self.connections.add(self.client_address)
        rng = self.headers.get("Range")
        start, end = 0, len(data) - 1
        status = 200
        if rng and (m := _RANGE.match(rng)):
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else end
            status = 206
        chunk = data[start:end + 1]
        self.send_response(status)
        self.send_header("Content-Length", str(len(chunk)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Type", "application/octet-stream")
        if name.startswith("cd/"):
            self.send_header("Content-Disposition", f'attachment; filename="{name[3:]}"')
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
        self.end_headers()
        if not head_only:
            try:
                self.wfile.write(chunk)
            except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
                pass

    def do_GET(self):
        self._send(False)

    def do_HEAD(self):
        self._send(True)


@pytest.fixture(scope="session")
def http_server():
    data = os.urandom(24 * 1024 * 1024)
    _Handler.files = {"big.bin": data, "video.mp4": data[: 3 * 1024 * 1024], "setup.exe": b"MZ" + data[:4096]}
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    srv.base = f"http://127.0.0.1:{srv.server_address[1]}"  # type: ignore[attr-defined]
    srv.sha = {k: hashlib.sha256(v).hexdigest() for k, v in _Handler.files.items()}  # type: ignore[attr-defined]
    srv.handler = _Handler  # type: ignore[attr-defined]
    yield srv
    srv.shutdown()
