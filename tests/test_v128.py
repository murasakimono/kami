"""v1.28 Player+: m3u/XMLTV, intro parmak izi hizalama, film adi tahmini, DLNA cevabi."""
import random

from app.core import player_plus as PP


def test_parse_m3u():
    txt = '#EXTM3U url-tvg="http://e/epg.xml"\n#EXTINF:-1 tvg-id="trt1" tvg-logo="http://l/1.png" group-title="Ulusal",TRT 1\nhttp://s/trt1.m3u8\n' \
          '#EXTINF:-1,Radyo\n#EXTGRP:Radyo\nrel/radyo.mp3\n'
    ch = PP.parse_m3u(txt, "http://base/list.m3u")
    assert ch[0] == {"name": "TRT 1", "group": "Ulusal", "logo": "http://l/1.png", "id": "trt1", "chno": "", "url": "http://s/trt1.m3u8"}
    assert ch[1]["url"] == "http://base/rel/radyo.mp3" and ch[1]["group"] == "Radyo"


def test_parse_xmltv_now_next():
    import time
    now = time.time()
    f = lambda t: time.strftime("%Y%m%d%H%M%S", time.localtime(t))   # noqa: E731
    xml = f'''<tv><programme start="{f(now - 3600)}" stop="{f(now - 1800)}" channel="trt1"><title>Eski</title></programme>
    <programme start="{f(now - 600)}" stop="{f(now + 600)}" channel="trt1"><title>Haber</title></programme>
    <programme start="{f(now + 600)}" stop="{f(now + 3600)}" channel="trt1"><title>Dizi</title></programme>
    <programme start="{f(now)}" stop="{f(now + 60)}" channel="baska"><title>X</title></programme></tv>'''.encode()
    e = PP.parse_xmltv(xml, {"trt1"}, now)
    assert [p["title"] for p in e["trt1"]] == ["Haber", "Dizi"] and "baska" not in e


def test_fingerprint_offset_finds_shifted_intro():
    rnd = random.Random(3)
    intro = [rnd.getrandbits(32) for _ in range(200)]
    ep1 = [rnd.getrandbits(32) for _ in range(100)] + intro + [rnd.getrandbits(32) for _ in range(300)]
    ep2 = [rnd.getrandbits(32) for _ in range(260)] + intro + [rnd.getrandbits(32) for _ in range(100)]
    assert PP.best_offset(ep1, 100, 200, ep2) in (259, 260)
    assert PP.best_offset(ep1, 100, 200, [rnd.getrandbits(32) for _ in range(600)]) is None


def test_guess_movie():
    assert PP.guess_movie("Inception.2010.1080p.BluRay.x264") == ("Inception", "2010")
    assert PP.guess_movie("Esaretin Bedeli (1994) [Turkce]") == ("Esaretin Bedeli", "1994")


def test_learn_and_find_intro_same_file(tmp_path, monkeypatch):
    monkeypatch.setattr(PP, "_INTRO", PP._Store("intro_test.json"))
    monkeypatch.setattr(PP._INTRO, "f", tmp_path / "i.json")
    PP._INTRO.d = {}
    assert PP.learn_intro("C:/d/ep1.mkv", "Dizi", 62, 151)["ok"]
    assert PP.find_intro("C:/d/ep1.mkv", "Dizi")[0]["start"] == 62
