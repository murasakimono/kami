"""Real-Debrid istemcisi + servis: sahte ag (gercek token gerekmez)."""
from __future__ import annotations

import json

import pytest

from app.core.debrid import (DebridError, DebridService, RealDebridClient, TokenStore, is_magnet,
                             is_torrent_url)

TOKEN = "A" * 52


class Resp:
    def __init__(self, status=200, data=None):
        self.status_code = status
        self._data = data
        self.content = b"" if data is None else json.dumps(data).encode()

    def json(self):
        return self._data


class FakeSession:
    """RD'nin davranisini taklit eder; gelen istekleri kaydeder."""

    def __init__(self):
        self.headers = {}
        self.calls = []
        self.torrent_state = "waiting_files_selection"

    def request(self, method, url, headers=None, data=None, params=None, timeout=None):
        path = url.split("/rest/1.0", 1)[1]
        self.calls.append((method, path, dict(headers or {}), data))
        auth = (headers or {}).get("Authorization", "")
        if path == "/hosts/domains":
            return Resp(200, ["mega.nz", "1fichier.com", "drive.google.com"])
        if auth != f"Bearer {TOKEN}":
            return Resp(401, {"error": "bad_token", "error_code": 8})
        if path == "/user":
            return Resp(200, {"username": "metehan", "type": "premium", "premium": 30 * 86400,
                              "expiration": "2026-12-04T00:00:00.000Z"})
        if path == "/unrestrict/link":
            link = data["link"]
            if "folder" in link and "/file/" not in link:
                return Resp(503, {"error": "unknown_ressource", "error_code": 7})
            if "dead" in link:
                return Resp(503, {"error": "file_unavailable", "error_code": 24})
            name = link.rsplit("/", 1)[-1] + ".bin"
            return Resp(200, {"filename": name, "filesize": 1000, "download": f"https://dl.rd/{name}"})
        if path == "/unrestrict/folder":
            return Resp(200, ["https://mega.nz/file/a1", "https://mega.nz/file/b2"])
        if path == "/torrents/addMagnet":
            return Resp(201, {"id": "T1", "uri": "x"})
        if path == "/torrents/addTorrent":
            return Resp(201, {"id": "T2", "uri": "x"})
        if path.startswith("/torrents/selectFiles/"):
            self.torrent_state = "downloaded"
            return Resp(204)
        if path.startswith("/torrents/info/"):
            info = {"id": path.rsplit("/", 1)[-1], "filename": "Album", "status": self.torrent_state,
                    "files": [{"id": 1, "path": "/Album/CD1/01.flac", "selected": 1},
                              {"id": 2, "path": "/Album/cover.txt", "selected": 0},
                              {"id": 3, "path": "/Album/CD2/02.flac", "selected": 1}]}
            if self.torrent_state == "downloaded":
                info["links"] = ["https://real-debrid.com/d/L1", "https://real-debrid.com/d/L2"]
            return Resp(200, info)
        if path == "/torrents":
            return Resp(200, [{"id": "T1", "filename": "Album", "status": "downloaded", "progress": 100,
                               "bytes": 5000, "links": ["x"]}])
        if path == "/downloads":
            return Resp(200, [{"id": "D1", "filename": "a.bin", "filesize": 10, "host": "mega.nz",
                               "download": "https://dl.rd/a.bin"}])
        return Resp(404, {"error": "unknown_ressource"})


class MemTokens(TokenStore):
    def __init__(self, token=""):
        self.value = token

    def save(self, token):
        self.value = token

    def load(self):
        return self.value

    def clear(self):
        self.value = ""


def make(token=TOKEN, tmp_path=None):
    sess = FakeSession()
    tokens = MemTokens(token)
    svc = DebridService(tokens, (tmp_path / "pending.json") if tmp_path else None,
                        client=RealDebridClient(tokens.load, sess))
    queued = []
    svc.enqueue = lambda files, folder: queued.append((files, folder)) or len(files)
    events = []
    svc.notify = events.append
    return svc, sess, queued, events


def test_link_detection():
    assert is_magnet("magnet:?xt=urn:btih:abc")
    assert not is_magnet("https://x/magnet:?")
    assert is_torrent_url("https://site.org/files/ubuntu.iso.torrent?x=1")
    assert not is_torrent_url("https://site.org/torrent/page")


def test_set_token_validates_and_never_leaks(caplog):
    svc, sess, _, _ = make(token="")
    with pytest.raises(DebridError) as e:
        svc.set_token("kisa")
    assert e.value.code == "rd_bad_token"
    with pytest.raises(DebridError) as e:
        svc.set_token("B" * 52)       # bicim dogru ama RD reddediyor -> kaydedilmez
    assert e.value.code == "rd_bad_token" and not svc.has_token()
    caplog.set_level("INFO")
    user = svc.set_token(TOKEN)
    assert user["username"] == "metehan" and svc.has_token()
    st = svc.status()
    assert st == {"has_token": True, "ok": True, "username": "metehan", "type": "premium",
                  "expiration": "2026-12-04T00:00:00.000Z", "premium_days": 30}
    assert TOKEN not in caplog.text and TOKEN not in json.dumps(st)


def test_no_token_errors():
    svc, _, _, _ = make(token="")
    with pytest.raises(DebridError) as e:
        svc.add_link("https://mega.nz/file/x")
    assert e.value.code == "rd_no_token"


def test_supports_uses_public_domains():
    svc, _, _, _ = make()
    assert svc.supports("https://mega.nz/file/abc#key")
    assert svc.supports("https://www.1fichier.com/?xyz")
    assert svc.supports("https://drive.google.com/file/d/1")
    assert not svc.supports("https://cloud.mail.ru/public/x")
    assert not svc.supports("https://evilmega.nz/file")


def test_unrestrict_link_and_folder_fallback():
    svc, _, queued, _ = make()
    assert svc.add_link("https://1fichier.com/abc") == 1
    assert queued[-1] == ([{"url": "https://dl.rd/abc.bin", "filename": "abc.bin", "size": 1000, "src": "https://1fichier.com/abc"}], "")
    # klasor linki: unrestrict/link basarisiz -> unrestrict/folder -> her dosya
    assert svc.add_link("https://mega.nz/folder/XYZ#k") == 2
    assert [f["filename"] for f in queued[-1][0]] == ["a1.bin", "b2.bin"]
    with pytest.raises(DebridError) as e:
        svc.unrestrict_files("https://1fichier.com/dead")
    assert e.value.code in ("rd_unavailable",)


def test_magnet_flow_select_then_queue_with_folders(tmp_path):
    svc, sess, queued, events = make(tmp_path=tmp_path)
    tid = svc.add_magnet("magnet:?xt=urn:btih:abc")
    assert tid == "T1"
    assert json.loads((tmp_path / "pending.json").read_text())["T1"]
    svc.poll_once()     # waiting_files_selection -> selectFiles(all)
    assert any(c[1] == "/torrents/selectFiles/T1" and c[3] == {"files": "all"} for c in sess.calls)
    svc.poll_once()     # downloaded -> linkler unrestrict -> kuyruk (klasor yapisi korunur)
    files, folder = queued[-1]
    assert folder == "Album"
    assert [f["rel"] for f in files] == ["CD1/01.flac", "CD2/02.flac"]
    assert events[-1] == {"kind": "queued", "name": "Album", "count": 2}
    assert json.loads((tmp_path / "pending.json").read_text()) == {}


def test_pending_survives_restart(tmp_path):
    svc, _, _, _ = make(tmp_path=tmp_path)
    svc.add_magnet("magnet:?xt=urn:btih:abc")
    svc2, _, _, _ = make(tmp_path=tmp_path)
    assert "T1" in svc2._pending


def test_torrent_bytes_and_add_any():
    svc, sess, _, _ = make()
    with pytest.raises(DebridError):
        svc.add_torrent_bytes(b"<html>not a torrent")
    assert svc.add_torrent_bytes(b"d8:announce...e") == "T2"
    put = [c for c in sess.calls if c[1] == "/torrents/addTorrent"][0]
    assert put[0] == "PUT" and put[2]["Content-Type"] == "application/x-bittorrent"
    assert svc.add_any("magnet:?xt=urn:btih:zz") == {"torrent": "T1"}
    assert svc.add_any("https://t.org/x.torrent", lambda u: b"d4:infoe") == {"torrent": "T2"}
    assert svc.add_any("https://1fichier.com/q") == {"added": 1}
    with pytest.raises(DebridError):
        svc.add_any("ftp-olmayan-metin")


def test_account_lists():
    svc, _, _, _ = make()
    lists = svc.account_lists()
    assert lists["torrents"][0]["name"] == "Album" and lists["torrents"][0]["status"] == "downloaded"
    assert lists["downloads"][0]["download"] == "https://dl.rd/a.bin"


def test_manager_add_debrid_files_keeps_structure(tmp_path):
    from app.core.events import EventBus
    from app.core.manager import DownloadManager
    from app.core.queue_store import DownloadStore
    from app.core.settings import Settings

    class Eng:
        running = True

        def start(self, d):
            return "g%d" % d.id

    settings = Settings(tmp_path / "s.json")
    settings.set("download_dir", str(tmp_path / "dl"))
    m = DownloadManager(DownloadStore(tmp_path / "k.db"), Eng(), EventBus(), settings, prober=None)
    n = m.add_debrid_files([{"url": "https://dl.rd/1", "filename": "01.flac", "rel": "CD1/01.flac"},
                            {"url": "https://dl.rd/2", "filename": "02.flac", "rel": "CD2/02.flac"}], "Album")
    assert n == 2
    dirs = sorted(d.directory for d in m.store.list())
    assert dirs == [str(tmp_path / "dl" / "Album" / "Album" / "CD1"), str(tmp_path / "dl" / "Album" / "Album" / "CD2")] \
        or dirs == [str(tmp_path / "dl" / "Album" / "CD1"), str(tmp_path / "dl" / "Album" / "CD2")]
    assert all(d.source == "plugin:realdebrid" for d in m.store.list())


def test_api_routing_modes(tmp_path):
    """rd_mode: ask -> rd_ask, auto -> RD'den gecer, off/direct -> RD'ye dokunulmaz; magnet ayni mantikla RD/yerel."""
    from app.core.events import EventBus
    from app.core.manager import DownloadManager
    from app.core.plugin_api import PluginRegistry
    from app.core.queue_store import DownloadStore
    from app.core.settings import Settings
    from app.ui.api import Api

    class Eng:
        running = True

        def start(self, d):
            return "g%d" % d.id

    settings = Settings(tmp_path / "s.json")
    settings.set("download_dir", str(tmp_path / "dl"))
    m = DownloadManager(DownloadStore(tmp_path / "k.db"), Eng(), EventBus(), settings, prober=None)
    svc, sess, _, _ = make()
    svc.enqueue = m.add_debrid_files
    m.debrid = svc
    api = Api(m, Eng(), PluginRegistry(), lambda: 0)
    link = "https://1fichier.com/?abc"

    settings.set("rd_mode", "ask")
    assert api.add_url(link) == {"ok": True, "rd_ask": link}
    assert api.link_supported(link)                       # pano da teklif eder
    settings.set("rd_mode", "auto")
    r = api.add_url(link)
    assert r["ok"] and r["rd"] and r["added"] == 1
    assert m.store.list()[0].url.startswith("https://dl.rd/")
    settings.set("rd_mode", "off")
    assert "rd_ask" not in api.add_url(link) and not api.link_supported("https://1fichier.com/?zz")
    settings.set("rd_mode", "ask")
    assert "rd_ask" not in api.add_url(link, direct=True)  # "Dogrudan (RD'siz)"
    mag = "magnet:?xt=urn:btih:abc"
    assert api.add_url(mag)["torrent_ask"]["src"] == mag   # Sor: "Real-Debrid / Yerel torrent"
    assert api.torrent_choose(mag, "", "rd")["torrents"] == 1
    settings.set("rd_mode", "auto")
    assert api.add_url(mag)["torrents"] == 1               # Otomatik: RD
    settings.set("rd_mode", "off")
    assert api.add_url(mag)["torrent_local"]["src"] == mag  # Kapali: yerel
    settings.set("rd_mode", "ask")
    svc.tokens.clear()                                    # token yoksa RD hic devreye girmez
    assert "rd_ask" not in api.add_url(link)
    assert "torrent_local" in api.add_url(mag)
    with pytest.raises(ValueError):
        settings.set("rd_mode", "bazen")
