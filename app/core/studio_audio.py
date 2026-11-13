"""Kami Studio Faz 8: Broadcast ses zinciri (-14 LUFS loudnorm, oto-ducking,
konusma netlestirme) + konusmaci ayrimi ve cift dil ASS/SRT motoru.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ---------------------------------------------------------------------------
# 1. Broadcast Ses Zinciri (-14 LUFS + Oto-Ducking + Konusma Netlestirme)
# ---------------------------------------------------------------------------

def loudnorm_filter(target_lufs: float = -14.0, true_peak: float = -1.0, lra: float = 11.0) -> str:
    # loudnorm tek geciste ornekleme hizini 192 kHz'e cikarir; yayin standardi 48 kHz'e geri al
    return f"loudnorm=I={target_lufs:.1f}:TP={true_peak:.1f}:LRA={lra:.1f},aresample=48000"


def voice_enhance_filter(strength: str = "medium") -> str:
    """ffmpeg tabanli profesyonel yayin konusma zinciri (DeepFilterNet yoksa da aninda calisir)."""
    nf = -20 if strength == "light" else (-30 if strength == "strong" else -25)
    return (
        f"highpass=f=85,afftdn=nf={nf},"
        "acompressor=threshold=-18dB:ratio=3:attack=5:release=120:makeup=2,"
        "equalizer=f=3200:t=q:w=1.2:g=2.5,"
        + loudnorm_filter()
    )


def build_ducking_filter(
    music_label: str = "0:a",
    voice_label: str = "1:a",
    out_label: str = "aout",
    threshold: float = 0.03,
    ratio: float = 6.0,
    attack: float = 15.0,
    release: float = 250.0,
) -> str:
    """Konusma varken arka plan muzigini otomatik kisan sidechaincompress filtresi."""
    return (
        f"[{voice_label}]asplit=2[sc][vmain];"
        f"[{music_label}][sc]sidechaincompress="
        f"threshold={threshold}:ratio={ratio}:attack={attack}:release={release}[mduck];"
        f"[mduck][vmain]amix=inputs=2:duration=longest:normalize=0,"
        f"{loudnorm_filter()}[{out_label}]"
    )


def enhance_audio_file(
    ffmpeg: str,
    src: str,
    out_path: str = "",
    strength: str = "medium",
) -> dict[str, Any]:
    """Ses/video dosyasinin sesini netlestirir ve -14 LUFS standardina normalize eder."""
    if not ffmpeg:
        return {"ok": False, "error": "ffmpeg bulunamadi"}
    p = Path(src)
    if not p.is_file():
        return {"ok": False, "error": "Dosya bulunamadi"}
    dst = Path(out_path) if out_path else p.with_name(f"{p.stem}_enhanced{p.suffix}")
    flt = voice_enhance_filter(strength)
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(p),
        "-c:v", "copy",
        "-af", flt,
        str(dst),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=3600, creationflags=NO_WINDOW)
    if res.returncode != 0 or not dst.exists():
        return {"ok": False, "error": (res.stderr or "Ses iyilestirme basarisiz")[:300]}
    return {"ok": True, "path": str(dst), "filter": flt}


def duck_music_with_voice(
    ffmpeg: str,
    music_path: str,
    voice_path: str,
    out_path: str,
) -> dict[str, Any]:
    """Muzik ve konusma dosyasini otomatik ducking + -14 LUFS ile miksler."""
    if not ffmpeg:
        return {"ok": False, "error": "ffmpeg bulunamadi"}
    flt = build_ducking_filter()
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-i", music_path, "-i", voice_path,
        "-filter_complex", flt,
        "-map", "[aout]",
        out_path,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=3600, creationflags=NO_WINDOW)
    if res.returncode != 0 or not Path(out_path).exists():
        return {"ok": False, "error": (res.stderr or "Oto-ducking basarisiz")[:300]}
    return {"ok": True, "path": out_path}


# ---------------------------------------------------------------------------
# 2. Konusmaci Ayrimi + Cift Dil ASS / SRT Altyazi Motoru
# ---------------------------------------------------------------------------

_SPEAKER_COLORS = [
    "&H00FFFFFF",  # Beyaz
    "&H00A6E62E",  # Zumrut (BGR)
    "&H005BA6F5",  # Kehribar (BGR)
    "&H00FA8BA7",  # Lavanta (BGR)
]


def _ass_time(sec: float) -> str:
    tot = int(round(max(0.0, float(sec)) * 100))   # santisaniye; yuvarlama saniyeyi tasir
    h, rem = divmod(tot, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _srt_time(sec: float) -> str:
    tot = int(round(max(0.0, float(sec)) * 1000))  # milisaniye; yuvarlama saniyeyi tasir
    h, rem = divmod(tot, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def assign_speakers(segments: list[dict[str, Any]], pause_split_sec: float = 1.4) -> list[dict[str, Any]]:
    """Konusmaci etiketi olmayan segmentlere duraklama/degisim bazli S1/S2 atar (Sortformer yoksa fallback)."""
    out: list[dict[str, Any]] = []
    cur_spk = 1
    prev_end = 0.0
    for i, seg in enumerate(segments):
        item = dict(seg)
        if item.get("speaker"):
            out.append(item)
            continue
        start = float(item.get("start", 0.0))
        if i > 0 and (start - prev_end) >= pause_split_sec:
            cur_spk = 2 if cur_spk == 1 else 1
        item["speaker"] = f"S{cur_spk}"
        prev_end = float(item.get("end", start))
        out.append(item)
    return out


def build_bilingual_ass(
    segments: list[dict[str, Any]],
    width: int = 1920,
    height: int = 1080,
    font_name: str = "Chakra Petch",
) -> str:
    """Konusmaci renkli + cift dilli (`text` + opsiyonel `tr`) ASS icerigi uretir."""
    speakers: list[str] = []
    for s in segments:
        sp = str(s.get("speaker") or "S1")
        if sp not in speakers:
            speakers.append(sp)
    if not speakers:
        speakers = ["S1"]

    styles = []
    for idx, sp in enumerate(_ for _ in speakers):
        col = _SPEAKER_COLORS[idx % len(_SPEAKER_COLORS)]
        styles.append(
            f"Style: {sp},{font_name},46,{col},&H000000FF,&H0009070E,&H80000000,"
            f"-1,0,0,0,100,100,0,0,1,2.4,0,2,40,40,56,1"
        )
    styles.append(
        f"Style: DualSub,{font_name},34,&H00A6E62E,&H000000FF,&H0009070E,&H80000000,"
        f"0,0,0,0,100,100,0,0,1,2.0,0,2,40,40,22,1"
    )

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 0",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        *styles,
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for seg in segments:
        st = _ass_time(float(seg.get("start", 0.0)))
        en = _ass_time(float(seg.get("end", 0.0)))
        sp = str(seg.get("speaker") or "S1")
        txt = str(seg.get("text") or "").replace("\n", "\\N")
        tr = str(seg.get("tr") or "").replace("\n", "\\N")
        if txt:
            lines.append(f"Dialogue: 1,{st},{en},{sp},{sp},0,0,0,,{txt}")
        if tr:
            lines.append(f"Dialogue: 0,{st},{en},DualSub,{sp},0,0,0,,{tr}")
    return "\n".join(lines) + "\n"


def build_bilingual_srt(segments: list[dict[str, Any]]) -> str:
    """Cift dilli SRT dosyasi uretir."""
    blocks = []
    for idx, seg in enumerate(segments, 1):
        st = _srt_time(float(seg.get("start", 0.0)))
        en = _srt_time(float(seg.get("end", 0.0)))
        txt = str(seg.get("text") or "").strip()
        tr = str(seg.get("tr") or "").strip()
        body = f"{txt}\n{tr}".strip() if tr else txt
        blocks.append(f"{idx}\n{st} --> {en}\n{body}")
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def subtitle_edit_convert(src: str, fmt: str = "ass") -> dict[str, Any]:
    """SubtitleEdit CLI kuruluysa cevirir, degilse temiz bilgi doner."""
    cli = shutil.which("SubtitleEdit") or shutil.which("SubtitleEdit.exe")
    if not cli:
        return {"ok": False, "error": "SubtitleEdit CLI bulunamadi", "installed": False}
    p = Path(src)
    if not p.is_file():
        return {"ok": False, "error": "Altyazi dosyasi bulunamadi", "installed": True}
    cmd = [cli, "/convert", str(p), fmt]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW)
    if res.returncode != 0:
        return {"ok": False, "error": (res.stderr or "SubtitleEdit hatasi")[:200], "installed": True}
    return {"ok": True, "path": str(p.with_suffix(f".{fmt.lstrip('.')}")), "installed": True}
