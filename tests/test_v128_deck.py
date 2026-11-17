"""v1.28: Kami Deck (telefon Stream Deck) + uzaktan indirme + Kapsul coklu dosya/yorum."""
import io
import json
import urllib.error
import urllib.request
import zipfile

import pytest


def test_deck_load_save_sanitize(tmp_path, monkeypatch):
    monkeypatch.setattr("app.paths.DATA_DIR", tmp_path)
    from app.core import deck
    d = deck.load()
    assert d["profiles"][0]["name"] == "Genel" and d["cols"] == 4
    out = deck.save({"cols": 99, "profiles": [{"name": "X" * 50, "buttons": [
        {"a": "studio:split", "label": "Böl"}, {"a": "evil:rm", "arg": "x"}, {"a": "sys:hotkey", "arg": "ctrl+shift+m", "zz": 1}]}]})
    assert out["cols"] == 6 and len(out["profiles"][0]["name"]) == 30
    btns = out["profiles"][0]["buttons"]
    assert [b["a"] for b in btns] == ["studio:split", "sys:hotkey"] and "zz" not in btns[1]
    assert deck.load()["profiles"][0]["buttons"][1]["arg"] == "ctrl+shift+m"
    assert deck.save({"profiles": []})["profiles"][0]["name"] == "Genel"   # bos -> varsayilan


def test_deck_bus_and_run(monkeypatch):
    from app.core import deck
    deck.bus_poll("player")
    assert deck.run("player:toggle", "", {})["ok"]
    assert deck.run("player:next", "", {})["ok"]
    assert deck.bus_poll("player") == ["toggle", "next"] and deck.bus_poll("player") == []
    deck.bus_push("studio", "split")
    monkeypatch.setattr(deck.time, "time", lambda: 1e12)   # 5 sn'den eski komut dusur
    assert deck.bus_poll("studio") == []
    assert deck.run("nope:x", "", {})["error"]
    called = []
    assert deck.run("dl:limit", "2048", {"dl:limit": lambda a: called.append(a)})["ok"] and called == ["2048"]
    assert not deck.run("app:studio", "", {})["ok"]   # handler yok -> hata metni, cokme yok


def test_parse_hotkey():
    from app.core import deck
    assert deck.parse_hotkey("ctrl+shift+m") == [0x11, 0x10, ord("M")]
    assert deck.parse_hotkey("F13") == [0x7C]
    with pytest.raises(ValueError):
        deck.parse_hotkey("ctrl+bogus")


def test_phone_deck_routes(tmp_path, monkeypatch):
    from app.core.phone import PhoneServer
    seen = []
    srv = PhoneServer(0, lambda: "anahtar123", lambda t, f="": 0)
    srv.on_deck = lambda p, b: (seen.append((p, b)) or (200, {"ok": True, "p": p}))
    assert srv.start()
    port = srv._srv.server_address[1]
    try:
        page = urllib.request.urlopen(f"http://127.0.0.1:{port}/deck").read().decode()
        assert "Kami <b>Deck</b>" in page and "/deck/run" in page
        req = urllib.request.Request(f"http://127.0.0.1:{port}/deck/run", data=json.dumps({"a": "player:toggle"}).encode(),
                                     headers={"Content-Type": "application/json", "X-Kami-Key": "anahtar123"})
        assert json.loads(urllib.request.urlopen(req).read())["p"] == "/deck/run"
        assert seen == [("/deck/run", {"a": "player:toggle"})]
        bad = urllib.request.Request(f"http://127.0.0.1:{port}/dl/action", data=b"{}", headers={"X-Kami-Key": "yanlis"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(bad)
        assert e.value.code == 401
    finally:
        srv.stop()


def test_kapsul_multi_file_zip_comments(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.kapsul._store", lambda: tmp_path / "kapsul.json")
    from app.core import kapsul
    from app.core.room import RoomServer
    events = []
    monkeypatch.setattr(kapsul, "ON_EVENT", lambda kind, name, detail: events.append(kind))
    a, b = tmp_path / "a.txt", tmp_path / "b.bin"
    a.write_text("merhaba")
    b.write_bytes(b"\x00\x01" * 500)
    r = kapsul.create([str(a), str(b)], hours=1)
    assert r["ok"]
    srv = RoomServer()
    srv.start("Test", tunnel=False)
    try:
        base = f"http://127.0.0.1:{srv.httpd.server_address[1]}/c/{r['id']}"
        page = urllib.request.urlopen(base).read().decode()
        assert "a.txt" in page and "b.bin" in page
        z = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(base + "/zip").read()))
        assert sorted(z.namelist()) == ["a.txt", "b.bin"] and z.read("a.txt") == b"merhaba"
        assert urllib.request.urlopen(base + "/dl/1").read() == b"\x00\x01" * 500
        req = urllib.request.Request(base + "/comment", data=json.dumps({"name": "Ali", "text": "süper"}).encode(),
                                     headers={"Content-Type": "application/json"})
        assert json.loads(urllib.request.urlopen(req).read())["ok"]
        it = kapsul.get(r["id"])
        assert it["comments"][0]["text"] == "süper" and it["downloads"] >= 2
        assert "download" in events or "comment" in events
    finally:
        srv.stop()
