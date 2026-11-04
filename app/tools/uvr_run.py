"""python -m app.tools.uvr_run <girdi> <cikti_klasoru> <model> <model_klasoru> <bicim:mp3|flac|wav>
UVR5 modelleriyle vokal / enstrumantal ayirma (python-audio-separator). JSON satirlari: {"stage": ...} ...
{"done": [dosyalar], "device": ...} | {"error": "..."}"""
from __future__ import annotations

import json
import logging
import os
import sys


def emit(**kw) -> None:
    sys.stdout.write(json.dumps(kw, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main(argv: list[str]) -> int:
    src, out_dir, model, models, fmt = argv[:5]
    from audio_separator.separator import Separator
    os.makedirs(out_dir, exist_ok=True)
    emit(stage="load")
    sep = Separator(log_level=logging.WARNING, model_file_dir=models, output_dir=out_dir,
                    output_format=fmt.upper())
    sep.load_model(model_filename=model)
    device = "cuda"
    try:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        pass
    emit(stage="separate", device=device)
    base = os.path.splitext(os.path.basename(src))[0]
    files = sep.separate(src, {"Vocals": f"{base} (Vokal)", "Instrumental": f"{base} (Enstrumantal)"})
    files = [f if os.path.isabs(f) else os.path.join(out_dir, f) for f in files]
    emit(done=files, device=device)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:
        emit(error=f"{type(exc).__name__}: {str(exc)[:300]}")
        sys.exit(1)
