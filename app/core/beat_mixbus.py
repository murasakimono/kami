"""Kami Beat Asama 2b: ses/pan otomasyonu, send/bus (Reverb/Delay), beat'te vokale yer acma.

Otomasyon (kanal `automation: {volume: [[t, db], ...], pan: [[t, v], ...]}`):
  - Noktalar arasinda DOGRUSAL enterpolasyon (ses dB cinsinden dogrusal, pan -1..1 dogrusal); ilk noktadan once ilk
    deger, son noktadan sonra son deger tutulur (np.interp ile ayni; JS BeatAuto.valueAt birebir).
  - Ses seridi kanal suruklusune EKLENIR (0 dB = surgu seviyesi; -40..+12 dB). Pan seridi en az bir noktasi varsa
    kanal pan dugmesinin YERINE gecer.
  - Render: ornek duzeyinde zarf (mix_array); onizleme Web Audio setValueAtTime/linearRampToValueAtTime.
Send/bus (proje `buses: [{id, name, fx, volume_db, mute}]`, kanal `sends: {bus_id: db}`):
  - Post-fader: send kaynagi = kanal sesi x (surgu + ses otomasyonu), pan'dan once (stereo korunur).
  - Bus'a toplanir -> bus fx -> bus ses/mute -> master'a eklenir. Delay bus'inda yerlesik delay BPM'e kilitli
    ('sync' alani olan delay modulu her render'da proje BPM'inden yeniden hesaplanir).
  - pedalboard yokken bus'taki yerlesik reverb numpy tarak yedegiyle (beat_fx._np_reverb_wet) islenir; atlanan
    %100 islak modul kuru sesi bus'tan ikinci kez gecirmesin diye.
Vokale yer acma (beat kanali `make_room: {on, mode: band|wide, center_hz, width_oct, depth_db}`):
  - Anahtar: vokal kanallari (role=vocal, mute/solo kurali) post-fader toplamindan RMS zarfi (atak 10 ms, birakma
    150 ms; 2.5 ms bloklarla). Azaltma = derinlik x clamp((zarf - (-48)) / 20, 0, 1) dB.
  - band: STFT (mutlak izgara) ile merkez frekans cevresinde log-frekans Gauss agirlikli dinamik bant azaltma.
  - wide: tum beat genis bantta (0..3 dB).
  - Azaltma hic yoksa (vokal yok) beat BIREBIR degismeden doner."""
from __future__ import annotations

import copy
import logging
import math
from typing import Any

from app.core import beat_clean, beat_fx

log = logging.getLogger("kami.beat_mixbus")

AUTO_VOL_RANGE = (-40.0, 12.0)
AUTO_PAN_RANGE = (-1.0, 1.0)
AUTO_MAX_POINTS = 2000
SEND_OFF_DB = -60.0
BUS_TAIL = 3.0                 # sn: send'i olan miksin sonuna bus kuyrugu (reverb/delay) icin eklenen sure
BUS_PREROLL = 4.0              # sn: onizlemede bus girdisi pencereden bu kadar once baslar (delay/reverb kuyrugu)
DUCK_BLOCK_SEC = 0.0025
DUCK_ATTACK = 0.010
DUCK_RELEASE = 0.150
DUCK_LO_DB = -48.0
DUCK_RANGE_DB = 20.0
DUCK_PAD = 0.25                # sn: onizlemede beat pencereden bu kadar once islenir (STFT kenari)
MAKE_ROOM_DEFAULT = {"on": False, "mode": "band", "center_hz": 2000.0, "width_oct": 2.0, "depth_db": 3.0}


def _num(v: Any, d: float) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return d
    return x if math.isfinite(x) else d


# ---------------- otomasyon ----------------
def normalize_points(pts: Any, lo: float, hi: float) -> list[list[float]]:
    out: dict[float, float] = {}
    for p in pts or []:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            t, v = _num(p[0], float("nan")), _num(p[1], float("nan"))
            if not (math.isfinite(t) and math.isfinite(v)):
                continue                            # gecersiz nokta atlanir
            out[round(max(0.0, t), 4)] = round(max(lo, min(hi, v)), 4)
    return [[t, out[t]] for t in sorted(out)][:AUTO_MAX_POINTS]


def normalize_automation(a: Any) -> dict[str, list[list[float]]]:
    a = a if isinstance(a, dict) else {}
    return {"volume": normalize_points(a.get("volume"), *AUTO_VOL_RANGE),
            "pan": normalize_points(a.get("pan"), *AUTO_PAN_RANGE)}


def value_at(points: list[list[float]], t: float, default: float = 0.0) -> float:
    """Tek nokta degeri (JS BeatAuto.valueAt ile ayni)."""
    if not points:
        return default
    if t <= points[0][0]:
        return float(points[0][1])
    if t >= points[-1][0]:
        return float(points[-1][1])
    lo, hi = 0, len(points) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if points[mid][0] <= t:
            lo = mid
        else:
            hi = mid
    t0, v0 = points[lo]
    t1, v1 = points[hi]
    return float(v0 + (v1 - v0) * (t - t0) / (t1 - t0)) if t1 > t0 else float(v1)


def envelope(points: list[list[float]], start_sample: int, n: int, sr: int, default: float = 0.0):
    """Ornek duzeyinde zarf: t = (start_sample + i) / sr."""
    import numpy as np
    if not points:
        return np.full(n, default, dtype="float64")
    ts = np.array([p[0] for p in points], dtype="float64")
    vs = np.array([p[1] for p in points], dtype="float64")
    t = (start_sample + np.arange(n, dtype="float64")) / sr
    return np.interp(t, ts, vs)


def has_automation(tr: dict[str, Any]) -> bool:
    a = tr.get("automation")
    return isinstance(a, dict) and bool(a.get("volume") or a.get("pan"))


def fader_gain(tr: dict[str, Any], start_sample: int, n: int, sr: int):
    """Surgu + ses otomasyonu (dogrusal kazanc). Otomasyon yoksa skaler."""
    base = _num(tr.get("volume_db"), 0.0)
    a = normalize_automation(tr.get("automation"))
    if not a["volume"]:
        return 10.0 ** (base / 20.0)
    return 10.0 ** ((base + envelope(a["volume"], start_sample, n, sr)) / 20.0)


def apply_fader(data, tr: dict[str, Any], sr: int, start_sample: int = 0):
    """Kanal surgusu + pan (+ otomasyon). Pan yasasi mix_array ile ayni (sqrt esit guc)."""
    import numpy as np
    n = len(data)
    g = fader_gain(tr, start_sample, n, sr)
    a = normalize_automation(tr.get("automation"))
    out = np.empty((n, 2), dtype="float32")
    if a["pan"]:
        p = np.clip(envelope(a["pan"], start_sample, n, sr), -1.0, 1.0)
        lg = g * np.sqrt(0.5 * (1.0 - p))
        rg = g * np.sqrt(0.5 * (1.0 + p))
        out[:, 0] = data[:, 0] * lg
        out[:, 1] = data[:, 1] * rg
        return out
    pan = max(-1.0, min(1.0, _num(tr.get("pan"), 0.0)))
    l_gain = g * math.sqrt(0.5 * (1.0 - pan))      # skaler ya da ornek dizisi
    r_gain = g * math.sqrt(0.5 * (1.0 + pan))
    out[:, 0] = data[:, 0] * l_gain
    out[:, 1] = data[:, 1] * r_gain
    return out


def post_fader(data, tr: dict[str, Any], sr: int, start_sample: int = 0):
    """Send kaynagi: surgu + ses otomasyonu, pan'dan once."""
    import numpy as np
    g = fader_gain(tr, start_sample, len(data), sr)
    if np.ndim(g) == 0:
        return (data * g).astype("float32")
    return (data * g[:, None]).astype("float32")


# ---------------- bus'lar ----------------
def _bus_steps():
    from app.core import beat_style as bst
    verb = bst._st("verb", "Reverb (bus)", [{"type": "reverb", "room_size": 0.62, "damping": 0.5, "wet_level": 1.0,
                                             "dry_level": 0.0, "width": 1.0}],
                   ("supermassive", "mcharmverb"), [(("mix", "dry_wet", "wet"), 1.0)], note="%100 ıslak (bus)")
    dly = bst._st("delay", "Delay 1/4 (bus)", [{"type": "delay", "delay_seconds": 0.5, "feedback": 0.32, "mix": 1.0}],
                  ("mdelay",), [(("dry_wet", "mix", "wet"), 1.0)], sync="1/4",
                  note="%100 ıslak; eklentide BPM senkronunu pencereden aç")
    return verb, dly


def default_buses(plugins: list[dict[str, Any]] | None = None, bpm: float = 0.0, use_vst: bool = True,
                  param_lookup=None) -> list[dict[str, Any]]:
    """Varsayilan iki bus: Reverb (Supermassive tercih, yoksa yerlesik %100 islak) ve Delay (MDelay tercih, yoksa
    yerlesik BPM'e kilitli 1/4)."""
    from app.core import beat_style as bst
    verb, dly = _bus_steps()
    out = []
    for bid, name, st in (("reverb", "Reverb", verb), ("delay", "Delay", dly)):
        r = bst.resolve_steps([st], plugins, use_vst, bpm, param_lookup)
        fx = r["fx"]
        for f in fx:
            f.pop("style_role", None)
        out.append({"id": bid, "name": name, "fx": fx, "volume_db": 0.0, "mute": False,
                    "engine": r["steps"][0]["engine"] if r["steps"] else "builtin"})
    return out


def normalize_buses(buses: Any) -> list[dict[str, Any]]:
    out = []
    seen = set()
    for b in buses if isinstance(buses, list) else []:
        if not isinstance(b, dict):
            continue
        bid = str(b.get("id") or "").strip()[:24]
        if not bid or bid in seen:
            continue
        seen.add(bid)
        out.append({"id": bid, "name": str(b.get("name") or bid)[:32],
                    "fx": [f for f in b.get("fx") or [] if isinstance(f, dict)],
                    "volume_db": max(-60.0, min(12.0, _num(b.get("volume_db"), 0.0))), "mute": bool(b.get("mute")),
                    **({"engine": b["engine"]} if b.get("engine") else {})})
    return out


def active_sends(tr: dict[str, Any], buses: list[dict[str, Any]] | None) -> dict[str, float]:
    """{bus_id: dogrusal kazanc} — bus'i olmayan, mute'lu ya da -60 dB alti send'ler haric."""
    s = tr.get("sends")
    if not isinstance(s, dict) or not s:
        return {}
    live = {b["id"] for b in normalize_buses(buses) if not b["mute"]}
    out = {}
    for bid, db in s.items():
        if bid not in live or db is None:
            continue
        d = _num(db, SEND_OFF_DB)
        if d > SEND_OFF_DB:
            out[str(bid)] = 10.0 ** (min(12.0, d) / 20.0)
    return out


def bus_chain(bus: dict[str, Any], bpm: float) -> list[dict[str, Any]]:
    """Bus fx zinciri; 'sync'li yerlesik delay proje BPM'ine kilitlenir."""
    from app.core import beat_style as bst
    out = []
    for f in beat_fx.active_fx(bus.get("fx")):
        f = dict(f)
        if str(f.get("type")) == "delay" and f.get("sync"):
            f["delay_seconds"] = bst.delay_time(bpm, str(f["sync"]))
        out.append(f)
    return out


def process_bus(data, sr: int, bus: dict[str, Any], bpm: float, info: dict[str, Any] | None = None):
    """Bus fx (sira korunur) + bus ses seviyesi. pedalboard yoksa yerlesik reverb numpy yedegiyle."""
    import numpy as np
    info = {} if info is None else info
    info.setdefault("skipped", [])
    out = np.asarray(data, dtype="float32")
    chain = bus_chain(bus, bpm)
    pb = beat_fx.pedalboard_module()
    if pb is None:
        # yerlesik reverb'u numpy ile, gerisini beat_fx.process ile (sirayi koruyarak bolumler halinde)
        run: list[dict[str, Any]] = []
        for f in chain + [None]:
            if f is not None and str(f.get("type")) != "reverb":
                run.append(f)
                continue
            if run:
                out, i = beat_fx.process(out, sr, run)
                info["skipped"] += i["skipped"]
                run = []
            if f is not None:
                c = beat_fx.clamp_fx(f)
                wet = beat_fx._np_reverb_wet(out, sr, float(c.get("room_size", 0.25)), float(c.get("damping", 0.5)))
                out = (out * float(c.get("dry_level", 0.9)) + wet * float(c.get("wet_level", 0.12))).astype("float32")
    elif chain:
        out, i = beat_fx.process(out, sr, chain)
        info["skipped"] += i["skipped"]
    g = 10.0 ** (_num(bus.get("volume_db"), 0.0) / 20.0)
    return (out * g).astype("float32")


def render_buses(acc: dict[str, Any], buses: list[dict[str, Any]] | None, sr: int, bpm: float,
                 info: dict[str, Any] | None = None):
    """{bus_id: (N,2) toplanmis send} -> bus ciktilarinin toplami (N,2) ya da None."""
    import numpy as np
    total = None
    for b in normalize_buses(buses):
        x = acc.get(b["id"])
        if x is None or b["mute"] or not len(x):
            continue
        y = process_bus(x, sr, b, bpm, info)
        if total is None:
            total = np.zeros_like(y)
        if len(y) > len(total):
            total = np.concatenate([total, np.zeros((len(y) - len(total), 2), dtype="float32")])
        total[:len(y)] += y
    return total


# ---------------- vokale yer acma ----------------
def normalize_make_room(m: Any) -> dict[str, Any]:
    m = m if isinstance(m, dict) else {}
    mode = "wide" if m.get("mode") == "wide" else "band"
    depth = max(0.0, min(6.0, _num(m.get("depth_db"), MAKE_ROOM_DEFAULT["depth_db"])))
    if mode == "wide":
        depth = min(3.0, depth)
    return {"on": bool(m.get("on")), "mode": mode,
            "center_hz": max(300.0, min(8000.0, _num(m.get("center_hz"), 2000.0))),
            "width_oct": max(0.5, min(4.0, _num(m.get("width_oct"), 2.0))), "depth_db": depth}


def make_room_active(tr: dict[str, Any]) -> bool:
    if str(tr.get("role") or "") == "vocal":
        return False
    m = normalize_make_room(tr.get("make_room"))
    return m["on"] and m["depth_db"] > 0.0


def key_envelope(key, sr: int, abs_start: int = 0):
    """Vokal anahtarinin RMS zarfi (dB) mutlak blok izgarasinda: (blok_baslangic_ornegi, env_db dizisi).
    Blok = 2.5 ms; tek kutuplu izleyici guc uzerinde, atak 10 ms / birakma 150 ms."""
    import numpy as np
    blk = max(1, int(round(DUCK_BLOCK_SEC * sr)))
    k = np.asarray(key, dtype="float64")
    p = (k ** 2).mean(axis=1) if k.ndim == 2 else k ** 2
    skip = (-abs_start) % blk                  # ilk tam blok mutlak izgarada baslasin
    p = p[skip:]
    first = abs_start + skip
    nb = len(p) // blk
    if nb == 0:
        return first, np.full(0, -120.0)
    bp = p[: nb * blk].reshape(nb, blk).mean(axis=1)
    aa = math.exp(-DUCK_BLOCK_SEC / DUCK_ATTACK)
    ar = math.exp(-DUCK_BLOCK_SEC / DUCK_RELEASE)
    env = np.empty(nb)
    y = 0.0
    for i in range(nb):
        x = bp[i]
        c = aa if x > y else ar
        y = c * y + (1.0 - c) * x
        env[i] = y
    return first, 10.0 * np.log10(np.maximum(env, 1e-14))


def reduction_db(env_db, depth: float):
    import numpy as np
    return depth * np.clip((np.asarray(env_db) - DUCK_LO_DB) / DUCK_RANGE_DB, 0.0, 1.0)


def duck(beat, key, sr: int, settings: dict[str, Any], abs_start: int = 0, key_abs_start: int | None = None):
    """Beat (N,2) -> vokal anahtarina gore orta bant (ya da genis bant) azaltilmis beat. key: (M,2) post-fader vokal
    toplami, key_abs_start mutlak ornek konumu (None = abs_start). Azaltma yoksa girdi aynen doner."""
    import numpy as np
    m = normalize_make_room(settings)
    b = np.asarray(beat, dtype="float32")
    if not len(b) or key is None or not len(key) or m["depth_db"] <= 0:
        return b
    k0 = abs_start if key_abs_start is None else key_abs_start
    first, env = key_envelope(key, sr, k0)
    if not len(env):
        return b
    red = reduction_db(env, m["depth_db"])
    if float(np.max(red)) < 1e-3:
        return b
    blk = max(1, int(round(DUCK_BLOCK_SEC * sr)))
    centers = first + blk * np.arange(len(red)) + blk / 2.0

    def red_at(abs_samples):
        return np.interp(abs_samples, centers, red)

    if m["mode"] == "wide":
        r = red_at(abs_start + np.arange(len(b), dtype="float64"))
        if float(np.max(r)) < 1e-3:
            return b
        return (b * (10.0 ** (-r / 20.0))[:, None]).astype("float32")
    fc, wo = m["center_hz"], m["width_oct"]
    f = np.fft.rfftfreq(beat_clean.N_FFT, 1.0 / sr)
    w = np.exp(-0.5 * (np.log2(np.maximum(f, 1.0) / fc) / (wo / 2.0)) ** 2)[:, None]       # (F,1)

    def gain(mag, cen):
        r = red_at(np.asarray(cen, dtype="float64"))[None, :]
        return 10.0 ** (-(w * r) / 20.0)

    return beat_clean.stft_process(b, gain, abs_start=abs_start)


def band_energy(x, sr: int, lo: float = 1000.0, hi: float = 4000.0) -> float:
    """Yardimci (test/olcum): [lo, hi] bandinin toplam enerjisi."""
    import numpy as np
    m = np.asarray(x, dtype="float64")
    m = m.mean(axis=1) if m.ndim == 2 else m
    X = np.abs(np.fft.rfft(m)) ** 2
    f = np.fft.rfftfreq(len(m), 1.0 / sr)
    return float(X[(f >= lo) & (f <= hi)].sum())


# ---------------- tarz onayari -> send ----------------
def chain_to_sends(fx_list: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """2a onayarlarinin kanal sonundaki reverb/delay adimlarini (style_role verb/delay) send'e cevirir:
    zincirden cikarilir, islak miktari send seviyesine (dB) donusur. VST'li adimlar da (Supermassive/MDelay)
    bus'ta zaten var -> send olur."""
    keep: list[dict[str, Any]] = []
    sends: dict[str, float] = {}
    for f in fx_list or []:
        role = str(f.get("style_role") or "")
        if role not in ("verb", "delay") or f.get("bypass"):
            keep.append(f)
            continue
        if f.get("type") == "reverb":
            wet = _num(f.get("wet_level"), 0.12)
        elif f.get("type") == "delay":
            wet = _num(f.get("mix"), 0.15)
        else:
            vals = [v for k, v in (f.get("params") or {}).items() if any(w in k.lower() for w in ("mix", "wet"))]
            wet = _num(vals[0], 0.3) / 1.6 if vals else 0.2
        bid = "reverb" if role == "verb" else "delay"
        db = round(max(SEND_OFF_DB + 1, min(0.0, 20.0 * math.log10(max(wet, 1e-3)))), 1)
        sends[bid] = max(sends.get(bid, SEND_OFF_DB), db)
    return keep, sends


def copy_track(tr: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(tr)
