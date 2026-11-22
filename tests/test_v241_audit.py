"""v2.4.1 denetim ve guvenlik sertlestirme regresyon testleri."""
from __future__ import annotations

import hashlib
import http.cookiejar
import json
import types
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_studio_jobs_includes_all_five_studio_panel_calls():
    from app.ui.api import Api
    for name in ("studio_pixel_sort", "studio_datamosh", "studio_beatshift", "studio_data_graphic", "studio_audio_pro_process"):
        assert name in Api.JOB_METHODS
        assert hasattr(Api, name)


def test_main_quit_has_no_global_taskkill_im():
    src = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert '"/IM"' not in src


def test_phone_and_room_portal_suffix_range(tmp_path: Path):
    from app.core.phone import PhoneServer
    from app.core import room

    sample = tmp_path / "tail.bin"
    payload = bytes(range(100))
    sample.write_bytes(payload)

    ph = PhoneServer(0, lambda: "k1", lambda t, f="": 0)
    ph.portal_data = lambda: {"ok": True, "books": [], "media": [{"path": str(sample)}]}
    assert ph.start()
    try:
        p_port = ph._srv.server_address[1]
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        # ?k= artik reddedilmeli
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f"http://127.0.0.1:{p_port}/portal/data?k=k1")
        assert e.value.code == 401
        # X-Kami-Key ile portal/data acilinca kami_portal HttpOnly cerezi gelir
        dreq = urllib.request.Request(f"http://127.0.0.1:{p_port}/portal/data", headers={"X-Kami-Key": "k1"})
        assert json.loads(opener.open(dreq).read())["ok"] is True
        # Cerez ile URL'de anahtar olmadan suffix Range (son 10 bayt) dogru donmeli
        q_path = urllib.parse.quote(str(sample))
        rreq = urllib.request.Request(f"http://127.0.0.1:{p_port}/portal/file?p={q_path}", headers={"Range": "bytes=-10"})
        resp = opener.open(rreq)
        assert resp.status == 206
        assert resp.read() == payload[-10:]
        assert resp.headers["Content-Range"] == "bytes 90-99/100"
    finally:
        ph.stop()

    # Room tuneli uzerindeki /portal/file icin de ayni suffix Range kontrolu
    srv = room.RoomServer()
    srv.phone_srv = ph
    info = srv.start("Test", tunnel=False, room_id="portaltest1")
    try:
        base = info["local"].rstrip("/")
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        dreq = urllib.request.Request(f"{base}/portal/data", headers={"X-Kami-Key": "k1"})
        assert json.loads(opener.open(dreq).read())["ok"] is True
        q_path = urllib.parse.quote(str(sample))
        rreq = urllib.request.Request(f"{base}/portal/file?p={q_path}", headers={"Range": "bytes=-12"})
        resp = opener.open(rreq)
        assert resp.status == 206
        assert resp.read() == payload[-12:]
        assert resp.headers["Content-Range"] == "bytes 88-99/100"
    finally:
        srv.stop()
        srv.phone_srv = None


def test_kapsul_scrypt_size_cap_and_cf_ip(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.core.kapsul._store", lambda: tmp_path / "kapsul.json")
    from app.core import kapsul

    files = []
    for i in range(205):
        p = tmp_path / f"f{i:03d}.bin"
        p.write_bytes(b"a" * 10)
        files.append(str(p))
    res = kapsul.create(files, hours=1, password="gizli")
    assert res["ok"] is True
    assert res["size"] == 200 * 10
    assert res["files"] == 200
    it = kapsul.get(res["id"])
    assert it["pw"].startswith("scrypt$")
    assert kapsul.pw_ok(it, "gizli", "10.0.0.1") is True
    assert kapsul.pw_ok(it, "yanlis", "10.0.0.1") is False

    # CF-Connecting-IP yalnizca loopback peer icin guvenilir olmali
    fake_ext = types.SimpleNamespace(client_address=("192.168.1.50", 1234), headers={"CF-Connecting-IP": "1.2.3.4"})
    fake_cf = types.SimpleNamespace(client_address=("127.0.0.1", 1234), headers={"CF-Connecting-IP": "1.2.3.4"})
    assert kapsul._client_ip(fake_ext) == "192.168.1.50"
    assert kapsul._client_ip(fake_cf) == "1.2.3.4"


def test_download_update_sha256_verification(tmp_path: Path, monkeypatch):
    import requests
    from app.core import extras

    payload = b"MZ-fake-setup-binary"
    good_sha = hashlib.sha256(payload).hexdigest()

    class _Resp:
        status_code = 200
        def iter_content(self, _):
            yield payload

    monkeypatch.setattr(requests, "get", lambda *a, **kw: _Resp())
    url = f"https://github.com/{extras.GITHUB_REPO}/releases/download/v2.4.0/Kami-Setup-2.4.0.exe"

    ok_out = extras.download_update({"asset": "Kami-Setup-2.4.0.exe", "asset_url": url, "sha256": good_sha}, tmp_path)
    assert ok_out.is_file() and ok_out.read_bytes() == payload

    with pytest.raises(ValueError, match="checksum_mismatch"):
        extras.download_update({"asset": "Kami-Setup-2.4.0.exe", "asset_url": url, "sha256": "0" * 64}, tmp_path / "bad")
    assert not (tmp_path / "bad" / "Kami-Setup-2.4.0.exe").exists()


def test_music_tag_uses_id3v23(tmp_path: Path, monkeypatch):
    import mutagen.id3
    from app.core import music_tag

    saved_versions = []

    class _FakeID3:
        def delall(self, *_):
            pass
        def add(self, *_):
            pass
        def save(self, _path, v2_version=4):
            saved_versions.append(v2_version)

    monkeypatch.setattr(mutagen.id3, "ID3", lambda *_a: _FakeID3())
    f = tmp_path / "sarki.mp3"
    f.write_bytes(b"ID3")
    assert music_tag.cover_embed(str(f), b"\x89PNG\r\n\x1a\n") is True
    assert saved_versions == [3]


def test_listenbrainz_token_dpapi_migration_and_masking(tmp_path: Path, monkeypatch):
    from app import paths
    from app.ui.api import Api

    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    store_data = {"listenbrainz_token": "lb-legacy-secret"}
    settings_stub = types.SimpleNamespace(
        all=lambda: dict(store_data),
        get=lambda k, d=None: store_data.get(k, d),
        set=lambda k, v: store_data.__setitem__(k, v),
    )
    api = object.__new__(Api)
    api._manager = types.SimpleNamespace(settings=settings_stub, base_dir=lambda: str(tmp_path))

    got = api.get_settings()
    assert got["listenbrainz_token"] == ""
    assert got["_has_listenbrainz"] is True
    assert store_data["listenbrainz_token"] == ""
    assert (tmp_path / "listenbrainz_token.bin").is_file()
    assert api._lb_token() == "lb-legacy-secret"

    r = api.set_setting("listenbrainz_token", "lb-new-secret")
    assert r["ok"] is True and r["value"] == "" and r["_has_listenbrainz"] is True
    assert store_data["listenbrainz_token"] == ""
    assert api._lb_token() == "lb-new-secret"


def test_styles_css_legend_clears_all_siblings():
    css = (ROOT / "app/ui/web/styles.css").read_text(encoding="utf-8")
    assert "legend ~ *" in css and "clear: both" in css
    # Tek basina "legend + * { clear: both; }" hidden ilk kardes varken sonraki ogeyi saga tasiyordu
    assert "\nlegend + * { clear: both; }" not in css
