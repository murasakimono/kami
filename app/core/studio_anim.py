"""Kami Studio animasyonlari: klip (video/gorsel) ve yazi icin Giris / Cikis / Dongu.

Klip animasyonu tek tablodan iki yere cevrilir: ffmpeg ifadeleri (disa aktarim) ve ayni sayilar
JS'te (onizleme, catalog ile gider). Yazi animasyonlari ASS etiketleri: onizleme (JASSUB) ve disa
aktarim (libass) ayni ASS'i kullandigi icin birebir ayni gorunur.
"""
from __future__ import annotations

import math

# ---------------------------------------------------------------- klip animasyonlari
# Giris: baslangic durumu -> normal. Cikis: normal -> bitis durumu.
# s: olcek, sx/sy: tek eksen olcek (3B cevirme hissi), x/y: kayma (ekran orani), r: derece, a: saydamlik, b: bulaniklik
CLIP_IN = {
    "fade": {"name": "Belir", "a": 1},
    "zoom-in": {"name": "Yakınlaşarak", "s": 0.6, "a": 1},
    "zoom-out": {"name": "Uzaklaşarak", "s": 1.6, "a": 1},
    "pop": {"name": "Pop", "s": 0.3, "ease": "back"},
    "slide-l": {"name": "Soldan kay", "x": -1.0},
    "slide-r": {"name": "Sağdan kay", "x": 1.0},
    "slide-u": {"name": "Yukarıdan kay", "y": -1.0},
    "slide-d": {"name": "Aşağıdan kay", "y": 1.0},
    "push-l": {"name": "Soldan it", "x": -0.35, "a": 1},
    "push-r": {"name": "Sağdan it", "x": 0.35, "a": 1},
    "rise": {"name": "Yüksel", "y": 0.12, "a": 1},
    "drop": {"name": "Düş", "y": -0.25, "ease": "bounce"},
    "spin": {"name": "Dönerek", "r": -180, "s": 0.3, "a": 1},
    "spin-cw": {"name": "Saat yönünde", "r": 90, "a": 1},
    "swing": {"name": "Sallanarak", "r": -25, "ease": "elastic"},
    "flip-x": {"name": "Yatay çevir (3B)", "sx": 0.0},
    "flip-y": {"name": "Dikey çevir (3B)", "sy": 0.0},
    "stretch": {"name": "Esneyerek", "sx": 1.8, "sy": 0.4, "ease": "elastic"},
    "squeeze": {"name": "Sıkışarak", "sx": 0.2, "sy": 1.4, "ease": "back"},
    "blur": {"name": "Bulanıktan net", "b": 30, "a": 1},
    "zoom-blur": {"name": "Zoom + bulanık", "s": 1.4, "b": 24, "a": 1},
    "elastic": {"name": "Elastik", "s": 0.5, "ease": "elastic"},
    "bounce-in": {"name": "Zıplayarak", "s": 0.2, "ease": "bounce"},
    "tilt": {"name": "Eğilerek", "r": 12, "y": 0.08, "a": 1},
    "shake-in": {"name": "Titreyerek", "x": 0.04, "shake": 1, "a": 1},
}
CLIP_OUT = {
    "fade": {"name": "Kaybol", "a": 1},
    "zoom-in": {"name": "Yakınlaşarak", "s": 1.6, "a": 1},
    "zoom-out": {"name": "Uzaklaşarak", "s": 0.5, "a": 1},
    "pop": {"name": "Pop", "s": 0.0, "ease": "back"},
    "slide-l": {"name": "Sola kay", "x": -1.0},
    "slide-r": {"name": "Sağa kay", "x": 1.0},
    "slide-u": {"name": "Yukarı kay", "y": -1.0},
    "slide-d": {"name": "Aşağı kay", "y": 1.0},
    "push-l": {"name": "Sola it", "x": -0.35, "a": 1},
    "push-r": {"name": "Sağa it", "x": 0.35, "a": 1},
    "sink": {"name": "Bat", "y": 0.12, "a": 1},
    "fall": {"name": "Düş (yerçekimi)", "y": 1.1, "r": 18},
    "spin": {"name": "Dönerek", "r": 180, "s": 0.2, "a": 1},
    "flip-x": {"name": "Yatay çevir (3B)", "sx": 0.0},
    "flip-y": {"name": "Dikey çevir (3B)", "sy": 0.0},
    "stretch": {"name": "Esneyerek", "sx": 1.8, "sy": 0.2, "a": 1},
    "blur": {"name": "Bulanıklaşarak", "b": 30, "a": 1},
    "zoom-blur": {"name": "Zoom + bulanık", "s": 1.5, "b": 24, "a": 1},
    "tilt": {"name": "Eğilerek", "r": -12, "y": 0.08, "a": 1},
    "shake-out": {"name": "Titreyerek", "x": 0.04, "shake": 1, "a": 1},
}
# Dongu: tum klip boyunca (f: hz)
CLIP_LOOP = {
    "pulse": {"name": "Nabız", "s": 0.05, "f": 1.6},
    "breathe": {"name": "Nefes", "s": 0.03, "f": 0.35},
    "heartbeat": {"name": "Kalp atışı", "beat": 0.08, "f": 1.2},
    "wobble": {"name": "Yalpala", "r": 3, "f": 2.0},
    "swing": {"name": "Sallan", "r": 7, "f": 0.7},
    "float": {"name": "Süzül", "y": 0.015, "f": 0.6},
    "shake": {"name": "Sarsıl", "x": 0.008, "y": 0.008, "f": 12},
    "jitter": {"name": "Kıpır kıpır", "x": 0.003, "y": 0.003, "f": 23},
    "spin": {"name": "Sürekli dön", "spin": 90},
    "kenburns": {"name": "Ken Burns (yavaş zoom)", "grow": 0.12},
    "kenburns-out": {"name": "Ken Burns (geri)", "grow": -0.1},
    "pan-l": {"name": "Yavaş sola kay", "pan": -0.06},
    "pan-r": {"name": "Yavaş sağa kay", "pan": 0.06},
    "flip3d": {"name": "3B salınım", "sx": 0.12, "f": 0.5},
    "earthquake": {"name": "Deprem", "x": 0.02, "y": 0.015, "f": 9, "r": 1.2},
}
EASE_NAMES = {"out": "Yumuşak", "linear": "Doğrusal", "back": "Geri yaylan", "elastic": "Elastik", "bounce": "Zıpla"}


def clip_catalog() -> dict:
    return {"in": CLIP_IN, "out": CLIP_OUT, "loop": CLIP_LOOP, "ease": EASE_NAMES}


def _ease(e: str, p: str) -> str:
    """p (0..1) -> eğrili ilerleme (ffmpeg ifadesi)."""
    if e == "linear":
        return p
    if e == "back":
        return f"(1+2.70158*pow({p}-1,3)+1.70158*pow({p}-1,2))"
    if e == "elastic":
        return f"(1-exp(-6*{p})*cos(12*{p}))"
    if e == "bounce":
        return f"(1-abs(cos({p}*PI*1.5))*exp(-4*{p}))"
    return f"(1-pow(1-{p},3))"


def _wins(c: dict, d: float) -> tuple[dict | None, float, dict | None, float, dict | None]:
    an = c.get("anim") or {}
    if not isinstance(an, dict):
        return None, 0, None, 0, None
    ai, ao, al = CLIP_IN.get(an.get("in") or ""), CLIP_OUT.get(an.get("out") or ""), CLIP_LOOP.get(an.get("loop") or "")
    di = min(d, max(0.05, float(an.get("inDur", 0.5) or 0.5))) if ai else 0.0
    do = min(d - di, max(0.05, float(an.get("outDur", 0.5) or 0.5))) if ao else 0.0
    if ai:
        ai = {**ai, "ease": an.get("inEase") or ai.get("ease", "out")}
    if ao:
        ao = {**ao, "ease": an.get("outEase") or ao.get("ease", "out")}
    if al:
        k = float(an.get("loopAmt", 1) or 1)
        sp = float(an.get("loopSpeed", 1) or 1)
        al = {**al, "k": k, "sp": sp}
    return ai, di, ao, do, al


def clip_exprs(c: dict, d: float, L: str) -> dict[str, str]:
    """L: klip-yerel zaman ifadesi (sn). Doner: s, sx, sy, x, y, r ifadeleri ('' = sabit)."""
    ai, di, ao, do, al = _wins(c, d)
    out = {"s": [], "sx": [], "sy": [], "x": [], "y": [], "r": []}
    if ai:
        p = f"clip({L}/{di:.4f},0,1)"
        e = _ease(ai["ease"], p)
        inv = f"(1-{e})"
        for k in ("s", "sx", "sy"):
            if k in ai:
                out[k].append(f"(1+({ai[k] - 1:.4f})*{inv})")
        for k in ("x", "y", "r"):
            if k in ai:
                v = f"{ai[k]:.4f}*{inv}"
                if ai.get("shake"):
                    v = f"{v}*sin({L}*70)"
                out[k].append(v)
    if ao:
        q = f"clip(({L}-{d - do:.4f})/{do:.4f},0,1)"
        e = f"pow({q},3)" if ao["ease"] in ("out", "linear") else _ease(ao["ease"], q)
        for k in ("s", "sx", "sy"):
            if k in ao:
                out[k].append(f"(1+({ao[k] - 1:.4f})*{e})")
        for k in ("x", "y", "r"):
            if k in ao:
                v = f"{ao[k]:.4f}*{e}"
                if ao.get("shake"):
                    v = f"{v}*sin({L}*70)"
                out[k].append(v)
    if al:
        kk, f = al["k"], al.get("f", 1) * al["sp"]
        w = f"2*PI*{f:.4f}*{L}"
        if "s" in al:
            out["s"].append(f"(1+{al['s'] * kk:.4f}*sin({w}))")
        if "beat" in al:
            out["s"].append(f"(1+{al['beat'] * kk:.4f}*pow(max(0,sin({w})),8))")
        if "sx" in al:
            out["sx"].append(f"(1-{al['sx'] * kk:.4f}*(1+sin({w}))/2)")
        if "x" in al:
            out["x"].append(f"{al['x'] * kk:.4f}*sin({w})")
        if "y" in al:
            out["y"].append(f"{al['y'] * kk:.4f}*cos({w}*1.13)")
        if "r" in al:
            out["r"].append(f"{al['r'] * kk:.4f}*sin({w}*0.9)")
        if "spin" in al:
            out["r"].append(f"{al['spin'] * kk * al['sp']:.4f}*{L}")
        if "grow" in al:
            out["s"].append(f"(1+{al['grow'] * kk:.4f}*clip({L}/{d:.4f},0,1))")
        if "pan" in al:
            out["x"].append(f"{al['pan'] * kk:.4f}*clip({L}/{d:.4f},0,1)")
    res = {}
    for k, v in out.items():
        if not v:
            res[k] = ""
        elif k in ("s", "sx", "sy"):
            res[k] = "*".join(v)
        else:
            res[k] = "(" + "+".join(v) + ")"
    return res


def clip_fades(c: dict, d: float) -> tuple[float, float, float, float]:
    """(giris saydamlik suresi, cikis saydamlik suresi, giris bulanik, cikis bulanik)"""
    ai, di, ao, do, _ = _wins(c, d)
    return (di if ai and ai.get("a") else 0.0, do if ao and ao.get("a") else 0.0,
            float(ai.get("b", 0)) if ai else 0.0, float(ao.get("b", 0)) if ao else 0.0)


def clip_filters(c: dict, d: float, cut0: float, fps: int, W: int, H: int, tag: str) -> tuple[list[str], dict[str, str]]:
    """Klip zincirine eklenecek filtreler (perspective ile olcek, bulaniklik, saydamlik) + bindirme ifadeleri.
    Zincir burada W x H RGBA tuvalde. Donen dict: x, y (ekran orani ifadesi, L ile), r (derece, L ile)."""
    an = c.get("anim") or {}
    if not isinstance(an, dict) or not (an.get("in") or an.get("out") or an.get("loop")):
        return [], {}
    Lon = f"(on/{fps}+{cut0:.4f})"
    ex = clip_exprs(c, d, Lon)
    ch: list[str] = []
    if ex["s"] or ex["sx"] or ex["sy"]:
        s = ex["s"] or "1"
        sx = f"({s})*({ex['sx'] or '1'})"
        sy = f"({s})*({ex['sy'] or '1'})"
        hx, hy = f"(W/2)*(1-{sx})", f"(H/2)*(1-{sy})"
        ch.append(f"format=rgba,pad={W + 4}:{H + 4}:2:2:color=black@0")
        ch.append(f"perspective=x0='{hx}':y0='{hy}':x1='W-{hx}':y1='{hy}':x2='{hx}':y2='H-{hy}':x3='W-{hx}':y3='H-{hy}'"
                  f":sense=destination:eval=frame")
        ch.append(f"crop={W}:{H}:2:2")
    fi, fo, bi, bo = clip_fades(c, d)
    _, di, _, do, _ = _wins(c, d)
    if bi or bo:   # bulaniklik: bulanik kopyayla zamana bagli karisim
        Lt = f"(T+{cut0:.4f})"
        parts = []
        if bi:
            parts.append(f"(1-clip({Lt}/{di:.4f},0,1))")
        if bo:
            parts.append(f"clip(({Lt}-{d - do:.4f})/{do:.4f},0,1)")
        wexp = "max(" + ",".join(parts) + ",0)" if len(parts) > 1 else parts[0]
        sig = max(bi, bo)
        ch.append(f"split[{tag}ba][{tag}bb];[{tag}bb]gblur=sigma={sig:.1f}[{tag}bc];[{tag}ba][{tag}bc]blend=all_expr='A*(1-{wexp})+B*{wexp}'")
    if fi > 0 and cut0 < fi:
        ch.append(f"fade=t=in:st={-cut0:.3f}:d={fi:.3f}:alpha=1")
    if fo > 0:
        ch.append(f"fade=t=out:st={d - cut0 - fo:.3f}:d={fo:.3f}:alpha=1")
    return ch, {"x": ex["x"], "y": ex["y"], "r": ex["r"]}


# ---------------------------------------------------------------- yazi animasyonlari (ASS)
TEXT_IN = {
    "none": "Yok", "fade": "Belir", "pop": "Pop", "zoom": "Büyüyerek", "shrink": "Küçülerek", "slide-u": "Aşağıdan kay",
    "slide-d": "Yukarıdan kay", "slide-l": "Sağdan kay", "slide-r": "Soldan kay", "bounce": "Zıpla", "drop": "Düş",
    "spin": "Dönerek", "flip-x": "Yatay çevir", "flip-y": "Dikey çevir", "blur": "Bulanıktan net", "stretch": "Gerilerek",
    "squash": "Ezilerek", "elastic": "Elastik", "glitch": "Glitch", "flash": "Parlayarak", "wipe": "Soldan sil",
    "wipe-r": "Sağdan sil", "wipe-u": "Aşağıdan sil", "unfold": "Açılarak", "swing": "Sallanarak", "tilt": "Eğilerek",
    "type": "Daktilo", "letters": "Harf harf belir", "letters-up": "Harf harf yüksel", "letters-blur": "Harf harf netleş",
    "letters-color": "Harf harf renklen", "letters-spin": "Harf harf dön", "words": "Kelime kelime", "words-pop": "Kelime kelime pop",
    "scramble": "Karışık harf", "neon-on": "Neon yanış",
}
TEXT_OUT = {
    "none": "Yok", "fade": "Kaybol", "pop": "Pop", "zoom": "Büyüyerek kaybol", "shrink": "Küçülerek", "slide-u": "Yukarı kay",
    "slide-d": "Aşağı kay", "slide-l": "Sola kay", "slide-r": "Sağa kay", "drop": "Düş", "spin": "Dönerek", "flip-x": "Yatay çevir",
    "flip-y": "Dikey çevir", "blur": "Bulanıklaş", "stretch": "Gerilerek", "glitch": "Glitch", "flash": "Parlayarak",
    "wipe": "Sağa sil", "wipe-l": "Sola sil", "fold": "Katlanarak", "tilt": "Eğilerek", "type": "Silinerek (daktilo)",
    "letters": "Harf harf kaybol", "letters-down": "Harf harf düş", "letters-blur": "Harf harf bulanıklaş", "words": "Kelime kelime",
}
TEXT_LOOP = {
    "none": "Yok", "pulse": "Nabız", "breathe": "Nefes", "heartbeat": "Kalp atışı", "wobble": "Yalpala", "swing": "Sallan",
    "float": "Süzül", "shake": "Titreş", "jitter": "Kıpır kıpır", "glitch": "Glitch", "flicker": "Titrek ışık", "blink": "Yanıp sön",
    "rainbow": "Gökkuşağı", "glow": "Parıltı nabzı", "wave": "Dalga (harf)", "jelly": "Jöle", "tilt3d": "3B salınım", "spin": "Sürekli dön",
}


def text_catalog() -> dict:
    return {"in": TEXT_IN, "out": TEXT_OUT, "loop": TEXT_LOOP}


_PER_CHAR_IN = {"type", "letters", "letters-up", "letters-blur", "letters-color", "letters-spin", "words", "words-pop", "scramble"}
_PER_CHAR_OUT = {"type", "letters", "letters-down", "letters-blur", "words"}


def _ms(v: float) -> int:
    return int(round(v))


def _in_tags(kind: str, D: int, x: float, y: float, W: int, H: int, tw: float, th: float) -> tuple[str, tuple | None]:
    """Giris etiketleri (D ms). Doner: (etiketler, move) move=(x1,y1,x2,y2,t1,t2) ya da None."""
    if kind == "fade":
        return f"\\fad({D},0)", None
    if kind == "pop":
        a = _ms(D * 0.6)
        return f"\\fscx20\\fscy20\\t(0,{a},\\fscx112\\fscy112)\\t({a},{D},\\fscx100\\fscy100)", None
    if kind == "zoom":
        return f"\\fscx40\\fscy40\\alpha&HFF&\\t(0,{D},0.6,\\fscx100\\fscy100\\alpha&H00&)", None
    if kind == "shrink":
        return f"\\fscx260\\fscy260\\alpha&HFF&\\t(0,{D},0.5,\\fscx100\\fscy100\\alpha&H00&)", None
    if kind in ("slide-u", "slide-d", "slide-l", "slide-r"):
        dx = {"slide-l": W * 0.25, "slide-r": -W * 0.25}.get(kind, 0)
        dy = {"slide-u": H * 0.12, "slide-d": -H * 0.12}.get(kind, 0)
        return f"\\alpha&HFF&\\t(0,{_ms(D * 0.7)},\\alpha&H00&)", (x + dx, y + dy, x, y, 0, D)
    if kind == "bounce":
        a, b = _ms(D * 0.6), _ms(D * 0.8)
        return f"\\t({a},{b},\\fscy82\\fscx112)\\t({b},{D},\\fscy100\\fscx100)", (x, y - H * 0.18, x, y, 0, a)
    if kind == "drop":
        a = _ms(D * 0.55)
        return f"\\t({a},{_ms(D * 0.7)},\\fscy88)\\t({_ms(D * 0.7)},{D},\\fscy100)", (x, y - H * 0.5, x, y, 0, a)
    if kind == "spin":
        return f"\\frz-360\\fscx10\\fscy10\\t(0,{D},0.6,\\frz0\\fscx100\\fscy100)", None
    if kind == "flip-x":
        return f"\\fry90\\t(0,{D},\\fry0)", None
    if kind == "flip-y":
        return f"\\frx90\\t(0,{D},\\frx0)", None
    if kind == "blur":
        return f"\\blur30\\alpha&HFF&\\t(0,{D},\\blur0\\alpha&H00&)", None
    if kind == "stretch":
        a = _ms(D * 0.7)
        return f"\\fscx300\\fscy20\\alpha&H80&\\t(0,{a},\\fscx92\\fscy108\\alpha&H00&)\\t({a},{D},\\fscx100\\fscy100)", None
    if kind == "squash":
        a = _ms(D * 0.7)
        return f"\\fscx20\\fscy260\\t(0,{a},\\fscx108\\fscy94)\\t({a},{D},\\fscx100\\fscy100)", None
    if kind == "elastic":
        st = [(0.0, 10), (0.35, 125), (0.55, 88), (0.72, 108), (0.86, 97), (1.0, 100)]
        return "\\fscx10\\fscy10" + "".join(f"\\t({_ms(D * a)},{_ms(D * b)},\\fscx{v}\\fscy{v})" for (a, _), (b, v) in zip(st, st[1:])), None
    if kind == "glitch":
        n = max(3, D // 50)
        return "\\alpha&H60&" + "".join(f"\\t({i * 50},{i * 50 + 25},\\fax{0.4 if i % 2 else -0.4}\\fscx{120 if i % 3 == 0 else 95}\\alpha&H{max(0, 0x60 - i * 18):02X}&)"
                                         for i in range(n)) + f"\\t({D - 30},{D},\\fax0\\fscx100\\alpha&H00&)", None
    if kind == "flash":
        return f"\\1c&HFFFFFF&\\3c&HFFFFFF&\\blur18\\alpha&HFF&\\t(0,{_ms(D * 0.3)},\\alpha&H00&)\\t({_ms(D * 0.3)},{D},\\blur0)", "RESTORE_COL"
    if kind in ("wipe", "wipe-r", "wipe-u", "unfold"):
        l, r, t, b = x - tw / 2, x + tw / 2, y - th / 2, y + th / 2
        if kind == "wipe":
            return f"\\clip({l:.0f},0,{l:.0f},{H})\\t(0,{D},\\clip({l:.0f},0,{r:.0f},{H}))", None
        if kind == "wipe-r":
            return f"\\clip({r:.0f},0,{r:.0f},{H})\\t(0,{D},\\clip({l:.0f},0,{r:.0f},{H}))", None
        if kind == "wipe-u":
            return f"\\clip(0,{b:.0f},{W},{b:.0f})\\t(0,{D},\\clip(0,{t:.0f},{W},{b:.0f}))", None
        return f"\\clip({x:.0f},0,{x:.0f},{H})\\t(0,{D},\\clip({l:.0f},0,{r:.0f},{H}))", None
    if kind == "swing":
        st = [(0, -30), (0.4, 14), (0.65, -7), (0.85, 3), (1.0, 0)]
        return f"\\frz-30" + "".join(f"\\t({_ms(D * a)},{_ms(D * b)},\\frz{v})" for (a, _), (b, v) in zip(st, st[1:])), None
    if kind == "tilt":
        return f"\\frz14\\alpha&HFF&\\t(0,{D},\\frz0\\alpha&H00&)", (x, y + H * 0.06, x, y, 0, D)
    if kind == "neon-on":
        seq = [(0, "FF"), (0.12, "30"), (0.2, "FF"), (0.35, "40"), (0.42, "D0"), (0.6, "10"), (0.68, "90"), (1.0, "00")]
        return "\\alpha&HFF&" + "".join(f"\\t({_ms(D * a)},{_ms(D * a) + 1},\\alpha&H{v}&)" for a, v in seq), None
    return "", None


def _out_tags(kind: str, D: int, x: float, y: float, W: int, H: int, tw: float, th: float) -> tuple[str, tuple | None]:
    if kind == "fade":
        return f"\\fad(0,{D})", None
    if kind == "pop":
        a = _ms(D * 0.35)
        return f"\\t(0,{a},\\fscx112\\fscy112)\\t({a},{D},\\fscx0\\fscy0)", None
    if kind == "zoom":
        return f"\\t(0,{D},1.6,\\fscx250\\fscy250\\alpha&HFF&)", None
    if kind == "shrink":
        return f"\\t(0,{D},1.6,\\fscx20\\fscy20\\alpha&HFF&)", None
    if kind in ("slide-u", "slide-d", "slide-l", "slide-r"):
        dx = {"slide-l": -W * 0.25, "slide-r": W * 0.25}.get(kind, 0)
        dy = {"slide-u": -H * 0.12, "slide-d": H * 0.12}.get(kind, 0)
        return f"\\t({_ms(D * 0.3)},{D},\\alpha&HFF&)", (x, y, x + dx, y + dy, 0, D)
    if kind == "drop":
        return f"\\t(0,{D},1.8,\\frz12)", (x, y, x, y + H * 0.7, 0, D)
    if kind == "spin":
        return f"\\t(0,{D},1.6,\\frz360\\fscx10\\fscy10\\alpha&HFF&)", None
    if kind == "flip-x":
        return f"\\t(0,{D},\\fry90)", None
    if kind == "flip-y":
        return f"\\t(0,{D},\\frx90)", None
    if kind == "blur":
        return f"\\t(0,{D},\\blur30\\alpha&HFF&)", None
    if kind == "stretch":
        return f"\\t(0,{D},1.5,\\fscx320\\fscy15\\alpha&HFF&)", None
    if kind == "glitch":
        n = max(3, D // 50)
        return "".join(f"\\t({i * 50},{i * 50 + 25},\\fax{0.4 if i % 2 else -0.4}\\fscx{120 if i % 3 == 0 else 95}\\alpha&H{min(255, i * 255 // n):02X}&)"
                       for i in range(n)) + f"\\t({D - 20},{D},\\alpha&HFF&)", None
    if kind == "flash":
        return f"\\t(0,{_ms(D * 0.6)},\\1c&HFFFFFF&\\3c&HFFFFFF&\\blur18)\\t({_ms(D * 0.6)},{D},\\alpha&HFF&)", None
    if kind in ("wipe", "wipe-l", "fold"):
        l, r = x - tw / 2, x + tw / 2
        if kind == "wipe":
            return f"\\clip({l:.0f},0,{r:.0f},{H})\\t(0,{D},\\clip({r:.0f},0,{r:.0f},{H}))", None
        if kind == "wipe-l":
            return f"\\clip({l:.0f},0,{r:.0f},{H})\\t(0,{D},\\clip({l:.0f},0,{l:.0f},{H}))", None
        return f"\\clip({l:.0f},0,{r:.0f},{H})\\t(0,{D},\\clip({x:.0f},0,{x:.0f},{H}))", None
    if kind == "tilt":
        return f"\\t(0,{D},\\frz-14\\alpha&HFF&)", (x, y, x, y + H * 0.06, 0, D)
    return "", None


def _loop_tags(kind: str, D: int, x: float, y: float, W: int, H: int) -> str:
    """Dongu: D ms boyunca tekrar eden \\t dizisi (cok uzun yazilarda 600 adimla sinirli)."""
    def rep(period: int, steps: list[tuple[float, str]]) -> str:
        out, t, n = [], 0, 0
        while t < D and n < 600:
            for (a, _), (b, tag) in zip(steps, steps[1:]):
                t0, t1 = t + _ms(period * a), t + _ms(period * b)
                if t0 >= D:
                    break
                out.append(f"\\t({t0},{min(t1, D)},{tag})")
                n += 1
            t += period
        return "".join(out)
    org_far_y = f"\\org({x:.0f},{y + 20000:.0f})"   # uzak donme merkezi: kucuk aci ~ yatay kayma
    org_far_x = f"\\org({x + 20000:.0f},{y:.0f})"   # ~ dikey kayma
    px = lambda d: d / 20000 * 180 / math.pi   # noqa: E731  piksel -> derece (uzak merkez)
    if kind == "pulse":
        return rep(620, [(0, ""), (0.5, "\\fscx107\\fscy107"), (1, "\\fscx100\\fscy100")])
    if kind == "breathe":
        return rep(2600, [(0, ""), (0.5, "\\fscx104\\fscy104"), (1, "\\fscx100\\fscy100")])
    if kind == "heartbeat":
        return rep(900, [(0, ""), (0.12, "\\fscx112\\fscy112"), (0.24, "\\fscx100\\fscy100"), (0.36, "\\fscx108\\fscy108"), (0.5, "\\fscx100\\fscy100"), (1, "\\fscx100\\fscy100")])
    if kind == "wobble":
        return rep(500, [(0, ""), (0.25, "\\frz4"), (0.75, "\\frz-4"), (1, "\\frz0")])
    if kind == "swing":
        return rep(1500, [(0, ""), (0.25, "\\frz9"), (0.75, "\\frz-9"), (1, "\\frz0")])
    if kind == "float":
        a = px(H * 0.014)
        return org_far_x + rep(1600, [(0, ""), (0.5, f"\\frz{a:.4f}"), (1, f"\\frz{-a:.4f}")])
    if kind == "shake":
        a = px(W * 0.006)
        return org_far_y + rep(90, [(0, ""), (0.5, f"\\frz{a:.4f}"), (1, f"\\frz{-a:.4f}")])
    if kind == "jitter":
        return rep(140, [(0, ""), (0.33, "\\frz1.5\\fscx102"), (0.66, "\\frz-1\\fscy103"), (1, "\\frz0\\fscx100\\fscy100")])
    if kind == "glitch":
        return rep(700, [(0, ""), (0.8, "\\fax0"), (0.84, "\\fax0.35\\fscx118"), (0.9, "\\fax-0.25\\fscx92"), (1, "\\fax0\\fscx100")])
    if kind == "flicker":
        return rep(1300, [(0, ""), (0.62, "\\alpha&H00&"), (0.64, "\\alpha&HB0&"), (0.68, "\\alpha&H00&"), (0.7, "\\alpha&H90&"), (0.74, "\\alpha&H00&"), (1, "\\alpha&H00&")])
    if kind == "blink":
        return rep(900, [(0, ""), (0.5, "\\alpha&H00&"), (0.52, "\\alpha&HFF&"), (0.98, "\\alpha&HFF&"), (1, "\\alpha&H00&")])
    if kind == "rainbow":
        cols = ["&H3C3CFF&", "&H00A5FF&", "&H00E6FF&", "&H5AE62E&", "&HFFA82E&", "&HE65AB4&", "&H3C3CFF&"]
        st = [(i / (len(cols) - 1), f"\\1c{c}") for i, c in enumerate(cols)]
        return rep(2400, [(0, "")] + st[1:])
    if kind == "glow":
        return rep(1200, [(0, ""), (0.5, "\\blur8\\bord12"), (1, "\\blur2")])
    if kind == "jelly":
        return rep(800, [(0, ""), (0.25, "\\fscx110\\fscy92"), (0.5, "\\fscx94\\fscy106"), (0.75, "\\fscx104\\fscy97"), (1, "\\fscx100\\fscy100")])
    if kind == "tilt3d":
        return rep(2200, [(0, ""), (0.25, "\\fry18"), (0.75, "\\fry-18"), (1, "\\fry0")])
    if kind == "spin":
        return f"\\t(0,{D},\\frz{-360 * max(1, D // 2000)})"
    return ""


def _units(text: str, words: bool) -> list[str]:
    if not words:
        return list(text)
    import re
    return re.findall(r"\S+\s*|\s+", text) or [text]


def text_events(text: str, st: dict, s: float, e: float, x: float, y: float, W: int, H: int, base: str,
                esc, ts, layer: int = 5, extra: str = "") -> list[str]:
    """Yeni yazi animasyonu sistemi: giris / orta / cikis bolumleri ayri satir (her biri kendi \\move'u)."""
    dur = max(0.05, e - s)
    ki, ko, kl = st.get("animIn") or "none", st.get("animOut") or "none", st.get("animLoop") or "none"
    di = min(dur * 0.6, max(0.08, float(st.get("inDur", 0.45) or 0.45))) if ki != "none" else 0.0
    do = min(max(0.0, dur - di) * 0.9, max(0.08, float(st.get("outDur", 0.4) or 0.4))) if ko != "none" else 0.0
    size = float(st.get("size", 7)) * H / 100
    tw = max(size, len(text.split("\\N")[0]) * size * 0.58)
    th = size * 1.3 * (1 + text.count("\n"))
    pos = f"\\pos({x:.0f},{y:.0f})"
    segs = []
    if di:
        segs.append(("in", s, s + di))
    if dur - di - do > 0.01:
        segs.append(("mid", s + di, e - do))
    if do:
        segs.append(("out", e - do, e))
    out = []
    for kind, a, b in segs:
        D = max(1, int((b - a) * 1000))
        tags, move, body = "", None, None
        if kind == "in":
            if ki in _PER_CHAR_IN:
                body = _per_char_in(ki, text, D, esc, st)
            else:
                tags, move = _in_tags(ki, D, x, y, W, H, tw, th)
                if move == "RESTORE_COL":
                    move = None
        elif kind == "out":
            if ko in _PER_CHAR_OUT:
                body = _per_char_out(ko, text, D, esc)
            else:
                tags, move = _out_tags(ko, D, x, y, W, H, tw, th)
        if kl != "none" and not (kind == "in" and ki != "none" and ki not in ("fade", "blur")):
            if kl == "wave" and body is None:
                body = _wave(text, D, esc)
            elif kl != "wave":
                tags += _loop_tags(kl, D, x, y, W, H) if move is None else ""
        p = (f"\\move({move[0]:.0f},{move[1]:.0f},{move[2]:.0f},{move[3]:.0f},{move[4]},{move[5]})" if move else pos)
        out.append(f"Dialogue: {layer},{ts(a)},{ts(b)},Default,,0,0,0,,{{{base}{p}{extra}{tags}}}{body if body is not None else esc(text)}")
    return out


def _per_char_in(kind: str, text: str, D: int, esc, st: dict) -> str:
    us = _units(text, kind.startswith("words"))
    vis = [u for u in us if u.strip()]
    n = max(1, len(vis))
    if kind == "type":
        per = max(15, int(D / n))
        span = 1
    else:
        per = max(12, int(D * 0.6 / n))
        span = max(60, int(D * 0.5))
    out, i = [], 0
    import random
    order = list(range(n))
    random.Random(len(text) * 7919 + sum(map(ord, text))).shuffle(order)
    for u in us:
        if not u.strip():
            out.append(esc(u))
            continue
        t0 = min(D - 1, i * per)
        t1 = min(D, t0 + span)
        if kind == "type":
            tg = f"\\alpha&HFF&\\t({t0},{t0 + 1},\\alpha&H00&)"
        elif kind in ("letters", "words"):
            tg = f"\\alpha&HFF&\\t({t0},{t1},\\alpha&H00&)"
        elif kind == "letters-up":
            tg = f"\\fscy0\\alpha&HFF&\\t({t0},{t1},0.5,\\fscy100\\alpha&H00&)"
        elif kind == "letters-blur":
            tg = f"\\blur20\\alpha&HFF&\\t({t0},{t1},\\blur0\\alpha&H00&)"
        elif kind == "letters-color":
            col = st.get("highlight", "#FFE600").lstrip("#")
            hc = f"&H{col[4:6]}{col[2:4]}{col[0:2]}&" if len(col) == 6 else "&H00E6FF&"
            tg = f"\\alpha&HFF&\\1c{hc}\\t({t0},{t0 + 40},\\alpha&H00&)\\t({t0 + 40},{t1 + 120},\\1c{_col_of(st)})"
        elif kind == "letters-spin":
            tg = f"\\frx90\\alpha&HFF&\\t({t0},{t1},\\frx0\\alpha&H00&)"
        elif kind == "words-pop":
            tg = f"\\fscy10\\alpha&HFF&\\t({t0},{t0 + 90},\\fscy120\\alpha&H00&)\\t({t0 + 90},{t0 + 170},\\fscy100)"
        elif kind == "scramble":   # harfler karisik sirayla belirir
            t0 = min(D - 1, order[i] * per)
            tg = f"\\alpha&HFF&\\t({t0},{t0 + 40},\\alpha&H00&)"
        else:
            tg = ""
        out.append(f"{{{tg}}}{esc(u)}")
        i += 1
    return "".join(out)


def _per_char_out(kind: str, text: str, D: int, esc) -> str:
    us = _units(text, kind == "words")
    vis = [u for u in us if u.strip()]
    n = max(1, len(vis))
    per = max(12, int(D * (1.0 if kind == "type" else 0.6) / n))
    span = 1 if kind == "type" else max(60, int(D * 0.5))
    out, i = [], 0
    order = list(range(len(vis)))
    if kind == "type":
        order = order[::-1]
    rank = {j: order.index(j) for j in range(len(vis))}
    for u in us:
        if not u.strip():
            out.append(esc(u))
            continue
        t0 = min(D - 1, rank[i] * per)
        t1 = min(D, t0 + span)
        if kind in ("type", "letters", "words"):
            tg = f"\\t({t0},{t1},\\alpha&HFF&)"
        elif kind == "letters-down":
            tg = f"\\t({t0},{t1},1.5,\\fscy0\\alpha&HFF&)"
        else:
            tg = f"\\t({t0},{t1},\\blur20\\alpha&HFF&)"
        out.append(f"{{{tg}}}{esc(u)}")
        i += 1
    return "".join(out)


def _wave(text: str, D: int, esc) -> str:
    out = []
    period = 900
    for j, ch in enumerate(text):
        if ch.isspace():
            out.append(esc(ch))
            continue
        ph = (j * 90) % period
        tg, t = "", -ph
        n = 0
        while t < D and n < 120:
            a, b = max(0, t), max(0, t + period // 2)
            if b > 0:
                tg += f"\\t({a},{min(D, b)},\\fscy122)\\t({min(D, b)},{min(D, t + period)},\\fscy100)"
            t += period
            n += 1
        out.append(f"{{{tg}}}{esc(ch)}")
    return "".join(out)


def _col_of(st: dict) -> str:
    c = str(st.get("color", "#FFFFFF")).lstrip("#")
    return f"&H{c[4:6]}{c[2:4]}{c[0:2]}&" if len(c) == 6 else "&HFFFFFF&"


LEGACY = {"pop": ("pop", "none"), "fade": ("fade", "fade"), "slide": ("slide-u", "fade"), "bounce": ("bounce", "none"),
          "zoom": ("zoom", "fade"), "glitch": ("glitch", "none"), "type": ("type", "none"), "shake": ("none", "none"), "none": ("none", "none")}
