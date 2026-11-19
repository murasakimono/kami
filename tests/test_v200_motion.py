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
