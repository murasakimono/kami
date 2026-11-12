"""OpenSubtitles: ad ayristirma ve yanlis dizi/bolum eleme (Kyle XY yerine See indirmesin)."""
from app.core import opensubs as os_


def _item(title, season=None, ep=None, release="", hash_=False, dl=100):
    return {"attributes": {"release": release, "moviehash_match": hash_, "download_count": dl,
                           "feature_details": {"parent_title": title, "season_number": season, "episode_number": ep},
                           "files": [{"file_id": 1}]}}


def test_parse_turkish_and_scene_names():
    assert os_.parse("C:/x/Kyle XY 1. Sezon 2. Bölüm.mp4") == {"show": "Kyle XY", "season": 1, "episode": 2, "year": None}
    assert os_.parse("C:/x/See.S02E06.1080p.mkv")["season"] == 2
    assert os_.parse("C:/x/abc.mkv", "Kyle XY 1. Sezon 2. Bölüm")["show"] == "Kyle XY"
    assert os_.parse("C:/x/Film.2019.1080p.mkv")["season"] is None


def test_judge_rejects_wrong_show_even_with_hash():
    info = os_.parse("C:/x/Kyle XY 1. Sezon 2. Bölüm.mp4")
    assert os_._judge(_item("See", 2, 6, hash_=True), info)[0] is False
    assert os_._judge(_item("Kyle XY", 1, 3), info)[0] is False        # yanlis bolum
    ok, score = os_._judge(_item("Kyle XY", 1, 2), info)
    assert ok and score > 0
