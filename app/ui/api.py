"""Python <-> JS koprusu. JS tarafinda pywebview.api.<metot> olarak cagrilir."""
from __future__ import annotations

import itertools
import re
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
        self._media_post = None                          # Asama 6b (main baglar)
        self._ai = None
        self._genius = None
        self._ai_events: list[str] = []
        self._follow = None                              # follow.FollowService
        # Asama 6c (main baglar)
        self._history = None
        self._shutdown = None
        self._watcher = None
        self._phone = None
        self._phone_key = None
        self._ntfy = None
        self._media = None                               # media_server.MediaServer (P1 oynatici, main baglar)
        self._play_inbox: list[str] = []                 # (eski) Sunak ici oynatici kuyrugu
        self._player_q: list[dict[str, Any]] = []        # Kami Player penceresine giden istekler
        self._player_win = None                          # pywebview penceresi (kapaninca None)
        self._make_player_window = None                  # main: pencere fabrikasi
        self._front_player = None                        # main: pencereyi one getir (Win32)
        self._warns: list[dict[str, Any]] = []
        self._probe_rules: dict[str, dict[str, Any]] = {}   # url -> eslesen kural (secim penceresi icin)
        manager.events.on("ui.warn", lambda **kw: self._on_warn(kw))

    # ---------- arka plan isleri ----------
    # Ag/uzun isler arayuzu bekletmesin: job_start hemen is kimligi doner, arayuz job_result ile sorar.
    JOB_METHODS = frozenset({
        "add_url", "media_probe", "cloud_list", "add_cloud", "rd_add", "torrent_choose", "torrent_open",
        "torrent_source", "rd_lists", "rd_status", "rd_set_token", "rd_queue_torrent", "rd_queue_download",
        "rd_delete", "check_update", "install_update", "hash_file", "make_report", "firewall_allow",
        "media_lyrics", "media_archive", "genius_set_token", "follow_add", "follow_check_now", "subtitle_translate", "subtitle_sync", "player_open_url",
        "library_get", "library_albums", "ocr_image", "ocr_translate", "player_lyrics",
        "batch_from_page", "batch_add", "phone_test", "ntfy_test", "ntfy_set_topic",
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
            ai_events, self._ai_events = self._ai_events, []
            warns, self._warns = self._warns, []
            plays, self._play_inbox = self._play_inbox, []
        rd = self._rd
        upd = None
        with self._inbox_lock:
            if self._update_info and not self._update_shown:   # yeni surum bilgisi arayuze bir kez
                upd, self._update_shown = self._update_info, True
        return {
            "play_requests": plays,
            "ai_events": ai_events,
            "warns": warns,
            "shutdown": self._shutdown.state() if self._shutdown else None,
            "ai_installing": dict(self._ai.installing) if self._ai else {},
            "update": upd,
            "rd_progress": rd.progress() if rd is not None and hasattr(rd, "progress") else [],
            "rd_events": rd_events,
            "torrent_requests": torrents,
            "media_requests": inbox,
            "clip_offers": offers,
            "items": [self._public(d) for d in items],
            "total_speed": self._manager.total_speed(),
            "engine_ok": self._engine.running,
            "bridge_port": self._bridge_port(),
        }

    @staticmethod
    def _public(d) -> dict[str, Any]:
        """Arayuz kaydi; biten medya dosyalarinda Altyazi/Vokal rozetleri diskteki gercek dosyalardan turetilir."""
        pub = d.to_public()
        if str(d.status) in ("complete", "Status.COMPLETE") or getattr(d.status, "value", "") == "complete":
            try:
                from app.core import aitools
                pub["extra"] = aitools.merge_disk_state(pub.get("extra") or {}, d.path)
            except Exception:
                pass
        return pub

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
                return self.media_probe(url, direct=direct)   # direct: RD sorusu tekrar gelmesin (dongu)
        except Exception:
            log.exception("yt-dlp tanima hatasi")
        try:
            added = self._manager.add(DownloadRequest(url=url, filename=filename, source="ui"))
        except PageLinkRejected:
            res = self.media_probe(url, direct=True)   # genel cikarici: sayfadaki gomulu video
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
        defaults = self._manager.default_media_options()
        rule = None
        if self._manager.settings.get("rules_enabled") and info.get("kind") == "video":
            from app.core import rules
            rule = rules.match(self._manager.settings.get("site_rules") or [], url, media=True, info=info)
        if rule:
            from app.core import rules
            defaults = {**defaults, **rules.media_options(rule)}
            with self._inbox_lock:
                self._probe_rules[info.get("url") or url] = rule
                self._probe_rules[url] = rule
            if rule.get("auto"):   # kural: pencereyi atla, dogrudan indir
                d = self._manager.add_media(info.get("url") or url, options=defaults, title=info.get("title") or "",
                                            source="ui", headers=headers,
                                            directory=rules.folder_path(rule, self._manager.base_dir()))
                return {"ok": True, "ids": [d.id], "rule": rule.get("name")}
        return {"ok": True, "media": info, "defaults": defaults, "rule": rule.get("name") if rule else ""}

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
                                            source="ui", page_url=page_url, headers=headers,
                                            directory=self._rule_dir_for(url, options or {}))
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
        from app.core.debrid import is_media_site
        if is_media_site(url):   # youtube vb.: RD destek listesinde olsa da asla sorulmaz
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

    def install_update(self) -> dict[str, Any]:
        """Yeni surum kurulumunu indir + sessiz calistir (Kami'yi kurulum kapatir, sonra yeniden acar).
        Ayarlar ve gecmis %LOCALAPPDATA%\\Kami\\data'da: kurulum onlara dokunmaz."""
        from app import paths
        from app.core import extras
        info = self._update_info or extras.check_update()
        if not info.get("available") or not info.get("asset"):
            return {"ok": False, "error": "no_update"}
        try:
            exe = extras.download_update(info, paths.USER_DIR / "updates")
        except Exception as exc:
            log.warning("Guncelleme indirilemedi: %s", exc)
            return {"ok": False, "error": "download_failed", "detail": str(exc)[:200]}
        log.info("Guncelleme kuruluyor: %s", exe)
        subprocess.Popen([str(exe), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], close_fds=True)
        # kurulum da Kami.exe --quit cagirir; yine de kendimiz kapanalim (dosyalar kilitli kalmasin)
        return {"ok": True, "path": str(exe)}

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
        """Ayarlar > Eklentiler: liste + plugin.json ayar semasi + mevcut degerler (gizliler sadece var/yok)."""
        store = self._registry.store
        out = []
        for p in self._registry.plugins:
            fields = []
            for sc in p.settings_schema:
                f = {k: sc.get(k) for k in ("key", "type", "label", "help", "choices", "min", "max", "default")}
                if sc.get("type") == "secret":
                    f["has_value"] = bool(store and store.secret(p.id, sc["key"]))
                else:
                    f["value"] = store.value(p.id, sc["key"], sc.get("default")) if store else sc.get("default")
                fields.append(f)
            out.append({"id": p.id, "name": p.name, "version": p.version, "description": p.description,
                        "author": p.meta.get("author", ""), "kinds": p.meta.get("kinds") or [],
                        "sites": [x.get("name", "") for x in p.url_patterns],
                        "enabled": p.enabled, "error": p.error, "settings": fields})
        return out

    def plugin_set_enabled(self, plugin_id: str, on: bool) -> dict[str, Any]:
        from app.core.plugin_loader import set_enabled
        info = set_enabled(self._registry, str(plugin_id), bool(on))
        return {"ok": info is not None and not info.error, "error": info.error if info else "not_found"}

    def plugin_reload(self, plugin_id: str) -> dict[str, Any]:
        from app.core.plugin_loader import reload_plugin
        info = reload_plugin(self._registry, str(plugin_id))
        return {"ok": info is not None and not info.error, "error": info.error if info else "not_found",
                "version": info.version if info else ""}

    def plugin_set(self, plugin_id: str, key: str, value: Any) -> dict[str, Any]:
        from app.core.plugin_loader import coerce_setting
        info = next((p for p in self._registry.plugins if p.id == str(plugin_id)), None)
        sc = next((x for x in (info.settings_schema if info else []) if x["key"] == key), None)
        store = self._registry.store
        if not info or not sc or store is None:
            return {"ok": False, "error": "not_found"}
        try:
            if sc.get("type") == "secret":
                store.set_secret(info.id, key, str(value or "").strip())
                return {"ok": True}
            v = coerce_setting(sc, value)
        except (ValueError, TypeError):
            return {"ok": False, "error": "bad_value"}
        store.set_value(info.id, key, v)
        return {"ok": True, "value": v}

    # ---------- Asama 6b: soz, muzik arsivi, Whisper, UVR ----------
    def _on_ai_event(self, msg: str) -> None:
        with self._inbox_lock:
            self._ai_events.append(str(msg))

    def media_lyrics(self, download_id: int) -> dict[str, Any]:
        if not self._media_post:
            return {"ok": False, "error": "unavailable"}
        return self._media_post.lyrics(int(download_id))

    def media_lyrics_paste(self, download_id: int, text: str) -> dict[str, Any]:
        if not self._media_post:
            return {"ok": False, "error": "unavailable"}
        return self._media_post.lyrics_paste(int(download_id), str(text or "")[:200_000])

    def media_archive(self, download_id: int) -> dict[str, Any]:
        if not self._media_post:
            return {"ok": False, "error": "unavailable"}
        return self._media_post.archive(int(download_id))

    def ai_status(self) -> dict[str, Any]:
        from app.core import aitools
        return {name: {"installed": aitools.installed(name), "size_gb": t["size_gb"],
                       "installing": (self._ai.installing.get(name) if self._ai else None)}
                for name, t in aitools.TOOLS.items()} | {
            "whisper_models": aitools.WHISPER_MODELS, "uvr_models": aitools.UVR_MODELS}

    def ai_install(self, name: str) -> dict[str, Any]:
        """Kullanici onayladiktan sonra cagrilir (arayuz boyutu sorar)."""
        from app.core import aitools
        if name not in aitools.TOOLS or not self._ai:
            return {"ok": False, "error": "bad_tool"}
        self._ai.install_async(name)
        return {"ok": True}

    def ai_run(self, kind: str, download_id: int, lang: str = "") -> dict[str, Any]:
        if not self._ai:
            return {"ok": False, "error": "unavailable"}
        opts = {"lang": lang} if kind in ("whisper", "lyrics") and lang else {}
        return self._ai.submit(str(kind), int(download_id), **opts)

    def ai_cancel(self, kind: str, download_id: int) -> None:
        if self._ai:
            self._ai.cancel(str(kind), int(download_id))

    def genius_status(self) -> dict[str, Any]:
        return {"has_token": bool(self._genius and self._genius.load())}

    def genius_set_token(self, token: str) -> dict[str, Any]:
        """Genius 'Client Access Token' (api.genius.com/clients). Bir arama ile dogrulanir, DPAPI ile saklanir."""
        import re
        import requests
        token = str(token or "").strip()
        if not self._genius or not re.fullmatch(r"[A-Za-z0-9_\-]{20,128}", token):
            return {"ok": False, "error": "bad_token"}
        try:
            r = requests.get("https://api.genius.com/search", params={"q": "test"},
                             headers={"Authorization": f"Bearer {token}"}, timeout=15)
        except requests.RequestException:
            return {"ok": False, "error": "network"}
        if r.status_code != 200:
            return {"ok": False, "error": "bad_token"}
        self._genius.save(token)
        return {"ok": True}

    def genius_clear(self) -> dict[str, Any]:
        if self._genius:
            self._genius.clear()
        return {"ok": True}

    def open_link(self, url: str) -> bool:
        """Soz linkleri (Genius / AZLyrics) varsayilan tarayicida."""
        url = str(url or "")
        if not url.startswith(("https://genius.com/", "https://search.azlyrics.com/", "https://www.azlyrics.com/")):
            return False
        os.startfile(url)  # type: ignore[attr-defined]
        return True

    def open_path(self, path: str) -> bool:
        """Uretilen yan dosyalar (srt, lrc, ayrilmis parcalar): sadece indirme kayitlarinda gecen yollar."""
        path = str(path or "")
        known = set()
        for d in self._manager.snapshot():
            x = d.extra or {}
            known.update([x.get("ai_whisper_srt"), x.get("lyrics_lrc"), *(x.get("ai_uvr_files") or [])])
        if path in known and os.path.exists(path):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            return True
        return False

    # ---------- kanal / liste takibi ----------
    def follow_list(self) -> list[dict[str, Any]]:
        return self._follow.list() if self._follow else []

    def follow_add(self, url: str, fmt: str = "mp4", quality: str = "best", backfill: int = 0) -> dict[str, Any]:
        if not self._follow:
            return {"ok": False, "error": "unavailable"}
        return self._follow.add_follow(str(url or ""), str(fmt), str(quality), int(backfill or 0))

    def follow_update(self, fid: str, changes: dict) -> dict[str, Any]:
        if not self._follow:
            return {"ok": False, "error": "unavailable"}
        allowed = {k: v for k, v in dict(changes or {}).items() if k in ("enabled", "format", "quality")}
        return self._follow.update(str(fid), **allowed)

    def follow_remove(self, fid: str) -> dict[str, Any]:
        if self._follow:
            self._follow.remove(str(fid))
        return {"ok": True}

    def follow_check_now(self, fid: str = "") -> dict[str, Any]:
        if not self._follow:
            return {"ok": False, "error": "unavailable"}
        return {"ok": True, "new": self._follow.check(str(fid) or None, force=True)}

    # ---------- Asama 6c ----------
    def _rule_dir_for(self, url: str, options: dict) -> str:
        """Secim penceresinden gelen medya: probe'da eslesen kural, bicim degismediyse klasorunu uygular."""
        with self._inbox_lock:
            rule = self._probe_rules.get(url)
        if not rule or (rule.get("format") and options.get("format") and options["format"] != rule["format"]):
            return ""
        from app.core import rules
        return rules.folder_path(rule, self._manager.base_dir())

    def _on_warn(self, kw: dict[str, Any]) -> None:
        with self._inbox_lock:
            self._warns.append(kw)

    # site kurallari
    def rules_get(self) -> list[dict[str, Any]]:
        return self._manager.settings.get("site_rules") or []

    def rules_set(self, rules_list: list) -> dict[str, Any]:
        try:
            self._manager.settings.set("site_rules", list(rules_list or []))
        except (ValueError, TypeError) as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "rules": self._manager.settings.get("site_rules")}

    # gecmis
    def history_search(self, q: str = "") -> list[dict[str, Any]]:
        return self._history.search(str(q or "")) if self._history else []

    def history_clear(self) -> dict[str, Any]:
        if self._history:
            self._history.clear()
        return {"ok": True}

    def history_open(self, path: str) -> bool:
        path = str(path or "")
        if not self._history or not any(h["path"] == path for h in self._history.search("", 5000)):
            return False
        if os.path.exists(path):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            return True
        return False

    # kapatma
    def shutdown_arm(self, on: bool) -> dict[str, Any]:
        self._manager.settings.set("shutdown_when_done", bool(on))
        if not on and self._shutdown:
            self._shutdown.cancel()
        return {"ok": True, **(self._shutdown.state() if self._shutdown else {})}

    def shutdown_cancel(self) -> dict[str, Any]:
        if self._shutdown:
            self._shutdown.cancel()
        return {"ok": True}

    # ---------- oynatici (P1) ----------
    def player_open(self, download_id: int) -> dict[str, Any]:
        """Biten indirmeyi Kami'nin kendi oynaticisinda ac: yerel medya sunucusu adresi + mod (direct/remux/transcode)."""
        if not self._media:
            return {"ok": False, "error": "player_unavailable"}
        d = self._manager.store.get(int(download_id))
        if not d or not d.path or not os.path.isfile(d.path):
            return {"ok": False, "error": "not_found"}
        x = dict(d.extra or {})
        try:
            from app.core import aitools
            x = aitools.merge_disk_state(x, d.path)
        except Exception:
            pass
        return self._media.register(d.path, d.filename or "", [x.get("ai_whisper_srt") or ""])

    def player_open_path(self, path: str) -> dict[str, Any]:
        """Surukle-birak / gecmis: kullanicinin verdigi yerel medya dosyasi."""
        if not self._media:
            return {"ok": False, "error": "player_unavailable"}
        return self._media.register(str(path or ""))

    def player_siblings(self, path: str) -> list[str]:
        """Ayni klasordeki ayni turden medya: otomatik 'siradakiler' listesi."""
        from app.core.library import siblings
        return siblings(str(path or ""))

    def _library_dirs(self) -> list[str]:
        dirs = [str(self._manager.base_dir())] + [str(d) for d in (self._manager.settings.get("library_dirs") or [])]
        return list(dict.fromkeys(d for d in dirs if d))

    def library_get(self) -> dict[str, Any]:
        from app.core.library import scan
        res = scan(self._library_dirs())
        res["dirs"] = self._library_dirs()
        res["base"] = str(self._manager.base_dir())
        return res

    def library_albums(self) -> dict[str, Any]:
        """Kutuphanedeki muzik: album kartlari (kapak, sanatci, parcalar)."""
        from app import paths
        from app.core.library import albums, scan
        res = scan(self._library_dirs())
        al = albums(res.get("items", []), paths.DATA_DIR / "albums_cache.json")
        for g in al:
            g["cover"] = (self._media.asset_url(g["cover_path"], "c") if g["cover_path"] else
                          self._media.asset_url(g["cover_img"], "f") if g["cover_img"] else "") if self._media else ""
            g.pop("cover_path", None); g.pop("cover_img", None)
        return {"ok": True, "albums": al}

    def library_add_dir(self) -> dict[str, Any]:
        d = ""
        if self._player_win is not None:   # kutuphane oynatici penceresinden: iletisim kutusu orada acilsin
            import webview
            dialog = getattr(getattr(webview, "FileDialog", None), "FOLDER", None) or webview.FOLDER_DIALOG
            res = self._player_win.create_file_dialog(dialog, directory=str(self._manager.base_dir()))
            d = res[0] if res else ""
        else:
            d = self.choose_folder()
        if d:
            cur = list(self._manager.settings.get("library_dirs") or [])
            if d not in cur:
                self._manager.settings.set("library_dirs", cur + [d])
        return {"ok": bool(d), "dirs": self._library_dirs()}

    def library_remove_dir(self, path: str) -> dict[str, Any]:
        cur = [d for d in (self._manager.settings.get("library_dirs") or []) if d != path]
        self._manager.settings.set("library_dirs", cur)
        return {"ok": True, "dirs": self._library_dirs()}

    def _pl(self):
        if not getattr(self, "_playlists", None):
            from app import paths
            from app.core.library import Playlists
            self._playlists = Playlists(paths.DATA_DIR / "playlists.json")
        return self._playlists

    def playlist_get(self) -> dict[str, list[str]]:
        return self._pl().all()

    def playlist_save(self, name: str, items: list) -> dict[str, list[str]]:
        return self._pl().save(str(name), [str(x) for x in (items or [])])

    def playlist_delete(self, name: str) -> dict[str, list[str]]:
        return self._pl().delete(str(name))

    def subtitle_translate(self, video_path: str, text: str, src: str = "en", engine: str = "nllb") -> dict[str, Any]:
        """Altyaziyi Turkceye cevir (NLLB yerel / googletrans), videonun yanina <ad>.tr.srt yazar; oynatici VTT'yi alir."""
        from pathlib import Path
        from app.core import aitools
        from app.core.media_server import srt_to_vtt
        p = Path(str(video_path or ""))
        if not p.is_file() or not str(text or "").strip():
            return {"ok": False, "error": "bad_input"}
        out = p.with_name(p.stem + ".tr.srt")
        if out.exists():
            out = p.with_name(p.stem + ".tr.kami.srt")   # var olan insan yapimi altyaziya dokunma
        res = aitools.translate_subtitle(str(text), str(out), str(src or "en"), "tr", "google" if engine == "google" else "nllb")
        if "error" in res:
            return {"ok": False, "error": str(res["error"])[:200]}
        return {"ok": True, "path": res["done"], "engine": res.get("engine"),
                "vtt": srt_to_vtt(Path(res["done"]).read_text(encoding="utf-8"))}

    def player_open_url(self, url: str) -> dict[str, Any]:
        """Indirmeden izle: hoster linki + RD token -> Real-Debrid linki; medya sitesi -> yt-dlp akisi; yoksa dogrudan URL."""
        if not self._media:
            return {"ok": False, "error": "player_unavailable"}
        url = str(url or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            return {"ok": False, "error": "bad_url"}
        from app.core.debrid import is_media_site
        rd = self._rd
        if rd is not None and rd.has_token() and not is_media_site(url):
            try:
                if rd.supports(url, wait=False):
                    files = rd.unrestrict_files(url)
                    vids = [f for f in files if f["filename"].lower().endswith((".mkv", ".mp4", ".avi", ".webm", ".mov", ".m4v", ".ts", ".mp3", ".flac", ".m4a"))]
                    if vids:
                        f = max(vids, key=lambda x: x["size"])
                        return {**self._media.register_url([f["url"]], f["filename"] or url), "source": "rd"}
            except Exception as exc:   # RD olmazsa yt-dlp / dogrudan dene
                log.info("RD ile izlenemedi: %s", exc)
        try:
            from app.engines.ytdlp_engine import _ytdlp, _cookiefile
            yt_dlp = _ytdlp()
            opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True,
                    "format": "bv*[height<=1080][vcodec^=avc1]+ba[acodec^=mp4a]/bv*[height<=1080]+ba/b[height<=1080]/b"}
            with _cookiefile(url) as ck, yt_dlp.YoutubeDL({**opts, "cookiefile": ck} if ck else opts) as ydl:
                info = ydl.extract_info(url, download=False)
            fmts = info.get("requested_formats") or [info]
            urls = [f["url"] for f in fmts if f.get("url")]
            headers = (fmts[0].get("http_headers") or info.get("http_headers") or {})
            if urls:
                return {**self._media.register_url(urls[:2], info.get("title") or url, headers, info.get("duration") or 0),
                        "source": "ytdlp", "webpage": url}
        except Exception as exc:
            log.info("yt-dlp ile izlenemedi: %s", str(exc)[:200])
        return {**self._media.register_url([url], url.rsplit("/", 1)[-1][:120] or url), "source": "direct"}

    def subtitle_sync(self, video_path: str, text: str, lang: str = "") -> dict[str, Any]:
        """Altyaziyi sese hizala; videonun yanina <ad>[.dil].sync.srt yazar, oynatici VTT'yi alir."""
        from pathlib import Path
        from app.core import aitools
        from app.core.media_server import srt_to_vtt
        p = Path(str(video_path or ""))
        if not p.is_file() or not str(text or "").strip():
            return {"ok": False, "error": "bad_input"}
        out = p.with_name(p.stem + (f".{lang}" if lang else "") + ".sync.srt")
        res = aitools.sync_subtitle(str(p), str(text), str(out))
        if "error" in res:
            return {"ok": False, "error": str(res["error"])[:200]}
        return {"ok": True, "path": res["done"], "vtt": srt_to_vtt(Path(res["done"]).read_text(encoding="utf-8"))}

    # ---------- sozluk (altyazida kelimeye tikla; yerel Vikisozluk SQLite) ----------
    def _dict(self):
        if not getattr(self, "_dictionary", None):
            from app import paths
            from app.core.dictionary import Dictionary
            self._dictionary = Dictionary(paths.DATA_DIR / "dict" / "wiktionary.db")
        return self._dictionary

    def dict_status(self) -> dict[str, Any]:
        return self._dict().status()

    def dict_install(self, pack: str = "tr") -> dict[str, Any]:
        return {"ok": self._dict().install(str(pack or ""))}

    def dict_lookup(self, word: str, lang: str = "", line: str = "", pos: int = -1) -> dict[str, Any]:
        """word: tiklanan kelime; bosluksuz dillerde (ja/zh) line + pos ile en uzun eslesme bulunur."""
        d = self._dict()
        lang = str(lang or "")[:5]
        w = str(word or "")[:80]
        if line and pos >= 0 and lang in ("ja", "zh"):
            w = d.longest_match(str(line)[:300], int(pos), lang)
        try:
            return {"ok": True, "word": w, "entries": d.lookup(w, lang), "installed": d.installed()}
        except Exception as exc:   # veritabani kilitli (kurulum suruyor) vb.
            return {"ok": False, "word": w, "error": str(exc)[:160], "installed": d.installed()}

    # ---------- muzik modu sozleri (B7): yan .lrc/.txt -> gomulu etiket -> LRCLIB ----------
    def player_lyrics(self, path: str, artist: str = "", title: str = "", album: str = "", duration: float = 0,
                      online: bool = True) -> dict[str, Any]:
        from pathlib import Path
        from app.core import lyrics as ly
        links = ly.search_links(str(artist or ""), str(title or "")) if title else {}
        p = Path(str(path or ""))
        if p.is_file():
            for ext, src in ((".lrc", "lrc"), (".txt", "txt")):
                q = p.with_suffix(ext)
                if q.is_file():
                    try:
                        t = q.read_text(encoding="utf-8-sig", errors="replace")
                    except OSError:
                        continue
                    if t.strip():
                        lrc = ly.is_lrc(t)
                        return {"ok": True, "synced": t if lrc else "", "plain": "" if lrc else t, "source": src, "links": links}
            if self._media is not None:
                from app.core.media_server import find_ffprobe, probe
                tg = probe(find_ffprobe(self._media.ffmpeg()), str(p)).get("tags", {})
                t = tg.get("syncedlyrics") or tg.get("lyrics") or tg.get("unsyncedlyrics") or ""
                if t.strip():
                    lrc = ly.is_lrc(t)
                    return {"ok": True, "synced": t if lrc else "", "plain": "" if lrc else t, "source": "tag", "links": links}
        if online and title:
            hit = None
            dur = float(duration or 0)
            tries = [(artist, title, album, dur), ("", f"{artist} {title}".strip(), "", dur), (artist, title, "", 0)]
            for a_, t_, al_, d_ in tries:   # tam eslesme -> serbest arama -> sure filtresiz (klip surumleri uzun olur)
                try:
                    hit = ly.lrclib_find(str(a_ or ""), str(t_), str(al_ or ""), float(d_ or 0))
                except Exception:
                    hit = None
                if hit:
                    break
            if hit:
                return {"ok": True, "synced": hit.get("synced", ""), "plain": hit.get("plain", ""),
                        "instrumental": bool(hit.get("instrumental")), "source": "lrclib", "links": links}
        return {"ok": True, "synced": "", "plain": "", "source": "", "links": links}

    def player_lyrics_save(self, path: str, text: str) -> dict[str, Any]:
        """Yapistirilan sozu sarkinin yanina yazar (.lrc zamanliysa, degilse .txt); var olan dosyanin ustune yazar."""
        from pathlib import Path
        from app.core import lyrics as ly
        p = Path(str(path or ""))
        text = str(text or "").strip()
        if not p.is_file() or not text or len(text) > 200_000:
            return {"ok": False, "error": "bad_input"}
        lrc = ly.is_lrc(text)
        q = p.with_suffix(".lrc" if lrc else ".txt")
        try:
            q.write_text(text + "\n", encoding="utf-8")
            other = p.with_suffix(".txt" if lrc else ".lrc")
            if other.is_file() and not lrc:
                pass   # zamanli .lrc onceliklidir; duz metin yalnizca .lrc yoksa okunur
        except OSError as exc:
            return {"ok": False, "error": str(exc)[:160]}
        return {"ok": True, "source": "lrc" if lrc else "txt", "path": str(q)}

    # ---------- ekran ustu OCR (B6) ----------
    def ocr_image(self, png_b64: str, lang: str = "") -> dict[str, Any]:
        from app.core import ocr
        return ocr.recognize(png_b64, lang)

    def ocr_translate(self, text: str, src: str = "", engine: str = "google") -> dict[str, Any]:
        """OCR metnini Turkceye cevir (googletrans / NLLB); basarisizsa arayuz metni cevirisiz gosterir."""
        import os as _os
        import tempfile
        from app.core import aitools
        text = str(text or "").strip()[:2000]
        if not text:
            return {"ok": False, "error": "bad_input"}
        vtt = "WEBVTT\n\n00:00:00.000 --> 00:00:05.000\n" + text.replace("\n\n", "\n") + "\n"
        fd, out = tempfile.mkstemp(prefix="kami_ocr_tr_", suffix=".srt")
        _os.close(fd)
        try:
            res = aitools.translate_subtitle(vtt, out, str(src or "en")[:5], "tr", "nllb" if engine == "nllb" else "google")
            if "error" in res:
                return {"ok": False, "error": str(res["error"])[:200]}
            with open(res["done"], encoding="utf-8") as f:
                lines = [ln for ln in f.read().splitlines() if ln.strip() and "-->" not in ln and not ln.strip().isdigit()]
            return {"ok": True, "text": "\n".join(lines)}
        finally:
            try:
                _os.remove(out)
            except OSError:
                pass

    # ---------- Kami Player penceresi (ayri pywebview penceresi; main baglar) ----------
    def player_show(self, req: dict | None = None) -> dict[str, Any]:
        """Sunak / Gezgin / surukle-birak -> Kami Player penceresi: {id} | {path} | {url} | {library: True}."""
        req = req or {}
        item: dict[str, Any] = {}
        if req.get("id") is not None:
            d = self._manager.store.get(int(req["id"]))
            if not d or not d.path or not os.path.isfile(d.path):
                return {"ok": False, "error": "not_found"}
            item["path"] = d.path
        elif req.get("path"):
            item["path"] = str(req["path"])
        elif req.get("url"):
            item["url"] = str(req["url"])
        if req.get("queue"):
            item["queue"] = [str(x) for x in req["queue"]]
        if req.get("library"):
            item["library"] = True
        with self._inbox_lock:
            self._player_q.append(item)
        self._ensure_player()
        return {"ok": True}

    def player_poll(self) -> list[dict[str, Any]]:
        with self._inbox_lock:
            q, self._player_q = self._player_q, []
        return q

    def player_fullscreen(self, on: bool = True) -> None:
        w = self._player_win
        if w is not None:   # pywebview cagrisi arayuz is parcacigini bekleyebilir: JS'i bekletme
            threading.Thread(target=w.toggle_fullscreen, name="kami-player-fs", daemon=True).start()

    def player_mini(self, on: bool = True, kind: str = "audio", aspect: float = 0) -> dict[str, Any]:
        """Mini oynatici (YouTube PiP gibi): cercevesiz, hep ustte, ekranin sag alti. Video: 16:9 kart, muzik: ince kart."""
        from app.core.winwin import MiniWindow
        if not getattr(self, "_mini", None):
            self._mini = MiniWindow("Kami Player")
        try:
            if on:
                if kind == "video":
                    ar = float(aspect or 0) if 0.4 < float(aspect or 0) < 3.5 else 16 / 9
                    w = 480 if ar >= 1 else 300
                    ok = self._mini.enter(w, int(w / ar))
                else:
                    ok = self._mini.enter(440, 132)
            else:
                ok = self._mini.leave()
            return {"ok": bool(ok)}
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception("mini oynatici")
            return {"ok": False, "error": str(exc)[:160]}

    def player_mini_move(self, dx: int = 0, dy: int = 0) -> None:
        if getattr(self, "_mini", None):
            self._mini.move(int(dx), int(dy))

    def _ensure_player(self) -> None:
        if self._player_win is None and self._make_player_window:
            self._player_win = self._make_player_window()
        elif self._player_win is not None and self._front_player:
            self._front_player()

    def _play_request(self, path: str) -> None:
        self.player_show({"path": str(path)})

    def player_default_apps(self) -> bool:
        """Windows Ayarlar > Varsayilan uygulamalar > Kami (varsayilan programla degistirilemez, kullanici secer)."""
        try:
            os.startfile("ms-settings:defaultapps?registeredAppUser=Kami")  # type: ignore[attr-defined]
            return True
        except OSError:
            return False

    # inerken izle
    def watch(self, download_id: int) -> dict[str, Any]:
        if not self._watcher:
            return {"ok": False, "error": "watch_unsupported"}
        return self._watcher.start(int(download_id))

    def watch_cancel(self, download_id: int) -> None:
        if self._watcher:
            self._watcher.cancel(int(download_id))

    # telefondan gonder
    def phone_info(self) -> dict[str, Any]:
        import socket
        from app.core.phone import lan_ips
        s = self._manager.settings
        key = self._phone_key.load() if self._phone_key else ""
        ips = lan_ips()
        return {"enabled": bool(s.get("phone_enabled")), "running": bool(self._phone and self._phone.running),
                "ip": ips[0], "ips": ips, "host": socket.gethostname().lower() + ".local",
                "port": s.get("phone_port"), "key": key,
                "last": (self._phone.last if self._phone else {}) or {}}

    def phone_test(self, url: str) -> dict[str, Any]:
        """Ayarlar'daki "test": bu bilgisayardan o adrese /test istegi (telefon tarafini kanitlamaz, sunucuyu kanitlar)."""
        import requests
        url = str(url or "")
        if not re.fullmatch(r"http://[\w.\-]+:\d+/test", url):
            return {"ok": False}
        try:
            r = requests.get(url, headers={"Accept": "application/json"}, timeout=4)
            return {"ok": r.status_code == 200, "message": r.json().get("message", "")}
        except Exception as exc:
            return {"ok": False, "message": type(exc).__name__}

    def phone_status_items(self) -> list[dict[str, Any]]:
        """Telefon sayfasindaki "indirme durumu": aktif/bekleyen/duraklatilmis + son bitenler."""
        order = {Status.ACTIVE: 0, Status.WAITING: 1, Status.PAUSED: 2, Status.ERROR: 3, Status.COMPLETE: 4}
        items = sorted(self._manager.snapshot(), key=lambda d: (order.get(d.status, 5), -(d.id or 0)))
        out = []
        for d in items[:15]:
            pct = int(d.downloaded * 100 / d.size) if d.size else (100 if d.status == Status.COMPLETE else 0)
            st = {Status.ACTIVE: "iniyor", Status.WAITING: "sırada", Status.PAUSED: "duraklatıldı",
                  Status.ERROR: "hata", Status.COMPLETE: "bitti"}.get(d.status, str(d.status))
            speed = f" · {d.speed / 1048576:.1f} MB/sn" if d.status == Status.ACTIVE and d.speed else ""
            out.append({"id": d.id, "name": d.filename or d.url, "percent": max(0, min(100, pct)),
                        "label": f"{st} · %{pct}{speed}",
                        "can_pause": d.status in (Status.ACTIVE, Status.WAITING),
                        "can_resume": d.status in (Status.PAUSED, Status.ERROR)})
        return out

    def phone_control(self, download_id: int, action: str) -> bool:
        if action == "pause":
            self._manager.pause(int(download_id))
            return True
        if action == "resume":
            self._manager.resume(int(download_id))
            return True
        return False

    def phone_new_key(self) -> dict[str, Any]:
        from app.core.phone import new_key
        if not self._phone_key:
            return {"ok": False}
        self._phone_key.save(new_key())
        return {"ok": True, **self.phone_info()}

    def add_text(self, text: str, source: str = "phone") -> int:
        """Telefondan / toplu listeden gelen metin: icindeki linkleri pencere acmadan kuyruga ekler."""
        return self.add_text_detail(text, source)["added"]

    def add_text_detail(self, text: str, source: str = "phone", fmt: str = "") -> dict[str, Any]:
        """fmt (telefon): mp4 | mp3 | ask. Telefonda medya linki + format yok/ask -> Kami'de secim penceresi."""
        from app.core.automate import extract_links
        from app.engines import ytdlp_engine as yt
        names, asked = [], False
        for link in extract_links(str(text or ""))[:200]:
            if source == "phone" and fmt in ("", "ask") and yt.is_supported(link) \
                    and not self._manager.cloud.provider_for(link):
                self._on_media_choose(link)
                self._manager.events.emit("ui.attention", reason="media_choose")
                names.append(link)
                asked = True
                continue
            if self._add_quiet(link, source, fmt if fmt in ("mp4", "mp3") else ""):
                names.append(link)
        return {"added": len(names), "names": names, "asked": asked}

    def _add_quiet(self, link: str, source: str, fmt: str = "") -> bool:
        from app.core.debrid import is_magnet, is_torrent_url
        from app.engines import ytdlp_engine as yt
        try:
            if is_magnet(link) or is_torrent_url(link):
                route = self._torrent_route()
                if route == "rd":
                    return bool(self.rd_add(link).get("ok"))
                with self._inbox_lock:   # yerel/sor: Kami'de secim (dosya listesi) gerekir
                    self._torrent_inbox.append({"src": link, "route": route})
                return True
            if self._rd_route(link) == "auto":
                return bool(self.rd_add(link).get("ok"))
            if self._manager.cloud.provider_for(link):
                token, listing = self._manager.cloud.list(link)
                return bool(self._manager.add_cloud(token, list(range(len(listing.files)))))
            if yt.is_supported(link):
                # Sessiz eklemede "son secim" (medya penceresi MP3'te kalmis olabilir) KULLANILMAZ: varsayilan MP4;
                # MP3 sadece acikca istenirse (telefon format=mp3) ya da muzik kurali gercekten eslesirse.
                opts, directory = {"format": fmt or "mp4"}, ""
                if fmt == "mp3":
                    opts["audio_kbps"] = self._manager.settings.get("media_audio_kbps") or 320
                if not fmt and self._manager.settings.get("rules_enabled"):
                    from app.core import rules
                    rule = rules.match(self._manager.settings.get("site_rules") or [], link, media=True,
                                       info={"categories": []})
                    if rule:
                        opts = {"format": "mp4", **rules.media_options(rule)}
                        directory = rules.folder_path(rule, self._manager.base_dir())
                self._manager.add_media(link, options=opts, source=source, directory=directory)
                return True
            from app.core.models import DownloadRequest
            return bool(self._manager.add(DownloadRequest(url=link, source=source)))
        except Exception as exc:
            log.warning("Link eklenemedi (%s): %s", source, type(exc).__name__)
            return False

    # toplu link listesi
    def batch_parse(self, text: str) -> dict[str, Any]:
        from app.core.automate import expand_numbered, extract_links
        links: list[str] = []
        for line in str(text or "").splitlines():
            for x in expand_numbered(line.strip()) if "[" in line else [line]:
                links += extract_links(x)
        return {"ok": True, "links": list(dict.fromkeys(links))[:5000]}

    def batch_from_page(self, url: str) -> dict[str, Any]:
        """yt-dlp'nin tanidigi sayfa (YouTube kanal/liste/arama vb.) -> duz video listesi; digerleri <a> linkleri."""
        from app.core.automate import fetch_page_links
        from app.engines import ytdlp_engine as yt
        url = str(url or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            return {"ok": False, "error": "bad_url"}
        try:
            if yt.is_supported(url) and not re.search(r"[?&]v=|youtu\.be/|/shorts/[\w-]+$", url):
                from app.core.follow import list_entries, normalize_url
                title, entries = list_entries(normalize_url(url), limit=500)
                if entries:
                    return {"ok": True, "links": [e["url"] for e in entries], "source": "ytdlp", "title": title,
                            "titles": {e["url"]: e["title"] for e in entries}, "hidden": 0}
        except Exception:
            log.info("yt-dlp liste cikarimi olmadi, sayfa linkleri deneniyor", exc_info=True)
        try:
            r = fetch_page_links(url)
            return {"ok": True, "links": r["links"][:5000], "hidden": r["hidden"], "source": "page"}
        except Exception as exc:
            return {"ok": False, "error": "page_fetch", "detail": type(exc).__name__}

    def batch_add(self, links: list) -> dict[str, Any]:
        n = sum(1 for link in list(links or [])[:5000] if self._add_quiet(str(link), "batch"))
        return {"ok": n > 0, "added": n, "total": len(links or [])}

    # ntfy
    def ntfy_status(self) -> dict[str, Any]:
        return {"has_topic": bool(self._ntfy and self._ntfy.load())}

    def ntfy_set_topic(self, topic: str) -> dict[str, Any]:
        import re
        topic = str(topic or "").strip()
        if not self._ntfy or not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", topic):
            return {"ok": False, "error": "ntfy_topic"}
        self._ntfy.save(topic)
        return {"ok": True}

    def ntfy_test(self) -> dict[str, Any]:
        from app.core.automate import ntfy_send
        s = self._manager.settings
        ok = ntfy_send(s.get("ntfy_server"), self._ntfy.load() if self._ntfy else "", "Kami", "Test bildirimi ✓",
                       "bell")
        return {"ok": ok}
