"""Telefondan gonder (Asama 6c, 05.11 duzeltmesi): iPhone Paylas -> "Kami'ye gonder" Kestirmesi -> ayni agdaki Kami.

- Yerel agda dinler (0.0.0.0:<port>), sadece ozel ag adreslerinden gelen istekleri kabul eder.
- Anahtarli uclar "X-Kami-Key" basligi (Kestirme) ya da govdede "key" alani (tarayici sayfasi) ister.
  Anahtar URL'ye YAZILMAZ; DPAPI ile saklanir (data/phone_key.bin). Sabit zamanli karsilastirma.
- POST /send   govde: JSON (ic ice sozluk/dizi), form, duz metin - HEPSINDE ilk http(s)/magnet linkleri aranir
               (YouTube paylasimi "text" alaninda link vermeyebilir; tum govde taranir). Her istek LOGLANIR
               (anahtar haric: govde turu, alanlar, kisa ozet, sonuc).
               Yanit: Kestirme icin okunur Turkce metin ("Kuyruga eklendi: ..." / "Link bulunamadi: gelen icerik ...").
- GET  /       mobil sayfa: link gonder + baglanti testi + indirme durumu ekrani.
- GET  /test   anahtarsiz baglanti testi (tarayicidan acilir): "Kami'ye ulasildi".
- GET  /status anahtarli: aktif/son indirmeler (ad, yuzde, hiz). POST /control {id, action: pause|resume}.
Dakikada en fazla 60 istek; govde en fazla 64 KB.
"""
from __future__ import annotations

import hmac
import ipaddress
import json
import logging
import re
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs

log = logging.getLogger(__name__)

MAX_BODY = 64 * 1024
LINK_RE = re.compile(r"""(?:https?://|magnet:\?)[^\s<>"'`{}|\\^\[\]]+""", re.I)

PAGE = """<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Kami</title>
<style>body{font:16px -apple-system,system-ui,sans-serif;background:#15111C;color:#E7E2EF;margin:0;padding:18px}
h1{font-size:20px;color:#9D6BFF;margin:4px 0 12px}h2{font-size:16px;color:#C9B3FF;margin:22px 0 8px}
textarea,input{width:100%;box-sizing:border-box;font:inherit;padding:10px;border-radius:8px;border:1px solid #2A2236;
background:#0D0A12;color:inherit;margin:6px 0 10px}button{width:100%;padding:12px;border:0;border-radius:8px;
background:#7C4DFF;color:#fff;font:600 16px inherit;margin-bottom:8px}button.g{background:#1D1727;color:#C9B3FF}
.r{margin:6px 0 4px;min-height:1.2em}.it{background:#1D1727;border-radius:8px;padding:10px;margin:6px 0}
.it b{display:block;font-size:14px;word-break:break-all}.bar{height:5px;background:#2A2236;border-radius:3px;margin:6px 0}
.bar i{display:block;height:100%;background:#9D6BFF;border-radius:3px}.it small{color:#9A91AB}
.it button{width:auto;padding:6px 12px;font-size:13px;margin:6px 0 0}</style></head><body>
<h1>Kami'ye gönder</h1><form id="f"><textarea id="t" rows="3" placeholder="Linki yapıştır"></textarea>
<input id="k" type="password" autocomplete="off" placeholder="Anahtar (Kami > Ayarlar > Telefon)">
<button>Gönder</button></form><div class="r" id="r"></div>
<button class="g" id="tb">Bağlantı testi</button><div class="r" id="tr"></div>
<h2>İndirme durumu</h2><div id="st"><small>Anahtarı girince görünür.</small></div>
<script>const $=(i)=>document.getElementById(i),k=$('k');k.value=localStorage.kamiKey||'';
const H=()=>({'Content-Type':'application/json','X-Kami-Key':k.value,'Accept':'application/json'});
const esc=(s)=>String(s).replace(/[&<>"]/g,(c)=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
$('f').onsubmit=async(e)=>{e.preventDefault();localStorage.kamiKey=k.value;
const r=await fetch('/send',{method:'POST',headers:H(),body:JSON.stringify({text:$('t').value})}).then(x=>x.json()).catch(()=>({message:'✕ Kami\\'ye bağlanılamadı'}));
$('r').textContent=r.message||'';if(r.ok){$('t').value='';load();}};
$('tb').onclick=async()=>{$('tr').textContent='…';const t0=Date.now();
const r=await fetch('/test',{headers:{'Accept':'application/json'}}).then(x=>x.json()).catch(()=>null);
$('tr').textContent=r?('✓ Kami\\'ye ulaşıldı ('+r.host+', '+(Date.now()-t0)+' ms)'):'✕ Ulaşılamadı';};
async function load(){if(!k.value)return;localStorage.kamiKey=k.value;
const r=await fetch('/status',{headers:H()}).then(x=>x.json()).catch(()=>null);
if(!r||!r.ok){$('st').innerHTML='<small>'+esc(r&&r.message||'Durum alınamadı')+'</small>';return;}
$('st').innerHTML=r.items.length?r.items.map(d=>'<div class="it"><b>'+esc(d.name)+'</b><div class="bar"><i style="width:'+d.percent+'%"></i></div><small>'+esc(d.label)+'</small>'+
(d.can_pause?'<button data-a="pause" data-i="'+d.id+'">Duraklat</button>':'')+(d.can_resume?'<button data-a="resume" data-i="'+d.id+'">Devam</button>':'')+'</div>').join(''):'<small>Şu an indirme yok.</small>';}
$('st').onclick=async(e)=>{const b=e.target.closest('button');if(!b)return;
await fetch('/control',{method:'POST',headers:H(),body:JSON.stringify({id:+b.dataset.i,action:b.dataset.a})});load();};
k.onchange=load;load();setInterval(load,3000);</script>
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


def lan_ips() -> list[str]:
    """Bilgisayarin TUM ozel IPv4 adresleri (Ethernet + Wi-Fi); varsayilan rota adresi once."""
    out = [lan_ip()]
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in out:
                out.append(ip)
    except OSError:
        pass
    keep = []
    for ip in out:
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if a.is_private and not a.is_loopback and not a.is_link_local:
            keep.append(ip)
    return keep or ["127.0.0.1"]


def new_key() -> str:
    return secrets.token_urlsafe(18)


def find_links(body: Any, raw: str = "") -> list[str]:
    """Govdenin TAMAMINDA (ic ice JSON, dizi, form, duz metin) linkleri sirayla bulur; 'key' alani atlanir."""
    found: list[str] = []

    def walk(v: Any) -> None:
        if isinstance(v, dict):
            for k, x in v.items():
                if str(k).lower() not in ("key", "x-kami-key"):
                    walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
        elif v is not None:
            for m in LINK_RE.finditer(str(v)):
                found.append(m.group(0).rstrip(".,;:!?)»”’"))

    walk(body)
    if not found and raw:   # govde cozulemediyse ham metin
        walk(raw)
    return list(dict.fromkeys(found))


def describe(body: Any, ctype: str, n: int) -> str:
    """Log + hata mesaji icin govde ozeti (anahtar gizli)."""
    def red(v: Any) -> Any:
        if isinstance(v, dict):
            return {k: ("***" if str(k).lower() in ("key", "x-kami-key") else red(x)) for k, x in v.items()}
        if isinstance(v, list):
            return [red(x) for x in v[:5]]
        s = str(v)
        return s if len(s) <= 80 else s[:80] + "…"
    kind = type(body).__name__
    keys = list(body.keys())[:8] if isinstance(body, dict) else []
    return f"tür={ctype or '-'} boyut={n} gövde={kind} alanlar={keys} özet={json.dumps(red(body), ensure_ascii=False)[:200]}"


class PhoneServer:
    def __init__(self, port: int, key: Callable[[], str], on_text: Callable[[str], Any],
                 status: Callable[[], list[dict[str, Any]]] = lambda: [],
                 control: Callable[[int, str], bool] = lambda i, a: False) -> None:
        self.port = port
        self.key = key
        self.on_text = on_text            # metin -> eklenen link sayisi (int) ya da {added, links}
        self.status = status
        self.control = control
        self._srv: ThreadingHTTPServer | None = None
        self._hits: list[float] = []
        self._lock = threading.Lock()
        self.last: dict[str, Any] = {}    # son /send (Ayarlar'da gosterilir)

    @property
    def running(self) -> bool:
        return self._srv is not None

    def _rate_ok(self) -> bool:
        now = time.monotonic()
        with self._lock:
            self._hits = [t for t in self._hits if now - t < 60]
            if len(self._hits) >= 60:
                return False
            self._hits.append(now)
            return True

    def handle_send(self, raw: str, ctype: str, header_key: str, client: str) -> tuple[int, dict[str, Any]]:
        """/send mantigi (HTTP'den bagimsiz, test edilebilir). -> (kod, yanit)"""
        ctype = (ctype or "").lower()
        body: Any
        if "json" in ctype or raw.lstrip()[:1] in ("{", "["):
            try:
                body = json.loads(raw)
            except ValueError:
                body = {"text": raw}
        elif "form" in ctype:
            body = {k: v[0] if len(v) == 1 else v for k, v in parse_qs(raw).items()}
        else:
            body = {"text": raw}   # Kestirme "Dosya"/duz metin olarak da gonderebilir
        desc = describe(body, ctype, len(raw))
        given = header_key or (str(body.get("key") or "") if isinstance(body, dict) else "")
        expected = self.key()
        if not expected or not hmac.compare_digest(given.encode(), expected.encode()):
            log.warning("Telefon /send REDDEDILDI (anahtar hatali/eksik) ip=%s %s", client, desc)
            self.last = {"t": time.time(), "ok": False, "error": "key", "ip": client}
            return 401, {"ok": False, "error": "key",
                         "message": "✕ Anahtar yanlış ya da eksik. Kestirme'de üstbilgi adı X-Kami-Key olmalı, "
                                    "değeri Kami > Ayarlar > Telefon'daki anahtar."}
        links = find_links(body, raw)
        if not links:
            log.warning("Telefon /send: link YOK ip=%s %s", client, desc)
            self.last = {"t": time.time(), "ok": False, "error": "no_link", "ip": client, "desc": desc}
            preview = desc.split("özet=", 1)[-1][:120]
            return 200, {"ok": False, "added": 0, "error": "no_link",
                         "message": f"✕ Link bulunamadı: gelen içerik {preview}. Kestirme'ye \"Girdideki URL'leri Al\" "
                                    "adımını ekleyip gövdeye o URL'leri koy."}
        try:
            res = self.on_text("\n".join(links))
        except Exception:
            log.exception("Telefondan gelen link eklenemedi")
            return 500, {"ok": False, "error": "internal", "message": "✕ Kami linki ekleyemedi (log'a bak)."}
        added = int(res.get("added", 0)) if isinstance(res, dict) else int(res or 0)
        log.info("Telefon /send: ip=%s %s linkler=%s eklendi=%d", client, desc, links[:3], added)
        self.last = {"t": time.time(), "ok": added > 0, "ip": client, "added": added, "link": links[0]}
        if not added:
            return 200, {"ok": False, "added": 0, "error": "not_added",
                         "message": f"✕ Link eklenemedi: {links[0][:120]}"}
        names = (res.get("names") if isinstance(res, dict) else None) or links
        more = f" (+{added - 1})" if added > 1 else ""
        return 200, {"ok": True, "added": added, "error": "", "message": f"✓ Kuyruğa eklendi: {names[0][:120]}{more}"}

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

            def _wants_text(self) -> bool:
                """Kestirmeler okunur metin gostersin: tarayici/fetch JSON ister, Kestirme genelde istemez."""
                acc = (self.headers.get("Accept") or "").lower()
                ua = (self.headers.get("User-Agent") or "")
                return "json" not in acc and "Safari" not in ua and "Mozilla" not in ua

            def _send(self, code: int, obj: dict[str, Any]) -> None:
                if self._wants_text() and "message" in obj:
                    data, ctype = str(obj["message"]).encode(), "text/plain; charset=utf-8"
                else:
                    data, ctype = json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8"
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def _key_ok(self) -> bool:
                exp = outer.key()
                got = str(self.headers.get("X-Kami-Key") or "")
                return bool(exp) and hmac.compare_digest(got.encode(), exp.encode())

            def _html(self, html: str) -> None:
                data = html.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if not self._allowed():
                    return self._send(403, {"ok": False, "error": "forbidden", "message": "✕ Sadece yerel ağ."})
                path = self.path.split("?")[0]
                if path == "/":
                    return self._html(PAGE)
                if path in ("/test", "/send"):   # tarayicidan acilinca baglanti testi
                    log.info("Telefon baglanti testi: ip=%s yol=%s", self.client_address[0], path)
                    info = {"ok": True, "host": socket.gethostname(), "time": time.strftime("%H:%M:%S"),
                            "message": f"✓ Kami'ye ulaşıldı ({socket.gethostname()}, {time.strftime('%H:%M:%S')})."
                                       " Link göndermek için POST /send kullan."}
                    if "json" in (self.headers.get("Accept") or "").lower():
                        return self._send(200, info)
                    return self._html(f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
                                      f"<body style='font:18px system-ui;background:#15111C;color:#E7E2EF;padding:20px'>"
                                      f"<h2 style='color:#9D6BFF'>{info['message']}</h2><p><a style='color:#C9B3FF' href='/'>"
                                      f"Gönderme sayfası + indirme durumu</a></p>")
                if path == "/status":
                    if not self._key_ok():
                        return self._send(401, {"ok": False, "error": "key", "message": "Anahtar yanlış ya da eksik."})
                    try:
                        items = outer.status()
                    except Exception:
                        log.exception("Telefon durum")
                        items = []
                    return self._send(200, {"ok": True, "items": items})
                return self._send(404, {"ok": False, "message": "✕ Böyle bir adres yok."})

            def do_POST(self):
                client = self.client_address[0]
                if not self._allowed():
                    log.warning("Telefon: yerel ag disi istek reddedildi ip=%s", client)
                    return self._send(403, {"ok": False, "error": "forbidden", "message": "✕ Sadece yerel ağ."})
                path = self.path.split("?")[0]
                if path not in ("/send", "/control"):
                    return self._send(404, {"ok": False, "message": "✕ Böyle bir adres yok."})
                if not outer._rate_ok():
                    return self._send(429, {"ok": False, "error": "rate", "message": "✕ Çok sık istek, biraz bekle."})
                n = int(self.headers.get("Content-Length") or 0)
                if n <= 0 or n > MAX_BODY:
                    log.warning("Telefon %s: gecersiz govde boyutu %s ip=%s", path, n, client)
                    return self._send(413, {"ok": False, "error": "size",
                                            "message": "✕ Gövde boş ya da çok büyük. Kestirme'de İstek Gövdesi: JSON."})
                raw = self.rfile.read(n).decode("utf-8", "replace")
                if path == "/control":
                    if not self._key_ok():
                        return self._send(401, {"ok": False, "error": "key"})
                    try:
                        b = json.loads(raw)
                        ok = outer.control(int(b.get("id")), str(b.get("action")))
                    except (ValueError, TypeError, AttributeError):
                        ok = False
                    return self._send(200, {"ok": bool(ok)})
                code, obj = outer.handle_send(raw, self.headers.get("Content-Type") or "",
                                              str(self.headers.get("X-Kami-Key") or ""), client)
                return self._send(code, obj)

        try:
            self._srv = ThreadingHTTPServer(("0.0.0.0", self.port), H)
        except OSError as exc:
            log.warning("Telefon sunucusu acilamadi (port %s): %s", self.port, exc)
            self._srv = None
            return False
        self._srv.daemon_threads = True
        threading.Thread(target=self._srv.serve_forever, name="kami-phone", daemon=True).start()
        log.info("Telefondan gonder: %s port %s dinleniyor", ", ".join(lan_ips()), self.port)
        return True

    def stop(self) -> None:
        if self._srv:
            self._srv.shutdown()
            self._srv.server_close()
            self._srv = None
