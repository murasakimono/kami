"""Kami Beat Asama 1b: kayit akisinin saf zaman hesaplari (yan etkisiz).

Ayni semantik app/ui/web/beat-transport.js (window.BeatTransport) icinde birebir uygulanir;
tests/test_beat_1b.py iki uygulamayi node ile karsilastirir. Sureler SANIYE, sonuclar r6 ile yuvarlanir.

Kavramlar:
  u (dogrusal tasima zamani): calma basladiktan sonra kesintisiz akan saat; zaman cizelgesi konumuna esit,
     ta ki dongu sonuna (b) gelinene kadar. Dongude u >= b iken t = a + ((u - b) mod (b - a)).
  Sayim (count-in): kayit konumu F'den bars * bar kadar once tasima baslar; sayim tiklari F'ye gore hizalanir.
  Kayit yerlesimi: Python kaydinin 0. ornegi dogrusal zamanda u0'a denk gelir:
     u0 = anchor_u - (anchor_wall - rec_epoch0)       (ayni makinenin duvar saati)
     u0e = u0 - latency_s                              (alkis testi: cikis + giris gecikmesi)
  Kayittaki k. saniye dogrusal zamanda u0e + k'ya denk gelir.
"""
from __future__ import annotations

import math
from typing import Any

from app.core.beat_clips import MIN_LEN, r6

MIN_LAP_PARTIAL = 0.25     # hic tam tur yoksa, en az bu kadar uzun yarim tur take olarak tutulur


def _f(v: Any, d: float = 0.0) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return d
    return x if math.isfinite(x) else d


def beat_sec(bpm: float) -> float:
    bpm = _f(bpm)
    return 60.0 / bpm if bpm > 0 else 0.5


def bar_sec(bpm: float, beats_per_bar: int = 4) -> float:
    return beat_sec(bpm) * max(1, int(beats_per_bar or 4))


def metronome_ticks(bpm: float, t0: float, t1: float, beats_per_bar: int = 4, origin: float = 0.0) -> list[dict[str, Any]]:
    """[t0, t1) araligindaki vuruslar: origin + k * vurus. beat = k mod beats_per_bar, accent = beat == 0 (bar basi)."""
    b = beat_sec(bpm)
    bpb = max(1, int(beats_per_bar or 4))
    t0, t1, origin = _f(t0), _f(t1), _f(origin)
    out: list[dict[str, Any]] = []
    if t1 <= t0:
        return out
    k = math.ceil((t0 - origin) / b - 1e-9)
    while True:
        t = origin + k * b
        if t >= t1 - 1e-9:
            break
        beat = k % bpb
        out.append({"t": r6(t), "k": k, "beat": beat, "accent": beat == 0})
        k += 1
        if len(out) > 100000:
            break
    return out


def count_in_plan(rec_from: float, bpm: float, bars: int, beats_per_bar: int = 4) -> dict[str, Any]:
    """Sayim plani: tasima transport_start'ta baslar, kayit rec_from'da 'baslar' (klip oradan itibaren tutulur).
    bars=0 -> sayim yok. Tiklar rec_from'a gore hizali (son tik rec_from'dan bir vurus once)."""
    bars = max(0, min(2, int(_f(bars))))
    bpb = max(1, int(beats_per_bar or 4))
    f = _f(rec_from)
    dur = bars * bar_sec(bpm, bpb)
    start = f - dur
    ticks = metronome_ticks(bpm, start, f, bpb, origin=f) if bars else []
    return {"transport_start": r6(start), "rec_from": r6(f), "duration": r6(dur), "beats": bars * bpb, "ticks": ticks}


def timeline_at(u: float, u_start: float, loop_a: float | None = None, loop_b: float | None = None) -> float:
    """Dogrusal zaman -> zaman cizelgesi konumu. Dongu yalniz tasima b'den once basladiysa sarar."""
    u = _f(u)
    if loop_a is None or loop_b is None:
        return r6(u)
    a, b = _f(loop_a), _f(loop_b)
    ln = b - a
    if ln < MIN_LEN or _f(u_start) >= b or u < b:
        return r6(u)
    return r6(a + math.fmod(u - b, ln))


def recording_origin(anchor_u: float, anchor_wall: float, rec_epoch0: float, latency_s: float = 0.0) -> float:
    """Kaydin 0. orneginin (gecikme telafili) dogrusal zamani: u0e."""
    return r6(_f(anchor_u) - (_f(anchor_wall) - _f(rec_epoch0)) - _f(latency_s))


def linear_take(u0e: float, rec_len: float, keep_from: float) -> dict[str, float] | None:
    """Duz kayit: klip keep_from'da (sayim sonrasi asil baslangic) baslar; oncesi (sayim/on-kayit) atilir."""
    u0e, rec_len, f = _f(u0e), _f(rec_len), _f(keep_from)
    start = max(f, u0e, 0.0)
    src_in = start - u0e
    if rec_len - src_in < MIN_LEN:
        return None
    return {"start": r6(start), "src_in": r6(src_in), "src_out": r6(rec_len)}


def loop_laps(u0e: float, rec_len: float, a: float, b: float) -> list[dict[str, Any]]:
    """Dongude kayit -> tur basina take. Tasima a'dan (veya sayimla a'dan once) baslar ve a..b'yi doner.
    k. tur dogrusal zamanda [a + k*L, a + (k+1)*L]. Tam turlar tutulur; hic tam tur yoksa >= 0.25 s'lik
    yarim tur tutulur (son yarim tur, tam turlar varsa atilir: kullanici durdurmak icin basmistir)."""
    u0e, rec_len, a, b = _f(u0e), _f(rec_len), _f(a), _f(b)
    ln = b - a
    if ln < MIN_LEN or rec_len < MIN_LEN:
        return []
    laps: list[dict[str, Any]] = []
    k = 0
    while True:
        lap_u0 = a + k * ln
        src_in = lap_u0 - u0e
        if src_in >= rec_len - MIN_LEN:
            break
        start = a
        if src_in < 0:                       # kayit turun ortasinda basladiysa (olmamali) basi kirp
            start = a - src_in
            src_in = 0.0
        src_out = (lap_u0 + ln) - u0e
        complete = src_out <= rec_len + 0.005 and start == a
        src_out = min(src_out, rec_len)
        if src_out - src_in >= MIN_LEN:
            laps.append({"lap": k, "start": r6(start), "src_in": r6(src_in), "src_out": r6(src_out), "complete": complete})
        k += 1
        if k > 10000:
            break
    full = [x for x in laps if x["complete"]]
    if full:
        return full
    part = [x for x in laps if x["src_out"] - x["src_in"] >= MIN_LAP_PARTIAL]
    return part[:1]


def punch_window(u0e: float, rec_len: float, t0: float, t1: float, xfade: float = 0.01) -> dict[str, float] | None:
    """Punch klibinin kaynagi: zaman cizelgesinde t0 - xf/2 .. t1 + xf/2 (kayit kisa kaldiysa kirpilir)."""
    u0e, rec_len, t0, t1 = _f(u0e), _f(rec_len), _f(t0), _f(t1)
    h = max(0.0, _f(xfade)) / 2.0
    start = max(t0 - h, u0e, 0.0)
    src_in = start - u0e
    src_out = min((t1 + h) - u0e, rec_len)
    if src_out - src_in < MIN_LEN:
        return None
    return {"start": r6(start), "src_in": r6(src_in), "src_out": r6(src_out)}
