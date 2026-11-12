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
    # Paketli (konsolsuz) Kami'de cokme izsiz kalmasin: yakalanmayan istisnalar + yerel cokmeler log'a
    sys.excepthook = lambda t, v, tb: logging.getLogger("kami").critical("Yakalanmayan hata", exc_info=(t, v, tb))
    threading.excepthook = lambda a: logging.getLogger("kami").critical(
        "Thread hatasi (%s)", a.thread.name if a.thread else "?", exc_info=(a.exc_type, a.exc_value, a.exc_traceback))
    try:
        import faulthandler
        global _FAULT_FILE
        _FAULT_FILE = open(paths.DATA_DIR / "crash.log", "a", encoding="utf-8")   # noqa: SIM115
        faulthandler.enable(_FAULT_FILE)
    except Exception:
        pass


_FAULT_FILE = None


def _magnet_arg(argv: list[str]) -> str:
    """Windows magnet: isleyicisi -> kami_open.pyw --magnet "<link>"."""
    for i, a in enumerate(argv):
        if a == "--magnet" and i + 1 < len(argv):
            return argv[i + 1]
        if a.lower().startswith("magnet:?"):
            return a
    return ""


def _play_arg(argv: list[str]) -> str:
    """Kami Player: Kami.exe --play "<dosya>" (dosya iliskilendirme) ya da dogrudan medya dosyasi yolu."""
    from app.core.media_server import AUDIO_EXT, VIDEO_EXT
    for i, a in enumerate(argv):
        if a == "--play" and i + 1 < len(argv):
            return argv[i + 1]
        if not a.startswith("-") and os.path.splitext(a)[1].lower() in VIDEO_EXT | AUDIO_EXT and os.path.isfile(a):
            return a
    return ""


IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif", ".jfif", ".heic", ".tif", ".tiff")


def _view_arg(argv: list[str]) -> str:
    """Fotograf goruntuleyici: Kami.exe --view "<gorsel>" ya da dogrudan gorsel yolu ("Birlikte ac")."""
    for i, a in enumerate(argv):
        if a == "--view" and i + 1 < len(argv):
            return os.path.abspath(argv[i + 1])
        if not a.startswith("-") and a.lower().endswith(IMAGE_EXT) and os.path.isfile(a):
            return os.path.abspath(a)
    return ""


_MUTEX = None
_MUTEX_OTHER: bool | None = None   # ilk mutex denemesinin sonucu (tekrar cagrilinca ayni)


def _already_running_mutex() -> bool:
    """True: ayni oturumda baska Kami zaten mutex'i tutuyor. Kendi mutex'imiz surec boyunca acik kalir."""
    global _MUTEX, _MUTEX_OTHER
    if os.name != "nt":
        return False
    if _MUTEX_OTHER is not None:   # ikinci cagri: kendi tuttugumuz mutex'i "baskasi" sanmayalim
        return _MUTEX_OTHER
    import ctypes
    _MUTEX = ctypes.windll.kernel32.CreateMutexW(None, False, r"Local\KamiSingleInstance")
    _MUTEX_OTHER = ctypes.windll.kernel32.GetLastError() == 183   # ERROR_ALREADY_EXISTS
    return _MUTEX_OTHER


def main() -> int:
    paths.setup_frozen()
    paths.ensure_dirs()
    _setup_logging()
    if "--setup" in sys.argv[1:]:   # Inno Setup: native host + magnet kaydi / kaldirma (pencere acilmaz)
        from app.core import setup_tasks
        return setup_tasks.run(sys.argv[1:])
    if "--selfcheck-whisper" in sys.argv[1:]:   # once calisan Kami'nin ICINDE dene (gercek ortam), yoksa bu surecte
        import json as _json
        _i = sys.argv.index("--selfcheck-whisper") + 1
        _file = sys.argv[_i] if _i < len(sys.argv) else ""
        out = call_running_instance(paths.BRIDGE_INFO_PATH, "/v1/selfcheck-whisper", {"path": _file}, timeout=1800)
        if out is None:
            from app.core import aitools
            out = {"ok": True, "local": True, "result": aitools.selfcheck_whisper(_file)}
        (paths.DATA_DIR / "selfcheck.txt").write_text(_json.dumps(out, ensure_ascii=False), encoding="utf-8")
        return 0
    if "--quit" in sys.argv[1:]:    # kurulum/kaldirma: calisan Kami'yi duzgun kapat, kapanana kadar bekle
        import json as _json
        import time as _time
        try:
            pid = int(_json.loads(paths.BRIDGE_INFO_PATH.read_text(encoding="utf-8")).get("pid") or 0)
        except (OSError, ValueError):
            pid = 0
        if call_running_instance(paths.BRIDGE_INFO_PATH, "/v1/quit"):
            from app.core.winwin import pid_alive
            for _ in range(100):   # en fazla 10 sn
                if not pid or not pid_alive(pid):
                    break
                _time.sleep(0.1)
            _time.sleep(1.5)       # aria2 (--stop-with-process) Kami'den hemen sonra kapanir: bin\ kilitli kalmasin
        return 0
    magnet = _magnet_arg(sys.argv[1:])
    play = _play_arg(sys.argv[1:])
    view = _view_arg(sys.argv[1:])
    lens = next((os.path.abspath(sys.argv[i + 2]) for i, a in enumerate(sys.argv[1:]) if a == "--lens" and i + 2 < len(sys.argv)), "")
    if "--lens-screen" in sys.argv[1:]:
        lens = "screen"
    read = next((os.path.abspath(sys.argv[i + 2]) for i, a in enumerate(sys.argv[1:]) if a == "--read" and i + 2 < len(sys.argv)), "")
    if not read:
        from app.core.reader import COMIC as _COMIC
        read = next((os.path.abspath(a) for a in sys.argv[1:] if not a.startswith("-") and a.lower().endswith(_COMIC[:4])
                     and os.path.isfile(a)), "")
    uri = next((sys.argv[i + 2] for i, a in enumerate(sys.argv[1:]) if a == "--uri" and i + 2 < len(sys.argv)), "")
    convert = [os.path.abspath(a) for a in sys.argv[sys.argv.index("--convert") + 1:]] if "--convert" in sys.argv else []
    if convert and not call_running_instance(paths.BRIDGE_INFO_PATH, "/v1/ping") and _already_running_mutex():
        import time as _time
        for _ in range(30):   # Gezgin'de coklu secim: ilk kopya acilirken digerleri kopruyu bekler
            _time.sleep(0.5)
            if call_running_instance(paths.BRIDGE_INFO_PATH, "/v1/ping"):
                break

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
        if convert:   # Gezgin sag tik: "Kami ile donustur"
            call_running_instance(paths.BRIDGE_INFO_PATH, "/v1/convert", {"paths": convert}, timeout=5.0)
            return 0
        if uri:   # bildirim dugmesi (kami://...)
            call_running_instance(paths.BRIDGE_INFO_PATH, "/v1/uri", {"uri": uri}, timeout=5.0)
            return 0
        if view:   # gorsel: calisan Kami'nin fotograf goruntuleyicisi
            call_running_instance(paths.BRIDGE_INFO_PATH, "/v1/view", {"path": view}, timeout=5.0)
            return 0
        if read:   # Kami Reader: manga / PDF / klasor
            call_running_instance(paths.BRIDGE_INFO_PATH, "/v1/read", {"path": read}, timeout=5.0)
            return 0
        if lens:   # Gezgin sag tik "Kami Lens ile ara"
            call_running_instance(paths.BRIDGE_INFO_PATH, "/v1/lens", {"path": lens}, timeout=5.0)
            return 0
        if play:   # Gezgin'de cift tik: calisan Kami oynaticiyi acar (pencereyi de one getirir)
            res = call_running_instance(paths.BRIDGE_INFO_PATH, "/v1/play", {"path": os.path.abspath(play)}, timeout=5.0)
            log.info("Oynatma calisan Kami'ye iletildi: %s", bool(res and res.get("ok")))
            return 0
        if "--tray" not in sys.argv[1:]:
            call_running_instance(paths.BRIDGE_INFO_PATH, "/v1/show")
        log.info("Kami zaten calisiyor; pencere one getirildi.")
        return 0

    # Kopru yanit vermese de (eski/farkli veri klasorlu kopya, takilmis kopya) ikinci kopya acilmasin: adli Windows mutex'i
    if _already_running_mutex():
        import ctypes
        from app.core import winwin
        hwnd = ctypes.windll.user32.FindWindowW(None, "Kami")
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 9)   # SW_RESTORE (tepsiye gizliyse de)
            winwin.bring_to_front(hwnd)
        log.warning("Baska bir Kami kopyasi calisiyor (mutex); o one getirildi, bu kopya kapaniyor.")
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
    engine.auto_mirror = bool(settings.get("auto_mirror"))
    engine.start_service()
    from app.core.plugin_loader import PluginStore
    registry = load_plugins(paths.PLUGINS_DIR, events, settings, store=PluginStore(paths.DATA_DIR / "plugins.json"))
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
    start_hidden = "--tray" in sys.argv[1:] or bool(play)   # Gezgin'den dosya: sadece Kami Player penceresi
    window = webview.create_window(
        "Kami",
        url=str(paths.WEB_DIR / "index.html"),
        js_api=api,
        width=1445, height=850, min_size=(820, 520),
        background_color="#0D0A12" if settings.get("theme") == "dark" else "#F5F3F9",
        text_select=False,
        minimized=start_hidden,
    )
    api._set_window(window)

    # ---- Kami Player: --play ile acilis, calisan ornege gelen istek, pencereye birakilan medya dosyasi
    def play_request(path: str) -> None:
        api._play_request(path)   # Kami Player penceresi acilir / one gelir (Sunak tepside kalabilir)

    def bind_drop(win) -> None:
        try:
            from webview.dom import DOMEventHandler
            from app.core.media_server import AUDIO_EXT, VIDEO_EXT

            def on_drop(e) -> None:
                if api._conv_view:   # Donusturucu acik: tum dosyalar ona
                    api.convert_add([f.get("pywebviewFullPath") for f in (e.get("dataTransfer") or {}).get("files") or []
                                     if f.get("pywebviewFullPath")])
                    return
                for f in (e.get("dataTransfer") or {}).get("files") or []:
                    p = f.get("pywebviewFullPath") or ""
                    if p and os.path.splitext(p)[1].lower() in (".cbz", ".cbr", ".cb7", ".cbt"):
                        api.reader_show(p)
                        break
                    if p and os.path.splitext(p)[1].lower() in VIDEO_EXT | AUDIO_EXT:
                        api._play_request(p)
                        break
            win.dom.document.events.drop += DOMEventHandler(on_drop, True, False)
        except Exception:
            log.exception("Surukle-birak oynatma baglanamadi")
    window.events.loaded += lambda: bind_drop(window)

    # ---- Kami Player: ayri pencere (ayni surec, ayni api); kapaninca yok olur, istekte yeniden kurulur
    player_front = WindowFront("Kami Player")

    def make_player_window():
        w = webview.create_window("Kami Player", url=str(paths.WEB_DIR / "player.html"), js_api=api,
                                  width=1280, height=760, min_size=(360, 150), background_color="#050408",
                                  text_select=False)

        def closed() -> None:
            api._player_win = None
        w.events.closed += closed

        def loaded() -> None:
            bind_drop(w)
            # simge durumundaki / arka plandaki Kami'den acilinca da one gelsin (Gezgin ikinci ornegi izin verdi)
            player_front.request()
            threading.Timer(0.6, player_front.request).start()
        w.events.loaded += loaded
        return w
    api._make_player_window = make_player_window
    api._front_player = player_front.request

    # ---- Kami Picture: fotograf goruntuleyici + Kami Lens (ayri pencere, ayni api)
    picture_front = WindowFront("Kami Picture")

    def make_picture_window():
        w = webview.create_window("Kami Picture", url=str(paths.WEB_DIR / "picture.html"), js_api=api,
                                  width=1280, height=820, min_size=(520, 360), background_color="#050408", text_select=False)

        def closed() -> None:
            api._picture_win = None
        w.events.closed += closed
        w.events.loaded += lambda: (picture_front.request(), threading.Timer(0.6, picture_front.request).start())
        return w
    api._make_picture_window = make_picture_window
    api._front_picture = picture_front.request

    reader_front = WindowFront("Kami Reader")

    def make_reader_window():
        w = webview.create_window("Kami Reader", url=str(paths.WEB_DIR / "reader.html"), js_api=api,
                                  width=1360, height=880, min_size=(560, 400), background_color="#07060B", text_select=True)

        def closed() -> None:
            api._reader_win = None
            api.reader_close()
        w.events.closed += closed
        def loaded() -> None:
            reader_front.request(); threading.Timer(0.6, reader_front.request).start()
            try:
                from webview.dom import DOMEventHandler
                from app.core.reader import READ_EXT

                def on_drop(e) -> None:
                    for f in (e.get("dataTransfer") or {}).get("files") or []:
                        p = f.get("pywebviewFullPath") or ""
                        if p and (os.path.isdir(p) or p.lower().endswith(READ_EXT)):
                            api.reader_show(p)
                            break
                w.dom.document.events.drop += DOMEventHandler(on_drop, True, False)
            except Exception:
                log.exception("Reader surukle-birak")
        w.events.loaded += loaded
        return w
    api._make_reader_window = make_reader_window
    api._front_reader = reader_front.request

    room_front = WindowFront("Kami Oda")
    from app.core import desktop   # asagidaki yerel import yuzunden burada da gerekli (UnboundLocalError)
    room_keys = {"mute": desktop.HotKey(lambda: room_js("kamiKey('mute')")),
                 "deaf": desktop.HotKey(lambda: room_js("kamiKey('deaf')")),
                 "ptt": desktop.KeyHold(lambda down: room_js(f"kamiKey('ptt', {str(down).lower()})"))}

    def room_js(code: str) -> None:
        w = getattr(api, "_room_win", None)
        if w is not None:
            try:
                w.evaluate_js(code)
            except Exception:
                pass

    def room_keys_on(on: bool) -> None:
        if on:
            room_keys["mute"].start(settings.get("room_mute_hotkey") or "ctrl+shift+m")
            room_keys["deaf"].start(settings.get("room_deaf_hotkey") or "ctrl+shift+d")
            if settings.get("room_ptt_key"):
                room_keys["ptt"].start(settings.get("room_ptt_key"))
        else:
            for k in room_keys.values():
                k.stop()

    def make_room_window(url: str):
        w = webview.create_window("Kami Oda", url=url, js_api=api, width=1280, height=820, min_size=(420, 520),
                                  background_color="#07060B", text_select=True)

        def closed() -> None:
            api._room_win = None
            room_keys_on(False)
        w.events.closed += closed

        def loaded() -> None:
            room_front.request()
            try:   # mikrofon / ekran paylasimi izinleri: yalnizca kendi oda sayfamiza otomatik izin
                def perm(sender, args):
                    u = str(args.Uri or "")
                    if u.startswith("http://127.0.0.1:") or ".trycloudflare.com/" in u:
                        from Microsoft.Web.WebView2.Core import CoreWebView2PermissionState
                        args.State = CoreWebView2PermissionState.Allow
                if not getattr(w, "_kami_perm", None):
                    from System import Action   # CoreWebView2 yalnizca arayuz is parcacigindan

                    def attach() -> None:
                        w.native.browser.webview.CoreWebView2.PermissionRequested += perm
                    w._kami_perm = (perm, attach)
                    w.native.Invoke(Action(attach))
            except Exception:
                log.exception("Oda izinleri baglanamadi (tarayici kendi sorar)")
        w.events.loaded += loaded
        room_keys_on(True)
        return w
    api._make_room_window = make_room_window
    api._front_room = room_front.request

    def make_grab_window():   # Kami Lens: ekrandan alan sec (cercevesiz, tam ekran, hep ustte)
        api._grab_win = webview.create_window("Kami Lens", url=str(paths.WEB_DIR / "grab.html"), js_api=api, frameless=True,
                                              on_top=True, fullscreen=True, background_color="#000000")
    api._make_grab_window = make_grab_window

    bridge.on_play = play_request
    bridge.on_uri = lambda u: api.handle_uri(u)
    bridge.on_convert = api.convert_add
    bridge.on_view = api.picture_open
    bridge.on_read = api.reader_show
    bridge.on_lens = lambda p: api.picture_open(p, True)
    if view:
        threading.Timer(1.5, lambda: api.picture_open(view)).start()
    if lens:
        threading.Timer(1.5, lambda: api.picture_open(lens, True)).start()
    if read:
        threading.Timer(1.5, lambda: api.reader_show(read)).start()
    if convert:
        api.convert_add(convert)
    if uri:   # Kami kapaliyken bildirim dugmesine basildi: acilinca isle
        threading.Timer(4.0, lambda: api.handle_uri(uri)).start()
    if paths.FROZEN:   # kami:// + bildirim kimligi (guncellemede yol degisebilir; her acilista ucuz)
        try:
            from app.core.setup_tasks import register_convert_menu, register_player, register_protocol
            register_protocol(sys.executable)
            register_player(sys.executable)   # gorsel iliskilendirmesi (Birlikte ac > Kami) guncellemede de eklensin
            register_convert_menu(sys.executable)
        except Exception:
            log.exception("kami:// kaydedilemedi")

    # ---- indirme bitince dugmeli bildirim (Oynat / Klasoru ac / Altyazi uret); PostComplete cagirir
    def completed_toast(download) -> bool:
        from app.core.media_server import AUDIO_EXT, VIDEO_EXT
        en = settings.get("language") == "en"
        ext = os.path.splitext(download.path or "")[1].lower()
        acts = []
        if ext in VIDEO_EXT | AUDIO_EXT:
            acts.append(("Play" if en else "Oynat", f"kami://play?id={download.id}"))
        acts.append(("Open folder" if en else "Klasörü aç", f"kami://folder?id={download.id}"))
        if ext in VIDEO_EXT:
            acts.append(("Make subtitles" if en else "Altyazı üret", f"kami://subs?id={download.id}"))
        name = os.path.basename(download.path or "") or download.filename or "Kami"
        return desktop.toast(name, "Download complete" if en else "İndirme tamamlandı", acts)
    api._completed_toast = completed_toast
    if play:
        api._play_request(os.path.abspath(play))

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

    bridge.on_quit = quit_app   # Kami.exe --quit (kurulum/kaldirma/guncelleme)
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

    # ---- "Bu sarki ne?" genel kisayolu: bilgisayardan cikan sesi 10 sn dinler, Shazam ile tanir, bildirim gosterir
    def on_song_hotkey() -> None:
        def run() -> None:
            lang_en = settings.get("language") == "en"
            tray.notify("Kami", "Listening… (10 s)" if lang_en else "Dinleniyor… (10 sn)") if tray.running else None
            res = api.song_identify("")
            if res.get("ok"):
                s = res["song"]
                msg = f"{s.get('artist', '')} — {s.get('title', '')}"
                try:   # panoya kopyala (clip.exe UTF-16 + BOM ister)
                    import subprocess as _sp
                    _sp.run(["clip"], input=("\ufeff" + msg).encode("utf-16le"), creationflags=getattr(_sp, "CREATE_NO_WINDOW", 0), timeout=5)
                except Exception:
                    pass
                tray.notify("Kami: " + ("This song" if lang_en else "Bu şarkı"), msg + (" (copied)" if lang_en else " (panoya kopyalandı)"))
            else:
                err = res.get("error", "")
                tray.notify("Kami", ("Not recognized" if lang_en else "Tanınamadı") + ("" if err in ("not_found", "silence") else f": {err}"))
        threading.Thread(target=run, name="kami-song", daemon=True).start()

    song_hotkey = desktop.HotKey(on_song_hotkey)
    lens_hotkey = desktop.HotKey(lambda: threading.Thread(target=api.picture_open, args=("screen", True), daemon=True).start())
    if settings.get("lens_hotkey_enabled"):
        lens_hotkey.start(settings.get("lens_hotkey"))

    # Ekran kaydi: Alt+F10 son 30 sn, Alt+F9 kayit ac/kapa
    from app.core.recorder import Recorder
    from app.engines.ytdlp_engine import find_ffmpeg as _ff
    api.recorder = Recorder(_ff, settings, lambda *a: None)
    rec_replay_key = desktop.HotKey(lambda: threading.Thread(target=api.rec_save_replay, daemon=True).start())
    rec_record_key = desktop.HotKey(lambda: threading.Thread(target=api.rec_toggle, daemon=True).start())
    rec_replay_key.start(settings.get("rec_replay_hotkey"))
    rec_record_key.start(settings.get("rec_record_hotkey"))
    if settings.get("rec_replay_enabled") and os.name == "nt":
        threading.Thread(target=api.recorder.start_replay, name="kami-replay", daemon=True).start()
    api.recorder.watch()
    if settings.get("song_hotkey_enabled"):
        song_hotkey.start(settings.get("song_hotkey"))

    # ---- masaustu mini karti: Kami kucultulunce / tepsideyken indirme varsa kosede, hep ustte
    api._show_main = show_window

    def card_loop() -> None:
        import time as _t
        while not quitting["v"]:
            _t.sleep(2)
            try:
                hwnd = front._hwnd()
                away = bool(hwnd) and (not winwin.is_visible(hwnd) or bool(winwin.user32.IsIconic(hwnd)))
                busy = api.card_state()["n"] > 0
                want = settings.get("mini_card") and not api._card_hidden and away and busy
                if want and api._card_win is None:
                    sc = webview.screens[0] if webview.screens else None
                    w, h = 360, 98
                    x, y = ((sc.x + sc.width - w - 18), (sc.y + sc.height - h - 70)) if sc else (None, None)
                    api._card_win = webview.create_window("Kami Kart", url=str(paths.WEB_DIR / "card.html"), js_api=api, width=w, height=h,
                                                          x=x, y=y, frameless=True, easy_drag=True, on_top=True, resizable=False,
                                                          background_color="#0B0910", focus=False)
                    api._card_shown = True
                elif api._card_win is not None:
                    if want and not getattr(api, "_card_shown", False):
                        api._card_win.show(); api._card_shown = True
                    elif not want and getattr(api, "_card_shown", False):
                        api._card_win.hide(); api._card_shown = False
            except Exception:
                log.debug("mini kart", exc_info=True)

    threading.Thread(target=card_loop, name="kami-card", daemon=True).start()

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
            elif key in ("lens_hotkey", "lens_hotkey_enabled"):
                lens_hotkey.start(settings.get("lens_hotkey")) if settings.get("lens_hotkey_enabled") else lens_hotkey.stop()
            elif key == "rec_replay_hotkey":
                rec_replay_key.start(value)
            elif key == "rec_record_hotkey":
                rec_record_key.start(value)
            elif key in ("rec_replay_enabled", "rec_fps", "rec_mic"):
                def _re():
                    api.recorder.stop_replay()
                    if settings.get("rec_replay_enabled"):
                        api.recorder.start_replay()
                threading.Thread(target=_re, daemon=True).start()
            elif key in ("song_hotkey", "song_hotkey_enabled"):
                song_hotkey.start(settings.get("song_hotkey")) if settings.get("song_hotkey_enabled") else song_hotkey.stop()
            elif key == "auto_mirror":
                engine.auto_mirror = bool(value)
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
    post.toast = completed_toast if paths.FROZEN else None   # gelistirmede bildirim kimligi kayitli degil

    # ---- Asama 6b: soz + muzik arsivi + Whisper/UVR (alt surecte, sirali GPU kuyrugu)
    from app.core import aitools
    from app.core.debrid import TokenStore
    from app.core.mediapost import MediaPost
    genius = TokenStore(paths.DATA_DIR / "genius_token.bin")
    api._osub = TokenStore(paths.DATA_DIR / "opensubtitles_key.bin")
    media_post = MediaPost(manager, None, genius.load)
    ai = aitools.AiQueue(settings, media_post.set_extra,
                         lambda did: (manager.store.get(did).path if manager.store.get(did) else ""),
                         notify=api._on_ai_event)
    media_post.ai = ai
    post.media = media_post
    api._media_post, api._ai, api._genius = media_post, ai, genius
    from app.core import room as _room
    api._turn_store = TokenStore(paths.DATA_DIR / "turn_key.bin")
    _room.SERVER.turn_key = lambda: tuple((api._turn_store.load() or ":").split(":", 1))
    room_link_store = TokenStore(paths.DATA_DIR / "room_worker.bin")
    def _stable() -> tuple[str, str]:   # DPAPI: "https://kami-oda.<hesap>.workers.dev|gizli-anahtar"
        raw = room_link_store.load() or ""
        url, _, key = raw.partition("|")
        return (url or str(settings.get("room_worker_url") or ""), key) if key else ("", "")
    _room.SERVER.stable = _stable

    def room_joined(name: str) -> None:   # biri odaya girdi, ev sahibi pencerede degilse haber ver
        if getattr(api, "_room_win", None) is None and name != api._room_name():
            en = settings.get("language") == "en"
            desktop.toast("Kami Oda", f"{name} " + ("joined the room" if en else "odaya girdi"),
                          [("Join" if en else "Katıl", "kami://room")])
    _room.SERVER.on_join = room_joined
    if settings.get("room_always") and _stable()[1]:
        threading.Timer(3.0, lambda: api.room_open(False)).start()
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
                      player=lambda p: _watch_play(p))

    def _watch_play(p: str) -> str:
        """Inerken izle: Kami Player (varsayilan) ya da Screenbox / Windows varsayilani."""
        how = settings.get("watch_player") or "kami"
        if how == "kami" and api._media:
            play_request(p)
            return "kami"
        return _play(p, how)
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

    # ---- P1 oynatici: yerel medya sunucusu (Range + ffmpeg akisi, sadece 127.0.0.1)
    import atexit
    from app.core.media_server import MediaServer
    from app.engines.ytdlp_engine import find_ffmpeg
    media_srv = MediaServer(find_ffmpeg, paths.WEB_DIR / "vendor" / "jassub")
    try:
        media_srv.start()
        api._media = media_srv
        media_srv.growing = watcher.head   # inerken izle: inmemis kisim istenirse bekle
        atexit.register(media_srv.stop)
    except OSError:
        log.exception("Medya sunucusu acilamadi")

    def tray_warn(**kw) -> None:
        if kw.get("kind") == "disk" and not winwin.is_foreground(front._hwnd()):
            tray.notify("Kami", f"Disk dolacak: {kw.get('name', '')[:80]}")
    events.on("ui.warn", tray_warn)
    post.start()

    def update_loop() -> None:
        import time as _t
        _t.sleep(30)
        while True:
            if settings.get("update_check") and _t.time() - int(settings.get("update_last") or 0) > 21600:
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
        _clear_web_cache_on_update()
        webview.start(debug=bool(os.environ.get("KAMI_DEBUG")), private_mode=False,
                      storage_path=str(paths.DATA_DIR / "webview"))
    finally:
        log.info("Kami kapaniyor")
        song_hotkey.stop()
        lens_hotkey.stop()
        rec_replay_key.stop(); rec_record_key.stop()
        try:
            from app.core import room as _room
            _room.SERVER.stop()
        except Exception:
            pass
        try:
            api.recorder.shutdown()
        except Exception:
            log.exception("kayit kapatilamadi")
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


def _main_logged() -> int:
    try:
        return main()
    except SystemExit:
        raise
    except BaseException:
        logging.getLogger("kami").critical("Kami baslatilamadi / coktu", exc_info=True)
        raise


def _clear_web_cache_on_update() -> None:
    """Surum degisince WebView2 onbellegini sil; yoksa eski JS/CSS calisir (1.1.0'da Anime4K gorunmedi)."""
    import shutil
    from app.core.extras import APP_VERSION
    root = paths.DATA_DIR / "webview"
    mark = root / "ui_version.txt"
    try:
        if mark.exists() and mark.read_text(encoding="utf-8").strip() == APP_VERSION:
            return
        base = root / "EBWebView" / "Default"
        for d in ("Cache", "Code Cache", "GPUCache", "Service Worker"):
            shutil.rmtree(base / d, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        mark.write_text(APP_VERSION, encoding="utf-8")
    except Exception:
        log.exception("WebView onbellegi temizlenemedi")


if __name__ == "__main__":
    sys.exit(_main_logged())
