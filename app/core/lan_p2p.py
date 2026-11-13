"""Faz 16.2 — LAN P2P Paylasim (aiortc WebRTC durumu + harici sunucusuz yerel ag dosya paylasim odasi)."""
from __future__ import annotations

import hmac
import ipaddress
import logging
import secrets
import socket
import shutil
import threading
from urllib.parse import quote
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def p2p_capabilities() -> dict[str, Any]:
    has_aiortc = False
    try:
        import aiortc  # noqa: F401
        has_aiortc = True
    except Exception:
        pass
    return {"ok": True, "aiortc_installed": has_aiortc, "lan_http_ready": True}


def _is_lan_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return ip.is_private or ip.is_loopback
    except ValueError:
        return False


def local_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.168.1.1", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


class LanShareServer:
    """Harici sunucusuz, yalnizca yerel ag IP'lerine acik token-korumali dosya paylasim odasi."""

    def __init__(self) -> None:
        self._srv: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.token: str = ""
        self.port: int = 0
        self.files: dict[str, Path] = {}

    def share_file(self, path: str | Path) -> dict[str, Any]:
        p = Path(path)
        if not p.is_file():
            return {"ok": False, "error": "Paylasilacak dosya bulunamadi"}
        if self._srv is None:
            self.start()
        fid = secrets.token_hex(6)
        self.files[fid] = p
        ip = local_lan_ip()
        return {
            "ok": True,
            "id": fid,
            "name": p.name,
            "size": p.stat().st_size,
            "url": f"http://{ip}:{self.port}/file/{fid}?token={self.token}",
            "token": self.token,
        }

    def start(self, port: int = 0) -> dict[str, Any]:
        if self._srv is not None:
            return {"ok": True, "port": self.port, "token": self.token}
        self.token = secrets.token_urlsafe(12)
        parent = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:  # noqa: ARG002
                pass

            def do_GET(self) -> None:
                client_ip = self.client_address[0] if self.client_address else ""
                if not _is_lan_ip(client_ip):
                    self.send_error(403, "Yalnizca yerel ag")
                    return
                path_only, _, qs = self.path.partition("?")
                tok = self.headers.get("X-Kami-Lan-Token", "")
                if not tok and "token=" in qs:
                    tok = qs.split("token=", 1)[1].split("&", 1)[0]
                if not hmac.compare_digest(tok, parent.token):
                    self.send_error(401, "Gecersiz anahtar")
                    return
                if path_only.startswith("/file/"):
                    fid = path_only.removeprefix("/file/")
                    fp = parent.files.get(fid)
                    if not fp or not fp.is_file():
                        self.send_error(404, "Dosya yok")
                        return
                    # Dosya parca parca akar (GB'lik dosyayi RAM'e okumaz); basliklar latin-1 oldugu icin
                    # Turkce/Japonca ad RFC 5987 filename* ile gider (yoksa UnicodeEncodeError)
                    ascii_name = fp.name.encode("ascii", "replace").decode().replace('"', "_")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(fp.stat().st_size))
                    self.send_header("Content-Disposition", f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(fp.name)}")
                    self.end_headers()
                    try:
                        with fp.open("rb") as fh:
                            shutil.copyfileobj(fh, self.wfile, 1024 * 1024)
                    except (ConnectionError, OSError):
                        pass
                    return
                self.send_error(404)

        self._srv = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
        self.port = int(self._srv.server_address[1])
        self._thread = threading.Thread(target=self._srv.serve_forever, name="kami-lan-p2p", daemon=True)
        self._thread.start()
        return {"ok": True, "port": self.port, "token": self.token}

    def stop(self) -> dict[str, Any]:
        if self._srv is not None:
            self._srv.shutdown()
            self._srv.server_close()
            self._srv = None
        self.files.clear()
        return {"ok": True, "stopped": True}
