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


def inspect_metadata(src: str) -> dict[str, Any]:
    """Dosyadaki gizlilik acisindan hassas metadata alanlarini (GPS, cihaz, tarih) listeler."""
    p = Path(src)
    if not p.is_file():
        return {"ok": False, "error": "Dosya bulunamadı"}
    ext = p.suffix.lower()
    fields: dict[str, str] = {}
    has_gps = False
    if ext in IMAGE_EXTS:
        try:
            from PIL import Image, ExifTags
            with Image.open(p) as im:
                ex = im.getexif()
                for tag_id, val in (ex or {}).items():
                    name = ExifTags.TAGS.get(tag_id, str(tag_id))
                    if name == "GPSInfo" or "gps" in str(name).lower():
                        has_gps = True
                        fields["GPS"] = "Konum koordinatı mevcut!"
                    elif name in ("Make", "Model", "DateTimeOriginal", "DateTime", "Software", "Artist"):
                        fields[str(name)] = str(val)[:80]
                if hasattr(ex, "get_ifd"):
                    try:
                        if ex.get_ifd(0x8825):
                            has_gps = True
                            fields["GPS"] = "Konum koordinatı mevcut!"
                    except Exception:
                        pass
        except Exception:
            pass
    elif ext in AUDIO_EXTS or ext in VIDEO_EXTS:
        ff = _tools().get("ffmpeg") or ""
        if ff:
            probe = str(Path(ff).with_name("ffprobe" + Path(ff).suffix))
            try:
                import json as _json
                r = subprocess.run([probe, "-v", "quiet", "-print_format", "json", "-show_format", str(p)],
                                   capture_output=True, text=True, timeout=15, creationflags=NO_WINDOW)
                tags = ((_json.loads(r.stdout or "{}").get("format") or {}).get("tags")) or {}
                for k, v in tags.items():
                    if "location" in k.lower() or "gps" in k.lower():
                        has_gps = True
                    fields[str(k)] = str(v)[:80]
            except Exception:
                pass
    return {"ok": True, "has_gps": has_gps, "fields": fields, "count": len(fields)}


def process(src: str, *, shield: bool = False, tools: dict[str, str] | None = None, ctx: Any = None) -> dict[str, Any]:
    """Medya dosyasından tüm metadata/parmak izlerini temizler; shield=True ile mikro Content-ID kalkanı uygular."""
    p = Path(src)
    if not p.is_file():
        return {"ok": False, "error": "Dosya bulunamadı"}
    ext = p.suffix.lower()
    tag = "ghost-shield" if shield else "ghost"
    out = converter.out_path(str(p), ext.lstrip("."), tag=tag)

    if ext in IMAGE_EXTS:
        from PIL import Image, ImageOps
        with Image.open(p) as im:
            icc = im.info.get("icc_profile")
            im = ImageOps.exif_transpose(im)
            clean = Image.new(im.mode if im.mode in ("RGB", "RGBA", "L") else "RGB", im.size)
            conv = im.convert(clean.mode)
            if shield and conv.width > 8 and conv.height > 8:
                # 1px kırpıp orijinal boyuta ölçekleyerek algılanmaz piksel matrisi değişimi
                cropped = conv.crop((1, 1, conv.width - 1, conv.height - 1))
                conv = cropped.resize(im.size, Image.Resampling.LANCZOS)
            clean.paste(conv)
            save_kw: dict[str, Any] = {}
            if icc:
                save_kw["icc_profile"] = icc
            if ext in (".jpg", ".jpeg"):
                clean = clean.convert("RGB")
                save_kw.update({"quality": 95, "optimize": True})
            elif ext == ".webp":
                save_kw["quality"] = 95
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
                   "-map", "0:a", "-map_metadata", "-1", "-fflags", "+bitexact", "-c:a", "copy", str(out)]
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
                   "-map", "0", "-map_metadata", "-1", "-fflags", "+bitexact", "-c", "copy", str(out)]
    else:
        return {"ok": False, "error": f"Desteklenmeyen uzantı: {ext}"}

    if ctx:
        r = ctx.run_proc(cmd, timeout=600)
    else:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=600, creationflags=NO_WINDOW)
    if r.returncode != 0:
        out.unlink(missing_ok=True)
        return {"ok": False, "error": (r.stderr or f"ffmpeg rc={r.returncode}")[:200]}
    return {"ok": True, "out": str(out), "shield": shield, "kind": "video" if ext in VIDEO_EXTS else "audio"}


def process_folder(folder: str, *, shield: bool = False, tools: dict[str, str] | None = None, ctx: Any = None) -> dict[str, Any]:
    d = Path(folder)
    if not d.is_dir():
        return {"ok": False, "error": "Klasör bulunamadı"}
    exts = IMAGE_EXTS | AUDIO_EXTS | VIDEO_EXTS
    files = [f for f in sorted(d.iterdir()) if f.is_file() and f.suffix.lower() in exts and "-ghost" not in f.stem]
    if not files:
        return {"ok": False, "error": "Klasörde temizlenecek medya bulunamadı"}
    done, errs = [], []
    for i, f in enumerate(files):
        if ctx and ctx.cancelled.is_set():
            break
        if ctx:
            ctx.set(int(100 * i / len(files)), f"Temizleniyor: {f.name}")
        res = process(str(f), shield=shield, tools=tools, ctx=ctx)
        if res.get("ok"):
            done.append(res["out"])
        else:
            errs.append(f"{f.name}: {res.get('error')}")
    return {"ok": len(done) > 0, "count": len(done), "files": done, "errors": errs}
