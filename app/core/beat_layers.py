"""Kami Beat Asama 1d: kanal ekle/sil/sirala + vokal katmanlari (Double / Adlib / Chant).

Saf fonksiyonlar (yan etkisiz; her zaman yeni liste/sozluk dondurur). Arayuz (beat.js) kanal listesini
bu modulun API sarmalayicilarina (beat_tracks_op / beat_layer_prepare / beat_layer_layout) gonderir ve donen
listeyi tek geri al adimi olarak uygular -> mantik tek yerde (Python), JS kopyasi yok.

Katman alanlari (kanal):
    layer      : "" | "double" | "adlib" | "chant"   (bos = normal kanal / ana vokal)
    layer_of   : katmanin ait oldugu ana vokal kanalinin id'si
    auto_place : True ise pan/ses otomatik yerlesim kurallarina gore guncellenir (kullanici surguye dokununca False)
    chant_dev  : {delay_ms, cents}  (yalniz chant; deterministik tohumdan)
    color      : istege bagli kanal rengi (#RRGGBB)

Hizalama (align_signals): kisa pencerelerde (250 ms) baslangic-enerjisi zarfinin capraz korelasyonu ile yerel
kayma; sonuc sabit ofset ya da (yerel kaymalar belirgin farkliysa) klibi parca parca bolup her parcayi
kaydirma onerisidir. Ses esnetilmez (kalite bozulmaz).
"""
from __future__ import annotations

import math
import re
import uuid
from typing import Any

from app.core import beat_clips

LAYER_KINDS = ("double", "adlib", "chant")
TRACK_ROLES = ("vocal", "beat", "fx")
PROTECTED_TRACKS = ("beat", "vocal1")        # temel kanallar silinmez (beat_mcp / booth varsayilanlari bunlara bakar)
MAX_TRACKS = 24
CHANT_MAX = 4
DOUBLE_MAX = 4
TRACK_PALETTE = ("#9D6BFF", "#F59E0B", "#38BDF8", "#EC4899", "#A3E635", "#F97316", "#2DD4BF", "#E879F9")
LAYER_NAMES = {"double": "Double", "adlib": "Adlib", "chant": "Chant"}
LAYER_PRESET = {"double": "double_layer", "adlib": "adlib_layer", "chant": "chant_layer"}
ROLE_NAMES = {"vocal": "Vokal", "beat": "Beat", "fx": "FX / Efekt"}


def _r3(x: float) -> float:
    return math.floor(float(x) * 1000.0 + 0.5) / 1000.0


def _r1(x: float) -> float:
    return math.floor(float(x) * 10.0 + 0.5) / 10.0


# ---------------- deterministik tohum (chant sapmalari) ----------------
def _u32(x: int) -> int:
    return x & 0xFFFFFFFF


def _imul(a: int, b: int) -> int:
    return _u32(_u32(a) * _u32(b))


def fnv1a(text: str) -> int:
    h = 0x811C9DC5
    for ch in str(text or ""):
        h = _imul(h ^ (ord(ch) & 0xFFFF), 0x01000193)
    return h


def mulberry32(seed: int):
    state = _u32(int(seed))

    def nxt() -> float:
        nonlocal state
        state = _u32(state + 0x6D2B79F5)
        a = state
        t = _imul(a ^ (a >> 15), 1 | a)
        t = _u32(t + _imul(t ^ (t >> 7), 61 | t)) ^ t
        return _u32(t ^ (t >> 14)) / 4294967296.0
    return nxt


def chant_deviation(seed: int, index: int) -> dict[str, float]:
    """index. chant take'i icin 5-15 ms gecikme ve +-8 cent sapma (ayni tohum -> ayni sonuc)."""
    rnd = mulberry32(_u32(int(seed) + int(index) * 7919))
    delay = 5.0 + 10.0 * rnd()
    cents = -8.0 + 16.0 * rnd()
    return {"delay_ms": _r1(delay), "cents": _r1(cents)}


def chant_deviations(seed: int, n: int) -> list[dict[str, float]]:
    return [chant_deviation(seed, i) for i in range(max(0, int(n)))]


# ---------------- yerlesim kurallari ----------------
def placement(kind: str, index: int, count: int) -> dict[str, Any]:
    """Katman kanalinin pan / ses (dB) / onayar karari.
    double: tek double -> pan +0.3, -6 dB; 2+ double -> L/R cifti -0.6 / +0.6 (her biri -3 dB)
    adlib : donusumlu -0.5 / +0.5, -4 dB
    chant : take'ler yan yana kanallarda -0.7..+0.7'ye esit yayilir, -6 dB."""
    kind = str(kind or "")
    index, count = max(0, int(index)), max(1, int(count))
    if kind == "double":
        if count == 1:
            return {"pan": 0.3, "volume_db": -6.0, "preset": LAYER_PRESET["double"]}
        return {"pan": -0.6 if index % 2 == 0 else 0.6, "volume_db": -3.0, "preset": LAYER_PRESET["double"]}
    if kind == "adlib":
        return {"pan": -0.5 if index % 2 == 0 else 0.5, "volume_db": -4.0, "preset": LAYER_PRESET["adlib"]}
    if kind == "chant":
        pan = 0.0 if count == 1 else _r3(-0.7 + 1.4 * index / (count - 1))
        return {"pan": pan, "volume_db": -6.0, "preset": LAYER_PRESET["chant"]}
    return {"pan": 0.0, "volume_db": 0.0, "preset": ""}


# ---------------- kanal islemleri ----------------
def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(text or "").lower()).strip("_")
    return s[:16] or "kanal"


def unique_track_id(tracks: list[dict[str, Any]], base: str) -> str:
    used = {str(t.get("id")) for t in tracks}
    base = _slug(base)
    if base not in used:
        return base
    n = 2
    while f"{base}_{n}" in used:
        n += 1
    return f"{base}_{n}"


def unique_name(tracks: list[dict[str, Any]], base: str) -> str:
    used = {str(t.get("name")) for t in tracks}
    if base not in used:
        return base
    n = 2
    while f"{base} {n}" in used:
        n += 1
    return f"{base} {n}"


def next_color(tracks: list[dict[str, Any]]) -> str:
    used = {str(t.get("color") or "").upper() for t in tracks}
    for c in TRACK_PALETTE:
        if c.upper() not in used:
            return c
    return TRACK_PALETTE[len(tracks) % len(TRACK_PALETTE)]


def new_track(tracks: list[dict[str, Any]], role: str = "vocal", name: str = "", color: str = "",
              tid: str = "", layer: str = "", layer_of: str = "") -> dict[str, Any]:
    """Varsayilan alanlariyla yeni kanal (listeye eklemez)."""
    role = role if role in TRACK_ROLES else "vocal"
    name = str(name or "").strip()[:40] or unique_name(tracks, LAYER_NAMES.get(layer) or ROLE_NAMES[role])
    col = str(color or "").strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", col):
        col = "#14F195" if role == "beat" else next_color(tracks)
    tr: dict[str, Any] = {
        "id": tid or unique_track_id(tracks, layer or name),
        "name": name, "role": role, "color": col,
        "path": "", "takes": [], "active_take": "", "volume_db": 0.0, "pan": 0.0, "mute": False, "solo": False,
        "offset_ms": 0.0, "latency_ms": 0.0, "clips": [], "denoise": False, "preset": "", "fx": [],
    }
    if layer in LAYER_KINDS:
        tr.update(layer=layer, layer_of=str(layer_of or "vocal1"), auto_place=True)
    return tr


def add_track(tracks: list[dict[str, Any]], track: dict[str, Any], index: int | None = None) -> list[dict[str, Any]]:
    out = list(tracks)
    if len(out) >= MAX_TRACKS or any(t.get("id") == track.get("id") for t in out):
        return out
    if index is None or index < 0 or index > len(out):
        out.append(track)
    else:
        out.insert(int(index), track)
    return out


def remove_track(tracks: list[dict[str, Any]], tid: str) -> list[dict[str, Any]]:
    if tid in PROTECTED_TRACKS:
        return list(tracks)
    return [t for t in tracks if t.get("id") != tid]


def move_track(tracks: list[dict[str, Any]], tid: str, to_index: int) -> list[dict[str, Any]]:
    out = list(tracks)
    i = next((k for k, t in enumerate(out) if t.get("id") == tid), -1)
    if i < 0:
        return out
    tr = out.pop(i)
    to = max(0, min(len(out), int(to_index)))
    out.insert(to, tr)
    return out


def reorder_tracks(tracks: list[dict[str, Any]], ids: list[str]) -> list[dict[str, Any]]:
    """ids sirasina gore; listede olmayan kanallar sondaki eski sirasiyla kalir."""
    by = {t.get("id"): t for t in tracks}
    out = [by[i] for i in ids if i in by]
    seen = {t.get("id") for t in out}
    return out + [t for t in tracks if t.get("id") not in seen]


def tracks_op(tracks: list[dict[str, Any]], op: str, args: dict[str, Any] | None = None,
              presets: dict[str, Any] | None = None) -> dict[str, Any]:
    """Arayuzun tek kapisi: add | remove | move | reorder | rename | recolor."""
    a = dict(args or {})
    tracks = [dict(t) for t in (tracks or []) if isinstance(t, dict)]
    if op == "add":
        if len(tracks) >= MAX_TRACKS:
            return {"ok": False, "error": "too_many_tracks"}
        tr = new_track(tracks, str(a.get("role") or "vocal"), str(a.get("name") or ""), str(a.get("color") or ""))
        if tr["role"] == "vocal" and presets and "clean_rap" in presets:
            tr["preset"] = "clean_rap"
            tr["fx"] = [dict(f) for f in presets["clean_rap"].get("fx", [])]
        return {"ok": True, "tracks": add_track(tracks, tr, a.get("index")), "track_id": tr["id"]}
    tid = str(a.get("id") or "")
    if op == "remove":
        if tid in PROTECTED_TRACKS:
            return {"ok": False, "error": "protected_track", "tracks": tracks}
        if not any(t.get("id") == tid for t in tracks):
            return {"ok": False, "error": "track_not_found", "tracks": tracks}
        return {"ok": True, "tracks": remove_track(tracks, tid)}
    if op == "move":
        return {"ok": True, "tracks": move_track(tracks, tid, int(a.get("index") or 0))}
    if op == "reorder":
        return {"ok": True, "tracks": reorder_tracks(tracks, [str(x) for x in a.get("ids") or []])}
    if op in ("rename", "recolor"):
        for t in tracks:
            if t.get("id") == tid:
                if op == "rename":
                    nm = str(a.get("name") or "").strip()[:40]
                    if nm:
                        t["name"] = nm
                else:
                    col = str(a.get("color") or "")
                    if re.fullmatch(r"#[0-9a-fA-F]{6}", col):
                        t["color"] = col
        return {"ok": True, "tracks": tracks}
    return {"ok": False, "error": "bad_op", "tracks": tracks}


# ---------------- katman kanallari ----------------
def layer_tracks(tracks: list[dict[str, Any]], kind: str, main_id: str) -> list[dict[str, Any]]:
    out = []
    for t in tracks:
        lay = t.get("layer")
        if lay == kind and (t.get("layer_of") or "vocal1") == main_id:
            out.append(t)
        elif kind == "adlib" and not lay and t.get("id") == "adlib" and main_id == "vocal1":
            out.append(t)            # varsayilan projedeki "Adlib / Back Vokal" kanali ana vokalin adlib'i sayilir
    return out


def _busy(tr: dict[str, Any], t0: float, t1: float) -> bool:
    probe = {"start": t0, "src_in": 0.0, "src_out": max(beat_clips.MIN_LEN, t1 - t0)}
    return any(beat_clips.overlaps(c, probe) for c in beat_clips.stack_view(list(tr.get("clips") or [])))


def _apply_preset(tr: dict[str, Any], preset: str, presets: dict[str, Any] | None) -> None:
    p = (presets or {}).get(preset)
    if p:
        tr["preset"] = preset
        tr["fx"] = [dict(f) for f in p.get("fx", [])]
        tr["denoise"] = bool(p.get("denoise"))


def prepare_layer(tracks: list[dict[str, Any]], kind: str, main_id: str, t0: float, t1: float,
                  seed: int = 0, presets: dict[str, Any] | None = None, pitch_ok: bool = False) -> dict[str, Any]:
    """Katman kaydinin hedef kanalini secer; yoksa olusturur (ana vokalin hemen altina).
    double: [t0,t1] araliginda bos olan ilk double kanali; hepsi doluysa yeni (en fazla 4)
    adlib : toplam adlib klibi sayisina gore donusumlu iki kanal (L/R)
    chant : her take yeni yan kanal (en fazla 4; sonra araligi bos olan ilk chant kanali)
    Donus: {ok, tracks, track_id, created, kind}."""
    if kind not in LAYER_KINDS:
        return {"ok": False, "error": "bad_layer"}
    tracks = [dict(t) for t in (tracks or [])]
    main = next((t for t in tracks if t.get("id") == main_id), None)
    if main is None:
        return {"ok": False, "error": "main_not_found"}
    mine = layer_tracks(tracks, kind, main_id)
    target = None
    if kind == "double":
        target = next((t for t in mine if not _busy(t, t0, t1)), None)
        if target is None and len(mine) >= DOUBLE_MAX:
            target = mine[-1]
    elif kind == "adlib":
        n = sum(len(beat_clips.stack_view(list(t.get("clips") or []))) for t in mine)
        want = n % 2
        if want < len(mine):
            target = mine[want]
        elif mine and len(mine) >= 2:
            target = mine[0]
    else:  # chant
        if len(mine) >= CHANT_MAX:
            target = next((t for t in mine if not _busy(t, t0, t1)), mine[0])
    if target is not None:
        return {"ok": True, "tracks": tracks, "track_id": target["id"], "created": False, "kind": kind}
    if len(tracks) >= MAX_TRACKS:
        return {"ok": False, "error": "too_many_tracks"}
    base = LAYER_NAMES[kind]
    name = f"{base} {len(mine) + 1}" if kind == "chant" else (unique_name(tracks, base) if mine else base)
    if any(t.get("name") == name for t in tracks):
        name = unique_name(tracks, name)
    tr = new_track(tracks, "vocal", name, "", "", kind, main_id)
    _apply_preset(tr, LAYER_PRESET[kind], presets)
    # ana vokalin (ve mevcut katmanlarinin) hemen altina
    last = max([k for k, t in enumerate(tracks) if t.get("id") == main_id or t in mine] or [len(tracks) - 1])
    tracks.insert(last + 1, tr)
    out = layout_layers(tracks, main_id, seed=seed, pitch_ok=pitch_ok)
    return {"ok": True, "tracks": out, "track_id": tr["id"], "created": True, "kind": kind}


def layout_layers(tracks: list[dict[str, Any]], main_id: str, seed: int = 0, pitch_ok: bool = False) -> list[dict[str, Any]]:
    """Ana vokale bagli tum katman kanallarinin pan/sesini kurallara gore yeniden dagitir (auto_place=False olanlar
    disinda). Chant kanallari tohumdan sapma alir; pitch_ok (pedalboard PitchShift) ise zincirin basina
    otomatik pitchshift eklenir, degilse otomatik pitchshift kaldirilir (yalniz zaman sapmasi)."""
    out = [dict(t) for t in tracks]
    by_id = {t.get("id"): t for t in out}
    for kind in LAYER_KINDS:
        mine = layer_tracks(out, kind, main_id)
        for i, t in enumerate(mine):
            tt = by_id[t.get("id")]
            if kind == "chant":
                dev = chant_deviation(seed, i)
                tt["chant_dev"] = dev
                fx = [f for f in (tt.get("fx") or []) if not (isinstance(f, dict) and f.get("auto") == "chant")]
                if pitch_ok and dev["cents"]:
                    fx = [{"type": "pitchshift", "semitones": round(dev["cents"] / 100.0, 4), "auto": "chant"}] + fx
                tt["fx"] = fx
            if tt.get("auto_place") is False or (kind == "adlib" and not tt.get("layer")):
                continue      # kullanici elle ayarlamis / eski varsayilan adlib kanali (pan'ina dokunma)
            pl = placement(kind, i, len(mine))
            tt["pan"] = pl["pan"]
            tt["volume_db"] = pl["volume_db"]
    return out


def shift_clips(clips: list[dict[str, Any]], ids: list[str], delta_s: float) -> list[dict[str, Any]]:
    """Belirtilen klipleri delta_s kadar kaydirir (start >= 0)."""
    want = set(ids or [])
    return [beat_clips.normalize(dict(c, start=max(0.0, float(c.get("start") or 0.0) + float(delta_s))))
            if c.get("id") in want else c for c in clips]


# ---------------- hizalama ----------------
ENV_RATE = 2000          # zarf orneklem hizi (0.5 ms cozunurluk)


def onset_envelope(x, sr: int, rate: int = ENV_RATE):
    """Mono sinyal -> baslangic-enerjisi zarfi (log RMS'in pozitif turevi, hafif yumusatilmis)."""
    import numpy as np
    x = np.asarray(x, dtype="float64")
    if x.ndim > 1:
        x = x.mean(axis=1)
    hop = max(1, int(round(sr / float(rate))))
    n = len(x) // hop
    if n < 4:
        return np.zeros(max(0, n))
    fr = x[: n * hop].reshape(n, hop)
    rms = np.sqrt(np.mean(fr * fr, axis=1) + 1e-12)
    lg = np.log10(rms + 1e-5)
    k = np.ones(5) / 5.0
    lg = np.convolve(lg, k, mode="same")
    d = np.diff(lg, prepend=lg[0])
    d[d < 0] = 0.0
    return np.convolve(d, np.ones(3) / 3.0, mode="same")


def _ncc_lag(a, b, max_lag: int) -> tuple[int, float]:
    """b'nin a'ya gore gecikmesi (ornek; pozitif = b gec) ve normalize korelasyon tepesi."""
    import numpy as np
    a = np.asarray(a, dtype="float64") - float(np.mean(a))
    b = np.asarray(b, dtype="float64") - float(np.mean(b))
    na, nb = float(np.sqrt(np.sum(a * a))), float(np.sqrt(np.sum(b * b)))
    if na < 1e-9 or nb < 1e-9:
        return 0, 0.0
    n = len(a) + len(b)
    size = 1 << (n - 1).bit_length()
    fa = np.fft.rfft(a, size)
    fb = np.fft.rfft(b, size)
    cc = np.fft.irfft(fb * np.conj(fa), size)          # cc[k] = sum a[i] b[i+k]
    lags = np.concatenate([np.arange(0, max_lag + 1), np.arange(-max_lag, 0)])
    vals = np.concatenate([cc[: max_lag + 1], cc[size - max_lag:]]) if max_lag > 0 else cc[:1]
    j = int(np.argmax(vals))
    return int(lags[j]), float(vals[j] / (na * nb))


def align_signals(ref, sig, sr: int, max_global_ms: float = 150.0, local_ms: float = 40.0,
                  win_ms: float = 250.0, split_ms: float = 6.0) -> dict[str, Any]:
    """ref (ana vokal) ve sig (katman) ayni zaman ekseninde. Dondurur:
    {ok, offset_ms (pozitif = katman gec -> sola kaydir), confidence (0..1),
     segments: [{t0, t1, offset_ms}] (sig'in zamaninda), split (bool)}"""
    import numpy as np
    er = onset_envelope(ref, sr)
    es = onset_envelope(sig, sr)
    n = min(len(er), len(es))
    if n < ENV_RATE * 0.2:
        return {"ok": False, "error": "too_short"}
    er, es = er[:n], es[:n]
    if float(np.max(er)) < 1e-6 or float(np.max(es)) < 1e-6:
        return {"ok": False, "error": "no_signal"}
    mg = int(round(max_global_ms / 1000.0 * ENV_RATE))
    g, conf = _ncc_lag(er, es, mg)
    lm = int(round(local_ms / 1000.0 * ENV_RATE))
    w = max(8, int(round(win_ms / 1000.0 * ENV_RATE)))
    loc: list[tuple[int, int, float]] = []          # (pencere basi, kayma, guven)
    for s in range(0, n - w + 1, w):
        a0, a1 = s - g - lm, s - g + w + lm          # ref'te karsilik gelen bolge (genis)
        if a0 < 0 or a1 > n:
            continue
        seg_s = es[s:s + w]
        if float(np.sum(seg_s)) < 0.02 * float(np.sum(es)) / max(1, n // w):
            continue                                 # sessiz pencere
        best, bc = 0, -1.0
        ref_win = er[a0:a1]
        # seg_s'i ref_win icinde kaydirarak (g etrafinda +-lm) en iyi eslesme
        for k in range(0, 2 * lm + 1):
            r = ref_win[k:k + w]
            if len(r) < w:
                break
            rc, sc = r - r.mean(), seg_s - seg_s.mean()
            den = float(np.sqrt(np.sum(rc * rc) * np.sum(sc * sc)))
            v = float(np.sum(rc * sc)) / den if den > 1e-12 else -1.0
            if v > bc:
                bc, best = v, lm - k
        loc.append((s, g + best, bc))
    if loc:
        offs = [o for _, o, c in loc if c > 0.3]
        if offs:
            g2 = int(np.median(offs))
            if abs(g2 - g) <= lm:
                g = g2
    to_ms = 1000.0 / ENV_RATE
    segs: list[dict[str, float]] = []
    good = [(s, o) for s, o, c in loc if c > 0.3]
    if good:
        # 3'luk medyan ile yumusat, benzer kaymalari grupla; tek pencerelik grup komsusuna katilir (gurultu)
        vals = [o for _, o in good]
        sm = [int(np.median(vals[max(0, i - 1): i + 2])) for i in range(len(vals))]
        groups: list[list[Any]] = [[good[0][0], [sm[0]]]]
        for (s, _), o in zip(good[1:], sm[1:]):
            if abs(o - float(np.median(groups[-1][1]))) * to_ms > split_ms / 2.0:
                groups.append([s, [o]])
            else:
                groups[-1][1].append(o)
        merged: list[list[Any]] = []
        for gr in groups:
            if merged and (len(gr[1]) < 2 or abs(float(np.median(gr[1])) - float(np.median(merged[-1][1]))) * to_ms
                           <= split_ms / 2.0):
                merged[-1][1].extend(gr[1])
            else:
                merged.append(gr)
        for i, (s0, os_) in enumerate(merged):
            t1 = merged[i + 1][0] / ENV_RATE if i + 1 < len(merged) else n / ENV_RATE
            segs.append({"t0": 0.0 if i == 0 else s0 / ENV_RATE, "t1": t1,
                         "offset_ms": round(float(np.median(os_)) * to_ms, 2)})
    offs_ms = [s["offset_ms"] for s in segs]
    split = len(segs) > 1 and (max(offs_ms) - min(offs_ms)) >= split_ms
    if not split:
        segs = [{"t0": 0.0, "t1": n / ENV_RATE, "offset_ms": round(g * to_ms, 2)}]
    return {"ok": True, "offset_ms": round(g * to_ms, 2), "confidence": round(max(0.0, min(1.0, conf)), 3),
            "segments": segs, "split": bool(split), "windows": len(loc)}


def proposal_clips(clips: list[dict[str, Any]], clip_id: str, align: dict[str, Any], origin: float,
                   bias_ms: float = 0.0, xfade: float = 0.005) -> list[dict[str, Any]]:
    """Hizalama sonucunu katman klibine uygular (yeni liste). origin: align'deki 0 sn'nin zaman cizelgesi karsiligi.
    Sabit ofset: klip kaydirilir. Parcali: segment sinirlarinda bolunur, her parca kendi ofsetiyle kaydirilir,
    kesim noktalarina kisa fade (tik olmasin)."""
    i = beat_clips._find(clips, clip_id)
    if i < 0 or not align.get("ok"):
        return list(clips)
    bias = float(bias_ms) / 1000.0
    segs = align.get("segments") or [{"t0": 0.0, "t1": 1e9, "offset_ms": align.get("offset_ms", 0.0)}]
    if not align.get("split") or len(segs) < 2:
        d = -float(align.get("offset_ms") or 0.0) / 1000.0 + bias
        return shift_clips(clips, [clip_id], d)
    out = list(clips)
    pieces = [clip_id]
    cur = clip_id
    for sg in segs[1:]:
        t = origin + float(sg["t0"])
        k = beat_clips._find(out, cur)
        s, e = beat_clips.clip_bounds(out[k])
        if not (s + beat_clips.MIN_LEN < t < e - beat_clips.MIN_LEN):
            continue
        nid = "c_" + uuid.uuid4().hex[:8]
        out = beat_clips.split(out, cur, t, nid)
        pieces.append(nid)
        cur = nid
    # her parca: orta noktasinin dustugu segmentin ofseti
    res = out
    for pid in pieces:
        k = beat_clips._find(res, pid)
        if k < 0:
            continue
        s, e = beat_clips.clip_bounds(res[k])
        mid = (s + e) / 2.0 - origin
        sg = next((x for x in segs if x["t0"] <= mid < x["t1"]), segs[-1])
        res = shift_clips(res, [pid], -float(sg["offset_ms"]) / 1000.0 + bias)
        k = beat_clips._find(res, pid)
        c = res[k]
        fi = xfade if pid != pieces[0] else float(c.get("fade_in") or 0.0)
        fo = xfade if pid != pieces[-1] else float(c.get("fade_out") or 0.0)
        res = res[:k] + [beat_clips.set_fade(c, max(float(c.get("fade_in") or 0.0), fi), max(float(c.get("fade_out") or 0.0), fo))] + res[k + 1:]
    return res


def propose_alignment(proj: dict[str, Any], layer_tid: str, clip_id: str, main_tid: str = "",
                      bias_ms: float = 0.0, sr: int = 16000, render=None) -> dict[str, Any]:
    """Katman klibini ana vokale hizalama onerisi (projeye yazmaz). render: beat_studio.render_track_clips."""
    if render is None:
        from app.core.beat_studio import render_track_clips as render
    tracks = proj.get("tracks") or []
    lt = next((t for t in tracks if t.get("id") == layer_tid), None)
    if lt is None:
        return {"ok": False, "error": "track_not_found"}
    main_tid = main_tid or str(lt.get("layer_of") or "vocal1")
    mt = next((t for t in tracks if t.get("id") == main_tid), None)
    if mt is None:
        return {"ok": False, "error": "main_not_found"}
    k = beat_clips._find(lt.get("clips") or [], clip_id)
    if k < 0:
        return {"ok": False, "error": "clip_not_found"}
    clip = lt["clips"][k]
    s, e = beat_clips.clip_bounds(clip)
    pad = 0.2
    w0, w1 = max(0.0, s - pad), e + pad
    near = [c for c in (mt.get("clips") or []) if beat_clips.clip_bounds(c)[1] > w0 - 1 and beat_clips.clip_bounds(c)[0] < w1 + 1]
    if not near:
        return {"ok": False, "error": "no_main_vocal"}
    cache: dict[str, Any] = {}
    ref = render(near, sr, cache)
    sig = render([dict(clip, fade_in=0.0, fade_out=0.0)], sr, cache)
    a, b = int(round(w0 * sr)), int(round(w1 * sr))

    def cut(x):
        import numpy as np
        seg = x[a:b] if len(x) > a else np.zeros((0, 2), dtype="float32")
        if len(seg) < b - a:
            seg = np.concatenate([seg, np.zeros((b - a - len(seg), 2), dtype="float32")])
        return seg
    al = align_signals(cut(ref), cut(sig), sr)
    if not al.get("ok"):
        return al
    clips = proposal_clips(list(lt.get("clips") or []), clip_id, al, w0, bias_ms)
    return {**al, "track_id": layer_tid, "clip_id": clip_id, "clips": clips, "origin": w0, "bias_ms": float(bias_ms)}
