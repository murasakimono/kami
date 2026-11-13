"""Kami Studio: proje islemleri, ASS uretimi, ffmpeg grafigi ve MCP protokolu (ffmpeg calistirmadan)."""
import json
from pathlib import Path

from app.core import studio as S


def _proj():
    p = S.new_project("t", 1080, 1920, 30)
    p["assets"]["a1"] = {"path": "C:/v/a.mp4", "kind": "video", "dur": 10.0, "w": 1920, "h": 1080, "audio": True, "name": "a"}
    p["assets"]["a2"] = {"path": "C:/v/m.mp3", "kind": "audio", "dur": 30.0, "audio": True, "name": "m"}
    S.add_clip(p, asset="a1", track="v1", start=0, dur=10, zoom=[{"t": 0, "z": 1}, {"t": 0.2, "z": 1.3, "e": "out"}], fx=["vhs"],
               reframe=[{"t": 0, "cx": 0.3}, {"t": 5, "cx": 0.7}], trans={"in": "flash"})
    S.add_clip(p, asset="a2", track="a1", start=0, dur=10, vol=0.5, fadeOut=1)
    S.add_clip(p, text="Merhaba", start=1, dur=2, style={"anim": "type", "glow": True})
    S.add_clip(p, subscribe="classic", start=4, dur=4)
    S.add_clip(p, words=[{"w": "bir", "s": 0, "e": 0.3}, {"w": "iki", "s": 0.3, "e": 0.6}], start=5, dur=3, style={"caption": "hormozi"})
    S.add_clip(p, mode="dream", start=2, dur=1)
    return p


def test_split_and_remove_ranges():
    p = _proj()
    c = p["clips"][0]
    n = S.split_clip(p, c["id"], 4.0)
    assert c["dur"] == 4.0 and n["start"] == 4.0 and n["in"] == 4.0 and n["dur"] == 6.0
    assert "zoom" not in n or not n["zoom"]       # zoom kareleri sol parcada kaldi
    removed = S.remove_ranges(p, c["id"], [[2.0, 3.0], [6.0, 7.5]])
    assert removed == 2
    vids = sorted([x for x in p["clips"] if x["track"] == "v1"], key=lambda x: x["start"])
    assert abs(S.project_end({"clips": vids}) - (10 - (1.0 - 0.16) - (1.5 - 0.16))) < 1e-6
    for a, b in zip(vids, vids[1:]):              # bosluk kalmadi
        assert abs(a["start"] + a["dur"] - b["start"]) < 1e-6


def test_ass_has_all_layers():
    ass = S.build_ass(_proj())
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    assert ass.count("Dialogue:") > 8
    assert "ABONE OL" in ass and "\\p1" in ass     # abone: vektor cizim
    assert "\\alpha&HFF&" in ass                   # daktilo
    assert "BİR" in ass or "BIR" in ass             # altyazi buyuk harf


def test_export_graph(tmp_path: Path):
    args, total = S.build_export(_proj(), str(tmp_path / "o.mp4"), tmp_path, "h264_nvenc", {})
    assert total == 10.0
    g = args[args.index("-filter_complex") + 1]
    assert "zoompan=" in g and "crop=w=" in g and "rgbashift" in g and "subtitles=k.ass" in g
    assert "amix=inputs=2" in g and "adelay" not in g.split("amix")[0].split("[1:a]")[0]
    assert "[vout]" in g and "[aout]" in g and "h264_nvenc" in args
    assert (tmp_path / "k.ass").is_file()
    # aralik: 3-6 sn
    args, total = S.build_export(_proj(), str(tmp_path / "o.mp4"), tmp_path, "libx264", {"range": [3, 6]})
    assert total == 3.0 and "-ss" in args


def test_fx_chain_labels_unique():
    a = S._fx_chain(S.FX["dream"]["ff"], 1920, 1080, 0, "c1")
    b = S._fx_chain(S.FX["dream"]["ff"], 1920, 1080, 0, "c2")
    assert "[c1d0]" in a and "[c2d0]" in b and "[d0]" not in a


def test_kf_expr():
    e = S.kf_expr(S.kf_resolve([{"t": 0, "z": 1}, {"t": -0.001, "z": 2}], 4.0), "z", "T", 1)
    assert e.startswith("if(lt(T,0.0000),1.0000") and "3.9990" in e


def test_mcp_protocol(tmp_path, monkeypatch):
    from app.core import studio_mcp as M
    monkeypatch.setattr(M, "CURRENT", tmp_path / "current.json")
    monkeypatch.setattr(S, "home_dir", lambda: tmp_path)
    r = M.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
    assert r["result"]["serverInfo"]["name"] == "kami-studio"
    tools = M.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
    assert {"get_project", "add_text", "cut_silences", "render_frame", "export_video"} <= {t["name"] for t in tools}
    r = M.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "new_project", "arguments": {"name": "x", "path": str(tmp_path / "x.kstudio")}}})
    assert not r["result"].get("isError")
    r = M.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "add_text", "arguments": {"text": "Selam", "start": 1}}})
    assert json.loads(r["result"]["content"][0]["text"])["track"] == "tx"
    r = M.handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "add_effect", "arguments": {"mode": "yok"}}})
    assert r["result"]["isError"]
    assert M.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_pro_features(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "home_dir", lambda: tmp_path)
    # renk: bos ayar = birim LUT
    assert not S.grade_active({}) and S.grade_active({"exp": 0.5})
    r, g, b = S.grade_pixel({"sat": 1}, 0.3, 0.5, 0.7)
    assert abs(r - 0.3) < 1e-6 and abs(b - 0.7) < 1e-6
    f = S.bake_grade({"exp": 0.2}, tmp_path / "g.cube")
    n, data = S.parse_cube(f)
    assert n == S.LUT_N and len(data) == n ** 3
    # hiz rampasi: sabit 2x = yari sure
    c = {"dur": 4.0, "srcLen": 4.0, "ramp": [{"p": 0, "s": 2}, {"p": 1, "s": 2}]}
    assert abs(S.ramp_duration(c) - 2.0) < 1e-6
    # sablon + kare dondurma
    p = _proj()
    added = S.apply_template(p, "yt-lower", 2.0)
    assert any(x.get("graphic") == "lower" for x in p["clips"] if x["id"] in added)
    vid = next(x for x in p["clips"] if x["track"] == "v1")
    before = len(p["clips"])
    S.apply_template(p, "freeze", 3.0, clip_id=vid["id"])
    assert any(x.get("freeze") for x in p["clips"]) and len(p["clips"]) >= before + 2
    # teslim bicimleri
    args, _ = S.build_export(_proj(), str(tmp_path / "o.gif"), tmp_path, "libx264", {"format": "gif"})
    assert "palettegen" in args[args.index("-filter_complex") + 1]
    args, _ = S.build_export(_proj(), str(tmp_path / "o.mp3"), tmp_path, "libx264", {"format": "mp3", "lufs": -14})
    assert "libmp3lame" in args and "loudnorm" in args[args.index("-filter_complex") + 1]
    # grafik + YouTube abone dizisi ASS uretir
    from app.core import studio_gfx as G
    for kind in G.SUBSCRIBE_PRO:
        assert G.subscribe(kind, S._ts, S._col, S._esc, S._rrect, 0, 4, 1920, 1080, {})
    for kind in G.GRAPHICS:
        assert G.graphic(kind, S._ts, S._col, S._esc, S._rrect, 0, 4, 1920, 1080, {"title": "x"})


def test_anim_and_text_helpers(tmp_path):
    from app.core import studio, studio_anim
    assert studio.tr_upper("istanbul ılık") == "İSTANBUL ILIK"
    st = {"animIn": "letters-up", "animOut": "wipe", "animLoop": "pulse"}
    ev = studio_anim.text_events("Merhaba", st, 0, 3, 960, 540, 1920, 1080, "\\an5", studio._esc, studio._ts)
    assert len(ev) == 3 and all(e.startswith("Dialogue:") for e in ev)
    ch, ex = studio_anim.clip_filters({"anim": {"in": "pop", "loop": "wobble", "out": "spin"}}, 3, 0, 30, 1920, 1080, "a")
    assert any("perspective" in c for c in ch) and ex["r"]
    assert studio_anim.clip_filters({}, 3, 0, 30, 1920, 1080, "a") == ([], {})
    s = studio.Studio(lambda: "ffmpeg")
    s._fcflag = "-/filter_complex"
    out = s._fc_file(["-i", "x", "-filter_complex", "[0:v]null[vout]", "-map", "[vout]"], tmp_path)
    assert out[2] == "-/filter_complex" and (tmp_path / "graph.txt").read_text() == "[0:v]null[vout]"
    assert len(studio.FX) >= 80


def test_lottie_resolve_direct():
    from app.core.lottie_conv import resolve
    assert resolve("https://lottie.host/a/b.json") == "https://lottie.host/a/b.json"
    assert resolve("https://assets-v2.lottiefiles.com/a/x/y.lottie?v=1").endswith("?v=1")


def test_all_transitions_have_ffmpeg_chain():
    for kind in S.TRANS_FF:
        ch = S._trans_in(kind, 0.4, 1080, 1920, "tr0", 0.1, 30)
        assert ch and ch != "null", kind


def test_transitions_run_in_ffmpeg():
    """Her gecis zinciri gercek ffmpeg'de calisir (ffmpeg yoksa atlanir)."""
    import shutil
    import subprocess
    import pytest
    ff = shutil.which("ffmpeg")
    if not ff:
        pytest.skip("ffmpeg yok")
    for kind in sorted(S.TRANS_FF):
        ch = S._trans_in(kind, 0.3, 320, 180, "tr0", 0.05, 30)
        g = f"[0:v]format=rgba,{ch},format=rgba[o]"
        r = subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=0.5", "-filter_complex", g,
                            "-map", "[o]", "-f", "null", "-"], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, (kind, r.stderr[-300:])


def test_new_caption_styles_emit_dialogues():
    words = [{"w": w, "s": i * 0.4, "e": i * 0.4 + 0.38} for i, w in enumerate("bir iki üç dört beş altı".split())]
    for mode in ("mrbeast", "highlight", "reveal", "hollow", "cinema"):
        assert mode in S.CAPTION_STYLES
        p = S.new_project("t", 1080, 1920, 30)
        S.add_clip(p, words=words, start=0, dur=3, style={"caption": mode})
        ass = S.build_ass(p)
        assert ass.count("Dialogue:") >= 1, mode
    p = S.new_project("t", 1080, 1920, 30)
    S.add_clip(p, words=words, start=0, dur=3, style={"caption": "reveal"})
    assert "\\alpha&HFF&" in S.build_ass(p)     # henuz soylenmeyen kelimeler saydam


def test_zoom_presets_unique_and_valid():
    ids = [z["id"] for z in S.ZOOM_PRESETS]
    assert len(ids) == len(set(ids)) and len(ids) >= 16
    for z in S.ZOOM_PRESETS:
        assert S.kf_resolve(z["kf"], 2.0), z["id"]


def test_all_fx_run_in_ffmpeg():
    """Butun efekt zincirleri (FX + FX2 + FX3) gercek ffmpeg'de calisir (ffmpeg yoksa atlanir)."""
    import shutil
    import subprocess
    import pytest
    ff = shutil.which("ffmpeg")
    if not ff:
        pytest.skip("ffmpeg yok")
    bad = []
    for fid, fx in S.FX.items():
        ch = S._fx_chain(fx["ff"], 320, 180, 0.0, "c0" + fid.replace("-", ""))
        g = f"[0:v]format=rgba,{ch},format=rgba[o]"
        r = subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=0.4", "-filter_complex", g,
                            "-map", "[o]", "-f", "null", "-"], capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            bad.append((fid, r.stderr[-200:]))
    assert not bad, bad


def test_caption_presets_map_to_behaviour_and_font():
    words = [{"w": w, "s": i * 0.4, "e": i * 0.4 + 0.38} for i, w in enumerate("bir iki üç dört".split())]
    for mode, p in S.CAPTIONS2.items():
        assert mode in S.CAPTION_STYLES and p["b"] in S.CAPTION_STYLES
        pr = S.new_project("t", 1080, 1920, 30)
        S.add_clip(pr, words=words, start=0, dur=2, style={"caption": mode})
        ass = S.build_ass(pr)
        assert ass.count("Dialogue:") >= 1, mode
        if p["st"].get("font"):
            assert "\\fn" + p["st"]["font"] in ass, mode


def test_bundled_fonts_cover_turkish_and_are_listed():
    from app import paths
    from PIL import ImageFont
    fams = {}
    for f in (paths.WEB_DIR / "fonts").glob("*.ttf"):
        fams[ImageFont.truetype(str(f), 12).getname()[0]] = f
    for name in S.FONTS[10:]:
        assert name in fams, name
    used = {p["st"]["font"] for p in S.CAPTIONS2.values() if p["st"].get("font")}
    assert used <= set(fams), used - set(fams)


def test_clip_anim_pack_runs_in_ffmpeg():
    import shutil
    import subprocess
    import pytest
    from app.core import studio_anim as A
    from app.core.studio_anim_pack import CLIP_IN2, CLIP_LOOP2, CLIP_OUT2
    ff = shutil.which("ffmpeg")
    if not ff:
        pytest.skip("ffmpeg yok")
    cases = [{"in": k} for k in CLIP_IN2] + [{"out": k} for k in CLIP_OUT2] + [{"loop": k} for k in CLIP_LOOP2]
    for an in cases:
        c = {"anim": an}
        f, _ = A.clip_filters(c, 2.0, 0.0, 30, 320, 180, "an0")
        ex = A.clip_exprs(c, 2.0, "t")
        g = (f"[0:v]format=rgba,{','.join(f) or 'null'}[c];color=black:s=640x360:r=30[bg];"
             f"[bg][c]overlay=x='(W-w)/2+({ex.get('x') or 0})*320':y='(H-h)/2+({ex.get('y') or 0})*180':shortest=1[o]")
        r = subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=1", "-filter_complex", g, "-map", "[o]",
                            "-f", "null", "-"], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, (an, r.stderr[-200:])


def test_real_transition_extends_previous_clip_under_next():
    p = S.new_project("t", 1280, 720, 30)
    p["assets"]["a1"] = {"path": "C:/v/a.mp4", "kind": "video", "dur": 20.0, "w": 1920, "h": 1080, "audio": False, "name": "a"}
    S.add_clip(p, asset="a1", track="v1", start=0, dur=4, **{"in": 0})
    S.add_clip(p, asset="a1", track="v1", start=4, dur=4, trans={"in": "diag-tl", "dur": 0.5}, **{"in": 10})
    a = p["assets"]["a1"]
    first, second = sorted([c for c in p["clips"] if c["track"] == "v1"], key=lambda c: c["start"])
    assert abs(S.trans_tail(first, p["clips"], a) - 0.5) < 1e-6
    assert S.trans_tail(second, p["clips"], a) == 0
    second["trans"]["over"] = False
    assert S.trans_tail(first, p["clips"], a) == 0
    second["trans"]["over"] = True
    first["in"] = 15.8          # kaynakta 0.2 sn kaldi -> o kadar uzar
    assert abs(S.trans_tail(first, p["clips"], a) - 0.2) < 1e-6
    from pathlib import Path
    args, _ = S.build_export(p, "C:/o.mp4", Path(__import__("tempfile").mkdtemp()), "libx264", {})
    g = " ".join(args)
    assert "between(t,0.0000,4.2000)" in g    # ilk klip gecis boyunca altta


def test_silence_asymmetric_pad_and_selective_restore():
    p = S.new_project("silence", 1280, 720, 30)
    p["assets"]["a1"] = {"path": "C:/v/a.mp4", "kind": "video", "dur": 20.0, "w": 1280, "h": 720, "audio": True, "name": "a"}
    c = S.add_clip(p, asset="a1", track="v1", start=0, dur=20.0, **{"in": 0})
    # Iki sessiz bolge: [2.0, 6.0] (4 sn) ve [10.0, 14.0] (4 sn)
    # Konusma sonrasi pay=0.1, konusma oncesi pay=1.0 -> her kesimden 2.9 sn kesilir
    n = S.remove_ranges(p, c["id"], [[2.0, 6.0], [10.0, 14.0]], pad=0.1, pad_before=1.0)
    assert n == 2
    assert len(p["cuts"]) == 2
    end_after_cut = S.project_end(p)
    assert abs(end_after_cut - (20.0 - 2.9 - 2.9)) < 0.01

    # Sadece ilk kesilen bolgeyi geri getir (ikinci kesim korunur!)
    first_cut = sorted(p["cuts"], key=lambda x: x["seamStart"])[0]
    restored = S.restore_cuts(p, [first_cut["id"]])
    assert len(restored) == 1
    assert len(p["cuts"]) == 1
    assert abs(S.project_end(p) - (20.0 - 2.9)) < 0.01


def test_wave2_catalog_and_mask_blend_adj_kf_ffmpeg(tmp_path: Path):
    import shutil
    import subprocess
    import pytest

    cat = S.catalog()
    assert len(cat["blends"]) == 9 and "screen" in cat["blends"] and "multiply" in cat["blends"]
    assert len(cat["masks"]) == 8 and "heart" in cat["masks"] and "circle" in cat["masks"]
    assert "easeOutExpo" in cat["bezierPresets"] and "pop" in cat["bezierPresets"]

    ff = shutil.which("ffmpeg")
    if not ff:
        pytest.skip("ffmpeg yok")

    v1 = tmp_path / "base.mp4"
    v2 = tmp_path / "ov.mp4"
    subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=24:d=2",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-shortest",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(v1)], check=True)
    subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "smptebars=s=320x180:r=24:d=2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(v2)], check=True)

    p = S.new_project("wave2", 640, 360, 24)
    p["assets"]["a1"] = {"path": str(v1), "kind": "video", "dur": 2.0, "w": 320, "h": 180, "audio": True, "name": "base"}
    p["assets"]["a2"] = {"path": str(v2), "kind": "video", "dur": 2.0, "w": 320, "h": 180, "audio": False, "name": "ov"}

    S.add_clip(p, asset="a1", track="v1", start=0, dur=2.0, kf=[
        {"t": 0.0, "scale": 1.0, "x": -0.1, "rot": 0, "opacity": 1.0, "vol": 0.8},
        {"t": 1.0, "scale": 1.25, "x": 0.05, "rot": 8, "opacity": 0.85, "vol": 0.3, "bez": "easeOutExpo"},
        {"t": 2.0, "scale": 1.0, "x": 0.0, "rot": 0, "opacity": 1.0, "vol": 1.0, "bez": [0.34, 1.45, 0.64, 1.0]},
    ])
    S.add_clip(p, asset="a2", track="v2", start=0.0, dur=1.0, blend="screen",
               mask={"type": "heart", "x": 0.5, "y": 0.5, "w": 0.6, "h": 0.6, "rot": 15, "feather": 4, "invert": False})
    S.add_clip(p, asset="a2", track="v2", start=1.0, dur=1.0, blend="multiply",
               mask={"type": "circle", "x": 0.5, "y": 0.5, "w": 0.5, "h": 0.5, "rot": 0, "feather": 6, "invert": True})
    S.add_clip(p, mode="adjustment", track="fx", start=0.2, dur=1.5,
               adj={"bri": 8, "con": 12, "sat": 20}, fx=["vhs"], opacity=0.75, blend="overlay")

    out = tmp_path / "wave2_out.mp4"
    args, total = S.build_export(p, str(out), tmp_path, "libx264", {"quality": "medium"})
    assert abs(total - 2.0) < 1e-6
    r = subprocess.run([ff, "-y", "-v", "error", *args], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-400:]
    assert out.is_file() and out.stat().st_size > 1000


def test_wave3_optflow_shutter_parent_eq_pan_ffmpeg(tmp_path: Path):
    import shutil
    import subprocess
    import pytest

    cat = S.catalog()
    assert len(cat["eqBands"]) == 10 and "podcast" in cat["eqPresets"]
    assert "qsin" in cat["audioCurves"]

    ff = shutil.which("ffmpeg")
    if not ff:
        pytest.skip("ffmpeg yok")

    v1 = tmp_path / "p.mp4"
    v2 = tmp_path / "ch.mp4"
    subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=24:d=2",
                    "-f", "lavfi", "-i", "sine=frequency=330:duration=2", "-shortest",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(v1)], check=True)
    subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "smptebars=s=160x90:r=12:d=2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(v2)], check=True)

    p = S.new_project("wave3", 640, 360, 24)
    p["assets"]["a1"] = {"path": str(v1), "kind": "video", "dur": 2.0, "w": 320, "h": 180, "audio": True, "name": "parent"}
    p["assets"]["a2"] = {"path": str(v2), "kind": "video", "dur": 2.0, "w": 160, "h": 90, "audio": False, "name": "child"}

    parent = S.add_clip(p, asset="a1", track="v1", start=0.0, dur=1.5, shutterAngle=180,
                        pan=-0.35, fadeIn=0.15, fadeCurve="qsin",
                        eq=[4, 2, 0, -2, 0, 2, 4, 3, 2, 0],
                        kf=[{"t": 0.0, "x": -0.1, "scale": 1.0, "rot": 0},
                            {"t": 1.5, "x": 0.1, "scale": 1.15, "rot": 15, "bez": "easeOutExpo"}])
    S.add_clip(p, asset="a2", track="v2", start=0.0, dur=1.5, parent=parent["id"],
               x=0.15, y=0.05, scale=0.45, rot=10, speed=0.5, optFlow=True)

    out = tmp_path / "wave3_out.mp4"
    args, total = S.build_export(p, str(out), tmp_path, "libx264", {"quality": "medium"})
    assert abs(total - 1.5) < 1e-6
    g = args[args.index("-filter_complex") + 1]
    assert "minterpolate=" in g and "tmix=" in g and "equalizer=" in g and "stereotools=balance_out=-0.350" in g and ":curve=qsin" in g
    r = subprocess.run([ff, "-y", "-v", "error", *args], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-400:]
    assert out.is_file() and out.stat().st_size > 1000


def test_wave4_pro_pack_stabilize_solo_close_gaps(tmp_path: Path):
    import re
    import shutil
    import subprocess
    import pytest

    cat = S.catalog()
    assert len(cat["fx"]) >= 187
    assert len(cat["trans"]) >= 63
    assert len(cat["zoom"]) >= 50
    assert len(cat["captions"]) >= 33
    assert len(cat["afx"]) >= 15
    assert len(cat["templates"]) >= 24
    assert len(S.SFX) >= 52

    # Tum efektlerde canli onizleme (css ya da ov) ve tum gecislerde CSS/JS onizlemesi olmali
    empty_fx = [k for k, v in S.FX.items() if not v.get("css") and not v.get("ov")]
    assert not empty_fx, f"Onizlemesiz efektler: {empty_fx}"
    css_txt = (Path(__file__).resolve().parents[1] / "app" / "ui" / "web" / "studio.css").read_text("utf-8")
    css_tv = set(re.findall(r"\.tv-([a-z0-9-]+)::", css_txt))
    missing_tv = [k for k in S.TRANS if k != "none" and k not in css_tv]
    assert not missing_tv, f"CSS gecis karti eksik: {missing_tv}"

    # ripple_close_gaps kontrolu
    pr_gap = S.new_project("gaps", 320, 180, 24)
    c1 = S.add_clip(pr_gap, text="bir", start=1.5, dur=1.0)
    c2 = S.add_clip(pr_gap, text="iki", start=5.0, dur=2.0)
    moved = S.ripple_close_gaps(pr_gap, c1["track"])
    assert moved == 2
    assert c1["start"] == 0.0 and c2["start"] == 1.0

    ff = shutil.which("ffmpeg")
    if not ff:
        pytest.skip("ffmpeg yok")

    v1 = tmp_path / "v1.mp4"
    a1 = tmp_path / "a1.wav"
    a2 = tmp_path / "a2.wav"
    subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=24:d=2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(v1)], check=True)
    subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(a1)], check=True)
    subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=880:duration=1", str(a2)], check=True)

    p = S.new_project("wave4", 320, 180, 24)
    p["assets"]["v1"] = {"path": str(v1), "kind": "video", "dur": 2.0, "w": 320, "h": 180, "audio": False, "name": "v"}
    p["assets"]["s1"] = {"path": str(a1), "kind": "audio", "dur": 1.0, "audio": True, "name": "s1"}
    p["assets"]["s2"] = {"path": str(a2), "kind": "audio", "dur": 1.0, "audio": True, "name": "s2"}
    tk_a2 = "a2"
    p["tracks"].append({"id": tk_a2, "kind": "audio", "name": "Müzik 2", "vol": 1.0, "solo": True})   # yalnizca tk_a2 duyulmali

    S.add_clip(p, asset="v1", track="v1", start=0.0, dur=1.2, stabilize=True,
               fx=["halation-pro", "crisp-4k"], trans={"in": "rgb-tear", "dur": 0.35})
    S.add_clip(p, asset="s1", track="a1", start=0.0, dur=1.0)
    S.add_clip(p, asset="s2", track=tk_a2, start=0.0, dur=1.0, afx=["compressor-punch"])

    out = tmp_path / "wave4_out.mp4"
    args, total = S.build_export(p, str(out), tmp_path, "libx264", {"quality": "medium"})
    assert abs(total - 1.2) < 1e-6
    g = args[args.index("-filter_complex") + 1]
    assert "deshake=" in g and "acompressor=" in g and "geq=" in g and "amix=inputs=1" in g
    r = subprocess.run([ff, "-y", "-v", "error", *args], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-400:]
    assert out.is_file() and out.stat().st_size > 1000


def test_dalga5_tr_memes_and_sfx_ffmpeg(tmp_path: Path, monkeypatch):
    import shutil
    import subprocess
    import pytest
    from app.core import studio_brand as SB
    from app.core import studio_tr_memes as TM
    from app.ui import api_studio as AS

    cat = S.catalog()
    assert len(TM.SFX_TR_MEME) >= 18
    assert len(TM.FX_TR_MEME) >= 5
    assert len(TM.TEMPLATES_TR_MEME) >= 5
    assert len(TM.RECIPES_TR_MEME) >= 4
    assert len(TM.TR_MEME_SOUNDS) >= 50
    assert len(TM.TR_MEME_VIDEOS) >= 20
    assert len(TM.AI_MEME_PROMPTS) >= 5

    # Wiring kontrolleri
    assert len(S.SFX) >= 70
    assert all(k in S.SFX for k in TM.SFX_TR_MEME)
    assert all(k in S.SFX_CAT for k in TM.SFX_TR_MEME)
    assert all(k in S.FX for k in TM.FX_TR_MEME)
    assert all(k in SB.VIRAL_RECIPES for k in TM.RECIPES_TR_MEME)
    empty_fx = [k for k, v in S.FX.items() if not v.get("css") and not v.get("ov")]
    assert not empty_fx, f"Onizlemesiz efektler: {empty_fx}"
    assert len(cat["fx"]) >= 192
    assert len(cat["templates"]) >= 29

    # Myinstants HTML blok ayristirma duzeltmesi
    sample_html = (
        '<div class="instant">'
        '<div class="small-button-background"></div>'
        '<button type="button" onclick="play(\'/media/sounds/test-bocek.mp3\', \'loader-1\', \'button-1\')"></button>'
        '<div id="loader-1"></div><div class="small-button-shadow"></div>'
        '<a href="/en/instant/test/" class="instant-link link-secondary">AI Hamam Böceği Slow-Mo &amp; Dram</a>'
        '</div>'
    )
    parsed = AS._parse_myinstants(sample_html)
    assert parsed == [{"name": "AI Hamam Böceği Slow-Mo & Dram", "url": "https://www.myinstants.com/media/sounds/test-bocek.mp3"}]

    # TR meme bankasi URL ve veri kontrolleri
    bank = AS.StudioMixin().studio_tr_meme_bank()
    assert all(s["url"].startswith("https://") for s in bank["sounds"])
    assert all(v["url"].startswith("https://") for v in bank["videos"])
    assert all(p["title"] and p["prompt"] for p in bank["aiPrompts"])

    ff = shutil.which("ffmpeg")
    if not ff:
        pytest.skip("ffmpeg yok")

    monkeypatch.setattr(S, "home_dir", lambda: tmp_path / "studio_home")
    st = S.Studio(lambda: ff)

    # Sablon & viral recete uygulama kontrolleri
    for rec_id in TM.RECIPES_TR_MEME:
        pr = S.new_project("rec_" + rec_id, 320, 180, 24)
        pr["assets"]["v1"] = {"path": str(tmp_path / "dummy.mp4"), "kind": "video", "dur": 4.0, "w": 320, "h": 180, "audio": True, "name": "dummy"}
        S.add_clip(pr, asset="v1", track="v1", start=0.0, dur=4.0)
        res = SB.apply_viral_recipe(pr, rec_id)
        assert res["ok"] and res["applied_clips"] >= 1

    for tpl in TM.TEMPLATES_TR_MEME:
        pr = S.new_project("tpl_" + tpl["id"], 320, 180, 24)
        created = S.apply_template(pr, tpl["id"], 0.0, ffmpeg=ff, info=st.info)
        assert len(created) >= 1

    # 18 yeni SFX'in hepsi gercek ffmpeg ile wav uretmeli
    for sid in TM.SFX_TR_MEME:
        built = S.ensure_sfx(ff, sid)
        assert sid in built and Path(built[sid]).is_file() and Path(built[sid]).stat().st_size > 800, f"SFX uretilemedi: {sid}"

    # 5 yeni TR Meme FX'inin tamami gercek ffmpeg export'unda hatasiz calismali
    v1 = tmp_path / "meme_src.mp4"
    subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=24:d=3",
                    "-f", "lavfi", "-i", "sine=frequency=220:duration=3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(v1)], check=True)
    pr_fx = S.new_project("dalga5_fx", 320, 180, 24)
    pr_fx["assets"]["v1"] = {"path": str(v1), "kind": "video", "dur": 3.0, "w": 320, "h": 180, "audio": True, "name": "meme"}
    for idx, fx_id in enumerate(TM.FX_TR_MEME):
        S.add_clip(pr_fx, asset="v1", track="v1", start=idx * 0.4, dur=0.4, fx=[fx_id])
    out = tmp_path / "dalga5_fx_out.mp4"
    args, total = S.build_export(pr_fx, str(out), tmp_path, "libx264", {"quality": "medium"})
    assert abs(total - len(TM.FX_TR_MEME) * 0.4) < 1e-6
    r = subprocess.run([ff, "-y", "-v", "error", *args], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-400:]
    assert out.is_file() and out.stat().st_size > 1000


def test_dalga6_features_and_api_wiring(tmp_path: Path):
    import re
    import shutil
    import subprocess
    import pytest
    from app.core import studio_gfx as SG
    from app.core import studio_tr_memes as TM

    root = Path(__file__).resolve().parent.parent
    apis = set(re.findall(r"def (studio_[a-zA-Z0-9_]+)\(", (root / "app/ui/api_studio.py").read_text(encoding="utf-8")))
    web = "\n".join(p.read_text(encoding="utf-8") for p in (root / "app/ui/web").glob("*.js"))
    missing = [a for a in sorted(apis) if a not in web]
    assert not missing, f"UI'da baglanmamis studio_* API'leri: {missing}"

    assert len(TM.TR_MEME_VIDEOS) >= 50
    assert len(TM.TR_MEME_SOUNDS) >= 90
    assert len(TM.TEMPLATES_TR_MEME) >= 7
    assert len(SG.STICKERS) >= 20
    for gk in ("news-card", "split-card", "stat-table", "birazdan"):
        assert gk in SG.GRAPHICS

    cat = S.catalog()
    assert len(cat.get("stickers", {})) >= 20
    assert len(cat.get("voiceChangers", {})) >= 5

    p = S.new_project("dalga6", 640, 360, 24)
    S.add_clip(p, track="tx", start=0.0, dur=1.2, graphic="news-card", style={"title": "SON DAKİKA", "sub": "Detay"})
    S.add_clip(p, track="tx", start=1.2, dur=1.0, sticker="arrow-red", style={"x": 0.5, "y": 0.5, "size": 90, "color": "#FF2E54"})
    ass = S.build_ass(p)
    assert "SON DAK" in ass and "\\p1" in ass

    ff = shutil.which("ffmpeg")
    if not ff:
        pytest.skip("ffmpeg yok")

    v1 = tmp_path / "src6.mp4"
    subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=24:d=2.5",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=2.5", "-shortest",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(v1)], check=True)
    p["assets"]["a1"] = {"path": str(v1), "kind": "video", "dur": 2.5, "w": 320, "h": 180, "audio": True, "name": "src6"}
    S.add_clip(
        p, asset="a1", track="v1", start=0.0, dur=2.0, **{"in": 0.0},
        reverse=True,
        crop={"l": 0.1, "r": 0.1, "t": 0.05, "b": 0.05},
        radius=0.18, borderW=4, borderColor="#8B5CF6",
        grade={"vignette": 0.35, "grain": 0.2, "halation": 0.25, "curves": {"luma": [[0, 0], [0.5, 0.62], [1, 1]]}},
        pitch=2, voice="megaphone", audioLead=0.1, audioTail=0.1,
    )
    out = tmp_path / "dalga6_out.mp4"
    args, total = S.build_export(p, str(out), tmp_path, "libx264", {"quality": "medium"})
    assert total >= 2.0
    r = subprocess.run([ff, "-y", "-v", "error", *args], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-500:]
    assert out.is_file() and out.stat().st_size > 1000

