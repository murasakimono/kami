"""Kami Ghost: metadata/EXIF/FFmpeg parmak izi temizleyici + Content-ID kalkanı."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from app.core import converter

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
AUDIO_EXTS = {".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg", ".opus"}
VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v"}


def _tools(tools: dict[str, str] | None = None) -> dict[str, str]:
    if tools:
        return tools
    from app.engines.ytdlp_engine import find_ffmpeg
    return {"ffmpeg": find_ffmpeg() or ""}


def process(src: str, *, shield: bool = False, tools: dict[str, str] | None = None) -> dict[str, Any]:
    """Medya dosyasından tüm metadata/parmak izlerini temizler; shield=True ile mikro Content-ID kalkanı uygular."""
    p = Path(src)
    if not p.is_file():
        return {"ok": False, "error": "Dosya bulunamadı"}
    ext = p.suffix.lower()
    tag = "ghost-shield" if shield else "ghost"
    out = converter.out_path(str(p), ext.lstrip("."), tag=tag)

    if ext in IMAGE_EXTS:
        from PIL import Image, ImageChops
        with Image.open(p) as im:
            clean = Image.new(im.mode if im.mode in ("RGB", "RGBA", "L") else "RGB", im.size)
            conv = im.convert(clean.mode)
            if shield and conv.width > 8 and conv.height > 8:
                # 1px kırpıp orijinal boyuta ölçekleyerek algılanmaz piksel matrisi değişimi
                cropped = conv.crop((1, 1, conv.width - 1, conv.height - 1))
                conv = cropped.resize(im.size, Image.Resampling.LANCZOS)
            clean.paste(conv)
            save_kw: dict[str, Any] = {}
            if ext in (".jpg", ".jpeg"):
                clean = clean.convert("RGB")
                save_kw = {"quality": 95, "optimize": True}
            elif ext == ".webp":
                save_kw = {"quality": 95}
            clean.save(out, **save_kw)
        return {"ok": True, "out": str(out), "shield": shield, "kind": "image"}

    t = _tools(tools)
    ffmpeg = t.get("ffmpeg") or ""
    if not ffmpeg:
        return {"ok": False, "error": "ffmpeg bulunamadı"}

    if ext in AUDIO_EXTS:
        if shield:
            af = "asetrate=44100*1.006,aresample=44100,atempo=0.994"
            acodec = converter.AUDIO_ARGS.get(ext.lstrip("."), ["-c:a", "aac", "-b:a", "256k"])
            cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(p),
                   "-map_metadata", "-1", "-fflags", "+bitexact", "-af", af, *acodec, str(out)]
        else:
            cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(p),
                   "-map_metadata", "-1", "-fflags", "+bitexact", "-c:a", "copy", str(out)]
    elif ext in VIDEO_EXTS:
        if shield:
            use_nvenc = converter.has_nvenc(ffmpeg)
            vcodec = (["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "19", "-b:v", "0"]
                      if use_nvenc else ["-c:v", "libx264", "-preset", "medium", "-crf", "19"])
            vf = "scale=iw:ih:flags=lanczos,eq=brightness=0.005:contrast=1.01"
            af = "asetrate=44100*1.006,aresample=44100,atempo=0.994"
            cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(p),
                   "-map_metadata", "-1", "-fflags", "+bitexact",
                   "-vf", vf, *vcodec, "-pix_fmt", "yuv420p",
                   "-af", af, "-c:a", "aac", "-b:a", "192k", str(out)]
        else:
            cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(p),
                   "-map_metadata", "-1", "-fflags", "+bitexact", "-c", "copy", str(out)]
    else:
        return {"ok": False, "error": f"Desteklenmeyen uzantı: {ext}"}

    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=600, creationflags=NO_WINDOW)
    if r.returncode != 0:
        out.unlink(missing_ok=True)
        return {"ok": False, "error": (r.stderr or f"ffmpeg rc={r.returncode}")[:200]}
    return {"ok": True, "out": str(out), "shield": shield, "kind": "video" if ext in VIDEO_EXTS else "audio"}
