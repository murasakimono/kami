"""python -m app.tools.selftest <whisper|uvr> <test_klasoru>
Kurulumdan sonra (ve onarimda) kendi kendine test: modeli INDIRMEDEN paketlerin ice aktarilip kucuk bir sesi
cozebildigini dener. Tek satir JSON: {"ok": true, "device": "cuda"} | {"ok": false, "error": "..."}"""
from __future__ import annotations

import json
import math
import os
import shutil
import struct
import subprocess
import sys
import wave


def emit(**kw) -> None:
    sys.stdout.write(json.dumps(kw, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def make_audio(folder: str) -> str:
    """1 sn 440 Hz ton: once WAV (stdlib), ffmpeg varsa MP3'e cevirir (gercek kullanim MP3)."""
    os.makedirs(folder, exist_ok=True)
    wav = os.path.join(folder, "kami_selftest.wav")
    with wave.open(wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / 16000)))
                               for i in range(16000)))
    ff = shutil.which("ffmpeg")
    try:
        from app.engines.ytdlp_engine import find_ffmpeg
        ff = find_ffmpeg() or ff
    except Exception:
        pass
    if ff:
        mp3 = os.path.join(folder, "kami_selftest.mp3")
        r = subprocess.run([ff, "-y", "-v", "error", "-i", wav, mp3], capture_output=True,
                           creationflags=0x08000000, timeout=60)
        if r.returncode == 0 and os.path.isfile(mp3):
            return mp3
    return wav


def test_whisper(audio: str) -> dict:
    from app.tools.whisper_run import _cuda_dlls
    _cuda_dlls()
    from faster_whisper.audio import decode_audio   # PyAV uyumu (metadata_errors hatasi burada cikar)
    samples = decode_audio(audio)
    if len(samples) < 8000:
        return {"ok": False, "error": "decode_short"}
    import ctranslate2
    device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    return {"ok": True, "device": device}


def test_uvr(audio: str) -> dict:
    import audioread                                  # VR mimarisi + spec_utils bunu ister
    from audio_separator.separator import Separator  # noqa: F401  (ice aktarma zinciri)
    import librosa
    y, _sr = librosa.load(audio, sr=44100, mono=False)
    if y.size < 20000:
        return {"ok": False, "error": "decode_short"}
    with audioread.audio_open(audio) as f:
        _ = f.duration
    device = "cpu"
    try:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        pass
    return {"ok": True, "device": device}


def test_iopaint(_audio: str) -> dict:
    import iopaint  # noqa: F401
    import torch
    return {"ok": True, "device": "cuda" if torch.cuda.is_available() else "cpu"}


def main(argv: list[str]) -> int:
    name, folder = argv[:2]
    if name == "iopaint":
        res = test_iopaint("")
        emit(**res)
        return 0 if res.get("ok") else 1
    audio = make_audio(folder)
    try:
        res = {"whisper": test_whisper, "uvr": test_uvr}[name](audio)
    finally:
        for ext in (".wav", ".mp3"):
            p = os.path.join(folder, "kami_selftest" + ext)
            if os.path.exists(p):
                os.remove(p)
    emit(**res)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:
        emit(ok=False, error=f"{type(exc).__name__}: {str(exc)[:300]}")
        sys.exit(1)
