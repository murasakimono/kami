"""aria2 motoru + indirme yoneticisi uctan uca (yerel HTTP sunucusuyla)."""
from __future__ import annotations

import hashlib
import os
import time

import pytest

from app import paths
from app.core.events import EventBus
from app.core.manager import CaptureRejected, DownloadManager
from app.core.models import DownloadRequest, Status
from app.core.queue_store import DownloadStore
from app.core.settings import Settings
from app.engines.aria2_engine import Aria2Engine

pytestmark = pytest.mark.skipif(not paths.ARIA2_EXE.is_file(), reason="bin/aria2c.exe yok")


def _sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


@pytest.fixture
def env(tmp_path):
    settings = Settings(tmp_path / "s.json")
    settings.set("download_dir", str(tmp_path / "dl"))
    engine = Aria2Engine(paths.ARIA2_EXE, connections=16)
    engine.start_service()
    events = EventBus()
    seen = []
    events.on("*", lambda event, **kw: seen.append(event))
    mgr = DownloadManager(DownloadStore(tmp_path / "k.db"), engine, events, settings, poll_interval=0.2)
    mgr.start()
    yield mgr, settings, seen, tmp_path
    mgr.stop()
    engine.shutdown()


def _wait(mgr, did, status, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        d = mgr.store.get(did)
        if d.status == status:
            return d
        if d.status == Status.ERROR and status != Status.ERROR:
            raise AssertionError(d.error)
        time.sleep(0.1)
    raise AssertionError(f"zaman asimi, durum: {mgr.store.get(did).status}")


def test_multiconnection_download(env, http_server):
    mgr, settings, seen, tmp = env
    http_server.handler.connections.clear()
    max_conn = 0
    [d] = mgr.add(DownloadRequest(url=http_server.base + "/big.bin", source="context_menu",
                                  headers={"Cookie": "a=b", "User-Agent": "KamiTest"}))
    deadline = time.time() + 30
    while time.time() < deadline:
        for s in mgr.snapshot():
            if s.id == d.id:
                max_conn = max(max_conn, s.connections)
        if mgr.store.get(d.id).status == Status.COMPLETE:
            break
        time.sleep(0.05)
    d = _wait(mgr, d.id, Status.COMPLETE)
    assert _sha(d.path) == http_server.sha["big.bin"]
    assert d.size == 24 * 1024 * 1024
    # 24 MB / 1 MB parca -> birden fazla baglanti acilmis olmali
    assert len(http_server.handler.connections) > 1, http_server.handler.connections
    assert "download.completed" in seen
    assert d.gid == ""  # tamamlaninca motordan temizlenir


def test_category_folder_and_server_name(env, http_server):
    mgr, settings, seen, tmp = env
    [d] = mgr.add(DownloadRequest(url=http_server.base + "/video.mp4"))
    d = _wait(mgr, d.id, Status.COMPLETE)
    assert os.path.basename(d.directory) == "Video" and d.category == "video"
    # ad sadece Content-Disposition'da -> tamamlaninca kategori klasorune tasinir
    [d2] = mgr.add(DownloadRequest(url=http_server.base + "/cd/video.mp4?token=1"))
    d2 = _wait(mgr, d2.id, Status.COMPLETE)
    assert os.path.basename(d2.directory) == "Video"
    assert d2.filename.startswith("video") and os.path.isfile(d2.path)


def test_confirm_and_capture_rules(env, http_server):
    mgr, settings, seen, tmp = env
    settings.set("capture_min_size_kib", 1)
    with pytest.raises(CaptureRejected):
        mgr.add(DownloadRequest(url=http_server.base + "/setup.exe", source="browser", size=100))
    settings.set("capture_exclude_hosts", ["127.0.0.1"])
    with pytest.raises(CaptureRejected):
        mgr.add(DownloadRequest(url=http_server.base + "/big.bin", source="browser"))
    settings.set("capture_exclude_hosts", [])
    [d] = mgr.add(DownloadRequest(url=http_server.base + "/setup.exe", source="browser", size=4098))
    assert d.status == Status.CONFIRM and "ui.attention" in seen
    mgr.confirm(d.id, True)
    d = _wait(mgr, d.id, Status.COMPLETE)
    assert os.path.basename(d.directory) == "Program"


def test_pause_resume_remove(env, http_server):
    mgr, settings, seen, tmp = env
    mgr.engine.set_global(max_overall_download_limit="2M")  # yavaslat ki duraklatabilelim
    [d] = mgr.add(DownloadRequest(url=http_server.base + "/big.bin", filename="yavas.bin"))
    _wait(mgr, d.id, Status.ACTIVE)
    mgr.pause(d.id)
    _wait(mgr, d.id, Status.PAUSED)
    time.sleep(0.5)
    assert mgr.store.get(d.id).status == Status.PAUSED
    mgr.engine.set_global(max_overall_download_limit="0")
    mgr.resume(d.id)
    d = _wait(mgr, d.id, Status.COMPLETE)
    assert _sha(d.path) == http_server.sha["big.bin"]
    mgr.remove(d.id, delete_file=True)
    assert not os.path.exists(d.path) and mgr.store.get(d.id) is None


def test_recover_after_restart(tmp_path, http_server):
    """Uygulama kapanip acilinca yarim indirme kaldigi yerden devam eder."""
    settings = Settings(tmp_path / "s.json")
    settings.set("download_dir", str(tmp_path / "dl"))
    db = tmp_path / "k.db"
    e1 = Aria2Engine(paths.ARIA2_EXE)
    e1.start_service()
    m1 = DownloadManager(DownloadStore(db), e1, EventBus(), settings, poll_interval=0.2)
    m1.start()
    e1.set_global(max_overall_download_limit="3M")
    [d] = m1.add(DownloadRequest(url=http_server.base + "/big.bin", filename="devam.bin"))
    _wait(m1, d.id, Status.ACTIVE)
    time.sleep(1.5)
    m1.stop()
    e1.shutdown()
    partial = m1.store.get(d.id).downloaded
    assert 0 < partial < 24 * 1024 * 1024

    e2 = Aria2Engine(paths.ARIA2_EXE)
    e2.start_service()
    m2 = DownloadManager(DownloadStore(db), e2, EventBus(), settings, poll_interval=0.2)
    m2.start()
    try:
        d = _wait(m2, d.id, Status.COMPLETE)
        assert _sha(d.path) == http_server.sha["big.bin"]
        assert d.filename == "devam.bin"  # yeni dosya acmadan devam etti
    finally:
        m2.stop()
        e2.shutdown()
