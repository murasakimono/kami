"""Kami Kapsul: bir dosya icin sureli, istege bagli sifreli ve indirme sinirli paylasim linki.

Dosya bilgisayardan cikmaz: Kami Oda'nin tuneli (ve varsa sabit Worker adresi) uzerinden /c/<kimlik> yolundan sunulur.
Sayfa onizleme gosterir (gorsel, video/ses akisi Range destekli), sure dolunca ya da silinince link olur.
Sifrenin kendisi saklanmaz; sha256 ozeti tutulur, sayfa yazilan sifrenin ozetini gonderir.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import json
import logging
import mimetypes
import os
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

from app import paths

log = logging.getLogger(__name__)
_LOCK = threading.Lock()
_BAD: dict[str, list[float]] = {}
MAX_HOURS = 24 * 30
ON_EVENT = None   # (tur, kapsul_adi, ayrinti) -> masaustu bildirimi (api baglar): "dl" | "comment"


def _notify(kind: str, it: dict[str, Any], detail: str = "") -> None:
    if ON_EVENT:
        try:
            ON_EVENT(kind, it.get("name", ""), detail)
        except Exception:
            log.exception("kapsul bildirimi")


def _store() -> Path:
    return paths.DATA_DIR / "kapsul.json"


def _load() -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(_store().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(items: dict[str, dict[str, Any]]) -> None:
    tmp = _store().with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(_store())


def _prune(items: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    now = time.time()
    return {k: v for k, v in items.items()
            if v.get("expires", 0) > now and (not v.get("max_dl") or v.get("downloads", 0) < v["max_dl"])}


def create(path: str | list[str], hours: float = 24, password: str = "", max_dl: int = 0, note: str = "") -> dict[str, Any]:
    """Tek dosya ya da birden fazla dosya (tek link, dosya listesi + hepsini zip)."""
    paths_ = [path] if isinstance(path, str) else list(path or [])
    files = [Path(x) for x in paths_ if x and Path(x).is_file()]
    if not files:
        return {"ok": False, "error": "Dosya bulunamadi"}
    hours = max(0.25, min(float(hours or 24), MAX_HOURS))
    cid = secrets.token_urlsafe(9)
    p = files[0]
    item = {"path": str(p), "name": p.name if len(files) == 1 else f"{len(files)} dosya ({p.name}…)",
            "size": sum(f.stat().st_size for f in files), "created": time.time(),
            "expires": time.time() + hours * 3600, "pw": hashlib.sha256(password.encode("utf-8")).hexdigest() if password else "",
            "max_dl": max(0, int(max_dl or 0)), "downloads": 0, "note": str(note or "")[:200], "comments": []}
    if len(files) > 1:
        item["files"] = [{"path": str(f), "name": f.name, "size": f.stat().st_size} for f in files[:200]]
    with _LOCK:
        items = _prune(_load())
        items[cid] = item
        _save(items)
    return {"ok": True, "id": cid, **public(cid, item)}


def add_comment(cid: str, name: str, text: str, ip: str) -> bool:
    name, text = str(name or "Misafir").strip()[:40] or "Misafir", str(text or "").strip()[:500]
    if not text:
        return False
    now = time.time()
    hits = [t for t in _BAD.get("c:" + ip, []) if now - t < 60]
    if len(hits) >= 6:   # dakikada 6 yorum
        return False
    _BAD["c:" + ip] = hits + [now]
    with _LOCK:
        items = _load()
        it = items.get(cid)
        if not it:
            return False
        it.setdefault("comments", []).append({"name": name, "text": text, "t": now})
        it["comments"] = it["comments"][-100:]
        _save(items)
    _notify("comment", it, f"{name}: {text[:80]}")
    return True


def public(cid: str, it: dict[str, Any]) -> dict[str, Any]:
    return {"id": cid, "name": it["name"], "size": it["size"], "expires": it["expires"], "locked": bool(it.get("pw")),
            "max_dl": it.get("max_dl", 0), "downloads": it.get("downloads", 0), "path": it["path"],
            "files": len(it.get("files") or []) or 1, "comments": it.get("comments", [])[-20:]}


def list_all() -> list[dict[str, Any]]:
    with _LOCK:
        items = _prune(_load())
        _save(items)
    return sorted((public(k, v) for k, v in items.items()), key=lambda x: -x["expires"])


def delete(cid: str) -> bool:
    with _LOCK:
        items = _load()
        ok = items.pop(cid, None) is not None
        _save(items)
    return ok


def get(cid: str) -> dict[str, Any] | None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,40}", cid or ""):
        return None
    with _LOCK:
        it = _prune(_load()).get(cid)
    if it and not any(os.path.isfile(f["path"]) for f in (it.get("files") or [{"path": it["path"]}])):
        return None
    return it


def pw_ok(it: dict[str, Any], given: str, ip: str) -> bool:
    if not it.get("pw"):
        return True
    now = time.time()
    hits = [t for t in _BAD.get(ip, []) if now - t < 60]
    if len(hits) >= 10:
        _BAD[ip] = hits
        return False
    if given and hmac.compare_digest(given.lower().encode(), it["pw"].encode()):
        return True
    hits.append(now)
    _BAD[ip] = hits[-20:]
    return False


def count_download(cid: str, what: str = "") -> None:
    with _LOCK:
        items = _load()
        it = items.get(cid)
        if it:
            it["downloads"] = it.get("downloads", 0) + 1
            _save(items)
    if it:
        _notify("dl", it, what)


def _fmt_size(n: float) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


def page(cid: str, it: dict[str, Any], host: str = "") -> str:
    """Paylasim sayfasi (Kami gorunumu, harici kaynak yok)."""
    mime = mimetypes.guess_type(it["name"])[0] or ""
    kind = "image" if mime.startswith("image/") else "video" if mime.startswith("video/") else "audio" if mime.startswith("audio/") else ""
    name = html.escape(it["name"])
    left = max(0, int(it["expires"] - time.time()))
    note = html.escape(it.get("note") or "")
    files = it.get("files") or []
    multi = len(files) > 1
    if multi:
        kind = ""
    cms = "".join(f'<div class="cmi"><b>{html.escape(c["name"])}</b>{html.escape(c["text"])}</div>' for c in (it.get("comments") or [])[-50:])
    return f"""<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name} · Kami Kapsül</title><meta name="robots" content="noindex">
<style>
*{{box-sizing:border-box}}html,body{{margin:0;min-height:100%;background:#07060B;color:#EDE9F6;font:15px system-ui,-apple-system,"Segoe UI",sans-serif}}
.w{{min-height:100vh;display:grid;place-items:center;padding:24px;background:radial-gradient(ellipse 60% 50% at 50% 25%,#221538,#07060B 72%)}}
.c{{width:min(720px,100%);background:#100C17;border:1px solid #2A2140;border-radius:16px;overflow:hidden;box-shadow:0 24px 64px rgba(0,0,0,.6)}}
.pv{{background:#000;display:grid;place-items:center;max-height:62vh;overflow:hidden;border-bottom:1px solid #201833}}.pv img,.pv video{{max-width:100%;max-height:62vh;display:block}}.pv audio{{width:92%;margin:28px 0}}
.b{{padding:20px 22px;display:grid;gap:12px}}h1{{margin:0;font-size:19px;word-break:break-word;line-height:1.3}}.m{{color:#9E96B8;font-size:13px;display:flex;flex-wrap:wrap;gap:6px;align-items:center}}
a.dl,button{{display:inline-flex;align-items:center;justify-content:center;gap:6px;background:linear-gradient(135deg,#6D28D9,#8B5CF6);color:#fff;text-decoration:none;border:0;border-radius:10px;padding:11px 20px;font:600 14px inherit;cursor:pointer;transition:filter .15s,transform .1s}}
a.dl:hover,button:hover{{filter:brightness(1.1);transform:translateY(-1px)}}
input{{background:#08060E;border:1px solid #2A2140;border-radius:9px;color:inherit;padding:10px 12px;font:inherit;width:100%;transition:border-color .15s}}input:focus{{outline:none;border-color:#9D6BFF}}.e{{color:#FF6B81;font-size:13px}}
.k{{font:700 11px system-ui;letter-spacing:.26em;color:#9D6BFF}}
.fl{{display:grid;gap:4px}}.fl a{{display:flex;justify-content:space-between;gap:10px;color:#EDE9F6;text-decoration:none;padding:9px 11px;border:1px solid #201833;background:#140F1F;border-radius:9px;font-size:13.5px;transition:border-color .15s}}
.fl a:hover{{border-color:#9D6BFF}}.fl small{{color:#8E86A3}}
.cm{{display:grid;gap:8px;margin-top:8px;padding-top:14px;border-top:1px solid #201833}}.cmi{{font-size:13px;border-left:2px solid #9D6BFF;background:#140F1F;border-radius:0 8px 8px 0;padding:7px 10px}}.cmi b{{color:#C4B5FD;margin-right:6px}}
</style></head><body><div class="w"><div class="c">
<div class="pv" id="pv"></div>
<div class="b"><span class="k">KAMI KAPSÜL</span><h1>{name}</h1>
<div class="m">{_fmt_size(it["size"])} · <span id="left"></span> sonra silinir{(" · " + html.escape(host) + " paylaştı") if host else ""}</div>
{f'<div class="m">{note}</div>' if note else ""}
<div id="pw" hidden><input id="pwi" type="password" placeholder="Şifre"><div class="e" id="pwe"></div></div>
<div><a class="dl" id="dl" href="#">{"Hepsini indir (zip)" if multi else "İndir"}</a></div>
<div id="fl" class="fl"></div>
<div class="cm"><span class="k">YORUMLAR</span><div id="cms">{cms}</div>
<input id="cn" placeholder="Adın" maxlength="40"><input id="ct" placeholder="Bir şey yaz (paylaşan kişi bildirim alır)" maxlength="500"><button id="cs">Gönder</button></div>
</div></div></div>
<script>
const LOCKED = {json.dumps(bool(it.get("pw")))}, KIND = {json.dumps(kind)}, BASE = location.pathname.replace(/\\/$/, "");
const FILES = {json.dumps([{"name": f["name"], "size": _fmt_size(f["size"])} for f in files], ensure_ascii=False)};
document.getElementById("cs").onclick = async () => {{
  const t = document.getElementById("ct").value.trim(); if (!t) return;
  const r = await fetch(BASE + "/comment" + (key ? "?p=" + key : ""), {{ method: "POST", headers: {{ "Content-Type": "application/json" }}, body: JSON.stringify({{ name: document.getElementById("cn").value, text: t }}) }});
  if (r.ok) {{ const d = document.createElement("div"); d.className = "cmi"; d.innerHTML = "<b></b><span></span>"; d.querySelector("b").textContent = document.getElementById("cn").value || "Misafir"; d.querySelector("span").textContent = t; document.getElementById("cms").appendChild(d); document.getElementById("ct").value = ""; }}
}};
let left = {left}; const L = document.getElementById("left");
const fmt = (s) => s > 86400 ? Math.floor(s / 86400) + " gün" : s > 3600 ? Math.floor(s / 3600) + " saat" : Math.max(1, Math.floor(s / 60)) + " dakika";
L.textContent = fmt(left); setInterval(() => {{ left -= 30; L.textContent = fmt(left); }}, 30000);
async function h(t) {{ const b = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(t)); return [...new Uint8Array(b)].map((x) => x.toString(16).padStart(2, "0")).join(""); }}
let key = "";
function show() {{
  const q = key ? "?p=" + key : "";
  document.getElementById("dl").href = BASE + (FILES.length > 1 ? "/zip" : "/dl") + q;
  document.getElementById("fl").innerHTML = FILES.length > 1 ? FILES.map((f, i) => `<a href="${{BASE}}/dl/${{i}}${{q}}"><span>${{f.name.replace(/[<>&]/g, "")}}</span><small>${{f.size}}</small></a>`).join("") : "";
  const pv = document.getElementById("pv");
  if (KIND === "image") pv.innerHTML = `<img src="${{BASE}}/raw${{q}}" alt="">`;
  else if (KIND === "video") pv.innerHTML = `<video src="${{BASE}}/raw${{q}}" controls playsinline preload="metadata"></video>`;
  else if (KIND === "audio") pv.innerHTML = `<audio src="${{BASE}}/raw${{q}}" controls preload="metadata"></audio>`;
}}
if (!LOCKED) show();
else {{
  document.getElementById("pw").hidden = false;
  const dl = document.getElementById("dl"); dl.textContent = "Aç";
  dl.onclick = async (e) => {{
    if (key) return;
    e.preventDefault();
    const k = await h(document.getElementById("pwi").value);
    const r = await fetch(BASE + "/check?p=" + k);
    if (r.ok) {{ key = k; document.getElementById("pw").hidden = true; dl.textContent = "İndir"; show(); }}
    else document.getElementById("pwe").textContent = r.status === 429 ? "Çok fazla deneme, 1 dakika bekle." : "Şifre yanlış.";
  }};
  document.getElementById("pwi").addEventListener("keydown", (e) => e.key === "Enter" && dl.click());
}}
</script></body></html>"""


def serve(h: Any, rest: list[str], query: dict[str, list[str]], host: str = "") -> None:
    """room.py istek isleyicisinden: /c/<id>[/raw|/dl|/check]."""
    cid = rest[0] if rest else ""
    it = get(cid)
    if not it:
        body = "<!doctype html><meta charset=utf-8><body style='background:#07060B;color:#EDE9F6;font:16px system-ui;display:grid;place-items:center;height:100vh;margin:0'><p>Bu Kami Kapsül'ün süresi dolmuş ya da silinmiş.</p>".encode()
        return h._send(body, "text/html; charset=utf-8", code=404)
    sub = rest[1] if len(rest) > 1 else ""
    if not sub:
        return h._send(page(cid, it, host).encode("utf-8"), "text/html; charset=utf-8")
    ip = str(h.headers.get("CF-Connecting-IP") or (h.client_address[0] if h.client_address else ""))
    if not pw_ok(it, (query.get("p") or [""])[0][:128], ip):
        return h._send(b'{"ok":false}', "application/json", code=429 if len(_BAD.get(ip, [])) >= 10 else 401)
    if sub == "check":
        return h._send(b'{"ok":true}', "application/json")
    files = it.get("files") or [{"path": it["path"], "name": it["name"]}]
    if sub == "zip":
        return _send_zip(h, files, it["name"], cid)
    if sub not in ("raw", "dl"):
        return h._err(404)
    try:
        idx = int(rest[2]) if len(rest) > 2 else 0
    except ValueError:
        return h._err(404)
    if not 0 <= idx < len(files):
        return h._err(404)
    f = files[idx]
    _send_file(h, Path(f["path"]), f["name"], attach=(sub == "dl"))
    if sub == "dl":
        count_download(cid, f["name"])


def serve_post(h: Any, rest: list[str], query: dict[str, list[str]], body: dict[str, Any]) -> None:
    """POST /c/<id>/comment {name, text}."""
    cid = rest[0] if rest else ""
    it = get(cid)
    if not it or len(rest) < 2 or rest[1] != "comment":
        return h._err(404)
    ip = str(h.headers.get("CF-Connecting-IP") or (h.client_address[0] if h.client_address else ""))
    if not pw_ok(it, (query.get("p") or [""])[0][:128], ip):
        return h._send(b'{"ok":false}', "application/json", code=401)
    ok = add_comment(cid, str(body.get("name", "")), str(body.get("text", "")), ip)
    h._send(json.dumps({"ok": ok}).encode(), "application/json", code=200 if ok else 429)


def _send_zip(h: Any, files: list[dict[str, Any]], name: str, cid: str) -> None:
    """Coklu dosya: sikistirmadan (hizli) zip akisi; boyut onceden bilinmez, baglanti kapaninca biter."""
    import zipfile

    class _W:
        def __init__(self, w: Any) -> None:
            self.w, self.n = w, 0

        def write(self, b: bytes) -> int:
            self.w.write(b)
            self.n += len(b)
            return len(b)

        def tell(self) -> int:
            return self.n

        def flush(self) -> None:
            self.w.flush()

    zname = re.sub(r'[\\/:*?"<>|]+', "_", name)[:60] + ".zip"
    h.send_response(200)
    h.send_header("Content-Type", "application/zip")
    h.send_header("Content-Disposition", f"attachment; filename=\"kapsul.zip\"; filename*=UTF-8''{quote(zname)}")
    h.send_header("Connection", "close")
    h.end_headers()
    h.close_connection = True
    try:
        with zipfile.ZipFile(_W(h.wfile), "w", zipfile.ZIP_STORED, allowZip64=True) as z:
            seen: set[str] = set()
            for f in files:
                p = Path(f["path"])
                if not p.is_file():
                    continue
                arc = f["name"]
                while arc in seen:
                    arc = "_" + arc
                seen.add(arc)
                with p.open("rb") as src, z.open(zipfile.ZipInfo(arc, time.localtime(p.stat().st_mtime)[:6]), "w", force_zip64=True) as dst:
                    while True:
                        chunk = src.read(1 << 20)
                        if not chunk:
                            break
                        dst.write(chunk)
        count_download(cid, "zip")
    except (ConnectionError, OSError):
        pass


def _send_file(h: Any, p: Path, name: str, attach: bool) -> None:
    size = p.stat().st_size
    start, end = 0, size - 1
    rng = h.headers.get("Range") or ""
    m = re.match(r"bytes=(\d*)-(\d*)", rng)
    code = 200
    if m and not attach:
        if m.group(1):
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else size - 1
        elif m.group(2):
            start = max(0, size - int(m.group(2)))
        end = min(end, size - 1)
        if start > end:
            h.send_response(416)
            h.send_header("Content-Range", f"bytes */{size}")
            h.end_headers()
            return
        code = 206
    h.send_response(code)
    h.send_header("Content-Type", mimetypes.guess_type(name)[0] or "application/octet-stream")
    h.send_header("Content-Length", str(end - start + 1))
    h.send_header("Accept-Ranges", "bytes")
    h.send_header("Cache-Control", "no-store")
    if code == 206:
        h.send_header("Content-Range", f"bytes {start}-{end}/{size}")
    if attach:
        safe = name.encode("ascii", "replace").decode().replace('"', "_")
        h.send_header("Content-Disposition", f"attachment; filename=\"{safe}\"; filename*=UTF-8''{quote(name)}")
    h.end_headers()
    try:
        with p.open("rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(1024 * 1024, left))
                if not chunk:
                    break
                h.wfile.write(chunk)
                left -= len(chunk)
    except (ConnectionError, OSError):
        pass
