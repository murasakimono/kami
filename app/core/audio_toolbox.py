"""Faz 12.4 — Kami Ses Kutusu: VST3/FX (pedalboard/FFmpeg), Audio->MIDI (Basic Pitch/FFmpeg) & Yerli TTS."""
from __future__ import annotations

import logging
import math
import shutil
import struct
import subprocess
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _ffmpeg() -> str:
    try:
        from app.engines.ytdlp_engine import find_ffmpeg
        return find_ffmpeg() or ""
    except Exception:
        return shutil.which("ffmpeg") or ""


def apply_audio_fx(
    src: str | Path,
    dst: str | Path = "",
    *,
    preset: str = "vocal_studio",
    reverb: float = 0.2,
    compressor: bool = True,
) -> dict[str, Any]:
    """Ses dosyasina pedalboard (varsa) veya FFmpeg FX zinciri uygular."""
    src_p = Path(src)
    if not src_p.is_file():
        return {"ok": False, "error": "Kaynak ses dosyasi bulunamadi"}
    out_p = Path(dst) if dst else src_p.with_name(f"{src_p.stem}_{preset}.wav")

    try:
        import pedalboard
        from pedalboard.io import AudioFile
        board = pedalboard.Pedalboard()
        if compressor:
            board.append(pedalboard.Compressor(threshold_db=-18, ratio=3.5))
        if reverb > 0:
            board.append(pedalboard.Reverb(room_size=min(1.0, max(0.05, reverb)), wet_level=min(0.6, reverb)))
        if preset == "radio":
            board.append(pedalboard.HighpassFilter(cutoff_hz=280))
            board.append(pedalboard.LowpassFilter(cutoff_hz=3600))
        with AudioFile(str(src_p)) as f:
            audio = f.read(f.frames)
            sr = f.samplerate
        effected = board(audio, sr)
        with AudioFile(str(out_p), "w", sr, effected.shape[0]) as f:
            f.write(effected)
        return {"ok": True, "path": str(out_p), "engine": "pedalboard"}
    except Exception:
        pass

    ff = _ffmpeg()
    if not ff:
        return {"ok": False, "error": "FFmpeg bulunamadi"}

    filters = []
    if preset == "radio":
        filters.append("highpass=f=300,lowpass=f=3400")
    elif preset == "bass_boost":
        filters.append("bass=g=6:f=90")
    else:
        filters.append("highpass=f=80")
    if compressor:
        filters.append("acompressor=threshold=-18dB:ratio=3:attack=10:release=120")
    if reverb > 0.05:
        delay_ms = int(45 + reverb * 80)
        decay = round(min(0.6, 0.2 + reverb * 0.4), 2)
        filters.append(f"aecho=0.8:0.88:{delay_ms}:{decay}")

    r = subprocess.run(
        [ff, "-y", "-i", str(src_p), "-af", ",".join(filters), str(out_p)],
        capture_output=True, text=True, timeout=300, creationflags=NO_WINDOW,
    )
    if r.returncode != 0 or not out_p.is_file():
        return {"ok": False, "error": (r.stderr or "").splitlines()[-1:] or "FX hatasi"}
    return {"ok": True, "path": str(out_p), "engine": "ffmpeg"}


def _hz_to_midi(hz: float) -> int:
    if hz <= 0:
        return 0
    return max(21, min(108, int(round(69 + 12 * math.log2(hz / 440.0)))))


def audio_to_notes(src: str | Path) -> dict[str, Any]:
    """Audio -> Nota/MIDI analizi (Basic Pitch varsa tam MIDI, yoksa FFmpeg temel frekans notalari)."""
    src_p = Path(src)
    if not src_p.is_file():
        return {"ok": False, "error": "Ses dosyasi bulunamadi", "notes": []}

    try:
        from basic_pitch.inference import predict
        _, midi_data, note_events = predict(str(src_p))
        midi_out = src_p.with_suffix(".mid")
        midi_data.write(str(midi_out))
        notes = [
            {"start": round(float(n[0]), 3), "end": round(float(n[1]), 3), "midi": int(n[2]), "amp": round(float(n[3]), 3)}
            for n in note_events[:400]
        ]
        return {"ok": True, "engine": "basic_pitch", "midi_path": str(midi_out), "notes": notes}
    except Exception:
        pass

    ff = _ffmpeg()
    if not ff:
        return {"ok": False, "error": "FFmpeg bulunamadi", "notes": []}

    sr = 8000
    r = subprocess.run(
        [ff, "-v", "error", "-t", "20", "-i", str(src_p), "-ac", "1", "-ar", str(sr), "-f", "s16le", "pipe:1"],
        capture_output=True, timeout=30, creationflags=NO_WINDOW,
    )
    raw = r.stdout
    n = len(raw) // 2
    if n < sr // 2:
        return {"ok": False, "error": "Ses cok kisa", "notes": []}
    samples = struct.unpack(f"<{n}h", raw[:n * 2])
    hop = sr // 4   # 0.25 sn adim
    notes: list[dict[str, Any]] = []
    min_lag, max_lag = sr // 500, sr // 75
    for idx in range(0, n - hop, hop):
        win = samples[idx:idx + hop]
        rms = math.sqrt(sum(s * s for s in win) / len(win))
        if rms < 400:
            continue
        best_lag, best_corr = min_lag, -1.0
        for lag in range(min_lag, min(max_lag, len(win) // 2)):
            c = sum(win[i] * win[i + lag] for i in range(0, len(win) - lag, 2))
            if c > best_corr:
                best_corr, best_lag = c, lag
        hz = sr / best_lag if best_lag else 0.0
        notes.append({"start": round(idx / sr, 2), "end": round((idx + hop) / sr, 2), "midi": _hz_to_midi(hz), "hz": round(hz, 1)})
    return {"ok": True, "engine": "ffmpeg_pitch", "midi_path": "", "notes": notes}


def synthesize_tts(text: str, out_wav: str | Path, *, lang: str = "tr") -> dict[str, Any]:
    """Yerli cevrimdisi TTS (Piper CLI varsa onu, yoksa Windows SAPI uzerinden WAV uretir)."""
    clean = (text or "").strip()
    if not clean:
        return {"ok": False, "error": "Metin bos"}
    dst = Path(out_wav)
    dst.parent.mkdir(parents=True, exist_ok=True)

    piper = shutil.which("piper") or shutil.which("piper.exe")
    if piper:
        try:
            r = subprocess.run([piper, "--output_file", str(dst)], input=clean, text=True, capture_output=True, timeout=60, creationflags=NO_WINDOW)
            if r.returncode == 0 and dst.is_file():
                return {"ok": True, "path": str(dst), "engine": "piper"}
        except Exception:
            pass

    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.SetOutputToWaveFile($args[0]); "
        "$s.Speak($args[1]); "
        "$s.Dispose();"
    )
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps, str(dst), clean],
        capture_output=True, text=True, timeout=45, creationflags=NO_WINDOW,
    )
    if r.returncode == 0 and dst.is_file():
        return {"ok": True, "path": str(dst), "engine": "windows_sapi"}
    return {"ok": False, "error": (r.stderr or "TTS basarisiz").strip()[:200]}
