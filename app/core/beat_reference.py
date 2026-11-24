"""Kami Beat Asama 2a: referans A/B — seviye esleme ve kisa spektrum karsilastirmasi.

- Seviye esleme: referansin entegre LUFS'u ile miksin (arayuzde duyulan ham miks: beat_studio.mix_array, hedef
  LUFS normalizasyonu YOK) entegre LUFS'u olculur; referans kazanci = miks - referans. Boylece A/B'de "daha yuksek
  = daha iyi" yanilgisi olmaz. Olcum beat_studio.measure_lufs (ffmpeg ebur128; yoksa RMS yaklasigi) — iki taraf
  ayni yontemle olculur.
- Spektrum ozeti: 5 bant (alcak / orta / ust orta / parlaklik / hava) enerjisinin TOPLAM enerjiye orani (dB).
  Oranlar ses seviyesinden bagimsizdir; referans ile miks arasindaki en buyuk 2-3 fark kisa madde olur
  ("Referans daha parlak (+3.0 dB 6-10 kHz)"). Yalniz bilgi; hicbir seye otomatik dokunmaz.
"""
from __future__ import annotations

import logging
import math
import os
import uuid
from typing import Any

log = logging.getLogger(__name__)

SR = 48000
FRAME = 4096
MAX_FRAMES = 360            # ~30 sn esdegeri; uzun dosyada esit aralikli cerceveler
MATCH_LIMIT_DB = 24.0
DIFF_THRESHOLD_DB = 1.5

# (anahtar, ad, alt Hz, ust Hz, referans fazla ifadesi, miks fazla ifadesi)
BANDS: list[tuple[str, str, float, float, str, str]] = [
    ("low", "Alçak", 20.0, 250.0, "Referansın alt ucu daha dolu", "Miksin alt ucu referanstan daha dolu"),
    ("mid", "Orta", 250.0, 2000.0, "Referans orta bölgede daha yoğun", "Miks orta bölgede daha yoğun (çamur olabilir)"),
    ("highmid", "Üst orta", 2000.0, 6000.0, "Referans üst ortada daha önde (vokal varlığı)", "Miks üst ortada daha sert"),
    ("bright", "Parlaklık", 6000.0, 10000.0, "Referans daha parlak", "Miks referanstan daha parlak"),
    ("air", "Hava", 10000.0, 16000.0, "Referansta daha fazla hava", "Miksin üst ucunda daha fazla hava var"),
]


def _hz(x: float) -> str:
    return f"{x / 1000:g}" if x >= 1000 else f"{x:g}"


def band_range(lo: float, hi: float) -> str:
    """'6-10 kHz', '250 Hz-2 kHz', '20-250 Hz'."""
    if lo >= 1000:
        return f"{_hz(lo)}-{_hz(hi)} kHz"
    if hi >= 1000:
        return f"{_hz(lo)} Hz-{_hz(hi)} kHz"
    return f"{_hz(lo)}-{_hz(hi)} Hz"


def band_profile(data, sr: int = SR) -> dict[str, float]:
    """(N,2) ya da (N,) -> {bant: toplam enerjiye oran (dB)}. Hann pencereli FFT, cerceve ortalamasi."""
    import numpy as np
    x = np.asarray(data, dtype="float32")
    if x.ndim == 2:
        x = x.mean(axis=1)
    n = len(x)
    if n < FRAME:
        x = np.concatenate([x, np.zeros(FRAME - n, dtype="float32")])
        n = FRAME
    count = n // FRAME
    idx = np.linspace(0, count - 1, num=min(count, MAX_FRAMES)).round().astype(int)
    frames = np.stack([x[i * FRAME:(i + 1) * FRAME] for i in idx])
    win = np.hanning(FRAME).astype("float32")
    spec = np.abs(np.fft.rfft(frames * win, axis=1)) ** 2
    power = spec.mean(axis=0)
    freqs = np.fft.rfftfreq(FRAME, 1.0 / sr)
    tot_mask = (freqs >= BANDS[0][2]) & (freqs < BANDS[-1][3])
    total = float(power[tot_mask].sum()) + 1e-20
    out: dict[str, float] = {}
    for key, _, lo, hi, _, _ in BANDS:
        m = (freqs >= lo) & (freqs < hi)
        out[key] = round(10.0 * math.log10(float(power[m].sum()) / total + 1e-12), 2)
    return out


def compare_spectra(ref: dict[str, float], mix: dict[str, float], threshold: float = DIFF_THRESHOLD_DB,
                    top: int = 3) -> list[dict[str, Any]]:
    """Referans - miks bant farklari: esigi asan en buyuk `top` fark, kisa Turkce madde olarak."""
    diffs = []
    for key, name, lo, hi, more, less in BANDS:
        if key not in ref or key not in mix:
            continue
        d = round(float(ref[key]) - float(mix[key]), 1)
        if abs(d) >= threshold:
            diffs.append({"band": key, "name": name, "range": band_range(lo, hi), "diff_db": d,
                          "text": f"{more if d > 0 else less} ({d:+.1f} dB {band_range(lo, hi)})"})
    diffs.sort(key=lambda x: -abs(x["diff_db"]))
    if not diffs:
        return [{"band": "", "name": "", "range": "", "diff_db": 0.0, "text": "Ton dengesi referansa yakın (fark < 1.5 dB)."}]
    return diffs[:max(1, int(top))]


def level_match(ref_lufs: float | None, mix_lufs: float | None) -> dict[str, Any]:
    """Referans kazanci (dB) ki entegre ses seviyeleri esit olsun. diff = referans - miks (LU)."""
    if ref_lufs is None or mix_lufs is None or not math.isfinite(ref_lufs) or not math.isfinite(mix_lufs):
        return {"ok": False, "gain_db": 0.0, "diff_lu": None, "text": "Ses seviyesi ölçülemedi — referans eşitlenmedi."}
    diff = float(ref_lufs) - float(mix_lufs)
    gain = max(-MATCH_LIMIT_DB, min(MATCH_LIMIT_DB, -diff))
    if abs(diff) < 0.5:
        txt = f"Seviyeler zaten yakın (fark {abs(diff):.1f} LU)."
    else:
        txt = f"Referans {abs(diff):.1f} LU daha {'yüksek' if diff > 0 else 'düşük'}, eşitlendi."
    if abs(-diff) > MATCH_LIMIT_DB:
        txt += f" (en fazla ±{MATCH_LIMIT_DB:g} dB)"
    return {"ok": True, "gain_db": round(gain, 2), "diff_lu": round(diff, 2), "text": txt}


def _lufs_of_array(data, sr: int = SR) -> float | None:
    from app.core import beat_studio
    d = beat_studio.recordings_dir() / "_mix_tmp"
    d.mkdir(parents=True, exist_ok=True)
    fp = d / f"refmatch_{uuid.uuid4().hex[:8]}.wav"
    try:
        beat_studio._write_wav_np(str(fp), data, sr)
        r = beat_studio.measure_lufs(str(fp))
        return float(r["lufs"]) if r.get("ok") and r.get("lufs") is not None else None
    except Exception:
        log.debug("miks LUFS olculemedi", exc_info=True)
        return None
    finally:
        try:
            os.remove(fp)
        except OSError:
            pass


def analyze(pid: str, path: str, start: float = 0.0) -> dict[str, Any]:
    """Referans dosyasi + projenin guncel (kaydedilmis) miksi -> seviye esleme + spektrum maddeleri.
    Arayuz once bekleyen kaydi yazar (flushSave), sonra bunu arka plan isi olarak cagirir."""
    from app.core import beat_studio
    if not path or not os.path.isfile(path):
        return {"ok": False, "error": "file_not_found"}
    ld = beat_studio.load_project(pid) if pid else {"ok": False, "error": "project_not_found"}
    if not ld.get("ok"):
        return ld
    try:
        ref, _ = beat_studio._read_audio_np(path, SR)
    except Exception as exc:
        return {"ok": False, "error": f"decode: {str(exc)[:100]}"}
    rl = beat_studio.measure_lufs(path)
    ref_lufs = float(rl["lufs"]) if rl.get("ok") and rl.get("lufs") is not None else None
    s0 = max(0, int(round(float(start or 0.0) * SR)))
    ref_prof = band_profile(ref[s0:] if s0 < len(ref) else ref, SR)
    mix = beat_studio.mix_array(ld["project"], SR)
    out: dict[str, Any] = {"ok": True, "path": path, "ref_lufs": ref_lufs, "duration": round(len(ref) / SR, 2),
                           "ref_bands": ref_prof}
    if mix is None or not len(mix):
        out.update(mix_lufs=None, match=level_match(None, None), notes=[], mix_bands={},
                   warning="Miks boş — önce kanallara ses ekle; referans eşitlenmedi.")
        return out
    mix_lufs = _lufs_of_array(mix, SR)
    mix_prof = band_profile(mix, SR)
    out.update(mix_lufs=mix_lufs, match=level_match(ref_lufs, mix_lufs), mix_bands=mix_prof,
               notes=compare_spectra(ref_prof, mix_prof))
    return out
