"""Kami Beat: vokal + beat BPM esleme, perde kaydirma ve mashup miks/master motoru."""
from __future__ import annotations

import math
import os
from pathlib import Path
import struct
import subprocess
from typing import Any

from app.core import converter

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _find_ffmpeg(ffmpeg: str = "") -> str:
    if ffmpeg:
        return ffmpeg
    from app.engines.ytdlp_engine import find_ffmpeg
    return find_ffmpeg() or ""


def analyze_bpm(audio_path: str, ffmpeg: str = "") -> float:
    """Ses dosyasindan enerji zarfi otokorelasyonu ile yaklasik BPM (65-175) tahmini yapar."""
    p = Path(audio_path)
    ff = _find_ffmpeg(ffmpeg)
    if not p.is_file() or not ff:
        return 0.0
    # Ilk 45 saniyeyi 8000 Hz mono s16le olarak oku
    r = subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-t", "45", "-i", str(p),
         "-ac", "1", "-ar", "8000", "-f", "s16le", "pipe:1"],
        capture_output=True, timeout=30, creationflags=NO_WINDOW,
    )
    raw = r.stdout or b""
    if r.returncode != 0 or len(raw) < 16000:
        return 0.0
    n_samples = len(raw) // 2
    # 200 orneklik (25ms -> 40 Hz) pencerelerde RMS enerji zarfi
    win = 200
    env: list[float] = []
    samples = struct.unpack(f"<{n_samples}h", raw[:n_samples * 2])
    for i in range(0, len(samples) - win, win):
        block = samples[i:i + win]
        env.append(math.sqrt(sum(x * x for x in block) / win))
    if len(env) < 120:
        return 0.0
    # Onset farki (pozitif enerji artislari)
    onset = [max(0.0, env[i] - env[i - 1]) for i in range(1, len(env))]
    mean_o = sum(onset) / len(onset)
    onset = [x - mean_o for x in onset]
    fps = 8000.0 / win  # 40 Hz
    min_lag = max(1, int(fps * 60.0 / 175.0))
    max_lag = min(len(onset) // 2, int(fps * 60.0 / 65.0))
    best_lag = 0
    best_score = -1.0
    for lag in range(min_lag, max_lag + 1):
        s = sum(onset[i] * onset[i + lag] for i in range(len(onset) - lag))
        if s > best_score:
            best_score = s
            best_lag = lag
    if best_lag <= 0:
        return 0.0
    bpm = 60.0 * fps / best_lag
    return round(bpm, 1)


_NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_MAJ_PROF = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
_MIN_PROF = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
_CAMELOT_MAJ = {"C": "8B", "C#": "3B", "D": "10B", "D#": "5B", "E": "12B", "F": "7B", "F#": "2B", "G": "9B", "G#": "4B", "A": "11B", "A#": "6B", "B": "1B"}
_CAMELOT_MIN = {"C": "5A", "C#": "12A", "D": "7A", "D#": "2A", "E": "9A", "F": "4A", "F#": "11A", "G": "6A", "G#": "1A", "A": "8A", "A#": "3A", "B": "10A"}


def detect_key(audio_path: str, ffmpeg: str = "") -> dict[str, str]:
    """FFmpeg PCM uzerinden Krumhansl-Schmuckler chroma korelasyonu ile muzikal ton + Camelot tahmini."""
    p = Path(audio_path)
    ff = _find_ffmpeg(ffmpeg)
    if not p.is_file() or not ff:
        return {"key": "", "camelot": ""}
    r = subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-t", "30", "-i", str(p),
         "-ac", "1", "-ar", "4000", "-f", "s16le", "pipe:1"],
        capture_output=True, timeout=25, creationflags=NO_WINDOW,
    )
    raw = r.stdout or b""
    if r.returncode != 0 or len(raw) < 8000:
        return {"key": "", "camelot": ""}
    n = min(len(raw) // 2, 4000 * 12)
    samples = struct.unpack(f"<{n}h", raw[:n * 2])
    # 12 yarim tonun orta oktav frekanslari (C3-B3 ve C4-B4) Goertzel enerjisi
    chroma = [0.0] * 12
    sr = 4000.0
    step_samples = samples[::2]  # 2000 Hz yeterli (~2.5s pencere)
    m = len(step_samples)
    for pc in range(12):
        total = 0.0
        for octave in (3, 4):
            midi = 12 * (octave + 1) + pc
            freq = 440.0 * (2.0 ** ((midi - 69) / 12.0))
            w = 2.0 * math.pi * freq / (sr / 2.0)
            cw = 2.0 * math.cos(w)
            s0 = s1 = 0.0
            for x in step_samples[:2048]:
                s2 = x + cw * s1 - s0
                s0, s1 = s1, s2
            total += max(0.0, s1 * s1 + s0 * s0 - cw * s1 * s0)
        chroma[pc] = math.sqrt(total)
    best_name, best_cam, best_score = "", "", -1e9
    for root in range(12):
        rot = [chroma[(root + i) % 12] for i in range(12)]
        maj_s = sum(rot[i] * _MAJ_PROF[i] for i in range(12))
        min_s = sum(rot[i] * _MIN_PROF[i] for i in range(12))
        if maj_s > best_score:
            best_score = maj_s
            note = _NOTES[root]
            best_name, best_cam = note, _CAMELOT_MAJ[note]
        if min_s > best_score:
            best_score = min_s
            note = _NOTES[root]
            best_name, best_cam = f"{note}m", _CAMELOT_MIN[note]
    return {"key": best_name, "camelot": best_cam}


def separate_stems(audio_path: str, out_dir: str = "", model: str = "htdemucs_ft.yaml") -> dict[str, Any]:
    """UVR5 ile 4 kanali (vokal, davul, bas, diger) ayirir."""
    p = Path(audio_path)
    if not p.is_file():
        return {"ok": False, "error": "Ses dosyası bulunamadı"}
    from app.core import aitools
    import threading
    dest = Path(out_dir) if out_dir else (p.parent / f"{p.stem}_stems")
    dest.mkdir(parents=True, exist_ok=True)
    res = aitools._run_json(
        ["app.tools.uvr_run", str(p), str(dest), model, aitools.models_dir("uvr"), "wav", "fast"],
        lambda _m: None,
        threading.Event(),
        "uvr",
    )
    if "error" in res:
        return {"ok": False, "error": str(res["error"])[:200]}
    return {"ok": True, "dir": str(dest), "files": res.get("done") or []}


def _atempo_chain(ratio: float) -> str:
    """FFmpeg atempo filtresi 0.5-2.0 sinirini zincirleyerek asar."""
    r = max(0.25, min(4.0, float(ratio)))
    parts: list[str] = []
    while r > 2.0:
        parts.append("atempo=2.0")
        r /= 2.0
    while r < 0.5:
        parts.append("atempo=0.5")
        r /= 0.5
    parts.append(f"atempo={r:.5f}")
    return ",".join(parts)


def mashup(
    vocal_path: str,
    beat_path: str,
    out_path: str = "",
    *,
    vocal_bpm: float = 0.0,
    beat_bpm: float = 0.0,
    pitch_semi: float = 0.0,
    vocal_offset: float = 0.0,
    auto_uvr: bool = False,
    matchering_ref: str = "",
    vocal_gain_db: float = 1.5,
    beat_gain_db: float = -1.5,
    ffmpeg: str = "",
    ctx: Any = None,
) -> dict[str, Any]:
    """Vokali beat BPM'ine esleyip perde kaydirma + opsiyonel UVR5 & Matchering master ile birlestirir."""
    vp, bp = Path(vocal_path), Path(beat_path)
    if not vp.is_file() or not bp.is_file():
        return {"ok": False, "error": "Vokal veya beat dosyası bulunamadı"}
    ff = _find_ffmpeg(ffmpeg)
    if not ff:
        return {"ok": False, "error": "ffmpeg bulunamadı"}

    if auto_uvr:
        if ctx:
            ctx.set(10, "UVR5 ile vokal ve beat ayrılıyor...")
        s1 = separate_stems(str(vp))
        s2 = separate_stems(str(bp))
        if s1.get("ok"):
            v_cand = next((f for f in s1["files"] if "vokal" in os.path.basename(f).lower() or "vocal" in os.path.basename(f).lower()), "")
            if v_cand:
                vp = Path(v_cand)
        if s2.get("ok"):
            b_cand = next((f for f in s2["files"] if "enstr" in os.path.basename(f).lower() or "no_vocals" in os.path.basename(f).lower()), "")
            if b_cand:
                bp = Path(b_cand)

    if ctx:
        ctx.set(35, "BPM ve ton ölçülüyor...")
    vbpm = float(vocal_bpm or 0) or analyze_bpm(str(vp), ff)
    bbpm = float(beat_bpm or 0) or analyze_bpm(str(bp), ff)
    vkey = detect_key(str(vp), ff)
    bkey = detect_key(str(bp), ff)
    ratio = (bbpm / vbpm) if (vbpm > 0 and bbpm > 0) else 1.0
    while ratio > 1.33:
        ratio /= 2.0
    while ratio < 0.75:
        ratio *= 2.0
    ratio = max(0.75, min(1.33, ratio))

    v_filters: list[str] = ["aresample=44100"]
    semi = float(pitch_semi or 0.0)
    if abs(semi) >= 0.05:
        pf = 2.0 ** (semi / 12.0)
        v_filters.append(f"asetrate=44100*{pf:.6f},aresample=44100")
        ratio = ratio / pf
    if abs(ratio - 1.0) >= 0.005:
        v_filters.append(_atempo_chain(ratio))
    off = float(vocal_offset or 0.0)
    if off > 0.01:
        ms = int(round(off * 1000))
        v_filters.append(f"adelay={ms}|{ms}")
    elif off < -0.01:
        v_filters.append(f"atrim=start={abs(off):.3f},asetpts=PTS-STARTPTS")
    v_filters.append(f"volume={float(vocal_gain_db):+.1f}dB")

    b_filters = [f"aresample=44100,volume={float(beat_gain_db):+.1f}dB"]
    out = Path(out_path) if out_path else converter.out_path(str(vp), "mp3", tag="mashup")
    fc = (
        f"[0:a]{','.join(v_filters)}[v];"
        f"[1:a]{','.join(b_filters)}[b];"
        "[v][b]amix=inputs=2:duration=longest:dropout_transition=2,"
        "loudnorm=I=-14:TP=-1.0:LRA=11[out]"
    )
    acodec = converter.AUDIO_ARGS.get(out.suffix.lstrip(".").lower(), ["-c:a", "libmp3lame", "-q:a", "0"])
    cmd = [ff, "-hide_banner", "-loglevel", "error", "-y",
           "-i", str(vp), "-i", str(bp), "-filter_complex", fc, "-map", "[out]", *acodec, str(out)]
    if ctx:
        ctx.set(60, "Mashup miksleniyor...")
        r = ctx.run_proc(cmd, timeout=300)
    else:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=300, creationflags=NO_WINDOW)
    if r.returncode != 0:
        out.unlink(missing_ok=True)
        return {"ok": False, "error": (r.stderr or "Mashup oluşturulamadı")[:200]}

    mastered = False
    if matchering_ref and Path(matchering_ref).is_file():
        try:
            import matchering as mg
            if ctx:
                ctx.set(85, "Matchering ile master alınıyor...")
            m_out = out.with_name(f"{out.stem}_master{out.suffix}")
            mg.process(target=str(out), reference=str(matchering_ref), results=[mg.pcm24(str(m_out))])
            if m_out.is_file():
                out = m_out
                mastered = True
        except Exception:
            pass

    return {
        "ok": True, "out": str(out), "mastered": mastered,
        "vocal_bpm": vbpm, "beat_bpm": bbpm,
        "vocal_key": vkey, "beat_key": bkey,
        "ratio": round(bbpm / vbpm, 3) if (vbpm > 0 and bbpm > 0) else 1.0,
    }


def _first_onset_sec(audio_path: str, ffmpeg: str = "") -> float:
    """Ilk belirgin enerji baslangicini (saniye) bulur; beatgrid buna hizalanir."""
    ff = _find_ffmpeg(ffmpeg)
    if not ff:
        return 0.0
    try:
        r = subprocess.run(
            [ff, "-v", "error", "-t", "5", "-i", str(audio_path), "-ac", "1", "-ar", "4000", "-f", "s16le", "pipe:1"],
            capture_output=True, timeout=15, creationflags=NO_WINDOW,
        )
        raw = r.stdout or b""
        n = len(raw) // 2
        if n < 200:
            return 0.0
        samples = struct.unpack(f"<{n}h", raw[:n * 2])
        win = 200  # 50 ms
        energies = [sum(abs(s) for s in samples[i:i + win]) / win for i in range(0, n - win, win)]
        peak = max(energies) if energies else 0.0
        thresh = peak * 0.35
        for idx, e in enumerate(energies):
            if e >= thresh:
                return round(idx * 0.05, 3)
    except Exception:
        pass
    return 0.0


def build_beatgrid(audio_path: str, duration: float = 0.0, ffmpeg: str = "") -> dict[str, Any]:
    """BPM, tonalite, ilk vurusa hizali beat/downbeat zaman damgalari ve akor haritasi uretir."""
    p = Path(audio_path)
    if not p.is_file():
        return {"ok": False, "error": "Ses dosyasi bulunamadi"}
    bpm = analyze_bpm(str(p), ffmpeg=ffmpeg) or 120.0
    key_info = detect_key(str(p), ffmpeg=ffmpeg)
    dur = duration if duration > 0 else 180.0
    step = 60.0 / bpm
    offset = _first_onset_sec(str(p), ffmpeg=ffmpeg)
    beats: list[float] = []
    downbeats: list[float] = []
    t = offset
    idx = 0
    while t < dur and len(beats) < 2000:
        rt = round(t, 3)
        beats.append(rt)
        if idx % 4 == 0:
            downbeats.append(rt)
        t += step
        idx += 1

    root = key_info.get("key") or "C"
    scale = key_info.get("scale") or "major"
    chords = [
        {"bar": i + 1, "start": db, "chord": f"{root} {scale}".strip()}
        for i, db in enumerate(downbeats)
    ]
    return {
        "ok": True,
        "bpm": bpm,
        "offset_sec": offset,
        "key": key_info,
        "beats": beats,
        "downbeats": downbeats,
        "chords": chords,
    }


def word_sync_lyrics(lrc_text: str, duration: float = 0.0) -> list[dict[str, Any]]:
    """Enhanced LRC (<mm:ss.xx>) varsa kelime zamanlarini korur; yoksa satiri esit boler."""
    import re
    rows: list[tuple[float, str]] = []
    for ln in (lrc_text or "").splitlines():
        m = re.match(r"^\s*\[(\d{1,2}):(\d{2}(?:\.\d{1,3})?)\]\s*(.+)$", ln)
        if m:
            sec = int(m.group(1)) * 60 + float(m.group(2))
            txt = m.group(3).strip()
            if txt:
                rows.append((sec, txt))
    rows.sort(key=lambda x: x[0])
    out: list[dict[str, Any]] = []
    wt_re = re.compile(r"<(\d{1,2}):(\d{2}(?:\.\d{1,3})?)>\s*([^<\s]+)")
    for i, (start, raw_txt) in enumerate(rows):
        end = rows[i + 1][0] if i + 1 < len(rows) else (duration if duration > start else start + 4.0)
        explicit = wt_re.findall(raw_txt)
        clean_txt = re.sub(r"<\d{1,2}:\d{2}(?:\.\d{1,3})?>", "", raw_txt).strip()
        if explicit:
            w_items = []
            for j, (mm, ss, w) in enumerate(explicit):
                ws = round(int(mm) * 60 + float(ss), 3)
                if j + 1 < len(explicit):
                    we = round(int(explicit[j + 1][0]) * 60 + float(explicit[j + 1][1]), 3)
                else:
                    we = round(end, 3)
                w_items.append({"word": w, "start": ws, "end": max(ws, we)})
            out.append({"start": round(start, 3), "end": round(end, 3), "text": clean_txt, "words": w_items})
            continue
        span = max(0.3, min(12.0, end - start))
        words = clean_txt.split()
        if not words:
            continue
        w_dur = span / len(words)
        w_items = [
            {"word": w, "start": round(start + j * w_dur, 3), "end": round(start + (j + 1) * w_dur, 3)}
            for j, w in enumerate(words)
        ]
        out.append({"start": round(start, 3), "end": round(end, 3), "text": clean_txt, "words": w_items})
    return out
