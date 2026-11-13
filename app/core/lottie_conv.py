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

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0 Safari/537.36"
_FILE = re.compile(r"https://(?:lottie\.host|assets[-\w]*\.lottiefiles\.com)/[^\"'\s<>&\\]+?\.(?:json|lottie)")


def _get(url: str, data: bytes | None = None, headers: dict | None = None, limit: int = 8_000_000) -> bytes:
    h = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9", **(headers or {})}
    return urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h), timeout=25).read(limit)


def resolve(src: str) -> str:
    """Sayfa / paylasim baglantisini dogrudan .json/.lottie adresine cevirir."""
    url = src.strip()
    if re.search(r"\.(json|lottie)(\?|#|$)", url):
        return url
    m = re.search(r"app\.lottiefiles\.com/share/([\w-]+)", url)
    if m:   # paylasim baglantisi: sayfa bos (SPA), dosya adresi herkese acik GraphQL'den
        q = "query($c:String!){publicShareByCode(shareCode:$c){resource{__typename ... on File{fileObject{url}}}}}"
        d = json.loads(_get("https://graphql.lottiefiles.com/2022-08", json.dumps({"query": q, "variables": {"c": m.group(1)}}).encode(),
                            {"Content-Type": "application/json", "Origin": "https://app.lottiefiles.com"}))
        f = (((d.get("data") or {}).get("publicShareByCode") or {}).get("resource") or {}).get("fileObject") or {}
        if f.get("url"):
            return f["url"]
        err = ((d.get("errors") or [{}])[0]).get("message") or "erişilemedi"
        raise ValueError(f"paylaşım bağlantısı açılamadı ({err}); paylaşım herkese açık olmalı")
    html = _get(url).decode("utf-8", "replace")
    flat = html.replace("\\/", "/").replace("\\u002F", "/").replace("%2F", "/").replace("%3A", ":")
    slug = re.search(r"-([A-Za-z0-9]{8,12})/?(?:[?#]|$)", url)   # lottiefiles.com/free-animation/ad-KOD
    found = _FILE.findall(flat)
    if slug:
        own = [f for f in found if slug.group(1) in f]
        found = own or found
    if not found:
        raise ValueError("sayfada Lottie dosyası bulunamadı (.json/.lottie adresini doğrudan yapıştır ya da dosyayı seç)")
    return found[0]


NOWIN = 0x08000000 if os.name == "nt" else 0


def fetch(src: str, folder: Path) -> Path:
    """Yerel dosya ya da adres (LottieFiles sayfasi, lottie.host .json/.lottie) -> yerel .json."""
    folder.mkdir(parents=True, exist_ok=True)
    if os.path.isfile(src):
        p = Path(src)
    else:
        if not src.startswith("https://"):
            raise ValueError("dosya ya da https adresi ver")
        url = resolve(src)
        data = _get(url, limit=30_000_000)
        name = re.sub(r"[^\w.-]+", "_", url.rsplit("/", 1)[-1].split("?")[0])[:80] or "anim.json"
        p = folder / name
        p.write_bytes(data)
    if p.suffix.lower() == ".lottie":   # dotLottie = zip
        with zipfile.ZipFile(io.BytesIO(p.read_bytes())) as z:
            names = [n for n in z.namelist() if n.startswith("animations/") and n.endswith(".json")] or [n for n in z.namelist() if n.endswith(".json") and "manifest" not in n]
            if not names:
                raise ValueError(".lottie içinde animasyon yok")
            j = folder / (p.stem + ".json")
            anim = json.loads(z.read(names[0]))
            import base64
            files = {n.rsplit("/", 1)[-1]: n for n in z.namelist() if not n.endswith("/")}
            for a in anim.get("assets") or []:   # gomulu olmayan gorselleri iceri al (rlottie disari bakamaz)
                fn = a.get("p")
                if fn and not str(fn).startswith("data:") and fn in files:
                    ext = fn.rsplit(".", 1)[-1].lower()
                    mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
                    a.update(u="", e=1, p=f"data:{mime};base64," + base64.b64encode(z.read(files[fn])).decode())
            j.write_text(json.dumps(anim), "utf-8")
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
    from app.core.procjob import attach
    enc = attach(subprocess.Popen([ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra",
                            "-s", f"{w}x{h}", "-r", f"{fps:.4f}", "-i", "pipe:0", "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
                            "-auto-alt-ref", "0", "-b:v", "0", "-crf", "24", "-row-mt", "1", "-deadline", "good", "-cpu-used", "5", str(out)],
                           stdin=subprocess.PIPE, creationflags=NOWIN))
    for i in range(n):
        buf = anim.lottie_animation_render(frame_num=i, width=w, height=h)
        enc.stdin.write(bytes(buf))
    enc.stdin.close()
    enc.wait()
    if enc.returncode or not out.is_file():
        raise RuntimeError("Lottie dönüştürülemedi")
    return out
