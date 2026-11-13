"""Faz 9 testleri: Bezier/Shutter, Kinetik Tipografi, Cursor Auto-Zoom,
2.5D Paralaks, Marka Kiti & 5 Viral Kurgu Paketi + MCP run_recipe + Scopes.
"""
from __future__ import annotations

from pathlib import Path

from app import paths
from app.core.studio_brand import BrandKitStore, apply_viral_recipe, list_recipes
from app.core.studio_mcp import TOOLS
from app.core.studio_motion import (
    BEZIER_PRESETS,
    cubic_bezier,
    cursor_auto_zoom,
    kinetic_text_plan,
    parallax_25d_plan,
    shutter_blur_params,
)


def test_bezier_and_shutter_blur() -> None:
    assert cubic_bezier(0.0, 0.0, 1.0, 1.0, 0.0) == 0.0
    assert cubic_bezier(0.0, 0.0, 1.0, 1.0, 1.0) == 1.0
    p1x, p1y, p2x, p2y = BEZIER_PRESETS["easeOutExpo"]
    mid = cubic_bezier(p1x, p1y, p2x, p2y, 0.5)
    assert 0.85 < mid <= 1.0

    sh = shutter_blur_params(180.0, 30)
    assert sh["blur_fraction"] == 0.5
    assert sh["samples"] == 8
    assert "tblend=" in sh["ffmpeg_filter"]


def test_kinetic_text_and_cursor_auto_zoom() -> None:
    plan = kinetic_text_plan("Kami Studio Hızlı Kurgu", start=1.0, dur=2.0, style="pop")
    assert plan["ok"] is True
    assert plan["count"] == 4
    assert plan["items"][0]["word"] == "Kami"
    assert plan["items"][0]["msdf"] is True

    events = [
        {"t": 0.5, "x": 960, "y": 540, "click": True},
        {"t": 0.7, "x": 980, "y": 550, "click": True},  # hold_sec icinde: filtrelenir
        {"t": 3.0, "x": 300, "y": 200, "click": True},
    ]
    kfs = cursor_auto_zoom(events, width=1920, height=1080, zoom_scale=1.6, hold_sec=1.0)
    assert len(kfs) == 6
    assert kfs[1]["scale"] == 1.6
    assert kfs[4]["x"] < 0.25

    par = parallax_25d_plan(0.05, 0.1, -0.05, 1.15)
    assert par["depth_strength"] == 0.05
    assert par["zoom"] == 1.15


def test_brand_kit_and_viral_recipes(tmp_path: Path) -> None:
    store = BrandKitStore(path=tmp_path / "brand_kits.json")
    saved = store.save("magaza", {"name": "Venma", "primary": "#FF3366"})
    assert saved["name"] == "Venma"
    assert store.load("magaza")["primary"] == "#FF3366"

    recs = list_recipes()
    assert len(recs) >= 12
    assert {
        "iman_gadzhi", "magnates_media", "ali_abdaal", "fps_frag", "minimal_shorts",
        "rap_mv_dark", "roblox_gaming", "anime_velocity", "mrbeast_retention",
        "podcast_clip", "retro_vhs", "cinematic_vlog",
    }.issubset({r["id"] for r in recs})

    proj = {
        "name": "Test",
        "clips": [
            {"id": "c1", "kind": "video", "start": 0.0, "in": 0.0, "out": 5.0},
            {"id": "c2", "kind": "video", "start": 5.0, "in": 0.0, "out": 5.0},
        ],
        "markers": [],
    }
    res = apply_viral_recipe(proj, "iman_gadzhi", brand_kit=saved, clip_ids=["c1"])
    assert res["ok"] is True
    assert res["applied_clips"] == 1
    assert res["project"]["shutterAngle"] == 180
    assert res["project"]["clips"][0]["grade"]["con"] == 0.16
    assert "grade" not in res["project"]["clips"][1]


def test_mcp_recipe_tools_and_scopes_js() -> None:
    assert "list_recipes" in TOOLS
    assert "run_recipe" in TOOLS
    scopes_js = (paths.WEB_DIR / "studio-scopes.js").read_text(encoding="utf-8")
    assert "drawWaveform" in scopes_js and "drawParade" in scopes_js and "drawVectorscope" in scopes_js
