"""Kami Beat Asama 1c: bolum haritasi, soz paneli + teleprompter, mikrofon asistani, mikrofon yeri (yankililik)."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SR = 22050
BPM = 120.0
BAR = 2.0          # 120 BPM, 4/4


def _synth_beat(plan, seed: int = 1):
    """Farkli enerjili bloklar: ('intro'|'verse'|'chorus', bar sayisi). Verse/chorus tini ve enerjisi farkli."""
    import numpy as np
    rng = np.random.default_rng(seed)
    out = []
    for kind, nbars in plan:
        n = int(nbars * BAR * SR)
        t = np.arange(n) / SR
        if kind == "intro":
            x = 0.02 * np.sin(2 * np.pi * 220 * t)
        elif kind == "verse":
            x = 0.25 * (0.6 * np.sin(2 * np.pi * 110 * t) + 0.3 * rng.standard_normal(n) * (np.mod(t, 0.5) < 0.05))
        else:
            x = 0.7 * (0.5 * np.sin(2 * np.pi * 220 * t) + 0.3 * np.sin(2 * np.pi * 440 * t)
                       + 0.4 * rng.standard_normal(n) * (np.mod(t, 0.25) < 0.06))
        out.append(x.astype("float32"))
    return np.concatenate(out)


PLAN = [("intro", 4), ("verse", 8), ("chorus", 8), ("verse", 8), ("chorus", 8), ("intro", 4)]
EXPECT = [(0, 4, "Intro"), (4, 12, "Verse"), (12, 20, "Nakarat"), (20, 28, "Verse"), (28, 36, "Nakarat"), (36, 40, "Outro")]


@pytest.fixture()
def bs(tmp_path, monkeypatch):
    from app.core import beat_studio
    monkeypatch.setattr(beat_studio, "projects_dir", lambda: (tmp_path / "proj").mkdir(exist_ok=True) or tmp_path / "proj")
    monkeypatch.setattr(beat_studio, "recordings_dir", lambda: (tmp_path / "rec").mkdir(exist_ok=True) or tmp_path / "rec")
    return beat_studio


def _check_sections(secs, offset_bars: float = 0.0):
    assert len(secs) == len(EXPECT), [(s["name"], s["start"] / BAR, s["end"] / BAR) for s in secs]
    for s, (a, b, name) in zip(secs, EXPECT):
        assert abs(s["start"] / BAR - (a + offset_bars)) <= 1.0, (s, a)
        assert abs(s["end"] / BAR - (b + offset_bars)) <= 1.0, (s, b)
        assert s["name"].startswith(name), (s["name"], name)
        # bar izgarasina oturmus
        assert abs(s["start"] / BAR - round(s["start"] / BAR)) < 1e-6
        assert abs(s["end"] / BAR - round(s["end"] / BAR)) < 1e-6
        assert s["id"] and s["end"] > s["start"]
    for x, y in zip(secs, secs[1:]):
        assert x["end"] == y["start"]


# ---------------- 1. bolum haritasi ----------------
def test_sections_fallback_numpy():
    from app.core import beat_sections as bsx
    r = bsx.detect_sections(_synth_beat(PLAN), SR, BPM, use_librosa=False)
    assert r["ok"] and r["engine"] == "numpy" and r["bars"] == 40
    _check_sections(r["sections"])
    names = [s["name"] for s in r["sections"]]
    assert names[1] == "Verse 1" and names[3] == "Verse 2"


def test_sections_offset_rounds_to_timeline_grid():
    """Beat klibi zaman cizelgesinde 4 sn (2 bar) sonra basliyorsa bolumler de 2 bar kayar, izgarada kalir."""
    from app.core import beat_sections as bsx
    r = bsx.detect_sections(_synth_beat(PLAN), SR, BPM, offset=4.0, use_librosa=False)
    _check_sections(r["sections"], offset_bars=2.0)


def test_sections_librosa_path_if_available():
    from app.core import beat_sections as bsx
    if not bsx.has_librosa():
        pytest.skip("librosa yok (yedek yol yukarida test edildi)")
    r = bsx.detect_sections(_synth_beat(PLAN), SR, BPM, use_librosa=True)
    assert r["ok"] and r["engine"] == "librosa"
    _check_sections(r["sections"])


def test_label_rules():
    from app.core import beat_sections as bsx
    # tekrar yok: en yuksek enerji Nakarat; ilk/son dusuk = Intro/Outro; ortadaki tekil = Verse (nakarat tek)
    assert bsx.label_segments([-40, -20, -10, -40], [0, 1, 2, 3]) == ["Intro", "Verse", "Nakarat", "Outro"]
    # iki nakarat arasindaki tekil bolum = Kopru
    labels = bsx.label_segments([-12, -10, -15, -10], [0, 1, 2, 1])
    assert labels == ["Verse", "Nakarat", "Köprü", "Nakarat"]
    assert bsx.label_segments([], []) == []


def test_sections_too_short():
    import numpy as np
    from app.core import beat_sections as bsx
    assert not bsx.detect_sections(np.zeros(100, dtype="float32"), SR, BPM)["ok"]
    r = bsx.detect_sections(_synth_beat([("verse", 3)]), SR, BPM, use_librosa=False)
    assert r["ok"] and len(r["sections"]) == 1     # bolunemeyecek kadar kisa: tek bolum


def test_analyze_project_uses_beat_clip(bs, tmp_path, monkeypatch):
    import numpy as np
    from app.core import beat_sections as bsx
    from app.core import kami_beat
    if not kami_beat._find_ffmpeg() and not _has_sf():
        pytest.skip("ses yazici yok")
    x = _synth_beat(PLAN)
    wav = tmp_path / "beat.wav"
    bs._write_wav_np(str(wav), np.stack([x, x], axis=1), SR)
    monkeypatch.setattr(kami_beat, "analyze_bpm", lambda p, ffmpeg="": 120.0)
    monkeypatch.setattr(kami_beat, "detect_key", lambda p, ffmpeg="": {"key": "Am", "camelot": "8A"})
    pr = bs.create_project("Bolum testi")["project"]
    r = bs.add_take_to_track(pr["id"], "beat", str(wav))
    assert r["ok"]
    res = bsx.analyze_project(pr["id"])
    assert res["ok"], res
    assert res["bpm"] == 120.0 and res["key"] == "Am"
    _check_sections(res["sections"])
    assert bsx.get_progress()["running"] is False
    # projeye yazmaz (arayuz geri alinabilir adim olarak uygular)
    assert bs.load_project(pr["id"])["project"]["sections"] == []
    # klip zaman cizelgesinde 2 bar ileride ve basindan 4 bar (intro) kirpilmis: kesit + konum dikkate alinir
    proj = bs.load_project(pr["id"])["project"]
    beat = next(t for t in proj["tracks"] if t["role"] == "beat")
    beat["clips"][0].update({"start": 4.0, "src_in": 8.0})
    bs.save_project(proj)
    res2 = bsx.analyze_project(pr["id"])
    assert res2["ok"]
    got = [(round(s["start"] / BAR), round(s["end"] / BAR), s["name"].split()[0]) for s in res2["sections"]]
    assert [g[2] for g in got] == ["Verse", "Nakarat", "Verse", "Nakarat", "Outro"], got
    assert [g[0] for g in got] == [2, 10, 18, 26, 34] and got[-1][1] == 38, got


def _has_sf() -> bool:
    try:
        import soundfile  # noqa: F401
        return True
    except Exception:
        return False


def test_project_model_sections_lyric_times_roundtrip(bs):
    pr = bs.create_project("Model")["project"]
    assert pr["sections"] == [] and pr["lyric_times"] == {"bars_per_line": 1, "anchors": []}
    pr["sections"] = [{"id": "s1", "name": "Nakarat", "start": 8.0, "end": 24.0, "bars_per_line": 2}]
    pr["lyric_times"] = {"bars_per_line": 1, "anchors": [{"line": 3, "t": 12.5, "text": "x"}]}
    bs.save_project(pr)
    back = bs.load_project(pr["id"])["project"]
    assert back["sections"] == pr["sections"] and back["lyric_times"] == pr["lyric_times"]
    # eski proje (alanlar yok) -> goc varsayilan ekler, idempotent
    old = dict(back)
    old.pop("sections"); old.pop("lyric_times")
    assert bs.migrate_project(old) is True
    assert old["sections"] == [] and old["lyric_times"]["anchors"] == []
    assert bs.migrate_project(old) is False


# ---------------- 2. soz paneli + teleprompter ----------------
LYR = """Bastaki satir
[Nakarat]
gece coker sehrin ustune
sokak lambalari sahit sozume

[Verse 2: Metehan]
bir iki uc
dort bes alti
[Kopru]
tek satir"""

SECS = [
    {"id": "a", "name": "Intro", "start": 0.0, "end": 8.0},
    {"id": "b", "name": "Verse 1", "start": 8.0, "end": 24.0},
    {"id": "c", "name": "Nakarat", "start": 24.0, "end": 40.0},
    {"id": "d", "name": "Verse 2", "start": 40.0, "end": 56.0, "bars_per_line": 2},
    {"id": "e", "name": "Köprü", "start": 56.0, "end": 64.0},
]


def test_header_parsing():
    from app.core import beat_lyrics as bl
    assert bl.header_name("[Nakarat]") == "Nakarat"
    assert bl.header_name("  [ Verse 2: Metehan ] ") == "Verse 2"
    assert bl.header_name("Nakarat") == "" and bl.header_name("[a] b") == ""
    assert bl.section_base("NAKARAT 2") == "nakarat" and bl.section_base("Chorus") == "nakarat"
    assert bl.section_base("Kıta 1") == "verse" and bl.section_base("Bridge") == "köprü"
    assert bl.section_base("İNTRO") == "intro" and bl.section_base("Kopru") == "köprü"
    p = bl.parse_lyrics(LYR)
    assert p["count"] == 6
    assert [b["header"] for b in p["blocks"]] == ["", "Nakarat", "Verse 2", "Kopru"]
    assert [b["lines"] for b in p["blocks"]] == [[0], [1, 2], [3, 4], [5]]
    kinds = [x["kind"] for x in p["lines"]]
    assert kinds.count("header") == 3 and kinds.count("blank") == 1


def test_block_assignment_by_header_name():
    from app.core import beat_lyrics as bl
    p = bl.parse_lyrics(LYR)
    # basliksiz ilk blok Intro'yu atlar -> Verse 1; [Nakarat] -> Nakarat; [Verse 2] -> Verse 2; [Kopru] -> Kopru
    assert bl.assign_blocks(p["blocks"], SECS) == [1, 2, 3, 4]
    # eslesen ad yoksa siradaki bolum; bolumler biterse -1
    p2 = bl.parse_lyrics("[Nakarat]\na\n[Bilinmeyen]\nb\n[Nakarat]\nc")
    assert bl.assign_blocks(p2["blocks"], SECS[:3]) == [2, -1, -1]
    assert bl.assign_blocks(p2["blocks"], []) == [-1, -1, -1]


def test_line_times_bars_per_line_and_sections():
    from app.core import beat_lyrics as bl
    tm = bl.line_times(LYR, SECS, 120, 1)
    ts = [x["t"] for x in tm]
    # Verse 1 @8: 1 satir; Nakarat @24: 1 bar/satir; Verse 2 @40: bolum 2 bar/satir; Kopru @56
    assert ts == [8.0, 24.0, 26.0, 40.0, 44.0, 56.0]
    assert [x["section"] for x in tm] == [1, 2, 2, 3, 3, 4]
    tm2 = bl.line_times(LYR, SECS, 120, 2)              # genel 2 bar/satir (Verse 2 zaten 2)
    assert [x["t"] for x in tm2] == [8.0, 24.0, 28.0, 40.0, 44.0, 56.0]
    # bolum yoksa satirlar 0'dan akar
    assert [x["t"] for x in bl.line_times("a\nb\n[Nakarat]\nc", [], 120, 1)] == [0.0, 2.0, 4.0]


def test_manual_sync_shifts_following_lines_in_block():
    from app.core import beat_lyrics as bl
    texts = ["gece coker sehrin ustune"]
    anc = bl.sync_line([], 1, 25.0, texts[0])
    tm = bl.line_times(LYR, SECS, 120, 1, anc)
    ts = {x["n"]: x["t"] for x in tm}
    assert ts[1] == 25.0 and ts[2] == 27.0                 # sonraki satir 1 sn kaydi
    assert ts[3] == 40.0                                    # sonraki blok kendi bolumunde
    assert [x["anchored"] for x in tm] == [False, True, False, False, False, False]
    # ayni satiri yeniden sabitleme eskiyi degistirir; kaldirma geri getirir
    anc2 = bl.sync_line(anc, 1, 24.5, texts[0])
    assert len(anc2) == 1 and anc2[0]["t"] == 24.5
    assert bl.line_times(LYR, SECS, 120, 1, bl.unsync_line(anc2, 1))[1]["t"] == 24.0
    # satir eklenince capa metniyle dogru satiri bulur
    lyr2 = LYR.replace("[Nakarat]\n", "[Nakarat]\nyeni ilk satir\n")
    ts2 = {x["n"]: x["t"] for x in bl.line_times(lyr2, SECS, 120, 1, anc)}
    assert ts2[2] == 25.0 and ts2[1] == 24.0
    # aktif satir
    assert bl.active_line(tm, 26.9) == 1 and bl.active_line(tm, 27.0) == 2 and bl.active_line(tm, 1.0) == -1


def test_rhyme_color_grouping_skips_headers(bs):
    lyr = "[Nakarat]\nsehrin ustune\nsahit sozune\nbir yol\n[Verse]\nkapat gozune\nyine bir yol"
    r = bs.analyze_lyrics_bars(lyr, 120)
    lines = r["lines"]
    heads = [x for x in lines if x["kind"] == "header"]
    assert [x["header"] for x in heads] == ["Nakarat", "Verse"]
    assert all(x["syllables"] == 0 and x["color"] == -1 for x in heads)
    by = {x["text"]: x for x in lines}
    assert by["sehrin ustune"]["color"] == by["sahit sozune"]["color"] == by["kapat gozune"]["color"] >= 0
    assert by["bir yol"]["color"] == by["yine bir yol"]["color"] >= 0
    assert by["bir yol"]["color"] != by["sehrin ustune"]["color"]
    assert 0 <= max(x["color"] for x in lines) < bs.RHYME_PALETTE_SIZE
    assert [x["n"] for x in lines if x["kind"] == "line"] == [0, 1, 2, 3, 4]
    assert r["total_lines"] == 5


# ---------------- 3-4. mikrofon asistani + yer asistani ----------------
def _noise(n, db, seed=0):
    import numpy as np
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(n)
    return x / np.sqrt(np.mean(x * x)) * 10 ** (db / 20.0)


def test_mic_metrics_noise_peak_snr():
    import numpy as np
    from app.core import beat_mic as bm
    sr = 16000
    noise = _noise(5 * sr, -65.0)
    t = np.arange(5 * sr) / sr
    speech = 0.25 * np.sin(2 * np.pi * 220 * t) + _noise(len(t), -65.0, 1)   # tepe ~ -12 dBFS, RMS ~ -15
    m = bm.mic_metrics(noise, speech, sr)
    assert abs(m["noise_db"] - (-65.0)) < 0.5
    assert abs(m["peak_db"] - 20 * np.log10(0.25)) < 0.3
    assert abs(m["avg_db"] - 20 * np.log10(0.25 / np.sqrt(2))) < 0.5
    assert abs(m["snr_db"] - (m["avg_db"] - m["noise_db"])) < 1e-9 and m["snr_db"] > 45
    assert m["noise_rating"] == "iyi" and m["level_rating"] == "iyi" and not m["clipping"]
    # patlama + gurultulu oda
    loud = np.clip(1.2 * np.sin(2 * np.pi * 220 * t), -1, 1)
    m2 = bm.mic_metrics(_noise(5 * sr, -45.0), loud, sr)
    assert m2["clipping"] and m2["level_rating"] == "patlıyor" and m2["noise_rating"] == "kötü"
    assert any("kazancı düşür" in x for x in m2["tips"])
    # cok kisik
    m3 = bm.mic_metrics(_noise(5 * sr, -55.0), 0.03 * np.sin(2 * np.pi * 220 * t), sr)
    assert m3["too_quiet"] and m3["noise_rating"] == "orta" and any("yaklaş" in x for x in m3["tips"])


def _speechy(sr, secs=5.0, seed=3):
    """Hece benzeri genis bantli patlamalar (120 ms, 240 ms aralik, hizli birakma)."""
    import numpy as np
    rng = np.random.default_rng(seed)
    n = int(secs * sr)
    env = np.zeros(n)
    for k in range(int((secs - 0.3) / 0.24)):
        s, L, r = int((0.1 + k * 0.24) * sr), int(0.12 * sr), int(0.01 * sr)
        w = np.ones(L)
        w[:r] = np.linspace(0, 1, r)
        w[-r:] = np.linspace(1, 0, r)
        env[s:s + L] += w * (0.3 + 0.2 * rng.random())
    return rng.standard_normal(n) * 0.35 * env


def _reverb(x, sr, rt60, seed=7):
    import numpy as np
    rng = np.random.default_rng(seed)
    L = int(rt60 * 1.2 * sr)
    ir = rng.standard_normal(L) * np.exp(-6.91 * np.arange(L) / (rt60 * sr))
    ir[0] = 1.0
    ir /= np.sqrt(np.sum(ir ** 2))
    return np.convolve(x, ir)[: len(x)]


def test_reverb_score_dry_less_than_reverberant():
    from app.core import beat_mic as bm
    sr = 16000
    dry = _speechy(sr) + _noise(5 * sr, -80.0, 9)
    wet = _reverb(_speechy(sr), sr, 0.8) + _noise(5 * sr, -80.0, 9)
    a = bm.reverb_estimate(dry, sr, -80.0)
    b = bm.reverb_estimate(wet, sr, -80.0)
    assert a["ok"] and b["ok"]
    assert a["rt60"] < b["rt60"] and a["score"] < b["score"]
    assert a["label"] == "kuru" and b["label"] in ("orta", "yankılı")
    adv_dry = bm.placement_advice({"noise_rating": "iyi"}, a)
    adv_wet = bm.placement_advice({"noise_rating": "iyi"}, b)
    assert any("30-60 cm" in x for x in adv_dry) and any("pop filtresi" in x for x in adv_dry)
    if b["label"] == "yankılı":
        assert any("Aşama 2" in x for x in adv_wet) and any("yorgan" in x for x in adv_wet)
    # sinyal yoksa tahmin yok
    assert not bm.reverb_estimate(_noise(sr, -70.0), sr, -70.0)["ok"]


def test_analyze_test_splits_noise_and_speech():
    import numpy as np
    from app.core import beat_mic as bm
    sr = 16000
    rec = np.concatenate([_noise(5 * sr, -62.0), _speechy(sr) + _noise(5 * sr, -62.0, 2)])
    r = bm.analyze_test(rec, sr, 5.0)
    assert r["ok"] and abs(r["metrics"]["noise_db"] - (-62.0)) < 1.0
    assert r["metrics"]["snr_db"] > 30 and r["reverb"]["ok"] and r["placement"]
    assert not bm.analyze_test(rec[: 5 * sr], sr, 5.0)["ok"]


# ---------------- JS <-> Python esdegerligi + sozdizimi ----------------
_NODE_RUNNER = r"""
global.window = {};
require(process.argv[2]);
const cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const out = cases.map(([fn, args]) => window.BeatLyrics[fn](...args));
process.stdout.write(JSON.stringify(out));
"""


def _cases():
    from app.core import beat_lyrics as bl
    anc = bl.sync_line([], 1, 25.0, "gece coker sehrin ustune")
    lyr2 = LYR.replace("[Nakarat]\n", "[Nakarat]\nyeni ilk satir\n")
    cases = [
        ["header_name", ["[Nakarat]"]], ["header_name", ["  [ Verse 2: Metehan ] "]], ["header_name", ["x"]], ["header_name", ["[]"]],
        ["section_base", ["NAKARAT 2"]], ["section_base", ["İntro"]], ["section_base", ["Kıta #3"]], ["section_base", ["Hook"]],
        ["section_base", ["Pre-Chorus"]], ["tr_lower", ["IŞIK İÇİN"]],
        ["parse_lyrics", [LYR]], ["parse_lyrics", [""]], ["parse_lyrics", ["\n\n[A]\n\nx\r\ny"]],
        ["assign_blocks", [bl.parse_lyrics(LYR)["blocks"], SECS]],
        ["line_times", [LYR, SECS, 120, 1]], ["line_times", [LYR, SECS, 93.5, 2, anc]], ["line_times", [lyr2, SECS, 120, 1, anc]],
        ["line_times", ["a\nb\nc", [], 0, 0]], ["line_times", [LYR, SECS[:2], 140, 1.5, [{"line": 4, "t": 50.3, "text": "zzz"}]]],
        ["sync_line", [anc, 3, 41.234567891, "bir iki uc"]], ["sync_line", [[], 0, -3, ""]], ["unsync_line", [anc, 1]],
        ["resolve_anchors", [[{"line": 9, "t": 3.0, "text": "b"}, {"line": 0, "t": -1}], ["a", "b", "c"]]],
        ["active_line", [bl.line_times(LYR, SECS, 120, 1), 26.0]], ["active_line", [[], 3.0]],
    ]
    return cases


def test_js_python_equivalence_1c(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node yok")
    from app.core import beat_lyrics as bl
    cases = _cases()
    runner = tmp_path / "run.js"
    runner.write_text(_NODE_RUNNER, encoding="utf-8")
    p = subprocess.run([node, str(runner), str(ROOT / "app/ui/web/beat-lyrics.js")],
                       input=json.dumps(cases), capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    js_out = json.loads(p.stdout)
    py_out = json.loads(json.dumps([getattr(bl, fn)(*args) for fn, args in cases]))
    for (fn, args), a, b in zip(cases, py_out, js_out):
        assert a == b, f"{fn}{tuple(args)[:2]}: py={a} js={b}"


def test_beat_1c_ui_js_syntax():
    node = shutil.which("node")
    if not node:
        pytest.skip("node yok")
    for name in ("beat-clips.js", "beat-transport.js", "beat-lyrics.js", "beat-timeline.js", "beat.js"):
        p = subprocess.run([node, "--check", str(ROOT / "app/ui/web" / name)], capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, f"{name}: {p.stderr}"
    html = (ROOT / "app/ui/web/beat.html").read_text(encoding="utf-8")
    assert html.index("beat-lyrics.js") < html.index("beat-timeline.js") < html.index('src="beat.js"')
    for el_id in ("tlSections", "secAnalyze", "prompter", "micTestBtn", "micCard", "lyrBpl"):
        assert f'id="{el_id}"' in html, el_id


def test_api_jobs_registered():
    from app.ui.api import Api
    for name in ("beat_analyze_sections", "beat_mic_test"):
        assert name in Api.JOB_METHODS and hasattr(Api, name)
    assert hasattr(Api, "beat_analysis_progress") and hasattr(Api, "beat_mic_test_status")
