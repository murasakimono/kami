"""Kami Beat Asama 1a/1b: saf klip islemleri + take destesi (yan etkisiz, her zaman yeni nesne/liste dondurur).

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
DIVISIONS = (1, 2, 4, 8, 16, 32)


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
    if c.get("stack_id"):              # 1b: take destesi (alan yoksa tek klip = deste yok)
        c["stack_id"] = str(c["stack_id"])
        c["stack_active"] = bool(c.get("stack_active"))
    else:
        c.pop("stack_id", None)
        c.pop("stack_active", None)
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
    _with_fx(left)
    _with_fx(right)   # R4: klip fx zinciri parcalar arasinda paylasilmaz (derin kopya)
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
    c = _with_fx(dict(out[i]))
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


# ---------------- 1b: take destesi (stack) ----------------
# Ayni destedeki klipler ortak "stack_id" tasir; "stack_active" True olan uye duyulur ve cizilir.
# Hicbir uye aktif isaretli degilse (bozuk veri) listedeki SON uye aktif sayilir.
# Alan yoksa klip tek basinadir (goc gerekmez).
XFADE = 0.01              # punch kenarlarinda capraz gecis (10 ms)


def new_stack_id() -> str:
    return "s_" + uuid.uuid4().hex[:8]


def stack_members(clips: list[dict[str, Any]], stack_id: str) -> list[dict[str, Any]]:
    """Destenin uyeleri (liste sirasiyla, kopya). stack_id bossa []."""
    if not stack_id:
        return []
    return [dict(c) for c in clips if c.get("stack_id") == stack_id]


def stack_active_id(clips: list[dict[str, Any]], stack_id: str) -> str:
    mem = [c for c in clips if stack_id and c.get("stack_id") == stack_id]
    if not mem:
        return ""
    for c in mem:
        if c.get("stack_active"):
            return str(c.get("id"))
    return str(mem[-1].get("id"))


def stack_set_active(clips: list[dict[str, Any]], stack_id: str, clip_id: str) -> list[dict[str, Any]]:
    """clip_id destenin aktif uyesi olur, digerleri pasif. clip_id uye degilse degisiklik yok."""
    out = [dict(c) for c in clips]
    if not stack_id or not any(c.get("stack_id") == stack_id and c.get("id") == clip_id for c in out):
        return out
    for c in out:
        if c.get("stack_id") == stack_id:
            c["stack_active"] = c.get("id") == clip_id
    return out


def is_audible_member(clips: list[dict[str, Any]], clip: dict[str, Any]) -> bool:
    sid = clip.get("stack_id")
    return not sid or stack_active_id(clips, sid) == clip.get("id")


def stack_view(clips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Duyulan/cizilen klipler: destesiz klipler + her destenin aktif uyesi (liste sirasi korunur)."""
    act: dict[str, str] = {}
    out = []
    for c in clips:
        sid = c.get("stack_id")
        if sid:
            if sid not in act:
                act[sid] = stack_active_id(clips, sid)
            if act[sid] != c.get("id"):
                continue
        out.append(dict(c))
    return out


def _dissolve_singletons(out: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for c in out:
        if c.get("stack_id"):
            counts[c["stack_id"]] = counts.get(c["stack_id"], 0) + 1
    for c in out:
        if c.get("stack_id") and counts[c["stack_id"]] < 2:
            c.pop("stack_id", None)
            c.pop("stack_active", None)
    return out


def stack_push(clips: list[dict[str, Any]], stack_id: str, clip: dict[str, Any]) -> list[dict[str, Any]]:
    """clip'i destenin ustune (aktif) koyar; destenin son uyesinin hemen arkasina eklenir."""
    out = [dict(c) for c in clips]
    nc = dict(clip)
    nc["stack_id"] = stack_id
    nc["stack_active"] = True
    last = -1
    for i, c in enumerate(out):
        if c.get("stack_id") == stack_id:
            c["stack_active"] = False
            last = i
    if last < 0:
        out.append(nc)
    else:
        out.insert(last + 1, nc)
    return out


def stack_remove(clips: list[dict[str, Any]], clip_id: str) -> list[dict[str, Any]]:
    """Desteden bir take'i siler. Aktif olan silinirse kalan son uye aktif olur; tek uye kalirsa deste cozulur."""
    i = _find(clips, clip_id)
    if i < 0:
        return [dict(c) for c in clips]
    sid = clips[i].get("stack_id")
    out = [dict(c) for c in clips if c.get("id") != clip_id]
    if sid:
        mem = [c for c in out if c.get("stack_id") == sid]
        if mem and not any(c.get("stack_active") for c in mem):
            mem[-1]["stack_active"] = True
        out = _dissolve_singletons(out)
    return out


def punch_in(clips: list[dict[str, Any]], clip_id: str, t0: float, t1: float, punch_clip: dict[str, Any],
             xfade: float = XFADE, ids: Any = None) -> list[dict[str, Any]]:
    """Punch-in sonucu: hedef klip (destesiyse tum uyeleri) t0/t1'den bolunur -> once / punch destesi / sonra.
    Orta parcalar + punch_clip yeni bir destede toplanir (punch aktif). Kenarlarda xfade uzunlugunda capraz
    gecis: onceki parca t0+xf/2'ye kadar uzar ve fade-out alir, punch t0-xf/2'den baslar ve fade-in alir
    (t1 kenari simetrik). punch_clip'in start/src_in/src_out'u cagiran tarafca t0-xf/2..t1+xf/2'ye gore verilir.
    ids: yeni kimlik ureten cagrilabilir (test icin belirlenebilir); yoksa rastgele."""
    gen = ids or (lambda kind: (new_stack_id() if kind == "s" else _new_id()))
    i = _find(clips, clip_id)
    if i < 0:
        return [dict(c) for c in clips]
    target = clips[i]
    sid = target.get("stack_id")
    members = [c for c in clips if c.get("stack_id") == sid] if sid else [target]
    act_id = stack_active_id(clips, sid) if sid else target.get("id")
    act = next(c for c in members if c.get("id") == act_id)
    s, e = clip_bounds(act)
    t0 = max(_num(t0), s)
    t1 = min(_num(t1), e)
    if t1 - t0 < MIN_LEN:
        return [dict(c) for c in clips]
    xf = max(0.0, _num(xfade))
    h = xf / 2.0
    sb, sm, sa = gen("s"), gen("s"), gen("s")
    befores, mids, afters = [], [], []
    has_b = has_a = False
    for m in members:
        ms, me = clip_bounds(m)
        is_act = m.get("id") == act_id
        first_id = [m.get("id")]

        def take_id():
            if first_id:
                return first_id.pop()
            return gen("c")
        b = a = None
        if t0 - ms >= MIN_LEN:
            b = trim_end(m, min(me, t0 + h))
            b["id"] = take_id()
            b = set_fade(b, b.get("fade_in"), xf)
            b["stack_id"], b["stack_active"] = sb, is_act
            befores.append(b)
        if t1 > ms and t0 < me:
            md = trim_start(trim_end(m, min(me, t1 + h)), max(ms, t0 - h))
            md["id"] = take_id()
            fi = xf if t0 - ms >= MIN_LEN else _num(m.get("fade_in"))
            fo = xf if me - t1 >= MIN_LEN else _num(m.get("fade_out"))
            md = set_fade(md, fi, fo)
            md["stack_id"], md["stack_active"] = sm, False
            mids.append(md)
        if me - t1 >= MIN_LEN:
            a = trim_start(m, max(ms, t1 - h))
            a["id"] = take_id()
            a = set_fade(a, xf, a.get("fade_out"))
            a["stack_id"], a["stack_active"] = sa, is_act
            afters.append(a)
        if is_act:
            has_b, has_a = b is not None, a is not None
    p = normalize(punch_clip)
    p = set_fade(p, xf if has_b else 0.0, xf if has_a else 0.0)
    p["stack_id"], p["stack_active"] = sm, True
    mids.append(p)
    ids_old = {c.get("id") for c in members}
    first = min(_find(clips, c.get("id")) for c in members)
    rest = [dict(c) for c in clips if c.get("id") not in ids_old]
    out = rest[:first] + befores + mids + afters + rest[first:]
    return _dissolve_singletons(out)


# ---------------- Revize 4: klip / bolge efekti ----------------
def _fx_copy(fx: Any) -> list[dict[str, Any]]:
    """Klip fx zincirinin derin kopyasi (bolunen parcalar ayni listeyi paylasmasin)."""
    out = []
    for f in fx or []:
        if isinstance(f, dict):
            d = dict(f)
            if isinstance(d.get("params"), dict):
                d["params"] = dict(d["params"])
            out.append(d)
    return out


def _with_fx(c: dict[str, Any]) -> dict[str, Any]:
    if isinstance(c.get("fx"), list):
        c["fx"] = _fx_copy(c["fx"])
    return c


def has_clip_fx(clip: dict[str, Any]) -> bool:
    """Klibin duyulan (bypass'siz) kendi efekti var mi ya da kanal efektini atliyor mu (rozet)."""
    return any(isinstance(f, dict) and not f.get("bypass") for f in (clip.get("fx") or [])) or bool(clip.get("skip_track_fx"))


def region_split(clips: list[dict[str, Any]], clip_id: str, t0: float, t1: float, xfade: float = XFADE,
                 ids: Any = None, fx: Any = None) -> dict[str, Any]:
    """'Bu bolgeye efekt': hedef klip (destesiyse tum uyeleri) t0/t1'den once / orta / sonra olarak bolunur.
    Sinirlarda xfade capraz gecis (punch_in ile ayni geometri: onceki parca t0+xf/2'ye uzar ve fade-out alir,
    orta parca t0-xf/2'den baslar ve fade-in alir; t1 simetrik). Ayni kaynak sesin dogrusal capraz gecisi
    toplamda birim kazanc oldugundan efektsiz halde duyulan ses degismez.
    Tum parcalar ozgun klibin fx zincirini (derin kopya) tasir; fx verilirse ortadaki AKTIF parcaya o atanir.
    ids: liste (sirayla tuketilir) ya da cagrilabilir(kind) -> belirlenebilir kimlik (JS esdegerlik testi).
    Dondurur: {clips, mid_id} (bolunemediyse mid_id = '')."""
    if isinstance(ids, list):
        pool = list(ids)

        def gen(kind):
            return pool.pop(0) if pool else (new_stack_id() if kind == "s" else _new_id())
    else:
        gen = ids or (lambda kind: (new_stack_id() if kind == "s" else _new_id()))
    i = _find(clips, clip_id)
    if i < 0:
        return {"clips": [dict(c) for c in clips], "mid_id": ""}
    target = clips[i]
    sid = target.get("stack_id")
    members = [c for c in clips if c.get("stack_id") == sid] if sid else [target]
    act_id = stack_active_id(clips, sid) if sid else target.get("id")
    act = next((c for c in members if c.get("id") == act_id), target)
    s, e = clip_bounds(act)
    t0 = max(_num(t0), s)
    t1 = min(_num(t1), e)
    if t1 - t0 < MIN_LEN:
        return {"clips": [dict(c) for c in clips], "mid_id": ""}
    xf = max(0.0, _num(xfade))
    h = xf / 2.0
    has_b = t0 - s >= MIN_LEN
    has_a = e - t1 >= MIN_LEN
    sb = sm = sa = ""
    if sid:
        sb = sid
        sm = gen("s") if has_b else sid
        sa = gen("s") if has_a else sid
    befores, mids, afters = [], [], []
    mid_id = ""
    for m in members:
        ms, me = clip_bounds(m)
        is_act = m.get("id") == act_id
        first = [m.get("id")]

        def nid():
            return first.pop() if first else gen("c")
        if has_b:
            b = _with_fx(set_fade(trim_end(m, min(me, t0 + h)), m.get("fade_in"), xf))
            b["id"] = nid()
            if sid:
                b["stack_id"], b["stack_active"] = sb, bool(m.get("stack_active"))
            befores.append(b)
        md = m
        if has_a:
            md = trim_end(md, min(me, t1 + h))
        if has_b:
            md = trim_start(md, max(ms, t0 - h))
        md = _with_fx(set_fade(md, xf if has_b else m.get("fade_in"), xf if has_a else m.get("fade_out")))
        md["id"] = nid()
        if sid:
            md["stack_id"], md["stack_active"] = sm, bool(m.get("stack_active"))
        if is_act:
            mid_id = md["id"]
            if fx is not None:
                md["fx"] = _fx_copy(fx)
        mids.append(md)
        if has_a:
            a = _with_fx(set_fade(trim_start(m, max(ms, t1 - h)), xf, m.get("fade_out")))
            a["id"] = nid()
            if sid:
                a["stack_id"], a["stack_active"] = sa, bool(m.get("stack_active"))
            afters.append(a)
    ids_old = {c.get("id") for c in members}
    first_i = min(_find(clips, c.get("id")) for c in members)
    rest = [dict(c) for c in clips if c.get("id") not in ids_old]
    out = rest[:first_i] + befores + mids + afters + rest[first_i:]
    return {"clips": _dissolve_singletons(out), "mid_id": mid_id}


def apply_fx_to_stack(clips: list[dict[str, Any]], clip_id: str) -> list[dict[str, Any]]:
    """'Tum desteye uygula': klibin fx zinciri + skip_track_fx destedeki tum take'lere kopyalanir."""
    out = [dict(c) for c in clips]
    i = _find(out, clip_id)
    if i < 0 or not out[i].get("stack_id"):
        return out
    src = out[i]
    for c in out:
        if c.get("stack_id") == src.get("stack_id") and c.get("id") != src.get("id"):
            c["fx"] = _fx_copy(src.get("fx"))
            c["skip_track_fx"] = bool(src.get("skip_track_fx"))
    return out
