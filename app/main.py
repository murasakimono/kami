"""Kami giris noktasi:  .venv\\Scripts\\python.exe -m app.main"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import time
import threading
from typing import Any

from app import paths
from app.core.bridge_server import BridgeServer, call_running_instance
from app.core.events import EventBus
from app.core.manager import DownloadManager
from app.core.plugin_loader import load_plugins
from app.core.queue_store import DownloadStore
from app.core.settings import Settings
from app.core import oplog, resume_router
from app.engines.aria2_engine import Aria2Engine
from app.ui.api import Api

log = logging.getLogger("kami")


def _set_app_id(app_id: str = "Murasakimono.Kami.App") -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


def _set_hwnd_app_id(title: str, app_id: str) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        class PROPERTYKEY(ctypes.Structure):
            _fields_ = [("fmtid", ctypes.c_byte * 16), ("pid", wintypes.DWORD)]

        class PROPVARIANT(ctypes.Structure):
            _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort), ("r2", ctypes.c_ushort),
                        ("r3", ctypes.c_ushort), ("val", ctypes.c_wchar_p), ("pad", ctypes.c_void_p)]

        hwnd = ctypes.windll.user32.FindWindowW(None, title)
        if not hwnd:
            return
        from app.core import winwin
        winwin.set_caption_color(hwnd=hwnd)
        iid = (ctypes.c_byte * 16).from_buffer_copy(bytes.fromhex("886d8eeb8cf244468d02cdba1dbdcf99"))
        store = ctypes.c_void_p()
        if ctypes.windll.shell32.SHGetPropertyStoreForWindow(hwnd, ctypes.byref(iid), ctypes.byref(store)) != 0 or not store:
            return
        vtbl = ctypes.cast(ctypes.cast(store, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
        set_val = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(PROPERTYKEY), ctypes.POINTER(PROPVARIANT))(vtbl[6])
        commit = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(vtbl[7])
        release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])
        # PKEY_AppUserModel_ID: {9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}, 5
        import uuid
        pkey = PROPERTYKEY((ctypes.c_byte * 16).from_buffer_copy(uuid.UUID("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3").bytes_le), 5)
        pv = PROPVARIANT(31, 0, 0, 0, app_id, None)  # VT_LPWSTR = 31
        set_val(store, ctypes.byref(pkey), ctypes.byref(pv))
        commit(store)
        release(store)
    except Exception:
        pass


_MOD_ICONS_KEEP: list[int] = []


def _set_hwnd_icon(title: str, key: str, accent: tuple[int, int, int] | None = None) -> None:
    """Modul penceresine kendine ozgu renkli/simgeli gorev cubugu ve baslik ikonu atar."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from app.core import icons
        icon_dir = paths.DATA_DIR / "icons"
        icon_dir.mkdir(parents=True, exist_ok=True)
        ico = icon_dir / f"{key}_v20.ico"
        if not ico.is_file():
            icons.write_ico(key, ico)
        hwnd = ctypes.windll.user32.FindWindowW(None, title)
        if not hwnd:
            return
        from app.core import winwin
        winwin.set_caption_color(hwnd=hwnd)
        for idx, sz in ((0, 16), (1, 32)):
            hi = ctypes.windll.user32.LoadImageW(0, str(ico), 1, sz, sz, 0x10)
            if hi:
                _MOD_ICONS_KEEP.append(hi)
                ctypes.windll.user32.SendMessageW(hwnd, 0x0080, idx, hi)
    except Exception:
        pass


def _setup_logging() -> None:
    handler = logging.handlers.RotatingFileHandler(paths.LOG_PATH, maxBytes=2_000_000, backupCount=2,
                                                   encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.setLevel(logging.DEBUG)   # dosyada debug ayrintisi da kalsin (sessiz yutmalar izlenebilir); konsol INFO kalir
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
    _set_app_id("Murasakimono.Kami.App")
    # Kami Oda / Player: ses kullanici tiklamasi beklemeden baslasin (oda otomatik girince AudioContext askida kaliyordu)
    # Kucultup/tepsiden geri acinca beyaz-siyah ekran: Chromium'un Windows pencere ortusme hesabi (native occlusion)
    # WebView2'yi "gorunmuyor" sanip cizimi durduruyor, geri gelince yeniden cizmiyor. Kapat; arka plana atma da
    # Player/Oda sesini ve Sunak'i kesmesin. (Sunak GPU kendi ticker'ini document.hidden'da durdurur.)
    _wv = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
    for _arg in ("--autoplay-policy=no-user-gesture-required", "--disable-features=CalculateNativeWinOcclusion",
                 "--disable-backgrounding-occluded-windows"):
        if _arg.split("=")[0] not in _wv:
            _wv = (_wv + " " + _arg).strip()
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = _wv
    paths.setup_frozen()
    paths.ensure_dirs()
    _setup_logging()
    from app.core.extras import APP_VERSION as _APP_VERSION
    log.info("Kami %s basladi", _APP_VERSION)
    if "--studio-mcp" in sys.argv[1:]:   # Claude masaustu: Kami Studio MCP sunucusu (stdio, pencere yok)
        from app.core import studio_mcp
        return studio_mcp.main()
    if "--studio-run" in sys.argv[1:]:   # otomasyon: Kami.exe --studio-run <boru hatti> <dosya...> (makbuz JSON yazar)
        import json as _json
        from app.core import studio_mcp_pro
        i = sys.argv.index("--studio-run")
        rest = sys.argv[i + 1:]
        if not rest:
            return 2
        rec = studio_mcp_pro.t_pipeline("run", name=rest[0], media=rest[1:])
        try:   # pencereli exe'de stdout yok; makbuz zaten Otomasyon\Çıktı'ya yazildi
            print(_json.dumps(rec, ensure_ascii=False, indent=1))
        except (AttributeError, OSError, ValueError):
            pass
        return 0 if rec.get("out") else 1
    if "--picture-mcp" in sys.argv[1:]:   # Claude/Antigravity: Kami Picture Pro MCP sunucusu (stdio)
        from app.core import picture_mcp
        return picture_mcp.main()
    if "--cli" in sys.argv[1:]:   # kami-cli bassiz SDK
        from app.core import kami_cli
        _idx = sys.argv.index("--cli")
        return kami_cli.main(sys.argv[_idx + 1:])
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
    studio = next((os.path.abspath(sys.argv[i + 2]) for i, a in enumerate(sys.argv[1:]) if a == "--studio" and i + 2 < len(sys.argv)), "")
    if not studio:
        studio = next((os.path.abspath(a) for a in sys.argv[1:] if not a.startswith("-") and a.lower().endswith(".kstudio") and os.path.isfile(a)), "")
    if "--studio" in sys.argv[1:] and not studio:
        studio = "open"
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
        if studio:   # Kami Studio (proje dosyasi ya da bos)
            call_running_instance(paths.BRIDGE_INFO_PATH, "/v1/studio", {"path": "" if studio == "open" else studio}, timeout=5.0)
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
    try:
        from app.core import backup as _backup, extras as _extras
        _rr = _backup.apply_pending_restore(paths.DATA_DIR, _extras.APP_VERSION)
        if _rr and _rr.get("ok"):
            log.info("Bekleyen yedek acilista geri yuklendi (%d dosya)", len(_rr.get("restored") or []))
        elif _rr and not _rr.get("ok"):
            log.warning("Bekleyen yedek uygulanamadi: %s", _rr.get("error"))
    except Exception:
        log.exception("Bekleyen yedek kontrolu")
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
    try:
        from app.core.games import TRACKER as _GAME_TRACKER
        _GAME_TRACKER.on_active_change = api._on_game_active_change
    except Exception:
        pass
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
                if getattr(api, "_ai_drop_view", False):   # AI Altyazi/Vokal/Lirik studyosu acik: dosyalar ona
                    api.ai_drop_add([f.get("pywebviewFullPath") for f in (e.get("dataTransfer") or {}).get("files") or []
                                     if f.get("pywebviewFullPath")])
                    return
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
    main_win = {"w": window}   # ana pencere yok edilirse (beklenmedik kapanma) istekte yeniden kurulur

    # ---- Kami Player: ayri pencere (ayni surec, ayni api); kapaninca yok olur, istekte yeniden kurulur
    # v1.35.2 "sicak tut": modul penceresi kapatilinca yok edilmez, gizlenir. Her acilista sifirdan WebView2
    # motoru kurmak 2-5 sn surdugu icin "bin saatte aciliyor"du; ikinci ve sonraki acilislar artik aninda.
    # closing isleyicisinde arayuz is parcacigina Invoke eden HICBIR cagri yapilmaz (bkz. keep_warm).
    # Uygulama gercekten kapanirken (quit_app -> quitting) normal kapanir.
    def keep_warm(w, on_hide_js: str = "") -> None:
        # v1.35.3: pywebview closing isleyicisini AYRI is parcaciginda calistirir ve arayuz is parcacigi
        # onun bitmesini bekler (Event.set -> join). w.hide()/run_js arayuz is parcacigina Invoke eder ->
        # birbirini bekleyip kilitlenir ("Yanit Vermiyor"). Bu yuzden burada yalniz kapatmayi iptal edip
        # donuyoruz; gizleme isleyici dondukten sonra ayri is parcaciginda yapilir.
        def _hide_later():
            time.sleep(0.05)
            try:
                if on_hide_js:
                    w.run_js(on_hide_js)
                w.hide()
            except Exception:
                log.debug("pencere gizlenemedi", exc_info=True)

        def closing():
            if quitting["v"] or getattr(w, "_kami_allow_destroy", False):
                return None
            threading.Thread(target=_hide_later, name="kami-keepwarm-hide", daemon=True).start()
            return False   # kapatmayi iptal et; pencere hemen ardindan gizlenir
        w.events.closing += closing

    player_front = WindowFront("Kami Player")

    def make_player_window(prewarm: bool = False, js_api: Any = None):
        w = webview.create_window("Kami Player", url=str(paths.WEB_DIR / "player.html"), js_api=js_api or api,
                                  width=1280, height=760, min_size=(360, 150), background_color="#050408",
                                  text_select=False, hidden=prewarm)
        state = {"prewarm": prewarm}

        def closed() -> None:
            if getattr(api, "_player_win", None) is w:
                api._player_win = None
        w.events.closed += closed
        keep_warm(w, "try{var v=document.getElementById('plVideo');if(v)v.pause();if(document.fullscreenElement)document.exitFullscreen()}catch(e){}")

        def loaded() -> None:
            bind_drop(w)
            _set_hwnd_app_id("Kami Player", "Murasakimono.Kami.Player")
            _set_hwnd_icon("Kami Player", "player", (46, 230, 166))
            if state.pop("prewarm", False):   # arka planda hazirlandi: one getirme, gizli kalsin
                return
            # simge durumundaki / arka plandaki Kami'den acilinca da one gelsin (Gezgin ikinci ornegi izin verdi)
            player_front.request()
            threading.Timer(0.6, player_front.request).start()
        w.events.loaded += loaded
        return w
    api._make_player_window = make_player_window

    def _prewarm_player() -> None:   # v1.35.2: ilk Player acilisi da aninda olsun (ayar: prewarm_player)
        try:
            if settings.get("prewarm_player", True) and api._player_win is None:
                api._player_win = make_player_window(prewarm=True)
        except Exception:
            log.debug("Player on isitma", exc_info=True)
    threading.Timer(8.0, _prewarm_player).start()
    api._front_player = player_front.request

    def _startup_selftest() -> None:
        try:
            from app.core import extras, selftest
            if not selftest.should_run(extras.APP_VERSION):
                return
            def _notify(msg: str) -> None:
                import json as _json
                mw = main_win.get("w")
                if mw is not None:
                    mw.evaluate_js(f"try{{if(typeof toast==='function')toast({_json.dumps(msg)},true,true)}}catch(e){{}}")
            selftest.run_selftest(
                api,
                extras.APP_VERSION,
                lambda mod, title, html, to: selftest.probe_pywebview_window(webview, api, mod, title, html, to),
                notify_fn=_notify,
            )
        except Exception:
            log.debug("Acilis kendini sinamasi", exc_info=True)
    threading.Timer(15.0, _startup_selftest).start()

    # ---- Kami Picture: fotograf goruntuleyici + Kami Lens (ayri pencere, ayni api)
    picture_front = WindowFront("Kami Picture")

    def make_picture_window(selftest: bool = False, js_api: Any = None):
        w = webview.create_window("Kami Picture [SelfTest]" if selftest else "Kami Picture", url=str(paths.WEB_DIR / "picture.html"), js_api=js_api or api,
                                  width=1280, height=820, min_size=(520, 360), background_color="#050408",
                                  text_select=False, hidden=selftest)

        def closed() -> None:
            if getattr(api, "_picture_win", None) is w:
                api._picture_win = None
        w.events.closed += closed
        keep_warm(w)
        if not selftest:
            w.events.loaded += lambda: (_set_hwnd_app_id("Kami Picture", "Murasakimono.Kami.Picture"), _set_hwnd_icon("Kami Picture", "picture", (56, 189, 248)), picture_front.request(), threading.Timer(0.6, picture_front.request).start())
        return w
    api._make_picture_window = make_picture_window
    api._front_picture = picture_front.request

    # ---- Kami Oyun / Muzik / Suzgec / Iyilestirici (her biri kendi ayri penceresinde) ----
    _MOD_ICON_COLORS = {"games": (129, 140, 248), "music": (192, 132, 252), "cleaner": (244, 114, 182),
                        "enhance": (163, 230, 53)}
    for _mkey, _mtitle, _mfile, _mw, _mh in (
        ("games", "Kami Games", "games.html", 1320, 840),
        ("music", "Kamify", "music.html", 1240, 800),
        ("cleaner", "Kami Cleaner", "cleaner.html", 1220, 780),
        ("enhance", "Kami İyileştirici", "enhance.html", 1180, 820),
    ):
        def _bind_mod(k=_mkey, t=_mtitle, f=_mfile, ww=_mw, hh=_mh, col=_MOD_ICON_COLORS[_mkey]):
            fr = WindowFront(t)
            def _make(selftest: bool = False, js_api: Any = None):
                w = webview.create_window(f"{t} [SelfTest]" if selftest else t, url=str(paths.WEB_DIR / f), js_api=js_api or api,
                                          width=ww, height=hh, min_size=(760, 520), background_color="#08070C",
                                          text_select=True, hidden=selftest)
                def _on_closed():
                    if getattr(api, f"_{k}_win", None) is w:
                        setattr(api, f"_{k}_win", None)
                w.events.closed += _on_closed
                keep_warm(w)
                if not selftest:
                    def _on_mod_loaded(win_t=t, win_k=k, win_col=col, mod_fr=fr) -> None:
                        _set_hwnd_app_id(win_t, f"Murasakimono.Kami.{win_k.title()}")
                        _set_hwnd_icon(win_t, win_k, win_col)
                        if win_k == "music":
                            try:
                                from app.core import taskbar
                                hwnd = winwin.find_window(win_t)
                                if hwnd:
                                    taskbar.set_thumb_buttons(hwnd, bool(getattr(api, "_thumb_playing", False)), lambda cmd: api.mini_island_music_cmd(cmd))
                            except Exception:
                                pass
                        mod_fr.request()
                        threading.Timer(0.5, mod_fr.request).start()
                    w.events.loaded += _on_mod_loaded
                return w
            setattr(api, f"_make_{k}_window", _make)
            setattr(api, f"_front_{k}", fr.request)
        _bind_mod()

    reader_front = WindowFront("Kami Reader")

    def make_reader_window(selftest: bool = False, js_api: Any = None):
        w = webview.create_window("Kami Reader [SelfTest]" if selftest else "Kami Reader", url=str(paths.WEB_DIR / "reader.html"), js_api=js_api or api,
                                  width=1360, height=880, min_size=(560, 400), background_color="#07060B",
                                  text_select=True, hidden=selftest)

        def closed() -> None:
            if getattr(api, "_reader_win", None) is w:
                api._reader_win = None
                api.reader_close()
        w.events.closed += closed
        keep_warm(w)
        def loaded() -> None:
            if selftest:
                return
            _set_hwnd_app_id("Kami Reader", "Murasakimono.Kami.Reader")
            _set_hwnd_icon("Kami Reader", "reader", (245, 158, 11))
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

    # ---- Kami Studio: video editoru (ayri pencere, ayni api)
    studio_front = WindowFront("Kami Studio")

    def make_studio_window(selftest: bool = False, js_api: Any = None):
        w = webview.create_window("Kami Studio [SelfTest]" if selftest else "Kami Studio", url=str(paths.WEB_DIR / "studio.html"), js_api=js_api or api,
                                  width=1600, height=960, min_size=(1100, 680), background_color="#07060B",
                                  text_select=False, hidden=selftest)

        def closed() -> None:
            if getattr(api, "_studio_win", None) is w:
                api._studio_win = None
        w.events.closed += closed
        keep_warm(w)

        def loaded() -> None:
            if selftest:
                return
            _set_hwnd_app_id("Kami Studio", "Murasakimono.Kami.Studio")
            _set_hwnd_icon("Kami Studio", "studio", (167, 139, 250))
            studio_front.request(); threading.Timer(0.6, studio_front.request).start()
            try:
                w.maximize()
            except Exception:
                pass
            try:
                from webview.dom import DOMEventHandler

                def on_drop(e) -> None:
                    ps = [f.get("pywebviewFullPath") for f in (e.get("dataTransfer") or {}).get("files") or []]
                    ps = [p for p in ps if p and os.path.isfile(p)]
                    if ps:
                        with api._inbox_lock:
                            api._studio_q = list(api._studio_q) + ps
                w.dom.document.events.drop += DOMEventHandler(on_drop, True, False)
            except Exception:
                log.exception("Studio surukle-birak")
        w.events.loaded += loaded
        return w
    api._make_studio_window = make_studio_window
    api._front_studio = studio_front.request
    try:
        api._studio_load_packs()
    except Exception:
        log.exception("Studio paketleri")

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

        # v1.35.2: closing/closed arayuz is parcaciginda calisir. Burada evaluate_js (JS yanitini bekler) ya da
        # baska pencereye dokunan cagri yapmak tum Kami'yi kilitliyordu (odadan cikip X'e basinca donma).
        # Ayrilma sunucu tarafinda yapilir (leave_cid); is arka plan is parcacigina alinir, kapanis beklemez.
        def _leave_bg() -> None:
            try:
                from app.core import room as _room_mod
                rm = _room_mod.SERVER.room
                if rm is not None:
                    rm.leave_cid("kami-host")
            except Exception:
                log.debug("oda ayrilma", exc_info=True)
            try:
                api.room_island_push({"people": [], "left": True})
            except Exception:
                log.debug("ada guncelleme", exc_info=True)

        def closed() -> None:
            api._room_win = None
            def _bg() -> None:
                try:
                    room_keys_on(False)   # HotKey.stop() is parcacigi basina 2 sn'ye kadar join eder: arayuzde olmasin
                except Exception:
                    pass
                _leave_bg()
            threading.Thread(target=_bg, name="kami-room-close", daemon=True).start()
        w.events.closed += closed

        def loaded() -> None:
            _set_hwnd_app_id("Kami Oda", "Murasakimono.Kami.Room")
            _set_hwnd_icon("Kami Oda", "room", (168, 85, 247))
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

    def make_pin_window(pid: str, w_px: int = 380, h_px: int = 280):
        win = webview.create_window("Kami Pin", url=f"{(paths.WEB_DIR / 'pin.html').as_uri()}?pid={pid}",
                                    js_api=api, frameless=True, easy_drag=False, on_top=True,
                                    width=max(160, int(w_px)), height=max(120, int(h_px)),
                                    background_color="#09070D")
        win.events.closed += lambda: getattr(api, "_pin_wins", {}).pop(pid, None)
        return win
    api._make_pin_window = make_pin_window

    def make_lens_quick_window():
        w_card, h_card = 408, 152
        try:
            sw = int(ctypes.windll.user32.GetSystemMetrics(0))
            sh = int(ctypes.windll.user32.GetSystemMetrics(1))
            px, py = max(20, sw - w_card - 24), max(20, sh - h_card - 72)
        except Exception:
            px, py = 820, 620
        win = webview.create_window("Kami Yakalama", url=str(paths.WEB_DIR / "lens_quick.html"),
                                    js_api=api, frameless=True, easy_drag=False, on_top=True,
                                    width=w_card, height=h_card, x=px, y=py,
                                    background_color="#0B0812")
        win.events.closed += lambda: setattr(api, "_lens_quick_win", None)
        api._lens_quick_win = win
        return win
    api._make_lens_quick_window = make_lens_quick_window

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
    bridge.on_studio = api.studio_show
    if studio:
        threading.Timer(1.5, lambda: api.studio_show("" if studio == "open" else studio)).start()
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
        if quitting["v"]:
            return
        quitting["v"] = True
        try:
            tray.stop()
        except Exception:
            pass
        for fn in (
            lambda: __import__("app.core.librespot_host", fromlist=["stop"]).stop(),
            lambda: __import__("app.core.room", fromlist=["SERVER"]).SERVER.stop(),
            lambda: manager.stop(),
            lambda: bridge.stop(),
        ):
            try:
                fn()
            except Exception:
                pass
        # Kapanis: bin/ alt surecleri (uv.exe, aria2c, ffmpeg ...) arka planda asili kalmasin
        # (bir sonraki kurulumda base_library.zip / bin dosyalarini kilitlemesin).
        if os.name == "nt":
            import subprocess as _sp
            for _img in ("uv.exe", "aria2c.exe", "ffmpeg.exe", "ffprobe.exe", "deno.exe"):
                try:
                    _sp.run(["taskkill", "/F", "/IM", _img, "/T"], capture_output=True, timeout=8,
                            creationflags=0x08000000)
                except Exception:
                    pass
        for w in list(webview.windows):
            try:
                w.destroy()
            except Exception:
                log.debug("Pencere kapatilamadi")
        t = threading.Timer(1.2, lambda: os._exit(0))
        t.daemon = True
        t.start()

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

    def on_main_closed():
        if not quitting["v"]:   # X ile gercekten kapandi (tepsiye gizleme kapali): diger pencereler sureci tutmasin
            log.info("Ana pencere kapandi; Kami cikiyor")
            quit_app()

    main_ready = threading.Event()
    recreate_lock = threading.Lock()

    def bind_main(w) -> None:
        api._set_window(w)
        w.events.shown += lambda: main_ready.set()
        w.events.loaded += lambda: (main_ready.set(), bind_drop(w), winwin.set_caption_color("Kami"), _set_hwnd_icon("Kami", "main", (157, 107, 255)))
        w.events.closing += on_closing
        w.events.closed += on_main_closed

    def recreate_main() -> None:
        if quitting["v"] or not main_ready.is_set():
            return
        with recreate_lock:
            if quitting["v"] or winwin.find_window("Kami"):
                hwnd = winwin.find_window("Kami")
                if hwnd:
                    winwin.bring_to_front(hwnd)
                return
            if main_win.get("w") in list(webview.windows):
                return
            w = webview.create_window(
                "Kami", url=str(paths.WEB_DIR / "index.html"), js_api=api,
                width=1445, height=850, min_size=(820, 520),
                background_color="#0D0A12" if settings.get("theme") == "dark" else "#F5F3F9", text_select=False)
            main_win["w"] = w
            bind_main(w)

    bind_main(window)
    front.on_missing = recreate_main
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
    from app.core import recorder as _recorder_mod
    _recorder_mod.set_active(api.recorder)   # games.py otomatik replay buradan alir
    rec_replay_key = desktop.HotKey(lambda: threading.Thread(target=api.rec_save_replay, daemon=True).start())
    rec_record_key = desktop.HotKey(lambda: threading.Thread(target=api.rec_toggle, daemon=True).start())
    rec_replay_key.start(settings.get("rec_replay_hotkey"))
    rec_record_key.start(settings.get("rec_record_hotkey"))
    if settings.get("rec_replay_enabled") and os.name == "nt":
        threading.Thread(target=api.recorder.start_replay, name="kami-replay", daemon=True).start()
    api.recorder.watch()
    if settings.get("song_hotkey_enabled"):
        song_hotkey.start(settings.get("song_hotkey"))

    # Kami 2.0 B8: Sistem Sesi Arka Plan (Calan Sarki Gunlugu) ayri kisayolu (varsayilan Ctrl+Shift+G)
    def on_scrobbler_hotkey() -> None:
        def run_scrob() -> None:
            res = api.scrobbler_recognize_now()
            if res.get("ok") and res.get("song"):
                s = res["song"]
                if tray.running:
                    tray.notify("Kami Dinleme Günlüğü", f"✓ Günlüğe eklendi: {s.get('artist', '')} — {s.get('title', '')}")
        threading.Thread(target=run_scrob, name="kami-scrobbler", daemon=True).start()

    scrobbler_hotkey = desktop.HotKey(on_scrobbler_hotkey)
    try:
        scrobbler_hotkey.start(settings.get("scrobbler_hotkey") or "ctrl+shift+g")
    except Exception:
        pass

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

    # ---- Faz 7.5: Masaustu Mini-Ada Seridi
    def _make_island_window():
        sc = webview.screens[0] if webview.screens else None
        w, h = 460, 48
        x, y = ((sc.x + (sc.width - w) // 2), (sc.y + 14)) if sc else (None, None)
        win = webview.create_window(
            "Kami Mini-Ada",
            url=str(paths.WEB_DIR / "mini-island.html"),
            js_api=api,
            width=w,
            height=h,
            min_size=(220, 36),
            x=x,
            y=y,
            frameless=True,
            shadow=True,
            transparent=False,
            easy_drag=True,
            on_top=True,
            resizable=True,
            background_color="#0B0910",
            focus=False,
        )

        def _clip_island() -> None:
            try:
                winwin.round_pill("Kami Mini-Ada")
            except Exception:
                pass

        def _bind_island_drop() -> None:
            try:
                from webview.dom import DOMEventHandler
                import json as _json

                def _on_drop(e) -> None:
                    fs = [f.get("pywebviewFullPath") for f in (e.get("dataTransfer") or {}).get("files") or [] if f.get("pywebviewFullPath")]
                    if fs:
                        api._island_drop_files = fs
                        try:
                            win.run_js(f"window.kamiIslandExternalDrop && window.kamiIslandExternalDrop({_json.dumps(fs)})")
                        except Exception:
                            pass

                win.dom.document.events.drop += DOMEventHandler(_on_drop, True, False)
            except Exception:
                pass

        win.events.loaded += lambda: (_clip_island(), _bind_island_drop(), threading.Timer(0.18, _clip_island).start())
        win.events.shown += lambda: (_clip_island(), threading.Timer(0.18, _clip_island).start())
        return win

    api._island_factory = _make_island_window

    def _music_island_loop() -> None:
        while True:
            time.sleep(2.0)
            try:
                api.music_island_tick()
            except Exception:
                log.debug("muzik mini-ada", exc_info=True)
    threading.Thread(target=_music_island_loop, name="kami-music-island", daemon=True).start()

    def _caption_loop() -> None:   # yeni acilan her pencerenin gri baslik cubugunu uygulama rengine boyar
        from app.core import winwin as _ww
        while True:
            try:
                _ww.tint_own_windows()
            except Exception:
                log.debug("baslik rengi", exc_info=True)
            time.sleep(0.4)
    if sys.platform == "win32":
        threading.Thread(target=_caption_loop, name="kami-caption", daemon=True).start()
    if settings.get("mini_island"):
        try:
            api.mini_island_toggle(True)
        except Exception:
            log.debug("mini_island acilamadi", exc_info=True)

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
    try:
        aitools.reset_stale_ai(manager.store)
    except Exception:
        log.exception("Takili AI isleri temizlenemedi")
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
    _room.SERVER.key_hash = lambda: str(settings.get("room_password_hash") or "")

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
    manager.oplog = oplog.OpLog(str(paths.DATA_DIR / "oplog.jsonl"))   # Kami Echo: geri al günlüğü
    manager.resume_router = resume_router                              # Kami Ghost-Resume: çapraz kaynak kurtarma
    ntfy_topic = TokenStore(paths.DATA_DIR / "ntfy_topic.bin")
    post.after.append(automate.AfterActions(manager, history, ntfy_topic.load, media_post.music_dir))

    def queue_done() -> None:
        if settings.get("ntfy_enabled") and settings.get("ntfy_queue"):
            automate.ntfy_send(settings.get("ntfy_server"), ntfy_topic.load(), "Kami", "Kuyruk bitti ✓", "tada")

    shutdown = automate.ShutdownWatcher(
        manager, busy_extra=lambda: bool(ai._cancel), on_queue_done=queue_done)
    shutdown.start()
    # v1.29 coklu kuyruk (adli kuyruklar: kendi esZamanli/hiz siniri, saat penceresi, bitince bildir/kapat)
    from app.core.queues import QueueRunner

    def _queue_done(q: dict) -> None:
        tray.notify("Kami", f"Kuyruk bitti: {q['name']}") if tray.running else None
        if q.get("on_done") == "shutdown":
            settings.set("shutdown_when_done", True)   # 60 sn iptal edilebilir geri sayim (ShutdownWatcher)
    queues = QueueRunner(manager, on_done=_queue_done)
    queues.start()
    api._queues = queues
    # v1.29 RSS otomatik indirme (torrent akislari / podcast)
    from app.core.rss import RssService

    def _rss_fetch(url: str) -> bytes:
        import requests
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 Kami-RSS"})
        r.raise_for_status()
        return r.content[:8 * 1024 * 1024]
    rss = RssService(_rss_fetch, api._rss_add, notify=lambda t, msg: tray.notify(t, msg) if tray.running else None)
    rss.start()
    api._rss = rss

    def _reader_series_loop() -> None:   # v1.30 Reader yeni bolum takibi: 30 dk'da bir (ilk yoklama 2 dk sonra)
        import time as _t
        _t.sleep(120)
        while True:
            try:
                api.reader_series_check()
            except Exception:
                log.exception("Reader seri yoklamasi")
            _t.sleep(1800)
    threading.Thread(target=_reader_series_loop, name="kami-reader-series", daemon=True).start()
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
    phone.on_upload = api.phone_on_upload
    phone.on_deck = api.phone_deck
    phone.recent_media = api.phone_recent_media
    from app.core import room as _room
    _room.SERVER.phone_srv = phone
    from app.core.jobs import jobs as _jobs
    def _job_notify(j: dict) -> None:
        if j.get("status") == "done":
            desktop.toast("Kami İşler", f"{j.get('title', 'İş')} tamamlandı ✓", [])
        elif j.get("status") == "error":
            desktop.toast("Kami İşler", f"{j.get('title', 'İş')} hata: {j.get('error', '')}", [])
    _jobs.on_done = _job_notify

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

    # ---- v1.26 Studio otomasyonu: Otomasyon\<boru hatti>\ klasorune birakilan dosyalar islenir
    if settings.get("studio_automation", True):
        try:
            from app.core.studio_mcp_pro import DropWatcher
            _drop = DropWatcher()
            _drop.start()
            atexit.register(_drop.stop)
        except Exception:
            log.exception("Studio otomasyon izleyicisi acilamadi")

    # ---- Faz 7.1: Cross-Origin Isolation (COOP/COEP + SharedArrayBuffer) yerel HTTP sunucusu
    from app.core.web_isolation import UiIsolationServer
    ui_iso_srv = UiIsolationServer(paths.WEB_DIR)
    try:
        ui_iso_srv.start()
        api._ui_iso = ui_iso_srv
        atexit.register(ui_iso_srv.stop)
    except OSError:
        log.exception("UiIsolationServer acilamadi")

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
            try:
                from app.core import backup
                ls_data = None
                mw = main_win.get("w")
                if mw is not None:
                    try:
                        ls_data = mw.evaluate_js("JSON.stringify(localStorage)")
                    except Exception:
                        ls_data = None
                backup.maybe_auto_backup(settings, local_storage=ls_data)
            except Exception:
                log.exception("Otomatik yedek")
            _t.sleep(3600)

    threading.Thread(target=update_loop, name="kami-update", daemon=True).start()

    # v1.35.4: otomatik sayfa yenileme KALDIRILDI. load_url pywebview'in "loaded" bayragini sifirliyor ve
    # bazen bir daha kurmuyordu -> tum JS<->Python donusleri "Main window failed to start" ile kalici olarak
    # kopuyordu (Oyun 0 oyun, Ekosistem sekmeleri takili; 17.11 logunda 3083 kez). Donma yalniz loglanir.
    api._watchdog = UiWatchdog(lambda: winwin.is_visible(front._hwnd()))
    api._watchdog.start()
    manager.start()
    debrid.start()
    bridge.start()
    api._bridge = bridge
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
