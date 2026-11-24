"""Kami Beat Asama 1d + 1e: katman hizalama/yerlesim/chant sapmasi, kanal ekle/sil/sirala + bounce, kulaklikta
efektli dinleme (saf kisimlar + sahte sounddevice), lisans cikarimi, beat rafi / fikir rafi kaliciligi ve projeye
ekleme, yayin oncesi uyari, iPhone Booth hedef secimi."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import types
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SR = 48000


# ---------------- yardimcilar ----------------
def _syllable_env(n: int, sr: int, seed: int = 1, dur: float | None = None):
    rng = np.random.default_rng(seed)
    env = np.zeros(n)
    t = 0.2
    dur = dur or n / sr
    while t < dur - 0.4:
        ln = rng.uniform(0.08, 0.3)
        a, b = int(t * sr), int((t + ln) * sr)
        env[a:b] = np.hanning(b - a) * rng.uniform(0.3, 1.0)
        t += ln + rng.uniform(0.05, 0.25)
    return env


def _voice(env, seed: int, shift_ms: float, sr: int):
    """Ayni hece zarfi, farkli gurultu (gercek double gibi: ayni ritim, farkli dalga) + bilinen kayma."""
    r = np.random.default_rng(seed)
    e = np.roll(env, int(round(shift_ms * sr / 1000.0)))
    return (r.standard_normal(len(env)) * e * 0.3).astype("float32")


def _wav(bs, path: Path, mono) -> Path:
    bs._write_wav_np(str(path), np.stack([mono, mono], axis=1).astype("float32"), SR)
    return path


def _dc(bs, path: Path, secs: float, amp: float = 0.25) -> Path:
    bs._write_wav_np(str(path), np.full((int(round(secs * SR)), 2), amp, dtype="float32"), SR)
    return path


@pytest.fixture()
def bs(tmp_path, monkeypatch):
    from app.core import beat_studio
    monkeypatch.setattr(beat_studio, "projects_dir", lambda: (tmp_path / "proj").mkdir(exist_ok=True) or tmp_path / "proj")
    monkeypatch.setattr(beat_studio, "recordings_dir", lambda: (tmp_path / "rec").mkdir(exist_ok=True) or tmp_path / "rec")
    return beat_studio


def _clip(cid, path, start, length, src_len=None, **kw):
    c = {"id": cid, "take_id": "t_" + cid, "path": str(path), "src_in": 0.0, "src_out": float(length), "start": float(start),
         "gain_db": 0.0, "fade_in": 0.0, "fade_out": 0.0, "muted": False, "src_len": float(src_len or length)}
    c.update(kw)
    return c


# ---------------- 1d-1: hizalama ----------------
@pytest.mark.parametrize("shift_ms", [0.0, 7.0, 23.0, -18.0, 38.0])
def test_align_known_offset_synthetic_double(shift_ms):
    from app.core import beat_layers as bl
    sr = 16000
    n = int(6.0 * sr)
    env = _syllable_env(n, sr)
    ref = _voice(env, 2, 0.0, sr)
    sig = _voice(env, 3, shift_ms, sr)
    r = bl.align_signals(ref, sig, sr)
    assert r["ok"]
    assert abs(r["offset_ms"] - shift_ms) <= 2.0, r
    assert not r["split"] and len(r["segments"]) == 1
    assert r["confidence"] > 0.5


def test_align_piecewise_split_segments():
    from app.core import beat_layers as bl
    sr = 16000
    n = int(6.0 * sr)
    env = _syllable_env(n, sr)
    ref = _voice(env, 2, 0.0, sr)
    e2 = np.concatenate([np.roll(env, int(0.010 * sr))[: n // 2], np.roll(env, int(0.032 * sr))[n // 2:]])
    sig = (np.random.default_rng(5).standard_normal(n) * e2 * 0.3).astype("float32")
    r = bl.align_signals(ref, sig, sr)
    assert r["split"] and len(r["segments"]) == 2, r["segments"]
    a, b = r["segments"]
    assert abs(a["offset_ms"] - 10.0) <= 2.0 and abs(b["offset_ms"] - 32.0) <= 2.0
    assert abs(a["t1"] - 3.0) <= 0.3 and b["t0"] == a["t1"]


def test_align_no_signal_and_too_short():
    from app.core import beat_layers as bl
    z = np.zeros(16000 * 2, dtype="float32")
    assert bl.align_signals(z, z, 16000)["error"] == "no_signal"
    assert bl.align_signals(z[:100], z[:100], 16000)["error"] == "too_short"


def test_proposal_constant_and_split_clips():
    from app.core import beat_layers as bl, beat_clips as bc
    clips = [_clip("d", "x.wav", 2.0, 4.0, src_len=5.0)]
    out = bl.proposal_clips(clips, "d", {"ok": True, "offset_ms": 12.0, "split": False, "segments": []}, 1.8)
    assert out[0]["start"] == pytest.approx(2.0 - 0.012)
    out = bl.proposal_clips(clips, "d", {"ok": True, "offset_ms": 12.0, "split": False, "segments": []}, 1.8, bias_ms=9.0)
    assert out[0]["start"] == pytest.approx(2.0 - 0.012 + 0.009)
    seg = {"ok": True, "offset_ms": 20.0, "split": True,
           "segments": [{"t0": 0.0, "t1": 2.2, "offset_ms": 10.0}, {"t0": 2.2, "t1": 9.0, "offset_ms": 30.0}]}
    out = bl.proposal_clips(clips, "d", seg, 1.8)
    assert len(out) == 2
    first, second = sorted(out, key=lambda c: c["start"])
    # ilk parca 1.8+2.2=4.0'a kadar, -10 ms; ikinci parca -30 ms; kaynak kesitleri korunur (ses esnetilmez)
    assert first["start"] == pytest.approx(1.99) and first["src_out"] == pytest.approx(2.0)
    assert second["start"] == pytest.approx(4.0 - 0.03) and second["src_in"] == pytest.approx(2.0)
    assert first["fade_out"] == pytest.approx(0.005) and second["fade_in"] == pytest.approx(0.005)
    assert sum(bc.clip_len(c) for c in out) == pytest.approx(4.0)


def test_propose_alignment_from_project_files(bs, tmp_path):
    """Gercek dosyalarla: ana vokal klibi + 21 ms gec kaydedilmis double -> oneri klibi ~21 ms sola alir."""
    from app.core import beat_layers as bl
    n = int(5.0 * SR)
    env = _syllable_env(n, SR, seed=4)
    main_p = _wav(bs, tmp_path / "main.wav", _voice(env, 7, 0.0, SR))
    dbl_p = _wav(bs, tmp_path / "dbl.wav", _voice(env, 8, 0.0, SR))
    proj = {"tracks": [
        {"id": "vocal1", "role": "vocal", "clips": [_clip("m", main_p, 1.0, 5.0)]},
        {"id": "double", "role": "vocal", "layer": "double", "layer_of": "vocal1",
         "clips": [_clip("d", dbl_p, 1.021, 5.0)]},
    ]}
    r = bl.propose_alignment(proj, "double", "d")
    assert r["ok"], r
    assert abs(r["offset_ms"] - 21.0) <= 2.0
    assert r["clips"][0]["start"] == pytest.approx(1.0, abs=0.002)
    assert bl.propose_alignment(proj, "double", "nope")["error"] == "clip_not_found"


# ---------------- 1d-1: yerlesim + chant ----------------
def test_placement_rules():
    from app.core import beat_layers as bl
    assert bl.placement("double", 0, 1) == {"pan": 0.3, "volume_db": -6.0, "preset": "double_layer"}
    assert bl.placement("double", 0, 2)["pan"] == -0.6 and bl.placement("double", 1, 2)["pan"] == 0.6
    assert [bl.placement("adlib", i, 3)["pan"] for i in range(3)] == [-0.5, 0.5, -0.5]
    assert bl.placement("adlib", 0, 1)["volume_db"] == -4.0
    assert [bl.placement("chant", i, 4)["pan"] for i in range(4)] == [-0.7, -0.233, 0.233, 0.7]
    assert [bl.placement("chant", i, 3)["pan"] for i in range(3)] == [-0.7, 0.0, 0.7]
    assert bl.placement("chant", 0, 1)["pan"] == 0.0


def test_chant_deviation_deterministic_and_bounded():
    from app.core import beat_layers as bl
    a = bl.chant_deviations(bl.fnv1a("proj123"), 4)
    b = bl.chant_deviations(bl.fnv1a("proj123"), 4)
    c = bl.chant_deviations(bl.fnv1a("baska"), 4)
    assert a == b and a != c
    for d in a + c:
        assert 5.0 <= d["delay_ms"] <= 15.0 and -8.0 <= d["cents"] <= 8.0
    assert len({d["delay_ms"] for d in a}) > 1                  # her take farkli
    # ayni tohumdan ardisik cagrilar tekrarlanabilir, [0, 1) araliginda
    r1, r2 = bl.mulberry32(42), bl.mulberry32(42)
    seq = [r1() for _ in range(50)]
    assert seq == [r2() for _ in range(50)] and all(0.0 <= x < 1.0 for x in seq) and len(set(seq)) == 50


def _default_tracks(bs):
    return bs._default_project("T")["tracks"]


def test_prepare_layer_double_pair_and_layout(bs):
    from app.core import beat_layers as bl
    tr = _default_tracks(bs)
    r = bl.prepare_layer(tr, "double", "vocal1", 2.0, 6.0, seed=1, presets=bs.VOCAL_PRESETS)
    assert r["ok"] and r["created"]
    ids = [t["id"] for t in r["tracks"]]
    assert ids.index(r["track_id"]) == ids.index("vocal1") + 1          # ana vokalin hemen altinda
    d1 = next(t for t in r["tracks"] if t["id"] == r["track_id"])
    assert d1["layer"] == "double" and d1["layer_of"] == "vocal1" and d1["name"] == "Double"
    assert (d1["pan"], d1["volume_db"]) == (0.3, -6.0) and d1["preset"] == "double_layer" and d1["fx"]
    # ayni aralikta bos double kanali varsa ona kaydeder
    r_same = bl.prepare_layer(r["tracks"], "double", "vocal1", 2.0, 6.0, seed=1, presets=bs.VOCAL_PRESETS)
    assert not r_same["created"] and r_same["track_id"] == d1["id"]
    # double kanali o aralikta doluysa ikinci double -> L/R cifti
    tracks = [dict(t, clips=[_clip("x", "a.wav", 2.0, 4.0)]) if t["id"] == d1["id"] else t for t in r["tracks"]]
    r2 = bl.prepare_layer(tracks, "double", "vocal1", 2.5, 5.0, seed=1, presets=bs.VOCAL_PRESETS)
    assert r2["created"] and r2["track_id"] != d1["id"]
    pans = {t["id"]: (t["pan"], t["volume_db"]) for t in r2["tracks"] if t.get("layer") == "double"}
    assert pans[d1["id"]] == (-0.6, -3.0) and pans[r2["track_id"]] == (0.6, -3.0)
    # kullanici elle ayarladiysa (auto_place False) dokunulmaz
    t3 = [dict(t, auto_place=False, pan=0.1) if t["id"] == d1["id"] else t for t in r2["tracks"]]
    lay = bl.layout_layers(t3, "vocal1")
    assert next(t for t in lay if t["id"] == d1["id"])["pan"] == 0.1


def test_prepare_layer_adlib_alternates_and_chant_spread(bs):
    from app.core import beat_layers as bl
    tr = _default_tracks(bs)
    r = bl.prepare_layer(tr, "adlib", "vocal1", 1.0, 2.0)
    assert r["track_id"] == "adlib" and not r["created"]              # varsayilan adlib kanali ilk adlib
    tracks = [dict(t, clips=[_clip("a1", "a.wav", 1.0, 1.0)]) if t["id"] == "adlib" else t for t in r["tracks"]]
    r2 = bl.prepare_layer(tracks, "adlib", "vocal1", 3.0, 4.0, presets=bs.VOCAL_PRESETS)
    assert r2["created"]
    a2 = next(t for t in r2["tracks"] if t["id"] == r2["track_id"])
    assert a2["layer"] == "adlib" and a2["pan"] == 0.5 and a2["volume_db"] == -4.0 and a2["preset"] == "adlib_layer"
    assert next(t for t in r2["tracks"] if t["id"] == "adlib")["pan"] == 0.15     # eski kanal elle ayari korunur
    # chant: her take yeni kanal, 4'e kadar, +-0.7'ye yayilir, sapma alani
    tracks = r2["tracks"]
    made = []
    for i in range(5):
        rc = bl.prepare_layer(tracks, "chant", "vocal1", 1.0, 3.0, seed=bl.fnv1a("p"), pitch_ok=False)
        tracks = rc["tracks"]
        if rc["created"]:
            made.append(rc["track_id"])
            tracks = [dict(t, clips=[_clip("c%d" % i, "c.wav", 1.0, 2.0)]) if t["id"] == rc["track_id"] else t for t in tracks]
    assert len(made) == 4
    ch = [t for t in tracks if t.get("layer") == "chant"]
    assert [t["pan"] for t in ch] == [-0.7, -0.233, 0.233, 0.7]
    assert [t["chant_dev"] for t in ch] == bl.chant_deviations(bl.fnv1a("p"), 4)
    assert not any(f.get("auto") == "chant" for t in ch for f in t["fx"])       # pedalboard yok: yalniz zaman
    lay = bl.layout_layers(tracks, "vocal1", seed=bl.fnv1a("p"), pitch_ok=True)
    for t in [t for t in lay if t.get("layer") == "chant"]:
        ps = [f for f in t["fx"] if f.get("auto") == "chant"]
        assert len(ps) == 1 and ps[0]["semitones"] == pytest.approx(t["chant_dev"]["cents"] / 100.0)
    lay2 = bl.layout_layers(lay, "vocal1", seed=bl.fnv1a("p"), pitch_ok=True)   # tekrar: cift eklenmez
    assert all(sum(1 for f in t["fx"] if f.get("auto") == "chant") == 1 for t in lay2 if t.get("layer") == "chant")


def test_layer_presets_valid():
    from app.core import beat_fx, beat_studio
    for k in ("double_layer", "adlib_layer", "chant_layer"):
        for f in beat_studio.VOCAL_PRESETS[k]["fx"]:
            assert beat_fx.clamp_fx(f) == f


# ---------------- 1d-1: kanal ekle / sil / sirala + bounce ----------------
def test_tracks_op_add_remove_move_reorder(bs):
    from app.core import beat_layers as bl
    tr = _default_tracks(bs)
    before = json.dumps(tr, sort_keys=True)
    r = bl.tracks_op(tr, "add", {"role": "fx", "name": "Ses Efekti", "color": "#ABCDEF"})
    assert r["ok"] and r["tracks"][-1]["name"] == "Ses Efekti" and r["tracks"][-1]["color"] == "#ABCDEF"
    assert r["tracks"][-1]["role"] == "fx" and r["tracks"][-1]["clips"] == []
    r2 = bl.tracks_op(r["tracks"], "add", {"role": "vocal"}, bs.VOCAL_PRESETS)
    v = r2["tracks"][-1]
    assert v["name"] == "Vokal" and v["preset"] == "clean_rap" and v["id"] not in {t["id"] for t in r["tracks"]}
    assert len({t["color"] for t in r2["tracks"] if t.get("color")}) == len([t for t in r2["tracks"] if t.get("color")])
    assert bl.tracks_op(r2["tracks"], "remove", {"id": "beat"})["error"] == "protected_track"
    assert bl.tracks_op(r2["tracks"], "remove", {"id": "vocal1"})["error"] == "protected_track"
    r3 = bl.tracks_op(r2["tracks"], "remove", {"id": "adlib"})
    assert "adlib" not in [t["id"] for t in r3["tracks"]]
    r4 = bl.tracks_op(r3["tracks"], "move", {"id": v["id"], "index": 0})
    assert r4["tracks"][0]["id"] == v["id"]
    ids = [t["id"] for t in r4["tracks"]][::-1]
    r5 = bl.tracks_op(r4["tracks"], "reorder", {"ids": ids})
    assert [t["id"] for t in r5["tracks"]] == ids
    r6 = bl.tracks_op(r5["tracks"], "rename", {"id": v["id"], "name": "Back"})
    assert next(t for t in r6["tracks"] if t["id"] == v["id"])["name"] == "Back"
    assert json.dumps(tr, sort_keys=True) == before        # girdi listesi degismez (yan etkisiz)
    many = [dict(t) for t in tr]
    for _ in range(30):
        x = bl.tracks_op(many, "add", {"role": "vocal"})
        if not x["ok"]:
            assert x["error"] == "too_many_tracks"
            break
        many = x["tracks"]
    assert len(many) == bl.MAX_TRACKS


def test_added_track_in_bounce_and_order_invariant(bs, tmp_path):
    """Yeni kanal bounce'a girer, silinince cikar; kanal sirasi ciktiyi degistirmez."""
    from app.core import beat_layers as bl
    proj = bs.create_project("Kanal")["project"]
    beat = _dc(bs, tmp_path / "b.wav", 2.0, 0.1)
    extra = _dc(bs, tmp_path / "e.wav", 1.0, 0.2)
    for t in proj["tracks"]:
        t["fx"] = []
        t["volume_db"] = 0.0
        t["pan"] = 0.0
        if t["id"] == "beat":
            t["clips"] = [_clip("b", beat, 0.0, 2.0)]
    r = bl.tracks_op(proj["tracks"], "add", {"role": "fx", "name": "Ekstra"})
    proj["tracks"] = r["tracks"]
    nt = proj["tracks"][-1]
    nt["clips"] = [_clip("e", extra, 0.5, 1.0)]
    bs.save_project(proj)

    def mix(name):
        out = tmp_path / name
        res = bs.render_mixdown(proj["id"], str(out), target_lufs=0.0)
        assert res["ok"], res
        return bs._read_audio_np(str(out), SR)[0]
    with_new = mix("mix_a.wav")
    i = int(1.0 * SR)
    assert with_new[i, 0] == pytest.approx((0.1 + 0.2) * np.sqrt(0.5), abs=2e-3)
    proj["tracks"] = bl.tracks_op(proj["tracks"], "reorder", {"ids": [t["id"] for t in proj["tracks"]][::-1]})["tracks"]
    bs.save_project(proj)
    reordered = mix("mix_b.wav")
    assert np.allclose(with_new, reordered, atol=1e-4)
    proj["tracks"] = bl.tracks_op(proj["tracks"], "remove", {"id": nt["id"]})["tracks"]
    bs.save_project(proj)
    without = mix("mix_c.wav")
    assert without[i, 0] == pytest.approx(0.1 * np.sqrt(0.5), abs=2e-3)


def test_layer_recording_track_roundtrip(bs, tmp_path):
    """Katman kanali olusturulup kaydedilince proje kalici; apply_recording yeni kanala klip yazar."""
    from app.core import beat_layers as bl
    proj = bs.create_project("Katman")["project"]
    r = bl.prepare_layer(proj["tracks"], "double", "vocal1", 0.0, 2.0, presets=bs.VOCAL_PRESETS)
    proj["tracks"] = r["tracks"]
    bs.save_project(proj)
    rec = _dc(bs, tmp_path / "rec.wav", 2.0)
    res = bs.apply_recording(proj["id"], r["track_id"], str(rec), {"mode": "linear", "anchor_u": 0.0, "anchor_wall": 100.0,
                                                                  "keep_from": 0.0}, 100.0)
    assert res["ok"], res
    lt = next(t for t in bs.load_project(proj["id"])["project"]["tracks"] if t["id"] == r["track_id"])
    assert lt["layer"] == "double" and len(lt["clips"]) == 1


# ---------------- 1d-2: kulaklikta efektli dinleme ----------------
def test_monitor_latency_math_and_warning():
    from app.core import beat_monitor as bm
    assert bm.latency_ms(128, 48000, (0.004, 0.006)) == pytest.approx(12.7)
    assert bm.latency_ms(256, 48000, 0.01) == pytest.approx(15.3)
    assert bm.latency_ms(128, 48000, None) == pytest.approx(2.7)
    ok = bm.latency_report(12.7)
    assert not ok["warn"] and ok["message"] == "İzleme gecikmesi: 13 ms"
    bad = bm.latency_report(23.4)
    assert bad["warn"] and "Gecikme yüksek, kuru dinleme önerilir" in bad["message"]
    assert not bm.latency_report(20.0)["warn"] and bm.latency_report(20.1)["warn"]


def test_monitor_chain_and_tune_vst():
    from app.core import beat_monitor as bm
    ch = bm.monitor_chain(True, False)
    assert [f["type"] for f in ch["fx"]] == ["reverb"] and ch["notes"] == []
    ch = bm.monitor_chain(True, True, None)
    assert "tune_unavailable" in ch["notes"] and [f["type"] for f in ch["fx"]] == ["reverb"]
    vst = bm.find_tune_vst([{"name": "Kotelnikov", "path": "a"}, {"name": "Graillon 3", "path": "/v/G.vst3"}])
    assert vst["path"] == "/v/G.vst3"
    ch = bm.monitor_chain(False, True, vst)
    assert ch["fx"] == [{"type": "vst3", "path": "/v/G.vst3", "name": "Graillon 3"}]
    assert bm.monitor_chain(False, False)["fx"] == []


def test_room_air_block_size_invariant_and_wet():
    from app.core import beat_monitor as bm
    x = np.random.default_rng(0).standard_normal(48000).astype("float32") * 0.1
    a, b = bm.RoomAir(48000, max_block=256), bm.RoomAir(48000, max_block=256)
    ya = np.concatenate([a.process(x[i:i + 128]) for i in range(0, 47872, 128)])
    yb = np.concatenate([b.process(x[i:i + 256]) for i in range(0, 47872, 256)])
    assert np.allclose(ya, yb, atol=1e-6)
    imp = np.zeros(4096, dtype="float32")
    imp[0] = 1.0
    ra = bm.RoomAir(48000, wet=0.1, max_block=256)
    y = np.concatenate([ra.process(imp[i:i + 256]) for i in range(0, 4096, 256)])
    assert y[0, 0] == pytest.approx(1.0)                   # kuru sinyal aynen
    assert np.abs(y[1:, 0]).max() > 0.0 and np.abs(y[1:, 0]).max() < 0.1   # hafif kuyruk
    assert not np.allclose(y[1:, 0], y[1:, 1])                             # sag/sol farkli (genislik)
    with pytest.raises(ValueError):
        bm.RoomAir(48000, max_block=128).process(np.zeros(8192, dtype="float32"))


class _FakeStream:
    last = None

    def __init__(self, **kw):
        self.kw = kw
        self.latency = (0.005, 0.008)
        self.started = False
        _FakeStream.last = self

    def start(self):
        self.started = True

    def stop(self):
        self.started = False

    def close(self):
        pass


def _fake_sd(fail=False):
    m = types.ModuleType("sounddevice")

    class S(_FakeStream):
        def __init__(self, **kw):
            if fail:
                raise RuntimeError("Invalid device")
            super().__init__(**kw)
    m.Stream = S
    m.InputStream = S
    return m


def test_monitor_start_stop_with_fake_sounddevice(monkeypatch):
    from app.core import beat_fx, beat_monitor as bm
    monkeypatch.setattr(beat_fx, "_PB_OVERRIDE", False)          # pedalboard yok -> numpy oda havasi
    monkeypatch.setitem(sys.modules, "sounddevice", _fake_sd())
    mon = bm.Monitor()
    r = mon.start(device_id=-1, blocksize=128, reverb=True)
    assert r["ok"] and r["running"] and r["engine"] == "numpy"
    assert r["latency_ms"] == pytest.approx(15.7) and not r["warn"]
    kw = _FakeStream.last.kw
    assert kw["blocksize"] == 128 and kw["channels"] == (1, 2) and kw["latency"] == "low"
    # geri cagri: tap HAM girisi alir, cikis islenmis stereo
    got = []
    mon.add_tap(lambda ind, fr: got.append(ind.copy()))
    ind = np.full((128, 1), 0.5, dtype="float32")
    out = np.zeros((128, 2), dtype="float32")
    mon._callback(ind, out, 128, None, None)
    assert np.array_equal(got[0], ind) and out[0, 0] == pytest.approx(0.5) and out.shape == (128, 2)
    assert mon.stop()["error"] == "recording_active"           # kayit tap'i varken kapanmaz
    assert mon.stop(force=True)["ok"] and not mon.running
    r = mon.start(blocksize=999, reverb=False)
    assert r["blocksize"] == bm.DEFAULT_BLOCK and r["engine"] == "dry"
    mon.stop()


def test_monitor_errors_keep_feature_passive(monkeypatch):
    import builtins
    from app.core import beat_monitor as bm
    monkeypatch.setitem(sys.modules, "sounddevice", _fake_sd(fail=True))
    mon = bm.Monitor()
    r = mon.start()
    assert not r["ok"] and r["error"] == "stream_failed" and "Invalid device" in r["detail"] and not mon.running
    real = builtins.__import__

    def fake(name, *a, **kw):
        if name == "sounddevice":
            raise ImportError("yok")
        return real(name, *a, **kw)
    monkeypatch.delitem(sys.modules, "sounddevice")
    monkeypatch.setattr(builtins, "__import__", fake)
    r = mon.start()
    assert not r["ok"] and r["error"] == "sounddevice_missing" and not mon.running


def test_recorder_taps_monitor_raw_input(monkeypatch):
    """Izleme acikken PC kaydedici mikrofonu ikinci kez acmaz; kayda HAM blok girer (efekt yalniz kulaklikta)."""
    from app.core import beat_fx, beat_monitor as bm, kami_booth
    monkeypatch.setattr(beat_fx, "_PB_OVERRIDE", False)
    monkeypatch.setitem(sys.modules, "sounddevice", _fake_sd())
    mon = bm.Monitor()
    monkeypatch.setattr(bm, "MONITOR", mon)
    assert mon.start(reverb=True)["ok"]
    rec = kami_booth.PcRecorder()
    r = rec.start("", "", None)
    assert r["ok"] and r.get("tapped") and rec._stream is None
    ind = np.linspace(-0.5, 0.5, 128, dtype="float32").reshape(-1, 1)
    out = np.zeros((128, 2), dtype="float32")
    mon._callback(ind, out, 128, None, None)
    assert np.array_equal(rec._chunks[0], ind)
    rec._close_stream()
    assert mon.status()["taps"] == 0
    mon.stop()


# ---------------- 1e-1: lisans cikarimi + raf ----------------
LIC_CASES = [
    ("[FREE] Travis Scott Type Beat - \"Night\" (prod. Kami Beats)",
     "FREE for non-profit use only. Purchase a lease for commercial use: https://beatstars.com/x\n140 BPM | Key: F#m",
     "free_nonprofit", "prod. by Kami Beats"),
    ("Dark Trap Beat", "Free for profit! Just credit me: (prod. by DJ Ali)", "credit_required", "prod. by DJ Ali"),
    ("Hard Beat 150 BPM", "Free for profit use. Royalty free.", "free_profit", "prod. by Up"),
    ("Drill Beat | prod. by Zed", "Buy this beat (untagged): https://airbit.com/zed", "lease_required", "prod. by Zed"),
    ("Chill beat", "Use it, but you must credit the producer.", "credit_required", "prod. by Up"),
    ("Random video", "just a vlog", "unknown", "prod. by Up"),
    ("[FREE] Old School Beat", "", "free_nonprofit", "prod. by Up"),
    ("Beat", "Ticari kullanım serbest, kredi verin.", "credit_required", "prod. by Up"),
]


@pytest.mark.parametrize("title,desc,kind,credit", LIC_CASES)
def test_infer_license_kinds(title, desc, kind, credit):
    from app.core import beat_shelf as sh
    lic = sh.infer_license(desc, title, "Up")
    assert lic["kind"] == kind, lic
    assert lic["credit_text"] == credit
    assert lic["guessed"] and not lic["user_set"]
    if kind != "unknown":
        assert lic["evidence"] and len(lic["evidence"]) == len(set(lic["evidence"]))


def test_parse_bpm_key_and_producer():
    from app.core import beat_shelf as sh
    assert sh.parse_bpm_key("140 BPM | Key: F#m") == {"bpm": 140.0, "key": "F#m"}
    assert sh.parse_bpm_key("BPM: 92 · C# minor") == {"bpm": 92.0, "key": "C#m"}
    assert sh.parse_bpm_key("Eb Major beat") == {"bpm": 0.0, "key": "Eb"}
    assert sh.parse_bpm_key("I am a beat 2024") == {"bpm": 0.0, "key": ""}
    assert sh.guess_producer("Beat (Prod. By Mali)") == "Mali"
    assert sh.guess_producer("No Tag", "", "Kanal") == "Kanal"
    assert sh.guess_producer("Beat", "the producer is great", "U") == "U"


def test_shelf_download_persist_filter_update(bs, tmp_path):
    from app.core import beat_shelf as sh
    beat = _dc(bs, tmp_path / "dl.wav", 1.0)
    calls = {}

    def info(url):
        calls["info"] = url
        return {"title": "[FREE] Night Type Beat (prod. Kami)", "uploader": "KamiCh", "duration": 1.0, "url": url,
                "description": "Free for non-profit. Lease: beatstars.com/kami\n140 BPM Key: Am", "tags": []}

    def dl(url, prog):
        prog(phase="downloading", downloaded=50, size=100)
        calls["dl"] = url
        return str(beat)
    assert sh.add_from_url("ftp://x")["error"] == "bad_url"
    r = sh.add_from_url("https://youtu.be/abc", info_fn=info, download_fn=dl, analyze=False)
    assert r["ok"] and calls == {"info": "https://youtu.be/abc", "dl": "https://youtu.be/abc"}
    it = r["item"]
    assert it["bpm"] == 140.0 and it["key"] == "Am" and it["producer"] == "Kami"
    assert it["license"]["kind"] == "free_nonprofit" and it["file"] == str(beat)
    assert sh.progress()["phase"] == "done"
    data = json.loads(sh.shelf_path().read_text(encoding="utf-8"))
    assert data["items"][0]["id"] == it["id"]
    assert set(it) >= {"id", "title", "producer", "source_url", "file", "bpm", "key", "license", "note", "added_at"}
    # ayni URL tekrar -> guncelleme (cift kayit yok)
    sh.add_from_url("https://youtu.be/abc", info_fn=info, download_fn=dl, analyze=False)
    assert len(sh.load_shelf()) == 1
    sh.add_item({"title": "Drill", "producer": "Zed", "source_url": "u2", "file": str(beat), "bpm": 150, "key": "C#m",
                 "license": {"kind": "lease_required"}})
    assert [i["title"] for i in sh.list_items(bpm_min=145)["items"]] == ["Drill"]
    assert [i["title"] for i in sh.list_items(bpm_max=145)["items"]] == [it["title"]]
    assert [i["title"] for i in sh.list_items(key="c#M")["items"]] == ["Drill"]
    assert [i["title"] for i in sh.list_items(license_kind="free_nonprofit")["items"]] == [it["title"]]
    assert [i["title"] for i in sh.list_items(query="zed")["items"]] == ["Drill"]
    assert sh.list_items()["items"][0]["exists"]
    u = sh.update_item(it["id"], {"license": {"kind": "free_profit", "credit_text": "prod. by Kami"}, "bpm": "141.5"})
    assert u["ok"] and u["item"]["license"]["kind"] == "free_profit" and u["item"]["license"]["user_set"]
    assert not u["item"]["license"]["guessed"] and u["item"]["bpm"] == 141.5
    assert sh.remove_item(it["id"])["ok"] and len(sh.load_shelf()) == 1


def test_shelf_errors(bs):
    from app.core import beat_shelf as sh

    def bad_info(url):
        raise RuntimeError("Video unavailable")
    r = sh.add_from_url("https://youtu.be/x", info_fn=bad_info)
    assert not r["ok"] and r["error"] == "info_failed" and sh.progress()["phase"] == "error"
    r = sh.add_from_url("https://youtu.be/x", info_fn=lambda u: {"title": "t", "url": u}, download_fn=lambda u, p: "")
    assert r["error"] == "download_failed"


def test_shelf_to_project_meta_and_release_warnings(bs, tmp_path, monkeypatch):
    from app.core import beat_shelf as sh, kami_beat
    monkeypatch.setattr(kami_beat, "analyze_bpm", lambda p, *a, **k: 0.0)
    monkeypatch.setattr(kami_beat, "detect_key", lambda p, *a, **k: {})
    beat = _dc(bs, tmp_path / "beat.wav", 2.0, 0.1)
    it = sh.add_item({"title": "Night", "producer": "Kami", "source_url": "u", "file": str(beat), "bpm": 140, "key": "Am",
                      "license": sh.infer_license("Free for non-profit use only", "Night (prod. Kami)")})
    proj = bs.create_project("Raf")["project"]
    r = sh.add_to_project(proj["id"], it["id"])
    assert r["ok"]
    p = bs.load_project(proj["id"])["project"]
    bt = next(t for t in p["tracks"] if t["role"] == "beat")
    assert bt["clips"] and bt["clips"][0]["path"] == str(beat)
    assert p["beat_meta"]["shelf_id"] == it["id"] and p["beat_meta"]["credit_text"] == "prod. by Kami"
    assert p["bpm"] == 140.0 and p["key"] == "Am"
    w = sh.release_warnings(p)
    assert w[0]["kind"] == "free_nonprofit" and w[0]["level"] == "block" and "ticari kullanıma kapalı" in w[0]["message"]
    # bounce sonucunda uyari doner
    res = bs.render_mixdown(proj["id"], str(tmp_path / "out.wav"), target_lufs=0.0)
    assert res["ok"] and [x["kind"] for x in res["release_warnings"]][0] == "free_nonprofit"
    # lisans turlerine gore tetikleme
    for kind, want in (("lease_required", ["lease_required"]), ("credit_required", ["credit"]),
                       ("free_profit", ["credit"]), ("unknown", ["unknown"])):
        p2 = dict(p, beat_meta=dict(p["beat_meta"], license={"kind": kind, "credit_text": "prod. by Kami"}))
        got = sh.release_warnings(p2)
        assert [x["kind"] for x in got] == want, (kind, got)
        if kind == "credit_required":
            assert got[0]["level"] == "warn" and got[0]["credit_text"] == "prod. by Kami"
        if kind == "lease_required":
            assert "lisans gerekli" in got[0]["message"]
    # beat kanalinda raftaki dosya artik yoksa (kullanici kendi beat'ini koydu) uyari yok
    p3 = json.loads(json.dumps(p))
    for t in p3["tracks"]:
        if t["role"] == "beat":
            t["clips"] = [dict(t["clips"][0], path=str(tmp_path / "baska.wav"))]
    assert sh.release_warnings(p3) == []
    assert sh.release_warnings({"tracks": []}) == []
    assert sh.add_to_project(proj["id"], "yok")["error"] == "not_found"


# ---------------- 1e-2: fikir rafi ----------------
def test_ideas_persist_link_and_add_to_project(bs, tmp_path):
    from app.core import beat_ideas as bi
    src = _dc(bs, tmp_path / "not.wav", 12.0, 0.2)
    r = bi.add_idea(str(src), "Nakarat fikri", "nakarat, melodi #gece", "ilk satira", source="file")
    assert r["ok"] and not r["long"]
    it = r["item"]
    assert Path(it["file"]).parent == bi.ideas_dir() and src.is_file()          # kopyalandi, kaynak duruyor
    assert it["tags"] == ["nakarat", "melodi", "gece"] and it["duration"] == pytest.approx(12.0, abs=0.05)
    assert it["peaks"] and it["link"] is None and it["source"] == "file"
    raw = _dc(bs, tmp_path / "pc_mic.wav", 5.0)
    r2 = bi.add_idea(str(raw), source="pc", move=True)
    assert r2["ok"] and not raw.exists() and r2["item"]["name"] == "Fikir 2"
    data = json.loads(bi.ideas_path().read_text(encoding="utf-8"))
    assert [i["id"] for i in data["items"]] == [r2["item"]["id"], it["id"]]
    assert [i["id"] for i in bi.list_ideas(tag="gece")["items"]] == [it["id"]]
    assert [i["id"] for i in bi.list_ideas(query="nakarat")["items"]] == [it["id"]]
    assert bi.list_ideas()["tags"] == ["gece", "melodi", "nakarat"]
    proj = bs.create_project("Fikir")["project"]
    assert bi.link_idea(it["id"], proj["id"], 3)["item"]["link"] == {"project": proj["id"], "line": 3}
    fp = bi.ideas_for_project(proj["id"])
    assert list(fp["lines"]) == ["3"] and fp["lines"]["3"][0]["id"] == it["id"]
    assert bi.list_ideas(project=proj["id"])["items"][0]["id"] == it["id"]
    res = bi.add_idea_to_project(proj["id"], it["id"], "vocal1", 4.0)
    assert res["ok"] and res["clip"]["start"] == pytest.approx(4.0) and res["take"]["label"].startswith("Fikir:")
    assert bi.link_idea(it["id"], "", -1)["item"]["link"] is None
    assert bi.update_idea(it["id"], {"name": "Yeni ad", "tags": "a,b"})["item"]["tags"] == ["a", "b"]
    f = it["file"]
    assert bi.remove_idea(it["id"])["ok"] and not Path(f).exists()
    assert bi.add_idea(str(tmp_path / "yok.wav"))["error"] == "not_found"
    long = _dc(bs, tmp_path / "uzun.wav", 40.0, 0.1)
    assert bi.add_idea(str(long))["long"]


def test_booth_upload_target_idea(bs, tmp_path):
    """iPhone Booth: hedef 'idea' iken yukleme fikir rafina gider, projeye dokunmaz; baslik ile kayit basina secim."""
    import http.client
    from app.core import beat_ideas as bi, kami_booth
    proj = bs.create_project("Booth")["project"]
    srv = kami_booth.BoothServer()
    st = srv.start(proj["id"], "vocal1", "idea")
    try:
        assert st["target"] == "idea"
        wav = _dc(bs, tmp_path / "ph.wav", 1.0).read_bytes()

        def post(extra):
            c = http.client.HTTPConnection("127.0.0.1", st["port"], timeout=10)
            c.request("POST", "/api/upload_wav", body=wav, headers={"Content-Type": "audio/wav", "X-Booth-Token": st["token"], **extra})
            resp = c.getresponse()
            return json.loads(resp.read().decode("utf-8"))
        j = post({"X-Booth-Name": "nakarat.wav"})
        assert j["ok"] and j["target"] == "idea" and j["idea"]["name"] == "nakarat" and j["idea"]["source"] == "iphone"
        assert len(bi.load_ideas()) == 1 and srv.status()["last_upload"]["target"] == "idea"
        p = bs.load_project(proj["id"])["project"]
        assert not next(t for t in p["tracks"] if t["id"] == "vocal1")["clips"]
        j2 = post({"X-Booth-Target": "track"})
        assert j2["ok"] and j2["target"] == "track" and j2["take"]
        p = bs.load_project(proj["id"])["project"]
        assert len(next(t for t in p["tracks"] if t["id"] == "vocal1")["clips"]) == 1
        srv.set_target(proj["id"], "vocal1", "track")
        assert srv.status()["target"] == "track"
    finally:
        srv.stop()


# ---------------- arayuz ----------------
def test_beat_1de_ui_js_syntax_and_hooks():
    node = shutil.which("node")
    if not node:
        pytest.skip("node yok")
    for name in ("beat-library.js", "beat.js", "beat-timeline.js"):
        p = subprocess.run([node, "--check", str(ROOT / "app/ui/web" / name)], capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, (name, p.stderr)
    html = (ROOT / "app/ui/web/beat.html").read_text(encoding="utf-8")
    for el in ("tlLayer", "tlAddTrack", "addTrackPop", "alignBar", "monOn", "monLat", "boothTarget", "pane-shelf",
               "pane-ideas", "shelfUrl", "ideaRec", "ideaDrop", "releaseBox", "beat-library.js"):
        assert el in html, el
    js = (ROOT / "app/ui/web/beat.js").read_text(encoding="utf-8")
    api_src = (ROOT / "app/ui/api.py").read_text(encoding="utf-8")
    lib = (ROOT / "app/ui/web/beat-library.js").read_text(encoding="utf-8")
    import re
    called = set(re.findall(r"api\(\)\?\.(beat_[a-z_]+|booth_[a-z_]+)", js + lib)) | set(re.findall(r'runJob\("([a-z_]+)"', js + lib))
    for name in called:
        assert f"def {name}(" in api_src, name
    from app.ui.api import Api
    for job in ("beat_shelf_add_url", "beat_layer_align", "beat_shelf_to_project", "beat_idea_to_project"):
        assert job in Api.JOB_METHODS
