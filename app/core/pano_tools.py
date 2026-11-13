"""Faz 16.3 — Kami Pano (Dropover Rafi), OKLCH Renk Secici, Piksel Cetveli & Ekran OCR Koprusu.

Mevcut clipboard.py ve ocr.py modullerine dokunmaz; pano rafindan dogrudan ocr.read_text() cagirir.
"""
from __future__ import annotations

import json
import math
import tempfile
import time
from pathlib import Path
from typing import Any


def _shelf_path(data_dir: Path | None = None) -> Path:
    if data_dir:
        return Path(data_dir) / "pano_shelf.json"
    from app import paths
    return paths.DATA_DIR / "pano_shelf.json"


def list_shelf(data_dir: Path | None = None) -> list[dict[str, Any]]:
    p = _shelf_path(data_dir)
    if not p.is_file():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, list) else []
    except Exception:
        return []


def add_shelf_item(kind: str, value: str, label: str = "", data_dir: Path | None = None) -> dict[str, Any]:
    items = list_shelf(data_dir)
    entry = {
        "id": f"p_{int(time.time() * 1000)}_{len(items)}",
        "kind": kind,
        "value": value,
        "label": label or (Path(value).name if kind == "file" else value[:48]),
        "ts": int(time.time()),
    }
    items.insert(0, entry)
    items = items[:60]
    p = _shelf_path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "item": entry, "count": len(items)}


def remove_shelf_item(item_id: str, data_dir: Path | None = None) -> dict[str, Any]:
    items = [it for it in list_shelf(data_dir) if it.get("id") != item_id]
    p = _shelf_path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "count": len(items)}


def rgb_to_oklch_info(r: int, g: int, b: int) -> dict[str, Any]:
    from app.core.picture_pro import _srgb_to_oklch
    L, C, H = _srgb_to_oklch(r / 255.0, g / 255.0, b / 255.0)
    return {
        "ok": True,
        "rgb": [int(r), int(g), int(b)],
        "hex": f"#{int(r):02X}{int(g):02X}{int(b):02X}",
        "oklch": [L, C, H],
        "css": f"oklch({L:.3f} {C:.3f} {H:.1f})",
    }


def pick_screen_oklch(x: int, y: int) -> dict[str, Any]:
    try:
        from PIL import ImageGrab
        im = ImageGrab.grab(bbox=(int(x), int(y), int(x) + 1, int(y) + 1))
        r, g, b = im.convert("RGB").getpixel((0, 0))
        return rgb_to_oklch_info(r, g, b)
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def measure_pixel_rect(x1: int, y1: int, x2: int, y2: int) -> dict[str, Any]:
    w = abs(int(x2) - int(x1))
    h = abs(int(y2) - int(y1))
    diag = round(math.hypot(w, h), 2)
    g = math.gcd(w, h) if (w and h) else 1
    return {
        "ok": True,
        "width": w,
        "height": h,
        "diagonal": diag,
        "aspect": f"{w // g}:{h // g}" if (w and h) else "0:0",
    }


def pano_ocr_region(x: int, y: int, w: int, h: int, lang: str = "") -> dict[str, Any]:
    """Ekran bolgesini yakalar ve mevcut app.core.ocr.read_text() ile metni okur."""
    if w <= 2 or h <= 2:
        return {"ok": False, "error": "Gecersiz bolge boyutu"}
    tmp = Path(tempfile.gettempdir()) / f"kami_pano_ocr_{int(time.time() * 1000)}.png"
    try:
        from PIL import ImageGrab
        from app.core import ocr
        im = ImageGrab.grab(bbox=(int(x), int(y), int(x + w), int(y + h)))
        im.save(tmp)
        res = ocr.read_text(str(tmp), lang=lang)
        return {"ok": True, **res}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}
    finally:
        tmp.unlink(missing_ok=True)
