"""Dalga 2 (Oynatici & Muzik Ekosistemi) birim ve sozlesme testleri."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent


def test_settings_wave2_defaults(tmp_path, monkeypatch):
    from app.core.settings import DEFAULTS, Settings

    assert DEFAULTS["player_engine"] == "html5"
    assert DEFAULTS["player_loudness_norm"] is False
    assert DEFAULTS["player_target_lufs"] == -14.0
    assert DEFAULTS["discord_rp_enabled"] is False

    s = Settings(tmp_path / "settings.json")
    s.set("player_engine", "libmpv")
    assert s.get("player_engine") == "libmpv"
    s.set("player_loudness_norm", True)
    assert s.get("player_loudness_norm") is True
    s.set("player_target_lufs", -16.0)
    assert s.get("player_target_lufs") == -16.0


def test_harmonic_score_and_autodj_mix(tmp_path):
    from app.core import mix

    # Ayni ton ve BPM -> ~1.0
    assert mix.harmonic_score(120, "Am", 120, "Am") == 1.0
    # Yari/cift tempo uyumu (120 vs 60) + komsu Camelot (8A -> 9A / Em)
    sc = mix.harmonic_score(120, "Am", 60, "Em")
    assert sc > 0.85
    # Uyumsuz BPM ve ton
    bad = mix.harmonic_score(90, "Cm", 130, "F#m")
    assert bad < 0.4

    # build_autodj_mix siralamasi
    t1 = tmp_path / "a.mp3"
    t2 = tmp_path / "b.mp3"
    t3 = tmp_path / "c.mp3"
    for p in (t1, t2, t3):
        p.write_bytes(b"")
    tracks = [
        {"path": str(t1), "name": "A", "kind": "audio"},
        {"path": str(t2), "name": "B", "kind": "audio"},
        {"path": str(t3), "name": "C", "kind": "audio"},
    ]
    fake_meta = {
        str(t1): (120.0, "Am"),
        str(t2): (150.0, "F#m"),
        str(t3): (122.0, "Em"),
    }
    with patch("app.core.mix._analyze_track_cached", side_effect=lambda p, ff, c: fake_meta[p]):
        res = mix.build_autodj_mix(tracks, n=3, seed_path=str(t1), ffmpeg="")
    assert len(res) == 3
    assert res[0]["path"] == str(t1)
    # t1 (120 Am) sonrasinda t3 (122 Em) t2'den (150 F#m) once gelmeli
    assert res[1]["path"] == str(t3)
    assert res[1]["transition_score"] > res[2]["transition_score"]


def test_mpv_engine_status():
    from app.core import mpv_engine

    with patch("app.core.mpv_engine.find_mpv", return_value={"exe": "", "dll": ""}):
        st = mpv_engine.CONTROLLER.status()
        assert st["ok"] is True
        assert st["available"] is False
        assert st["engine"] == "html5"
        res = mpv_engine.CONTROLLER.play("C:/x.mp4")
        assert res["ok"] is False and res["error"] == "mpv_not_installed"


def test_discord_rp_graceful_when_closed():
    from app.core.discord_rp import DiscordPresence

    dp = DiscordPresence()
    with patch.object(dp, "_connect", return_value=False):
        r = dp.update("Test Song", "Artist", "Kami Player", duration=120, elapsed=10)
        assert r["ok"] is False
        assert r["error"] == "discord_not_running"
    c = dp.clear()
    assert c["ok"] is True


def test_music_tag_auto_plan_and_fetch_cover(tmp_path):
    from app.core import music_tag

    f1 = tmp_path / "Contra - Ölü.mp3"
    f1.write_bytes(b"")
    with patch("app.core.music_tag.read_id3_summary", return_value={"artist": "", "title": "", "album": "", "year": "", "has_cover": False}):
        plan = music_tag.auto_tag_plan(str(tmp_path))
    assert plan["ok"] is True
    assert len(plan["items"]) == 1
    assert plan["items"][0]["artist"] == "Contra"
    assert plan["items"][0]["title"] == "Ölü"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": [{
            "artworkUrl100": "https://example.com/art/100x100bb.jpg",
            "artistName": "Contra",
            "trackName": "Ölü",
            "collectionName": "Single",
            "releaseDate": "2014-01-01",
        }]
    }
    mock_img = MagicMock()
    mock_img.status_code = 200
    mock_img.content = b"\xff\xd8\xff\xe0" + b"0" * 64
    mock_img.headers = {"content-type": "image/jpeg"}
    with patch("requests.get", side_effect=[mock_resp, mock_img]):
        cov = music_tag.fetch_hires_cover("Contra", "Ölü")
    assert cov["ok"] is True
    assert cov["source"] == "itunes"
    assert cov["data_url"].startswith("data:image/jpeg;base64,")


def test_wave2_api_surface_and_ui_contracts():
    from app.ui.api import Api

    for m in ("mpv_status", "mpv_install", "mpv_play", "mpv_command", "mpv_stop",
              "mix_autodj", "music_tag_fetch_cover", "music_tag_auto_plan", "music_tag_auto_apply",
              "discord_rp_update", "discord_rp_clear"):
        assert hasattr(Api, m), f"Api.{m} eksik"
    for jm in ("mpv_install", "mix_autodj", "music_tag_fetch_cover", "music_tag_auto_apply", "player_replaygain"):
        assert jm in Api.JOB_METHODS, f"JOB_METHODS icinde {jm} eksik"

    pjs = (ROOT / "app/ui/web/player.js").read_text(encoding="utf-8")
    assert "player_engine" in pjs and "mpv_play" in pjs
    assert "discord_rp_update" in pjs and "discord_rp_clear" in pjs
    assert "plToggleNotes" in pjs

    plib = (ROOT / "app/ui/web/player-lib.js").read_text(encoding="utf-8")
    assert "player_loudness_norm" in plib and "-14 LUFS" in plib
    assert "plNotesDrawer" in plib and "scratchpad_add" in plib
    assert "mpv_install" in plib

    mhtml = (ROOT / "app/ui/web/music.html").read_text(encoding="utf-8")
    assert "mix_autodj" in mhtml and "discord_rp_update" in mhtml

    mthtml = (ROOT / "app/ui/web/music_tag.html").read_text(encoding="utf-8")
    assert "music_tag_fetch_cover" in mthtml and "music_tag_auto_plan" in mthtml and "music_tag_auto_apply" in mthtml
