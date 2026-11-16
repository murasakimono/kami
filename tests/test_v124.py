"""v1.24: Kami Doktor, arayuz bekcisi kurtarma, oda sifresi + ses panosu, Kasa anlamsal katman (sahte gomme)."""
import hashlib
import json
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image


def test_watchdog_recovers_once():
    from app.core.watchdog import UiWatchdog
    calls = []
    wd = UiWatchdog(lambda: True, stall=1, on_recover=lambda: calls.append(1), recover_after=5)
    wd._visible_since = wd.last_beat = 0.0
    wd._was_visible = True
    assert wd.check(now=2.0) is True          # donma bildirildi
    assert wd.check(now=3.0) is False         # henuz kurtarma yok
    assert wd.check(now=6.0) is True          # kurtarma tetiklendi
    assert wd.check(now=9.0) is False         # ayni bolumde ikinci kez yok
    import time
    time.sleep(0.2)
    assert calls == [1] and wd.recoveries == 1


def test_doctor_runs_all_checks(tmp_path, monkeypatch):
    from app.core import doctor
    r = doctor.run_all()
    ids = {c["id"] for c in r["checks"]}
    assert {"disk", "ffmpeg", "ytdlp", "virtual", "ui"} <= ids
    assert all(c["status"] in ("ok", "warn", "fail", "info") for c in r["checks"])


def test_room_password_and_soundboard():
    from app.core.room import RoomServer, soundboard_list
    sounds = soundboard_list()
    assert len(sounds) >= 20 and all({"id", "label", "cat"} <= set(s) for s in sounds)
    srv = RoomServer()
    pw = hashlib.sha256(b"gizli").hexdigest()
    srv.key_hash = lambda: pw
    srv.start("Test", tunnel=False, room_id="odatest123")
    try:
        base = f"http://127.0.0.1:{srv.httpd.server_address[1]}/odatest123/"
        info = json.loads(urllib.request.urlopen(base + "info").read())
        assert info["locked"] is True
        try:
            urllib.request.urlopen(base + "ice")
            raise AssertionError("sifresiz girdi")
        except urllib.error.HTTPError as e:
            assert e.code == 401
        ok = json.loads(urllib.request.urlopen(base + "ice?k=" + pw).read())
        assert "iceServers" in ok
        lst = json.loads(urllib.request.urlopen(base + "sb?k=" + pw).read())
        assert lst["sounds"]
    finally:
        srv.stop()


def test_kasa_semantic_merge(tmp_path, monkeypatch):
    from app.core import kasa_embed
    from app.core import semantic_vault as sv
    db = tmp_path / "k.db"
    a, b = tmp_path / "sahil_gun_batimi.jpg", tmp_path / "kar_dag.jpg"
    Image.new("RGB", (32, 32), (200, 90, 40)).save(a)
    Image.new("RGB", (32, 32), (250, 250, 250)).save(b)

    def vec(t):
        t = t.lower()
        return [1.0, 0.1, 0.0] if ("sahil" in t or "beach" in t) else [0.1, 1.0, 0.0]
    monkeypatch.setattr(kasa_embed, "available", lambda: True)
    monkeypatch.setattr(kasa_embed, "embed_text", lambda ts: [vec(t) for t in ts])
    monkeypatch.setattr(kasa_embed, "embed_clip_text", lambda ts: [vec(t) for t in ts])
    monkeypatch.setattr(kasa_embed, "embed_images", lambda ps: [vec(Path(p).stem) for p in ps])
    assert sv.index_media(a, db_path=db)["semantic"] and sv.index_media(b, db_path=db)["semantic"]
    r = sv.semantic_search("deniz kenari beach", db_path=db)
    assert r["semantic"] and r["results"][0]["title"].startswith("sahil")
    assert sv.kasa_stats(db)["files"] == 2


def test_kasa_falls_back_without_tool(tmp_path, monkeypatch):
    from app.core import kasa_embed
    from app.core import semantic_vault as sv
    monkeypatch.setattr(kasa_embed, "available", lambda: False)
    img = tmp_path / "kirmizi_araba.jpg"
    Image.new("RGB", (16, 16), (255, 0, 0)).save(img)
    db = tmp_path / "k.db"
    assert sv.index_media(img, db_path=db)["semantic"] is False
    r = sv.semantic_search("araba", db_path=db)
    assert r["semantic"] is False and r["results"][0]["title"] == "kirmizi araba"
