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


def _torch_birefnet(model: str):
    """BiRefNet (resmi agirliklar, transformers) - ekran kartinda fp16 + GPU resize + batch: kare basina ~0.15-0.25 sn."""
    try:
        import torch
        import torch.nn.functional as F
        if not torch.cuda.is_available():
            return None
        from transformers import AutoModelForImageSegmentation
        repo = {"birefnet-general-lite": "ZhengPeng7/BiRefNet_lite"}.get(model, "ZhengPeng7/BiRefNet")
        net = AutoModelForImageSegmentation.from_pretrained(repo, trust_remote_code=True)
        net.to("cuda").eval().half()
        torch.backends.cudnn.benchmark = True
        mean = torch.tensor([0.485, 0.456, 0.406], device="cuda").view(1, 3, 1, 1).half()
        std = torch.tensor([0.229, 0.224, 0.225], device="cuda").view(1, 3, 1, 1).half()
        emit(p=0.02, line="aygıt: CUDA (torch fp16 batch)")

        def predict_batch(frames_rgb: list[bytes], w: int, h: int) -> list[bytes]:
            import numpy as np
            arr = np.stack([np.frombuffer(b, dtype=np.uint8).reshape(h, w, 3) for b in frames_rgb], axis=0)
            x = torch.from_numpy(arr).to("cuda", non_blocking=True).permute(0, 3, 1, 2).half() / 255.0
            x = F.interpolate(x, size=(1024, 1024), mode="bilinear", align_corners=False)
            with torch.no_grad():
                y = net((x - mean) / std)[-1].sigmoid()
                y = F.interpolate(y, size=(h, w), mode="bilinear", align_corners=False)
                masks = y[:, 0].float().clamp(0, 1).mul(255).byte().cpu().numpy()
            out_rgba = []
            for i in range(len(frames_rgb)):
                rgba = np.empty((h, w, 4), dtype=np.uint8)
                rgba[..., :3] = arr[i]
                rgba[..., 3] = masks[i]
                out_rgba.append(rgba.tobytes())
            return out_rgba
        return predict_batch
    except Exception as exc:
        emit(p=0.02, line=f"torch yolu olmadı ({type(exc).__name__}), rembg deneniyor")
        return None


def _rembg(model: str):
    try:
        import torch  # noqa: F401  (CUDA DLL'leri onnxruntime icin)
        import onnxruntime as ort
        if hasattr(ort, "preload_dlls"):
            ort.preload_dlls()
    except Exception:
        pass
    from rembg import new_session, remove
    sess = new_session(model, providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    return lambda im: remove(im, session=sess, only_mask=True, post_process_mask=True)


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
    try:
        from app.core.procjob import attach
    except Exception:
        attach = lambda p: p  # noqa: E731
    from PIL import Image
    predict_batch = _torch_birefnet(model)
    predict = None if predict_batch else _rembg(model)
    dec = attach(subprocess.Popen([ff, "-hide_banner", "-nostdin", "-loglevel", "error", "-ss", start, "-t", dur, "-i", src,
                            "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], stdout=subprocess.PIPE, creationflags=NOWIN))
    enc = attach(subprocess.Popen([ff, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}",
                            "-r", f"{fps:.5f}", "-i", "pipe:0", "-ss", start, "-t", dur, "-i", src, "-map", "0:v", "-map", "1:a?",
                            "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0", "-b:v", "0", "-crf", "28", "-row-mt", "1",
                            "-deadline", "good", "-cpu-used", "4", "-c:a", "libopus", "-b:a", "160k", "-shortest", out],
                           stdin=subprocess.PIPE, creationflags=NOWIN))
    size = w * h * 3
    n, t0 = 0, time.time()
    batch_sz = 4 if predict_batch else 1
    while True:
        frames = []
        for _ in range(batch_sz):
            buf = dec.stdout.read(size)
            if len(buf) < size:
                break
            frames.append(buf)
        if not frames:
            break
        if predict_batch:
            for rgba_bytes in predict_batch(frames, w, h):
                enc.stdin.write(rgba_bytes)
        else:
            im = Image.frombytes("RGB", (w, h), frames[0])
            mask = predict(im)
            rgba = im.convert("RGBA")
            rgba.putalpha(mask.convert("L").resize((w, h)))
            enc.stdin.write(rgba.tobytes())
        n += len(frames)
        if n % 5 == 0 or len(frames) < batch_sz:
            el = time.time() - t0
            emit(p=round(min(0.99, n / total), 3), line=f"{n}/{total} kare · kalan ~{int(el / max(1, n) * max(0, total - n))} sn")
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
