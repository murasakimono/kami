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
