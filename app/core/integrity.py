"""Dosya butunlugu (v1.29): inen dosya gercekten saglam mi?

- Boyut: sunucunun bildirdigi boyuttan kucukse -> bozuk (yarim).
- Arsiv: 7-Zip 't' (yoksa zip icin zipfile.testzip). Sifreli arsiv parolasiz test edilemez -> 'bilinmiyor' (bozuk SAYILMAZ).
- Video/ses: ffprobe (sure + akis; MP4'te moov yoksa burada yakalanir) + bas ve SON 8 sn'yi gercekten coz
  (yarim inen dosyada son kisim bozuk olur). Tam cozum yapilmaz: 2 GB dosyada da birkac saniye surer.
- Resim: Pillow verify.
Sonuc: {"state": "ok"|"bad"|"unknown"|"skip", "kind", "detail"}.
"""
from __future__ import annotations

import json
import os
import subprocess
import zipfile
from typing import Any

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
VIDEO = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".ts", ".flv", ".wmv", ".mpg", ".mpeg"}
AUDIO = {".mp3", ".m4a", ".flac", ".wav", ".ogg", ".opus", ".aac", ".wma"}
ARCH = {".zip", ".7z", ".rar", ".tar", ".gz", ".tgz", ".xz", ".001"}
IMAGE = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
# Yalniz kesin bozukluk isaretleri (aramada sik gorulen zararsiz 'error while decoding'/'non-existing PPS' sayilmaz)
_BAD_HINTS = ("invalid data found", "moov atom not found", "truncat", "partial file", "header damaged",
              "could not find codec parameters", "end of file")


def _run(cmd: list[str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout, creationflags=NO_WINDOW)


def check_media(path: str, ffmpeg: str) -> dict[str, Any]:
    probe = os.path.join(os.path.dirname(ffmpeg), "ffprobe" + (".exe" if ffmpeg.lower().endswith(".exe") else ""))
    if not os.path.isfile(probe):
        import shutil
        probe = shutil.which("ffprobe") or ""
    dur = 0.0
    if probe:
        r = _run([probe, "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", path], 60)
        try:
            info = json.loads(r.stdout or "{}")
        except ValueError:
            info = {}
        streams = [s.get("codec_type") for s in info.get("streams", [])]
        if r.returncode != 0 or not streams:
            return {"state": "bad", "detail": (r.stderr or "akis yok").strip()[:160]}
        try:
            dur = float(info.get("format", {}).get("duration") or 0)
        except ValueError:
            dur = 0.0
    errs = []
    spots = [0.0] + ([max(0.0, dur - 8)] if dur > 20 else [])
    for ss in spots:
        r = _run([ffmpeg, "-v", "error", "-ss", f"{ss:.2f}", "-i", path, "-t", "8", "-map", "0:v:0?", "-map", "0:a:0?",
                  "-f", "null", "-"], 120)
        low = (r.stderr or "").lower()
        if r.returncode != 0 or any(h in low for h in _BAD_HINTS):
            last = (r.stderr or "").strip().splitlines()[-1][:120] if (r.stderr or "").strip() else "cozulemedi"
            errs.append(f"{'son' if ss else 'bas'}: {last}")
    if errs:
        return {"state": "bad", "detail": " | ".join(errs)}
    return {"state": "ok", "detail": f"{dur:.0f} sn" if dur else ""}


def check_archive(path: str, sevenzip: str) -> dict[str, Any]:
    if sevenzip:
        r = _run([sevenzip, "t", "-p", "-bso0", "-bsp0", path], 3600)   # bos parola: sifreliyse 'Wrong password'
        out = ((r.stdout or "") + (r.stderr or "")).lower()
        if r.returncode == 0:
            return {"state": "ok", "detail": "7-Zip test"}
        if "wrong password" in out or "encrypted" in out or "can not open encrypted" in out:
            return {"state": "unknown", "detail": "sifreli"}
        if "is not archive" in out or "unexpected end" in out or "data error" in out or "crc failed" in out or "headers error" in out:
            return {"state": "bad", "detail": out.strip().splitlines()[-1][:160] if out.strip() else "7-Zip hata"}
        return {"state": "bad" if r.returncode == 2 else "unknown", "detail": f"7-Zip kod {r.returncode}"}
    if path.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(path) as z:
                bad = z.testzip()
            return {"state": "bad", "detail": f"CRC: {bad}"} if bad else {"state": "ok", "detail": "zip test"}
        except RuntimeError:
            return {"state": "unknown", "detail": "sifreli"}
        except (zipfile.BadZipFile, OSError, EOFError) as exc:
            return {"state": "bad", "detail": str(exc)[:160]}
    return {"state": "skip", "detail": "7-Zip yok"}


def check_image(path: str) -> dict[str, Any]:
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:   # verify sonrasi yeniden ac: gercek cozum (kesik JPEG burada patlar)
            im.load()
        return {"state": "ok", "detail": ""}
    except ImportError:
        return {"state": "skip", "detail": ""}
    except Exception as exc:
        return {"state": "bad", "detail": str(exc)[:160]}


def check(path: str, expected_size: int = 0, *, ffmpeg: str = "", sevenzip: str = "") -> dict[str, Any]:
    if not path or not os.path.isfile(path):
        return {"state": "skip", "kind": "", "detail": "dosya yok"}
    ext = os.path.splitext(path)[1].lower()
    size = os.path.getsize(path)
    if expected_size and size < expected_size:
        return {"state": "bad", "kind": "size", "detail": f"{size} / {expected_size} bayt"}
    if size == 0:
        return {"state": "bad", "kind": "size", "detail": "0 bayt"}
    if ext in VIDEO or ext in AUDIO:
        if not ffmpeg:
            return {"state": "skip", "kind": "media", "detail": "ffmpeg yok"}
        return {"kind": "media", **check_media(path, ffmpeg)}
    if ext in ARCH:
        return {"kind": "archive", **check_archive(path, sevenzip)}
    if ext in IMAGE:
        return {"kind": "image", **check_image(path)}
    return {"state": "skip", "kind": "", "detail": ""}
