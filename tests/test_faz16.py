"""Faz 16 testleri: UxPlay/scrcpy kopru, LAN P2P paylasim, Kami Pano (OKLCH/cetvel/raf) & Hey Kami sesli komut."""
from __future__ import annotations

import urllib.request
from pathlib import Path

from app.core import lan_p2p, pano_tools, screen_bridge, voice_cmd


def test_screen_bridge_status():
    st = screen_bridge.mirror_status()
    assert st["ok"] is True
    assert "scrcpy_installed" in st
    assert "uxplay_installed" in st


def test_lan_p2p_token_protected_share(tmp_path: Path):
    sample = tmp_path / "deneme.txt"
    sample.write_text("Kami LAN P2P Test", encoding="utf-8")

    srv = lan_p2p.LanShareServer()
    try:
        info = srv.share_file(sample)
        assert info["ok"] is True
        local_url = info["url"].replace(lan_p2p.local_lan_ip(), "127.0.0.1")
        with urllib.request.urlopen(local_url, timeout=5) as resp:
            assert resp.read().decode("utf-8") == "Kami LAN P2P Test"
    finally:
        srv.stop()


def test_pano_shelf_oklch_and_ruler(tmp_path: Path):
    added = pano_tools.add_shelf_item("text", "oklch(0.7 0.2 290)", label="Mor", data_dir=tmp_path)
    assert added["ok"] is True
    items = pano_tools.list_shelf(data_dir=tmp_path)
    assert len(items) == 1
    pano_tools.remove_shelf_item(added["item"]["id"], data_dir=tmp_path)
    assert pano_tools.list_shelf(data_dir=tmp_path) == []

    col = pano_tools.rgb_to_oklch_info(124, 58, 237)
    assert col["hex"] == "#7C3AED"
    assert col["css"].startswith("oklch(")

    rect = pano_tools.measure_pixel_rect(10, 20, 1930, 1100)
    assert rect["width"] == 1920
    assert rect["height"] == 1080
    assert rect["aspect"] == "16:9"


def test_voice_command_parser():
    no_wake = voice_cmd.parse_voice_command("duraklat")
    assert no_wake["wake"] is False

    cmd1 = voice_cmd.parse_voice_command("Hey Kami, klip al")
    assert cmd1["ok"] is True
    assert cmd1["wake"] is True
    assert cmd1["action"] == "save_replay"

    cmd2 = voice_cmd.parse_voice_command("kami ekran oku")
    assert cmd2["action"] == "ocr"
