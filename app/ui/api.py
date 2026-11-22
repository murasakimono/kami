"""Python <-> JS koprusu. JS tarafinda pywebview.api.<metot> olarak cagrilir."""
from __future__ import annotations

import itertools
import json
import re
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app import paths
from app.core.manager import CaptureRejected, PageLinkRejected
from app.core.watchdog import log_slow_calls
from app.core.models import DownloadRequest, Status
from app.ui.api_enhance import EnhanceMixin
from app.ui.api_studio import STUDIO_JOBS, StudioMixin

if TYPE_CHECKING:
    from app.core.manager import DownloadManager
    from app.core.plugin_api import PluginRegistry
    from app.engines.aria2_engine import Aria2Engine

log = logging.getLogger(__name__)


@log_slow_calls
class Api(StudioMixin, EnhanceMixin):
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
        self._lrc_cancels: dict[str, threading.Event] = {}   # .lrc isleri için iptal olayları (music_lrc_cancel)
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
        self._queues = None
        self._rss = None
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
        self._island_auto = False                        # ada Kamify icin otomatik mi acildi
        self._island_factory = None
        self._warns: list[dict[str, Any]] = []
        self._probe_rules: dict[str, dict[str, Any]] = {}   # url -> eslesen kural (secim penceresi icin)
        self._manual_speed_profile = str(manager.settings.get("speed_profile") or "full")
        self._auto_speed_reason = ""
        self._island_drop_files: list[str] = []
        self._island_sp_t = 0.0
        self._island_lyric_cache: tuple[str, str, list[dict[str, Any]]] = ("", "", [])
        self._thumb_playing: bool | None = None
        manager.events.on("ui.warn", lambda **kw: self._on_warn(kw))
        manager.events.on("download.completed", lambda download=None, **_: self._on_notify_dl("completed", "İndirme tamamlandı", download))
        manager.events.on("download.failed", lambda download=None, **_: self._on_notify_dl("error", "İndirme başarısız", download))

    # ---------- arka plan isleri ----------
    # Ag/uzun isler arayuzu bekletmesin: job_start hemen is kimligi doner, arayuz job_result ile sorar.
    JOB_METHODS = frozenset({
        "add_url", "pic_ai", "pic_freq_sep", "pic_seam_carve", "pic_clone_lut", "pic_hdr_merge",
        "pic_focus_stack", "pic_ecom_pack", "pic_mockup", "pic_watermark_embed",
        "editor_vectorize", "editor_gif", "room_open", "room_relink", "editor_export", "editor_project_save", "room_turn_set", "reader_open", "reader_page", "reader_thumb", "reader_search", "reader_speak", "reader_text", "rec_save_replay", "rec_toggle", "rec_replay", "media_probe", "cloud_list", "add_cloud", "rd_add", "torrent_choose", "torrent_open",
        "torrent_source", "rd_lists", "rd_status", "rd_set_token", "rd_queue_torrent", "rd_queue_download",
        "rd_delete", "check_update", "install_update", "hash_file", "make_report", "firewall_allow",
        "backup_export", "backup_import",
        "media_lyrics", "media_archive", "genius_set_token", "follow_add", "follow_check_now", "reader_series_add", "reader_series_check", "reader_epub_font", "lens_price", "lens_text", "lens_table", "lens_codes", "rss_add", "rss_check", "rss_preview", "subtitle_translate", "subtitle_sync", "player_open_url",
        "library_get", "library_albums", "lyrics_search", "song_identify", "subtitle_fetch", "subtitle_search", "image_data", "library_organize", "player_skips", "library_posters", "library_meta", "tmdb_set_key", "iptv_load", "iptv_epg", "cast_devices", "cast_play", "cast_control", "media_extract_audio", "media_clip", "media_repair", "ocr_image", "ocr_translate", "player_lyrics",
        "batch_from_page", "batch_add", "phone_test", "ntfy_test", "ntfy_set_topic",
        "music_whisper_lrc", "music_lrc_polish_ollama", "cleaner_dust", "cleaner_janitor", "games_scan_folder", "scrobbler_recognize_now",
        # Denetim 2.3.5: arayüze bağlanan yavaş araçlar (ffmpeg/ağ) — job_start ile arka planda çalışmalı
        "audio_fx_apply", "audio_to_midi", "tts_speak", "beat_analyze", "beat_grid", "player_detect_scenes",
        "crawler_crawl", "web_archive_save", "library_find_duplicates", "library_scan_health", "library_smart_compress",
        "subtitle_batch", "clip_factory_highlights", "hardsub_extract", "kamipack_export", "kamipack_import",
        "kasa_index_media", "lyrics_word_sync",
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

    def ui_error(self, page: str, msg: str, src: str = "", stack: str = "") -> bool:
        """kami-guard.js: arayuzdeki JS hatasi -> kami.log (Kami Doktor son hatalari buradan gosterir)."""
        import collections
        import time as _t
        page, msg, src, stack = str(page)[:30], str(msg)[:500], str(src)[:300], str(stack)[:1500]
        if not hasattr(self, "_ui_errors"):
            self._ui_errors = collections.deque(maxlen=50)
        self._ui_errors.append({"t": int(_t.time()), "page": page, "msg": msg, "src": src})
        log.warning("Arayuz hatasi [%s] %s @ %s%s", page, msg, src, ("\n" + stack) if stack else "")
        return True

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
        pub_items = []
        for d in items:
            pub = self._public(d)
            if pub.get("status") in ("active", "waiting", "paused"):
                bp, np = self._manager.live_pieces(d.id)
                if bp:
                    pub["bitfield"] = bp
                    pub["num_pieces"] = np
            pub_items.append(pub)
        notifs = getattr(self._manager.events, "notifications", None)
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
            "items": pub_items,
            "total_speed": self._manager.total_speed(),
            "engine_ok": self._engine.running,
            "bridge_port": self._bridge_port(),
            "speed_profile": str(self._manager.settings.get("speed_profile") or "full"),
            "speed_profile_auto": getattr(self, "_auto_speed_reason", ""),
            "notif_unread": notifs.unread_count() if notifs else 0,
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

        def shelf(text: str) -> None:   # Pano rafi: kopyalanan metin/link (ayar pano_shelf_record, varsayilan acik)
            if not self._manager.settings.get("pano_shelf_record", True):
                return
            from app.core.clipboard import first_url
            from app.core.pano_tools import add_shelf_item
            t = text.strip()
            u = first_url(t)
            add_shelf_item("url" if u and len(t) <= len(u) + 2 else "text", t)

        self._clip_watcher = ClipboardWatcher(
            self.link_supported, offer, lambda: bool(self._manager.settings.get("clipboard_watch")), on_text=shelf)

        def _skip_excluded() -> bool:
            try:
                excl = [str(x).strip().lower() for x in (self._manager.settings.get("pano_exclude_apps") or []) if str(x).strip()]
                if not excl:
                    return False
                from app.core.winwin import foreground_process_name
                fg = foreground_process_name()
                return bool(fg and fg in excl)
            except Exception:
                return False

        self._clip_watcher.should_ignore = _skip_excluded
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
        # Kami 2.0 C10: DeArrow (Clickbait Baslik & Kapak Duzeltici) aciksa YouTube basligini temizle
        if self._manager.settings.get("media_dearrow", False):
            try:
                from app.core import mediatools as mt
                vid = mt.youtube_id(url, {"purl": url})
                if vid:
                    da = mt.dearrow_info(vid, self._mt_cache())
                    if da.get("ok") and da.get("title"):
                        info["original_title"] = info.get("title", "")
                        info["title"] = da["title"]
                        info["dearrow"] = True
            except Exception:
                pass
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
            if (d.extra or {}).get("qhold"):   # adli kuyrugun bekleyeni: kuyruk kendisi baslatir
                continue
            self._manager.resume(d.id)

    def perf_stats(self) -> dict[str, Any]:
        from app.core import perfmon
        try:
            return {"ok": True, **perfmon.snapshot(self._manager.total_speed())}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:120]}

    # ---------- v1.30 Ctrl+K her seyi arar ----------
    def global_search(self, q: str, limit: int = 40) -> list[dict[str, Any]]:
        """Indirmeler (liste + gecmis), Reader kitapligi/seriler, Studio projeleri, kuyruklar/RSS, Kasa (anlamsal, varsa).
        Her sonuc: {kind, t, sub, path|url|id}. Arayuz 'kind'e gore acar."""
        q = str(q or "").strip()
        if len(q) < 2:
            return []
        ql = q.lower()
        out: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add(kind: str, t: str, sub: str = "", **kw: Any) -> None:
            key = kind + "|" + (kw.get("path") or kw.get("url") or str(kw.get("id", "")) or t)
            if key not in seen and len(out) < limit:
                seen.add(key)
                out.append({"kind": kind, "t": t, "sub": sub, **kw})

        try:
            for d in self._manager.store.list():
                nm = d.filename or d.url
                if ql in nm.lower() or ql in (d.url or "").lower():
                    add("download", nm, str(getattr(d.status, "value", d.status)), id=d.id, path=d.path if str(d.status) == "complete" or getattr(d.status, "value", "") == "complete" else "")
        except Exception:
            log.debug("ara: indirmeler")
        if getattr(self, "_history", None):
            try:
                for h in self._history.search(q, 30):
                    if h.get("exists"):
                        add("file", h.get("filename") or os.path.basename(h.get("path") or ""), "geçmiş · " + (h.get("category") or ""), path=h["path"])
            except Exception:
                log.debug("ara: gecmis")
        try:
            from app.core import reader
            for b in reader.recent(200):
                if ql in (b.get("title") or "").lower() or ql in b["path"].lower():
                    add("book", b.get("title") or os.path.basename(b["path"]), f"Reader · {b.get('page', 0) + 1}/{b.get('count', 0)}", path=b["path"])
            for s in reader.series_list():
                if ql in (s.get("title") or "").lower():
                    add("series", s["title"], f"seri · {len(s.get('new') or [])} yeni", id=s["id"])
        except Exception:
            log.debug("ara: reader")
        try:
            for pr in self.studio_recent():
                nm = pr.get("name") or os.path.basename(pr.get("path", ""))
                if ql in nm.lower():
                    add("studio", nm, "Studio projesi", path=pr["path"])
        except Exception:
            log.debug("ara: studio")
        try:
            for f in (self._rss.public() if getattr(self, "_rss", None) else []):
                if ql in (f.get("title") or "").lower():
                    add("rss", f["title"], "RSS akışı", id=f["id"])
        except Exception:
            log.debug("ara: rss")
        # Kami 2.0 D15 Omnisearch: Reader PDF Vurgulari & Notlari, Pano OCR/Metin Rafi ve Whisper/LRC Dosyalari
        try:
            from app import paths
            from app.core import reader
            if reader.ROOT.exists():
                for rf in list(reader.ROOT.glob("*.json"))[:60]:
                    try:
                        rd = json.loads(rf.read_text(encoding="utf-8"))
                        if not isinstance(rd, dict) or not rd.get("path"):
                            continue
                        btitle = rd.get("title") or os.path.basename(rd["path"])
                        for hl in (rd.get("hl") or []):
                            txt = str((hl or {}).get("text") or "") + " " + str((hl or {}).get("note") or "")
                            if ql in txt.lower():
                                pg = int((hl or {}).get("page") or 0)
                                add("book", f"{btitle} (S.{pg + 1})", f"PDF Vurgu: {txt.strip()[:70]}", path=rd["path"], page=pg)
                                break
                    except Exception:
                        pass
            from app.core import pano_tools
            for pit in (pano_tools.list_shelf() or [])[:50]:
                ptxt = str(pit.get("text") or pit.get("ocr") or "")
                if ql in ptxt.lower():
                    add("file", ptxt.strip()[:60], "Kami Pano Rafı", path=pit.get("path") or "")
            # Indirilenlerin yanindaki .srt ve .lrc dosyalari icinde ara
            for d in self._manager.store.list()[:60]:
                if not d.path or not os.path.isfile(d.path):
                    continue
                base = os.path.splitext(d.path)[0]
                for side_ext, lbl in ((".lrc", "Şarkı Sözü (.lrc)"), (".srt", "Whisper Altyazı (.srt)"), (".tr.srt", "Whisper TR (.srt)")):
                    sp = base + side_ext
                    if os.path.isfile(sp):
                        try:
                            with open(sp, encoding="utf-8", errors="replace") as _sf:
                                raw_side = _sf.read(32768)
                            idx_hit = raw_side.lower().find(ql)
                            if idx_hit >= 0:
                                snippet = raw_side[max(0, idx_hit - 20):idx_hit + 55].replace("\n", " ").strip()
                                add("file", d.filename or os.path.basename(d.path), f"{lbl}: {snippet}", path=d.path)
                                break
                        except OSError:
                            pass
        except Exception:
            log.debug("ara: omnisearch")
        return out

    def global_open(self, item: dict) -> dict[str, Any]:
        k, path = str(item.get("kind") or ""), str(item.get("path") or "")
        if k in ("file", "download") and path and os.path.exists(path):
            ext = os.path.splitext(path)[1].lower()
            from app.core.reader import READ_EXT
            if ext in READ_EXT:
                return self.reader_show(path)
            if ext in (".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".mp3", ".m4a", ".flac", ".wav", ".ogg", ".opus"):
                return self.player_show({"path": path})
            if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif", ".heic"):
                return self.picture_open(path)
            return {"ok": bool(self.open_path(path))}
        if k == "book" and path:
            return self.reader_show(path)
        if k == "studio" and path:
            return self.studio_show(path)
        if k == "series":
            return self.reader_show()
        return {"ok": False}

    # ---------- v1.29 RSS otomatik indirme ----------
    def _rss_add(self, it: dict, feed: dict) -> bool:
        """RSS girdisi -> torrent (RD ayarina gore; yerelde tum dosyalar) ya da duz dosya. Sormadan."""
        from app.core.debrid import is_magnet, is_torrent_url
        link = str(it.get("dl") or "")
        qid = str(feed.get("queue") or "")
        added_ids: list[int] = []
        if is_magnet(link) or is_torrent_url(link):
            if self._torrent_route() == "rd":
                r = self.rd_add(link)
                return bool(r.get("ok"))
            svc = self._manager.torrents
            if is_magnet(link):
                token, meta = svc.from_magnet(link, timeout=120)
            else:
                token, meta = svc.from_bytes(self._fetch_torrent(link))
            n = len([f for f in meta.files if not f.get("pad")])
            d = self._manager.add_torrent(token, list(range(n)))
            added_ids = [d.id]
        else:
            added_ids = [d.id for d in self._manager.add(DownloadRequest(url=link, source="plugin:rss"), confirm=False)]
        q = getattr(self, "_queues", None)
        if qid and q and added_ids:
            q.assign(added_ids, qid)
        return bool(added_ids)

    def rss_list(self) -> list[dict[str, Any]]:
        return self._rss.public() if getattr(self, "_rss", None) else []

    def rss_add(self, url: str, opts: dict | None = None) -> dict[str, Any]:
        if not getattr(self, "_rss", None):
            return {"ok": False, "error": "rss_off"}
        return self._rss.add_feed(str(url), **(opts if isinstance(opts, dict) else {}))

    def rss_update(self, fid: str, opts: dict) -> dict[str, Any]:
        return {"ok": bool(getattr(self, "_rss", None) and self._rss.update(str(fid), **(opts or {}))), "feeds": self.rss_list()}

    def rss_remove(self, fid: str) -> list[dict[str, Any]]:
        if getattr(self, "_rss", None):
            self._rss.remove(str(fid))
        return self.rss_list()

    def rss_preview(self, fid: str) -> dict[str, Any]:
        try:
            return {"ok": True, "items": self._rss.preview(str(fid))}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:160]}

    def rss_check(self, fid: str = "") -> dict[str, Any]:
        if not getattr(self, "_rss", None):
            return {"ok": False}
        return {"ok": True, "new": self._rss.check(str(fid) or None, force=True), "feeds": self.rss_list()}

    # ---------- v1.29 coklu kuyruk ----------
    def queue_list(self) -> list[dict[str, Any]]:
        q = getattr(self, "_queues", None)
        return q.summary() if q else []

    def queue_save(self, qs: list) -> list[dict[str, Any]]:
        from app.core import queues
        old = {x["id"]: x for x in queues.load()}
        keep = [x for x in (qs or []) if isinstance(x, dict)]
        for x in keep:   # 'running' arayuzden gelmez, korunur
            if x.get("id") in old:
                x["running"] = old[x["id"]]["running"]
        out = queues.save(keep)
        gone = set(old) - {x["id"] for x in out}
        if gone and getattr(self, "_queues", None):   # silinen kuyrugun isleri ana kuyruga doner
            for g in gone:
                self._queues.assign([d.id for d in self._queues.members(g)], queues.MAIN)
        return self.queue_list()

    def queue_assign(self, ids: list, qid: str) -> dict[str, Any]:
        q = getattr(self, "_queues", None)
        if not q:
            return {"ok": False}
        return {"ok": True, "n": q.assign([int(i) for i in ids or []], str(qid))}

    def queue_run(self, qid: str, on: bool) -> dict[str, Any]:
        q = getattr(self, "_queues", None)
        return {"ok": bool(q and q.set_running(str(qid), bool(on))), "queues": self.queue_list()}

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

    def item_peek(self, item_id: int) -> dict[str, Any]:
        """v1.32.1 Sunak kart onizlemesi: medya ozeti (+ video icin kucuk kare). Sonuc dosya+mtime ile onbellekli."""
        import base64
        d = next((x for x in self._manager.snapshot() if x.id == int(item_id)), None)
        if d is None or d.status != "complete" or d.category not in ("video", "music"):
            return {}
        p = d.path
        try:
            key = (p, os.path.getmtime(p))
        except OSError:
            return {}
        cache = self.__dict__.setdefault("_peek_cache", {})
        if key in cache:
            return cache[key]
        from app.core.media_server import find_ffprobe, probe
        from app.engines.ytdlp_engine import find_ffmpeg
        ff = find_ffmpeg() or ""
        info = probe(find_ffprobe(ff) if ff else "", p)
        out: dict[str, Any] = {"duration": info.get("duration", 0), "w": info.get("width", 0), "h": info.get("height", 0),
                               "vcodec": info.get("vcodec", ""), "acodec": (info.get("audio") or [{}])[0].get("codec", "")}
        if d.category == "video" and ff:
            try:
                t = max(1.0, float(out["duration"] or 0) * 0.2)
                r = subprocess.run([ff, "-v", "error", "-ss", f"{t:.1f}", "-i", p, "-frames:v", "1", "-vf", "scale=320:-2",
                                    "-q:v", "6", "-f", "image2pipe", "-vcodec", "mjpeg", "-"],
                                   capture_output=True, timeout=12, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if r.stdout:
                    out["thumb"] = "data:image/jpeg;base64," + base64.b64encode(r.stdout).decode()
            except (OSError, subprocess.SubprocessError):
                pass
        if len(cache) > 80:
            cache.clear()
        cache[key] = out
        return out

    def audio_peaks(self, path: str, n: int = 600) -> dict[str, Any]:
        """v1.32.1 Player muzik modu: gercek dalga formu (0..1 tepe dizisi). ffmpeg 8 kHz mono; dosya+mtime onbellekli."""
        import array
        p = str(path or "")
        try:
            key = (p, os.path.getmtime(p), int(n))
        except OSError:
            return {"ok": False}
        cache = self.__dict__.setdefault("_peaks_cache", {})
        if key in cache:
            return cache[key]
        from app.engines.ytdlp_engine import find_ffmpeg
        ff = find_ffmpeg()
        if not ff:
            return {"ok": False, "error": "ffmpeg"}
        try:
            r = subprocess.run([ff, "-v", "error", "-i", p, "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                               capture_output=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError):
            return {"ok": False}
        a = array.array("h"); a.frombytes(r.stdout[: len(r.stdout) // 2 * 2])
        n = max(50, min(2000, int(n)))
        if len(a) < n:
            return {"ok": False}
        step = len(a) // n
        peaks = [max(abs(min(a[i * step:(i + 1) * step])), abs(max(a[i * step:(i + 1) * step]))) for i in range(n)]
        top = max(peaks) or 1
        out = {"ok": True, "peaks": [round(x / top, 3) for x in peaks]}
        if len(cache) > 40:
            cache.clear()
        cache[key] = out
        return out

    def dash_stats(self) -> dict[str, Any]:
        """v1.32.1 Sunak gosterge paneli: disk, bugun inenler, RD (5 dk onbellekli), haftalik."""
        import shutil as _sh
        out: dict[str, Any] = {}
        try:
            u = _sh.disk_usage(self._manager.base_dir())
            out["disk_free"], out["disk_total"] = u.free, u.total
        except OSError:
            pass
        day0 = time.time() - (time.time() - time.timezone) % 86400   # yerel gun baslangici (kabaca)
        week0 = time.time() - 7 * 86400
        today = week = 0
        n_today = 0
        for it in self._manager.snapshot():
            if getattr(it, "status", "") != "complete":
                continue
            fa, size = float(getattr(it, "finished_at", 0) or 0), int(getattr(it, "size", 0) or 0)
            if fa >= week0:
                week += size
                if fa >= day0:
                    today += size
                    n_today += 1
        out.update(today=today, today_n=n_today, week=week)
        try:
            rd = self._rd.status() if self._rd is not None and self._rd.has_token() else {}
            if rd.get("ok"):
                out["rd_days"] = rd.get("premium_days", 0)
        except Exception:
            pass
        return out

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
        import requests, socket, ipaddress
        from urllib.parse import urlparse
        u = urlparse(url)
        if u.scheme not in ("http", "https") or not u.hostname:
            raise ValueError("unsupported url")
        host = u.hostname

        def _blocked(ip_str: str) -> bool:
            try:
                a = ipaddress.ip_address(ip_str)
            except ValueError:
                return False
            return (a.is_private or a.is_loopback or a.is_link_local or a.is_reserved
                    or a.is_multicast or a.is_unspecified)

        if _blocked(host):
            raise ValueError("blocked host")
        try:
            for info in socket.getaddrinfo(host, None):
                if _blocked(info[4][0]):
                    raise ValueError("blocked host")
        except socket.gaierror:
            pass
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

    def provenance_read(self, download_id: int) -> dict[str, Any]:
        """Dosyanin kaynak kaydini (sidecar) okur; yoksa bos doner."""
        from app.core import provenance
        d = self._manager.store.get(int(download_id))
        if not d or not d.path:
            return {"ok": False, "error": "no_file"}
        rec = provenance.read(d.path)
        return {"ok": True, "provenance": rec} if rec else {"ok": False, "provenance": None}

    def oplog_list(self, n: int = 20) -> dict[str, Any]:
        """Kami Echo: son geri alınabilir işlemler."""
        oplog = getattr(self._manager, "oplog", None)
        return {"ok": True, "items": oplog.list(int(n or 20)) if oplog else []}

    def oplog_undo(self, eid: str) -> dict[str, Any]:
        """Kami Echo: kayıtlı bir işlemi geri al."""
        oplog = getattr(self._manager, "oplog", None)
        if not oplog:
            return {"ok": False, "error": "no_oplog"}
        return oplog.undo(str(eid))

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
        if getattr(self._manager, "oplog", None):
            try:
                self._manager.oplog.record("rename", old, new)
            except Exception:
                pass
        nd = self._manager.store.update(d.id, filename=name)
        self._manager.events.emit("download.updated", download=nd)
        return {"ok": True, "path": new}

    def batch_rename(self, pairs: list[dict]) -> dict[str, Any]:
        """Toplu yeniden adlandirma: [{path, new_name}] — her biri geri alinabilir (oplog). Uzanti korunur."""
        done = []
        errors = []
        oplog = getattr(self._manager, "oplog", None)
        for it in pairs or []:
            src = str((it or {}).get("path") or "").strip()
            nn = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str((it or {}).get("new_name") or "")).strip().rstrip(". ")
            if not src or not nn or not os.path.isfile(src):
                errors.append({"path": src, "error": "invalid"})
                continue
            ext = os.path.splitext(src)[1]
            if ext and not nn.lower().endswith(ext.lower()):
                nn += ext
            dst = os.path.join(os.path.dirname(src), nn)
            if os.path.normcase(dst) == os.path.normcase(src):
                continue
            if os.path.exists(dst):
                errors.append({"path": src, "error": "exists"});
                continue
            try:
                os.rename(src, dst)
            except OSError as exc:
                errors.append({"path": src, "error": str(exc)[:120]});
                continue
            if oplog:
                try:
                    oplog.record("rename", src, dst)
                except Exception:
                    pass
            done.append({"path": dst, "old": src})
        return {"ok": True, "done": done, "errors": errors}

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
        ch = str(self._manager.settings.get("update_channel") or "stable")
        res = extras.check_update(channel=ch)
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
        ch = str(self._manager.settings.get("update_channel") or "stable")
        info = self._update_info or extras.check_update(channel=ch)
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

    def backup_export(self, dest_path: str = "") -> dict[str, Any]:
        from app.core import backup
        p = str(dest_path or "").strip()
        if not p and self._window is not None:
            import time as _t
            import webview
            picked = self._window.create_file_dialog(
                webview.SAVE_DIALOG,
                save_filename=f"kami_backup_{_t.strftime('%Y%m%d_%H%M%S')}.kamibak",
                file_types=("Kami Yedek (*.kamibak)",),
            )
            if not picked:
                return {"ok": False, "cancelled": True}
            p = picked[0] if isinstance(picked, (list, tuple)) else str(picked)
        ls_data = None
        if self._window is not None:
            try:
                ls_data = self._window.evaluate_js("JSON.stringify(localStorage)")
            except Exception:
                ls_data = None
        res = backup.create_backup(p or None, local_storage=ls_data)
        if res.get("ok") and not dest_path:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(res["path"])])
        return res

    def backup_import(self, src_path: str = "") -> dict[str, Any]:
        from app.core import backup
        p = str(src_path or "").strip()
        if not p and self._window is not None:
            import webview
            picked = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=("Kami Yedek (*.kamibak)",),
            )
            if not picked:
                return {"ok": False, "cancelled": True}
            p = picked[0] if isinstance(picked, (list, tuple)) else str(picked)
        return backup.stage_restore(p)

    def consume_pending_localstorage(self) -> dict[str, Any]:
        from app import paths
        p = paths.DATA_DIR / "pending_localstorage.json"
        if not p.is_file():
            return {}
        try:
            data = json.loads(p.read_text("utf-8"))
        except Exception:
            data = {}
        try:
            p.unlink()
        except OSError:
            pass
        return data if isinstance(data, dict) else {}

    # ---------- Kami Doktor ----------
    def ping(self) -> dict[str, Any]:
        from app.core.extras import APP_VERSION
        return {"ok": True, "version": APP_VERSION}

    def is_selftest(self) -> bool:
        return False

    def taskbar_progress(self, pct: int = 0, state: str = "none") -> bool:
        try:
            import ctypes
            from app.core import taskbar
            hwnd = ctypes.windll.user32.FindWindowW(None, "Kami") if os.name == "nt" else 0
            return taskbar.set_progress(int(hwnd or 0), int(pct), str(state or "none"))
        except Exception:
            return False

    def doctor_run(self) -> dict[str, Any]:
        from app.core import doctor
        wd = getattr(self, "_watchdog", None)
        return doctor.run_all(self._engine, list(getattr(self, "_ui_errors", []) or []),
                              getattr(wd, "recoveries", 0), self._manager.base_dir(),
                              media=getattr(self, "_media", None),
                              bridge=getattr(self, "_bridge", None),
                              api=self)

    def doctor_fix(self, fix_id: str) -> dict[str, Any]:
        from app.core import doctor
        fix_id = str(fix_id or "")
        if fix_id == "restart_aria2":
            self._engine.start_service(timeout=8.0)
            return {"ok": bool(self._engine.running)}
        if fix_id == "room_relink":
            return {"ok": True, **self.room_relink()}
        if fix_id == "open_wv2":
            os.startfile("https://developer.microsoft.com/microsoft-edge/webview2/")  # type: ignore[attr-defined]
            return {"ok": True}
        if fix_id == "report":
            return self.make_report()
        fn = doctor.FIXES.get(fix_id)
        if not fn:
            return {"ok": False, "error": "unknown_fix"}
        try:
            return fn()
        except Exception as exc:
            log.exception("Doktor onarimi basarisiz: %s", fix_id)
            return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:160]}"}

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
        if key == "speed_profile":
            return self.speed_profile_set(str(value or "full"), auto=False)
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

    def choose_files(self, exts: list[str] | None = None) -> list[str]:
        """Coklu dosya secici (Toplu Adlandir / Etiket Editörü)."""
        if not self._window:
            return []
        import webview
        dialog = getattr(getattr(webview, "FileDialog", None), "OPEN", None) or webview.OPEN_DIALOG
        ft = ()
        if exts:
            ft = ("Dosyalar (" + ";".join("*" + e for e in exts) + ")",)
        res = self._window.create_file_dialog(dialog, allow_multiple=True, file_types=ft)
        return list(res) if res else []

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

    def anki_add(self, front: str, back: str, deck: str = "Kami") -> dict[str, Any]:
        """Fikir 7 (Anki Koprusu): Reader'dan secilen metni Anki karti olarak CSV'ye kaydet (Anki'ye import edilebilir)."""
        import csv
        p = paths.DATA_DIR / "anki_export.csv"
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            new = not p.is_file()
            with open(p, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(["Deck", "Front", "Back"])
                w.writerow([str(deck or "Kami"), str(front or ""), str(back or "")])
            return {"ok": True, "path": str(p)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:120]}

    def scene_search(self, image_path: str, folder: str = "") -> dict[str, Any]:
        """Fikir 10 (Sahne Arama): bir kareden hangi video + dakika oldugunu bul (algisal aHash)."""
        from PIL import Image
        from app.engines.ytdlp_engine import find_ffmpeg as _ffmpeg
        p = str(image_path or "")
        if not p or not os.path.isfile(p):
            return {"ok": False, "error": "no_file"}

        def _ahash(im):
            im = im.convert("L").resize((16, 16))
            px = list(im.getdata())
            avg = sum(px) / len(px)
            return "".join("1" if x > avg else "0" for x in px)

        def _dist(a, b):
            return sum(1 for x, y in zip(a, b) if x != y)

        try:
            target = _ahash(Image.open(p))
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:120]}

        ff = _ffmpeg() or ""
        if not ff:
            return {"ok": False, "error": "no_ffmpeg"}
        base = str(folder or self._manager.base_dir())
        vids = []
        for dp, _dn, fn in os.walk(base):
            for f in fn:
                if os.path.splitext(f)[1].lower() in (".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v"):
                    vids.append(os.path.join(dp, f))
            if len(vids) > 120:
                break
        import tempfile
        best = None
        for v in vids:
            try:
                with tempfile.TemporaryDirectory() as td:
                    out = os.path.join(td, "f%02d.jpg")
                    subprocess.run([ff, "-loglevel", "error", "-i", v, "-vf", "fps=1/60", "-frames:v", "8", out],
                                   capture_output=True, creationflags=0x08000000, timeout=90)
                    for i in range(8):
                        fp = os.path.join(td, f"f{i + 1:02d}.jpg")
                        if not os.path.isfile(fp):
                            continue
                        d = _dist(target, _ahash(Image.open(fp)))
                        if best is None or d < best[0]:
                            best = (d, v, (i + 1) * 60)
            except Exception:
                continue
        if best is None:
            return {"ok": True, "found": False}
        return {"ok": True, "found": True, "video": best[1], "name": os.path.basename(best[1]),
                "seconds": best[2], "dist": best[0]}

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

    def _record_portal_media(self, path: str, title: str = "") -> None:
        p = str(path or "").strip()
        if not p or not os.path.isfile(p):
            return
        ap = os.path.abspath(p)
        rec_list = getattr(self, "_recent_portal_media", None)
        if rec_list is None:
            rec_list = []
            self._recent_portal_media = rec_list
        norm = os.path.normcase(ap)
        rec_list[:] = [x for x in rec_list if os.path.normcase(str(x.get("path") or "")) != norm]
        rec_list.insert(0, {"id": None, "name": title or os.path.basename(ap), "path": ap, "pct": 0, "label": "Kami Player son oynatılan"})
        del rec_list[20:]

    def phone_recent_media(self) -> list[dict[str, Any]]:
        rec_list = getattr(self, "_recent_portal_media", [])
        return [x for x in rec_list if x.get("path") and os.path.isfile(str(x["path"]))]

    # ---------- oynatici (P1) ----------
    def player_open(self, download_id: int) -> dict[str, Any]:
        """Biten indirmeyi Kami'nin kendi oynaticisinda ac: yerel medya sunucusu adresi + mod (direct/remux/transcode)."""
        if not self._media:
            return {"ok": False, "error": "player_unavailable"}
        d = self._manager.store.get(int(download_id))
        if not d or not d.path or not os.path.isfile(d.path):
            return {"ok": False, "error": "not_found"}
        self._record_portal_media(d.path, d.filename or os.path.basename(d.path))
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
        p = str(path or "")
        self._record_portal_media(p)
        return self._media.register(p)

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

    def mix_build(self, n: int = 20) -> dict[str, Any]:
        """Kami 'For You' Radyo: scrobble geçmişinden kişisel, tekrar etmeyen kuyruk."""
        from app.core import library, mix
        dirs = self._library_dirs()
        if not dirs:
            return {"ok": False, "error": "no_library"}
        items = library.scan(dirs)["items"]
        tracks = mix.build_mix(items, history=self.scrobbler_history(200), n=int(n or 20))
        return {"ok": True, "tracks": [{"path": t["path"], "name": t["name"], "kind": t.get("kind", "")} for t in tracks]}

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
        if info.get("series"):   # kullanicinin ogrettigi intro/outro (her dizi, anime olmasa da)
            try:
                from app.core import player_plus as PP
                mine = PP.find_intro(str(p), info["series"])
                for m in mine:
                    if m.get("from_end") and duration:
                        span = m["end"] - m["start"]
                        m["start"], m["end"] = max(0.0, float(duration) - span - 2), float(duration)
                out = [o for o in out if not any(o.get("type") == m["type"] for m in mine)] + mine
            except Exception:
                log.exception("ogrenilmis intro")
        return {"ok": True, "segments": out, "series": info.get("series", ""), "episode": info.get("episode", 0)}

    # ---------- v1.28 Player+: bilgi, intro ogret, IPTV, TV'ye yayin ----------
    def _tmdb_store(self):
        from app import paths
        from app.core.debrid import TokenStore
        return TokenStore(paths.DATA_DIR / "tmdb_key.bin")

    def tmdb_set_key(self, key: str) -> dict[str, Any]:
        import re as _re
        import requests
        key = str(key or "").strip()
        if not _re.fullmatch(r"[A-Za-z0-9]{20,64}", key):
            return {"ok": False, "error": "bad_key"}
        try:
            r = requests.get("https://api.themoviedb.org/3/configuration", params={"api_key": key}, timeout=12)
        except requests.RequestException:
            return {"ok": False, "error": "network"}
        if r.status_code != 200:
            return {"ok": False, "error": "bad_key"}
        self._tmdb_store().save(key)
        return {"ok": True}

    def library_meta(self, names: list | None = None, movies: list | None = None) -> dict[str, Any]:
        """Dizi (TVmaze) ve film (TMDB, anahtar varsa) bilgisi: afis, ozet, yil, tur, puan, bolum adlari."""
        from app.core import player_plus as PP
        out: dict[str, Any] = {"series": {}, "movies": {}}
        for n in (names or [])[:60]:
            i = PP.series_info(str(n))
            if i:
                out["series"][str(n)] = {k: v for k, v in i.items() if k != "_t"}
        key = self._tmdb_store().load() if movies else ""
        for stem in (movies or [])[:60]:
            t, y = PP.guess_movie(str(stem))
            i = PP.movie_info(t, y, key) if t else None
            if i:
                out["movies"][str(stem)] = {k: v for k, v in i.items() if k != "_t"}
        out["tmdb"] = bool(key) if movies else None
        return out

    def player_intro_learn(self, path: str, start: float, end: float, kind: str = "intro") -> dict[str, Any]:
        from pathlib import Path
        from app.core import player_plus as PP
        from app.core.library import parse_name
        info = parse_name(Path(str(path)).stem)
        if not info.get("series"):
            return {"ok": False, "error": "dizi_degil"}
        return PP.learn_intro(str(path), info["series"], float(start), float(end), "outro" if kind == "outro" else "intro")

    def iptv_load(self, src: str) -> dict[str, Any]:
        from app.core import player_plus as PP
        res = PP.load_playlist(str(src))
        if res.get("ok"):
            lists = self._manager.settings.get("iptv_lists") or []
            if src not in lists:
                self._manager.settings.set("iptv_lists", ([src] + lists)[:10])
        return res

    def iptv_epg(self, url: str, ids: list | None = None) -> dict[str, Any]:
        from app.core import player_plus as PP
        return PP.load_epg(str(url), [str(x) for x in ids or []])

    def iptv_lists(self) -> list:
        return list(self._manager.settings.get("iptv_lists") or [])

    def cast_devices(self) -> dict[str, Any]:
        from app.core import player_plus as PP
        devs = PP.discover(3.0)
        self._cast_devs = {d["id"]: d for d in devs}
        return {"ok": True, "devices": [{"id": d["id"], "name": d["name"], "model": d["model"]} for d in devs]}

    def cast_play(self, dev_id: str, path: str, start: float = 0.0) -> dict[str, Any]:
        from app.core import player_plus as PP
        d = (getattr(self, "_cast_devs", {}) or {}).get(str(dev_id))
        if not d:
            return {"ok": False, "error": "cihaz_yok"}
        import os as _os
        if not _os.path.isfile(str(path)):
            return {"ok": False, "error": "yalniz_yerel_dosya"}
        self._cast_cur = d
        return PP.cast_play(d, str(path), float(start or 0))

    def cast_control(self, action: str, value: float = 0) -> dict[str, Any]:
        from app.core import player_plus as PP
        d = getattr(self, "_cast_cur", None)
        if not d:
            return {"ok": False, "error": "yayin_yok"}
        return PP.cast_control(d, str(action), float(value or 0))

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
        try:   # Fikir 13: sarki kesif notu — taninan sarkiyi zaman damgali logla
            self._discovery_add(self._last_song)
        except Exception:
            pass
        return {"ok": True, "song": self._last_song}

    def _discovery_add(self, song: dict) -> None:
        import json, time
        p = paths.DATA_DIR / "discovery_log.json"
        items = []
        try:
            if p.is_file():
                items = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            items = []
        items.insert(0, {"artist": str((song or {}).get("artist") or ""), "title": str((song or {}).get("title") or ""), "ts": int(time.time())})
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(items[:50], ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def discovery_list(self) -> dict[str, Any]:
        """Sarki kesif notlari (Fikir 13): 'Bu sarki ne?' ile taninan sarkilarin zaman damgali listesi."""
        import json
        p = paths.DATA_DIR / "discovery_log.json"
        try:
            if not p.is_file():
                return {"ok": True, "items": []}
            return {"ok": True, "items": json.loads(p.read_text(encoding="utf-8"))}
        except Exception:
            return {"ok": True, "items": []}

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
                self._lv["t0"] = time.time()

                def _ln(ln: str) -> None:
                    m = re.search(r'@hf-progress\s*(\{.*\})', ln)
                    if m:
                        try:
                            d = json.loads(m.group(1))
                        except ValueError:
                            return
                        pct = int(d.get("pct") or 0) / 100
                        t0 = self._lv.setdefault("t0", time.time())
                        el = time.time() - t0
                        eta = int(el / pct - el) if pct >= 0.05 else 0   # kalan sn (kabaca)
                        self._lv.update(p=pct, code=str(d.get("code") or ""), eta=eta)

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
        return {"ok": True, "kind": doc.kind, "count": doc.count, "title": doc.title, "path": doc.path, "ebook": bool(getattr(doc, "ebook", False)),
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

    # ---- v1.30 Reader: istatistik, seri/yeni bolum takibi, e-kitap punto
    def reader_stats(self) -> dict[str, Any]:
        from app.core import reader
        return reader.stats()

    def reader_series(self) -> list[dict[str, Any]]:
        from app.core import reader
        return reader.series_list()

    def reader_series_add(self, src: str) -> dict[str, Any]:
        from app.core import reader
        try:
            return reader.series_add(str(src or ""))
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:160]}

    def reader_series_remove(self, sid: str) -> list[dict[str, Any]]:
        from app.core import reader
        reader.series_remove(str(sid))
        return reader.series_list()

    def reader_series_seen(self, sid: str) -> bool:
        from app.core import reader
        reader.series_seen(str(sid))
        return True

    def reader_series_check(self) -> dict[str, Any]:
        from app.core import reader
        found = reader.series_check()
        self._reader_notify_new(found)
        return {"ok": True, "found": found, "series": reader.series_list()}

    def _reader_notify_new(self, found: list) -> None:
        if not found:
            return
        try:
            from app.core import desktop
            msg = "; ".join(f"{f['title']}: {len(f['new'])} yeni" for f in found[:3])
            desktop.toast("Kami Reader — yeni bölüm", msg)
        except Exception:
            log.debug("Reader bildirimi gosterilemedi")
        with self._inbox_lock:
            self._warns.append({"kind": "reader_new", "text": "Yeni bölüm: " + ", ".join(f["title"] for f in found[:3])})

    def reader_epub_font(self, size: float) -> dict[str, Any]:
        """E-kitap puntosu: belge yeniden dizilir ve yeniden acilir (sayfa yuzdesi korunur)."""
        from app.core import reader
        d = self._rdoc
        if not d or not getattr(d, "ebook", False):
            return {"ok": False}
        st = reader.load_state(d.key)
        frac = (st.get("page", 0) + 0.5) / max(1, d.count)
        st.setdefault("settings", {})["epub_font"] = max(7.0, min(24.0, float(size)))
        reader.save_state(d.key, st, d.path, d.title)
        path = d.path
        r = self.reader_open(path)
        if r.get("ok"):
            st2 = reader.load_state(self._rdoc.key)
            st2["page"] = min(r["count"] - 1, int(frac * r["count"]))
            reader.save_state(self._rdoc.key, st2, path, self._rdoc.title)
            r["state"] = st2
        return r

    def reader_pick(self, folder: bool = False) -> str:
        import webview
        w = getattr(self, "_reader_win", None) or (webview.windows[0] if webview.windows else None)
        if not w:
            return ""
        if folder:
            r = w.create_file_dialog(webview.FOLDER_DIALOG)
        else:
            r = w.create_file_dialog(webview.OPEN_DIALOG, file_types=(
                "Kitap ve çizgi roman (*.pdf;*.epub;*.mobi;*.fb2;*.azw3;*.cbz;*.cbr;*.cb7;*.zip;*.rar;*.7z)", "Tüm dosyalar (*.*)"))
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

    # ---- oda sifresi + Mini-Ada oda seridi
    def room_set_password(self, password: str = "") -> dict[str, Any]:
        """Bos: sifreyi kaldir. Sifrenin kendisi saklanmaz, sha256'si ayarlara yazilir (misafir de ayni ozeti gonderir)."""
        import hashlib
        pw = str(password or "").strip()
        if pw and len(pw) < 4:
            return {"ok": False, "error": "short"}
        self._manager.settings.set("room_password_hash", hashlib.sha256(pw.encode("utf-8")).hexdigest() if pw else "")
        return {"ok": True, "locked": bool(pw)}

    def room_key(self) -> str:
        """Yalnizca Kami pencereleri (ev sahibinin oda penceresi, Player yayini) cagirabilir: sifreyi sormadan girer."""
        return str(self._manager.settings.get("room_password_hash") or "")

    def room_island_push(self, state: dict[str, Any]) -> bool:
        """Ev sahibinin oda penceresi (room.js) -> Mini-Ada: kim var, kim konusuyor, mikrofon/kulaklik."""
        import time as _t
        st = state if isinstance(state, dict) else {}
        if st.get("left"):
            self._room_island = None
            if getattr(self, "_auto_speed_reason", "") == "room":
                self.speed_profile_set(getattr(self, "_manual_speed_profile", "full"), auto=True, reason="")
            if getattr(self, "_island_auto", False) and self._island_shown:
                self._island_auto = False
                self.mini_island_toggle(False, persist=False)
            return True
        people = [{"name": str(p.get("name", ""))[:24], "talk": bool(p.get("talk")), "muted": bool(p.get("muted")),
                   "me": bool(p.get("me"))} for p in (st.get("people") or [])[:8] if isinstance(p, dict)]
        if not people:
            self._room_island = None
            if getattr(self, "_auto_speed_reason", "") == "room":
                self.speed_profile_set(getattr(self, "_manual_speed_profile", "full"), auto=True, reason="")
            if getattr(self, "_island_auto", False) and self._island_shown:
                self._island_auto = False
                self.mini_island_toggle(False, persist=False)
            return True
        self._room_island = {"t": _t.time(), "people": people, "muted": bool(st.get("muted")), "deaf": bool(st.get("deaf"))}
        if getattr(self, "_auto_speed_reason", "") != "game":
            self.speed_profile_set("room", auto=True, reason="room")
        others = sum(1 for p in people if not p["me"])
        if self._manager.settings.get("room_island") and (others or len(people) >= 1) and not self._island_shown:
            self.mini_island_toggle(True, persist=False)   # odaya girildi: seridi kendiligimizden ac
            self._island_auto = True
        elif not people and getattr(self, "_island_auto", False) and self._island_shown:
            self._island_auto = False
            self.mini_island_toggle(False, persist=False)
        return True

    def room_island_cmd(self, cmd: str) -> bool:
        c = "mute" if cmd == "mic" else str(cmd or "")
        if c in ("mute", "deaf", "open", "leave"):
            if c == "open":
                self.room_open(True)
                return True
            if c == "leave":
                self._room_island = None
                if getattr(self, "_island_auto", False) and self._island_shown:
                    self._island_auto = False
                    self.mini_island_toggle(False)
            elif isinstance(getattr(self, "_room_island", None), dict):
                if c == "mute":
                    self._room_island["muted"] = not bool(self._room_island.get("muted"))
                elif c == "deaf":
                    new_deaf = not bool(self._room_island.get("deaf"))
                    self._room_island["deaf"] = new_deaf
                    if new_deaf:
                        self._room_island["muted"] = True
            self._room_island_q = (getattr(self, "_room_island_q", []) + [c])[-5:]
        return True

    def room_island_poll(self) -> list[str]:
        q, self._room_island_q = getattr(self, "_room_island_q", []), []
        return q

    # ---- Kami Kapsul: sureli / sifreli paylasim linki (Oda tuneli + sabit adres)
    def _kapsul_url(self, cid: str) -> str:
        from app.core import room
        base = room.SERVER.public_base()
        return f"{base}/c/{cid}" if base else ""

    # ---- Gizlilik Kalkani (secenek): yuz, e-posta, telefon, TC, IBAN, kart + EXIF/GPS silme
    def privacy_shield(self, paths_: list[str] | None = None, kinds: list[str] | None = None) -> dict[str, Any]:
        from app.core import privacy
        files = [str(x) for x in (paths_ or []) if x]
        if not files:
            if not self._window:
                return {"ok": False, "error": "no_window"}
            import webview
            res = self._window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=True,
                                                  file_types=("Görseller (*.jpg;*.jpeg;*.png;*.webp;*.bmp)", "Tüm dosyalar (*.*)"))
            if not res:
                return {"ok": False, "error": "cancelled"}
            files = list(res)
        out = []
        for f in files[:50]:
            try:
                r = privacy.shield_image(f, kinds=kinds)
            except Exception as exc:
                log.exception("Gizlilik Kalkani: %s", f)
                r = {"ok": False, "error": f"{type(exc).__name__}"}
            r.pop("regions", None)
            out.append({"src": f, **r})
        return {"ok": True, "items": out}

    def privacy_reveal(self, path: str) -> bool:
        if os.path.isfile(path):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            return True
        return False

    def kapsul_create(self, path: Any = "", hours: float = 24, password: str = "", max_dl: int = 0, note: str = "",
                      shield: bool = False) -> dict[str, Any]:
        from app.core import kapsul, room
        if not kapsul.ON_EVENT:   # indirildi / yorum bildirimi
            def _ev(kind: str, name: str, detail: str) -> None:
                from app.core import desktop
                desktop.toast("Kami Kapsül", (f"İndirildi: {detail or name}" if kind == "dl" else f"Yorum ({name}): {detail}"))
            kapsul.ON_EVENT = _ev
        if not path:
            if not self._window:
                return {"ok": False, "error": "no_window"}
            import webview
            res = self._window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=True)
            if not res:
                return {"ok": False, "error": "cancelled"}
            path = list(res) if len(res) > 1 else res[0]
        if isinstance(path, list):   # birden fazla dosya: tek link (kalkan yalniz tek gorselde)
            res = kapsul.create([str(x) for x in path], hours, password, max_dl, note)
            if res.get("ok"):
                room.SERVER.start(self._room_name(), True, self._room_id())
                res["url"] = self._kapsul_url(res["id"])
            return res
        shielded = None
        if shield and os.path.splitext(path)[1].lower() in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
            from app import paths
            from app.core import privacy
            d = paths.DATA_DIR / "kapsul_files"
            d.mkdir(parents=True, exist_ok=True)
            sr = privacy.shield_image(path, str(d / f"{int(__import__('time').time())}_{os.path.basename(path)}"))
            if sr.get("ok"):
                path, shielded = sr["path"], sr.get("found", {})
        res = kapsul.create(path, hours, password, max_dl, note)
        if shielded is not None:
            res["shielded"] = shielded
        if res.get("ok"):
            room.SERVER.start(self._room_name(), True, self._room_id())   # sunucu + tunel (zaten aciksa bir sey yapmaz)
            res["url"] = self._kapsul_url(res["id"])
        return res

    def kapsul_list(self) -> dict[str, Any]:
        from app.core import kapsul
        items = kapsul.list_all()
        for it in items:
            it["url"] = self._kapsul_url(it["id"])
        return {"ok": True, "items": items}

    def kapsul_delete(self, cid: str) -> dict[str, Any]:
        from app.core import kapsul
        return {"ok": kapsul.delete(str(cid))}

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

    def rec_schedule_at(self, hh_mm: str) -> dict[str, Any]:
        """Fikir 12: planli ekran kaydi (ornek '19:30'da otomatik kayda basla)."""
        import re as _re
        import threading as _th
        import datetime as _dt
        m = _re.fullmatch(r"(\d{1,2})[:.](\d{2})", str(hh_mm or "").strip())
        if not m:
            return {"ok": False, "error": "bad_time"}
        h, mm = int(m.group(1)), int(m.group(2))
        if not (0 <= h <= 23 and 0 <= mm <= 59):
            return {"ok": False, "error": "bad_time"}
        now = _dt.datetime.now()
        target = now.replace(hour=h, minute=mm, second=0, microsecond=0)
        if target <= now:
            target += _dt.timedelta(days=1)
        self._rec_sched_cancel()
        self._rec_sched_at = target
        self._rec_sched_stop = _th.Event()

        def _wait() -> None:
            while not self._rec_sched_stop.wait(10):
                if _dt.datetime.now() >= target:
                    try:
                        if not self.recorder.status().get("recording"):
                            self.rec_toggle()
                    except Exception:
                        pass
                    break
            self._rec_sched_at = None

        _th.Thread(target=_wait, name="kami-rec-sched", daemon=True).start()
        return {"ok": True, "at": target.strftime("%H:%M")}

    def rec_schedule_cancel(self) -> dict[str, Any]:
        self._rec_sched_cancel()
        return {"ok": True}

    def rec_schedule_status(self) -> dict[str, Any]:
        at = getattr(self, "_rec_sched_at", None)
        return {"ok": True, "scheduled": bool(at), "at": at.strftime("%H:%M") if at else ""}

    def _rec_sched_cancel(self) -> None:
        ev = getattr(self, "_rec_sched_stop", None)
        if ev:
            ev.set()
        self._rec_sched_at = None

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
            try:
                import pillow_heif
                pillow_heif.register_heif_opener()
            except Exception:
                pass
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
            raw = None
            if fmt in ("JPEG", "PNG", "WEBP", "GIF") and max(w, h) <= max_side and os.path.getsize(path) < 25e6:
                with open(path, "rb") as _if:
                    raw = _if.read()
            if raw is None:
                im = ImageOps.exif_transpose(im)
                im.thumbnail((max_side, max_side))
                buf = io.BytesIO()
                im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB").save(buf, "PNG" if im.mode in ("RGBA", "LA", "P") else "JPEG", quality=92)
                raw, fmt = buf.getvalue(), ("PNG" if im.mode in ("RGBA", "LA", "P") else "JPEG")
            mime = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp", "GIF": "image/gif"}.get(fmt, "image/png")
            try:
                im.close()
            except Exception:
                pass
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
        if not path:   # v1.33.1: sekmedeki "ayri pencerede ac" -> bos Picture penceresi
            if getattr(self, "_picture_win", None) is None and getattr(self, "_make_picture_window", None):
                self._picture_win = self._make_picture_window()
            elif getattr(self, "_front_picture", None):
                self._front_picture()
            return {"ok": True}
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

    # ---- v1.30 Picture toplu islem: dosya secimi + secilen klasore yazma (ad korunur, uzerine yazmaz)
    def pic_batch_pick(self) -> list[str]:
        import webview
        w = getattr(self, "_picture_win", None) or self._window
        if not w:
            return []
        r = w.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=True, file_types=(
            "Görseller (*.jpg;*.jpeg;*.png;*.webp;*.bmp;*.gif;*.tif;*.tiff;*.heic;*.avif)", "Tüm dosyalar (*.*)"))
        return [str(x) for x in (r or [])][:500]

    def pic_batch_dir(self) -> str:
        import webview
        w = getattr(self, "_picture_win", None) or self._window
        r = w.create_file_dialog(webview.FileDialog.FOLDER) if w else None
        return str(r[0]) if r else ""

    def pic_batch_write(self, src: str, out_dir: str, suffix: str, fmt: str, data_url: str) -> dict[str, Any]:
        import base64
        fmt = fmt if fmt in ("png", "jpg", "webp") else "jpg"
        try:
            raw = base64.b64decode(str(data_url).split(",", 1)[1])
        except Exception:
            return {"ok": False, "error": "bad_data"}
        d = str(out_dir or "") or os.path.join(os.path.dirname(str(src)), "Kami toplu")
        os.makedirs(d, exist_ok=True)
        base = re.sub(r'[\\/:*?"<>|]+', "_", os.path.splitext(os.path.basename(str(src)))[0])[:100] or "gorsel"
        sfx = re.sub(r'[\\/:*?"<>|]+', "_", str(suffix or ""))[:40]
        out = os.path.join(d, f"{base}{sfx}.{fmt}")
        n = 2
        while os.path.exists(out):
            out = os.path.join(d, f"{base}{sfx} ({n}).{fmt}")
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
        home = os.path.realpath(os.path.expanduser("~"))
        path = str(path or "")
        if path:
            # Guvenlik: yalnizca home altindaki .kami dosyalarina izin ver; disi reddedilir (path traversal)
            target = os.path.realpath(path)
            if not target.lower().endswith(".kami") or not (target == home or target.startswith(home + os.sep)):
                path = ""
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

    def editor_psd_open(self, path: str = "") -> dict[str, Any]:
        """Kami Picture: Katmanli Adobe Photoshop (.psd) dosyasini acar."""
        from app.core.psd_reader import read_psd_layers
        p = str(path or "").strip()
        if not p:
            import webview
            w = getattr(self, "_picture_win", None)
            if not w:
                return {"ok": False, "error": "no_window"}
            r = w.create_file_dialog(webview.OPEN_DIALOG, directory=self._edit_out_dir(""), file_types=("Photoshop (*.psd)",))
            if not r:
                return {"ok": False}
            p = str(r[0])
        res = read_psd_layers(p)
        if res.get("ok"):
            res["path"] = p
        return res

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

    def pic_contact_shadow(self, image: str, bg_color: str = "#FFFFFF", pad_ratio: float = 0.12,
                           size: int = 1200, bounce: bool = True, out_path: str = "") -> dict[str, Any]:
        from app.core.picture_pro import add_contact_shadow
        return add_contact_shadow(str(image), out_path=str(out_path or ""), bg_color=str(bg_color),
                                  pad_ratio=float(pad_ratio), size=int(size), bounce=bool(bounce))

    def pic_export_webp_sheet(self, images: list[str], out_path: str = "", duration_ms: int = 140) -> dict[str, Any]:
        from app.core.picture_pro import export_webp_sheet
        return export_webp_sheet([str(x) for x in (images or [])], out_path=str(out_path or ""), duration_ms=int(duration_ms))

    def pic_macro_list(self) -> list[dict[str, Any]]:
        from app.core.picture_pro import list_macros
        return list_macros()

    def pic_macro_save(self, name: str, steps: list[dict[str, Any]], macro_id: str = "") -> dict[str, Any]:
        from app.core.picture_pro import save_macro
        return save_macro(str(name), steps or [], macro_id=str(macro_id or ""))

    def pic_macro_run(self, image: str, macro: Any, out_path: str = "") -> dict[str, Any]:
        from app.core.picture_pro import run_macro
        return run_macro(str(image), macro, out_path=str(out_path or ""))

    def pic_macro_batch(self, target: Any, macro: Any, out_dir: str = "") -> dict[str, Any]:
        from app.core.picture_pro import batch_run_macro
        return batch_run_macro(target, macro, out_dir=str(out_dir or ""))

    def pic_send_to_studio(self, image: str, folder: str = "Gorseller") -> dict[str, Any]:
        from app.core.picture_pro import send_to_studio_asset
        return send_to_studio_asset(str(image), folder=str(folder or "Gorseller"))

    def pic_set_current(self, path: str) -> dict[str, Any]:
        from app.core.picture_mcp import set_current_image
        try:
            return set_current_image(str(path), by="ui")
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def pic_save_temp_png(self, data_url: str, name: str = "kami_pic") -> dict[str, Any]:
        import base64
        from app import paths
        raw_b64 = str(data_url or "").split(",", 1)[-1]
        out_dir = paths.DATA_DIR / "pic_work"
        out_dir.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r'[<>:"/\\|?*]+', "_", str(name or "kami_pic")).strip(" .")[:48] or "kami_pic"
        dst = out_dir / f"{safe}.png"
        dst.write_bytes(base64.b64decode(raw_b64))
        try:
            from app.core.picture_mcp import set_current_image
            set_current_image(str(dst), by="editor")
        except Exception:
            pass
        return {"ok": True, "path": str(dst)}

    def picture_poll(self) -> list[dict[str, Any]]:
        with self._inbox_lock:
            q, self._picture_q = getattr(self, "_picture_q", []), []
        return q

    def lens_search(self, path: str) -> dict[str, Any]:
        from app.core import lens
        if not os.path.isfile(str(path or "")):
            return {"ok": False, "error": "no_file"}
        try:
            r = lens.search(str(path))
            self._lens_last = {str(path): r}   # fiyat sorgusu onerisi icin
            return r
        except Exception as exc:
            log.exception("Kami Lens")
            return {"ok": False, "error": str(exc)[:160]}

    # ---- v1.30 Lens araclari: fiyat, metin, tablo -> Excel, QR/barkod
    def lens_price(self, query: str = "", path: str = "") -> dict[str, Any]:
        from app.core import lens_tools
        q = str(query or "").strip()
        if not q and path:
            lr = getattr(self, "_lens_last", {}).get(str(path)) or {}
            q = lens_tools.product_query(lr, lens_tools.ocr_text(str(path)).get("text", "") if os.name == "nt" else "")
        if not q:
            return {"ok": False, "error": "sorgu", "query": ""}
        return lens_tools.price_search(q)

    def lens_text(self, path: str) -> dict[str, Any]:
        from app.core import lens_tools
        try:
            return lens_tools.ocr_text(str(path))
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:160]}

    def lens_table(self, path: str) -> dict[str, Any]:
        from app.core import lens_tools
        p = str(path)
        out = os.path.join(self._manager.settings.get("download_dir") or os.path.dirname(p),
                           os.path.splitext(os.path.basename(p))[0].replace("kami_lens_", "lens_") + "_tablo.xlsx")
        try:
            return lens_tools.table_to_xlsx(p, out)
        except Exception as exc:
            log.exception("Lens tablo")
            return {"ok": False, "error": str(exc)[:160]}

    def lens_codes(self, path: str) -> dict[str, Any]:
        from app.core import lens_tools
        try:
            return lens_tools.barcodes(str(path))
        except Exception as exc:
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
        if not self._manager:
            return ""
        norm = os.path.normcase(os.path.abspath(path))
        base = os.path.basename(path)
        items = self._manager.store.list()
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

    def subtitle_scan(self, folder: str) -> dict[str, Any]:
        """Klasördeki videoları tarar; .srt/.vtt/.ass'si eksik olanları döner (altyazı yöneticisi)."""
        root = str(folder or "").strip()
        if not root or not os.path.isdir(root):
            return {"ok": False, "error": "no_folder"}
        vids = []
        for dp, _dn, fn in os.walk(root):
            for f in fn:
                ext = os.path.splitext(f)[1].lower()
                if ext not in (".mp4", ".mkv", ".avi", ".mov", ".webm", ".ts", ".m2ts"):
                    continue
                p = os.path.join(dp, f)
                base = os.path.splitext(p)[0]
                has_sub = any(os.path.exists(base + s) for s in (".srt", ".vtt", ".ass", ".ssa"))
                vids.append({"path": p, "name": f, "has_sub": has_sub})
        missing = [v for v in vids if not v["has_sub"]]
        return {"ok": True, "total": len(vids), "missing": len(missing), "videos": vids}

    def subtitle_batch(self, paths: list[str], lang: str = "tr") -> dict[str, Any]:
        """Toplu altyazı indirme (eksik olanlar için; OpenSubtitles anahtarı gerekli)."""
        done, errors = [], []
        for p in (paths or []):
            try:
                r = self.subtitle_fetch(str(p), str(lang or "tr")[:5])
            except Exception as exc:
                errors.append({"path": p, "error": str(exc)[:100]}); continue
            if r.get("ok"):
                done.append(p)
            else:
                errors.append({"path": p, "error": r.get("error", "fail")})
        return {"ok": True, "done": done, "errors": errors}

    def tag_read(self, path: str) -> dict[str, Any]:
        """Muzik dosyasinin etiketlerini okur (mutagen easy)."""
        p = str(path or "").strip()
        if not p or not os.path.isfile(p):
            return {"ok": False, "error": "no_file"}
        try:
            import mutagen
            f = mutagen.File(p, easy=True)
            if f is None:
                return {"ok": True, "tags": {}}
            return {"ok": True, "tags": {str(k): (v[0] if isinstance(v, list) else str(v)) for k, v in (f.tags or {}).items()}}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:120]}

    def tag_write(self, path: str, tags: dict) -> dict[str, Any]:
        """Muzik dosyasina etiket yazar (mutagen easy; title/artist/album...)."""
        p = str(path or "").strip()
        if not p or not os.path.isfile(p):
            return {"ok": False, "error": "no_file"}
        try:
            import mutagen
            f = mutagen.File(p, easy=True)
            if f is None:
                return {"ok": False, "error": "unsupported"}
            for k, v in (tags or {}).items():
                if v in (None, ""):
                    continue
                f[str(k)] = str(v)
            f.save()
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:120]}

    def tag_cover_write(self, path: str, data_url: str) -> dict[str, Any]:
        """Muzik dosyasina kapak resmi yazar (ID3 APIC / FLAC PICTURE / MP4 covr)."""
        import base64
        p = str(path or "").strip()
        if not p or not os.path.isfile(p):
            return {"ok": False, "error": "no_file"}
        try:
            raw = base64.b64decode(str(data_url or "").split(",", 1)[1])
        except Exception:
            return {"ok": False, "error": "bad_image"}
        mime = "image/png" if str(data_url or "").startswith("data:image/png") else "image/jpeg"
        try:
            import mutagen
            ext = os.path.splitext(p)[1].lower()
            if ext == ".mp3":
                from mutagen.id3 import APIC, ID3
                id3 = mutagen.File(p)
                if id3 is None or id3.tags is None:
                    id3 = ID3()
                id3.delall("APIC")
                id3.add(APIC(encoding=3, mime=mime, type=3, desc="cover", data=raw))
                id3.save(p)
            elif ext == ".flac":
                from mutagen.flac import Picture
                f = mutagen.File(p)
                pic = Picture()
                pic.type = 3
                pic.mime = mime
                pic.desc = "cover"
                pic.data = raw
                f.clear_pictures()
                f.add_picture(pic)
                f.save()
            elif ext in (".m4a", ".mp4"):
                from mutagen.mp4 import MP4Cover
                f = mutagen.File(p)
                fmt = MP4Cover.FORMAT_PNG if mime == "image/png" else MP4Cover.FORMAT_JPEG
                f.tags["covr"] = [MP4Cover(raw, imageformat=fmt)]
                f.save()
            else:
                return {"ok": False, "error": "unsupported"}
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:120]}

    # ---------- Muzik Etiket / Kapak / Isimlendir (MP3tag mantigi) ----------
    def music_tag_open(self) -> dict[str, Any]:
        return self._open_mod_window("musictag")

    def music_tag_pick_folder(self) -> dict[str, Any]:
        import webview
        try:
            res = self._window.create_file_dialog(webview.FileDialog.FOLDER)
            return {"ok": True, "path": (res[0] if isinstance(res, (list, tuple)) else res) or ""}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:120]}

    def music_tag_rename_plan(self, folder: str, style: str = "feat_after", recursive: bool = False) -> dict[str, Any]:
        from app.core import music_tag
        return music_tag.rename_plan(str(folder or ""), style or "feat_after", bool(recursive))

    def music_tag_rename_apply(self, pairs: list) -> dict[str, Any]:
        return self.batch_rename(pairs or [])

    def music_tag_cover_batch(self, folder: str, data_url: str, recursive: bool = False) -> dict[str, Any]:
        from app.core import music_tag
        return music_tag.cover_batch(str(folder or ""), data_url or "", bool(recursive))

    def music_tag_export_m3u(self, folder: str, recursive: bool = False) -> dict[str, Any]:
        from app.core import music_tag
        return music_tag.m3u_export(str(folder or ""), bool(recursive))

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
        if p.suffix.lower() == ".mp3" and self._manager.settings.get("lyrics_embed", True):
            try:
                from app.core import media_meta
                media_meta.write_mp3_tags(str(p), lyrics=text)
            except Exception:
                pass
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
        if req.get("at"):
            item["at"] = float(req["at"])
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

    def phone_status_items(self, limit: int = 15) -> list[dict[str, Any]]:
        """Telefon sayfasindaki "indirme durumu": aktif/bekleyen/duraklatilmis + son bitenler."""
        order = {Status.ACTIVE: 0, Status.WAITING: 1, Status.PAUSED: 2, Status.ERROR: 3, Status.COMPLETE: 4}
        items = sorted(self._manager.snapshot(), key=lambda d: (order.get(d.status, 5), -(d.id or 0)))
        out = []
        for d in items[:max(1, int(limit))]:
            pct = int(d.downloaded * 100 / d.size) if d.size else (100 if d.status == Status.COMPLETE else 0)
            st = {Status.ACTIVE: "iniyor", Status.WAITING: "sırada", Status.PAUSED: "duraklatıldı",
                  Status.ERROR: "hata", Status.COMPLETE: "bitti"}.get(d.status, str(d.status))
            speed = f" · {d.speed / 1048576:.1f} MB/sn" if d.status == Status.ACTIVE and d.speed else ""
            out.append({"id": d.id, "name": d.filename or d.url, "path": d.path or "", "percent": max(0, min(100, pct)),
                        "label": f"{st} · %{pct}{speed}",
                        "can_pause": d.status in (Status.ACTIVE, Status.WAITING),
                        "can_resume": d.status in (Status.PAUSED, Status.ERROR),
                        "can_top": d.status in (Status.WAITING, Status.PAUSED), "status": str(getattr(d.status, "value", d.status))})
        return out

    def phone_control(self, download_id: int, action: str) -> bool:
        if action == "pause":
            self._manager.pause(int(download_id))
            return True
        if action == "resume":
            self._manager.resume(int(download_id))
            return True
        if action.startswith("deck:"):   # eski Pad sayfasi da yeni eylemleri cagirabilsin
            return bool(self.deck_run(action[5:]).get("ok"))
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

    # ---------- v1.28 Kami Deck (telefonu Stream Deck gibi kullan) + uzaktan indirme yonetimi ----------
    def _deck_handlers(self) -> dict[str, Any]:
        return {
            "app:studio": lambda a="": self.studio_show(), "app:picture": lambda a="": self.picture_open_editor(),
            "app:player": lambda a="": self.player_show(), "app:reader": lambda a="": self.reader_show(),
            "app:room": lambda a="": self.room_open(True), "app:show": lambda a="": self._deck_show_main(),
            "rec:toggle": lambda a="": self.rec_toggle(), "rec:replay": lambda a="": self.rec_save_replay(),
            "room:mute": lambda a="": self.room_island_cmd("mute"), "room:deaf": lambda a="": self.room_island_cmd("deaf"),
            "dl:pause_all": lambda a="": self.pause_all(), "dl:resume_all": lambda a="": self.resume_all(),
            "dl:limit": lambda a="": self.set_setting("speed_limit_kib", max(0, int(float(a or 0)))),
            "studio_open": lambda: None,   # Studio komutlari: pencere acik degilse komut 5 sn icinde duser
        }

    def _deck_show_main(self) -> None:
        try:
            if self._window:
                self._window.restore()
                self._window.show()
        except Exception:
            pass

    def deck_get(self) -> dict[str, Any]:
        from app.core import deck
        return {**deck.load(), "catalog": deck.CATALOG}

    def deck_save(self, data: dict) -> dict[str, Any]:
        from app.core import deck
        return deck.save(data if isinstance(data, dict) else {})

    def deck_run(self, action: str, arg: str = "") -> dict[str, Any]:
        from app.core import deck
        return deck.run(str(action), str(arg or ""), self._deck_handlers())

    def deck_bus_poll(self, target: str) -> list:
        from app.core import deck
        return deck.bus_poll(str(target))

    def phone_deck(self, path: str, body: dict) -> tuple[int, dict[str, Any]]:
        """Telefon sunucusundan: /deck/data, /deck/run, /deck/save, /dl/action, /dl/list."""
        b = body if isinstance(body, dict) else {}
        if path == "/deck/data":
            return 200, {"ok": True, **self.deck_get(), "downloads": self.phone_status_items(40),
                         "limit": int(self._manager.settings.get("speed_limit_kib") or 0)}
        if path == "/deck/run":
            return 200, self.deck_run(str(b.get("a", "")), str(b.get("arg", "")))
        if path == "/deck/save":
            return 200, {"ok": True, **self.deck_save(b)}
        if path == "/dl/action":
            act, did = str(b.get("action", "")), int(b.get("id") or 0)
            if act == "remove":
                self._manager.remove(did, bool(b.get("delete_file")))
            elif act == "top":
                ids = [d.id for d in self._manager.snapshot() if not d.status.is_finished]
                if did in ids:
                    self._manager.reorder([did] + [x for x in ids if x != did])
            elif not self.phone_control(did, act):
                return 400, {"ok": False, "error": "bad_action"}
            return 200, {"ok": True, "downloads": self.phone_status_items(40)}
        return 404, {"ok": False}

    def phone_on_upload(self, path: str, kind: str) -> None:
        from app.core import desktop
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

    def hunter_search(self, query: str, site: str = "", cluster: bool = True) -> dict[str, Any]:
        from app.core import kami_hunter
        return kami_hunter.search(str(query or "").strip(), site=str(site or "").strip(), cluster=bool(cluster))

    def hunter_archive(self, url: str, title: str = "", artist: str = "", out_dir: str = "", lyrics: str = "") -> dict[str, Any]:
        from app.core import kami_hunter
        return kami_hunter.archive_underground_track(
            str(url or "").strip(),
            title=str(title or "").strip(),
            artist=str(artist or "").strip(),
            out_dir=str(out_dir or "").strip(),
            lyrics=str(lyrics or "").strip(),
        )

    def mod_list(self) -> list[dict[str, Any]]:
        from app.core import kami_mod
        return kami_mod.list_mods()

    def mod_preview_diff(self, archive: str, game_dir: str) -> dict[str, Any]:
        from app.core import kami_mod
        return kami_mod.preview_mod_diff(str(archive or "").strip(), str(game_dir or "").strip())

    def mod_install(self, archive: str, game_dir: str) -> dict[str, Any]:
        from app.core import kami_mod
        return kami_mod.install_mod(str(archive or "").strip(), str(game_dir or "").strip())

    def mod_rollback(self, mod_id: str) -> dict[str, Any]:
        from app.core import kami_mod
        return kami_mod.rollback_mod(str(mod_id or "").strip())

    def mod_export_profile(self, game_dir: str, out_json: str = "") -> dict[str, Any]:
        from app.core import kami_mod
        return kami_mod.export_mod_profile(str(game_dir or "").strip(), str(out_json or "").strip())

    def mod_import_profile(self, profile_json: str) -> dict[str, Any]:
        from app.core import kami_mod
        return kami_mod.import_mod_profile(str(profile_json or "").strip())

    def phone_bridge_url(self) -> dict[str, Any]:
        from app.core.phone import lan_ip
        from app.core import room as _room
        port = int(self._manager.settings.get("phone_port") or 47322)
        key = self._phone_key.load() if self._phone_key else ""
        local_url = f"http://{lan_ip()}:{port}/bridge" + (f"?k={key}" if key else "")
        tunnel_url = ""
        if _room.SERVER.public and _room.SERVER.room:
            base_t = _room.SERVER.public.rstrip("/")
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
        return link_check.check_links(list(urls or []), cloud_service=getattr(self._manager, "cloud", None))

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
        from app.core.debrid import TokenStore
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
        from app.core import music_hub
        card = self.card_state()
        try:
            mus = music_hub.cached_now(allow_paused=True)
        except TypeError:
            mus = music_hub.cached_now()
        mus_out = None
        if mus and mus.get("title"):
            prog = int(mus.get("progress_ms") or 0)
            dur = int(mus.get("duration_ms") or 0)
            mus_out = {
                "id": mus.get("id", ""),
                "playing": bool(mus.get("playing")),
                "title": mus.get("title", ""),
                "artist": mus.get("artist", ""),
                "cover": mus.get("cover", ""),
                "progress_ms": prog,
                "duration_ms": dur,
                "lyric_line": self._island_lyric_for(mus.get("title", ""), mus.get("artist", ""), prog),
            }
        return {
            "speed": card.get("speed", 0),
            "active": card.get("n", 0),
            "telemetry": snapshot(),
            "profile": self._profile_store().active_profile(),
            "speed_profile": str(self._manager.settings.get("speed_profile") or "full"),
            "island_music_expand": bool(self._manager.settings.get("island_music_expand", True)),
            "visible": bool(self._island_shown),
            "room": self._room_island_live(),
            "music": mus_out,
        }

    def _room_island_live(self) -> dict[str, Any] | None:
        import time as _t
        ri = getattr(self, "_room_island", None)
        if not ri or not self._manager.settings.get("room_island") or _t.time() - ri.get("t", 0) > 6:
            return None
        return ri

    def mini_island_toggle(self, show: bool | None = None, persist: bool = True) -> dict[str, Any]:
        target = (not self._island_shown) if show is None else bool(show)
        if persist:
            self._island_auto = False   # kullanici elle actiysa/kapattiysa otomatik mod devreden cikar
        if target:
            if self._island_win is None and self._island_factory is not None:
                self._island_win = self._island_factory()
            if self._island_win is not None:
                try:
                    self._island_win.show()
                    from app.core import winwin
                    winwin.round_pill("Kami Mini-Ada")
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
        if persist:
            self._manager.settings.set("mini_island", self._island_shown)
        return {"ok": True, "visible": self._island_shown}

    def mini_island_open_main(self) -> dict[str, Any]:
        """Mini-Ada'daki 'Ana Pencereyi Ac' butonu: ana pencereyi one getirir.

        mini-island.html bu metodu cagiriyordu ama api.py'de hic tanimli degildi
        (buton sessizce hicbir sey yapmiyordu).
        """
        try:
            if self._window is not None:
                self._window.restore()
                self._window.show()
        except Exception:
            log.debug("ana pencere gosterilemedi", exc_info=True)
        try:
            from app.core import winwin
            hwnd = winwin.find_window("Kami")
            if hwnd:
                winwin.bring_to_front(hwnd)
        except Exception:
            log.debug("ana pencere one getirilemedi", exc_info=True)
        return {"ok": True}

    def music_island_tick(self) -> None:
        """v1.38.0: Kamify gizliyken arka planda Spotify/librespot durumunu tazeler, Mini-Ada'yi ve gorev cubugu ThumbButtons'u senkronlar."""
        import time as _t
        from app.core import music_hub, winwin
        now_t = _t.monotonic()
        if now_t - float(getattr(self, "_island_sp_t", 0.0)) >= 4.0:
            self._island_sp_t = now_t
            try:
                has_sp = bool(music_hub.get_spotify_token("")) or bool(music_hub._librespot_now())
                if has_sp:
                    music_hub.spotify_now("")
            except Exception:
                pass
        try:
            m = music_hub.cached_now(allow_paused=True)
        except TypeError:
            m = music_hub.cached_now()
        playing = bool(m and m.get("playing") and m.get("title"))
        self._update_music_thumbbar(playing)
        if self._island_shown and not getattr(self, "_island_auto", False):
            return
        h = winwin.find_window("Kamify")
        kamify_open = bool(h) and winwin.is_visible(h)
        dl_active = False
        try:
            dl_active = int(self.card_state().get("n", 0) or 0) > 0
        except Exception:
            dl_active = False
        want = (playing or dl_active) and not kamify_open
        if want and not self._island_shown:
            self.mini_island_toggle(True, persist=False)
            self._island_auto = True
        elif not want and self._island_shown and getattr(self, "_island_auto", False) and not getattr(self, "_room_island", None):
            if not m or not m.get("title") or kamify_open:
                self.mini_island_toggle(False, persist=False)
                self._island_auto = False

    # ---------- Faz 11: LinkCrawler, Canli DVR, Web Arsivi, Medya Sagligi ----------
    def crawler_rules_list(self) -> dict[str, Any]:
        from app.core.link_crawler import load_rules
        return {"ok": True, "rules": load_rules()}

    def crawler_rule_save(self, rule: dict[str, Any]) -> dict[str, Any]:
        from app.core.link_crawler import save_rule
        return save_rule(rule)

    def crawler_rule_delete(self, name: str) -> dict[str, Any]:
        from app.core.link_crawler import delete_rule
        return delete_rule(name)

    def crawler_crawl(self, url: str) -> dict[str, Any]:
        from app.core.link_crawler import crawl
        return crawl(url)

    def dvr_start(self, url: str, out_dir: str = "", from_start: bool = True) -> dict[str, Any]:
        from app.core.web_archive import start_live_dvr
        target = out_dir or str(self._manager.settings.get("download_dir", "Downloads"))
        return start_live_dvr(url, target, from_start=from_start, background=True)

    def dvr_cancel(self, job_id: str) -> dict[str, Any]:
        from app.core.web_archive import cancel_live_dvr
        return cancel_live_dvr(job_id)

    def dvr_list(self) -> dict[str, Any]:
        from app.core.web_archive import list_live_dvr
        return {"ok": True, "jobs": list_live_dvr()}

    def web_archive_save(self, url: str, out_path: str = "") -> dict[str, Any]:
        from app.core.web_archive import archive_webpage
        if not out_path:
            base = Path(self._manager.settings.get("download_dir", "Downloads")) / "WebArsiv"
            out_path = str(base / f"arsiv_{int(time.time())}.html")
        return archive_webpage(url, out_path)

    def library_find_duplicates(self, folder: str, max_hamming: int = 6) -> dict[str, Any]:
        from app.core.library_health import find_duplicates
        return find_duplicates(folder, max_hamming=max_hamming)

    def library_smart_compress(self, src: str, dst: str = "", codec: str = "", min_vmaf: float = 95.0) -> dict[str, Any]:
        from app.core.library_health import smart_compress
        return smart_compress(src, dst, codec=codec, min_vmaf=min_vmaf)

    def library_scan_health(self, folder: str, manifest_path: str = "", deep_decode: bool = False) -> dict[str, Any]:
        from app.core.library_health import scan_health
        man = manifest_path or str(Path(folder) / ".kami_health.json")
        return scan_health(folder, man, deep_decode=deep_decode)

    # ---------- Faz 12: Sahne Haritasi, ReplayGain, Beatgrid, Word-Karaoke & Ses Kutusu ----------
    def player_detect_scenes(self, video_path: str, threshold: float = 0.32) -> dict[str, Any]:
        from app.core.scene_detect import detect_scenes
        return detect_scenes(video_path, threshold=threshold)

    def player_replaygain(self, media_path: str, target_lufs: float = -18.0) -> dict[str, Any]:
        from app.core.scene_detect import measure_replaygain
        return measure_replaygain(media_path, target_lufs=target_lufs)

    def beat_grid(self, audio_path: str, duration: float = 0.0) -> dict[str, Any]:
        from app.core.kami_beat import build_beatgrid
        return build_beatgrid(audio_path, duration=duration)

    def lyrics_word_sync(self, lrc_text: str, duration: float = 0.0) -> dict[str, Any]:
        from app.core.kami_beat import word_sync_lyrics
        return {"ok": True, "lines": word_sync_lyrics(lrc_text, duration=duration)}

    def audio_fx_apply(self, src: str, dst: str = "", preset: str = "vocal_studio", reverb: float = 0.2) -> dict[str, Any]:
        from app.core.audio_toolbox import apply_audio_fx
        return apply_audio_fx(src, dst, preset=preset, reverb=reverb)

    def audio_to_midi(self, src: str) -> dict[str, Any]:
        from app.core.audio_toolbox import audio_to_notes
        return audio_to_notes(src)

    def tts_speak(self, text: str, out_wav: str = "", lang: str = "tr") -> dict[str, Any]:
        from app.core.audio_toolbox import synthesize_tts
        target = out_wav or str(Path(self._manager.settings.get("download_dir", "Downloads")) / f"tts_{int(time.time())}.wav")
        return synthesize_tts(text, target, lang=lang)

    # ---------- Faz 13: Kami Kasa Semantik Arama & Oto-Bolumlendirme ----------
    def kasa_index_media(self, video_path: str, tags: str = "", transcript_segments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        from app.core.semantic_vault import index_media
        return index_media(video_path, tags=tags, transcript_segments=transcript_segments)

    def kasa_search(self, query: str, limit: int = 30) -> dict[str, Any]:
        import base64
        from app.core.semantic_vault import semantic_search
        res = semantic_search(query, limit=limit)
        for r in res.get("results") or []:   # kucuk resimler veri adresi olarak (file:// izinlerine takilmasin)
            th = r.get("thumb") or ""
            r["thumb_url"] = ""
            try:
                if th and os.path.isfile(th) and os.path.getsize(th) < 400_000 and th.lower().endswith((".jpg", ".jpeg")):
                    with open(th, "rb") as f:
                        r["thumb_url"] = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode("ascii")
            except OSError:
                pass
        return res

    def kasa_setup(self) -> dict[str, Any]:
        from app.core import aitools
        from app.core.semantic_vault import INDEX_STATE, kasa_stats
        if aitools.installed("kasa") and not getattr(self, "_kasa_warm", False):   # ilk aramada 20 sn beklemesin
            self._kasa_warm = True
            from app.core import kasa_embed
            threading.Thread(target=lambda: (kasa_embed.embed_text(["."]), kasa_embed.embed_clip_text(["."])),
                             name="kami-kasa-warm", daemon=True).start()
        return {"installed": aitools.installed("kasa"), "size_gb": aitools.TOOLS["kasa"]["size_gb"],
                "installing": (self._ai.installing.get("kasa") if self._ai else None),
                "index": dict(INDEX_STATE), **kasa_stats()}

    def kasa_index_folder(self, folder: str = "") -> dict[str, Any]:
        from app.core.semantic_vault import INDEX_STATE, index_folder
        if INDEX_STATE.get("running"):
            return {"ok": False, "error": "busy"}
        if not folder:
            if not self._window:
                return {"ok": False, "error": "no_window"}
            import webview
            res = self._window.create_file_dialog(webview.FileDialog.FOLDER)
            if not res:
                return {"ok": False, "error": "cancelled"}
            folder = res[0]
        threading.Thread(target=index_folder, args=(folder,), name="kami-kasa-index", daemon=True).start()
        return {"ok": True, "folder": folder}

    def kasa_open(self, path: str, at: float = 0.0) -> dict[str, Any]:
        """Sonuca tikla: video Kami Player'da o saniyeden, gorsel Kami Picture'da, PDF/not Kami Reader'da."""
        from app.core.semantic_vault import DOC_EXT, IMAGE_EXT
        if not os.path.isfile(path):
            return {"ok": False, "error": "not_found"}
        ext = os.path.splitext(path)[1].lower()
        if ext in IMAGE_EXT and hasattr(self, "picture_open"):
            return self.picture_open(path)
        if ext in DOC_EXT and hasattr(self, "reader_open"):
            return self.reader_open(path)
        return self.player_show({"path": path, "at": float(at or 0)})

    def kasa_auto_chapters(self, transcript_segments: list[dict[str, Any]], chunk_seconds: float = 180.0, use_ollama: bool = True) -> dict[str, Any]:
        from app.core.semantic_vault import auto_chapters
        return auto_chapters(transcript_segments, chunk_seconds=chunk_seconds, use_ollama=use_ollama)

    def kasa_stats(self) -> dict[str, Any]:
        from app.core.semantic_vault import kasa_stats
        return kasa_stats()

    # ---------- Faz 14: Klip Fabrikasi, Oto Oyun Vurgu & Sanal Kamera ----------
    def clip_factory_vertical(self, video_path: str, out_path: str = "", x_ratio: float | None = None) -> dict[str, Any]:
        from app.core.clip_factory import auto_vertical_reframe
        return auto_vertical_reframe(video_path, out_path, x_ratio=x_ratio)

    def clip_factory_highlights(self, video_path: str, out_dir: str = "", max_clips: int = 3) -> dict[str, Any]:
        from app.core.clip_factory import extract_viral_clips
        dst = out_dir or str(Path(self._manager.settings.get("download_dir", "Downloads")) / "Klipler")
        return extract_viral_clips(video_path, dst, max_clips=max_clips)

    def clip_factory_ugc_matrix(self, hooks: list[str], body: str, ctas: list[str], out_dir: str = "", platform: str = "tiktok") -> dict[str, Any]:
        from app.core.clip_factory import render_ugc_matrix
        dst = out_dir or str(Path(self._manager.settings.get("download_dir", "Downloads")) / "UGC")
        return render_ugc_matrix(hooks, body, ctas, dst, platform=platform)

    def _hw(self):
        if getattr(self, "_highlight_watcher", None) is None:
            from app.core.game_highlight import HighlightWatcher
            self._highlight_watcher = HighlightWatcher(self.recorder)
        return self._highlight_watcher

    def highlight_watcher_start(self, games: list[str] | None = None, keywords: list[str] | None = None) -> dict[str, Any]:
        if not self.recorder:
            return {"ok": False, "error": "Recorder hazir degil"}
        hw = self._hw()
        hw.recorder = self.recorder   # izleyici recorder baglanmadan once olusturulduysa guncelle
        try:   # vurgu kaydedebilmek icin replay tamponu acik olmali
            self.recorder.start_replay()
        except Exception:
            log.debug("highlight: replay tamponu baslatilamadi", exc_info=True)
        return hw.start(games=games, keywords=keywords)

    def highlight_watcher_stop(self) -> dict[str, Any]:
        return self._hw().stop()

    def highlight_watcher_status(self) -> dict[str, Any]:
        return self._hw().status()

    def virtual_cam_status(self) -> dict[str, Any]:
        from app.core.game_highlight import virtual_camera_status
        return virtual_camera_status()

    def highlight_build_fragmovie(
        self, clip_paths: list[str] | str, out_kstudio: str = "", title: str = "Oyun Fragmovie"
    ) -> dict[str, Any]:
        from app.core.game_highlight import build_fragmovie_project
        return build_fragmovie_project(clip_paths, out_kstudio=str(out_kstudio or "").strip(), title=str(title or "Oyun Fragmovie").strip())

    # ---------- Faz 15: Belge Donusturucu & Manga Ceviri Studyosu ----------
    def doc_pdf_to_markdown(self, src_pdf: str, out_md: str = "") -> dict[str, Any]:
        from app.core.doc_studio import pdf_to_markdown
        return pdf_to_markdown(src_pdf, out_md)

    def doc_convert(self, src_path: str, target_format: str = "html", out_path: str = "") -> dict[str, Any]:
        from app.core.doc_studio import convert_document
        return convert_document(src_path, target_format=target_format, out_path=out_path)

    def manga_translate_page(self, image_path: str, out_path: str = "", target_lang: str = "tr") -> dict[str, Any]:
        from app.core.manga_translate import translate_manga_page
        return translate_manga_page(image_path, out_path, target_lang=target_lang)

    # ---------- Faz 16: Kami Kopru, LAN P2P, Kami Pano & Sesli Komut ----------
    def bridge_mirror_status(self) -> dict[str, Any]:
        from app.core.screen_bridge import mirror_status
        return mirror_status()

    def bridge_mirror_start(self, kind: str = "scrcpy", record_path: str = "") -> dict[str, Any]:
        from app.core.screen_bridge import start_mirror
        return start_mirror(kind, record_path=record_path)

    def bridge_mirror_stop(self, kind: str = "") -> dict[str, Any]:
        from app.core.screen_bridge import stop_mirror
        return stop_mirror(kind)

    def _lan_srv(self):
        if getattr(self, "_lan_p2p", None) is None:
            from app.core.lan_p2p import LanShareServer
            self._lan_p2p = LanShareServer()
        return self._lan_p2p

    def lan_share_file(self, path: str) -> dict[str, Any]:
        return self._lan_srv().share_file(path)

    def lan_share_stop(self) -> dict[str, Any]:
        return self._lan_srv().stop()

    def pano_shelf_list(self) -> dict[str, Any]:
        from app.core.pano_tools import list_shelf
        return {"ok": True, "items": list_shelf()}

    def pano_shelf_add(self, kind: str, value: str, label: str = "") -> dict[str, Any]:
        from app.core.pano_tools import add_shelf_item
        return add_shelf_item(kind, value, label)

    def pano_shelf_clear(self) -> dict[str, Any]:
        from app.core.pano_tools import clear_shelf
        return clear_shelf()

    def pano_shelf_remove(self, item_id: str) -> dict[str, Any]:
        from app.core.pano_tools import remove_shelf_item
        return remove_shelf_item(item_id)

    def pano_pick_oklch(self, x: int, y: int) -> dict[str, Any]:
        from app.core.pano_tools import pick_screen_oklch
        return pick_screen_oklch(x, y)

    def pano_measure_rect(self, x1: int, y1: int, x2: int, y2: int) -> dict[str, Any]:
        from app.core.pano_tools import measure_pixel_rect
        return measure_pixel_rect(x1, y1, x2, y2)

    def pano_ocr(self, x: int, y: int, w: int, h: int, lang: str = "") -> dict[str, Any]:
        from app.core.pano_tools import pano_ocr_region
        return pano_ocr_region(x, y, w, h, lang=lang)

    def voice_parse_command(self, text: str) -> dict[str, Any]:
        from app.core.voice_cmd import parse_voice_command
        return parse_voice_command(text)

    def voice_status(self) -> dict[str, Any]:
        from app.core.voice_cmd import voice_capabilities
        return voice_capabilities()

    # ---------- Faz 18: Yerel Copilot, Akis Zinciri, .kamipack ----------
    def copilot_status(self) -> dict[str, Any]:
        from app.core.local_copilot import copilot_status
        return copilot_status()

    def copilot_run(self, prompt: str, model: str = "qwen2.5:7b") -> dict[str, Any]:
        from app.core.local_copilot import run_copilot
        return run_copilot(prompt, model=model)

    def flow_catalog(self) -> dict[str, Any]:
        from app.core.flow_chain import NODE_CATALOG, list_flows
        return {"ok": True, "nodes": NODE_CATALOG, "flows": list_flows()}

    def flow_save(self, name: str, graph: dict[str, Any]) -> dict[str, Any]:
        from app.core.flow_chain import save_flow
        return save_flow(name, graph)

    def flow_execute(self, graph: dict[str, Any]) -> dict[str, Any]:
        from app.core.flow_chain import execute_graph
        return execute_graph(graph)

    def kamipack_export(self, name: str, payload: dict[str, Any], out_path: str, kind: str = "workflow") -> dict[str, Any]:
        from app.core.kamipack import export_kamipack
        return export_kamipack(name, payload, out_path, kind=kind)

    def kamipack_inspect(self, pack_path: str) -> dict[str, Any]:
        from app.core.kamipack import inspect_kamipack
        return inspect_kamipack(pack_path)

    def kamipack_import(self, pack_path: str, dest_dir: str = "") -> dict[str, Any]:
        from app.core.kamipack import import_kamipack
        return import_kamipack(pack_path, dest_dir=dest_dir or None)

    # ---------- Dalga C/D/E: Kami Oyun, Kami Muzik, Kami Suzgec ----------
    def _open_mod_window(self, key: str) -> dict[str, Any]:
        w = getattr(self, f"_{key}_win", None)
        maker = getattr(self, f"_make_{key}_window", None)
        if w is None and maker:
            w = maker()
            setattr(self, f"_{key}_win", w)
        front = getattr(self, f"_front_{key}", None)
        if front:
            try:
                front()
            except Exception:
                pass
        return {"ok": w is not None}

    def games_open(self) -> dict[str, Any]:
        return self._open_mod_window("games")

    def music_open(self) -> dict[str, Any]:
        return self._open_mod_window("music")

    def cleaner_open(self) -> dict[str, Any]:
        return self._open_mod_window("cleaner")

    def games_list(self, include_owned: bool = True) -> dict[str, Any]:
        from app.core.games import list_games, TRACKER
        TRACKER.ensure_started()
        r = list_games(include_owned=include_owned)
        # v1.35.4: Playnite'in diskteki kapaklari file:// geliyor; pywebview sayfasi file:// resim yukleyemiyor
        # (WebView2'de 0x0 dogrulandi). Yerel medya sunucusundan (127.0.0.1 + oturum anahtari) verilir.
        if self._media is not None:
            from urllib.parse import unquote, urlparse
            for g in r.get("games") or []:
                c = str(g.get("cover") or "")
                if c.startswith("file:"):
                    try:
                        fp = unquote(urlparse(c).path).lstrip("/") if os.name == "nt" else unquote(urlparse(c).path)
                        g["cover"] = self._media.asset_url(fp)
                    except Exception:
                        g["cover"] = ""
        return r

    def games_launch(self, launch_target: str, key: str = "") -> dict[str, Any]:
        from app.core.games import launch_game
        return launch_game(launch_target, key=key)

    def games_toggle_favorite(self, key: str) -> dict[str, Any]:
        from app.core.games import toggle_favorite
        return toggle_favorite(key)

    def games_backup_save(self, title: str, out_dir: str = "") -> dict[str, Any]:
        from app.core.games import backup_save_ludusavi
        return backup_save_ludusavi(title, out_dir)

    def games_set_sgdb_key(self, key: str) -> dict[str, Any]:
        from app.core.games import set_sgdb_key
        return set_sgdb_key(key)

    def games_keys_status(self) -> dict[str, Any]:
        from app.core.games import has_sgdb_key, has_steam_web
        return {"sgdb": has_sgdb_key(), "steam_web": has_steam_web()}

    def games_set_steam_web(self, api_key: str, steam_id: str) -> dict[str, Any]:
        from app.core.games import set_steam_web
        return set_steam_web(api_key, steam_id)

    def games_tracker_status(self) -> dict[str, Any]:
        from app.core.games import TRACKER
        TRACKER.ensure_started()
        return TRACKER.status()

    def games_set_auto_replay(self, enabled: bool) -> dict[str, Any]:
        from app.core.games import TRACKER
        return TRACKER.set_auto_replay(enabled)

    def games_import_playnite(self) -> dict[str, Any]:
        from app.core.games import import_playnite_library
        return import_playnite_library()

    def games_add_custom(self, title: str, exe_path: str) -> dict[str, Any]:
        from app.core.games import add_custom_game
        return add_custom_game(title, exe_path)

    def music_search(self, query: str, limit: int = 12) -> dict[str, Any]:
        from app.core.music_hub import search_ytmusic
        return search_ytmusic(query, limit=limit)

    def music_spotify_now(self) -> dict[str, Any]:
        from app.core.music_hub import spotify_now
        return spotify_now(str(self._manager.settings.get("spotify_token") or ""))

    def music_set_spotify_token(self, token: str) -> dict[str, Any]:
        from app.core.music_hub import set_spotify_token
        return set_spotify_token(token)

    def music_spotify_login(self, client_id: str) -> dict[str, Any]:
        from app.core.music_hub import spotify_login
        return spotify_login(client_id)

    def music_spotify_status(self) -> dict[str, Any]:
        from app.core.music_hub import spotify_oauth_status
        return spotify_oauth_status()

    def music_spotify_logout(self) -> dict[str, Any]:
        from app.core.music_hub import spotify_logout
        return spotify_logout()

    def music_spotify_control(self, action: str) -> dict[str, Any]:
        from app.core.music_hub import spotify_control
        return spotify_control(str(self._manager.settings.get("spotify_token") or ""), action)

    def music_lyrics(self, title: str, artist: str = "") -> dict[str, Any]:
        from app.core.music_hub import fetch_track_lyrics
        return fetch_track_lyrics(title, artist)

    def music_spotify_search(self, query: str, kind: str = "track,album,playlist", limit: int = 10) -> dict[str, Any]:
        from app.core.music_hub import spotify_search
        return spotify_search(query, kind=kind, limit=limit)

    def music_spotify_playlists(self, limit: int = 40) -> dict[str, Any]:
        from app.core.music_hub import spotify_playlists
        return spotify_playlists(limit=limit)

    def music_spotify_playlist_tracks(self, playlist_id: str, limit: int = 100) -> dict[str, Any]:
        from app.core.music_hub import spotify_playlist_tracks
        return spotify_playlist_tracks(playlist_id, limit=limit)

    def music_spotify_saved(self, limit: int = 50) -> dict[str, Any]:
        from app.core.music_hub import spotify_saved_tracks
        return spotify_saved_tracks(limit=limit)

    def music_spotify_recent(self, limit: int = 30) -> dict[str, Any]:
        from app.core.music_hub import spotify_recent_tracks
        return spotify_recent_tracks(limit=limit)

    def music_spotify_play(self, uri: str = "", context_uri: str = "", position_ms: int = 0) -> dict[str, Any]:
        from app.core.music_hub import spotify_play_uri
        return spotify_play_uri(uri=uri, context_uri=context_uri, position_ms=position_ms)

    def music_spotify_queue(self, uri: str) -> dict[str, Any]:
        from app.core.music_hub import spotify_queue_add
        return spotify_queue_add(uri)

    def music_spotify_playlist_create(self, name: str, description: str = "", public: bool = False) -> dict[str, Any]:
        from app.core.music_hub import spotify_playlist_create
        return spotify_playlist_create(name, description=description, public=public)

    def music_spotify_playlist_modify(self, playlist_id: str, uris: list[str], remove: bool = False) -> dict[str, Any]:
        from app.core.music_hub import spotify_playlist_modify
        return spotify_playlist_modify(playlist_id, uris, remove=remove)

    def music_spotify_playlist_details(self, playlist_id: str, name: str = "", description: str = "") -> dict[str, Any]:
        """Playlist adini ve/veya aciklamasini degistir."""
        from app.core.music_hub import spotify_playlist_details
        return spotify_playlist_details(playlist_id, name=name, description=description)

    def music_spotify_playlist_cover(self, playlist_id: str, image_b64: str) -> dict[str, Any]:
        """Playlist kapagini degistir (base64 JPEG)."""
        from app.core.music_hub import spotify_playlist_cover
        return spotify_playlist_cover(playlist_id, image_b64)

    def music_spotify_devices(self) -> dict[str, Any]:
        from app.core.music_hub import spotify_devices
        return spotify_devices()

    def music_spotify_transfer(self, device_id: str) -> dict[str, Any]:
        from app.core.music_hub import spotify_transfer
        return spotify_transfer(device_id)

    def music_spotify_seek(self, position_ms: int) -> dict[str, Any]:
        from app.core.music_hub import spotify_seek
        return spotify_seek(position_ms)

    def music_spotify_shuffle(self, state: bool) -> dict[str, Any]:
        from app.core.music_hub import spotify_shuffle
        return spotify_shuffle(state)

    def music_spotify_repeat(self, state: str) -> dict[str, Any]:
        from app.core.music_hub import spotify_repeat
        return spotify_repeat(state)

    def music_spotify_volume(self, percent: int) -> dict[str, Any]:
        from app.core.music_hub import spotify_volume
        return spotify_volume(percent)

    def music_spotify_like_check(self, track_id: str) -> dict[str, Any]:
        from app.core.music_hub import spotify_like_check
        return spotify_like_check(track_id)

    def music_spotify_like_toggle(self, track_id: str, like: bool) -> dict[str, Any]:
        from app.core.music_hub import spotify_like_toggle
        return spotify_like_toggle(track_id, like)

    def music_spotify_queue_list(self) -> dict[str, Any]:
        from app.core.music_hub import spotify_queue_list
        return spotify_queue_list()

    def music_spotify_album_tracks(self, album_id: str, limit: int = 50) -> dict[str, Any]:
        from app.core.music_hub import spotify_album_tracks
        return spotify_album_tracks(album_id, limit=limit)

    def music_local_add(self, folder: str = "") -> dict[str, Any]:
        from app.core.music_hub import local_folders_add
        if not folder and self._window:
            import webview
            res = self._window.create_file_dialog(webview.FileDialog.FOLDER)
            if not res:
                return {"ok": False, "error": "cancelled"}
            folder = res[0]
        return local_folders_add(folder)

    def music_local_remove(self, folder: str) -> dict[str, Any]:
        from app.core.music_hub import local_folders_remove
        return local_folders_remove(folder)

    def music_local_rename(self, folder: str, new_name: str) -> dict[str, Any]:
        """Yerel muzik klasorunun adini degistir."""
        from app.core.music_hub import local_folder_rename
        return local_folder_rename(folder, new_name)

    def music_local_cover(self, folder: str, image_b64: str) -> dict[str, Any]:
        """Yerel muzik klasorune folder.jpg kapak yazar."""
        from app.core.music_hub import local_folder_cover
        return local_folder_cover(folder, image_b64)

    def music_local_scan(self, folder: str = "", query: str = "", limit: int = 500) -> dict[str, Any]:
        from app.core.music_hub import local_scan_folder
        return local_scan_folder(folder=folder, query=query, limit=limit)

    def music_local_play(self, path: str, folder: str = "") -> dict[str, Any]:
        if folder and hasattr(self, "playlist_add_folder"):
            try:
                self.playlist_add_folder(folder)
            except Exception:
                pass
        return self.player_show({"path": path})

    def music_ytm_saved(self) -> list[dict[str, str]]:
        from app.core.music_hub import ytm_saved_playlists
        return ytm_saved_playlists()

    def music_ytm_playlist(self, url_or_id: str, limit: int = 2000) -> dict[str, Any]:
        from app.core.music_hub import ytm_get_playlist
        return ytm_get_playlist(url_or_id, limit=limit, save=True)

    def music_play_url(self, url: str) -> dict[str, Any]:
        """YT Music / web akisini Kami Player penceresinde acar ve calar."""
        u = str(url or "").strip()
        if not u:
            return {"ok": False, "error": "empty_url"}
        return self.player_show({"url": u})

    def music_download(self, url: str, title: str = "", fmt: str = "mp3") -> dict[str, Any]:
        """Kamify'dan dogrudan ses (MP3) indirmesi baslatir ve hedef klasoru doner."""
        u = str(url or "").strip()
        if not u:
            return {"ok": False, "error": "empty_url"}
        d = self._manager.add_media(
            u,
            options={"format": "mp3", "audio_kbps": "320", "no_playlist": True},
            title=str(title or ""),
            source="music",
        )
        return {"ok": True, "id": d.id, "dir": d.directory or str(self._manager.base_dir())}

    def music_ytm_to_spotify(self, url_or_id: str, new_name: str = "") -> dict[str, Any]:
        from app.core.music_hub import ytm_to_spotify_playlist
        return ytm_to_spotify_playlist(url_or_id, new_name=new_name)

    def music_librespot_status(self) -> dict[str, Any]:
        from app.core.librespot_host import status
        return status()

    def music_librespot_start(self) -> dict[str, Any]:
        from app.core.librespot_host import ensure_started
        return ensure_started(download=True)

    def music_librespot_reset(self) -> dict[str, Any]:
        from app.core.librespot_host import reset_credentials
        return reset_credentials()

    def acoustid_test(self, key: str = "") -> dict[str, Any]:
        """AcoustID API anahtarini gercek lookup ucunda dogrular (code 3=anahtar gecerli, code 4=gecersiz)."""
        import json as _json
        import urllib.error
        import urllib.parse
        import urllib.request
        k = str(key or self._manager.settings.get("acoustid_key") or "").strip()
        if not k:
            return {"ok": False, "error": "empty_key"}
        qs = urllib.parse.urlencode({"client": k, "duration": "120", "fingerprint": "AQAA", "meta": "recordings"})
        try:
            with urllib.request.urlopen(f"https://api.acoustid.org/v2/lookup?{qs}", timeout=6) as resp:
                data = _json.loads(resp.read().decode("utf-8", "replace"))
                return {"ok": data.get("status") == "ok"}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            try:
                err = (_json.loads(raw).get("error") or {})
                if err.get("code") == 3:
                    return {"ok": True}
                return {"ok": False, "error": err.get("message") or f"HTTP {exc.code}"}
            except Exception:
                return {"ok": False, "error": f"HTTP {exc.code}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:100]}

    def cleaner_search(self, query: str, root: str = "", limit: int = 80) -> dict[str, Any]:
        from app.core.cleaner import search_files
        return search_files(query, root=root, limit=limit)

    def cleaner_treemap(self, root: str = "") -> dict[str, Any]:
        from app.core.cleaner import disk_treemap
        return disk_treemap(root=root)

    def cleaner_trash(self, path: str) -> dict[str, Any]:
        from app.core.cleaner import trash_path
        return trash_path(path)

    # ---------- v1.38.0 Dalga 1: Hiz Profili, Bildirim Merkezi, Mini-Ada Kontrolleri ----------
    def _on_notify_dl(self, kind: str, title: str, download: Any) -> None:
        try:
            notifs = getattr(getattr(self._manager, "events", None), "notifications", None)
            if not notifs:
                return
            fname = str(getattr(download, "filename", "") or (download.get("filename", "") if isinstance(download, dict) else "") or getattr(download, "url", ""))
            did = getattr(download, "id", None) if not isinstance(download, dict) else download.get("id")
            notifs.push(kind, title, fname, {"id": did} if did is not None else None)
        except Exception:
            pass

    def notifications_list(self, limit: int = 60) -> dict[str, Any]:
        notifs = getattr(getattr(self._manager, "events", None), "notifications", None)
        if not notifs:
            return {"ok": True, "items": [], "unread": 0}
        return {"ok": True, "items": notifs.list(limit=int(limit)), "unread": notifs.unread_count()}

    def notifications_mark_read(self) -> dict[str, Any]:
        notifs = getattr(getattr(self._manager, "events", None), "notifications", None)
        if notifs:
            notifs.mark_all_read()
        return {"ok": True, "unread": 0}

    def notifications_clear(self) -> dict[str, Any]:
        notifs = getattr(getattr(self._manager, "events", None), "notifications", None)
        if notifs:
            notifs.clear()
        return {"ok": True, "unread": 0}

    def speed_profile_state(self) -> dict[str, Any]:
        profs = self._manager.settings.get("speed_profiles") or {}
        cur = str(self._manager.settings.get("speed_profile") or "full")
        return {
            "ok": True,
            "current": cur,
            "manual": getattr(self, "_manual_speed_profile", cur),
            "auto_reason": getattr(self, "_auto_speed_reason", ""),
            "profiles": profs,
        }

    def speed_profile_set(self, name: str, auto: bool = False, reason: str = "") -> dict[str, Any]:
        profs = self._manager.settings.get("speed_profiles") or {"full": 0, "stream": 15000, "game": 4000, "room": 8000, "night": 0}
        key = name if name in profs else "full"
        if not auto:
            self._manual_speed_profile = key
            self._auto_speed_reason = ""
        else:
            self._auto_speed_reason = reason
        try:
            self._manager.settings.set("speed_profile", key)
            kib = int(profs.get(key, 0) or 0)
            self._manager.settings.set("speed_limit_kib", kib)
            if self._engine and self._engine.running:
                self._engine.set_global(max_overall_download_limit=f"{kib}K")
        except Exception:
            pass
        return self.speed_profile_state()

    def _on_game_active_change(self, key: str, title: str = "") -> None:
        try:
            if key:
                self.speed_profile_set("game", auto=True, reason="game")
            elif getattr(self, "_auto_speed_reason", "") == "game":
                self.speed_profile_set(getattr(self, "_manual_speed_profile", "full"), auto=True, reason="")
        except Exception:
            pass

    def _island_lyric_for(self, title: str, artist: str, prog_ms: int) -> str:
        t, a = str(title or "").strip(), str(artist or "").strip()
        if not t:
            return ""
        ct, ca, clines = getattr(self, "_island_lyric_cache", ("", "", []))
        if (t, a) != (ct, ca):
            try:
                from app.core.music_hub import fetch_track_lyrics
                res = fetch_track_lyrics(t, a)
                clines = res.get("lines") or []
            except Exception:
                clines = []
            self._island_lyric_cache = (t, a, clines)
        sec = max(0.0, float(prog_ms or 0) / 1000.0)
        cur = ""
        for ln in clines:
            ts = float(ln.get("time") or ln.get("t") or 0.0)
            if ts <= sec + 0.35:
                cur = str(ln.get("text") or "").strip()
            else:
                break
        return cur[:90]

    def _update_music_thumbbar(self, playing: bool) -> None:
        if getattr(self, "_thumb_playing", None) is playing:
            return
        self._thumb_playing = playing
        try:
            from app.core import winwin, taskbar
            hwnd = winwin.find_window("Kamify")
            if hwnd:
                taskbar.set_thumb_buttons(hwnd, playing, lambda cmd: self.mini_island_music_cmd(cmd))
        except Exception:
            pass

    def mini_island_resize(self, w: int, h: int) -> dict[str, Any]:
        try:
            from app.core import winwin
            ok = winwin.resize_pill("Kami Mini-Ada", int(w), int(h), anchor_top_center=True)
            return {"ok": bool(ok)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:100]}

    def mini_island_music_cmd(self, act: str, pos_ms: int | None = None) -> dict[str, Any]:
        from app.core import music_hub
        a = str(act or "").lower().strip()
        if a == "seek" and pos_ms is not None:
            r = music_hub.spotify_seek(max(0, int(pos_ms)))
            try:
                if music_hub._LAST_NOW:
                    music_hub._LAST_NOW["progress_ms"] = max(0, int(pos_ms))
            except Exception:
                pass
            return r
        if a in ("prev", "previous"):
            a = "previous"
        elif a == "toggle":
            try:
                cur = music_hub.cached_now(allow_paused=True) or {}
            except TypeError:
                cur = music_hub.cached_now() or {}
            a = "pause" if cur.get("playing") else "play"
        r = music_hub.spotify_control("", a)
        try:
            if a in ("play", "pause") and music_hub._LAST_NOW:
                music_hub._LAST_NOW["playing"] = (a == "play")
                self._update_music_thumbbar(a == "play")
        except Exception:
            pass
        return r

    def mini_island_drop_action(self, action: str, paths: list[str] | None = None) -> dict[str, Any]:
        files = [str(p) for p in (paths or getattr(self, "_island_drop_files", []) or []) if str(p).strip()]
        if not files:
            return {"ok": False, "error": "no_files"}
        self._island_drop_files = []
        act = str(action or "player").lower().strip()
        first = files[0]
        try:
            if act == "player":
                self._play_request(first)
                return {"ok": True}
            if act == "picture":
                return self.picture_open(first)
            if act == "studio":
                res = self._open_mod_window("studio")
                try:
                    self.studio_import_media(first)
                except Exception:
                    pass
                return res
            if act == "convert":
                if hasattr(self, "convert_add"):
                    return self.convert_add(files)
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:120]}
        return {"ok": False, "error": "bad_action"}

    # ---------- v1.38.0 Dalga 3: Player (AnkiConnect / Picture / Studio Kopruleri) ----------
    def player_anki_mine(self, word: str, sentence: str, reading: str = "", meaning: str = "",
                         deck: str = "Kami", model: str = "Basic", audio_b64: str = "", image_b64: str = "") -> dict[str, Any]:
        from app.core.player_plus import anki_connect_mine
        return anki_connect_mine(word, sentence, reading=reading, meaning=meaning, deck=deck,
                                 model=model, audio_b64=audio_b64, image_b64=image_b64)

    def player_pick_file(self) -> str:
        w = self._player_win or self._window
        if not w:
            return ""
        try:
            import webview
            res = w.create_file_dialog(webview.OPEN_DIALOG, file_types=("Medya (*.mp4;*.mkv;*.webm;*.mov;*.avi;*.mp3;*.flac;*.wav;*.m4a)", "Tümü (*.*)"))
            return res[0] if res else ""
        except Exception:
            return ""

    def player_send_frame_picture(self, data_url: str, beautify: bool = True) -> dict[str, Any]:
        import base64, time as _t
        from app import paths
        raw = str(data_url or "")
        if "," in raw[:60]:
            raw = raw.split(",", 1)[1]
        if not raw:
            return {"ok": False, "error": "empty_image"}
        out = paths.DATA_DIR / "exports" / f"player_frame_{int(_t.time())}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(base64.b64decode(raw))
        r = self.picture_open(str(out))
        return {**r, "path": str(out), "beautify": bool(beautify)}

    def player_send_clip_studio(self, path: str, at_sec: float = 0.0) -> dict[str, Any]:
        res = self._open_mod_window("studio")
        try:
            if path:
                self.studio_import_media(str(path))
        except Exception:
            pass
        return {**res, "at": float(at_sec or 0.0)}

    # ---------- v1.38.0 Dalga 3: Kami Games (SGDB Kapak Secici + Save Snapshot Timeline) ----------
    def games_search_covers(self, query: str) -> dict[str, Any]:
        from app.core.games import sgdb_search_covers
        return sgdb_search_covers(str(query or ""))

    def games_set_cover(self, key: str, cover_url: str) -> dict[str, Any]:
        from app.core.games import set_custom_cover
        return set_custom_cover(str(key or ""), str(cover_url or ""))

    def games_save_snapshot(self, key: str, title: str = "", src_dir: str = "") -> dict[str, Any]:
        from app.core.games import create_save_snapshot
        return create_save_snapshot(str(key or ""), str(title or ""), str(src_dir or ""))

    def games_list_snapshots(self, key: str) -> list[dict[str, Any]]:
        from app.core.games import list_save_snapshots
        return list_save_snapshots(str(key or ""))

    def games_restore_snapshot(self, key: str, snap_id: str, dest_dir: str = "") -> dict[str, Any]:
        from app.core.games import restore_save_snapshot
        return restore_save_snapshot(str(key or ""), str(snap_id or ""), str(dest_dir or ""))

    # ---------- v1.38.0 Dalga 4: Picture Beautify / Pin / Lens Quick & Cleaner Pro ----------
    def picture_data_url(self, path: str) -> dict[str, Any]:
        import base64
        p = Path(str(path or ""))
        if not p.is_file():
            return {"ok": False, "error": "no_file"}
        ext = p.suffix.lower().lstrip(".")
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp",
                "gif": "image/gif", "bmp": "image/bmp"}.get(ext, "image/png")
        try:
            raw = p.read_bytes()
            return {"ok": True, "url": f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"}
        except OSError as exc:
            return {"ok": False, "error": str(exc)[:120]}

    def picture_save_data_url(self, data_url: str, orig_path: str = "", suffix: str = "_beautify") -> dict[str, Any]:
        import base64
        import io
        import time
        from PIL import Image
        s = str(data_url or "")
        if "," not in s or not s.startswith("data:image/"):
            return {"ok": False, "error": "bad_data_url"}
        try:
            raw = base64.b64decode(s.split(",", 1)[1], validate=True)
            im = Image.open(io.BytesIO(raw))
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:120]}
        op = Path(str(orig_path)) if orig_path else None
        if op and op.parent.is_dir():
            out_dir = op.parent
            stem = re.sub(r'[<>:"/\\|?*]', "_", op.stem)[:60] or "kami_image"
        else:
            out_dir = Path.home() / "Pictures" / "Kami"
            out_dir.mkdir(parents=True, exist_ok=True)
            stem = f"kami_{int(time.time())}"
        suf = re.sub(r'[^A-Za-z0-9_-]', "", str(suffix or "_beautify")) or "_beautify"
        target = out_dir / f"{stem}{suf}.png"
        idx = 2
        while target.exists():
            target = out_dir / f"{stem}{suf}_{idx}.png"
            idx += 1
        im.save(target, format="PNG")
        return {"ok": True, "path": str(target)}

    def picture_pin(self, path: str) -> dict[str, Any]:
        import base64
        import time
        from PIL import Image
        p = Path(str(path or ""))
        if not p.is_file():
            return {"ok": False, "error": "no_file"}
        try:
            with Image.open(p) as im:
                iw, ih = im.size
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:120]}
        scale = min(1.0, 480.0 / max(1, iw, ih))
        ww = max(180, int(round(iw * scale)))
        wh = max(135, int(round(ih * scale)))
        pid = f"pin_{int(time.time() * 1000)}"
        pins = getattr(self, "_pins", None)
        if pins is None:
            pins = {}
            self._pins = pins
        pins[pid] = {"path": str(p), "w": ww, "h": wh}
        maker = getattr(self, "_make_pin_window", None)
        if maker is not None:
            win = maker(pid, ww, wh)
            wins = getattr(self, "_pin_wins", None)
            if wins is None:
                wins = {}
                self._pin_wins = wins
            wins[pid] = win
        return {"ok": True, "pid": pid, "w": ww, "h": wh}

    def pin_info(self, pid: str = "") -> dict[str, Any]:
        pins = getattr(self, "_pins", {}) or {}
        if not pins:
            return {"ok": False}
        key = pid if pid in pins else next(reversed(pins))
        rec = pins[key]
        d = self.picture_data_url(rec["path"])
        return {"ok": bool(d.get("ok")), "pid": key, "url": d.get("url", ""), "w": rec["w"], "h": rec["h"]}

    def pin_resize(self, pid: str = "", w: int = 360, h: int = 270) -> dict[str, Any]:
        wins = getattr(self, "_pin_wins", {}) or {}
        key = pid if pid in wins else (next(reversed(wins)) if wins else "")
        win = wins.get(key)
        if win is not None and hasattr(win, "resize"):
            win.resize(max(160, int(w)), max(120, int(h)))
        return {"ok": win is not None}

    def pin_close(self, pid: str = "") -> dict[str, Any]:
        wins = getattr(self, "_pin_wins", {}) or {}
        pins = getattr(self, "_pins", {}) or {}
        key = pid if pid in wins else (next(reversed(wins)) if wins else "")
        pins.pop(key, None)
        win = wins.pop(key, None)
        if win is not None:
            threading.Thread(target=win.destroy, daemon=True).start()
        return {"ok": True}

    def lens_capture_quick(self) -> dict[str, Any]:
        shot = self.lens_screen_grab()
        if not shot:
            return {"ok": False, "error": "cancelled"}
        return self.lens_quick_show(shot)

    def lens_quick_show(self, path: str) -> dict[str, Any]:
        p = Path(str(path or ""))
        if not p.is_file():
            return {"ok": False, "error": "no_file"}
        self._lens_quick_path = str(p)
        maker = getattr(self, "_make_lens_quick_window", None)
        if maker is not None:
            old = getattr(self, "_lens_quick_win", None)
            if old is not None:
                try:
                    threading.Thread(target=old.destroy, daemon=True).start()
                except Exception:
                    pass
            maker()
        return {"ok": True, "path": str(p)}

    def lens_quick_info(self) -> dict[str, Any]:
        p = str(getattr(self, "_lens_quick_path", "") or "")
        if not p or not os.path.isfile(p):
            return {"ok": False}
        from PIL import Image
        with Image.open(p) as im:
            w, h = im.size
        d = self.picture_data_url(p)
        return {"ok": True, "path": p, "width": w, "height": h, "url": d.get("url", "")}

    def lens_quick_action(self, action: str) -> dict[str, Any]:
        p = str(getattr(self, "_lens_quick_path", "") or "")
        act = str(action or "").strip().lower()
        if act == "close":
            win = getattr(self, "_lens_quick_win", None)
            self._lens_quick_win = None
            if win is not None:
                threading.Thread(target=win.destroy, daemon=True).start()
            return {"ok": True}
        if not p or not os.path.isfile(p):
            return {"ok": False, "error": "no_file"}
        if act == "pin":
            return self.picture_pin(p)
        if act == "lens":
            return self.picture_open(p, lens=True)
        if act == "beautify":
            self.picture_open(p, lens=False)
            return {"ok": True, "message": "Picture penceresinde açıldı"}
        if act == "ocr":
            try:
                from app.core import ocr
                r = ocr.read_text(p)
                return {"ok": True, "text": str((r or {}).get("text") or "").strip()}
            except Exception as exc:
                return {"ok": False, "error": str(exc)[:120]}
        if act == "copy":
            if os.name == "nt":
                import base64
                # Yol, f-string/quoting yerine ortam degiskeni + EncodedCommand ile guvenli gecirilir
                ps = (
                    "Add-Type -AssemblyName System.Windows.Forms,System.Drawing; "
                    "$img = [System.Drawing.Image]::FromFile($env:KAMI_IMG); "
                    "[System.Windows.Forms.Clipboard]::SetImage($img); $img.Dispose()"
                )
                enc = base64.b64encode(ps.encode("utf-16le")).decode()
                subprocess.run(["powershell", "-NoProfile", "-EncodedCommand", enc], timeout=8,
                               env={**os.environ, "KAMI_IMG": p},
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                return {"ok": True, "message": "Panoya kopyalandı ✓"}
            return {"ok": False, "error": "unsupported"}
        if act == "save":
            import shutil
            import time
            dst_dir = Path.home() / "Pictures" / "Kami Captures"
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst = dst_dir / f"KamiCapture_{time.strftime('%Y%m%d_%H%M%S')}.png"
            shutil.copy2(p, dst)
            return {"ok": True, "path": str(dst), "message": f"Kaydedildi: {dst.name}"}
        return {"ok": False, "error": "bad_action"}

    def cleaner_drives(self) -> dict[str, Any]:
        from app.core import cleaner
        return cleaner.drive_summary()

    def cleaner_by_ext(self, root: str = "") -> dict[str, Any]:
        from app.core import cleaner
        return cleaner.by_ext(str(root or ""))

    def cleaner_largest(self, root: str = "", limit: int = 100) -> dict[str, Any]:
        from app.core import cleaner
        return cleaner.largest_files(str(root or ""), limit=int(limit or 100))

    def cleaner_duplicates(self, root: str = "") -> dict[str, Any]:
        from app.core import cleaner
        return cleaner.find_duplicates(str(root or ""))

    def cleaner_similar_images(self, root: str = "", threshold: int = 8) -> dict[str, Any]:
        from app.core import cleaner
        return cleaner.find_similar_images(str(root or ""), threshold=int(threshold or 8))

    def cleaner_caches(self) -> dict[str, Any]:
        from app.core import cleaner
        return cleaner.scan_safe_caches()

    def cleaner_preview(self, path: str) -> dict[str, Any]:
        from app.core import cleaner
        return cleaner.preview_file(str(path or ""))

    def cleaner_trash_many(self, paths_list: list[str]) -> dict[str, Any]:
        from app.core import cleaner
        ok_n, fail_n, errors = 0, 0, []
        for p in (paths_list or [])[:200]:
            r = cleaner.trash_path(str(p or ""))
            if r.get("ok"):
                ok_n += 1
            else:
                fail_n += 1
                errors.append(r.get("error", "fail"))
        return {"ok": fail_n == 0 or ok_n > 0, "trashed": ok_n, "failed": fail_n, "errors": errors[:5]}

    def cleaner_open_folder(self, path: str) -> bool:
        p = Path(str(path or ""))
        if not p.exists():
            return False
        if p.is_file():
            return self.open_path_folder(str(p))
        if os.name == "nt":
            subprocess.Popen(["explorer", str(p)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return True
        return False

    # ---------- Kami 2.0 (v2.0.0): Kami Dust, Klasor Bekcisi, MP3 Whisper LRC + Editor, B8 Scrobbler, A2/A3/Fitts/Snapshot ----------
    def cleaner_dust(self, min_idle_days: int = 21, min_size_kb: int = 128) -> dict[str, Any]:
        from app.core import cleaner
        return cleaner.scan_kami_dust(min_idle_days=int(min_idle_days or 21), min_size_kb=int(min_size_kb or 128))

    def cleaner_janitor(self, dry_run: bool = True) -> dict[str, Any]:
        from app.core import cleaner
        return cleaner.run_folder_janitor(download_dir=self._manager.base_dir(), dry_run=bool(dry_run))

    def games_scan_folder(self, folder: str) -> dict[str, Any]:
        from app.core import games
        return games.scan_folder_for_games(str(folder or ""), auto_add=True)

    def games_hltb(self, title: str) -> dict[str, Any]:
        from app.core import games
        return games.estimate_hltb(str(title or ""))

    def _notify_player_lyrics(self, path: str) -> None:
        """Acik Kami Player penceresine yan .lrc / USLT degistigini aninda bildirir."""
        w = getattr(self, "_player_win", None)
        if w is None:
            return
        try:
            js = f"window.plReloadLyrics?.({json.dumps(str(path or ''))});"
            threading.Thread(target=lambda: w.evaluate_js(js), name="kami-plyr-reload", daemon=True).start()
        except Exception:
            pass

    def music_lrc_read(self, path: str) -> dict[str, Any]:
        from app.core import lyrics
        return lyrics.read_local_lrc(str(path or ""))

    def music_lrc_save(self, path: str, lines_or_text: Any, artist: str = "", title: str = "") -> dict[str, Any]:
        from app.core import lyrics
        res = lyrics.save_edited_lrc(str(path or ""), lines_or_text, artist=str(artist or ""), title=str(title or ""),
                                     embed=bool(self._manager.settings.get("lyrics_embed", True)))
        if res.get("ok"):
            self._notify_player_lyrics(str(path or ""))
        return res

    def music_whisper_lrc(self, path: str, lang: str = "tr", strong: bool = True) -> dict[str, Any]:
        import uuid
        from app.core import aitools
        p = os.path.abspath(str(path or ""))
        if not p or not os.path.isfile(p):
            return {"ok": False, "error": "no_file"}
        if not aitools.installed("whisper"):
            return {"ok": False, "error": "tool_missing", "tool": "whisper"}
        jid = f"lrc_{uuid.uuid4().hex[:8]}"
        lang_s = str(lang or self._manager.settings.get("whisper_lang") or "tr")
        strong_b = bool(strong)
        model_s = str(self._manager.settings.get("whisper_model") or "large-v3-turbo")
        uvr_s = str(self._manager.settings.get("uvr_model") or "")
        embed_b = bool(self._manager.settings.get("lyrics_embed", True))
        uvr_eksik = strong_b and not aitools.installed("uvr")
        cancel_ev = threading.Event()
        with self._inbox_lock:
            self._lrc_cancels[jid] = cancel_ev
            self._jobs[jid] = {
                "state": "running",
                "name": f"LRC: {os.path.basename(p)}",
                # UVR istenip kurulu değilse kullanıcıyı uyar (eskiden sessizce vokalsiz çözüyordu)
                "msg": ("UVR5 kurulu değil — vokalsiz çözülüyor (Güçlü Mod devre dışı)" if uvr_eksik else "UVR5 + Whisper başlatıldı…"),
                "p": 0.05,
                "t": time.monotonic(),
                "result": None,
            }

        def _worker() -> None:
            def _on_prog(frac: float, stage: str) -> None:
                lbl = "UVR5 Vokal Ayırma…" if "uvr" in str(stage) else ("Whisper Çözümlüyor…" if stage == "whisper" else "Kaydediliyor…")
                with self._inbox_lock:
                    if jid in self._jobs:
                        self._jobs[jid]["p"] = float(frac)
                        self._jobs[jid]["msg"] = lbl
            try:
                res = aitools.generate_mp3_lrc(
                    p, lang=lang_s, strong=strong_b, use_uvr=strong_b,
                    model_name=model_s, uvr_model=uvr_s, embed=embed_b,
                    on_progress=_on_prog, cancel=cancel_ev,
                )
                if uvr_eksik:
                    res["uvr_missing"] = True
                with self._inbox_lock:
                    if jid in self._jobs:
                        if res.get("error") == "cancelled":
                            self._jobs[jid]["state"] = "cancelled"
                            self._jobs[jid]["msg"] = "İptal edildi"
                        else:
                            self._jobs[jid]["state"] = "done" if res.get("ok") else "error"
                            self._jobs[jid]["msg"] = "Hazır ✓" if res.get("ok") else str(res.get("error") or "hata")
                        self._jobs[jid]["p"] = 1.0 if res.get("ok") else self._jobs[jid].get("p", 0.0)
                        self._jobs[jid]["result"] = res
                if res.get("ok"):
                    self._notify_player_lyrics(p)
            except Exception as exc:
                with self._inbox_lock:
                    if jid in self._jobs:
                        self._jobs[jid]["state"] = "error"
                        self._jobs[jid]["msg"] = str(exc)[:180]
                        self._jobs[jid]["result"] = {"ok": False, "error": str(exc)[:180]}
            finally:
                self._lrc_cancels.pop(jid, None)

        threading.Thread(target=_worker, name=f"kami-{jid}", daemon=True).start()
        return {"ok": True, "queued": True, "job_id": jid, "path": p}

    def music_lrc_whisper(self, path: str, lang: str = "tr", strong: bool = True) -> dict[str, Any]:
        return self.music_whisper_lrc(path, lang=lang, strong=strong)

    def music_lrc_job_status(self, job_id: str) -> dict[str, Any]:
        with self._inbox_lock:
            j = self._jobs.get(str(job_id or ""))
            if not j:
                return {"ok": False, "error": "unknown_job"}
            return {"ok": True, **j}

    def music_lrc_cancel(self, job_id: str) -> dict[str, Any]:
        jid = str(job_id or "")
        ev = self._lrc_cancels.get(jid)
        if ev is not None:
            ev.set()
        with self._inbox_lock:
            if jid in self._jobs:
                self._jobs[jid]["state"] = "cancelled"
                self._jobs[jid]["msg"] = "İptal edildi"
        return {"ok": ev is not None}

    def music_lrc_polish_ollama(self, raw_lrc: str, title: str = "", artist: str = "") -> dict[str, Any]:
        from app.core import lyrics
        return lyrics.polish_lyrics_with_ollama(str(raw_lrc or ""), title=str(title or ""), artist=str(artist or ""))

    def music_lrc_ollama_polish(self, raw_lrc: str, title: str = "", artist: str = "") -> dict[str, Any]:
        return self.music_lrc_polish_ollama(raw_lrc, title=title, artist=artist)

    def _scrobble_file(self) -> Path:
        from app import paths
        return paths.DATA_DIR / "scrobble_history.json"

    def scrobbler_history(self, limit: int = 100) -> list[dict[str, Any]]:
        p = self._scrobble_file()
        try:
            if p.is_file():
                items = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(items, list):
                    return items[:int(limit or 100)]
        except Exception:
            pass
        return []

    def scrobbler_recognize_now(self) -> dict[str, Any]:
        """B8 Sistem Sesi Arka Plan (Calan Sarki Gunlugu) — Ctrl+Shift+G kisayolu veya Kamify dugmesi ile tetiklenir."""
        res = self.song_identify("")
        if not res.get("ok") or not res.get("song"):
            return res
        s = res["song"]
        entry = {
            "title": str(s.get("title") or ""),
            "artist": str(s.get("artist") or ""),
            "ts": int(time.time()),
        }
        cur = self.scrobbler_history(200)
        if not cur or (cur[0].get("title") != entry["title"] or cur[0].get("artist") != entry["artist"]):
            cur.insert(0, entry)
            p = self._scrobble_file()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(cur[:200], ensure_ascii=False, indent=2), encoding="utf-8")
            # ListenBrainz scrobbling (token ayarliysa)
            try:
                self.scrobble_send(entry["artist"], entry["title"], "", 0, False)
            except Exception:
                pass
        return {"ok": True, "song": entry, "history_count": len(cur)}

    def scrobble_send(self, artist: str, title: str, album: str = "", duration: int = 0, playing: bool = False) -> dict[str, Any]:
        """ListenBrainz scrobbling: dinlenen sarkiyi gonder (playing_now veya scrobble). Token bos = no-op."""
        token = str(self._manager.settings.get("listenbrainz_token") or "").strip()
        if not token or not title:
            return {"ok": False, "error": "no_token"}
        import requests
        meta = {"artist_name": str(artist or ""), "track_name": str(title or "")}
        if album:
            meta["release_name"] = str(album)
        if playing:
            body = {"listen_type": "playing_now", "payload": [{"track_metadata": meta}]}
        else:
            body = {"listen_type": "single", "payload": [{"listened_at": int(time.time()), "track_metadata": meta}]}
        try:
            r = requests.post("https://api.listenbrainz.org/1/submit-listens", json=body,
                              headers={"Authorization": f"Token {token}", "Content-Type": "application/json"}, timeout=15)
            return {"ok": r.status_code in (200, 202), "status": r.status_code}
        except requests.RequestException as exc:
            return {"ok": False, "error": str(exc)[:120]}

    def listenbrainz_test(self, token: str = "") -> dict[str, Any]:
        """ListenBrainz token'ini validate-token ucunda dogrular."""
        import requests
        t = str(token or self._manager.settings.get("listenbrainz_token") or "").strip()
        if not t:
            return {"ok": False, "error": "empty_token"}
        try:
            r = requests.get("https://api.listenbrainz.org/1/validate-token",
                             headers={"Authorization": f"Token {t}"}, timeout=10)
            if r.status_code == 200:
                d = r.json()
                return {"ok": True, "user": d.get("user_name") or d.get("user") or ""}
            return {"ok": False, "error": f"http_{r.status_code}"}
        except requests.RequestException as exc:
            return {"ok": False, "error": str(exc)[:120]}

    def active_jobs_hud(self) -> dict[str, Any]:
        """A3 Birlesik Arka Plan Islem & Kuyruk HUD'u: Ortada aktif is yokken count=0 doner ve HUD tamamen gizlenir."""
        jobs_out: list[dict[str, Any]] = []
        # 1) Aktif indirmeler
        for d in self._manager.snapshot():
            if str(getattr(d, "status", "")) == "active" or getattr(getattr(d, "status", None), "value", "") == "active":
                pct = int(round((d.downloaded / d.size) * 100)) if d.size else 0
                jobs_out.append({"id": f"dl_{d.id}", "kind": "İndirme", "title": d.filename or d.url, "pct": pct})
        # 2) AI isleri (Whisper / UVR / Lyrics)
        for d in self._manager.snapshot():
            ex = d.extra or {}
            for ak, albl in (("whisper", "Whisper Altyazı"), ("uvr", "UVR5 Vokal"), ("lyrics", "Şarkı Sözü AI")):
                if ex.get(f"ai_{ak}") in ("running", "queued"):
                    pct = int(round(float(ex.get(f"ai_{ak}_p") or 0) * 100))
                    jobs_out.append({"id": f"ai_{ak}_{d.id}", "kind": albl, "title": d.filename or "", "pct": pct})
        # 3) Donusturucu isleri
        with self._conv_lock:
            for cj in self._conv_jobs:
                if cj.get("state") in ("running", "queued"):
                    jobs_out.append({"id": cj["id"], "kind": "Dönüştürücü", "title": cj.get("name", ""), "pct": int(round(float(cj.get("p") or 0) * 100))})
        # 4) Yalnızca uzun/kullanici odakli arka plan isleri (player_lyrics / player_skips / rd_status gibi sessiz RPC yoklamalari haric)
        import time as _t
        hud_long = frozenset({
            "music_whisper_lrc", "pic_ai", "pic_freq_sep", "pic_seam_carve", "pic_clone_lut",
            "pic_hdr_merge", "pic_focus_stack", "pic_ecom_pack", "pic_mockup", "editor_vectorize",
            "editor_gif", "editor_export", "backup_export", "backup_import", "media_extract_audio",
            "media_clip", "media_repair", "ocr_image", "ocr_translate", "cleaner_dust",
            "cleaner_janitor", "install_update", "studio_export", "studio_render",
            "studio_build_preview", "studio_scenes", "studio_silences", "studio_freezes", "studio_beats",
        })
        now_m = _t.monotonic()
        with self._inbox_lock:
            for jid, jinfo in self._jobs.items():
                if jinfo.get("state") != "running":
                    continue
                jname = str(jinfo.get("name") or "")
                is_lrc = str(jid).startswith("lrc_")
                if not (is_lrc or jname in hud_long):
                    continue
                if "t" in jinfo and (now_m - float(jinfo["t"])) >= 900:
                    continue
                if is_lrc or jname == "music_whisper_lrc":
                    kind_lbl = "AI Altyazı"
                elif jname == "cleaner_dust":
                    kind_lbl = "Kami Dust"
                elif jname.startswith("studio_"):
                    kind_lbl = "Kami Studio"
                else:
                    kind_lbl = "İşlem"
                pct = int(round(float(jinfo.get("p") or 0.5) * 100))
                jobs_out.append({"id": jid, "kind": kind_lbl, "title": jname, "pct": pct})
        return {"ok": True, "count": len(jobs_out), "items": jobs_out}

    def scratchpad_load(self) -> dict[str, Any]:
        """A2 Zaman/Sayfa Damgali Yuzen Karalama Karti verisini yukler."""
        from app import paths
        p = paths.DATA_DIR / "scratchpad.json"
        try:
            if p.is_file():
                return {"ok": True, "notes": json.loads(p.read_text(encoding="utf-8"))}
        except Exception:
            pass
        return {"ok": True, "notes": []}

    def scratchpad_add(self, text: str, context: str = "", target_path: str = "", stamp: str = "") -> dict[str, Any]:
        from app import paths
        t = str(text or "").strip()
        if not t:
            return {"ok": False, "error": "empty"}
        cur = self.scratchpad_load().get("notes") or []
        item = {
            "id": int(time.time() * 1000),
            "text": t,
            "context": str(context or "Sunak"),
            "path": str(target_path or ""),
            "stamp": str(stamp or time.strftime("%H:%M:%S")),
            "ts": int(time.time()),
        }
        cur.insert(0, item)
        p = paths.DATA_DIR / "scratchpad.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cur[:120], ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "item": item, "notes": cur[:120]}

    def scratchpad_delete(self, note_id: int) -> dict[str, Any]:
        from app import paths
        cur = [n for n in (self.scratchpad_load().get("notes") or []) if int(n.get("id") or 0) != int(note_id or 0)]
        p = paths.DATA_DIR / "scratchpad.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "notes": cur}

    def session_snapshot_save(self, name: str = "Son Oturum") -> dict[str, Any]:
        """#16 Oturum Snapshot: Acik Reader belgesi, Studio projesi ve aktif hiz profilini kaydeder."""
        from app import paths
        from app.core import reader
        rec_books = reader.recent(3)
        rec_studio = self.studio_recent()[:3] if hasattr(self, "studio_recent") else []
        snap = {
            "name": str(name or "Oturum"),
            "ts": int(time.time()),
            "speed_profile": str(self._manager.settings.get("speed_profile") or "full"),
            "active_profile": str(self._manager.settings.get("active_profile") or "kisisel"),
            "book": rec_books[0] if rec_books else None,
            "studio": rec_studio[0] if rec_studio else None,
        }
        p = paths.DATA_DIR / "session_snapshot.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "snapshot": snap}

    def session_snapshot_restore(self) -> dict[str, Any]:
        from app import paths
        p = paths.DATA_DIR / "session_snapshot.json"
        if not p.is_file():
            return {"ok": False, "error": "no_snapshot"}
        try:
            snap = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:100]}
        if snap.get("speed_profile"):
            self.speed_profile_set(snap["speed_profile"])
        if snap.get("book") and snap["book"].get("path") and os.path.exists(snap["book"]["path"]):
            self.reader_show(snap["book"]["path"])
        return {"ok": True, "snapshot": snap}

    # ---------- AI Altyazi / Vokal / MP3 Zaman Damgali Lirik Surukle-Birak Studyosu ----------
    def ai_drop_view(self, on: bool = True) -> bool:
        self._ai_drop_view = bool(on)
        return self._ai_drop_view

    def ai_drop_add(self, paths_list: list[str]) -> None:
        with self._conv_lock:
            cur = getattr(self, "_ai_drop_inbox", [])
            self._ai_drop_inbox = cur + [str(p) for p in (paths_list or []) if p and os.path.isfile(str(p))]

    def ai_drop_inbox(self) -> list[str]:
        with self._conv_lock:
            got = list(getattr(self, "_ai_drop_inbox", []))
            self._ai_drop_inbox = []
        return got

    def ai_drop_pick(self) -> list[str]:
        import webview
        if not self._window:
            return []
        dialog = getattr(getattr(webview, "FileDialog", None), "OPEN", None) or webview.OPEN_DIALOG
        res = self._window.create_file_dialog(dialog, allow_multiple=True)
        return [str(p) for p in (res or []) if p and os.path.isfile(str(p))]

    def games_fullscreen(self, on: bool = True) -> dict[str, Any]:
        from app.core import winwin
        ok = winwin.set_fullscreen("Kami Games", bool(on))
        return {"ok": bool(ok), "fullscreen": bool(on)}


