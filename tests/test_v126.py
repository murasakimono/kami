from __future__ import annotations

import subprocess
from pathlib import Path

from app.core import studio, studio_brand, studio_mcp, studio_pro_v26
from app.engines.ytdlp_engine import find_ffmpeg


def _make_sample_mp4(dst: Path, dur: float = 2.5) -> Path:
    ff = find_ffmpeg()
    assert ff, "ffmpeg required"
    subprocess.run(
        [
            ff, "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"testsrc=size=320x180:rate=25:duration={dur}",
            "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={dur}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ac", "2", str(dst),
        ],
        check=True,
    )
    return dst


def test_v126_transitions_run_in_ffmpeg(tmp_path: Path):
    ff = find_ffmpeg()
    assert ff
    for k in studio_pro_v26.TRANS_V26:
        assert k in studio.TRANS
        flt = studio._trans_in(k, 0.4, 320, 180)
        assert flt and flt != "null"
        r = subprocess.run(
            [ff, "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
             "-f", "lavfi", "-i", "color=c=purple:s=320x180:d=0.6",
             "-vf", f"format=rgba,{flt}", "-f", "null", "-"],
            capture_output=True, text=True, timeout=30,
        )
        assert r.returncode == 0, f"{k} failed: {r.stderr}"


def test_v126_ai_inspect_reactive_reframe_proxy_split(tmp_path: Path):
    ff = find_ffmpeg()
    assert ff
    vid = _make_sample_mp4(tmp_path / "sample.mp4", 2.5)

    insp = studio_pro_v26.inspect_video_for_ai(ff, str(vid), tmp_path / "inspect", interval_s=1.0)
    assert insp["ok"] and insp["w"] == 320 and insp["h"] == 180
    assert insp["contact_sheet"] and Path(insp["contact_sheet"]).is_file()
    assert insp["energy_map"]

    kf = studio_pro_v26.build_audio_reactive_kf(ff, str(vid), 0.0, 2.5, 2.5, 0.15)
    assert len(kf) >= 5 and all("z" in x and "t" in x for x in kf)

    ref = studio_pro_v26.auto_reframe_plan(str(vid), 0.0, 2.0, sample_step=0.5)
    assert ref["ok"] and ref["kf"]

    st = studio.Studio(lambda: ff)
    sp = st.split_audio_channels(str(vid))
    assert sp["ok"] and sp["mode"] == "stereo_lr" and len(sp["paths"]) == 2
    px = st.make_proxy(str(vid), 180)
    assert px["ok"] and Path(px["path"]).is_file()


def test_v126_styles_ramps_and_mcp_tools():
    for k in studio_pro_v26.PRO_STYLES_V26:
        assert k in studio_brand.VIRAL_RECIPES
    assert "car_velocity" in studio_pro_v26.SPEED_RAMP_PRESETS
    for tname in ("inspect_video_for_ai", "apply_audio_reactive", "auto_reframe_clip", "apply_speed_ramp"):
        assert tname in studio_mcp.TOOLS
