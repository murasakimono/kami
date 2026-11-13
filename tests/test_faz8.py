"""Faz 8 testleri: Metin kurgusu, FFT multi-cam senkron, Ripple/Roll/Slip/Slide,
J/L cut, Bileşik Klip, Smart Cut ve Broadcast Ses / Çift Dil Altyazı.
"""
from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path

import pytest

from app.core.studio_audio import (
    assign_speakers,
    build_bilingual_ass,
    build_bilingual_srt,
    build_ducking_filter,
    enhance_audio_file,
    loudnorm_filter,
    voice_enhance_filter,
)
from app.core.studio_edit import (
    apply_jl_cut,
    apply_timeline_edit,
    build_smart_cut_cmd,
    compute_audio_offset,
    create_compound_clip,
    expand_compound_clip,
    remap_captions_for_cuts,
    smart_cut,
    transcript_to_cuts,
)


def _find_ffmpeg() -> str:
    local = Path(__file__).resolve().parent.parent / "bin" / "ffmpeg.exe"
    if local.is_file():
        return str(local)
    return shutil.which("ffmpeg") or ""


def test_transcript_cuts_and_caption_remap() -> None:
    words = [
        {"word": "merhaba", "start": 0.5, "end": 1.0},
        {"word": "bozuk", "start": 2.0, "end": 2.5, "deleted": True},
        {"word": "dunya", "start": 4.0, "end": 4.6},
    ]
    cuts = transcript_to_cuts(words, keep_indices=[0, 2], total_dur=6.0, pad=0.05, merge_gap=0.1)
    assert len(cuts) == 2
    assert cuts[0] == {"in": 0.45, "out": 1.05}
    assert cuts[1] == {"in": 3.95, "out": 4.65}

    caps = [
        {"start": 0.5, "end": 1.0, "text": "merhaba"},
        {"start": 2.0, "end": 2.5, "text": "bozuk"},
        {"start": 4.0, "end": 4.6, "text": "dunya"},
    ]
    remapped = remap_captions_for_cuts(caps, cuts)
    assert [c["text"] for c in remapped] == ["merhaba", "dunya"]
    assert remapped[1]["start"] == pytest.approx(0.65, abs=0.02)


def test_fft_multicam_audio_offset() -> None:
    sr = 8000
    # 1.5s pulse pattern shifted by +0.25s in target
    ref = [0.0] * (sr * 2)
    tgt = [0.0] * (sr * 2)
    for i in range(400):
        val = math.sin(2 * math.pi * 440 * i / sr) * (1.0 - i / 400.0)
        ref[2000 + i] = val
        tgt[4000 + i] = val  # +2000 samples = +0.25s

    res = compute_audio_offset(ref, tgt, sample_rate=sr)
    assert res["ok"] is True
    assert abs(res["offset_sec"] - (-0.25)) <= 0.02 or abs(res["offset_sec"] - 0.25) <= 0.02


def test_timeline_edit_modes_and_compound_clips() -> None:
    base = [
        {"id": "c1", "track": "v1", "start": 0.0, "in": 0.0, "out": 5.0},
        {"id": "c2", "track": "v1", "start": 5.0, "in": 2.0, "out": 7.0},
        {"id": "c3", "track": "v1", "start": 10.0, "in": 0.0, "out": 4.0},
    ]

    rip = apply_timeline_edit(base, "ripple", "c1", 1.5, edge="out")
    assert rip[0]["out"] == 6.5
    assert rip[1]["start"] == 6.5
    assert rip[2]["start"] == 11.5

    rol = apply_timeline_edit(base, "roll", "c1", 1.0)
    assert rol[0]["out"] == 6.0
    assert rol[1]["in"] == 3.0
    assert rol[1]["start"] == 6.0

    slp = apply_timeline_edit(base, "slip", "c2", 1.2)
    assert slp[1]["start"] == 5.0
    assert slp[1]["in"] == 3.2
    assert slp[1]["out"] == 8.2

    sld = apply_timeline_edit(base, "slide", "c2", 1.0)
    assert sld[1]["start"] == 6.0
    assert sld[0]["out"] == 6.0
    assert sld[2]["in"] == 1.0

    jl = apply_jl_cut(base[0], audio_lead=-0.8, audio_tail=1.2)
    assert jl["audioLead"] == -0.8 and jl["audioTail"] == 1.2

    cmp_res = create_compound_clip(base, ["c1", "c2"], name="Grup A")
    assert cmp_res["ok"] is True
    assert len(cmp_res["clips"]) == 2
    expanded = expand_compound_clip(cmp_res["clips"], cmp_res["compound"]["id"])
    assert len(expanded) == 3
    assert {c["id"] for c in expanded} == {"c1", "c2", "c3"}


def test_audio_filters_and_bilingual_subtitles() -> None:
    assert "loudnorm=I=-14.0" in loudnorm_filter()
    assert "afftdn=nf=-25" in voice_enhance_filter("medium")
    duck = build_ducking_filter()
    assert "sidechaincompress=" in duck and "loudnorm=" in duck

    segs = assign_speakers([
        {"start": 0.0, "end": 1.2, "text": "Hello", "tr": "Merhaba"},
        {"start": 3.0, "end": 4.5, "text": "World", "tr": "Dünya"},
    ])
    assert segs[0]["speaker"] == "S1"
    assert segs[1]["speaker"] == "S2"

    ass = build_bilingual_ass(segs)
    assert "Style: S1," in ass and "Style: DualSub," in ass
    assert "Dialogue: 1,0:00:00.00,0:00:01.20,S1,S1,0,0,0,,Hello" in ass
    assert "Dialogue: 0,0:00:00.00,0:00:01.20,DualSub,S1,0,0,0,,Merhaba" in ass

    srt = build_bilingual_srt(segs)
    assert "00:00:00,000 --> 00:00:01,200\nHello\nMerhaba" in srt


def test_ffmpeg_smart_cut_and_voice_enhance_real(tmp_path: Path) -> None:
    ff = _find_ffmpeg()
    if not ff:
        pytest.skip("ffmpeg yok")
    src = tmp_path / "sample.mp4"
    subprocess.run(
        [
            ff, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black:s=320x240:r=25:d=3",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=3",
            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
            str(src),
        ],
        check=True,
        timeout=30,
    )
    cmd = build_smart_cut_cmd(ff, str(src), 0.5, 2.0, str(tmp_path / "cut.mp4"))
    assert "-c" in cmd and "copy" in cmd

    cut_res = smart_cut(ff, str(src), 0.5, 2.0, str(tmp_path / "cut.mp4"))
    assert cut_res["ok"] is True and Path(cut_res["path"]).stat().st_size > 0

    enh_res = enhance_audio_file(ff, str(src), str(tmp_path / "enh.mp4"), strength="medium")
    assert enh_res["ok"] is True and Path(enh_res["path"]).stat().st_size > 0
