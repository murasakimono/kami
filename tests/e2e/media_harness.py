"""E2E icin baslı Kami yerine basliksiz test sunucusu: gercek kopru + yonetici + aria2 + yt-dlp, gecici veri.

Kullanicinin calisan Kami'sine dokunmaz: kopru bilgisi <tmp>/bridge.json'a yazilir; test Chrome'u
KAMI_BRIDGE_INFO=<o yol> ortamiyla acilir (native host bunu okur). Durum <tmp>/state.json'a yazilir.
Kullanim: python tests/e2e/media_harness.py <tmp_dir>
"""
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app import paths  # noqa: E402
from app.core import bridge_server  # noqa: E402
from app.core.events import EventBus  # noqa: E402
from app.core.manager import DownloadManager  # noqa: E402
from app.core.plugin_loader import load_plugins  # noqa: E402
from app.core.queue_store import DownloadStore  # noqa: E402
from app.core.settings import Settings  # noqa: E402
from app.engines import ytdlp_engine as yt  # noqa: E402
from app.engines.aria2_engine import Aria2Engine  # noqa: E402

tmp = Path(sys.argv[1])
tmp.mkdir(parents=True, exist_ok=True)
settings = Settings(tmp / "settings.json")
settings.set("download_dir", str(tmp / "dl"))
eng = Aria2Engine(paths.ARIA2_EXE)
eng.start_service()
events = EventBus()
registry = load_plugins(paths.PLUGINS_DIR, events, settings)   # bulut eklentileri (bulut-once yonlendirme)
mgr = DownloadManager(DownloadStore(tmp / "k.db"), eng, events, settings, registry,
                      media=yt.MediaRunner(eng))
chooses: list[dict] = []
events.on("media.choose", lambda **kw: chooses.append({k: v for k, v in kw.items() if k != "headers"}))


class FakeDebrid:
    """RD taklidi: kopru /v1/rd'nin eklentiden ne aldigini kaydeder (gercek token/ag yok)."""
    def __init__(self):
        self.calls = []
        self.notify = lambda ev: None

    def has_token(self):
        return True

    def add_magnet(self, m):
        self.calls.append({"kind": "magnet", "value": m})

    def add_torrent_bytes(self, data):
        self.calls.append({"kind": "torrent", "value": data[:40].decode("latin-1"), "size": len(data)})

    def add_link(self, url):
        self.calls.append({"kind": "link", "value": url})
        return 1


mgr.debrid = FakeDebrid()
bridge_server.PREFERRED_PORT = 0  # kullanicinin Kami'si 47321'de olabilir
bridge = bridge_server.BridgeServer(mgr, tmp / "bridge.json")
mgr.start()
bridge.start()


def dump() -> None:
    while True:
        items = [{"id": d.id, "url": d.url, "status": str(d.status), "filename": d.filename, "kind": d.kind,
                  "size": d.size, "error": d.error, "path": d.path} for d in mgr.snapshot()]
        tmpf = tmp / "state.tmp"
        tmpf.write_text(json.dumps({"items": items, "chooses": chooses, "rd": mgr.debrid.calls}, ensure_ascii=False), encoding="utf-8")
        tmpf.replace(tmp / "state.json")
        time.sleep(0.5)


threading.Thread(target=dump, daemon=True).start()
print("HAZIR", flush=True)
try:
    sys.stdin.read()  # ust surec stdin'i kapatinca biter
finally:
    bridge.stop()
    mgr.stop()
    eng.shutdown()
