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
from app.ui.api_studio import STUDIO_JOBS, StudioMixin

if TYPE_CHECKING:
    from app.core.manager import DownloadManager
    from app.core.plugin_api import PluginRegistry
    from app.engines.aria2_engine import Aria2Engine

log = logging.getLogger(__name__)


@log_slow_calls
class Api(StudioMixin):
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
        self._turn_store = None                          # Kami Oda: Cloudflare TURN anahtari (DPAPI)
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
        self._osub = None                                # OpenSubtitles API anahtari (DPAPI, main baglar)
        self._last_song: dict[str, Any] = {}
        self._conv_inbox: list[str] = []                 # Gezgin sag tik / surukle-birak ile gelen dosyalar
        self._conv_jobs: list[dict[str, Any]] = []       # donusturme isleri (arayuz yoklar)
        self._conv_cancel = threading.Event()
        self._conv_lock = threading.Lock()
        self._conv_view = False                          # Donusturucu acik: birakilan dosyalar ona gider
        self._lv: dict[str, Any] = {"state": "idle"}     # lyric video isi (tek seferde bir)
        self._lv_cancel = threading.Event()
        self._card_win = None                            # masaustu mini karti (main kurar)
        self._card_hidden = False                        # kullanici bu oturumda kapatti
        self._show_main = None                           # main: ana pencereyi geri getir
        self._ui_iso = None                              # Faz 7.1: COOP/COEP izole sunucu
        self._profiles = None                            # Faz 7.4: Coklu profil deposu
        self._island_win = None                          # Faz 7.5: Masaustu mini-ada seridi
        self._island_shown = False
        self._island_factory = None
        self._warns: list[dict[str, Any]] = []
        self._probe_rules: dict[str, dict[str, Any]] = {}   # url -> eslesen kural (secim penceresi icin)
        manager.events.on("ui.warn", lambda **kw: self._on_warn(kw))

    # ---------- arka plan isleri ----------
    # Ag/uzun isler arayuzu bekletmesin: job_start hemen is kimligi doner, arayuz job_result ile sorar.
    JOB_METHODS = frozenset({
        "add_url", "pic_ai", "pic_freq_sep", "pic_seam_carve", "pic_clone_lut", "pic_hdr_merge",
        "pic_focus_stack", "pic_ecom_pack", "pic_mockup", "pic_watermark_embed",
        "editor_vectorize", "editor_gif", "room_open", "room_relink", "editor_export", "editor_project_save", "room_turn_set", "reader_open", "reader_page", "reader_thumb", "reader_search", "reader_speak", "reader_text", "rec_save_replay", "rec_toggle", "rec_replay", "media_probe", "cloud_list", "add_cloud", "rd_add", "torrent_choose", "torrent_open",
        "torrent_source", "rd_lists", "rd_status", "rd_set_token", "rd_queue_torrent", "rd_queue_download",
        "rd_delete", "check_update", "install_update", "hash_file", "make_report", "firewall_allow",
        "media_lyrics", "media_archive", "genius_set_token", "follow_add", "follow_check_now", "subtitle_translate", "subtitle_sync", "player_open_url",
        "library_get", "library_albums", "lyrics_search", "song_identify", "subtitle_fetch", "subtitle_search", "image_data", "library_organize", "player_skips", "library_posters", "media_extract_audio", "media_clip", "media_repair", "ocr_image", "ocr_translate", "player_lyrics",
        "batch_from_page", "batch_add", "phone_test", "ntfy_test", "ntfy_set_topic",
    }) | STUDIO_JOBS

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

    def set_favorite(self, download_id: int, on: bool = True) -> bool:
        d = self._manager.store.get(int(download_id))
        if not d:
            return False
        extra = {**(d.extra or {}), "fav": bool(on)}
        if not on:
            extra.pop("fav", None)
        nd = self._manager.store.update(d.id, extra=extra)
        self._manager.events.emit("download.updated", download=nd)
        return True

    def rename_download(self, download_id: int, new_name: str) -> dict[str, Any]:
        """F2: bitmis dosyanin adini diskte ve listede degistirir (uzanti korunur, ayni klasorde)."""
        d = self._manager.store.get(int(download_id))
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(new_name or "")).strip().rstrip(". ")
        if not d or not name:
            return {"ok": False, "error": "bad_input"}
        old = d.path or ""
        if not old or not os.path.isfile(old):
            return {"ok": False, "error": "no_file"}
        ext = os.path.splitext(old)[1]
        if not name.lower().endswith(ext.lower()):
            name += ext
        new = os.path.join(os.path.dirname(old), name)
        if os.path.normcase(new) == os.path.normcase(old):
            return {"ok": True, "path": old}
        if os.path.exists(new):
            return {"ok": False, "error": "exists"}
        try:
            os.rename(old, new)
        except OSError as exc:
            return {"ok": False, "error": str(exc)[:120]}
        nd = self._manager.store.update(d.id, filename=name)
        self._manager.events.emit("download.updated", download=nd)
        return {"ok": True, "path": new}

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

    def system_fonts(self) -> list[str]:
        """Altyazi font secici: Windows'ta kurulu font aileleri (makine + kullanici)."""
        import re as _re
        names: set[str] = set()
        try:
            import winreg
            for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts") as k:
                        for i in range(winreg.QueryInfoKey(k)[1]):
                            n = winreg.EnumValue(k, i)[0]
                            n = _re.sub(r"\s*\((TrueType|OpenType|All res)\)\s*$", "", n)
                            for part in n.split("&"):
                                fam = _re.sub(r"\s+(Bold|Italic|Light|Semibold|SemiBold|Black|Regular|Medium|Thin|ExtraLight|Condensed|Oblique)\b.*$", "", part.strip())
                                if fam and not fam.startswith("@"):
                                    names.add(fam)
                except OSError:
                    continue
        except ImportError:
            pass
        return sorted(names, key=str.lower)[:600]

    def open_web(self, url: str) -> bool:
        """Kami Lens sonuclari: http(s) adresini varsayilan tarayicida acar."""
        url = str(url or "")
        if not url.startswith(("https://", "http://")):
            return False
        os.startfile(url)  # type: ignore[attr-defined]
        return True

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

    # ---------- B8/B9: atlama araliklari, posterler, ses cikar, klip, onarim, cop kutusu ----------
    def _mt_cache(self):
        if not getattr(self, "_mtc", None):
            from app import paths
            from app.core.mediatools import _Cache
            self._mtc = _Cache(paths.DATA_DIR / "online_cache.json")
        return self._mtc

    def player_skips(self, path: str, duration: float = 0, tags: dict | None = None) -> dict[str, Any]:
        """Intro/outro (AniSkip, anime) + SponsorBlock (YouTube'dan inenler)."""
        from pathlib import Path
        from app.core import mediatools as mt
        from app.core.library import parse_name
        p = Path(str(path or ""))
        out: list[dict[str, Any]] = []
        info = parse_name(p.stem) if p.name else {}
        if info.get("series") and info.get("episode"):
            out += mt.aniskip(info["series"], int(info["episode"]), float(duration or 0), self._mt_cache())
        vid = mt.youtube_id(str(p), tags or {})
        if vid:
            out += mt.sponsorblock(vid, self._mt_cache())
        return {"ok": True, "segments": out, "series": info.get("series", ""), "episode": info.get("episode", 0)}

    def library_posters(self, names: list | None = None) -> dict[str, Any]:
        from app.core import mediatools as mt
        res = {}
        for n in (names or [])[:60]:
            al = mt.anilist(str(n), self._mt_cache())
            if al and al.get("cover"):
                res[str(n)] = {"cover": al["cover"], "color": al.get("color", "")}
        return {"ok": True, "posters": res}

    def _ff(self) -> str:
        from app.engines.ytdlp_engine import find_ffmpeg
        return find_ffmpeg() or ""

    def media_extract_audio(self, path: str, codec: str = "") -> dict[str, Any]:
        from app.core import mediatools as mt
        if not os.path.isfile(str(path or "")) or not self._ff():
            return {"ok": False, "error": "bad_input"}
        return mt.extract_audio(self._ff(), str(path), str(codec or ""))

    def media_clip(self, path: str, a: float, b: float, mode: str = "copy") -> dict[str, Any]:
        from app.core import mediatools as mt
        if not os.path.isfile(str(path or "")) or not self._ff():
            return {"ok": False, "error": "bad_input"}
        return mt.clip(self._ff(), str(path), float(a), float(b), str(mode), "h264_nvenc")

    def media_repair(self, path: str) -> dict[str, Any]:
        from app.core import mediatools as mt
        if not os.path.isfile(str(path or "")) or not self._ff():
            return {"ok": False, "error": "bad_input"}
        return mt.repair(self._ff(), str(path))

    def library_trash(self, paths: list | None = None) -> dict[str, Any]:
        """Izlenmis diziyi Geri Donusum Kutusu'na tasi (yalnizca kutuphane klasorlerindeki dosyalar)."""
        from app.core import mediatools as mt
        roots = [os.path.normcase(os.path.abspath(d)) for d in self._library_dirs()]
        ok_paths = [p for p in (paths or []) if os.path.isfile(str(p))
                    and any(os.path.normcase(os.path.abspath(str(p))).startswith(r + os.sep) for r in roots)]
        if not ok_paths:
            return {"ok": False, "error": "no_files"}
        return {"ok": mt.to_trash(ok_paths), "count": len(ok_paths)}

    def lyrics_search(self, text: str) -> dict[str, Any]:
        """Sozden sarki bul: LRCLIB tam metin arama + kutuphanede eslesen dosya."""
        import re as _re
        import requests
        from app.core.library import scan
        q = str(text or "").strip()[:200]
        if len(q) < 4:
            return {"ok": False, "hits": []}
        js = []
        tok = self._genius.load() if self._genius else ""
        if tok:   # Genius resmi API sozlerin icinde de arar (sayfa cekilmez, sadece baslik/sanatci)
            try:
                r = requests.get("https://api.genius.com/search", params={"q": q}, headers={"Authorization": f"Bearer {tok}", "User-Agent": "Kami/1.0"}, timeout=15)
                for h in ((r.json().get("response") or {}).get("hits") or []) if r.status_code == 200 else []:
                    res = h.get("result") or {}
                    if h.get("type") == "song":
                        js.append({"artistName": (res.get("primary_artist") or {}).get("name", ""), "trackName": res.get("title", "")})
            except Exception:
                js = []
        if not js:   # LRCLIB yalnizca baslik/sanatci arar
            try:
                r = requests.get("https://lrclib.net/api/search", params={"q": q}, headers={"User-Agent": "Kami/1.0"}, timeout=15)
                js = r.json() if r.status_code == 200 else []
            except Exception:
                js = []
        norm = lambda x: _re.sub(r"[^\w]+", " ", str(x).lower()).strip()
        try:
            items = [it for it in scan(self._library_dirs()).get("items", []) if it.get("kind") == "audio"]
        except Exception:
            items = []
        hits, seen = [], set()
        for h in js[:15]:
            key = (norm(h.get("artistName")), norm(h.get("trackName")))
            if key in seen or not key[1]:
                continue
            seen.add(key)
            local = next((it["path"] for it in items if key[1] in norm(it["name"]) and (not key[0] or key[0].split()[0] in norm(it["name"]))), "")
            hits.append({"artist": h.get("artistName", ""), "title": h.get("trackName", ""), "local": local})
            if len(hits) >= 8:
                break
        return {"ok": True, "hits": hits}

    # ---------- 1.1: Bu sarki ne?, OpenSubtitles, sezon klasorleri, mini kart ----------
    def song_identify(self, path: str = "", start: float = 0) -> dict[str, Any]:
        from app.core import aitools
        src = str(path or "") if path and os.path.isfile(str(path)) else "loopback"
        res = aitools.identify_song(src, float(start or 0))
        if "error" in res:
            return {"ok": False, "error": str(res["error"])[:200]}
        self._last_song = res.get("done") or {}
        return {"ok": True, "song": self._last_song}

    # ---------- Donusturucu ----------
    def convert_view(self, on: bool = True) -> None:
        self._conv_view = bool(on)

    def convert_inbox(self) -> list[dict[str, Any]]:
        """Sag tik / surukle-birak ile bekleyen dosyalar (bir kez verilir) + her birinin secenekleri."""
        from app.core import converter as cv
        with self._conv_lock:
            got, self._conv_inbox = self._conv_inbox, []
        return [{"path": p, "name": os.path.basename(p), "kind": cv.kind(p), "targets": cv.targets(p),
                 "size": os.path.getsize(p) if os.path.isfile(p) else 0} for p in got if os.path.isfile(p)]

    def convert_add(self, paths: list[str]) -> None:
        with self._conv_lock:
            self._conv_inbox += [str(p) for p in paths or [] if p]

    def convert_pick(self) -> list[dict[str, Any]]:
        import webview
        if not self._window:
            return []
        dialog = getattr(getattr(webview, "FileDialog", None), "OPEN", None) or webview.OPEN_DIALOG
        res = self._window.create_file_dialog(dialog, allow_multiple=True)
        self.convert_add(list(res or []))
        return self.convert_inbox()

    def convert_info(self, paths: list[str]) -> list[dict[str, Any]]:
        self.convert_add(paths)
        return self.convert_inbox()

    def convert_tools(self) -> dict[str, Any]:
        from app.core import converter as cv
        return {"libreoffice": bool(cv.find_soffice())}

    def convert_install_office(self) -> dict[str, Any]:
        """LibreOffice'i winget ile kurar (Windows kendi onayini sorar)."""
        try:
            subprocess.Popen(["cmd", "/c", "start", "Kami - LibreOffice kurulumu", "winget", "install", "-e", "--id",
                              "TheDocumentFoundation.LibreOffice", "--accept-package-agreements", "--accept-source-agreements"])
            return {"ok": True}
        except OSError as exc:
            return {"ok": False, "error": str(exc)}

    def convert_start(self, paths: list[str], target: str, opts: dict | None = None) -> dict[str, Any]:
        from app.core import converter as cv
        from app.core.media_server import find_ffprobe
        from app.engines.ytdlp_engine import find_ffmpeg
        opts = dict(opts or {})
        paths = [str(p) for p in paths or [] if os.path.isfile(str(p))]
        if not paths:
            return {"ok": False, "error": "no_file"}
        ff = find_ffmpeg()
        tools = {"ffmpeg": ff, "ffprobe": find_ffprobe(ff)}
        if self._conv_cancel.is_set():
            self._conv_cancel = threading.Event()
        cancel = self._conv_cancel
        # birlestirme araclari: tum dosyalar tek cikti
        if target in ("pdf:merge", "pdf:images"):
            jobs = [{"id": f"c{next(self._job_ids)}", "name": f"{len(paths)} dosya → PDF", "src": paths, "target": target,
                     "state": "queued", "p": 0.0, "out": "", "error": ""}]
        else:
            jobs = [{"id": f"c{next(self._job_ids)}", "name": os.path.basename(p), "src": p, "target": target,
                     "state": "queued", "p": 0.0, "out": "", "error": ""} for p in paths]
        with self._conv_lock:
            self._conv_jobs = [j for j in self._conv_jobs if j["state"] in ("queued", "running")] + jobs

        def run() -> None:
            for j in jobs:
                if cancel.is_set():
                    j["state"], j["error"] = "error", "cancelled"
                    continue
                j["state"] = "running"
                try:
                    if j["target"] == "pdf:merge":
                        out = cv.pdf_merge(j["src"], opts)
                    elif j["target"] == "pdf:images":
                        out = cv.images_to_pdf(j["src"], opts, tools)
                    else:
                        out = cv.convert_one(j["src"], j["target"], opts, tools, lambda p, j=j: j.update(p=p), cancel)
                    j.update(state="done", p=1.0, out=str(out))
                except InterruptedError:
                    j.update(state="error", error="cancelled")
                except Exception as exc:
                    log.warning("Donusturme hatasi %s -> %s: %s", j["name"], j["target"], exc)
                    j.update(state="error", error=str(exc)[:160] or type(exc).__name__)

        threading.Thread(target=run, name="kami-convert", daemon=True).start()
        return {"ok": True, "n": len(jobs)}

    def convert_status(self) -> list[dict[str, Any]]:
        with self._conv_lock:
            return [{k: v for k, v in j.items() if k != "src"} for j in self._conv_jobs]

    def convert_cancel(self) -> None:
        self._conv_cancel.set()

    def convert_clear(self) -> None:
        with self._conv_lock:
            self._conv_jobs = [j for j in self._conv_jobs if j["state"] in ("queued", "running")]

    def convert_reveal(self, job_id: str) -> bool:
        j = next((x for x in self._conv_jobs if x["id"] == job_id), None)
        if not j or not j.get("out") or not os.path.exists(j["out"]):
            return False
        subprocess.Popen(["explorer", "/select,", os.path.normpath(j["out"])])
        return True

    # ---------- Lyric video (HyperFrames) ----------
    def lyricvideo_start(self, path: str, style: str = "kinetic", vertical: bool = False, start: float = 0,
                         length: float = 0, lrc: str = "") -> dict[str, Any]:
        """Senkron sozlerden MP4. lrc verilmezse dosyanin LRC/SRT/etiket sozleri aranir (player_lyrics)."""
        import tempfile
        from pathlib import Path as _P
        from app.core import lyricvideo as lv
        from app.engines.ytdlp_engine import find_ffmpeg
        path = str(path or "")
        if self._lv.get("state") == "running":
            return {"ok": False, "error": "busy"}
        if not os.path.isfile(path):
            return {"ok": False, "error": "no_file"}
        if not lv.find_node():
            return {"ok": False, "error": "node_yok"}
        lines = lv.parse_lrc(lrc) if lrc else []
        if not lines:
            p = _P(path)
            for side in [p.with_suffix(".lrc")] + sorted(p.parent.glob(p.stem + "*.srt")):
                if side.is_file():
                    t = side.read_text(encoding="utf-8-sig", errors="replace")
                    lines = lv.parse_lrc(t) if side.suffix == ".lrc" else lv.parse_srt(t)
                    if lines:
                        break
        if not lines:
            try:
                ly = self.player_lyrics(path, online=True)
                lines = lv.parse_lrc(ly.get("synced") or "")
            except Exception:
                lines = []
        if not lines:
            return {"ok": False, "error": "no_synced"}
        from app.core.media_server import find_ffprobe, probe
        ff = find_ffmpeg()
        tg = probe(find_ffprobe(ff), path).get("tags", {}) if ff else {}
        title = " - ".join(x for x in (tg.get("artist"), tg.get("title")) if x) or _P(path).stem
        vertical = bool(vertical)
        start = max(0.0, float(start or 0))
        length = float(length or 0) or (30.0 if vertical else 0.0)
        tag = "Reels" if vertical else "Lyric"
        out = str(_P(path).with_name(f"{_P(path).stem} ({tag} video).mp4"))
        n = 2
        while os.path.exists(out):
            out = str(_P(path).with_name(f"{_P(path).stem} ({tag} video {n}).mp4"))
            n += 1
        job = _P(tempfile.mkdtemp(prefix="kami_lyric_"))
        self._lv_cancel = threading.Event()
        self._lv = {"state": "running", "stage": "hazirlik", "line": "", "out": out, "src": path}

        def run() -> None:
            import shutil as _sh
            try:
                lv.build(job, path, lines, title, "", ff, style if style in ("kinetic", "simple", "karaoke") else "kinetic",
                         vertical, start, length)
                self._lv["stage"] = "render"
                def _ln(ln: str) -> None:
                    m = re.search(r'@hf-progress .*"pct":\s*(\d+)', ln)
                    if m:
                        self._lv.update(p=int(m.group(1)) / 100)

                res = lv.render(job, out, _ln, self._lv_cancel)
            except Exception as exc:
                log.exception("Lyric video")
                res = {"ok": False, "error": str(exc)[:160]}
            _sh.rmtree(job, ignore_errors=True)
            self._lv = {**self._lv, "state": "done" if res.get("ok") else "error", "error": res.get("error", "")}
            if res.get("ok"):
                en = self._manager.settings.get("language") == "en"
                try:
                    from app.core import desktop
                    desktop.toast(_P(out).name, "Lyric video ready" if en else "Lyric video hazır",
                                  [("Play" if en else "Oynat", "kami://lvplay"), ("Open folder" if en else "Klasörü aç", "kami://lvfolder")])
                except Exception:
                    log.exception("Lyric video bildirimi")

        threading.Thread(target=run, name="kami-lyricvideo", daemon=True).start()
        return {"ok": True, "out": out, "lines": len(lines)}

    def lyricvideo_status(self) -> dict[str, Any]:
        return dict(self._lv)

    def lyricvideo_cancel(self) -> None:
        self._lv_cancel.set()

    def lyricvideo_open(self, what: str = "play") -> bool:
        out = str(self._lv.get("out") or "")
        if self._lv.get("state") != "done" or not os.path.isfile(out):
            return False
        if what == "folder":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(out)])
        else:
            self._play_request(out)
        return True

    # ---------- Kami Reader ----------
    _rdoc = None

    def reader_show(self, path: str = "") -> dict[str, Any]:
        """Kami Reader penceresini acar (path verilirse o belgeyle)."""
        path = str(path or "")
        if path:
            with self._inbox_lock:
                self._reader_q = getattr(self, "_reader_q", []) + [path]
        if getattr(self, "_reader_win", None) is None and getattr(self, "_make_reader_window", None):
            self._reader_win = self._make_reader_window()
        elif getattr(self, "_front_reader", None):
            self._front_reader()
        return {"ok": True}

    def reader_poll(self) -> list[str]:
        with self._inbox_lock:
            q, self._reader_q = getattr(self, "_reader_q", []), []
        return q

    def reader_open(self, path: str) -> dict[str, Any]:
        from app.core import reader
        path = str(path or "")
        if not os.path.exists(path):
            return {"ok": False, "error": "no_file"}
        try:
            doc = reader.Doc(path)
        except Exception as exc:
            log.exception("Reader acilamadi")
            return {"ok": False, "error": str(exc)[:160]}
        if not doc.count:
            return {"ok": False, "error": "empty"}
        self.reader_close()
        self._rdoc = doc
        st = reader.load_state(doc.key)
        st["count"] = doc.count
        reader.save_state(doc.key, st, doc.path, doc.title)
        return {"ok": True, "kind": doc.kind, "count": doc.count, "title": doc.title, "path": doc.path,
                "state": st, "outline": doc.outline()}

    def reader_page(self, i: int, width: int = 1400, words: bool = False) -> dict[str, Any]:
        d = self._rdoc
        if not d or not 0 <= int(i) < d.count:
            return {"ok": False}
        try:
            r = d.page_image(int(i), max(200, min(4000, int(width))))
            if words:
                r["words"] = d.words(int(i))
            return {"ok": True, "i": int(i), **r}
        except Exception as exc:
            log.exception("Reader sayfa")
            return {"ok": False, "error": str(exc)[:160]}

    def reader_thumb(self, i: int) -> str:
        d = self._rdoc
        try:
            return d.thumb(int(i)) if d else ""
        except Exception:
            return ""

    def reader_cover(self, path: str) -> str:
        from app.core import reader
        try:
            return reader.cover(str(path))
        except Exception:
            return ""

    def reader_text(self, i: int) -> str:
        d = self._rdoc
        return d.text(int(i)) if d else ""

    def reader_search(self, q: str) -> list[dict[str, Any]]:
        d = self._rdoc
        return d.search(str(q)) if d else []

    def reader_save(self, state: dict[str, Any]) -> bool:
        from app.core import reader
        d = self._rdoc
        if not d or not isinstance(state, dict):
            return False
        state["count"] = d.count
        reader.save_state(d.key, state, d.path, d.title)
        return True

    def reader_recent(self) -> list[dict[str, Any]]:
        from app.core import reader
        return reader.recent()

    def reader_pick(self, folder: bool = False) -> str:
        import webview
        w = getattr(self, "_reader_win", None) or (webview.windows[0] if webview.windows else None)
        if not w:
            return ""
        if folder:
            r = w.create_file_dialog(webview.FOLDER_DIALOG)
        else:
            r = w.create_file_dialog(webview.OPEN_DIALOG, file_types=(
                "Kitap ve çizgi roman (*.pdf;*.cbz;*.cbr;*.cb7;*.zip;*.rar;*.7z)", "Tüm dosyalar (*.*)"))
        return str(r[0]) if r else ""

    def reader_speak(self, text: str, lang: str = "", rate: float = 1.0) -> dict[str, Any]:
        from app.core import reader
        text = str(text or "").strip()
        if not text:
            return {"ok": False, "error": "empty"}
        try:
            return {"ok": True, "src": reader.speak(text[:1500], str(lang or ""), float(rate or 1.0))}
        except Exception as exc:
            log.exception("Piper")
            return {"ok": False, "error": str(exc)[:160]}

    def reader_tts_status(self) -> dict[str, Any]:
        from app.core import reader
        return {**reader.TTS_STATE, "tr": reader.tts_installed("tr"), "en": reader.tts_installed("en")}

    def reader_split(self, text: str) -> list[str]:
        from app.core import reader
        return reader.split_sentences(str(text or ""))

    def reader_close(self) -> None:
        d, self._rdoc = self._rdoc, None
        if d:
            d.close()

    def reader_export_notes(self) -> dict[str, Any]:
        """Vurgu ve notlari belgenin yanina Markdown olarak yazar."""
        from app.core import reader
        d = self._rdoc
        if not d:
            return {"ok": False}
        st = reader.load_state(d.key)
        lines = [f"# {d.title}", ""]
        for h in sorted(st.get("hl", []), key=lambda x: (x.get("page", 0), x.get("y", 0))):
            lines.append(f"- **s. {h.get('page', 0) + 1}** — {h.get('text', '').strip()}")
            if h.get("note"):
                lines.append(f"  - Not: {h['note']}")
        base = d.path if os.path.isfile(d.path) else os.path.join(d.path, d.title)
        out = os.path.splitext(base)[0] + " - notlar.md"
        with open(out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return {"ok": True, "path": out}

    # ---------- Kami Oda (sesli oda + ekran paylasimi + oynatici yayini) ----------
    def _room_name(self) -> str:
        return str(self._manager.settings.get("watch_name") or os.environ.get("USERNAME") or "Kami")

    def room_open(self, show: bool = True) -> dict[str, Any]:
        """Odayi acar (tunel ilk seferde cloudflared indirir) ve Kami Oda penceresini gosterir."""
        from app.core import room
        st = room.SERVER.start(self._room_name(), True, self._room_id())
        if show:
            self._show_room(st["local"])
        return {**st, "name": self._room_name()}

    def _room_id(self) -> str:
        import secrets as _s
        rid = str(self._manager.settings.get("room_id") or "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{10,40}", rid):
            rid = _s.token_urlsafe(12)
            self._manager.settings.set("room_id", rid)
        return rid

    def room_join(self, url: str) -> dict[str, Any]:
        """Baskasinin oda baglantisini Kami penceresinde acar."""
        url = str(url or "").strip()
        if not re.match(r"^https://[a-z0-9.-]+\.(trycloudflare\.com|workers\.dev)/[A-Za-z0-9_-]+/?$", url) and not url.startswith("http://127.0.0.1:"):
            return {"ok": False, "error": "bad_url"}
        self._show_room(url if url.endswith("/") else url + "/")
        return {"ok": True}

    def _show_room(self, url: str) -> None:
        w = getattr(self, "_room_win", None)
        if w is None and getattr(self, "_make_room_window", None):
            self._room_win = self._make_room_window(url)
        elif w is not None:
            try:
                if (w.get_current_url() or "").rstrip("/") != url.rstrip("/"):
                    w.load_url(url)
            except Exception:
                pass
            getattr(self, "_front_room", None) and self._front_room()

    def room_status(self) -> dict[str, Any]:
        from app.core import room
        return {**room.SERVER.status(), "name": self._room_name()}

    def room_relink(self) -> dict[str, Any]:
        """Sabit adrese guncel tunel adresini yeniden bildirir (tunel yoksa acar)."""
        from app.core import room
        if not room.SERVER.room:
            return self.room_open(False)
        if room.SERVER.public:
            room.SERVER._publish(room.SERVER.public)
        else:
            room.SERVER.start(self._room_name(), True, self._room_id())
        return self.room_status()

    def room_stop(self) -> bool:
        from app.core import room
        room.SERVER.stop()
        w = getattr(self, "_room_win", None)
        if w is not None:
            try:
                w.destroy()
            except Exception:
                pass
        return True

    def room_turn_set(self, key_id: str, token: str) -> dict[str, Any]:
        """Cloudflare Realtime TURN: 'Turn Token ID' + 'API Token'. Denenir, DPAPI ile saklanir."""
        from app.core import room
        key_id, token = str(key_id or "").strip(), str(token or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9]{16,64}", key_id) or not re.fullmatch(r"[A-Za-z0-9_\-]{20,200}", token):
            return {"ok": False, "error": "bad_format"}
        store = self._turn_store
        old = store.load() if store else ""
        if not store:
            return {"ok": False, "error": "no_store"}
        store.save(key_id + ":" + token)
        r = room.SERVER.test_turn()
        if not r["ok"]:
            store.save(old) if old else store.clear()
            room.SERVER.test_turn()
            return {"ok": False, "error": "rejected"}
        return {"ok": True}

    def room_turn_status(self) -> dict[str, Any]:
        return {"has": bool(self._turn_store and self._turn_store.load())}

    def room_turn_clear(self) -> dict[str, Any]:
        if self._turn_store:
            self._turn_store.clear()
        return {"ok": True}

    def copy_text(self, text: str) -> bool:
        try:
            import subprocess as sp
            sp.run(["clip"], input=str(text).encode("utf-16-le"), check=False, creationflags=0x08000000)
            return True
        except Exception:
            return False

    # ---------- Ekran kaydi ----------
    recorder = None   # main.py baglar

    def rec_status(self) -> dict[str, Any]:
        r = self.recorder
        return r.status() if r else {"replay": False, "recording": False, "error": "yok"}

    def rec_toggle(self) -> dict[str, Any]:
        r = self.recorder
        if not r:
            return {"ok": False, "error": "yok"}
        res = r.toggle_record()
        self._rec_done(res, start_msg=True)
        return res

    def rec_save_replay(self) -> dict[str, Any]:
        r = self.recorder
        if not r:
            return {"ok": False, "error": "yok"}
        try:
            res = {"ok": True, "path": r.save_replay(), "replay": True}
        except Exception as exc:
            res = {"ok": False, "error": str(exc)[:160], "replay": True}
        self._rec_done(res)
        return res

    def rec_replay(self, on: bool) -> dict[str, Any]:
        r = self.recorder
        if not r:
            return {"ok": False}
        ok = r.start_replay() if on else (r.stop_replay() or True)
        return {"ok": bool(ok), **r.status()}

    def rec_open_folder(self) -> bool:
        from app.core.recorder import clips_dir
        os.startfile(str(clips_dir())) if os.name == "nt" else None
        return True

    def _rec_done(self, res: dict[str, Any], start_msg: bool = False) -> None:
        from app.core import desktop
        en = self._manager.settings.get("language") == "en"
        if res.get("recording"):
            desktop.toast("Kami", "Recording started (Alt+F9 to stop)" if en else "Kayıt başladı (durdurmak için Alt+F9)", [])
            return
        if res.get("ok") and res.get("path"):
            self._rec_last = res["path"]
            title = ("Clip saved" if en else "Klip kaydedildi") if res.get("replay") else ("Recording saved" if en else "Kayıt kaydedildi")
            desktop.toast(title, os.path.basename(res["path"]), [("Play / trim" if en else "Oynat / kırp", "kami://recplay"),
                                                                ("Edit in Studio" if en else "Studio'da Kurguya Aç", "kami://recstudio"),
                                                                ("Open folder" if en else "Klasörü aç", "kami://recfolder")])
            if self._manager.settings.get("chain_rec_studio"):
                self.studio_show(res["path"])
        elif not res.get("ok"):
            desktop.toast("Kami", ("Could not save: " if en else "Kaydedilemedi: ") + str(res.get("error", "")), [])

    # ---------- Fotograf goruntuleyici ----------
    # RAW (faz 5): rawpy/LibRaw ile kamera beyaz dengesiyle gelistirilir (Canon CR2/CR3, Nikon NEF, Sony ARW, Fuji RAF, DNG...)
    RAW_EXT = (".cr2", ".cr3", ".nef", ".nrw", ".arw", ".srf", ".sr2", ".raf", ".orf", ".rw2", ".pef", ".dng", ".srw", ".3fr", ".iiq")
    IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif", ".jfif", ".heic", ".tif", ".tiff") + RAW_EXT

    @staticmethod
    def _open_raw(path: str, half: bool = True):
        """RAW -> PIL RGB. half=True: goruntuleyici/onizleme icin yari cozunurluk (cok daha hizli)."""
        import rawpy
        from PIL import Image
        with rawpy.imread(path) as r:
            rgb = r.postprocess(use_camera_wb=True, half_size=half, no_auto_bright=False, output_bps=8)
        return Image.fromarray(rgb)

    def image_data(self, path: str, max_side: int = 3000) -> dict[str, Any]:
        """Goruntuleyici icin data URL (buyuk/HEIC/RAW gorseller kucultulup JPEG/PNG'ye cevrilir)."""
        import base64
        import io
        path = str(path or "")
        if not os.path.isfile(path) or not path.lower().endswith(self.IMAGE_EXT):
            return {"ok": False, "error": "no_file"}
        try:
            from PIL import Image, ImageOps
            if path.lower().endswith(self.RAW_EXT):
                try:
                    im = self._open_raw(path, half=max_side <= 3000)
                except ImportError:
                    return {"ok": False, "error": "raw_unsupported"}
                im.format = "RAW"
            else:
                im = Image.open(path)
            w, h = im.size
            fmt = (im.format or "").upper()
            exif = {}
            try:
                ex = im.getexif()
                exif = {k: str(v)[:60] for k, v in {"Kamera": ex.get(0x0110), "Tarih": ex.get(0x0132)}.items() if v}
            except Exception:
                pass
            raw = open(path, "rb").read() if fmt in ("JPEG", "PNG", "WEBP", "GIF") and max(w, h) <= max_side and os.path.getsize(path) < 25e6 else None
            if raw is None:
                im = ImageOps.exif_transpose(im)
                im.thumbnail((max_side, max_side))
                buf = io.BytesIO()
                im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB").save(buf, "PNG" if im.mode in ("RGBA", "LA", "P") else "JPEG", quality=92)
                raw, fmt = buf.getvalue(), ("PNG" if im.mode in ("RGBA", "LA", "P") else "JPEG")
            mime = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp", "GIF": "image/gif"}.get(fmt, "image/png")
            return {"ok": True, "url": f"data:{mime};base64," + base64.b64encode(raw).decode(), "w": w, "h": h,
                    "size": os.path.getsize(path), "name": os.path.basename(path), "exif": exif}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:120]}

    # ---------- Kami Picture + Kami Lens ----------
    def picture_open(self, path: str, lens: bool = False, edit: bool = False) -> dict[str, Any]:
        """Kami Picture penceresini acar; lens=True ise hemen gorsel aramasi, edit=True ise editorde acar.
        path='screen': ekrandan alan sec."""
        path = str(path or "")
        if path == "screen":
            path = self.lens_screen_grab()
            if not path:
                return {"ok": False, "error": "cancelled"}
            lens = not edit
        if not os.path.isfile(path):
            return {"ok": False, "error": "no_file"}
        with self._inbox_lock:
            self._picture_q = getattr(self, "_picture_q", []) + [{"path": path, "lens": bool(lens), "edit": bool(edit)}]
        if getattr(self, "_picture_win", None) is None and getattr(self, "_make_picture_window", None):
            self._picture_win = self._make_picture_window()
        elif getattr(self, "_front_picture", None):
            self._front_picture()
        return {"ok": True}

    # ---------- Picture editoru: yapay zeka (IOPaint) ----------
    def pic_ai_status(self) -> dict[str, Any]:
        from app.core import aitools, iopaint_srv
        return {"installed": aitools.installed("iopaint"), "size_gb": aitools.TOOLS["iopaint"]["size_gb"],
                "installing": (self._ai.installing.get("iopaint") if self._ai else None),
                "state": iopaint_srv.SERVER.state, "device": iopaint_srv.SERVER.device, "error": aitools.LAST_ERROR.get("iopaint", "")}

    def pic_ai(self, op: str, image: str, mask: str = "", clicks: list | None = None, scale: float = 4.0) -> dict[str, Any]:
        """op: erase (LaMa, maske gerekli) | seg (SAM2 tikla-sec maskesi) | nobg | upscale | face"""
        from app.core import iopaint_srv
        S = iopaint_srv.SERVER
        try:
            if op == "erase":
                return {"ok": True, "image": S.inpaint(image, mask)}
            if op == "seg":
                return {"ok": True, "image": S.plugin("InteractiveSeg", image, clicks=[[int(c[0]), int(c[1]), int(c[2])] for c in (clicks or [])], mask=True)}
            name = {"nobg": "RemoveBG", "upscale": "RealESRGAN", "face": "GFPGAN"}.get(op)
            if not name:
                return {"ok": False, "error": "bad_op"}
            return {"ok": True, "image": S.plugin(name, image, scale=float(scale or 4))}
        except Exception as exc:
            log.exception("Picture AI: %s", op)
            return {"ok": False, "error": str(exc)[:200]}

    # ---------- Picture editoru ----------
    def picture_open_editor(self) -> dict[str, Any]:
        """Kami Picture'i bos editorle (sablon secimi) acar."""
        with self._inbox_lock:
            self._picture_q = getattr(self, "_picture_q", []) + [{"path": "", "lens": False, "edit": True}]
        if getattr(self, "_picture_win", None) is None and getattr(self, "_make_picture_window", None):
            self._picture_win = self._make_picture_window()
        elif getattr(self, "_front_picture", None):
            self._front_picture()
        return {"ok": True}

    def _edit_out_dir(self, near: str) -> str:
        if near and os.path.isfile(near):
            return os.path.dirname(near)
        d = os.path.join(os.path.expanduser("~"), "Pictures", "Kami")
        os.makedirs(d, exist_ok=True)
        return d

    def editor_export(self, near: str, name: str, fmt: str, data_url: str) -> dict[str, Any]:
        """Duzenlenen gorseli orijinalin yanina '<ad> (düzenlendi).png' olarak yazar (uzerine yazmaz)."""
        import base64
        fmt = fmt if fmt in ("png", "jpg", "webp") else "png"
        try:
            raw = base64.b64decode(str(data_url).split(",", 1)[1])
        except Exception:
            return {"ok": False, "error": "bad_data"}
        base = re.sub(r'[\\/:*?"<>|]+', "_", str(name or "Kami"))[:80] or "Kami"
        d = self._edit_out_dir(str(near or ""))
        out = os.path.join(d, f"{base} (düzenlendi).{fmt}")
        n = 2
        while os.path.exists(out):
            out = os.path.join(d, f"{base} (düzenlendi {n}).{fmt}")
            n += 1
        with open(out, "wb") as f:
            f.write(raw)
        return {"ok": True, "path": out}

    def editor_vectorize(self, near: str, name: str, data_url: str, preset: str = "color") -> dict[str, Any]:
        """Bitmap -> SVG (vtracer). preset: color (logo/cizim, renkli) | bw (siyah-beyaz cizgi) | photo (ayrintili)."""
        import base64
        import vtracer
        raw = base64.b64decode(str(data_url).split(",", 1)[1])
        opts = {"color": dict(colormode="color", hierarchical="stacked", mode="spline", filter_speckle=4, color_precision=6,
                              layer_difference=16, corner_threshold=60, length_threshold=4.0, splice_threshold=45),
                "bw": dict(colormode="binary", mode="spline", filter_speckle=4, corner_threshold=60),
                "photo": dict(colormode="color", hierarchical="stacked", mode="spline", filter_speckle=8, color_precision=8,
                              layer_difference=8, corner_threshold=60)}.get(preset, {})
        try:
            svg = vtracer.convert_raw_image_to_svg(raw, img_format="png", **opts)
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:160]}
        base = re.sub(r'[\\/:*?"<>|]+', "_", str(name or "Kami"))[:80] or "Kami"
        out = os.path.join(self._edit_out_dir(str(near or "")), base + ".svg")
        n = 2
        while os.path.exists(out):
            out = os.path.join(self._edit_out_dir(str(near or "")), f"{base} ({n}).svg")
            n += 1
        with open(out, "w", encoding="utf-8") as f:
            f.write(svg)
        return {"ok": True, "path": out, "svg": svg}

    def editor_gif(self, near: str, name: str, frames: list, ms: int = 120, fmt: str = "gif") -> dict[str, Any]:
        """Katmanlar = kareler: GIF ya da MP4 (ffmpeg)."""
        import base64
        import io
        from PIL import Image
        imgs = [Image.open(io.BytesIO(base64.b64decode(str(f).split(",", 1)[1]))).convert("RGBA") for f in frames[:400]]
        if not imgs:
            return {"ok": False, "error": "no_frames"}
        base = re.sub(r'[\\/:*?"<>|]+', "_", str(name or "Kami"))[:80] or "Kami"
        d = self._edit_out_dir(str(near or ""))
        out = os.path.join(d, f"{base} (animasyon).{'mp4' if fmt == 'mp4' else 'gif'}")
        if fmt == "mp4":
            import subprocess
            import tempfile
            from app.engines.ytdlp_engine import find_ffmpeg
            tmp = tempfile.mkdtemp(prefix="kami_anim_")
            for i, im in enumerate(imgs):
                bg = Image.new("RGB", im.size, (0, 0, 0)); bg.paste(im, mask=im.split()[3]); bg.save(os.path.join(tmp, f"{i:04d}.png"))
            r = subprocess.run([find_ffmpeg(), "-y", "-loglevel", "error", "-framerate", f"{1000 / max(20, ms):.3f}", "-i", os.path.join(tmp, "%04d.png"),
                                "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "18", out],
                               capture_output=True, creationflags=0x08000000)
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
            if r.returncode != 0:
                return {"ok": False, "error": "ffmpeg"}
        else:
            imgs[0].save(out, save_all=True, append_images=imgs[1:], duration=max(20, int(ms)), loop=0, disposal=2, optimize=False)
        return {"ok": True, "path": out}

    def editor_project_save(self, path: str, name: str, data: str) -> dict[str, Any]:
        """.kami projesi (katmanlar, metinler, ayarlar) — JSON."""
        path = str(path or "")
        if not path:
            base = re.sub(r'[\\/:*?"<>|]+', "_", str(name or "Kami"))[:80] or "Kami"
            path = os.path.join(self._edit_out_dir(""), base + ".kami")
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(data))
        return {"ok": True, "path": path}

    def editor_project_open(self) -> dict[str, Any]:
        import webview
        w = getattr(self, "_picture_win", None)
        if not w:
            return {"ok": False}
        r = w.create_file_dialog(webview.OPEN_DIALOG, directory=self._edit_out_dir(""), file_types=("Kami projesi (*.kami)",))
        if not r:
            return {"ok": False}
        with open(r[0], encoding="utf-8") as f:
            return {"ok": True, "path": r[0], "data": f.read()}

    # ---------- Faz 10: Picture Pro, Lightroom, Mockup, OKLCH & Telif Imzasi ----------

    def pic_freq_sep(self, image: str, radius: float = 4.0) -> dict[str, Any]:
        from app.core.picture_pro import frequency_separation
        return frequency_separation(str(image), radius=float(radius))

    def pic_seam_carve(self, image: str, target_w: int, target_h: int, out_path: str = "") -> dict[str, Any]:
        from app.core.picture_pro import seam_carve_resize
        return seam_carve_resize(str(image), int(target_w), int(target_h), str(out_path or ""))

    def pic_clone_lut(self, src_image: str, ref_image: str, out_cube: str, size: int = 17) -> dict[str, Any]:
        from app.core.picture_pro import clone_lut_from_reference
        return clone_lut_from_reference(str(src_image), str(ref_image), str(out_cube), size=int(size))

    def pic_cube_to_hald(self, cube_path: str, out_png: str) -> dict[str, Any]:
        from app.core.picture_pro import cube_to_haldclut
        return cube_to_haldclut(str(cube_path), str(out_png))

    def pic_hdr_merge(self, images: list[str], out_path: str) -> dict[str, Any]:
        from app.core.picture_pro import hdr_merge_mertens
        return hdr_merge_mertens([str(x) for x in (images or [])], str(out_path))

    def pic_focus_stack(self, images: list[str], out_path: str) -> dict[str, Any]:
        from app.core.picture_pro import focus_stack_laplacian
        return focus_stack_laplacian([str(x) for x in (images or [])], str(out_path))

    def pic_ecom_pack(self, image: str, pad_ratio: float = 0.12, size: int = 1200, shadow: bool = True) -> dict[str, Any]:
        from app.core.picture_pro import ecommerce_studio_pack
        return ecommerce_studio_pack(str(image), pad_ratio=float(pad_ratio), size=int(size), shadow=bool(shadow))

    def pic_mockup(self, design: str, base: str, dst_quad: list[list[float]], out_path: str = "") -> dict[str, Any]:
        from app.core.picture_pro import perspective_mockup
        return perspective_mockup(str(design), str(base), dst_quad or [], str(out_path or ""))

    def pic_oklch_palette(self, image: str, count: int = 6) -> dict[str, Any]:
        from app.core.picture_pro import oklch_palette
        return oklch_palette(str(image), count=int(count))

    def pic_watermark_embed(self, image: str, text: str, out_path: str = "") -> dict[str, Any]:
        from app.core.picture_pro import embed_blind_watermark
        return embed_blind_watermark(str(image), str(text), str(out_path or ""))

    def pic_watermark_read(self, image: str) -> dict[str, Any]:
        from app.core.picture_pro import extract_blind_watermark
        return extract_blind_watermark(str(image))

    def pic_ai_bridge_status(self) -> dict[str, Any]:
        from app.core.picture_pro import ai_bridge_status
        return ai_bridge_status()

    def picture_poll(self) -> list[dict[str, Any]]:
        with self._inbox_lock:
            q, self._picture_q = getattr(self, "_picture_q", []), []
        return q

    def lens_search(self, path: str) -> dict[str, Any]:
        from app.core import lens
        if not os.path.isfile(str(path or "")):
            return {"ok": False, "error": "no_file"}
        try:
            return lens.search(str(path))
        except Exception as exc:
            log.exception("Kami Lens")
            return {"ok": False, "error": str(exc)[:160]}

    def lens_download(self, url: str, near: str = "") -> dict[str, Any]:
        """Bulunan en buyuk / secilen gorseli indirir (aranan gorselin klasorune; yoksa indirme klasorune)."""
        from app.core import lens
        urls = [str(u) for u in (url if isinstance(url, list) else [url]) if str(u or "").startswith(("http://", "https://"))]
        if not urls:
            return {"ok": False, "error": "bad_url"}
        folder = os.path.dirname(str(near)) if near and os.path.isfile(str(near)) and "kami_lens_" not in str(near) else self._manager.settings.get("download_dir")
        stem = os.path.splitext(os.path.basename(str(near)))[0] if near else "lens"
        try:
            return {"ok": True, "path": lens.download(urls, folder, stem)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:160]}

    def lens_screen_grab(self) -> str:
        """Ekran goruntusu al, secim penceresinde alan sectir, kirpilmis PNG yolunu dondur (iptal: '')."""
        import tempfile
        import time
        from PIL import ImageGrab
        shot = os.path.join(tempfile.gettempdir(), f"kami_lens_full_{int(time.time())}.png")
        ImageGrab.grab(all_screens=False).save(shot)
        self._grab = {"full": shot, "rect": None, "done": threading.Event()}
        if getattr(self, "_make_grab_window", None):
            self._make_grab_window()
        if not self._grab["done"].wait(120) or not self._grab["rect"]:
            return ""
        from PIL import Image
        x, y, w, h = self._grab["rect"]
        out = shot.replace("_full_", "_")
        Image.open(shot).crop((int(x), int(y), int(x + w), int(y + h))).save(out)
        try:
            os.remove(shot)
        except OSError:
            pass
        return out

    def lens_grab_info(self) -> dict[str, Any]:
        g = getattr(self, "_grab", None)
        if not g:
            return {}
        import base64
        return {"url": "data:image/png;base64," + base64.b64encode(open(g["full"], "rb").read()).decode()}

    def lens_grab_done(self, x: float = 0, y: float = 0, w: float = 0, h: float = 0) -> None:
        g = getattr(self, "_grab", None)
        if not g:
            return
        g["rect"] = (x, y, w, h) if w > 8 and h > 8 else None
        g["done"].set()
        win = getattr(self, "_grab_win", None)
        if win is not None:
            threading.Thread(target=win.destroy, daemon=True).start()
            self._grab_win = None

    def picture_send(self, path: str, target: str = "") -> None:
        """Kami Picture -> Donusturucu (ana pencerede acilir)."""
        self.convert_add([str(path)])
        if target:
            self._conv_target = str(target)
        if self._show_main:
            self._show_main()

    def convert_preset(self) -> str:
        t, self._conv_target = getattr(self, "_conv_target", ""), ""
        return t

    def open_path_folder(self, path: str) -> bool:
        path = str(path or "")
        if not os.path.isfile(path):
            return False
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        return True

    def image_siblings(self, path: str) -> list[str]:
        """Ayni klasordeki gorseller (ileri / geri gezinme)."""
        d = os.path.dirname(str(path or ""))
        try:
            return sorted(os.path.join(d, n) for n in os.listdir(d) if n.lower().endswith(self.IMAGE_EXT))[:2000]
        except OSError:
            return []

    def opensub_status(self) -> dict[str, Any]:
        return {"has_key": bool(self._osub and self._osub.load())}

    def opensub_set_key(self, key: str) -> dict[str, Any]:
        if not self._osub:
            return {"ok": False}
        key = str(key or "").strip()
        self._osub.save(key) if key else self._osub.clear()
        return {"ok": True, "has_key": bool(key)}

    def _page_title_for(self, path: str) -> str:
        if not self.manager:
            return ""
        norm = os.path.normcase(os.path.abspath(path))
        base = os.path.basename(path)
        items = self.manager.store.list()
        for d in items:
            full = os.path.join(d.directory, d.filename) if d.directory and d.filename else ""
            if full and os.path.normcase(os.path.abspath(full)) == norm:
                t = str((d.extra or {}).get("page_title") or "").strip()
                if t:
                    return t
        for d in items:
            if d.filename and d.filename == base:
                t = str((d.extra or {}).get("page_title") or "").strip()
                if t:
                    return t
        return ""

    def subtitle_fetch(self, path: str, lang: str = "tr", title: str = "", file_id: int = 0) -> dict[str, Any]:
        """OpenSubtitles: videonun yanina <ad>.<dil>.srt indirir, oynatici VTT'yi alir. file_id verilirse o aday."""
        from app.core import opensubs
        from app.core.media_server import srt_to_vtt
        key = self._osub.load() if self._osub else ""
        if not key:
            return {"ok": False, "error": "no_key"}
        if not os.path.isfile(str(path or "")):
            return {"ok": False, "error": "bad_input"}
        lang = str(lang or "tr")[:5]
        hint = str(title or "") or self._page_title_for(str(path))
        if file_id:
            res = opensubs.download(str(path), key, int(file_id), lang)
        else:
            res = opensubs.find_and_download(str(path), key, lang, hint)
        if not res.get("ok"):
            return res
        return {"ok": True, "path": res["path"], "release": res.get("release", ""), "vtt": srt_to_vtt(res.pop("srt"))}

    def subtitle_search(self, path: str, lang: str = "tr", title: str = "") -> dict[str, Any]:
        """'Bul' dugmesi: dogrulanmis adaylar listesi (kullanici secer)."""
        from app.core import opensubs
        key = self._osub.load() if self._osub else ""
        if not key:
            return {"ok": False, "error": "no_key"}
        if not os.path.isfile(str(path or "")):
            return {"ok": False, "error": "bad_input"}
        hint = str(title or "") or self._page_title_for(str(path))
        return opensubs.search(str(path), key, str(lang or "tr")[:5], hint)

    def library_organize(self, paths: list | None = None, apply: bool = False) -> dict[str, Any]:
        """Dizi bolumlerini 'Dizi / Sezon 01 / bolum' duzenine tasi (once onizleme, apply=True ile tasir; yan altyazilar da gider)."""
        import re as _re
        import shutil
        from pathlib import Path
        from app.core.library import parse_name
        roots = [os.path.normcase(os.path.abspath(d)) for d in self._library_dirs()]
        bad = '<>:"/\\|?*'
        moves: list[list[str]] = []
        for p in [Path(str(x)) for x in (paths or [])]:
            if not p.is_file() or not any(os.path.normcase(str(p.resolve())).startswith(r + os.sep) for r in roots):
                continue
            info = parse_name(p.stem)
            series = "".join(c for c in (info.get("series") or "") if c not in bad).strip(" .")
            if not series:
                continue
            season = int(info.get("season") or 1)
            parent = p.parent
            if _re.match(r"^(sezon|season|s)\s*\d+$", parent.name, _re.I):
                sdir = parent.parent
            elif series.lower()[:12] in parent.name.lower():
                sdir = parent
            else:
                sdir = parent / series
            dst_dir = sdir / f"Sezon {season:02d}"
            if dst_dir == parent:
                continue
            moves.append([str(p), str(dst_dir / p.name)])
            for side in parent.glob(_re.sub(r"([\[\]])", r"[\1]", p.stem) + ".*"):
                if side != p and side.suffix.lower() in (".srt", ".ass", ".ssa", ".vtt", ".lrc", ".sub", ".idx"):
                    moves.append([str(side), str(dst_dir / side.name)])
        if not apply:
            return {"ok": True, "moves": moves, "count": len(moves)}
        done = 0
        for src, dst in moves:
            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if not os.path.exists(dst):
                    shutil.move(src, dst)
                    done += 1
            except OSError:
                log.warning("Tasinamadi: %s", src)
        return {"ok": True, "count": done}

    def handle_uri(self, uri: str) -> None:
        """kami://play?id=N | folder?id=N | subs?id=N | show (bildirim dugmeleri)."""
        from urllib.parse import parse_qs, urlparse
        u = urlparse(str(uri))
        act = (u.netloc or u.path.strip("/")).lower()
        q = parse_qs(u.query)
        did = int((q.get("id") or ["0"])[0] or 0)
        try:
            if act == "play" and did:
                self.player_show({"id": did})
            elif act == "folder" and did:
                self.open_folder(did)
            elif act == "room":
                self.room_open(True)
            elif act == "phoneinbox":
                from app import paths
                inbox = paths.DATA_DIR / "phone_inbox"
                inbox.mkdir(parents=True, exist_ok=True)
                subprocess.Popen(["explorer", os.path.normpath(str(inbox))])
            elif act in ("recplay", "recfolder", "recstudio"):    # son ekran kaydi / klip
                out = str(getattr(self, "_rec_last", "") or "")
                if os.path.isfile(out):
                    if act == "recfolder":
                        subprocess.Popen(["explorer", "/select,", os.path.normpath(out)])
                    elif act == "recstudio":
                        self.studio_show(out)
                    else:
                        self._play_request(out)
            elif act in ("lvplay", "lvfolder"):   # yol URI'de degil: son lyric video
                self.lyricvideo_open("folder" if act == "lvfolder" else "play")
            elif act == "subs" and did:
                self.ai_run("whisper", did)
                self._show_main and self._show_main()
            else:
                self._show_main and self._show_main()
        except Exception:
            log.exception("kami:// islenemedi: %s", uri)

    def card_state(self) -> dict[str, Any]:
        """Masaustu mini karti: toplam hiz, aktif sayisi, toplam yuzde, kalan sure, goz durumu."""
        n, size, done = 0, 0, 0
        for d in self._manager.snapshot():
            st = str(getattr(d.status, "value", d.status)).lower().split(".")[-1]
            if st in ("active", "waiting"):
                n += 1
                size += int(getattr(d, "size", 0) or 0)
                done += int(getattr(d, "downloaded", 0) or 0)
        spd = int(self._manager.total_speed() or 0)
        eta = int((size - done) / spd) if spd and size > done else 0
        state = ("speed" if spd >= 8 * 1024 * 1024 else "down") if n else "idle"
        return {"n": n, "speed": spd, "p": round(done / size, 3) if size else 0, "eta": eta, "state": state}

    def card_open(self) -> None:
        if self._card_win is not None:
            self._card_win.hide()
        if self._show_main:
            self._show_main()

    def card_close(self) -> None:
        self._card_hidden = True   # bu oturumda gosterme
        if self._card_win is not None:
            self._card_win.hide()

    def card_drop(self, text: str) -> None:
        if str(text or "").strip():
            try:
                self.add_text(str(text).strip())
            except Exception:
                log.exception("Karta birakilan link eklenemedi")

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
        """Klasor listeleri ("folder:<yol>") her acilista klasorun guncel icerigine acilir (yeni dosyalar da gelir)."""
        out = {}
        for name, items in self._pl().all().items():
            if len(items) == 1 and str(items[0]).startswith("folder:"):
                from app.core.library import scan
                d = str(items[0])[7:]
                try:
                    files = sorted((it["path"] for it in scan([d]).get("items", [])), key=lambda p: p.lower())
                except Exception:
                    files = []
                out[name] = files
            else:
                out[name] = items
        return out

    def playlist_add_folder(self) -> dict[str, Any]:
        """Listeler: bir klasor sec, adiyla klasor listesi olarak kaydet."""
        import webview
        if self._player_win is None:
            return {"ok": False}
        dialog = getattr(getattr(webview, "FileDialog", None), "FOLDER", None) or webview.FOLDER_DIALOG
        res = self._player_win.create_file_dialog(dialog, directory=str(self._manager.base_dir()))
        d = res[0] if res else ""
        if not d:
            return {"ok": False}
        name = "📁 " + (os.path.basename(os.path.normpath(d)) or d)
        self._pl().save(name, ["folder:" + d])
        return {"ok": True, "name": name}

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
        if action.startswith("pad:"):
            act = action.split(":", 1)[1]
            if act == "rec_toggle":
                self.rec_toggle()
            elif act == "rec_replay":
                self.rec_save_replay()
            elif act == "studio":
                self.studio_show()
            elif act == "picture":
                self.picture_open_editor()
            else:
                return False
            return True
        return False

    def phone_on_upload(self, path: str, kind: str) -> None:
        from app.ui import desktop
        desktop.toast("Kami Mobil Köprü", f"Telefondan alındı: {os.path.basename(path)}",
                      [("Klasörü aç", "kami://phoneinbox")])
        if kind == "snap" and os.path.isfile(path):
            self.picture_open(path, edit=True)

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

    # ---------- Faz 2: Bypass, Sezon Kaziyici, Grab-All ----------
    def bypass_resolve(self, url: str) -> dict[str, Any]:
        from app.core import bypass
        return bypass.resolve(str(url or "").strip())

    def season_scrape(self, url: str) -> dict[str, Any]:
        from app.core import season_scraper
        return season_scraper.scrape_season(str(url or "").strip())

    def season_download(self, episodes: list, show_title: str = "") -> dict[str, Any]:
        from app.core.models import DownloadRequest
        from app.core.categories import sanitize_filename
        added = 0
        for ep in list(episodes or []):
            if not isinstance(ep, dict):
                continue
            stream = str(ep.get("stream_url") or "").strip()
            if not stream:
                continue
            ep_no = int(ep.get("episode") or 0)
            base = sanitize_filename(str(ep.get("title") or f"{show_title} - S01E{ep_no:02d}".strip(" -")))
            page_url = str(ep.get("page_url") or "")
            headers = {"Referer": str(ep.get("embed_url") or page_url)} if (ep.get("embed_url") or page_url) else {}
            try:
                if ".m3u8" in stream.lower() or ".txt" in stream.lower():
                    self._manager.add_media(stream, title=base, source="season_scraper", page_url=page_url, headers=headers)
                else:
                    ext = os.path.splitext(stream.split("?")[0])[1] or ".mp4"
                    fname = base if base.lower().endswith(ext.lower()) else f"{base}{ext}"
                    self._manager.add(DownloadRequest(url=stream, filename=fname, referer=headers.get("Referer", ""),
                                                      headers=headers, source="season_scraper", page_url=page_url,
                                                      extra={"page_title": base}))
                added += 1
            except Exception:
                log.warning("Sezon bolumu kuyruga eklenemedi: %s", stream, exc_info=True)
        return {"ok": added > 0, "added": added}

    def grab_all_status(self) -> dict[str, Any]:
        from app.core import grab_all
        exe = grab_all.find_gallery_dl()
        st = dict(getattr(self, "_grab_state", None) or {})
        return {
            "installed": bool(exe),
            "exe": exe or "",
            "dest": grab_all.default_dest(self._manager.base_dir()),
            **st,
        }

    def grab_all_start(self, url: str, limit: int = 0, media_type: str = "all",
                       date_after: str = "", date_before: str = "") -> dict[str, Any]:
        import threading
        from app.core import grab_all
        u = str(url or "").strip()
        dest = grab_all.default_dest(self._manager.base_dir())
        res = grab_all.start(
            u,
            dest,
            int(limit or 0),
            media_type=str(media_type or "all"),
            date_after=str(date_after or ""),
            date_before=str(date_before or ""),
        )
        if not res.get("ok"):
            return res
        proc = res.pop("proc")
        cookie_file = str(res.pop("cookie_file", "") or "")
        state: dict[str, Any] = {"running": True, "rc": None, "files_count": 0, "tail": [], "last_url": u}
        self._grab_state = state

        def _wait():
            out_lines: list[str] = []
            try:
                if proc.stdout:
                    for raw in proc.stdout:
                        ln = raw.strip()
                        if not ln:
                            continue
                        out_lines.append(ln)
                        if not ln.startswith(("[", "#")):
                            state["files_count"] = int(state.get("files_count") or 0) + 1
                        state["tail"] = out_lines[-6:]
                rc = proc.wait()
                state["running"] = False
                state["rc"] = rc
                if rc == 0 and self._manager.settings.get("chain_grab_ghost"):
                    from app.core import ghost
                    ghost.process_folder(dest)
                self._manager.events.emit("ui.warn" if rc else "ui.toast", kind="grab_all",
                                          name=f"Grab-All {'hata' if rc else 'tamamlandı'} ({state['files_count']} dosya): {dest}")
            except Exception:
                state["running"] = False
            finally:
                if cookie_file:
                    try:
                        os.remove(cookie_file)
                    except OSError:
                        pass

        threading.Thread(target=_wait, daemon=True).start()
        return res

    # ---------- Faz 3: Kami Hardsub, Kami Ghost ----------
    def hardsub_extract(self, path: str, lang: str = "", burn: bool = False) -> dict[str, Any]:
        from app.core import hardsub
        return hardsub.extract_and_translate(str(path or "").strip(), lang=str(lang or ""), burn=bool(burn))

    def ghost_process(self, path: str, shield: bool = False) -> dict[str, Any]:
        from app.core import ghost
        return ghost.process(str(path or "").strip(), shield=bool(shield))

    # ---------- Faz 4: Kami Beat, Kami Hunter, Kami Mod, Mobil Kopru ----------
    def beat_analyze(self, path: str) -> dict[str, Any]:
        from app.core import kami_beat
        bpm = kami_beat.analyze_bpm(str(path or "").strip())
        return {"ok": bpm > 0, "bpm": bpm}

    def beat_mashup(self, vocal: str, beat: str, vocal_bpm: float = 0.0, beat_bpm: float = 0.0,
                    pitch_semi: float = 0.0, vocal_offset: float = 0.0) -> dict[str, Any]:
        from app.core import kami_beat
        return kami_beat.mashup(str(vocal or "").strip(), str(beat or "").strip(),
                                vocal_bpm=float(vocal_bpm or 0), beat_bpm=float(beat_bpm or 0),
                                pitch_semi=float(pitch_semi or 0), vocal_offset=float(vocal_offset or 0))

    def hunter_search(self, query: str, site: str = "") -> dict[str, Any]:
        from app.core import kami_hunter
        return kami_hunter.search(str(query or "").strip(), site=str(site or "").strip())

    def mod_list(self) -> list[dict[str, Any]]:
        from app.core import kami_mod
        return kami_mod.list_mods()

    def mod_install(self, archive: str, game_dir: str) -> dict[str, Any]:
        from app.core import kami_mod
        return kami_mod.install_mod(str(archive or "").strip(), str(game_dir or "").strip())

    def mod_rollback(self, mod_id: str) -> dict[str, Any]:
        from app.core import kami_mod
        return kami_mod.rollback_mod(str(mod_id or "").strip())

    def phone_bridge_url(self) -> dict[str, Any]:
        from app.core.phone import lan_ip
        from app.core import room as _room
        port = int(self._manager.settings.get("phone_port") or 47322)
        key = self._phone_key.load() if self._phone_key else ""
        local_url = f"http://{lan_ip()}:{port}/bridge" + (f"?k={key}" if key else "")
        tunnel_url = ""
        if _room.SERVER.tunnel_url and _room.SERVER.room:
            base_t = _room.SERVER.tunnel_url.rstrip("/")
            tunnel_url = f"{base_t}/{_room.SERVER.room.id}/bridge" + (f"?k={key}" if key else "")
        return {"ok": True, "url": local_url, "tunnel_url": tunnel_url, "key": key}

    # ---------- Faz 5: Is Merkezi, Zincirler, Ekstra Araclar ----------
    def jobs_list(self) -> list[dict[str, Any]]:
        from app.core.jobs import jobs
        return jobs.list()

    def job_poll(self, job_id: str) -> dict[str, Any]:
        from app.core.jobs import jobs
        return jobs.get(str(job_id or "")) or {"ok": False, "error": "İş bulunamadı"}

    def job_cancel(self, job_id: str) -> dict[str, Any]:
        from app.core.jobs import jobs
        return {"ok": jobs.cancel(str(job_id or ""))}

    def hardsub_start(self, path: str, lang: str = "", burn: bool = False,
                      top_pct: float = 0.76, height_pct: float = 0.24,
                      color_filter: str = "both", use_nllb: bool = False,
                      mask_mode: str = "delogo") -> dict[str, Any]:
        from app.core import hardsub
        from app.core.jobs import jobs
        jid = jobs.start(
            "hardsub", f"Hardsub: {os.path.basename(path)}",
            lambda ctx: hardsub.extract_and_translate(
                str(path or "").strip(), lang=str(lang or ""), burn=bool(burn),
                top_pct=float(top_pct), height_pct=float(height_pct),
                color_filter=str(color_filter or "both"), use_nllb=bool(use_nllb),
                mask_mode=str(mask_mode or "delogo"), ctx=ctx,
            ),
        )
        return {"ok": True, "job_id": jid}

    def ghost_inspect(self, path: str) -> dict[str, Any]:
        from app.core import ghost
        return ghost.inspect_metadata(str(path or "").strip())

    def ghost_folder_start(self, folder: str, shield: bool = False) -> dict[str, Any]:
        from app.core import ghost
        from app.core.jobs import jobs
        jid = jobs.start(
            "ghost", f"Ghost Klasör: {os.path.basename(folder)}",
            lambda ctx: ghost.process_folder(str(folder or "").strip(), shield=bool(shield), ctx=ctx),
        )
        return {"ok": True, "job_id": jid}

    def beat_stems(self, path: str) -> dict[str, Any]:
        from app.core import kami_beat
        from app.core.jobs import jobs
        jid = jobs.start("beat_stems", f"4-Kanal Ayır: {os.path.basename(path)}",
                         lambda _ctx: kami_beat.separate_stems(str(path or "").strip()))
        return {"ok": True, "job_id": jid}

    def beat_key(self, path: str) -> dict[str, Any]:
        from app.core import kami_beat
        return {"ok": True, **kami_beat.detect_key(str(path or "").strip())}

    def beat_mashup_start(self, vocal: str, beat: str, vocal_bpm: float = 0.0, beat_bpm: float = 0.0,
                          pitch_semi: float = 0.0, vocal_offset: float = 0.0,
                          auto_uvr: bool = False, matchering_ref: str = "") -> dict[str, Any]:
        from app.core import kami_beat
        from app.core.jobs import jobs
        jid = jobs.start(
            "beat_mashup", f"Kami Beat: {os.path.basename(vocal)}",
            lambda ctx: kami_beat.mashup(
                str(vocal or "").strip(), str(beat or "").strip(),
                vocal_bpm=float(vocal_bpm or 0), beat_bpm=float(beat_bpm or 0),
                pitch_semi=float(pitch_semi or 0), vocal_offset=float(vocal_offset or 0),
                auto_uvr=bool(auto_uvr), matchering_ref=str(matchering_ref or "").strip(), ctx=ctx,
            ),
        )
        return {"ok": True, "job_id": jid}

    def mod_steam_games(self) -> list[dict[str, str]]:
        from app.core import kami_mod
        return kami_mod.find_steam_games()

    def hunter_preview(self, url: str) -> dict[str, Any]:
        from app.core import kami_hunter
        return kami_hunter.preview_url(str(url or "").strip())

    def links_check(self, urls: list[str]) -> dict[str, Any]:
        from app.core import link_check
        return link_check.check_links(list(urls or []), cloud_service=getattr(self.manager, "cloud", None))

    def reader_ocr_pdf(self, path: str) -> dict[str, Any]:
        from app.core import pdf_ocr
        from app.core.jobs import jobs
        jid = jobs.start("pdf_ocr", f"PDF OCR: {os.path.basename(path)}",
                         lambda ctx: pdf_ocr.make_searchable_pdf(str(path or "").strip(), ctx=ctx))
        return {"ok": True, "job_id": jid}

    def rec_export_gif(self, path: str) -> dict[str, Any]:
        if not self.recorder:
            return {"ok": False}
        from app.core.jobs import jobs
        jid = jobs.start("rec_gif", f"GIF: {os.path.basename(path)}",
                         lambda _c: self.recorder.export_gif(str(path or "").strip()))
        return {"ok": True, "job_id": jid}

    def rec_fit_discord(self, path: str) -> dict[str, Any]:
        if not self.recorder:
            return {"ok": False}
        from app.core.jobs import jobs
        jid = jobs.start("rec_discord", f"Discord Sığdır: {os.path.basename(path)}",
                         lambda _c: self.recorder.fit_discord(str(path or "").strip()))
        return {"ok": True, "job_id": jid}

    def rec_start_region(self, x: int = 0, y: int = 0, w: int = 1280, h: int = 720, window_title: str = "") -> dict[str, Any]:
        if not self.recorder:
            return {"ok": False}
        reg = None if window_title else {"x": int(x), "y": int(y), "w": int(w), "h": int(h)}
        return self.recorder.start_record(region=reg, window_title=str(window_title or "").strip())

    def _pw_store(self):
        from app import paths
        from app.core.vault import TokenStore
        return TokenStore(paths.DATA_DIR / "archive_passwords.bin")

    def chain_get(self) -> dict[str, Any]:
        import json as _json
        s = self._manager.settings
        pw_raw = self._pw_store().load()
        try:
            pws = _json.loads(pw_raw) if pw_raw else []
        except ValueError:
            pws = []
        return {
            "chain_grab_ghost": bool(s.get("chain_grab_ghost")),
            "chain_rec_studio": bool(s.get("chain_rec_studio")),
            "rec_replay_seconds": int(s.get("rec_replay_seconds") or 30),
            "archive_passwords": pws if isinstance(pws, list) else [],
            "grab_follow_profiles": list(s.get("grab_follow_profiles") or []),
        }

    def chain_set(self, key: str, val: Any) -> dict[str, Any]:
        import json as _json
        if key == "archive_passwords":
            clean = [str(x).strip() for x in (val or []) if str(x).strip()]
            self._pw_store().save(_json.dumps(clean, ensure_ascii=False))
            return {"ok": True}
        allowed = {"chain_grab_ghost", "chain_rec_studio", "rec_replay_seconds", "grab_follow_profiles"}
        if key not in allowed:
            return {"ok": False, "error": "Geçersiz ayar"}
        self._manager.settings.set(key, val)
        return {"ok": True}

    # ---------- Faz 7: Izolasyon, VRAM Guard, Profiller, Mini-Ada ----------

    def _profile_store(self):
        if self._profiles is None:
            from app.core.profiles import ProfileStore
            self._profiles = ProfileStore(settings=self._manager.settings)
        return self._profiles

    def isolation_info(self) -> dict[str, Any]:
        if self._ui_iso is None:
            return {"running": False, "port": 0, "origin": "", "probe_url": "", "coop": "same-origin", "coep": "credentialless"}
        return self._ui_iso.info()

    def vram_status(self) -> dict[str, Any]:
        from app.core.vram_guard import snapshot
        return snapshot()

    def vram_preflight(self, required_mb: int = 1024) -> dict[str, Any]:
        from app.core.vram_guard import preflight
        return preflight(required_mb=required_mb)

    def profiles_list(self) -> dict[str, Any]:
        store = self._profile_store()
        return {
            "active": store.active_id(),
            "profiles": store.list_profiles(),
            "download_dir": str(store.effective_download_dir()),
        }

    def profile_switch(self, profile_id: str) -> dict[str, Any]:
        store = self._profile_store()
        try:
            prof = store.switch_profile(profile_id)
            return {"ok": True, "profile": prof, "download_dir": str(store.effective_download_dir())}
        except KeyError as exc:
            return {"ok": False, "error": str(exc)}

    def profile_create(self, name: str, accent_theme: str = "mor", download_subfolder: str | None = None) -> dict[str, Any]:
        store = self._profile_store()
        try:
            prof = store.create_profile(name, accent_theme=accent_theme, download_subfolder=download_subfolder)
            return {"ok": True, "profile": prof}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    def profile_delete(self, profile_id: str) -> dict[str, Any]:
        ok = self._profile_store().delete_profile(profile_id)
        return {"ok": ok}

    def mini_island_state(self) -> dict[str, Any]:
        from app.core.vram_guard import snapshot
        card = self.card_state()
        return {
            "speed": card.get("speed", 0),
            "active": card.get("n", 0),
            "telemetry": snapshot(),
            "profile": self._profile_store().active_profile(),
            "visible": bool(self._island_shown),
        }

    def mini_island_toggle(self, show: bool | None = None) -> dict[str, Any]:
        target = (not self._island_shown) if show is None else bool(show)
        if target:
            if self._island_win is None and self._island_factory is not None:
                self._island_win = self._island_factory()
            if self._island_win is not None:
                try:
                    self._island_win.show()
                except Exception:
                    log.debug("mini_island show", exc_info=True)
            self._island_shown = True
        else:
            if self._island_win is not None:
                try:
                    self._island_win.hide()
                except Exception:
                    log.debug("mini_island hide", exc_info=True)
            self._island_shown = False
        self._manager.settings.set("mini_island", self._island_shown)
        return {"ok": True, "visible": self._island_shown}
