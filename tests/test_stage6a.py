"""Donma duzeltmesi + bolum 22 kalani + Asama 6a: hedefli testler."""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import inspect
import logging
import threading
import time
import zipfile

import pytest

from app.core import extras, winwin
from app.core.desktop import parse_hotkey
from app.core.events import EventBus
from app.core.manager import DownloadManager
from app.core.models import DownloadRequest, Status
from app.core.plugin_api import PluginRegistry
from app.core.queue_store import DownloadStore
from app.core.settings import Settings
from app.core.watchdog import UiWatchdog, log_slow_calls


class Eng:
    running = True
    connections = 16

    def __init__(self):
        self.calls = []

    def start(self, d):
        return "g%d" % d.id

    def call(self, method, *params, **kw):
        self.calls.append((method, params))
        return "OK"

    def status(self, gids):
        return {}


@pytest.fixture
def mgr(tmp_path):
    settings = Settings(tmp_path / "s.json")
    settings.set("download_dir", str(tmp_path / "dl"))
    return DownloadManager(DownloadStore(tmp_path / "k.db"), Eng(), EventBus(), settings, prober=None)


def make_api(mgr):
    from app.ui.api import Api
    from app.core.torrent import TorrentService
    mgr.torrents = TorrentService(mgr.engine, mgr.store_dir if hasattr(mgr, "store_dir") else
                                  __import__("pathlib").Path(mgr.base_dir()) / "_t")
    return Api(mgr, mgr.engine, PluginRegistry(), lambda: 0)


# ---------------------------------------------------------------- 1) donma
def test_window_front_never_blocks_caller(monkeypatch):
    started, release = threading.Event(), threading.Event()
    calls = []

    def slow_front(hwnd):          # arayuz is parcacigi kilitli gibi: cok bekler
        calls.append(hwnd)
        started.set()
        release.wait(5)
        return True

    monkeypatch.setattr(winwin, "bring_to_front", slow_front)
    monkeypatch.setattr(winwin, "find_window", lambda title, pid=None: 1234)
    wf = winwin.WindowFront("Kami")
    t0 = time.monotonic()
    for _ in range(20):            # kopru art arda istek atiyor
        wf.request()
    assert time.monotonic() - t0 < 0.2          # cagiran asla beklemez
    assert started.wait(2)
    release.set()
    time.sleep(0.3)
    assert 1 <= len(calls) <= 2                 # ust uste istekler birlesir


def test_slow_call_log_keeps_signature(caplog):
    @log_slow_calls
    class A:
        def fast(self, url: str, n: int = 1):
            return url

        def slow(self):
            time.sleep(0.05)

    import app.core.watchdog as w
    old = w.SLOW_CALL_SEC
    assert inspect.getfullargspec(A.fast).args == ["self", "url", "n"]   # pywebview JS taslagi
    log_slow_calls(type("B", (), {"slow": lambda self: time.sleep(0.05)}), threshold=0.01)
    with caplog.at_level(logging.WARNING, logger="kami.watchdog"):
        B = log_slow_calls(type("B", (), {"slow": lambda self: time.sleep(0.05)}), threshold=0.01)
        B().slow()
    assert "Yavas api cagrisi: slow" in caplog.text
    assert w.SLOW_CALL_SEC == old


def test_api_methods_keep_args_for_pywebview():
    from app.ui.api import Api
    assert inspect.getfullargspec(Api.add_url).args == ["self", "url", "filename", "direct"]
    assert inspect.getfullargspec(Api.torrent_meta).args == ["self", "job"]


def test_ui_watchdog_reports_stall_only_when_visible(caplog):
    vis = {"v": False}
    w = UiWatchdog(lambda: vis["v"], stall=8)
    t = time.monotonic()
    assert not w.check(t + 100)                # gizli: zamanlayici durur, donma sayilmaz
    vis["v"] = True
    assert not w.check(t + 101)                # yeni gorundu: sure buradan baslar
    w.last_beat = t + 102
    assert not w.check(t + 109)
    with caplog.at_level(logging.WARNING, logger="kami.watchdog"):
        assert w.check(t + 111)
    assert "yanit vermiyor" in caplog.text and "MainThread" in caplog.text
    assert not w.check(t + 130)                # bir kez bildirir
    w.beat()
    assert "yeniden yanit veriyor" in caplog.text


# ---------------------------------------------------------------- 2) torrent meta veri isi + RD ilerlemesi
class MetaEngine(Eng):
    def __init__(self, torrent_bytes, peers_then_done=3):
        super().__init__()
        self.data = torrent_bytes
        self.left = peers_then_done
        self.dir = None

    def call(self, method, *params, **kw):
        if method == "aria2.addUri":
            self.dir = params[1]["dir"]
            assert "udp://tracker.opentrackr.org:1337/announce" in params[1]["bt-tracker"]
            return "G1"
        if method == "aria2.tellStatus":
            self.left -= 1
            if self.left <= 0:
                import pathlib
                (pathlib.Path(self.dir) / "x.torrent").write_bytes(self.data)
                return {"status": "complete"}
            return {"status": "active", "connections": "7", "numSeeders": "2"}
        return "OK"


def test_magnet_job_reports_peers_then_done(tmp_path, monkeypatch):
    from tests.test_torrent import TORRENT_MULTI
    from app.core.torrent import TorrentService
    import app.core.torrent as T
    monkeypatch.setattr(T.time, "sleep", lambda s: None)
    svc = TorrentService(MetaEngine(TORRENT_MULTI, 3), tmp_path / "t")
    seen = []
    tok, meta = svc.from_magnet("magnet:?xt=urn:btih:" + "a" * 40, on_progress=seen.append)
    assert meta.name == "Sintel" and seen[0]["peers"] == 7 and seen[0]["seeders"] == 2


def test_magnet_job_cancel(tmp_path):
    from app.core.torrent import TorrentService
    svc = TorrentService(MetaEngine(b"", 10_000), tmp_path / "t")
    jid = svc.start_magnet("magnet:?xt=urn:btih:" + "b" * 40)
    time.sleep(0.2)
    assert svc.job(jid)["state"] == "searching"
    svc.cancel_job(jid)
    for _ in range(30):
        if svc.job(jid)["state"] != "searching":
            break
        time.sleep(0.1)
    assert svc.job(jid)["error"] == "cancelled"
    assert svc.job("yok")["error"] == "cloud_expired"


def test_api_torrent_open_magnet_is_background(mgr, monkeypatch):
    from tests.test_torrent import TORRENT_MULTI
    import app.core.torrent as T
    mgr.engine = MetaEngine(TORRENT_MULTI, 2)
    api = make_api(mgr)
    api._manager.torrents.engine = mgr.engine
    r = api.torrent_open("magnet:?xt=urn:btih:" + "c" * 40)
    assert r["ok"] and r["meta_job"]
    for _ in range(50):
        s = api.torrent_meta(r["meta_job"])
        if s["state"] != "searching":
            break
        time.sleep(0.1)
    assert s["state"] == "done" and s["cloud"]["title"] == "Sintel"


def test_tracker_list_merges_downloaded(tmp_path, monkeypatch):
    import app.core.torrent as T
    f = tmp_path / "trackers.txt"
    f.write_text("udp://new.example:6969/announce\n\nhttp://evil example/announce\n", encoding="utf-8")
    monkeypatch.setattr(T, "_TRACKER_FILE", f)
    lst = T.trackers().split(",")
    assert "udp://new.example:6969/announce" in lst and lst[0].startswith("http://tracker.opentrackr")
    assert len(lst) == len(set(lst))


def test_rd_progress_exposed():
    from tests.test_debrid import make
    svc, sess, _, _ = make()
    sess.torrent_state = "downloading"
    svc.add_magnet("magnet:?xt=urn:btih:abc")
    svc.poll_once()
    p = svc.progress()
    assert p and p[0]["name"] == "Album" and p[0]["status"] == "downloading"


# ---------------------------------------------------------------- 3) Asama 6a
def test_parse_hotkey():
    assert parse_hotkey("ctrl+alt+k") == (0x3, ord("K"))
    assert parse_hotkey("Win+Shift+F5") == (0xC, 0x74)
    for bad in ("k", "ctrl+", "foo+k", "ctrl+alt+ü"):
        with pytest.raises(ValueError):
            parse_hotkey(bad)


def test_settings_new_keys(tmp_path):
    s = Settings(tmp_path / "s.json")
    s.set("schedule_start", "2:05")
    assert s.get("schedule_start") == "02:05"
    s.set("hotkey", "Ctrl + Alt + D")
    assert s.get("hotkey") == "ctrl+alt+d"
    for k, v in (("schedule_stop", "25:00"), ("hotkey", "x"), ("defender_mode", "bazen")):
        with pytest.raises(ValueError):
            s.set(k, v)


def test_schedule_window_and_transitions(tmp_path):
    assert extras.in_window(3 * 60, "02:00", "08:00")
    assert not extras.in_window(9 * 60, "02:00", "08:00")
    assert extras.in_window(23 * 60 + 30, "23:00", "07:00") and extras.in_window(60, "23:00", "07:00")
    s = Settings(tmp_path / "s.json")
    s.set("schedule_enabled", True)
    log = []
    sch = extras.Scheduler(s, lambda: log.append("start"), lambda: log.append("stop"))
    day = dt.datetime(2026, 11, 4)
    assert sch.check(day.replace(hour=1)) == ""          # ilk bakis: dokunma
    assert sch.check(day.replace(hour=2, minute=1)) == "start"
    assert sch.check(day.replace(hour=5)) == ""
    assert sch.check(day.replace(hour=8)) == "stop"
    assert log == ["start", "stop"]


def test_should_scan_default_exec_archive(tmp_path):
    assert extras.should_scan("C:/a/setup.EXE", "exec_archive")
    assert extras.should_scan("C:/a/x.7z", "exec_archive")
    assert not extras.should_scan("C:/a/film.mkv", "exec_archive")
    assert extras.should_scan("C:/a/film.mkv", "all")
    assert not extras.should_scan("C:/a/setup.exe", "off")


def test_hash_helpers(tmp_path):
    f = tmp_path / "a.bin"
    f.write_bytes(b"kami" * 1000)
    h = hashlib.sha256(b"kami" * 1000).hexdigest()
    assert extras.sha256_file(str(f)) == h
    assert extras.norm_hash("SHA256: " + h.upper()) == h
    assert extras.norm_hash("sha-256=" + h) == h and extras.norm_hash("abc") == ""


def test_checksum_from_bridge_and_fragment(mgr):
    h = "a" * 64
    d = mgr.add(DownloadRequest(url="https://x.org/f.zip", source="ui", extra={"checksum": "sha256:" + h}))[0]
    assert d.extra["checksum"] == h
    d2 = mgr.add(DownloadRequest(url="https://x.org/g.zip#sha256=" + "b" * 64, source="ui"))[0]
    assert d2.extra["checksum"] == "b" * 64


def test_postcomplete_checksum_mismatch_and_defender(mgr, tmp_path, monkeypatch):
    from app.core.postcomplete import PostComplete
    f = tmp_path / "dl" / "setup.exe"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"MZ123")
    d = mgr.store.add(url="https://x/setup.exe", filename="setup.exe", directory=str(f.parent), category="program",
                      status=Status.COMPLETE, extra={"checksum": "0" * 64})
    scanned = []
    monkeypatch.setattr(extras, "defender_scan", lambda p: scanned.append(p) or "threat")
    notes = []
    pc = PostComplete(mgr, lambda t, m: notes.append(m) or True, focused=lambda: True)
    pc.completed(d.id)
    x = mgr.store.get(d.id).extra
    assert x["checksum_ok"] is False and x["scan"] == "threat" and scanned == [str(f)]
    assert notes and "UYUŞMUYOR" in notes[0] and "TEHDİT" in notes[0]   # pencere ondeyken bile uyarir


def test_postcomplete_quiet_when_focused(mgr, tmp_path):
    from app.core.postcomplete import PostComplete
    mgr.settings.set("defender_mode", "off")
    d = mgr.store.add(url="https://x/a.mkv", filename="a.mkv", directory=str(tmp_path), category="video",
                      status=Status.COMPLETE)
    notes = []
    PostComplete(mgr, lambda t, m: notes.append(m), focused=lambda: True).completed(d.id)
    assert notes == []
    PostComplete(mgr, lambda t, m: notes.append(m), focused=lambda: False).completed(d.id)
    assert notes and notes[0].startswith("İndi: a.mkv")


def test_reorder_sets_positions_and_engine_queue(mgr):
    a, b, c = (mgr.add(DownloadRequest(url=f"https://x.org/{n}.bin", source="ui"))[0] for n in "abc")
    assert [d.id for d in mgr.store.list()] == [c.id, b.id, a.id]     # yeni en ustte
    mgr.reorder([a.id, c.id, b.id])
    assert [d.id for d in mgr.store.list()] == [a.id, c.id, b.id]
    pos = [(p[0], p[1]) for m, p in mgr.engine.calls if m == "aria2.changePosition"]
    assert pos == [("g%d" % a.id, 0), ("g%d" % c.id, 1), ("g%d" % b.id, 2)]


def test_api_hash_and_drop_torrent(mgr, tmp_path):
    from tests.test_torrent import TORRENT_MULTI
    api = make_api(mgr)
    f = tmp_path / "f.bin"
    f.write_bytes(b"x" * 10)
    d = mgr.store.add(url="u", filename="f.bin", directory=str(tmp_path), category="other", status=Status.COMPLETE)
    h = hashlib.sha256(b"x" * 10).hexdigest()
    r = api.hash_file(d.id, "")
    assert r == {"ok": True, "sha256": h, "expected": "", "match": None}
    assert api.hash_file(d.id, h.upper())["match"] is True
    assert api.hash_file(d.id, "zz")["error"] == "bad_hash"
    mgr.settings.set("rd_mode", "off")
    r = api.drop_torrent(base64.b64encode(TORRENT_MULTI).decode())
    assert r["ok"] and r["torrent_local"]["name"] == "Sintel"
    assert api.drop_torrent("bm90IGEgdG9ycmVudA==")["error"] == "bad_torrent"


def test_check_update(monkeypatch):
    import requests

    class R:
        def __init__(self, code, j):
            self.status_code, self._j = code, j

        def json(self):
            return self._j

    monkeypatch.setattr(requests, "get", lambda *a, **k: R(200, {
        "tag_name": "v0.7.0", "html_url": "https://github.com/murasakimono/kami/releases/tag/v0.7.0"}))
    r = extras.check_update("0.6.0")
    assert r["available"] and r["version"] == "0.7.0"
    assert not extras.check_update("0.7.0")["available"]
    monkeypatch.setattr(requests, "get", lambda *a, **k: R(200, {"tag_name": "v9", "html_url": "https://evil/x"}))
    assert extras.check_update("0.6.0")["url"] == "https://github.com/murasakimono/kami/releases"
    monkeypatch.setattr(requests, "get", lambda *a, **k: R(404, {}))
    assert extras.check_update()["none"]


def test_report_masks_secrets(tmp_path, monkeypatch):
    from app import paths
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(paths, "SETTINGS_PATH", tmp_path / "settings.json")
    tok = "Q" * 52
    (tmp_path / "kami.log").write_text(
        f"RD token={tok}\nGET https://dl.rd/file.bin?sig=abc123&exp=9\nAuthorization: Bearer {tok}\n"
        "Cookie: SID=xyz\n", encoding="utf-8")
    (tmp_path / "settings.json").write_text('{"language": "tr"}', encoding="utf-8")
    out = extras.build_report({"items": [{"url": "https://x/a?token=" + tok}]}, tmp_path / "out")
    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
        blob = "".join(z.read(n).decode("utf-8", "replace") for n in names)
    assert {"kami.log.txt", "state.json", "settings.json", "system.json", "threads.txt"} <= names
    assert tok not in blob and "sig=abc123" not in blob and "SID=xyz" not in blob
    assert "rd_token.bin" not in names and "yt_cookies.bin" not in names
