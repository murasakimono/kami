"""Kami Studio Dalga 2 yardimcilari: Kalici Maskeler, Blend Modlari, Renk Ayar Katmani ve Bezier Keyframe."""
from __future__ import annotations

import math
from typing import Any

from app.core.studio_motion import BEZIER_PRESETS, cubic_bezier

BLEND_MODES: dict[str, tuple[str, str]] = {
    "normal": ("Normal", "normal"),
    "screen": ("Ekran (Screen)", "screen"),
    "overlay": ("Kaplama (Overlay)", "overlay"),
    "multiply": ("Çarpma (Multiply)", "multiply"),
    "lighten": ("Aydınlat (Lighten)", "lighten"),
    "darken": ("Koyulaştır (Darken)", "darken"),
    "dodge": ("Renk Soldur (Dodge)", "dodge"),
    "difference": ("Fark (Difference)", "difference"),
    "addition": ("Ekle (Add)", "addition"),
}

MASK_TYPES: dict[str, str] = {
    "none": "Yok",
    "circle": "Daire / Elips",
    "rect": "Dikdörtgen",
    "split": "Bölünmüş (Çizgi)",
    "mirror": "Ayna (Şerit)",
    "filmstrip": "Film Şeridi",
    "star": "Yıldız",
    "heart": "Kalp",
}


def adj_filters(adj: dict[str, Any] | None) -> list[str]:
    """Parlaklik, kontrast, doygunluk, ton, sicaklik ve bulaniklik FFmpeg filtre zinciri."""
    if not adj:
        return []
    ch: list[str] = []
    if any(adj.get(x) for x in ("bri", "con", "sat")):
        ch.append(
            f"eq=brightness={float(adj.get('bri', 0)) / 100:.3f}"
            f":contrast={1 + float(adj.get('con', 0)) / 100:.3f}"
            f":saturation={1 + float(adj.get('sat', 0)) / 100:.3f}"
        )
    if adj.get("hue"):
        ch.append(f"hue=h={float(adj['hue']):.2f}")
    if adj.get("temp"):
        tv = float(adj["temp"]) / 200.0
        ch.append(f"colorbalance=rs={tv:.3f}:bs={-tv:.3f}:rm={tv / 2:.3f}:bm={-tv / 2:.3f}")
    if adj.get("blur"):
        ch.append(f"gblur=sigma={float(adj['blur']):.2f}")
    return ch


def mask_filter(mask: dict[str, Any] | None, W: int, H: int) -> str:
    """Klip alfa kanalini kalici sekle (circle/rect/split/mirror/filmstrip/star/heart) kirpar."""
    if not mask:
        return ""
    mtype = str(mask.get("type", "none"))
    if mtype == "none" or mtype not in MASK_TYPES:
        return ""
    cx = float(mask.get("x", 0.5)) * W
    cy = float(mask.get("y", 0.5)) * H
    rx = max(2.0, float(mask.get("w", 0.55)) * W * 0.5)
    ry = max(2.0, float(mask.get("h", 0.55)) * H * 0.5)
    rot_deg = float(mask.get("rot", 0.0) or 0.0)
    feather = max(0.0, float(mask.get("feather", 0.0) or 0.0))
    invert = bool(mask.get("invert", False))

    if abs(rot_deg) < 0.05:
        dx = f"(X-{cx:.2f})"
        dy = f"(Y-{cy:.2f})"
    else:
        rad = math.radians(rot_deg)
        c, s = math.cos(rad), math.sin(rad)
        dx = f"((X-{cx:.2f})*{c:.5f}+(Y-{cy:.2f})*{s:.5f})"
        dy = f"(-(X-{cx:.2f})*{s:.5f}+(Y-{cy:.2f})*{c:.5f})"

    if mtype == "circle":
        dist = f"hypot(({dx})/{rx:.2f},({dy})/{ry:.2f})"
    elif mtype == "rect":
        dist = f"max(abs({dx})/{rx:.2f},abs({dy})/{ry:.2f})"
    elif mtype == "split":
        # dx <= 0 -> 1.0 iceride, dx > 0 -> disarida
        scale_r = max(10.0, min(W, H) * 0.5)
        dist = f"(1+({dx})/{scale_r:.2f})"
    elif mtype == "mirror":
        dist = f"(abs({dy})/{ry:.2f})"
    elif mtype == "filmstrip":
        strip_w = max(8.0, W / 5.0)
        dist = f"max(abs({dy})/{ry:.2f},lt(mod(X+{strip_w * 0.5:.1f},{strip_w:.1f}),{strip_w * 0.14:.1f})*2)"
    elif mtype == "star":
        ang = f"atan2(({dy})/{ry:.2f},({dx})/{rx:.2f})"
        dist = f"(hypot(({dx})/{rx:.2f},({dy})/{ry:.2f})/(0.68+0.32*cos(5*{ang}+1.5708)))"
    else:  # heart
        hx = f"(({dx})/({rx * 0.85:.2f}))"
        hy = f"(-({dy})/({ry * 0.85:.2f})+0.15)"
        dist = f"(1+(pow({hx}*{hx}+{hy}*{hy}-1,3)-{hx}*{hx}*{hy}*{hy}*{hy})*0.45)"

    if feather > 0.5:
        fw = max(0.015, feather / max(min(rx, ry), 1.0))
        m_expr = f"clip((1+{fw * 0.5:.4f}-({dist}))/{fw:.4f},0,1)"
    else:
        m_expr = f"lte({dist},1)"

    if invert:
        m_expr = f"(1-({m_expr}))"
    return f"format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*({m_expr})'"


def blend_composite_chain(
    base_tag: str,
    fg_tag: str,
    out_tag: str,
    k: int,
    blend: str,
    ox: str,
    oy: str,
    enable_expr: str,
    W: int,
    H: int,
    FPS: int,
) -> list[str]:
    """Katman blend modunu (screen/overlay/multiply/vb.) alfa maskesini koruyarak FFmpeg'de birlestirir."""
    ff_mode = BLEND_MODES.get(blend or "normal", ("Normal", "normal"))[1]
    if ff_mode == "normal":
        return [f"[{base_tag}][{fg_tag}]overlay=x='{ox}':y='{oy}':eof_action=pass:enable='{enable_expr}'[{out_tag}]"]
    if ox == "0" and oy == "0":
        return [
            f"[{base_tag}]split[ba{k}][bb{k}]",
            f"[bb{k}]format=rgba[bgf{k}]",
            f"[{fg_tag}]format=rgba,split[fgb{k}][fga{k}]",
            f"[fga{k}]alphaextract[al{k}]",
            f"[bgf{k}][fgb{k}]blend=c0_mode={ff_mode}:c1_mode={ff_mode}:c2_mode={ff_mode}:c3_mode=normal:shortest=1,format=rgba[rgb{k}]",
            f"[rgb{k}][al{k}]alphamerge[ma{k}]",
            f"[ba{k}][ma{k}]overlay=enable='{enable_expr}'[{out_tag}]",
        ]
    return [
        f"[{base_tag}]split[ba{k}][bb{k}]",
        f"[bb{k}]format=rgba[bgf{k}]",
        f"color=c=black@0:s={W}x{H}:r={FPS},format=rgba[tr{k}]",
        f"[tr{k}][{fg_tag}]overlay=x='{ox}':y='{oy}':eof_action=endall,format=rgba,split[fgb{k}][fga{k}]",
        f"[fga{k}]alphaextract[al{k}]",
        f"[bgf{k}][fgb{k}]blend=c0_mode={ff_mode}:c1_mode={ff_mode}:c2_mode={ff_mode}:c3_mode=normal:shortest=1,format=rgba[rgb{k}]",
        f"[rgb{k}][al{k}]alphamerge[ma{k}]",
        f"[ba{k}][ma{k}]overlay=enable='{enable_expr}'[{out_tag}]",
    ]


def _seg_bezier_expr(tv: str, t0: float, t1: float, v0: float, v1: float, bez: Any, fallback_tail: str) -> str:
    """[p1x,p1y,p2x,p2y] Bezier egrisini 8 parcali dogrusal FFmpeg ifadesine derler."""
    if isinstance(bez, str) and bez in BEZIER_PRESETS:
        pts_b = BEZIER_PRESETS[bez]
    elif isinstance(bez, (list, tuple)) and len(bez) == 4:
        pts_b = tuple(float(x) for x in bez)
    else:
        return ""
    p1x, p1y, p2x, p2y = pts_b
    span = max(1e-3, t1 - t0)
    steps = 8
    expr = fallback_tail
    for j in range(steps - 1, -1, -1):
        u0 = j / steps
        u1 = (j + 1) / steps
        st0 = t0 + span * u0
        st1 = t0 + span * u1
        sv0 = v0 + (v1 - v0) * cubic_bezier(p1x, p1y, p2x, p2y, u0)
        sv1 = v0 + (v1 - v0) * cubic_bezier(p1x, p1y, p2x, p2y, u1)
        sub_u = f"(({tv}-{st0:.4f})/{max(1e-4, st1 - st0):.4f})"
        expr = f"if(lt({tv},{st1:.4f}),{sv0:.4f}+({sv1 - sv0:.4f})*{sub_u},{expr})"
    return expr


def kf_expr_adv(kf: list[dict[str, Any]], key: str, tv: str, default: float) -> str:
    """Universal keyframe listesini (Bezier veya lineer/ease) FFmpeg zaman ifadesine cevirir."""
    pts = [(float(k["t"]), float(k.get(key, default)), k.get("e", ""), k.get("bez")) for k in kf if key in k]
    if not pts:
        return f"{default}"
    expr = f"{pts[-1][1]:.4f}"
    for i in range(len(pts) - 1, 0, -1):
        t0, v0, _, _ = pts[i - 1]
        t1, v1, e, bez = pts[i]
        b_expr = _seg_bezier_expr(tv, t0, t1, v0, v1, bez, expr)
        if b_expr:
            expr = b_expr
            continue
        span = max(1e-3, t1 - t0)
        u = f"(({tv}-{t0:.4f})/{span:.4f})"
        if e == "out":
            ee = f"(1-(1-{u})*(1-{u}))"
        elif e == "in":
            ee = f"({u}*{u})"
        elif e == "inout":
            ee = f"({u}*{u}*(3-2*{u}))"
        else:
            ee = u
        expr = f"if(lt({tv},{t1:.4f}),{v0:.4f}+({v1 - v0:.4f})*{ee},{expr})"
    return f"if(lt({tv},{pts[0][0]:.4f}),{pts[0][1]:.4f},{expr})"


EQ_BANDS: list[int] = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]

EQ_PRESETS: dict[str, tuple[str, list[float]]] = {
    "flat": ("Düz", [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
    "podcast": ("Podcast / Net Vokal", [-6, -4, -2, -1, 1, 2, 4, 5, 3, 1]),
    "bass": ("Bas Güçlendir", [6, 5, 4, 2, 0, -1, 0, 1, 1, 0]),
    "bright": ("Tiz & Parlak", [-1, -1, 0, 0, 1, 2, 3, 5, 6, 5]),
    "radio": ("Radyo / Eski", [-12, -10, -6, 2, 5, 6, 4, -4, -9, -12]),
    "cinema": ("Sıcak Sinema", [3, 2, 1, 0, -1, 1, 2, 2, 3, 2]),
}

AUDIO_CURVES: dict[str, str] = {
    "tri": "Doğrusal",
    "qsin": "Yumuşak (S-Eğri)",
    "log": "Logaritmik",
    "exp": "Keskin (Üstel)",
}


def eq_filters(eq: list[Any] | None) -> list[str]:
    """10-bant EQ (-12..+12 dB) FFmpeg equalizer zincirine cevirir."""
    if not eq or not isinstance(eq, (list, tuple)):
        return []
    out: list[str] = []
    for freq, raw_g in zip(EQ_BANDS, eq):
        try:
            g = max(-18.0, min(18.0, float(raw_g or 0)))
        except (TypeError, ValueError):
            continue
        if abs(g) >= 0.1:
            out.append(f"equalizer=f={freq}:t=o:w=1:g={g:.2f}")
    return out


def pan_filter(pan: Any) -> str:
    """Stereo pan (-1 sol .. +1 sag) -> stereotools balance_out."""
    try:
        p = max(-1.0, min(1.0, float(pan or 0)))
    except (TypeError, ValueError):
        return ""
    return f"stereotools=balance_out={p:.3f}" if abs(p) >= 0.01 else ""


def resolve_parent_xform(
    c: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    resolve_kf: Any,
    T0: float,
    off: float,
    cut0: float,
    W: int,
    H: int,
) -> tuple[str, bool, str, bool, str, str]:
    """AE katman ebeveynligini (c.parent) dongusuz cozer -> (scale_ex, dyn_sc, rot_ex, dyn_rot, px_ex, py_ex)."""
    chain: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = c
    seen: set[str] = set()
    while cur and cur.get("id") not in seen:
        seen.add(str(cur.get("id") or ""))
        chain.append(cur)
        pid = cur.get("parent")
        cur = by_id.get(str(pid)) if pid else None

    def prop_stream(node: dict[str, Any], key: str, default: float) -> tuple[str, bool]:
        shift = float(c.get("start", 0)) - float(node.get("start", 0))
        tv = f"(t+{cut0 + shift:.4f})"
        d_n = float(node.get("dur", 0) or 0)
        ukf = resolve_kf(node.get("kf") or [], d_n)
        base = float(node.get(key) if node.get(key) is not None else default)
        if any(key in q for q in ukf):
            return kf_expr_adv(ukf, key, tv, base), True
        return f"{base:.4f}", abs(base - default) > 1e-4

    def prop_ov(node: dict[str, Any], key: str, default: float) -> tuple[str, bool]:
        tv = f"(t+{T0 - float(node.get('start', 0)):.4f})"
        d_n = float(node.get("dur", 0) or 0)
        ukf = resolve_kf(node.get("kf") or [], d_n)
        base = float(node.get(key) if node.get(key) is not None else default)
        if any(key in q for q in ukf):
            return kf_expr_adv(ukf, key, tv, base), True
        return f"{base:.4f}", abs(base - default) > 1e-4

    sc_parts: list[str] = []
    dyn_sc = False
    rot_parts: list[str] = []
    dyn_rot = False
    for node in chain:
        se, ds = prop_stream(node, "scale", 1.0)
        if ds or se != "1.0000":
            sc_parts.append(f"({se})")
        dyn_sc = dyn_sc or ds
        re_, dr = prop_stream(node, "rot", 0.0)
        if dr or abs(float(node.get("rot", 0) or 0)) > 0.01:
            rot_parts.append(f"({re_})")
        dyn_rot = dyn_rot or dr

    px_expr = "0"
    py_expr = "0"
    cum_s_parts: list[str] = []
    cum_r_parts: list[str] = []
    for idx in range(len(chain) - 1, -1, -1):
        node = chain[idx]
        nx, hx = prop_ov(node, "x", 0.0)
        ny, hy = prop_ov(node, "y", 0.0)
        if hx or hy or abs(float(node.get("x", 0) or 0)) > 1e-4 or abs(float(node.get("y", 0) or 0)) > 1e-4:
            cx, cy = f"({nx})*{W}", f"({ny})*{H}"
            if not cum_s_parts and not cum_r_parts:
                px_expr, py_expr = cx, cy
            else:
                cs = "*".join(cum_s_parts) if cum_s_parts else "1"
                if not cum_r_parts:
                    px_expr = f"({px_expr})+({cs})*({cx})"
                    py_expr = f"({py_expr})+({cs})*({cy})"
                else:
                    cr = f"(({'+'.join(cum_r_parts)})*PI/180)"
                    px_expr = f"({px_expr})+({cs})*(({cx})*cos({cr})-({cy})*sin({cr}))"
                    py_expr = f"({py_expr})+({cs})*(({cx})*sin({cr})+({cy})*cos({cr}))"
        ns, ds = prop_ov(node, "scale", 1.0)
        if ds or ns != "1.0000":
            cum_s_parts.append(f"({ns})")
        nr, dr = prop_ov(node, "rot", 0.0)
        if dr or abs(float(node.get("rot", 0) or 0)) > 0.01:
            cum_r_parts.append(f"({nr})")

    return "*".join(sc_parts) or "1.0000", dyn_sc, "+".join(rot_parts) or "0.0000", dyn_rot, px_expr, py_expr
