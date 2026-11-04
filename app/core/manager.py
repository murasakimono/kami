"""Indirme yoneticisi: kuyruk + motor + eklentiler + olaylar arasindaki yapistirici.

Akis:
  add(request) -> Resolver'lar (eklentiler) -> kayit (SQLite) -> motor.start
  arka plan dongusu motor durumunu okur, kaydi gunceller, olay yayar.
"""
from __future__ import annotations

import functools
import logging
import os
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
    """Link bir dosya degil, web sayfasi (orn. youtube.com/watch). Aşama 2'de yt-dlp bunlari cozecek."""

    def __init__(self) -> None:
        super().__init__("page_link")


class DownloadManager:
    def __init__(self, store: DownloadStore, engine: Engine, events: EventBus, settings: Settings,
                 registry: PluginRegistry | None = None, poll_interval: float = 0.5,
                 prober: Callable[..., ProbeResult] | None = probe) -> None:
        self.prober = prober  # None = yoklama yok (testler)
        self.store = store
        self.engine = engine
        self.events = events
        self.settings = settings
        self.registry = registry or PluginRegistry()
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
        requests = self._resolve(req)
        added: list[Download] = []
        for r in requests:
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
                page_url=r.page_url, max_conn=max_conn,
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
        if d.gid:
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
        out = []
        for d in items:
            info = live.get(d.id)
            if info and d.status in (Status.ACTIVE, Status.WAITING):
                d = replace(d, speed=info["speed"], connections=info["connections"])
            out.append(d)
        return out

    def total_speed(self) -> int:
        with self._lock:
            return sum(v["speed"] for v in self._live.values())

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
