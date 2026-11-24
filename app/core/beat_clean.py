"""Kami Beat Asama 2b: otomatik vokal temizligi (oner -> onayla), YIKICI DEGIL.

Uc ayri islem, her biri ac/kapa + siddet:
  a) Gurultu: kaydin en sessiz 0.5-1 sn'sinden gurultu profili cikarilir. Yerel yontemler:
     - "auto": noisereduce kuruluysa o (profil = sessiz bolge), yoksa numpy spektral kapi (bu modulde).
     - "ffmpeg": afftdn, gurultu tabani (nf) profilden olculur.
     - "advanced": resemble-enhance denoiser (MIT). YALNIZ kullanici "Gelismis temizlik modelini indir"
       dugmesine basinca kurulur (model_info boyut + kaynak gosterir, install_model akisi). Modul yoksa
       zarif devre disi: otomatik olarak "auto" yontemine duser ve sonucta not doner.
  b) Nefes: kisa (150-600 ms), dusuk enerjili, genis bantli (spektral duzluk yuksek, yuksek frekans agirlikli),
     sozlu sesten hemen once gelen bolgeler. Oneri: -6..-18 dB kisma (silme degil; "tamamen sil" secilebilir).
     Bolgeler tek tek acilip kapatilabilir (klip clean.breath.regions = [[t0, t1, on], ...], kaynak dosya zamani).
  c) Agiz sesi (click/smack): <10 ms gecici tepe tespiti (ikinci fark, yerel medyan esigi) + kubik Hermite
     enterpolasyonu. Tiklarin disindaki ornekler BIREBIR korunur.

Sonuc ayri dosyadir: recordings/_clean/<kaynak_imzasi>_<ayar_imzasi>.wav (32-bit float, ayni uzunluk/48 kHz ->
klibin src_in/src_out'u degismeden gecerli). Ham dosya HIC degismez. Klip alani:
  clean: {noise: {on, strength, method}, breath: {on, mode, db, regions}, click: {on, strength},
          file, src, key, off?}
render_track_audio kaynak olarak source_path(klip) kullanir; "Temizligi kaldir" = alani silmek."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import math
import os
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("kami.beat_clean")

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
SR = 48000
N_FFT = 2048
HOP = 512

BREATH_MIN = 0.15
BREATH_MAX = 0.60
BREATH_SPEECH_GAP = 0.6       # nefesten sonra en gec bu kadar sn icinde sozlu ses baslamali
BREATH_DB_RANGE = (-18.0, -6.0)
BREATH_RAMP = 0.010
CLICK_MAX_MS = 10.0
NOISE_PROFILE_SEC = (0.5, 1.0)

DEFAULTS: dict[str, Any] = {
    "noise": {"on": True, "strength": 50.0, "method": "auto"},
    "breath": {"on": True, "mode": "reduce", "db": -10.0, "regions": []},
    "click": {"on": True, "strength": 50.0},
}


# ---------------- yardimcilar ----------------
def _num(v: Any, d: float) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return d
    return x if math.isfinite(x) else d


def clean_dir() -> Path:
    from app.core import beat_studio
    d = beat_studio.recordings_dir() / "_clean"
    d.mkdir(parents=True, exist_ok=True)
    return d


def normalize_settings(s: dict[str, Any] | None) -> dict[str, Any]:
    """Eksik alanlari doldurur, araliklari sikistirir (kopya). Yalniz sesi etkileyen alanlar."""
    s = s if isinstance(s, dict) else {}
    n = s.get("noise") if isinstance(s.get("noise"), dict) else {}
    b = s.get("breath") if isinstance(s.get("breath"), dict) else {}
    c = s.get("click") if isinstance(s.get("click"), dict) else {}
    method = str(n.get("method") or "auto")
    if method not in ("auto", "ffmpeg", "advanced", "numpy"):
        method = "auto"
    regions = []
    for r in b.get("regions") or []:
        if isinstance(r, (list, tuple)) and len(r) >= 2:
            t0, t1 = max(0.0, _num(r[0], 0.0)), max(0.0, _num(r[1], 0.0))
            if t1 - t0 >= 0.02:
                regions.append([round(t0, 4), round(t1, 4), bool(r[2]) if len(r) > 2 else True])
    regions.sort(key=lambda r: r[0])
    return {
        "noise": {"on": bool(n.get("on", DEFAULTS["noise"]["on"])),
                  "strength": max(0.0, min(100.0, _num(n.get("strength"), 50.0))), "method": method},
        "breath": {"on": bool(b.get("on", DEFAULTS["breath"]["on"])),
                   "mode": "remove" if b.get("mode") == "remove" else "reduce",
                   "db": max(BREATH_DB_RANGE[0], min(BREATH_DB_RANGE[1], _num(b.get("db"), -10.0))),
                   "regions": regions},
        "click": {"on": bool(c.get("on", DEFAULTS["click"]["on"])),
                  "strength": max(0.0, min(100.0, _num(c.get("strength"), 50.0)))},
    }


def any_on(s: dict[str, Any]) -> bool:
    s = normalize_settings(s)
    return bool(s["noise"]["on"] or s["click"]["on"]
                or (s["breath"]["on"] and any(r[2] for r in s["breath"]["regions"])))


def _file_sig(path: str) -> list[Any]:
    try:
        st = os.stat(path)
        return [os.path.abspath(path), int(st.st_size), round(st.st_mtime, 3)]
    except OSError:
        return [os.path.abspath(path), 0, 0]


def source_hash(path: str) -> str:
    return hashlib.sha1(json.dumps(_file_sig(path)).encode("utf-8")).hexdigest()[:12]


def settings_hash(s: dict[str, Any]) -> str:
    s = normalize_settings(s)
    core: dict[str, Any] = {}
    if s["noise"]["on"]:
        core["n"] = [round(s["noise"]["strength"], 1), s["noise"]["method"]]
    if s["click"]["on"]:
        core["c"] = round(s["click"]["strength"], 1)
    if s["breath"]["on"]:
        on = [[r[0], r[1]] for r in s["breath"]["regions"] if r[2]]
        if on:
            core["b"] = [s["breath"]["mode"], round(s["breath"]["db"], 1), on]
    raw = json.dumps(core, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def cache_path(path: str, settings: dict[str, Any]) -> Path:
    """Onbellek dosyasi: kaynak imzasi (yol/boyut/mtime) + ayar imzasi."""
    return clean_dir() / f"{source_hash(path)}_{settings_hash(settings)}.wav"


def source_path(clip: dict[str, Any]) -> str:
    """Render'in okuyacagi dosya: gecerli temizlik dosyasi varsa o, yoksa ham kaynak."""
    p = str(clip.get("path") or "")
    cl = clip.get("clean")
    if not isinstance(cl, dict) or cl.get("off"):
        return p
    f = str(cl.get("file") or "")
    src = str(cl.get("src") or p)
    if f and src == p and os.path.isfile(f):
        return f
    return p


def write_wav_f32(path: str, audio, sr: int = SR) -> None:
    """32-bit float stereo WAV (WAVE_FORMAT_IEEE_FLOAT). Bagimliliksiz; temizlik dosyasi hassasiyet kaybetmesin."""
    import numpy as np
    a = np.asarray(audio, dtype="<f4")
    if a.ndim == 1:
        a = np.stack([a, a], axis=1)
    a = np.ascontiguousarray(a[:, :2])
    ch = a.shape[1]
    data = a.tobytes()
    fmt = struct.pack("<HHIIHH", 3, ch, sr, sr * ch * 4, ch * 4, 32)
    fact = struct.pack("<I", len(a))
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 4 + 8 + len(fmt) + 8 + len(fact) + 8 + len(data)) + b"WAVE")
        f.write(b"fmt " + struct.pack("<I", len(fmt)) + fmt)
        f.write(b"fact" + struct.pack("<I", len(fact)) + fact)
        f.write(b"data" + struct.pack("<I", len(data)) + data)


# ---------------- STFT (numpy; scipy pakette yok) ----------------
def _win(n: int):
    import numpy as np
    return np.sqrt(np.hanning(n + 1)[:n]).astype("float64")     # periyodik sqrt-hann: analiz + sentez = hann


def stft_process(x, gain_fn: Callable[[Any, Any], Any], n_fft: int = N_FFT, hop: int = HOP, abs_start: int = 0,
                 chunk: int = 384, ctx: int = 2):
    """(N,) ya da (N,C) -> ayni boyut. Cerceveler MUTLAK izgarada (k*hop) durur: pencereli onizleme ile tam
    render ayni cercevelerden gecer. gain_fn(mag_mid (F,T), frame_centers_abs (T,)) -> (F,T) kazanc maskesi;
    tum kanallara ayni maske (stereo goruntu korunur). Maske 1 ise cikis girdiye (yuvarlama hatasiyla) esit.
    Bellek icin cerceveler `chunk`'lik gruplarla islenir; maske yumusatmasi icin her grup `ctx` komsu cerceve gorur."""
    import numpy as np
    a = np.asarray(x, dtype="float64")
    mono = a.ndim == 1
    if mono:
        a = a[:, None]
    n = len(a)
    if n == 0:
        return np.asarray(x, dtype="float32")
    w = _win(n_fft)
    lead = (abs_start % hop) + n_fft           # ilk cerceve mutlak izgarada, girdinin oncesinden baslar
    total = lead + n + n_fft
    total += (-(total - n_fft)) % hop
    pad = np.zeros((total, a.shape[1]), dtype="float64")
    pad[lead:lead + n] = a
    nfr = 1 + (total - n_fft) // hop
    out = np.zeros_like(pad)
    wsum = np.zeros(total, dtype="float64")
    ww = w * w
    nch = a.shape[1]
    for f0 in range(0, nfr, chunk):
        f1 = min(nfr, f0 + chunk)
        g0, g1 = max(0, f0 - ctx), min(nfr, f1 + ctx)
        idx = np.arange(n_fft)[None, :] + hop * np.arange(g0, g1)[:, None]
        centers = abs_start - lead + hop * np.arange(g0, g1) + n_fft // 2
        specs = [np.fft.rfft(pad[idx, ch] * w[None, :], axis=1).T for ch in range(nch)]   # (F,T)
        mid = np.abs(sum(specs) / nch)
        g = np.asarray(gain_fn(mid, centers), dtype="float64")
        if g.ndim == 2:
            g = g[:, f0 - g0: f0 - g0 + (f1 - f0)]
        for ch in range(nch):
            S = specs[ch][:, f0 - g0: f0 - g0 + (f1 - f0)]
            fr = np.fft.irfft((S * g).T, n=n_fft, axis=1) * w[None, :]
            for k in range(f1 - f0):
                s0 = hop * (f0 + k)
                out[s0:s0 + n_fft, ch] += fr[k]
        for k in range(f0, f1):
            wsum[hop * k: hop * k + n_fft] += ww
    wsum[wsum < 1e-9] = 1.0
    res = (out / wsum[:, None])[lead:lead + n]
    return (res[:, 0] if mono else res).astype("float32")


def _smooth(m, kt: int = 3, kf: int = 5):
    """Maske yumusatma (muzikal gurultu azalir): zaman ve frekans ekseninde hareketli ortalama."""
    import numpy as np
    out = m
    if kf > 1:
        k = np.ones(kf) / kf
        out = np.apply_along_axis(lambda v: np.convolve(np.pad(v, (kf // 2, kf // 2), mode="edge"), k, "valid"), 0, out)
    if kt > 1:
        k = np.ones(kt) / kt
        out = np.apply_along_axis(lambda v: np.convolve(np.pad(v, (kt // 2, kt // 2), mode="edge"), k, "valid"), 1, out)
    return out


# ---------------- a) gurultu ----------------
def _mono(data):
    import numpy as np
    a = np.asarray(data, dtype="float32")
    return a.mean(axis=1) if a.ndim == 2 else a


def noise_profile(data, sr: int = SR) -> dict[str, Any]:
    """En sessiz 0.5-1 sn'lik bolge (dijital sessizlik haric). {t0, t1, floor_db}."""
    import numpy as np
    m = _mono(data).astype("float64")
    n = len(m)
    if n == 0:
        return {"t0": 0.0, "t1": 0.0, "floor_db": -120.0}
    blk = int(0.05 * sr)
    nb = max(1, n // blk)
    pw = np.array([np.mean(m[i * blk:(i + 1) * blk] ** 2) for i in range(nb)])
    dur = n / sr
    win_s = NOISE_PROFILE_SEC[1] if dur >= 6.0 else max(NOISE_PROFILE_SEC[0], min(NOISE_PROFILE_SEC[1], dur * 0.15))
    k = max(1, int(round(win_s / 0.05)))
    valid = pw > 1e-14                          # dijital sessizlik (kesilmis/0 dolgu) profil olmaz
    if k >= nb:
        sel = valid if valid.any() else np.ones(nb, bool)
        fl = float(np.mean(pw[sel]))
        return {"t0": 0.0, "t1": round(dur, 4), "floor_db": round(10 * math.log10(max(fl, 1e-14)), 2)}
    cs = np.concatenate([[0.0], np.cumsum(np.where(valid, pw, 0.0))])
    cv = np.concatenate([[0], np.cumsum(valid.astype(int))])
    best, bi = None, 0
    for i in range(0, nb - k + 1):
        cnt = cv[i + k] - cv[i]
        if cnt < k * 0.8:
            continue
        v = (cs[i + k] - cs[i]) / cnt
        if best is None or v < best:
            best, bi = v, i
    if best is None:
        best, bi = float(np.mean(pw)), 0
    return {"t0": round(bi * 0.05, 4), "t1": round((bi + k) * 0.05, 4),
            "floor_db": round(10 * math.log10(max(best, 1e-14)), 2)}


def spectral_gate(data, sr: int = SR, strength: float = 50.0, profile: dict[str, Any] | None = None):
    """numpy spektral kapi (Wiener benzeri cikarma + taban): gurultu profili sessiz bolgenin ortalama genliginden."""
    import numpy as np
    a = np.asarray(data, dtype="float32")
    prof = profile or noise_profile(a, sr)
    i0, i1 = int(prof["t0"] * sr), int(prof["t1"] * sr)
    seg = a[i0:i1] if i1 - i0 >= N_FFT else a[: max(N_FFT, min(len(a), sr))]
    if len(seg) < N_FFT:
        return a
    w = _win(N_FFT)
    sm = _mono(seg).astype("float64")
    nfr = 1 + (len(sm) - N_FFT) // HOP
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(nfr)[:, None]
    nmag = np.abs(np.fft.rfft(sm[idx] * w[None, :], axis=1)).mean(axis=0)[:, None]     # (F,1)
    s = max(0.0, min(100.0, float(strength))) / 100.0
    red_db = 6.0 + 18.0 * s
    floor = 10 ** (-red_db / 20.0)
    alpha = 1.0 + 1.5 * s

    def gain(mag, _c):
        g = 1.0 - (alpha * nmag) / np.maximum(mag, 1e-12)
        return np.clip(_smooth(np.clip(g, floor, 1.0), kt=3, kf=1), floor, 1.0)   # frekansta yumusatma harmonikleri kirpar

    return stft_process(a, gain)


def _noisereduce(data, sr: int, strength: float, profile: dict[str, Any]):
    import numpy as np
    import noisereduce as nr                   # noqa: PLC0415  (kuruluysa)
    a = np.asarray(data, dtype="float32")
    i0, i1 = int(profile["t0"] * sr), int(profile["t1"] * sr)
    noise = a[i0:i1] if i1 > i0 else a[: sr]
    prop = 0.4 + 0.6 * max(0.0, min(100.0, float(strength))) / 100.0
    out = np.empty_like(a)
    for ch in range(a.shape[1]):
        out[:, ch] = nr.reduce_noise(y=a[:, ch], sr=sr, y_noise=noise[:, ch], prop_decrease=prop, stationary=True)[: len(a)]
    return out.astype("float32")


def _ffmpeg_afftdn(data, sr: int, strength: float, profile: dict[str, Any]):
    import numpy as np
    from app.core import kami_beat
    ff = kami_beat._find_ffmpeg()
    if not ff:
        raise RuntimeError("ffmpeg_missing")
    nf = max(-80.0, min(-20.0, float(profile.get("floor_db") or -50.0)))
    nr_db = 6.0 + 24.0 * max(0.0, min(100.0, float(strength))) / 100.0
    arr = np.ascontiguousarray(data, dtype="<f4")
    r = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-f", "f32le", "-ar", str(sr), "-ac", "2", "-i", "pipe:0",
                        "-af", f"afftdn=nr={nr_db:.1f}:nf={nf:.1f}:tn=1", "-f", "f32le", "-ar", str(sr), "-ac", "2", "pipe:1"],
                       input=arr.tobytes(), capture_output=True, timeout=600, creationflags=NO_WINDOW)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError(r.stderr.decode("utf-8", errors="replace")[:200])
    out = np.frombuffer(r.stdout, dtype="<f4")
    out = out[: (len(out) // 2) * 2].reshape(-1, 2).copy()
    if len(out) < len(arr):
        out = np.concatenate([out, np.zeros((len(arr) - len(out), 2), dtype="float32")])
    return out[: len(arr)]


def denoise(data, sr: int = SR, strength: float = 50.0, method: str = "auto",
            profile: dict[str, Any] | None = None) -> tuple[Any, dict[str, Any]]:
    """Gurultu azaltma. Donus: (dizi, {method, note})."""
    prof = profile or noise_profile(data, sr)
    note = ""
    if method == "advanced":
        if advanced_available():
            try:
                return advanced_denoise(data, sr), {"method": "advanced", "note": ""}
            except Exception as exc:
                log.warning("Gelismis temizlik basarisiz, yerel yonteme dusuldu", exc_info=True)
                note = f"gelişmiş model çalışmadı ({str(exc)[:60]}) — yerel yöntem kullanıldı"
        else:
            note = "gelişmiş model kurulu değil — yerel yöntem kullanıldı"
        method = "auto"
    if method == "ffmpeg":
        try:
            return _ffmpeg_afftdn(data, sr, strength, prof), {"method": "ffmpeg", "note": note}
        except Exception:
            log.warning("afftdn basarisiz, numpy kapisina dusuldu", exc_info=True)
            note = (note + "; " if note else "") + "ffmpeg afftdn çalışmadı — numpy kapısı"
            method = "auto"
    if method == "auto" and importlib.util.find_spec("noisereduce") is not None:
        try:
            return _noisereduce(data, sr, strength, prof), {"method": "noisereduce", "note": note}
        except Exception:
            log.debug("noisereduce basarisiz", exc_info=True)
    return spectral_gate(data, sr, strength, prof), {"method": "numpy", "note": note}


# ---------------- gelismis (resemble-enhance, istege bagli) ----------------
ADVANCED = {
    "name": "resemble-enhance (denoiser)",
    "license": "MIT",
    "package": "resemble-enhance",
    "source": "PyPI: resemble-enhance · ağırlıklar: huggingface.co/ResembleAI/resemble-enhance",
    "size_mb": 710,          # HF deposu ~810 MB, ornek mp4'ler haric agirliklar ~710 MB
    "extra": "PyTorch (CPU) gerekir; ilk kurulumda ayrıca ~200 MB+ indirilir",
}


def models_dir() -> Path:
    from app.core import beat_style
    d = beat_style.settings_dir() / "models" / "resemble_enhance"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ensure_path() -> None:
    p = str(models_dir() / "site")
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)


def advanced_available() -> bool:
    try:
        _ensure_path()
        return importlib.util.find_spec("resemble_enhance") is not None
    except Exception:
        return False


def model_info() -> dict[str, Any]:
    return dict(ADVANCED, ok=True, installed=advanced_available(), target=str(models_dir()),
                progress=dict(_INSTALL))


def advanced_denoise(data, sr: int = SR):
    """Ince sarmalayici: resemble_enhance.enhancer.inference.denoise(tensor, sr, device) -> (tensor, sr).
    Kanal basina islenir; cikis ornekleme hizi farkliysa ffmpeg'siz dogrusal yeniden ornekleme."""
    import numpy as np
    _ensure_path()
    import torch                                             # noqa: PLC0415
    from resemble_enhance.enhancer.inference import denoise as _rd   # noqa: PLC0415
    a = np.asarray(data, dtype="float32")
    dev = "cuda" if getattr(torch, "cuda", None) is not None and torch.cuda.is_available() else "cpu"
    outs = []
    for ch in range(a.shape[1]):
        wav, osr = _rd(torch.from_numpy(np.ascontiguousarray(a[:, ch])), sr, dev)
        y = wav.detach().cpu().numpy().astype("float32") if hasattr(wav, "detach") else np.asarray(wav, dtype="float32")
        if int(osr) != sr and len(y):
            t_new = np.arange(len(a)) / sr
            y = np.interp(t_new, np.arange(len(y)) / float(osr), y).astype("float32")
        outs.append(np.pad(y, (0, max(0, len(a) - len(y))))[: len(a)])
    return np.stack(outs, axis=1).astype("float32")


_INSTALL: dict[str, Any] = {"state": "idle", "pct": 0, "text": ""}
_INSTALL_LOCK = threading.Lock()


def install_model(confirm: bool = False, runner: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Kullanicinin acik dugmesiyle (confirm=True) paket + model kurulumu. pip --target ile ayar klasorune
    kurulur (uygulama dosyalarina dokunmaz). runner testte sahte subprocess.Popen verilir."""
    if not confirm:
        return {"ok": False, "error": "confirm_required", "info": model_info()}
    if advanced_available():
        return {"ok": True, "installed": True, "already": True}
    if not _INSTALL_LOCK.acquire(blocking=False):
        return {"ok": False, "error": "busy"}
    try:
        target = models_dir() / "site"
        target.mkdir(parents=True, exist_ok=True)
        py = sys.executable
        cmd = [py, "-m", "pip", "install", "--disable-pip-version-check", "--progress-bar", "off",
               "--target", str(target), ADVANCED["package"]]
        _INSTALL.update(state="running", pct=1, text="Paket indiriliyor…")
        popen = runner or subprocess.Popen
        proc = popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=NO_WINDOW)
        n = 0
        for line in proc.stdout or []:
            n += 1
            line = str(line).strip()
            if line.startswith(("Collecting", "Downloading", "Installing", "Successfully")):
                _INSTALL.update(pct=min(95, 2 + n), text=line[:120])
        rc = proc.wait()
        if rc != 0:
            _INSTALL.update(state="error", text=f"pip çıkış kodu {rc}")
            return {"ok": False, "error": f"pip_failed_{rc}"}
        importlib.invalidate_caches()
        ok = advanced_available()
        _INSTALL.update(state="done" if ok else "error", pct=100 if ok else _INSTALL["pct"],
                        text="Kuruldu (model ağırlıkları ilk kullanımda indirilir)" if ok else "Paket bulunamadı")
        return {"ok": ok, "installed": ok}
    except Exception as exc:
        log.warning("Gelismis model kurulamadi", exc_info=True)
        _INSTALL.update(state="error", text=str(exc)[:120])
        return {"ok": False, "error": str(exc)[:160]}
    finally:
        _INSTALL_LOCK.release()


# ---------------- b) nefes ----------------
def _frames_feats(m, sr: int, hop: int, nwin: int = 1024):
    """Cerceve ozellikleri: enerji (dB), spektral duzluk (500 Hz-8 kHz), yuksek frekans orani (>1.5 kHz)."""
    import numpy as np
    n = len(m)
    nfr = max(0, 1 + (n - nwin) // hop) if n >= nwin else 0
    if nfr == 0:
        return np.zeros(0), np.zeros(0), np.zeros(0)
    idx = np.arange(nwin)[None, :] + hop * np.arange(nfr)[:, None]
    fr = m[idx]
    e_db = 10 * np.log10(np.maximum(np.mean(fr[:, (nwin - hop) // 2:(nwin + hop) // 2] ** 2, axis=1), 1e-14))
    P = np.abs(np.fft.rfft(fr * np.hanning(nwin)[None, :], axis=1)) ** 2 + 1e-18
    f = np.fft.rfftfreq(nwin, 1.0 / sr)
    band = (f >= 500) & (f <= 8000)
    Pb = P[:, band]
    flat = np.exp(np.mean(np.log(Pb), axis=1)) / np.mean(Pb, axis=1)
    hf = P[:, f >= 1500].sum(axis=1) / np.maximum(P[:, f >= 80].sum(axis=1), 1e-18)
    return e_db, flat, hf


def detect_breaths(data, sr: int = SR) -> list[list[Any]]:
    """Nefes bolgeleri [[t0, t1, True], ...] (kaynak zamani, sn)."""
    import numpy as np
    m = _mono(data).astype("float64")
    hop = int(0.01 * sr)
    e, flat, hf = _frames_feats(m, sr, hop)
    if not len(e):
        return []
    floor = float(np.percentile(e, 10))
    speech = float(np.percentile(e, 95))
    if speech - floor < 15.0:
        return []
    voiced = (e > speech - 22.0) & (flat < 0.12)
    cand = (e > floor + 6.0) & (e < speech - 12.0) & (flat > 0.18) & (hf > 0.35) & ~voiced
    # 1 cercevelik bosluklari kapat
    c = cand.copy()
    c[1:-1] |= cand[:-2] & cand[2:]
    out = []
    i, nfr = 0, len(c)
    off = (1024 - hop) / 2.0 / sr
    while i < nfr:
        if not c[i]:
            i += 1
            continue
        j = i
        while j + 1 < nfr and c[j + 1]:
            j += 1
        t0, t1 = i * hop / sr + off, (j + 1) * hop / sr + off
        d = t1 - t0
        if BREATH_MIN <= d <= BREATH_MAX:
            k1 = min(nfr, j + 1 + int(BREATH_SPEECH_GAP * sr / hop))
            if voiced[j + 1:k1].any():                 # sozlu sesten once gelir
                out.append([round(t0, 4), round(t1, 4), True])
        i = j + 1
    return out


def breath_gain(n: int, sr: int, regions: list[list[Any]], db: float = -10.0, remove: bool = False):
    """Ornek duzeyinde kazanc zarfi: acik bolgelerde 10 ms rampalarla db (ya da 0) kisma."""
    import numpy as np
    g = np.ones(n, dtype="float32")
    target = 0.0 if remove else 10 ** (float(db) / 20.0)
    r = int(BREATH_RAMP * sr)
    for reg in regions or []:
        if len(reg) > 2 and not reg[2]:
            continue
        a, b = int(round(float(reg[0]) * sr)), int(round(float(reg[1]) * sr))
        a, b = max(0, a), min(n, b)
        if b - a < 2:
            continue
        rr = min(r, (b - a) // 2)
        seg = np.full(b - a, target, dtype="float32")
        if rr > 0:
            seg[:rr] = np.linspace(1.0, target, rr, endpoint=False)
            seg[-rr:] = np.linspace(target, 1.0, rr + 1)[1:]
        g[a:b] = np.minimum(g[a:b], seg)
    return g


# ---------------- c) agiz sesi / tik ----------------
def detect_clicks(data, sr: int = SR, strength: float = 50.0) -> list[tuple[int, int]]:
    """[(a, b), ...] ornek araliklari (b haric). Ikinci fark |x[n] - (x[n-1]+x[n+1])/2| yerel medyanin k katini
    ve mutlak tabani asarsa isaretlenir; 1 ms'den yakin isaretler birlesir; 10 ms'den uzunlar tik sayilmaz."""
    import numpy as np
    a = np.asarray(data, dtype="float64")
    if a.ndim == 1:
        a = a[:, None]
    n = len(a)
    if n < 8:
        return []
    d = np.zeros(n)
    d[1:-1] = np.max(np.abs(a[1:-1] - 0.5 * (a[:-2] + a[2:])), axis=1)
    blk = 1024
    nb = (n + blk - 1) // blk
    med = np.array([np.median(d[i * blk:(i + 1) * blk]) for i in range(nb)])
    # komsu bloklarin en buyugu: sureklilik (sibilant) bolgesinde esik yukselir
    medn = np.maximum.reduce([med, np.r_[med[1:], med[-1]], np.r_[med[0], med[:-1]]])
    local = np.repeat(medn, blk)[:n]
    s = max(0.0, min(100.0, float(strength))) / 100.0
    k = 16.0 - 10.0 * s                         # siddet 0 -> 16x, 100 -> 6x (guvenli esik)
    thr = np.maximum(k * local, 0.004 + 0.012 * (1.0 - s))
    flag = np.flatnonzero(d > thr)
    if not len(flag):
        return []
    gap = max(1, int(0.001 * sr))
    maxlen = int(CLICK_MAX_MS / 1000.0 * sr)
    out = []
    st = pv = int(flag[0])
    for x in flag[1:]:
        x = int(x)
        if x - pv <= gap:
            pv = x
            continue
        out.append((st, pv + 1))
        st = pv = x
    out.append((st, pv + 1))
    return [(max(2, s0 - 2), min(n - 2, e0 + 2)) for s0, e0 in out if e0 - s0 <= maxlen and min(n - 2, e0 + 2) > max(2, s0 - 2)]


AR_ORDER = 32
AR_CTX = 768


def _ar_predict(ctx, order: int, steps: int):
    """ctx'e (en yeni ornek sonda) AR(order) uydurup steps ornek ileri tahmin. Uydurulamazsa None."""
    import numpy as np
    x = np.asarray(ctx, dtype="float64")
    if len(x) < order * 3 or steps <= 0:
        return None
    A = np.lib.stride_tricks.sliding_window_view(x[:-1], order)[:, ::-1]
    y = x[order:]
    try:
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    except Exception:
        return None
    hist = list(x[-order:][::-1])
    out = np.empty(steps)
    for i in range(steps):
        v = float(np.dot(coef, hist))
        out[i] = v
        hist.insert(0, v)
        hist.pop()
    peak = float(np.max(np.abs(x))) * 1.5 + 1e-6
    return np.clip(out, -peak, peak)


def _ar_fill(col, p0: int, p1: int):
    """[p0+1, p1) boslugunu sol baglamdan ileri ve sag baglamdan geri AR tahmini ile, kosinus gecisle doldurur."""
    import numpy as np
    L = p1 - p0 - 1
    left = col[max(0, p0 + 1 - AR_CTX):p0 + 1]
    right = col[p1:p1 + AR_CTX][::-1]
    order = min(AR_ORDER, max(4, min(len(left), len(right)) // 4))
    f = _ar_predict(left, order, L)
    b = _ar_predict(right, order, L)
    if f is None or b is None:
        return None
    w = 0.5 - 0.5 * np.cos(np.pi * (np.arange(1, L + 1) / (L + 1)))
    return (f * (1.0 - w) + b[::-1] * w).astype("float32")


def declick(data, sr: int = SR, strength: float = 50.0, events: list[tuple[int, int]] | None = None):
    """Tik araliklarini doldurur: kisa olanlar kubik Hermite (uc noktalar + egimler), 16 ornekten uzunlar
    (smack) AR tahmini (ileri + geri, kosinus gecis; olmazsa Hermite). Diger ornekler birebir."""
    import numpy as np
    a = np.array(data, dtype="float32", copy=True)
    two = a.ndim == 2
    if not two:
        a = a[:, None]
    ev = detect_clicks(a, sr, strength) if events is None else events
    n = len(a)
    for s0, e0 in ev:
        p0, p1 = s0 - 1, e0                     # degismeyen uc ornekler
        L = p1 - p0
        if L > 16:
            fills = [_ar_fill(a[:, ch], p0, p1) for ch in range(a.shape[1])]
            if all(fl is not None for fl in fills):
                for ch, fl in enumerate(fills):
                    a[p0 + 1:p1, ch] = fl
                continue
        q = max(1, min(16, L // 8))             # egim, uc noktanin q ornek komsulugundan (uzun boslukta tiz buyumesin)
        if p0 < q or p1 > n - 1 - q:
            continue
        t = (np.arange(1, L) / L)[:, None]
        y0, y1 = a[p0], a[p1]
        m0 = (a[p0] - a[p0 - q]) / q * L
        m1 = (a[p1 + q] - a[p1]) / q * L
        h00 = 2 * t ** 3 - 3 * t ** 2 + 1
        h10 = t ** 3 - 2 * t ** 2 + t
        h01 = -2 * t ** 3 + 3 * t ** 2
        h11 = t ** 3 - t ** 2
        a[p0 + 1:p1] = (h00 * y0 + h10 * m0 + h01 * y1 + h11 * m1).astype("float32")
    return a if two else a[:, 0]


# ---------------- oner + uygula ----------------
_PROG: dict[str, Any] = {"state": "idle", "pct": 0, "text": "", "path": ""}
_PROG_LOCK = threading.Lock()


def progress() -> dict[str, Any]:
    with _PROG_LOCK:
        return dict(_PROG)


def _prog(pct: float, text: str, state: str = "running", path: str = "") -> None:
    with _PROG_LOCK:
        _PROG.update(state=state, pct=int(max(0, min(100, pct))), text=text)
        if path:
            _PROG["path"] = path


def _read(path: str):
    from app.core import beat_studio
    data, _ = beat_studio._read_audio_np(path, SR)
    return data


def analyze(path: str, data=None) -> dict[str, Any]:
    """Oneri: gurultu tabani + profil bolgesi, nefes bolgeleri, tik sayisi; onerilen ac/kapa + siddet."""
    import numpy as np
    if data is None:
        if not path or not os.path.isfile(path):
            return {"ok": False, "error": "file_not_found"}
        _prog(5, "Kayıt okunuyor…", path=path)
        try:
            data = _read(path)
        except Exception as exc:
            _prog(0, "Okunamadı", "error")
            return {"ok": False, "error": str(exc)[:160]}
    data = np.asarray(data, dtype="float32")
    _prog(30, "Gürültü profili çıkarılıyor…")
    prof = noise_profile(data, SR)
    _prog(55, "Nefesler aranıyor…")
    breaths = detect_breaths(data, SR)
    _prog(80, "Ağız sesleri aranıyor…")
    clicks = detect_clicks(data, SR, 50.0)
    fl = prof["floor_db"]
    n_on = fl > -66.0
    n_str = round(max(20.0, min(85.0, 20.0 + (fl + 70.0) * 2.2)), 0)
    _prog(100, "Öneri hazır", "done")
    return {"ok": True, "path": path, "duration": round(len(data) / SR, 4),
            "noise": {"floor_db": fl, "profile": [prof["t0"], prof["t1"]],
                      "suggest": {"on": bool(n_on), "strength": n_str, "method": "auto"},
                      "why": (f"Gürültü tabanı {fl:.0f} dBFS — {'temizlik önerilir' if n_on else 'zaten temiz'}"),
                      "advanced": advanced_available()},
            "breath": {"regions": breaths, "suggest": {"on": bool(breaths), "mode": "reduce", "db": -10.0},
                       "why": f"{len(breaths)} nefes bulundu (silinmez, kısılır)"},
            "click": {"count": len(clicks), "positions": [round(a / SR, 4) for a, _ in clicks[:300]],
                      "suggest": {"on": len(clicks) > 0, "strength": 50.0},
                      "why": f"{len(clicks)} ağız sesi/tık"}}


def process(data, settings: dict[str, Any], sr: int = SR,
            on_progress: Callable[[float, str], None] | None = None) -> tuple[Any, dict[str, Any]]:
    """Sira: tik giderme (ham uzerinde) -> gurultu -> nefes kismasi. Uzunluk korunur."""
    import numpy as np
    s = normalize_settings(settings)
    cb = on_progress or (lambda p, t: None)
    out = np.asarray(data, dtype="float32")
    info: dict[str, Any] = {"clicks": 0, "breaths": 0, "noise_method": "", "notes": []}
    if s["click"]["on"]:
        cb(15, "Ağız sesleri temizleniyor…")
        ev = detect_clicks(out, sr, s["click"]["strength"])
        out = declick(out, sr, s["click"]["strength"], ev)
        info["clicks"] = len(ev)
    if s["noise"]["on"]:
        cb(40, "Gürültü azaltılıyor…")
        out, ni = denoise(out, sr, s["noise"]["strength"], s["noise"]["method"])
        info["noise_method"] = ni["method"]
        if ni.get("note"):
            info["notes"].append(ni["note"])
    if s["breath"]["on"]:
        regs = [r for r in s["breath"]["regions"] if r[2]]
        if regs:
            cb(80, "Nefesler kısılıyor…")
            g = breath_gain(len(out), sr, regs, s["breath"]["db"], s["breath"]["mode"] == "remove")
            out = (out * g[:, None]).astype("float32")
            info["breaths"] = len(regs)
    return np.ascontiguousarray(out, dtype="float32"), info


def apply(path: str, settings: dict[str, Any]) -> dict[str, Any]:
    """Temizlik dosyasini uretir (ya da onbellekten verir). Ham dosya yalniz okunur."""
    if not path or not os.path.isfile(path):
        return {"ok": False, "error": "file_not_found"}
    s = normalize_settings(settings)
    if not any_on(s):
        return {"ok": False, "error": "nothing_selected"}
    out = cache_path(path, s)
    key = out.stem
    if out.is_file():
        _prog(100, "Hazır (önbellek)", "done", path)
        return {"ok": True, "file": str(out), "key": key, "cached": True, "settings": s}
    tm = time.monotonic()
    try:
        _prog(3, "Kayıt okunuyor…", path=path)
        data = _read(path)
        res, info = process(data, s, SR, lambda p, t: _prog(p, t))
        _prog(92, "Dosya yazılıyor…")
        tmp = out.with_suffix(".part.wav")
        write_wav_f32(str(tmp), res, SR)
        os.replace(tmp, out)
    except Exception as exc:
        log.warning("Temizlik basarisiz", exc_info=True)
        _prog(0, "Hata: " + str(exc)[:80], "error")
        return {"ok": False, "error": str(exc)[:160]}
    _prog(100, "Temizlik hazır", "done")
    return {"ok": True, "file": str(out), "key": key, "cached": False, "settings": s, "info": info,
            "ms": int((time.monotonic() - tm) * 1000)}


def clip_clean_field(path: str, settings: dict[str, Any], res: dict[str, Any]) -> dict[str, Any]:
    """Klibe yazilacak alan (arayuz de ayni yapiyi kurar)."""
    s = normalize_settings(settings)
    return {"noise": s["noise"], "breath": s["breath"], "click": s["click"], "file": res.get("file", ""),
            "src": path, "key": res.get("key", "")}
