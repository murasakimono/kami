"""Yerel kopru: native host relay'i -> Kami.

- Sadece 127.0.0.1, gizli anahtar (X-Kami-Token) zorunlu.
- 'Origin' basligi tasiyan istekler (web sayfalari) reddedilir.
- Port + anahtar data/bridge.json'a yazilir; relay oradan okur.
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import secrets
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from app.core.manager import CaptureRejected, DownloadManager
from app.core.models import DownloadRequest

log = logging.getLogger(__name__)

PREFERRED_PORT = 47321
MAX_BODY = 1024 * 1024
APP_VERSION = "0.1.0"


class BridgeServer:
    def __init__(self, manager: DownloadManager, info_path: Path,
                 on_show: Callable[[], None] | None = None) -> None:
        self.manager = manager
        self.info_path = info_path
        self.on_show = on_show or (lambda: None)
        self.token = secrets.token_urlsafe(32)
        self.httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self.httpd.server_address[1] if self.httpd else 0

    def start(self) -> None:
        handler = _make_handler(self)
        try:
            self.httpd = ThreadingHTTPServer(("127.0.0.1", PREFERRED_PORT), handler)
        except OSError:
            self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.httpd.daemon_threads = True
        self._thread = threading.Thread(target=self.httpd.serve_forever, name="kami-bridge", daemon=True)
        self._thread.start()
        self.info_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.info_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"port": self.port, "token": self.token, "pid": os.getpid()}), encoding="utf-8")
        tmp.replace(self.info_path)
        log.info("Kopru dinliyor: 127.0.0.1:%s", self.port)

    def stop(self) -> None:
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
        try:
            info = json.loads(self.info_path.read_text(encoding="utf-8"))
            if info.get("pid") == os.getpid():
                self.info_path.unlink()
        except Exception:
            pass

    # ---------- islemler ----------
    def handle(self, path: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if path == "/v1/ping":
            return 200, {"ok": True, "app": "kami", "version": APP_VERSION,
                         "capture_enabled": bool(self.manager.settings.get("capture_enabled"))}
        if path == "/v1/show":
            self.on_show()
            return 200, {"ok": True}
        if path == "/v1/capture":  # eklenti acilir penceresindeki "otomatik devral" anahtari
            self.manager.settings.set("capture_enabled", bool(body.get("enabled")))
            return 200, {"ok": True, "capture_enabled": bool(self.manager.settings.get("capture_enabled"))}
        if path == "/v1/add":
            url = str(body.get("url") or "").strip()
            if not url.lower().startswith(("http://", "https://", "ftp://")):
                return 400, {"ok": False, "error": "bad_url"}
            headers = body.get("headers") or {}
            if not isinstance(headers, dict):
                headers = {}
            req = DownloadRequest(
                url=url,
                filename=str(body.get("filename") or ""),
                referer=str(body.get("referer") or ""),
                headers={str(k): str(v) for k, v in headers.items()},
                size=_int(body.get("size")),
                mime=str(body.get("mime") or ""),
                source=str(body.get("source") or "browser"),
                page_url=str(body.get("page_url") or ""),
            )
            if req.source not in ("browser", "context_menu", "ui"):
                req.source = "browser"
            try:
                added = self.manager.add(req)
            except CaptureRejected as exc:
                return 200, {"ok": True, "accepted": False, "reason": str(exc)}
            return 200, {"ok": True, "accepted": True, "ids": [d.id for d in added],
                         "confirm": any(d.status == "confirm" for d in added)}
        return 404, {"ok": False, "error": "not_found"}


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _make_handler(server: BridgeServer):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # stdout yerine log
            log.debug("bridge: " + fmt, *args)

        def _reply(self, code: int, payload: dict[str, Any]) -> None:
            data = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _authorized(self) -> bool:
            if self.headers.get("Origin"):
                return False
            token = self.headers.get("X-Kami-Token", "")
            return hmac.compare_digest(token.encode(), server.token.encode())

        def _dispatch(self, body: dict[str, Any]) -> None:
            if not self._authorized():
                self._reply(403, {"ok": False, "error": "forbidden"})
                return
            try:
                code, payload = server.handle(self.path.split("?", 1)[0], body)
            except Exception as exc:
                log.exception("Kopru istegi hata verdi")
                code, payload = 500, {"ok": False, "error": str(exc)}
            self._reply(code, payload)

        def do_GET(self):
            self._dispatch({})

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                self._reply(413, {"ok": False, "error": "too_large"})
                return
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw or b"{}")
                if not isinstance(body, dict):
                    raise ValueError
            except ValueError:
                self._reply(400, {"ok": False, "error": "bad_json"})
                return
            self._dispatch(body)

    return Handler


def call_running_instance(info_path: Path, path: str, body: dict | None = None,
                          timeout: float = 2.0) -> dict[str, Any] | None:
    """Calisan bir Kami varsa ona istek atar; yoksa None. (Tek ornek kontrolu + relay icin ortak.)"""
    try:
        info = json.loads(info_path.read_text(encoding="utf-8"))
        req = urllib.request.Request(
            f"http://127.0.0.1:{int(info['port'])}{path}",
            data=json.dumps(body or {}).encode(),
            headers={"Content-Type": "application/json", "X-Kami-Token": info["token"]},
            method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception:
        return None
