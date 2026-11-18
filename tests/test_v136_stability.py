"""v1.36.0: 4 stabilite ozelligi icin testler (Doktor, Selftest, .kamibak Yedek, Guncelleme Kanali)."""
from __future__ import annotations

import json
import sqlite3
import types
import zipfile
from pathlib import Path
from unittest.mock import patch

from app.core import backup, doctor, extras, selftest


def test_doctor_expanded_and_aria2_fix():
    class FakeEngine:
        running = False

    rep = doctor.run_all(engine=FakeEngine(), ui_errors=[], recoveries=0, download_dir=".")
    ids = {c["id"]: c for c in rep["checks"]}
    for key in ("spotify", "librespot", "playnite", "media", "bridge", "modwins"):
        assert key in ids, f"missing doctor check: {key}"
    assert ids["aria2"]["status"] == "fail"
    assert ids["aria2"]["fix"] == "restart_aria2"


def test_selftest_runs_on_version_change_and_skips_open(tmp_path: Path):
    assert selftest.should_run("1.36.0", data_dir=tmp_path) is True

    api = types.SimpleNamespace(_games_win=object())
    notified: list[str] = []

    def fake_probe(mod: str, title: str, html: str, timeout: float):
        if mod == "studio":
            return {"ok": False, "error": "timeout"}
        return {"ok": True}

    res = selftest.run_selftest(api, "1.36.0", fake_probe, notify_fn=notified.append, data_dir=tmp_path)
    assert res["results"]["games"]["status"] == "skipped"
    assert res["results"]["studio"]["status"] == "fail"
    assert res["results"]["music"]["status"] == "ok"
    assert notified == ["Kami Studio penceresi cevap vermiyor"]
    assert selftest.should_run("1.36.0", data_dir=tmp_path) is False
    assert selftest.should_run("1.36.1", data_dir=tmp_path) is True

    # _SelfTestApiProxy dir() icinde ping ve is_selftest gorunmeli (pywebview get_functions icin)
    class FakeRealApi:
        def ping(self):
            return {"ok": True}

        def is_selftest(self):
            return False

    real_api = FakeRealApi()
    proxy = selftest._SelfTestApiProxy(real_api)
    assert "ping" in dir(proxy) and "is_selftest" in dir(proxy)
    assert real_api.is_selftest() is False and proxy.is_selftest() is True


def test_backup_restore_and_version_guard(tmp_path: Path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "settings.json").write_text(json.dumps({"lang": "tr", "max_concurrent": 5}), "utf-8")
    (src_dir / "media_meta.json").write_text(json.dumps({"m1": {"title": "Film"}}), "utf-8")
    (src_dir / "ytm_playlists.json").write_text(json.dumps([{"id": "PL1", "title": "Test"}]), "utf-8")
    (src_dir / "rd_token.bin").write_bytes(b"dpapi-secret-do-not-export")
    (src_dir / "steam_web.bin").write_bytes(b"dpapi-steam-secret")
    with sqlite3.connect(src_dir / "kami.db") as con:
        con.execute("CREATE TABLE downloads (id TEXT PRIMARY KEY, title TEXT)")
        con.execute("INSERT INTO downloads VALUES ('d1', 'Sample')")
        con.commit()
    with sqlite3.connect(src_dir / "history.db") as con:
        con.execute("CREATE TABLE history (id TEXT PRIMARY KEY, title TEXT)")
        con.execute("INSERT INTO history VALUES ('h1', 'PastDownload')")
        con.commit()

    bak_file = tmp_path / "test.kamibak"
    out = backup.create_backup(
        bak_file,
        data_dir=src_dir,
        db_path=src_dir / "kami.db",
        version="1.36.1",
        local_storage={"kami.recent": "[{\"title\":\"Video1\"}]"},
    )
    assert out["ok"] is True
    with zipfile.ZipFile(bak_file, "r") as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "data/settings.json" in names
        assert "data/kami.db" in names
        assert "data/history.db" in names
        assert "data/media_meta.json" in names
        assert "data/localstorage_backup.json" in names
        assert "data/rd_token.bin" not in names
        assert "data/steam_web.bin" not in names

    # Eski surum yeni yedegi reddetmeli
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()
    (dst_dir / "settings.json").write_text(json.dumps({"lang": "en"}), "utf-8")
    rej = backup.stage_restore(bak_file, target_dir=dst_dir, current_version="1.35.0")
    assert rej["ok"] is False and rej["error"] == "newer_version"

    # Ayni veya yeni surum stage + apply_pending_restore ile acabilmeli
    staged = backup.stage_restore(bak_file, target_dir=dst_dir, current_version="1.36.2")
    assert staged["ok"] is True and staged["staged"] is True
    assert "Real-Debrid" in staged["reenter_keys"] and "Steam API" in staged["reenter_keys"]
    ok_res = backup.apply_pending_restore(target_dir=dst_dir, current_version="1.36.2")
    assert ok_res is not None and ok_res["ok"] is True
    assert Path(ok_res["safety_backup"]).is_dir()
    assert json.loads((dst_dir / "settings.json").read_text("utf-8"))["max_concurrent"] == 5
    assert (dst_dir / "pending_localstorage.json").is_file()
    with sqlite3.connect(dst_dir / "history.db") as con:
        assert con.execute("SELECT title FROM history").fetchall() == [("PastDownload",)]


def test_update_channel_stable_vs_beta():
    class FakeResp:
        def __init__(self, code, data):
            self.status_code = code
            self._data = data

        def json(self):
            return self._data

    def fake_get(url, **kw):
        if url.endswith("/releases/latest"):
            return FakeResp(200, {"tag_name": "v1.36.0", "html_url": f"https://github.com/{extras.GITHUB_REPO}/releases/tag/v1.36.0", "assets": []})
        return FakeResp(200, [
            {"tag_name": "v1.36.0", "prerelease": False, "draft": False, "html_url": f"https://github.com/{extras.GITHUB_REPO}/releases/tag/v1.36.0", "assets": []},
            {"tag_name": "v1.37.0", "prerelease": True, "draft": False, "html_url": f"https://github.com/{extras.GITHUB_REPO}/releases/tag/v1.37.0", "assets": []},
        ])

    with patch("requests.get", side_effect=fake_get):
        st = extras.check_update(current="1.36.0", channel="stable")
        bt = extras.check_update(current="1.36.0", channel="beta")
    assert st["available"] is False and st["version"] == "1.36.0"
    assert bt["available"] is True and bt["version"] == "1.37.0" and bt["prerelease"] is True


def test_music_island_auto_show_hide(monkeypatch):
    """v1.37.5: Kamify gizliyken muzik caliyorsa ada gecici acilir; durunca kapanir; elle acilmis adaya dokunmaz."""
    from app.core import music_hub, winwin
    from app.ui.api import Api
    a = object.__new__(Api)
    a._island_shown, a._island_auto, a._island_win, a._island_factory = False, False, None, None
    calls = []
    def toggle(show=None, persist=True):
        calls.append((show, persist)); a._island_shown = bool(show)
        return {"ok": True}
    a.mini_island_toggle = toggle
    state = {"m": {"playing": True, "title": "Sarki"}, "vis": False}
    monkeypatch.setattr(music_hub, "cached_now", lambda: state["m"])
    monkeypatch.setattr(winwin, "find_window", lambda t: 123)
    monkeypatch.setattr(winwin, "is_visible", lambda h: state["vis"])
    a.music_island_tick()
    assert calls[-1] == (True, False) and a._island_auto          # gizli + caliyor -> ac (ayara yazmadan)
    state["vis"] = True; a.music_island_tick()
    assert calls[-1] == (False, False) and not a._island_auto     # Kamify one geldi -> kapat
    a._island_shown, a._island_auto = True, False                 # kullanici elle acti
    state["vis"] = False; state["m"] = None; n = len(calls); a.music_island_tick()
    assert len(calls) == n                                         # elle acilmis adaya dokunulmaz


def test_progid_icon_prefers_versioned_file(tmp_path):
    import os, sys, time
    import pytest
    if sys.platform != "win32":
        pytest.skip("winreg yalniz Windows'ta")
    from app.core import setup_tasks
    exe = tmp_path / "Kami.exe"; exe.write_bytes(b"x")
    d = tmp_path / "icons"; d.mkdir()
    (d / "player.ico").write_bytes(b"x")
    old = d / "player-1373.ico"; old.write_bytes(b"x"); os.utime(old, (time.time() - 100, time.time() - 100))
    new = d / "player-1375.ico"; new.write_bytes(b"x")
    assert setup_tasks._progid_icon(str(exe), "Kami.Video") == f'"{new}",0'
    assert setup_tasks._progid_icon(str(exe), "Kami.Image") == f'"{exe}",0'


def test_icon_layers_small_variant(tmp_path):
    from PIL import Image
    from app.core import icons
    p = icons.write_ico("player", tmp_path / "p.ico")
    assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= set(Image.open(p).info["sizes"])
    assert icons.export_all(tmp_path / "out")[0].name.startswith("player-")


def test_music_island_does_not_close_room_island(monkeypatch):
    from app.core import music_hub, winwin
    from app.ui.api import Api
    a = object.__new__(Api)
    a._island_shown, a._island_auto, a._room_island = True, True, {"people": [1]}
    calls = []
    a.mini_island_toggle = lambda show=None, persist=True: calls.append(show)
    monkeypatch.setattr(music_hub, "cached_now", lambda: None)
    monkeypatch.setattr(winwin, "find_window", lambda t: 0)
    a.music_island_tick()
    assert calls == []   # oda suruyor: muzik durdu diye Oda'nin adasi kapanmaz
