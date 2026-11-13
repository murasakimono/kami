"""WebView2 Cross-Origin Isolation (COOP/COEP) sunucusu.

`file://` kokendeki mevcut localStorage verisini bozmadan, SharedArrayBuffer ve
cok is parcacikli WebAssembly/Worker modulleri icin `Cross-Origin-Opener-Policy: same-origin`
ve `Cross-Origin-Embedder-Policy: credentialless` basliklariyla yerel HTTP kokusu sunar.
"""
from __future__ import annotations

import logging
import mimetypes
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from app import paths

log = logging.getLogger(__name__)

ISOLATION_HEADERS: tuple[tuple[str, str], ...] = (
    ("Cross-Origin-Opener-Policy", "same-origin"),
    ("Cross-Origin-Embedder-Policy", "credentialless"),
    ("Cross-Origin-Resource-Policy", "cross-origin"),
    ("Access-Control-Allow-Origin", "*"),
    ("Cache-Control", "no-store"),
)

_SAB_PROBE_HTML = b"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Kami SAB Probe</title></head>
<body><script>
const info = {
  crossOriginIsolated: Boolean(window.crossOriginIsolated),
  sharedArrayBuffer: typeof SharedArrayBuffer !== "undefined",
  origin: location.origin,
};
if (window.parent && window.parent !== window) {
  window.parent.postMessage({ type: "kami:sab-probe", ...info }, "*");
}
window.__KAMI_SAB_INFO__ = info;
</script></body></html>
"""


class _ThreadingIsolationHTTP(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def _bind_server(preferred_port: int, handler_cls) -> ThreadingHTTPServer:
    if preferred_port > 0:
        try:
            return _ThreadingIsolationHTTP(("127.0.0.1", preferred_port), handler_cls)
        except OSError:
            pass
    return _ThreadingIsolationHTTP(("127.0.0.1", 0), handler_cls)


class UiIsolationServer:
    """`paths.WEB_DIR` icerigini COOP/COEP basliklariyla 127.0.0.1 uzerinden sunar."""

    def __init__(self, root: Path | None = None, preferred_port: int = 47395) -> None:
        self.root = (root or paths.WEB_DIR).resolve()
        self.preferred_port = preferred_port
        self.httpd: ThreadingHTTPServer | None = None
        self.port: int = 0
        self._thread: threading.Thread | None = None

    def start(self) -> int:
        if self.httpd is not None:
            return self.port
        handler = self._make_handler()
        self.httpd = _bind_server(self.preferred_port, handler)
        self.port = int(self.httpd.server_address[1])
        self._thread = threading.Thread(
            target=self.httpd.serve_forever,
            name="kami-ui-iso",
            daemon=True,
        )
        self._thread.start()
        log.info("UiIsolationServer hazir: http://127.0.0.1:%d", self.port)
        return self.port

    def stop(self) -> None:
        if self.httpd is not None:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except OSError:
                pass
            self.httpd = None
            self.port = 0

    def url(self, rel_path: str = "sab-probe.html") -> str:
        if not self.port:
            return ""
        clean = str(rel_path or "").lstrip("/")
        return f"http://127.0.0.1:{self.port}/{clean}"

    def info(self) -> dict[str, Any]:
        return {
            "running": self.httpd is not None,
            "port": self.port,
            "origin": f"http://127.0.0.1:{self.port}" if self.port else "",
            "probe_url": self.url("sab-probe.html"),
            "headers": dict(ISOLATION_HEADERS[:3]),
            "coop": "same-origin",
            "coep": "credentialless",
        }

    def _make_handler(self):
        root = self.root

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt: str, *args: Any) -> None:
                log.debug("ui-iso: " + fmt, *args)

            def _send_isolation_headers(self) -> None:
                for k, v in ISOLATION_HEADERS:
                    self.send_header(k, v)

            def _send_bytes(self, code: int, body: bytes, ctype: str, head: bool) -> None:
                self.send_response(code)
                self._send_isolation_headers()
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if not head and body:
                    self.wfile.write(body)

            def do_OPTIONS(self) -> None:
                self.send_response(204)
                self._send_isolation_headers()
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_HEAD(self) -> None:
                self.do_GET(head=True)

            def do_GET(self, head: bool = False) -> None:
                rel = unquote(urlsplit(self.path).path).lstrip("/") or "index.html"
                if rel == "sab-probe.html":
                    self._send_bytes(200, _SAB_PROBE_HTML, "text/html; charset=utf-8", head)
                    return
                try:
                    target = (root / rel).resolve()
                except OSError:
                    self._send_bytes(400, b"", "text/plain; charset=utf-8", head)
                    return
                if not target.is_relative_to(root) or not target.is_file():
                    self._send_bytes(404, b"Not found", "text/plain; charset=utf-8", head)
                    return
                ctype, _ = mimetypes.guess_type(str(target))
                if target.suffix == ".js":
                    ctype = "application/javascript; charset=utf-8"
                elif target.suffix == ".css":
                    ctype = "text/css; charset=utf-8"
                elif target.suffix == ".html":
                    ctype = "text/html; charset=utf-8"
                elif target.suffix == ".wasm":
                    ctype = "application/wasm"
                data = target.read_bytes()
                self._send_bytes(200, data, ctype or "application/octet-stream", head)

        return Handler
