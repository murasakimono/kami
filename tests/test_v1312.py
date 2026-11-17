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


def test_dash_and_peaks(tmp_path):
    import shutil
    import subprocess
    import types

    import pytest

    from app.core.models import Download, Status
    from app.ui.api import Api
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg yok")
    wav = tmp_path / "s.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=f=440:d=3", str(wav)], check=True)
    import time
    d = Download(id=1, url="x", filename="s.wav", directory=str(tmp_path), category="music", status=Status.COMPLETE,
                 size=1000, finished_at=time.time())
    a = Api.__new__(Api)
    a._manager = types.SimpleNamespace(snapshot=lambda: [d], base_dir=lambda: str(tmp_path))
    st = a.dash_stats()
    assert st["today"] == 1000 and st["today_n"] == 1 and st["disk_free"] > 0
    pk = a.audio_peaks(str(wav), 100)
    assert pk["ok"] and len(pk["peaks"]) == 100 and max(pk["peaks"]) == 1.0
    m = a.item_peek(1)
    assert round(m["duration"]) == 3 and m["acodec"]


def test_games_launch_guard_and_cleaner_guard(tmp_path):
    from app.core import cleaner, games
    assert games.launch_game("cmd.exe /c calc")["error"] == "unsupported_target"
    assert games.launch_game(str(tmp_path))["error"] == "unsupported_target"   # klasor: Gezgin acmasin
    assert cleaner.trash_path(str(tmp_path.anchor))["error"] == "protected"
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "f.bin").write_bytes(b"x" * 5000)
    m = cleaner.disk_treemap(str(tmp_path))
    assert m["ok"] and m["items"][0]["size"] == 5000 and m["approx"] is False


def test_spotify_pkce_login_and_refresh(tmp_path, monkeypatch):
    import threading
    import urllib.parse
    import urllib.request
    import webbrowser

    from app import paths
    from app.core import debrid
    from app.core import music_hub as m
    store: dict = {}

    class TS:
        def __init__(self, p): self.p = str(p)
        def save(self, v): store[self.p] = v
        def load(self): return store.get(self.p, "")
        def clear(self): store.pop(self.p, None)
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(debrid, "TokenStore", TS)
    monkeypatch.setattr(m, "_SP_CACHE", {"token": "", "exp": 0.0})
    monkeypatch.setattr(m, "_sp_token_request", lambda f: {"access_token": "AT_" + f["grant_type"], "refresh_token": "RT", "expires_in": 3600})

    def opener(state_override=None):
        def _open(url):
            q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
            assert q["code_challenge_method"] == "S256" and q["redirect_uri"] == m.SP_REDIRECT
            st = state_override or q["state"]
            threading.Timer(0.2, lambda: urllib.request.urlopen(f"{m.SP_REDIRECT}?code=C&state={st}").read()).start()
        return _open
    monkeypatch.setattr(webbrowser, "open", opener())
    assert m.spotify_login("CID", timeout=5)["ok"]
    assert m.spotify_oauth_status()["connected"]
    m._SP_CACHE["exp"] = 0
    assert m.spotify_access_token() == "AT_refresh_token"
    monkeypatch.setattr(webbrowser, "open", opener("SAHTE"))
    assert m.spotify_login("CID", timeout=5)["error"] == "state_mismatch"
