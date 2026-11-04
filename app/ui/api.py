"""Python <-> JS koprusu. JS tarafinda pywebview.api.<metot> olarak cagrilir."""
from __future__ import annotations

import logging
import os
import subprocess
import threading
from typing import TYPE_CHECKING, Any

from app.core.manager import CaptureRejected, PageLinkRejected
from app.core.models import DownloadRequest, Status

if TYPE_CHECKING:
    from app.core.manager import DownloadManager
    from app.core.plugin_api import PluginRegistry
    from app.engines.aria2_engine import Aria2Engine

log = logging.getLogger(__name__)


class Api:
    # pywebview, alt cizgiyle baslayan nitelikleri JS'e acmaz
    def __init__(self, manager: "DownloadManager", engine: "Aria2Engine", registry: "PluginRegistry",
                 bridge_port_getter) -> None:
        self._manager = manager
        self._engine = engine
        self._registry = registry
        self._bridge_port = bridge_port_getter
        self._window = None
        self._media_inbox: list[dict[str, Any]] = []   # eklentiden "Kami'de sec" istekleri
        self._inbox_lock = threading.Lock()
        self._clip_offers: list[str] = []               # pano izleyicinin buldugu linkler
        self._clip_watcher = None
        self._rd_events: list[dict[str, Any]] = []      # RD bildirimleri (arka plan torrentleri, kopru)
        if getattr(manager, "debrid", None) is not None:
            manager.debrid.notify = self._on_rd_event
        manager.events.on("media.choose", self._on_media_choose)

    def _set_window(self, window) -> None:
        self._window = window

    # ---------- durum ----------
    def get_state(self) -> dict[str, Any]:
        items = self._manager.snapshot()
        with self._inbox_lock:
            inbox, self._media_inbox = self._media_inbox, []
            offers, self._clip_offers = self._clip_offers, []
            rd_events, self._rd_events = self._rd_events, []
        return {
            "rd_events": rd_events,
            "media_requests": inbox,
            "clip_offers": offers,
            "items": [d.to_public() for d in items],
            "total_speed": self._manager.total_speed(),
            "engine_ok": self._engine.running,
            "bridge_port": self._bridge_port(),
        }

    # ---------- pano ----------
    def link_supported(self, url: str) -> bool:
        """Ag kullanmadan: bulut eklentisi, yt-dlp ozel cikarici ya da bilinen dosya uzantisi."""
        from app.core.categories import EXT_TO_CATEGORY, extension_of
        from urllib.parse import unquote, urlparse
        if self._manager.cloud.provider_for(url):
            return True
        if self._rd_route(url):
            return True
        if extension_of(unquote(urlparse(url).path)) in EXT_TO_CATEGORY:
            return True
        from app.engines import ytdlp_engine as yt
        try:
            return yt.is_supported(url)
        except Exception:
            return False

    def _start_clipboard(self) -> None:
        from app.core.clipboard import ClipboardWatcher

        def offer(url: str) -> None:
            with self._inbox_lock:
                self._clip_offers.append(url)

        self._clip_watcher = ClipboardWatcher(
            self.link_supported, offer, lambda: bool(self._manager.settings.get("clipboard_watch")))
        self._clip_watcher.start()

    def read_clipboard(self) -> str:
        from app.core.clipboard import get_text
        try:
            return get_text()
        except Exception:
            log.exception("Pano okunamadi")
            return ""

    def own_copy(self) -> None:
        """Arayuz kendi menusuyle kopyaladi: izleyici bunu sormasin."""
        if self._clip_watcher:
            self._clip_watcher.ignore_next = True

    # ---------- indirme islemleri ----------
    def add_url(self, url: str, filename: str = "", direct: bool = False) -> dict[str, Any]:
        """Dosya linki -> aria2. yt-dlp'nin tanidigi sayfa linki -> {media: bilgi} (arayuz secim penceresi acar).
        Magnet -> Real-Debrid. RD destekli hoster linki -> rd_mode'a gore (direct=True: RD'siz)."""
        url = (url or "").strip()
        from app.core.debrid import is_magnet
        if is_magnet(url):
            return self.rd_add(url)
        if not url.lower().startswith(("http://", "https://", "ftp://")):
            return {"ok": False, "error": "bad_url"}
        if not direct:
            routed = self._rd_routed(url)
            if routed is not None:
                return routed
        if self._manager.cloud.provider_for(url):
            return self.cloud_list(url)
        from app.engines import ytdlp_engine as yt
        try:
            if yt.is_supported(url):
                return self.media_probe(url)
        except Exception:
            log.exception("yt-dlp tanima hatasi")
        try:
            added = self._manager.add(DownloadRequest(url=url, filename=filename, source="ui"))
        except PageLinkRejected:
            res = self.media_probe(url)   # genel cikarici: sayfadaki gomulu video
            return res if res.get("ok") else {"ok": False, "error": "page_link"}
        except CaptureRejected as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "ids": [d.id for d in added]}

    # ---------- bulut paylasimlari ----------
    def cloud_list(self, url: str) -> dict[str, Any]:
        from app.core.cloud import CloudError
        try:
            token, listing = self._manager.cloud.list(url.strip())
        except CloudError as exc:
            return {"ok": False, "error": exc.code, "detail": exc.detail}
        return {"ok": True, "cloud": listing.public(token)}

    def add_cloud(self, token: str, indexes: list) -> dict[str, Any]:
        from app.core.cloud import CloudError
        try:
            added = self._manager.add_cloud(str(token), [int(i) for i in indexes or []])
        except CloudError as exc:
            return {"ok": False, "error": exc.code, "detail": exc.detail}
        return {"ok": bool(added), "ids": [d.id for d in added],
                "failed": int(getattr(self._manager, "cloud_failed", 0))}

    # ---------- medya (yt-dlp) ----------
    def media_probe(self, url: str, headers: dict | None = None, direct: bool = False) -> dict[str, Any]:
        if not direct:
            routed = self._rd_routed(url or "")
            if routed is not None:
                return routed
        if self._manager.cloud.provider_for(url or ""):
            return self.cloud_list(url)
        from app.engines import ytdlp_engine as yt
        try:
            info = yt.probe(url, headers=headers)
        except yt.MediaError as exc:
            if str(exc) == yt.BOT_ERROR:
                return {"ok": False, "error": yt.BOT_ERROR}
            return {"ok": False, "error": "media_unsupported", "detail": str(exc)}
        except Exception as exc:
            log.exception("Medya bilgisi alinamadi")
            return {"ok": False, "error": "media_unsupported", "detail": str(exc)}
        return {"ok": True, "media": info, "defaults": self._manager.default_media_options()}

    def add_media(self, items: list, options: dict, headers: dict | None = None,
                  page_url: str = "") -> dict[str, Any]:
        """items: [{url, title}] (tek video ya da listeden secilenler)."""
        ids = []
        try:
            for it in items or []:
                url = str(it.get("url") or "").strip()
                if not url.lower().startswith(("http://", "https://")):
                    continue
                d = self._manager.add_media(url, options=options or {}, title=str(it.get("title") or ""),
                                            source="ui", page_url=page_url, headers=headers)
                ids.append(d.id)
        except ValueError as exc:
            return {"ok": False, "error": "bad_time", "detail": str(exc)}
        return {"ok": bool(ids), "ids": ids}

    def _on_media_choose(self, url: str, page_url: str = "", headers: dict | None = None,
                         title: str = "") -> None:
        with self._inbox_lock:
            self._media_inbox.append({"url": url, "page_url": page_url, "headers": headers or {},
                                      "title": title})

    def pause(self, download_id: int) -> None:
        self._manager.pause(int(download_id))

    def resume(self, download_id: int) -> None:
        self._manager.resume(int(download_id))

    def remove(self, download_id: int, delete_file: bool = False) -> None:
        self._manager.remove(int(download_id), bool(delete_file))

    def confirm(self, download_id: int, accept: bool) -> None:
        self._manager.confirm(int(download_id), bool(accept))

    def pause_all(self) -> None:
        for d in self._manager.store.list([Status.ACTIVE, Status.WAITING, Status.QUEUED]):
            self._manager.pause(d.id)

    def resume_all(self) -> None:
        for d in self._manager.store.list([Status.PAUSED]):
            self._manager.resume(d.id)

    def clear_finished(self) -> None:
        self._manager.clear_finished()

    def open_file(self, download_id: int) -> bool:
        d = self._manager.store.get(int(download_id))
        if d and d.path and os.path.isfile(d.path):
            os.startfile(d.path)  # type: ignore[attr-defined]
            return True
        return False

    def open_folder(self, download_id: int) -> bool:
        d = self._manager.store.get(int(download_id))
        if not d:
            return False
        if d.path and os.path.exists(d.path):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(d.path)])
            return True
        if os.path.isdir(d.directory):
            os.startfile(d.directory)  # type: ignore[attr-defined]
            return True
        return False

    def open_downloads_dir(self) -> None:
        base = self._manager.base_dir()
        os.makedirs(base, exist_ok=True)
        os.startfile(base)  # type: ignore[attr-defined]

    # ---------- Real-Debrid ----------
    @property
    def _rd(self):
        return getattr(self._manager, "debrid", None)

    def _rd_route(self, url: str) -> str:
        """'' | 'auto' | 'ask': token varsa ve link RD destekli hoster (ya da .torrent) ise ayara gore."""
        rd = self._rd
        mode = self._manager.settings.get("rd_mode")
        if rd is None or mode == "off" or not (url or "").lower().startswith(("http://", "https://")) \
                or not rd.has_token():
            return ""
        from app.core.debrid import is_torrent_url
        try:
            return mode if (is_torrent_url(url) or rd.supports(url)) else ""
        except Exception:
            log.exception("RD destek kontrolu")
            return ""

    def _rd_routed(self, url: str) -> dict[str, Any] | None:
        mode = self._rd_route(url)
        if mode == "ask":
            return {"ok": True, "rd_ask": url}
        if mode == "auto":
            res = self.rd_add(url)
            if res.get("ok"):
                return res
            log.info("RD otomatik gecis basarisiz (%s), dogrudan deneniyor", res.get("error"))
        return None

    def _on_rd_event(self, ev: dict[str, Any]) -> None:
        with self._inbox_lock:
            self._rd_events.append(ev)

    @staticmethod
    def _rd_err(exc) -> dict[str, Any]:
        return {"ok": False, "error": exc.code, "detail": exc.detail}

    def rd_status(self) -> dict[str, Any]:
        if self._rd is None:
            return {"has_token": False, "available": False}
        return {**self._rd.status(), "available": True}

    def rd_set_token(self, token: str) -> dict[str, Any]:
        from app.core.debrid import DebridError
        try:
            u = self._rd.set_token(str(token or ""))
        except DebridError as exc:
            return self._rd_err(exc)
        return {"ok": True, "username": u.get("username", "")}

    def rd_clear_token(self) -> dict[str, Any]:
        self._rd.clear_token()
        return {"ok": True}

    @staticmethod
    def _fetch_torrent(url: str) -> bytes:
        import requests
        limit = 10 * 1024 * 1024
        with requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"}, stream=True) as r:
            r.raise_for_status()
            data = r.raw.read(limit + 1, decode_content=True)
        if len(data) > limit:
            raise ValueError("torrent too large")
        return data

    def rd_add(self, text: str) -> dict[str, Any]:
        """Yapistir-gec: her satir magnet / .torrent linki / hoster linki."""
        from app.core.debrid import DebridError
        if self._rd is None:
            return {"ok": False, "error": "rd_no_token"}
        lines = [x.strip() for x in str(text or "").splitlines() if x.strip()]
        if not lines:
            return {"ok": False, "error": "bad_url"}
        torrents = added = 0
        err = None
        for line in lines:
            try:
                r = self._rd.add_any(line, self._fetch_torrent)
                torrents += 1 if "torrent" in r else 0
                added += int(r.get("added") or 0)
            except DebridError as exc:
                err = exc
            except Exception as exc:   # .torrent indirilemedi vb.
                log.warning("RD ekleme hatasi: %s", type(exc).__name__)
                err = DebridError("rd_failed", type(exc).__name__)
        if not torrents and not added:
            return self._rd_err(err) if err else {"ok": False, "error": "rd_failed"}
        return {"ok": True, "rd": True, "torrents": torrents, "added": added,
                "partial": err.code if err else ""}

    def rd_pick_torrent(self) -> dict[str, Any]:
        from app.core.debrid import DebridError
        if not self._window or self._rd is None:
            return {"ok": False, "error": "rd_failed"}
        import webview
        dialog = getattr(getattr(webview, "FileDialog", None), "OPEN", None) or webview.OPEN_DIALOG
        res = self._window.create_file_dialog(dialog, allow_multiple=True, file_types=("Torrent (*.torrent)",))
        if not res:
            return {"ok": False, "cancelled": True}
        n, err = 0, None
        for path in res:
            try:
                with open(path, "rb") as f:
                    self._rd.add_torrent_bytes(f.read(10 * 1024 * 1024))
                n += 1
            except DebridError as exc:
                err = exc
            except OSError:
                err = DebridError("rd_bad_torrent")
        if not n:
            return self._rd_err(err) if err else {"ok": False, "error": "rd_failed"}
        return {"ok": True, "rd": True, "torrents": n, "added": 0}

    def rd_lists(self) -> dict[str, Any]:
        from app.core.debrid import DebridError
        try:
            return {"ok": True, **self._rd.account_lists()}
        except DebridError as exc:
            return self._rd_err(exc)

    def rd_queue_torrent(self, tid: str) -> dict[str, Any]:
        from app.core.debrid import DebridError
        try:
            return {"ok": True, "added": self._rd.queue_torrent(str(tid))}
        except DebridError as exc:
            return self._rd_err(exc)

    def rd_queue_download(self, item: dict) -> dict[str, Any]:
        from app.core.debrid import DebridError
        try:
            return {"ok": True, "added": self._rd.queue_download(dict(item or {}))}
        except DebridError as exc:
            return self._rd_err(exc)
        except KeyError:
            return {"ok": False, "error": "rd_failed"}

    def rd_delete(self, kind: str, rid: str) -> dict[str, Any]:
        from app.core.debrid import DebridError
        try:
            if kind == "torrent":
                self._rd.client.delete_torrent(str(rid))
            else:
                self._rd.client.delete_download(str(rid))
            return {"ok": True}
        except DebridError as exc:
            return self._rd_err(exc)

    # ---------- ayarlar ----------
    def get_settings(self) -> dict[str, Any]:
        s = self._manager.settings.all()
        s["_effective_download_dir"] = self._manager.base_dir()
        return s

    def set_setting(self, key: str, value: Any) -> dict[str, Any]:
        try:
            self._manager.settings.set(key, value)
            return {"ok": True, "value": self._manager.settings.get(key)}
        except (KeyError, ValueError, TypeError) as exc:
            return {"ok": False, "error": str(exc)}

    def choose_folder(self) -> str:
        if not self._window:
            return ""
        import webview
        dialog = getattr(getattr(webview, "FileDialog", None), "FOLDER", None)
        if dialog is None:
            dialog = webview.FOLDER_DIALOG  # eski surumler
        result = self._window.create_file_dialog(dialog, directory=self._manager.base_dir())
        return result[0] if result else ""

    def plugins(self) -> list[dict[str, Any]]:
        return [
            {"id": p.id, "name": p.name, "version": p.version, "description": p.description,
             "enabled": p.enabled, "error": p.error}
            for p in self._registry.plugins
        ]
