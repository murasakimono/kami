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
