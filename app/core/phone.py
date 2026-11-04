"""Telefondan gonder (Asama 6c): iPhone Paylas -> "Kami'ye gonder" Kisayolu -> ayni Wi-Fi'daki Kami.

- Yerel agda dinler (0.0.0.0:<port>), sadece ozel ag adreslerinden gelen istekleri kabul eder.
- Her istek gizli anahtar ister: "X-Kami-Key" basligi (Kisayol) ya da form alani "key" (tarayici sayfasi).
  Anahtar URL'ye YAZILMAZ; DPAPI ile saklanir (data/phone_key.bin). Sabit zamanli karsilastirma.
- POST /send  {"text": "<link(ler) ya da paylasilan metin>"}  -> metindeki linkler kuyruga.
- GET  /      kucuk mobil sayfa (Kisayol yoksa Safari'den yapistir-gonder; anahtar telefonda localStorage'da).
Dakikada en fazla 30 istek; govde en fazla 64 KB.
"""
from __future__ import annotations

import hmac
import ipaddress
import json
import logging
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs

log = logging.getLogger(__name__)

MAX_BODY = 64 * 1024

PAGE = """<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Kami</title>
<style>body{font:16px -apple-system,system-ui,sans-serif;background:#15111C;color:#E7E2EF;margin:0;padding:20px}
h1{font-size:20px;color:#9D6BFF}textarea,input{width:100%;box-sizing:border-box;font:inherit;padding:10px;border-radius:8px;
border:1px solid #2A2236;background:#0D0A12;color:inherit;margin:6px 0 12px}button{width:100%;padding:12px;border:0;border-radius:8px;
background:#7C4DFF;color:#fff;font:600 16px inherit}#r{margin-top:12px}</style></head><body>
<h1>Kami'ye gönder</h1><form id="f"><label>Link</label><textarea id="t" rows="4" placeholder="Linki yapıştır"></textarea>
<label>Anahtar</label><input id="k" type="password" autocomplete="off" placeholder="Kami > Ayarlar'daki anahtar">
<button>Gönder</button></form><div id="r"></div>
<script>const k=document.getElementById('k');k.value=localStorage.kamiKey||'';
document.getElementById('f').onsubmit=async(e)=>{e.preventDefault();localStorage.kamiKey=k.value;
const r=await fetch('/send',{method:'POST',headers:{'Content-Type':'application/json','X-Kami-Key':k.value},
body:JSON.stringify({text:document.getElementById('t').value})}).then(x=>x.json()).catch(()=>({ok:false}));
document.getElementById('r').textContent=r.ok?('✓ '+r.added+' link Kami kuyruğunda'):('✕ '+(r.error||'bağlanamadı'));};</script>
</body></html>"""


def lan_ip() -> str:
    """Varsayilan rota arayuzunun yerel IP'si (paket gonderilmez: UDP connect sadece rota secer)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))   # TEST-NET-1, ulasilmaz; sadece kaynak adresi icin
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def new_key() -> str:
    return secrets.token_urlsafe(18)


class PhoneServer:
    def __init__(self, port: int, key: Callable[[], str], on_text: Callable[[str], int]) -> None:
        self.port = port
        self.key = key
        self.on_text = on_text            # metin -> kuyruga eklenen link sayisi
        self._srv: ThreadingHTTPServer | None = None
        self._hits: list[float] = []
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._srv is not None

    def _rate_ok(self) -> bool:
        now = time.monotonic()
        with self._lock:
            self._hits = [t for t in self._hits if now - t < 60]
            if len(self._hits) >= 30:
                return False
            self._hits.append(now)
            return True

    def start(self) -> bool:
        if self._srv:
            return True
        outer = self

        class H(BaseHTTPRequestHandler):
            server_version = "Kami"
            sys_version = ""

            def log_message(self, fmt, *args):   # erisim logu yazma (anahtar basliklari vb.)
                pass

            def _allowed(self) -> bool:
                try:
                    ip = ipaddress.ip_address(self.client_address[0])
                except ValueError:
                    return False
                return ip.is_private or ip.is_loopback or ip.is_link_local

            def _json(self, code: int, obj: dict[str, Any]) -> None:
                data = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if not self._allowed():
                    return self._json(403, {"ok": False, "error": "forbidden"})
                if self.path.split("?")[0] != "/":
                    return self._json(404, {"ok": False})
                data = PAGE.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                if not self._allowed():
                    return self._json(403, {"ok": False, "error": "forbidden"})
                if self.path.split("?")[0] != "/send":
                    return self._json(404, {"ok": False})
                if not outer._rate_ok():
                    return self._json(429, {"ok": False, "error": "rate"})
                n = int(self.headers.get("Content-Length") or 0)
                if n <= 0 or n > MAX_BODY:
                    return self._json(413, {"ok": False, "error": "size"})
                raw = self.rfile.read(n).decode("utf-8", "replace")
                ctype = (self.headers.get("Content-Type") or "").lower()
                if "json" in ctype:
                    try:
                        body = json.loads(raw)
                    except ValueError:
                        body = {"text": raw}
                elif "form" in ctype:
                    body = {k: v[0] for k, v in parse_qs(raw).items()}
                else:
                    body = {"text": raw}   # Kisayol "Dosya"/duz metin olarak da gonderebilir
                if not isinstance(body, dict):
                    body = {"text": str(body)}
                given = str(self.headers.get("X-Kami-Key") or body.get("key") or "")
                expected = outer.key()
                if not expected or not hmac.compare_digest(given.encode(), expected.encode()):
                    log.warning("Telefondan gonder: anahtar hatali (%s)", self.client_address[0])
                    return self._json(401, {"ok": False, "error": "key"})
                text = str(body.get("text") or body.get("url") or "")[:MAX_BODY]
                try:
                    added = outer.on_text(text)
                except Exception:
                    log.exception("Telefondan gelen link eklenemedi")
                    return self._json(500, {"ok": False, "error": "internal"})
                return self._json(200, {"ok": added > 0, "added": added, "error": "" if added else "no_link"})

        try:
            self._srv = ThreadingHTTPServer(("0.0.0.0", self.port), H)
        except OSError as exc:
            log.warning("Telefon sunucusu acilamadi (port %s): %s", self.port, exc)
            self._srv = None
            return False
        self._srv.daemon_threads = True
        threading.Thread(target=self._srv.serve_forever, name="kami-phone", daemon=True).start()
        log.info("Telefondan gonder: %s:%s dinleniyor", lan_ip(), self.port)
        return True

    def stop(self) -> None:
        if self._srv:
            self._srv.shutdown()
            self._srv.server_close()
            self._srv = None
