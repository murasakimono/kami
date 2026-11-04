"""DPAPI cerez deposu + YouTube bot hatasi eslemesi."""
import os

from app.core import vault
from app.engines import ytdlp_engine as yt

CK = [
    {"name": "SAPISID", "value": "abc", "domain": ".youtube.com", "path": "/", "secure": True,
     "hostOnly": False, "session": False, "expirationDate": 1893456000.5},
    {"name": "NID", "value": "x", "domain": "www.google.com", "path": "/", "secure": False,
     "hostOnly": True, "session": True},
    {"name": "evil", "value": "1", "domain": ".example.com", "path": "/"},
]


def test_dpapi_roundtrip():
    enc = vault.protect(b"gizli")
    assert enc != b"gizli" and vault.unprotect(enc) == b"gizli"


def test_netscape_format():
    txt = vault.to_netscape(CK[:2])
    lines = txt.splitlines()
    assert lines[0] == "# Netscape HTTP Cookie File"
    assert ".youtube.com\tTRUE\t/\tTRUE\t1893456000\tSAPISID\tabc" in lines
    assert "www.google.com\tFALSE\t/\tFALSE\t0\tNID\tx" in lines


def test_store_filters_encrypts_and_cleans(tmp_path):
    store = vault.CookieStore(tmp_path / "ck.bin")
    assert store.save(CK) == 2                      # example.com elendi
    assert b"SAPISID" not in (tmp_path / "ck.bin").read_bytes()
    assert store.has_login()
    with store.cookiefile() as path:
        assert "SAPISID\tabc" in open(path, encoding="utf-8").read()
    assert not os.path.exists(path)


def test_cookiefile_only_for_youtube(tmp_path, monkeypatch):
    store = vault.CookieStore(tmp_path / "ck.bin")
    store.save(CK)
    monkeypatch.setattr(yt, "COOKIES", store)
    with yt._cookiefile("https://www.youtube.com/watch?v=x") as p:
        assert p
    with yt._cookiefile("https://vimeo.com/1") as p:
        assert p is None


def test_bot_error_mapped():
    msg = "ERROR: [youtube] abc: Sign in to confirm you’re not a bot. This helps protect"
    assert yt._clean_error(msg) == yt.BOT_ERROR
    assert yt._clean_error("ERROR: baska hata") == "baska hata"
