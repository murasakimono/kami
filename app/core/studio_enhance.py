"""Kami Studio: yapay zeka ile netlestirme (Real-ESRGAN) ve akici agir cekim / kare cogaltma (RIFE).

Ikisi de ncnn-vulkan ikilisi: Python ortami gerekmez, NVIDIA/AMD/Intel ekran kartinda calisir,
ilk kullanimda GitHub surumunden indirilir (~45 MB + ~60 MB). Kare kare: ffmpeg cikarir -> arac -> ffmpeg birlestirir.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import zipfile
from pathlib import Path
from typing import Callable

from app.paths import MEDIA_ENV

NO_WINDOW = 0x08000000 if hasattr(subprocess, "STARTUPINFO") else 0
ROOT = MEDIA_ENV / "ncnn"

TOOLS: dict[str, dict[str, str]] = {
    "esrgan": {"url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip",
               "exe": "realesrgan-ncnn-vulkan.exe"},
    "rife": {"url": "https://github.com/nihui/rife-ncnn-vulkan/releases/download/20221029/rife-ncnn-vulkan-20221029-windows.zip",
             "exe": "rife-ncnn-vulkan.exe"},
}


def exe(tool: str) -> Path | None:
    d = ROOT / tool
    if not d.is_dir():
        return None
    hit = next(d.rglob(TOOLS[tool]["exe"]), None)
    return hit if hit and hit.is_file() else None


def installed(tool: str) -> bool:
    return exe(tool) is not None


def install(tool: str, progress: Callable[[str], None] = lambda s: None) -> bool:
    import requests
    info = TOOLS[tool]
    d = ROOT / tool
    d.mkdir(parents=True, exist_ok=True)
    z = d / "dl.zip"
    with requests.get(info["url"], stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length") or 0)
        got = 0
        with open(z, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
                got += len(chunk)
                if total:
                    progress(f"İndiriliyor %{got * 100 // total}")
    progress("Açılıyor")
    with zipfile.ZipFile(z) as zf:
        for m in zf.namelist():   # zip-slip korumasi
            if m.startswith("/") or ".." in Path(m).parts:
                raise RuntimeError("guvensiz zip")
        zf.extractall(d)
    z.unlink(missing_ok=True)
    return installed(tool)


def probe_fps(ffmpeg: str, path: str) -> float:
    r = subprocess.run([ffmpeg, "-hide_banner", "-i", path], capture_output=True, timeout=60, creationflags=NO_WINDOW)
    m = re.search(r"([\d.]+) fps", r.stderr.decode("utf-8", "replace"))
    return float(m.group(1)) if m else 30.0


def _count(d: Path) -> int:
    try:
        return sum(1 for _ in os.scandir(d))
    except OSError:
        return 0


def _watch(proc: subprocess.Popen, out_dir: Path, expect: int, job: dict, p0: float, p1: float) -> int:
    while proc.poll() is None:
        if job["cancel"].wait(0.7):
            proc.kill()
            return -9
        if expect:
            job["p"] = p0 + (p1 - p0) * min(1.0, _count(out_dir) / expect)
    return proc.returncode


def esrgan_args(exe_path: str, src: Path, dst: Path, model: str, scale: int) -> list[str]:
    return [exe_path, "-i", str(src), "-o", str(dst), "-n", model, "-s", str(scale), "-f", "png"]


def rife_args(exe_path: str, src: Path, dst: Path, frames: int, model: str = "rife-v4.6") -> list[str]:
    return [exe_path, "-i", str(src), "-o", str(dst), "-m", model, "-n", str(frames), "-f", "%08d.png"]


def run(job: dict, ffmpeg: str, kind: str, path: str, start: float, dur: float, opts: dict, out_dir: Path) -> None:
    """kind: upscale (opts.model anime|photo, opts.scale 2|4) | interp (opts.factor 2|4, opts.mode slow|smooth)."""
    import tempfile
    work = Path(tempfile.mkdtemp(prefix="kstudio_ncnn_"))
    try:
        tool = "esrgan" if kind == "upscale" else "rife"
        ex = exe(tool)
        if not ex:
            raise RuntimeError("arac kurulu degil")
        fin, fout = work / "in", work / "out"
        fin.mkdir()
        fout.mkdir()
        fps = probe_fps(ffmpeg, path)
        job["line"] = "Kareler çıkarılıyor"
        vf = []
        if kind == "upscale":   # 4K'yi asmasin: kaynak buyukse once kucult
            sc = 4 if int(opts.get("scale", 2)) == 4 else 2
            vf.append(f"scale='min(iw,{3840 // sc})':-2")
        cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", path,
               *(["-vf", ",".join(vf)] if vf else []), "-fps_mode", "passthrough", str(fin / "%08d.png")]
        subprocess.run(cmd, capture_output=True, timeout=3600, creationflags=NO_WINDOW, check=True)
        n_in = _count(fin)
        if not n_in:
            raise RuntimeError("kare cikmadi")
        job["p"] = 0.1
        if kind == "upscale":
            model = "realesrgan-x4plus" if opts.get("model") == "photo" else "realesr-animevideov3"
            scale = 4 if model == "realesrgan-x4plus" else int(sc)
            args, expect, out_fps = esrgan_args(str(ex), fin, fout, model, scale), n_in, fps
            job["line"] = f"Netleştiriliyor ({n_in} kare)"
        else:
            factor = 4 if int(opts.get("factor", 2)) >= 4 else 2
            expect = n_in * factor
            args = rife_args(str(ex), fin, fout, expect)
            out_fps = fps if opts.get("mode", "slow") == "slow" else fps * factor
            job["line"] = f"Ara kareler üretiliyor ({expect} kare)"
        proc = subprocess.Popen(args, cwd=str(ex.parent), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=NO_WINDOW)
        err: list[bytes] = []
        threading.Thread(target=lambda: err.append(proc.stderr.read() if proc.stderr else b""), daemon=True).start()
        rc = _watch(proc, fout, expect, job, 0.1, 0.9)
        if rc == -9:
            job.update(state="cancelled")
            return
        if rc != 0 or not _count(fout):
            raise RuntimeError("arac hatasi: " + (b"".join(err).decode("utf-8", "replace")[-240:] or str(rc)))
        job["line"] = "Video birleştiriliyor"
        stem = re.sub(r"[^\w\-]+", "_", Path(path).stem)[:40]
        tag = "net" if kind == "upscale" else ("agir" if opts.get("mode", "slow") == "slow" else "akici")
        out_dir.mkdir(parents=True, exist_ok=True)
        dst = out_dir / f"{stem}_{tag}_{int(start * 1000)}.mp4"
        keep_audio = not (kind == "interp" and opts.get("mode", "slow") == "slow")
        enc = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-framerate", f"{out_fps:.4f}", "-i", str(fout / "%08d.png")]
        if keep_audio:
            enc += ["-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", path, "-map", "0:v", "-map", "1:a?", "-c:a", "aac", "-b:a", "256k", "-shortest"]
        enc += ["-c:v", "libx264", "-crf", "15", "-preset", "medium", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dst)]
        r = subprocess.run(enc, capture_output=True, timeout=7200, creationflags=NO_WINDOW)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.decode("utf-8", "replace")[-240:])
        job.update(state="done", p=1.0, result={"path": str(dst), "fps": out_fps, "frames": _count(fout)})
    except Exception as exc:
        job.update(state="error", error=str(exc)[:300])
    finally:
        shutil.rmtree(work, ignore_errors=True)
