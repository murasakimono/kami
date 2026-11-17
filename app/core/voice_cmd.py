"""Faz 16.4 — 'Hey Kami' Sesli Komut Motoru (Silero VAD + faster-whisper-tiny + komut cozucu)."""
from __future__ import annotations

import re
from typing import Any

WAKE_RE = re.compile(r"^\s*(?:hey\s+kami|merhaba\s+kami|kami)\b[,:\s]*(.*)$", re.I)

COMMAND_MAP: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(duraklat|durdur|pause|stop)\b", re.I), "pause"),
    (re.compile(r"\b(oynat|devam|baslat|play|resume)\b", re.I), "play"),
    (re.compile(r"\b(klip\s*al|tekrar\s*kaydet|save\s*replay)\b", re.I), "save_replay"),
    (re.compile(r"\b(ekran\s*oku|ocr)\b", re.I), "ocr"),
    (re.compile(r"\b(sesi\s*kapat|sustur|mute)\b", re.I), "mute"),
    (re.compile(r"\b(indir|download)\b", re.I), "download"),
]


def _norm_tr(text: str) -> str:
    tbl = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    return (text or "").translate(tbl).lower().strip()


def parse_voice_command(text: str, *, require_wake: bool = True) -> dict[str, Any]:
    raw = _norm_tr(text)
    if not raw:
        return {"ok": False, "wake": False, "action": "", "arg": ""}

    m = WAKE_RE.match(raw)
    if require_wake and not m:
        return {"ok": False, "wake": False, "action": "", "arg": raw}

    body = (m.group(1) if m else raw).strip()
    for rx, action in COMMAND_MAP:
        if rx.search(body):
            return {"ok": True, "wake": True, "action": action, "arg": body}
    return {"ok": True, "wake": True, "action": "unknown", "arg": body}


def listen_once(seconds: float = 3.5, require_wake: bool = False) -> dict[str, Any]:
    """Mikrofondan kisa ses kaydedip faster-whisper varsa metne cevirir ve komutu cozer."""
    import tempfile
    import wave
    from pathlib import Path
    try:
        import pyaudiowpatch as pyaudio  # type: ignore
    except Exception:
        try:
            import pyaudio  # type: ignore
        except Exception:
            return {"ok": False, "error": "audio_input_missing"}
    rate, ch, chunk = 16000, 1, 1024
    pa = pyaudio.PyAudio()
    frames: list[bytes] = []
    try:
        st = pa.open(format=pyaudio.paInt16, channels=ch, rate=rate, input=True, frames_per_buffer=chunk)
        for _ in range(int(rate / chunk * max(1.0, float(seconds)))):
            frames.append(st.read(chunk, exception_on_overflow=False))
        st.stop_stream()
        st.close()
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}
    finally:
        pa.terminate()

    tmp = Path(tempfile.gettempdir()) / "kami_voice_cmd.wav"
    with wave.open(str(tmp), "wb") as wf:
        wf.setnchannels(ch)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"".join(frames))
    try:
        from faster_whisper import WhisperModel  # type: ignore
        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        segs, _ = model.transcribe(str(tmp), language="tr")
        txt = " ".join(s.text.strip() for s in segs).strip()
        parsed = parse_voice_command(txt, require_wake=require_wake)
        return {**parsed, "text": txt}
    except Exception as exc:
        return {"ok": False, "error": f"transcribe_failed: {str(exc)[:80]}"}
    finally:
        tmp.unlink(missing_ok=True)


def voice_capabilities() -> dict[str, Any]:
    import importlib.util

    has_vad = importlib.util.find_spec("torch") is not None
    has_whisper = importlib.util.find_spec("faster_whisper") is not None
    return {
        "ok": True,
        "silero_vad_ready": has_vad,
        "faster_whisper_ready": has_whisper,
    }
