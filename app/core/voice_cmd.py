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


def parse_voice_command(text: str, *, require_wake: bool = True) -> dict[str, Any]:
    raw = (text or "").strip()
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


def voice_capabilities() -> dict[str, Any]:
    has_vad = False
    has_whisper = False
    try:
        import torch  # noqa: F401
        has_vad = True
    except Exception:
        pass
    try:
        import faster_whisper  # noqa: F401
        has_whisper = True
    except Exception:
        pass
    return {
        "ok": True,
        "silero_vad_ready": has_vad,
        "faster_whisper_ready": has_whisper,
    }
