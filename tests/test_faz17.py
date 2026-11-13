"""Faz 17 — Sunak PixiJS v8 GPU Sahnesi & Eklemli Kukla Maskot dogrulama testleri."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "app" / "ui" / "web"


def test_pixi_v8_bundle_and_sunak_gpu_contract():
    pixi_js = WEB / "vendor" / "pixi" / "pixi.min.js"
    assert pixi_js.is_file()
    assert pixi_js.stat().st_size > 200_000

    gpu_js = (WEB / "sunak-gpu.js").read_text(encoding="utf-8")
    for token in (
        "KamiSunakGPU",
        "initBg",
        "initAltar",
        "setState",
        "setFx",
        "triggerSwallow",
        "setCostume",
        "ColorMatrixFilter",
        "PuppetRig",
        "ribbons",
    ):
        assert token in gpu_js


def test_sunak_html_css_and_sfx_integration():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    pixi_pos = html.find('src="vendor/pixi/pixi.min.js"')
    gpu_pos = html.find('src="sunak-gpu.js"')
    sunak_pos = html.find('src="sunak.js"')
    assert pixi_pos != -1 and gpu_pos != -1 and sunak_pos != -1
    assert pixi_pos < gpu_pos < sunak_pos

    css = (WEB / "sunak.css").read_text(encoding="utf-8")
    assert "body.sunak-gpu #skAltar svg.sk-ring" in css
    assert "body.sunak-gpu #skAltar canvas.sk-char" in css
    assert "body.sunak-gpu #skFx" in css

    sunak_js = (WEB / "sunak.js").read_text(encoding="utf-8")
    assert "KamiSunakGPU" in sunak_js
    assert "fxInit2D" in sunak_js

    sfx_js = (WEB / "sunak-sfx.js").read_text(encoding="utf-8")
    assert "KamiSunakGPU?.setCostume" in sfx_js
