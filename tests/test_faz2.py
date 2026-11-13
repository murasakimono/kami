from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import MagicMock

from app.core import bypass, grab_all, season_scraper
from app.core.events import EventBus
from app.core.plugin_loader import load_plugins
from app.core.settings import Settings


def test_faz2_plugins_load_cleanly(tmp_path):
    root = Path(__file__).resolve().parent.parent / "plugins"
    s = Settings(tmp_path / "settings.json")
    reg = load_plugins(root, EventBus(), s)
    ids = {p.id for p in reg.plugins}
    for expected in ("gofile", "qiwi", "bunkr", "krakenfiles", "sendcm", "bypass"):
        assert expected in ids
        p = next(x for x in reg.plugins if x.id == expected)
        assert not p.error, f"{expected} hata: {p.error}"
    cloud_names = {p.name for p in reg.clouds}
    for cname in ("gofile", "qiwi", "bunkr", "krakenfiles", "sendcm"):
        assert cname in cloud_names
    assert any(r.name == "bypass" for r in reg.resolvers)


def test_bypass_linkvertise_and_js_and_captcha():
    b64 = base64.b64encode(b"https://gofile.io/d/AbCd12").decode()
    r1 = bypass.resolve(f"https://linkvertise.com/12345/file?r={b64}")
    assert r1["ok"] is True
    assert r1["url"] == "https://gofile.io/d/AbCd12"

    sess = MagicMock()
    sess.get.return_value = MagicMock(
        status_code=200,
        url="https://tr.link/abc",
        text='<script>window.location.href="https://pixeldrain.com/u/XyZ123";</script>',
    )
    r2 = bypass.resolve("https://tr.link/abc", session=sess)
    assert r2["ok"] is True
    assert r2["url"] == "https://pixeldrain.com/u/XyZ123"

    sess_cap = MagicMock()
    sess_cap.get.return_value = MagicMock(
        status_code=200,
        url="https://ouo.io/abc",
        text='<div class="g-recaptcha" data-sitekey="x"></div>',
    )
    r3 = bypass.resolve("https://ouo.io/abc", session=sess_cap)
    assert r3["ok"] is False
    assert r3["error"] == "captcha_required"


def test_season_scraper_extracts_episodes_and_playerjs():
    sess = MagicMock()
    season_page = MagicMock(
        status_code=200,
        text='<h1>Dragon Ball</h1><a href="/episode/1">Bölüm 1</a><a href="/episode/2">Bölüm 2</a>',
    )
    ep1_page = MagicMock(
        status_code=200,
        text='<iframe src="https://vidmoly.to/embed-ep1.html"></iframe>',
    )
    vidmoly_ep1 = MagicMock(
        status_code=200,
        text='<script>new Playerjs({id:"player", file:"https://cdn.example.com/db_e01.m3u8"});</script>',
    )
    ep2_page = MagicMock(
        status_code=200,
        text='<iframe src="https://vidmoly.to/embed-ep2.html"></iframe>',
    )
    vidmoly_ep2 = MagicMock(
        status_code=200,
        text='<script>sources: [{file: "https://cdn.example.com/db_e02.mp4"}]</script>',
    )
    sess.get.side_effect = [season_page, ep1_page, vidmoly_ep1, ep2_page, vidmoly_ep2]

    res = season_scraper.scrape_season("https://anime.example/db/season/1", session=sess)
    assert res["ok"] is True
    assert res["title"] == "Dragon Ball"
    assert len(res["episodes"]) == 2
    assert res["episodes"][0]["stream_url"] == "https://cdn.example.com/db_e01.m3u8"
    assert res["episodes"][1]["stream_url"] == "https://cdn.example.com/db_e02.mp4"


def test_grab_all_supported_hosts():
    assert grab_all.is_supported("https://www.instagram.com/murasakimono/") is True
    assert grab_all.is_supported("https://x.com/user/media") is True
    assert grab_all.is_supported("https://tr.pinterest.com/board/") is True
    assert grab_all.is_supported("https://www.reddit.com/r/wallpapers/") is True
    assert grab_all.is_supported("https://example.com/file.zip") is False


def test_bypass_rejects_on_failure_and_skips_plain_shorteners(monkeypatch):
    import pytest
    from app.core.manager import CaptureRejected
    from app.core.models import DownloadRequest
    from plugins.bypass.plugin import BypassResolver

    assert bypass.is_bypassable("https://bit.ly/abc") is False
    assert bypass.is_bypassable("https://t.co/xyz") is False
    assert bypass.is_bypassable("https://tinyurl.com/123") is False

    monkeypatch.setattr(bypass, "resolve", lambda u: {"ok": False, "url": u, "hops": 0, "error": "captcha_required"})
    with pytest.raises(CaptureRejected):
        BypassResolver().resolve(DownloadRequest(url="https://ouo.io/abc"))


def test_bypass_rentry_query_and_pastebin_prefer_cloud():
    sess = MagicMock()
    sess.get.return_value = MagicMock(
        status_code=200,
        text="Bilgi: https://example.com/info\nDosya: https://gofile.io/d/Test12\n",
    )
    res = bypass.resolve("https://rentry.co/abc?foo=1", session=sess)
    assert res["ok"] is True
    assert res["url"] == "https://gofile.io/d/Test12"
    assert sess.get.call_args[0][0] == "https://rentry.co/abc/raw"


def test_bunkr_wildcard_and_qiwi_no_guess(monkeypatch):
    import pytest
    from plugins.bunkr.plugin import Bunkr
    from plugins.qiwi.plugin import Qiwi

    b = Bunkr()
    assert b.can_handle("https://bunkrr.su/a/AbCd") is True
    assert b.can_handle("https://bunkr.cr/f/file123") is True
    assert b.can_handle("https://example.com/a/AbCd") is False

    fake_s = MagicMock()
    fake_s.get.return_value = MagicMock(status_code=200, text="<html><h1>No link here</h1></html>")
    with pytest.raises(RuntimeError):
        Qiwi._parse_file(fake_s, "https://qiwi.gg/file/AbC123", "AbC123")
