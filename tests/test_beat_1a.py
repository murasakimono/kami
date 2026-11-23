"""Kami Beat Asama 1a: klip islemleri, v2 goc, atomik kayit + history, klip tabanli bounce, gecikme olcumu, JS<->Python esdegerligi."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
SR = 48000


# ---------------- yardimcilar ----------------
def _sine(path: Path, secs: float, freq: float = 440.0, amp: float = 0.25) -> Path:
    import numpy as np
    from app.core import beat_studio
    t = np.arange(int(round(secs * SR)), dtype="float64") / SR
    mono = (amp * np.sin(2 * np.pi * freq * t)).astype("float32")
    beat_studio._write_wav_np(str(path), np.stack([mono, mono], axis=1), SR)
    return path


def _dc(path: Path, secs: float, amp: float = 0.25) -> Path:
    """Sabit genlikli (DC) sinyal: konum/sure/fade dogrulamasi icin en temiz sinyal."""
    import numpy as np
    from app.core import beat_studio
    n = int(round(secs * SR))
    beat_studio._write_wav_np(str(path), np.full((n, 2), amp, dtype="float32"), SR)
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


# ---------------- 1. beat_clips ----------------
def test_split_basic_and_edges():
    from app.core import beat_clips as bc
    clips = [_clip(fade_in=0.5, fade_out=0.7)]
    out = bc.split(clips, "a", 2.5, new_id="b")
    assert [c["id"] for c in out] == ["a", "b"]
    left, right = out
    assert left["src_out"] == 1.5 and left["start"] == 1.0 and left["fade_in"] == 0.5 and left["fade_out"] == 0.0
    assert right["src_in"] == 1.5 and right["src_out"] == 4.0 and right["start"] == 2.5
    assert right["fade_in"] == 0.0 and right["fade_out"] == 0.7
    assert clips[0]["src_out"] == 4.0, "girdi degismemeli (saf fonksiyon)"
    # kenara 10 ms'den yakin bolme -> degisiklik yok
    assert bc.split(clips, "a", 1.005, new_id="b") == clips
    assert bc.split(clips, "a", 4.995, new_id="b") == clips
    assert bc.split(clips, "a", 0.5, new_id="b") == clips
    assert bc.split(clips, "yok", 2.0) == clips


def test_trim_start_end_limits():
    from app.core import beat_clips as bc
    c = _clip(src_in=1.0, src_out=3.0, start=5.0, src_len=4.0, fade_in=1.5, fade_out=0.4)
    t = bc.trim_start(c, 5.5)
    assert t["start"] == 5.5 and t["src_in"] == 1.5 and t["src_out"] == 3.0
    assert t["fade_in"] + t["fade_out"] <= bc.clip_len(t) + 1e-9
    # kaynak basini asamaz: src_in en fazla 0'a iner -> start en az 4.0
    t = bc.trim_start(c, 0.0)
    assert t["src_in"] == 0.0 and t["start"] == 4.0
    # sag kenara 10 ms'den yakin olamaz
    t = bc.trim_start(c, 99.0)
    assert t["start"] == pytest.approx(6.99) and bc.clip_len(t) == pytest.approx(0.01)
    # trim_end: kaynak sonunu (src_len=4) asamaz -> bitis en fazla 5 + (4-1) = 8
    e = bc.trim_end(c, 50.0)
    assert e["src_out"] == 4.0
    e = bc.trim_end(c, 6.0)
    assert e["src_out"] == 2.0
    e = bc.trim_end(c, 0.0)
    assert bc.clip_len(e) == pytest.approx(0.01)
    # src_in < src_out her zaman
    for x in (bc.trim_start(c, 7.0), bc.trim_end(c, 5.0)):
        assert x["src_in"] < x["src_out"]


def test_move_snap_duplicate_delete_fade():
    from app.core import beat_clips as bc
    clips = [_clip(), _clip(id="z", start=10.0)]
    m = bc.move(clips, "a", -3.0)
    assert m[0]["start"] == 0.0
    m = bc.move(clips, "a", 2.3, snap={"bpm": 120, "division": 4})
    assert m[0]["start"] == 2.5
    d = bc.duplicate(clips, "a", new_id="a2")
    assert [c["id"] for c in d] == ["a", "a2", "z"] and d[1]["start"] == 5.0 and d[1]["src_in"] == 0.0
    assert [c["id"] for c in bc.delete(clips, "a")] == ["z"]
    f = bc.set_fade(_clip(), 3.0, 3.0)   # uzunluk 4 -> toplam en fazla 4
    assert f["fade_in"] == 3.0 and f["fade_out"] == 1.0
    f = bc.set_fade(_clip(), -1, 0.5)
    assert f["fade_in"] == 0.0 and f["fade_out"] == 0.5
    assert bc.overlaps(clips[0], _clip(id="q", start=4.9)) and not bc.overlaps(clips[0], _clip(id="q", start=5.0))
    assert bc.clip_bounds(clips[0]) == [1.0, 5.0]


def test_snap_120bpm_quarter_and_sixteenth():
    from app.core import beat_clips as bc
    # 120 BPM: vurus 0.5 s, bar 2 s, 1/16 = 0.125 s
    assert bc.snap_time(0.26, 120, 4) == 0.5
    assert bc.snap_time(0.24, 120, 4) == 0.0
    assert bc.snap_time(1.74, 120, 4) == 1.5
    assert bc.snap_time(0.07, 120, 16) == 0.125
    assert bc.snap_time(0.06, 120, 16) == 0.0
    assert bc.snap_time(3.19, 120, 16) == 3.25
    assert bc.snap_time(2.9, 120, 1) == 2.0
    assert bc.snap_time(3.1, 120, 1) == 4.0
    assert bc.snap_time(1.234, 0, 4) == 1.234      # bpm yok -> yapisma yok
    assert bc.snap_time(1.234, 120, 3) == 1.234    # gecersiz bolum


def test_normalize_rules():
    from app.core import beat_clips as bc
    c = bc.normalize({"src_in": -1, "src_out": 0.001, "start": -5, "fade_in": 9, "fade_out": 9})
    assert c["src_in"] == 0.0 and c["src_out"] == 0.01 and c["start"] == 0.0
    assert c["fade_in"] + c["fade_out"] <= 0.01 + 1e-9 and c["id"].startswith("c_")
    c = bc.normalize({"src_in": 1, "src_out": 9, "src_len": 3})
    assert c["src_out"] == 3.0


# ---------------- 2. goc ----------------
def _v1_project(pid: str, beat: str, voc: str, beat_off: float, voc_off: float) -> dict:
    return {
        "id": pid, "name": "Eski", "bpm": 120, "key": "Am", "lyrics": "", "tracks": [
            {"id": "beat", "name": "Beat", "role": "beat", "path": beat, "takes": [{"id": "tb", "label": "B", "path": beat}],
             "active_take": "tb", "volume_db": 0, "pan": 0, "mute": False, "solo": False, "offset_ms": beat_off, "fx": []},
            {"id": "vocal1", "name": "Vokal", "role": "vocal", "path": voc, "takes": [{"id": "tv", "label": "V", "path": voc}],
             "active_take": "tv", "volume_db": 0, "pan": 0, "mute": False, "solo": False, "offset_ms": voc_off, "fx": []},
            {"id": "adlib", "name": "Adlib", "role": "vocal", "path": "", "takes": [], "active_take": "",
             "volume_db": 0, "pan": 0, "mute": False, "solo": False, "offset_ms": 0, "fx": []},
        ],
    }


def test_v1_migration_positive_negative_offset_idempotent(bs, tmp_path):
    beat = _sine(tmp_path / "b.wav", 3.0)
    voc = _sine(tmp_path / "v.wav", 2.0)
    p = _v1_project("old1", str(beat), str(voc), 250.0, -500.0)
    (bs.projects_dir() / "old1.kbeat.json").write_text(json.dumps(p), encoding="utf-8")
    r = bs.load_project("old1")
    assert r["ok"] and not r.get("recovered")
    proj = r["project"]
    assert proj["schema"] == 2 and proj["latency_ms"] == 0.0
    b, v, a = proj["tracks"]
    assert len(b["clips"]) == 1 and b["offset_ms"] == 0.0
    cb = b["clips"][0]
    assert cb["start"] == 0.25 and cb["src_in"] == 0.0 and cb["src_out"] == pytest.approx(3.0, abs=1e-3)
    assert cb["take_id"] == "tb" and cb["path"] == str(beat)
    cv = v["clips"][0]
    assert cv["start"] == 0.0 and cv["src_in"] == 0.5 and cv["src_out"] == pytest.approx(2.0, abs=1e-3)
    assert a["clips"] == [] and a["latency_ms"] == 0.0
    # idempotent: tekrar yukle -> ayni klipler (ayni id'ler)
    again = bs.load_project("old1")["project"]
    assert again["tracks"][0]["clips"] == b["clips"] and again["tracks"][1]["clips"] == v["clips"]
    assert bs.migrate_project(again) is False


# ---------------- 3. kayit / history / kurtarma ----------------
def test_save_atomic_history_ring_and_recovery(bs):
    pr = bs.create_project("Kayit Testi")["project"]
    pid = pr["id"]
    for i in range(14):
        pr["name"] = f"Ad {i}"
        bs.save_project(pr)
    fp = bs.projects_dir() / f"{pid}.kbeat.json"
    assert not (bs.projects_dir() / f"{pid}.kbeat.json.tmp").exists()
    hist = sorted((bs.projects_dir() / f"{pid}.history").glob("*.json"))
    assert len(hist) == bs.HISTORY_KEEP == 10
    assert json.loads(hist[-1].read_text(encoding="utf-8"))["name"] == "Ad 13"
    # list_projects history/tmp dosyalarini proje sanmamali
    assert [p["id"] for p in bs.list_projects()["projects"]] == [pid]
    # bozuk ana dosya -> en yeni history
    fp.write_text('{"id": "' + pid + '", "tracks": [', encoding="utf-8")
    assert [p["name"] for p in bs.list_projects()["projects"]] == ["Ad 13"], "bozuk proje listeden dusmemeli"
    r = bs.load_project(pid)
    assert r["ok"] and r["recovered"] is True and r["project"]["name"] == "Ad 13"
    assert json.loads(fp.read_text(encoding="utf-8"))["name"] == "Ad 13", "kurtarilan surum geri yazilmali"
    # hepsi bozuk -> hata
    for h in (bs.projects_dir() / f"{pid}.history").glob("*.json"):
        h.write_text("xx", encoding="utf-8")
    fp.write_text("bozuk", encoding="utf-8")
    assert bs.load_project(pid)["ok"] is False


def test_add_take_creates_clips_and_latency(bs, tmp_path):
    a = _sine(tmp_path / "a.wav", 1.5)
    b = _sine(tmp_path / "b.wav", 1.0)
    pid = bs.create_project("Take")["project"]["id"]
    r1 = bs.add_take_to_track(pid, "vocal1", str(a), "T1")
    r2 = bs.add_take_to_track(pid, "vocal1", str(b), "T2")
    clips = r2["project"]["tracks"][1]["clips"]
    assert [c["start"] for c in clips] == [0.0, pytest.approx(1.5, abs=1e-3)]
    assert clips[0]["take_id"] == r1["take"]["id"] and clips[1]["take_id"] == r2["take"]["id"]
    assert r2["project"]["tracks"][1]["path"] == str(b), "geriye uyum alani guncel kalmali"
    # kayittan gelen: proje 30 ms + kanal 20 ms gecikme -> 50 ms sola
    proj = bs.load_project(pid)["project"]
    proj["latency_ms"] = 30.0
    proj["tracks"][2]["latency_ms"] = 20.0
    bs.save_project(proj)
    r3 = bs.add_take_to_track(pid, "adlib", str(a), "Rec", start=2.0, from_recording=True)
    assert r3["clip"]["start"] == pytest.approx(1.95)
    r4 = bs.add_take_to_track(pid, "adlib", str(a), "Rec0", start=0.0, from_recording=True)
    assert r4["clip"]["start"] == 0.0 and r4["clip"]["src_in"] == pytest.approx(0.05)


# ---------------- 4. render / bounce ----------------
def test_bounce_split_move_fade_positions_and_raw_files_untouched(bs, tmp_path):
    import numpy as np
    from app.core import beat_clips as bc
    voc = _dc(tmp_path / "voc.wav", 2.0, 0.25)
    beat = _dc(tmp_path / "beat.wav", 1.0, 0.1)
    h_voc, h_beat = _md5(voc), _md5(beat)

    pid = bs.create_project("Bounce")["project"]["id"]
    with patch("app.core.kami_beat.analyze_bpm", return_value=120.0), \
         patch("app.core.kami_beat.detect_key", return_value={"key": "Am"}):
        bs.add_take_to_track(pid, "beat", str(beat), "B")
    bs.add_take_to_track(pid, "vocal1", str(voc), "V")
    proj = bs.load_project(pid)["project"]
    for tr in proj["tracks"]:
        tr["fx"], tr["denoise"], tr["volume_db"], tr["pan"] = [], False, 0.0, 0.0
    # beat kanali sessiz: yalniz vokal duzenlemelerini olc
    proj["tracks"][0]["mute"] = True
    vt = proj["tracks"][1]
    cid = vt["clips"][0]["id"]
    clips = bc.split(vt["clips"], cid, 1.0, new_id="r")        # [0..1) ve [1..2)
    clips = bc.move(clips, "r", 3.0)                             # sag parca 3.0 s'ye
    clips = [bc.set_fade(c, 0.0, 0.5) if c["id"] == "r" else c for c in clips]   # sag parcaya 0.5 s fade out
    clips = [bc.trim_start(c, 0.25) if c["id"] == cid else c for c in clips]     # sol parca 0.25'ten baslar
    vt["clips"] = clips
    bs.save_project(proj)

    out = tmp_path / "bounce.wav"
    res = bs.bounce(pid, str(out), target_lufs=0.0)
    assert res["ok"], res
    data, sr = bs._read_audio_np(str(out), SR)
    mono = data[:, 0]
    tol = 3   # ornek

    amp = 0.25 * (0.5 ** 0.5)   # merkez pan = esit guc yasasi (-3 dB)

    def on(i):
        return abs(mono[i]) > 0.1

    assert len(mono) == pytest.approx(4.0 * SR, abs=tol)
    assert not on(int(0.24 * SR)) and on(int(0.26 * SR))           # sol parca 0.25'te baslar
    assert on(int(0.99 * SR)) and not on(int(1.01 * SR))           # 1.0'da biter
    assert np.max(np.abs(mono[int(1.02 * SR):int(2.98 * SR)])) < 1e-4   # bosluk
    assert on(int(3.01 * SR))                                       # sag parca 3.0'da
    assert mono[int(3.49 * SR)] == pytest.approx(amp, abs=0.005)   # fade oncesi tam genlik
    assert mono[int(3.75 * SR)] == pytest.approx(amp / 2, abs=0.005)  # fade ortasi ~ yarim
    assert abs(mono[-2]) < 0.01                                     # fade sonu ~ 0
    # ham dosyalar degismedi
    assert _md5(voc) == h_voc and _md5(beat) == h_beat
    # sessize alinmis klip duyulmamali
    proj = bs.load_project(pid)["project"]
    for c in proj["tracks"][1]["clips"]:
        c["muted"] = c["id"] == "r"
    bs.save_project(proj)
    res = bs.bounce(pid, str(out), target_lufs=0.0)
    data, _ = bs._read_audio_np(str(out), SR)
    assert len(data) == pytest.approx(1.0 * SR, abs=tol)


def test_bounce_fx_runs_once_per_track(bs, tmp_path, monkeypatch):
    voc = _sine(tmp_path / "v.wav", 1.0, 300.0, 0.2)
    pid = bs.create_project("FX")["project"]["id"]
    bs.add_take_to_track(pid, "vocal1", str(voc), "V")
    proj = bs.load_project(pid)["project"]
    vt = proj["tracks"][1]
    from app.core import beat_clips as bc
    vt["clips"] = bc.split(vt["clips"], vt["clips"][0]["id"], 0.5, new_id="r")
    bs.save_project(proj)
    calls = []
    real = bs.apply_fx_chain

    def spy(*a, **kw):
        calls.append(a[0])
        return real(*a, **kw)
    monkeypatch.setattr(bs, "apply_fx_chain", spy)
    res = bs.bounce(pid, str(tmp_path / "o.wav"), target_lufs=0.0)
    assert res["ok"]
    assert len(calls) == 1 and "_mix_tmp" in calls[0]


# ---------------- 5. gecikme ----------------
@pytest.mark.parametrize("delay_ms", [0.0, 7.3, 23.0, 61.7, 180.0])
def test_estimate_latency_known_shift(delay_ms):
    import numpy as np
    from app.core import beat_studio as bs
    sig = bs.latency_probe_signal(SR)
    d = int(round(delay_ms * SR / 1000.0))
    rec = np.zeros(len(sig) + 12000, dtype="float32")
    rec[d:d + len(sig)] += 0.3 * sig
    rng = np.random.default_rng(1)
    rec += (0.003 * rng.standard_normal(len(rec))).astype("float32")
    r = bs.estimate_latency(sig, rec, SR)
    assert r["ok"] and abs(r["latency_ms"] - delay_ms) <= 1.0 and r["confidence"] > 0.5


def test_estimate_latency_no_signal():
    import numpy as np
    from app.core import beat_studio as bs
    sig = bs.latency_probe_signal(SR)
    assert bs.estimate_latency(sig, np.zeros(len(sig)), SR) == {"ok": False, "error": "no_signal"}
    rng = np.random.default_rng(2)
    r = bs.estimate_latency(sig, 0.05 * rng.standard_normal(len(sig)), SR)
    assert r["ok"] is False and r["error"] == "no_signal"


def test_measure_latency_without_sounddevice(monkeypatch):
    import builtins
    from app.core import beat_studio as bs
    real = builtins.__import__

    def fake(name, *a, **kw):
        if name == "sounddevice":
            raise ImportError("yok")
        return real(name, *a, **kw)
    monkeypatch.setattr(builtins, "__import__", fake)
    assert bs.measure_latency() == {"ok": False, "error": "sounddevice_missing"}


# ---------------- 6. JS <-> Python esdegerligi ----------------
_NODE_RUNNER = r"""
global.window = {};
require(process.argv[2]);
const B = window.BeatClips;
const cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const out = cases.map(([fn, args]) => B[fn](...args));
process.stdout.write(JSON.stringify(out));
"""


def _cases():
    base = [_clip(fade_in=0.5, fade_out=0.7, src_len=6.0), _clip(id="z", start=7.3, src_in=0.333, src_out=2.111)]
    c = _clip(src_in=1.0, src_out=3.0, start=5.0, src_len=4.0, fade_in=1.5, fade_out=0.4)
    cases = [
        ["split", [base, "a", 2.5, "b"]], ["split", [base, "a", 1.004, "b"]], ["split", [base, "z", 8.0001, "y"]],
        ["split", [base, "a", 4.9999, "b"]], ["split", [base, "nope", 2.0, "b"]],
        ["trim_start", [c, 5.5]], ["trim_start", [c, 0.0]], ["trim_start", [c, 99.0]], ["trim_start", [c, 6.123456789]],
        ["trim_end", [c, 50.0]], ["trim_end", [c, 6.0]], ["trim_end", [c, 0.0]], ["trim_end", [_clip(), 9.87654321]],
        ["move", [base, "a", -3.0, None]], ["move", [base, "a", 2.3, {"bpm": 120, "division": 4}]],
        ["move", [base, "z", 7.77, {"bpm": 93.5, "division": 16}]], ["move", [base, "a", 1.1, {"bpm": 0, "division": 4}]],
        ["duplicate", [base, "a", "a2"]], ["duplicate", [base, "z", "z2"]], ["delete", [base, "a"]],
        ["set_fade", [_clip(), 3.0, 3.0]], ["set_fade", [_clip(), -1, 0.5]], ["set_fade", [c, 0.1, 0.2]],
        ["clip_bounds", [base[1]]], ["overlaps", [base[0], base[1]]], ["overlaps", [base[0], _clip(id="q", start=4.9)]],
        ["normalize", [{"id": "n", "src_in": -1, "src_out": 0.001, "start": -5, "fade_in": 9, "fade_out": 9}]],
        ["normalize", [{"id": "n", "src_in": 1, "src_out": 9, "src_len": 3, "gain_db": "2.5"}]],
        ["track_end", [base]], ["track_end", [[]]],
    ]
    for bpm in (60, 87.3, 120, 140, 174):
        for div in (1, 2, 4, 8, 16):
            for t in (0.0, 0.26, 1.74, 3.19, 12.3456, 61.0):
                cases.append(["snap_time", [t, bpm, div]])
    return cases


def test_js_python_equivalence(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node yok")
    from app.core import beat_clips as bc
    cases = _cases()
    runner = tmp_path / "run.js"
    runner.write_text(_NODE_RUNNER, encoding="utf-8")
    js_file = ROOT / "app/ui/web/beat-clips.js"
    p = subprocess.run([node, str(runner), str(js_file)], input=json.dumps(cases), capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    js_out = json.loads(p.stdout)
    py_out = [getattr(bc, fn)(*args) for fn, args in cases]
    py_out = json.loads(json.dumps(py_out))   # tuple/list ve float/int farklarini esitle
    for (fn, args), a, b in zip(cases, py_out, js_out):
        assert a == b, f"{fn}{tuple(args)[1:]}: py={a} js={b}"


def test_beat_ui_js_syntax():
    node = shutil.which("node")
    if not node:
        pytest.skip("node yok")
    for name in ("beat-clips.js", "beat-timeline.js", "beat.js"):
        p = subprocess.run([node, "--check", str(ROOT / "app/ui/web" / name)], capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, f"{name}: {p.stderr}"
    html = (ROOT / "app/ui/web/beat.html").read_text(encoding="utf-8")
    assert html.index("beat-clips.js") < html.index("beat-timeline.js") < html.index('src="beat.js"')


# ---------------- 7. dalga formu karolari ----------------
def test_waveform_tiles_and_peaks(tmp_path):
    import numpy as np
    from app.core import beat_studio as bs
    p = tmp_path / "w.wav"
    n = 10 * SR
    a = np.zeros((n, 2), dtype="float32")
    a[: 5 * SR] = 0.2
    a[5 * SR:] = 0.8
    bs._write_wav_np(str(p), a, SR)
    full = bs.waveform_peaks(str(p), 100)
    assert full["ok"] and len(full["peaks"]) == 100 and full["duration"] == pytest.approx(10.0, abs=0.01)
    # (adim kenarinda yeniden ornekleme tasmasi olabilir -> oran ile kontrol)
    assert full["peaks"][90] > 0.9 and full["peaks"][10] / full["peaks"][90] == pytest.approx(0.25, abs=0.02)
    t0 = bs.waveform_tile(str(p), rate=64, index=0, size=256)   # 256 tepe = 4 s
    t1 = bs.waveform_tile(str(p), rate=64, index=1, size=256)   # 4..8 s
    assert t0["ok"] and len(t0["peaks"]) == 256
    hi = t1["peaks"][-1]
    assert hi > 0.9 and max(t0["peaks"]) / hi == pytest.approx(0.25, abs=0.02) and t1["peaks"][0] / hi == pytest.approx(0.25, abs=0.02)
    assert len(bs.waveform_tile(str(p), rate=64, index=2, size=256)["peaks"]) == 128   # son karo yarim
    assert bs.waveform_tile(str(p), rate=3)["ok"] is False
