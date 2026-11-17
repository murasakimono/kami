"""v1.31.2: Pano rafi kaydi, Deck'in oda tuneli uzerinden calismasi."""
import json
import urllib.error
import urllib.request

from app.core import pano_tools, room


def test_shelf_dedupe_and_clear(tmp_path):
    pano_tools.add_shelf_item("text", "merhaba dunya", data_dir=tmp_path)
    pano_tools.add_shelf_item("url", "https://a.com/x.zip", data_dir=tmp_path)
    pano_tools.add_shelf_item("text", "merhaba dunya", data_dir=tmp_path)   # tekrar -> en uste, kopya yok
    items = pano_tools.list_shelf(tmp_path)
    assert [i["value"] for i in items] == ["merhaba dunya", "https://a.com/x.zip"]
    assert pano_tools.clear_shelf(tmp_path)["ok"] and pano_tools.list_shelf(tmp_path) == []


def test_shelf_label_collapses_whitespace(tmp_path):
    pano_tools.add_shelf_item("text", "satir 1\n\n   satir 2", data_dir=tmp_path)
    assert pano_tools.list_shelf(tmp_path)[0]["label"] == "satir 1 satir 2"


class _Phone:
    def __init__(self):
        self.on_deck = lambda path, body: (200, {"ok": True, "path": path, "body": body})

    def _rate_ok(self):
        return True

    def key(self):
        return "K1"

    def handle_send(self, raw, ctype, key, client):
        return (200, {"ok": True}) if key == "K1" else (401, {"ok": False})


def _req(url, body=None, key="K1"):
    r = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                               headers={"X-Kami-Key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=5) as x:
            return x.status, x.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_deck_through_room_tunnel():
    srv = room.SERVER
    srv.phone_srv = _Phone()
    info = srv.start("test", tunnel=False)
    try:
        base = info["local"].rstrip("/")
        code, body = _req(base + "/deck")
        assert code == 200 and b"<html" in body.lower()
        code, body = _req(base + "/deck/data", {})
        assert code == 200 and json.loads(body)["path"] == "/deck/data"
        assert _req(base + "/deck/run", {"id": "x"}, key="yanlis")[0] == 401
        assert json.loads(_req(base + "/dl/action", {"a": 1})[1])["path"] == "/dl/action"
        assert _req(base + "/send", {"text": "http://x"})[0] == 200
    finally:
        srv.stop()
        srv.phone_srv = None
