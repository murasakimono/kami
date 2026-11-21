"""FlashVSR (difuzyon video super-resolution) — Faz 3 "Yeniden uret" motoru.

Neden ayri ortam: torch+CUDA ~4 GB. Arayuz surecine yuklenmez (aitools deseniyle ayni):
%LOCALAPPDATA%\\Kami\\media-env\\flashvsr altinda kendi venv'i + kaynak kodu + model agirliklari durur.
Coker de Kami ayakta kalir.

Neden difuzyon: Real-ESRGAN "bozulmayi temizleyip keskinlestirir" (kaynak goruntuye sadik).
FlashVSR kareyi yeniden URETIR; daha cok detay hayal eder ama yuz/yazi degisebilir.
Bu yuzden ayri, "riskli" etiketli bir preset.

Kaynak: https://github.com/lihaoyun6/FlashVSR_plus (Apache-2.0 turevi; LICENSE repoda)
"""
from __future__ import annotations

import io
import logging
import os
import re
import shutil
import subprocess
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Callable

import requests

from app import paths

log = logging.getLogger(__name__)

REPO_ZIP = "https://github.com/lihaoyun6/FlashVSR_plus/archive/refs/heads/main.zip"
TORCH_INDEX = "https://download.pytorch.org/whl/cu128"

ROOT = paths.MEDIA_ENV / "flashvsr"          # venv + src + models
SRC = ROOT / "src"                            # run.py, models/
PY = ROOT / "Scripts" / "python.exe"
NO_WINDOW = 0x08000000

# torch/torchvision cu128 indeksinden, geri kalan PyPI'dan kurulur (ayri adim: CPU tekerlegi ezmesin)
TORCH_PKGS = ["torch", "torchvision"]
PKGS = ["gradio", "numpy", "einops", "safetensors", "tqdm", "pillow", "imageio",
        "imageio-ffmpeg", "ffmpeg-python", "huggingface_hub", "hf-xet",
        "triton-windows", "sageattention"]

SIZE_GB = 7.5   # torch cu128 ~2.9 GB + diger ~0.6 GB + model agirliklari ~3 GB

LAST_ERROR: dict[str, str] = {}


# ------------------------------------------------------------------ durum

def _uv() -> str | None:
    """uv ikilisi: once paketle gelen bin/uv.exe, sonra PATH."""
    local = paths.BIN_DIR / "uv.exe"
    return str(local) if local.is_file() else shutil.which("uv")


def installed() -> bool:
    """venv + kaynak kodu yerinde mi (agirliklar ilk calistirmada iner)."""
    return PY.is_file() and (SRC / "run.py").is_file()


def weights_ready() -> bool:
    """Model agirliklari indirilmis mi (ilk calistirmada ~3 GB iner)."""
    d = SRC / "models" / "FlashVSR"
    return d.is_dir() and (d / "diffusion_pytorch_model_streaming_dmd.safetensors").is_file()


def status() -> dict[str, Any]:
    return {"installed": installed(), "weights": weights_ready(), "size_gb": SIZE_GB,
            "root": str(ROOT), "error": LAST_ERROR.get("flashvsr", "")}


# ------------------------------------------------------------------ kurulum

def _log(name: str, line: str) -> None:
    try:
        p = paths.DATA_DIR / "models" / name / "install.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _run(cmd: list[str], on_line: Callable[[str], None], cwd: Path | None = None) -> int:
    """Alt sureci calistirir, her satiri iletir (kurulum ilerlemesi)."""
    log.info("flashvsr kurulum adimi: %s", " ".join(cmd[:3]))
    proc = subprocess.Popen(cmd, cwd=str(cwd) if cwd else None, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, creationflags=NO_WINDOW, text=True,
                            encoding="utf-8", errors="replace")
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            _log("flashvsr", line)
            on_line(line[-160:])
    return proc.wait()


def install(on_line: Callable[[str], None] = lambda s: None) -> bool:
    """Uzun surer (~7 GB). Cagiran arka planda calistirir."""
    LAST_ERROR.pop("flashvsr", None)
    try:
        return _install(on_line)
    except Exception as exc:   # noqa: BLE001
        log.exception("FlashVSR kurulumu istisna")
        LAST_ERROR["flashvsr"] = f"{type(exc).__name__}: {exc}"[:300]
        return False


def _install(on_line: Callable[[str], None]) -> bool:
    uv = _uv()
    if not uv:
        LAST_ERROR["flashvsr"] = "uv.exe bulunamadi (bin klasoru veya PATH)"
        return False
    ROOT.mkdir(parents=True, exist_ok=True)

    # 1) venv
    if not PY.is_file():
        on_line("Python ortami olusturuluyor...")
        if _run([uv, "venv", "--python", "3.12", "--seed", str(ROOT)], on_line) != 0 or not PY.is_file():
            LAST_ERROR["flashvsr"] = "Python ortami olusturulamadi"
            return False

    # 2) kaynak kodu (git gerekmez: zip)
    if not (SRC / "run.py").is_file():
        on_line("Kaynak kodu indiriliyor (~32 MB)...")
        r = requests.get(REPO_ZIP, timeout=180)
        r.raise_for_status()
        tmp = ROOT / "_src_tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            for m in z.namelist():   # zip-slip korumasi
                if m.startswith("/") or ".." in Path(m).parts:
                    raise RuntimeError("guvensiz zip")
            z.extractall(tmp)
        inner = next(p for p in tmp.iterdir() if p.is_dir())
        shutil.rmtree(SRC, ignore_errors=True)
        shutil.move(str(inner), str(SRC))
        shutil.rmtree(tmp, ignore_errors=True)
        on_line("Kaynak kodu hazir")
    if not (SRC / "run.py").is_file():
        LAST_ERROR["flashvsr"] = "run.py bulunamadi"
        return False

    # 3) torch (CUDA 12.8) — ayri adim, cunku ana indeks PyPI torch'u CPU tekerlegi
    on_line("PyTorch CUDA kuruluyor (~3 GB)...")
    if _run([uv, "pip", "install", "--python", str(PY), "--index-url", TORCH_INDEX, *TORCH_PKGS], on_line) != 0:
        LAST_ERROR["flashvsr"] = "torch kurulumu basarisiz"
        return False

    # 4) geri kalan paketler + sageattention (FlashVSR wan_video_dit onu import ediyor)
    on_line("Bagimliliklar kuruluyor...")
    if _run([uv, "pip", "install", "--python", str(PY), *PKGS], on_line) != 0:
        LAST_ERROR["flashvsr"] = "bagimlilik kurulumu basarisiz"
        return False

    # 5) saglik kontrolu: torch CUDA goruyor mu + run.py argumanlari okunuyor mu
    on_line("Kontrol ediliyor...")
    check = [str(PY), "-c", "import torch,sys;sys.exit(0 if torch.cuda.is_available() else 3)"]
    if _run(check, on_line) != 0:
        LAST_ERROR["flashvsr"] = "torch CUDA goremiyor (surucu/uyumsuzluk)"
        return False
    on_line("Kuruldu: FlashVSR hazir (ilk calistirmada ~3 GB model iner)")
    return True


# ------------------------------------------------------------------ calistirma

def vram_flags(scale: int = 4, mode: str = "tiny", tile: int = 256,
               tiled_dit: bool = False, unload_dit: bool = False) -> list[str]:
    """6 GB VRAM icin OLCULMUS calisan bayraklar.

    Olcum (RTX 4050 Laptop 6 GB, 2026-11-21): `-m tiny --tiled-vae` ile 30 kare uretildi.
    `-m tiny-long --tiled-dit` denemesinde tile videolari yazilmadi ve stitch asamasinda
    FileNotFoundError verdi (upstream bug). Bu yuzden tiled-dit VARSAYILAN KAPALI;
    yalniz cok buyuk girdide opt-in.
    """
    sc = 4 if int(scale) >= 4 else 2
    m = mode if mode in ("tiny", "tiny-long", "full") else "tiny"
    f = ["-s", str(sc), "-m", m, "--tiled-vae", "--color-fix", "-t", "bf16", "-a", "sage"]
    if tiled_dit:
        f += ["--tiled-dit", "--tile-size", str(max(128, min(512, int(tile)))), "--overlap", "24"]
    if unload_dit:
        f.append("--unload-dit")
    return f


def build_args(path: str, opts: dict[str, Any], out_dir: str) -> list[str]:
    """run.py icin tam komut satiri (saf fonksiyon: test edilebilir)."""
    flags = vram_flags(int(opts.get("scale") or 4),
                       str(opts.get("mode") or "tiny"),
                       int(opts.get("tile") or 256),
                       bool(opts.get("tiled_dit")),
                       bool(opts.get("unload_dit")))
    return [str(PY), "run.py", "-i", str(path), *flags, str(out_dir)]


def run_video(job: dict, ffmpeg: str, path: str, opts: dict[str, Any], out_dir: Path,
              dst: Path) -> Path:
    """FlashVSR'i alt surecte calistirir; ciktiyi dst'ye tasir.

    job: {"cancel": Event, "p": float, "line": str}  (video_enhance sozlesmesi)
    """
    if not installed():
        raise RuntimeError("FlashVSR kurulu degil")
    work = out_dir / f"_fvsr_{int(time.time() * 1000)}"
    work.mkdir(parents=True, exist_ok=True)
    args = build_args(str(path), opts, str(work))
    env = dict(os.environ)
    env["PATH"] = str(Path(ffmpeg).parent) + os.pathsep + env.get("PATH", "")   # ffmpeg-python bulsun
    env["PYTHONUNBUFFERED"] = "1"
    # Turkce Windows'ta stdout cp1254 olur ve FlashVSR'in Unicode banner'i coker (UnicodeEncodeError).
    # pythonw altinda konsol hic yok; her durumda UTF-8 sabitle.
    env["PYTHONIOENCODING"] = "utf-8"
    # Triton JIT onbellegi varsayilan olarak %USERPROFILE%\.triton; kendi klasorumuzde tutalim
    # (ev dizini salt-okunur/kilitliyse kurulum calissin, kullanici evi de kirlenmesin)
    triton_dir = ROOT / "triton"
    triton_dir.mkdir(parents=True, exist_ok=True)
    env["TRITON_CACHE_DIR"] = str(triton_dir)
    # Alt surecin gecici klasoru de Kami'nin altinda olsun (sistem temp'i kilitliyse calissin,
    # uzun videoda C: temp sismesin)
    tmp_dir = ROOT / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    for k in ("TMP", "TEMP", "TMPDIR"):
        env[k] = str(tmp_dir)
    job["line"] = "FlashVSR başlıyor (ilk çalıştırmada ~3 GB model iner)"
    proc = subprocess.Popen(args, cwd=str(SRC), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            creationflags=NO_WINDOW, env=env, text=True, encoding="utf-8", errors="replace")
    tail: list[str] = []
    assert proc.stdout is not None
    for raw in proc.stdout:
        if job["cancel"].is_set():
            proc.kill()
            proc.wait(timeout=15)
            raise _Cancelled()
        line = raw.strip()
        if not line:
            continue
        tail.append(line)
        if len(tail) > 40:
            tail.pop(0)
        m = re.search(r"(\d{1,3})%", line)
        if m:
            job["p"] = round(min(0.97, int(m.group(1)) / 100.0), 4)
        if "download" in line.lower() or "safetensors" in line.lower():
            job["line"] = "Model indiriliyor… " + line[-60:]
        elif "%" not in line:
            job["line"] = line[-90:]
    rc = proc.wait()
    if job["cancel"].is_set():
        raise _Cancelled()
    if rc != 0:
        raise RuntimeError("FlashVSR hatasi: " + (" | ".join(tail[-3:]) or str(rc)))

    made = sorted((p for p in work.rglob("*.mp4")), key=lambda p: p.stat().st_size, reverse=True)
    if not made:
        raise RuntimeError("FlashVSR cikti uretmedi")
    job["line"] = "Dosya hazırlanıyor"
    dst.parent.mkdir(parents=True, exist_ok=True)
    # hizli baslangic icin remux (yeniden kodlama yok)
    r = subprocess.run([ffmpeg, "-hide_banner", "-nostdin", "-y", "-i", str(made[0]),
                        "-c", "copy", "-movflags", "+faststart", str(dst)],
                       capture_output=True, timeout=3600, creationflags=NO_WINDOW)
    if r.returncode != 0 or not dst.is_file():
        shutil.copy2(made[0], dst)
    shutil.rmtree(work, ignore_errors=True)
    return dst


class _Cancelled(Exception):
    """Kullanici iptal etti."""
