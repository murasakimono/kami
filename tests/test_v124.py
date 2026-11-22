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
    import http.cookiejar
    from app.core.room import RoomServer, hash_pw, soundboard_list
    sounds = soundboard_list()
    assert len(sounds) >= 20 and all({"id", "label", "cat"} <= set(s) for s in sounds)
    srv = RoomServer()
    srv.key_hash = lambda: hash_pw("gizli")
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
        # Eski ?k= sorgu parametresi artik kabul edilmemeli
        try:
            urllib.request.urlopen(base + "ice?k=gizli")
            raise AssertionError("URL query ile girdi")
        except urllib.error.HTTPError as e:
            assert e.code == 401
        # X-Kami-Key basligi veya POST /unlock oturum cerezi ile giris
        req_hdr = urllib.request.Request(base + "ice", headers={"X-Kami-Key": "gizli"})
        assert "iceServers" in json.loads(urllib.request.urlopen(req_hdr).read())
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        ureq = urllib.request.Request(base + "unlock", data=json.dumps({"password": "gizli"}).encode(),
                                      headers={"Content-Type": "application/json"})
        assert json.loads(opener.open(ureq).read())["ok"] is True
        lst = json.loads(opener.open(base + "sb").read())
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


def test_kapsul_share_page_range_password(tmp_path, monkeypatch):
    import http.cookiejar
    monkeypatch.setattr("app.core.kapsul._store", lambda: tmp_path / "kapsul.json")
    from app.core import kapsul
    from app.core.room import RoomServer
    f = tmp_path / "şarkı demo.mp3"
    f.write_bytes(bytes(range(256)) * 40)
    r = kapsul.create(str(f), hours=1, password="1234", max_dl=1)
    assert r["ok"] and r["locked"]
    srv = RoomServer()
    srv.start("Test", tunnel=False, room_id="odatest456")
    try:
        base = f"http://127.0.0.1:{srv.httpd.server_address[1]}/c/{r['id']}"
        html_ = urllib.request.urlopen(base).read().decode()
        assert "KAMI KAPSÜL" in html_ and "şarkı demo.mp3" in html_
        assert "?p=" not in html_
        try:
            urllib.request.urlopen(base + "/raw")
            raise AssertionError("sifresiz indi")
        except urllib.error.HTTPError as e:
            assert e.code == 401
        try:
            urllib.request.urlopen(base + "/raw?p=1234")
            raise AssertionError("URL query ile indi")
        except urllib.error.HTTPError as e:
            assert e.code == 401
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        ureq = urllib.request.Request(base + "/unlock", data=json.dumps({"password": "1234"}).encode(),
                                      headers={"Content-Type": "application/json"})
        assert json.loads(opener.open(ureq).read())["ok"] is True
        req = urllib.request.Request(base + "/raw", headers={"Range": "bytes=10-19"})
        resp = opener.open(req)
        assert resp.status == 206 and resp.read() == bytes(range(10, 20))
        dl = opener.open(base + "/dl")
        assert len(dl.read()) == 256 * 40 and "filename*=UTF-8''" in dl.headers["Content-Disposition"]
        try:   # indirme siniri 1: kapsul oldu
            urllib.request.urlopen(base)
            raise AssertionError("sinir asildi")
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        srv.stop()


def test_privacy_shield_regions_and_exif(tmp_path, monkeypatch):
    from app.core import privacy
    assert privacy.tc_valid("10000000146") and not privacy.tc_valid("12345678901")
    src = tmp_path / "ekran.jpg"
    im = Image.new("RGB", (400, 200), (255, 255, 255))
    exif = Image.Exif(); exif[0x8825] = {2: (41.0, 0.0, 0.0)}   # GPS
    im.save(src, exif=exif)
    scan = {"lines": [{"text": "ara 0532 123 45 67", "words": [
        {"t": "ara", "x": 10, "y": 10, "w": 30, "h": 20}, {"t": "0532", "x": 50, "y": 10, "w": 40, "h": 20},
        {"t": "123", "x": 95, "y": 10, "w": 30, "h": 20}, {"t": "45", "x": 130, "y": 10, "w": 20, "h": 20},
        {"t": "67", "x": 155, "y": 10, "w": 20, "h": 20}]}], "faces": [{"x": 250, "y": 60, "w": 80, "h": 80}]}
    monkeypatch.setattr(privacy, "_scan", lambda p, f: scan)
    r = privacy.shield_image(str(src))
    assert r["ok"] and r["found"] == {"phone": 1, "face": 1}
    regs = {x["kind"]: x["box"] for x in r["regions"]}
    assert regs["phone"][0] == 50 and regs["phone"][2] == 175   # "ara" kelimesi gizlenmez
    with Image.open(r["path"]) as out:
        assert not out.getexif().get(0x8825)
