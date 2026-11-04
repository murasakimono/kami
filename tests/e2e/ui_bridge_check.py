"""Gercek pywebview penceresinde arayuz <-> Python koprusunu dogrular (gecici veriyle)."""
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import webview  # noqa: E402

from app import paths  # noqa: E402
from app.core.events import EventBus  # noqa: E402
from app.core.manager import DownloadManager  # noqa: E402
from app.core.models import Status  # noqa: E402
from app.core.plugin_api import PluginRegistry  # noqa: E402
from app.core.queue_store import DownloadStore  # noqa: E402
from app.core.settings import Settings  # noqa: E402
from app.ui.api import Api  # noqa: E402

tmp = Path(tempfile.mkdtemp())
settings = Settings(tmp / "s.json")
settings.set("download_dir", str(tmp / "dl"))


class Eng:
    running = True
    connections = 16
    def status(self, gids): return {}
    def start(self, d): return ""
    def pause(self, g): pass
    def resume(self, g): pass
    def remove(self, g): pass


store = DownloadStore(tmp / "k.db")
store.add(url="http://x/film.mkv", filename="film.mkv", directory=str(tmp), category="video",
          status=Status.PAUSED, size=1000, downloaded=420)
store.add(url="http://x/setup.exe", filename="setup.exe", directory=str(tmp), category="program",
          status=Status.CONFIRM, size=50)
mgr = DownloadManager(store, Eng(), EventBus(), settings, PluginRegistry())
api = Api(mgr, Eng(), PluginRegistry(), lambda: 47321)
win = webview.create_window("Kami UI check", url=str(paths.WEB_DIR / "index.html"), js_api=api, width=1000, height=640)
api._set_window(win)
result = {}


def probe(w):
    time.sleep(4)
    result["dom"] = w.evaluate_js("""JSON.stringify({
        items: [...document.querySelectorAll('.item .name')].map(e => e.textContent),
        confirmBtn: !!document.querySelector('.item.st-confirm button[data-act=confirm-yes]'),
        bridge: document.querySelector('#bridgeStatus').textContent,
        lang: document.documentElement.lang,
        addPlaceholder: document.querySelector('#addInput').placeholder })""")
    # arayuzden Python'a: onay butonuna bas -> manager.confirm -> durum degismeli
    w.evaluate_js("document.querySelector('.item.st-confirm button[data-act=confirm-yes]').click()")
    time.sleep(1.5)
    result["after_confirm"] = [str(d.status) for d in store.list()]
    w.destroy()


webview.start(probe, win)
print(json.dumps(result, ensure_ascii=False, indent=1))
