"""1.17 inceleme duzeltmeleri: bilesik klip, zaman damgasi yuvarlama, loudnorm ornekleme hizi, profil klasoru."""
from app.core import studio as S
from app.core import studio_audio as A
from app.core import studio_edit as E


def _proj():
    p = S.new_project("t", 1280, 720, 30)
    p["assets"]["a1"] = {"path": "C:/v/a.mp4", "kind": "video", "dur": 20.0, "w": 1920, "h": 1080, "audio": False, "name": "a"}
    S.add_clip(p, asset="a1", track="v1", start=2, dur=3)
    S.add_clip(p, text="Merhaba", start=3, dur=2)
    return p


def test_compound_keeps_duration_and_renders():
    p = _proj()
    ids = [c["id"] for c in p["clips"]]
    r = E.create_compound_clip(p["clips"], ids)
    assert r["ok"] and abs(r["compound"]["dur"] - 3.0) < 1e-6      # 2..5 sn
    p["clips"] = r["clips"]
    assert abs(S.project_end(p) - 5.0) < 1e-6                       # eskiden KeyError('dur')
    flat = S.flatten_clips(p["clips"])
    assert sorted(round(c["start"], 3) for c in flat) == [2.0, 3.0]
    from pathlib import Path
    args, total = S.build_export(p, "C:/o.mp4", Path(__import__("tempfile").mkdtemp()), "libx264", {})
    assert total > 0 and args
    assert "Merhaba" in S.build_ass(p)
    back = E.expand_compound_clip(p["clips"], r["compound"]["id"])
    assert sorted(round(c["start"], 3) for c in back) == [2.0, 3.0]


def test_timestamps_carry_rounding():
    assert A._ass_time(1.996) == "0:00:02.00"
    assert A._srt_time(59.9996) == "00:01:00,000"
    assert A._ass_time(3725.5) == "1:02:05.50"


def test_loudnorm_resamples_to_48k():
    assert "aresample=48000" in A.loudnorm_filter()


def test_profile_subfolder_is_sanitised(tmp_path):
    from app.core.profiles import ProfileStore
    st = ProfileStore(path=tmp_path / "profiles.json")
    p = st.create_profile("Kötü", download_subfolder="..\\..\\Windows:System")
    assert ".." not in p["download_subfolder"] and ":" not in p["download_subfolder"] and "\\" not in p["download_subfolder"]
