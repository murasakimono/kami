"""Faz 5b gecis paketi: studio.TRANS'a eklenir, _trans_in bilinmeyen turde trans_in2'ye duser.
Ayni kurallar: akis t=0 = klibin c0. saniyesi, e = cubic ease-out (onizleme: studio-fx.js transIn2)."""
from __future__ import annotations

TRANS2 = {
    "diag-tl": "Çapraz silme ↘", "diag-br": "Çapraz silme ↖", "diag-tr": "Çapraz silme ↙", "diag-bl": "Çapraz silme ↗",
    "wipe-soft": "Yumuşak silme", "wave-wipe": "Dalgalı silme", "corner": "Köşeden daire", "diamond": "Elmas açılış",
    "heart": "Kalp açılış", "cross": "Artı açılış", "blinds-h": "Jaluzi (yatay)", "blinds-v": "Jaluzi (dikey)",
    "checker": "Dama tahtası", "stripes": "Çapraz şeritler", "blocks": "Blok blok", "dissolve": "Dağılarak belir",
    "pop-in": "Küçükten büyü", "bounce-in": "Yaylanarak büyü", "flip-h": "Yatay çevir", "flip-v": "Dikey çevir",
    "dip-black": "Siyah flaş", "dip-pink": "Renkli flaş", "dip-cyan": "Camgöbeği flaş", "whip-v": "Dikey savurma", "spin180": "Yarım tur dön", "vhs-roll": "VHS sarma",
}


def trans_in2(kind: str, d: float, W: int, H: int, tag: str = "t", c0: float = 0.0, fps: int = 30) -> str:
    def prog(v: str) -> tuple[str, str]:
        u = f"min(1,max(0,({v}+{c0:.4f})/{d:.4f}))"
        return u, f"(1-pow(1-{u},3))"
    u, e = prog("t")
    U, E = prog("T")
    en = f"enable='lt(t,{max(0.001, d - c0):.4f})'"
    masks = {
        "diag-tl": f"lt(X/W+Y/H,2*{E})", "diag-br": f"gt(X/W+Y/H,2*(1-{E}))",
        "diag-tr": f"lt((W-X)/W+Y/H,2*{E})", "diag-bl": f"gt((W-X)/W+Y/H,2*(1-{E}))",
        "wave-wipe": f"lt(X,W*1.1*{E}-W*0.05+sin(Y/H*14)*W*0.04*(1-{E}))",
        "corner": f"lt(hypot(X,Y),{E}*hypot(W,H))",
        "diamond": f"lt(abs(X-W/2)/W+abs(Y-H/2)/H,{E})",
        "heart": f"lt(pow(pow((X-W/2)/(H*{E}*0.9+1),2)+pow((H*0.45-Y)/(H*{E}*0.9+1)+0.0,2)-0.09,3)-pow((X-W/2)/(H*{E}*0.9+1),2)*pow((H*0.45-Y)/(H*{E}*0.9+1),3),0)+gte({E},0.999)",
        "cross": f"lt(abs(X-W/2),{E}*W/2)+lt(abs(Y-H/2),{E}*H/2)",
        "blinds-h": f"lt(mod(Y,H/8),{E}*H/8+1)", "blinds-v": f"lt(mod(X,W/10),{E}*W/10+1)",
        "checker": f"lt(mod(floor(X/(W/8))+floor(Y/(H/6)),2)*0.5+0.5*mod(X,W/8)/(W/8),{E})",
        "stripes": f"lt(mod(X+Y,W/6),{E}*W/6+1)",
        "blocks": f"lt(mod(floor(X/(W/16))*7+floor(Y/(H/9))*13,17)/17,{E}*1.06)",
        "dissolve": f"lt(random(1),{U}*1.05)",
    }
    if kind == "wipe-soft":   # 20% yumusak kenar
        return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*min(1,max(0,(W*1.25*{E}-X)/(W*0.25)))':{en}"
    if kind in masks:
        return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if({masks[kind]},alpha(X,Y),0)':{en}"
    # yeniden ornekleme: olcekli kopya, disari saydam (onizleme: sx/sy)
    if kind in ("pop-in", "bounce-in", "flip-h", "flip-v"):
        back = f"(1+2.70158*pow({U}-1,3)+1.70158*pow({U}-1,2))"
        sx = sy = {"pop-in": f"(0.3+0.7*{E})", "bounce-in": f"max(0.05,{back})"}.get(kind, "1")
        if kind == "flip-h":
            sx = f"max(0.02,{E})"
        if kind == "flip-v":
            sy = f"max(0.02,{E})"
        xs, ys = f"(W/2+(X-W/2)/{sx})", f"(H/2+(Y-H/2)/{sy})"
        inside = f"between({xs},0,W-1)*between({ys},0,H-1)"
        return (f"geq=r='r({xs},{ys})':g='g({xs},{ys})':b='b({xs},{ys})':a='if({inside},alpha({xs},{ys}),0)':{en}")
    if kind == "dip-black":
        return f"eq=brightness='-0.9*(1-{u})':eval=frame:{en}"
    if kind == "dip-pink":
        return f"eq=brightness='0.35*(1-{u})':gamma_r='1+1.2*(1-{u})':gamma_g='1-0.3*(1-{u})':gamma_b='1+0.6*(1-{u})':eval=frame:{en}"
    if kind == "dip-cyan":
        return f"eq=brightness='0.35*(1-{u})':gamma_r='1-0.3*(1-{u})':gamma_g='1+0.9*(1-{u})':gamma_b='1+1.2*(1-{u})':eval=frame:{en}"
    if kind == "whip-v":
        return f"pad=iw:ih*2:0:ih:color=black@0,crop={W}:{H}:x=0:y='ih/2*{e}',gblur=sigma=0.5:sigmaV=36:{en}"
    if kind == "spin180":
        return f"rotate=a='-(1-{e})*PI':c=black@0:{en}"
    if kind == "vhs-roll":   # dikey kayma + gurultu + renk kaymasi
        return (f"split[{tag}a][{tag}b];[{tag}b]crop=iw:ih:0:'mod(ih*4*(1-{u}),ih)',noise=alls=40:allf=t,rgbashift=rh=10:bh=-10,format=rgba[{tag}c];"
                f"[{tag}a][{tag}c]overlay={en}")
    return "null"
