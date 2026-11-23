"""Kami Beat Asama 1a: saf klip islemleri (yan etkisiz, her zaman yeni nesne/liste dondurur).

Klip semasi (sureler SANIYE, float):
    {id, take_id, path, src_in, src_out, start, gain_db, fade_in, fade_out, muted, [src_len]}
    start          : zaman cizelgesindeki konum
    src_in/src_out : kaynak dosyadaki kesit (ham dosya ASLA degismez)
    src_len        : kaynak dosyanin toplam suresi (biliniyorsa; kirpma siniri)

Ayni semantik app/ui/web/beat-clips.js (window.BeatClips) icinde birebir uygulanir;
tests/test_beat_1a.py iki uygulamanin ayni girdide ayni sonucu verdigini dogrular.
Bu yuzden aritmetik ifadeler JS ile ayni sirada yazilir ve her sonuc r6() ile mikro-saniyeye yuvarlanir.
"""
from __future__ import annotations

import math
import uuid
from typing import Any

MIN_LEN = 0.01            # 10 ms: bir klibin alabilecegi en kisa uzunluk
DIVISIONS = (1, 2, 4, 8, 16)


def r6(x: float) -> float:
    """Mikro-saniye yuvarlama (JS: Math.floor(x * 1e6 + 0.5) / 1e6 ile ayni)."""
    return math.floor(float(x) * 1e6 + 0.5) / 1e6


def _new_id() -> str:
    return "c_" + uuid.uuid4().hex[:8]


def _num(v: Any, default: float = 0.0) -> float:
    if isinstance(v, bool):
        return default
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) else default


def clip_len(clip: dict[str, Any]) -> float:
    return r6(_num(clip.get("src_out")) - _num(clip.get("src_in")))


def clip_bounds(clip: dict[str, Any]) -> list[float]:
    """[baslangic, bitis] zaman cizelgesinde."""
    s = _num(clip.get("start"))
    return [r6(s), r6(s + clip_len(clip))]


def overlaps(a: dict[str, Any], b: dict[str, Any]) -> bool:
    a0, a1 = clip_bounds(a)
    b0, b1 = clip_bounds(b)
    return a0 < b1 and b0 < a1


def _clamp_fades(c: dict[str, Any]) -> dict[str, Any]:
    ln = clip_len(c)
    fi = max(0.0, min(_num(c.get("fade_in")), ln))
    fo = max(0.0, min(_num(c.get("fade_out")), r6(ln - fi)))
    c["fade_in"] = r6(fi)
    c["fade_out"] = r6(fo)
    return c


def normalize(clip: dict[str, Any]) -> dict[str, Any]:
    """Eksik alanlari doldurur, kurallari zorlar (kopya dondurur)."""
    c = dict(clip)
    c["id"] = str(c.get("id") or _new_id())
    c["take_id"] = str(c.get("take_id") or "")
    c["path"] = str(c.get("path") or "")
    src_in = max(0.0, _num(c.get("src_in")))
    src_out = _num(c.get("src_out"), src_in + MIN_LEN)
    src_len = c.get("src_len")
    if src_len is not None and _num(src_len) > 0:
        src_len = r6(_num(src_len))
        c["src_len"] = src_len
        src_out = min(src_out, src_len)
        src_in = min(src_in, r6(src_len - MIN_LEN))
    else:
        c.pop("src_len", None)
    if src_out - src_in < MIN_LEN:
        src_out = src_in + MIN_LEN
    c["src_in"] = r6(src_in)
    c["src_out"] = r6(src_out)
    c["start"] = r6(max(0.0, _num(c.get("start"))))
    c["gain_db"] = r6(_num(c.get("gain_db")))
    c["muted"] = bool(c.get("muted"))
    c["fade_in"] = _num(c.get("fade_in"))
    c["fade_out"] = _num(c.get("fade_out"))
    return _clamp_fades(c)


def _find(clips: list[dict[str, Any]], clip_id: str) -> int:
    for i, c in enumerate(clips):
        if c.get("id") == clip_id:
            return i
    return -1


def snap_time(t: float, bpm: float, division: int = 4) -> float:
    """Bar/vurus izgarasina yapistirir. division: bar basina nota (1=bar, 4=dortluk, 16=onaltilik)."""
    t = _num(t)
    bpm = _num(bpm)
    try:
        division = int(division)
    except (TypeError, ValueError):
        division = 0
    if bpm <= 0 or division not in DIVISIONS:
        return r6(max(0.0, t))
    grid = (60.0 / bpm) * 4.0 / division
    return r6(max(0.0, math.floor(t / grid + 0.5) * grid))


def split(clips: list[dict[str, Any]], clip_id: str, t: float, new_id: str | None = None) -> list[dict[str, Any]]:
    """t (zaman cizelgesi) noktasinda klibi ikiye boler. Sol fade_in'i, sag fade_out'u korur."""
    out = [dict(c) for c in clips]
    i = _find(out, clip_id)
    if i < 0:
        return out
    c = out[i]
    s, e = clip_bounds(c)
    t = _num(t)
    if t < s + MIN_LEN or t > e - MIN_LEN:
        return out
    cut = r6(_num(c.get("src_in")) + (t - s))
    left = dict(c)
    left["src_out"] = cut
    left["fade_out"] = 0.0
    right = dict(c)
    right["id"] = new_id or _new_id()
    right["src_in"] = cut
    right["start"] = r6(t)
    right["fade_in"] = 0.0
    out[i] = _clamp_fades(left)
    out.insert(i + 1, _clamp_fades(right))
    return out


def trim_start(clip: dict[str, Any], new_start: float) -> dict[str, Any]:
    """Sol kenari tasir (sag kenar sabit). Kaynak basini (src_in>=0) ve 10 ms siniri asmaz."""
    c = dict(clip)
    s, e = clip_bounds(c)
    src_in = _num(c.get("src_in"))
    lo = max(0.0, s - src_in)
    hi = e - MIN_LEN
    ns = max(lo, min(_num(new_start), hi))
    c["src_in"] = r6(src_in + (ns - s))
    c["start"] = r6(ns)
    return _clamp_fades(c)


def trim_end(clip: dict[str, Any], new_end: float) -> dict[str, Any]:
    """Sag kenari tasir. Kaynak sonunu (src_len biliniyorsa) ve 10 ms siniri asmaz."""
    c = dict(clip)
    s = _num(c.get("start"))
    src_in = _num(c.get("src_in"))
    lo = s + MIN_LEN
    ne = max(lo, _num(new_end))
    src_len = c.get("src_len")
    if src_len is not None and _num(src_len) > 0:
        ne = min(ne, s + (_num(src_len) - src_in))
        ne = max(lo, ne)
    c["src_out"] = r6(src_in + (ne - s))
    return _clamp_fades(c)


def move(clips: list[dict[str, Any]], clip_id: str, new_start: float, snap: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Klibi new_start'a tasir. snap = {"bpm": .., "division": ..} verilirse izgaraya yapistirir."""
    out = [dict(c) for c in clips]
    i = _find(out, clip_id)
    if i < 0:
        return out
    ns = _num(new_start)
    if snap:
        ns = snap_time(ns, _num(snap.get("bpm")), snap.get("division", 4))
    out[i]["start"] = r6(max(0.0, ns))
    return out


def duplicate(clips: list[dict[str, Any]], clip_id: str, new_id: str | None = None) -> list[dict[str, Any]]:
    """Klibin kopyasini hemen sagina (bitisine) yerlestirir."""
    out = [dict(c) for c in clips]
    i = _find(out, clip_id)
    if i < 0:
        return out
    c = dict(out[i])
    c["id"] = new_id or _new_id()
    c["start"] = clip_bounds(out[i])[1]
    out.insert(i + 1, c)
    return out


def delete(clips: list[dict[str, Any]], clip_id: str) -> list[dict[str, Any]]:
    return [dict(c) for c in clips if c.get("id") != clip_id]


def set_fade(clip: dict[str, Any], fade_in: float, fade_out: float) -> dict[str, Any]:
    c = dict(clip)
    c["fade_in"] = max(0.0, _num(fade_in))
    c["fade_out"] = max(0.0, _num(fade_out))
    return _clamp_fades(c)


def track_end(clips: list[dict[str, Any]]) -> float:
    """Kanaldaki son klibin bitisi (bos ise 0)."""
    return max([clip_bounds(c)[1] for c in clips] or [0.0])
