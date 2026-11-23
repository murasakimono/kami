"""Paket 1 kritik bug ve guvenlik duzeltmeleri regresyon testleri."""
from __future__ import annotations

import http.client
import json
import threading
import time
import types
import zipfile
from pathlib import Path
from unittest.mock import patch


def test_mpv_engine_search_dirs_uses_bin_dir(tmp_path: Path, monkeypatch):
    from app import paths
    from app.core import mpv_engine

    fake_bin = tmp_path / "bin"
    mpv_sub = fake_bin / "mpv"
    mpv_sub.mkdir(parents=True)
    exe = mpv_sub / "mpv.exe"
    exe.write_bytes(b"MZ")

    monkeypatch.setattr(paths, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(paths, "BIN_DIR", fake_bin)
    monkeypatch.setattr(mpv_engine.shutil, "which", lambda _name: "")

    dirs = mpv_engine._search_dirs()
    assert mpv_sub in dirs and fake_bin in dirs
    res = mpv_engine.find_mpv()
    assert res["exe"] == str(exe)


def test_kami_booth_lan_bind_and_token_auth(tmp_path: Path, monkeypatch):
    from app.core import beat_studio, kami_booth

    monkeypatch.setattr(beat_studio, "recordings_dir", lambda: tmp_path)
    monkeypatch.setattr(
        beat_studio,
        "load_project",
        lambda pid: {"ok": True, "project": {"id": pid, "lyrics": "test sozleri", "bpm": 128, "name": "Demo"}},
    )
    monkeypatch.setattr(
        beat_studio,
        "add_take_to_track",
        lambda pid, tid, path, label="": {"ok": True, "take": {"id": "t1", "path": path}},
    )

    srv = kami_booth.BoothServer()
    st = srv.start("p1", "vocal1")
    try:
        assert st["running"] is True
        assert srv._srv is not None
        assert srv._srv.server_address[0] == "0.0.0.0"
        tok = st["token"]
        assert tok and f"?token={tok}" in st["url"]
        port = st["port"]

        # Token olmadan reddedilmeli
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request("GET", "/")
        assert c.getresponse().status == 403
        c.close()

        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request("GET", "/api/teleprompter")
        assert c.getresponse().status == 401
        c.close()

        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request("POST", "/api/upload_wav", body=b"RIFFdata", headers={"Content-Type": "audio/wav", "Content-Length": "8"})
        assert c.getresponse().status == 401
        c.close()

        # Query token ile HTML acilir ve HttpOnly Cookie set edilir
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request("GET", f"/?token={tok}")
        r = c.getresponse()
        r.read()
        assert r.status == 303 and r.getheader("Location") == "/"   # v2.5.3: cerez kurulur, tokensiz adrese yonlendirilir
        sc = r.getheader("Set-Cookie") or ""
        assert f"kami_booth_tok={tok}" in sc and "HttpOnly" in sc and "SameSite=Strict" in sc
        c.close()

        # Cookie ile teleprompter okunur
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request("GET", "/api/teleprompter", headers={"Cookie": f"kami_booth_tok={tok}"})
        r = c.getresponse()
        body = json.loads(r.read().decode("utf-8"))
        assert r.status == 200 and body["ok"] is True and body["lyrics"] == "test sozleri"
        c.close()

        # X-Booth-Token ile WAV yuklenir
        payload = b"RIFF0000WAVE"
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request(
            "POST",
            "/api/upload_wav",
            body=payload,
            headers={"Content-Type": "audio/wav", "X-Booth-Token": tok, "Content-Length": str(len(payload))},
        )
        r = c.getresponse()
        up = json.loads(r.read().decode("utf-8"))
        assert r.status == 200 and up["ok"] is True and Path(up["path"]).read_bytes() == payload
        c.close()
    finally:
        srv.stop()
    assert srv._token == ""


def test_games_companion_zip_slip_and_drive_prefix_blocked(tmp_path: Path, monkeypatch):
    from app.core import games_companion as gc

    monkeypatch.setattr(gc, "_mod_backups_dir", lambda: tmp_path / "mb")

    zp = tmp_path / "evil.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("good/save.dat", b"OK")
        zf.writestr("../escaped.txt", b"BAD1")
        zf.writestr("/abs_escaped.txt", b"BAD2")
        zf.writestr("C:drive_evil.txt", b"BAD3")
        zf.writestr("sub\\..\\..\\win_escaped.txt", b"BAD4")

    dst = tmp_path / "restore_target"
    res = gc.restore_snapshot(str(zp), str(dst))
    assert res["ok"] is True
    assert (dst / "good" / "save.dat").read_bytes() == b"OK"
    assert not (tmp_path / "escaped.txt").exists()
    assert not (tmp_path / "win_escaped.txt").exists()
    assert not (dst / "C:drive_evil.txt").exists()

    gdir = tmp_path / "game_dir"
    gdir.mkdir()
    inst = gc.mod_install_zip("cyberpunk", str(gdir), str(zp))
    assert inst["ok"] is True and inst["added"] == 1 and inst["overwritten"] == 0
    assert (gdir / "good" / "save.dat").read_bytes() == b"OK"
    assert not (tmp_path / "escaped.txt").exists()
    assert not (gdir / "C:drive_evil.txt").exists()


def test_converter_video_maps_skip_bitmap_subtitles(tmp_path: Path, monkeypatch):
    from app.core import converter

    src = tmp_path / "movie.mkv"
    src.write_bytes(b"\x00")
    captured: list[list[str]] = []

    monkeypatch.setattr(converter, "_duration", lambda *_a: 10.0)
    monkeypatch.setattr(converter, "has_nvenc", lambda _ff: False)
    monkeypatch.setattr(converter, "_ffmpeg", lambda ff, args, *_a: captured.append(list(args)))

    tools = {"ffmpeg": "ffmpeg", "ffprobe": "ffprobe"}
    for ext in ("mp4", "webm"):
        converter._media(str(src), ext, {"folder": str(tmp_path), "hw": False}, tools, lambda *_: None, threading.Event())

    assert len(captured) == 2
    for args in captured:
        idx_v = args.index("-map")
        assert args[idx_v : idx_v + 4] == ["-map", "0:v:0", "-map", "0:a:0?"]


def test_torrent_and_rss_lock_thread_safety(tmp_path: Path, monkeypatch):
    from app.core import rss
    from app.core.torrent import TorrentMeta, TorrentService

    class _DummyEngine:
        def call(self, *_a, **_kw):
            return {}

    tsrv = TorrentService(_DummyEngine(), tmp_path / "tor")

    def fake_from_magnet(magnet, timeout=180.0, on_progress=None, cancel=None):
        for i in range(40):
            if on_progress:
                on_progress({"peers": i, "seeders": 1, "elapsed": i})
            time.sleep(0.001)
        return "tok_123", TorrentMeta(name="x", infohash="0" * 40)

    monkeypatch.setattr(tsrv, "from_magnet", fake_from_magnet)
    jid = tsrv.start_magnet("magnet:?xt=urn:btih:" + ("a" * 40))
    for _ in range(80):
        st = tsrv.job(jid)
        assert isinstance(st, dict)
        if st.get("state") in ("done", "error"):
            break
        time.sleep(0.001)

    monkeypatch.setattr(rss, "_file", lambda: tmp_path / "rss.json")
    xml = (
        b"<rss><channel><title>Show</title>"
        b"<item><title>Show.S01E01.1080p</title><link>https://example.com/1.torrent</link><guid>g1</guid></item>"
        b"</channel></rss>"
    )
    rsrv = rss.RssService(fetch=lambda _u: xml, add=lambda _it, _f: True)
    rsrv.add_feed("https://example.com/feed.xml")

    errors: list[Exception] = []

    def worker_check():
        try:
            for _ in range(10):
                rsrv.check(force=True)
        except Exception as exc:
            errors.append(exc)

    def worker_public():
        try:
            for _ in range(25):
                rsrv.public()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker_check), threading.Thread(target=worker_public)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    assert errors == []


def test_recorder_save_replay_lock_without_deadlock(tmp_path: Path, monkeypatch):
    from app.core import recorder

    monkeypatch.setattr(recorder, "clips_dir", lambda: tmp_path / "clips")
    rec = recorder.Recorder(lambda: "ffmpeg", {"rec_replay_seconds": 30}, lambda *_: None)
    rec.work = tmp_path / "work"
    rec.work.mkdir(parents=True)
    seg = rec.work / "seg_000.ts"
    seg.write_bytes(b"TSDATA")
    rec.buf = types.SimpleNamespace(poll=lambda: None)

    events: list[str] = []
    real_lock = rec.lock

    class _SpyLock:
        def __enter__(self):
            events.append("enter")
            return real_lock.__enter__()

        def __exit__(self, exc_type, exc, tb):
            events.append("exit")
            return real_lock.__exit__(exc_type, exc, tb)

    rec.lock = _SpyLock()
    monkeypatch.setattr(recorder.subprocess, "run", lambda *a, **kw: types.SimpleNamespace(returncode=0))
    monkeypatch.setattr(rec, "_duration", lambda _p: 5.0)
    monkeypatch.setattr(rec, "_mux", lambda joined, t0, t1, out, cut=0.0, job=None: out.parent.mkdir(parents=True, exist_ok=True) or out.write_bytes(b"MP4"))

    out = rec.save_replay(15)
    assert Path(out).is_file()
    assert events.count("enter") >= 2 and events.count("enter") == events.count("exit")


def test_cast_server_range_416_and_suffix(tmp_path: Path, monkeypatch):
    from app.core import player_plus

    monkeypatch.setattr(player_plus, "lan_ip", lambda: "127.0.0.1")
    f = tmp_path / "sample.bin"
    payload = b"0123456789" * 10
    f.write_bytes(payload)

    srv = player_plus.CastServer()
    url = srv.share(str(f))
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        port = parsed.port

        # Suffix range: son 10 bayt
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request("GET", parsed.path, headers={"Range": "bytes=-10"})
        r = c.getresponse()
        data = r.read()
        assert r.status == 206
        assert r.getheader("Content-Range") == "bytes 90-99/100"
        assert data == b"0123456789"
        c.close()

        # Out-of-bounds range -> 416
        for bad_rng in ("bytes=150-200", "bytes=20-10", "bytes=-0"):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            c.request("GET", parsed.path, headers={"Range": bad_rng})
            r = c.getresponse()
            r.read()
            assert r.status == 416
            assert r.getheader("Content-Range") == "bytes */100"
            c.close()
    finally:
        srv.stop()


def test_grab_all_cleans_cookie_file_when_popen_fails(tmp_path: Path, monkeypatch):
    from app.core import grab_all

    ck = tmp_path / "kami_ga_test.txt"
    ck.write_text("# cookie", encoding="utf-8")

    monkeypatch.setattr(grab_all, "ensure_gallery_dl", lambda: (True, ["gallery-dl"]))
    monkeypatch.setattr(grab_all, "_write_cookies", lambda _url: str(ck))

    with patch("subprocess.Popen", side_effect=OSError("popen failed")):
        try:
            grab_all.start("https://x.com/test/status/1", str(tmp_path / "out"))
            raised = False
        except OSError:
            raised = True
    assert raised is True and not ck.exists()


def test_oracle_relay_secret_dpapi_migration_and_backup_label(tmp_path: Path, monkeypatch):
    from app import paths
    from app.core import backup
    from app.ui.api import Api

    assert "oracle_relay_secret.bin" in backup.DPAPI_KEY_LABELS

    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    store_data = {"oracle_relay_secret": "legacy-hmac-secret", "listenbrainz_token": ""}
    settings_stub = types.SimpleNamespace(
        all=lambda: dict(store_data),
        get=lambda k, d=None: store_data.get(k, d),
        set=lambda k, v: store_data.__setitem__(k, v),
    )
    api = object.__new__(Api)
    api._manager = types.SimpleNamespace(settings=settings_stub, base_dir=lambda: str(tmp_path))

    got = api.get_settings()
    assert got["oracle_relay_secret"] == ""
    assert got["_has_oracle_relay_secret"] is True
    assert store_data["oracle_relay_secret"] == ""
    assert (tmp_path / "oracle_relay_secret.bin").is_file()
    assert api._oracle_secret() == "legacy-hmac-secret"

    res = api.set_setting("oracle_relay_secret", "updated-hmac-secret")
    assert res["ok"] is True and res["value"] == "" and res["_has_oracle_relay_secret"] is True
    assert store_data["oracle_relay_secret"] == ""
    assert api._oracle_secret() == "updated-hmac-secret"
