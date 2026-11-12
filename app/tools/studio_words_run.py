"""python -m app.tools.studio_words_run <girdi> <cikti.json> <bas> <sure> <dil> <model> <model_klasoru> <ffmpeg>
Kami Studio otomatik altyazi: kelime zamanli Whisper. Cikti: {"lang", "words": [{"w","s","e"}]} (sure: araliga gore sn).
Satir satir JSON: {"p": 0.4} ... {"done": 1} | {"error": "..."}"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

from app.tools.whisper_run import _cuda_dlls, emit


def main(argv: list[str]) -> int:
    from app.tools import load_args
    src, out, start, dur, lang, model_name, models, ff = load_args(argv)[:8]
    fd, wav = tempfile.mkstemp(prefix="kstudio_", suffix=".wav")
    os.close(fd)
    try:
        r = subprocess.run([ff, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-ss", start, "-t", dur, "-i", src,
                            "-vn", "-ac", "1", "-ar", "16000", wav], capture_output=True, creationflags=0x08000000 if os.name == "nt" else 0)
        if r.returncode:
            emit(error="ffmpeg: " + r.stderr.decode("utf-8", "replace")[-200:])
            return 2
        _cuda_dlls()
        from faster_whisper import WhisperModel
        model = None
        for device, ctype in (("cuda", "float16"), ("cpu", "int8")):
            try:
                model = WhisperModel(model_name, device=device, compute_type=ctype, download_root=models)
                break
            except Exception as exc:
                emit(warn=f"{device}: {str(exc)[:160]}")
        if model is None:
            emit(error="model_load")
            return 2
        segs, info = model.transcribe(wav, language=None if lang == "auto" else lang, beam_size=5, word_timestamps=True,
                                      vad_filter=True, vad_parameters={"min_silence_duration_ms": 300})
        total = float(info.duration or 0) or 1.0
        words = []
        for seg in segs:
            for w in seg.words or []:
                t = (w.word or "").strip()
                if t:
                    words.append({"w": t, "s": round(float(w.start), 3), "e": round(float(w.end), 3)})
            emit(p=round(min(float(seg.end) / total, 1.0), 3))
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"lang": info.language, "words": words}, f, ensure_ascii=False)
        emit(done=1, words=len(words))
        return 0
    finally:
        try:
            os.remove(wav)
        except OSError:
            pass


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:
        emit(error=f"{type(exc).__name__}: {str(exc)[:300]}")
        sys.exit(1)
