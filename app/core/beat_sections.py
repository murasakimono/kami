"""Kami Beat Asama 1c: beat analizi + bolum haritasi (intro/verse/nakarat/kopru/outro tahmini).

Yol: bar basina ozellik vektoru (log bant enerjileri + RMS) -> komsu pencere farkindan yenilik egrisi ->
tepe secimi (en az MIN_SECTION_BARS bar) -> sinirlar bar izgarasina oturur -> benzer bolumler gruplanir ->
etiket kurallari (tekrar eden + en yuksek enerjili grup = Nakarat, ilk dusuk enerji = Intro ...).
librosa varsa ozellikler MFCC + chroma ile (daha iyi tekrar algisi); yoksa saf numpy enerji/bant yedegi.
Etiketler TAHMINDIR; kullanici cift tikla yeniden adlandirir.
"""
from __future__ import annotations

import logging
import math
import threading
import time
import uuid
from typing import Any

log = logging.getLogger(__name__)

MIN_SECTION_BARS = 4
ANALYSIS_SR = 22050
_BANDS = (0, 150, 400, 1000, 2500, 6000, 11025)

_PROGRESS_LOCK = threading.Lock()
PROGRESS: dict[str, Any] = {"pid": "", "stage": "", "pct": 0, "running": False, "t": 0.0}


def _set_progress(pid: str, stage: str, pct: int, running: bool = True) -> None:
    with _PROGRESS_LOCK:
        PROGRESS.update({"pid": pid, "stage": stage, "pct": int(pct), "running": running, "t": time.time()})


def get_progress() -> dict[str, Any]:
    with _PROGRESS_LOCK:
        return dict(PROGRESS)


def has_librosa() -> bool:
    try:
        import librosa  # noqa: F401
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- ozellikler
def _bar_spans(n_samples: int, sr: int, bar: float, offset: float) -> list[tuple[int, int, int]]:
    """Zaman cizelgesi bar izgarasi (0'dan) ile kesisen barlar: [(bar_indeksi, s0, s1)] ornek araliklari.
    offset = sesin 0. orneginin zaman cizelgesindeki konumu. Yarisindan azi seste olan barlar atilir."""
    dur = n_samples / float(sr)
    out: list[tuple[int, int, int]] = []
    if bar <= 0 or dur <= 0:
        return out
    k0 = int(math.floor(offset / bar + 1e-9))
    k1 = int(math.ceil((offset + dur) / bar - 1e-9))
    for k in range(max(0, k0), k1):
        a = max(0.0, k * bar - offset)
        b = min(dur, (k + 1) * bar - offset)
        if b - a >= bar * 0.5:
            out.append((k, int(round(a * sr)), int(round(b * sr))))
    return out


def _bar_features_numpy(mono, sr: int, spans):
    import numpy as np
    feats = []
    win = 2048
    freqs = np.fft.rfftfreq(win, 1.0 / sr)
    band_idx = [(freqs >= lo) & (freqs < hi) for lo, hi in zip(_BANDS[:-1], _BANDS[1:])]
    hann = np.hanning(win).astype("float32")
    for _, s0, s1 in spans:
        seg = mono[s0:s1]
        rms = float(np.sqrt(np.mean(seg.astype("float64") ** 2))) if len(seg) else 0.0
        n_fr = max(1, (len(seg) - win) // win + 1)
        acc = np.zeros(len(band_idx))
        cnt = 0
        for i in range(n_fr):
            fr = seg[i * win:(i + 1) * win]
            if len(fr) < win:
                break
            sp = np.abs(np.fft.rfft(fr * hann)) ** 2
            acc += np.array([sp[m].sum() for m in band_idx])
            cnt += 1
        acc = acc / max(1, cnt)
        feats.append([20.0 * math.log10(max(rms, 1e-6))] + [10.0 * math.log10(max(v, 1e-10)) for v in acc])
    return np.asarray(feats, dtype="float64")


def _bar_features_librosa(mono, sr: int, spans):
    import librosa
    import numpy as np
    hop = 512
    mf = librosa.feature.mfcc(y=mono, sr=sr, n_mfcc=13, hop_length=hop)
    ch = librosa.feature.chroma_stft(y=mono, sr=sr, hop_length=hop)
    rms = librosa.feature.rms(y=mono, hop_length=hop)[0]
    feats = []
    for _, s0, s1 in spans:
        f0, f1 = s0 // hop, max(s0 // hop + 1, s1 // hop)
        r = float(np.mean(rms[f0:f1])) if f1 > f0 else 0.0
        feats.append(np.concatenate([[20.0 * math.log10(max(r, 1e-6))], mf[:, f0:f1].mean(axis=1),
                                     ch[:, f0:f1].mean(axis=1) * 10.0]))
    return np.asarray(feats, dtype="float64")


# ---------------------------------------------------------------- sinir + etiket
def _novelty(z, w: int = 2):
    import numpy as np
    n = len(z)
    nov = np.zeros(n)
    for k in range(1, n):
        a = z[max(0, k - w):k].mean(axis=0)
        b = z[k:min(n, k + w)].mean(axis=0)
        nov[k] = float(np.linalg.norm(a - b))
    return nov


def _pick_boundaries(nov, n: int, min_len: int) -> list[int]:
    """Guclu tepeden zayifa: her sinir iki yandaki sinirlara/uclara en az min_len bar uzaklikta olmali."""
    import numpy as np
    if n < 2 * min_len:
        return []
    vals = nov[1:]
    thr = float(np.mean(vals) + 0.5 * np.std(vals))
    cand = [k for k in range(1, n) if nov[k] >= thr and nov[k] >= nov[k - 1] and (k + 1 >= n or nov[k] >= nov[k + 1])]
    cand.sort(key=lambda k: -nov[k])
    chosen: list[int] = []
    for k in cand:
        if k < min_len or n - k < min_len:
            continue
        if all(abs(k - c) >= min_len for c in chosen):
            chosen.append(k)
    return sorted(chosen)


def _group_segments(means) -> list[int]:
    """Ortalama vektoru birbirine yakin bolumleri ayni gruba koyar (basit tek baglantili kumeleme)."""
    import numpy as np
    m = len(means)
    if m == 0:
        return []
    d = np.zeros((m, m))
    for i in range(m):
        for j in range(m):
            d[i, j] = float(np.linalg.norm(means[i] - means[j]))
    mx = float(d.max()) or 1.0
    thr = 0.3 * mx
    gid = list(range(m))

    def find(x: int) -> int:
        while gid[x] != x:
            x = gid[x]
        return x

    for i in range(m):
        for j in range(i + 1, m):
            if d[i, j] <= thr:
                gid[find(j)] = find(i)
    roots: dict[int, int] = {}
    return [roots.setdefault(find(i), len(roots)) for i in range(m)]


def label_segments(energy: list[float], groups: list[int]) -> list[str]:
    """Kurallar: (1) tekrar eden gruplar icinde ortalama enerjisi en yuksek olan = Nakarat (tekrar yoksa en
    yuksek enerjili bolum); (2) ilk bolum dusuk enerjiliyse Intro, son bolum dusuk enerjiliyse Outro;
    (3) kalan tekrar edenler Verse; ilk ve son nakarat arasindaki tekil bolum Koprü; digerleri Verse.
    Verse'ler sirayla numaralanir."""
    m = len(energy)
    if m == 0:
        return []
    labels = [""] * m
    srt = sorted(energy)
    med = srt[m // 2]
    lo_thr = med - 4.0
    members: dict[int, list[int]] = {}
    for i, g in enumerate(groups):
        members.setdefault(g, []).append(i)
    rep = {g: ix for g, ix in members.items() if len(ix) >= 2}
    if rep:
        chorus_g = max(rep, key=lambda g: sum(energy[i] for i in rep[g]) / len(rep[g]))
        chorus_ix = set(rep[chorus_g])
    else:
        chorus_ix = {max(range(m), key=lambda i: energy[i])}
    top = max(energy)
    if True:
        # tekrar eden nakarat adayi belirgin bicimde sessizse (or. tekrarli intro/outro) en yuksek enerjiye don
        if max(energy[i] for i in chorus_ix) < top - 6.0:
            chorus_ix = {max(range(m), key=lambda i: energy[i])}
    for i in chorus_ix:
        labels[i] = "Nakarat"
    if m >= 2 and not labels[0] and energy[0] <= lo_thr:
        labels[0] = "Intro"
    if m >= 3 and not labels[-1] and energy[-1] <= lo_thr:
        labels[-1] = "Outro"
    ch_sorted = sorted(chorus_ix)
    first_ch, last_ch = ch_sorted[0], ch_sorted[-1]
    for i in range(m):
        if labels[i]:
            continue
        single = len(members[groups[i]]) < 2
        labels[i] = "Köprü" if (single and first_ch < i < last_ch) else "Verse"
    nv = sum(1 for x in labels if x == "Verse")
    if nv > 1:
        k = 0
        for i in range(m):
            if labels[i] == "Verse":
                k += 1
                labels[i] = f"Verse {k}"
    return labels


def detect_sections(mono, sr: int, bpm: float, offset: float = 0.0, beats_per_bar: int = 4,
                    use_librosa: bool | None = None, min_bars: int = MIN_SECTION_BARS) -> dict[str, Any]:
    """mono: float dizi (zaman cizelgesinde offset'te baslar). Donus: {ok, sections:[{id,name,start,end}],
    engine, bars}. Bolum sinirlari zaman cizelgesi bar izgarasinda (0'dan, bpm'e gore)."""
    import numpy as np
    mono = np.asarray(mono, dtype="float32").reshape(-1)
    bpm = float(bpm or 0) or 120.0
    bar = 60.0 / bpm * max(1, int(beats_per_bar or 4))
    spans = _bar_spans(len(mono), sr, bar, float(offset or 0.0))
    if not spans:
        return {"ok": False, "error": "too_short", "sections": []}
    engine = "numpy"
    feats = None
    if use_librosa is None:
        use_librosa = has_librosa()
    if use_librosa:
        try:
            feats = _bar_features_librosa(mono, sr, spans)
            engine = "librosa"
        except Exception:
            log.debug("librosa ozellikleri alinamadi, numpy yedegi", exc_info=True)
            feats = None
    if feats is None:
        feats = _bar_features_numpy(mono, sr, spans)
    n = len(feats)
    energy_bar = feats[:, 0]
    mu = feats.mean(axis=0)
    sd = feats.std(axis=0)
    sd[sd < 1e-6] = 1.0
    z = (feats - mu) / sd
    z[:, 0] *= 1.5            # yukseklik/enerji degisimi bolum sinirinin en guclu ipucu
    bounds = _pick_boundaries(_novelty(z), n, max(1, int(min_bars)))
    edges = [0] + bounds + [n]
    segs = [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]
    means = [z[a:b].mean(axis=0) for a, b in segs]
    groups = _group_segments(means)
    # komsu ve ayni gruptaki bolumleri birlestir
    merged: list[tuple[int, int, int]] = []
    for (a, b), g in zip(segs, groups):
        if merged and merged[-1][2] == g:
            merged[-1] = (merged[-1][0], b, g)
        else:
            merged.append((a, b, g))
    energy = [float(np.mean(energy_bar[a:b])) for a, b, _ in merged]
    labels = label_segments(energy, [g for _, _, g in merged])
    first_k = spans[0][0]
    sections = []
    for (a, b, _), name, e in zip(merged, labels, energy):
        ka = spans[a][0] if a > 0 else first_k
        kb = spans[b - 1][0] + 1
        sections.append({
            "id": "s_" + uuid.uuid4().hex[:8], "name": name,
            "start": round(ka * bar, 6), "end": round(kb * bar, 6),
            "energy_db": round(e, 1),
        })
    return {"ok": True, "sections": sections, "engine": engine, "bars": n, "bar_sec": round(bar, 6)}


# ---------------------------------------------------------------- proje analizi (arka plan isi)
def _beat_source(proj: dict[str, Any]) -> dict[str, Any] | None:
    """Beat kanalindaki duyulan en uzun klip: {path, src_in, src_out, start}."""
    from app.core import beat_clips
    tr = next((t for t in proj.get("tracks", []) or [] if t.get("role") == "beat"), None)
    if not tr:
        return None
    clips = [c for c in beat_clips.stack_view(tr.get("clips") or []) if not c.get("muted") and c.get("path")]
    if not clips:
        return None
    c = max(clips, key=lambda x: float(x.get("src_out", 0)) - float(x.get("src_in", 0)))
    return {"path": str(c["path"]), "src_in": float(c.get("src_in") or 0.0),
            "src_out": float(c.get("src_out") or 0.0), "start": float(c.get("start") or 0.0)}


def analyze_project(pid: str, path: str = "") -> dict[str, Any]:
    """BPM + ton + bolum haritasi. Projeye YAZMAZ (arayuz sonucu tek geri-al adimi olarak uygular)."""
    import os

    from app.core import beat_studio, kami_beat
    _set_progress(pid, "Beat okunuyor", 5)
    try:
        src = None
        if not path:
            lr = beat_studio.load_project(pid)
            if not lr.get("ok"):
                return {"ok": False, "error": lr.get("error") or "not_found"}
            src = _beat_source(lr["project"])
            if not src:
                return {"ok": False, "error": "no_beat"}
            path = src["path"]
        if not os.path.isfile(path):
            return {"ok": False, "error": "file_missing"}
        _set_progress(pid, "Tempo ölçülüyor", 15)
        try:
            bpm = float(kami_beat.analyze_bpm(path) or 0.0)
        except Exception:
            bpm = 0.0
        _set_progress(pid, "Ton bulunuyor", 30)
        try:
            key = kami_beat.detect_key(path) or {}
        except Exception:
            key = {}
        _set_progress(pid, "Ses çözülüyor", 45)
        data, sr = beat_studio._read_audio_np(path, ANALYSIS_SR)
        mono = data.mean(axis=1)
        offset = 0.0
        if src:
            s0 = int(round(src["src_in"] * sr))
            s1 = int(round(src["src_out"] * sr)) if src["src_out"] > src["src_in"] else len(mono)
            mono = mono[s0:s1]
            offset = src["start"]
        _set_progress(pid, "Bölümler aranıyor", 70)
        use_bpm = bpm if bpm > 0 else 120.0
        res = detect_sections(mono, sr, use_bpm, offset=offset)
        _set_progress(pid, "Bitti", 100, running=False)
        if not res.get("ok"):
            return res
        res.update({"bpm": round(bpm, 1) if bpm > 0 else 0.0, "key": key.get("key", ""),
                    "camelot": key.get("camelot", ""), "path": path})
        return res
    except Exception as exc:
        log.exception("Beat analizi hatasi")
        return {"ok": False, "error": str(exc)[:140]}
    finally:
        with _PROGRESS_LOCK:
            PROGRESS["running"] = False
