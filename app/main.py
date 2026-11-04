"""Kami giris noktasi:  .venv\\Scripts\\python.exe -m app.main"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import threading

from app import paths
from app.core.bridge_server import BridgeServer, call_running_instance
from app.core.events import EventBus
from app.core.manager import DownloadManager
from app.core.plugin_loader import load_plugins
from app.core.queue_store import DownloadStore
from app.core.settings import Settings
from app.engines.aria2_engine import Aria2Engine
from app.ui.api import Api

log = logging.getLogger("kami")


def _setup_logging() -> None:
    handler = logging.handlers.RotatingFileHandler(paths.LOG_PATH, maxBytes=2_000_000, backupCount=2,
                                                   encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if sys.stderr:
        root.addHandler(logging.StreamHandler())


def _magnet_arg(argv: list[str]) -> str:
    """Windows magnet: isleyicisi -> kami_open.pyw --magnet "<link>"."""
    for i, a in enumerate(argv):
        if a == "--magnet" and i + 1 < len(argv):
            return argv[i + 1]
        if a.lower().startswith("magnet:?"):
            return a
    return ""


def main() -> int:
    paths.ensure_dirs()
    _setup_logging()
    magnet = _magnet_arg(sys.argv[1:])

    # Tek ornek: zaten calisiyorsa onu one getir ve cik
    if call_running_instance(paths.BRIDGE_INFO_PATH, "/v1/ping"):
        try:   # on plandaki biz: calisan Kami'nin one gelmesine izin ver
            import json as _json
            from app.core.winwin import allow_foreground
            allow_foreground(_json.loads(paths.BRIDGE_INFO_PATH.read_text(encoding="utf-8")).get("pid"))
        except Exception:
            pass
        if magnet:
            res = call_running_instance(paths.BRIDGE_INFO_PATH, "/v1/rd", {"url": magnet, "source": "magnet"},
                                        timeout=5.0)
            log.info("Magnet calisan Kami'ye iletildi: %s", bool(res and res.get("ok")))
        if "--tray" not in sys.argv[1:]:
            call_running_instance(paths.BRIDGE_INFO_PATH, "/v1/show")
        log.info("Kami zaten calisiyor; pencere one getirildi.")
        return 0

    import webview  # GUI yalnizca gerektiginde yuklensin

    # IPv6'si olmayan agda her AAAA adresi 21 sn bekletiyordu (RD 42 sn). IPv4 once; IPv6 hic yoksa aria2'de kapat.
    settings = Settings()
    from app.core import net
    net.prefer_ipv4()
    no_v6 = not settings.get("aria2_ipv6") or not net.ipv6_works()
    if no_v6:
        log.info("aria2: IPv6 kapali (ayar ya da IPv6 yok)")

    events = EventBus()
    bt_port = settings.get("torrent_port") or settings.get("torrent_port_last")
    if not bt_port:   # otomatik: bir kez sec, sonra hep ayni port (DHT dugumu + guvenlik duvari)
        import random
        bt_port = random.randint(6881, 6999)
        settings.set("torrent_port_last", bt_port)
    from app.core import torrent as _torrent
    _torrent.set_tracker_file(paths.DATA_DIR / "trackers.txt")
    if settings.get("torrent_tracker_update"):
        threading.Thread(target=_torrent.update_trackers, name="kami-trackers", daemon=True).start()
    engine = Aria2Engine(
        paths.ARIA2_EXE,
        connections=settings.get("connections"),
        max_concurrent=settings.get("max_concurrent"),
        max_tries=settings.get("max_tries"),
        speed_limit_kib=settings.get("speed_limit_kib"),
        log_file=paths.DATA_DIR / "aria2.log",
        bt_port=bt_port,
        upload_limit_kib=settings.get("torrent_upload_limit_kib"),
        dht_file=paths.DATA_DIR / "dht.dat",
        disable_ipv6=no_v6,
    )
    engine.start_service()
    registry = load_plugins(paths.PLUGINS_DIR, events, settings)
    store = DownloadStore(paths.DB_PATH)
    from app.engines import ytdlp_engine
    if settings.get("ytdlp_autoupdate"):
        ytdlp_engine.start_self_update(24, settings)
    media = ytdlp_engine.MediaRunner(engine, max_concurrent=settings.get("max_concurrent"),
                                     connections_getter=lambda: int(settings.get("connections")))
    manager = DownloadManager(store, engine, events, settings, registry, media=media)
    # yt-dlp importu + ~1800 cikarici regex'inin ilk derlenmesi ~0.6 sn: pano kontrolu (link_supported) hep <10 ms olsun
    threading.Thread(target=ytdlp_engine.is_supported, args=("https://kami.invalid/isinma",),
                     name="kami-ytdlp-warm", daemon=True).start()
    from app.core.debrid import DebridService, TokenStore
    debrid = DebridService(TokenStore(paths.DATA_DIR / "rd_token.bin"), paths.DATA_DIR / "rd_pending.json")
    debrid.enqueue = manager.add_debrid_files
    manager.debrid = debrid
    from app.core.torrent import TorrentService
    manager.torrents = TorrentService(engine, paths.DATA_DIR / "torrents")

    # Pencereyi one getirme: Win32 ile, cagirani (kopru) BEKLETMEDEN. pywebview on_top/restore/show
    # arayuz is parcacigini bekliyor ve evaluate_js ile kilitlendi (defter 23).
    from app.core.winwin import WindowFront
    front = WindowFront("Kami")

    def show_window() -> None:
        front.request()

    from app.core.vault import CookieStore
    from app.engines import ytdlp_engine
    ytdlp_engine.COOKIES = CookieStore(paths.DATA_DIR / "yt_cookies.bin")

    bridge = BridgeServer(manager, paths.BRIDGE_INFO_PATH, on_show=show_window)

    def on_setting(key, value):
        try:
            if key == "connections":
                engine.connections = int(value)
                engine.set_global(split=value, max_connection_per_server=value)
            elif key == "max_concurrent":
                engine.set_global(max_concurrent_downloads=value)
            elif key == "speed_limit_kib":
                engine.set_global(max_overall_download_limit=f"{int(value)}K")
            elif key == "max_tries":
                engine.set_global(max_tries=value)
            elif key == "torrent_upload_limit_kib":
                engine.set_global(max_overall_upload_limit=f"{int(value)}K")
        except Exception:
            log.exception("Ayar motora uygulanamadi: %s", key)

    settings.on_change(on_setting)
    events.on("ui.attention", lambda reason: show_window())

    api = Api(manager, engine, registry, lambda: bridge.port)
    start_hidden = "--tray" in sys.argv[1:]
    window = webview.create_window(
        "Kami",
        url=str(paths.WEB_DIR / "index.html"),
        js_api=api,
        width=1180, height=740, min_size=(820, 520),
        background_color="#0D0A12" if settings.get("theme") == "dark" else "#F5F3F9",
        text_select=False,
        minimized=start_hidden,
    )
    api._set_window(window)

    from app.core import desktop, winwin
    from app.core.watchdog import UiWatchdog

    # ---- sistem tepsisi + X ile tepsiye gizleme
    quitting = {"v": False}

    def pause_all() -> None:
        api.pause_all()

    def resume_all() -> None:
        api.resume_all()

    def quit_app() -> None:
        quitting["v"] = True
        try:
            window.destroy()
        except Exception:
            log.exception("Pencere kapatilamadi")

    tray = desktop.Tray(show_window, pause_all, resume_all, quit_app, lambda: settings.get("language"))
    if settings.get("tray_enabled"):
        tray.start()

    def on_closing():
        if not quitting["v"] and settings.get("close_to_tray") and tray.running:
            winwin.hide(front._hwnd())   # arayuz is parcacigindayiz; Async: beklemez
            return False                 # kapatmayi iptal et
        quitting["v"] = True
        return None

    window.events.closing += on_closing
    if start_hidden:   # Windows'la baslama: tepside basla (kucuk acilir, hemen gizlenir)
        window.events.shown += lambda: winwin.hide(front._hwnd()) if tray.running else None

    # Kapanista arayuzun yarida kalan api cevabi (500 ms tick) olu GUI is parcacigina donmeye calisir:
    # pywebview "Error occurred in script / InvalidAsynchronousStateException" loglar. Zararsiz -> sustur.
    logging.getLogger("pywebview").addFilter(
        lambda rec: not (quitting["v"] and "Error occurred in script" in rec.getMessage()))

    # ---- genel kisayol: one getir + panodaki desteklenen linki sor
    def on_hotkey() -> None:
        show_window()
        try:
            from app.core.clipboard import get_text
            txt = (get_text() or "").strip()
            if txt and len(txt) < 4000 and api.link_supported(txt):
                with api._inbox_lock:
                    api._clip_offers.append(txt)
        except Exception:
            log.exception("Kisayol: pano okunamadi")

    hotkey = desktop.HotKey(on_hotkey)
    api._hotkey = hotkey
    if settings.get("hotkey_enabled"):
        hotkey.start(settings.get("hotkey"))

    # Windows'la baslama ayari kayit defteriyle esit olsun (kullanici elle silmis olabilir)
    try:
        if bool(settings.get("autostart")) != desktop.autostart_enabled():
            desktop.set_autostart(bool(settings.get("autostart")))
    except OSError:
        log.exception("Windows'la baslama ayarlanamadi")

    def on_desktop_setting(key, value):
        try:
            if key == "tray_enabled":
                tray.start() if value else tray.stop()
            elif key == "autostart":
                desktop.set_autostart(bool(value))
            elif key in ("hotkey", "hotkey_enabled"):
                if settings.get("hotkey_enabled"):
                    hotkey.start(settings.get("hotkey"))
                else:
                    hotkey.stop()
        except Exception:
            log.exception("Masaustu ayari uygulanamadi: %s", key)

    settings.on_change(on_desktop_setting)

    # ---- zamanlayici, bitis sonrasi (SHA256 + Defender + bildirim), guncelleme denetimi
    from app.core.extras import Scheduler
    from app.core.postcomplete import PostComplete
    scheduler = Scheduler(settings, resume_all, pause_all)
    scheduler.start()
    post = PostComplete(manager, tray.notify,
                        focused=lambda: winwin.is_foreground(front._hwnd()))

    # ---- Asama 6b: soz + muzik arsivi + Whisper/UVR (alt surecte, sirali GPU kuyrugu)
    from app.core import aitools
    from app.core.debrid import TokenStore
    from app.core.mediapost import MediaPost
    genius = TokenStore(paths.DATA_DIR / "genius_token.bin")
    media_post = MediaPost(manager, None, genius.load)
    ai = aitools.AiQueue(settings, media_post.set_extra,
                         lambda did: (manager.store.get(did).path if manager.store.get(did) else ""),
                         notify=api._on_ai_event)
    media_post.ai = ai
    post.media = media_post
    api._media_post, api._ai, api._genius = media_post, ai, genius
    ytdlp_engine.SOCIAL_COOKIES = lambda: bool(settings.get("social_cookies"))
    from app.core.follow import FollowService
    follow = FollowService(paths.DATA_DIR / "follows.json", settings,
                           lambda url, opts, title: manager.add_media(url, options={**manager.default_media_options(),
                                                                                    **opts},
                                                                      title=title, source="follow"),
                           notify=api._on_ai_event)
    api._follow = follow
    follow.start()

    # ---- Asama 6c: gecmis, bitince isler, kapatma, link yenileme, izle, telefon, ntfy, kurallar
    from app.core import automate
    from app.core.linkrefresh import LinkRefresher
    from app.core.phone import PhoneServer, new_key
    from app.core.watch import Watcher, play as _play
    if not settings.get("rules_seeded"):
        from app.core.rules import DEFAULT_RULES
        if not settings.get("site_rules"):
            settings.set("site_rules", DEFAULT_RULES)
        settings.set("rules_seeded", True)
    history = automate.History(paths.DATA_DIR / "history.db")
    manager.history = history
    manager.link_refresher = LinkRefresher(manager)
    ntfy_topic = TokenStore(paths.DATA_DIR / "ntfy_topic.bin")
    post.after.append(automate.AfterActions(manager, history, ntfy_topic.load, media_post.music_dir))

    def queue_done() -> None:
        if settings.get("ntfy_enabled") and settings.get("ntfy_queue"):
            automate.ntfy_send(settings.get("ntfy_server"), ntfy_topic.load(), "Kami", "Kuyruk bitti ✓", "tada")

    shutdown = automate.ShutdownWatcher(
        manager, busy_extra=lambda: bool(ai._cancel), on_queue_done=queue_done)
    shutdown.start()
    watcher = Watcher(manager, media_post.set_extra,
                      player=lambda p: _play(p, settings.get("watch_player") or "screenbox"))
    phone_key = TokenStore(paths.DATA_DIR / "phone_key.bin")
    phone = PhoneServer(int(settings.get("phone_port")), phone_key.load,
                        lambda text, fmt="": api.add_text_detail(text, "phone", fmt),
                        status=api.phone_status_items, control=api.phone_control)

    def phone_apply() -> None:
        if settings.get("phone_enabled"):
            if not phone_key.load():
                phone_key.save(new_key())
            phone.port = int(settings.get("phone_port"))
            phone.start()
        else:
            phone.stop()

    phone_apply()
    settings.on_change(lambda k, v: phone_apply() if k in ("phone_enabled", "phone_port") else None)
    api._history, api._shutdown, api._watcher = history, shutdown, watcher
    api._phone, api._phone_key, api._ntfy = phone, phone_key, ntfy_topic

    def tray_warn(**kw) -> None:
        if kw.get("kind") == "disk" and not winwin.is_foreground(front._hwnd()):
            tray.notify("Kami", f"Disk dolacak: {kw.get('name', '')[:80]}")
    events.on("ui.warn", tray_warn)
    post.start()

    def update_loop() -> None:
        import time as _t
        _t.sleep(30)
        while True:
            if settings.get("update_check") and _t.time() - int(settings.get("update_last") or 0) > 86400:
                try:
                    api.check_update()
                except Exception:
                    log.exception("Guncelleme denetimi")
            _t.sleep(3600)

    threading.Thread(target=update_loop, name="kami-update", daemon=True).start()

    api._watchdog = UiWatchdog(lambda: winwin.is_visible(front._hwnd()))
    api._watchdog.start()
    manager.start()
    debrid.start()
    bridge.start()
    api._start_clipboard()
    if magnet:   # Kami kapaliyken magnet linkine tiklandi
        threading.Thread(target=bridge.handle, args=("/v1/rd", {"url": magnet, "source": "magnet"}),
                         daemon=True).start()
    try:
        webview.start(debug=bool(os.environ.get("KAMI_DEBUG")), private_mode=False,
                      storage_path=str(paths.DATA_DIR / "webview"))
    finally:
        log.info("Kami kapaniyor")
        hotkey.stop()
        tray.stop()
        scheduler.stop()
        shutdown.stop()      # kapali veritabanina dokunmasin
        follow.stop()
        phone.stop()
        bridge.stop()
        debrid.stop()
        manager.stop()
        engine.shutdown()
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
