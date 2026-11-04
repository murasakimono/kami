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

from app.core.manager import CaptureRejected, DownloadManager, PageLinkRejected
from app.core.models import DownloadRequest

log = logging.getLogger(__name__)

PREFERRED_PORT = 47321
MAX_BODY = 8 * 1024 * 1024   # .torrent dosyasi (base64) icin
from app.core.extras import APP_VERSION  # noqa: E402


class BridgeServer:
    RD_WAIT = 20.0   # saniye; native host'un rd zaman asimi (host.py) bundan uzun olmali
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
                extra={"checksum": str(body.get("checksum") or "")[:80]} if body.get("checksum") else {},
            )
            if req.source not in ("browser", "context_menu", "ui"):
                req.source = "browser"
            if req.source != "browser" and self.manager.cloud.provider_for(url):
                # bulut paylasim linki (sag tik): Kami'de klasor/secim penceresi acilsin
                self._media_choose(url, req.page_url, {})
                return 200, {"ok": True, "accepted": True, "ids": [], "media": True}
            try:
                added = self.manager.add(req)
            except PageLinkRejected:
                if req.source == "browser":
                    return 200, {"ok": True, "accepted": False, "reason": "page_link"}
                # sag tik ile sayfa linki (orn. YouTube): Kami'de medya penceresi acilsin
                self._media_choose(url, req.page_url, req.headers)
                return 200, {"ok": True, "accepted": True, "ids": [], "media": True}
            except CaptureRejected as exc:
                return 200, {"ok": True, "accepted": False, "reason": str(exc)}
            return 200, {"ok": True, "accepted": True, "ids": [d.id for d in added],
                         "confirm": any(d.status == "confirm" for d in added)}
        if path == "/v1/cookies":  # eklenti: YouTube/Google oturum cerezleri (DPAPI ile saklanir)
            from app.engines import ytdlp_engine as yt
            cookies = body.get("cookies")
            if yt.COOKIES is None or not isinstance(cookies, list):
                return 400, {"ok": False, "error": "bad_cookies"}
            n = yt.COOKIES.save(cookies)
            return 200, {"ok": True, "saved": n}
        if path == "/v1/media":  # video ustu buton / acilir penceredeki yakalanan akislar
            url = str(body.get("url") or "").strip()
            if not url.lower().startswith(("http://", "https://")):
                return 400, {"ok": False, "error": "bad_url"}
            headers = body.get("headers") or {}
            headers = {str(k): str(v) for k, v in headers.items()} if isinstance(headers, dict) else {}
            page_url = str(body.get("page_url") or "")
            mode = str(body.get("mode") or "choose")
            cloud_url = self._cloud_url(url, page_url)
            if cloud_url:   # bulut paylasimi (orn. MEGA video sayfasi): eklenti cozucu, yt-dlp degil
                self._media_choose(cloud_url, page_url, {})
                return 200, {"ok": True, "accepted": True, "ids": [], "media": True, "cloud": True}
            if mode not in ("mp4", "mp3"):
                self._media_choose(url, page_url, headers, str(body.get("title") or ""))
                return 200, {"ok": True, "accepted": True, "ids": [], "media": True}
            try:
                d = self.manager.add_media(url, options={"format": mode}, title=str(body.get("title") or ""),
                                           source="extension", page_url=page_url, headers=headers)
            except (ValueError, CaptureRejected) as exc:
                return 200, {"ok": True, "accepted": False, "reason": str(exc)}
            return 200, {"ok": True, "accepted": True, "ids": [d.id]}
        if path == "/v1/rd":   # eklenti "Real-Debrid'e gonder" / Windows magnet isleyicisi
            return self._rd(body)
        return 404, {"ok": False, "error": "not_found"}

    def _rd(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """RD'ye ekler; sonuc hem cevapta (eklenti popup/rozet) hem Kami'de bildirim olarak doner."""
        import base64
        from app.core.debrid import DebridError, is_magnet
        rd = getattr(self.manager, "debrid", None)
        url = str(body.get("url") or "").strip()
        raw = str(body.get("torrent_b64") or "")
        if not raw and not (is_magnet(url) or url.lower().startswith(("http://", "https://"))):
            return 400, {"ok": False, "error": "bad_url"}
        if body.get("source") == "magnet" and is_magnet(url):
            # Windows magnet: isleyicisi -> RD / yerel torrent secimi Kami'de (rd_mode ayari)
            self.manager.events.emit("torrent.request", src=url)
            self.on_show()
            return 200, {"ok": True, "accepted": True}
        notify = rd.notify if rd else (lambda ev: None)
        if rd is None or not rd.has_token():
            notify({"kind": "error", "error": "rd_no_token"})
            self.on_show()
            return 200, {"ok": True, "accepted": False, "reason": "rd_no_token"}
        try:
            data = base64.b64decode(raw, validate=True) if raw else b""
        except ValueError:
            return 400, {"ok": False, "error": "bad_torrent"}

        result: dict[str, Any] = {}

        def work() -> None:
            try:
                if data:
                    rd.add_torrent_bytes(data)
                    ev = {"kind": "torrent", "name": str(body.get("name") or "")}
                elif is_magnet(url):
                    rd.add_magnet(url)
                    ev = {"kind": "torrent", "name": ""}
                else:
                    n = rd.add_link(url)
                    ev = {"kind": "queued", "name": "", "count": n}
                result.update(accepted=True, kind=ev["kind"])
            except DebridError as exc:
                log.warning("RD istegi basarisiz: %s %s", exc.code, exc.detail)
                ev = {"kind": "error", "error": exc.code, "detail": exc.detail}
                result.update(accepted=False, reason=exc.code, detail=exc.detail)
            except Exception:
                log.exception("RD istegi hatasi")
                ev = {"kind": "error", "error": "rd_failed"}
                result.update(accepted=False, reason="rd_failed", detail="")
            notify(ev)

        # Eklenti sonucu gostersin diye RD cevabini bekleriz (cogu 1-3 sn); gecikirse "isleniyor" doner,
        # sonuc yine Kami'de bildirim olarak gorunur.
        t = threading.Thread(target=work, name="kami-rd-req", daemon=True)
        t.start()
        t.join(self.RD_WAIT)
        if not result:
            return 200, {"ok": True, "accepted": True, "pending": True}
        return 200, {"ok": True, **dict(result)}

    def _cloud_url(self, url: str, page_url: str) -> str:
        """Link ya da sayfasi bir bulut eklentisine uyuyorsa o link (eklenti cozuculeri yt-dlp'den once)."""
        for u in (url, page_url):
            if u and u.lower().startswith(("http://", "https://")) and self.manager.cloud.provider_for(u):
                return u
        return ""

    def _media_choose(self, url: str, page_url: str, headers: dict[str, str], title: str = "") -> None:
        self.manager.events.emit("media.choose", url=url, page_url=page_url, headers=headers, title=title)
        self.on_show()


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
