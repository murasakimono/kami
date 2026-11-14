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


def test_v1231_regressions_zoom_pitch_fps_pads_sfx(tmp_path: Path, sample_media):
    import shutil
    import subprocess
    import wave
    import numpy as np
    from app.core import studio, studio_pro_plugins as pl

    ff = shutil.which("ffmpeg")
    assert ff
    # 1. Beat zoom & Power Loop write 'z' (not 's') and shift by clip 'in'/'speed', exporting non-1.0 zoompan
    pr = studio.new_project("zoom_reg", 320, 180, 24)
    pr["assets"]["v1"] = {"path": str(sample_media["vid"]), "kind": "video", "dur": 4.0, "w": 320, "h": 180, "audio": True, "name": "v"}
    c = studio.add_clip(pr, asset="v1", track="v1", start=1.0, dur=2.0, **{"in": 0.5})
    pl.apply_beat_sync(pr, [1.0, 1.5], clip_id=c["id"], mode="zoom", zoom_amt=1.2)
    assert any(k.get("z", 1.0) > 1.15 for k in c["zoom"])
    args, _ = studio.build_export(pr, str(tmp_path / "z.mp4"), tmp_path, "libx264", {"quality": "medium"})
    fg = args[args.index("-filter_complex") + 1]
    assert "1.2000" in fg and "zoompan=" in fg

    # 2. Perfect Pitch on 44.1kHz source preserves exact frequency & duration
    s44 = tmp_path / "s44.wav"
    subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1:sample_rate=44100", str(s44)], check=True)
    pr_p = pl.process_audio_clip_pro(ff, str(s44), str(tmp_path / "p44.wav"), preset="", pitch_semitones=2.0)
    assert pr_p["ok"]
    with wave.open(pr_p["path"]) as w:
        sr, n = w.getframerate(), w.getnframes()
        x = np.frombuffer(w.readframes(n), dtype=np.int16)[0::2].astype(float)
    freq = np.fft.rfftfreq(len(x), 1.0 / sr)[np.argmax(np.abs(np.fft.rfft(x)))]
    assert abs(freq - 493.88) < 15.0 and abs((n / sr) - 1.0) < 0.05

    # 3. Pixel Sort on 24fps 2.5s video keeps duration ~2.5s
    v24 = tmp_path / "v24.mp4"
    subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=24:d=2.5",
                    "-f", "lavfi", "-i", "sine=frequency=330:duration=2.5", "-shortest",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(v24)], check=True)
    ps = pl.pixel_sort_video(ff, str(v24), str(tmp_path / "ps24.mp4"), max_frames=120)
    fp = shutil.which("ffprobe")
    ps_dur = float(subprocess.check_output([fp, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration", "-of", "csv=p=0", ps["path"]], text=True).strip())
    assert ps["ok"] and ps_dur > 2.3

    # 4. Parliament 0 seats & invalid color do not crash
    par0 = pl.generate_data_graphic(ff, "parliament", {"parties": [{"label": "X", "seats": 0, "color": "kirmizi"}]},
                                    str(tmp_path / "p0.webm"), w=320, h=240, dur=1.0, fps=12)
    assert par0["ok"]

    # 5. Multiple clips with Pack 3 effects + grade.prism render cleanly without duplicate pad errors
    pr_m = studio.new_project("pads", 320, 180, 24)
    pr_m["assets"]["v1"] = {"path": str(v24), "kind": "video", "dur": 2.5, "w": 320, "h": 180, "audio": True, "name": "v24"}
    studio.add_clip(pr_m, asset="v1", track="v1", start=0.0, dur=0.5, fx=["broken-prism"], grade={"prism": 0.4})
    studio.add_clip(pr_m, asset="v1", track="v1", start=0.5, dur=0.5, fx=["broken-prism", "white-stroke-edge"])
    args_m, _ = studio.build_export(pr_m, str(tmp_path / "pads.mp4"), tmp_path, "libx264", {"quality": "medium"})
    fg_m = args_m[args_m.index("-filter_complex") + 1]
    assert "rgbashift=" in fg_m
    rm = subprocess.run([ff, "-y", "-v", "error", *args_m], cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert rm.returncode == 0, rm.stderr[-300:]

    # 6. New Pack 3 template SFX keys exist and synthesize cleanly
    orig_home = studio.home_dir
    try:
        studio.home_dir = lambda: tmp_path
        sfx_map = studio.ensure_sfx(ff)
        for k in ("kalem-cizim", "haber-flas", "gerilim-vurdu"):
            assert k in sfx_map and Path(sfx_map[k]).stat().st_size > 1000
    finally:
        studio.home_dir = orig_home
