"""python -m app.tools.whisper_run <girdi> <cikti.srt> <dil:auto|tr|en> <model> <model_klasoru> [strong_song:0|1] [elrc_out]
Satir satir JSON yazar: {"p": 0.42} ... {"done": "<srt>", "elrc": "<lrc>", "lang": "tr", "device": "cuda"} | {"error": "..."}"""
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


def lrc_ts(t: float) -> str:
    total = max(0.0, float(t or 0.0))
    mm = int(total // 60)
    ss = total % 60
    return f"{mm:02d}:{ss:05.2f}"


def main(argv: list[str]) -> int:
    from app.tools import load_args
    args = load_args(argv)
    src, out, lang, model_name, models = args[:5]
    strong_song = str(args[5] if len(args) > 5 else "0").strip().lower() in ("1", "true", "strong", "song")
    elrc_out = str(args[6] if len(args) > 6 else "").strip()
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
    if strong_song:
        # Kami 2.0 Guclu Sarki Modu: Hizli rap / vokallerde VAD bar kesmesin, condition_on_previous_text=False ile
        # nakarat/bosluk sonrasi takilma veya bar atlama sifirlansin, kelime zaman damgalari (ELRC) uretilsin.
        tx_kwargs = {
            "language": None if lang == "auto" else lang,
            "beam_size": 5,
            "condition_on_previous_text": False,
            "vad_filter": True,
            "vad_parameters": {"min_silence_duration_ms": 1400, "speech_pad_ms": 550, "threshold": 0.22},
            "no_speech_threshold": 0.92,
            "compression_ratio_threshold": 2.8,
            "word_timestamps": True,
        }
        if lang == "tr":
            tx_kwargs["initial_prompt"] = "Türkçe rap şarkı sözleri, nakarat ve verse satırları:"
    else:
        tx_kwargs = {
            "language": None if lang == "auto" else lang,
            "beam_size": 5,
            "vad_filter": True,
            "vad_parameters": {"min_silence_duration_ms": 500},
        }
    segments, info = model.transcribe(src, **tx_kwargs)
    total = float(info.duration or 0) or 1.0
    n = 0
    tmp = out + ".part"
    elrc_lines: list[str] = []
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        for seg in segments:
            text = (seg.text or "").strip()
            if not text:
                continue
            n += 1
            f.write(f"{n}\n{ts(seg.start)} --> {ts(seg.end)}\n{text}\n\n")
            words = getattr(seg, "words", None) or []
            if words:
                w_tags = " ".join(
                    f"<{lrc_ts(w.start)}>{(w.word or '').strip()}"
                    for w in words if (w.word or "").strip()
                )
                elrc_lines.append(f"[{lrc_ts(seg.start)}]{w_tags or text}")
            else:
                elrc_lines.append(f"[{lrc_ts(seg.start)}]{text}")
            emit(p=round(min(seg.end / total, 1.0), 3))
    os.replace(tmp, out)
    if elrc_out and elrc_lines:
        with open(elrc_out, "w", encoding="utf-8", newline="\n") as ef:
            ef.write("\n".join(elrc_lines) + "\n")
    emit(done=out, elrc=elrc_out if elrc_lines else "", lang=info.language, device=device, segments=n, strong=strong_song)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:
        emit(error=f"{type(exc).__name__}: {str(exc)[:300]}")
        sys.exit(1)
