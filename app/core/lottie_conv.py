"""Lottie -> seffaf WebM. rlottie-python (ana ortam) ile kareleri cizer, ffmpeg'e RGBA borusuyla verir."""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import urllib.request
import zipfile
from pathlib import Path

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130 Safari/537.36"
NOWIN = 0x08000000 if os.name == "nt" else 0


def fetch(src: str, folder: Path) -> Path:
    """Yerel dosya ya da adres (LottieFiles sayfasi, lottie.host .json/.lottie) -> yerel .json."""
    folder.mkdir(parents=True, exist_ok=True)
    if os.path.isfile(src):
        p = Path(src)
    else:
        if not src.startswith("https://"):
            raise ValueError("dosya ya da https adresi ver")
        url = src
        if not re.search(r"\.(json|lottie)(\?|$)", url):   # sayfa: icindeki lottie.host baglantisini bul
            html = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=20).read().decode("utf-8", "replace")
            m = re.search(r"https://(?:lottie\.host|assets\d*\.lottiefiles\.com)/[^\"'\s]+?\.(?:json|lottie)", html)
            if not m:
                raise ValueError("sayfada Lottie dosyası bulunamadı (.json/.lottie adresini doğrudan yapıştır)")
            url = m.group(0)
        data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30).read(30_000_000)
        name = re.sub(r"[^\w.-]+", "_", url.rsplit("/", 1)[-1].split("?")[0])[:80] or "anim.json"
        p = folder / name
        p.write_bytes(data)
    if p.suffix.lower() == ".lottie":   # dotLottie = zip
        with zipfile.ZipFile(io.BytesIO(p.read_bytes())) as z:
            names = [n for n in z.namelist() if n.startswith("animations/") and n.endswith(".json")] or [n for n in z.namelist() if n.endswith(".json") and "manifest" not in n]
            if not names:
                raise ValueError(".lottie içinde animasyon yok")
            j = folder / (p.stem + ".json")
            j.write_bytes(z.read(names[0]))
            p = j
    json.loads(p.read_text("utf-8"))   # gecerli mi
    return p


def to_webm(src: Path, ffmpeg: str, height: int = 1080) -> Path:
    from rlottie_python import LottieAnimation
    out = src.with_suffix(".webm")
    if out.is_file() and out.stat().st_mtime > src.stat().st_mtime:
        return out
    anim = LottieAnimation.from_file(str(src))
    w0, h0 = anim.lottie_animation_get_size()
    fps = anim.lottie_animation_get_framerate() or 30
    n = anim.lottie_animation_get_totalframe()
    k = min(2.0, height / max(1, h0)) if h0 < height else 1.0
    w, h = int(w0 * k) // 2 * 2, int(h0 * k) // 2 * 2
    enc = subprocess.Popen([ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra",
                            "-s", f"{w}x{h}", "-r", f"{fps:.4f}", "-i", "pipe:0", "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
                            "-auto-alt-ref", "0", "-b:v", "0", "-crf", "24", "-row-mt", "1", str(out)], stdin=subprocess.PIPE, creationflags=NOWIN)
    for i in range(n):
        buf = anim.lottie_animation_render(frame_num=i, width=w, height=h)
        enc.stdin.write(bytes(buf))
    enc.stdin.close()
    enc.wait()
    if enc.returncode or not out.is_file():
        raise RuntimeError("Lottie dönüştürülemedi")
    return out
