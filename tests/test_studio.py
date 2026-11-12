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
