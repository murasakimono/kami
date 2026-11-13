"""Faz 14 testleri: 9:16 dikey kirpma, UGC A/B matrisi, safe-zone, oto oyun vurgu & sanal kamera."""
from __future__ import annotations

import subprocess
from pathlib import Path

from app.core import clip_factory, game_highlight


def _make_dummy_mp4(path: Path, dur: float = 1.2) -> bool:
    ff = clip_factory._ffmpeg()
    if not ff:
        return False
    r = subprocess.run(
        [ff, "-y", "-f", "lavfi", "-i", f"color=c=purple:s=640x360:d={dur}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    return r.returncode == 0 and path.is_file()


def test_safe_zone_and_highlight_scoring():
    sz = clip_factory.safe_zone_rect("tiktok", 1080, 1920)
    assert sz["x"] > 0 and sz["y"] > 0
    assert sz["width"] < 1080 and sz["height"] < 1920

    segs = [
        {"start": 2.0, "end": 8.0, "text": "Neden bu hata herkesi yavaslatiyor?"},
        {"start": 45.0, "end": 55.0, "text": "Sakin bunu deneme, gizli sebep burada!"},
        {"start": 90.0, "end": 95.0, "text": "Normal bir cumle."},
    ]
    picked = clip_factory.score_highlight_segments(segs, clip_sec=25.0, max_clips=2)
    assert len(picked) == 2
    assert picked[0]["score"] >= picked[1]["score"]


def test_vertical_reframe_and_ugc_matrix_real(tmp_path: Path):
    vid = tmp_path / "src.mp4"
    if not _make_dummy_mp4(vid, dur=1.0):
        return  # FFmpeg yoksa atla
    out_v = tmp_path / "vert.mp4"
    res = clip_factory.auto_vertical_reframe(vid, out_v, x_ratio=0.5, target_w=360, target_h=640)
    assert res["ok"] is True
    assert out_v.is_file()

    mat = clip_factory.render_ugc_matrix([str(vid)], str(vid), [str(vid)], tmp_path / "ugc", platform="reels")
    assert mat["ok"] is True
    assert len(mat["outputs"]) == 1
    assert Path(mat["outputs"][0]["path"]).is_file()


def test_game_highlight_watcher_and_vcam(tmp_path: Path):
    class FakeRecorder:
        def __init__(self):
            self.calls = 0

        def save_replay(self) -> str:
            self.calls += 1
            return f"Klip_{self.calls}.mp4"

    rec = FakeRecorder()
    watcher = game_highlight.HighlightWatcher(rec, cooldown_sec=60.0)
    roi_img = tmp_path / "roi.png"
    roi_img.write_bytes(b"fake")

    # Oyun kapaliyken tetiklenmez
    r1 = watcher.check_once(window_title_fn=lambda: "Notepad", grab_roi_fn=lambda: roi_img)
    assert r1["triggered"] is False and r1["reason"] == "no_game"

    # Oyun acik + keyword eslesmesi -> save_replay tetiklenir
    r2 = watcher.check_once(
        window_title_fn=lambda: "VALORANT",
        grab_roi_fn=lambda: roi_img,
        detect_fn=lambda _p, _kw: {"hit": True, "keyword": "ACE"},
    )
    assert r2["triggered"] is True
    assert rec.calls == 1

    # Cooldown icinde tekrar tetiklenmez
    r3 = watcher.check_once(
        window_title_fn=lambda: "VALORANT",
        grab_roi_fn=lambda: roi_img,
        detect_fn=lambda _p, _kw: {"hit": True, "keyword": "ACE"},
    )
    assert r3["triggered"] is False and r3["reason"] == "cooldown"

    vc = game_highlight.virtual_camera_status()
    assert vc["ok"] is True
    assert "pyvirtualcam_installed" in vc


def test_highlight_watcher_no_recorder(tmp_path):
    from app.core import game_highlight

    roi_img = tmp_path / "roi.png"
    roi_img.write_bytes(b"\x89PNG\r\n\x1a\n")
    watcher = game_highlight.HighlightWatcher(recorder=None)
    res = watcher.check_once(
        window_title_fn=lambda: "VALORANT",
        grab_roi_fn=lambda: roi_img,
        detect_fn=lambda _p, _kw: {"hit": True, "keyword": "ACE"},
    )
    assert res["triggered"] is False
    assert res["reason"] == "no_recorder"


def test_ugc_matrix_silent_clips(tmp_path, monkeypatch):
    from app.core import clip_factory

    hook = tmp_path / "hook.mp4"
    body = tmp_path / "body.mp4"
    cta = tmp_path / "cta.mp4"
    for p in (hook, body, cta):
        p.write_bytes(b"fake-mp4")

    monkeypatch.setattr(clip_factory, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(clip_factory, "_has_audio", lambda _p: False)
    seen_cmds = []

    class _FakeRes:
        returncode = 0

    def _fake_run(cmd, **_kwargs):
        seen_cmds.append(cmd)
        Path(cmd[-1]).write_bytes(b"out-mp4")
        return _FakeRes()

    monkeypatch.setattr(clip_factory.subprocess, "run", _fake_run)
    res = clip_factory.render_ugc_matrix([hook], body, [cta], tmp_path / "out")
    assert res["ok"] is True
    assert len(res["outputs"]) == 1
    assert "concat=n=3:v=1:a=0[v]" in " ".join(seen_cmds[0])
