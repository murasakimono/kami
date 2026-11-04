"""Python <-> JS koprusu. JS tarafinda pywebview.api.<metot> olarak cagrilir."""
from __future__ import annotations

import itertools
import logging
import os
import subprocess
import threading
from typing import TYPE_CHECKING, Any

from app.core.manager import CaptureRejected, PageLinkRejected
from app.core.watchdog import log_slow_calls
from app.core.models import DownloadRequest, Status

if TYPE_CHECKING:
    from app.core.manager import DownloadManager
    from app.core.plugin_api import PluginRegistry
    from app.engines.aria2_engine import Aria2Engine

log = logging.getLogger(__name__)


@log_slow_calls
class Api:
    # pywebview, alt cizgiyle baslayan nitelikleri JS'e acmaz
    def __init__(self, manager: "DownloadManager", engine: "Aria2Engine", registry: "PluginRegistry",
                 bridge_port_getter) -> None:
        self._manager = manager
        self._engine = engine
        self._registry = registry
        self._bridge_port = bridge_port_getter
        self._window = None
        self._watchdog = None                            # UiWatchdog (kalp atisi: get_state)
        self._hotkey = None                              # desktop.HotKey (main kurar)
        self._update_info: dict[str, Any] | None = None  # GitHub'da yeni surum varsa
        self._update_shown = False
        self._media_inbox: list[dict[str, Any]] = []   # eklentiden "Kami'de sec" istekleri
        self._inbox_lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}       # arka plan isleri (job_start / job_result)
        self._job_ids = itertools.count(1)
        self._clip_offers: list[str] = []               # pano izleyicinin buldugu linkler
        self._clip_watcher = None
        self._rd_events: list[dict[str, Any]] = []      # RD bildirimleri (arka plan torrentleri, kopru)
        if getattr(manager, "debrid", None) is not None:
            manager.debrid.notify = self._on_rd_event
        manager.events.on("media.choose", self._on_media_choose)
        self._torrent_inbox: list[dict[str, Any]] = []   # magnet isleyicisinden gelenler (sor / yerel)
        manager.events.on("torrent.request", lambda src: self._on_torrent_request(src))

    # ---------- arka plan isleri ----------
    # Ag/uzun isler arayuzu bekletmesin: job_start hemen is kimligi doner, arayuz job_result ile sorar.
    JOB_METHODS = frozenset({
        "add_url", "media_probe", "cloud_list", "add_cloud", "rd_add", "torrent_choose", "torrent_open",
        "torrent_source", "rd_lists", "rd_status", "rd_set_token", "rd_queue_torrent", "rd_queue_download",
        "rd_delete", "check_update", "hash_file", "make_report", "firewall_allow",
    })

    def job_start(self, name: str, args: list | None = None) -> dict[str, Any]:
        import time as _t
        name = str(name or "")
        if name not in self.JOB_METHODS:
            return {"ok": False, "error": "bad_job"}
        fn = getattr(self, name)
        with self._inbox_lock:
            jid = f"j{next(self._job_ids)}"
            self._jobs[jid] = {"state": "running", "name": name, "t": _t.monotonic()}
            for k in [k for k, v in self._jobs.items() if v["state"] != "running" and _t.monotonic() - v["t"] > 600]:
                del self._jobs[k]   # unutulmus sonuclar

        def run() -> None:
            try:
                res, state = fn(*(args or [])), "done"
            except Exception as exc:
                log.exception("Arka plan isi hatasi: %s", name)
                res, state = {"ok": False, "error": type(exc).__name__}, "done"
            with self._inbox_lock:
                self._jobs[jid] = {"state": state, "result": res, "name": name, "t": _t.monotonic()}

        threading.Thread(target=run, name=f"kami-job-{name}", daemon=True).start()
        return {"ok": True, "job": jid}

    def job_result(self, job: str) -> dict[str, Any]:
        """running | done (+result, bir kez verilir) | lost."""
        with self._inbox_lock:
            j = self._jobs.get(str(job))
            if not j:
                return {"state": "lost"}
            if j["state"] == "running":
                return {"state": "running"}
            self._jobs.pop(str(job), None)
            return {"state": "done", "result": j.get("result")}

    def _set_window(self, window) -> None:
        self._window = window

    # ---------- durum ----------
    def get_state(self) -> dict[str, Any]:
        if self._watchdog:
            self._watchdog.beat()
        items = self._manager.snapshot()
        with self._inbox_lock:
            inbox, self._media_inbox = self._media_inbox, []
            offers, self._clip_offers = self._clip_offers, []
            rd_events, self._rd_events = self._rd_events, []
            torrents, self._torrent_inbox = self._torrent_inbox, []
        rd = self._rd
        upd = None
        with self._inbox_lock:
            if self._update_info and not self._update_shown:   # yeni surum bilgisi arayuze bir kez
                upd, self._update_shown = self._update_info, True
        return {
            "update": upd,
            "rd_progress": rd.progress() if rd is not None and hasattr(rd, "progress") else [],
            "rd_events": rd_events,
            "torrent_requests": torrents,
            "media_requests": inbox,
            "clip_offers": offers,
            "items": [d.to_public() for d in items],
            "total_speed": self._manager.total_speed(),
            "engine_ok": self._engine.running,
            "bridge_port": self._bridge_port(),
        }

    # ---------- pano ----------
    def link_supported(self, url: str) -> bool:
        """Ag kullanmadan (<100 ms): bulut eklentisi, RD hoster (onbellek), yt-dlp ozel cikarici, dosya uzantisi."""
        from app.core.categories import EXT_TO_CATEGORY, extension_of
        from urllib.parse import unquote, urlparse
        if self._manager.cloud.provider_for(url):
            return True
        if self._rd_route(url, wait=False):
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
        from app.core.debrid import is_magnet, is_torrent_url
        if is_magnet(url):
            return self.torrent_source(url)
        if not url.lower().startswith(("http://", "https://", "ftp://")):
            return {"ok": False, "error": "bad_url"}
        if is_torrent_url(url) and not direct:
            return self.torrent_source(url)
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

    # ---------- torrent: Real-Debrid / yerel ----------
    def _torrent_route(self) -> str:
        """'rd' | 'ask' | 'local'. RD ayari (rd_mode) ile ayni mantik; token yoksa ya da Kapali ise yerel.
        RD reddederse (orn. telif engeli) yerele OTOMATIK GECILMEZ: sadece sebep gosterilir."""
        rd = self._rd
        mode = self._manager.settings.get("rd_mode")
        if rd is None or mode == "off" or not rd.has_token():
            return "local"
        return "rd" if mode == "auto" else "ask"

    def torrent_source(self, src: str = "", token: str = "") -> dict[str, Any]:
        """Magnet / .torrent linki (src) ya da dosyadan okunmus torrent (token) -> ayara gore RD / sor / yerel."""
        route = self._torrent_route()
        if route == "rd":
            return self.torrent_choose(src, token, "rd")
        name = ""
        if token:
            try:
                name = self._manager.torrents.get(token)[0].name
            except Exception:
                pass
        payload = {"src": src, "token": token, "name": name}
        return {"ok": True, "torrent_ask" if route == "ask" else "torrent_local": payload}

    def torrent_choose(self, src: str, token: str, target: str) -> dict[str, Any]:
        if target != "rd":
            return self.torrent_open(src, token)
        if token:
            from app.core.debrid import DebridError
            try:
                _, path = self._manager.torrents.get(token)
                self._rd.add_torrent_bytes(path.read_bytes())
            except DebridError as exc:
                return self._rd_err(exc)
            except Exception as exc:
                return {"ok": False, "error": getattr(exc, "code", "rd_failed")}
            return {"ok": True, "rd": True, "torrents": 1, "added": 0}
        return self.rd_add(src)

    def torrent_open(self, src: str = "", token: str = "") -> dict[str, Any]:
        """Yerel torrent: dosya listesi (magnet'te aria2 metadata'yi indirir; es yoksa ~3 dk sonra hata)."""
        from app.core.debrid import is_magnet
        from app.core.torrent import TorrentError
        svc = self._manager.torrents
        try:
            if token:
                meta, _ = svc.get(token)
            elif is_magnet(src):   # arka planda: arayuz "meta veri aranıyor - N eş" gosterir (torrent_meta)
                return {"ok": True, "meta_job": svc.start_magnet(src.strip())}
            elif src.lower().startswith(("http://", "https://")):
                try:
                    data = self._fetch_torrent(src)
                except Exception as exc:
                    log.warning(".torrent indirilemedi: %s", type(exc).__name__)
                    return {"ok": False, "error": "torrent_fetch"}
                token, meta = svc.from_bytes(data)
            else:
                return {"ok": False, "error": "bad_url"}
        except TorrentError as exc:
            log.warning("Torrent acilamadi: %s %s", exc.code, exc.detail)
            return {"ok": False, "error": exc.code, "detail": exc.detail}
        return {"ok": True, "cloud": svc.public(token, meta)}

    def torrent_meta(self, job: str) -> dict[str, Any]:
        """Magnet meta veri isinin durumu: searching (peers, seeders, elapsed) | done (cloud) | error."""
        svc = self._manager.torrents
        j = svc.job(str(job))
        if j.get("state") == "done":
            try:
                meta, _ = svc.get(j["token"])
            except Exception:
                return {"ok": False, "state": "error", "error": "cloud_expired"}
            return {"ok": True, "state": "done", "cloud": svc.public(j["token"], meta)}
        if j.get("state") == "error":
            return {"ok": False, **j}
        return {"ok": True, **j}

    def torrent_meta_cancel(self, job: str) -> None:
        self._manager.torrents.cancel_job(str(job))

    def firewall_status(self) -> dict[str, Any]:
        from app.core import firewall
        return {"ok": True, "rule": firewall.has_rule()}

    def firewall_allow(self) -> dict[str, Any]:
        from app import paths
        from app.core import firewall
        return {"ok": firewall.request_rule(paths.ARIA2_EXE)}

    def torrent_add(self, token: str, indexes: list) -> dict[str, Any]:
        from app.core.torrent import TorrentError
        try:
            d = self._manager.add_torrent(str(token), [int(i) for i in indexes or []])
        except TorrentError as exc:
            return {"ok": False, "error": exc.code}
        return {"ok": True, "ids": [d.id]}

    def torrent_pick_file(self) -> dict[str, Any]:
        """.torrent dosyasi sec -> ayara gore RD / sor / yerel."""
        from app.core.torrent import TorrentError
        if not self._window:
            return {"ok": False, "error": "bad_torrent"}
        import webview
        dialog = getattr(getattr(webview, "FileDialog", None), "OPEN", None) or webview.OPEN_DIALOG
        res = self._window.create_file_dialog(dialog, allow_multiple=False, file_types=("Torrent (*.torrent)",))
        if not res:
            return {"ok": False, "cancelled": True}
        try:
            with open(res[0], "rb") as f:
                token, _ = self._manager.torrents.from_bytes(f.read(10 * 1024 * 1024 + 1))
        except (OSError, TorrentError):
            return {"ok": False, "error": "bad_torrent"}
        return self.torrent_source("", token)

    def _on_torrent_request(self, src: str) -> None:
        """Windows magnet isleyicisi (kopru): ayara gore RD'ye gonder ya da Kami'de sor / dosya listesi ac."""
        route = self._torrent_route()
        if route == "rd":
            def work() -> None:
                r = self.rd_add(src)
                self._on_rd_event({"kind": "torrent", "name": ""} if r.get("ok") else
                                  {"kind": "error", "error": r.get("error"), "detail": r.get("detail", "")})
            threading.Thread(target=work, name="kami-magnet-rd", daemon=True).start()
            return
        with self._inbox_lock:
            self._torrent_inbox.append({"src": src, "route": route})

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

    def _rd_route(self, url: str, wait: bool = True) -> str:
        """'' | 'auto' | 'ask': token varsa ve link RD destekli hoster (ya da .torrent) ise ayara gore."""
        rd = self._rd
        mode = self._manager.settings.get("rd_mode")
        if rd is None or mode == "off" or not (url or "").lower().startswith(("http://", "https://")) \
                or not rd.has_token():
            return ""
        try:   # magnet/.torrent burada degil: torrent_source (RD / yerel torrent secimi)
            return mode if rd.supports(url, wait=wait) else ""
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

    # ---------- sira / oncelik ----------
    def reorder(self, ids: list) -> dict[str, Any]:
        self._manager.reorder([int(i) for i in ids or []])
        return {"ok": True}

    # ---------- SHA256 ----------
    def hash_file(self, download_id: int, expected: str = "") -> dict[str, Any]:
        """SHA256 hesapla (onbellekli); expected verilirse karsilastir ve beklenen olarak kaydet."""
        from app.core import extras
        d = self._manager.store.get(int(download_id))
        if not d or not d.path or not os.path.isfile(d.path):
            return {"ok": False, "error": "no_file"}
        exp = extras.norm_hash(expected) if expected else (d.extra or {}).get("checksum", "")
        if expected and not exp:
            return {"ok": False, "error": "bad_hash"}
        got = (d.extra or {}).get("sha256") or extras.sha256_file(d.path)
        extra = {**(d.extra or {}), "sha256": got}
        if exp:
            extra.update(checksum=exp, checksum_ok=(got == exp))
        self._manager.store.update(d.id, extra=extra)
        return {"ok": True, "sha256": got, "expected": exp, "match": (got == exp) if exp else None}

    # ---------- surukle-birak ----------
    def drop_torrent(self, b64: str) -> dict[str, Any]:
        import base64
        from app.core.torrent import TorrentError
        try:
            data = base64.b64decode(str(b64 or ""), validate=True)
            token, _ = self._manager.torrents.from_bytes(data)
        except (ValueError, TorrentError):
            return {"ok": False, "error": "bad_torrent"}
        return self.torrent_source("", token)

    # ---------- guncelleme / sorun bildir / masaustu ----------
    def check_update(self) -> dict[str, Any]:
        from app.core import extras
        res = extras.check_update()
        self._manager.settings.set("update_last", int(__import__("time").time()))
        if res.get("available"):
            with self._inbox_lock:
                if not self._update_info or self._update_info.get("version") != res.get("version"):
                    self._update_shown = False
                self._update_info = res
        return {"ok": "error" not in res, "current": extras.APP_VERSION, **res}

    def open_release(self) -> bool:
        from app.core import extras
        url = (self._update_info or {}).get("url") or             f"https://github.com/{extras.GITHUB_REPO}/releases"
        if not url.startswith(f"https://github.com/{extras.GITHUB_REPO}/"):
            return False
        os.startfile(url)  # type: ignore[attr-defined]
        return True

    def make_report(self) -> dict[str, Any]:
        from app import paths
        from app.core import extras
        rd = self._rd
        state = {
            "items": [{k: v for k, v in d.to_public().items() if k not in ("referer",)}
                      for d in self._manager.snapshot()[:200]],
            "engine_ok": self._engine.running,
            "rd": {"has_token": bool(rd and rd.has_token()), "pending": rd.progress() if rd else []},
            "settings": {k: v for k, v in self._manager.settings.all().items()},
            "plugins": self.plugins(),
        }
        try:
            out = extras.build_report(state, paths.downloads_dir())
        except Exception as exc:
            log.exception("Sorun paketi olusturulamadi")
            return {"ok": False, "error": type(exc).__name__}
        subprocess.Popen(["explorer", "/select,", os.path.normpath(str(out))])
        return {"ok": True, "path": str(out)}

    def desktop_status(self) -> dict[str, Any]:
        from app.core import desktop, extras
        hk = self._hotkey
        return {"autostart": desktop.autostart_enabled(), "hotkey_error": hk.error if hk else "",
                "defender": bool(extras.mpcmdrun()), "version": extras.APP_VERSION}

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
