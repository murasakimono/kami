"""Indirme yoneticisi: kuyruk + motor + eklentiler + olaylar arasindaki yapistirici.

Akis:
  add(request) -> Resolver'lar (eklentiler) -> kayit (SQLite) -> motor.start
  arka plan dongusu motor durumunu okur, kaydi gunceller, olay yayar.
"""
from __future__ import annotations

import functools
import logging
import os
import re
import threading
import time
from dataclasses import replace
from typing import Any, Callable
from urllib.parse import urlparse

from app import paths
from app.core.categories import category_for, extension_of, filename_from_url, folder_for, sanitize_filename
from app.core.events import EventBus
from app.core.models import Download, DownloadRequest, Status
from app.core.plugin_api import Engine, PluginRegistry
from app.core.probe import ProbeResult, probe
from app.core.queue_store import DownloadStore
from app.core.settings import Settings

log = logging.getLogger(__name__)

_ARIA2_TO_STATUS = {
    "active": Status.ACTIVE,
    "waiting": Status.WAITING,
    "paused": Status.PAUSED,
    "error": Status.ERROR,
    "complete": Status.COMPLETE,
    "removed": Status.REMOVED,
}


def _transition(fn):
    """Kullanici islemleri ve durum dongusunun yazma adimi ayni kilitten gecer (yaris olmasin)."""
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        with self._state:
            return fn(self, *args, **kwargs)
    return wrapper


class CaptureRejected(Exception):
    """Tarayici yakalamasi kurallara gore reddedildi -> tarayici kendisi indirsin."""


class PageLinkRejected(CaptureRejected):
    """Link bir dosya degil, web sayfasi. Arayuz/kopru bunu yt-dlp ile medya olarak cozmeyi dener."""

    def __init__(self) -> None:
        super().__init__("page_link")


class DownloadManager:
    def __init__(self, store: DownloadStore, engine: Engine, events: EventBus, settings: Settings,
                 registry: PluginRegistry | None = None, poll_interval: float = 0.5,
                 prober: Callable[..., ProbeResult] | None = probe, media: Any = None) -> None:
        self.prober = prober  # None = yoklama yok (testler)
        self.media = media    # MediaRunner (yt-dlp); None = medya devre disi
        if media is not None:
            media.on_event = self._on_media_event
        self._media_live: dict[int, dict[str, Any]] = {}       # id -> {speed, phase}
        self._media_progress: dict[int, tuple[int, int]] = {}  # id -> (downloaded, size); DB'ye her seferinde yazilmaz
        self.store = store
        self.engine = engine
        self.events = events
        self.settings = settings
        self.registry = registry or PluginRegistry()
        from app.core.cloud import CloudService
        self.cloud = CloudService(self.registry.clouds)
        self.poll_interval = poll_interval
        self._live: dict[int, dict[str, Any]] = {}   # id -> {speed, connections}
        self._retries: dict[int, int] = {}           # id -> otomatik yeniden deneme sayisi
        self._lock = threading.RLock()     # _live / _retries
        self._state = threading.RLock()    # durum gecisleri
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---------- yasam dongusu ----------
    def start(self) -> None:
        self._recover()
        self._thread = threading.Thread(target=self._loop, name="kami-poll", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def _recover(self) -> None:
        """Onceki oturumdan kalanlar: motor yeni basladigi icin gid'ler gecersiz."""
        for d in self.store.list([Status.ACTIVE, Status.WAITING, Status.QUEUED]):
            self.store.update(d.id, gid="", status=Status.QUEUED)
            self._start_engine(self.store.get(d.id))  # type: ignore[arg-type]
        for d in self.store.list([Status.PAUSED]):
            self.store.update(d.id, gid="")

    # ---------- ekleme ----------
    def base_dir(self) -> str:
        return self.settings.get("download_dir") or str(paths.downloads_dir())

    def check_capture(self, req: DownloadRequest) -> None:
        """Tarayicidan otomatik yakalanan indirmeler icin kurallar."""
        if not self.settings.get("capture_enabled"):
            raise CaptureRejected("capture_disabled")
        host = (urlparse(req.url).hostname or "").lower()
        page_host = (urlparse(req.page_url).hostname or "").lower() if req.page_url else ""
        for ex in self.settings.get("capture_exclude_hosts") or []:
            ex = ex.lower().lstrip(".")
            for h in (host, page_host):
                if h and (h == ex or h.endswith("." + ex)):
                    raise CaptureRejected("excluded_host")
        min_size = int(self.settings.get("capture_min_size_kib") or 0) * 1024
        if req.size and 0 < req.size < min_size:
            raise CaptureRejected("too_small")

    def needs_confirm(self, filename: str, url: str) -> bool:
        exts = set(self.settings.get("confirm_extensions") or [])
        name = filename or filename_from_url(url)
        return extension_of(name) in exts

    def add(self, req: DownloadRequest, *, confirm: bool | None = None) -> list[Download]:
        """Istegi (gerekirse eklentilerle cozup) kuyruga ekler. Eklenen kayitlari dondurur."""
        if req.source == "browser":
            self.check_capture(req)
        requests = self._resolve(req) if req.kind != "media" else [req]
        added: list[Download] = []
        for r in requests:
            if r.kind == "media":
                added.append(self._add_media(r))
                continue
            max_conn = 0
            info = self._probe(r)
            if info and info.ok:
                if info.is_html and r.source in ("ui", "context_menu") and not info.filename \
                        and not filename_from_url(r.url).lower().endswith((".htm", ".html")):
                    raise PageLinkRejected()
                if not info.ranges:
                    max_conn = 1  # sunucu parcali indirmeyi desteklemiyor: bosuna 16 baglanti deneme
                if not r.filename and info.filename:
                    r = replace(r, filename=info.filename)
                if not r.size and info.size > 1:
                    r = replace(r, size=info.size)
                if not r.mime and info.content_type:
                    r = replace(r, mime=info.content_type)
            filename = sanitize_filename(r.filename) if r.filename else ""
            category = category_for(filename, r.url, r.mime)
            directory = r.directory or folder_for(
                self.base_dir(), category, bool(self.settings.get("use_category_folders")))
            need_confirm = confirm if confirm is not None else (
                r.source in ("browser", "context_menu") and self.needs_confirm(filename, r.url))
            d = self.store.add(
                url=r.url, filename=filename, directory=directory, category=category,
                status=Status.CONFIRM if need_confirm else Status.QUEUED,
                size=r.size or 0, referer=r.referer, headers=r.headers, source=r.source,
                page_url=r.page_url, max_conn=max_conn, options=r.options,
            )
            self.events.emit("download.added", download=d)
            if need_confirm:
                self.events.emit("ui.attention", reason="confirm")
            else:
                d = self._start_engine(d)
            added.append(d)
        return added

    def _probe(self, r: DownloadRequest) -> ProbeResult | None:
        if not self.prober or r.source.startswith("plugin") or not r.url.lower().startswith(("http://", "https://")):
            return None
        try:
            # tarayici indirmesi bekletiliyor: kisa tut
            return self.prober(r.url, headers=r.headers, referer=r.referer,
                               timeout=4.0 if r.source == "browser" else 6.0)
        except Exception:
            log.exception("Link yoklanamadi: %s", r.url)
            return None

    def _resolve(self, req: DownloadRequest) -> list[DownloadRequest]:
        for resolver in self.registry.resolvers:
            try:
                if resolver.can_handle(req):
                    out = resolver.resolve(req)
                    if out:
                        return out
            except Exception:
                log.exception("Resolver hata verdi: %s", resolver.name)
        return [req]

    def _start_engine(self, d: Download) -> Download:
        if d.kind == "media":
            return self._start_media(d)
        try:
            os.makedirs(d.directory, exist_ok=True)
            gid = self.engine.start(d)
            d = self.store.update(d.id, gid=gid, status=Status.WAITING, error="")  # type: ignore[assignment]
        except Exception as exc:
            log.exception("Motor indirmeyi baslatamadi: %s", d.url)
            d = self.store.update(d.id, status=Status.ERROR, error=str(exc))  # type: ignore[assignment]
            self.events.emit("download.failed", download=d)
        self.events.emit("download.updated", download=d)
        return d

    # ---------- bulut paylasimlari ----------
    def add_cloud(self, token: str, indexes: list[int]) -> list[Download]:
        """Listelenmis paylasimdan secilen dosyalari kuyruga ekler (alt klasor yapisi korunur)."""
        from app.core.cloud import CloudError
        provider, listing = self.cloud.get(token)
        root = ""
        if listing.is_folder:
            root = os.path.join(self.base_dir(), sanitize_filename(listing.title) or provider.name)
        files = [listing.files[int(i)] for i in indexes if 0 <= int(i) < len(listing.files)]

        def resolve(f):
            try:
                return f, provider.file_request(listing, f), None
            except Exception as exc:  # tek dosyanin hatasi digerlerini durdurmasin
                log.warning("Bulut dosya linki alinamadi (%s): %s", f.path, exc)
                return f, None, exc

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=8) as pool:   # Drive/Mediafire dosya basina istek atar
            resolved = list(pool.map(resolve, files))
        added: list[Download] = []
        first_error = None
        self.cloud_failed = sum(1 for _, res, _ in resolved if res is None)   # arayuz uyarisi icin
        for f, res, exc in resolved:
            if res is None:
                first_error = first_error or exc
                continue
            url, headers, options = res
            directory = ""
            if root:
                sub = [sanitize_filename(p) for p in f.folder.split("/") if p]
                directory = os.path.join(root, *[p for p in sub if p])
            added += self.add(DownloadRequest(
                url=url, filename=f.name, headers=headers, size=f.size, source=f"plugin:{provider.name}",
                directory=directory, page_url=listing.url, options=options))
        log.info("Bulut kuyruga eklendi (%s): %s | %d/%d dosya linki cozuldu",
                 provider.name, listing.title, len(files) - self.cloud_failed, len(files))
        if not added and first_error is not None:
            if isinstance(first_error, CloudError):
                raise first_error
            raise CloudError("cloud_failed", str(first_error))
        return added

    # ---------- medya (yt-dlp) ----------
    def default_media_options(self) -> dict[str, Any]:
        s = self.settings
        return {"format": s.get("media_format"), "quality": s.get("media_quality"),
                "audio_kbps": s.get("media_audio_kbps"), "subs": s.get("media_subs"),
                "embed": s.get("media_embed"), "sponsorblock": s.get("media_sponsorblock"),
                "start": "", "end": "", "no_playlist": True}

    def add_media(self, url: str, *, options: dict[str, Any] | None = None, title: str = "",
                  source: str = "ui", page_url: str = "", headers: dict[str, str] | None = None) -> Download:
        from app.engines.ytdlp_engine import _clean_headers, parse_time
        opts = self.default_media_options()
        for k, v in (options or {}).items():
            if k in opts:
                opts[k] = v
        parse_time(opts.get("start", ""))   # gecersizse ValueError
        parse_time(opts.get("end", ""))
        h = _clean_headers(url, headers)
        if h:
            opts["headers"] = h
        if title and source == "extension":
            opts["out_title"] = title   # eklenti sadece yakalanan akis/dogrudan dosyada baslik yollar
        return self.add(DownloadRequest(url=url, filename=title, source=source, page_url=page_url,
                                        kind="media", options=opts))[0]

    def _add_media(self, r: DownloadRequest) -> Download:
        opts = dict(r.options)
        category = "music" if opts.get("format") == "mp3" else "video"
        directory = r.directory or folder_for(
            self.base_dir(), category, bool(self.settings.get("use_category_folders")))
        d = self.store.add(
            url=r.url, filename=sanitize_filename(r.filename) if r.filename else "", directory=directory,
            category=category, status=Status.QUEUED, referer=r.referer, headers={}, source=r.source,
            page_url=r.page_url, kind="media", options=opts,
        )
        self.events.emit("download.added", download=d)
        return self._start_engine(d)

    def _start_media(self, d: Download) -> Download:
        if self.media is None:
            d = self.store.update(d.id, status=Status.ERROR, error="yt-dlp yok")  # type: ignore[assignment]
            self.events.emit("download.updated", download=d)
            return d
        os.makedirs(d.directory, exist_ok=True)
        d = self.store.update(d.id, status=Status.WAITING, error="")  # type: ignore[assignment]
        self.media.start(d.id, d.url, d.directory, d.options)
        self.events.emit("download.updated", download=d)
        return d

    def _on_media_event(self, download_id: int, kind: str, **f: Any) -> None:
        """MediaRunner thread'inden gelir: started | progress | done | error | cancelled."""
        with self._state:
            d = self.store.get(download_id)
            if not d or d.kind != "media":
                return
            if kind == "cancelled" or d.status not in (Status.WAITING, Status.ACTIVE):
                with self._lock:   # kullanici duraklatti/sildi: kayda dokunma
                    self._media_live.pop(download_id, None)
                return
            fields: dict[str, Any] = {}
            if kind in ("started", "progress"):
                if d.status != Status.ACTIVE:
                    fields["status"] = Status.ACTIVE
                if f.get("title") and not d.filename:
                    fields["filename"] = sanitize_filename(f["title"])
                if f.get("base") and d.options.get("base") != f["base"]:
                    fields["options"] = {**d.options, "base": f["base"]}
                with self._lock:
                    cur = self._media_live.setdefault(download_id, {"speed": 0, "phase": ""})
                    if "speed" in f:
                        cur["speed"] = int(f["speed"])
                    if f.get("phase"):
                        cur["phase"] = f["phase"]
                    if "downloaded" in f or "size" in f:
                        dl, sz = self._media_progress.get(download_id, (d.downloaded, d.size))
                        self._media_progress[download_id] = (int(f.get("downloaded", dl)),
                                                             int(f.get("size") or sz))
                if not fields:
                    return  # sik ilerleme: DB'ye yazma, canli tablodan okunur
            elif kind == "done":
                self._flush_media_progress(download_id)
                path = f.get("path") or ""
                fields.update(status=Status.COMPLETE, finished_at=time.time())
                if path and os.path.isfile(path):
                    directory, filename = os.path.split(path)
                    size = os.path.getsize(path)
                    fields.update(directory=directory, filename=filename, size=size, downloaded=size)
                with self._lock:
                    self._media_live.pop(download_id, None)
            elif kind == "error":
                self._flush_media_progress(download_id)
                fields.update(status=Status.ERROR, error=f.get("error") or "yt-dlp hatasi",
                              finished_at=time.time())
                with self._lock:
                    self._media_live.pop(download_id, None)
            nd = self.store.update(d.id, **fields)
        if kind == "done":
            self.events.emit("download.completed", download=nd)
        elif kind == "error":
            self.events.emit("download.failed", download=nd)
        self.events.emit("download.updated", download=nd)

    def _flush_media_progress(self, download_id: int) -> None:
        with self._lock:
            p = self._media_progress.pop(download_id, None)
        if p:
            self.store.update(download_id, downloaded=p[0], size=p[1])

    @staticmethod
    def _media_files(d: Download, include_final: bool) -> list[str]:
        """Medya isinin diskteki dosyalari: yarim parcalar (+ istenirse bitmis dosya)."""
        out = []
        if include_final and d.status == Status.COMPLETE and d.path and os.path.isfile(d.path):
            out.append(d.path)
        base = (d.options or {}).get("base") or ""
        if base and os.path.isdir(d.directory):
            for name in os.listdir(d.directory):
                if not name.startswith(base + ".") or name == d.filename:
                    continue
                if re.search(r"\.(part|aria2|ytdl|temp)$|\.part-Frag\d+|\.f\d+[^.]*\.\w+|\.(vtt|srt|ass|jpg|webp|png)$", name):
                    out.append(os.path.join(d.directory, name))
        return out

    # ---------- kullanici islemleri ----------
    @_transition
    def confirm(self, download_id: int, accept: bool) -> None:
        d = self.store.get(download_id)
        if not d or d.status != Status.CONFIRM:
            return
        if accept:
            self._start_engine(self.store.update(d.id, status=Status.QUEUED))  # type: ignore[arg-type]
        else:
            self.store.delete(d.id)
            self.events.emit("download.removed", download_id=d.id)

    @_transition
    def pause(self, download_id: int) -> None:
        d = self.store.get(download_id)
        if not d or d.status not in (Status.ACTIVE, Status.WAITING, Status.QUEUED):
            return
        if d.kind == "media":
            if self.media is not None:
                self.media.cancel(d.id)
            self._flush_media_progress(d.id)
            with self._lock:
                self._media_live.pop(d.id, None)
        elif d.gid:
            self.engine.pause(d.gid)
        d = self.store.update(d.id, status=Status.PAUSED)
        self.events.emit("download.updated", download=d)

    @_transition
    def resume(self, download_id: int) -> None:
        d = self.store.get(download_id)
        if not d or d.status not in (Status.PAUSED, Status.ERROR):
            return
        with self._lock:
            self._retries.pop(d.id, None)
        if d.kind == "media":
            self._start_engine(self.store.update(d.id, status=Status.QUEUED, error=""))  # type: ignore[arg-type]
            return
        if d.status == Status.PAUSED and d.gid:
            try:
                self.engine.resume(d.gid)
                d = self.store.update(d.id, status=Status.WAITING)
                self.events.emit("download.updated", download=d)
                return
            except Exception:
                log.info("unpause basarisiz, yeniden ekleniyor: %s", d.gid)
        # gid yok (yeniden baslatildi) ya da hata -> ayni dir/out ile yeniden ekle, .aria2 ile devam eder
        if d.gid:
            self.engine.remove(d.gid)
        self._start_engine(self.store.update(d.id, gid="", status=Status.QUEUED, error=""))  # type: ignore[arg-type]

    @_transition
    def remove(self, download_id: int, delete_file: bool = False) -> None:
        d = self.store.get(download_id)
        if not d:
            return
        if d.kind == "media":
            if self.media is not None:
                self.media.cancel(d.id)
            # yarim parcalar her zaman temizlenir; bitmis dosya sadece "dosyayla sil"de
            targets = self._media_files(d, include_final=delete_file)
            if targets and self.media is not None:
                time.sleep(0.5)  # iptal edilen is aria2/ffmpeg dosyalarini birakabilsin
            for p in targets:
                try:
                    os.remove(p)
                except OSError:
                    log.warning("Dosya silinemedi: %s", p)
            self.store.delete(d.id)
            with self._lock:
                self._media_live.pop(d.id, None)
                self._media_progress.pop(d.id, None)
            self.events.emit("download.removed", download_id=d.id)
            return
        if d.gid:
            self.engine.remove(d.gid)
        if delete_file and d.path:
            for p in (d.path, d.path + ".aria2"):
                try:
                    if os.path.isfile(p):
                        os.remove(p)
                except OSError:
                    log.warning("Dosya silinemedi: %s", p)
        elif d.status != Status.COMPLETE and d.path:
            # yarim indirmenin kontrol dosyasi tek basina ise yaramaz
            try:
                if os.path.isfile(d.path + ".aria2"):
                    os.remove(d.path + ".aria2")
            except OSError:
                pass
        self.store.delete(d.id)
        with self._lock:
            self._live.pop(d.id, None)
        self.events.emit("download.removed", download_id=d.id)

    @_transition
    def clear_finished(self) -> None:
        for d in self.store.list([Status.COMPLETE]):
            self.store.delete(d.id)
            self.events.emit("download.removed", download_id=d.id)

    # ---------- durum ----------
    def snapshot(self) -> list[Download]:
        items = self.store.list()
        with self._lock:
            live = dict(self._live)
            mlive = {k: dict(v) for k, v in self._media_live.items()}
            mprog = dict(self._media_progress)
        out = []
        for d in items:
            if d.kind == "media":
                if d.id in mprog and d.status == Status.ACTIVE:
                    d = replace(d, downloaded=mprog[d.id][0], size=mprog[d.id][1])
                info = mlive.get(d.id)
                if info and d.status in (Status.ACTIVE, Status.WAITING):
                    d = replace(d, speed=info["speed"], phase=info["phase"])
            else:
                info = live.get(d.id)
                if info and d.status in (Status.ACTIVE, Status.WAITING):
                    d = replace(d, speed=info["speed"], connections=info["connections"])
            out.append(d)
        return out

    def total_speed(self) -> int:
        with self._lock:
            return sum(v["speed"] for v in self._live.values()) + \
                sum(v.get("speed", 0) for v in self._media_live.values())

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception:
                log.exception("Durum dongusu hatasi")
            self._stop.wait(self.poll_interval)

    def poll_once(self) -> None:
        tracked = [d for d in self.store.list([Status.ACTIVE, Status.WAITING, Status.PAUSED]) if d.gid]
        if not tracked:
            with self._lock:
                self._live.clear()
            return
        statuses = self.engine.status([d.gid for d in tracked])
        live: dict[int, dict[str, Any]] = {}
        for old in tracked:
            with self._state:
                # motor sorgulanirken kullanici duraklatmis/silmis olabilir: guncel kayitla karar ver
                d = self.store.get(old.id)
                if not d or d.status != old.status or d.gid != old.gid:
                    continue
                self._apply_status(d, statuses.get(d.gid), live)
        with self._lock:
            self._live = live

    def _apply_status(self, d: Download, s: dict[str, Any] | None, live: dict[int, dict[str, Any]]) -> None:
        if not s or s.get("status") == "missing":
            if d.status != Status.PAUSED:
                # motor bu isi bilmiyor (yeniden basladi vb.) -> yeniden kuyruga al
                self._start_engine(self.store.update(d.id, gid="", status=Status.QUEUED))  # type: ignore[arg-type]
            return
        new_status = _ARIA2_TO_STATUS.get(s["status"], d.status)
        if new_status == Status.ERROR and d.status != Status.ERROR and self._auto_retry(d, s):
            return
        if d.status == Status.PAUSED and new_status in (Status.ACTIVE, Status.WAITING):
            new_status = Status.PAUSED  # pause istegi motora henuz yansimadi
        fields: dict[str, Any] = {"status": new_status}
        if s["total"]:
            fields["size"] = s["total"]
        fields["downloaded"] = s["completed"]
        if s["path"]:
            directory, filename = os.path.split(s["path"])
            if filename and filename != d.filename:
                fields["filename"] = filename
                if d.category == "other":
                    fields["category"] = category_for(filename)
            if directory and os.path.normcase(directory) != os.path.normcase(d.directory):
                fields["directory"] = directory
        if new_status == Status.ERROR:
            fields["error"] = s["error"] or f"aria2 hata kodu {s['error_code']}"
        if new_status in (Status.COMPLETE, Status.ERROR) and not d.finished_at:
            fields["finished_at"] = time.time()
        if new_status in (Status.ACTIVE, Status.WAITING):
            live[d.id] = {"speed": s["speed"], "connections": s["connections"]}

        completing = new_status == Status.COMPLETE and d.status != Status.COMPLETE
        if completing:
            # tasima/son islem/temizlik COMPLETE yazilmadan once: disaridan bakan yarim hal gormesin
            fields.update(self._after_complete(replace(d, **fields)))
        changed = any(getattr(d, k) != v for k, v in fields.items())
        if changed:
            nd = self.store.update(d.id, **fields)
            if completing:
                self.events.emit("download.completed", download=nd)
            elif new_status == Status.ERROR and d.status != Status.ERROR:
                self.events.emit("download.failed", download=nd)
            self.events.emit("download.updated", download=nd)

    # aria2 hata kodlari: 1 bilinmeyen ("No URI available" dahil), 2 zaman asimi, 6 ag sorunu,
    # 22 beklenmeyen HTTP durumu (429/503 gibi), 29 sunucu asiri yuklu
    _RETRYABLE_CODES = {"1", "2", "6", "22", "29"}
    _MAX_AUTO_RETRIES = 3

    def _auto_retry(self, d: Download, s: dict[str, Any]) -> bool:
        """Sunucu cok baglantiyi reddedince (429 vb.) baglanti sayisini dusurup kaldigi yerden devam et."""
        code = str(s.get("error_code") or "")
        if code not in self._RETRYABLE_CODES and "No URI available" not in (s.get("error") or ""):
            return False
        with self._lock:
            n = self._retries.get(d.id, 0)
            if n >= self._MAX_AUTO_RETRIES:
                return False
            self._retries[d.id] = n + 1
        current = d.max_conn or int(getattr(self.engine, "connections", 16))
        next_conn = 4 if current > 4 else 1
        log.info("Otomatik yeniden deneme %s/%s (%s, kod %s): baglanti %s -> %s",
                 n + 1, self._MAX_AUTO_RETRIES, d.filename or d.url, code, current, next_conn)
        try:
            self.engine.remove(d.gid)
        except Exception:
            pass
        nd = self.store.update(d.id, gid="", status=Status.QUEUED, max_conn=next_conn,
                               downloaded=s.get("completed", d.downloaded), size=s.get("total") or d.size)
        self.events.emit("download.updated", download=nd)

        def restart() -> None:
            with self._state:
                cur = self.store.get(d.id)
                if cur and cur.status == Status.QUEUED and not cur.gid:
                    self._start_engine(cur)

        t = threading.Timer(1.5 * (n + 1), restart)
        t.daemon = True
        t.start()
        return True

    def _after_complete(self, d: Download) -> dict[str, Any]:
        """Tamamlanan indirme icin tasima + son islem + motor temizligi. Degisen alanlari dondurur."""
        changes: dict[str, Any] = {}
        # Kategori baslangicta bilinmiyorduysa (ad sunucudan geldi) dosyayi dogru klasore tasi
        if not d.source.startswith("plugin") and self.settings.get("use_category_folders") and d.filename:
            base = self.base_dir()
            if os.path.normcase(d.directory) == os.path.normcase(base):
                cat = category_for(d.filename)
                target_dir = folder_for(base, cat, True)
                if os.path.normcase(target_dir) != os.path.normcase(d.directory):
                    moved = self._move(d, target_dir)
                    if moved:
                        changes.update(directory=target_dir, filename=moved, category=cat)
                        d = replace(d, **changes)
        for pp in self.registry.postprocessors:
            try:
                if pp.applies(d):
                    pp.process(d)
            except Exception:
                log.exception("PostProcessor hata verdi: %s", pp.name)
        if d.gid:
            try:
                self.engine.remove(d.gid)  # motorun sonuc listesinden temizle
            except Exception:
                pass
            changes["gid"] = ""
        return changes

    @staticmethod
    def _move(d: Download, target_dir: str) -> str:
        """Dosyayi tasir, yeni dosya adini dondurur (basarisizsa bos)."""
        try:
            os.makedirs(target_dir, exist_ok=True)
            base, ext = os.path.splitext(d.filename)
            target = os.path.join(target_dir, d.filename)
            n = 1
            while os.path.exists(target):
                target = os.path.join(target_dir, f"{base} ({n}){ext}")
                n += 1
            os.replace(d.path, target)
            return os.path.basename(target)
        except OSError:
            log.exception("Dosya kategori klasorune tasinamadi: %s", d.path)
            return ""
