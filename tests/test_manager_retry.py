"""Otomatik baglanti dusurme (sahte motorla, deterministik)."""
from __future__ import annotations

import time

from app.core.events import EventBus
from app.core.manager import DownloadManager
from app.core.models import DownloadRequest, Status
from app.core.plugin_api import Engine
from app.core.queue_store import DownloadStore
from app.core.settings import Settings


class FakeEngine(Engine):
    name = "fake"
    connections = 16

    def __init__(self, fail_times: int, code: str = "1", msg: str = "No URI available.") -> None:
        self.fail_times = fail_times
        self.code, self.msg = code, msg
        self.started: list[int] = []   # her baslatmada max_conn
        self.n = 0

    def can_handle(self, request):
        return True

    def start(self, download):
        self.started.append(download.max_conn)
        self.n += 1
        return f"g{self.n}"

    def pause(self, gid): pass
    def resume(self, gid): pass
    def remove(self, gid): pass

    def status(self, gids):
        out = {}
        for g in gids:
            idx = int(g[1:])
            if idx <= self.fail_times:
                out[g] = {"status": "error", "total": 100, "completed": 40, "speed": 0, "connections": 0,
                          "error_code": self.code, "error": self.msg, "path": ""}
            else:
                out[g] = {"status": "complete", "total": 100, "completed": 100, "speed": 0, "connections": 0,
                          "error_code": "0", "error": "", "path": ""}
        return out


def _mgr(tmp_path, engine):
    s = Settings(tmp_path / "s.json")
    s.set("download_dir", str(tmp_path / "dl"))
    events = EventBus()
    seen = []
    events.on("*", lambda event, **kw: seen.append(event))
    return DownloadManager(DownloadStore(tmp_path / "k.db"), engine, events, s, prober=None), seen


def _poll_until(mgr, did, status, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        mgr.poll_once()
        if mgr.store.get(did).status == status:
            return mgr.store.get(did)
        time.sleep(0.1)
    raise AssertionError(mgr.store.get(did))


def test_fallback_16_4_1_then_complete(tmp_path):
    eng = FakeEngine(fail_times=2)
    mgr, seen = _mgr(tmp_path, eng)
    [d] = mgr.add(DownloadRequest(url="http://x/a.bin"))
    d = _poll_until(mgr, d.id, Status.COMPLETE)
    assert eng.started == [0, 4, 1]          # 16 (ayar) -> 4 -> 1
    assert d.max_conn == 1
    assert "download.failed" not in seen and "download.completed" in seen


def test_gives_up_after_max_retries(tmp_path):
    eng = FakeEngine(fail_times=99)
    mgr, seen = _mgr(tmp_path, eng)
    [d] = mgr.add(DownloadRequest(url="http://x/a.bin"))
    d = _poll_until(mgr, d.id, Status.ERROR, timeout=20)
    assert len(eng.started) == 1 + DownloadManager._MAX_AUTO_RETRIES
    assert "download.failed" in seen


def test_not_found_is_not_retried(tmp_path):
    eng = FakeEngine(fail_times=99, code="3", msg="Resource not found")
    mgr, seen = _mgr(tmp_path, eng)
    [d] = mgr.add(DownloadRequest(url="http://x/a.bin"))
    d = _poll_until(mgr, d.id, Status.ERROR)
    assert eng.started == [0] and "Resource not found" in d.error
