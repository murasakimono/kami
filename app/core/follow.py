"""Kanal / liste takibi (Asama 6b): YouTube kanali ya da oynatma listesi; yeni icerik -> kurala gore MP3/MP4.

- Ilk eklemede mevcut videolar "goruldu" sayilir (geriye donuk toplu indirme YOK; istenirse backfill=N).
- Kontrol araligi ayarli (follow_interval_min); her takip kendi son kontrol zamanini tutar.
- Liste yt-dlp ile duz (extract_flat) cekilir: sadece son 30 girdi, video sayfasina girilmez (hizli, kotasiz).
- Kayit: data/follows.json (gizli bilgi yok).
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

SCAN_LIMIT = 30
SEEN_KEEP = 1000


def normalize_url(url: str) -> str:
    """youtube.com/@kanal (ve /channel/ID, /c/, /user/) -> .../videos; liste linki oldugu gibi."""
    url = (url or "").strip()
    if "list=" in url:
        m = re.search(r"[?&]list=([\w-]+)", url)
        return f"https://www.youtube.com/playlist?list={m.group(1)}" if m else url
    m = re.match(r"(https?://(?:www\.|m\.)?youtube\.com/(?:@[^/?#]+|channel/[\w-]+|c/[^/?#]+|user/[^/?#]+))/?"
                 r"(?:featured|videos|shorts|streams)?/?(?:[?#].*)?$", url)
    if m:
        return re.sub(r"^https?://(?:www\.|m\.)?youtube\.com", "https://www.youtube.com", m.group(1)) + "/videos"
    return url


def list_entries(url: str, limit: int = SCAN_LIMIT) -> tuple[str, list[dict[str, str]]]:
    """-> (baslik, [{id, url, title}]) en yeniden eskiye."""
    from app.engines import ytdlp_engine as yt
    yt_dlp = yt._ytdlp()
    opts = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist", "playlistend": limit,
            "skip_download": True, "logger": yt._YdlLogger()}
    with yt._cookiefile(url) as ck, yt_dlp.YoutubeDL({**opts, "cookiefile": ck} if ck else opts) as ydl:
        info = ydl.extract_info(url, download=False) or {}
    out = []
    for e in (info.get("entries") or [])[:limit]:
        if not isinstance(e, dict) or not e.get("id"):
            continue
        u = e.get("url") or ""
        if not u.startswith("http"):
            u = f"https://www.youtube.com/watch?v={e['id']}"
        out.append({"id": str(e["id"]), "url": u, "title": str(e.get("title") or "")})
    title = str(info.get("channel") or info.get("uploader") or info.get("title") or url)
    return title, out


class FollowService:
    def __init__(self, path: Path, settings, add: Callable[[str, dict[str, Any], str], Any],
                 lister: Callable[[str], tuple[str, list[dict[str, str]]]] = list_entries,
                 notify: Callable[[str], None] = lambda m: None) -> None:
        self.path = path
        self.settings = settings
        self.add = add                  # (video_url, media_options, title) -> manager.add_media
        self.lister = lister
        self.notify = notify
        self._lock = threading.RLock()
        self._items: list[dict[str, Any]] = self._load()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._busy = threading.Lock()

    # ---- kayit
    def _load(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return [x for x in data if isinstance(x, dict) and x.get("id")] if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def _save(self) -> None:
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._items, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [{k: v for k, v in x.items() if k != "seen"} | {"seen_count": len(x.get("seen") or [])}
                    for x in self._items]

    # ---- ekle / degistir / sil
    def add_follow(self, url: str, fmt: str = "mp4", quality: str = "best", backfill: int = 0) -> dict[str, Any]:
        url = normalize_url(url)
        if not url.lower().startswith(("http://", "https://")):
            return {"ok": False, "error": "bad_url"}
        with self._lock:
            if any(x["url"] == url for x in self._items):
                return {"ok": False, "error": "follow_exists"}
        try:
            title, entries = self.lister(url)
        except Exception as exc:
            log.warning("Takip eklenemedi: %s", exc)
            return {"ok": False, "error": "follow_unsupported", "detail": str(exc)[:200]}
        if not entries:
            return {"ok": False, "error": "follow_empty"}
        item = {"id": uuid.uuid4().hex[:10], "url": url, "name": title[:120], "format": fmt if fmt in ("mp3", "mp4")
                else "mp4", "quality": str(quality or "best"), "enabled": True, "added": time.time(),
                "last_check": time.time(), "last_new": 0, "error": "",
                "seen": [e["id"] for e in entries]}
        with self._lock:
            self._items.append(item)
            self._save()
        for e in reversed(entries[:max(0, int(backfill))]):   # istenirse son N video hemen
            self._queue(item, e)
        log.info("Takip eklendi: %s (%d mevcut, %d indirilecek)", title, len(entries), max(0, int(backfill)))
        return {"ok": True, "follow": {k: v for k, v in item.items() if k != "seen"}}

    def update(self, fid: str, **kw: Any) -> dict[str, Any]:
        with self._lock:
            for x in self._items:
                if x["id"] == fid:
                    for k in ("enabled", "format", "quality", "name"):
                        if k in kw:
                            x[k] = kw[k]
                    self._save()
                    return {"ok": True}
        return {"ok": False, "error": "not_found"}

    def remove(self, fid: str) -> None:
        with self._lock:
            self._items = [x for x in self._items if x["id"] != fid]
            self._save()

    # ---- kontrol
    def _queue(self, item: dict[str, Any], e: dict[str, str]) -> None:
        opts: dict[str, Any] = {"format": item["format"]}
        if item["format"] == "mp4" and item.get("quality") and item["quality"] != "best":
            opts["quality"] = item["quality"]
        try:
            self.add(e["url"], opts, e.get("title") or "")
        except Exception:
            log.exception("Takipten indirme eklenemedi")

    def check(self, fid: str | None = None, force: bool = False) -> int:
        """Vadesi gelen (ya da fid) takipleri kontrol et; eklenen yeni video sayisi."""
        if not self._busy.acquire(blocking=False):
            return 0
        try:
            interval = int(self.settings.get("follow_interval_min") or 60) * 60
            now = time.time()
            with self._lock:
                due = [x for x in self._items if (fid is None or x["id"] == fid) and x.get("enabled")
                       and (force or now - float(x.get("last_check") or 0) >= interval)]
            total = 0
            for item in due:
                try:
                    _, entries = self.lister(item["url"])
                    err = ""
                except Exception as exc:
                    entries, err = [], str(exc)[:200]
                    log.warning("Takip kontrolu basarisiz (%s): %s", item.get("name"), err)
                seen = set(item.get("seen") or [])
                new = [e for e in entries if e["id"] not in seen]
                for e in reversed(new):   # eskiden yeniye sirayla
                    self._queue(item, e)
                with self._lock:
                    item["seen"] = ([e["id"] for e in new] + list(item.get("seen") or []))[:SEEN_KEEP]
                    item["last_check"] = time.time()
                    item["error"] = err
                    if new:
                        item["last_new"] = time.time()
                    self._save()
                if new:
                    total += len(new)
                    self.notify(f"follow:{item.get('name')}:{len(new)}")
                    log.info("Takip: %s -> %d yeni", item.get("name"), len(new))
            return total
        finally:
            self._busy.release()

    def start(self) -> None:
        threading.Thread(target=self._loop, name="kami-follow", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def _loop(self) -> None:
        self._stop.wait(60)   # acilista aga yuklenme
        while not self._stop.is_set():
            if self.settings.get("follow_enabled"):
                try:
                    self.check()
                except Exception:
                    log.exception("Takip dongusu")
            self._wake.wait(60)
            self._wake.clear()
