"""RD hata kodlari + eklentiye sonuc (kopru) + yerel torrent (ayristirma, secim, aria2 secenekleri)."""
from __future__ import annotations

import hashlib

import pytest

from app.core.debrid import DebridError, rd_error_code
from app.core.torrent import TorrentError, TorrentService, parse_torrent
from tests.test_debrid import FakeSession, Resp, make


def benc(x) -> bytes:
    if isinstance(x, int):
        return b"i%de" % x
    if isinstance(x, str):
        x = x.encode()
    if isinstance(x, bytes):
        return b"%d:%s" % (len(x), x)
    if isinstance(x, list):
        return b"l" + b"".join(benc(i) for i in x) + b"e"
    if isinstance(x, dict):
        return b"d" + b"".join(benc(k) + benc(v) for k, v in sorted(x.items())) + b"e"
    raise TypeError(x)


INFO_MULTI = {"name": "Sintel", "piece length": 16384, "pieces": b"\0" * 20, "files": [
    {"length": 100, "path": ["Sintel.mp4"]},
    {"length": 7, "path": [".pad", "7"], "attr": "p"},
    {"length": 20, "path": ["subs", "Sintel.tr.srt"]},
    {"length": 30, "path": ["poster.jpg"]},
]}
TORRENT_MULTI = benc({"announce": "udp://t.example:1337", "info": INFO_MULTI})


# ---------------------------------------------------------------- 1) RD hata kodlari
@pytest.mark.parametrize("name,code,expected", [
    ("infringing_file", 35, "rd_infringing"),
    ("", 35, "rd_infringing"),
    ("too_many_active_downloads", 21, "rd_too_many"),
    ("traffic_exhausted", 23, "rd_traffic"),
    ("hoster_unavailable", 19, "rd_hoster_down"),
    ("bad_token", 8, "rd_bad_token"),
    ("permission_denied", 9, "rd_denied"),
    ("bilinmeyen_hata", 999, "rd_failed"),
])
def test_rd_error_code(name, code, expected):
    assert rd_error_code(name, code) == expected


class InfringingSession(FakeSession):
    def request(self, method, url, **kw):
        if url.endswith("/torrents/addMagnet") and "telifli" in (kw.get("data") or {}).get("magnet", ""):
            self.calls.append((method, "/torrents/addMagnet", {}, kw.get("data")))
            return Resp(451, {"error": "infringing_file", "error_code": 35})
        return super().request(method, url, **kw)


def _svc_with(session_cls):
    svc, _, queued, events = make()
    svc.client.s = session_cls()
    return svc, events


def test_client_maps_infringing():
    svc, _ = _svc_with(InfringingSession)
    with pytest.raises(DebridError) as ei:
        svc.add_magnet("magnet:?xt=urn:btih:telifli")
    assert ei.value.code == "rd_infringing" and ei.value.detail == "infringing_file"


# ---------------------------------------------------------------- 2) kopru: eklenti sonucu gorur
def test_bridge_rd_returns_reason(tmp_path):
    from app.core.bridge_server import BridgeServer

    class M:
        pass

    svc, events = _svc_with(InfringingSession)
    m = M()
    m.debrid = svc
    b = BridgeServer(m, tmp_path / "bridge.json")
    code, res = b._rd({"url": "magnet:?xt=urn:btih:telifli"})
    assert code == 200 and res["ok"] and res["accepted"] is False
    assert res["reason"] == "rd_infringing" and res["detail"] == "infringing_file"
    assert events[-1] == {"kind": "error", "error": "rd_infringing", "detail": "infringing_file"}
    code, res = b._rd({"url": "magnet:?xt=urn:btih:serbest"})
    assert res["accepted"] is True and res["kind"] == "torrent"


def test_bridge_magnet_handler_goes_to_route(tmp_path):
    """Windows magnet isleyicisi RD'ye dogrudan gitmez: Kami'de RD/yerel secimi (olay)."""
    from app.core.bridge_server import BridgeServer
    from app.core.events import EventBus

    class M:
        pass

    svc, _ = _svc_with(InfringingSession)
    m = M()
    m.debrid = svc
    m.events = EventBus()
    got = []
    m.events.on("torrent.request", lambda src: got.append(src))
    b = BridgeServer(m, tmp_path / "bridge.json")
    code, res = b._rd({"url": "magnet:?xt=urn:btih:abc", "source": "magnet"})
    assert res["accepted"] and got == ["magnet:?xt=urn:btih:abc"]
    assert not [c for c in svc.client.s.calls if c[1] == "/torrents/addMagnet"]


# ---------------------------------------------------------------- 3) .torrent ayristirma
def test_parse_torrent_multi_and_infohash():
    meta = parse_torrent(TORRENT_MULTI)
    assert meta.name == "Sintel" and meta.multi
    assert meta.infohash == hashlib.sha1(benc(INFO_MULTI)).hexdigest()
    assert [f["path"] for f in meta.files] == ["Sintel.mp4", ".pad/7", "subs/Sintel.tr.srt", "poster.jpg"]
    assert meta.files[1]["pad"] and meta.total == 157


def test_private_torrent_gets_no_extra_trackers(tmp_path):
    m, eng, _ = _manager(tmp_path)
    priv = benc({"info": {"name": "x.bin", "length": 5, "piece length": 1, "pieces": b"", "private": 1}})
    token, meta = m.torrents.from_bytes(priv)
    assert meta.private
    m.add_torrent(token, [0])
    assert "bt-tracker" not in eng.added[-1][1][2]


def test_parse_torrent_single_and_bad():
    meta = parse_torrent(benc({"info": {"name": "ubuntu.iso", "length": 5, "piece length": 1, "pieces": b""}}))
    assert not meta.multi and meta.files == [{"path": "ubuntu.iso", "size": 5, "pad": False}]
    with pytest.raises(TorrentError):
        parse_torrent(b"d4:spami3ee")
    with pytest.raises(TorrentError):
        TorrentService(None, __import__("pathlib").Path(".")).from_bytes(b"<html>")


def test_service_public_hides_pad(tmp_path):
    svc = TorrentService(None, tmp_path)
    token, meta = svc.from_bytes(TORRENT_MULTI)
    assert (tmp_path / f"{meta.infohash}.torrent").read_bytes() == TORRENT_MULTI
    pub = svc.public(token, meta)
    assert pub["kind"] == "torrent" and [f["path"] for f in pub["files"]] == \
        ["Sintel.mp4", "subs/Sintel.tr.srt", "poster.jpg"]


# ---------------------------------------------------------------- 4) secim -> aria2 secenekleri
def _manager(tmp_path):
    from app.core.events import EventBus
    from app.core.manager import DownloadManager
    from app.core.queue_store import DownloadStore
    from app.core.settings import Settings
    from app.engines.aria2_engine import Aria2Engine

    class Eng(Aria2Engine):
        def __init__(self):
            super().__init__(tmp_path / "aria2c.exe")
            self.added = []

        def call(self, method, *params, timeout=10.0):
            self.added.append((method, params))
            return "gid1"

    settings = Settings(tmp_path / "s.json")
    settings.set("download_dir", str(tmp_path / "dl"))
    eng = Eng()
    m = DownloadManager(DownloadStore(tmp_path / "k.db"), eng, EventBus(), settings, prober=None)
    m.torrents = TorrentService(eng, tmp_path / "torrents")
    return m, eng, settings


def test_add_torrent_selection_and_seed(tmp_path):
    m, eng, settings = _manager(tmp_path)
    token, _ = m.torrents.from_bytes(TORRENT_MULTI)
    d = m.add_torrent(token, [0, 2])          # gorunen liste: Sintel.mp4, subs/..srt, poster.jpg
    method, (b64, uris, opts) = eng.added[-1]
    assert method == "aria2.addTorrent" and uris == []
    assert opts["select-file"] == "1,4"        # aria2 sirasi (dolgu dosyasi 2. sirada)
    assert opts["bt-remove-unselected-file"] == "true" and "opentrackr" in opts["bt-tracker"]
    assert opts["seed-time"] == "0" and "seed-ratio" not in opts   # varsayilan: paylasimi durdur
    assert d.kind == "torrent" and d.size == 130 and d.filename == "Sintel" and d.gid == "gid1"

    settings.set("torrent_stop_seeding", False)
    token, _ = m.torrents.from_bytes(TORRENT_MULTI)
    m.add_torrent(token, [0, 1, 2])            # hepsi -> select-file yok
    opts = eng.added[-1][1][2]
    assert "select-file" not in opts and opts["seed-ratio"] == "1.0" and "seed-time" not in opts
    with pytest.raises(TorrentError):
        m.add_torrent(token, [])


def test_torrent_status_keeps_name_and_shows_seeding(tmp_path):
    m, eng, _ = _manager(tmp_path)
    token, _ = m.torrents.from_bytes(TORRENT_MULTI)
    d = m.add_torrent(token, [0])
    live = {}
    m._apply_status(d, {"status": "active", "total": 100, "completed": 100, "speed": 0, "connections": 2,
                        "error_code": "0", "error": "", "path": str(tmp_path / "dl" / "Sintel" / "Sintel.mp4"),
                        "seeder": True, "upload_speed": 5}, live)
    nd = m.store.get(d.id)
    assert nd.filename == "Sintel" and live[d.id]["phase"] == "seeding"


def test_settings_torrent_port_validation(tmp_path):
    from app.core.settings import Settings
    s = Settings(tmp_path / "s.json")
    assert s.get("torrent_stop_seeding") is True and s.get("torrent_port") == 0
    s.set("torrent_port", 51413)
    with pytest.raises(ValueError):
        s.set("torrent_port", 80)
