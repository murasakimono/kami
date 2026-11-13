"""Asama 6c: gecmis + arama, bitince otomatik isler, kuyruk bitince bilgisayari KAPAT, ntfy, toplu link.

Hepsi Ayarlar'dan acilip kapanir. Gizli bilgi (ntfy konusu) DPAPI ile ayri dosyada (data/ntfy_topic.bin).
"""
from __future__ import annotations

import html
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urljoin, urlparse

log = logging.getLogger(__name__)

NO_WINDOW = 0x08000000


# ---------------------------------------------------------------- gecmis
def url_key(url: str) -> str:
    """Tekrar indirme tespiti icin anahtar: YouTube video kimligi; digerlerinde sorgu/parcasiz URL."""
    u = urlparse(url or "")
    host = (u.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    if host in ("youtube.com", "music.youtube.com") and parse_qs(u.query).get("v"):
        return "yt:" + parse_qs(u.query)["v"][0]
    if host == "youtu.be" and u.path.strip("/"):
        return "yt:" + u.path.strip("/").split("/")[0]
    if (url or "").startswith("magnet:"):
        m = re.search(r"btih:([0-9a-zA-Z]+)", url)
        return "bt:" + m.group(1).lower() if m else url
    return f"{host}{u.path}"


class History:
    """Bitmis indirmelerin kalici kaydi (listeden temizlense de kalir). data/history.db"""

    def __init__(self, path: Path) -> None:
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.execute("""CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY, key TEXT, url TEXT, page_url TEXT, filename TEXT, path TEXT,
            size INTEGER, category TEXT, source TEXT, finished REAL)""")
        self._db.execute("CREATE INDEX IF NOT EXISTS hk ON history(key)")
        self._db.commit()

    def add(self, d) -> None:
        keys = {url_key(d.url)}
        if d.page_url:
            keys.add(url_key(d.page_url))
        with self._lock:
            for k in keys:
                self._db.execute(
                    "INSERT INTO history(key,url,page_url,filename,path,size,category,source,finished)"
                    " VALUES(?,?,?,?,?,?,?,?,?)",
                    (k, d.url, d.page_url, d.filename, d.path, int(d.size or 0), d.category, d.source,
                     d.finished_at or time.time()))
            self._db.commit()

    def find(self, url: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT filename, path, finished FROM history WHERE key=? ORDER BY finished DESC"
                                   " LIMIT 1", (url_key(url),)).fetchone()
        if not row:
            return None
        return {"filename": row[0], "path": row[1], "finished": row[2],
                "exists": bool(row[1] and os.path.exists(row[1]))}

    def search(self, q: str = "", limit: int = 200) -> list[dict[str, Any]]:
        sql = ("SELECT MIN(id), url, page_url, filename, path, size, category, MAX(finished) FROM history "
               "{w} GROUP BY url ORDER BY MAX(finished) DESC LIMIT ?")
        with self._lock:
            if q.strip():
                like = f"%{q.strip()}%"
                rows = self._db.execute(sql.format(w="WHERE filename LIKE ? OR url LIKE ? OR page_url LIKE ?"),
                                        (like, like, like, limit)).fetchall()
            else:
                rows = self._db.execute(sql.format(w=""), (limit,)).fetchall()
        return [{"id": r[0], "url": r[1], "page_url": r[2], "filename": r[3], "path": r[4], "size": r[5],
                 "category": r[6], "finished": r[7], "exists": bool(r[4] and os.path.exists(r[4]))} for r in rows]

    def clear(self) -> None:
        with self._lock:
            self._db.execute("DELETE FROM history")
            self._db.commit()


# ---------------------------------------------------------------- ntfy (telefona bildirim)
def ntfy_send(server: str, topic: str, title: str, message: str, tags: str = "", timeout: float = 10.0) -> bool:
    if not topic:
        return False
    import requests
    try:
        r = requests.post(f"{(server or 'https://ntfy.sh').rstrip('/')}/{topic}", data=message.encode("utf-8"),
                          headers={"Title": title.encode("utf-8"), **({"Tags": tags} if tags else {})},
                          timeout=timeout)
        return r.status_code < 300
    except Exception as exc:
        log.warning("ntfy gonderilemedi: %s", type(exc).__name__)
        return False


# ---------------------------------------------------------------- arsiv acma
ARCHIVE_EXT = (".zip", ".7z", ".rar", ".tar", ".gz", ".tgz", ".xz")


def find_7z() -> str:
    for c in (shutil.which("7z"), r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"):
        if c and os.path.isfile(c):
            return c
    return ""


def is_multipart_tail(name: str) -> bool:
    """part2.rar, .r01, .z01 gibi parca devamlari: sadece ilk parca acilir."""
    n = name.lower()
    m = re.search(r"\.part(\d+)\.rar$", n)
    return bool(m and int(m.group(1)) > 1) or bool(re.search(r"\.(r\d\d|z\d\d|\d{3})$", n) and not n.endswith(".001"))


def extract(path: str, passwords: list[str] | None = None) -> str:
    """Arsivi yanindaki <ad> klasorune acar. Basariliysa klasor yolu, degilse ''."""
    base = os.path.basename(path)
    stem = re.sub(r"(\.part\d+)?\.(zip|7z|rar|tar|gz|tgz|xz|001)$", "", base, flags=re.I) or base
    dest = os.path.join(os.path.dirname(path), stem)
    i = 2
    while os.path.exists(dest):
        dest = os.path.join(os.path.dirname(path), f"{stem} ({i})")
        i += 1
    sz = find_7z()
    try:
        if sz:
            ok = False
            for pwd in ("", *[str(x) for x in (passwords or []) if x]):
                r = subprocess.run([sz, "x", "-y", f"-p{pwd}", f"-o{dest}", path], capture_output=True,
                                   creationflags=NO_WINDOW, timeout=6 * 3600)
                if r.returncode == 0:
                    ok = True
                    break
                shutil.rmtree(dest, ignore_errors=True)
        elif path.lower().endswith(".zip"):
            with zipfile.ZipFile(path) as z:
                for m in z.namelist():   # zip slip korumasi
                    if os.path.isabs(m) or ".." in Path(m).parts:
                        raise ValueError("bad member")
                z.extractall(dest)
            ok = True
        else:
            log.info("Arsiv acilamadi (7-Zip yok): %s", base)
            return ""
    except Exception:
        log.exception("Arsiv acma hatasi: %s", base)
        ok = False
    if not ok:
        shutil.rmtree(dest, ignore_errors=True)
        return ""
    return dest


def archive_parts(path: str) -> list[str]:
    """Silinecek parcalar: ilk parca + ayni adli devamlari."""
    d, base = os.path.split(path)
    m = re.match(r"(.*)\.part\d+\.rar$", base, re.I)
    if m:
        return [os.path.join(d, f) for f in os.listdir(d) if re.fullmatch(re.escape(m.group(1)) + r"\.part\d+\.rar", f, re.I)]
    stem, ext = os.path.splitext(base)
    if ext.lower() == ".001":
        return [os.path.join(d, f) for f in os.listdir(d) if re.fullmatch(re.escape(stem) + r"\.\d{3}", f)]
    if ext.lower() == ".rar":
        return [path] + [os.path.join(d, f) for f in os.listdir(d) if re.fullmatch(re.escape(stem) + r"\.r\d\d", f, re.I)]
    return [path]


# ---------------------------------------------------------------- bitince isler
class AfterActions:
    """PostComplete.after'a eklenir: gecmis kaydi, arsiv ac(+sil), muzigi muzik klasorune, ntfy."""

    def __init__(self, manager, history: History | None, ntfy_topic: Callable[[], str] = lambda: "",
                 music_dir: Callable[[], str] = lambda: "") -> None:
        self.manager = manager
        self.history = history
        self.ntfy_topic = ntfy_topic
        self.music_dir = music_dir

    def __call__(self, did: int) -> None:
        s = self.manager.settings
        d = self.manager.store.get(did)
        if not d:
            return
        if self.history is not None and s.get("history_enabled"):
            self.history.add(d)
        path = d.path
        if path and os.path.isfile(path) and s.get("auto_extract") and path.lower().endswith(ARCHIVE_EXT + (".001",)) \
                and not is_multipart_tail(os.path.basename(path)):
            pws = []
            try:
                import json as _json
                from app.core import paths as _paths
                from app.core.vault import TokenStore
                raw = TokenStore(_paths.DATA_DIR / "archive_passwords.bin").load()
                if raw:
                    data = _json.loads(raw)
                    if isinstance(data, list):
                        pws = [str(x) for x in data if x]
            except Exception:
                pws = []
            out = extract(path, passwords=pws)
            self._set(did, extracted=out or "", extract_failed=not out)
            if out and s.get("auto_extract_delete"):
                for p in archive_parts(path):
                    try:
                        os.remove(p)
                    except OSError:
                        log.warning("Arsiv silinemedi: %s", p)
        # muzik -> muzik klasoru (arsivci kapaliysa; arsivci zaten Sanatci/Album'e tasir)
        d = self.manager.store.get(did) or d
        if d.path and os.path.isfile(d.path) and d.category == "music" and s.get("music_move") \
                and not s.get("music_archive"):
            target = self.music_dir()
            if target and os.path.normcase(os.path.dirname(d.path)) != os.path.normcase(target):
                os.makedirs(target, exist_ok=True)
                dest = os.path.join(target, d.filename)
                if not os.path.exists(dest):
                    shutil.move(d.path, dest)
                    lrc = os.path.splitext(d.path)[0] + ".lrc"
                    if os.path.isfile(lrc):
                        shutil.move(lrc, os.path.splitext(dest)[0] + ".lrc")
                    self.manager.store.update(did, directory=target)
        if s.get("ntfy_enabled") and s.get("ntfy_each"):
            ntfy_send(s.get("ntfy_server"), self.ntfy_topic(), "Kami", f"İndi: {d.filename or d.url}"[:300],
                      "white_check_mark")

    def failed(self, did: int) -> None:
        s = self.manager.settings
        d = self.manager.store.get(did)
        if d and s.get("ntfy_enabled") and s.get("ntfy_errors"):
            ntfy_send(s.get("ntfy_server"), self.ntfy_topic(), "Kami: hata", f"{d.filename or d.url}\n{d.error}"[:300],
                      "warning")

    def _set(self, did: int, **kw: Any) -> None:
        d = self.manager.store.get(did)
        if d:
            nd = self.manager.store.update(did, extra={**(d.extra or {}), **kw})
            self.manager.events.emit("download.updated", download=nd)


def disk_check(directory: str, need: int, margin: int = 512 * 1024 * 1024) -> dict[str, Any] | None:
    """Dosya diske sigmayacaksa {free, need} (indirme baslamadan once uyarmak icin)."""
    if not need or need <= 0:
        return None
    probe = directory
    while probe and not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    try:
        free = shutil.disk_usage(probe or ".").free
    except OSError:
        return None
    return {"free": free, "need": need} if need + margin > free else None


# ---------------------------------------------------------------- kuyruk bitince KAPAT
class ShutdownWatcher:
    """shutdown_when_done acikken: kuyrukta is kalmayinca (en az bir indirme bittiyse) 60 sn geri sayim,
    iptal edilmezse `shutdown /s /t 0`. Uyku YOK (kullanici uyku kullanmiyor). Tek seferlik: tetiklenince ayar kapanir."""

    COUNTDOWN = 60

    def __init__(self, manager, busy_extra: Callable[[], bool] = lambda: False,
                 do_shutdown: Callable[[], None] | None = None, on_queue_done: Callable[[], None] = lambda: None,
                 tick: float = 2.0) -> None:
        self.manager = manager
        self.busy_extra = busy_extra            # AI kuyrugu vb. hala calisiyor mu
        self.do_shutdown = do_shutdown or (lambda: subprocess.Popen(["shutdown", "/s", "/t", "0"],
                                                                    creationflags=NO_WINDOW))
        self.on_queue_done = on_queue_done
        self.tick = tick
        self.deadline: float | None = None
        self._had_work = False
        self._was_busy = False
        self._stop = threading.Event()

    def busy(self) -> bool:
        from app.core.models import Status
        return bool(self.manager.store.list([Status.ACTIVE, Status.WAITING, Status.QUEUED])) or self.busy_extra()

    def cancel(self) -> None:
        if self.deadline is not None:
            log.info("Kapatma geri sayimi iptal edildi")
        self.deadline = None
        self.manager.settings.set("shutdown_when_done", False)

    def state(self) -> dict[str, Any]:
        return {"armed": bool(self.manager.settings.get("shutdown_when_done")),
                "countdown": max(0, int(self.deadline - time.monotonic())) if self.deadline else None}

    def step(self) -> None:
        busy = self.busy()
        if busy:
            self._had_work = True
            self.deadline = None
        elif self._was_busy:
            self.on_queue_done()            # kuyruk bitti bildirimi (ntfy) - kapatma acik olmasa da
        self._was_busy = busy
        armed = bool(self.manager.settings.get("shutdown_when_done"))
        if not armed:
            self.deadline = None
            self._had_work = busy
            return
        if busy or not self._had_work:
            return
        if self.deadline is None:
            self.deadline = time.monotonic() + self.COUNTDOWN
            log.info("Kuyruk bitti: %d sn sonra bilgisayar kapatilacak", self.COUNTDOWN)
            self.manager.events.emit("ui.attention", reason="shutdown")
            return
        if time.monotonic() >= self.deadline:
            self.deadline = None
            self.manager.settings.set("shutdown_when_done", False)   # tek seferlik
            log.warning("Kuyruk bitti: bilgisayar KAPATILIYOR")
            self.do_shutdown()

    def stop(self) -> None:
        self._stop.set()

    def start(self) -> None:
        def loop() -> None:
            while not self._stop.wait(self.tick):
                try:
                    self.step()
                except Exception:
                    log.exception("Kapatma izleyicisi")
        threading.Thread(target=loop, name="kami-shutdown", daemon=True).start()


# ---------------------------------------------------------------- toplu link
_URL_RE = re.compile(r"""(?:https?|ftp)://[^\s<>"'`{}|\\^\[\]]+|magnet:\?[^\s<>"']+""", re.I)


# Sayfa kaynagi dosyalari (sayfadan cekerken varsayilan GIZLI): js/css/ikon/font/izleme pikselleri
_RESOURCE_EXT = {".js", ".mjs", ".css", ".ico", ".svg", ".woff", ".woff2", ".ttf", ".otf", ".eot", ".map",
                 ".json", ".xml", ".webmanifest", ".rss", ".atom", ".php", ".asp", ".aspx"}
_RESOURCE_RE = re.compile(r"generate_204|/favicon|/manifest|/opensearch|/feeds?/|/rss|/s/player/|/yts/|/sw\.js|"
                          r"googletagmanager|google-analytics|doubleclick|/ads?/|/static/|/assets?/(?:css|js|fonts?)/",
                          re.I)


def is_resource(url: str) -> bool:
    """Sayfanin kendi kaynagi (indirilecek dosya degil)?"""
    from urllib.parse import urlparse
    try:
        p = urlparse(url)
    except ValueError:
        return True
    ext = os.path.splitext(p.path.lower())[1]
    return ext in _RESOURCE_EXT or bool(_RESOURCE_RE.search(url))


def page_anchor_links(html_text: str, base: str) -> list[str]:
    """Sadece <a href> linkleri (src/data-src = sayfa kaynagi, alinmaz)."""
    out: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r"""<a\b[^>]*?\bhref\s*=\s*["']([^"']+)["']""", html_text, re.I):
        u = html.unescape(m.group(1).strip())
        if u.startswith(("#", "javascript:", "mailto:", "data:", "tel:")):
            continue
        if not re.match(r"^(?:https?|ftp|magnet):", u, re.I):
            u = urljoin(base, u)
        if re.match(r"^(?:https?|ftp)://|^magnet:\?", u, re.I) and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def extract_links(text: str, base: str = "") -> list[str]:
    """Metin ya da HTML -> benzersiz linkler (sirayi koru). HTML'de href/src de okunur, goreli linkler cozulur."""
    out: list[str] = []
    seen: set[str] = set()

    def add(u: str) -> None:
        u = html.unescape(u.strip()).rstrip(".,;:!?)»”’")
        if base and not re.match(r"^(?:https?|ftp|magnet):", u, re.I):
            if u.startswith(("#", "javascript:", "mailto:", "data:")):
                return
            u = urljoin(base, u)
        if re.match(r"^(?:https?|ftp)://|^magnet:\?", u, re.I) and u not in seen:
            seen.add(u)
            out.append(u)

    if base or "<a " in text.lower():
        for m in re.finditer(r"""(?:href|src|data-src)\s*=\s*["']([^"']+)["']""", text, re.I):
            add(m.group(1))
    for m in _URL_RE.finditer(text):
        add(m.group(0))
    return out


def expand_numbered(text: str) -> list[str]:
    """http://x/dosya[001-120].jpg -> 120 link (IDM/XDM'deki numarali toplu indirme)."""
    m = re.search(r"\[(\d+)-(\d+)\]", text)
    if not m:
        return [text]
    a, b = m.group(1), m.group(2)
    width = len(a) if a.startswith("0") else 0
    lo, hi = int(a), int(b)
    if hi < lo or hi - lo > 5000:
        return [text]
    return [text[:m.start()] + str(i).zfill(width) + text[m.end():] for i in range(lo, hi + 1)]


def fetch_page_links(url: str, timeout: float = 20.0) -> dict[str, Any]:
    """Sayfadaki <a> linkleri; kaynak dosyalari (js/css/ikon...) ayiklanir. -> {links, hidden}"""
    import requests
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    text = r.text[:5_000_000]
    raw = page_anchor_links(text, r.url)
    raw = list(dict.fromkeys(raw))
    links = [u for u in raw if not is_resource(u)]
    return {"links": links, "hidden": len(raw) - len(links)}
