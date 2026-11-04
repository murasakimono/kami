"""Asama 6b: soz, muzik arsivi, AI kuyrugu, sosyal cerezler, kanal takibi (ag/GPU yok; sahte oturumlar)."""
from __future__ import annotations

import os
import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from app.core import aitools, follow, lyrics, media_meta, musicarchive
from app.core.vault import CookieStore, group_of
from tests.test_stage6a import make_api, mgr  # noqa: F401


def make_mp3(path: Path, seconds: int = 3) -> Path:
    from app.engines.ytdlp_engine import find_ffmpeg
    ff = find_ffmpeg() or shutil.which("ffmpeg")
    if not ff:
        pytest.skip("ffmpeg yok")
    subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono", "-t", str(seconds),
                    "-q:a", "9", str(path)], check=True)
    return path


class Resp:
    def __init__(self, code, data=None, content=b""):
        self.status_code, self._data, self.content = code, data, content

    def json(self):
        return self._data


class Sess:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, params=None, **kw):
        self.calls.append((url, params))
        for key, val in self.routes.items():
            if key in url:
                return val(params) if callable(val) else val
        return Resp(404, {})


def test_split_and_clean_titles():
    assert media_meta.split_artist_title("Rick Astley - Never Gonna Give You Up (Official Music Video).mp3") == \
        ("Rick Astley", "Never Gonna Give You Up")
    assert media_meta.split_artist_title("Sezen Aksu – Gülümse [Resmi Klip]") == ("Sezen Aksu", "Gülümse")
    assert media_meta.clean_title("Song ft. Someone") == "Song"


def test_lyrics_synced_writes_lrc_and_embeds(tmp_path):
    p = make_mp3(tmp_path / "Rick Astley - Never Gonna Give You Up.mp3")
    synced = "[00:01.00] Never gonna give you up\n[00:02.00] Never gonna let you down"
    s = Sess({"/api/get": Resp(200, {"id": 1, "syncedLyrics": synced, "plainLyrics": "x", "instrumental": False})})
    res = lyrics.fetch_for_file(str(p), session=s)
    assert res["lyrics"] == "synced" and Path(res["lrc"]).read_text(encoding="utf-8").startswith("[ar:Rick Astley]")
    from mutagen.id3 import ID3
    assert "Never gonna let you down" in str(ID3(str(p)).getall("USLT")[0])
    assert s.calls[0][1]["artist_name"] == "Rick Astley"


def test_lyrics_missing_gives_links_and_genius_song(tmp_path):
    p = make_mp3(tmp_path / "Yeraltı Grubu - Gizli Parça.mp3")
    s = Sess({"/api/get": Resp(404, {}), "/api/search": Resp(200, []),
              "api.genius.com": Resp(200, {"response": {"hits": [
                  {"type": "song", "result": {"title": "Gizli Parça", "url": "https://genius.com/x-lyrics"}}]}})})
    res = lyrics.fetch_for_file(str(p), genius_token=lambda: "tok", session=s)
    assert res["lyrics"] == "none"
    assert res["links"]["genius_song"] == "https://genius.com/x-lyrics"
    assert res["links"]["azlyrics"].startswith("https://search.azlyrics.com/search.php?q=")
    assert not (tmp_path / "Yeraltı Grubu - Gizli Parça.lrc").exists()


def test_lyrics_no_genius_call_without_token(tmp_path):
    p = make_mp3(tmp_path / "A - B.mp3")
    s = Sess({"/api/get": Resp(404, {}), "/api/search": Resp(200, [])})
    lyrics.fetch_for_file(str(p), session=s)
    assert not any("genius" in u for u, _ in s.calls)


def test_musicarchive_moves_and_tags(tmp_path, monkeypatch):
    monkeypatch.setattr(musicarchive, "_last", [0.0])
    monkeypatch.setattr(musicarchive.time, "sleep", lambda s: None)
    p = make_mp3(tmp_path / "rick astley - never gonna give you up.mp3")
    (tmp_path / "rick astley - never gonna give you up.lrc").write_text("[00:01.00]x", encoding="utf-8")
    rec = {"recordings": [{"id": "rec1", "score": 100, "title": "Never Gonna Give You Up", "length": 3000,
                           "artist-credit": [{"name": "Rick Astley"}],
                           "releases": [{"id": "relS", "title": "Single", "status": "Official",
                                         "release-group": {"primary-type": "Single"}, "date": "1987"},
                                        {"id": "relA", "title": "Whenever You Need Somebody", "status": "Official",
                                         "release-group": {"primary-type": "Album"}, "date": "1987-11-12",
                                         "media": [{"track": [{"number": "1"}]}]}]}]}
    s = Sess({"musicbrainz.org": Resp(200, rec), "coverartarchive.org": Resp(200, None, b"\xff\xd8\xff" + b"0" * 50)})
    res = musicarchive.archive(str(p), str(tmp_path / "Muzik"), session=s)
    assert res["archive"] == "ok" and res["album"] == "Whenever You Need Somebody"
    dest = tmp_path / "Muzik" / "Rick Astley" / "Whenever You Need Somebody" / "01 Never Gonna Give You Up.mp3"
    assert Path(res["path"]) == dest and dest.exists() and dest.with_suffix(".lrc").exists()
    assert (dest.parent / "cover.jpg").exists()
    from mutagen.id3 import ID3
    t = ID3(str(dest))
    assert str(t["TALB"]) == "Whenever You Need Somebody" and t.getall("APIC")


def test_musicarchive_low_score_untouched(tmp_path, monkeypatch):
    monkeypatch.setattr(musicarchive.time, "sleep", lambda s: None)
    p = make_mp3(tmp_path / "X - Y.mp3")
    s = Sess({"musicbrainz.org": Resp(200, {"recordings": [{"id": "r", "score": 40, "title": "Y"}]})})
    # 05.11: dusuk MB puaninda MB etiketi yazilmaz; YouTube/dosya adi yedegiyle Sanatci/Tekliler'e gider
    r = musicarchive.archive(str(p), str(tmp_path / "M"), session=s)
    assert r["archive"] == "ok" and r["source"] == "youtube" and r["album"] == ""
    assert os.path.isfile(os.path.join(tmp_path, "M", "X", "Tekliler", "Y.mp3"))


def test_cookie_store_groups_merge(tmp_path):
    st = CookieStore(tmp_path / "c.bin")
    st.save([{"name": "SID", "value": "1", "domain": ".youtube.com"}])
    st.save([{"name": "sessionid", "value": "2", "domain": ".instagram.com"}])
    st.save([{"name": "sessionid", "value": "3", "domain": ".instagram.com"}])   # ayni grup: degisir
    names = sorted((c["domain"], c["value"]) for c in st.load())
    assert names == [(".instagram.com", "3"), (".youtube.com", "1")]
    assert st.groups() == ["instagram", "youtube"] and st.has_login()
    with st.cookiefile("https://www.instagram.com/stories/x/") as f:
        txt = Path(f).read_text(encoding="utf-8")
    assert "instagram.com" in txt and "youtube.com" not in txt
    assert group_of("https://x.com/a/status/1") == "x" and group_of("https://vm.tiktok.com/abc") == "tiktok"


def test_social_cookiefile_respects_setting(tmp_path, monkeypatch):
    from app.engines import ytdlp_engine as yt
    st = CookieStore(tmp_path / "c.bin")
    st.save([{"name": "auth_token", "value": "z", "domain": ".x.com"}])
    monkeypatch.setattr(yt, "COOKIES", st)
    monkeypatch.setattr(yt, "SOCIAL_COOKIES", lambda: True)
    with yt._cookiefile("https://x.com/u/status/1") as f:
        assert f and "auth_token" in Path(f).read_text(encoding="utf-8")
    monkeypatch.setattr(yt, "SOCIAL_COOKIES", lambda: False)
    with yt._cookiefile("https://x.com/u/status/1") as f:
        assert f is None


def test_bridge_drops_social_cookies_when_off(mgr, tmp_path, monkeypatch):  # noqa: F811
    from app.core.bridge_server import BridgeServer
    from app.engines import ytdlp_engine as yt
    st = CookieStore(tmp_path / "c.bin")
    monkeypatch.setattr(yt, "COOKIES", st)
    mgr.settings.set("social_cookies", False)
    b = BridgeServer(mgr, tmp_path / "b.json", on_show=lambda: None)
    code, res = b.handle("/v1/cookies", {"cookies": [
        {"name": "sessionid", "value": "s", "domain": ".instagram.com"},
        {"name": "SID", "value": "y", "domain": ".youtube.com"}]})
    assert code == 200 and res["saved"] == 1
    assert st.groups() == ["youtube"]


def test_ai_queue_missing_tool_and_run(tmp_path, monkeypatch, mgr):  # noqa: F811
    extras = {}
    q = aitools.AiQueue(mgr.settings, lambda did, **kw: extras.setdefault(did, {}).update(kw),
                        lambda did: str(tmp_path / "v.mp4"))
    monkeypatch.setattr(aitools, "installed", lambda n: False)
    r = q.submit("whisper", 1)
    assert r == {"ok": False, "error": "tool_missing", "tool": "whisper", "size_gb": 3.0}
    monkeypatch.setattr(aitools, "installed", lambda n: True)
    (tmp_path / "v.mp4").write_bytes(b"x")
    seen = {}

    def fake_run(args, on_msg, cancel):
        seen["args"] = args
        on_msg({"p": 0.5})
        (tmp_path / "v.srt").write_text("1\n", encoding="utf-8")
        return {"done": str(tmp_path / "v.srt"), "lang": "tr", "device": "cuda"}
    monkeypatch.setattr(aitools, "_run_json", fake_run)
    mgr.settings.set("whisper_embed", False)
    assert q.submit("whisper", 1)["ok"]
    for _ in range(100):
        if extras.get(1, {}).get("ai_whisper") == "done":
            break
        time.sleep(0.02)
    assert extras[1]["ai_whisper"] == "done" and extras[1]["ai_whisper_lang"] == "tr"
    assert seen["args"][0] == "app.tools.whisper_run" and seen["args"][3] == "auto"


def test_follow_first_add_marks_seen_then_new(tmp_path, mgr):  # noqa: F811
    feed = [[{"id": "v3", "url": "u3", "title": "3"}, {"id": "v2", "url": "u2", "title": "2"},
             {"id": "v1", "url": "u1", "title": "1"}]]
    added = []
    svc = follow.FollowService(tmp_path / "f.json", mgr.settings,
                               lambda url, opts, title: added.append((url, opts["format"])),
                               lister=lambda url: ("Kanal", feed[0]))
    r = svc.add_follow("https://www.youtube.com/@kanal", "mp3", backfill=1)
    assert r["ok"] and added == [("u3", "mp3")]           # sadece son 1 video (backfill), gerisi goruldu
    assert svc.check() == 0                                # aralik dolmadi
    feed[0] = [{"id": "v5", "url": "u5", "title": "5"}, {"id": "v4", "url": "u4", "title": "4"}] + feed[0]
    assert svc.check(force=True) == 2
    assert added[1:] == [("u4", "mp3"), ("u5", "mp3")]     # eskiden yeniye
    assert svc.check(force=True) == 0
    assert json.loads((tmp_path / "f.json").read_text(encoding="utf-8"))[0]["name"] == "Kanal"
    assert svc.add_follow("https://youtube.com/@kanal/videos")["error"] == "follow_exists"


def test_follow_normalize():
    assert follow.normalize_url("https://www.youtube.com/@abc") == "https://www.youtube.com/@abc/videos"
    assert follow.normalize_url("https://m.youtube.com/@abc/featured") == "https://www.youtube.com/@abc/videos"
    assert follow.normalize_url("https://www.youtube.com/watch?v=x&list=PL123") == \
        "https://www.youtube.com/playlist?list=PL123"


def test_mediapost_auto_lyrics_and_archive(tmp_path, mgr, monkeypatch):  # noqa: F811
    from app.core.mediapost import MediaPost
    from app.core.models import DownloadRequest
    p = make_mp3(tmp_path / "A - B.mp3")
    d = mgr.add(DownloadRequest(url="https://e.com/A%20-%20B.mp3", filename="A - B.mp3", source="ui"))[0]
    mgr.store.update(d.id, directory=str(tmp_path), filename=p.name, status="complete")
    calls = []
    monkeypatch.setattr(lyrics, "fetch_for_file", lambda *a, **k: calls.append("ly") or
                        {"lyrics": "synced", "links": {}, "lrc": "x.lrc"})
    monkeypatch.setattr(musicarchive, "archive", lambda *a, **k: calls.append("ar") or {"archive": "nomatch"})
    mp = MediaPost(mgr)
    mgr.settings.set("music_archive", True)
    mp.process(d.id)
    assert calls == ["ly", "ar"]
    assert mgr.store.get(d.id).extra["lyrics"] == "synced"


def test_api_job_whitelist_has_6b(mgr):  # noqa: F811
    api = make_api(mgr)
    for n in ("media_lyrics", "media_archive", "follow_add", "follow_check_now", "genius_set_token"):
        assert n in api.JOB_METHODS
    assert api.open_link("https://evil.example/x") is False
