"""Kami Studio Faz 9: After Effects hareket egrileri, Shutter Motion Blur,
Kinetik Tipografi, Cursor Auto-Zoom (.cursor.json), 2.5D/3D Kamera ve AI Takip/Talker kopruleri.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

BEZIER_PRESETS: dict[str, tuple[float, float, float, float]] = {
    "linear": (0.0, 0.0, 1.0, 1.0),
    "ease": (0.25, 0.1, 0.25, 1.0),
    "easeOutExpo": (0.16, 1.0, 0.3, 1.0),
    "snappy": (0.22, 1.0, 0.36, 1.0),
    "filmEase": (0.45, 0.0, 0.15, 1.0),
    "pop": (0.34, 1.45, 0.64, 1.0),
}


def cubic_bezier(p1x: float, p1y: float, p2x: float, p2y: float, t: float) -> float:
    """[0,1] zamaninda kubik Bezier Y degerini Newton-Raphson ile cozer."""
    t = max(0.0, min(1.0, float(t)))
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    cx = 3.0 * p1x
    bx = 3.0 * (p2x - p1x) - cx
    ax = 1.0 - cx - bx
    cy = 3.0 * p1y
    by = 3.0 * (p2y - p1y) - cy
    ay = 1.0 - cy - by

    u = t
    for _ in range(8):
        x = ((ax * u + bx) * u + cx) * u - t
        if abs(x) < 1e-6:
            break
        dx = (3.0 * ax * u + 2.0 * bx) * u + cx
        if abs(dx) < 1e-6:
            break
        u = max(0.0, min(1.0, u - x / dx))
    return ((ay * u + by) * u + cy) * u


def shutter_blur_params(shutter_angle: float = 180.0, fps: int = 30) -> dict[str, Any]:
    """After Effects Shutter Angle (0..360) -> GPU & ffmpeg hareket bulanikligi parametreleri."""
    ang = max(0.0, min(360.0, float(shutter_angle)))
    frac = round(ang / 360.0, 4)
    samples = max(1, min(16, int(round(ang / 22.5)))) if ang > 0 else 1
    return {
        "shutter_angle": ang,
        "blur_fraction": frac,
        "samples": samples,
        "fps": max(1, int(fps or 30)),
        "ffmpeg_filter": f"tblend=all_mode=average,framestep=1" if ang >= 90 else "",
    }


def kinetic_text_plan(
    text: str,
    start: float = 0.0,
    dur: float = 3.0,
    style: str = "pop",
    wght_from: int = 400,
    wght_to: int = 800,
) -> dict[str, Any]:
    """Kelime bazli kinetik tipografi + degisken font eksen (wght/slnt) plani uretir."""
    words = [w for w in str(text or "").strip().split() if w]
    if not words:
        return {"ok": False, "items": []}
    step = max(0.08, dur / max(1, len(words)))
    items = []
    for idx, w in enumerate(words):
        ws = round(start + idx * step, 3)
        we = round(min(start + dur, ws + max(step * 1.4, 0.35)), 3)
        items.append({
            "word": w,
            "start": ws,
            "end": we,
            "style": style,
            "wghtFrom": int(wght_from),
            "wghtTo": int(wght_to),
            "msdf": True,
        })
    return {"ok": True, "items": items, "count": len(items)}


def cursor_auto_zoom(
    events: list[dict[str, Any]],
    width: int = 1920,
    height: int = 1080,
    zoom_scale: float = 1.55,
    hold_sec: float = 1.2,
) -> list[dict[str, Any]]:
    """`.cursor.json` fare olaylarindan Screen Studio tarzi oto-zoom keyframe listesi uretir."""
    if not events:
        return []
    W = max(1.0, float(width or 1920))
    H = max(1.0, float(height or 1080))
    clicks = [e for e in events if e.get("click")]
    targets = clicks if clicks else events[:: max(1, len(events) // 6)]

    kfs: list[dict[str, Any]] = []
    last_t = -99.0
    for ev in targets:
        t = float(ev.get("t", 0.0))
        if t - last_t < hold_sec * 0.8:
            continue
        nx = max(0.15, min(0.85, float(ev.get("x", W / 2)) / W))
        ny = max(0.15, min(0.85, float(ev.get("y", H / 2)) / H))
        kfs.append({"t": round(max(0.0, t - 0.18), 3), "scale": 1.0, "x": 0.5, "y": 0.5, "ease": "easeOutExpo"})
        kfs.append({"t": round(t, 3), "scale": round(zoom_scale, 3), "x": round(nx, 4), "y": round(ny, 4), "ease": "easeOutExpo"})
        kfs.append({"t": round(t + hold_sec, 3), "scale": 1.0, "x": 0.5, "y": 0.5, "ease": "filmEase"})
        last_t = t
    return kfs


def parallax_25d_plan(depth_strength: float = 0.035, pan_x: float = 0.08, pan_y: float = 0.03, zoom: float = 1.08) -> dict[str, Any]:
    """2.5D derinlik haritasi kamerasi icin WebGL2 shader parametreleri doner."""
    return {
        "depth_strength": max(0.0, min(0.2, float(depth_strength))),
        "pan_x": max(-0.5, min(0.5, float(pan_x))),
        "pan_y": max(-0.5, min(0.5, float(pan_y))),
        "zoom": max(1.0, min(2.0, float(zoom))),
    }


def gyroflow_status() -> dict[str, Any]:
    exe = shutil.which("gyroflow") or shutil.which("gyroflow.exe")
    return {"installed": bool(exe), "path": exe or ""}


def musetalk_preflight() -> dict[str, Any]:
    """MuseTalk (4-5.5 GB VRAM) calistirmadan once 6 GB RTX 4050 VRAM guvenlik kontrolu."""
    from app.core.vram_guard import preflight
    return preflight(required_mb=4200)
