"""Birlikte izle: Kami Player'daki videoyu bir web sayfasi uzerinden arkadasinla esli izleme.

- Yerel sunucu (127.0.0.1) /<oda>/ altinda: izleme sayfasi, oynatma durumu (uzun yoklama), sohbet.
- Video, oynaticinin medya sunucusundan vekil (proxy) ile verilir: dogrudan / remux / NVENC donusturme ayni kalir.
- Disariya Cloudflare quick tunnel (cloudflared, hesap gerekmez) ile acilir: https://<rastgele>.trycloudflare.com/<oda>/
- Oda anahtari rastgele; bilmeyen giremez. Oda kapaninca tunel de kapanir.
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler
from typing import Any

from app import paths

log = logging.getLogger("kami")
NOWIN = 0x08000000 if os.name == "nt" else 0
CF_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
CF_EXE = paths.DATA_DIR / "tools" / "cloudflared.exe"


class Room:
    def __init__(self, media_base: str, info: dict[str, Any], host_name: str) -> None:
        self.id = secrets.token_urlsafe(9)
        self.media_base = media_base.rstrip("/")         # http://127.0.0.1:P/<token>
        self.info = info
        self.host_name = host_name
        self.state = {"playing": False, "t": 0.0, "at": time.time(), "by": "host", "v": 1}
        self.events: list[dict[str, Any]] = []           # sohbet + sistem satirlari
        self.seq = 0
        self.people: dict[str, dict[str, Any]] = {}      # id -> {name, seen}
        self.cv = threading.Condition()

    # ---- durum
    def set_state(self, playing: bool, t: float, by: str) -> None:
        with self.cv:
            self.state = {"playing": bool(playing), "t": max(0.0, float(t)), "at": time.time(), "by": by,
                          "v": self.state["v"] + 1}
            self.cv.notify_all()

    def say(self, who: str, text: str, kind: str = "chat") -> None:
        text = str(text or "").strip()[:500]
        if not text:
            return
        with self.cv:
            self.seq += 1
            self.events.append({"n": self.seq, "who": who[:40], "text": text, "kind": kind, "t": time.time()})
            self.events = self.events[-300:]
            self.cv.notify_all()

    def touch(self, pid: str, name: str) -> None:
        with self.cv:
            new = pid not in self.people
            self.people[pid] = {"name": name[:40] or "Misafir", "seen": time.time()}
        if new and pid != "host":
            self.say(name or "Misafir", "katıldı", "sys")

    def snapshot(self, since_v: int, since_n: int, wait: float, pid: str = "") -> dict[str, Any]:
        end = time.time() + wait
        with self.cv:
            while self.state["v"] <= since_v and self.seq <= since_n and time.time() < end:
                self.cv.wait(max(0.05, end - time.time()))
            now = time.time()
            gone = [k for k, p in self.people.items() if now - p["seen"] > 45 and k != "host"]
            for k in gone:
                nm = self.people.pop(k)["name"]
                self.seq += 1
                self.events.append({"n": self.seq, "who": nm, "text": "ayrıldı", "kind": "sys", "t": now})
            return {"state": self.state, "events": [e for e in self.events if e["n"] > since_n], "now": now,
                    "people": [p["name"] for k, p in self.people.items() if k != "host"], "host": self.host_name}

    def public_info(self) -> dict[str, Any]:
        """Medya adreslerini oda altindaki vekil yollara cevirir."""
        def rel(u: str) -> str:
            return u.replace(self.media_base + "/", "m/") if isinstance(u, str) else u
        i = self.info
        return {"title": i.get("title", ""), "kind": i.get("kind", "video"), "mode": i.get("mode", "direct"),
                "duration": i.get("duration", 0), "direct_url": rel(i.get("direct_url", "")),
                "stream_url": rel(i.get("stream_url", "")), "cover": rel(i.get("cover", "") or ""),
                "subs": [{"label": str(x.get("label", ""))[:80], "url": rel(x.get("url", ""))} for x in (i.get("subs") or [])
                         if isinstance(x, dict) and str(x.get("url", "")).startswith(self.media_base)],
                "audio": len(i.get("audio") or [])}


class WatchServer:
    def __init__(self) -> None:
        self.room: Room | None = None
        self.httpd = None
        self.tunnel: subprocess.Popen | None = None
        self.public = ""
        self.tunnel_state = "off"          # off | installing | starting | on | error
        self.tunnel_error = ""
        self.lock = threading.Lock()

    # ---- yasam dongusu
    def start(self, media_base: str, info: dict[str, Any], host_name: str, tunnel: bool = True) -> dict[str, Any]:
        with self.lock:
            self.room = Room(media_base, info, host_name)
            self.room.touch("host", host_name)
            if not self.httpd:
                from app.core.net import ExclusiveHTTPServer
                self.httpd = ExclusiveHTTPServer.make(("127.0.0.1", 0), _handler(self))
                self.httpd.daemon_threads = True
                threading.Thread(target=self.httpd.serve_forever, name="kami-watch", daemon=True).start()
        if tunnel and not (self.tunnel and self.tunnel.poll() is None):
            threading.Thread(target=self._open_tunnel, name="kami-tunnel", daemon=True).start()
        return self.status()

    def stop(self) -> None:
        with self.lock:
            self.room = None
            t, self.tunnel = self.tunnel, None
            self.public, self.tunnel_state = "", "off"
        if t and t.poll() is None:
            t.terminate()

    @property
    def port(self) -> int:
        return self.httpd.server_address[1] if self.httpd else 0

    def status(self) -> dict[str, Any]:
        r = self.room
        local = f"http://127.0.0.1:{self.port}/{r.id}/" if r else ""
        return {"on": bool(r), "local": local, "url": (self.public + f"/{r.id}/") if (r and self.public) else "",
                "tunnel": self.tunnel_state, "error": self.tunnel_error,
                "people": [p["name"] for k, p in (r.people.items() if r else []) if k != "host"]}

    # ---- cloudflared
    def _ensure_cf(self) -> str:
        if CF_EXE.exists() and CF_EXE.stat().st_size > 1_000_000:
            return str(CF_EXE)
        self.tunnel_state = "installing"
        CF_EXE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CF_EXE.with_suffix(".part")
        req = urllib.request.Request(CF_URL, headers={"User-Agent": "Kami"})
        with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
            while True:
                b = r.read(1 << 16)
                if not b:
                    break
                f.write(b)
        tmp.replace(CF_EXE)
        return str(CF_EXE)

    def _open_tunnel(self) -> None:
        try:
            exe = self._ensure_cf()
            self.tunnel_state, self.tunnel_error = "starting", ""
            p = subprocess.Popen([exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{self.port}"],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=NOWIN,
                                 text=True, encoding="utf-8", errors="replace")
            self.tunnel = p
            deadline = time.time() + 60
            for line in p.stdout:
                m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
                if m:
                    self.public, self.tunnel_state = m.group(0), "on"
                    log.info("Birlikte izle tuneli: %s", self.public)
                    break
                if time.time() > deadline:
                    raise RuntimeError("tunel adresi gelmedi")
            else:
                raise RuntimeError("cloudflared kapandi")
            threading.Thread(target=lambda: [None for _ in p.stdout], daemon=True).start()   # ciktiyi bosalt
        except Exception as exc:
            self.tunnel_state, self.tunnel_error = "error", str(exc)[:160]
            log.warning("Birlikte izle tuneli acilamadi: %s", exc)


def _handler(srv: WatchServer):
    page = (paths.WEB_DIR / "watch.html")

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _room(self) -> tuple[Room | None, list[str]]:
            seg = self.path.split("?", 1)[0].strip("/").split("/")
            r = srv.room
            if not r or not seg or not secrets.compare_digest(seg[0], r.id):
                return None, seg
            return r, seg[1:]

        def _json(self, obj: Any, code: int = 200) -> None:
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _err(self, code: int) -> None:
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            r, rest = self._room()
            if not r:
                return self._err(404)
            from urllib.parse import parse_qs, urlsplit
            q = parse_qs(urlsplit(self.path).query)
            try:
                if not rest or rest == [""]:
                    data = page.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(data)
                elif rest[0] == "info":
                    self._json(r.public_info())
                elif rest[0] == "poll":
                    pid = (q.get("id") or [""])[0][:40]
                    if pid:
                        r.touch(pid, (q.get("name") or ["Misafir"])[0])
                    self._json(r.snapshot(int((q.get("v") or ["0"])[0] or 0), int((q.get("n") or ["0"])[0] or 0), 20.0, pid))
                elif rest[0] == "font" and len(rest) == 2 and re.fullmatch(r"[A-Za-z-]+\.ttf", rest[1]):
                    f = paths.WEB_DIR / "fonts" / rest[1]
                    if not f.exists():
                        return self._err(404)
                    data = f.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "font/ttf")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "max-age=86400")
                    self.end_headers()
                    self.wfile.write(data)
                elif rest[0] == "m":
                    self._proxy(r, "/".join(rest[1:]), urlsplit(self.path).query)
                else:
                    self._err(404)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def do_POST(self):
            r, rest = self._room()
            if not r or rest != ["act"]:
                return self._err(404)
            n = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(min(n, 20000)) or b"{}")
            except ValueError:
                return self._err(400)
            pid, name = str(body.get("id", ""))[:40], str(body.get("name") or "Misafir")[:40]
            k = body.get("kind")
            if pid:
                r.touch(pid, name)
            if k == "state":
                r.set_state(bool(body.get("playing")), float(body.get("t") or 0), pid)
                r.say(name, ("oynattı" if body.get("playing") else "durdurdu") + f" · {_fmt(float(body.get('t') or 0))}", "sys")
            elif k == "chat":
                r.say(name, str(body.get("text", "")))
            self._json({"ok": True})

        def _proxy(self, r: Room, rest: str, query: str) -> None:
            url = f"{r.media_base}/{rest}" + (f"?{query}" if query else "")
            hdr = {"User-Agent": "Kami-watch"}
            if self.headers.get("Range"):
                hdr["Range"] = self.headers["Range"]
            try:
                up = urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=60)
            except urllib.error.HTTPError as e:
                return self._err(e.code)
            except Exception:
                return self._err(502)
            with up:
                self.send_response(up.status)
                for h in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"):
                    if up.headers.get(h):
                        self.send_header(h, up.headers[h])
                chunked = not up.headers.get("Content-Length")
                if chunked:
                    self.send_header("Transfer-Encoding", "chunked")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                while True:
                    b = up.read(1 << 16)
                    if not b:
                        break
                    if chunked:
                        self.wfile.write(f"{len(b):X}\r\n".encode() + b + b"\r\n")
                    else:
                        self.wfile.write(b)
                if chunked:
                    self.wfile.write(b"0\r\n\r\n")

    return H


def _fmt(t: float) -> str:
    t = int(t)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


SERVER = WatchServer()


def host_poll(since_v: int, since_n: int) -> dict[str, Any]:
    r = SERVER.room
    if not r:
        return {"on": False}
    r.touch("host", r.host_name)
    return {"on": True, **r.snapshot(since_v, since_n, 0.0), **{"status": SERVER.status()}}


def host_act(kind: str, playing: bool = False, t: float = 0.0, text: str = "") -> bool:
    r = SERVER.room
    if not r:
        return False
    if kind == "state":
        r.set_state(playing, t, "host")
    elif kind == "chat":
        r.say(r.host_name, text)
    return True

