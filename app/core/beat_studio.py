"""Kami Beat Studio: cok kanalli vokal/beat miks, VST3 zinciri, Vocal Comping, Soz Defteri ve Referans A/B."""
from __future__ import annotations

import json
import logging
import math
import os
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from app import paths
from app.core import beat_clips, beat_fx, beat_transport, kami_beat

log = logging.getLogger(__name__)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

SCHEMA_VERSION = 2
_TR_VOWELS = set("aeıioöuüAEIİOÖUÜ")
RHYME_PALETTE_SIZE = 8   # 1c: soz panelindeki sonuk kafiye renkleri (beat.js RHYME_COLORS ile ayni uzunluk)

VOCAL_PRESETS: dict[str, dict[str, Any]] = {
    "clean_rap": {
        "name": "Temiz Rap (Dry & Punchy)",
        "desc": "HPF 90Hz -> Çamur kesimi -> 4:1 Kompresör -> De-Esser -> +2.5dB Hava -> Hafif Saturasyon -> Kısa Oda",
        "denoise": False,
        "fx": [
            {"type": "highpass", "cutoff_hz": 90.0},
            {"type": "peak", "cutoff_hz": 360.0, "gain_db": -2.8, "q": 1.4},
            {"type": "compressor", "threshold_db": -18.0, "ratio": 4.0, "attack_ms": 8.0, "release_ms": 85.0},
            {"type": "deesser", "freq_hz": 6800.0, "gain_db": -4.0},
            {"type": "peak", "cutoff_hz": 6200.0, "gain_db": 2.5, "q": 0.9},
            {"type": "distortion", "drive_db": 3.0},
            {"type": "reverb", "room_size": 0.18, "wet_level": 0.08, "dry_level": 0.95},
            {"type": "limiter", "threshold_db": -1.0},
        ],
    },
    "melodic_trap": {
        "name": "Melodik / Trap (Geniş & Parlak)",
        "desc": "HPF 85Hz -> Sıkı Kompresör -> De-Esser -> Parlak Hava -> Geniş Delay & Reverb",
        "denoise": False,
        "fx": [
            {"type": "highpass", "cutoff_hz": 85.0},
            {"type": "peak", "cutoff_hz": 320.0, "gain_db": -3.2, "q": 1.3},
            {"type": "compressor", "threshold_db": -20.0, "ratio": 5.0, "attack_ms": 5.0, "release_ms": 75.0},
            {"type": "deesser", "freq_hz": 7000.0, "gain_db": -4.5},
            {"type": "peak", "cutoff_hz": 7500.0, "gain_db": 3.5, "q": 0.8},
            {"type": "distortion", "drive_db": 4.0},
            {"type": "delay", "delay_seconds": 0.25, "feedback": 0.22, "mix": 0.16},
            {"type": "reverb", "room_size": 0.55, "wet_level": 0.22, "dry_level": 0.88},
            {"type": "limiter", "threshold_db": -1.0},
        ],
    },
    "lofi_emotional": {
        "name": "Lo-Fi / Duygusal",
        "desc": "Sıcak analog kesim (120Hz-9kHz) -> Yumuşak Kompresör -> Derin Reverb",
        "denoise": False,
        "fx": [
            {"type": "highpass", "cutoff_hz": 120.0},
            {"type": "lowpass", "cutoff_hz": 9000.0},
            {"type": "compressor", "threshold_db": -16.0, "ratio": 3.0, "attack_ms": 14.0, "release_ms": 120.0},
            {"type": "distortion", "drive_db": 5.0},
            {"type": "reverb", "room_size": 0.65, "wet_level": 0.28, "dry_level": 0.85},
            {"type": "limiter", "threshold_db": -1.5},
        ],
    },
    "atk_n9_cleanup": {
        "name": "ATK N9 / iPhone Ham Kayıt Temizleyici",
        "desc": "AI Gürültü Silme + Noise Gate + HPF 100Hz + De-Esser + Dengeli Kompresör",
        "denoise": True,
        "fx": [
            {"type": "noisegate", "threshold_db": -42.0, "ratio": 6.0},
            {"type": "highpass", "cutoff_hz": 100.0},
            {"type": "peak", "cutoff_hz": 400.0, "gain_db": -3.0, "q": 1.4},
            {"type": "compressor", "threshold_db": -18.0, "ratio": 3.8, "attack_ms": 10.0, "release_ms": 95.0},
            {"type": "deesser", "freq_hz": 6500.0, "gain_db": -4.0},
            {"type": "limiter", "threshold_db": -1.0},
        ],
    },
    # 1d: katman onayarlari (ana vokalden hafif farkli: double daha ince/kuru, adlib telefonumsu + delay, chant genis)
    "double_layer": {
        "name": "Double Katmanı (İnce & Sıkı)",
        "desc": "HPF 140Hz -> Sıkı Kompresör -> De-Esser -> 11 kHz Lowpass -> Az Reverb",
        "denoise": False,
        "fx": [
            {"type": "highpass", "cutoff_hz": 140.0},
            {"type": "compressor", "threshold_db": -22.0, "ratio": 6.0, "attack_ms": 4.0, "release_ms": 70.0},
            {"type": "deesser", "freq_hz": 6800.0, "gain_db": -6.0},
            {"type": "lowpass", "cutoff_hz": 11000.0},
            {"type": "reverb", "room_size": 0.2, "wet_level": 0.06, "dry_level": 0.95},
        ],
    },
    "adlib_layer": {
        "name": "Adlib Katmanı (Bant & Delay)",
        "desc": "HPF 220Hz -> 8 kHz Lowpass -> Kompresör -> Saturasyon -> Delay -> Reverb",
        "denoise": False,
        "fx": [
            {"type": "highpass", "cutoff_hz": 220.0},
            {"type": "lowpass", "cutoff_hz": 8000.0},
            {"type": "compressor", "threshold_db": -20.0, "ratio": 5.0, "attack_ms": 6.0, "release_ms": 80.0},
            {"type": "distortion", "drive_db": 5.0},
            {"type": "delay", "delay_seconds": 0.25, "feedback": 0.25, "mix": 0.2},
            {"type": "reverb", "room_size": 0.45, "wet_level": 0.18, "dry_level": 0.9},
        ],
    },
    "chant_layer": {
        "name": "Chant Katmanı (Geniş Grup)",
        "desc": "HPF 160Hz -> Kompresör -> Chorus -> Geniş Reverb",
        "denoise": False,
        "fx": [
            {"type": "highpass", "cutoff_hz": 160.0},
            {"type": "compressor", "threshold_db": -20.0, "ratio": 4.0, "attack_ms": 8.0, "release_ms": 90.0},
            {"type": "chorus", "rate_hz": 0.8, "depth": 0.2, "mix": 0.25},
            {"type": "reverb", "room_size": 0.6, "wet_level": 0.22, "dry_level": 0.85},
        ],
    },
}


def projects_dir() -> Path:
    d = paths.DATA_DIR / "beat_projects"
    d.mkdir(parents=True, exist_ok=True)
    return d


def recordings_dir() -> Path:
    d = paths.DATA_DIR / "beat_recordings"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _vst3_search_dirs() -> list[Path]:
    cands = [
        Path(r"C:\Program Files\Common Files\VST3"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Common" / "VST3",
        Path(os.environ.get("APPDATA", "")) / "VST3",
        paths.DATA_DIR / "vst3",
    ]
    return [p for p in cands if str(p).strip() and p.is_dir()]


def _guess_vst_category(name: str) -> str:
    n = name.lower()
    if any(k in n for k in ("nova", "eq", "filter", "pro-q")):
        return "EQ"
    if any(k in n for k in ("kotelnikov", "comp", "mjuc", "limiter", "de-esser", "deesser")):
        return "Dynamics"
    if any(k in n for k in ("reverb", "supermassive", "valhalla", "delay", "echo")):
        return "Space / Reverb"
    if any(k in n for k in ("graillon", "pitch", "tune", "autotune")):
        return "Pitch / Auto-Tune"
    if any(k in n for k in ("ivgi", "sat", "tube", "drive", "distort")):
        return "Saturation"
    if any(k in n for k in ("loudness", "meter", "youlean", "span")):
        return "Metering"
    if any(k in n for k in ("vital", "synth", "serum")):
        return "Synth"
    return "FX"


def scan_vst3() -> dict[str, Any]:
    """Sistemdeki tum VST3 eklentilerini tarar."""
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for base in _vst3_search_dirs():
        try:
            for item in base.rglob("*.vst3"):
                key = item.name.lower()
                if key in seen:
                    continue
                seen.add(key)
                found.append({
                    "name": item.stem,
                    "path": str(item),
                    "category": _guess_vst_category(item.stem),
                    "dir": str(base),
                })
        except OSError:
            continue
    found.sort(key=lambda x: (x["category"], x["name"].lower()))
    return {"ok": True, "plugins": found, "dirs": [str(d) for d in _vst3_search_dirs()]}


def count_syllables_tr(line: str) -> int:
    return sum(1 for ch in str(line or "") if ch in _TR_VOWELS)


def _rhyme_key(line: str) -> str:
    words = re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ0-9]+", str(line or "").lower())
    if not words:
        return ""
    last = words[-1]
    vowels = [c for c in last if c in _TR_VOWELS]
    tail = last[-3:] if len(last) >= 3 else last
    vtail = "".join(vowels[-2:]) if vowels else ""
    return f"{vtail}:{tail[-2:]}" if vtail else tail


def analyze_lyrics_bars(text: str, bpm: float = 0.0) -> dict[str, Any]:
    """Soz Defteri: satir bazli hece sayimi, kafiye grubu renk etiketi ve bar tahmini."""
    from app.core import beat_lyrics
    lines = str(text or "").splitlines()
    rhyme_counts: dict[str, int] = {}
    keys: list[str] = []
    heads = [beat_lyrics.header_name(ln) if beat_lyrics._HEADER_RE.match(ln) else None for ln in lines]
    for i, ln in enumerate(lines):
        rk = "" if heads[i] is not None else _rhyme_key(ln)   # 1c: [Nakarat] gibi basliklar kafiye/heceye girmez
        keys.append(rk)
        if rk:
            rhyme_counts[rk] = rhyme_counts.get(rk, 0) + 1

    group_ids: dict[str, int] = {}
    next_gid = 1
    out: list[dict[str, Any]] = []
    bar_sec = (240.0 / bpm) if bpm and bpm > 0 else 0.0
    n_sung = 0
    for idx, ln in enumerate(lines):
        is_head = heads[idx] is not None
        syl = 0 if is_head else count_syllables_tr(ln)
        rk = keys[idx]
        gid = 0
        if rk and rhyme_counts.get(rk, 0) >= 2:
            if rk not in group_ids:
                group_ids[rk] = next_gid
                next_gid += 1
            gid = group_ids[rk]
        out.append({
            "line": idx + 1,
            "text": ln,
            "syllables": syl,
            "rhyme_group": gid,
            "rhyme_key": rk if gid else "",
            "bar_seconds": round(bar_sec, 2) if bar_sec else 0.0,
            # 1c: renk paleti indeksi (RHYME_PALETTE_SIZE renk, ayni kafiye anahtari = ayni renk), baslik, soz sirasi
            "color": ((gid - 1) % RHYME_PALETTE_SIZE) if gid else -1,
            "header": heads[idx] or "",
            "kind": "header" if is_head else ("line" if ln.strip() else "blank"),
            "n": (n_sung if (not is_head and ln.strip()) else -1),
        })
        if not is_head and ln.strip():
            n_sung += 1
    total_syl = sum(x["syllables"] for x in out)
    non_empty = sum(1 for x in out if x["kind"] == "line")
    return {
        "ok": True,
        "lines": out,
        "total_lines": non_empty,
        "total_syllables": total_syl,
        "rhyme_groups": len(group_ids),
    }


def _read_audio_np(path: str, target_sr: int = 48000):
    import numpy as np
    try:
        import soundfile as sf
        data, sr = sf.read(path, dtype="float32", always_2d=True)
        if sr != target_sr:   # v2.5.3: scipy pakette yok (kami.spec EXCLUDES) -> ornekleme donusumu ffmpeg ile
            raise ValueError("resample_via_ffmpeg")
        if data.shape[1] == 1:
            data = np.repeat(data, 2, axis=1)
        elif data.shape[1] > 2:
            data = data[:, :2]
        return data, target_sr
    except Exception:
        ff = kami_beat._find_ffmpeg()
        if not ff:
            raise
        r = subprocess.run(
            [ff, "-hide_banner", "-loglevel", "error", "-i", path,
             "-ac", "2", "-ar", str(target_sr), "-f", "f32le", "pipe:1"],
            capture_output=True, timeout=90, creationflags=NO_WINDOW,
        )
        if r.returncode != 0 or not r.stdout:
            raise RuntimeError("audio_decode_failed")
        arr = np.frombuffer(r.stdout, dtype="<f4")
        arr = arr[: (len(arr) // 2) * 2].reshape(-1, 2).copy()
        return arr, target_sr


def _write_wav_np(path: str, audio, sr: int = 48000) -> None:
    import numpy as np
    arr = np.clip(audio, -1.0, 1.0).astype("float32")
    try:
        import soundfile as sf
        sf.write(path, arr, sr, subtype="PCM_24")
    except Exception:
        ff = kami_beat._find_ffmpeg()
        if not ff:
            raise
        p = subprocess.run(
            [ff, "-y", "-hide_banner", "-loglevel", "error",
             "-f", "f32le", "-ar", str(sr), "-ac", "2", "-i", "pipe:0", path],
            input=arr.tobytes(), capture_output=True, timeout=90, creationflags=NO_WINDOW,
        )
        if p.returncode != 0:
            raise RuntimeError("audio_encode_failed")


def _ebur128(path: str) -> dict[str, Any] | None:
    """v2.5.3: Gercek EBU R128 olcumu (K-agirlikli, kapili Integrated LUFS + True Peak) - ffmpeg ebur128 filtresi."""
    ff = kami_beat._find_ffmpeg()
    if not ff:
        return None
    try:
        r = subprocess.run([ff, "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
                           capture_output=True, timeout=180, creationflags=NO_WINDOW)
        from app.core.studio_finish import parse_ebur128
        res = parse_ebur128(r.stderr.decode("utf-8", errors="replace"))
        return res if res.get("i") is not None else None
    except Exception:
        log.debug("ebur128 olcumu basarisiz", exc_info=True)
        return None


def _ffmpeg_denoise(data, sr: int):
    import numpy as np
    ff = kami_beat._find_ffmpeg()
    if not ff:
        log.warning("Beat: ffmpeg yok, gurultu temizleme atlandi")
        return data
    arr = np.ascontiguousarray(data, dtype="<f4")
    try:
        r = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-f", "f32le", "-ar", str(sr), "-ac", "2", "-i", "pipe:0",
                            "-af", "highpass=f=70,afftdn=nr=14:nf=-40:tn=1", "-f", "f32le", "-ar", str(sr), "-ac", "2", "pipe:1"],
                           input=arr.tobytes(), capture_output=True, timeout=300, creationflags=NO_WINDOW)
        if r.returncode != 0 or not r.stdout:
            raise RuntimeError(r.stderr.decode("utf-8", errors="replace")[:200])
        out = np.frombuffer(r.stdout, dtype="<f4")
        return out[: (len(out) // 2) * 2].reshape(-1, 2).copy()
    except Exception:
        log.warning("Beat: gurultu temizleme basarisiz, atlandi", exc_info=True)
        return data


def measure_lufs(path: str) -> dict[str, Any]:
    """Integrated LUFS + True Peak (dBTP). ffmpeg yoksa RMS tabanli kaba tahmine duser (approx=True)."""
    import numpy as np
    if not path or not os.path.isfile(path):
        return {"ok": False, "error": "file_not_found"}
    eb = _ebur128(path)
    if eb:
        dur = 0.0
        try:
            dur = float(eb["mom"][-1][0]) if eb.get("mom") else 0.0
        except Exception:
            dur = 0.0
        if dur <= 0:
            try:
                data, _ = _read_audio_np(path, 48000)
                dur = len(data) / 48000.0
            except Exception:
                dur = 0.0
        return {"ok": True, "lufs": round(float(eb["i"]), 2), "lra": eb.get("lra"),
                "peak_db": round(float(eb["tp"]), 2) if eb.get("tp") is not None else None,
                "duration": round(dur, 2), "approx": False}
    try:
        data, _ = _read_audio_np(path, 48000)
        if data.size == 0:
            return {"ok": False, "error": "empty_audio"}
        rms = float(np.sqrt(np.mean(data ** 2)))
        peak = float(np.max(np.abs(data)))
        lufs = 20.0 * math.log10(max(rms, 1e-7)) - 0.691
        peak_db = 20.0 * math.log10(max(peak, 1e-7))
        return {"ok": True, "lufs": round(lufs, 2), "peak_db": round(peak_db, 2), "duration": round(len(data) / 48000.0, 2), "approx": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}


PEAK_RATE = 256          # temel tepe cozunurlugu (tepe/sn); 8192 Hz mono cozumde 32 ornek = 1 tepe
_PEAK_SR = 8192
_PEAK_CACHE: dict[tuple[str, float, int], tuple[Any, float]] = {}
_PEAK_CACHE_MAX = 8


def _peak_base(path: str):
    """(tepeler[float32, PEAK_RATE/sn, 0..1 mutlak], sure_sn). Bellekte LRU; 1 saatlik dosya ~3.7 MB.
    ffmpeg ile akis halinde cozulur (tum dosya bellege alinmaz)."""
    import numpy as np
    st = os.stat(path)
    key = (os.path.abspath(path), st.st_mtime, st.st_size)
    hit = _PEAK_CACHE.pop(key, None)
    if hit is not None:
        _PEAK_CACHE[key] = hit
        return hit
    step = _PEAK_SR // PEAK_RATE
    peaks_parts = []
    n_samples = 0
    ff = kami_beat._find_ffmpeg()
    if ff:
        proc = subprocess.Popen([ff, "-hide_banner", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", str(_PEAK_SR),
                                 "-f", "f32le", "pipe:1"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                creationflags=NO_WINDOW)
        rest = np.zeros(0, dtype="<f4")
        try:
            while True:
                chunk = proc.stdout.read(step * 4 * 8192)
                if not chunk:
                    break
                arr = np.frombuffer(chunk[: len(chunk) // 4 * 4], dtype="<f4")
                arr = np.concatenate([rest, arr]) if len(rest) else arr
                full = len(arr) // step * step
                if full:
                    peaks_parts.append(np.abs(arr[:full]).reshape(-1, step).max(axis=1))
                rest = arr[full:].copy()
                n_samples += full
            if len(rest):
                peaks_parts.append(np.array([np.abs(rest).max()], dtype="<f4"))
                n_samples += len(rest)
        finally:
            proc.stdout.close()
            proc.wait(timeout=30)
        dur = n_samples / float(_PEAK_SR)
    else:
        import soundfile as sf
        data, sr = sf.read(path, dtype="float32", always_2d=True)
        mono = np.abs(data).mean(axis=1)
        bounds = np.unique((np.arange(0, int(len(mono) * PEAK_RATE / sr) + 1) * sr / PEAK_RATE).astype(int))
        bounds = bounds[bounds < len(mono)]
        if len(bounds):
            peaks_parts.append(np.maximum.reduceat(mono, bounds))
        dur = len(mono) / float(sr)
    peaks = np.concatenate(peaks_parts).astype("float32") if peaks_parts else np.zeros(0, dtype="float32")
    res = (peaks, dur)
    _PEAK_CACHE[key] = res
    while len(_PEAK_CACHE) > _PEAK_CACHE_MAX:
        _PEAK_CACHE.pop(next(iter(_PEAK_CACHE)))
    return res


def waveform_peaks(path: str, buckets: int = 160) -> dict[str, Any]:
    """Arayuzde dalga formu cizimi icin normalize tepe degerleri (0..1) uretir."""
    import numpy as np
    if not path or not os.path.isfile(path):
        return {"ok": False, "peaks": []}
    try:
        base, dur = _peak_base(path)
        if len(base) == 0:
            return {"ok": True, "peaks": [], "duration": 0.0}
        buckets = max(16, min(int(buckets or 160), 200000))
        edges = np.linspace(0, len(base), min(buckets, len(base)) + 1).astype(int)
        edges = np.unique(edges[:-1])
        pk = np.maximum.reduceat(base, edges)
        mx = float(pk.max()) if len(pk) else 0.0
        if mx > 0:
            pk = pk / mx
        return {"ok": True, "peaks": [round(float(x), 3) for x in pk], "duration": round(dur, 3)}
    except Exception as exc:
        return {"ok": False, "peaks": [], "error": str(exc)[:120]}


def waveform_tile(path: str, rate: int = 64, index: int = 0, size: int = 2048) -> dict[str, Any]:
    """Zaman cizelgesi icin karo: `rate` tepe/sn cozunurlukte `index`. karo (size tepe).
    Degerler dosyanin genel tepesine gore normalize (karolar birbiriyle tutarli). Yalniz gorunen karolar istenir."""
    import numpy as np
    if not path or not os.path.isfile(path):
        return {"ok": False, "peaks": [], "error": "file_not_found"}
    try:
        rate = int(rate)
        if rate < 1 or rate > PEAK_RATE or (PEAK_RATE % rate):
            return {"ok": False, "peaks": [], "error": "bad_rate"}
        size = max(64, min(int(size or 2048), 8192))
        base, dur = _peak_base(path)
        gmax = float(base.max()) if len(base) else 0.0
        f = PEAK_RATE // rate
        a = int(index) * size * f
        seg = base[a: a + size * f]
        if len(seg) == 0:
            return {"ok": True, "peaks": [], "duration": round(dur, 3), "rate": rate, "index": int(index)}
        pad = (-len(seg)) % f
        if pad:
            seg = np.concatenate([seg, np.zeros(pad, dtype=seg.dtype)])
        pk = seg.reshape(-1, f).max(axis=1)
        if gmax > 0:
            pk = pk / gmax
        return {"ok": True, "peaks": [round(float(x), 3) for x in pk], "duration": round(dur, 3),
                "rate": rate, "index": int(index)}
    except Exception as exc:
        return {"ok": False, "peaks": [], "error": str(exc)[:120]}


def apply_fx_chain(in_path: str, out_path: str, fx_list: list[dict[str, Any]], use_denoise: bool = False) -> dict[str, Any]:
    """Ses dosyasina gurultu temizleme + pedalboard DSP + VST3 eklenti zinciri uygular (R4: beat_fx.process;
    pedalboard yoksa zarif yedek: yalniz birebir yapilabilen efektler, digerleri atlanir)."""
    if not in_path or not os.path.isfile(in_path):
        return {"ok": False, "error": "input_not_found"}
    try:
        data, sr = _read_audio_np(in_path, 48000)
        processed, info = beat_fx.process(data, sr, fx_list, denoise=use_denoise, denoise_fn=_ffmpeg_denoise)
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        _write_wav_np(out_path, processed, sr)
        return {"ok": True, "path": out_path, "fx_count": info["applied"], "engine": info["engine"],
                "skipped": info["skipped"]}
    except Exception as exc:
        log.exception("apply_fx_chain hatasi")
        return {"ok": False, "error": str(exc)[:160]}


def _default_project(name: str = "Yeni Parça") -> dict[str, Any]:
    pid = uuid.uuid4().hex[:10]
    return {
        "id": pid,
        "name": name,
        "bpm": 120.0,
        "key": "Am",
        "lyrics": "",
        "reference_path": "",
        "last_mixdown": "",
        "updated_at": time.time(),
        "schema": SCHEMA_VERSION,
        "latency_ms": 0.0,
        "sections": [],                                      # 1c: [{id, name, start, end, bars_per_line?}]
        "lyric_times": {"bars_per_line": 1, "anchors": []},  # 1c: teleprompter; anchors=[{line, t, text}]
        "tracks": [
            {
                "id": "beat",
                "name": "Beat / Altyapı",
                "role": "beat",
                "path": "",
                "takes": [],
                "active_take": "",
                "volume_db": -1.5,
                "pan": 0.0,
                "mute": False,
                "solo": False,
                "offset_ms": 0.0,
                "latency_ms": 0.0,
                "clips": [],
                "denoise": False,
                "preset": "",
                "fx": [],
            },
            {
                "id": "vocal1",
                "name": "Ana Vokal",
                "role": "vocal",
                "path": "",
                "takes": [],
                "active_take": "",
                "volume_db": 0.0,
                "pan": 0.0,
                "mute": False,
                "solo": False,
                "offset_ms": 0.0,
                "latency_ms": 0.0,
                "clips": [],
                "denoise": False,
                "preset": "clean_rap",
                "fx": list(VOCAL_PRESETS["clean_rap"]["fx"]),
            },
            {
                "id": "adlib",
                "name": "Adlib / Back Vokal",
                "role": "vocal",
                "path": "",
                "takes": [],
                "active_take": "",
                "volume_db": -4.0,
                "pan": 0.15,
                "mute": False,
                "solo": False,
                "offset_ms": 0.0,
                "latency_ms": 0.0,
                "clips": [],
                "denoise": False,
                "preset": "melodic_trap",
                "fx": list(VOCAL_PRESETS["melodic_trap"]["fx"]),
            },
        ],
    }


def _proj_file(pid: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", str(pid or ""))
    return projects_dir() / f"{safe}.kbeat.json"


def create_project(name: str = "Yeni Parça") -> dict[str, Any]:
    p = _default_project(name or "Yeni Parça")
    save_project(p)
    return {"ok": True, "project": p}


HISTORY_KEEP = 10


def _history_dir(pid: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", str(pid or ""))
    return projects_dir() / f"{safe}.history"


def _atomic_write(fp: Path, text: str) -> None:
    tmp = fp.with_name(fp.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass
    os.replace(tmp, fp)


def save_project(proj: dict[str, Any]) -> dict[str, Any]:
    """Atomik kayit (.tmp + os.replace) + son HISTORY_KEEP kaydin doner tamponu (<id>.history/)."""
    pid = str(proj.get("id") or "")
    if not pid:
        return {"ok": False, "error": "missing_id"}
    proj["updated_at"] = time.time()
    fp = _proj_file(pid)
    fp.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(proj, ensure_ascii=False, indent=2)
    _atomic_write(fp, text)
    try:
        hd = _history_dir(pid)
        hd.mkdir(parents=True, exist_ok=True)
        _atomic_write(hd / f"{time.time_ns():020d}.json", text)
        snaps = sorted(hd.glob("*.json"))
        for old in snaps[:-HISTORY_KEEP]:
            old.unlink(missing_ok=True)
    except OSError:
        log.debug("Beat: history yazilamadi", exc_info=True)
    return {"ok": True, "path": str(fp)}


def audio_duration(path: str) -> float:
    """Ses dosyasinin suresi (sn). Bulunamazsa/okunamazsa 0."""
    if not path or not os.path.isfile(path):
        return 0.0
    try:
        import soundfile as sf
        info = sf.info(path)
        if info.frames and info.samplerate:
            return float(info.frames) / float(info.samplerate)
    except Exception:
        pass
    try:
        data, sr = _read_audio_np(path, 8000)
        return len(data) / float(sr)
    except Exception:
        return 0.0


def _new_clip_for(path: str, take_id: str, start: float, duration: float) -> dict[str, Any] | None:
    """start negatifse (gecikme telafisi / v1 negatif offset) basi kirpilir: src_in = -start, start = 0."""
    if duration <= 0:
        return None
    src_in = 0.0
    if start < 0:
        src_in = -start
        start = 0.0
    if duration - src_in < beat_clips.MIN_LEN:
        return None
    return beat_clips.normalize({
        "id": "c_" + uuid.uuid4().hex[:8], "take_id": take_id, "path": path,
        "src_in": src_in, "src_out": duration, "start": start, "src_len": duration,
        "gain_db": 0.0, "fade_in": 0.0, "fade_out": 0.0, "muted": False,
    })


def migrate_project(proj: dict[str, Any]) -> bool:
    """v1 -> v2 (klip tabanli). Yerinde degistirir; bir sey degistiyse True. Idempotent."""
    changed = False
    for tr in proj.get("tracks", []) or []:
        if "latency_ms" not in tr:
            tr["latency_ms"] = 0.0
            changed = True
        if isinstance(tr.get("clips"), list):
            continue
        clips: list[dict[str, Any]] = []
        path = str(tr.get("path") or "")
        take_id = str(tr.get("active_take") or "")
        if not path and take_id:
            tk = next((t for t in tr.get("takes", []) or [] if t.get("id") == take_id), None)
            path = str((tk or {}).get("path") or "")
        if path:
            if not take_id or not any(t.get("id") == take_id and t.get("path") == path for t in tr.get("takes", []) or []):
                take_id = next((str(t.get("id")) for t in tr.get("takes", []) or [] if t.get("path") == path), take_id)
            start = float(tr.get("offset_ms") or 0.0) / 1000.0
            c = _new_clip_for(path, take_id, start, audio_duration(path))
            if c:
                clips.append(c)
        tr["clips"] = clips
        tr["offset_ms"] = 0.0
        changed = True
    if proj.get("schema") != SCHEMA_VERSION:
        proj["schema"] = SCHEMA_VERSION
        changed = True
    if "latency_ms" not in proj:
        proj["latency_ms"] = 0.0
        changed = True
    if not isinstance(proj.get("sections"), list):        # 1c: bolum haritasi
        proj["sections"] = []
        changed = True
    lt = proj.get("lyric_times")
    if not isinstance(lt, dict) or not isinstance(lt.get("anchors"), list):
        proj["lyric_times"] = {"bars_per_line": (lt or {}).get("bars_per_line", 1) if isinstance(lt, dict) else 1,
                               "anchors": []}
        if isinstance(lt, dict) and lt.get("start") is not None:
            proj["lyric_times"]["start"] = lt.get("start")
        changed = True
    lt = proj["lyric_times"]
    if "start" in lt:                                    # R3: sozlerin baslangic noktasi (sn) ya da None
        st = lt.get("start")
        try:
            stf = float(st) if st is not None else None
        except (TypeError, ValueError):
            stf = None
        if stf is not None and not (math.isfinite(stf) and stf >= 0):
            stf = None
        if stf is None:
            lt.pop("start", None)
            changed = True
        elif stf != st:
            lt["start"] = stf
            changed = True
    return changed


def _read_project_file(fp: Path) -> dict[str, Any]:
    data = json.loads(fp.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("tracks"), list):
        raise ValueError("bad_project")
    return data


def load_project(pid: str) -> dict[str, Any]:
    """Yukler + v2'ye goc eder. Ana dosya bozuksa en yeni saglam history kaydi (recovered=True)."""
    fp = _proj_file(pid)
    if not fp.is_file():
        return {"ok": False, "error": "not_found"}
    recovered = False
    try:
        data = _read_project_file(fp)
    except Exception as exc:
        data = None
        for snap in sorted(_history_dir(pid).glob("*.json"), reverse=True):
            try:
                data = _read_project_file(snap)
                recovered = True
                log.warning("Beat: %s bozuk, history'den kurtarildi (%s)", fp.name, snap.name)
                break
            except Exception:
                continue
        if data is None:
            return {"ok": False, "error": str(exc)[:120]}
    if migrate_project(data) or recovered:
        save_project(data)
    res: dict[str, Any] = {"ok": True, "project": data}
    if recovered:
        res["recovered"] = True
    return res


def list_projects() -> dict[str, Any]:
    out = []
    for fp in sorted(projects_dir().glob("*.kbeat.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            try:
                d = _read_project_file(fp)
            except Exception:
                # bozuk ana dosya: listeden dusurme (load_project history'den kurtarir), bilgiyi son saglam kayittan al
                pid0 = fp.name[: -len(".kbeat.json")]
                d = None
                for snap in sorted(_history_dir(pid0).glob("*.json"), reverse=True):
                    try:
                        d = _read_project_file(snap)
                        break
                    except Exception:
                        continue
                if d is None:
                    continue
            out.append({
                "id": d.get("id", fp.stem.replace(".kbeat", "")),
                "name": d.get("name", "Adsız"),
                "bpm": d.get("bpm", 0),
                "key": d.get("key", ""),
                "updated_at": d.get("updated_at", fp.stat().st_mtime),
            })
        except Exception:
            continue
    return {"ok": True, "projects": out}


def add_take_to_track(pid: str, track_id: str, audio_path: str, label: str = "",
                      start: float | None = None, from_recording: bool = False) -> dict[str, Any]:
    """Take ekler + onu kapsayan yeni klip (start verilmezse: kanal bossa 0, degilse son klibin bitisi).
    from_recording=True ise proje + kanal latency_ms kadar sola kaydirilir."""
    loaded = load_project(pid)
    if not loaded.get("ok"):
        return loaded
    proj = loaded["project"]
    for tr in proj.get("tracks", []):
        if tr.get("id") == track_id:
            tid = f"take_{uuid.uuid4().hex[:6]}"
            take = {
                "id": tid,
                "label": label or f"Take {len(tr.get('takes', [])) + 1}",
                "path": audio_path,
                "created_at": time.time(),
            }
            tr.setdefault("takes", []).append(take)
            tr["active_take"] = tid
            tr["path"] = audio_path   # geriye uyum (v1 okuyuculari, beat_mcp)
            clips = tr.setdefault("clips", [])
            pos = beat_clips.track_end(clips) if start is None or float(start) < 0 else float(start)
            if from_recording:
                pos -= _recording_latency_s(proj, tr)
            clip = _new_clip_for(audio_path, tid, pos, audio_duration(audio_path))
            if clip:
                clips.append(clip)
            if tr.get("role") == "beat" and os.path.isfile(audio_path):
                bpm = kami_beat.analyze_bpm(audio_path)
                kinfo = kami_beat.detect_key(audio_path)
                if bpm:
                    proj["bpm"] = bpm
                if kinfo.get("key"):
                    proj["key"] = kinfo["key"]
            save_project(proj)
            return {"ok": True, "project": proj, "take": take, "clip": clip}
    return {"ok": False, "error": "track_not_found"}


def render_track_clips(clips: list[dict[str, Any]], sr: int = 48000, cache: dict[str, Any] | None = None):
    """Klipleri kaynaktan kesip (src_in..src_out) gain + dogrusal fade uygular ve start konumuna yerlestirir.
    Ham dosyalar yalniz okunur. Dondurur: (N,2) float32 dizi (bos kanal -> 0 uzunluk)."""
    import numpy as np
    cache = {} if cache is None else cache
    parts = []
    total = 0
    for raw in beat_clips.stack_view(list(clips or [])):   # 1b: destede yalniz aktif take duyulur
        c = beat_clips.normalize(raw)
        if c.get("muted") or not c["path"]:
            continue
        src = cache.get(c["path"])
        if src is None:
            if not os.path.isfile(c["path"]):
                continue
            try:
                src, _ = _read_audio_np(c["path"], sr)
            except Exception:
                log.warning("Beat: klip kaynagi okunamadi: %s", c["path"], exc_info=True)
                continue
            cache[c["path"]] = src
        a = int(round(c["src_in"] * sr))
        b = min(int(round(c["src_out"] * sr)), len(src))
        if b <= a:
            continue
        seg = src[a:b].astype("float32", copy=True)
        n = len(seg)
        g = 10.0 ** (float(c.get("gain_db") or 0.0) / 20.0)
        env = np.full(n, g, dtype="float32")
        fi = min(n, int(round(c["fade_in"] * sr)))
        fo = min(n - fi, int(round(c["fade_out"] * sr)))
        if fi > 0:
            env[:fi] *= np.linspace(0.0, 1.0, fi, endpoint=False, dtype="float32")
        if fo > 0:
            env[n - fo:] *= np.linspace(1.0, 0.0, fo, endpoint=True, dtype="float32")
        seg *= env[:, None]
        off = int(round(c["start"] * sr))
        parts.append((off, seg))
        total = max(total, off + n)
    out = np.zeros((total, 2), dtype="float32")
    for off, seg in parts:
        out[off:off + len(seg)] += seg
    return out


# ---------------- Revize 4: tek kaynak kanal render'i (bounce + efektli onizleme) ----------------
PREVIEW_PREROLL = 1.0            # sn: pencereli render'da durumlu efektler (kompresor/reverb) isinsin diye on-isleme
PREVIEW_MAX_BYTES = 500 * 1024 * 1024
PREVIEW_MAX_DUR = 120.0


def _clip_env(c: dict[str, Any], n: int, sr: int):
    """Klip zarfi (gain + dogrusal fade), render_track_clips ile birebir ayni."""
    import numpy as np
    g = 10.0 ** (float(c.get("gain_db") or 0.0) / 20.0)
    env = np.full(n, g, dtype="float32")
    fi = min(n, int(round(c["fade_in"] * sr)))
    fo = min(n - fi, int(round(c["fade_out"] * sr)))
    if fi > 0:
        env[:fi] *= np.linspace(0.0, 1.0, fi, endpoint=False, dtype="float32")
    if fo > 0:
        env[n - fo:] *= np.linspace(1.0, 0.0, fo, endpoint=True, dtype="float32")
    return env


def track_has_fx(tr: dict[str, Any], t0: float = 0.0, t1: float | None = None) -> bool:
    """Kanalda (ya da [t0, t1) araligindaki kliplerde) duyulan bir efekt var mi."""
    if beat_fx.active_fx(tr.get("fx")) or tr.get("denoise"):
        return True
    for raw in beat_clips.stack_view(list(tr.get("clips") or [])):
        s, e = beat_clips.clip_bounds(raw)
        if e <= t0 or (t1 is not None and s >= t1) or raw.get("muted"):
            continue
        if beat_fx.active_fx(raw.get("fx")):
            return True
    return False


def render_track_audio(tr: dict[str, Any], sr: int = 48000, cache: dict[str, Any] | None = None,
                       t0: float = 0.0, t1: float | None = None, preroll: float | None = None,
                       info: dict[str, Any] | None = None):
    """Kanalin TEK render yolu (bounce ve efektli onizleme ayni fonksiyonu kullanir -> ayni duyulur).
    Sira: klip kaynagi -> klip fx (klibin kendi zinciri) -> klip zarfi (gain + fade) -> klipler toplanir
    -> kanal fx (+ denoise; 'skip_track_fx' klipler bu adimi atlar) . Ses seviyesi/pan/master cagiranda.
    Pencere [t0, t1): t1 None ise kanalin sonuna kadar. Pencereli render'da efektler pencereden `preroll`
    sn once baslatilip kirpilir (durumlu efektler isinsin). Dondurur: (N,2) float32, N = pencere uzunlugu."""
    import numpy as np
    cache = {} if cache is None else cache
    info = {} if info is None else info
    info.setdefault("skipped", [])
    info.setdefault("engine", "none")
    windowed = t0 > 0 or t1 is not None
    pre = int(round((PREVIEW_PREROLL if preroll is None else max(0.0, float(preroll))) * sr)) if windowed else 0
    w0 = max(0, int(round(max(0.0, float(t0)) * sr)))
    p0 = max(0, w0 - pre)
    w1 = None if t1 is None else max(w0, int(round(float(t1) * sr)))
    items = []
    for raw in beat_clips.stack_view(list(tr.get("clips") or [])):   # 1b: destede yalniz aktif take duyulur
        c = beat_clips.normalize(raw)
        if c.get("muted") or not c["path"]:
            continue
        src = cache.get(c["path"])
        if src is None:
            if not os.path.isfile(c["path"]):
                continue
            try:
                src, _ = _read_audio_np(c["path"], sr)
            except Exception:
                log.warning("Beat: klip kaynagi okunamadi: %s", c["path"], exc_info=True)
                continue
            cache[c["path"]] = src
        a = int(round(c["src_in"] * sr))
        b = min(int(round(c["src_out"] * sr)), len(src))
        if b <= a:
            continue
        items.append((c, src, a, b - a, int(round(c["start"] * sr))))
    end = max([off + n for _, _, _, n, off in items] or [0])
    if w1 is None:
        w1 = max(end, w0)
    length = w1 - p0
    through = np.zeros((max(0, length), 2), dtype="float32")
    skip = None
    for c, src, a, n, off in items:
        lo, hi = max(off, p0), min(off + n, w1)
        if hi <= lo:
            continue
        cfx = beat_fx.active_fx(c.get("fx"))
        if cfx:
            plo = max(off, lo - pre) if windowed else off
            seg = src[a + (plo - off): a + (hi - off)].astype("float32", copy=True)
            seg, ci = beat_fx.process(seg, sr, cfx)
            info["skipped"] += ci["skipped"]
            if ci["engine"] != "none":
                info["engine"] = ci["engine"]
            seg = seg[lo - plo:]
        else:
            seg = src[a + (lo - off): a + (hi - off)].astype("float32", copy=True)
        seg *= _clip_env(c, n, sr)[lo - off: hi - off, None]
        if c.get("skip_track_fx"):
            if skip is None:
                skip = np.zeros_like(through)
            skip[lo - p0: hi - p0] += seg
        else:
            through[lo - p0: hi - p0] += seg
    tfx = tr.get("fx") or []
    if (beat_fx.active_fx(tfx) or tr.get("denoise")) and len(through):
        through, ti = beat_fx.process(through, sr, tfx, denoise=bool(tr.get("denoise")), denoise_fn=_ffmpeg_denoise)
        info["skipped"] += ti["skipped"]
        if ti["engine"] != "none":
            info["engine"] = ti["engine"]
    if skip is not None:
        through = through + skip
    return np.ascontiguousarray(through[w0 - p0:], dtype="float32")


def preview_dir() -> Path:
    d = recordings_dir() / "_mix_tmp" / "preview"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _file_sig(path: str) -> list[Any]:
    try:
        st = os.stat(path)
        return [path, int(st.st_size), round(st.st_mtime, 3)]
    except OSError:
        return [path, 0, 0]


def preview_window(start: float, dur: float, clip: dict[str, Any] | None = None,
                   loop: dict[str, Any] | None = None) -> tuple[float, float]:
    """Onizleme penceresi: calma konumundan dur sn; dongu aciksa ve konum dongu icindeyse dongu bolgesi
    (konum dongu oncesindeyse konumdan dongu sonuna); klip verilirse klibin araligiyla kesisim."""
    t0 = max(0.0, float(start or 0.0))
    d = max(0.5, min(PREVIEW_MAX_DUR, float(dur or 15.0)))
    t1 = t0 + d
    if loop and loop.get("on"):
        a, b = float(loop.get("start") or 0.0), float(loop.get("end") or 0.0)
        if b - a >= 0.05 and t0 < b:
            if t0 >= a:                      # konum dongu icinde: tum dongu bolgesi (motor a..b'yi doner)
                t0 = a
            t1 = min(b, t0 + PREVIEW_MAX_DUR)
    if clip:
        s, e = beat_clips.clip_bounds(clip)
        if t1 <= s or t0 >= e:
            t0, t1 = s, min(e, s + d)
        else:
            t0, t1 = max(t0, s), min(t1, e)
    return round(t0, 6), round(max(t0 + 0.05, t1), 6)


def preview_key(tr: dict[str, Any], t0: float, t1: float, sr: int = 48000, preroll: float = PREVIEW_PREROLL) -> str:
    """Onbellek anahtari: pencereye (on-isleme dahil) dokunan kliplerin kaynak dosyasi (boyut/mtime),
    src_in/out, konum, zarf, klip fx ozeti + kanal fx zinciri ozeti + pencere."""
    import hashlib
    lo = t0 - preroll
    parts = []
    for raw in beat_clips.stack_view(list(tr.get("clips") or [])):
        c = beat_clips.normalize(raw)
        s, e = beat_clips.clip_bounds(c)
        if c.get("muted") or not c["path"] or e <= lo or s >= t1:
            continue
        parts.append([_file_sig(c["path"]), c["src_in"], c["src_out"], c["start"], c["gain_db"], c["fade_in"],
                      c["fade_out"], beat_fx.chain_hash(c.get("fx")), bool(c.get("skip_track_fx"))])
    raw_key = json.dumps({"c": parts, "fx": beat_fx.chain_hash(tr.get("fx"), bool(tr.get("denoise"))),
                          "w": [round(t0, 3), round(t1, 3)], "sr": sr, "pre": preroll}, sort_keys=True, default=str)
    return hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:20]


def prune_preview_cache(max_bytes: int = PREVIEW_MAX_BYTES, keep: str = "") -> int:
    """Onizleme onbellegi boyut siniri: en eski (mtime) dosyalar silinir. Silinen dosya sayisi."""
    d = preview_dir()
    files = []
    for f in d.glob("*.wav"):
        try:
            st = f.stat()
            files.append((st.st_mtime, st.st_size, f))
        except OSError:
            continue
    total = sum(sz for _, sz, _ in files)
    removed = 0
    for _, sz, f in sorted(files, key=lambda x: x[0]):
        if total <= max_bytes:
            break
        if f.name == keep:
            continue
        try:
            f.unlink()
            total -= sz
            removed += 1
        except OSError:
            continue
    return removed


_PREVIEW_SRC: dict[tuple, Any] = {}      # kaynak ses onbellegi (path, boyut, mtime) -> dizi; en fazla 3 dosya
_PREVIEW_SRC_MAX = 3


class _SrcCache(dict):
    """render_track_audio icin: yol -> dizi; dosya degismediyse onceki onizlemelerden yeniden kullanilir."""

    def get(self, path, default=None):
        sig = tuple(_file_sig(path))
        hit = _PREVIEW_SRC.get(sig)
        if hit is not None:
            _PREVIEW_SRC[sig] = _PREVIEW_SRC.pop(sig)     # LRU: sona al
            return hit
        return default

    def __setitem__(self, path, arr):
        sig = tuple(_file_sig(path))
        _PREVIEW_SRC[sig] = arr
        while len(_PREVIEW_SRC) > _PREVIEW_SRC_MAX:
            _PREVIEW_SRC.pop(next(iter(_PREVIEW_SRC)))


_PREVIEW_GEN: dict[tuple[str, str], int] = {}
_PREVIEW_LOCK = threading.Lock()
_PREVIEW_SEM = threading.BoundedSemaphore(2)


def preview_render(pid: str, track_id: str, start: float = 0.0, dur: float = 15.0, clip_id: str = "",
                   track: dict[str, Any] | None = None, loop: dict[str, Any] | None = None,
                   sr: int = 48000) -> dict[str, Any]:
    """Efektli onizleme: kanalin (veya klibin) penceresini bounce ile AYNI render yoluyla isleyip gecici WAV
    dondurur. track verilirse (arayuzun kaydedilmemis guncel hali) o kullanilir, yoksa projeden okunur.
    Ayni kanal icin daha yeni istek geldiyse sirada bekleyen eski istek islenmeden 'superseded' doner."""
    tr = track if isinstance(track, dict) else None
    if tr is None or loop is None:
        ld = load_project(pid) if pid else {"ok": False}
        if tr is None:
            if not ld.get("ok"):
                return ld if ld.get("error") else {"ok": False, "error": "project_not_found"}
            tr = next((t for t in ld["project"].get("tracks", []) if t.get("id") == track_id), None)
            if tr is None:
                return {"ok": False, "error": "track_not_found"}
        if loop is None and ld.get("ok"):
            loop = ld["project"].get("loop")
    clip = None
    if clip_id:
        clip = next((c for c in tr.get("clips") or [] if c.get("id") == clip_id), None)
        if clip is None:
            return {"ok": False, "error": "clip_not_found"}
    t0, t1 = preview_window(start, dur, clip, loop)
    if not track_has_fx(tr, t0 - PREVIEW_PREROLL, t1):
        return {"ok": True, "dry": True, "t0": t0, "t1": t1}
    key = preview_key(tr, t0, t1, sr)
    out = preview_dir() / f"{key}.wav"
    if out.is_file():
        try:
            os.utime(out, None)
        except OSError:
            pass
        return {"ok": True, "path": str(out), "t0": t0, "t1": t1, "sr": sr, "cached": True, "key": key}
    gk = (str(pid or ""), str(track_id or ""))
    with _PREVIEW_LOCK:
        gen = _PREVIEW_GEN.get(gk, 0) + 1
        _PREVIEW_GEN[gk] = gen
    with _PREVIEW_SEM:
        with _PREVIEW_LOCK:
            if _PREVIEW_GEN.get(gk) != gen:
                return {"ok": False, "error": "superseded"}
        tm = time.monotonic()
        info: dict[str, Any] = {}
        try:
            data = render_track_audio(tr, sr, _SrcCache(), t0, t1, PREVIEW_PREROLL, info)
            tmp = out.with_suffix(".part.wav")
            _write_wav_np(str(tmp), data, sr)
            os.replace(tmp, out)
        except Exception as exc:
            log.warning("Onizleme render hatasi", exc_info=True)
            return {"ok": False, "error": str(exc)[:160]}
    prune_preview_cache(keep=out.name)
    return {"ok": True, "path": str(out), "t0": t0, "t1": t1, "sr": sr, "cached": False, "key": key,
            "engine": info.get("engine"), "skipped": sorted(set(info.get("skipped") or [])),
            "ms": int((time.monotonic() - tm) * 1000), "fx_available": beat_fx.available()}


# Revize R2: genel (kalici) gecikme ayari. Api, settings.beat_latency_ms okuyan bir fonksiyon baglar;
# bagli degilse (testler, MCP) 0 kabul edilir.
_GLOBAL_LATENCY_GETTER = None


def set_global_latency_getter(fn) -> None:
    global _GLOBAL_LATENCY_GETTER
    _GLOBAL_LATENCY_GETTER = fn


def global_latency_ms() -> float:
    fn = _GLOBAL_LATENCY_GETTER
    if fn is None:
        return 0.0
    try:
        v = float(fn() or 0.0)
    except Exception:
        return 0.0
    return v if math.isfinite(v) else 0.0


def effective_latency(proj: dict[str, Any]) -> dict[str, Any]:
    """Projenin etkin kayit gecikmesi: proje degeri (0 degilse) > genel ayar. {'ms', 'source'}."""
    return beat_transport.effective_latency_ms(proj.get("latency_ms"), global_latency_ms())


def _recording_latency_s(proj: dict[str, Any], tr: dict[str, Any]) -> float:
    try:
        tr_ms = float(tr.get("latency_ms") or 0.0)
    except (TypeError, ValueError):
        tr_ms = 0.0
    return (float(effective_latency(proj)["ms"]) + tr_ms) / 1000.0


def _same_span(c: dict[str, Any], start: float, length: float) -> bool:
    s, e = beat_clips.clip_bounds(c)
    return abs(s - start) < 0.002 and abs((e - s) - length) < 0.002


def apply_recording(pid: str, track_id: str, audio_path: str, plan: dict[str, Any], rec_epoch0: float,
                    label: str = "PC Mic") -> dict[str, Any]:
    """Asama 1b: kayit planina gore klip(ler) yerlestirir. Ham dosya yalniz okunur (src_in/src_out ile kesilir).
    plan: {mode: linear|loop|punch, anchor_u, anchor_wall (epoch sn), keep_from, loop_a, loop_b,
           clip_id, t0, t1, xfade}
      linear: tek klip keep_from'dan (sayim sonrasi) itibaren.
      loop  : her tam tur ayri take; hepsi ayni konumda tek destede (ayni araliktaki mevcut desteye eklenir),
              son tur aktif.
      punch : hedef klip once / punch destesi / sonra olarak bolunur (beat_clips.punch_in)."""
    loaded = load_project(pid)
    if not loaded.get("ok"):
        return loaded
    proj = loaded["project"]
    tr = next((t for t in proj.get("tracks", []) if t.get("id") == track_id), None)
    if tr is None:
        return {"ok": False, "error": "track_not_found"}
    rec_len = audio_duration(audio_path)
    if rec_len <= 0:
        return {"ok": False, "error": "empty_recording"}
    mode = str(plan.get("mode") or "linear")
    u0e = beat_transport.recording_origin(plan.get("anchor_u", 0.0), plan.get("anchor_wall", rec_epoch0), rec_epoch0,
                                          _recording_latency_s(proj, tr))
    clips = list(tr.get("clips") or [])
    takes = tr.setdefault("takes", [])
    new_takes: list[dict[str, Any]] = []
    new_ids: list[str] = []

    def mk_take(lbl: str) -> dict[str, Any]:
        tk = {"id": f"take_{uuid.uuid4().hex[:6]}", "label": lbl, "path": audio_path, "created_at": time.time()}
        takes.append(tk)
        new_takes.append(tk)
        return tk

    def mk_clip(spec: dict[str, Any], take_id: str) -> dict[str, Any]:
        c = beat_clips.normalize({"id": "c_" + uuid.uuid4().hex[:8], "take_id": take_id, "path": audio_path,
                                  "src_in": spec["src_in"], "src_out": spec["src_out"], "start": spec["start"],
                                  "src_len": rec_len, "gain_db": 0.0, "fade_in": 0.0, "fade_out": 0.0, "muted": False})
        new_ids.append(c["id"])
        return c

    n_take = len(takes)
    if mode == "loop":
        a, b = float(plan.get("loop_a") or 0.0), float(plan.get("loop_b") or 0.0)
        laps = beat_transport.loop_laps(u0e, rec_len, a, b)
        if not laps:
            return {"ok": False, "error": "no_complete_lap"}
        xf = beat_clips.XFADE
        sid = ""
        for c in beat_clips.stack_view(clips):
            if _same_span(c, laps[0]["start"], laps[0]["src_out"] - laps[0]["src_in"]):
                sid = c.get("stack_id") or ""
                if not sid:                         # ayni araliktaki tek klip desteye donusur
                    sid = beat_clips.new_stack_id()
                    clips = [dict(x, stack_id=sid, stack_active=True) if x.get("id") == c.get("id") else x for x in clips]
                break
        sid = sid or beat_clips.new_stack_id()
        for lap in laps:
            n_take += 1
            tk = mk_take(f"Tur {lap['lap'] + 1} · Take {n_take}")
            c = beat_clips.set_fade(mk_clip(lap, tk["id"]), min(xf, 0.005), min(xf, 0.005))   # tur kenarinda tik olmasin
            clips = beat_clips.stack_push(clips, sid, c)
        clips = beat_clips._dissolve_singletons(clips)
    elif mode == "punch":
        cid = str(plan.get("clip_id") or "")
        if beat_clips._find(clips, cid) < 0:
            return {"ok": False, "error": "punch_clip_not_found"}
        t0, t1 = float(plan.get("t0") or 0.0), float(plan.get("t1") or 0.0)
        xf = float(plan.get("xfade", beat_clips.XFADE))
        pw = beat_transport.punch_window(u0e, rec_len, t0, t1, xf)
        if not pw:
            return {"ok": False, "error": "punch_too_short"}
        # kayit erken durdurulduysa punch araligi kaydin bittigi yere kadar
        t1 = min(t1, pw["start"] + (pw["src_out"] - pw["src_in"]) - xf / 2.0)
        tk = mk_take(f"Punch · Take {n_take + 1}")
        pc = mk_clip(pw, tk["id"])
        clips = beat_clips.punch_in(clips, cid, t0, t1, pc, xf)
    else:
        spec = beat_transport.linear_take(u0e, rec_len, float(plan.get("keep_from") or 0.0))
        if not spec:
            return {"ok": False, "error": "empty_recording"}
        tk = mk_take(f"{label} Take {n_take + 1}")
        clips.append(mk_clip(spec, tk["id"]))
    tr["clips"] = clips
    tr["active_take"] = new_takes[-1]["id"]
    tr["path"] = audio_path
    save_project(proj)
    return {"ok": True, "project": proj, "take": new_takes[-1], "takes": new_takes, "new_clip_ids": new_ids,
            "mode": mode, "u0e": u0e}


def render_mixdown(pid: str, out_path: str = "", target_lufs: float = -14.0) -> dict[str, Any]:
    """Projedeki aktif kanallari efektleriyle isleyip tek WAV/MP3 dosyasinda birlestirir."""
    import numpy as np

    loaded = load_project(pid)
    if not loaded.get("ok"):
        return loaded
    proj = loaded["project"]
    tracks = proj.get("tracks", [])
    has_solo = any(t.get("solo") for t in tracks)

    sr = 48000
    rendered_tracks: list[tuple[Any, dict[str, Any]]] = []
    max_len = 0

    tmp_dir = recordings_dir() / "_mix_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    src_cache: dict[str, Any] = {}
    fx_info: dict[str, Any] = {}

    for tr in tracks:
        if tr.get("mute") or (has_solo and not tr.get("solo")):
            continue
        fx = tr.get("fx") or []
        denoise = bool(tr.get("denoise"))
        if isinstance(tr.get("clips"), list):
            # R4: klip fx -> klipler birlestirilir -> kanal fx (onizleme ile ayni tek render yolu)
            data = render_track_audio(tr, sr, src_cache, info=fx_info)
            if not len(data):
                continue
            max_len = max(max_len, len(data))
            rendered_tracks.append((data, {"offset": 0, "tr": tr}))
            continue
        p = str(tr.get("path") or "")
        if not p or not os.path.isfile(p):
            continue
        if fx or denoise:
            proc_p = str(tmp_dir / f"{pid}_{tr['id']}.wav")
            res = apply_fx_chain(p, proc_p, fx, use_denoise=denoise)
            src_p = proc_p if res.get("ok") else p
        else:
            src_p = p
        data, _ = _read_audio_np(src_p, sr)
        offset_samples = int(round((float(tr.get("offset_ms") or 0.0) / 1000.0) * sr))
        if offset_samples < 0 and len(data) > abs(offset_samples):
            data = data[abs(offset_samples) :]
            offset_samples = 0
        elif offset_samples < 0:
            offset_samples = 0
        end_len = offset_samples + len(data)
        if end_len > max_len:
            max_len = end_len
        rendered_tracks.append((data, {"offset": offset_samples, "tr": tr}))

    if not rendered_tracks or max_len == 0:
        return {"ok": False, "error": "no_playable_tracks"}

    mix = np.zeros((max_len, 2), dtype="float32")
    for data, meta in rendered_tracks:
        tr = meta["tr"]
        off = meta["offset"]
        gain = 10.0 ** (float(tr.get("volume_db") or 0.0) / 20.0)
        pan = max(-1.0, min(1.0, float(tr.get("pan") or 0.0)))
        l_gain = gain * math.sqrt(0.5 * (1.0 - pan))
        r_gain = gain * math.sqrt(0.5 * (1.0 + pan))
        end = off + len(data)
        mix[off:end, 0] += data[:, 0] * l_gain
        mix[off:end, 1] += data[:, 1] * r_gain

    if not out_path:
        safe_name = re.sub(r'[<>:"/\\|?*]', "_", str(proj.get("name") or pid)).strip() or pid
        out_path = str(recordings_dir() / f"{safe_name}_mixdown.wav")

    # v2.5.3: Hedef LUFS dengeleme gercek EBU R128 olcumuyle (eskiden RMS-0.691 tahmini birkac dB sapiyordu),
    # ardindan -1 dBTP tepe sinirlayici (pedalboard Limiter; yoksa dogrusal tepe korumasi).
    if target_lufs < 0 and float(np.max(np.abs(mix))) > 1e-6:
        _write_wav_np(out_path, mix, sr)
        eb = _ebur128(out_path)
        if eb and eb.get("i") is not None:
            cur_lufs = float(eb["i"])
        else:
            cur_lufs = 20.0 * math.log10(max(float(np.sqrt(np.mean(mix ** 2))), 1e-7)) - 0.691
        mix *= (10.0 ** (max(-18.0, min(18.0, target_lufs - cur_lufs)) / 20.0))
    if float(np.max(np.abs(mix))) > 0.891:   # yalniz tepe -1 dBFS'i asarsa sinirlayici
        try:
            import pedalboard as pb
            mix = pb.Pedalboard([pb.Limiter(threshold_db=-1.0, release_ms=120.0)])(mix.T.astype("float32"), sr).T
            # JUCE Limiter cikisi esik kadar yukseltir; hedefe geri ayarla
            _write_wav_np(out_path, mix, sr)
            eb2 = _ebur128(out_path)
            if eb2 and eb2.get("i") is not None and target_lufs < 0:
                mix *= (10.0 ** (max(-12.0, min(0.0, target_lufs - float(eb2["i"]))) / 20.0))
        except Exception:
            log.debug("Limiter yok, dogrusal tepe korumasi", exc_info=True)
    peak = float(np.max(np.abs(mix)))
    if peak > 0.891:   # -1 dBFS
        mix *= (0.891 / peak)
    _write_wav_np(out_path, mix, sr)
    proj["last_mixdown"] = out_path
    save_project(proj)
    lufs_info = measure_lufs(out_path)
    return {"ok": True, "path": out_path, "lufs": lufs_info.get("lufs"), "peak_db": lufs_info.get("peak_db"), "duration": lufs_info.get("duration"),
            "fx_skipped": sorted(set(fx_info.get("skipped") or []))}


def bounce(pid: str, out_path: str = "", target_lufs: float = -14.0) -> dict[str, Any]:
    """Klip tabanli bounce (render_mixdown'in ince sarmalayicisi)."""
    return render_mixdown(pid, out_path=out_path, target_lufs=target_lufs)


# ---------- Alkis (tik) gecikme testi ----------
LAT_SR = 48000


# Revize R2: tek 20 ms'lik kisik tik yerine 5 tiklik, genis bantli, yuksek enerjili chirp dizisi.
# Ayni parametrelerle arayuz (Web Audio) de birebir ayni sinyali uretir: tik kullanicinin DUYDUGU cikistan calar,
# Python yalniz kaydeder (zaman eslemesi 1b'deki saat capasi ile).
LAT_PROBE = {"count": 5, "spacing": 0.5, "dur": 0.05, "f0": 300.0, "f1": 8000.0, "amp": 0.8, "ramp": 0.003,
             "at": 0.05, "tail": 0.35}


def latency_probe_signal(sr: int = LAT_SR, total_s: float | None = None, at_s: float | None = None):
    """Gecikme olcumu sinyali: LAT_PROBE['count'] adet dogrusal chirp (300 Hz -> 8 kHz, 50 ms, Tukey kenarli),
    0.5 sn arayla. Ilk chirp at_s'de baslar. total_s verilmezse son chirp'ten sonra 'tail' kadar sessizlik."""
    import numpy as np
    P = LAT_PROBE
    at = float(P["at"] if at_s is None else at_s)
    n = int(round(P["dur"] * sr))
    t = np.arange(n, dtype="float64") / sr
    k = (P["f1"] - P["f0"]) / P["dur"]
    w = np.ones(n)                                       # Tukey penceresi: 3 ms yumusak kenar, ortasi tam enerji
    r = max(1, int(round(P["ramp"] * sr)))
    ramp = 0.5 - 0.5 * np.cos(np.pi * np.arange(r) / r)
    w[:r] = ramp
    w[n - r:] = ramp[::-1]
    chirp = np.sin(2 * np.pi * (P["f0"] * t + 0.5 * k * t * t)) * w * P["amp"]
    last = at + (P["count"] - 1) * P["spacing"] + P["dur"]
    total = float(total_s) if total_s is not None else last + P["tail"]
    out = np.zeros(max(int(round(total * sr)), int(round(last * sr)) + 1), dtype="float32")
    for i in range(int(P["count"])):
        a = int(round((at + i * P["spacing"]) * sr))
        out[a:a + n] = chirp.astype("float32")
    return out


def estimate_latency(played, recorded, sr: int, expected_at: int = 0, min_ms: float = -150.0,
                     max_ms: float = 1000.0) -> dict[str, Any]:
    """Saf hesap: calinan sinyalin kayitta nerede oldugunu bulur (normalize capraz korelasyon, FFT).
    expected_at: kayitta sinyalin gecikmesiz baslamasi gereken ornek (saat capasindan). Arama penceresi
    expected_at + [min_ms, max_ms] (expected_at=0 iken yalniz >= 0). Guven: normalize tepe (NCC) ve
    tepe / medyan orani. Dondurur {"ok", "latency_ms", "confidence", "ncc", "ratio"} veya
    {"ok": False, "error": "no_signal", ["reason": "quiet"|"weak"], ...} (sessiz kayitta yalniz ilk iki anahtar)."""
    import numpy as np
    x = np.asarray(played, dtype="float64").reshape(-1)
    y = np.asarray(recorded, dtype="float64")
    if y.ndim > 1:
        y = y.mean(axis=1)
    y = y.reshape(-1)
    if len(x) == 0 or len(y) == 0 or sr <= 0:
        return {"ok": False, "error": "no_signal"}
    y = y - float(np.mean(y))
    ex = float(np.sqrt(np.sum(x * x)))
    peak_in = float(np.max(np.abs(y)))
    if ex < 1e-9 or peak_in < 1e-3:
        return {"ok": False, "error": "no_signal"}
    # sinyalin etkin (sifir olmayan) kismi: korelasyon ve enerji penceresi yalniz bu bolgede
    nz = np.nonzero(np.abs(x) > 1e-9)[0]
    x0, x1 = int(nz[0]), int(nz[-1]) + 1
    xs = x[x0:x1]
    m = len(xs)
    exp = int(expected_at) + x0                     # kayitta xs'nin baslamasi gereken ornek
    lo = exp + int(math.floor(min_ms * sr / 1000.0)) if expected_at else exp
    hi = exp + int(math.ceil(max_ms * sr / 1000.0))
    lo = max(0, lo)
    hi = min(len(y) - m, hi)
    if hi < lo:
        return {"ok": False, "error": "no_signal"}
    nfft = 1 << (len(y) + m - 1).bit_length()
    corr = np.fft.irfft(np.fft.rfft(y, nfft) * np.conj(np.fft.rfft(xs, nfft)), nfft)[: len(y) - m + 1]
    c2 = np.concatenate(([0.0], np.cumsum(y * y)))
    eseg = np.sqrt(np.maximum(c2[m:] - c2[:-m], 0.0))[: len(corr)]
    ncc = np.where(eseg > 1e-9, corr / (np.sqrt(np.sum(xs * xs)) * np.maximum(eseg, 1e-12)), 0.0)
    win = ncc[lo:hi + 1]
    j = int(np.argmax(win))
    lag = lo + j
    pk = float(ncc[lag])
    med = float(np.median(np.abs(win))) + 1e-9
    ratio = pk / med
    frac = 0.0
    if 0 < lag < len(corr) - 1:                     # parabolik ara degerleme (alt-ornek)
        a, b, c = float(corr[lag - 1]), float(corr[lag]), float(corr[lag + 1])
        den = a - 2 * b + c
        if abs(den) > 1e-12:
            frac = max(-0.5, min(0.5, 0.5 * (a - c) / den))
    conf = max(0.0, min(1.0, (ratio - 10.0) / 40.0))   # saf gurultude oran ~5-8; net tikta yuzlerce
    info = {"ncc": round(pk, 3), "ratio": round(ratio, 1), "confidence": round(conf, 3)}
    if pk < 0.02 or ratio < 11.0:
        return {"ok": False, "error": "no_signal", "reason": "weak" if peak_in >= 0.01 else "quiet", **info}
    return {"ok": True, "latency_ms": round((lag + frac - exp) * 1000.0 / sr, 2), **info}


def latency_from_recording(rec, sr: int, rec_epoch0: float, play_wall: float) -> dict[str, Any]:
    """Revize R2 (arayuzden calinan tik): Python yalniz kaydetti; tik dizisinin ilk ornegi duvar saatinde
    play_wall'da (Web Audio zamanlamasi, 1b saat capasi) calindi. Kaydin 0. ornegi rec_epoch0'da.
    Gecikme = tikin kayitta bulundugu yer - beklenen yer. Kayit yerlesimiyle ayni saatler kullanildigi icin
    sonuc dogrudan latency_ms olarak kullanilabilir."""
    import numpy as np
    y = np.asarray(rec, dtype="float64")
    if y.ndim > 1:
        y = y.mean(axis=1)
    sig = latency_probe_signal(int(sr), at_s=0.0)
    expected = int(round((float(play_wall) - float(rec_epoch0)) * sr))
    if expected < 0 or expected >= len(y):
        return {"ok": False, "error": "clock", "expected": expected}
    r = estimate_latency(sig, y, int(sr), expected_at=max(1, expected))
    r["peak"] = round(float(np.max(np.abs(y))) if len(y) else 0.0, 4)
    return r


def measure_latency(device_id: int = -1, trials: int = 2, out_device: int = -1) -> dict[str, Any]:
    """Yedek yol: tiki Python calar (out_device; -1 = Windows varsayilan cikisi) ve ayni anda kaydeder.
    Arayuz once Web Audio yolunu (kullanicinin duydugu cikis) kullanir; bu yol ikinci secenek."""
    try:
        import numpy as np
        import sounddevice as sd
    except Exception:
        return {"ok": False, "error": "sounddevice_missing"}
    sig = latency_probe_signal(LAT_SR)
    results: list[dict[str, Any]] = []
    try:
        dev_in = None if device_id is None or int(device_id) < 0 else int(device_id)
        dev_out = None if out_device is None or int(out_device) < 0 else int(out_device)
        for _ in range(max(1, int(trials))):
            rec = sd.playrec(sig.reshape(-1, 1), samplerate=LAT_SR, channels=1, dtype="float32",
                             device=(dev_in, dev_out))
            sd.wait()
            results.append(estimate_latency(sig, np.asarray(rec).reshape(-1), LAT_SR))
            time.sleep(0.15)
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:140]}
    good = [r for r in results if r.get("ok")]
    if not good:
        return {"ok": False, "error": "no_signal", "trials": results}
    vals = [float(r["latency_ms"]) for r in good]
    mean = sum(vals) / len(vals)
    spread = max(vals) - min(vals)
    conf = sum(float(r["confidence"]) for r in good) / len(good)
    conf *= len(good) / len(results)
    if spread > 5.0:   # denemeler tutarsizsa guveni dusur
        conf *= 0.5
    return {"ok": True, "latency_ms": round(mean, 1), "confidence": round(conf, 2),
            "trials": vals, "spread_ms": round(spread, 2)}


def export_to_lyric_video(pid: str, title: str = "") -> dict[str, Any]:
    """Mixdown + Soz Defteri metnini alip Kami Studio lirik video projesi hazirlar."""
    loaded = load_project(pid)
    if not loaded.get("ok"):
        return loaded
    proj = loaded["project"]
    audio_p = str(proj.get("last_mixdown") or "")
    if not audio_p or not os.path.isfile(audio_p):
        mr = render_mixdown(pid)
        if not mr.get("ok"):
            return mr
        audio_p = mr["path"]

    lyrics_txt = str(proj.get("lyrics") or "").strip()
    from app.core import studio
    proj_title = title.strip() or f"{proj.get('name', 'Kami Beat')} - Lirik Video"
    lufs_info = measure_lufs(audio_p)
    dur = float(lufs_info.get("duration") or 30.0)
    st_proj = studio.new_project(proj_title)
    st_proj["assets"]["a_mix"] = {
        "path": audio_p,
        "kind": "audio",
        "dur": dur,
        "w": 0,
        "h": 0,
        "audio": True,
        "name": Path(audio_p).name,
    }
    st_proj["clips"].append({
        "id": "c_aud_1",
        "track": "a1",
        "asset": "a_mix",
        "start": 0.0,
        "in": 0.0,
        "dur": dur,
        "speed": 1.0,
        "vol": 1.0,
        "fadeIn": 0.0,
        "fadeOut": 0.0,
    })
    non_empty = [ln.strip() for ln in lyrics_txt.splitlines() if ln.strip()]
    if non_empty:
        slot = max(1.2, dur / len(non_empty))
        for idx, line in enumerate(non_empty):
            t0 = round(idx * slot, 3)
            st_proj["clips"].append({
                "id": f"c_lyr_{idx + 1}",
                "track": "tx",
                "start": t0,
                "in": 0.0,
                "dur": round(min(slot, max(0.5, dur - t0)), 3),
                "text": line,
                "style": {"font": "Chakra Petch", "size": 7, "pos": "center", "anim": "pop", "outline": 4},
            })
    kstudio_path = studio.save_project(str(Path(audio_p).with_suffix(".kstudio")), st_proj)
    txt_path = str(Path(audio_p).with_suffix(".lyrics.txt"))
    Path(txt_path).write_text(lyrics_txt, encoding="utf-8")
    return {
        "ok": True,
        "audio_path": audio_p,
        "lyrics_path": txt_path,
        "kstudio_path": kstudio_path,
        "title": proj_title,
        "studio_project": st_proj,
    }
