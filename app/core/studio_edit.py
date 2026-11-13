"""Kami Studio Faz 8: Premiere seviyesi zaman cizelgesi duzenleme, metin kurgusu,
FFT coklu kamera senkronu ve kayipsiz Smart Cut motoru.
"""
from __future__ import annotations

import copy
import logging
import math
import struct
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ---------------------------------------------------------------------------
# 1. Metin Tabanli Video Kurgusu (Text-Based Editing)
# ---------------------------------------------------------------------------

def transcript_to_cuts(
    words: list[dict[str, Any]],
    keep_indices: set[int] | list[int] | None = None,
    total_dur: float = 0.0,
    pad: float = 0.06,
    merge_gap: float = 0.18,
) -> list[dict[str, float]]:
    """Transkript kelimelerinden tutulacak video araliklarini (`[{in, out}]`) uretir.

    Silinen kelimeler disarida kalir; birbirine `merge_gap` icinde yakin kalan
    parcalar kesintisiz akis icin birlestirilir.
    """
    if not words:
        return [{"in": 0.0, "out": round(max(0.0, total_dur), 3)}] if total_dur > 0 else []
    keep_set = set(range(len(words))) if keep_indices is None else set(int(i) for i in keep_indices)
    spans: list[list[float]] = []
    for idx, w in enumerate(words):
        if idx not in keep_set or w.get("deleted"):
            continue
        s = max(0.0, float(w.get("start", 0.0)) - pad)
        e = float(w.get("end", s)) + pad
        if total_dur > 0:
            e = min(total_dur, e)
        if e <= s:
            continue
        if spans and s - spans[-1][1] <= merge_gap:
            spans[-1][1] = max(spans[-1][1], e)
        else:
            spans.append([s, e])
    return [{"in": round(s, 3), "out": round(e, 3)} for s, e in spans]


def remap_captions_for_cuts(
    captions: list[dict[str, Any]],
    cuts: list[dict[str, float]],
) -> list[dict[str, Any]]:
    """Kesim araliklari sonrasinda altyazilarin yeni zaman cizelgesindeki konumunu hesaplar."""
    if not captions or not cuts:
        return []
    out_caps: list[dict[str, Any]] = []
    timeline_cursor = 0.0
    for seg in cuts:
        c_in = float(seg["in"])
        c_out = float(seg["out"])
        seg_dur = max(0.0, c_out - c_in)
        if seg_dur <= 0:
            continue
        for cap in captions:
            cs = float(cap.get("start", 0.0))
            ce = float(cap.get("end", 0.0))
            ov_s = max(c_in, cs)
            ov_e = min(c_out, ce)
            if ov_e > ov_s:
                nc = copy.deepcopy(cap)
                nc["start"] = round(timeline_cursor + (ov_s - c_in), 3)
                nc["end"] = round(timeline_cursor + (ov_e - c_in), 3)
                out_caps.append(nc)
        timeline_cursor += seg_dur
    return out_caps


# ---------------------------------------------------------------------------
# 2. FFT Capraz-Korelasyon ile Coklu Kamera (Multi-Cam) Ses Senkronu
# ---------------------------------------------------------------------------

def _extract_mono_pcm(ffmpeg: str, media_path: str, rate: int = 8000, max_sec: float = 90.0) -> list[float]:
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error",
        "-t", str(max_sec),
        "-i", media_path,
        "-vn", "-ac", "1", "-ar", str(rate), "-f", "s16le", "pipe:1",
    ]
    res = subprocess.run(cmd, capture_output=True, timeout=60, creationflags=NO_WINDOW)
    if res.returncode != 0 or not res.stdout:
        return []
    n = len(res.stdout) // 2
    if n == 0:
        return []
    samples = struct.unpack(f"<{n}h", res.stdout[: n * 2])
    return [s / 32768.0 for s in samples]


def compute_audio_offset(ref: list[float], target: list[float], sample_rate: int = 8000) -> dict[str, Any]:
    """Iki PCM sinyal arasindaki gecikmeyi (saniye) FFT capraz-korelasyon ile bulur.

    Pozitif `offset_sec`: `target`, `ref`'ten `offset_sec` saniye sonra baslamistir
    (yani zaman cizelgesinde `target.start = ref.start + offset_sec` olmalidir).
    """
    if not ref or not target:
        return {"ok": False, "offset_sec": 0.0, "confidence": 0.0}
    try:
        import numpy as np  # type: ignore
        a = np.asarray(ref, dtype=np.float64)
        b = np.asarray(target, dtype=np.float64)
        a -= a.mean()
        b -= b.mean()
        norm = float(np.linalg.norm(a) * np.linalg.norm(b))
        if norm < 1e-9:
            return {"ok": False, "offset_sec": 0.0, "confidence": 0.0}
        n = 1 << int(math.ceil(math.log2(len(a) + len(b) - 1)))
        fa = np.fft.rfft(a, n=n)
        fb = np.fft.rfft(b, n=n)
        corr = np.fft.irfft(fa * np.conj(fb), n=n)
        # Shift zero-lag to center
        half = n // 2
        corr_shifted = np.concatenate([corr[half:], corr[:half]])
        idx = int(np.argmax(corr_shifted))
        lag = idx - half
        conf = float(corr_shifted[idx] / norm)
        return {
            "ok": True,
            "offset_sec": round(lag / float(sample_rate), 4),
            "confidence": round(max(0.0, min(1.0, conf)), 4),
        }
    except ImportError:
        # Saf Python kaba zarf korelasyonu (numpy yoksa fallback)
        step = max(1, sample_rate // 100)
        ea = [sum(abs(x) for x in ref[i:i + step]) for i in range(0, len(ref), step)]
        eb = [sum(abs(x) for x in target[i:i + step]) for i in range(0, len(target), step)]
        if not ea or not eb:
            return {"ok": False, "offset_sec": 0.0, "confidence": 0.0}
        best_lag, best_val = 0, -1.0
        max_lag = min(len(ea), len(eb), 3000)
        for lag in range(-max_lag // 2, max_lag // 2):
            s = 0.0
            for i in range(len(ea)):
                j = i - lag
                if 0 <= j < len(eb):
                    s += ea[i] * eb[j]
            if s > best_val:
                best_val = s
                best_lag = lag
        return {
            "ok": True,
            "offset_sec": round((best_lag * step) / float(sample_rate), 4),
            "confidence": 0.5,
        }


def multicam_sync(ffmpeg: str, paths: list[str], sample_rate: int = 8000) -> dict[str, Any]:
    """Birden fazla medya dosyasini ilk dosyaya gore ses senkronu yapar."""
    if len(paths) < 2:
        return {"ok": False, "error": "En az 2 dosya gerekli", "offsets": []}
    if not ffmpeg:
        return {"ok": False, "error": "ffmpeg bulunamadi", "offsets": []}
    ref_pcm = _extract_mono_pcm(ffmpeg, paths[0], rate=sample_rate)
    if not ref_pcm:
        return {"ok": False, "error": "Referans sesten PCM alinamadi", "offsets": []}
    results = [{"path": paths[0], "offset_sec": 0.0, "confidence": 1.0}]
    for p in paths[1:]:
        tgt_pcm = _extract_mono_pcm(ffmpeg, p, rate=sample_rate)
        r = compute_audio_offset(ref_pcm, tgt_pcm, sample_rate=sample_rate)
        results.append({
            "path": p,
            "offset_sec": r.get("offset_sec", 0.0),
            "confidence": r.get("confidence", 0.0),
        })
    return {"ok": True, "offsets": results}


# ---------------------------------------------------------------------------
# 3. Premiere Seviyesi Kurgu: Ripple / Roll / Slip / Slide, J/L Cut, Compound
# ---------------------------------------------------------------------------

def _clip_dur(c: dict[str, Any]) -> float:
    """Zaman cizelgesi suresi: Studio klipleri `dur` tasir; `out` yalniz eski/harici modelde."""
    if c.get("dur") is not None:
        return max(0.05, float(c["dur"]))
    return max(0.05, float(c.get("out", 0.0)) - float(c.get("in", 0.0)))


def _set_clip_dur(c: dict[str, Any], dur: float) -> None:
    d = round(max(0.05, float(dur)), 3)
    c["dur"] = d
    if "out" in c:
        c["out"] = round(float(c.get("in", 0.0)) + d, 3)


def apply_timeline_edit(
    clips: list[dict[str, Any]],
    mode: str,
    clip_id: str,
    delta: float,
    edge: str = "out",
) -> list[dict[str, Any]]:
    """Zaman cizelgesi klibine Ripple, Roll, Slip veya Slide duzenlemesi uygular."""
    items = copy.deepcopy(clips)
    idx = next((i for i, c in enumerate(items) if c.get("id") == clip_id), -1)
    if idx < 0 or abs(delta) < 1e-6:
        return items

    target = items[idx]
    track = target.get("track", "v1")
    same_track = sorted(
        [(i, c) for i, c in enumerate(items) if c.get("track", "v1") == track],
        key=lambda x: float(x[1].get("start", 0.0)),
    )
    pos = next(k for k, (i, _) in enumerate(same_track) if i == idx)
    d = float(delta)

    if mode == "ripple":
        old_dur = _clip_dur(target)
        if edge in ("out", "r"):
            new_dur = max(0.05, old_dur + d)
            actual_d = new_dur - old_dur
            _set_clip_dur(target, new_dur)
            for _, nxt in same_track[pos + 1:]:
                nxt["start"] = round(max(0.0, float(nxt.get("start", 0.0)) + actual_d), 3)
        else:
            old_in = float(target.get("in", 0.0))
            new_in = max(0.0, min(old_in + old_dur - 0.05, old_in + d))
            actual_d = new_in - old_in
            target["in"] = round(new_in, 3)
            _set_clip_dur(target, old_dur - actual_d)
            for _, nxt in same_track[pos + 1:]:
                nxt["start"] = round(max(0.0, float(nxt.get("start", 0.0)) - actual_d), 3)

    elif mode == "roll":
        if pos + 1 < len(same_track):
            _, nxt = same_track[pos + 1]
            t_dur = _clip_dur(target)
            n_dur = _clip_dur(nxt)
            clamped = max(-(t_dur - 0.05), min(n_dur - 0.05, d))
            _set_clip_dur(target, t_dur + clamped)
            nxt["in"] = round(max(0.0, float(nxt.get("in", 0.0)) + clamped), 3)
            nxt["start"] = round(float(nxt.get("start", 0.0)) + clamped, 3)
            _set_clip_dur(nxt, n_dur - clamped)

    elif mode == "slip":
        dur = _clip_dur(target)
        new_in = max(0.0, float(target.get("in", 0.0)) + d)
        target["in"] = round(new_in, 3)
        _set_clip_dur(target, dur)

    elif mode == "slide":
        old_start = float(target.get("start", 0.0))
        new_start = max(0.0, old_start + d)
        actual_d = new_start - old_start
        target["start"] = round(new_start, 3)
        if pos > 0:
            _, prev = same_track[pos - 1]
            _set_clip_dur(prev, _clip_dur(prev) + actual_d)
        if pos + 1 < len(same_track):
            _, nxt = same_track[pos + 1]
            n_dur = _clip_dur(nxt)
            nxt["in"] = round(max(0.0, float(nxt.get("in", 0.0)) + actual_d), 3)
            nxt["start"] = round(max(0.0, float(nxt.get("start", 0.0)) + actual_d), 3)
            _set_clip_dur(nxt, max(0.05, n_dur - actual_d))

    return items


def apply_jl_cut(clip: dict[str, Any], audio_lead: float = 0.0, audio_tail: float = 0.0) -> dict[str, Any]:
    """Klibe J-cut (ses erken baslar) veya L-cut (ses gec biter) ofsetleri ekler."""
    out = copy.deepcopy(clip)
    out["audioLead"] = round(float(audio_lead), 3)
    out["audioTail"] = round(float(audio_tail), 3)
    return out


def create_compound_clip(clips: list[dict[str, Any]], clip_ids: list[str], name: str = "Bileşik Klip") -> dict[str, Any]:
    """Secili klipleri tek bir bilesik klip (`kind='compound'`) icinde paketler."""
    id_set = set(clip_ids)
    selected = [copy.deepcopy(c) for c in clips if c.get("id") in id_set]
    remaining = [copy.deepcopy(c) for c in clips if c.get("id") not in id_set]
    if not selected:
        return {"ok": False, "clips": clips}
    min_start = min(float(c.get("start", 0.0)) for c in selected)
    max_end = max(float(c.get("start", 0.0)) + _clip_dur(c) for c in selected)
    for c in selected:
        c["start"] = round(float(c.get("start", 0.0)) - min_start, 3)
    compound = {
        "id": f"cmp_{uuid.uuid4().hex[:8]}",
        "kind": "compound",
        "name": name,
        "track": selected[0].get("track", "v1"),
        "start": round(min_start, 3),
        "in": 0.0,
        "dur": round(max(0.1, max_end - min_start), 3),
        "out": round(max(0.1, max_end - min_start), 3),
        "children": selected,
    }
    remaining.append(compound)
    return {"ok": True, "compound": compound, "clips": remaining}


def expand_compound_clip(clips: list[dict[str, Any]], compound_id: str) -> list[dict[str, Any]]:
    """Bilesik klibi tekrar alt kliplerine acar."""
    out: list[dict[str, Any]] = []
    for c in clips:
        if c.get("id") == compound_id and c.get("kind") == "compound":
            base = float(c.get("start", 0.0))
            for child in c.get("children") or []:
                nc = copy.deepcopy(child)
                nc["start"] = round(base + float(nc.get("start", 0.0)), 3)
                out.append(nc)
        else:
            out.append(copy.deepcopy(c))
    return out


# ---------------------------------------------------------------------------
# 4. Hizli Kesim (Keyframe Copy) / Kare-Dogru Smart Cut
# ---------------------------------------------------------------------------

def build_smart_cut_cmd(ffmpeg: str, src: str, start: float, end: float, out_path: str, exact: bool = False) -> list[str]:
    """`exact=False`: anahtar kareden stream-copy hizli kesim; `exact=True`: kare-dogru yeniden kodlama."""
    s = max(0.0, float(start))
    dur = max(0.05, float(end) - s)
    if exact:
        return [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{s:.3f}", "-i", src, "-t", f"{dur:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            out_path,
        ]
    return [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{s:.3f}",
        "-i", src,
        "-t", f"{dur:.3f}",
        "-c", "copy",
        "-avoid_negative_ts", "make_zero",
        out_path,
    ]


def smart_cut(ffmpeg: str, src: str, start: float, end: float, out_path: str = "", exact: bool = False) -> dict[str, Any]:
    """Kesim uygular; `exact=False` anahtar-kare stream-copy, `exact=True` kare-dogru yeniden kodlama."""
    if not ffmpeg:
        return {"ok": False, "error": "ffmpeg bulunamadi"}
    p = Path(src)
    if not p.is_file():
        return {"ok": False, "error": "Kaynak dosya bulunamadi"}
    dst = Path(out_path) if out_path else p.with_name(f"{p.stem}_cut{p.suffix}")
    cmd = build_smart_cut_cmd(ffmpeg, str(p), start, end, str(dst), exact=exact)
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800, creationflags=NO_WINDOW)
    if res.returncode != 0 or not dst.exists():
        return {"ok": False, "error": (res.stderr or "Kesim basarisiz")[:300]}
    return {"ok": True, "path": str(dst), "size": dst.stat().st_size, "exact": bool(exact)}
