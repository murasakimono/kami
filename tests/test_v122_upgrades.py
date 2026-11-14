"""v1.22.0: Studio memeler/SFX/Auto-Box, Picture Pro+MCP, Hunter, Mod diff/profil ve Fragmovie testleri."""
from __future__ import annotations

import io
import json
import subprocess
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw


def test_tr_memes_short_clips_and_sfx_pack():
    from app.core import studio as S
    from app.core.studio_tr_memes import TR_MEME_SOUNDS, TR_MEME_VIDEOS

    assert len(TR_MEME_SOUNDS) >= 140
    assert len(TR_MEME_VIDEOS) >= 40
    for v in TR_MEME_VIDEOS:
        assert int(v.get("dur") or 0) <= 45, f"uzun video: {v}"
        low = str(v.get("title") or "").lower()
        assert "derleme" not in low and "compilation" not in low
    assert len(S.SFX) >= 94


def test_gfx_pack2_autobox_widens_on_long_text():
    from app.core import studio_gfx as SG

    ts = lambda v: f"0:00:{v:05.2f}"
    col = lambda c, a=0: f"&H{a:02X}FFFFFF"
    esc = lambda t: str(t)
    widths: list[float] = []
    rrect = lambda w, h, r=0: (widths.append(float(w)), f"m 0 0 l {w:.0f} 0 l {w:.0f} {h:.0f} l 0 {h:.0f}")[1]

    for mode in ("newspaper-cut", "device-notif", "social-comment", "whiteboard-sketch"):
        widths.clear()
        SG.graphic(mode, ts, col, esc, rrect, 0.0, 2.0, 1280, 720, {"title": "Hi", "sub": ""})
        short_w = max(widths)
        widths.clear()
        SG.graphic(
            mode,
            ts,
            col,
            esc,
            rrect,
            0.0,
            2.0,
            1280,
            720,
            {"title": "Cok uzun bir sosyal medya bildirim metni test ediliyor", "sub": "Alt baslik detayi burada"},
        )
        long_w = max(widths)
        assert long_w > short_w, f"{mode} genislemedi: {short_w} -> {long_w}"


def test_picture_pro_contact_shadow_sprite_macro_and_bridge(tmp_path: Path, monkeypatch):
    from app.core import picture_pro as pp, studio as S

    monkeypatch.setattr(S, "home_dir", lambda: tmp_path / "studio_home")

    src = tmp_path / "subject.png"
    im = Image.new("RGBA", (240, 240), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((60, 40, 180, 200), fill=(139, 92, 246, 255))
    im.save(src)

    # 1. Contact shadow
    r_sh = pp.add_contact_shadow(str(src), bg_color="#FFFFFF", pad_ratio=0.12, size=600, out_path=str(tmp_path / "ecom.png"))
    assert r_sh["ok"] is True
    out_im = Image.open(r_sh["path"])
    assert out_im.size == (600, 600)

    # 2. Animated WebP sprite sheet
    f2 = tmp_path / "f2.png"
    im.rotate(25).save(f2)
    r_sp = pp.export_webp_sheet([str(src), str(f2)], duration_ms=125, out_path=str(tmp_path / "anim.webp"))
    assert r_sp["ok"] is True
    assert r_sp["frames"] == 2
    assert Path(r_sp["path"]).is_file()

    # 3. Macros save/list/run/batch/delete
    macros = pp.list_macros()
    assert len(macros) >= 1
    sv = pp.save_macro(
        "Test Makro",
        [{"op": "contact_shadow", "bg_color": "#111111", "size": 400}, {"op": "watermark", "text": "KamiTest"}],
        macro_id="test-macro-v122",
    )
    assert sv["ok"] is True
    try:
        rr = pp.run_macro(str(src), "test-macro-v122", out_path=str(tmp_path / "macro_out.png"))
        assert rr["ok"] is True
        assert Path(rr["path"]).is_file()

        br = pp.batch_run_macro([str(src), str(f2)], "test-macro-v122", out_dir=str(tmp_path / "batch"))
        assert br["ok"] is True and br["processed"] == 2 and br["total"] == 2
    finally:
        dl = pp.delete_macro("test-macro-v122")
        assert dl["ok"] is True

    # 4. Studio asset bridge
    st_bridge = pp.send_to_studio_asset(str(src), folder="TestGorseller")
    assert st_bridge["ok"] is True
    assert Path(st_bridge["path"]).is_file()


def test_picture_mcp_and_studio_mcp_stdio_roundtrip(tmp_path: Path):
    import sys
    from app.core import picture_mcp as pm, studio_mcp as sm

    # Studio MCP includes all Picture tools
    for tool_name in ("pic_contact_shadow", "pic_export_webp_sheet", "pic_macro_list", "pic_macro_run", "pic_send_to_studio"):
        assert tool_name in pm.TOOLS
        assert tool_name in sm.TOOLS

    src = tmp_path / "p.png"
    im = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle((20, 20, 100, 100), fill=(255, 100, 50, 255))
    im.save(src)
    out_p = tmp_path / "p_ecom.png"

    reqs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "pic_contact_shadow", "arguments": {"image": str(src), "size": 320, "out_path": str(out_p)}},
        },
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "pic_macro_list", "arguments": {}}},
    ]
    proc = subprocess.run(
        [sys.executable, "-m", "app.core.picture_mcp"],
        input="\n".join(json.dumps(r) for r in reqs) + "\n",
        text=True,
        capture_output=True,
        timeout=20,
        check=True,
    )
    lines = [json.loads(line) for line in proc.stdout.strip().splitlines()]
    assert len(lines) == 4
    assert lines[0]["result"]["serverInfo"]["name"] == "kami-picture"
    tool_names = {t["name"] for t in lines[1]["result"]["tools"]}
    assert "pic_contact_shadow" in tool_names and "pic_macro_run" in tool_names
    res3 = json.loads(lines[2]["result"]["content"][0]["text"])
    assert res3["ok"] is True and out_p.is_file()
    res4 = json.loads(lines[3]["result"]["content"][0]["text"])
    assert res4["ok"] is True and len(res4["macros"]) >= 1


def test_kami_hunter_cluster_rank_and_archive(tmp_path: Path):
    from app.core import kami_hunter as kh

    sample = [
        {"title": "Hidra - Olume Inat [Official Video]", "source": "Dailymotion", "url": "https://dm.example/1", "duration": 210},
        {"title": "Hidra - Ölüme İnat (320kbps)", "source": "Bandcamp", "url": "https://bc.example/1", "duration": 210},
        {"title": "Hidra - Olume Inat (Konser)", "source": "VK", "url": "https://vk.example/1", "duration": 220},
        {"title": "Saian - Felek (FLAC)", "source": "Archive.org", "url": "https://ar.example/2", "duration": 240},
    ]
    ranked, clusters = kh.cluster_and_rank_items(sample, query="Hidra Olume Inat")
    assert len(clusters) == 2
    hidra = next(it for it in ranked if "Hidra" in it["title"])
    assert hidra["source"] == "Bandcamp"
    assert hidra["mirrors_count"] == 3

    # Underground local file archive + lyrics sidecar
    wav = tmp_path / "demo.wav"
    wav.write_bytes(b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
    arc = kh.archive_underground_track(
        str(wav),
        title="Olume Inat",
        artist="Hidra",
        out_dir=str(tmp_path / "arch"),
        lyrics="[00:01.00] Test satiri",
    )
    assert arc["ok"] is True
    assert Path(arc["path"]).is_file()
    assert Path(arc["lyrics_path"]).is_file() and arc["lyrics_path"].endswith(".lrc")


def test_kami_mod_diff_and_profiles(tmp_path: Path, monkeypatch):
    from app.core import kami_mod as km

    monkeypatch.setattr(km, "_backups_root", lambda: tmp_path / "backups")

    game_dir = tmp_path / "game"
    game_dir.mkdir()
    (game_dir / "existing.txt").write_text("old", encoding="utf-8")

    z1 = tmp_path / "modA.zip"
    with zipfile.ZipFile(z1, "w") as zf:
        zf.writestr("existing.txt", "modA")
        zf.writestr("new_file.dat", "data")

    diff1 = km.preview_mod_diff(str(z1), str(game_dir))
    assert diff1["ok"] is True
    assert "new_file.dat" in diff1["added"]
    assert "existing.txt" in diff1["overwrite"]
    assert diff1["conflicts"] == []

    inst = km.install_mod(str(z1), str(game_dir))
    assert inst["ok"] is True

    z2 = tmp_path / "modB.zip"
    with zipfile.ZipFile(z2, "w") as zf:
        zf.writestr("new_file.dat", "conflict")

    diff2 = km.preview_mod_diff(str(z2), str(game_dir))
    assert diff2["ok"] is True
    assert len(diff2["conflicts"]) == 1 and diff2["conflicts"][0]["file"] == "new_file.dat"

    prof_path = tmp_path / "prof.json"
    exp = km.export_mod_profile(str(game_dir), str(prof_path))
    assert exp["ok"] is True and exp["mods_count"] == 1
    imp = km.import_mod_profile(str(prof_path))
    assert imp["ok"] is True and imp["present"] == ["modA"] and imp["missing"] == []

    km.rollback_mod(inst["id"])
    imp2 = km.import_mod_profile(str(prof_path))
    assert imp2["missing"] == ["modA"]


def test_game_highlight_build_fragmovie(tmp_path: Path):
    from app.core import game_highlight as gh
    from app.engines.ytdlp_engine import find_ffmpeg

    ff = find_ffmpeg()
    assert ff
    clip = tmp_path / "kill.mp4"
    # 3s synthetic clip with a loud audio spike at t=1.5s
    cmd = [
        ff, "-y", "-f", "lavfi", "-i", "color=c=black:s=640x360:d=3",
        "-f", "lavfi", "-i", "aevalsrc='if(between(t,1.3,1.7),0.9*sin(2*PI*220*t),0.01*sin(2*PI*100*t))':d=3",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(clip),
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    out_proj = tmp_path / "frag.kstudio"
    res = gh.build_fragmovie_project([str(clip)], out_kstudio=str(out_proj), title="Test Fragmovie")
    assert res["ok"] is True
    assert Path(res["path"]).is_file()
    data = json.loads(Path(res["path"]).read_text("utf-8"))
    assert len(data["clips"]) >= 1
    assert len(data["markers"]) >= 1
    # Audio peak was around 1.5s
    assert any(0.9 <= float(p["peak_src"]) <= 2.1 for p in res["peaks"])
