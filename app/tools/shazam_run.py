"""python -m app.tools.shazam_run <kaynak: dosya yolu | "loopback"> <baslangic_sn> <ffmpeg>

"Bu sarki ne?": 10-12 sn ses alir (dosyadan ffmpeg ile ya da bilgisayarin cikisindan WASAPI loopback ile),
shazamio (resmi olmayan Shazam istemcisi) ile tanir. Whisper ortaminda calisir.
JSON satirlari: {"stage": ...} ... {"done": {...sarki...}} | {"error": "..."}"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import wave

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def emit(**kw) -> None:
    sys.stdout.write(json.dumps(kw, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def from_file(path: str, start: float, ffmpeg: str, out: str) -> None:
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{max(0.0, start):.2f}", "-t", "12",
                    "-i", path, "-vn", "-ac", "1", "-ar", "44100", "-f", "wav", out],
                   check=True, capture_output=True, creationflags=NO_WINDOW)


def from_loopback(out: str, seconds: int = 10) -> None:
    import numpy as np
    import soundcard as sc
    spk = sc.default_speaker()
    mic = sc.get_microphone(id=str(spk.name), include_loopback=True)
    rate = 44100
    data = mic.record(samplerate=rate, numframes=rate * seconds)   # (frames, kanal) float32
    mono = data.mean(axis=1) if data.ndim > 1 else data
    peak = float(np.abs(mono).max() or 0)
    if peak < 1e-4:
        raise RuntimeError("silence")
    pcm = (np.clip(mono / max(peak, 0.3), -1, 1) * 32767).astype("<i2")
    with wave.open(out, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm.tobytes())


async def recognize(path: str) -> dict:
    from shazamio import Shazam
    res = await Shazam().recognize(path)
    t = (res or {}).get("track") or {}
    if not t:
        return {}
    meta = {}
    for sec in t.get("sections") or []:
        for m in sec.get("metadata") or []:
            meta[str(m.get("title", "")).lower()] = m.get("text", "")
    return {"title": t.get("title", ""), "artist": t.get("subtitle", ""), "cover": (t.get("images") or {}).get("coverarthq") or (t.get("images") or {}).get("coverart") or "",
            "url": t.get("url", ""), "album": meta.get("album", ""), "year": meta.get("released", "")}


def main(argv: list[str]) -> int:
    from app.tools import load_args
    src, start, ffmpeg = (load_args(argv) + ["", "0", ""])[:3]
    fd, wav = tempfile.mkstemp(prefix="kami_song_", suffix=".wav"); os.close(fd)
    try:
        emit(stage="listen")
        try:
            if src == "loopback":
                from_loopback(wav)
            else:
                from_file(src, float(start or 0), ffmpeg, wav)
        except RuntimeError as exc:
            emit(error=str(exc)); return 2
        emit(stage="recognize")
        song = asyncio.run(recognize(wav))
        emit(done=song) if song else emit(error="not_found")
        return 0
    except Exception as exc:
        emit(error=f"{type(exc).__name__}: {str(exc)[:160]}")
        return 1
    finally:
        try:
            os.remove(wav)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
