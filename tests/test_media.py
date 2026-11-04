"""Asama 2 medya: secenek -> yt-dlp eslemesi, yonetici medya akisi, kopru /v1/media (ag kullanmaz)."""
from __future__ import annotations

import os

import pytest

from app.core.bridge_server import BridgeServer
from app.core.events import EventBus
from app.core.manager import DownloadManager
from app.core.models import Status
from app.core.queue_store import DownloadStore
from app.core.settings import Settings
from app.engines import ytdlp_engine as yt


# ---------------------------------------------------------------- build_args
def _ydl_opts(opts):
    import yt_dlp
    yt._register_downloader()
    return yt_dlp.parse_options(yt.build_args(opts, "C:/tmp")).ydl_opts


def test_mp4_defaults_map_to_ytdlp():
    o = _ydl_opts({"format": "mp4", "quality": "1080", "subs": True, "embed": True, "sponsorblock": "mark"})
    assert o["external_downloader"] == {"http": "kamiaria2"}
    assert o["concurrent_fragment_downloads"] == 8
    assert "height<=1080" in o["format"] and o["merge_output_format"] == "mp4"
    # insan yapimi EN/TR altyazi, otomatik altyazi YOK, gomulu iz
    assert o["writesubtitles"] is True and not o.get("writeautomaticsub")
    assert {"en", "tr"} <= set(o["subtitleslangs"])
    keys = [p["key"] for p in o["postprocessors"]]
    assert "FFmpegEmbedSubtitle" in keys and "EmbedThumbnail" in keys and "FFmpegMetadata" in keys
    emb = next(p for p in o["postprocessors"] if p["key"] == "FFmpegEmbedSubtitle")
    assert emb["already_have_subtitle"] is False          # yan .vtt dosyasi kalmaz
    meta = next(p for p in o["postprocessors"] if p["key"] == "FFmpegMetadata")
    assert meta["add_chapters"] and meta["add_metadata"]
    sb = next(p for p in o["postprocessors"] if p["key"] == "SponsorBlock")
    mc = next(p for p in o["postprocessors"] if p["key"] == "ModifyChapters")
    assert sb["categories"] and not mc["remove_sponsor_segments"]   # isaretle = kesme yok
    assert o["noplaylist"] is True


def test_mp3_and_sponsor_remove_and_range():
    o = _ydl_opts({"format": "mp3", "audio_kbps": 192, "sponsorblock": "remove", "start": "1:30", "end": "2:00",
                   "embed": False, "subs": True})
    ext = next(p for p in o["postprocessors"] if p["key"] == "FFmpegExtractAudio")
    assert ext["preferredcodec"] == "mp3" and ext["preferredquality"] in ("192", "192K")
    assert not o.get("writesubtitles")                    # mp3'te altyazi yok
    assert "EmbedThumbnail" not in [p["key"] for p in o["postprocessors"]]
    mc = next(p for p in o["postprocessors"] if p["key"] == "ModifyChapters")
    assert set(mc["remove_sponsor_segments"]) == {"sponsor", "selfpromo", "interaction"}
    assert o["download_ranges"] is not None


def test_sponsorblock_off_and_bad_kbps():
    args = yt.build_args({"format": "mp3", "audio_kbps": 999, "sponsorblock": "off"}, "x")
    assert "320K" in args and "--sponsorblock-mark" not in args


def test_parse_time():
    assert yt.parse_time("1:02:03") == 3723 and yt.parse_time("2:30") == 150 and yt.parse_time("") is None
    with pytest.raises(ValueError):
        yt.parse_time("abc")


def test_out_title_sanitized():
    args = yt.build_args({"out_title": 'Film: "A/B" 50%'}, "x")
    out = args[args.index("-o") + 1]
    assert out.endswith(".%(ext)s") and not any(c in out[:-8] for c in '/:"') and "50%%" in out


def test_youtube_gets_no_browser_cookies():
    h = {"Cookie": "a=1", "User-Agent": "UA", "X-Other": "z"}
    assert yt._clean_headers("https://www.youtube.com/watch?v=x", h) == {}
    assert yt._clean_headers("https://cdn.example.com/a.m3u8", h) == {"Cookie": "a=1", "User-Agent": "UA"}
    # Cookie basligi yt-dlp'ye cookiefile olarak gider (uyari yok)
    with yt._cookiefile("https://cdn.example.com/a.m3u8", yt._cookie_of(h)) as ck:
        text = open(ck, encoding="utf-8").read()
        assert ".cdn.example.com\tTRUE\t/\tTRUE\t0\ta\t1" in text
    assert not os.path.exists(ck)
    assert "Cookie:c=1" not in " ".join(yt.build_args({"headers": {"Cookie": "c=1"}}, "D:/x"))


# ---------------------------------------------------------------- yonetici
class FakeRunner:
    def __init__(self):
        self.on_event = None
        self.started, self.cancelled = [], []

    def start(self, did, url, directory, options):
        self.started.append((did, url, options))

    def cancel(self, did):
        self.cancelled.append(did)


class NoEngine:
    connections = 16
    def status(self, gids): return {}
    def start(self, d): raise AssertionError("medya aria2 kaydi acmamali")
    def pause(self, g): pass
    def resume(self, g): pass
    def remove(self, g): pass


@pytest.fixture
def mm(tmp_path):
    s = Settings(tmp_path / "s.json")
    s.set("download_dir", str(tmp_path / "dl"))
    runner = FakeRunner()
    m = DownloadManager(DownloadStore(tmp_path / "k.db"), NoEngine(), EventBus(), s, prober=None, media=runner)
    return m, runner, tmp_path


def test_media_lifecycle(mm):
    m, r, tmp = mm
    d = m.add_media("https://www.youtube.com/watch?v=x", options={"format": "mp3"}, title="Şarkı")
    assert d.kind == "media" and d.status == Status.WAITING and d.category == "music"
    assert d.directory.endswith(("Müzik", "Muzik", "Music")) or "music" in d.directory.lower() or os.path.isdir(d.directory)
    assert r.started[0][2]["format"] == "mp3" and r.started[0][2]["sponsorblock"] == "mark"

    r.on_event(d.id, "started")
    r.on_event(d.id, "progress", phase="downloading", base="Şarkı", size=1000, downloaded=250, speed=50)
    snap = m.snapshot()[0]
    assert snap.status == Status.ACTIVE and snap.downloaded == 250 and snap.speed == 50
    assert m.total_speed() == 50
    assert m.store.get(d.id).options["base"] == "Şarkı"

    m.pause(d.id)
    assert r.cancelled == [d.id] and m.store.get(d.id).status == Status.PAUSED
    assert m.store.get(d.id).downloaded == 250            # ilerleme kalici yazildi
    r.on_event(d.id, "progress", downloaded=400)          # gec gelen olay yok sayilir
    r.on_event(d.id, "cancelled")
    assert m.store.get(d.id).status == Status.PAUSED and m.total_speed() == 0

    m.resume(d.id)
    assert len(r.started) == 2 and m.store.get(d.id).status == Status.WAITING
    final = os.path.join(m.store.get(d.id).directory, "Şarkı.mp3")
    os.makedirs(os.path.dirname(final), exist_ok=True)
    with open(final, "wb") as f:
        f.write(b"x" * 777)
    r.on_event(d.id, "started")
    r.on_event(d.id, "done", path=final)
    done = m.store.get(d.id)
    assert done.status == Status.COMPLETE and done.size == 777 and done.filename == "Şarkı.mp3"


def test_media_error_and_remove_cleans_partials(mm):
    m, r, tmp = mm
    d = m.add_media("https://example.com/v", title="Klip")
    r.on_event(d.id, "progress", base="Klip", downloaded=10, size=100)
    part_dir = m.store.get(d.id).directory
    partials = ["Klip.f137.mp4.part", "Klip.f137.mp4.part.aria2", "Klip.en.vtt"]
    keep = "Klip (başka).mp4"
    for n in partials + [keep]:
        with open(os.path.join(part_dir, n), "wb") as f:
            f.write(b"1")
    r.on_event(d.id, "error", error="ERROR: Video unavailable")
    assert m.store.get(d.id).status == Status.ERROR
    m.media = None   # silmede bekleme olmasin
    m.remove(d.id)
    assert m.store.get(d.id) is None
    left = os.listdir(part_dir)
    assert keep in left and not any(p in left for p in partials)


def test_media_recover_restarts(mm):
    m, r, tmp = mm
    d = m.add_media("https://example.com/v")
    m.store.update(d.id, status=Status.ACTIVE)
    m._recover()
    assert len(r.started) == 2


def test_bad_time_rejected(mm):
    m, r, _ = mm
    with pytest.raises(ValueError):
        m.add_media("https://example.com/v", options={"start": "yarim"})


# ---------------------------------------------------------------- kopru
def test_bridge_media_routes(mm, tmp_path):
    m, r, _ = mm
    seen = []
    m.events.on("media.choose", lambda **kw: seen.append(kw))
    b = BridgeServer(m, tmp_path / "bridge.json")
    code, res = b.handle("/v1/media", {"url": "https://www.youtube.com/watch?v=x", "mode": "choose"})
    assert code == 200 and res["accepted"] and seen and seen[0]["url"].endswith("v=x")
    code, res = b.handle("/v1/media", {"url": "https://cdn.example.com/a.m3u8", "mode": "mp4", "title": "Sekme",
                                       "page_url": "https://example.com/p", "headers": {"Cookie": "c=1"}})
    d = m.store.get(res["ids"][0])
    assert d.kind == "media" and d.source == "extension" and d.options["out_title"] == "Sekme"
    assert d.options["headers"] == {"Cookie": "c=1"}
    assert "headers" not in d.to_public() and "options" not in d.to_public()
    assert b.handle("/v1/media", {"url": "javascript:x"})[0] == 400


def test_bridge_media_cloud_first(mm, tmp_path):
    """MEGA gibi bulut sayfasindan gelen video butonu yt-dlp'ye degil bulut penceresine gider."""
    from app.core.cloud import CloudProvider

    class FakeMega(CloudProvider):
        name, hosts = "mega", ("mega.nz",)

        def list(self, url):
            raise AssertionError("listelenmemeli")

    m, r, _ = mm
    m.cloud.providers.append(FakeMega())
    seen = []
    m.events.on("media.choose", lambda **kw: seen.append(kw))
    b = BridgeServer(m, tmp_path / "bridge.json")
    code, res = b.handle("/v1/media", {"url": "https://gfs1.userstorage.mega.co.nz/dl/x", "mode": "mp4",
                                       "page_url": "https://mega.nz/file/abc#key"})
    assert res["accepted"] and res.get("cloud") and seen[0]["url"] == "https://mega.nz/file/abc#key"
    assert not r.started and not m.store.list()
