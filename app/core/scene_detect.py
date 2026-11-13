"""Faz 12.1 & 12.2 Backend — Sahne Haritasi (FFmpeg/PySceneDetect) ve ReplayGain 2.0 (EBU R128)."""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _ffmpeg() -> str:
    try:
        from app.engines.ytdlp_engine import find_ffmpeg
        return find_ffmpeg() or ""
    except Exception:
        import shutil
        return shutil.which("ffmpeg") or ""


def detect_scenes(video_path: str | Path, *, threshold: float = 0.32, max_scenes: int = 80) -> dict[str, Any]:
    """Video sahne gecis zamanlarini cikarir (PySceneDetect varsa onu, yoksa FFmpeg scene filtresi)."""
    p = Path(video_path)
    if not p.is_file():
        return {"ok": False, "error": "Video dosyasi bulunamadi", "scenes": []}

    try:
        import scenedetect
        from scenedetect import ContentDetector, detect
        scene_list = detect(str(p), ContentDetector(threshold=max(10.0, threshold * 85.0)))
        scenes = [
            {"index": i, "start": round(s[0].get_seconds(), 2), "end": round(s[1].get_seconds(), 2)}
            for i, s in enumerate(scene_list[:max_scenes])
        ]
        return {"ok": True, "method": "pyscenedetect", "scenes": scenes}
    except Exception:
        pass

    ff = _ffmpeg()
    if not ff:
        return {"ok": False, "error": "FFmpeg bulunamadi", "scenes": []}

    cmd = [
        ff, "-hide_banner", "-i", str(p),
        "-vf", f"select='gt(scene,{threshold:.2f})',showinfo",
        "-f", "null", "-",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180, creationflags=NO_WINDOW)
    times: list[float] = [0.0]
    for m in re.finditer(r"pts_time:([0-9]+(?:\.[0-9]+)?)", r.stderr or ""):
        t = round(float(m.group(1)), 2)
        if not times or t - times[-1] >= 1.0:
            times.append(t)
        if len(times) >= max_scenes:
            break

    scenes = []
    for i, start in enumerate(times):
        end = times[i + 1] if i + 1 < len(times) else None
        scenes.append({"index": i, "start": start, "end": end})
    return {"ok": True, "method": "ffmpeg", "scenes": scenes}


def measure_replaygain(media_path: str | Path, *, target_lufs: float = -18.0) -> dict[str, Any]:
    """EBU R128 (ReplayGain 2.0) ile parca ses yuksekligi ve onerilen kazanc dB hesaplar."""
    p = Path(media_path)
    if not p.is_file():
        return {"ok": False, "error": "Medya dosyasi bulunamadi"}
    ff = _ffmpeg()
    if not ff:
        return {"ok": False, "error": "FFmpeg bulunamadi"}

    r = subprocess.run(
        [ff, "-hide_banner", "-i", str(p), "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True, timeout=120, creationflags=NO_WINDOW,
    )
    stderr = r.stderr or ""
    m_i = re.findall(r"I:\s*(-?[0-9]+(?:\.[0-9]+)?)\s*LUFS", stderr)
    m_pk = re.findall(r"Peak:\s*(-?[0-9]+(?:\.[0-9]+)?)\s*dBFS", stderr)
    if not m_i:
        return {"ok": False, "error": "EBU R128 olculemedi"}

    integrated = float(m_i[-1])
    peak_db = float(m_pk[-1]) if m_pk else -1.0
    gain_db = round(max(-15.0, min(12.0, target_lufs - integrated)), 2)
    # Kirpmayi (clipping) onlemek icin peak siniri uygula
    if peak_db + gain_db > -0.5:
        gain_db = round(-0.5 - peak_db, 2)
    linear = round(10.0 ** (gain_db / 20.0), 4)
    return {
        "ok": True,
        "integrated_lufs": integrated,
        "true_peak_db": peak_db,
        "gain_db": gain_db,
        "linear_gain": linear,
    }
