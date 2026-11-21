"""Faz 2: VapourSynth + vs-mlrt TensorRT hizli buyutme yolu.

Amac KALITE DEGIL HIZ: ncnn yoluyla AYNI agirliklar (realesr-animevideov3 / RealESRGANv2)
TensorRT motoruna derlenip VapourSynth hattinda calistirilir. ncnn'de kare kare PNG yaz/oku
(~35 MB/kare disk trafigi) yerine boru hatti: vspipe -> ffmpeg stdin.

Mimari (aitools/flashvsr deseniyle ayni): her sey kendi ortaminda.
  %LOCALAPPDATA%\\Kami\\media-env\\trt        -> venv (Python 3.12)
  %LOCALAPPDATA%\\Kami\\media-env\\trt-models -> onnx + derlenmis .engine (venv'den AYRI: venv silinse de kalir)

Neden TensorRT 11'de ONNX dogrudan verilemiyor: vs-mlrt eklentisi artik yalniz hazir .engine kabul
ediyor; ONNX->engine donusumu TensorRT Python baglariyla (builder + onnx parser) yapilir.
"""
from __future__ import annotations

import io
import json
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

ROOT = paths.MEDIA_ENV / "trt"             # venv
MODELS = paths.MEDIA_ENV / "trt-models"   # onnx + engine (venv'den bagimsiz)
PY = ROOT / "Scripts" / "python.exe"
VSPIPE = ROOT / "Lib" / "site-packages" / "vapoursynth" / "vspipe.exe"
NO_WINDOW = 0x08000000

MODEL_PACK = "https://github.com/AmusementClub/vs-mlrt/releases/download/v16.4.test1/models.v16.4.test1.7z"
PKGS = ["vapoursynth", "vapoursynth-mlrt-trt", "tensorrt-cu13-bindings", "py7zr",
        "vapoursynth-lsmas", "vapoursynth-ffms2", "vapoursynth-bestsource"]

# vs-mlrt resmi model paketi icindeki yollar -> bizim engine adimiz
ONNX_WANT = {
    "x2": "models/RealESRGANv2/RealESRGANv2-animevideo-xsx2.onnx",
    "x4": "models/RealESRGANv2/RealESRGANv2-animevideo-xsx4.onnx",
}
SIZE_GB = 2.9    # venv ~1 GB + model paketi 0.85 GB + engine ~0.2 GB

LAST_ERROR: dict[str, str] = {}


# ------------------------------------------------------------------ durum

def _uv() -> str | None:
    local = paths.BIN_DIR / "uv.exe"
    return str(local) if local.is_file() else shutil.which("uv")


def engine(scale: int) -> Path:
    return MODELS / f"esrgan_x{4 if int(scale) >= 4 else 2}_fp16.engine"


def installed() -> bool:
    return PY.is_file() and VSPIPE.is_file() and engine(2).is_file()


def status() -> dict[str, Any]:
    return {"installed": installed(), "size_gb": SIZE_GB, "root": str(ROOT),
            "models": str(MODELS), "engines": [p.name for p in MODELS.glob("*.engine")],
            "error": LAST_ERROR.get("trt", "")}


# ------------------------------------------------------------------ kurulum

def _log(name: str, line: str) -> None:
    try:
        p = paths.DATA_DIR / "models" / name / "install.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _run(cmd: list[str], on_line: Callable[[str], None], cwd: Path | None = None,
         env: dict[str, str] | None = None) -> int:
    proc = subprocess.Popen(cmd, cwd=str(cwd) if cwd else None, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, creationflags=NO_WINDOW, text=True,
                            encoding="utf-8", errors="replace", env=env)
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            _log("trt", line)
            on_line(line[-160:])
    return proc.wait()


def _build_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    tmp = ROOT / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    for k in ("TMP", "TEMP", "TMPDIR"):
        env[k] = str(tmp)
    return env


def install(on_line: Callable[[str], None] = lambda s: None) -> bool:
    LAST_ERROR.pop("trt", None)
    try:
        return _install(on_line)
    except Exception as exc:   # noqa: BLE001
        log.exception("TensorRT yolu kurulumu istisna")
        LAST_ERROR["trt"] = f"{type(exc).__name__}: {exc}"[:300]
        return False


def _install(on_line: Callable[[str], None]) -> bool:
    uv = _uv()
    if not uv:
        LAST_ERROR["trt"] = "uv.exe bulunamadi"
        return False
    ROOT.mkdir(parents=True, exist_ok=True)
    MODELS.mkdir(parents=True, exist_ok=True)

    if not PY.is_file():
        on_line("Python ortami olusturuluyor...")
        if _run([uv, "venv", "--python", "3.12", "--seed", str(ROOT)], on_line) != 0 or not PY.is_file():
            LAST_ERROR["trt"] = "Python ortami olusturulamadi"
            return False

    on_line("VapourSynth + TensorRT paketleri kuruluyor...")
    if _run([uv, "pip", "install", "--python", str(PY), *PKGS], on_line) != 0:
        LAST_ERROR["trt"] = "paket kurulumu basarisiz"
        return False

    # vspipe, hangi Python'u kullanacagini %APPDATA%\vapoursynth\vapoursynth.toml'den ogrenir.
    # Bu adim yoksa "Python executable and library path couldn't be determined" hatasi verir.
    on_line("VapourSynth yapilandirmasi yaziliyor...")
    _run([str(PY), "-m", "vapoursynth", "config"], on_line, env=_build_env())

    # model paketi (852 MB) + onnx cikarma
    onnx = {k: MODELS / v for k, v in ONNX_WANT.items()}
    if not all(p.is_file() for p in onnx.values()):
        z = MODELS / "models.7z"
        if not (z.is_file() and z.stat().st_size > 800_000_000):
            on_line("Model paketi indiriliyor (~852 MB)...")
            r = requests.get(MODEL_PACK, timeout=120, stream=True)
            r.raise_for_status()
            total = int(r.headers.get("content-length") or 0)
            got = 0
            with open(z, "wb") as f:
                for ch in r.iter_content(1 << 20):
                    f.write(ch)
                    got += len(ch)
                    if total and got * 100 // total % 10 == 0:
                        on_line(f"Model paketi %{got * 100 // total}")
        on_line("Modeller cikariliyor...")
        code = ("import py7zr,sys;z=py7zr.SevenZipFile(sys.argv[1],'r');"
                "z.extract(path=sys.argv[2], targets=sys.argv[3:])")
        if _run([str(PY), "-c", code, str(z), str(MODELS), *ONNX_WANT.values()], on_line,
                env=_build_env()) != 0:
            LAST_ERROR["trt"] = "model paketi cikarilamadi"
            return False

    # motorlar
    for scale, name in ((2, "x2"), (4, "x4")):
        eng = engine(scale)
        if eng.is_file():
            continue
        src = onnx[name]
        if not src.is_file():
            continue
        on_line(f"TensorRT motoru derleniyor ({name}) — ilk seferde dakikalar surer...")
        rc = _run([str(PY), "-m", "app.tools.trt_build_engine", str(src), str(eng),
                   "--fp16", "--max-w", "1920", "--max-h", "1080"], on_line, env=_build_env())
        if rc != 0 or not eng.is_file():
            LAST_ERROR["trt"] = f"engine derlenemedi ({name})"
            return False

    if not installed():
        LAST_ERROR["trt"] = "kurulum bitti ama engine/vspipe yok"
        return False
    on_line("TensorRT yolu hazir")
    return True


# ------------------------------------------------------------------ script

def matrix_for(height: int) -> str:
    """SD icerikte BT.601, HD'de BT.709 (yanlis matris renk kaymasina yol acar)."""
    return "709" if int(height) >= 720 else "470bg"


def script(src: str, engine_path: str, width: int = 1280, height: int = 720, threads: int = 4,
           tile: int = 4096, overlap: int = 16) -> str:
    """Calistirilacak .vpy metni. Saf fonksiyon: test edilebilir.

    vs-mlrt 17 argumanlari: engine_path, tilesize, overlap, device_id, num_streams, use_cuda_graph.
    (overlap_w/overlap_h bu surumde YOK; overlap verilirse tilesize zorunlu.)
    tilesize klip boyutundan BUYUK olamaz -> kirpiyoruz.
    """
    m = matrix_for(height)
    t = max(32, min(int(tile), int(width or 512), int(height or 512)))
    ov = max(0, min(int(overlap), t // 2))
    p = lambda x: str(x).replace("\\", "/")   # noqa: E731 - .vpy icinde ters bolu kacis sorunu
    return (
        "import vapoursynth as vs\n"
        f"core = vs.core\ncore.num_threads = {max(1, int(threads))}\n"
        f"clip = core.bs.VideoSource(r'{p(src)}')\n"
        f"clip = core.resize.Bicubic(clip, format=vs.RGBS, matrix_in_s='{m}')\n"
        f"clip = core.trt.Model(clip, engine_path=r'{p(engine_path)}', "
        f"tilesize={t}, overlap={ov}, num_streams=1, device_id=0)\n"
        f"clip = core.resize.Bicubic(clip, format=vs.YUV420P8, matrix_s='{m}')\n"
        "clip.set_output()\n"
    )


def run_video(job: dict, ffmpeg: str, path: str, opts: dict[str, Any], work: Path,
              dst: Path, width: int = 1280, height: int = 720) -> Path:
    """vspipe -> ffmpeg boru hatti. Kare basina disk trafigi YOK."""
    if not installed():
        raise RuntimeError("TensorRT yolu kurulu degil")
    scale = 4 if int(opts.get("scale") or 2) >= 4 else 2
    eng = engine(scale)
    if not eng.is_file():
        raise RuntimeError(f"{scale}x motoru yok")
    vpy = work / "hat.vpy"
    vpy.write_text(script(path, str(eng), width=width, height=height,
                          threads=int(opts.get("threads") or 4),
                          tile=int(opts.get("tile") or 4096),
                          overlap=int(opts.get("overlap") or 16)), encoding="utf-8")
    total = int(opts.get("frames") or 0)
    job["line"] = "VapourSynth + TensorRT işliyor"

    enc = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-i", "-",
           "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", str(dst)]
    env = _build_env()
    vp = subprocess.Popen([str(VSPIPE), "-p", "-c", "y4m", str(vpy.resolve()), "-"], cwd=str(work),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=NO_WINDOW,
                          env=env)
    ff = subprocess.Popen(enc, stdin=vp.stdout, stdout=subprocess.DEVNULL,
                          stderr=subprocess.PIPE, creationflags=NO_WINDOW)
    if vp.stdout:
        vp.stdout.close()
    err: list[bytes] = []
    vp_tail: list[str] = []
    threading.Thread(target=lambda: err.append(ff.stderr.read() if ff.stderr else b""), daemon=True).start()

    def _watch() -> None:
        assert vp.stderr is not None
        for raw in vp.stderr:
            if job["cancel"].is_set():
                vp.kill()
                ff.kill()
                return
            txt = raw.decode("utf-8", "replace").strip()
            if txt:
                vp_tail.append(txt)
                if len(vp_tail) > 20:
                    vp_tail.pop(0)
            m = re.search(r"Frame:\s*(\d+)", txt)
            if m and total:
                job["p"] = round(min(0.97, int(m.group(1)) / total), 4)

    threading.Thread(target=_watch, daemon=True).start()
    vp.wait()
    rc = ff.wait()
    if job["cancel"].is_set():
        raise _Cancelled()
    if vp.returncode != 0 or rc != 0 or not dst.is_file():
        why = " | ".join(vp_tail[-4:]) or b"".join(err).decode("utf-8", "replace")[-220:]
        raise RuntimeError("vspipe/ffmpeg hatasi: " + (why or f"vp={vp.returncode} ff={rc}"))
    return dst


class _Cancelled(Exception):
    """Kullanici iptal etti."""
