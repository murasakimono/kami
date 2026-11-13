"""python -m app.tools.studio_matte_run <video> <cikti.webm> <bas> <sure> <model> <ffmpeg>
Videoda arka plan silme: kare kare rembg (BiRefNet), seffaf WebM (VP9 alfa) + orijinal ses. IOPaint ortaminda calisir.
Satir satir JSON: {"p": 0.3, "line": "..."} ... {"done": 1} | {"error": "..."}"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

NOWIN = 0x08000000 if os.name == "nt" else 0


def emit(**kw) -> None:
    sys.stdout.write(json.dumps(kw) + "\n")
    sys.stdout.flush()


def main(argv: list[str]) -> int:
    from app.tools import load_args
    src, out, start, dur, model, ff = load_args(argv)[:6]
    dur_f = float(dur)
    ffprobe = os.path.join(os.path.dirname(ff), "ffprobe.exe" if os.name == "nt" else "ffprobe")
    info = json.loads(subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate",
                                      "-of", "json", src], capture_output=True, creationflags=NOWIN).stdout or b"{}")
    s0 = (info.get("streams") or [{}])[0]
    w, h = int(s0.get("width") or 0), int(s0.get("height") or 0)
    if not w:
        emit(error="video okunamadı")
        return 2
    if h > 1080:   # 4K'yi 1080'e indir (VRAM/sure)
        w, h = int(w * 1080 / h) // 2 * 2, 1080
    num, den = (s0.get("r_frame_rate") or "30/1").split("/")
    fps = float(num) / float(den or 1)
    total = max(1, int(dur_f * fps))
    emit(p=0.01, line="model yükleniyor")
    from PIL import Image
    from rembg import new_session, remove
    sess = new_session(model)
    dec = subprocess.Popen([ff, "-hide_banner", "-nostdin", "-loglevel", "error", "-ss", start, "-t", dur, "-i", src,
                            "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], stdout=subprocess.PIPE, creationflags=NOWIN)
    enc = subprocess.Popen([ff, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}",
                            "-r", f"{fps:.5f}", "-i", "pipe:0", "-ss", start, "-t", dur, "-i", src, "-map", "0:v", "-map", "1:a?",
                            "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0", "-b:v", "0", "-crf", "28", "-row-mt", "1",
                            "-deadline", "good", "-cpu-used", "4", "-c:a", "libopus", "-b:a", "160k", "-shortest", out],
                           stdin=subprocess.PIPE, creationflags=NOWIN)
    size = w * h * 3
    n, t0 = 0, time.time()
    while True:
        buf = dec.stdout.read(size)
        if len(buf) < size:
            break
        im = Image.frombytes("RGB", (w, h), buf)
        mask = remove(im, session=sess, only_mask=True, post_process_mask=True)
        rgba = im.convert("RGBA")
        rgba.putalpha(mask.convert("L").resize((w, h)))
        enc.stdin.write(rgba.tobytes())
        n += 1
        if n % 5 == 0:
            el = time.time() - t0
            emit(p=round(min(0.99, n / total), 3), line=f"{n}/{total} kare · kalan ~{int(el / n * (total - n))} sn")
    enc.stdin.close()
    enc.wait()
    dec.wait()
    if enc.returncode or not os.path.isfile(out):
        emit(error="kodlama başarısız")
        return 2
    emit(done=1, frames=n)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:
        emit(error=f"{type(exc).__name__}: {str(exc)[:300]}")
        sys.exit(1)
