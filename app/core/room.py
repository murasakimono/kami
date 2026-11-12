"""Kami Oda: Discord benzeri sesli oda + ekran paylasimi + Oynatici yayini (WebRTC).

- Yerel sunucu (127.0.0.1) /<oda>/ altinda: oda sayfasi (room.html), sinyal (uzun yoklama), sohbet, ICE (TURN).
- Ses/goruntu WebRTC ile dogrudan cihazlar arasinda (mesh, 2-5 kisi). Dogrudan olmazsa Cloudflare TURN rolesi.
- Disariya Cloudflare quick tunnel (cloudflared, hesap gerekmez): https://<rastgele>.trycloudflare.com/<oda>/
- TURN anahtari (Turn Token ID + API Token) DPAPI ile saklanir; tarayiciya yalnizca kisa omurlu kimlik verilir.
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
from typing import Any, Callable

from app import paths

log = logging.getLogger("kami")
NOWIN = 0x08000000 if os.name == "nt" else 0
CF_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
CF_EXE = paths.DATA_DIR / "tools" / "cloudflared.exe"
STUN = [{"urls": ["stun:stun.cloudflare.com:3478", "stun:stun.l.google.com:19302"]}]
STATIC = {   # oda sayfasinin kullandigi dosyalar (WEB_DIR altinda)
    "room.js": "room.js", "room-core.js": "room-core.js", "room.css": "room.css", "ns.js": "vendor/ns/ns.js",
    "rnnoise-worklet.js": "vendor/ns/rnnoise-worklet.js", "rnnoise.wasm": "vendor/ns/rnnoise.wasm",
    "rnnoise_simd.wasm": "vendor/ns/rnnoise_simd.wasm",
    "icon-192.png": "room-icon-192.png", "icon-512.png": "room-icon-512.png",
}
MIME = {".png": "image/png", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".wasm": "application/wasm",
        ".ttf": "font/ttf", ".html": "text/html; charset=utf-8"}


class Room:
    def __init__(self, host_name: str, room_id: str = "") -> None:
        self.id = room_id or secrets.token_urlsafe(9)
        self.host_name = host_name
        self.events: list[dict[str, Any]] = []           # sohbet + sistem satirlari
        self.seq = 0
        self.peers: dict[str, dict[str, Any]] = {}       # id -> {name, kind, seen, muted, deaf, sharing, q}
        self.cv = threading.Condition()
        self.on_join: Callable[[str], None] | None = None

    def say(self, who: str, text: str, kind: str = "chat") -> None:
        text = str(text or "").strip()[:800]
        if not text:
            return
        with self.cv:
            self.seq += 1
            self.events.append({"n": self.seq, "who": who[:40], "text": text, "kind": kind, "t": time.time()})
            self.events = self.events[-300:]
            self.cv.notify_all()

    def touch(self, pid: str, name: str, kind: str = "user") -> None:
        with self.cv:
            p = self.peers.get(pid)
            new = p is None
            if new:
                p = self.peers[pid] = {"name": name[:40] or "Misafir", "kind": kind, "seen": time.time(), "muted": False,
                                       "deaf": False, "sharing": "", "q": [], "joined": time.time()}
            else:
                p["seen"] = time.time()
                p["name"] = name[:40] or p["name"]
            self.cv.notify_all()
        if new and kind == "user":
            self.say(p["name"], "odaya girdi", "sys")
            if self.on_join:
                try:
                    self.on_join(p["name"])
                except Exception:
                    log.exception("oda katilim bildirimi")

    def leave(self, pid: str) -> None:
        with self.cv:
            p = self.peers.pop(pid, None)
            self.cv.notify_all()
        if p and p["kind"] == "user":
            self.say(p["name"], "ayrıldı", "sys")

    def set_me(self, pid: str, **kw: Any) -> None:
        with self.cv:
            p = self.peers.get(pid)
            if p:
                for k in ("muted", "deaf", "sharing"):
                    if k in kw:
                        p[k] = kw[k]
                self.cv.notify_all()

    def signal(self, frm: str, to: str, data: Any) -> bool:
        with self.cv:
            p = self.peers.get(to)
            if not p:
                return False
            p["q"].append({"from": frm, "data": data})
            p["q"] = p["q"][-400:]
            self.cv.notify_all()
            return True

    def _roster(self) -> list[dict[str, Any]]:
        return [{"id": k, "name": p["name"], "kind": p["kind"], "muted": p["muted"], "deaf": p["deaf"],
                 "sharing": p["sharing"]} for k, p in sorted(self.peers.items(), key=lambda kv: kv[1]["joined"])]

    def poll(self, pid: str, since_n: int, roster_v: str, wait: float) -> dict[str, Any]:
        end = time.time() + wait
        with self.cv:
            while True:
                me = self.peers.get(pid)
                sig = me["q"] if me else []
                ros = self._roster()
                rv = str(abs(hash(json.dumps([[r["id"], r["name"], r["muted"], r["deaf"], r["sharing"]] for r in ros]))))
                if sig or self.seq > since_n or rv != roster_v or time.time() >= end:
                    break
                self.cv.wait(max(0.05, end - time.time()))
            if me:
                me["q"] = []
                me["seen"] = time.time()
            now = time.time()
            for k in [k for k, p in self.peers.items() if now - p["seen"] > 40]:   # kopanlar
                nm, kind = self.peers[k]["name"], self.peers[k]["kind"]
                del self.peers[k]
                if kind == "user":
                    self.seq += 1
                    self.events.append({"n": self.seq, "who": nm, "text": "bağlantısı koptu", "kind": "sys", "t": now})
            return {"signals": sig, "events": [e for e in self.events if e["n"] > since_n], "roster": ros, "rv": rv,
                    "now": now, "host": self.host_name}


class RoomServer:
    def __init__(self) -> None:
        self.room: Room | None = None
        self.httpd = None
        self.tunnel: subprocess.Popen | None = None
        self.public = ""
        self.tunnel_state = "off"          # off | installing | starting | on | error
        self.tunnel_error = ""
        self.lock = threading.Lock()
        self.turn_key: Callable[[], tuple[str, str]] = lambda: ("", "")
        self._ice: tuple[float, list] = (0.0, [])
        self.stable: Callable[[], tuple[str, str]] = lambda: ("", "")   # (workers.dev adresi, gizli anahtar)
        self.on_join: Callable[[str], None] | None = None

    def start(self, host_name: str, tunnel: bool = True, room_id: str = "") -> dict[str, Any]:
        with self.lock:
            if not self.room:
                self.room = Room(host_name, room_id)
                self.room.on_join = self.on_join
            if not self.httpd:
                from app.core.net import ExclusiveHTTPServer
                self.httpd = ExclusiveHTTPServer.make(("127.0.0.1", 0), _handler(self))
                self.httpd.daemon_threads = True
                threading.Thread(target=self.httpd.serve_forever, name="kami-room", daemon=True).start()
        if tunnel and not (self.tunnel and self.tunnel.poll() is None):
            threading.Thread(target=self._open_tunnel, name="kami-tunnel", daemon=True).start()
        return self.status()

    def stop(self) -> None:
        threading.Thread(target=self._publish, args=("",), daemon=True).start()
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
        base = self.stable()[0].rstrip("/")
        url = ""
        if r and self.public:
            url = f"{base}/{r.id}/" if base and self.published else self.public + f"/{r.id}/"
        return {"on": bool(r), "local": local, "url": url, "stable": bool(base and self.published),
                "tunnel": self.tunnel_state, "error": self.tunnel_error,
                "people": [p["name"] for p in (list(r.peers.values()) if r else []) if p["kind"] == "user"],
                "turn": bool(self.turn_key()[0])}

    # ---- ICE: STUN + Cloudflare TURN (kisa omurlu kimlik, 12 sa onbellek)
    def ice(self) -> list[dict[str, Any]]:
        kid, tok = self.turn_key()
        if not kid or not tok:
            return STUN
        t, cached = self._ice
        if cached and time.time() - t < 12 * 3600:
            return cached
        try:
            req = urllib.request.Request(f"https://rtc.live.cloudflare.com/v1/turn/keys/{kid}/credentials/generate-ice-servers",
                                         data=json.dumps({"ttl": 86400}).encode(), method="POST",
                                         headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json",
                                                  "User-Agent": "Kami/1.6 (+github.com/murasakimono/kami)"})
            with urllib.request.urlopen(req, timeout=10) as r:
                servers = json.loads(r.read()).get("iceServers") or []
            out = []
            for s in servers if isinstance(servers, list) else [servers]:
                raw = s.get("urls")
                urls = [u for u in (raw if isinstance(raw, list) else [raw]) if u and ":53?" not in u and not u.endswith(":53")]
                if urls:
                    out.append({**s, "urls": urls})
            self._ice = (time.time(), out or STUN)
            return self._ice[1]
        except Exception as exc:
            log.warning("TURN kimligi alinamadi: %s", exc)
            return STUN

    def test_turn(self) -> dict[str, Any]:
        self._ice = (0.0, [])
        s = self.ice()
        return {"ok": any("turn:" in json.dumps(x) for x in s), "servers": len(s)}

    published = False

    def _publish(self, target: str) -> None:
        """Sabit adrese (Cloudflare Worker) guncel tunel adresini bildirir."""
        base, key = self.stable()
        if not base or not key:
            return
        for _ in range(5):
            try:
                req = urllib.request.Request(base.rstrip("/") + "/_kami/set", method="POST",
                                             data=json.dumps({"target": target, "host": self.room.host_name if self.room else ""}).encode(),
                                             headers={"Content-Type": "application/json", "x-kami-key": key, "User-Agent": "Kami"})
                with urllib.request.urlopen(req, timeout=10):
                    pass
                self.published = bool(target)
                log.info("Kami Oda sabit adresi guncellendi")
                return
            except Exception as exc:
                log.warning("Sabit adres guncellenemedi: %s", exc)
                time.sleep(3)

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
                    log.info("Kami Oda tuneli: %s", self.public)
                    self._publish(self.public)
                    break
                if time.time() > deadline:
                    raise RuntimeError("tunel adresi gelmedi")
            else:
                raise RuntimeError("cloudflared kapandi")
            threading.Thread(target=lambda: [None for _ in p.stdout], daemon=True).start()   # ciktiyi bosalt
        except Exception as exc:
            self.tunnel_state, self.tunnel_error = "error", str(exc)[:160]
            log.warning("Kami Oda tuneli acilamadi: %s", exc)


def _handler(srv: RoomServer):
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

        def end_headers(self):   # Kami Player (file://) yayinci olarak baglanabilsin
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            super().end_headers()

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _send(self, data: bytes, ctype: str, cache: str = "no-store", code: int = 200) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", cache)
            self.end_headers()
            self.wfile.write(data)

        def _json(self, obj: Any, code: int = 200) -> None:
            self._send(json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", code=code)

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
                    self._send((paths.WEB_DIR / "room.html").read_bytes(), MIME[".html"])
                elif rest[0] == "manifest.webmanifest":
                    m = {"name": "Kami Oda", "short_name": "Kami Oda", "start_url": "./", "scope": "./", "display": "standalone",
                         "background_color": "#07060B", "theme_color": "#07060B", "orientation": "any",
                         "icons": [{"src": "s/icon-192.png", "sizes": "192x192", "type": "image/png"},
                                   {"src": "s/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}]}
                    self._send(json.dumps(m).encode(), "application/manifest+json")
                elif rest[0] == "info":
                    self._json({"host": r.host_name, "id": r.id})
                elif rest[0] == "ice":
                    self._json({"iceServers": srv.ice()})
                elif rest[0] == "poll":
                    pid = (q.get("id") or [""])[0][:40]
                    if not pid:
                        return self._err(400)
                    r.touch(pid, (q.get("name") or ["Misafir"])[0], (q.get("kind") or ["user"])[0][:10])
                    self._json(r.poll(pid, int((q.get("n") or ["0"])[0] or 0), (q.get("rv") or [""])[0], 20.0))
                elif rest[0] == "s" and len(rest) == 2 and rest[1] in STATIC:
                    f = paths.WEB_DIR / STATIC[rest[1]]
                    self._send(f.read_bytes(), MIME.get(f.suffix, "application/octet-stream"), "max-age=300")
                elif rest[0] == "font" and len(rest) == 2 and re.fullmatch(r"[A-Za-z-]+\.ttf", rest[1]):
                    f = paths.WEB_DIR / "fonts" / rest[1]
                    if not f.exists():
                        return self._err(404)
                    self._send(f.read_bytes(), "font/ttf", "max-age=86400")
                else:
                    self._err(404)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def do_POST(self):
            r, rest = self._room()
            if not r or len(rest) != 1:
                return self._err(404)
            n = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(min(n, 200000)) or b"{}")
            except ValueError:
                return self._err(400)
            pid = str(body.get("id", ""))[:40]
            if not pid:
                return self._err(400)
            k = rest[0]
            if k == "sig":
                return self._json({"ok": r.signal(pid, str(body.get("to", ""))[:40], body.get("data"))})
            if k == "chat":
                p = r.peers.get(pid)
                r.say(p["name"] if p else "Misafir", str(body.get("text", "")))
            elif k == "me":
                r.set_me(pid, **{x: body[x] for x in ("muted", "deaf", "sharing") if x in body})
            elif k == "leave":
                r.leave(pid)
            else:
                return self._err(404)
            self._json({"ok": True})

    return H


SERVER = RoomServer()
