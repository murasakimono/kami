"""python -m app.tools.whisper_run <girdi> <cikti.srt> <dil:auto|tr|en> <model> <model_klasoru>
Satir satir JSON yazar: {"p": 0.42} ... {"done": "<srt>", "lang": "tr", "device": "cuda"} | {"error": "..."}"""
from __future__ import annotations

import json
import os
import sys


def emit(**kw) -> None:
    sys.stdout.write(json.dumps(kw, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _cuda_dlls() -> None:
    """pip'in nvidia-cublas-cu12 / nvidia-cudnn-cu12 DLL'leri (Windows'ta PATH'te degiller)."""
    import importlib.util
    for pkg in ("nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_runtime"):
        try:
            spec = importlib.util.find_spec(pkg)
        except ModuleNotFoundError:
            continue
        for base in (spec.submodule_search_locations or []) if spec else []:
            b = os.path.join(base, "bin")
            if os.path.isdir(b):
                os.add_dll_directory(b)
                os.environ["PATH"] = b + os.pathsep + os.environ.get("PATH", "")


def ts(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main(argv: list[str]) -> int:
    src, out, lang, model_name, models = argv[:5]
    _cuda_dlls()
    from faster_whisper import WhisperModel
    model = device = None
    for device, ctype in (("cuda", "float16"), ("cpu", "int8")):
        try:
            model = WhisperModel(model_name, device=device, compute_type=ctype, download_root=models)
            break
        except Exception as exc:   # CUDA yoksa CPU'ya dus
            emit(warn=f"{device}: {type(exc).__name__}: {str(exc)[:200]}")
    if model is None:
        emit(error="model_load")
        return 2
    segments, info = model.transcribe(src, language=None if lang == "auto" else lang, beam_size=5,
                                      vad_filter=True, vad_parameters={"min_silence_duration_ms": 500})
    total = float(info.duration or 0) or 1.0
    n = 0
    tmp = out + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        for seg in segments:
            text = (seg.text or "").strip()
            if not text:
                continue
            n += 1
            f.write(f"{n}\n{ts(seg.start)} --> {ts(seg.end)}\n{text}\n\n")
            emit(p=round(min(seg.end / total, 1.0), 3))
    os.replace(tmp, out)
    emit(done=out, lang=info.language, device=device, segments=n)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:
        emit(error=f"{type(exc).__name__}: {str(exc)[:300]}")
        sys.exit(1)
