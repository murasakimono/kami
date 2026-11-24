"""Kami Beat Asama 2a: tarz onayarlari (VST var/yok cozumleme, yogunluk, kullanici onayari, katman esleniği),
dinleme simulatoru profil tablosu (node), adlib hizli efektleri + klip pan render'i, referans seviye esleme ve
spektrum maddeleri (sentetik sinyal), efekt atmalari (bolge bolme + tail_sec ile kuyruk klip sonrasina tasar,
onizleme = bounce), ters reverb on-kabarmasi, JS <-> Python esdegerligi."""
from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SR = 48000
WEB = ROOT / "app" / "ui" / "web"

PLUGINS = [
    {"name": "TDR Nova", "path": "/vst/TDR Nova.vst3"},
    {"name": "MJUCjr", "path": "/vst/MJUCjr.vst3"},
    {"name": "OTT", "path": "/vst/OTT.vst3"},
    {"name": "ValhallaSupermassive", "path": "/vst/ValhallaSupermassive.vst3"},
    {"name": "T-De-Esser 2", "path": "/vst/T-De-Esser 2.vst3"},
    {"name": "Wider", "path": "/vst/Wider.vst3"},
    {"name": "IVGI2", "path": "/vst/IVGI2.vst3"},
    {"name": "Graillon 3", "path": "/vst/Graillon 3.vst3"},
    {"name": "Scotty", "path": "/vst/Scotty.vst3"},           # 'ott' alt dizgesi ama OTT degil
]
PARAMS = {"/vst/OTT.vst3": ["depth", "time", "in_gain", "out_gain"],
          "/vst/ValhallaSupermassive.vst3": ["mix", "delay_ms", "feedback", "width"],
          "/vst/Wider.vst3": ["width"]}


def lookup(path):
    return PARAMS.get(path, [])


@pytest.fixture()
def st(tmp_path, monkeypatch):
    from app.core import beat_style
    monkeypatch.setattr(beat_style, "settings_dir", lambda: (tmp_path / "set").mkdir(exist_ok=True) or tmp_path / "set")
    return beat_style


@pytest.fixture()
def fx(monkeypatch):
    from app.core import beat_fx
    monkeypatch.setattr(beat_fx, "_PB_OVERRIDE", False)          # bu ortamda pedalboard yok: numpy yedegi
    yield beat_fx
    monkeypatch.setattr(beat_fx, "_PB_OVERRIDE", None)


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


def _burst(n, amp=0.3):
    t = np.arange(n, dtype="float32")
    x = amp * np.sin(2 * np.pi * 330.0 * t / SR).astype("float32")
    return np.stack([x, x], axis=1)


# ---------------- 1. tarz onayarlari ----------------
def test_installed_map_matches_catalog(st):
    m = st.installed_map(PLUGINS)
    assert set(m) == {"nova", "mjuc", "ott", "supermassive", "tdeess", "wider", "ivgi", "graillon"}
    assert m["ott"]["name"] == "OTT"                              # 'Scotty' eslesmedi


def test_resolve_with_and_without_vst(st):
    with_v = st.resolve("hard", PLUGINS, 50, True, 140, lookup)
    types = [(f["type"], f.get("name")) for f in with_v["fx"]]
    assert ("vst3", "MJUCjr") in types and ("vst3", "TDR Nova") in types and ("vst3", "OTT") in types
    assert ("vst3", "T-De-Esser 2") in types and ("vst3", "IVGI2") in types
    ott = next(f for f in with_v["fx"] if f.get("name") == "OTT")
    assert ott["params"] == {"depth": pytest.approx(0.3)}         # bilinen parametre gercek listede ada gore eslesti
    sm = next(f for f in with_v["fx"] if f.get("name") == "Valhalla Supermassive")
    assert set(sm["params"]) == {"mix"}
    tune = next(f for f in with_v["fx"] if f.get("name") == "Graillon 3")
    assert tune["bypass"] is True                                  # ton duzeltme kapali eklenir
    assert with_v["vst_installed"] == with_v["vst_total"] == 7
    assert any("incelt" in n for n in with_v["notes"])            # parametresi bilinmeyen eklentiler icin not
    # hicbir eklenti yok -> tamamen yerlesik; ton duzeltmenin yerlesik karsiligi yok -> atlanir
    none = st.resolve("hard", [], 50, True, 140, lookup)
    assert all(f["type"] != "vst3" for f in none["fx"])
    assert [f["type"] for f in none["fx"]] == ["highpass", "deesser", "compressor", "peak", "distortion", "compressor",
                                               "reverb", "limiter"]
    assert none["vst_installed"] == 0 and any(s["engine"] == "skip" and s["role"] == "tune" for s in none["steps"])
    # eklenti kurulu ama "kurulu eklentileri kullan" kapali -> yerlesik
    off = st.resolve("hard", PLUGINS, 50, False, 140, lookup)
    assert [f["type"] for f in off["fx"]] == [f["type"] for f in none["fx"]]
    # parametre listesi okunamadi (pedalboard yok) -> eklenti varsayilan + not
    nolist = st.resolve("hard", PLUGINS, 50, True, 140, lambda p: None)
    assert "params" not in next(f for f in nolist["fx"] if f.get("name") == "OTT")
    assert any("OTT" in n and "incelt" in n for n in nolist["notes"])
    assert st.resolve("yok_boyle", PLUGINS)["error"] == "preset_not_found"


def test_all_presets_resolve_and_bpm_locked_delay(st):
    ids = [p["id"] for p in st.PRESETS]
    assert {"temiz_trap", "karanlik_drill", "hyperpop", "boom_bap", "lofi", "phonk", "disstrack", "hard", "soft",
            "storytelling", "sinematik", "telefon_radyo"} <= set(ids)
    for pid in ids:
        for plugs in ([], PLUGINS):
            r = st.resolve(pid, plugs, 50, True, 90, lookup)
            assert r["ok"] and r["fx"], pid
            from app.core import beat_fx
            for f in r["fx"]:
                assert f["type"] == "vst3" or f["type"] in beat_fx.FX_SCHEMA
    soft = st.resolve("soft", [], 50, True, 90)
    d = next(f for f in soft["fx"] if f["type"] == "delay")
    assert d["delay_seconds"] == pytest.approx(60 / 90) and d["sync"] == "1/4"
    assert st.delay_time(120, "1/8") == 0.25 and st.delay_time(120, "1/8d") == 0.375 and st.delay_time(0, "1/4") == 0.5
    assert st.delay_time(20, "1/4") == 2.0                        # sema siniri
    lp = st.list_presets(PLUGINS)["presets"]
    hard = next(p for p in lp if p["id"] == "hard")
    assert (hard["vst_installed"], hard["vst_total"]) == (7, 7) and "OTT" in hard["plugins"]
    assert next(p for p in st.list_presets([])["presets"] if p["id"] == "hard")["vst_installed"] == 0
    assert all(p["desc"] and p["why"] for p in lp if not p["user"])


def test_intensity_scaling(st):
    c = {"type": "compressor", "threshold_db": -20.0, "ratio": 5.0, "attack_ms": 5.0, "release_ms": 80.0}
    assert st.scale_fx(c, 50) == pytest.approx(c) or st.scale_fx(c, 50)["ratio"] == 5.0
    lo, hi = st.scale_fx(c, 0), st.scale_fx(c, 100)
    assert lo["ratio"] == 1.0 and lo["threshold_db"] == -10.0
    assert hi["ratio"] == 9.0 and hi["threshold_db"] == -30.0
    v = {"type": "reverb", "room_size": 0.5, "wet_level": 0.2}
    assert st.scale_fx(v, 100)["wet_level"] == pytest.approx(0.4) and st.scale_fx(v, 0)["wet_level"] == 0.0
    assert st.scale_fx({"type": "reverb", "wet_level": 0.8}, 100)["wet_level"] == 1.0      # sema sinirinda kirpilir
    assert st.scale_fx({"type": "delay", "mix": 0.2}, 75)["mix"] == pytest.approx(0.3)
    assert st.scale_fx({"type": "distortion", "drive_db": 6.0}, 25)["drive_db"] == pytest.approx(3.0)
    hp = {"type": "highpass", "cutoff_hz": 100.0}
    assert st.scale_fx(hp, 0) == hp and st.scale_fx(hp, 100) == hp                           # EQ dokunulmaz
    vs = {"type": "vst3", "path": "x", "params": {"mix": 0.2, "decay": 0.5}}
    assert st.scale_fx(vs, 100)["params"] == {"mix": pytest.approx(0.4), "decay": 0.5}
    a, b = st.resolve("soft", [], 50), st.resolve("soft", [], 100)
    ra, rb = (next(f for f in x["fx"] if f["type"] == "reverb") for x in (a, b))
    assert rb["wet_level"] == pytest.approx(min(1.0, ra["wet_level"] * 2))


def test_user_presets_save_load_delete(st):
    assert st.load_user_presets() == []
    chain = [{"type": "highpass", "cutoff_hz": 120.0}, {"type": "reverb", "wet_level": 0.3}]
    r = st.save_user_preset("Benim Zincir", chain, "deneme", denoise=True)
    assert r["ok"] and r["preset"]["id"].startswith("u_")
    assert (st.settings_dir() / "user_presets.json").is_file()
    st.save_user_preset("İkinci", [{"type": "gain", "gain_db": 2.0}])
    lp = st.list_presets([])["presets"]
    assert [p["name"] for p in lp[:2]] == ["İkinci", "Benim Zincir"] and lp[0]["user"] and not lp[2]["user"]
    again = st.save_user_preset("benim zincir", [{"type": "gain", "gain_db": 1.0}])      # ayni ad -> uzerine yazar
    assert again["preset"]["id"] == r["preset"]["id"] and len(st.load_user_presets()) == 2
    res = st.resolve(r["preset"]["id"], [], 50)
    assert res["ok"] and res["fx"] == [{"type": "gain", "gain_db": 1.0}] and res["name"] == "benim zincir"
    assert st.save_user_preset("", chain)["error"] == "name_required"
    assert st.save_user_preset("x", [])["error"] == "empty_chain"
    assert st.delete_user_preset(r["preset"]["id"])["ok"] and len(st.load_user_presets()) == 1
    assert st.delete_user_preset("u_yok")["error"] == "not_found"


def test_layer_counterparts_and_suggestions(st):
    main = st.resolve("hard", PLUGINS, 50, True, 120, lookup)
    dbl = st.resolve("hard:double", PLUGINS, 50, True, 120, lookup)
    assert dbl["name"] == "Hard Double" and dbl["kind"] == "double"
    hp = lambda r: next(f for f in r["fx"] if f["type"] == "highpass")["cutoff_hz"]
    assert hp(dbl) == hp(main) + 40.0
    assert any(f.get("name") == "Wider" for f in dbl["fx"])        # genislik (double kanallarinda)
    sm_main = next(f for f in main["fx"] if f.get("name") == "Valhalla Supermassive")["params"]["mix"]
    sm_dbl = next(f for f in dbl["fx"] if f.get("name") == "Valhalla Supermassive")["params"]["mix"]
    assert sm_dbl == pytest.approx(sm_main * 0.6)
    ad = st.resolve("storytelling:adlib", [], 50, True, 120)
    types = [f["type"] for f in ad["fx"]]
    assert "lowpass" in types and "delay" in types and hp(ad) >= 220.0
    ch = st.resolve("soft:chant", [], 50, True, 120)
    assert "chorus" in [f["type"] for f in ch["fx"]] and ch["name"] == "Soft Chant"
    tracks = [{"id": "vocal1", "name": "Ana Vokal"}, {"id": "dbl", "name": "Double 1", "layer": "double", "layer_of": "vocal1"},
              {"id": "ad", "name": "Adlib", "layer": "adlib", "layer_of": "vocal1"},
              {"id": "x", "name": "Başka", "layer": "double", "layer_of": "vocal2"}]
    sug = st.layer_suggestions(tracks, "vocal1", "hard")
    assert [(s["track_id"], s["preset_id"], s["name"]) for s in sug] == [("dbl", "hard:double", "Hard Double"),
                                                                       ("ad", "hard:adlib", "Hard Adlib")]
    assert st.layer_suggestions(tracks, "dbl", "hard") == [] and st.layer_suggestions(tracks, "vocal1", "hard:double") == []


# ---------------- 2. dinleme simulatoru (JS saf fonksiyon) ----------------
def _node():
    node = shutil.which("node")
    if not node:
        pytest.skip("node yok")
    return node


def _run_js(tmp_path, files, body):
    runner = tmp_path / "run.js"
    runner.write_text("global.window = {};\n" + "".join(f"require({json.dumps(str(WEB / f))});\n" for f in files)
                      + "const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));\n" + body, encoding="utf-8")
    return runner


def test_device_profiles_table(tmp_path):
    node = _node()
    runner = _run_js(tmp_path, ["beat-sim.js"], """
const S = window.BeatSim;
const out = {};
for (const id of [...S.ORDER, "yok"]) out[id] = S.profile(id);
out._w0 = S.widthMatrix(0); out._w1 = S.widthMatrix(1); out._w5 = S.widthMatrix(0.5);
const c = S.shaperCurve(0.35, 101); out._shape = [c[0], c[50], c[100], c[75]];
process.stdout.write(JSON.stringify(out));""")
    p = subprocess.run([node, str(runner)], input="{}", capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    P = json.loads(p.stdout)
    nodes = lambda k, t=None, typ=None: [n for n in P[k]["nodes"] if (t is None or n["t"] == t) and (typ is None or n.get("type") == typ)]
    assert P["normal"]["nodes"] == [] and P["yok"]["id"] == "normal"
    # telefon: HPF ~400, 2-4 kHz tepe, mono, doygunluk + sinirlama
    assert all(350 <= n["f"] <= 450 for n in nodes("phone", typ="highpass")) and nodes("phone", typ="highpass")
    pk = nodes("phone", typ="peaking")[0]
    assert 2000 <= pk["f"] <= 4000 and pk["g"] > 0
    assert nodes("phone", "width")[0]["w"] == 0 and nodes("phone", "shaper") and nodes("phone", "comp")
    # AirPods: hafif bas yukseltme, tiz hafif dusus
    assert nodes("airpods", typ="lowshelf")[0]["g"] > 0 and nodes("airpods", typ="highshelf")[0]["g"] < 0
    # araba: bas 60-100 Hz, kabin rezonansi ~150 Hz, hafif mono yonelim
    assert 60 <= nodes("car", typ="lowshelf")[0]["f"] <= 100 and nodes("car", typ="lowshelf")[0]["g"] > 0
    assert 130 <= nodes("car", typ="peaking")[0]["f"] <= 170 and 0 < nodes("car", "width")[0]["w"] < 1
    # laptop: HPF ~200, ince
    assert all(180 <= n["f"] <= 220 for n in nodes("laptop", typ="highpass"))
    assert P["mono"]["nodes"] == [{"t": "width", "w": 0}]
    # club: alt bas +, ust orta hafif -
    assert nodes("club", typ="lowshelf")[0]["g"] > 0 and nodes("club", typ="peaking")[0]["g"] < 0
    assert P["_w0"] == {"a": 0.5, "b": 0.5} and P["_w1"] == {"a": 1, "b": 0} and P["_w5"] == {"a": 0.75, "b": 0.25}
    assert P["_shape"][0] == pytest.approx(-1) and P["_shape"][2] == pytest.approx(1) and abs(P["_shape"][1]) < 1e-6
    assert all(P[k]["badge"] for k in P if not k.startswith("_") and k not in ("normal", "yok"))


def test_simulator_only_affects_listening_not_bounce():
    """Simulator Python render yoluna hic girmez: beat_studio/beat_fx'te 'listen' / simulator alani yok."""
    src = (ROOT / "app/core/beat_studio.py").read_text(encoding="utf-8")
    assert "BeatSim" not in src and "listen" not in src.lower().replace("listen_", "")
    tl = (WEB / "beat-timeline.js").read_text(encoding="utf-8")
    assert "Out.mixOut" in tl and "pan.connect(Out.mixOut)" in tl and "Eng.metroGain.connect(ac.destination)" in tl


# ---------------- 3. adlib hizli efektleri + klip pan'i ----------------
def test_quick_fx_recipes(st):
    ph = st.quick_fx("phone")
    assert ph["mode"] == "append" and [f["type"] for f in ph["fx"]] == ["highpass", "lowpass", "peak", "distortion"]
    assert st.quick_fx("high")["fx"] == [{"type": "pitchshift", "semitones": 4.0}]
    assert st.quick_fx("low")["fx"] == [{"type": "pitchshift", "semitones": -4.0}]
    wh = st.quick_fx("whisper")
    assert [f["type"] for f in wh["fx"]][0] == "highpass" and "reverb" in [f["type"] for f in wh["fx"]] and wh["tail_sec"] > 0
    assert st.quick_fx("autopan")["mode"] == "autopan"
    et = st.quick_fx("echo_tail", 100, "1/8")
    assert et["mode"] == "echo_tail" and et["fx"][0]["delay_seconds"] == pytest.approx(0.3) and et["region_sec"] == pytest.approx(0.6)
    td = st.quick_fx("throw_delay", 120, "1/8d")
    assert td["fx"][0]["delay_seconds"] == 0.375 and td["tail_sec"] == st.delay_tail(0.375, 0.45) and td["tail_sec"] > 3
    assert st.quick_fx("throw_reverse")["head_sec"] > 0 and st.quick_fx("throw_reverb")["tail_sec"] > 0
    assert st.quick_fx("bilinmeyen")["ok"] is False
    from app.core import beat_fx
    for k in list(st.ADLIB_KINDS) + ["throw_" + t for t in st.THROW_KINDS]:
        for f in st.quick_fx(k, 120)["fx"]:
            assert f["type"] in beat_fx.FX_SCHEMA


def test_apply_adlib_append_and_autopan(st):
    clips = [_clip("b", "/v.wav", 3.0, 0.0, 1.0), _clip("a", "/v.wav", 1.0, 0.0, 1.0, fx=[{"type": "gain", "gain_db": 1.0}]),
             _clip("c", "/v.wav", 5.0, 0.0, 1.0), _clip("o", "/v.wav", 7.0, 0.0, 1.0)]
    r = st.apply_adlib(clips, ["a", "b", "c"], st.quick_fx("whisper"))
    out = {c["id"]: c for c in r["clips"]}
    assert [f["type"] for f in out["a"]["fx"]][0] == "gain" and len(out["a"]["fx"]) == 5
    assert out["a"]["tail_sec"] == 0.6 and "fx" not in out["o"] and clips[1]["fx"] == [{"type": "gain", "gain_db": 1.0}]
    p = st.apply_adlib(clips, ["a", "b", "c"], st.quick_fx("autopan"))
    pans = {c["id"]: c.get("pan") for c in p["clips"]}
    assert pans == {"a": -0.5, "b": 0.5, "c": -0.5, "o": None}     # baslangic sirasina gore donusumlu
    st2 = [_clip("x", "/1.wav", 0.0, 0.0, 1.0, stack_id="s"), _clip("y", "/2.wav", 0.0, 0.0, 1.0, stack_id="s", stack_active=True),
           _clip("z", "/v.wav", 2.0, 0.0, 1.0)]
    q = {c["id"]: c["pan"] for c in st.alternate_pan(st2, ["x", "y", "z"], 0.4)}
    assert q == {"x": -0.4, "y": -0.4, "z": 0.4}                   # deste uyeleri ayni pan


def test_stereo_pan_matches_w3c_and_render(bs, fx):
    x = np.stack([np.full(4, 0.4, "float32"), np.full(4, 0.2, "float32")], axis=1)
    assert np.array_equal(bs.stereo_pan(x, 0.0), x)
    r = bs.stereo_pan(x, 0.5)
    a = 0.5 * math.pi / 2
    assert r[0, 0] == pytest.approx(0.4 * math.cos(a)) and r[0, 1] == pytest.approx(0.2 + 0.4 * math.sin(a))
    l = bs.stereo_pan(x, -1.0)
    assert l[0, 0] == pytest.approx(0.6) and l[0, 1] == pytest.approx(0.0, abs=1e-7)
    cache = {"/v.wav": np.full((SR, 2), 0.25, dtype="float32")}
    tr = {"id": "ad", "fx": [], "clips": [_clip("a", "/v.wav", 0.0, 0.0, 0.5, pan=-0.5), _clip("b", "/v.wav", 0.5, 0.0, 0.5, pan=0.5)]}
    out = bs.render_track_audio(tr, SR, cache)
    m = int(0.25 * SR)
    s = math.sin(0.25 * math.pi)
    assert out[m, 0] == pytest.approx(0.25 + 0.25 * math.cos(0.25 * math.pi)) and out[m, 1] == pytest.approx(0.25 * s)
    assert out[SR // 2 + m, 0] == pytest.approx(0.25 * math.cos(0.25 * math.pi)) and out[SR // 2 + m, 1] > out[SR // 2 + m, 0]
    # pan alani preview anahtarina girer (efektli onizleme yeniden islenir)
    tr2 = json.loads(json.dumps(tr)); tr2["clips"][0]["pan"] = 0.2
    assert bs.preview_key(tr, 0, 1) != bs.preview_key(tr2, 0, 1)


def test_normalize_pan_tail_clamp():
    from app.core import beat_clips as bc
    c = bc.normalize(_clip("a", "/v.wav", 0, 0, 1, pan=3, tail_sec=40, head_sec=-2))
    assert (c["pan"], c["tail_sec"], c["head_sec"]) == (1.0, bc.TAIL_MAX, 0.0)
    assert "pan" not in bc.normalize(_clip("a", "/v.wav", 0, 0, 1))


# ---------------- 4. referans A/B ----------------
def test_level_match(bs):
    from app.core import beat_reference as br
    m = br.level_match(-9.7, -12.0)
    assert m["gain_db"] == -2.3 and m["diff_lu"] == 2.3 and m["text"] == "Referans 2.3 LU daha yüksek, eşitlendi."
    q = br.level_match(-16.0, -12.0)
    assert q["gain_db"] == 4.0 and "daha düşük" in q["text"]
    assert "zaten yakın" in br.level_match(-12.2, -12.0)["text"]
    assert br.level_match(10.0, -40.0)["gain_db"] == -24.0
    assert br.level_match(None, -12.0)["ok"] is False


def _tone(freqs, secs=2.0, amp=0.1, seed=0):
    t = np.arange(int(secs * SR)) / SR
    x = sum(amp * np.sin(2 * np.pi * f * t) for f in freqs).astype("float32")
    return np.stack([x, x], axis=1)


def test_band_profile_and_spectrum_notes():
    from app.core import beat_reference as br
    mix = _tone([120, 900, 3000])
    ref = _tone([120, 900, 3000]) + _tone([8000], amp=0.1)          # referans 6-10 kHz'de fazladan enerji
    pm, pr = br.band_profile(mix), br.band_profile(ref)
    assert set(pm) == {"low", "mid", "highmid", "bright", "air"}
    assert pr["bright"] - pm["bright"] > 10
    notes = br.compare_spectra(pr, pm)
    assert notes[0]["band"] == "bright" and notes[0]["text"].startswith("Referans daha parlak (+") and "6-10 kHz" in notes[0]["text"]
    assert 1 <= len(notes) <= 3
    # ses seviyesinden bagimsiz (oranlar)
    assert br.band_profile(mix * 0.25) == pytest.approx(pm, abs=0.05)
    assert br.compare_spectra(pm, br.band_profile(mix * 3.0))[0]["text"].startswith("Ton dengesi referansa yakın")
    dark = br.compare_spectra(pm, pr)
    assert dark[0]["text"].startswith("Miks referanstan daha parlak (-")
    assert br.band_range(250, 2000) == "250 Hz-2 kHz" and br.band_range(20, 250) == "20-250 Hz"


def test_reference_analyze_end_to_end(bs, fx):
    from app.core import beat_reference as br
    rec = bs.recordings_dir()
    v = _tone([220, 1200], secs=3.0, amp=0.1)
    pv = str(rec / "v.wav"); bs._write_wav_np(pv, v, SR)
    proj = bs.create_project("Ref")["project"]
    for t in proj["tracks"]:
        t["clips"] = []
        t["fx"] = []
    tr = next(t for t in proj["tracks"] if t["id"] == "vocal1")
    tr["clips"] = [_clip("a", pv, 0.0, 0.0, 3.0)]
    tr["volume_db"] = 0.0
    bs.save_project(proj)
    mix = bs.mix_array(bs.load_project(proj["id"])["project"], SR)
    pr = str(rec / "ref.wav"); bs._write_wav_np(pr, mix * 2.0, SR)       # referans: ayni ses, +6 dB
    r = br.analyze(proj["id"], pr)
    assert r["ok"] and r["ref_lufs"] is not None and r["mix_lufs"] is not None
    assert r["match"]["gain_db"] == pytest.approx(-6.02, abs=0.3) and "daha yüksek, eşitlendi" in r["match"]["text"]
    assert r["notes"][0]["text"].startswith("Ton dengesi referansa yakın")
    assert br.analyze(proj["id"], str(rec / "yok.wav"))["error"] == "file_not_found"
    # bos miks: uyari, esleme yok
    for t in proj["tracks"]:
        t["clips"] = []
    bs.save_project(proj)
    e = br.analyze(proj["id"], pr)
    assert e["ok"] and e["match"]["ok"] is False and e["warning"]


def test_reference_migration(bs):
    p = {"id": "x", "tracks": [], "reference_path": "/a/b.mp3", "schema": bs.SCHEMA_VERSION, "latency_ms": 0,
         "sections": [], "lyric_times": {"bars_per_line": 1, "anchors": []}}
    assert bs.migrate_project(p) is True and p["reference"] == {"path": "/a/b.mp3", "gain_db": 0.0, "start": 0.0}
    assert bs.create_project("R")["project"]["reference"] == {"path": "", "gain_db": 0.0, "start": 0.0}


# ---------------- 5. efekt atmalari: bolge bolme + kuyruk ----------------
def test_numpy_delay_fallback_matches_model(fx):
    x = np.zeros((SR, 2), dtype="float32"); x[0] = 1.0
    y, info = fx.process(x, SR, [{"type": "delay", "delay_seconds": 0.1, "feedback": 0.5, "mix": 0.4}])
    d = int(0.1 * SR)
    assert info["engine"] == "numpy" and info["skipped"] == []
    assert y[0, 0] == pytest.approx(0.6) and y[d, 0] == pytest.approx(0.4) and y[2 * d, 0] == pytest.approx(0.2)
    assert y[3 * d, 0] == pytest.approx(0.1) and abs(y[d + 5, 0]) < 1e-9


def test_throw_split_and_tail_beyond_clip(st, bs, fx):
    cache = {"/v.wav": _burst(3 * SR)}
    clips = [_clip("c", "/v.wav", 0.0, 0.0, 2.0), _clip("n", "/v.wav", 2.0, 0.0, 0.5, gain_db=-60.0)]
    rec = st.quick_fx("throw_delay", 120, "1/8")
    r = st.apply_throw(clips, "c", 1.4, 2.0, rec, ids=["m"])
    assert r["mid_id"] == "m"
    out = {c["id"]: c for c in r["clips"]}
    from app.core import beat_clips as bc
    assert bc.clip_bounds(out["m"]) == [1.4 - bc.XFADE / 2, 2.0] and out["m"]["fx"] == rec["fx"]
    assert out["m"]["tail_sec"] == rec["tail_sec"] and "tail_sec" not in out["c"]
    tr = {"id": "v", "fx": [], "clips": r["clips"]}
    full = bs.render_track_audio(tr, SR, cache)
    assert len(full) >= int((2.0 + rec["tail_sec"]) * SR) - 2      # kuyruk kanalin sonunu uzatir
    after = full[int(2.6 * SR): int(3.2 * SR)]                    # klip (ve sonraki kisa klip) bittikten sonra
    assert np.max(np.abs(after)) > 0.01                            # yanki dogal suruyor
    notail = json.loads(json.dumps(r["clips"]))
    for c in notail:
        c.pop("tail_sec", None)
    dry = bs.render_track_audio({"id": "v", "fx": [], "clips": notail}, SR, cache)
    assert len(dry) == int(2.5 * SR) and np.max(np.abs(dry[int(2.51 * SR):] if len(dry) > int(2.51 * SR) else np.zeros(1))) == 0
    # kuyruk bitiste -60 dB'e iner (dogal biter)
    tail_end = full[-int(0.3 * SR):]
    assert np.max(np.abs(tail_end)) < 0.3 * 10 ** (-40 / 20)


def test_throw_preview_window_equals_bounce(st, bs, fx):
    cache = {"/v.wav": _burst(3 * SR)}
    rec = st.quick_fx("throw_delay", 100, "1/4")
    clips = st.apply_throw([_clip("c", "/v.wav", 0.5, 0.0, 2.0, fade_in=0.05, fade_out=0.1), _clip("d", "/v.wav", 3.0, 0.0, 1.0)],
                           "c", 1.5, 2.2, rec, ids=["m", "a"])["clips"]
    tr = {"id": "v", "fx": [{"type": "gain", "gain_db": -2.0}], "clips": clips}
    full = bs.render_track_audio(tr, SR, cache)
    for t0, t1 in ((0.0, 1.0), (2.0, 3.0), (2.4, 5.5), (4.1, 7.0), (2.6, 2.9)):  # pencere kuyrugun ortasinda baslasa da
        win = bs.render_track_audio(tr, SR, cache, t0, t1)
        a, b = int(round(t0 * SR)), int(round(t1 * SR))
        exp = np.zeros((b - a, 2), dtype="float32")
        seg = full[a:b]
        exp[:len(seg)] = seg
        assert np.array_equal(win, exp), (t0, t1)
    assert bs.track_has_fx({"id": "v", "fx": [], "clips": clips}, 4.0, 5.0)      # kuyruk araligi efektli sayilir


def test_throw_preview_render_file_matches_mixdown(st, bs, fx):
    rec = bs.recordings_dir()
    p = str(rec / "v.wav"); bs._write_wav_np(p, _burst(3 * SR), SR)
    proj = bs.create_project("Throw")["project"]
    for t in proj["tracks"]:
        t["clips"] = []
        t["fx"] = []
    tr = next(t for t in proj["tracks"] if t["id"] == "vocal1")
    tr["clips"] = st.apply_throw([_clip("c", p, 0.0, 0.0, 1.5)], "c", 1.0, 1.5, st.quick_fx("throw_delay", 120, "1/8"))["clips"]
    bs.save_project(proj)
    r = bs.preview_render(proj["id"], "vocal1", 1.5, 2.0)
    assert r["ok"] and not r.get("dry") and (r["t0"], r["t1"]) == (1.5, 3.5)
    wet, _ = bs._read_audio_np(r["path"], SR)
    full = bs.render_track_audio(tr, SR, {})
    assert np.max(np.abs(wet)) > 0.01 and np.allclose(wet, full[int(1.5 * SR): int(3.5 * SR)], atol=4e-5)
    out = bs.render_mixdown(proj["id"], str(rec / "mix.wav"), target_lufs=0.0)
    mix, _ = bs._read_audio_np(out["path"], SR)
    g = 10 ** (tr["volume_db"] / 20) * np.sqrt(0.5)
    assert np.allclose(mix[int(1.5 * SR): int(3.5 * SR)], wet * g, atol=8e-5)


def test_reverse_reverb_head_swell_before_word(st, bs, fx):
    cache = {"/v.wav": _burst(2 * SR)}
    clips = st.apply_throw([_clip("c", "/v.wav", 1.0, 0.0, 2.0)], "c", 2.0, 2.5, st.quick_fx("throw_reverse"), ids=["m", "a"])["clips"]
    m = next(c for c in clips if c["id"] == "m")
    assert m["head_sec"] == 1.2 and m["fx"][0]["type"] == "reverse_reverb"
    full = bs.render_track_audio({"id": "v", "fx": [], "clips": [m]}, SR, cache)
    s = int(round(m["start"] * SR))
    pre = full[s - int(0.6 * SR): s - int(0.05 * SR)]
    assert np.max(np.abs(pre)) > 1e-3                              # kabarma kelimeden ONCE
    assert np.max(np.abs(full[: s - int(1.3 * SR)])) == 0          # head_sec'ten once sessiz
    y, info = fx.process(_burst(4000), SR, [{"type": "reverse_reverb"}])
    assert info["applied"] == 1 and info["skipped"] == [] and y.shape == (4000, 2)


def test_echo_tail_splits_last_beat(st):
    clips = [_clip("a", "/v.wav", 1.0, 0.0, 2.0), _clip("b", "/v.wav", 4.0, 0.0, 1.0)]
    rec = st.quick_fx("echo_tail", 120, "1/8d")
    r = st.apply_adlib(clips, ["a", "b"], rec)
    from app.core import beat_clips as bc
    mids = [c for c in r["clips"] if c["id"] in r["ids"]]
    assert len(mids) == 2 and all(c.get("tail_sec") == rec["tail_sec"] for c in mids)
    ends = sorted(bc.clip_bounds(c)[1] for c in mids)
    assert ends == [3.0, 5.0]
    assert all(bc.clip_bounds(c)[1] - bc.clip_bounds(c)[0] == pytest.approx(0.5 + bc.XFADE / 2) for c in mids)


# ---------------- 6. JS <-> Python esdegerligi + arayuz ----------------
def test_js_python_equivalence_2a(st, tmp_path):
    node = _node()
    fxl = [{"type": "gain", "gain_db": 1.0}]
    c = _clip("c1", "/v.wav", 1.0, 0.5, 4.5, fade_in=0.2, fade_out=0.3, fx=fxl)
    o = _clip("o", "/v.wav", 8.0, 0.0, 1.0, tail_sec=0.5)
    sa = _clip("a", "/1.wav", 0.0, 0.0, 4.0, stack_id="s", stack_active=False)
    sb = _clip("b", "/2.wav", 0.0, 0.0, 4.0, stack_id="s", stack_active=True)
    recipes = [st.quick_fx(k, 97, "1/8d") for k in ("throw_delay", "throw_reverb", "throw_phone", "throw_reverse")]
    cases = []
    for rc in recipes:
        for t0, t1 in ((2.0, 3.0), (0.0, 2.0), (4.0, 9.0), (2.0, 2.005)):
            cases.append(["applyThrow", "apply_throw", [[c, o], "c1", t0, t1, rc, ["m", "a"]]])
        cases.append(["applyThrow", "apply_throw", [[o, sa, sb], "a", 1.0, 2.0, rc, ["s1", "s2", "x1", "x2", "x3", "x4"]]])
    for k in ("phone", "high", "whisper", "autopan"):
        cases.append(["applyAdlib", "apply_adlib", [[c, o, sa, sb], ["c1", "o", "a", "b"], st.quick_fx(k, 97)]])
    cases.append(["alternatePan", "alternate_pan", [[o, c, sa, sb], ["c1", "o", "a", "b"], 0.35]])
    runner = _run_js(tmp_path, ["beat-clips.js", "beat-style.js"],
                     "process.stdout.write(JSON.stringify(input.map(([fn, args]) => window.BeatStyle[fn](...args))));")
    p = subprocess.run([node, str(runner)], input=json.dumps([[a, b] for a, _, b in cases]), capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    js_out = json.loads(p.stdout)
    py_out = json.loads(json.dumps([getattr(st, py)(*args) for _, py, args in cases]))
    for (fn, _, args), a, b in zip(cases, py_out, js_out):
        assert a == b, f"{fn}{tuple(args)[1:4]}: py={a} js={b}"
    # normalize pan/tail esdegerligi
    from app.core import beat_clips as bc
    raw = [_clip("n", "/v.wav", 0, 0, 1, pan=-2.5, tail_sec=3.3333333, head_sec=12), _clip("k", "/v.wav", 0, 0, 1, pan=0.1234567)]
    runner2 = _run_js(tmp_path, ["beat-clips.js"], "process.stdout.write(JSON.stringify(input.map((c) => window.BeatClips.normalize(c))));")
    p2 = subprocess.run([node, str(runner2)], input=json.dumps(raw), capture_output=True, text=True, timeout=60)
    assert p2.returncode == 0, p2.stderr
    assert json.loads(p2.stdout) == json.loads(json.dumps([bc.normalize(x) for x in raw]))


def test_js_syntax_and_wiring():
    node = _node()
    for name in ("beat-sim.js", "beat-style.js", "beat.js", "beat-timeline.js", "beat-fx.js", "beat-clips.js"):
        p = subprocess.run([node, "--check", str(WEB / name)], capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, (name, p.stderr)
    html = (WEB / "beat.html").read_text(encoding="utf-8")
    for el in ("listenSel", "listenBadge", "styGrid", "styInt", "stySave", "adlibQuick", "refBox", "refGain", "abToggle"):
        assert f'id="{el}"' in html, el
    assert html.index("beat-sim.js") < html.index('src="beat.js"') and html.index("beat-style.js") < html.index('src="beat.js"')
    js = (WEB / "beat.js").read_text(encoding="utf-8")
    assert 'k === "b" || k === "B"' in js and "beat_reference_analyze" in js and "onThrow" in js
    fxjs = (WEB / "beat-fx.js").read_text(encoding="utf-8")
    assert "c.tail_sec" in fxjs and "c.pan" in fxjs                  # efektli onizleme imzasi pan/kuyruk icerir


def test_api_methods(st, monkeypatch):
    from app.ui.api import Api
    for m in ("beat_style_presets", "beat_style_resolve", "beat_style_suggest", "beat_user_preset_save",
              "beat_user_preset_delete", "beat_quick_fx", "beat_style_catalog", "beat_reference_analyze"):
        assert callable(getattr(Api, m, None)), m
    assert "beat_reference_analyze" in Api.JOB_METHODS and "beat_style_resolve" in Api.JOB_METHODS
    cat = st.catalog()
    assert [x["note"] for x in cat["sync"]] == ["1/4", "1/8", "1/8d"] and len(cat["throws"]) == 4
