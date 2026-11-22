"""Kami Beat Studio: cok kanalli vokal/beat miks, VST3 zinciri, Vocal Comping, Soz Defteri ve Referans A/B."""
from __future__ import annotations

import json
import logging
import math
import os
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from app import paths
from app.core import kami_beat

log = logging.getLogger(__name__)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_TR_VOWELS = set("aeıioöuüAEIİOÖUÜ")

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
    lines = str(text or "").splitlines()
    rhyme_counts: dict[str, int] = {}
    keys: list[str] = []
    for ln in lines:
        rk = _rhyme_key(ln)
        keys.append(rk)
        if rk:
            rhyme_counts[rk] = rhyme_counts.get(rk, 0) + 1

    group_ids: dict[str, int] = {}
    next_gid = 1
    out: list[dict[str, Any]] = []
    bar_sec = (240.0 / bpm) if bpm and bpm > 0 else 0.0
    for idx, ln in enumerate(lines):
        syl = count_syllables_tr(ln)
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
        })
    total_syl = sum(x["syllables"] for x in out)
    non_empty = sum(1 for x in out if x["text"].strip())
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
        if sr != target_sr:
            from scipy import signal
            n_out = max(1, int(round(data.shape[0] * target_sr / sr)))
            data = signal.resample(data, n_out, axis=0).astype("float32")
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


def measure_lufs(path: str) -> dict[str, Any]:
    """Ses dosyasinin yaklasik LUFS ve True Peak dB olcumunu dondurur."""
    import numpy as np
    if not path or not os.path.isfile(path):
        return {"ok": False, "error": "file_not_found"}
    try:
        data, _ = _read_audio_np(path, 48000)
        if data.size == 0:
            return {"ok": False, "error": "empty_audio"}
        rms = float(np.sqrt(np.mean(data ** 2)))
        peak = float(np.max(np.abs(data)))
        lufs = 20.0 * math.log10(max(rms, 1e-7)) - 0.691
        peak_db = 20.0 * math.log10(max(peak, 1e-7))
        return {"ok": True, "lufs": round(lufs, 2), "peak_db": round(peak_db, 2), "duration": round(len(data) / 48000.0, 2)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}


def waveform_peaks(path: str, buckets: int = 160) -> dict[str, Any]:
    """Arayuzde dalga formu cizimi icin normalize tepe degerleri (0..1) uretir."""
    import numpy as np
    if not path or not os.path.isfile(path):
        return {"ok": False, "peaks": []}
    try:
        data, sr = _read_audio_np(path, 24000)
        mono = np.abs(data).mean(axis=1)
        if len(mono) == 0:
            return {"ok": True, "peaks": [], "duration": 0.0}
        step = max(1, len(mono) // max(16, buckets))
        peaks = [round(float(mono[i : i + step].max()), 3) for i in range(0, len(mono), step)][:buckets]
        mx = max(peaks) if peaks else 1.0
        if mx > 0:
            peaks = [round(p / mx, 3) for p in peaks]
        return {"ok": True, "peaks": peaks, "duration": round(len(mono) / sr, 2)}
    except Exception as exc:
        return {"ok": False, "peaks": [], "error": str(exc)[:120]}


def apply_fx_chain(in_path: str, out_path: str, fx_list: list[dict[str, Any]], use_denoise: bool = False) -> dict[str, Any]:
    """Ses dosyasina AI gurultu temizleme + pedalboard DSP + VST3 eklenti zinciri uygular."""
    if not in_path or not os.path.isfile(in_path):
        return {"ok": False, "error": "input_not_found"}
    try:
        data, sr = _read_audio_np(in_path, 48000)
        if use_denoise:
            try:
                import noisereduce as nr
                import numpy as np
                ch0 = nr.reduce_noise(y=data[:, 0], sr=sr, prop_decrease=0.8)
                ch1 = nr.reduce_noise(y=data[:, 1], sr=sr, prop_decrease=0.8)
                data = np.stack([ch0, ch1], axis=1).astype("float32")
            except Exception:
                log.debug("noisereduce uygulanamadi, atlaniyor", exc_info=True)

        import pedalboard as pb
        plugins: list[Any] = []
        for fx in fx_list or []:
            if fx.get("bypass"):
                continue
            t = str(fx.get("type") or "").lower()
            try:
                if t == "vst3":
                    vp = str(fx.get("path") or "")
                    if vp and os.path.exists(vp):
                        plugins.append(pb.load_plugin(vp))
                elif t == "noisegate":
                    plugins.append(pb.NoiseGate(threshold_db=float(fx.get("threshold_db", -42)), ratio=float(fx.get("ratio", 6))))
                elif t == "highpass":
                    plugins.append(pb.HighpassFilter(cutoff_frequency_hz=float(fx.get("cutoff_hz", 90))))
                elif t == "lowpass":
                    plugins.append(pb.LowpassFilter(cutoff_frequency_hz=float(fx.get("cutoff_hz", 12000))))
                elif t == "peak":
                    plugins.append(pb.PeakFilter(cutoff_frequency_hz=float(fx.get("cutoff_hz", 1000)), gain_db=float(fx.get("gain_db", 0)), q=float(fx.get("q", 1.0))))
                elif t == "deesser":
                    plugins.append(pb.PeakFilter(cutoff_frequency_hz=float(fx.get("freq_hz", 6800)), gain_db=float(fx.get("gain_db", -4.0)), q=2.2))
                elif t == "compressor":
                    plugins.append(pb.Compressor(
                        threshold_db=float(fx.get("threshold_db", -18)),
                        ratio=float(fx.get("ratio", 4.0)),
                        attack_ms=float(fx.get("attack_ms", 8.0)),
                        release_ms=float(fx.get("release_ms", 85.0)),
                    ))
                elif t == "distortion":
                    plugins.append(pb.Distortion(drive_db=float(fx.get("drive_db", 3.0))))
                elif t == "delay":
                    plugins.append(pb.Delay(
                        delay_seconds=float(fx.get("delay_seconds", 0.25)),
                        feedback=float(fx.get("feedback", 0.2)),
                        mix=float(fx.get("mix", 0.15)),
                    ))
                elif t == "reverb":
                    plugins.append(pb.Reverb(
                        room_size=float(fx.get("room_size", 0.25)),
                        wet_level=float(fx.get("wet_level", 0.12)),
                        dry_level=float(fx.get("dry_level", 0.9)),
                    ))
                elif t == "gain":
                    plugins.append(pb.Gain(gain_db=float(fx.get("gain_db", 0.0))))
                elif t == "limiter":
                    plugins.append(pb.Limiter(threshold_db=float(fx.get("threshold_db", -1.0))))
            except Exception:
                log.debug("FX dugumu eklenemedi: %s", fx, exc_info=True)

        if plugins:
            board = pb.Pedalboard(plugins)
            # pedalboard (channels, samples) bekler
            processed = board(data.T, sr).T
        else:
            processed = data

        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        _write_wav_np(out_path, processed, sr)
        return {"ok": True, "path": out_path, "fx_count": len(plugins)}
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


def save_project(proj: dict[str, Any]) -> dict[str, Any]:
    pid = str(proj.get("id") or "")
    if not pid:
        return {"ok": False, "error": "missing_id"}
    proj["updated_at"] = time.time()
    fp = _proj_file(pid)
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(json.dumps(proj, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "path": str(fp)}


def load_project(pid: str) -> dict[str, Any]:
    fp = _proj_file(pid)
    if not fp.is_file():
        return {"ok": False, "error": "not_found"}
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        return {"ok": True, "project": data}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}


def list_projects() -> dict[str, Any]:
    out = []
    for fp in sorted(projects_dir().glob("*.kbeat.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
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


def add_take_to_track(pid: str, track_id: str, audio_path: str, label: str = "") -> dict[str, Any]:
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
            tr["path"] = audio_path
            if tr.get("role") == "beat" and os.path.isfile(audio_path):
                bpm = kami_beat.analyze_bpm(audio_path)
                kinfo = kami_beat.detect_key(audio_path)
                if bpm:
                    proj["bpm"] = bpm
                if kinfo.get("key"):
                    proj["key"] = kinfo["key"]
            save_project(proj)
            return {"ok": True, "project": proj, "take": take}
    return {"ok": False, "error": "track_not_found"}


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

    for tr in tracks:
        if tr.get("mute") or (has_solo and not tr.get("solo")):
            continue
        p = str(tr.get("path") or "")
        if not p or not os.path.isfile(p):
            continue
        fx = tr.get("fx") or []
        denoise = bool(tr.get("denoise"))
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

    # Hedef LUFS dengeleme + soft clip korumasi
    rms = float(np.sqrt(np.mean(mix ** 2)))
    if rms > 1e-6 and target_lufs < 0:
        cur_lufs = 20.0 * math.log10(rms) - 0.691
        diff_db = max(-12.0, min(12.0, target_lufs - cur_lufs))
        mix *= (10.0 ** (diff_db / 20.0))
    peak = float(np.max(np.abs(mix)))
    if peak > 0.98:
        mix *= (0.98 / peak)

    if not out_path:
        safe_name = re.sub(r'[<>:"/\\|?*]', "_", str(proj.get("name") or pid)).strip() or pid
        out_path = str(recordings_dir() / f"{safe_name}_mixdown.wav")
    _write_wav_np(out_path, mix, sr)
    proj["last_mixdown"] = out_path
    save_project(proj)
    lufs_info = measure_lufs(out_path)
    return {"ok": True, "path": out_path, "lufs": lufs_info.get("lufs"), "peak_db": lufs_info.get("peak_db"), "duration": lufs_info.get("duration")}


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
