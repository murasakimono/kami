"""RSS / Atom otomatik indirme (v1.29): torrent akislari (nyaa, tracker RSS'leri, showRSS...) ve podcast'ler.

- Akis basina: icerir / icermez filtreleri (virgul ya da /regex/), en buyuk boyut, kuyruk (queues.py), aralik.
- "Akilli bolum": ayni dizinin ayni SxxEyy'si (ya da anime ' - 07 ') bir kez iner; farkli kalite/grup tekrar inmez.
- Ilk eklemede mevcut girdiler 'goruldu' sayilir (geriye donuk toplu indirme yok; istenirse backfill=N).
- Kayit: data/rss.json. Indirme yolu api tarafinda (RD ayari -> RD; degilse yerel torrent tum dosyalar; .torrent
  olmayan ek -> normal indirme).
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from typing import Any, Callable

from app import paths

log = logging.getLogger(__name__)
SEEN_KEEP = 2000
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Kami-RSS/1.0"


def _file():
    return paths.DATA_DIR / "rss.json"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _size_from(text: str) -> int:
    m = re.search(r"([\d.,]+)\s*(KiB|MiB|GiB|TiB|KB|MB|GB|TB)\b", text or "", re.I)
    if not m:
        return 0
    n = float(m.group(1).replace(",", "."))
    mult = {"k": 1 << 10, "m": 1 << 20, "g": 1 << 30, "t": 1 << 40}[m.group(2)[0].lower()]
    return int(n * mult)


def parse_feed(xml: bytes | str) -> tuple[str, list[dict[str, Any]]]:
    """-> (baslik, girdiler[{id, title, link, size, date}]). RSS 2.0, Atom, torrent:/nyaa: uzantilari."""
    root = ET.fromstring(xml)
    title = ""
    items: list[dict[str, Any]] = []
    for el in root.iter():
        name = _local(el.tag)
        if name == "title" and not title:
            title = (el.text or "").strip()
        if name not in ("item", "entry"):
            continue
        it: dict[str, Any] = {"title": "", "link": "", "id": "", "size": 0, "date": "", "magnet": "", "enclosure": ""}
        for c in el:
            n, txt = _local(c.tag), (c.text or "").strip()
            if n == "title":
                it["title"] = txt
            elif n == "link":
                if (c.get("rel") or "") == "enclosure":
                    it["enclosure"] = c.get("href") or it["enclosure"]
                else:
                    it["link"] = c.get("href") or txt or it["link"]
            elif n in ("guid", "id"):
                it["id"] = txt
            elif n == "enclosure":
                it["enclosure"] = c.get("url") or ""
                ln = str(c.get("length") or "")
                if ln.isdigit() and not it["size"]:
                    it["size"] = int(ln)
            elif n in ("magneturi", "magnet"):
                it["magnet"] = txt
            elif n in ("contentlength", "size"):
                it["size"] = int(txt) if txt.isdigit() else _size_from(txt) or it["size"]
            elif n in ("infohash",) and txt and not it["magnet"]:
                it["magnet"] = f"magnet:?xt=urn:btih:{txt}&dn={it['title']}"
            elif n in ("pubdate", "published", "updated") and not it["date"]:
                it["date"] = txt
            elif n == "description" and not it["size"]:
                it["size"] = _size_from(txt)
        # en iyi indirme linki: magnet > .torrent eki > torrent linki > ek
        link = it["magnet"] or ""
        for cand in (it["enclosure"], it["link"]):
            if not link and cand and (cand.lower().startswith("magnet:") or ".torrent" in cand.lower().split("?")[0]):
                link = cand
        it["dl"] = link or it["enclosure"] or ""
        it["id"] = it["id"] or it["dl"] or it["link"] or it["title"]
        if it["dl"]:
            items.append(it)
    return title, items


_EP = [re.compile(r"\bS(\d{1,2})[ ._-]?E(\d{1,3})\b", re.I), re.compile(r"\b(\d{1,2})x(\d{2,3})\b"),
       re.compile(r"(?:^|[ _])-[ _](\d{1,4})(?:v\d)?(?=[ _\[(.]|$)")]


def episode_key(title: str) -> str:
    """'[Grup] Dizi Adi - 07 [1080p]' / 'Dizi.Adi.S01E07.720p' -> 'dizi adi|s01e07'. Bulamazsa ''."""
    t = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", title or "")
    for i, rx in enumerate(_EP):
        m = rx.search(t)
        if m:
            show = re.sub(r"[._]+", " ", t[: m.start()]).strip(" -").lower()
            show = re.sub(r"\s+", " ", show)
            ep = f"s{int(m.group(1)):02d}e{int(m.group(2)):02d}" if i < 2 else f"e{int(m.group(1)):03d}"
            return f"{show}|{ep}" if show else ""
    return ""


def _terms(s: str) -> list[Any]:
    s = (s or "").strip()
    if len(s) > 2 and s.startswith("/") and s.endswith("/"):
        try:
            return [re.compile(s[1:-1], re.I)]
        except re.error:
            return []
    return [x.strip().lower() for x in s.split(",") if x.strip()]


def _hit(term: Any, title: str) -> bool:
    return bool(term.search(title)) if hasattr(term, "search") else all(w in title.lower() for w in term.split())


def matches(feed: dict[str, Any], it: dict[str, Any]) -> bool:
    inc, exc = _terms(feed.get("include", "")), _terms(feed.get("exclude", ""))
    t = it.get("title", "")
    if inc and not any(_hit(x, t) for x in inc):
        return False
    if exc and any(_hit(x, t) for x in exc):
        return False
    mx = int(feed.get("max_mb") or 0)
    if mx and it.get("size") and it["size"] > mx * 1048576:
        return False
    return True


class RssService:
    def __init__(self, fetch: Callable[[str], bytes], add: Callable[[dict[str, Any], dict[str, Any]], bool],
                 notify: Callable[[str, str], Any] = lambda t, m: None) -> None:
        self.fetch, self.add, self.notify = fetch, add, notify
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self.feeds = self._load()

    def _load(self) -> list[dict[str, Any]]:
        try:
            return [f for f in json.loads(_file().read_text("utf-8")) if isinstance(f, dict)]
        except (OSError, ValueError):
            return []

    def _save(self) -> None:
        tmp = _file().with_suffix(".tmp")
        tmp.write_text(json.dumps(self.feeds, ensure_ascii=False), "utf-8")
        tmp.replace(_file())

    def public(self) -> list[dict[str, Any]]:
        with self._lock:
            return [{k: v for k, v in f.items() if k not in ("seen", "eps")} | {"seen_n": len(f.get("seen", []))} for f in self.feeds]

    def add_feed(self, url: str, **opts: Any) -> dict[str, Any]:
        url = (url or "").strip()
        if not re.match(r"^https?://", url, re.I):
            return {"ok": False, "error": "bad_url"}
        try:
            title, items = parse_feed(self.fetch(url))
        except Exception as exc:
            return {"ok": False, "error": "feed", "detail": str(exc)[:160]}
        f = {"id": uuid.uuid4().hex[:8], "url": url, "title": opts.get("title") or title or url, "enabled": True,
             "include": "", "exclude": "", "max_mb": 0, "smart_ep": True, "queue": "", "interval_min": 30,
             "last": time.time(), "last_new": 0, "error": "", "seen": [], "eps": []}
        f.update({k: v for k, v in opts.items() if k in ("include", "exclude", "max_mb", "smart_ep", "queue", "interval_min")})
        backfill = max(0, int(opts.get("backfill") or 0))
        with self._lock:
            self.feeds.append(f)
            todo = [it for it in items if matches(f, it)][:backfill]
            f["seen"] = [it["id"] for it in items if it not in todo]
            self._save()
        for it in todo:
            self._take(f, it)
        return {"ok": True, "feed": self.public()[-1], "items": len(items),
                "preview": [{"title": it["title"], "match": matches(f, it), "size": it["size"]} for it in items[:30]]}

    def update(self, fid: str, **kw: Any) -> bool:
        with self._lock:
            for f in self.feeds:
                if f["id"] == fid:
                    for k in ("title", "enabled", "include", "exclude", "max_mb", "smart_ep", "queue", "interval_min"):
                        if k in kw:
                            f[k] = kw[k]
                    f["interval_min"] = max(5, int(f.get("interval_min") or 30))
                    self._save()
                    return True
        return False

    def remove(self, fid: str) -> None:
        with self._lock:
            self.feeds = [f for f in self.feeds if f["id"] != fid]
            self._save()

    def preview(self, fid: str) -> list[dict[str, Any]]:
        f = next((x for x in self.feeds if x["id"] == fid), None)
        if not f:
            return []
        _, items = parse_feed(self.fetch(f["url"]))
        return [{"title": it["title"], "size": it["size"], "match": matches(f, it), "seen": it["id"] in f.get("seen", [])} for it in items[:50]]

    def _take(self, f: dict[str, Any], it: dict[str, Any]) -> bool:
        with self._lock:
            ek = episode_key(it["title"]) if f.get("smart_ep", True) else ""
            if ek and ek in f.get("eps", []):
                return False
        ok = False
        try:
            ok = bool(self.add(it, f))
        except Exception:
            log.exception("RSS girdisi eklenemedi: %s", it.get("title"))
        if ok and ek:
            with self._lock:
                f.setdefault("eps", []).append(ek)
                del f["eps"][:-SEEN_KEEP]
        return ok

    def check(self, fid: str | None = None, force: bool = False) -> int:
        new = 0
        with self._lock:
            feeds_copy = list(self.feeds)
        for f in feeds_copy:
            with self._lock:
                if fid and f["id"] != fid:
                    continue
                if not fid and (not f.get("enabled") or (not force and time.time() - f.get("last", 0) < f.get("interval_min", 30) * 60)):
                    continue
                url = f["url"]
                title = f["title"]
            try:
                _, items = parse_feed(self.fetch(url))
                with self._lock:
                    f["error"] = ""
            except Exception as exc:
                with self._lock:
                    f["error"], f["last"] = str(exc)[:160], time.time()
                continue
            with self._lock:
                seen = set(f.get("seen", []))
            got = []
            for it in reversed(items):   # eskiden yeniye: ayni bolumun ilk cikan surumu alinir
                if it["id"] in seen:
                    continue
                with self._lock:
                    f.setdefault("seen", []).append(it["id"])
                    should_take = matches(f, it)
                if should_take and self._take(f, it):
                    got.append(it["title"])
            with self._lock:
                del f["seen"][:-SEEN_KEEP]
                f["last"] = time.time()
                if got:
                    f["last_new"] = time.time()
            if got:
                new += len(got)
                self.notify("Kami RSS", f"{title}: {len(got)} yeni" + (f" — {got[0][:80]}" if got else ""))
        with self._lock:
            self._save()
        return new

    def start(self) -> None:
        def loop() -> None:
            while not self._stop.wait(60):
                try:
                    self.check()
                except Exception:
                    log.exception("RSS dongusu")
        threading.Thread(target=loop, name="kami-rss", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
