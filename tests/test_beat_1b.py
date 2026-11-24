"""Kami Beat Asama 1b: take destesi, punch-in, dongu turlarindan take, sayim/metronom zamanlamasi, kayit iptali,
JS<->Python esdegerligi."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SR = 48000


def _dc(path: Path, secs: float, amp: float = 0.25) -> Path:
    import numpy as np
    from app.core import beat_studio
    n = int(round(secs * SR))
    beat_studio._write_wav_np(str(path), np.full((n, 2), amp, dtype="float32"), SR)
    return path


def _steps(path: Path, levels: list[float], seg: float, tail: float = 0.0) -> Path:
    """Her seg saniyede bir DC seviyesi degisen sinyal (tur/konum dogrulamasi icin); son seviye tail s daha surer."""
    import numpy as np
    from app.core import beat_studio
    n = int(round(seg * SR))
    mono = np.concatenate([np.full(n, lv, dtype="float32") for lv in levels] + [np.full(int(round(tail * SR)), 0.5, dtype="float32")])
    beat_studio._write_wav_np(str(path), np.stack([mono, mono], axis=1), SR)
    return path


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


@pytest.fixture()
def bs(tmp_path, monkeypatch):
    from app.core import beat_studio
    monkeypatch.setattr(beat_studio, "projects_dir", lambda: (tmp_path / "proj").mkdir(exist_ok=True) or tmp_path / "proj")
    monkeypatch.setattr(beat_studio, "recordings_dir", lambda: (tmp_path / "rec").mkdir(exist_ok=True) or tmp_path / "rec")
    return beat_studio


def _clip(**kw):
    base = {"id": "a", "take_id": "t", "path": "x.wav", "src_in": 0.0, "src_out": 4.0, "start": 1.0,
            "gain_db": 0.0, "fade_in": 0.0, "fade_out": 0.0, "muted": False}
    base.update(kw)
    return base


def _stack3():
    return [
        _clip(id="p", start=0.0, src_out=1.0),
        _clip(id="t1", start=2.0, stack_id="s1", stack_active=False),
        _clip(id="t2", start=2.0, stack_id="s1", stack_active=False),
        _clip(id="t3", start=2.0, stack_id="s1", stack_active=True),
        _clip(id="q", start=9.0),
    ]


# ---------------- 1. deste islemleri ----------------
def test_stack_members_active_view():
    from app.core import beat_clips as bc
    cl = _stack3()
    assert [c["id"] for c in bc.stack_members(cl, "s1")] == ["t1", "t2", "t3"]
    assert bc.stack_members(cl, "") == []
    assert bc.stack_active_id(cl, "s1") == "t3"
    assert [c["id"] for c in bc.stack_view(cl)] == ["p", "t3", "q"]
    cl2 = bc.stack_set_active(cl, "s1", "t1")
    assert bc.stack_active_id(cl2, "s1") == "t1"
    assert [c["id"] for c in bc.stack_view(cl2)] == ["p", "t1", "q"]
    assert sum(1 for c in cl2 if c.get("stack_active")) == 1
    assert cl[3]["stack_active"] is True                       # girdi degismedi
    assert bc.stack_set_active(cl, "s1", "p") == cl           # uye degil -> degisiklik yok
    # hic aktif isaretli yoksa son uye aktif sayilir
    bad = [dict(c, stack_active=False) for c in cl]
    assert bc.stack_active_id(bad, "s1") == "t3"


def test_stack_push_remove_and_normalize():
    from app.core import beat_clips as bc
    cl = bc.stack_push(_stack3(), "s1", _clip(id="t4", start=2.0))
    assert [c["id"] for c in cl] == ["p", "t1", "t2", "t3", "t4", "q"]
    assert bc.stack_active_id(cl, "s1") == "t4"
    cl = bc.stack_remove(cl, "t4")                            # aktif silindi -> son kalan aktif
    assert bc.stack_active_id(cl, "s1") == "t3"
    cl = bc.stack_remove(bc.stack_remove(cl, "t3"), "t2")     # tek uye kaldi -> deste cozulur
    t1 = next(c for c in cl if c["id"] == "t1")
    assert "stack_id" not in t1 and "stack_active" not in t1
    n = bc.normalize(_clip(stack_id=5, stack_active=1))
    assert n["stack_id"] == "5" and n["stack_active"] is True
    n = bc.normalize(_clip(stack_id="", stack_active=True))
    assert "stack_id" not in n and "stack_active" not in n


# ---------------- 2. punch-in bolme ----------------
def _ids():
    k = {"n": 0}

    def gen(kind):
        k["n"] += 1
        return f"{kind}{k['n']}"
    return gen


def test_punch_in_split_bounds_and_fades():
    from app.core import beat_clips as bc
    orig = _clip(id="o", start=1.0, src_in=0.5, src_out=6.5, src_len=10.0, fade_in=0.2, fade_out=0.3)   # 1..7
    punch = {"id": "pp", "path": "rec.wav", "start": 2.995, "src_in": 4.995, "src_out": 7.005, "src_len": 20.0}
    out = bc.punch_in([_clip(id="x", start=20.0), orig], "o", 3.0, 5.0, punch, 0.01, ids=_ids())
    by = {c["id"]: c for c in out}
    before, after = by["o"], next(c for c in out if c["id"] not in ("o", "pp", "x") and c["start"] > 4)
    mid = next(c for c in out if c["id"] not in ("o", "pp", "x") and c is not after)
    p = by["pp"]
    # once: 1.0 .. 3.005, fade_in korunur, fade_out = 10 ms
    assert bc.clip_bounds(before) == [1.0, 3.005] and before["fade_in"] == 0.2 and before["fade_out"] == 0.01
    assert before["src_in"] == 0.5 and "stack_id" not in before
    # punch destesi: 2.995 .. 5.005, punch aktif, orijinal orta parca pasif
    assert bc.clip_bounds(mid) == [2.995, 5.005] and mid["src_in"] == pytest.approx(2.495)
    assert mid["fade_in"] == 0.01 and mid["fade_out"] == 0.01
    assert bc.clip_bounds(p) == [2.995, 5.005] and p["fade_in"] == 0.01 and p["fade_out"] == 0.01
    assert p["stack_id"] == mid["stack_id"] and p["stack_active"] is True and mid["stack_active"] is False
    assert [c["id"] for c in bc.stack_view(out)].count("pp") == 1 and mid["id"] not in [c["id"] for c in bc.stack_view(out)]
    # sonra: 4.995 .. 7.0, fade_in 10 ms, fade_out korunur
    assert bc.clip_bounds(after) == [4.995, 7.0] and after["fade_in"] == 0.01 and after["fade_out"] == 0.3
    assert after["src_in"] == pytest.approx(4.495) and after["src_out"] == 6.5
    # sira: x, once, orta, punch, sonra
    assert [c["id"] for c in out][0] == "x" and [c["id"] for c in out][1] == "o"


def test_punch_in_on_stack_and_edges():
    from app.core import beat_clips as bc
    cl = _stack3()                                 # deste s1: 2..6
    punch = {"id": "pp", "path": "r.wav", "start": 1.995, "src_in": 0.0, "src_out": 2.01}
    out = bc.punch_in(cl, "t2", 1.0, 4.0, punch, 0.01, ids=_ids())     # t0 klip basindan once -> klip basina kirpilir
    pp = next(c for c in out if c["id"] == "pp")
    assert pp["fade_in"] == 0.0 and pp["fade_out"] == 0.01           # once parcasi yok -> fade_in yok
    mids = bc.stack_members(out, pp["stack_id"])
    assert len(mids) == 4 and bc.stack_active_id(out, pp["stack_id"]) == "pp"
    afters = [c for c in out if c.get("stack_id") and c["stack_id"] != pp["stack_id"]]
    assert len(afters) == 3 and all(bc.clip_bounds(c) == [3.995, 6.0] for c in afters)
    act_after = bc.stack_active_id(out, afters[0]["stack_id"])
    assert act_after == afters[-1]["id"]                              # eski aktif take (t3) devami aktif kalir
    assert bc.punch_in(cl, "nope", 1, 2, punch) == cl
    assert bc.punch_in(cl, "p", 0.5, 0.505, punch) == cl              # 10 ms'den kisa aralik


# ---------------- 3. bounce: yalniz aktif deste uyesi + punch kenarlarinda tik yok ----------------
def _project_with_vocal(bs, tmp_path, wav):
    pid = bs.create_project("1b")["project"]["id"]
    bs.add_take_to_track(pid, "vocal1", str(wav), "V")
    proj = bs.load_project(pid)["project"]
    for tr in proj["tracks"]:
        tr["fx"], tr["denoise"], tr["volume_db"], tr["pan"] = [], False, 0.0, 0.0
    return pid, proj


def test_bounce_only_active_stack_member(bs, tmp_path):
    from app.core import beat_clips as bc
    lo = _dc(tmp_path / "lo.wav", 1.0, 0.1)
    hi = _dc(tmp_path / "hi.wav", 1.0, 0.4)
    pid, proj = _project_with_vocal(bs, tmp_path, lo)
    vt = proj["tracks"][1]
    c_lo = dict(vt["clips"][0], id="lo")
    c_hi = dict(c_lo, id="hi", path=str(hi))
    vt["clips"] = bc.stack_push(bc.stack_push([], "s", c_lo), "s", c_hi)
    bs.save_project(proj)
    amp = 0.5 ** 0.5
    out = tmp_path / "b.wav"
    assert bs.bounce(pid, str(out), target_lufs=0.0)["ok"]
    d, _ = bs._read_audio_np(str(out), SR)
    assert d[SR // 2, 0] == pytest.approx(0.4 * amp, abs=0.005)       # yalniz ust (hi) duyulur, toplam degil
    proj = bs.load_project(pid)["project"]                           # kapat/ac: deste aynen geldi
    assert bc.stack_active_id(proj["tracks"][1]["clips"], "s") == "hi"
    proj["tracks"][1]["clips"] = bc.stack_set_active(proj["tracks"][1]["clips"], "s", "lo")
    bs.save_project(proj)
    assert bs.bounce(pid, str(out), target_lufs=0.0)["ok"]
    d, _ = bs._read_audio_np(str(out), SR)
    assert d[SR // 2, 0] == pytest.approx(0.1 * amp, abs=0.005)


def test_punch_render_no_click(bs, tmp_path):
    import numpy as np
    from app.core import beat_clips as bc
    orig = _dc(tmp_path / "o.wav", 4.0, 0.3)
    rec = _dc(tmp_path / "r.wav", 6.0, 0.3)          # ayni seviye: capraz gecis duz kalmali
    h_o, h_r = _md5(orig), _md5(rec)
    clip = bc.normalize({"id": "o", "path": str(orig), "src_in": 0, "src_out": 4.0, "start": 0, "src_len": 4.0})
    pw = {"start": 0.995, "src_in": 1.995, "src_out": 4.005}        # kayit -1.0 s'de baslamis gibi
    p = bc.normalize(dict(pw, id="pp", path=str(rec), src_len=6.0))
    clips = bc.punch_in([clip], "o", 1.0, 3.0, p, 0.01)
    mono = bs.render_track_clips(clips, SR)[:, 0]
    assert len(mono) == pytest.approx(4 * SR, abs=2)
    seg = mono[int(0.9 * SR):int(3.1 * SR)]
    assert np.max(np.abs(seg - 0.3)) < 1e-3                          # ne cukur ne tepe (tik yok)
    # farkli seviye: gecis 10 ms boyunca monoton ve ornekler arasi sicrama kucuk
    rec2 = _dc(tmp_path / "r2.wav", 6.0, 0.6)
    p2 = bc.normalize(dict(pw, id="pp", path=str(rec2), src_len=6.0))
    mono = bs.render_track_clips(bc.punch_in([clip], "o", 1.0, 3.0, p2, 0.01), SR)[:, 0]
    assert np.max(np.abs(np.diff(mono[int(0.9 * SR):int(3.1 * SR)]))) < 0.6 / (0.01 * SR) * 1.5
    assert mono[int(0.98 * SR)] == pytest.approx(0.3, abs=1e-3) and mono[int(2.0 * SR)] == pytest.approx(0.6, abs=1e-3)
    assert mono[int(3.02 * SR)] == pytest.approx(0.3, abs=1e-3)
    assert _md5(orig) == h_o and _md5(rec) == h_r


# ---------------- 4. dongu turlarindan take ----------------
def test_loop_laps_pure():
    from app.core import beat_transport as bt
    # dongu 2..4 (L=2), sayim 1 bar @120 -> tasima 0'da basladi, kayit 0'da (u0e = -0.1: kayit 0.1 s erken)
    laps = bt.loop_laps(-0.1, 8.0, 2.0, 4.0)
    assert [(x["lap"], x["src_in"], x["src_out"]) for x in laps] == [(0, 2.1, 4.1), (1, 4.1, 6.1)]
    assert all(x["start"] == 2.0 and x["complete"] for x in laps)
    laps = bt.loop_laps(0.0, 3.0, 2.0, 4.0)                         # hic tam tur yok -> yarim tur tutulur
    assert len(laps) == 1 and laps[0]["src_out"] == 3.0 and laps[0]["complete"] is False
    assert bt.loop_laps(0.0, 2.1, 2.0, 4.0) == []                    # < 0.25 s yarim tur atilir
    assert bt.loop_laps(0.0, 8.0, 2.0, 2.0) == []


def test_apply_recording_loop_makes_stack(bs, tmp_path):
    import numpy as np
    from app.core import beat_clips as bc
    pid = bs.create_project("Loop")["project"]["id"]
    proj = bs.load_project(pid)["project"]
    proj["latency_ms"] = 10.0
    bs.save_project(proj)
    # 1 s on kayit (sayim) + 3 tam tur (her tur 1 s, seviyesi farkli) + 0.4 s yarim tur
    rec = _steps(tmp_path / "loop.wav", [0.05, 0.1, 0.2, 0.3], 1.0, tail=0.4)
    h = _md5(rec)
    # kayit 0. ornegi duvar saati 100.0; tasima u=1.0 duvar 99.99 -> u0=1.01, 10 ms gecikme -> u0e=1.0
    plan = {"mode": "loop", "loop_a": 2.0, "loop_b": 3.0, "anchor_u": 1.0, "anchor_wall": 99.99}
    r = bs.apply_recording(pid, "vocal1", str(rec), plan, rec_epoch0=100.0)
    assert r["ok"], r
    clips = r["project"]["tracks"][1]["clips"]
    assert len(clips) == 3 and len(r["takes"]) == 3                  # yarim tur atildi
    sid = clips[0]["stack_id"]
    assert all(c["stack_id"] == sid and bc.clip_bounds(c) == [2.0, 3.0] for c in clips)
    assert bc.stack_active_id(clips, sid) == clips[-1]["id"]         # son tur aktif
    assert [c["src_in"] for c in clips] == pytest.approx([1.0, 2.0, 3.0], abs=1e-6)
    mono = bs.render_track_clips(clips, SR)[:, 0]
    assert mono[int(2.5 * SR)] == pytest.approx(0.3, abs=1e-3)       # 3. tur
    clips2 = bc.stack_set_active(clips, sid, clips[0]["id"])
    assert bs.render_track_clips(clips2, SR)[int(2.5 * SR), 0] == pytest.approx(0.1, abs=1e-3)
    # ayni dongu araliginda ikinci kayit ayni desteye eklenir
    r2 = bs.apply_recording(pid, "vocal1", str(rec), plan, rec_epoch0=100.0)
    clips = r2["project"]["tracks"][1]["clips"]
    assert len(clips) == 6 and len({c["stack_id"] for c in clips}) == 1
    assert _md5(rec) == h
    assert np.isfinite(r2["u0e"])


# ---------------- 5. sayim sonrasi kayit konumu + metronom ----------------
def test_count_in_plan_and_linear_placement():
    from app.core import beat_transport as bt
    p = bt.count_in_plan(8.0, 120, 2)
    assert p["transport_start"] == 4.0 and p["duration"] == 4.0 and p["beats"] == 8
    assert [t["t"] for t in p["ticks"]] == [4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5]
    assert [t["accent"] for t in p["ticks"]] == [True, False, False, False] * 2
    assert bt.count_in_plan(8.0, 120, 0)["ticks"] == [] and bt.count_in_plan(8.0, 120, 0)["transport_start"] == 8.0
    assert bt.count_in_plan(1.0, 90, 1)["transport_start"] == pytest.approx(1.0 - 4 * 60 / 90, abs=1e-6)   # negatif olabilir
    # kayit tasima basinda (u=4.0) basladi; 20 ms gecikme; klip 8.0'da (sayim bitimi) baslamali
    u0e = bt.recording_origin(4.0, 50.0, 50.0, 0.02)
    assert u0e == pytest.approx(3.98)
    spec = bt.linear_take(u0e, 10.0, 8.0)
    assert spec == {"start": 8.0, "src_in": pytest.approx(4.02), "src_out": 10.0}
    assert bt.linear_take(9.0, 0.5, 8.0) == {"start": 9.0, "src_in": 0.0, "src_out": 0.5}   # kayit gec basladiysa
    assert bt.linear_take(0.0, 5.0, 8.0) is None


def test_metronome_ticks_and_timeline_wrap():
    from app.core import beat_transport as bt
    t = bt.metronome_ticks(120, 0.0, 2.0)
    assert [x["t"] for x in t] == [0.0, 0.5, 1.0, 1.5] and [x["accent"] for x in t] == [True, False, False, False]
    t = bt.metronome_ticks(90, 1.9, 4.1)
    assert [x["t"] for x in t] == pytest.approx([2.0, 2.666667, 3.333333, 4.0], abs=1e-6)
    assert [x["beat"] for x in t] == [3, 0, 1, 2]
    # yarim acik pencere: arka arkaya pencerelerde tik ne kaybolur ne iki kez gelir
    edges = [0.0, 0.37, 0.5, 1.0000000001, 1.7, 3.0]
    joined = [x["t"] for a, b in zip(edges, edges[1:]) for x in bt.metronome_ticks(120, a, b)]
    assert joined == [x["t"] for x in bt.metronome_ticks(120, 0.0, 3.0)]
    assert bt.timeline_at(5.5, 0.0, 2.0, 4.0) == 3.5 and bt.timeline_at(3.9, 0.0, 2.0, 4.0) == 3.9
    assert bt.timeline_at(4.0, 0.0, 2.0, 4.0) == 2.0 and bt.timeline_at(9.0, 5.0, 2.0, 4.0) == 9.0   # b'den sonra basladi
    pw = bt.punch_window(-1.0, 6.0, 1.0, 3.0, 0.01)
    assert pw == {"start": 0.995, "src_in": 1.995, "src_out": 4.005}


# ---------------- 6. kaydedici: iptal + plana gore yerlesim (sounddevice'siz) ----------------
def test_recorder_cancel_and_stop_with_plan(bs, tmp_path):
    import numpy as np
    from app.core import kami_booth
    rec = kami_booth.PcRecorder()
    pid = bs.create_project("Rec")["project"]["id"]
    rec._project_id, rec._track_id, rec._sr = pid, "vocal1", SR
    rec._recording = True
    rec._on_block(np.full((SR, 1), 0.5, dtype="float32"), SR)
    st = rec.status()
    assert st["level"] == pytest.approx(0.5) and st["level_db"] == pytest.approx(-6.0, abs=0.1) and st["rec_sec"] == 1.0
    assert rec.status()["level"] == 0.0                              # okununca sifirlanir
    r = rec.cancel()
    assert r["ok"] and r["cancelled"] and Path(r["path"]).name.startswith("_iptal_") and Path(r["path"]).is_file()
    assert bs.load_project(pid)["project"]["tracks"][1]["clips"] == []    # take eklenmedi
    # duz kayit, 1 bar sayim @120: tasima 0'da, kayit 0'da basladi, klip 2.0'da baslamali
    rec._recording = True
    rec._epoch0 = None
    rec._chunks, rec._frames = [], 0
    rec._on_block(np.full((4 * SR, 1), 0.2, dtype="float32"), 4 * SR)
    rec._epoch0 = 10.0
    plan = {"mode": "linear", "keep_from": 2.0, "anchor_u": 0.0, "anchor_wall": 10.0}
    r = rec.stop(ai_clean=False, plan=plan)
    assert r["ok"], r
    c = r["project"]["tracks"][1]["clips"][0]
    assert c["start"] == 2.0 and c["src_in"] == pytest.approx(2.0) and c["src_out"] == pytest.approx(4.0)


# ---------------- 7. JS <-> Python esdegerligi ----------------
_NODE_RUNNER = r"""
global.window = {};
require(process.argv[2]);
require(process.argv[3]);
const cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const out = cases.map(([mod, fn, args]) => window[mod][fn](...args));
process.stdout.write(JSON.stringify(out));
"""


def _cases():
    cl = _stack3()
    cases = [
        ["BeatClips", "stack_members", [cl, "s1"]], ["BeatClips", "stack_members", [cl, ""]],
        ["BeatClips", "stack_active_id", [cl, "s1"]], ["BeatClips", "stack_active_id", [cl, "zz"]],
        ["BeatClips", "stack_set_active", [cl, "s1", "t2"]], ["BeatClips", "stack_set_active", [cl, "s1", "q"]],
        ["BeatClips", "stack_view", [cl]], ["BeatClips", "stack_view", [[dict(c, stack_active=False) for c in cl]]],
        ["BeatClips", "stack_push", [cl, "s1", _clip(id="n")]], ["BeatClips", "stack_push", [cl, "s9", _clip(id="n")]],
        ["BeatClips", "stack_remove", [cl, "t3"]], ["BeatClips", "stack_remove", [cl, "p"]],
        ["BeatClips", "stack_remove", [[cl[1], cl[2]], "t1"]],
        ["BeatClips", "is_audible_member", [cl, cl[2]]], ["BeatClips", "is_audible_member", [cl, cl[3]]],
        ["BeatClips", "normalize", [_clip(stack_id=7, stack_active=0)]], ["BeatClips", "normalize", [_clip(stack_id=None)]],
        ["BeatTransport", "count_in_plan", [8.0, 120, 2]], ["BeatTransport", "count_in_plan", [1.0, 93.5, 1]],
        ["BeatTransport", "count_in_plan", [3.0, 120, 0]], ["BeatTransport", "count_in_plan", [3.0, 140, 5]],
        ["BeatTransport", "recording_origin", [4.0, 1700000000.123, 1700000000.05, 0.0123]],
        ["BeatTransport", "linear_take", [3.98, 10.0, 8.0]], ["BeatTransport", "linear_take", [0.0, 5.0, 8.0]],
        ["BeatTransport", "loop_laps", [-0.1, 8.0, 2.0, 4.0]], ["BeatTransport", "loop_laps", [0.0, 3.0, 2.0, 4.0]],
        ["BeatTransport", "loop_laps", [0.3, 9.7, 1.25, 3.0]], ["BeatTransport", "loop_laps", [0.0, 2.1, 2.0, 4.0]],
        ["BeatTransport", "punch_window", [-1.0, 6.0, 1.0, 3.0, 0.01]], ["BeatTransport", "punch_window", [2.0, 1.5, 1.0, 3.0]],
    ]
    for bpm in (60, 87.3, 120, 174):
        for (a, b, o) in ((0, 2, 0), (1.9, 4.1, 0), (-3.1, 0.2, 0.2), (12.34, 15.0, 1.0)):
            cases.append(["BeatTransport", "metronome_ticks", [bpm, a, b, 4, o]])
    for u in (0.0, 1.5, 3.999999, 4.0, 5.25, 17.3):
        cases.append(["BeatTransport", "timeline_at", [u, 0.5, 1.0, 4.0]])
        cases.append(["BeatTransport", "timeline_at", [u, 0.5, None, None]])
    return cases


def test_js_python_equivalence_1b(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node yok")
    from app.core import beat_clips as bc
    from app.core import beat_transport as bt
    mods = {"BeatClips": bc, "BeatTransport": bt}
    cases = _cases()
    runner = tmp_path / "run.js"
    runner.write_text(_NODE_RUNNER, encoding="utf-8")
    p = subprocess.run([node, str(runner), str(ROOT / "app/ui/web/beat-clips.js"), str(ROOT / "app/ui/web/beat-transport.js")],
                       input=json.dumps(cases), capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    js_out = json.loads(p.stdout)
    py_out = json.loads(json.dumps([getattr(mods[m], fn)(*args) for m, fn, args in cases]))
    for (m, fn, args), a, b in zip(cases, py_out, js_out):
        assert a == b, f"{m}.{fn}{tuple(args)}: py={a} js={b}"


def test_beat_1b_ui_js_syntax():
    node = shutil.which("node")
    if not node:
        pytest.skip("node yok")
    for name in ("beat-clips.js", "beat-transport.js", "beat-timeline.js", "beat.js"):
        p = subprocess.run([node, "--check", str(ROOT / "app/ui/web" / name)], capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, f"{name}: {p.stderr}"
    html = (ROOT / "app/ui/web/beat.html").read_text(encoding="utf-8")
    assert html.index("beat-clips.js") < html.index("beat-transport.js") < html.index("beat-timeline.js") < html.index('src="beat.js"')
