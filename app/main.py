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
        if magnet:
            res = call_running_instance(paths.BRIDGE_INFO_PATH, "/v1/rd", {"url": magnet, "source": "magnet"},
                                        timeout=5.0)
            log.info("Magnet calisan Kami'ye iletildi: %s", bool(res and res.get("ok")))
        call_running_instance(paths.BRIDGE_INFO_PATH, "/v1/show")
        log.info("Kami zaten calisiyor; pencere one getirildi.")
        return 0

    import webview  # GUI yalnizca gerektiginde yuklensin

    settings = Settings()
    events = EventBus()
    engine = Aria2Engine(
        paths.ARIA2_EXE,
        connections=settings.get("connections"),
        max_concurrent=settings.get("max_concurrent"),
        max_tries=settings.get("max_tries"),
        speed_limit_kib=settings.get("speed_limit_kib"),
        log_file=paths.DATA_DIR / "aria2.log",
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
    from app.core.debrid import DebridService, TokenStore
    debrid = DebridService(TokenStore(paths.DATA_DIR / "rd_token.bin"), paths.DATA_DIR / "rd_pending.json")
    debrid.enqueue = manager.add_debrid_files
    manager.debrid = debrid

    window_ref: dict = {}

    def show_window() -> None:
        w = window_ref.get("w")
        if not w:
            return
        try:
            w.restore()
            w.show()
            w.on_top = True
            w.on_top = False
        except Exception:
            log.exception("Pencere one getirilemedi")

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
        except Exception:
            log.exception("Ayar motora uygulanamadi: %s", key)

    settings.on_change(on_setting)
    events.on("ui.attention", lambda reason: show_window())

    api = Api(manager, engine, registry, lambda: bridge.port)
    window = webview.create_window(
        "Kami",
        url=str(paths.WEB_DIR / "index.html"),
        js_api=api,
        width=1180, height=740, min_size=(820, 520),
        background_color="#0D0A12" if settings.get("theme") == "dark" else "#F5F3F9",
        text_select=False,
    )
    window_ref["w"] = window
    api._set_window(window)

    # Kapanista arayuzun yarida kalan api cevabi (500 ms tick) olu GUI is parcacigina donmeye calisir:
    # pywebview "Error occurred in script / InvalidAsynchronousStateException" loglar. Zararsiz -> sustur.
    closing = {"v": False}
    window.events.closing += lambda: closing.__setitem__("v", True)
    logging.getLogger("pywebview").addFilter(
        lambda rec: not (closing["v"] and "Error occurred in script" in rec.getMessage()))

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
        bridge.stop()
        debrid.stop()
        manager.stop()
        engine.shutdown()
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
