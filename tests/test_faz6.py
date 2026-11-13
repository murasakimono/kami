from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core import grab_all, kami_hunter, season_scraper
from app.core.cloud import CloudError
from app.core.events import EventBus
from app.core.plugin_loader import load_plugins
from app.core.settings import Settings


def test_erome_and_kemono_plugins_load_and_match(tmp_path):
    root = Path(__file__).resolve().parent.parent / "plugins"
    reg = load_plugins(root, EventBus(), Settings(tmp_path / "settings.json"))
    by_id = {p.id: p for p in reg.plugins}
    for pid in ("erome", "kemono"):
        assert pid in by_id
        assert not by_id[pid].error, f"{pid} yükleme hatası: {by_id[pid].error}"

    clouds = {c.name: c for c in reg.clouds}
    erome = clouds["erome"]
    kemono = clouds["kemono"]

    assert erome.can_handle("https://www.erome.com/a/AbCd1234") is True
    assert erome.can_handle("https://erome.com/a/test_99") is True
    assert erome.can_handle("https://www.erome.com/") is False

    assert kemono.can_handle("https://kemono.su/patreon/user/12345") is True
    assert kemono.can_handle("https://kemono.cr/fanbox/user/99/post/555") is True
    assert kemono.can_handle("https://coomer.st/onlyfans/user/demo/post/1") is True
    assert kemono.can_handle("https://kemono.su/posts") is False


def test_erome_extracts_media_and_handles_errors():
    from plugins.erome.plugin import Erome

    album_html = """
    <html><head><title>x</title></head><body>
      <h1>Test Albüm Başlığı</h1>
      <img src="/assets/logo.png">
      <video poster="//v1.erome.com/poster_thumb.jpg">
        <source src="https://v12.erome.com/99/clip_1.mp4" type="video/mp4">
      </video>
      <img class="img-front lazyload" data-src="//s12.erome.com/99/photo_a.jpg">
      <img class="img-front" src="https://s12.erome.com/99/photo_a.jpg">
    </body></html>
    """
    sess = MagicMock()
    sess.get.return_value = MagicMock(status_code=200, text=album_html)
    sess.head.return_value = MagicMock(ok=True, headers={"Content-Length": "4096"})

    with patch("plugins.erome.plugin.session", return_value=sess):
        listing = Erome().list("https://www.erome.com/a/Demo123")
    assert listing.title == "Test Albüm Başlığı"
    assert len(listing.files) == 2
    assert listing.files[0].url == "https://v12.erome.com/99/clip_1.mp4"
    assert listing.files[0].headers == {"Referer": "https://www.erome.com/"}
    assert listing.files[0].size == 4096
    assert listing.files[1].url == "https://s12.erome.com/99/photo_a.jpg"

    sess.get.return_value = MagicMock(status_code=404, text="")
    with patch("plugins.erome.plugin.session", return_value=sess):
        with pytest.raises(CloudError) as e1:
            Erome().list("https://www.erome.com/a/Missing")
    assert e1.value.code == "cloud_not_found"

    sess.get.return_value = MagicMock(status_code=403, text="")
    with patch("plugins.erome.plugin.session", return_value=sess):
        with pytest.raises(CloudError) as e2:
            Erome().list("https://www.erome.com/a/Denied")
    assert e2.value.code == "cloud_denied"


def test_kemono_coomer_single_post_and_creator_fallback():
    from plugins.kemono.plugin import KemonoCoomer

    sess = MagicMock()
    post_payload = {
        "post": {
            "id": "777",
            "title": "Tek Gönderi",
            "published": "2026-10-01T10:00:00",
            "file": {"name": "cover.png", "path": "/ab/cd/cover.png"},
            "attachments": [
                {"name": "video.mp4", "path": "/11/22/video.mp4"},
                {"name": "dup.mp4", "path": "/11/22/video.mp4"},
            ],
        }
    }
    sess.get.return_value = MagicMock(status_code=200)
    sess.get.return_value.json.return_value = post_payload
    sess.request.return_value = MagicMock(status_code=200)
    sess.request.return_value.json.return_value = post_payload
    sess.head.return_value = MagicMock(ok=True, headers={"Content-Length": "1234"})

    with patch("plugins.kemono.plugin.session", return_value=sess):
        listing = KemonoCoomer().list("https://kemono.su/patreon/user/42/post/777")
    assert listing.title == "Tek Gönderi"
    assert len(listing.files) == 2
    assert listing.files[0].url == "https://kemono.su/data/ab/cd/cover.png"
    assert listing.files[1].url == "https://kemono.su/data/11/22/video.mp4"
    assert listing.files[0].size == 1234

    # Creator listing: /posts 404 -> fallback to /user/{id}
    def fake_req(method, url, **kwargs):
        r = MagicMock()
        if url.endswith("/profile"):
            r.status_code = 200
            r.json.return_value = {"name": "SanatciX"}
        elif url.endswith("/posts"):
            r.status_code = 404
        else:
            r.status_code = 200
            r.json.return_value = [
                {"id": "10", "published": "2026-09-01", "file": {"name": "a.jpg", "path": "/aa/a.jpg"}, "attachments": []}
            ]
        return r

    sess2 = MagicMock()
    sess2.request.side_effect = fake_req
    with patch("plugins.kemono.plugin.session", return_value=sess2):
        cl = KemonoCoomer().list("https://coomer.st/onlyfans/user/99")
    assert "SanatciX" in cl.title
    assert len(cl.files) == 1
    assert cl.files[0].url == "https://coomer.st/data/aa/a.jpg"


def test_grab_all_filters_and_new_hosts(tmp_path):
    for url in (
        "https://www.erome.com/a/Demo123",
        "https://kemono.su/patreon/user/123",
        "https://kemono.cr/fanbox/user/456",
        "https://coomer.su/onlyfans/user/abc",
        "https://coomer.st/candfans/user/xyz",
    ):
        assert grab_all.is_supported(url) is True

    ok_bad, err = grab_all.build_filter("video", "2026/01/01", "")
    assert ok_bad is False and "YYYY" in err

    ok_good, expr = grab_all.build_filter("video", "2025-01-01", "2026-12-31")
    assert ok_good is True
    assert "extension.lower()" in expr

    # Eval kontrolu (None, date ve str tarihlerle cokmemeli)
    assert eval(expr, {}, {"extension": "MP4", "date": dt.date(2025, 6, 15)}) is True
    assert eval(expr, {}, {"extension": "jpg", "date": dt.date(2025, 6, 15)}) is False
    assert eval(expr, {}, {"extension": "mp4", "date": None}) is False
    assert eval(expr, {}, {"extension": "mp4", "date": "2025-06-15T12:00:00"}) is True

    fake_proc = MagicMock(pid=999)
    with patch("app.core.grab_all.ensure_gallery_dl", return_value=(True, ["gallery-dl"])), \
         patch("app.core.grab_all.subprocess.Popen", return_value=fake_proc) as popen_mock:
        res = grab_all.start(
            "https://kemono.su/patreon/user/123",
            str(tmp_path),
            limit=10,
            media_type="image",
            date_after="2026-01-01",
        )
    assert res["ok"] is True
    cmd = popen_mock.call_args[0][0]
    assert "--filter" in cmd
    assert "--range" in cmd and "1-10" in cmd


def test_season_scraper_okru_vk_mailru():
    # 1. Ok.ru (video -> /videoembed + data-options JSON)
    ok_meta = {
        "flashvars": {
            "metadata": json.dumps({
                "videos": [
                    {"name": "sd", "url": "https://vd.okcdn.ru/sd.mp4"},
                    {"name": "full", "url": "https://vd.okcdn.ru/1080.mp4"},
                ]
            })
        }
    }
    ok_embed_html = f'<div data-options="{html.escape(json.dumps(ok_meta), quote=True)}"></div>'
    s_ok = MagicMock()
    s_ok.get.side_effect = [
        MagicMock(status_code=200, text="<html><body></body></html>"),
        MagicMock(status_code=200, url="https://ok.ru/videoembed/555666", text=ok_embed_html),
    ]
    assert season_scraper.resolve_embed("https://ok.ru/video/555666", session=s_ok) == "https://vd.okcdn.ru/1080.mp4"

    # 2. VK / vkvideo.ru (normal + kacisli JSON)
    vk_html = '<script>var playerParams = {"hls":"https:\\/\\/vkvd.vkuservideo.net\\/master.m3u8?q=1"};</script>'
    s_vk = MagicMock()
    s_vk.get.return_value = MagicMock(status_code=200, text=vk_html)
    assert season_scraper.resolve_embed("https://vkvideo.ru/video-123_456", session=s_vk) == "https://vkvd.vkuservideo.net/master.m3u8?q=1"

    vk_esc = r'<script>var d = "{\"url1080\":\"https:\\/\\/vkvd.vkuservideo.net\\/1080.mp4\"}";</script>'
    s_vk2 = MagicMock()
    s_vk2.get.return_value = MagicMock(status_code=200, text=vk_esc)
    assert season_scraper.resolve_embed("https://vk.com/video_ext.php?oid=-1&id=2", session=s_vk2) == "https://vkvd.vkuservideo.net/1080.mp4"

    # 3. Mail.ru video embed
    s_mail = MagicMock()
    meta_r = MagicMock(status_code=200)
    meta_r.json.return_value = {
        "videos": [
            {"key": "480p", "url": "//cdn.mail.ru/v/480.mp4"},
            {"key": "1080p", "url": "//cdn.mail.ru/v/1080.mp4"},
        ]
    }
    s_mail.get.side_effect = [
        MagicMock(status_code=200, text='<script>window.cfg={"metadataUrl":"//my.mail.ru/+/video/meta/999"};</script>'),
        meta_r,
    ]
    assert season_scraper.resolve_embed("https://my.mail.ru/video/embed/999", session=s_mail) == "https://cdn.mail.ru/v/1080.mp4"

    # 4. Tam sezon taramasi (Ok.ru + Mail.ru gomulu)
    s_sea = MagicMock()
    s_sea.get.side_effect = [
        MagicMock(status_code=200, text='<h1>Örnek Dizi</h1><a href="/bolum-1">Bölüm 1</a>'),
        MagicMock(status_code=200, text='<iframe src="//my.mail.ru/video/embed/101"></iframe>'),
        MagicMock(status_code=200, text='<script>{"metadataUrl":"https://my.mail.ru/+/video/meta/101"}</script>'),
        meta_r,
    ]
    res = season_scraper.scrape_season("https://dizi.example/ornek", session=s_sea)
    assert res["ok"] is True
    assert res["episodes"][0]["stream_url"] == "https://cdn.mail.ru/v/1080.mp4"


def test_kami_hunter_okru_vk_mailru_search_and_preview():
    def fake_get(url, **kwargs):
        r = MagicMock(status_code=200, ok=True, url=url, text="")
        r.json.return_value = {}
        if "ok.ru/video/search" in url:
            r.text = '<a href="/video/112233">Eski Yeraltı Klip</a>'
        elif "vkvideo.ru" in url:
            r.url = "https://vk.com/login"
        elif "my.mail.ru/video/search" in url:
            r.text = '<a href="/mail/user1/video/rap/42.html">Kayıp Parça</a>'
        return r

    sess = MagicMock()
    sess.get.side_effect = fake_get
    res = kami_hunter.search("yeraltı rap", session=sess)
    assert res["ok"] is True
    urls = [it["url"] for it in res["items"]]
    assert "https://ok.ru/video/112233" in urls
    assert "https://my.mail.ru/mail/user1/video/rap/42.html" in urls
    assert any("VK:" in n for n in res["notes"])

    with patch("app.core.season_scraper.resolve_embed", return_value="https://cdn.ok.ru/stream.m3u8"):
        prev = kami_hunter.preview_url("https://ok.ru/video/112233")
    assert prev["ok"] is True
    assert prev["stream"] == "https://cdn.ok.ru/stream.m3u8"
