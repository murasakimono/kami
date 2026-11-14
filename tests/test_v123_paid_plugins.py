"""Wave 8 (v1.23.0) verification tests: Paid NLE Plugin native equivalents + FFmpeg + MCP."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.core import studio, studio_mcp, studio_pro_pack3 as p3, studio_pro_plugins as pl


@pytest.fixture(scope="module")
def ff() -> str:
    return studio_mcp._ffmpeg()


@pytest.fixture(scope="module")
def sample_media(ff: str, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    td = tmp_path_factory.mktemp("v123_media")
    vid = td / "sample.mp4"
    # High contrast bars + pulsed audio bursts at 120 BPM (0.5s apart) for beat detection + pixel sorting
    subprocess.run([
        ff, "-v", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24:duration=2.0",
        "-f", "lavfi", "-i", "aevalsrc='0.7*sin(2*PI*120*t)*(lt(mod(t,0.5),0.08))':s=48000:d=2.0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(vid),
    ], check=True)
    return {"dir": td, "vid": vid}


def test_wave8_catalog_registered():
    cat = studio.catalog()
    for k in p3.FX_PACK3:
        assert k in cat["fx"], f"Missing FX: {k}"
    for k in p3.TRANS_PACK3:
        assert k in cat["trans"], f"Missing Trans: {k}"
    for k in p3.AUDIO_FIX_PACK3:
        assert k in cat["afx"], f"Missing AudioFix: {k}"
    tpl_ids = {t["id"] for t in cat["templates"]}
    for t in p3.TEMPLATES_PACK3:
        assert t["id"] in tpl_ids, f"Missing Template: {t['id']}"


def test_wave8_ffmpeg_filters_all_render(ff: str, sample_media: dict[str, Path]):
    src = sample_media["vid"]
    for k, fx in p3.FX_PACK3.items():
        chain = fx["ff"].replace("W:H", "320:180")
        r = subprocess.run(
            [ff, "-v", "error", "-y", "-i", str(src), "-vf", f"format=rgba,{chain},format=yuv420p", "-t", "0.3", "-f", "null", "-"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, f"FX {k} failed: {r.stderr}"

    for k in p3.TRANS_PACK3:
        tr = p3.trans_in_pack3(k, 0.4, 320, 180, "tr0", 0.0, 24.0)
        r = subprocess.run(
            [ff, "-v", "error", "-y", "-i", str(src), "-vf", f"format=rgba,{tr},format=yuv420p", "-t", "0.4", "-f", "null", "-"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, f"Trans {k} failed: {r.stderr}"

    for k, af in p3.AUDIO_FIX_PACK3.items():
        r = subprocess.run(
            [ff, "-v", "error", "-y", "-i", str(src), "-vn", "-af", af, "-f", "null", "-"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, f"AudioFix {k} failed: {r.stderr}"


def test_beatshift_detection_and_sync(ff: str, sample_media: dict[str, Path]):
    res = pl.detect_audio_beats(ff, str(sample_media["vid"]), min_gap_s=0.3, sensitivity=1.1)
    assert res["ok"] and res["beat_count"] >= 2
    assert res["bpm"] > 0

    pr = {
        "clips": [{"id": "c1", "track": "v1", "asset": "a1", "start": 0.0, "dur": 2.0, "in": 0.0}],
        "tracks": [{"id": "v1", "kind": "video"}],
        "markers": [],
    }
    sync_zoom = pl.apply_beat_sync(json.loads(json.dumps(pr)), res["beats"], clip_id="c1", mode="zoom", zoom_amt=1.18)
    assert sync_zoom["ok"] and sync_zoom["applied"] >= 2
    assert len(sync_zoom["project"]["clips"][0]["zoom"]) >= 4

    sync_cut = pl.apply_beat_sync(json.loads(json.dumps(pr)), [0.5, 1.0, 1.5], clip_id="c1", mode="cut")
    assert sync_cut["ok"] and len(sync_cut["project"]["clips"]) == 4


def test_pixel_sort_and_datamosh(ff: str, sample_media: dict[str, Path]):
    # Verify actual luminance span sorting on image array
    arr = np.zeros((32, 8, 3), dtype=np.uint8)
    arr[4:16, :, :] = np.linspace(220, 80, 12)[:, None, None].astype(np.uint8)
    im = Image.fromarray(arr, mode="RGB")
    sorted_im = pl.pixel_sort_image(im, low_thr=0.25, high_thr=0.95, direction="vertical", reverse=False)
    sorted_col = np.asarray(sorted_im)[4:16, 0, 0]
    assert np.all(np.diff(sorted_col) >= 0)  # ascending luminance verified

    ps = pl.pixel_sort_video(ff, str(sample_media["vid"]), str(sample_media["dir"] / "ps.mp4"), max_frames=6)
    assert ps["ok"] and Path(ps["path"]).stat().st_size > 1000

    for mode in ("i_frame_drop", "echo_bloom", "pixel_repeat"):
        dm = pl.datamosh_video(ff, str(sample_media["vid"]), str(sample_media["dir"] / f"dm_{mode}.mp4"), mode=mode)
        assert dm["ok"] and Path(dm["path"]).stat().st_size > 1000


def test_chartist_parliament_timer_graphics(ff: str, sample_media: dict[str, Path]):
    for kind in ("bar", "line", "parliament", "multistage_timer"):
        out = sample_media["dir"] / f"gfx_{kind}.webm"
        res = pl.generate_data_graphic(ff, kind=kind, out_path=str(out), w=480, h=270, dur=1.0, fps=12)
        assert res["ok"] and out.is_file() and out.stat().st_size > 500


def test_layout_duplicate_powerloop_adaptive_presets_audio(ff: str, sample_media: dict[str, Path], tmp_path: Path):
    pr = {
        "name": "Test",
        "clips": [
            {"id": "c1", "track": "v1", "start": 0.0, "dur": 3.0, "zoom": [{"t": 0.0, "s": 1.0}, {"t": 0.4, "s": 1.2}, {"t": 2.7, "s": 1.0}]},
            {"id": "c2", "track": "v2", "start": 0.0, "dur": 3.0},
            {"id": "c3", "track": "v3", "start": 0.0, "dur": 3.0},
            {"id": "c4", "track": "v4", "start": 0.0, "dur": 3.0},
        ],
    }
    lay = pl.layout_clips(pr, ["c1", "c2", "c3", "c4"], mode="radial")
    assert lay["ok"] and lay["count"] == 4
    assert pr["clips"][0]["scale"] != 1.0

    dup = pl.duplicate_rename_clips(pr, ["c2"], count=2, pattern="{name} #{n}", time_offset=0.5)
    assert dup["ok"] and dup["count"] == 2
    assert any(c.get("name", "").endswith("#2") for c in pr["clips"])

    ploop = pl.apply_power_loop(pr, "c2", mode="pingpong", period_s=0.8)
    assert ploop["ok"] and ploop["keyframe_count"] >= 4

    adap = pl.set_adaptive_timing(pr, "c1", in_dur=0.45, out_dur=0.45, new_dur=5.0)
    assert adap["ok"] and adap["dur"] == 5.0
    assert abs(pr["clips"][0]["zoom"][-1]["t"] - 4.7) < 0.01

    # User Preset save/apply/delete roundtrip
    orig_home = studio.home_dir
    try:
        studio.home_dir = lambda: tmp_path
        sv = pl.save_user_preset("UnitPreset", {"fx": ["grainiac-35mm"]}, pack="TestPack")
        assert sv["ok"]
        lst = pl.list_user_presets("TestPack")
        assert len(lst["presets"]) == 1
        pid = lst["presets"][0]["id"]
        ap = pl.apply_user_preset(pr, "c3", pid)
        assert ap["ok"] and pr["clips"][2]["fx"] == ["grainiac-35mm"]
        dl = pl.delete_user_preset(pid)
        assert dl["removed"] == 1
    finally:
        studio.home_dir = orig_home

    # Soundly Pro audio export
    au = pl.process_audio_clip_pro(ff, str(sample_media["vid"]), str(sample_media["dir"] / "pro.wav"),
                                   preset="denoise_voice", pitch_semitones=2.0, target_lufs=-14.0)
    assert au["ok"] and Path(au["path"]).stat().st_size > 1000


def test_mcp_wave8_tools_registered():
    names = set(studio_mcp.TOOLS.keys())
    expected = {
        "beatshift_sync", "pixel_sort_clip", "datamosh_clip", "generate_chart_graphic",
        "layout_clips", "duplicate_rename_clips", "power_loop", "set_adaptive_timing",
        "user_preset", "audio_pro_process",
    }
    missing = expected - names
    assert not missing, f"Missing Studio MCP tools: {missing}"
