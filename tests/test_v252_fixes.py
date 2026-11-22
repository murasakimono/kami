"""Tests for Kami v2.5.2 bugfixes, UI overhaul, Mini-Ada PiP, YouTube Watch-Together, Beat DAW, and Alt+G Companion."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "app" / "ui" / "web"


def test_player_url_watch_uses_player_open_url():
    src = (WEB / "player-v138.js").read_text(encoding="utf-8")
    assert "plShow(" not in src
    assert "playerOpenUrl" in src


def test_player_css_preserves_mini_player_colors():
    css = (WEB / "player.css").read_text(encoding="utf-8")
    assert "#player.mini .pmi-txt b { font: 600 13px" in css
    assert "color: #B9B2C9;" in css
    assert "color: #fff;" in css


def test_player_music_pm_meta_preserves_song_title_with_ft_and_pipe():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    js_path = (WEB / "player-music.js").read_text(encoding="utf-8")
    # Extract helper block (pmStripNoise..plMiniLabels) up to plMiniSync
    start = js_path.index("function pmStripNoise")
    end = js_path.index("// Mini oynatıcı")
    snippet = js_path[start:end]
    driver = f"""
const window = globalThis;
const $ = () => null;
const PM = {{ lines: [], plain: "", idx: -1 }};
const PL = {{}};
const plL = (a) => a;
{snippet}
const cases = [
  {{ r: {{ path: "C:/Music/Contra ft. Itimat - Ölü.mp3", title: "Contra ft. Itimat - Ölü", tags: {{ artist: "Contra" }} }}, wantArtist: "Contra", wantTitle: "Ölü" }},
  {{ r: {{ path: "C:/Music/Contra | Ölü.mp3", title: "Contra | Ölü", tags: {{}} }}, wantArtist: "Contra", wantTitle: "Ölü" }},
  {{ r: {{ path: "C:/Music/Contra - Ölü (Official Music Video).mp3", tags: {{}} }}, wantArtist: "Contra", wantTitle: "Ölü" }},
  {{ r: {{ path: "C:/Music/Contra - Ölü | Lyric Video.mp3", tags: {{}} }}, wantArtist: "Contra", wantTitle: "Ölü" }},
  {{ r: {{ path: "D:/Rap/Contra - Ölü.mp3", title: "Contra - Ölü", tags: {{ artist: "Contra", title: "Contra" }} }}, wantArtist: "Contra", wantTitle: "Ölü" }},
];
const out = cases.map((c) => {{
  const m = pmMeta(c.r);
  PM.meta = m;
  const lbl = plMiniLabels(c.r);
  return {{ m, lbl, ok: m.artist === c.wantArtist && m.title === c.wantTitle && lbl.sub === c.wantTitle && lbl.top.includes(c.wantArtist) }};
}});
console.log(JSON.stringify(out));
"""
    res = subprocess.run([node, "-e", driver], capture_output=True, text=True, encoding="utf-8")
    assert res.returncode == 0, res.stderr
    results = json.loads(res.stdout)
    assert all(x["ok"] for x in results), results


def test_room_mini_and_youtube_watch_together():
    rjs = (WEB / "room.js").read_text(encoding="utf-8")
    rcss = (WEB / "room.css").read_text(encoding="utf-8")
    assert '$("ytTile") ? 1 : 0' in rjs
    assert "ytFallbackDirect" in rjs
    assert "origin: location.origin" in rjs
    assert "room_mini_mode" in rjs
    assert "body.rm-mini" in rcss
    assert ".tile.yt video" in rcss


def test_beat_daw_and_fonts_and_companion_wiring():
    bhtml = (WEB / "beat.html").read_text(encoding="utf-8")
    bcss = (WEB / "beat.css").read_text(encoding="utf-8")
    bjs = (WEB / "beat.js").read_text(encoding="utf-8")
    chtml = (WEB / "companion.html").read_text(encoding="utf-8")
    ghtml = (WEB / "games.html").read_text(encoding="utf-8")

    assert '@font-face { font-family: "Chakra Petch"' in bcss
    assert 'id="trPlay"' in bhtml and 'id="fxRack"' in bhtml and 'id="boothQrImg"' in bhtml
    assert "drawWaveform" in bjs and "beat_media_url" in bjs and "beat_qr_svg" in bjs

    assert '@font-face { font-family: "Chakra Petch"' in chtml
    assert "kamiCompanionSetGame" in chtml and "games_companion_hide" in chtml
    assert "games_companion_toggle" in ghtml
    assert 'input[type="text"],input[type="password"]' in ghtml


def test_api_and_main_expose_v252_methods():
    from app.ui.api import Api

    for name in ("room_mini_mode", "room_mini_move", "beat_media_url", "beat_qr_svg", "games_companion_toggle", "games_companion_hide"):
        assert callable(getattr(Api, name, None)), f"Api missing {name}"

    main_src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert "_make_companion_window" in main_src
    assert '"companion_hotkey"' in main_src
    assert 'alt+g' in main_src
