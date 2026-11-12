"""python -m app.tools.rembg_run <girdi> <cikti.png> [model]

Yerel yapay zeka ile arka plan kaldirma (rembg, ONNX, CPU). Model ilk kullanimda bir kez iner (~170 MB).
Whisper ortaminda calisir. JSON satirlari: {"stage": ...} ... {"done": "<cikti>"} | {"error": "..."}"""
from __future__ import annotations

import json
import sys


def emit(**kw) -> None:
    sys.stdout.write(json.dumps(kw, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main(argv: list[str]) -> int:
    from app.tools import load_args
    src, out, model = (load_args(argv) + ["", "", "isnet-general-use"])[:3]
    try:
        emit(stage="model")
        from PIL import Image, ImageOps
        from rembg import new_session, remove
        sess = new_session(model or "isnet-general-use")
        emit(stage="remove")
        im = ImageOps.exif_transpose(Image.open(src)).convert("RGBA")
        res = remove(im, session=sess, post_process_mask=True)
        res.save(out, "PNG", optimize=True)
        emit(done=out)
        return 0
    except Exception as exc:
        emit(error=f"{type(exc).__name__}: {str(exc)[:160]}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
