"""Kami Beat Revize R1-R3: zoom'a bagli izgara + milimetrik kaydirma, kalici gecikme + calisan tik olcumu,
sozlerin baslangic noktasi. JS<->Python esdegerligi dahil."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SR = 48000


@pytest.fixture()
def bs(tmp_path, monkeypatch):
    from app.core import beat_studio
    monkeypatch.setattr(beat_studio, "projects_dir", lambda: (tmp_path / "proj").mkdir(exist_ok=True) or tmp_path / "proj")
    monkeypatch.setattr(beat_studio, "recordings_dir", lambda: (tmp_path / "rec").mkdir(exist_ok=True) or tmp_path / "rec")
    monkeypatch.setattr(beat_studio, "_GLOBAL_LATENCY_GETTER", None)
    return beat_studio


# ---------------- R1: izgara + kaydirma ----------------
def test_auto_grid_follows_zoom():
    from app.core import beat_transport as bt
    # 120 BPM: bar 2 s. GRID_MIN_PX = 10 -> iki cizgi arasi en az 10 px olan en ince bolum
    assert bt.auto_grid_div(2, 120) == 1          # bar 4 px: yine de en az 1 bar
    assert bt.auto_grid_div(10, 120) == 2         # 1/2 bar = 10 px
    assert bt.auto_grid_div(40, 120) == 8         # 1/8 = 0.25 s = 10 px
    assert bt.auto_grid_div(80, 120) == 16
    assert bt.auto_grid_div(400, 120) == 32       # cok yakin: 1/32
    assert bt.auto_grid_div(0, 120) == 1
    divs = [bt.auto_grid_div(p, 95) for p in (5, 20, 60, 120, 240, 600)]
    assert divs == sorted(divs)                    # yakinlastikca incelir (azalmaz)
    assert bt.resolve_grid("auto", 40, 120) == 8 and bt.resolve_grid(None, 40, 120) == 8
    assert bt.resolve_grid(16, 40, 120) == 16 and bt.resolve_grid("32", 1, 120) == 32
    assert bt.resolve_grid(0, 400, 120) == 0 and bt.resolve_grid("off", 400, 120) == 0 and bt.resolve_grid(3, 40, 120) == 0
    assert bt.grid_sec(120, 32) == pytest.approx(2.0 / 32) and bt.grid_sec(120, 0) == 0.0


def test_snap_off_has_no_rounding_and_32nd():
    from app.core import beat_clips as bc
    from app.core import beat_transport as bt
    assert bt.snap_to(1.2345678, 120, 0) == 1.234568          # yalniz mikro-saniye
    assert bt.snap_to(1.0005, 120, 0) == 1.0005               # 0.5 ms korunur
    assert bt.snap_to(-0.3, 120, 0) == 0.0
    assert bt.snap_to(1.03, 120, 32) == pytest.approx(1.0)    # 1/32 = 62.5 ms
    assert bt.snap_to(1.04, 120, 32) == pytest.approx(1.0625)
    assert bc.snap_time(1.04, 120, 32) == pytest.approx(1.0625)   # klip tasima da 1/32'yi tanir
    assert bt.snap_to(1.3, 0, 4) == 1.3                       # BPM yok -> serbest


def test_nudge_steps():
    from app.core import beat_transport as bt
    assert bt.nudge_time(1.0, 1, "1ms", 120, 4) == pytest.approx(1.001)
    assert bt.nudge_time(1.0, -1, "1ms", 120, 4) == pytest.approx(0.999)
    assert bt.nudge_time(1.0, 1, "10ms", 120, 4) == pytest.approx(1.01)
    assert bt.nudge_time(0.0005, -1, "1ms", 120, 4) == 0.0    # negatif olmaz
    # izgara adimi (1/4 = 0.5 s): izgara uzerindeyken bir adim, disindayken yondeki ilk cizgi
    assert bt.nudge_time(1.0, 1, "grid", 120, 4) == pytest.approx(1.5)
    assert bt.nudge_time(1.0, -1, "grid", 120, 4) == pytest.approx(0.5)
    assert bt.nudge_time(1.2, 1, "grid", 120, 4) == pytest.approx(1.5)
    assert bt.nudge_time(1.2, -1, "grid", 120, 4) == pytest.approx(1.0)
    assert bt.nudge_time(1.0, 1, "grid", 120, 32) == pytest.approx(1.0625)
    assert bt.nudge_time(1.0, 1, "grid", 120, 0) == pytest.approx(1.01)   # izgara kapali -> 10 ms
    # 1000 kez 1 ms = 1 s (birikimli hata yok)
    t = 2.0
    for _ in range(1000):
        t = bt.nudge_time(t, 1, "1ms", 120, 4)
    assert t == pytest.approx(3.0, abs=1e-6)


def test_format_position():
    from app.core import beat_transport as bt
    assert bt.format_position(0, 120) == {"time": "0:00.000", "bbt": "1.1.1"}
    assert bt.format_position(12.3456, 120) == {"time": "0:12.346", "bbt": "7.1.3"}
    assert bt.format_position(61.001, 120)["time"] == "1:01.001"


# ---------------- R2: kalici gecikme ----------------
def test_settings_beat_latency_validation(tmp_path):
    from app.core.settings import Settings
    p = tmp_path / "settings.json"
    s = Settings(p)
    assert s.get("beat_latency_ms") == 0.0
    s.set("beat_latency_ms", 37.5)
    assert Settings(p).get("beat_latency_ms") == 37.5          # yeniden acilinca duruyor
    s.set("beat_latency_ms", 9000)
    assert s.get("beat_latency_ms") == 500.0
    s.set("beat_latency_ms", "-750")
    assert s.get("beat_latency_ms") == -500.0
    for bad in ("abc", float("nan"), float("inf"), True, None):
        with pytest.raises((ValueError, TypeError)):
            s.set("beat_latency_ms", bad)
    assert s.get("beat_latency_ms") == -500.0
    p.write_text(json.dumps({"beat_latency_ms": "bozuk"}), encoding="utf-8")
    assert Settings(p).get("beat_latency_ms") == 0.0           # bozuk deger -> varsayilan


def test_effective_latency_priority(bs):
    from app.core import beat_transport as bt
    assert bt.effective_latency_ms(0, 42) == {"ms": 42.0, "source": "global"}
    assert bt.effective_latency_ms(None, 42) == {"ms": 42.0, "source": "global"}
    assert bt.effective_latency_ms(15, 42) == {"ms": 15.0, "source": "project"}
    assert bt.effective_latency_ms(-8, 0) == {"ms": -8.0, "source": "project"}
    assert bt.effective_latency_ms(0, 900) == {"ms": 500.0, "source": "global"}
    bs.set_global_latency_getter(lambda: 25.0)
    assert bs.effective_latency({"latency_ms": 0.0}) == {"ms": 25.0, "source": "global"}
    assert bs.effective_latency({"latency_ms": 7.0}) == {"ms": 7.0, "source": "project"}
    bs.set_global_latency_getter(lambda: 1 / 0)                # bozuk okuyucu -> 0
    assert bs.global_latency_ms() == 0.0


def _dc(path: Path, secs: float, amp: float = 0.25) -> Path:
    import numpy as np
    from app.core import beat_studio
    n = int(round(secs * SR))
    beat_studio._write_wav_np(str(path), np.full((n, 2), amp, dtype="float32"), SR)
    return path


def test_new_recordings_use_global_then_project_latency(bs, tmp_path):
    pid = bs.create_project("Lat")["project"]["id"]
    rec = _dc(tmp_path / "r.wav", 3.0)
    plan = {"mode": "linear", "keep_from": 2.0, "anchor_u": 2.0, "anchor_wall": 100.0}
    bs.set_global_latency_getter(lambda: 40.0)                 # genel ayar 40 ms
    r = bs.apply_recording(pid, "vocal1", str(rec), plan, rec_epoch0=100.0)
    assert r["ok"] and r["u0e"] == pytest.approx(2.0 - 0.040)
    c = [x for x in r["project"]["tracks"][1]["clips"]][-1]
    assert c["start"] == pytest.approx(2.0) and c["src_in"] == pytest.approx(0.040)
    proj = bs.load_project(pid)["project"]
    proj["latency_ms"] = 10.0                                  # proje degeri oncelikli
    bs.save_project(proj)
    r = bs.apply_recording(pid, "vocal1", str(rec), plan, rec_epoch0=100.0)
    assert r["u0e"] == pytest.approx(2.0 - 0.010)
    # eski yol (from_recording) da ayni oncelik
    proj = bs.load_project(pid)["project"]
    proj["latency_ms"] = 0.0
    bs.save_project(proj)
    r = bs.add_take_to_track(pid, "vocal1", str(rec), start=5.0, from_recording=True)
    assert r["clip"]["start"] == pytest.approx(5.0 - 0.040)


# ---------------- R2: tik dizisi + olcum ----------------
def test_probe_is_click_train():
    import numpy as np
    from app.core import beat_studio as bs
    P = bs.LAT_PROBE
    sig = bs.latency_probe_signal(SR)
    assert P["count"] >= 5 and P["spacing"] == 0.5
    nz = np.nonzero(np.abs(sig) > 1e-4)[0]
    starts = [int(nz[0])] + [int(b) for a, b in zip(nz, nz[1:]) if b - a > 0.1 * SR]   # 100 ms'den uzun sessizlik = yeni tik
    gaps = np.diff([s / SR for s in starts])
    assert len(starts) == P["count"] and np.allclose(gaps, P["spacing"], atol=0.01)
    assert float(np.max(np.abs(sig))) > 0.7                     # yuksek enerjili
    one = sig[starts[0]:starts[0] + int(P["dur"] * SR)]
    spec = np.abs(np.fft.rfft(one, 1 << 15))
    f = np.fft.rfftfreq(1 << 15, 1 / SR)
    bands = [spec[(f >= lo) & (f < lo * 1.26)].mean() for lo in (500, 800, 1250, 2000, 3150, 5000, 6300)]   # 1/3 oktav
    assert min(bands) > 0.5 * max(bands), bands                 # genis bant: 500 Hz - 8 kHz yaklasik duz


@pytest.mark.parametrize("delay_ms", [0.0, 4.2, 23.0, 61.7, 180.0, 333.3])
def test_estimate_latency_click_train(delay_ms):
    import numpy as np
    from app.core import beat_studio as bs
    sig = bs.latency_probe_signal(SR)
    d = int(round(delay_ms * SR / 1000.0))
    rng = np.random.default_rng(int(delay_ms * 10) + 1)
    rec = np.zeros(len(sig) + 24000)
    rec[d:d + len(sig)] += 0.3 * sig
    rec += 0.003 * rng.standard_normal(len(rec))
    r = bs.estimate_latency(sig, rec, SR)
    assert r["ok"] and abs(r["latency_ms"] - delay_ms) <= 1.0 and r["confidence"] > 0.8, r
    # gurultulu: tik gurultunun altinda (SNR ~ -8 dB), yine +-1 ms
    rec = np.zeros(len(sig) + 24000)
    rec[d:d + len(sig)] += 0.02 * sig
    rec += 0.05 * rng.standard_normal(len(rec))
    r = bs.estimate_latency(sig, rec, SR)
    assert r["ok"] and abs(r["latency_ms"] - delay_ms) <= 1.0, r


def test_estimate_latency_rejects_noise_and_silence():
    import numpy as np
    from app.core import beat_studio as bs
    sig = bs.latency_probe_signal(SR)
    assert bs.estimate_latency(sig, np.zeros(len(sig) + 1000), SR) == {"ok": False, "error": "no_signal"}
    for seed in range(15):
        r = bs.estimate_latency(sig, 0.05 * np.random.default_rng(seed).standard_normal(len(sig) + 20000), SR)
        assert r["ok"] is False and r["error"] == "no_signal" and r["reason"] == "weak", r


def test_latency_from_recording_clock_anchor():
    """Tik arayuzden (Web Audio) calinir; Python yalniz kaydeder. Saat capasi + kayittaki konum -> gecikme."""
    import numpy as np
    from app.core import beat_studio as bs
    sig = bs.latency_probe_signal(SR, at_s=0.0)
    rec_epoch0, play_wall, true_ms = 1000.0, 1000.42, 57.3   # tik kaydin 0.42. saniyesinde planlandi
    pos = int(round((play_wall - rec_epoch0 + true_ms / 1000.0) * SR))
    rng = np.random.default_rng(7)
    rec = 0.01 * rng.standard_normal(pos + len(sig) + 20000)
    rec[pos:pos + len(sig)] += 0.2 * sig
    r = bs.latency_from_recording(rec.astype("float32"), SR, rec_epoch0, play_wall)
    assert r["ok"] and abs(r["latency_ms"] - true_ms) <= 1.0, r
    # negatif gecikme de (saat sapmasi) bulunur
    pos = int(round((play_wall - rec_epoch0 - 0.030) * SR))
    rec = 0.01 * rng.standard_normal(pos + len(sig) + 20000)
    rec[pos:pos + len(sig)] += 0.2 * sig
    r = bs.latency_from_recording(rec, SR, rec_epoch0, play_wall)
    assert r["ok"] and abs(r["latency_ms"] + 30.0) <= 1.0, r
    # mikrofon sessiz -> no_signal (arayuz yonlendirici mesaj verir)
    r = bs.latency_from_recording(np.zeros(SR * 4), SR, rec_epoch0, play_wall)
    assert r["ok"] is False and r["error"] == "no_signal" and r["peak"] == 0.0
    assert bs.latency_from_recording(np.zeros(SR), SR, rec_epoch0, rec_epoch0 + 5.0)["error"] == "clock"


def test_latency_listener_no_sounddevice(monkeypatch):
    import builtins
    from app.core import kami_booth
    real = builtins.__import__

    def fake(name, *a, **kw):
        if name == "sounddevice":
            raise ImportError("x")
        return real(name, *a, **kw)
    monkeypatch.setattr(builtins, "__import__", fake)
    L = kami_booth.LatencyListener()
    assert L.start() == {"ok": False, "error": "sounddevice_missing"}
    assert L.stop(123.0)["error"] == "no_signal"


# ---------------- R3: sozlerin baslangic noktasi ----------------
LYR = """[Verse 1]
bir
iki
uc
[Nakarat]
dort
bes"""


def test_line_times_start_offset_without_sections():
    from app.core import beat_lyrics as bl
    base = [x["t"] for x in bl.line_times(LYR, [], 120, 1)]
    assert base == [0.0, 2.0, 4.0, 6.0, 8.0]                  # bolum yok: en bastan bar bar
    got = [x["t"] for x in bl.line_times(LYR, [], 120, 1, None, 4, 6.5)]
    assert got == [6.5, 8.5, 10.5, 12.5, 14.5]                # hepsi isaretten akar
    assert [x["t"] for x in bl.line_times(LYR, [], 120, 1, None, 4, None)] == base
    assert [x["t"] for x in bl.line_times(LYR, [], 120, 1, None, 4, -3)] == base   # gecersiz -> yok sayilir
    # elle capa oncelikli; capadan sonrasi capaya gore akar
    anc = [{"line": 2, "t": 20.0, "text": "uc"}]
    got = [x["t"] for x in bl.line_times(LYR, [], 120, 1, anc, 4, 6.5)]
    assert got == [6.5, 8.5, 20.0, 22.0, 24.0]


def test_line_times_start_offset_with_sections():
    from app.core import beat_lyrics as bl
    secs = [{"id": "v", "name": "Verse 1", "start": 8.0, "end": 24.0}, {"id": "n", "name": "Nakarat", "start": 24.0, "end": 40.0}]
    got = bl.line_times(LYR, secs, 120, 1, None, 4, 10.0)
    assert [x["t"] for x in got] == [10.0, 12.0, 14.0, 24.0, 26.0]   # ilk blok isarete, nakarat bolumune bagli
    assert [x["t"] for x in bl.line_times(LYR, secs, 120, 1)] == [8.0, 10.0, 12.0, 24.0, 26.0]
    assert bl.lyric_start("3.25") == 3.25 and bl.lyric_start(None) is None and bl.lyric_start(True) is None


def test_lyric_start_persisted_and_validated(bs):
    pr = bs.create_project("Soz")["project"]
    pr["lyric_times"] = {"bars_per_line": 1, "anchors": [], "start": 12.5}
    bs.save_project(pr)
    assert bs.load_project(pr["id"])["project"]["lyric_times"]["start"] == 12.5
    bad = {"tracks": [], "lyric_times": {"bars_per_line": 1, "anchors": [], "start": -4}}
    bs.migrate_project(bad)
    assert "start" not in bad["lyric_times"]
    bad = {"tracks": [], "lyric_times": {"bars_per_line": 2, "start": 3.0}}   # anchors yok -> yeniden kurulur, start korunur
    bs.migrate_project(bad)
    assert bad["lyric_times"] == {"bars_per_line": 2, "anchors": [], "start": 3.0}


def test_first_voiced_time_energy_threshold():
    import numpy as np
    from app.core import beat_sections as bsec
    sr = 16000
    rng = np.random.default_rng(3)
    x = 0.002 * rng.standard_normal(sr * 4)                     # ~ -54 dBFS oda gurultusu
    on = int(1.37 * sr)
    t = np.arange(sr * 2) / sr
    x[on:on + 2 * sr] += 0.3 * np.sin(2 * np.pi * 220 * t)       # 1.37 s'de ses
    x[int(0.5 * sr):int(0.5 * sr) + 40] += 0.5                  # 2.5 ms'lik tik: hold yuzunden sayilmaz
    assert bsec.first_voiced_time(x, sr) == pytest.approx(1.37, abs=0.03)
    assert bsec.first_voiced_time(0.001 * rng.standard_normal(sr), sr) is None   # yalniz gurultu (-60 dBFS)
    assert bsec.first_voiced_time(np.zeros(10), sr) is None


def test_find_lyric_start_vocal_then_verse(bs, tmp_path):
    import numpy as np
    from app.core import beat_sections as bsec
    sr = 48000
    mono = np.zeros(int(3.0 * sr), dtype="float32")
    t = np.arange(int(1.0 * sr)) / sr
    mono[int(1.2 * sr):int(2.2 * sr)] = 0.3 * np.sin(2 * np.pi * 200 * t)
    p = tmp_path / "voc.wav"
    bs._write_wav_np(str(p), np.stack([mono, mono], axis=1), sr)
    proj = {"tracks": [{"id": "beat", "role": "beat", "clips": []},
                       {"id": "vocal1", "role": "vocal", "clips": [
                           {"id": "c1", "path": str(p), "src_in": 0.5, "src_out": 3.0, "start": 10.0}]}],
            "sections": [{"id": "s", "name": "Verse 1", "start": 4.0, "end": 8.0}]}
    r = bsec.find_lyric_start(proj)
    assert r["ok"] and r["source"] == "vocal" and r["start"] == pytest.approx(10.0 + 0.7, abs=0.03)
    proj["tracks"][1]["clips"] = []
    r = bsec.find_lyric_start(proj)
    assert r == {"ok": True, "start": 4.0, "source": "verse", "section_id": "s"}
    proj["sections"] = []
    assert bsec.find_lyric_start(proj)["ok"] is False


# ---------------- JS <-> Python esdegerligi + arayuz ----------------
_NODE_RUNNER = r"""
global.window = {};
require(process.argv[2]);
require(process.argv[3]);
require(process.argv[4]);
const cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const out = cases.map(([mod, fn, args]) => window[mod][fn](...args));
process.stdout.write(JSON.stringify(out));
"""


def _cases():
    c = []
    for pps in (0, 2, 10, 39.9, 40, 80, 160, 333, 1000):
        for bpm in (0, 87, 120, 174.5):
            c.append(["BeatTransport", "auto_grid_div", [pps, bpm]])
    for mode in ("auto", "", None, 0, 1, "2", 4, 8.0, 16, 32, 3, "off"):
        c.append(["BeatTransport", "resolve_grid", [mode, 120, 93]])
    for t in (0, 0.0004, 1.2345678, 3.03125, 7.99, -1):
        for div in (0, 1, 4, 16, 32):
            c.append(["BeatTransport", "snap_to", [t, 97, div]])
            for mode in ("grid", "10ms", "1ms"):
                for d in (1, -1):
                    c.append(["BeatTransport", "nudge_time", [t, d, mode, 97, div]])
    for t in (0, 0.5, 12.3456, 61.001, 599.9999, 1.9999999):
        c.append(["BeatTransport", "format_position", [t, 120]])
        c.append(["BeatTransport", "format_position", [t, 87, 3]])
    for p, g in ((0, 0), (0, 42), (15, 42), (-8, 1), (0, 900), (None, -900), ("", 3)):
        c.append(["BeatTransport", "effective_latency_ms", [p, g]])
    for div in (1, 32):
        c.append(["BeatClips", "snap_time", [1.04, 120, div]])
    secs = [{"id": "v", "name": "Verse 1", "start": 8.0, "end": 24.0}, {"id": "n", "name": "Nakarat", "start": 24.0, "end": 40.0}]
    anc = [{"line": 2, "t": 20.0, "text": "uc"}]
    for st in (None, 0, 6.5, "3.25", -1, True):
        c.append(["BeatLyrics", "line_times", [LYR, [], 120, 1, None, 4, st]])
        c.append(["BeatLyrics", "line_times", [LYR, secs, 120, 1, anc, 4, st]])
        c.append(["BeatLyrics", "line_times", ["duz satir\nikinci", secs, 95, 2, None, 4, st]])
        c.append(["BeatLyrics", "lyric_start", [st]])
    return c


def test_js_python_equivalence_r123(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node yok")
    from app.core import beat_clips as bc
    from app.core import beat_lyrics as bl
    from app.core import beat_transport as bt
    mods = {"BeatClips": bc, "BeatTransport": bt, "BeatLyrics": bl}
    cases = _cases()
    runner = tmp_path / "run.js"
    runner.write_text(_NODE_RUNNER, encoding="utf-8")
    web = ROOT / "app/ui/web"
    p = subprocess.run([node, str(runner), str(web / "beat-clips.js"), str(web / "beat-transport.js"), str(web / "beat-lyrics.js")],
                       input=json.dumps(cases), capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    js_out = json.loads(p.stdout)
    py_out = json.loads(json.dumps([getattr(mods[m], fn)(*args) for m, fn, args in cases]))
    for (m, fn, args), a, b in zip(cases, py_out, js_out):
        assert a == b, f"{m}.{fn}{tuple(args)}: py={a} js={b}"


def test_r123_ui_js_syntax_and_ids():
    node = shutil.which("node")
    if not node:
        pytest.skip("node yok")
    for name in ("beat-clips.js", "beat-transport.js", "beat-lyrics.js", "beat-timeline.js", "beat.js"):
        p = subprocess.run([node, "--check", str(ROOT / "app/ui/web" / name)], capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, f"{name}: {p.stderr}"
    html = (ROOT / "app/ui/web/beat.html").read_text(encoding="utf-8")
    for el_id in ("tlSnap", "latInput", "latMinus10", "latPlus10", "latEar", "latSource", "earBar", "lyrFind", "prStartHint"):
        assert f'id="{el_id}"' in html, el_id
    assert 'value="auto"' in html and 'value="32"' in html


def test_api_r123_methods():
    from app.ui.api import Api
    for name in ("beat_latency_get", "beat_latency_set", "beat_latency_probe", "beat_latency_listen_start",
                 "beat_latency_listen_stop", "beat_find_lyric_start"):
        assert hasattr(Api, name), name
    assert "beat_find_lyric_start" in Api.JOB_METHODS
