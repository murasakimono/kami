"""Kami Beat Revize 4: efekt parametreleri (FX_SCHEMA), klip/bolge efekti, efektli onizleme render'i,
pedalboard'suz zarif yedek, VST3 parametre cikarma ve kendi penceresi (mock pedalboard ile)."""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
import threading
import time
import types
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SR = 48000


# ---------------- sahte pedalboard ----------------
class _FX:
    def __init__(self, **kw):
        self.kw = kw

    def process(self, x, sr):
        return x


class _Gain(_FX):
    def process(self, x, sr):
        return x * (10.0 ** (self.kw["gain_db"] / 20.0))


class _Limiter(_FX):          # sahte: esikte sert kirpar (dogrusal olmayan -> sira farki olculebilir)
    def process(self, x, sr):
        thr = 10.0 ** (self.kw["threshold_db"] / 20.0)
        return np.clip(x, -thr, thr)


class _Board:
    def __init__(self, plugins):
        self.plugins = list(plugins)

    def __call__(self, x, sr):
        for p in self.plugins:
            x = p.process(x, sr) if hasattr(p, "process") else p(x, sr)
        return x


def make_pb(load_plugin=None):
    from app.core import beat_fx
    ns = types.SimpleNamespace(Pedalboard=_Board, created=[])
    for spec in beat_fx.FX_SCHEMA.values():
        name = spec["pb"]
        base = {"Gain": _Gain, "Limiter": _Limiter}.get(name, _FX)

        def factory(_base=base, _name=name):
            def mk(**kw):
                o = _base(**kw)
                o.cls = _name
                ns.created.append(o)
                return o
            return mk
        setattr(ns, name, factory())
    if load_plugin is not None:
        ns.load_plugin = load_plugin
    return ns


@pytest.fixture()
def fx(monkeypatch):
    from app.core import beat_fx
    beat_fx.POOL.clear()
    beat_fx._PARAM_CACHE.clear()
    yield beat_fx
    monkeypatch.setattr(beat_fx, "_PB_OVERRIDE", None)
    beat_fx.POOL.clear()


@pytest.fixture()
def bs(tmp_path, monkeypatch):
    from app.core import beat_studio
    monkeypatch.setattr(beat_studio, "projects_dir", lambda: (tmp_path / "proj").mkdir(exist_ok=True) or tmp_path / "proj")
    monkeypatch.setattr(beat_studio, "recordings_dir", lambda: (tmp_path / "rec").mkdir(exist_ok=True) or tmp_path / "rec")
    monkeypatch.setattr(beat_studio, "_GLOBAL_LATENCY_GETTER", None)
    monkeypatch.setattr(beat_studio, "_PREVIEW_SRC", {})
    return beat_studio


def _clip(cid, path, start, src_in, src_out, **kw):
    c = {"id": cid, "take_id": "t", "path": path, "start": start, "src_in": src_in, "src_out": src_out,
         "gain_db": 0.0, "fade_in": 0.0, "fade_out": 0.0, "muted": False}
    c.update(kw)
    return c


def _ramp(n, amp=0.2):
    t = np.arange(n, dtype="float32")
    x = amp * np.sin(2 * np.pi * 220.0 * t / SR).astype("float32")
    return np.stack([x, x * 0.5], axis=1).astype("float32")


# ---------------- 1. FX_SCHEMA ----------------
def test_fx_schema_valid_and_matches_presets(fx):
    from app.core import beat_studio
    for t, spec in fx.FX_SCHEMA.items():
        assert spec["label"] and spec["pb"] and spec["group"], t
        keys = [p["key"] for p in spec["params"]]
        assert len(keys) == len(set(keys)), t
        for p in spec["params"]:
            assert p["min"] < p["max"], (t, p["key"])
            assert p["min"] <= p["default"] <= p["max"], (t, p["key"])
            assert p["step"] > 0 and p["scale"] in ("lin", "log"), (t, p["key"])
            if p["scale"] == "log":
                assert p["min"] > 0, (t, p["key"])
    # mevcut onayar/AI miks fx sozluklerinin her anahtari semada tanimli
    for pr in beat_studio.VOCAL_PRESETS.values():
        for f in pr["fx"]:
            spec = fx.FX_SCHEMA[f["type"]]
            known = {p["key"] for p in spec["params"]}
            assert set(f) - {"type"} <= known, f
            assert fx.clamp_fx(f) == f, f          # onayarlar aralik icinde
    pub = fx.schema_public()
    assert set(pub) == set(fx.FX_SCHEMA) and "pb" not in pub["compressor"]["params"][0]


def test_fx_param_limits_and_kwargs(fx):
    c = fx.clamp_fx({"type": "compressor", "threshold_db": -200, "ratio": 99, "attack_ms": "x", "bypass": True})
    assert c["threshold_db"] == -60.0 and c["ratio"] == 20.0 and c["attack_ms"] == 8.0 and c["bypass"] is True
    assert fx.clamp_fx({"type": "vst3", "params": {"Mix": 4, "Gain": -1}})["params"] == {"Mix": 1.0, "Gain": 0.0}
    assert fx.fx_kwargs({"type": "highpass", "cutoff_hz": 5}) == ("HighpassFilter", {"cutoff_frequency_hz": 20.0})
    name, kw = fx.fx_kwargs({"type": "deesser"})
    assert name == "PeakFilter" and kw == {"cutoff_frequency_hz": 6800.0, "gain_db": -4.0, "q": 2.2}
    name, kw = fx.fx_kwargs({"type": "reverb", "room_size": 0.5})
    assert kw["room_size"] == 0.5 and kw["damping"] == 0.5 and kw["width"] == 1.0
    assert fx.fx_kwargs({"type": "vst3"}) is None
    assert fx.default_fx("pitchshift") == {"type": "pitchshift", "semitones": 0.0}
    assert fx.default_fx("yok") is None
    # zincir ozeti: gorsel alanlar/bypass'li moduller duyulani degistirmez
    a = [{"type": "gain", "gain_db": 3.0, "name": "A"}, {"type": "reverb", "bypass": True}]
    b = [{"type": "gain", "gain_db": 3.0, "name": "B"}]
    assert fx.chain_hash(a) == fx.chain_hash(b) != fx.chain_hash([{"type": "gain", "gain_db": 3.1}])
    assert fx.chain_hash(b) != fx.chain_hash(b, denoise=True)


def test_build_plugins_with_mock_pedalboard(fx, monkeypatch, tmp_path):
    pb = make_pb()
    monkeypatch.setattr(fx, "_PB_OVERRIDE", pb)
    chain = [{"type": "highpass", "cutoff_hz": 120}, {"type": "compressor", "bypass": True},
             {"type": "gain", "gain_db": 6.0}, {"type": "vst3", "name": "Yok", "path": str(tmp_path / "x.vst3")},
             {"type": "bilinmeyen"}]
    plugins, borrowed, skipped = fx.build_plugins(pb, chain)
    assert [p.cls for p in plugins] == ["HighpassFilter", "Gain"]
    assert plugins[0].kw == {"cutoff_frequency_hz": 120.0} and borrowed == []
    assert skipped == ["Yok", "bilinmeyen"]
    x = _ramp(1000)
    y, info = fx.process(x, SR, chain)
    assert info["engine"] == "pedalboard" and info["applied"] == 2
    assert np.allclose(y, x * 10 ** (6 / 20), atol=1e-6) and y.shape == x.shape


# ---------------- 2. pedalboard yokken zarif yedek ----------------
def test_graceful_fallback_without_pedalboard(fx, bs, monkeypatch, tmp_path):
    monkeypatch.setattr(fx, "_PB_OVERRIDE", False)
    assert fx.pedalboard_module() is None
    assert fx.available() == {"pedalboard": False, "vst": False, "editor": False}
    x = _ramp(2000)
    y, info = fx.process(x, SR, [{"type": "gain", "gain_db": -6.0}, {"type": "compressor"}, {"type": "vst3", "path": "a"}])
    assert info["engine"] == "numpy" and info["applied"] == 1 and info["skipped"] == ["compressor", "vst3"]
    assert np.allclose(y, x * 10 ** (-6 / 20), atol=1e-6)
    assert fx.vst_params("x.vst3")["error"] == "pedalboard_missing"
    assert fx.open_editor("x.vst3")["error"] == "pedalboard_missing"
    # apply_fx_chain eskiden pedalboard yoksa hata donerdi; artik islenmis (yarim) dosya yazar
    src = tmp_path / "in.wav"
    bs._write_wav_np(str(src), x, SR)
    r = bs.apply_fx_chain(str(src), str(tmp_path / "out.wav"), [{"type": "gain", "gain_db": 6.0}, {"type": "reverb"}])
    assert r["ok"] and r["engine"] == "numpy" and r["skipped"] == ["reverb"]
    out, _ = bs._read_audio_np(str(tmp_path / "out.wav"), SR)
    assert np.allclose(out[:len(x)], np.clip(x * 10 ** (6 / 20), -1, 1), atol=2e-4)


# ---------------- 3. klip fx + kanal fx sirasi ----------------
def test_clip_fx_before_track_fx_and_skip(fx, bs, monkeypatch):
    monkeypatch.setattr(fx, "_PB_OVERRIDE", make_pb())
    n = SR
    src = np.full((n, 2), 0.2, dtype="float32")
    cache = {"/v.wav": src}
    lim = [{"type": "limiter", "threshold_db": 20 * np.log10(0.3)}]
    c_fx = [{"type": "gain", "gain_db": 20 * np.log10(2.0)}]
    tr = {"id": "v", "fx": lim, "clips": [_clip("a", "/v.wav", 0.0, 0.0, 0.5, fx=c_fx)]}
    out = bs.render_track_audio(tr, SR, cache)
    assert len(out) == SR // 2
    assert np.allclose(out, 0.3, atol=1e-6)       # klip fx (x2 = 0.4) SONRA kanal limiter (0.3); ters sira 0.4 olurdu
    # kanal efektini atlayan klip: yalniz klip fx
    tr2 = {"id": "v", "fx": lim, "clips": [_clip("a", "/v.wav", 0.0, 0.0, 0.5, fx=c_fx, skip_track_fx=True),
                                           _clip("b", "/v.wav", 0.5, 0.0, 0.5)]}
    out2 = bs.render_track_audio(tr2, SR, cache)
    assert np.allclose(out2[: SR // 2], 0.4, atol=1e-6) and np.allclose(out2[SR // 2:], 0.2, atol=1e-6)
    # klip gain zarfi klip fx'ten SONRA (fx'i olmayan klipte eski render_track_clips ile birebir)
    tr3 = {"id": "v", "fx": [], "clips": [_clip("a", "/v.wav", 0.25, 0.0, 0.5, gain_db=-6.0, fade_in=0.1, fade_out=0.05)]}
    assert np.array_equal(bs.render_track_audio(tr3, SR, cache), bs.render_track_clips(tr3["clips"], SR, cache))
    # bypass'li klip fx yok sayilir
    tr4 = {"id": "v", "fx": [], "clips": [_clip("a", "/v.wav", 0.0, 0.0, 0.5, fx=[dict(c_fx[0], bypass=True)])]}
    assert np.allclose(bs.render_track_audio(tr4, SR, cache), 0.2)
    assert bs.track_has_fx(tr4) is False and bs.track_has_fx(tr) is True


def test_stack_clip_fx_belongs_to_active_member(fx, bs, monkeypatch):
    monkeypatch.setattr(fx, "_PB_OVERRIDE", make_pb())
    from app.core import beat_clips as bc
    cache = {"/v.wav": np.full((SR, 2), 0.1, dtype="float32")}
    g6 = [{"type": "gain", "gain_db": 20 * np.log10(3.0)}]
    clips = [_clip("a", "/v.wav", 0.0, 0.0, 0.5, stack_id="s1", stack_active=False, fx=g6),
             _clip("b", "/v.wav", 0.0, 0.0, 0.5, stack_id="s1", stack_active=True)]
    tr = {"id": "v", "fx": [], "clips": clips}
    assert np.allclose(bs.render_track_audio(tr, SR, cache), 0.1)      # aktif take'in fx'i yok
    tr["clips"] = bc.apply_fx_to_stack(clips, "a")                       # tum desteye uygula
    assert all(c["fx"] == g6 for c in tr["clips"])
    assert tr["clips"][1]["fx"] is not tr["clips"][0]["fx"]               # derin kopya
    assert np.allclose(bs.render_track_audio(tr, SR, cache), 0.3, atol=1e-6)


# ---------------- 4. bolge efekti bolme ----------------
def test_region_split_boundaries_and_fx():
    from app.core import beat_clips as bc
    c = _clip("c1", "/v.wav", 1.0, 0.5, 4.5, fade_in=0.2, fade_out=0.3, fx=[{"type": "gain", "gain_db": 1.0}])
    other = _clip("o", "/v.wav", 8.0, 0.0, 1.0)
    rfx = [{"type": "reverb", "room_size": 0.6}]
    r = bc.region_split([c, other], "c1", 2.0, 3.0, ids=["m", "a"], fx=rfx)
    out = r["clips"]
    assert r["mid_id"] == "m" and [x["id"] for x in out] == ["c1", "m", "a", "o"]
    b, m, a = out[0], out[1], out[2]
    h = bc.XFADE / 2
    assert bc.clip_bounds(b) == [1.0, 2.0 + h] and b["fade_in"] == 0.2 and b["fade_out"] == bc.XFADE
    assert bc.clip_bounds(m) == [2.0 - h, 3.0 + h] and m["fade_in"] == bc.XFADE and m["fade_out"] == bc.XFADE
    assert bc.clip_bounds(a) == [3.0 - h, 5.0] and a["fade_in"] == bc.XFADE and a["fade_out"] == 0.3
    # kaynak surekliligi: zaman cizelgesindeki her an ayni kaynak ornegine denk gelir
    for x in (b, m, a):
        assert x["src_in"] - x["start"] == pytest.approx(c["src_in"] - c["start"], abs=1e-6)
    assert m["fx"] == rfx and b["fx"] == c["fx"] == a["fx"]
    assert b["fx"] is not a["fx"] and m["fx"] is not rfx
    # bolge klibin basinda/sonunda: tek kenar
    r2 = bc.region_split([c], "c1", 0.0, 2.0, ids=["a2"], fx=rfx)
    assert [x["id"] for x in r2["clips"]] == ["c1", "a2"] and r2["mid_id"] == "c1"
    assert r2["clips"][0]["fade_in"] == 0.2 and bc.clip_bounds(r2["clips"][0]) == [1.0, 2.0 + h]
    r3 = bc.region_split([c], "c1", 4.0, 9.0, ids=["m3"])
    assert r3["mid_id"] == "m3" and bc.clip_bounds(r3["clips"][1]) == [4.0 - h, 5.0] and r3["clips"][1]["fade_out"] == 0.3
    assert r3["clips"][1]["fx"] == c["fx"]                     # fx verilmezse ozgun zincir kalir
    # cok kisa / disarida -> degisiklik yok
    assert bc.region_split([c], "c1", 2.0, 2.005)["mid_id"] == ""
    assert bc.region_split([c], "yok", 2.0, 3.0)["mid_id"] == ""


def test_region_split_stack():
    from app.core import beat_clips as bc
    a = _clip("a", "/1.wav", 0.0, 0.0, 4.0, stack_id="s", stack_active=False, fx=[{"type": "gain", "gain_db": 2.0}])
    b = _clip("b", "/2.wav", 0.0, 0.0, 4.0, stack_id="s", stack_active=True)
    rfx = [{"type": "delay"}]
    r = bc.region_split([a, b], "a", 1.0, 2.0, ids=["sm", "sa", "am", "aa", "bm", "ba"], fx=rfx)
    out = {x["id"]: x for x in r["clips"]}
    assert r["mid_id"] == "bm"                                   # aktif uyenin orta parcasi
    assert {k: v.get("stack_id") for k, v in out.items()} == {"a": "s", "b": "s", "am": "sm", "bm": "sm", "aa": "sa", "ba": "sa"}
    assert out["bm"]["fx"] == rfx and out["am"]["fx"] == a["fx"]  # aktif olmayanin kendi fx'i korunur
    assert out["bm"]["stack_active"] and not out["am"]["stack_active"]


def test_region_split_is_transparent_without_fx(bs):
    """Capraz gecisli bolme efektsiz halde duyulani (neredeyse) degistirmez."""
    from app.core import beat_clips as bc
    cache = {"/v.wav": np.full((3 * SR, 2), 0.5, dtype="float32")}
    c = _clip("c", "/v.wav", 0.5, 0.25, 2.75)
    tr = {"id": "v", "fx": [], "clips": [c]}
    before = bs.render_track_audio(tr, SR, cache)
    tr["clips"] = bc.region_split([c], "c", 1.0, 2.0)["clips"]
    after = bs.render_track_audio(tr, SR, cache)
    assert len(before) == len(after)
    assert np.max(np.abs(before - after)) < 0.5 * 0.01      # dogrusal gecis ~ birim kazanc


# ---------------- 5. onizleme penceresi + onbellek anahtari ----------------
def test_preview_window(bs):
    assert bs.preview_window(3.0, 15.0) == (3.0, 18.0)
    assert bs.preview_window(-2.0, 500.0) == (0.0, bs.PREVIEW_MAX_DUR)
    loop = {"on": True, "start": 4.0, "end": 12.0}
    assert bs.preview_window(6.0, 15.0, loop=loop) == (4.0, 12.0)          # dongu icinde: tum dongu
    assert bs.preview_window(1.0, 15.0, loop=loop) == (1.0, 12.0)          # dongu oncesi: dongu sonuna kadar
    assert bs.preview_window(13.0, 5.0, loop=loop) == (13.0, 18.0)         # dongu sonrasi: dongu yok sayilir
    assert bs.preview_window(6.0, 15.0, loop={"on": False, "start": 4, "end": 12}) == (6.0, 21.0)
    clip = _clip("c", "/v.wav", 10.0, 0.0, 5.0)
    assert bs.preview_window(12.0, 15.0, clip) == (12.0, 15.0)             # klip araligiyla kesisim
    assert bs.preview_window(0.0, 3.0, clip) == (10.0, 13.0)               # klip disinda: klip basindan


def test_preview_key(bs, tmp_path):
    p = tmp_path / "v.wav"
    p.write_bytes(b"x" * 10)
    tr = {"id": "v", "fx": [{"type": "gain", "gain_db": 2.0}], "clips": [
        _clip("a", str(p), 0.0, 0.0, 4.0), _clip("far", str(p), 60.0, 0.0, 4.0)]}
    k = bs.preview_key(tr, 1.0, 3.0)
    assert k == bs.preview_key(json.loads(json.dumps(tr)), 1.0, 3.0)
    t2 = json.loads(json.dumps(tr)); t2["fx"][0]["gain_db"] = 2.5
    assert bs.preview_key(t2, 1.0, 3.0) != k                                 # parametre degisti
    t3 = json.loads(json.dumps(tr)); t3["fx"][0]["name"] = "Ad"; t3["fx"].append({"type": "reverb", "bypass": True})
    assert bs.preview_key(t3, 1.0, 3.0) == k                                 # duyulan ayni
    t4 = json.loads(json.dumps(tr)); t4["clips"][1]["start"] = 70.0
    assert bs.preview_key(t4, 1.0, 3.0) == k                                 # pencere disindaki klip
    t5 = json.loads(json.dumps(tr)); t5["clips"][0]["fx"] = [{"type": "gain", "gain_db": 1}]
    assert bs.preview_key(t5, 1.0, 3.0) != k                                 # klip fx
    t6 = json.loads(json.dumps(tr)); t6["clips"][0]["src_in"] = 0.1
    assert bs.preview_key(t6, 1.0, 3.0) != k
    assert bs.preview_key(tr, 1.0, 3.5) != k                                 # pencere
    time.sleep(0.01)
    p.write_bytes(b"y" * 11)
    assert bs.preview_key(tr, 1.0, 3.0) != k                                 # kaynak dosya degisti


# ---------------- 6. onizleme == bounce (ornek ornek) ----------------
def test_preview_window_equals_bounce_slice(fx, bs, monkeypatch):
    for override in (False, make_pb()):                       # numpy yedegi ve (mock) pedalboard
        monkeypatch.setattr(fx, "_PB_OVERRIDE", override)
        cache = {"/v.wav": _ramp(4 * SR), "/w.wav": _ramp(3 * SR, 0.1)}
        tr = {"id": "v", "fx": [{"type": "gain", "gain_db": -3.0}], "clips": [
            _clip("a", "/v.wav", 0.4, 0.1, 2.6, fade_in=0.05, fade_out=0.2, gain_db=1.5, fx=[{"type": "gain", "gain_db": 4.0}]),
            _clip("b", "/w.wav", 2.2, 0.0, 2.0, fade_in=0.3, skip_track_fx=True)]}
        full = bs.render_track_audio(tr, SR, cache)
        for t0, t1 in ((0.0, 1.0), (1.3, 2.7), (0.4, 4.2), (3.9, 6.0)):
            win = bs.render_track_audio(tr, SR, cache, t0, t1)
            a, b = int(round(t0 * SR)), int(round(t1 * SR))
            exp = np.zeros((b - a, 2), dtype="float32")
            seg = full[a:b]
            exp[:len(seg)] = seg
            assert win.shape == exp.shape
            assert np.array_equal(win, exp), (override, t0, t1)


def test_preview_render_file_matches_bounce(fx, bs, monkeypatch):
    monkeypatch.setattr(fx, "_PB_OVERRIDE", False)
    rec = bs.recordings_dir()
    src = _ramp(3 * SR, 0.3)
    p = str(rec / "v.wav")
    bs._write_wav_np(p, src, SR)
    proj = bs.create_project("R4")["project"]
    tr = next(t for t in proj["tracks"] if t["id"] == "vocal1")
    tr["fx"] = [{"type": "gain", "gain_db": -4.0}]
    tr["clips"] = [_clip("a", p, 0.5, 0.0, 2.5, fx=[{"type": "gain", "gain_db": 2.0}])]
    for t in proj["tracks"]:
        if t["id"] != "vocal1":
            t["clips"] = []
    bs.save_project(proj)
    r = bs.preview_render(proj["id"], "vocal1", 1.0, 1.5)
    assert r["ok"] and not r["cached"] and (r["t0"], r["t1"]) == (1.0, 2.5) and r["engine"] == "numpy"
    assert Path(r["path"]).parent == bs.preview_dir()
    wet, _ = bs._read_audio_np(r["path"], SR)
    full = bs.render_track_audio(tr, SR, {})
    assert np.allclose(wet, full[SR: int(2.5 * SR)], atol=4e-5)      # WAV nicemleme payi (soundfile yoksa ffmpeg 16 bit)
    # bounce (render_mixdown) ayni kanal render'ini kullanir: pan 0 -> sqrt(.5), LUFS dengelemesi kapali
    out = bs.render_mixdown(proj["id"], str(rec / "mix.wav"), target_lufs=0.0)
    assert out["ok"]
    mix, _ = bs._read_audio_np(out["path"], SR)
    g = 10 ** (tr["volume_db"] / 20) * np.sqrt(0.5)
    assert np.allclose(mix[SR: int(2.5 * SR)], wet * g, atol=8e-5)
    # ayni istek: onbellekten; arayuzden gelen guncel (kaydedilmemis) kanal: yeni anahtar
    assert bs.preview_render(proj["id"], "vocal1", 1.0, 1.5)["cached"] is True
    tr2 = json.loads(json.dumps(tr)); tr2["fx"][0]["gain_db"] = -5.0
    r2 = bs.preview_render(proj["id"], "vocal1", 1.0, 1.5, track=tr2)
    assert r2["ok"] and not r2["cached"] and r2["key"] != r["key"]
    # klip onizlemesi: klibin araligi
    r3 = bs.preview_render(proj["id"], "vocal1", 0.0, 1.0, clip_id="a")
    assert (r3["t0"], r3["t1"]) == (0.5, 1.0)
    assert bs.preview_render(proj["id"], "vocal1", 0, 1, clip_id="yok")["error"] == "clip_not_found"
    # efekt yoksa kuru (render yok)
    tr3 = json.loads(json.dumps(tr)); tr3["fx"] = []; tr3["clips"][0]["fx"] = []
    assert bs.preview_render(proj["id"], "vocal1", 1.0, 1.5, track=tr3) == {"ok": True, "dry": True, "t0": 1.0, "t1": 2.5}


def test_preview_supersedes_waiting_request(fx, bs, monkeypatch):
    monkeypatch.setattr(fx, "_PB_OVERRIDE", False)
    cache_src = _ramp(SR)
    monkeypatch.setattr(bs, "_read_audio_np", lambda path, sr=SR: (cache_src, SR))
    monkeypatch.setattr(bs, "_write_wav_np", lambda path, a, sr=SR: Path(path).write_bytes(b"RIFF"))
    monkeypatch.setattr(bs.os.path, "isfile", lambda p: True)
    tr = {"id": "v", "fx": [{"type": "gain", "gain_db": 1.0}], "clips": [_clip("a", "/v.wav", 0.0, 0.0, 0.9)]}
    sem = bs._PREVIEW_SEM
    sem.acquire(); sem.acquire()                        # tum isciler mesgul
    res = {}
    t_old = threading.Thread(target=lambda: res.setdefault("old", bs.preview_render("p", "v", 0.0, 0.5, track=tr, loop={})))
    t_old.start()
    time.sleep(0.15)
    tr_new = json.loads(json.dumps(tr)); tr_new["fx"][0]["gain_db"] = 2.0
    t_new = threading.Thread(target=lambda: res.setdefault("new", bs.preview_render("p", "v", 0.0, 0.5, track=tr_new, loop={})))
    t_new.start()
    time.sleep(0.15)
    sem.release(); sem.release()
    t_old.join(5); t_new.join(5)
    assert res["old"] == {"ok": False, "error": "superseded"}
    assert res["new"]["ok"] and res["new"]["path"]


def test_preview_source_cache_reuses_unchanged_file(fx, bs, monkeypatch, tmp_path):
    monkeypatch.setattr(fx, "_PB_OVERRIDE", False)
    p = tmp_path / "v.wav"
    bs._write_wav_np(str(p), _ramp(SR), SR)
    reads = []
    orig = bs._read_audio_np
    monkeypatch.setattr(bs, "_read_audio_np", lambda path, sr=SR: reads.append(path) or orig(path, sr))
    tr = {"id": "v", "fx": [{"type": "gain", "gain_db": 1.0}], "clips": [_clip("a", str(p), 0.0, 0.0, 0.9)]}
    assert bs.preview_render("p", "v", 0.0, 0.5, track=tr, loop={})["ok"]
    tr["fx"][0]["gain_db"] = 2.0
    assert bs.preview_render("p", "v", 0.0, 0.5, track=tr, loop={})["ok"]
    assert len(reads) == 1                                  # ikinci render kaynagi yeniden okumadi
    time.sleep(0.01)
    bs._write_wav_np(str(p), _ramp(SR, 0.1), SR)            # dosya degisti -> yeniden okunur
    tr["fx"][0]["gain_db"] = 3.0
    assert bs.preview_render("p", "v", 0.0, 0.5, track=tr, loop={})["ok"]
    assert len(reads) == 2


def test_preview_cache_prune(bs):
    d = bs.preview_dir()
    for i in range(5):
        f = d / f"k{i}.wav"
        f.write_bytes(b"\0" * 1000)
        t = time.time() - 100 + i
        import os
        os.utime(f, (t, t))
    assert bs.prune_preview_cache(max_bytes=2500, keep="k0.wav") == 3
    assert sorted(f.name for f in d.glob("*.wav")) == ["k0.wav", "k4.wav"]


# ---------------- 7. VST3: parametre cikarma + durum + pencere ----------------
class _Param:
    def __init__(self, name, raw=0.5, units="", boolean=False):
        self.name, self.raw_value, self.units, self.is_boolean = name, raw, units, boolean
        self.default_raw_value = raw
        self.string_value = f"{raw:.2f}"
        self.range = (0.0, 1.0, None)
        self.is_discrete = False


class _Plugin:
    loads = 0

    def __init__(self):
        _Plugin.loads += 1
        names = ["bypass", "midi_cc_1", "program"] + [f"aux_{i}" for i in range(30)] + ["mix", "threshold", "output_gain"]
        self.parameters = {n: _Param(n) for n in names}
        self.raw_state = b"S0"
        self.shown = 0

    def show_editor(self):
        self.shown += 1
        self.raw_state = b"EDITED"
        self.parameters["mix"].raw_value = 0.9

    def process(self, x, sr):
        return x * (2.0 * self.parameters["mix"].raw_value)


def test_vst_params_mock(fx, monkeypatch, tmp_path):
    plug = tmp_path / "Fake.vst3"
    plug.mkdir()
    _Plugin.loads = 0
    monkeypatch.setattr(fx, "_PB_OVERRIDE", make_pb(load_plugin=lambda p: _Plugin()))
    r = fx.vst_params(str(plug))
    assert r["ok"] and r["total"] == 36 and len(r["params"]) == fx.VST_PARAM_TOP and r["more"] == 36 - 24
    keys = [p["key"] for p in r["params"]]
    assert keys[:3] == ["mix", "threshold", "output_gain"]             # onemli olanlar once
    assert "bypass" not in keys and "program" not in keys               # onemsizler sona
    p0 = r["params"][0]
    assert p0["raw"] == 0.5 and p0["text"] == "0.50" and p0["min"] == 0.0 and p0["max"] == 1.0
    s = fx.vst_params(str(plug), query="AUX_1")
    assert {p["key"] for p in s["params"]} == {"aux_1"} | {f"aux_{i}" for i in range(10, 20)}
    assert _Plugin.loads == 1                                           # onbellek
    fx.vst_params(str(plug), refresh=True)
    assert _Plugin.loads == 1                                           # yenilemede havuzdaki ornek kullanildi
    assert fx.vst_params(str(tmp_path / "yok.vst3"))["error"] == "plugin_not_found"


def test_vst_state_applied_in_chain(fx, monkeypatch, tmp_path):
    plug = tmp_path / "Fake.vst3"
    plug.mkdir()
    made = []
    monkeypatch.setattr(fx, "_PB_OVERRIDE", make_pb(load_plugin=lambda p: made.append(_Plugin()) or made[-1]))
    x = np.full((100, 2), 0.1, dtype="float32")
    chain = [{"type": "vst3", "path": str(plug), "params": {"mix": 0.25, "yok": 0.3},
              "state_b64": base64.b64encode(b"STATE").decode()}]
    y, info = fx.process(x, SR, chain)
    assert info["applied"] == 1 and np.allclose(y, 0.05)
    assert made[0].raw_state == b"STATE" and made[0].parameters["mix"].raw_value == 0.25
    y2, _ = fx.process(x, SR, [dict(chain[0], params={"mix": 1.0})])
    assert len(made) == 1 and np.allclose(y2, 0.2)                      # havuzdan ayni ornek, yeni durum


def test_vst_editor_child_and_parent(fx, monkeypatch, tmp_path):
    plug = tmp_path / "Fake.vst3"
    plug.mkdir()
    holder = {}
    monkeypatch.setattr(fx, "_PB_OVERRIDE", make_pb(load_plugin=lambda p: holder.setdefault("p", _Plugin())))
    inp, outp = tmp_path / "in.json", tmp_path / "out.json"
    inp.write_text(json.dumps({"state_b64": base64.b64encode(b"OLD").decode(), "params": {"threshold": 0.1}}))
    assert fx.editor_child_main(str(plug), str(inp), str(outp)) == 0
    assert holder["p"].shown == 1
    res = fx.read_editor_result(str(outp))
    assert res["ok"] and base64.b64decode(res["state_b64"]) == b"EDITED"
    assert res["params"]["mix"] == 0.9 and res["params"]["threshold"] == 0.1
    # ana surec: Windows disinda pencere yok
    monkeypatch.setattr(fx.os, "name", "posix")
    assert fx.open_editor(str(plug))["error"] == "editor_windows_only"
    # Windows benzetimi: alt surec komutu dogru, sonuc dosyadan okunur
    monkeypatch.setattr(fx, "available", lambda: {"pedalboard": True, "vst": True, "editor": True})
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        Path(cmd[-1]).write_text(json.dumps({"ok": True, "state_b64": "QQ==", "params": {"mix": 0.7}}))
        return types.SimpleNamespace(returncode=0)
    monkeypatch.setattr(fx.subprocess, "run", fake_run)
    r = fx.open_editor(str(plug), "T0xE", {"mix": 0.2})
    assert r == {"ok": True, "state_b64": "QQ==", "params": {"mix": 0.7}}
    assert "--vst-editor" in seen["cmd"] and str(plug) in seen["cmd"]
    assert not Path(seen["cmd"][-1]).exists()                          # gecici dosyalar temizlendi
    assert fx.open_editor(str(tmp_path / "yok.vst3"))["error"] == "plugin_not_found"


# ---------------- 8. JS <-> Python esdegerligi + arayuz ----------------
_NODE_RUNNER = r"""
global.window = {};
require(process.argv[2]);
const cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const out = cases.map(([fn, args]) => window.BeatClips[fn](...args));
process.stdout.write(JSON.stringify(out));
"""


def test_js_python_equivalence_r4(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node yok")
    from app.core import beat_clips as bc
    fxl = [{"type": "gain", "gain_db": 1.0, "params": {"a": 1}}]
    c = _clip("c1", "/v.wav", 1.0, 0.5, 4.5, fade_in=0.2, fade_out=0.3, fx=fxl, src_len=9.0)
    sa = _clip("a", "/1.wav", 0.0, 0.0, 4.0, stack_id="s", stack_active=False, fx=fxl)
    sb = _clip("b", "/2.wav", 0.0, 0.0, 4.0, stack_id="s", stack_active=True)
    o = _clip("o", "/v.wav", 8.0, 0.0, 1.0)
    rfx = [{"type": "reverb", "room_size": 0.6}]
    cases = []
    for t0, t1 in ((2.0, 3.0), (0.0, 2.0), (4.0, 9.0), (2.0, 2.005), (1.003, 4.997), (2.1234567, 3.7654321)):
        cases.append(["region_split", [[c, o], "c1", t0, t1, 0.01, ["m", "a"], rfx]])
        cases.append(["region_split", [[o, sa, sb], "a", t0, t1, 0.02, ["s1", "s2", "x1", "x2", "x3", "x4"], None]])
    cases.append(["split", [[c], "c1", 2.5, "r"]])
    cases.append(["duplicate", [[c], "c1", "d"]])
    cases.append(["apply_fx_to_stack", [[sa, sb, o], "a"]])
    for cl in (c, o, dict(o, skip_track_fx=True), dict(o, fx=[{"type": "gain", "bypass": True}])):
        cases.append(["has_clip_fx", [cl]])
    runner = tmp_path / "run.js"
    runner.write_text(_NODE_RUNNER, encoding="utf-8")
    p = subprocess.run([node, str(runner), str(ROOT / "app/ui/web/beat-clips.js")], input=json.dumps(cases),
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    js_out = json.loads(p.stdout)
    py_out = json.loads(json.dumps([getattr(bc, fn)(*args) for fn, args in cases]))
    for (fn, args), a, b in zip(cases, py_out, js_out):
        assert a == b, f"{fn}{tuple(args)[1:4]}: py={a} js={b}"


def test_r4_ui_js_syntax_and_ids():
    node = shutil.which("node")
    if not node:
        pytest.skip("node yok")
    for name in ("beat-clips.js", "beat-timeline.js", "beat-fx.js", "beat.js"):
        p = subprocess.run([node, "--check", str(ROOT / "app/ui/web" / name)], capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, f"{name}: {p.stderr}"
    html = (ROOT / "app/ui/web/beat.html").read_text(encoding="utf-8")
    for el_id in ("fxPreviewToggle", "fxPreviewScope", "fxPreviewNote", "fxLevelTabs", "fxAddSel", "fxPanel"):
        assert f'id="{el_id}"' in html, el_id
    assert html.index("beat-fx.js") < html.index('src="beat.js"')


def test_api_r4_methods():
    from app.ui.api import Api
    for name in ("beat_fx_schema", "beat_preview_render", "beat_vst_params", "beat_vst_editor"):
        assert hasattr(Api, name), name
    assert {"beat_preview_render", "beat_vst_editor"} <= Api.JOB_METHODS
    r = Api.beat_fx_schema(None)
    assert r["ok"] and "compressor" in r["schema"] and r["vst_top"] == 24
