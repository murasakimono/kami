"""Dalga 3 (Kami Beat Alt Uygulamasi) birim ve sozlesme testleri."""
from __future__ import annotations

import math
from pathlib import Path
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parent.parent


def _make_test_wav(path: Path, freq: float = 220.0, dur: float = 0.5, sr: int = 48000) -> Path:
    from app.core import beat_studio

    t = np.linspace(0, dur, int(sr * dur), endpoint=False, dtype="float32")
    sig = 0.25 * np.sin(2.0 * math.pi * freq * t).astype("float32")
    stereo = np.stack([sig, sig], axis=1)
    beat_studio._write_wav_np(str(path), stereo, sr)
    return path


def test_vst3_scan_and_presets():
    from app.core import beat_studio

    res = beat_studio.scan_vst3()
    assert res["ok"] is True
    assert isinstance(res["plugins"], list)
    names = {p["name"] for p in res["plugins"]}
    # PC'de kurulu olanlardan en az biri (TDR Nova / TDR Kotelnikov) gorunmeli
    assert "TDR Nova" in names or "TDR Kotelnikov" in names
    assert "clean_rap" in beat_studio.VOCAL_PRESETS
    assert "atk_n9_cleanup" in beat_studio.VOCAL_PRESETS


def test_lyrics_syllables_and_rhyme_analysis():
    from app.core import beat_studio

    txt = "Gece yarısı sokakta yürüdüm\nKaranlığın içinde büyüdüm\nBaşka bir yol yok"
    res = beat_studio.analyze_lyrics_bars(txt, bpm=120)
    assert res["ok"] is True
    assert res["total_lines"] == 3
    assert res["lines"][0]["syllables"] == 11  # Ge-ce ya-rı-sı so-kak-ta yü-rü-düm
    assert res["rhyme_groups"] >= 1
    assert res["lines"][0]["rhyme_group"] == res["lines"][1]["rhyme_group"] > 0


def test_fx_chain_and_multitrack_mixdown(tmp_path, monkeypatch):
    from app.core import beat_studio, beat_mcp

    monkeypatch.setattr(beat_studio, "projects_dir", lambda: tmp_path / "proj")
    monkeypatch.setattr(beat_studio, "recordings_dir", lambda: tmp_path / "rec")

    beat_wav = _make_test_wav(tmp_path / "beat.wav", freq=110.0)
    voc_wav = _make_test_wav(tmp_path / "vocal.wav", freq=330.0)

    pr = beat_studio.create_project("Test Parça")
    assert pr["ok"] is True
    pid = pr["project"]["id"]

    with patch("app.core.kami_beat.analyze_bpm", return_value=124.0), \
         patch("app.core.kami_beat.detect_key", return_value={"key": "Am", "camelot": "8A"}):
        beat_studio.add_take_to_track(pid, "beat", str(beat_wav), "Beat")
        beat_studio.add_take_to_track(pid, "vocal1", str(voc_wav), "Take 1")

    ai = beat_mcp.apply_ai_mix_instruction(pid, "vokali öne çıkar ve reverb azalt", "vocal1")
    assert ai["ok"] is True and len(ai["actions"]) >= 1

    mix = beat_studio.render_mixdown(pid, target_lufs=-14.0)
    assert mix["ok"] is True
    assert Path(mix["path"]).is_file()
    assert -18.0 <= mix["lufs"] <= -10.0

    # Gercek .kstudio lirik video uretimi
    from app.core import studio
    loaded = beat_studio.load_project(pid)["project"]
    loaded["lyrics"] = "İlk satır burada\nİkinci satır devam"
    beat_studio.save_project(loaded)
    lv = beat_studio.export_to_lyric_video(pid, "Test Lirik")
    assert lv["ok"] is True and Path(lv["kstudio_path"]).is_file()
    st_loaded = studio.load_project(lv["kstudio_path"])
    tracks_used = {c.get("track") for c in st_loaded.get("clips", [])}
    assert "a1" in tracks_used and "tx" in tracks_used


def test_booth_devices_and_server():
    from app.core import kami_booth

    devs = kami_booth.list_input_devices()
    assert devs["ok"] is True
    st = kami_booth.BOOTH.start("", "vocal1")
    try:
        assert st["ok"] is True and st["running"] is True and st["port"] > 0
        assert st["url"].startswith("http://")
    finally:
        kami_booth.BOOTH.stop()


def test_wave3_api_surface_and_ui_contracts():
    from app.ui.api import Api

    for m in (
        "beat_open", "beat_vst_scan", "beat_presets", "beat_list_projects",
        "beat_create_project", "beat_load_project", "beat_save_project",
        "beat_add_take", "beat_waveform", "beat_measure_lufs",
        "beat_lyrics_analyze", "beat_apply_fx", "beat_render_mixdown",
        "beat_ai_mix", "beat_export_lyric_video", "beat_mashup", "beat_studio_mashup", "beat_pick_audio",
        "booth_devices", "booth_rec_start", "booth_rec_stop", "booth_rec_status",
        "booth_server_start", "booth_server_stop", "booth_server_status",
    ):
        assert hasattr(Api, m), f"Api.{m} eksik"

    for jm in ("beat_render_mixdown", "beat_apply_fx", "beat_mashup", "beat_studio_mashup", "beat_export_lyric_video"):
        assert jm in Api.JOB_METHODS, f"JOB_METHODS icinde {jm} eksik"

    assert (ROOT / "app/ui/web/beat.html").is_file()
    bjs = (ROOT / "app/ui/web/beat.js").read_text(encoding="utf-8")
    assert "beat_studio_mashup" in bjs and "booth_server_stop" in bjs and "player_show" in bjs
    assert (ROOT / "app/ui/web/beat.js").is_file()
    assert (ROOT / "app/ui/web/beat.css").is_file()
    assert (ROOT / "app/ui/web/booth_mobile.html").is_file()
    assert "beat_open" in (ROOT / "app/ui/web/sunak.js").read_text(encoding="utf-8")
