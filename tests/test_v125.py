"""v1.25: Studio yayin oncesi kontrol, konusma temizligi, referans stil, takip yolu, ncnn araclari."""
import shutil
import subprocess

import pytest

from app.core import studio, studio_enhance, studio_finish as sf


def test_speech_suggestions_rules():
    ws = [{"w": "ben", "s": 0, "e": .3}, {"w": "ben", "s": .45, "e": .7}, {"w": "ııı", "s": .9, "e": 1.3},
          {"w": "gel", "s": 1.5, "e": 1.7}, {"w": "gelmek", "s": 1.8, "e": 2.2}, {"w": "istiyorum", "s": 3.2, "e": 3.8},
          {"w": "bu", "s": 3.9, "e": 4.0}, {"w": "bugün", "s": 4.02, "e": 4.4}]
    kinds = [(x["kind"], x["text"]) for x in sf.speech_suggestions(ws)]
    assert ("repeat", "ben") in kinds and ("filler", "ııı") in kinds and ("false", "gel") in kinds
    assert any(k == "pause" for k, _ in kinds)
    assert not any(t == "bu" for _, t in kinds)   # "bu bugün" yarim baslangic degil


def test_speech_unsafe_inside_phrase():
    ws = [{"w": "şey", "s": 0, "e": .3}, {"w": "eee", "s": .31, "e": .6}, {"w": "dedim", "s": .61, "e": .9}]
    s = [x for x in sf.speech_suggestions(ws) if x["kind"] == "filler"][0]
    assert s["safe"] is False


def test_project_qc_flags():
    p = {"size": [1080, 1920], "clips": [
        {"id": "a", "track": "v1", "start": 0, "dur": 4, "trans": {"in": "zoom"}},
        {"id": "b", "track": "v1", "start": 4, "dur": 1, "trans": {"in": "zoom"}},
        {"id": "c", "track": "v1", "start": 5, "dur": 1, "trans": {"in": "zoom"}},
        {"id": "t", "track": "t1", "start": 0, "dur": 2, "text": "X", "style": {"y": .9, "size": 2}}]}
    msgs = " ".join(i["msg"] for i in sf.project_qc(p))
    assert "üst üste" in msgs and "güvenli alan" in msgs and "küçük" in msgs and "hareketsiz" in msgs


def test_identity_lut_and_cube(tmp_path):
    st = {"mean": [.4, .5, .6], "std": [.2, .2, .2], "sat": .3}
    lut = sf.transfer_lut(st, st, 5, 1.0)
    assert all(abs(a - b) < 1e-6 for a, b in zip(lut[1], (0.25, 0, 0)))
    f = sf.write_cube(tmp_path / "x.cube", lut, 5)
    n, data = studio.parse_cube(f)
    assert n == 5 and len(data) == 125


def test_pacing_and_ebur():
    p = sf.pacing([1.0, 2.0, 2.5], 4.0)
    assert p["shots"] == 4 and p["first_cut"] == 1.0 and p["max"] == 1.5
    txt = "t: 0.5 TARGET:-23 LUFS M: -20.0 S: -21\nt: 0.6 TARGET:-23 LUFS M: -inf S: -21\nSummary:\n I: -14.2 LUFS\n LRA: 5.0 LU\n Peak: -0.8 dBFS"
    e = sf.parse_ebur128(txt)
    assert e["i"] == -14.2 and e["tp"] == -0.8 and e["mom"] == [(0.5, -20.0)]


def test_track_path_splits_ass():
    line = "Dialogue: 5,0:00:00.00,0:00:02.00,Default,,0,0,0,,{\\an5\\pos(540,960)\\t(0,200,\\fscx120)}HEY"
    out = studio.apply_track_path([line], [{"t": 0, "dx": 0, "dy": 0}, {"t": 1, "dx": .1, "dy": 0}, {"t": 2, "dx": .1, "dy": .05}], 0.0, 1080, 1920)
    assert len(out) == 2 and "\\move(540,960,648,960,0,1000)" in out[0] and "\\t(" in out[0]
    assert "\\move(648,960,648,1056,0,1000)" in out[1] and "\\t(" not in out[1]


def test_build_ass_uses_track_path():
    p = {"w": 1080, "h": 1920, "tracks": [{"id": "t1", "kind": "text"}], "clips": [
        {"id": "x", "track": "t1", "start": 0, "dur": 2, "text": "A", "style": {"anim": "none"},
         "trackPath": [{"t": 0, "dx": 0, "dy": 0}, {"t": 2, "dx": .2, "dy": 0}]}]}
    assert "\\move(" in studio.build_ass(p)


def test_ncnn_args():
    from pathlib import Path
    a = studio_enhance.esrgan_args("x.exe", Path("i"), Path("o"), "realesr-animevideov3", 2)
    assert a[a.index("-n") + 1] == "realesr-animevideov3" and a[a.index("-s") + 1] == "2"
    r = studio_enhance.rife_args("r.exe", Path("i"), Path("o"), 240)
    assert r[r.index("-n") + 1] == "240"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg yok")
def test_media_qc_and_poster(tmp_path):
    ff = shutil.which("ffmpeg")
    src = tmp_path / "t.mp4"
    subprocess.run([ff, "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=black:s=160x120:d=1", "-f", "lavfi", "-i", "testsrc2=s=160x120:d=2",
                    "-f", "lavfi", "-i", "sine=f=440:d=3", "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]", "-map", "2:a",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(src)], check=True)
    r = sf.media_qc(ff, str(src), "youtube")
    assert any(i["fix"] == "poster" for i in r["issues"])
    b = sf.bake_poster(ff, str(src), 2.0)
    assert b["ok"] and sf.first_frame_verdict(sf.frame_stats(ff, b["path"])) == ""
