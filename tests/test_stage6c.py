"""Asama 6c: site kurallari, gecmis, otomatik isler, kapatma, link yenileme, telefon, ntfy, toplu link, izle."""
from __future__ import annotations

import json
import socket
import time
import urllib.request
import zipfile

import pytest

from app.core import automate, rules, watch
from app.core.models import DownloadRequest, Status
from tests.test_stage6a import make_api, mgr  # noqa: F401


# ---------------------------------------------------------------- kurallar
def test_rule_youtube_song_matches_only_music():
    rs = [rules.clean_rule(r) for r in rules.DEFAULT_RULES]
    yt = "https://www.youtube.com/watch?v=x"
    assert rules.match(rs, yt, media=True, info={"categories": ["Music"]})["format"] == "mp3"
    assert rules.match(rs, yt, media=True, info={"categories": ["Gaming"]}) is None
    assert rules.match(rs, "https://music.youtube.com/watch?v=x", media=True, info={}) is not None
    assert rules.match(rs, "https://vimeo.com/1", media=True, info={"categories": ["Music"]}) is None


def test_rule_file_ext_folder(mgr, tmp_path):  # noqa: F811
    mgr.settings.set("site_rules", [{"name": "arsiv", "host": "example.com", "ext": "zip,rar",
                                     "folder": str(tmp_path / "Zipler")}])
    d = mgr.add(DownloadRequest(url="https://dl.example.com/a/b.zip", filename="b.zip", source="ui"))[0]
    assert d.directory == str(tmp_path / "Zipler")
    d2 = mgr.add(DownloadRequest(url="https://dl.example.com/a/c.mp4", filename="c.mp4", source="ui"))[0]
    assert d2.directory != str(tmp_path / "Zipler")
    with pytest.raises(ValueError):
        rules.clean_rule({"folder": "goreli/klasor"})


def test_media_probe_applies_rule_and_auto(mgr, monkeypatch):  # noqa: F811
    from app.engines import ytdlp_engine as yt
    api = make_api(mgr)
    monkeypatch.setattr(yt, "probe", lambda url, headers=None: {"kind": "video", "title": "Sarki", "url": url,
                                                                "categories": ["Music"], "heights": []})
    mgr.settings.set("site_rules", rules.DEFAULT_RULES)
    r = api.media_probe("https://www.youtube.com/watch?v=x")
    assert r["defaults"]["format"] == "mp3" and r["defaults"]["audio_kbps"] == 320 and r["rule"]
    added = api.add_media([{"url": "https://www.youtube.com/watch?v=x", "title": "Sarki"}], r["defaults"])
    d = mgr.store.get(added["ids"][0])
    assert d.directory.endswith("Müzik")
    mgr.settings.set("site_rules", [{**rules.DEFAULT_RULES[0], "auto": True}])
    r = api.media_probe("https://www.youtube.com/watch?v=y")
    assert r["ids"] and "media" not in r


# ---------------------------------------------------------------- gecmis + uyarilar
def test_history_dup_warning(mgr, tmp_path):  # noqa: F811
    h = automate.History(tmp_path / "h.db")
    mgr.history = h
    warns = []
    mgr.events.on("ui.warn", lambda **kw: warns.append(kw))
    d = mgr.add(DownloadRequest(url="https://www.youtube.com/watch?v=abc&t=10", source="ui", filename="v.mp4"))[0]
    h.add(mgr.store.update(d.id, status=Status.COMPLETE, finished_at=time.time()))
    assert automate.url_key("https://youtu.be/abc") == "yt:abc"
    mgr.add(DownloadRequest(url="https://youtu.be/abc", source="ui", filename="v2.mp4"))
    assert warns and warns[-1]["kind"] == "dup" and warns[-1]["name"] == "v.mp4"
    assert h.search("v.mp4")[0]["filename"] == "v.mp4" and h.search("yok") == []


def test_disk_warning(mgr, monkeypatch):  # noqa: F811
    warns = []
    mgr.events.on("ui.warn", lambda **kw: warns.append(kw))
    monkeypatch.setattr(automate.shutil, "disk_usage", lambda p: type("U", (), {"free": 100 * 1024 * 1024})())
    mgr.add(DownloadRequest(url="https://e.com/big.iso", filename="big.iso", size=5 * 1024 ** 3, source="ui"))
    assert any(w["kind"] == "disk" for w in warns)


# ---------------------------------------------------------------- bitince isler
def test_after_extract_and_delete(mgr, tmp_path):  # noqa: F811
    z = tmp_path / "paket.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("ic/dosya.txt", "merhaba")
    d = mgr.add(DownloadRequest(url="https://e.com/paket.zip", filename="paket.zip", source="ui",
                                directory=str(tmp_path)))[0]
    mgr.store.update(d.id, status=Status.COMPLETE)
    mgr.settings.set("auto_extract", True)
    mgr.settings.set("auto_extract_delete", True)
    import app.core.automate as am
    orig = am.find_7z
    am.find_7z = lambda: ""   # zipfile yolu (7-Zip olmasa da calissin)
    try:
        automate.AfterActions(mgr, None)(d.id)
    finally:
        am.find_7z = orig
    assert (tmp_path / "paket" / "ic" / "dosya.txt").read_text() == "merhaba"
    assert not z.exists()
    assert mgr.store.get(d.id).extra["extracted"].endswith("paket")


def test_zip_slip_rejected(tmp_path, monkeypatch):
    z = tmp_path / "kotu.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("../disari.txt", "x")
    monkeypatch.setattr(automate, "find_7z", lambda: "")
    assert automate.extract(str(z)) == ""
    assert not (tmp_path / "disari.txt").exists()


def test_multipart_helpers(tmp_path):
    for n in ("film.part1.rar", "film.part2.rar", "film.part3.rar", "baska.rar"):
        (tmp_path / n).write_bytes(b"x")
    assert automate.is_multipart_tail("film.part2.rar") and not automate.is_multipart_tail("film.part1.rar")
    parts = sorted(p.split("\\")[-1].split("/")[-1] for p in automate.archive_parts(str(tmp_path / "film.part1.rar")))
    assert parts == ["film.part1.rar", "film.part2.rar", "film.part3.rar"]


def test_music_move(mgr, tmp_path):  # noqa: F811
    src = tmp_path / "in"
    src.mkdir()
    (src / "s.mp3").write_bytes(b"ID3")
    (src / "s.lrc").write_text("[00:01]x", encoding="utf-8")
    d = mgr.add(DownloadRequest(url="https://e.com/s.mp3", filename="s.mp3", source="ui", directory=str(src)))[0]
    mgr.store.update(d.id, status=Status.COMPLETE, category="music")
    mgr.settings.set("music_move", True)
    automate.AfterActions(mgr, None, music_dir=lambda: str(tmp_path / "PM"))(d.id)
    assert (tmp_path / "PM" / "s.mp3").exists() and (tmp_path / "PM" / "s.lrc").exists()
    assert mgr.store.get(d.id).directory == str(tmp_path / "PM")


def test_ntfy_each_and_errors(mgr, monkeypatch):  # noqa: F811
    sent = []
    monkeypatch.setattr(automate, "ntfy_send", lambda srv, topic, title, msg, tags="": sent.append((topic, title)))
    d = mgr.add(DownloadRequest(url="https://e.com/a.bin", filename="a.bin", source="ui"))[0]
    mgr.settings.set("ntfy_enabled", True)
    mgr.settings.set("ntfy_each", True)
    a = automate.AfterActions(mgr, None, ntfy_topic=lambda: "gizlikonu123")
    a(d.id)
    a.failed(d.id)
    assert sent == [("gizlikonu123", "Kami"), ("gizlikonu123", "Kami: hata")]


# ---------------------------------------------------------------- kapatma
def test_shutdown_countdown_and_cancel(mgr):  # noqa: F811
    calls = []
    done = []
    sw = automate.ShutdownWatcher(mgr, do_shutdown=lambda: calls.append(1), on_queue_done=lambda: done.append(1))
    sw.COUNTDOWN = 0.05
    d = mgr.add(DownloadRequest(url="https://e.com/a.bin", filename="a.bin", source="ui"))[0]
    mgr.settings.set("shutdown_when_done", True)
    sw.step()                                   # is var
    assert sw.deadline is None
    mgr.store.update(d.id, status=Status.COMPLETE)
    sw.step()                                   # geri sayim basladi
    assert sw.deadline is not None and sw.state()["countdown"] is not None and done == [1]
    sw.cancel()
    sw.step()
    assert calls == [] and not mgr.settings.get("shutdown_when_done")
    # tekrar kur, iptal etme -> kapat
    mgr.store.update(d.id, status=Status.QUEUED)
    mgr.settings.set("shutdown_when_done", True)
    sw.step()
    mgr.store.update(d.id, status=Status.COMPLETE)
    sw.step()
    time.sleep(0.08)
    sw.step()
    assert calls == [1] and not mgr.settings.get("shutdown_when_done")   # tek seferlik


def test_shutdown_needs_prior_work(mgr):  # noqa: F811
    calls = []
    sw = automate.ShutdownWatcher(mgr, do_shutdown=lambda: calls.append(1))
    mgr.settings.set("shutdown_when_done", True)
    sw.step()
    sw.step()
    assert sw.deadline is None and calls == []   # bos kuyrukta kurulunca hemen kapatmaz


# ---------------------------------------------------------------- link yenileme
def test_link_refresh_resumes_same_file(mgr):  # noqa: F811
    class R:
        def refresh(self, d):
            return ("https://yeni.example/link", None)
    mgr.link_refresher = R()
    mgr.refresh_sync = True
    d = mgr.add(DownloadRequest(url="https://eski.example/link", filename="f.bin", source="plugin:realdebrid",
                                extra={"refresh": {"type": "rd", "link": "https://hoster/x"}}))[0]
    d = mgr.store.update(d.id, gid="g1", status=Status.ACTIVE)
    mgr._apply_status(d, {"status": "error", "error_code": "22", "error": "403 Forbidden", "completed": 500,
                          "total": 1000, "speed": 0, "connections": 0, "path": ""}, {})
    nd = mgr.store.get(d.id)
    assert nd.url == "https://yeni.example/link" and nd.extra["refreshed"] == 1 and nd.status != Status.ERROR


def test_link_refresh_skips_without_info(mgr):  # noqa: F811
    mgr.link_refresher = type("R", (), {"refresh": lambda self, d: ("x", None)})()
    d = mgr.add(DownloadRequest(url="https://e.com/a.bin", filename="a.bin", source="ui"))[0]
    d = mgr.store.update(d.id, gid="g1", status=Status.ACTIVE)
    assert mgr._refresh_link(d, {"error_code": "22", "error": "403"}) is False


def test_rd_files_carry_source_link():
    from app.core.debrid import DebridService, TokenStore

    class C:
        def unrestrict(self, link):
            return {"download": "https://dl/1", "filename": "a.mkv", "filesize": 5, "link": link}
    svc = DebridService(TokenStore(__import__("pathlib").Path("x")), None, client=C())
    assert svc.unrestrict_files("https://hoster/abc")[0]["src"] == "https://hoster/abc"


# ---------------------------------------------------------------- toplu link
def test_extract_links_and_numbered():
    txt = 'bak <a href="/dosya.zip">x</a> ve https://e.com/a.mp4, magnet:?xt=urn:btih:ABC&dn=x tekrar https://e.com/a.mp4'
    assert automate.extract_links(txt, base="https://site.com/sayfa/") == [
        "https://site.com/dosya.zip", "https://e.com/a.mp4", "magnet:?xt=urn:btih:ABC&dn=x"]
    assert automate.expand_numbered("http://x/r[008-011].jpg") == [
        "http://x/r008.jpg", "http://x/r009.jpg", "http://x/r010.jpg", "http://x/r011.jpg"]


def test_batch_add_quiet_routes(mgr):  # noqa: F811
    api = make_api(mgr)
    r = api.batch_parse("https://e.com/a.zip\nhttps://e.com/b[1-3].bin")
    assert len(r["links"]) == 4
    res = api.batch_add(r["links"])
    assert res["added"] == 4 and len(mgr.store.list()) == 4


# ---------------------------------------------------------------- telefon
def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def test_phone_server_key_and_add():
    from app.core.phone import PhoneServer
    got = []
    port = _free_port()
    srv = PhoneServer(port, lambda: "dogru-anahtar-123", lambda t: got.append(t) or 1)
    assert srv.start()
    try:
        def post(key, body):
            req = urllib.request.Request(f"http://127.0.0.1:{port}/send", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json", "X-Kami-Key": key,
                                                  "Accept": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read())
        assert post("yanlis", {"text": "https://e.com/x"})[0] == 401 and not got
        code, res = post("dogru-anahtar-123", {"text": "https://e.com/x"})
        assert code == 200 and res["added"] == 1 and got == ["https://e.com/x"]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as r:
            page = r.read().decode()
        assert "Kami'ye gönder" in page and "dogru-anahtar" not in page
        # Kestirme (Accept: json yok): okunur duz metin yanit
        req = urllib.request.Request(f"http://127.0.0.1:{port}/send", data=b'{"text": "baslik"}',
                                     headers={"Content-Type": "application/json", "X-Kami-Key": "dogru-anahtar-123"})
        with urllib.request.urlopen(req, timeout=5) as r:
            assert r.read().decode().startswith("✕ Link bulunamadı")
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/test", timeout=5) as r:
            assert "Kami'ye ulaşıldı" in r.read().decode()
    finally:
        srv.stop()


# ---------------------------------------------------------------- inerken izle
def test_contiguous_head():
    # 8 parca, ilk 3'u tam (11100000 = e0), parca 1 MB
    assert watch.contiguous_head("e0", 8, 1 << 20) == 3 << 20
    assert watch.contiguous_head("e0", 8, 1 << 20, start=1 << 20) == 2 << 20
    assert watch.contiguous_head("00", 8, 1 << 20) == 0


def test_watcher_switches_inorder_and_plays(mgr, tmp_path):  # noqa: F811
    f = tmp_path / "film.mkv"
    f.write_bytes(b"0" * 10)
    d = mgr.add(DownloadRequest(url="https://dl/film.mkv", filename="film.mkv", source="plugin:realdebrid",
                                directory=str(tmp_path)))[0]
    d = mgr.store.update(d.id, gid="g9", status=Status.ACTIVE)
    calls = []

    def call(method, *params, **kw):
        calls.append((method, params))
        if method == "aria2.tellStatus":
            return {"bitfield": "ff", "numPieces": "8", "pieceLength": str(4 << 20), "status": "active",
                    "files": [{"path": str(f), "length": str(32 << 20), "selected": "true"}]}
        return "OK"
    mgr.engine.call = call
    played, extras = [], {}
    w = watch.Watcher(mgr, lambda did, **kw: extras.update(kw), player=lambda p: played.append(p) or "screenbox")
    assert w.start(d.id)["ok"]
    for _ in range(50):
        if played:
            break
        time.sleep(0.1)
    assert ("aria2.changeOption", ("g9", {"stream-piece-selector": "inorder"})) in calls
    assert played == [str(f)] and extras["watch"] == "playing"
