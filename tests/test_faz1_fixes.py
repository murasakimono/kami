from __future__ import annotations

from unittest.mock import MagicMock

from app.core import lyrics, opensubs
from app.core.manager import _smart_filename


def test_opensubs_rejects_short_substring_trap():
    assert opensubs._similar("Kyle XY", "See") < 0.65
    ok, _ = opensubs._judge(
        {"attributes": {"release": "See.S01E02.1080p", "feature_details": {"movie_name": "See", "season_number": 1, "episode_number": 2}}},
        {"show": "Kyle XY", "season": 1, "episode": 2},
    )
    assert ok is False


def test_opensubs_accepts_matching_show_and_episode():
    ok, score = opensubs._judge(
        {"attributes": {"release": "Kyle.XY.S01E02.720p", "feature_details": {"movie_name": "Kyle XY", "season_number": 1, "episode_number": 2}}},
        {"show": "Kyle XY", "season": 1, "episode": 2},
    )
    assert ok is True
    assert score >= 2


def test_smart_filename_renames_random_hash_and_generic():
    assert _smart_filename("basdasdwisad.mp4", "Kyle XY S01E02 - İzle", "video/mp4") == "Kyle XY S01E02.mp4"
    assert _smart_filename("master.m3u8", "Dragon Ball Z - Bölüm 12", "") == "Dragon Ball Z - Bölüm 12.m3u8"
    assert _smart_filename("Kyle.XY.S01E02.mkv", "DiziBox", "video/x-matroska") == "Kyle.XY.S01E02.mkv"


def test_lyrics_genius_and_azlyrics_fallback(tmp_path):
    mp3 = tmp_path / "Joker - Yaşamak Öldürür.mp3"
    mp3.write_bytes(b"ID3" + b"\x00" * 64)

    session = MagicMock()
    lrclib_empty = MagicMock(status_code=404)
    lrclib_search_empty = MagicMock(status_code=200)
    lrclib_search_empty.json.return_value = []

    genius_search_ok = MagicMock(status_code=200)
    genius_search_ok.json.return_value = {
        "response": {
            "hits": [{"type": "song", "result": {"title": "Yaşamak Öldürür", "url": "https://genius.com/Joker-yasamak-oldurur-lyrics"}}]
        }
    }
    genius_page_ok = MagicMock(
        status_code=200,
        text='<div data-lyrics-container="true">İlk satır<br/>İkinci satır</div>',
    )
    session.get.side_effect = [lrclib_empty, lrclib_search_empty, genius_search_ok, genius_page_ok]

    res = lyrics.fetch_for_file(str(mp3), title_hint="Joker - Yaşamak Öldürür", embed=False,
                                genius_token=lambda: "tok", session=session)
    assert res["lyrics"] == "plain"
    assert res["source"] == "genius"
    assert (tmp_path / "Joker - Yaşamak Öldürür.txt").read_text(encoding="utf-8").strip() == "İlk satır\nİkinci satır"


def test_lyrics_azlyrics_fallback_when_genius_empty(tmp_path):
    mp3 = tmp_path / "Artist - Track.mp3"
    mp3.write_bytes(b"ID3" + b"\x00" * 64)

    session = MagicMock()
    lrclib_404 = MagicMock(status_code=404)
    lrclib_search_empty = MagicMock(status_code=200)
    lrclib_search_empty.json.return_value = []
    az_page = MagicMock(
        status_code=200,
        text='<!-- Usage of azlyrics.com content by any third-party lyrics provider is prohibited -->\nHello world<br>\nSecond line</div>',
    )
    session.get.side_effect = [lrclib_404, lrclib_search_empty, az_page]

    res = lyrics.fetch_for_file(str(mp3), title_hint="Artist - Track", embed=False, session=session)
    assert res["lyrics"] == "plain"
    assert res["source"] == "azlyrics"
    assert (tmp_path / "Artist - Track.txt").read_text(encoding="utf-8").strip() == "Hello world\nSecond line"
