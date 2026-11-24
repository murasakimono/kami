"""Kami Beat Asama 2b: otomatik temizlik (gurultu SNR artisi, nefes tespiti + kisma, de-click), yikici olmayan
temizlik dosyasi (onbellek anahtari, ham dosya hash'i degismez, render temiz dosyayi okur), vokale yer acma
(vokal varken beat 1-4 kHz bandi duser, yokken birebir ayni), otomasyon enterpolasyonu (render zarfi = JS hesap),
send/bus toplama + bus fx sirasi (mock pedalboard), tarz onayari -> send, onizleme = bounce, arayuz baglantilari."""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import sys
import types
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SR = 48000
WEB = ROOT / "app" / "ui" / "web"
RNG = np.random.default_rng(2026)


def db(d):
    return 10 ** (d / 20.0)


@pytest.fixture()
def bs(tmp_path, monkeypatch):
    from app.core import beat_fx, beat_studio, beat_style
    monkeypatch.setattr(beat_studio, "projects_dir", lambda: (tmp_path / "proj").mkdir(exist_ok=True) or tmp_path / "proj")
    monkeypatch.setattr(beat_studio, "recordings_dir", lambda: (tmp_path / "rec").mkdir(exist_ok=True) or tmp_path / "rec")
    monkeypatch.setattr(beat_studio, "_GLOBAL_LATENCY_GETTER", None)
    monkeypatch.setattr(beat_studio, "_PREVIEW_SRC", {})
    monkeypatch.setattr(beat_style, "settings_dir", lambda: (tmp_path / "set").mkdir(exist_ok=True) or tmp_path / "set")
    monkeypatch.setattr(beat_fx, "_PB_OVERRIDE", False)          # bu ortamda pedalboard yok: numpy yedegi
    yield beat_studio
    monkeypatch.setattr(beat_fx, "_PB_OVERRIDE", None)


@pytest.fixture()
def bc():
    from app.core import beat_clean
    return beat_clean


@pytest.fixture()
def mb():
    from app.core import beat_mixbus
    return beat_mixbus


def _clip(cid, path, start, src_in, src_out, **kw):
    c = {"id": cid, "take_id": "t", "path": path, "start": start, "src_in": src_in, "src_out": src_out,
         "gain_db": 0.0, "fade_in": 0.0, "fade_out": 0.0, "muted": False}
    c.update(kw)
    return c


def _track(tid, role, clips, **kw):
    t = {"id": tid, "name": tid, "role": role, "volume_db": 0.0, "pan": 0.0, "mute": False, "solo": False,
         "clips": clips, "fx": [], "denoise": False}
    t.update(kw)
    return t


def _st(x):
    x = np.asarray(x, dtype="float32")
    return np.stack([x, x], axis=1)


def _voiced(n, rms, f0=180.0):
    t = np.arange(n) / SR
    y = sum((1.0 / k) * np.sin(2 * np.pi * f0 * k * t) for k in range(1, 11))
    return (y / np.sqrt(np.mean(y ** 2)) * rms).astype("float32")


def _bandnoise(n, lo, hi, rms):
    x = RNG.standard_normal(n)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1.0 / SR)
    X[(f < lo) | (f > hi)] = 0
    y = np.fft.irfft(X, n)
    return (y / np.sqrt(np.mean(y ** 2)) * rms).astype("float32")


def _write(bs, path, data):
    bs._write_wav_np(str(path), data, SR)
    return str(path)


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# ---------------- 1a. gurultu ----------------
def _speechlike(sec=4.0):
    t = np.arange(int(sec * SR)) / SR
    sp = sum((1.0 / k) * np.sin(2 * np.pi * 150 * k * t) for k in range(1, 12))
    env = (0.5 + 0.5 * np.sin(2 * np.pi * 3 * t)) ** 2
    env[(t > 1.5) & (t < 2.5)] = 0                     # konusma arasi: gurultu profili buradan
    return (0.1 * sp * env).astype("float32"), t


def test_noise_profile_finds_quietest_second(bc):
    clean, t = _speechlike()
    x = _st(clean + RNG.standard_normal(len(t)).astype("float32") * 0.01)
    p = bc.noise_profile(x)
    assert 1.45 <= p["t0"] and p["t1"] <= 2.55 and 0.5 <= p["t1"] - p["t0"] <= 1.0
    assert -43 < p["floor_db"] < -37                   # beyaz gurultu 0.01 rms = -40 dBFS


def test_denoise_raises_snr(bc):
    clean, t = _speechlike()
    noisy = clean + RNG.standard_normal(len(t)).astype("float32") * 0.01
    x = _st(noisy)

    def snr(o):
        return 10 * np.log10(np.sum(clean ** 2) / np.sum((o[:, 0] - clean) ** 2))

    out, info = bc.denoise(x, SR, 60.0, "auto")
    assert info["method"] == "numpy" and out.shape == x.shape
    assert snr(out) > snr(x) + 8.0                     # ~12 dB -> ~23 dB
    gap = (t > 1.6) & (t < 2.4)
    assert 20 * np.log10(np.sqrt(np.mean(out[gap, 0] ** 2))) < -52   # konusma arasi gurultu belirgin azaldi
    # strength 0 bile en az 6 dB taban; siddet arttikca bosluk daha sessiz
    lo, _ = bc.denoise(x, SR, 0.0)
    hi, _ = bc.denoise(x, SR, 100.0)
    assert np.mean(hi[gap] ** 2) < np.mean(lo[gap] ** 2) < np.mean(x[gap] ** 2)


def test_stft_identity_when_mask_is_one(bc):
    x = RNG.standard_normal((SR, 2)).astype("float32") * 0.2
    y = bc.stft_process(x, lambda m, c: np.ones_like(m))
    assert np.max(np.abs(x - y)) < 1e-5
    # mutlak izgara: pencereli islem tam islemin ayni bolumunu verir
    mask = lambda m, c: 0.5 + 0.4 * np.sin(np.asarray(c)[None, :] / 3000.0) * np.ones_like(m)
    full = bc.stft_process(x, mask)
    part = bc.stft_process(x[12000:], mask, abs_start=12000)
    assert np.max(np.abs(full[12000 + 4096:] - part[4096:])) < 1e-5


def test_advanced_method_falls_back_gracefully(bc, monkeypatch):
    clean, t = _speechlike(2.0)
    x = _st(clean + RNG.standard_normal(len(t)).astype("float32") * 0.01)
    monkeypatch.setattr(bc, "advanced_available", lambda: False)
    out, info = bc.denoise(x, SR, 50.0, "advanced")
    assert info["method"] == "numpy" and "kurulu değil" in info["note"]


def test_advanced_wrapper_with_mock_module(bc, monkeypatch):
    calls = []
    torch = types.ModuleType("torch")
    torch.from_numpy = lambda a: a
    torch.cuda = types.SimpleNamespace(is_available=lambda: False)
    inf = types.ModuleType("resemble_enhance.enhancer.inference")

    def fake_denoise(w, sr, dev):
        calls.append((len(w), sr, dev))
        return np.asarray(w) * 0.5, sr
    inf.denoise = fake_denoise
    for name, mod in {"torch": torch, "resemble_enhance": types.ModuleType("resemble_enhance"),
                      "resemble_enhance.enhancer": types.ModuleType("resemble_enhance.enhancer"),
                      "resemble_enhance.enhancer.inference": inf}.items():
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.setattr(bc, "advanced_available", lambda: True)
    x = _st(np.ones(1000, dtype="float32") * 0.4)
    out, info = bc.denoise(x, SR, 50.0, "advanced")
    assert info["method"] == "advanced" and calls == [(1000, SR, "cpu"), (1000, SR, "cpu")]
    assert np.allclose(out, 0.2)


def test_model_install_requires_explicit_button(bc, monkeypatch, tmp_path):
    from app.core import beat_style
    monkeypatch.setattr(beat_style, "settings_dir", lambda: tmp_path)
    monkeypatch.setattr(bc, "advanced_available", lambda: False)
    ran = []

    class FakeProc:
        def __init__(self, cmd, **kw):
            ran.append(cmd)
            self.stdout = ["Collecting resemble-enhance", "Downloading x.whl", "Successfully installed"]

        def wait(self):
            return 0
    r = bc.install_model(False, runner=FakeProc)
    assert r["ok"] is False and r["error"] == "confirm_required" and not ran
    info = r["info"]
    assert info["license"] == "MIT" and info["size_mb"] > 100 and "huggingface" in info["source"]
    r = bc.install_model(True, runner=FakeProc)
    assert ran and ran[0][1:4] == ["-m", "pip", "install"] and "--target" in ran[0] and "resemble-enhance" in ran[0]
    assert str(tmp_path) in ran[0][ran[0].index("--target") + 1]
    assert r["ok"] is False and bc._INSTALL["state"] == "error"      # sahte kurulum modulu getirmedi


# ---------------- 1b. nefes ----------------
def _breath_take():
    parts, truth = [], []
    floor = lambda n: RNG.standard_normal(n) * db(-62)
    pos = 0

    def add(x):
        nonlocal pos
        parts.append(np.asarray(x, dtype="float64"))
        pos += len(x)
    add(floor(int(0.8 * SR)))
    for _ in range(3):
        b0 = pos / SR
        n = int(0.3 * SR)
        add(_bandnoise(n, 400, 10000, db(-34)) + floor(n))
        truth.append((b0, pos / SR))
        add(floor(int(0.12 * SR)))
        n = int(0.9 * SR)
        add(_voiced(n, db(-14)) + floor(n))
        add(floor(int(0.5 * SR)))
    tone0 = pos / SR                                   # tuzak: ayni seviyede ama tonal (nefes degil)
    add(_voiced(int(0.3 * SR), db(-34), f0=300))
    add(floor(int(0.15 * SR)))
    add(_voiced(int(0.8 * SR), db(-14)))
    add(floor(int(0.5 * SR)))
    return _st(np.concatenate(parts)), truth, tone0


def test_breath_detection_accuracy(bc):
    x, truth, tone0 = _breath_take()
    regs = bc.detect_breaths(x)
    assert len(regs) == 3
    for (a, b, on), (ta, tb) in zip(regs, truth):
        assert on is True and abs(a - ta) < 0.05 and abs(b - tb) < 0.05
    assert not any(a <= tone0 + 0.3 and b >= tone0 for a, b, _ in regs)     # tonal parca nefes sayilmadi


def test_breath_gain_reduces_not_deletes(bc):
    n = SR
    sig = _st(RNG.standard_normal(n).astype("float32") * 0.1)
    regs = [[0.3, 0.6, True], [0.7, 0.8, False]]
    g = bc.breath_gain(n, SR, regs, -12.0)
    out = sig * g[:, None]
    mid = slice(int(0.32 * SR), int(0.58 * SR))
    ratio = 20 * np.log10(np.sqrt(np.mean(out[mid] ** 2)) / np.sqrt(np.mean(sig[mid] ** 2)))
    assert abs(ratio + 12.0) < 0.2                     # -12 dB kisildi (silinmedi)
    assert np.array_equal(out[:int(0.29 * SR)], sig[:int(0.29 * SR)])
    assert np.array_equal(out[int(0.7 * SR):], sig[int(0.7 * SR):])          # kapali bolgeye dokunulmadi
    gr = bc.breath_gain(n, SR, regs, -12.0, remove=True)
    assert np.max(np.abs(gr[mid])) == 0.0              # "tamamen sil"
    assert np.all(np.diff(g[int(0.29 * SR):int(0.32 * SR)]) <= 0)        # 10 ms rampa (tik yok)


# ---------------- 1c. de-click ----------------
def test_declick_removes_clicks_keeps_rest(bc):
    t = np.arange(2 * SR) / SR
    clean = (0.3 * np.sin(2 * np.pi * 220 * t) + RNG.standard_normal(len(t)) * 0.001).astype("float32")
    x = clean.copy()
    x[10000] += 0.6
    x[30000] -= 0.5
    x[50000:50003] += np.array([0.3, -0.4, 0.2], dtype="float32")
    x[70000:70144] += (RNG.standard_normal(144) * 0.3).astype("float32")      # 3 ms "smack"
    X = _st(x)
    ev = bc.detect_clicks(X)
    assert len(ev) == 4
    for (a, b), p in zip(ev, (10000, 30000, 50000, 70000)):
        assert a <= p < b and (b - a) <= int(0.010 * SR) + 6
    out = bc.declick(X, events=ev)
    keep = np.ones(len(x), bool)
    for a, b in ev:
        keep[a:b] = False
    assert np.array_equal(out[keep], X[keep])          # tiklarin disi birebir ayni
    for a, b in ev[:3]:                                # kisa tiklar: neredeyse temiz sinyale doner
        assert np.max(np.abs(out[a:b, 0] - clean[a:b])) < 0.1
    a, b = ev[3]                                       # 3 ms smack: enterpolasyon hatasi tikin cok altinda
    err = np.sqrt(np.mean((out[a:b, 0] - clean[a:b]) ** 2))
    assert err < 0.5 * np.sqrt(np.mean((x[a:b] - clean[a:b]) ** 2))
    assert bc.detect_clicks(_st(clean)) == []          # temiz sinyalde yanlis alarm yok
    # 10 ms'den uzun gecici olay tik sayilmaz
    y = clean.copy()
    y[40000:40000 + int(0.03 * SR)] += 0.4
    assert all(b - a <= int(0.010 * SR) + 6 for a, b in bc.detect_clicks(_st(y)))


# ---------------- 1d. yikici olmayan dosya + onbellek ----------------
def test_clean_file_cache_key_and_raw_untouched(bs, bc, tmp_path):
    x, truth, _ = _breath_take()
    x[30000] += 0.5
    raw = _write(bs, tmp_path / "take.wav", x)
    h0 = _sha(raw)
    an = bc.analyze(raw)
    assert an["ok"] and len(an["breath"]["regions"]) == 3 and an["click"]["count"] >= 1
    s = {"noise": an["noise"]["suggest"], "breath": dict(an["breath"]["suggest"], regions=an["breath"]["regions"]),
         "click": an["click"]["suggest"]}
    r1 = bc.apply(raw, s)
    assert r1["ok"] and not r1["cached"] and Path(r1["file"]).parent.name == "_clean"
    assert Path(r1["file"]).name == f"{bc.source_hash(raw)}_{bc.settings_hash(s)}.wav"
    assert _sha(raw) == h0                             # ham dosya degismedi
    r2 = bc.apply(raw, s)
    assert r2["cached"] and r2["file"] == r1["file"]
    # ayar degisince (bir nefes kapatildi) yeni dosya; gorsel/sirasiz alanlar anahtari degistirmez
    s2 = json.loads(json.dumps(s))
    s2["breath"]["regions"][1][2] = False
    assert bc.settings_hash(s2) != bc.settings_hash(s)
    s3 = json.loads(json.dumps(s))
    s3["breath"]["regions"] = list(reversed(s3["breath"]["regions"]))
    s3["noise"]["on"], s3["noise"]["strength"] = True, s["noise"]["strength"]
    assert bc.settings_hash(s3) == bc.settings_hash(s)
    off = {"noise": {"on": False}, "breath": {"on": False}, "click": {"on": False}}
    assert bc.apply(raw, off)["error"] == "nothing_selected"
    # temiz dosya: ayni uzunluk, 32-bit float
    a, _ = bs._read_audio_np(r1["file"], SR)
    assert len(a) == len(x)
    assert Path(r1["file"]).read_bytes()[20:22] == (3).to_bytes(2, "little")


def test_render_uses_clean_file_and_remove_restores(bs, bc, tmp_path):
    x = _st(_voiced(SR, db(-12)) + RNG.standard_normal(SR).astype("float32") * 0.01)
    raw = _write(bs, tmp_path / "v.wav", x)
    res = bc.apply(raw, {"noise": {"on": True, "strength": 70}, "breath": {"on": False}, "click": {"on": False}})
    c = _clip("c1", raw, 0.0, 0.0, 1.0)
    tr = _track("v", "vocal", [c])
    dry = bs.render_track_audio(tr, SR, {})
    c["clean"] = bc.clip_clean_field(raw, res["settings"], res)
    assert bc.source_path(c) == res["file"]
    cl = bs.render_track_audio(tr, SR, {})
    assert len(cl) == len(dry) and np.mean(cl ** 2) < np.mean(dry ** 2)
    c["clean"]["off"] = True                           # A/B: ham
    assert bc.source_path(c) == raw and np.array_equal(bs.render_track_audio(tr, SR, {}), dry)
    c["clean"].pop("off")
    c["clean"]["src"] = "/baska/dosya.wav"             # klip baska kaynaga tasindiysa eski temizlik kullanilmaz
    assert bc.source_path(c) == raw
    del c["clean"]                                     # "Temizligi kaldir"
    assert np.array_equal(bs.render_track_audio(tr, SR, {}), dry)
    # onizleme anahtari temiz dosyaya baglidir
    c2 = dict(c, clean=bc.clip_clean_field(raw, res["settings"], res))
    tr2 = _track("v", "vocal", [c2], fx=[{"type": "gain", "gain_db": -1}])
    assert bs.preview_key(tr2, 0, 1) != bs.preview_key(dict(tr2, clips=[c]), 0, 1)


# ---------------- 2. vokale yer acma ----------------
def _duck_project(bs, tmp_path, vocal=True, mode="band"):
    n = 3 * SR
    beat = _st(RNG.standard_normal(n).astype("float32") * 0.1)
    bp = _write(bs, tmp_path / "beat.wav", beat)
    v = np.zeros(n, dtype="float32")
    v[SR:2 * SR] = _voiced(SR, db(-16))
    vp = _write(bs, tmp_path / "voc.wav", _st(v))
    mr = {"on": True, "mode": mode, "center_hz": 2000, "width_oct": 2.0, "depth_db": 6.0}
    trs = [_track("beat", "beat", [_clip("b", bp, 0, 0, 3.0)], make_room=mr)]
    if vocal:
        trs.append(_track("v", "vocal", [_clip("v1", vp, 0, 0, 3.0)]))
    return {"id": "p", "bpm": 120, "tracks": trs, "buses": []}, beat


def test_make_room_dips_mid_band_only_when_vocal(bs, mb, tmp_path):
    proj, beat = _duck_project(bs, tmp_path)
    tr = proj["tracks"][0]
    data = bs.render_track_audio(tr, SR, {})
    rendered = [(data, {"offset": 0, "tr": tr}), (bs.render_track_audio(proj["tracks"][1], SR, {}), {"offset": 0, "tr": proj["tracks"][1]})]
    out = bs.apply_make_room(data, tr, rendered, SR)
    sing = slice(int(1.1 * SR), int(1.9 * SR))
    quiet = slice(int(0.1 * SR), int(0.8 * SR))
    drop = 10 * np.log10(mb.band_energy(out[sing], SR) / mb.band_energy(data[sing], SR))
    assert -6.5 < drop < -3.0                          # 1-4 kHz bandi vokal varken birkac dB geri
    lowdrop = 10 * np.log10(mb.band_energy(out[sing], SR, 60, 250) / mb.band_energy(data[sing], SR, 60, 250))
    assert lowdrop > -0.6                              # bas bolgesine dokunmaz
    assert abs(10 * np.log10(mb.band_energy(out[quiet], SR) / mb.band_energy(data[quiet], SR))) < 0.3
    # vokal hic yoksa beat birebir ayni
    proj2, _ = _duck_project(bs, tmp_path, vocal=False)
    t2 = proj2["tracks"][0]
    d2 = bs.render_track_audio(t2, SR, {})
    assert bs.apply_make_room(d2, t2, [(d2, {"offset": 0, "tr": t2})], SR) is d2
    assert mb.duck(d2, np.zeros_like(d2), SR, t2["make_room"]) is d2      # sessiz vokal -> degismez
    # wide (basit ducking): tum bant, en fazla 3 dB
    out_w = mb.duck(data, rendered[1][0], SR, dict(tr["make_room"], mode="wide"))
    dw = 10 * np.log10(np.mean(out_w[sing] ** 2) / np.mean(data[sing] ** 2))
    assert -3.2 < dw < -2.0


def test_make_room_in_mixdown_and_preview_equals_bounce(bs, mb, tmp_path):
    proj, _ = _duck_project(bs, tmp_path)
    proj["tracks"][1]["mute"] = False
    mix = bs.mix_array(proj, SR)
    # bounce'taki beat katkisi = miks - vokal katkisi
    vt = proj["tracks"][1]
    vdat = mb.apply_fader(bs.render_track_audio(vt, SR, {}), vt, SR, 0)
    beat_in_mix = mix[:len(vdat)] - vdat
    t0, t1 = 1.2, 2.4
    ctx = {"tracks": [vt], "buses": [], "bpm": 120}
    main, bus = bs.render_track_preview(proj["tracks"][0], ctx, t0, t1, SR, {})
    assert bus is None
    ref = mb.apply_fader(main, proj["tracks"][0], SR, int(t0 * SR))
    seg = beat_in_mix[int(t0 * SR):int(t0 * SR) + len(ref)]
    assert len(ref) == int(round((t1 - t0) * SR))
    assert np.max(np.abs(ref - seg)) < 2e-3
    # preview_render dosya yazar ve 'dry' degil
    r = bs.preview_render("", "beat", t0, t1 - t0, "", proj["tracks"][0], {}, SR, ctx)
    assert r["ok"] and not r.get("dry") and "bus_path" not in r
    r2 = bs.preview_render("", "beat", t0, t1 - t0, "", proj["tracks"][0], {}, SR, {"tracks": [], "buses": []})
    assert r2.get("dry")                               # vokal yoksa islenecek bir sey yok


# ---------------- 3. otomasyon ----------------
AUTO_VOL = [[0.5, -12.0], [1.0, 0.0], [1.5, 6.0], [2.5, -40.0]]
AUTO_PAN = [[0.0, -1.0], [2.0, 1.0]]


def test_automation_interpolation(mb):
    assert mb.value_at([], 1.0, 3.0) == 3.0
    assert mb.value_at(AUTO_VOL, 0.0) == -12.0 and mb.value_at(AUTO_VOL, 9.0) == -40.0
    assert mb.value_at(AUTO_VOL, 0.75) == pytest.approx(-6.0) and mb.value_at(AUTO_VOL, 2.0) == pytest.approx(-17.0)
    env = mb.envelope(AUTO_VOL, 0, 3 * SR, SR)
    for t in (0.1, 0.75, 1.25, 2.0, 2.9):
        assert env[int(t * SR)] == pytest.approx(mb.value_at(AUTO_VOL, int(t * SR) / SR), abs=1e-9)
    n = mb.normalize_automation({"volume": [[1, 99], [-1, -99], [1, 3], ["x", 1]], "pan": [[0, 2]]})
    assert n == {"volume": [[0.0, -40.0], [1.0, 3.0]], "pan": [[0.0, 1.0]]}


def test_automation_render_applies_sample_envelope(mb):
    x = np.ones((3 * SR, 2), dtype="float32") * 0.5
    tr = {"volume_db": -6.0, "pan": 0.3, "automation": {"volume": AUTO_VOL, "pan": AUTO_PAN}}
    out = mb.apply_fader(x, tr, SR, 0)
    for t in (0.2, 0.75, 1.25, 1.9, 2.7):
        i = int(t * SR)
        g = 10 ** ((-6.0 + mb.value_at(AUTO_VOL, i / SR)) / 20)
        p = mb.value_at(AUTO_PAN, i / SR)                  # pan seridi dugmenin yerine gecer
        assert out[i, 0] == pytest.approx(0.5 * g * math.sqrt(0.5 * (1 - p)), rel=1e-5)
        assert out[i, 1] == pytest.approx(0.5 * g * math.sqrt(0.5 * (1 + p)), rel=1e-5)
    # otomasyonsuz kanal: eski sabit surgu/pan yolu ile birebir
    plain = {"volume_db": -3.0, "pan": -0.4}
    o2 = mb.apply_fader(x, plain, SR)
    g = 10 ** (-3 / 20)
    assert np.array_equal(o2[:, 0], x[:, 0] * (g * math.sqrt(0.5 * 1.4)))
    # pencereli (ofsetli) zarf = tam zarfin dilimi
    o3 = mb.apply_fader(x[:SR], tr, SR, int(1.2 * SR))
    assert np.allclose(o3, out[int(1.2 * SR):int(2.2 * SR)], atol=1e-7)


def _node():
    node = shutil.which("node")
    if not node:
        pytest.skip("node yok")
    return node


def _run_js(tmp_path, files, body, inp="{}"):
    runner = tmp_path / "run.js"
    runner.write_text("global.window = {};\n" + "".join(f"require({json.dumps(str(WEB / f))});\n" for f in files)
                      + "const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));\n" + body, encoding="utf-8")
    p = subprocess.run([_node(), str(runner)], input=inp, capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def test_automation_js_equals_python(mb, tmp_path):
    sr = 1000
    raw = {"volume": [[1.5, 6], [0.5, -12], [1.0, 0], [2.5, -99], [1.0, 1.0]], "pan": [[2, 1], [0, -1], [3, 5]]}
    out = _run_js(tmp_path, ["beat-auto.js"], """
const A = window.BeatAuto;
const n = A.normalizeAll(input.raw);
const env = Array.from(A.envelope(n.volume, 250, 3000, 1000));
const penv = Array.from(A.envelope(n.pan, 0, 3500, 1000));
const ramp = A.rampPoints(n.volume, 0.25, 3.0, 0.02);
const ins = A.insert(n.volume, 0.75, -3, "volume");
const mv = A.move(ins.points, ins.idx, 5.0, 99, "volume");
process.stdout.write(JSON.stringify({n, env, penv, ramp, ins, mv, rm: A.remove(n.volume, 0),
  y0: A.yOf(0, "volume", 64), v0: A.vOf(A.yOf(-6, "volume", 64), "volume", 64), pc: A.vOf(A.yOf(0.02, "pan", 64), "pan", 64)}));""",
                  json.dumps({"raw": raw}))
    n = mb.normalize_automation(raw)
    assert out["n"] == n
    py = mb.envelope(n["volume"], 250, 3000, sr)
    assert np.allclose(out["env"], py, atol=1e-9)
    assert np.allclose(out["penv"], mb.envelope(n["pan"], 0, 3500, sr), atol=1e-9)
    # rampa noktalari zarf uzerinde ve 20 ms'den seyrek degil (Web Audio dogrusal kazanc ~ dB-dogrusal)
    rp = np.array(out["ramp"])
    assert rp[0][0] == 0.25 and rp[-1][0] == 3.0
    assert all(abs(v - mb.value_at(n["volume"], t)) < 1e-9 for t, v in rp)
    assert np.max(np.diff(rp[:, 0])) <= 0.5 + 1e-9 and np.sum(np.diff(rp[:, 0]) <= 0.0201) > 50
    # duzenleme: ekle siralar, tasima komsulari asmaz, sil
    assert [p[0] for p in out["ins"]["points"]] == sorted(p[0] for p in out["ins"]["points"])
    mvp = out["mv"]["points"][out["mv"]["idx"]]
    assert mvp[0] < out["ins"]["points"][out["ins"]["idx"] + 1][0] and mvp[1] == 12
    assert len(out["rm"]) == len(n["volume"]) - 1
    assert out["v0"] == -6 and out["pc"] == 0                # pan merkeze yapisir


# ---------------- 3b. send/bus ----------------
def make_pb(log):
    pb = types.ModuleType("fakepb")

    def plug(name):
        class P:
            def __init__(self, **kw):
                self.kw = kw
                self.name = name
        P.__name__ = name
        return P
    for nm in ("Reverb", "Delay", "Gain", "HighpassFilter", "LowpassFilter", "Compressor"):
        setattr(pb, nm, plug(nm))

    class Pedalboard:
        def __init__(self, plugins):
            self.plugins = plugins

        def __call__(self, audio, sr):
            out = np.array(audio, dtype="float32")
            for p in self.plugins:
                log.append(p.name)
                if p.name == "Gain":
                    out = out * 10 ** (p.kw["gain_db"] / 20)
                elif p.name == "Reverb":
                    out = out * p.kw["wet_level"] + 0.0
                elif p.name == "Delay":
                    d = int(round(p.kw["delay_seconds"] * sr))
                    sh = np.zeros_like(out)
                    sh[:, d:] = out[:, :-d] if d else out
                    out = (1 - p.kw["mix"]) * out + p.kw["mix"] * sh
            return out
    pb.Pedalboard = Pedalboard
    return pb


def test_default_buses_prefer_vst_else_builtin(mb, bs):
    b = mb.default_buses(None, 90.0)
    assert [x["id"] for x in b] == ["reverb", "delay"]
    rv, dl = b[0]["fx"][0], b[1]["fx"][0]
    assert rv["type"] == "reverb" and rv["wet_level"] == 1.0 and rv["dry_level"] == 0.0          # %100 islak
    assert dl["type"] == "delay" and dl["mix"] == 1.0 and dl["sync"] == "1/4"
    assert dl["delay_seconds"] == pytest.approx(60 / 90.0)                                       # BPM'e kilitli
    plugins = [{"name": "ValhallaSupermassive", "path": "/vst/ValhallaSupermassive.vst3"},
               {"name": "MDelay", "path": "/vst/MDelay.vst3"}]
    look = {"/vst/ValhallaSupermassive.vst3": ["mix", "feedback"], "/vst/MDelay.vst3": ["dry_wet", "time"]}
    v = mb.default_buses(plugins, 120, param_lookup=lambda p: look.get(p))
    assert v[0]["fx"][0]["type"] == "vst3" and v[0]["fx"][0]["params"] == {"mix": 1.0} and v[0]["engine"] == "vst"
    assert v[1]["fx"][0]["name"] == "MDelay" and v[1]["fx"][0]["params"] == {"dry_wet": 1.0}
    # BPM degisince yerlesik delay yeniden kilitlenir
    assert mb.bus_chain(b[1], 140.0)[0]["delay_seconds"] == pytest.approx(60 / 140.0)


def test_sends_post_fader_sum_into_bus_and_master(bs, mb, tmp_path, monkeypatch):
    from app.core import beat_fx
    log = []
    monkeypatch.setattr(beat_fx, "_PB_OVERRIDE", make_pb(log))
    x = np.zeros(2 * SR, dtype="float32")
    x[1000:1100] = 0.5
    p1 = _write(bs, tmp_path / "a.wav", _st(x))
    p2 = _write(bs, tmp_path / "b.wav", _st(x * 0.5))
    bus_fx = [{"type": "highpass", "cutoff_hz": 20}, {"type": "gain", "gain_db": -6.0}, {"type": "reverb", "wet_level": 1.0, "dry_level": 0.0}]
    buses = [{"id": "reverb", "name": "Reverb", "fx": bus_fx, "volume_db": -2.0, "mute": False},
             {"id": "delay", "name": "Delay", "fx": [{"type": "delay", "delay_seconds": 0.25, "feedback": 0, "mix": 1.0}],
              "volume_db": 0.0, "mute": True}]
    t1 = _track("v1", "vocal", [_clip("a", p1, 0, 0, 2.0)], volume_db=-6.0, pan=0.5, sends={"reverb": -3.0, "delay": 0.0})
    t2 = _track("v2", "vocal", [_clip("b", p2, 0, 0, 2.0)], volume_db=0.0, sends={"reverb": -60.0})
    proj = {"id": "p", "bpm": 120, "tracks": [t1, t2], "buses": buses}
    mix = bs.mix_array(proj, SR)
    assert log == ["HighpassFilter", "Gain", "Reverb"]  # bus fx sirasi korunur, mute'lu Delay bus'i islenmez
    d1 = bs.render_track_audio(t1, SR, {})
    d2 = bs.render_track_audio(t2, SR, {})
    dry = mb.apply_fader(d1, t1, SR) + mb.apply_fader(d2, t2, SR)
    send = d1 * 10 ** (-6 / 20) * 10 ** (-3 / 20)        # post-fader (pan'dan once), -60 dB send kapali
    wet = send * 10 ** (-6 / 20) * 1.0 * 10 ** (-2 / 20)
    assert np.allclose(mix[:len(dry)], dry + wet, atol=1e-5)
    # send yoksa bus'a hic gitmez; kanal mute/solo kurali send'i de keser
    t1["mute"] = True
    log.clear()
    m2 = bs.mix_array(proj, SR)
    assert log == [] and np.allclose(m2[:len(dry)], mb.apply_fader(d2, t2, SR), atol=1e-6)


def test_bus_without_pedalboard_uses_numpy_reverb(bs, mb):
    x = np.zeros((SR, 2), dtype="float32")
    x[100] = 1.0
    bus = mb.default_buses(None, 120)[0]
    y = mb.process_bus(x, SR, bus, 120)
    assert abs(y[100, 0]) < 1e-6                        # %100 islak: kuru darbe yok
    assert np.sum(y[2000:] ** 2) > 1e-4                # kuyruk var (atlanmadi)


def test_bus_preview_equals_bounce(bs, mb, tmp_path, monkeypatch):
    from app.core import beat_fx
    monkeypatch.setattr(beat_fx, "_PB_OVERRIDE", make_pb([]))
    t = np.arange(4 * SR) / SR
    x = (0.3 * np.sin(2 * np.pi * 330 * t) * (t % 1.0 < 0.3)).astype("float32")
    p = _write(bs, tmp_path / "v.wav", _st(x))
    buses = [{"id": "delay", "name": "Delay", "volume_db": -1.0, "mute": False,
              "fx": [{"type": "gain", "gain_db": -3.0}, {"type": "delay", "delay_seconds": 0.25, "feedback": 0.0, "mix": 1.0, "sync": "1/8"}]}]
    tr = _track("v", "vocal", [_clip("a", p, 0, 0, 4.0)], volume_db=-2.0,
                automation={"volume": [[0.0, 0.0], [4.0, -12.0]]}, sends={"delay": -4.0})
    proj = {"id": "p", "bpm": 120, "tracks": [tr], "buses": buses}
    mix = bs.mix_array(proj, SR)
    t0, t1 = 2.0, 3.5
    main, bus = bs.render_track_preview(tr, {"tracks": [], "buses": buses, "bpm": 120}, t0, t1, SR, {})
    w = slice(int(t0 * SR), int(t0 * SR) + len(main))
    # Web Audio: ana pencere kanal surgusu/otomasyonundan gecer, bus donusu dogrudan miks cikisina
    heard = mb.apply_fader(main, tr, SR, int(t0 * SR)) + bus
    assert np.max(np.abs(heard - mix[w])) < 1e-5
    r = bs.preview_render("", "v", t0, t1 - t0, "", tr, {}, SR, {"tracks": [], "buses": buses, "bpm": 120})
    assert r["ok"] and Path(r["bus_path"]).is_file() and Path(r["path"]).is_file()
    r2 = bs.preview_render("", "v", t0, t1 - t0, "", tr, {}, SR, {"tracks": [], "buses": buses, "bpm": 120})
    assert r2["cached"] and r2["bus_path"] == r["bus_path"]
    buses[0]["volume_db"] = -5.0                       # bus ses seviyesi onizleme anahtarina girer
    r3 = bs.preview_render("", "v", t0, t1 - t0, "", tr, {}, SR, {"tracks": [], "buses": buses, "bpm": 120})
    assert r3["key"] != r["key"]


def test_style_preset_reverb_delay_become_sends(bs):
    from app.core import beat_style
    r = beat_style.resolve("soft", None, 50, True, 120.0, use_sends=False)
    roles = [f.get("style_role") for f in r["fx"]]
    assert "verb" in roles and r["sends"] == {}
    s = beat_style.resolve("soft", None, 50, True, 120.0, use_sends=True)
    assert not any(f.get("style_role") in ("verb", "delay") for f in s["fx"])
    assert set(s["sends"]) <= {"reverb", "delay"} and "reverb" in s["sends"]
    assert all(-59 <= v <= 0 for v in s["sends"].values()) and any("send" in n for n in s["notes"])
    wet = next(f for f in r["fx"] if f.get("style_role") == "verb")["wet_level"]
    assert s["sends"]["reverb"] == pytest.approx(round(20 * math.log10(wet), 1))


def test_project_gets_default_buses_and_migrates(bs):
    p = bs.create_project("x")["project"]
    assert [b["id"] for b in p["buses"]] == ["reverb", "delay"] and p.get("buses_auto") is True
    old = {"id": "o", "tracks": [], "bpm": 100}
    assert bs.migrate_project(old) is True and len(old["buses"]) == 2
    assert old["buses"][1]["fx"][0]["delay_seconds"] == pytest.approx(0.6)
    assert bs.migrate_project(old) is False


def test_mixdown_bus_tail_and_trim(bs, tmp_path):
    x = np.zeros(SR, dtype="float32")
    x[-2000:] = 0.4
    p = _write(bs, tmp_path / "v.wav", _st(x))
    buses = [{"id": "delay", "name": "Delay", "volume_db": 0.0, "mute": False,
              "fx": [{"type": "delay", "delay_seconds": 0.5, "feedback": 0.0, "mix": 1.0}]}]
    tr = _track("v", "vocal", [_clip("a", p, 0, 0, 1.0)], sends={"delay": 0.0})
    mix = bs.mix_array({"id": "p", "bpm": 120, "tracks": [tr], "buses": buses}, SR)
    assert SR + int(0.45 * SR) < len(mix) <= SR + int(0.51 * SR)     # yankı kuyrugu kesilmedi, sessizlik kirpildi
    tr["sends"] = {}
    assert len(bs.mix_array({"id": "p", "bpm": 120, "tracks": [tr], "buses": buses}, SR)) == SR


# ---------------- arayuz baglantilari ----------------
def test_ui_wiring_present():
    html = (WEB / "beat.html").read_text(encoding="utf-8")
    js = (WEB / "beat.js").read_text(encoding="utf-8")
    tl = (WEB / "beat-timeline.js").read_text(encoding="utf-8")
    assert "beat-auto.js" in html and "beat-clean.js" in html and 'id="cleanPanel"' in html
    for k in ("beat_clean_analyze", "beat_clean_apply", "beat_clean_progress", "beat_clean_model_install",
              "beat_buses_default", "data-autotog", "data-busvol", "data-busmute", "data-send", "make_room", "use_sends"):
        assert k in js or k in (WEB / "beat-clean.js").read_text(encoding="utf-8"), k
    for k in ("kb-auto-lane", "kb-bus-lane", "kb-breath", "scheduleAuto", "busBuf", "setCleanAB"):
        assert k in tl, k
    from app.ui.api import Api
    for m in ("beat_clean_analyze", "beat_clean_apply", "beat_clean_model_install", "beat_buses_default"):
        assert m in Api.JOB_METHODS and hasattr(Api, m)
    assert hasattr(Api, "beat_clean_progress") and hasattr(Api, "beat_clean_model_info")


def test_node_check_all_beat_js():
    node = _node()
    for f in sorted(WEB.glob("beat*.js")):
        p = subprocess.run([node, "--check", str(f)], capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, (f.name, p.stderr)
