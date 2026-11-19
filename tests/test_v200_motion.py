"""Kami 2.0 Birlesik Hareket & Mikro-Etkilesim Katmani testleri."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "app" / "ui" / "web"


def test_kami_motion_assets_and_api():
    css = (WEB / "kami-motion.css").read_text(encoding="utf-8")
    for tok in (
        "@starting-style",
        "interpolate-size: allow-keywords",
        "linear(",
        "prefers-reduced-motion: reduce",
        ".km-err-shake",
        ".km-hold-btn",
        ".km-morph-ok",
        "#kmToastDeck",
        ".km-glider",
        ".km-glow",
        "#kmTip",
        ".km-odo",
        "km-bell-wiggle",
        "km-radial-wipe",
    ):
        assert tok in css, f"CSS token eksik: {tok}"

    js = (WEB / "kami-motion.js").read_text(encoding="utf-8")
    for fn in (
        "function shake(",
        "function morphDone(",
        "function attachHold(",
        "function toast(",
        "function bindGlider(",
        "function initProximityGlow(",
        "function initInstantTooltips(",
        "function rollNumber(",
        "function flip(",
        "function radialThemeTransition(",
        "function ringBell(",
    ):
        assert fn in js, f"JS fonksiyon eksik: {fn}"


def test_kami_motion_wired_across_modules():
    from app.core import room

    for static_key in ("kami-motion.css", "kami-motion.js", "kami-20.js"):
        assert static_key in room.STATIC

    idx = (WEB / "index.html").read_text(encoding="utf-8")
    assert "kami-motion.css" in idx
    assert "kami-motion.js" in idx

    embed = (WEB / "kami-embed.js").read_text(encoding="utf-8")
    assert "kami-motion.css" in embed
    assert "kami-motion.js" in embed

    fx = (WEB / "kami-fx.js").read_text(encoding="utf-8")
    assert "offset-path" in fx

    app_js = (WEB / "app.js").read_text(encoding="utf-8")
    assert "KamiMotion.toast" in app_js
    assert "KamiMotion?.shake" in app_js

    sunak_js = (WEB / "sunak.js").read_text(encoding="utf-8")
    assert "KamiMotion.rollNumber" in sunak_js
    assert "ringBell" in sunak_js

    cl_js = (WEB / "cleaner-v138.js").read_text(encoding="utf-8")
    assert "KamiMotion.attachHold" in cl_js
    assert "km-hold-lbl" in cl_js
    assert "bindGlider" in cl_js

    acc_js = (WEB / "accent.js").read_text(encoding="utf-8")
    assert "radialThemeTransition" in acc_js

    st_js = (WEB / "studio-v138.js").read_text(encoding="utf-8")
    assert "km-pop-origin" in st_js

    rd_js = (WEB / "reader-plus.js").read_text(encoding="utf-8")
    assert "km-pop-origin" in rd_js

    ed_js = (WEB / "editor.js").read_text(encoding="utf-8")
    assert "KamiMotion.flip" in ed_js
    assert 'data-id="${l.id}"' in ed_js

    k20_js = (WEB / "kami-20.js").read_text(encoding="utf-8")
    assert "morphDone" in k20_js
    assert "top: 10px" in k20_js

    games_html = (WEB / "games.html").read_text(encoding="utf-8")
    assert "KamiMotion.flip" in games_html

    ps_js = (WEB / "player-shell.js").read_text(encoding="utf-8")
    assert "KamiMotion.toast" in ps_js


def test_motion_selectors_and_hud_allowlist():
    import threading
    import time as _t
    from types import SimpleNamespace
    from app.ui.api import Api

    css = (WEB / "kami-motion.css").read_text(encoding="utf-8")
    for sel in ("#k20Cheat:not([hidden])", ".k20-rnode:active", '[data-mod="cleaner"]', ".km-glow:not(.tilting)::after", "bottom: 76px"):
        assert sel in css, f"Duzeltilmis CSS secici eksik: {sel}"

    js = (WEB / "kami-motion.js").read_text(encoding="utf-8")
    assert ".gcard" in js and "aside.side" in js and ".rd-top button" in js and ".pl-deck button" in js
    assert ".sk-dock button" not in js

    sunak_js = (WEB / "sunak.js").read_text(encoding="utf-8")
    assert 'data-gkey="${gk}"' in sunak_js

    api = object.__new__(Api)
    api._inbox_lock = threading.Lock()
    api._conv_lock = threading.Lock()
    api._conv_jobs = []
    api._manager = SimpleNamespace(snapshot=lambda: [])
    now = _t.monotonic()
    api._jobs = {
        "j1": {"state": "running", "name": "player_lyrics", "t": now},
        "j2": {"state": "running", "name": "player_skips", "t": now},
        "j3": {"state": "running", "name": "rd_status", "t": now},
        "j4": {"state": "running", "name": "cleaner_dust", "t": now - 1000},  # bayat (>15 dk)
        "lrc_a1": {"state": "running", "name": "LRC: deneme.mp3", "p": 0.42},
        "j5": {"state": "running", "name": "studio_export", "t": now, "p": 0.75},
    }
    res = api.active_jobs_hud()
    assert res["ok"] is True
    assert res["count"] == 2
    kinds = {it["kind"] for it in res["items"]}
    titles = {it["title"] for it in res["items"]}
    assert kinds == {"AI Altyazı", "Kami Studio"}
    assert "player_lyrics" not in titles
    assert "player_skips" not in titles
    assert "rd_status" not in titles


def test_six_new_animations_present_and_wired():
    css = (WEB / "kami-motion.css").read_text(encoding="utf-8")
    for tok in (
        ".km-cascade-item",
        "km-cascade-in",
        ".km-eq",
        "km-eq-bar",
        "animation-timeline: scroll(",
        "timeline-scope: --km-rd-scroll",
        "km-sheen-sweep",
        "km-portal-breathe",
        "km-portal-absorb",
        ".km-absorb",
        "#kpal .kp-l > .km-glider",
    ):
        assert tok in css, f"Yeni animasyon CSS tokeni eksik: {tok}"

    js = (WEB / "kami-motion.js").read_text(encoding="utf-8")
    for fn in ("function cascade(", "function eqHtml(", "function initDragPortals("):
        assert fn in js, f"Yeni animasyon JS fonksiyonu eksik: {fn}"

    pal_js = (WEB / "palette.js").read_text(encoding="utf-8")
    assert "kp-rows" in pal_js
    assert "bindGlider" in pal_js
    assert "syncSel(" in pal_js

    music_html = (WEB / "music.html").read_text(encoding="utf-8")
    assert "syncPlayingRow" in music_html
    assert "refreshListMotion" in music_html
    assert 'data-uri="${esc(t.uri' in music_html

    pl_lib = (WEB / "player-lib.js").read_text(encoding="utf-8")
    assert "KamiMotion.eqHtml" in pl_lib

    games_html = (WEB / "games.html").read_text(encoding="utf-8")
    assert "KamiMotion?.cascade" in games_html

    cl_js = (WEB / "cleaner-v138.js").read_text(encoding="utf-8")
    assert "cl-scroll" in cl_js
    assert "KamiMotion?.cascade" in cl_js

    sunak_js = (WEB / "sunak.js").read_text(encoding="utf-8")
    assert "KamiMotion?.cascade" in sunak_js


