"""v1.35.0 regresyon testleri: Oda cid tekillestirme, Mini-Ada temizleme, Soundboard SFX benzersizligi,
6 HyperFrames Motion Graphics blogu, Oyun last_played/favori ve Muzik/Player bilesenleri."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
from unittest.mock import MagicMock

from app import paths
from app.core import games, room, studio, studio_anim, studio_gfx, winwin
from app.engines.ytdlp_engine import find_ffmpeg


def test_room_cid_dedup_and_leave_cid():
    rm = room.Room("Metehan", "r-test")
    rm.touch("p1", "Metehan", "user", cid="kami-host")
    rm.touch("p2", "Sallit", "user", cid="guest-ipad")
    assert [p["id"] for p in rm._roster()] == ["p1", "p2"]
    # Yeniden baglanan host (ayni cid, yeni pid) eski hayalet p1'i silmeli
    rm.touch("p3", "Metehan", "user", cid="kami-host")
    ids = [p["id"] for p in rm._roster()]
    assert "p1" not in ids
    assert ids == ["p2", "p3"]
    # Pencere kapanisinda leave_cid tum eslesen hayaletleri cikarir
    rm.leave_cid("kami-host")
    assert [p["id"] for p in rm._roster()] == ["p2"]


def test_soundboard_unique_assets_and_oiia():
    ff = find_ffmpeg()
    assert ff
    sfx_dir = Path(studio.__file__).resolve().parent.parent / "assets" / "sfx"
    hashes: dict[str, list[str]] = {}
    for ogg in sorted(sfx_dir.glob("*.ogg")):
        res = subprocess.run([ff, "-v", "error", "-i", str(ogg), "-f", "s16le", "-ar", "16000", "-ac", "1", "-"],
                             capture_output=True)
        h = hashlib.md5(res.stdout).hexdigest()
        hashes.setdefault(h, []).append(ogg.name)
    dups = {h: names for h, names in hashes.items() if len(names) > 1}
    assert dups == {}, f"Ayni sesi calan kopya .ogg dosyalari var: {dups}"
    sounds = {x["id"]: x for x in room.soundboard_list()}
    assert "oiia-spin" in sounds
    data = room.soundboard_file("oiia-spin")
    assert data and len(data) > 1000


def test_hyperframes_motion_blocks_render_ass_and_catalog():
    cat = studio.catalog()
    expected = ("hf-glass-shard", "hf-wireframe-portal", "hf-code-slice",
                "hf-orbit-carousel", "hf-canopy-part", "hf-matrix-kinetic")
    for k in expected:
        assert k in cat["graphics"]
        lines = studio_gfx.graphic(
            k, studio._ts, studio._col, studio._esc, studio._rrect,
            0.0, 4.0, 1920, 1080, {"title": "TEST BAŞLIK", "sub": "İKİNCİ FAZ"},
        )
        assert len(lines) >= 2
        assert any("Dialogue:" in ln for ln in lines)
    tcat = studio_anim.text_catalog()
    for anim_k in ("portal-burst", "tile-flip", "shard-assemble"):
        assert anim_k in tcat["in"]


def test_mini_island_leave_clears_state(tmp_path, monkeypatch):
    from app.ui.api import Api

    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    mgr = MagicMock()
    mgr.debrid = None
    mgr.settings.get = lambda k, d=None: True if k == "room_island" else d
    api = Api(mgr, MagicMock(), MagicMock(), lambda: 0)
    api._island_win = MagicMock()
    api.room_island_push({"people": [{"name": "Metehan", "me": True}, {"name": "Sallit", "me": False}], "muted": False, "deaf": False})
    assert api._room_island is not None
    assert api._island_shown is True
    # Odadan ayrilinca state aninda sifirlanmali ve oto-acilan ada gizlenmeli
    api.room_island_push({"people": [], "left": True})
    assert api._room_island is None
    assert api._island_shown is False
    assert callable(winwin.round_pill)


def test_games_favorites_and_last_played(tmp_path, monkeypatch):
    import os
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(os, "startfile", lambda target: None, raising=False)
    exe = tmp_path / "demo_game.exe"
    exe.write_bytes(b"MZ")
    r_add = games.add_custom_game("Test Demo", str(exe))
    assert r_add["ok"] is True
    r_fav = games.toggle_favorite("testdemo")
    assert r_fav == {"ok": True, "favorite": True}
    r_launch = games.launch_game(str(exe), key="testdemo")
    assert r_launch == {"ok": True}
    assert games._load_json(games._last_played_path()).get("testdemo", 0) > 0
    assert games._load_json(games._favorites_path()).get("testdemo") is True
