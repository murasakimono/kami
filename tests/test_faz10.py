"""Faz 10 testleri: Photoshop Pro, Lightroom LUT/HDR/Focus, Kami Mockup, OKLCH ve Telif Imzasi."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from app import paths
from app.core.picture_pro import (
    ai_bridge_status,
    apply_adjustment_layer,
    clone_lut_from_reference,
    cube_to_haldclut,
    ecommerce_studio_pack,
    embed_blind_watermark,
    extract_blind_watermark,
    focus_stack_laplacian,
    frequency_separation,
    hdr_merge_mertens,
    oklch_palette,
    perspective_mockup,
    seam_carve_resize,
)


def _make_sample(path: Path, size=(96, 96), color=(120, 80, 200)) -> Path:
    im = Image.new("RGB", size, color)
    dr = ImageDraw.Draw(im)
    dr.rectangle([20, 20, size[0] - 20, size[1] - 20], fill=(240, 190, 90))
    im.save(path)
    return path


def test_photoshop_freq_sep_seam_carve_and_adj(tmp_path: Path) -> None:
    src = _make_sample(tmp_path / "src.png", size=(80, 64))

    fs = frequency_separation(str(src), radius=3.0)
    assert fs["ok"] is True
    assert Path(fs["low_path"]).is_file() and Path(fs["high_path"]).is_file()

    sc = seam_carve_resize(str(src), 64, 52)
    assert sc["ok"] is True
    assert Image.open(sc["path"]).size == (64, 52)

    adj = apply_adjustment_layer(str(src), {"exposure": 0.4, "vibrance": 0.3, "dehaze": 0.2, "tonemap": "agx"})
    assert adj["ok"] is True and Path(adj["path"]).is_file()


def test_lightroom_lut_hald_hdr_and_focus_stack(tmp_path: Path) -> None:
    src = _make_sample(tmp_path / "s.png", color=(40, 40, 60))
    ref = _make_sample(tmp_path / "r.png", color=(200, 120, 60))
    cube = tmp_path / "cloned.cube"

    lut_res = clone_lut_from_reference(str(src), str(ref), str(cube), size=9)
    assert lut_res["ok"] is True
    assert "LUT_3D_SIZE 9" in cube.read_text(encoding="utf-8")

    hald = cube_to_haldclut(str(cube), str(tmp_path / "hald.png"))
    assert hald["ok"] is True and Path(hald["path"]).is_file()

    dark = _make_sample(tmp_path / "e1.png", color=(30, 30, 30))
    bright = _make_sample(tmp_path / "e2.png", color=(210, 210, 210))
    hdr = hdr_merge_mertens([str(dark), str(bright)], str(tmp_path / "hdr.png"))
    assert hdr["ok"] is True and Path(hdr["path"]).is_file()

    fstack = focus_stack_laplacian([str(dark), str(bright)], str(tmp_path / "focus.png"))
    assert fstack["ok"] is True and Path(fstack["path"]).is_file()


def test_mockup_ecommerce_oklch_and_watermark(tmp_path: Path) -> None:
    fg = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
    ImageDraw.Draw(fg).ellipse([20, 20, 100, 100], fill=(124, 58, 237, 255))
    fg_path = tmp_path / "fg.png"
    fg.save(fg_path)

    ecom = ecommerce_studio_pack(str(fg_path), pad_ratio=0.12, size=400, shadow=True)
    assert ecom["ok"] is True and Image.open(ecom["path"]).size == (400, 400)

    base = _make_sample(tmp_path / "base.png", size=(200, 200))
    design = _make_sample(tmp_path / "design.png", size=(80, 80), color=(46, 230, 166))
    mock = perspective_mockup(str(design), str(base), [[40, 30], [160, 45], [150, 170], [35, 160]])
    assert mock["ok"] is True and Path(mock["path"]).is_file()

    pal = oklch_palette(str(base), count=4)
    assert pal["ok"] is True and len(pal["colors"]) == 4
    assert pal["colors"][0]["css"].startswith("oklch(")

    wm_src = _make_sample(tmp_path / "wm_src.png", size=(160, 160))
    emb = embed_blind_watermark(str(wm_src), "Kami-Metehan-2026")
    assert emb["ok"] is True
    ext = extract_blind_watermark(emb["path"])
    assert ext["ok"] is True and ext["text"] == "Kami-Metehan-2026"

    bridge = ai_bridge_status()
    assert "comfyui_running" in bridge and "vram_6gb_preflight" in bridge
    assert "applyLayerStyles" in (paths.WEB_DIR / "editor-fx.js").read_text(encoding="utf-8")
