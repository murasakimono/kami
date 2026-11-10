"""python -m app.tools.uvr_run <girdi> <cikti_klasoru> <model> <model_klasoru> <bicim:mp3|flac|wav> [kalite:fast|balanced|best]
UVR5 modelleriyle vokal / enstrumantal ayirma (python-audio-separator). JSON satirlari: {"stage": ...} ...
{"done": [dosyalar], "device": ...} | {"error": "..."}"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time

# Roformer/MDXC 'overlap': 8 = en iyi ama gercek zamanli (~150 sn sarki 149 sn, RTX 4050);
# 2 + autocast(fp16) = ~3.3 kat hizli (45 sn), kulakla fark cok az. Olcum 10.11.
QUALITY = {"fast": 2, "balanced": 4, "best": 8}
SPEED = {"fast": 0.32, "balanced": 0.55, "best": 1.0}   # ayirma suresi / sarki suresi (ilerleme tahmini)


def emit(**kw) -> None:
    sys.stdout.write(json.dumps(kw, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main(argv: list[str]) -> int:
    from app.tools import load_args
    args = load_args(argv)
    src, out_dir, model, models, fmt = args[:5]
    quality = args[5] if len(args) > 5 and args[5] in QUALITY else "fast"
    from audio_separator.separator import Separator
    os.makedirs(out_dir, exist_ok=True)
    emit(stage="load")
    ov = QUALITY[quality]
    sep = Separator(log_level=logging.WARNING, model_file_dir=models, output_dir=out_dir,
                    output_format=fmt.upper(), use_autocast=quality != "best",
                    mdxc_params={"segment_size": 256, "override_model_segment_size": False, "batch_size": 1,
                                 "overlap": ov, "pitch_shift": 0},
                    mdx_params={"hop_length": 1024, "segment_size": 256, "overlap": 0.25, "batch_size": 1, "enable_denoise": False})
    sep.load_model(model_filename=model)
    device = "cuda"
    try:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        pass
    emit(stage="separate", device=device, quality=quality)
    # audio-separator ilerleme vermiyor: sarki suresinden tahmini ilerleme (arayuz takildi sanmasin)
    stop = threading.Event()
    try:
        import librosa
        dur = float(librosa.get_duration(path=src))
    except Exception:
        dur = 0.0
    if dur > 0:
        est = max(5.0, dur * SPEED[quality] * (1.0 if device == "cuda" else 6.0))
        t0 = time.time()

        def tick() -> None:
            while not stop.wait(1.0):
                emit(p=round(min(0.3 + 0.65 * (time.time() - t0) / est, 0.95), 3))
        threading.Thread(target=tick, daemon=True).start()
    base = os.path.splitext(os.path.basename(src))[0]
    try:
        files = sep.separate(src, {"Vocals": f"{base} (Vokal)", "Instrumental": f"{base} (Enstrumantal)"})
    finally:
        stop.set()
    files = [f if os.path.isabs(f) else os.path.join(out_dir, f) for f in files]
    emit(done=files, device=device)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:
        emit(error=f"{type(exc).__name__}: {str(exc)[:300]}")
        sys.exit(1)
