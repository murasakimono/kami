"""Faz 11.4 — Cift Medya Temizligi (dHash), Akilli Sikistirma (AV1/HEVC + VMAF) & Bit-Rot Saglik Tarayicisi.

TMDB / MusicBrainz / smart_series_folders mevcut modullerde oldugu icin dokunulmaz.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".avi"}
AUDIO_EXTS = {".mp3", ".flac", ".wav", ".m4a", ".ogg", ".opus"}


def _ffmpeg() -> str:
    try:
        from app.engines.ytdlp_engine import find_ffmpeg
        return find_ffmpeg() or ""
    except Exception:
        import shutil
        return shutil.which("ffmpeg") or ""


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            buf = fh.read(chunk_size)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def image_dhash(path: str | Path) -> int | None:
    """9x8 gri tonlamali difference-hash (64-bit) hesaplar."""
    try:
        from PIL import Image
        with Image.open(path) as img:
            gray = img.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
            px = list(gray.get_flattened_data() if hasattr(gray, "get_flattened_data") else gray.getdata())
        bits = 0
        for row in range(8):
            base = row * 9
            for col in range(8):
                bits = (bits << 1) | (1 if px[base + col] > px[base + col + 1] else 0)
        return bits
    except Exception:
        return None


def hamming_distance(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def _video_frame_hashes(path: str | Path, ffmpeg: str) -> list[int]:
    if not ffmpeg:
        return []
    hashes: list[int] = []
    with tempfile.TemporaryDirectory(prefix="kami_dhash_") as tmp:
        for idx, sec in enumerate((2, 10, 25)):
            out = Path(tmp) / f"f{idx}.png"
            subprocess.run(
                [ffmpeg, "-y", "-ss", str(sec), "-i", str(path), "-frames:v", "1", "-q:v", "2", str(out)],
                capture_output=True, timeout=15, creationflags=NO_WINDOW,
            )
            if out.is_file():
                h = image_dhash(out)
                if h is not None:
                    hashes.append(h)
    return hashes


def find_duplicates(folder: str | Path, *, max_hamming: int = 6, include_video: bool = True) -> dict[str, Any]:
    """Klasordeki birebir (SHA-256) ve algisal (dHash) cift medya dosyalarini gruplar."""
    root = Path(folder)
    if not root.is_dir():
        return {"ok": False, "error": "Klasor bulunamadi", "groups": []}

    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in (IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS))
    by_sha: dict[str, list[Path]] = {}
    img_hashes: list[tuple[Path, int]] = []
    vid_hashes: list[tuple[Path, list[int]]] = []
    ff = _ffmpeg() if include_video else ""

    for p in files:
        digest = sha256_file(p)
        by_sha.setdefault(digest, []).append(p)
        ext = p.suffix.lower()
        if ext in IMAGE_EXTS:
            dh = image_dhash(p)
            if dh is not None:
                img_hashes.append((p, dh))
        elif include_video and ext in VIDEO_EXTS and ff:
            vh = _video_frame_hashes(p, ff)
            if vh:
                vid_hashes.append((p, vh))

    groups: list[dict[str, Any]] = []
    seen_paths: set[Path] = set()

    for digest, paths in by_sha.items():
        if len(paths) > 1:
            ordered = sorted(paths, key=lambda x: x.stat().st_size, reverse=True)
            seen_paths.update(ordered)
            groups.append({
                "kind": "exact_sha256",
                "keep": str(ordered[0]),
                "duplicates": [str(x) for x in ordered[1:]],
            })

    for i in range(len(img_hashes)):
        p1, h1 = img_hashes[i]
        if p1 in seen_paths:
            continue
        cluster = [p1]
        for j in range(i + 1, len(img_hashes)):
            p2, h2 = img_hashes[j]
            if p2 not in seen_paths and hamming_distance(h1, h2) <= max_hamming:
                cluster.append(p2)
        if len(cluster) > 1:
            ordered = sorted(cluster, key=lambda x: x.stat().st_size, reverse=True)
            seen_paths.update(ordered)
            groups.append({
                "kind": "perceptual_image",
                "keep": str(ordered[0]),
                "duplicates": [str(x) for x in ordered[1:]],
            })

    for i in range(len(vid_hashes)):
        p1, hs1 = vid_hashes[i]
        if p1 in seen_paths:
            continue
        cluster = [p1]
        for j in range(i + 1, len(vid_hashes)):
            p2, hs2 = vid_hashes[j]
            if p2 in seen_paths:
                pairs = min(len(hs1), len(hs2))
                if pairs and (sum(hamming_distance(hs1[k], hs2[k]) for k in range(pairs)) / pairs) <= max_hamming + 2:
                    cluster.append(p2)
        if len(cluster) > 1:
            ordered = sorted(cluster, key=lambda x: x.stat().st_size, reverse=True)
            seen_paths.update(ordered)
            groups.append({
                "kind": "perceptual_video",
                "keep": str(ordered[0]),
                "duplicates": [str(x) for x in ordered[1:]],
            })

    return {"ok": True, "scanned": len(files), "groups": groups}


def detect_encoder(ffmpeg: str = "") -> str:
    """Kullanilabilir en iyi donanim/yazilim video kodlayicisini secer."""
    ff = ffmpeg or _ffmpeg()
    if not ff:
        return ""
    try:
        r = subprocess.run([ff, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=10, creationflags=NO_WINDOW)
        out = r.stdout or ""
        for cand in ("av1_nvenc", "hevc_nvenc", "libx265", "libx264"):
            if cand in out:
                return cand
    except Exception:
        pass
    return "libx265"


def measure_vmaf(distorted: str | Path, reference: str | Path, ffmpeg: str = "") -> float | None:
    """libvmaf mevcutsa VMAF skorunu (0-100) olcer, yoksa None dondurur."""
    ff = ffmpeg or _ffmpeg()
    if not ff:
        return None
    try:
        flt = subprocess.run([ff, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=10, creationflags=NO_WINDOW)
        if "libvmaf" not in (flt.stdout or ""):
            return None
        r = subprocess.run(
            [ff, "-i", str(distorted), "-i", str(reference), "-lavfi", "libvmaf", "-f", "null", "-"],
            capture_output=True, text=True, timeout=300, creationflags=NO_WINDOW,
        )
        m = re.search(r"VMAF score:\s*([0-9]+(?:\.[0-9]+)?)", r.stderr or "")
        return float(m.group(1)) if m else None
    except Exception:
        return None


def smart_compress(
    src: str | Path,
    dst: str | Path = "",
    *,
    codec: str = "",
    min_vmaf: float = 95.0,
    cq: int = 24,
) -> dict[str, Any]:
    """AV1/HEVC ile akilli sikistirma + VMAF kalite dogrulamasi."""
    src_p = Path(src)
    if not src_p.is_file():
        return {"ok": False, "error": "Kaynak dosya bulunamadi"}
    ff = _ffmpeg()
    if not ff:
        return {"ok": False, "error": "FFmpeg bulunamadi"}

    enc = codec or detect_encoder(ff)
    out_p = Path(dst) if dst else src_p.with_name(f"{src_p.stem}_{enc}.mp4")
    q_flag = "-cq" if "nvenc" in enc else "-crf"
    cmd = [ff, "-y", "-i", str(src_p), "-c:v", enc, q_flag, str(cq), "-c:a", "aac", "-b:a", "192k", str(out_p)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, creationflags=NO_WINDOW)
    if r.returncode != 0 or not out_p.is_file():
        return {"ok": False, "codec": enc, "error": (r.stderr or "").splitlines()[-1:] or "Kodlama hatasi"}

    vmaf = measure_vmaf(out_p, src_p, ff)
    if vmaf is not None and vmaf < min_vmaf and cq > 16:
        # Kalite hedefin altindaysa daha yuksek kaliteyle bir kez yeniden dene
        better_cq = max(14, cq - 4)
        cmd_retry = [ff, "-y", "-i", str(src_p), "-c:v", enc, q_flag, str(better_cq), "-c:a", "aac", "-b:a", "192k", str(out_p)]
        r2 = subprocess.run(cmd_retry, capture_output=True, text=True, timeout=1800, creationflags=NO_WINDOW)
        if r2.returncode == 0 and out_p.is_file():
            vmaf = measure_vmaf(out_p, src_p, ff)

    orig_sz = src_p.stat().st_size
    new_sz = out_p.stat().st_size
    return {
        "ok": True,
        "path": str(out_p),
        "codec": enc,
        "vmaf": vmaf,
        "vmaf_passed": (vmaf is None) or (vmaf >= min_vmaf),
        "original_bytes": orig_sz,
        "compressed_bytes": new_sz,
        "saved_pct": round((1 - new_sz / orig_sz) * 100, 1) if orig_sz else 0.0,
    }


def scan_health(
    folder: str | Path,
    manifest_path: str | Path,
    *,
    deep_decode: bool = False,
) -> dict[str, Any]:
    """SHA-256 bit-rot taramasi ve istege bagli FFmpeg akis sagligi kontrolu."""
    root = Path(folder)
    if not root.is_dir():
        return {"ok": False, "error": "Klasor bulunamadi"}
    man_p = Path(manifest_path)
    prev: dict[str, dict[str, Any]] = {}
    if man_p.is_file():
        try:
            prev = json.loads(man_p.read_text(encoding="utf-8"))
        except Exception:
            prev = {}

    ff = _ffmpeg() if deep_decode else ""
    current: dict[str, dict[str, Any]] = {}
    corrupted: list[dict[str, str]] = []
    decode_errors: list[dict[str, str]] = []
    new_files: list[str] = []
    ok_count = 0

    for p in sorted(root.rglob("*")):
        if not p.is_file() or p == man_p:
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        st = p.stat()
        digest = sha256_file(p)
        current[rel] = {"sha256": digest, "size": st.st_size, "mtime_ns": st.st_mtime_ns}

        old = prev.get(rel)
        if old is None:
            new_files.append(rel)
        elif old.get("sha256") != digest and old.get("mtime_ns") == st.st_mtime_ns:
            corrupted.append({"file": rel, "expected": old["sha256"], "actual": digest})
        else:
            ok_count += 1

        if deep_decode and ff and p.suffix.lower() in (VIDEO_EXTS | AUDIO_EXTS):
            dr = subprocess.run(
                [ff, "-v", "error", "-i", str(p), "-f", "null", "-"],
                capture_output=True, text=True, timeout=120, creationflags=NO_WINDOW,
            )
            if dr.returncode != 0 or (dr.stderr or "").strip():
                decode_errors.append({"file": rel, "error": (dr.stderr or "decode error").strip()[:200]})

    missing = [k for k in prev if k not in current]
    man_p.parent.mkdir(parents=True, exist_ok=True)
    man_p.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "ok": len(corrupted) == 0 and len(decode_errors) == 0,
        "total": len(current),
        "ok_count": ok_count,
        "new_files": new_files,
        "missing": missing,
        "corrupted_bitrot": corrupted,
        "decode_errors": decode_errors,
    }
