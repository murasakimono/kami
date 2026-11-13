"""Kami Studio hareketli grafikleri (ASS vektor): YouTube tarzi abone/begen/zil dizileri, alt bantlar, konum, bolum basligi,
bitis ekrani, isaretci, ilerleme cubugu, vurgulayici, sayac. Onizleme (JASSUB) ve disa aktarim (libass) ayni ciktiyi kullanir.

Her fonksiyon Dialogue satirlari doner. Konum: style.x / style.y (0-1, merkez); boyut: style.size (% , 100 = 1080p'de dogal).
"""
from __future__ import annotations

from typing import Callable

SUBSCRIBE_PRO = {
    "yt-light": "YouTube açık (beğen → abone → zil)", "yt-dark": "YouTube koyu (beğen → abone → zil)",
    "play-morph": "Kırmızı oynat → ABONE OL", "channel": "Kanal kartı (avatar + isim)", "folding": "Açılan buton",
    "3d": "3D buton", "wave": "Dalga harfler", "meme": "Meme (dev yazı + ok)", "social": "Sosyal hesaplar",
    "lss": "Beğen · Paylaş · Abone sırası",
}
GRAPHICS = {
    "lower": "İsim alt bandı", "lower-min": "Sade alt bant", "location": "Konum etiketi", "chapter": "Bölüm başlığı",
    "endscreen": "Bitiş ekranı (2 video + abone)", "callout": "İşaretçi (halka + ok)", "progress": "İlerleme çubuğu",
    "highlight": "Vurgulayıcı kalem", "counter": "Sayaç (0 → N)", "quote": "Alıntı kartı",
}

# --- simgeler (0,0 sol ust; yaklasik 40x45 kutu)
THUMB = "m 0 18 l 8 18 l 8 44 l 0 44 m 11 18 l 20 0 b 26 0 27 5 26 10 l 24 16 l 40 16 b 45 16 46 21 44 24 l 38 42 b 37 44 35 45 33 45 l 11 45"
BELL = ("m 20 0 b 23 0 24 2 24 4 b 33 6 37 13 37 22 l 37 34 l 42 40 l 42 43 l -2 43 l -2 40 l 3 34 l 3 22 b 3 13 7 6 16 4 b 16 2 17 0 20 0 "
        "m 14 46 l 26 46 b 26 50 23 53 20 53 b 17 53 14 50 14 46")
CURSOR = "m 0 0 l 0 34 l 9 26 l 15 40 l 21 37 l 15 24 l 27 24"
HAND = ("m 10 0 b 13 0 15 2 15 5 l 15 18 b 16 16 19 16 20 18 b 21 16 24 16 25 19 b 26 17 30 17 30 21 l 30 34 b 30 42 25 48 17 48 "
        "b 10 48 7 45 3 38 l 0 32 b -1 29 2 27 5 29 l 5 5 b 5 2 7 0 10 0")
SHARE = "m 0 22 l 24 0 l 24 12 b 40 12 46 24 46 40 b 40 30 34 26 24 26 l 24 38 l 0 22"
PIN = "m 15 0 b 24 0 30 7 30 15 b 30 26 15 42 15 42 b 15 42 0 26 0 15 b 0 7 6 0 15 0 m 15 8 b 11 8 8 11 8 15 b 8 19 11 22 15 22 b 19 22 22 19 22 15 b 22 11 19 8 15 8"
PLAY = "m 0 0 l 0 30 l 26 15"
ARROW_DOWN = "m 20 0 l 40 0 l 40 40 l 60 40 l 30 75 l 0 40 l 20 40"
CIRCLE = "m -50 0 b -50 -67 50 -67 50 0 b 50 67 -50 67 -50 0"


def _ellipse(w: float, h: float) -> str:
    rx, ry = w / 2, h / 2
    k = 0.5523
    return (f"m {rx:.0f} 0 b {rx + rx * k:.0f} 0 {w:.0f} {ry - ry * k:.0f} {w:.0f} {ry:.0f} b {w:.0f} {ry + ry * k:.0f} {rx + rx * k:.0f} {h:.0f} {rx:.0f} {h:.0f} "
            f"b {rx - rx * k:.0f} {h:.0f} 0 {ry + ry * k:.0f} 0 {ry:.0f} b 0 {ry - ry * k:.0f} {rx - rx * k:.0f} 0 {rx:.0f} 0")


class _Ctx:
    """Ortak yardimcilar: studio.py'deki _ts/_col/_esc/_rrect ile."""

    def __init__(self, ts: Callable, col: Callable, esc: Callable, rrect: Callable, s: float, e: float, W: int, H: int, st: dict):
        self.ts, self.col, self.esc, self.rrect = ts, col, esc, rrect
        self.s, self.e, self.W, self.H, self.st = s, e, W, H, st
        self.k = H / 1080 * float(st.get("size", 100)) / 100
        self.cx, self.cy = W * float(st.get("x", 0.5)), H * float(st.get("y", 0.8))
        self.font = st.get("font", "Segoe UI")
        self.dur = max(0.5, e - s)
        self.out: list[str] = []

    def T(self, a: float, b: float | None = None) -> str:
        b = self.dur if b is None else b
        return f"{self.ts(self.s + max(0.0, a))},{self.ts(self.s + min(self.dur, b))}"

    def ev(self, layer: int, a: float, b: float | None, tags: str, body: str) -> None:
        if (b if b is not None else self.dur) <= a:
            return
        self.out.append(f"Dialogue: {layer},{self.T(a, b)},Default,,0,0,0,,{{{tags}}}{body}")

    def ms(self, sec: float) -> int:
        return int(sec * 1000)


def _enter(c: _Ctx, x: float, y: float, dy: float = 40) -> str:
    """Grup girisi: asagidan kayarak belir; sonda kaybol."""
    return f"\\an7\\move({x:.0f},{y + dy * c.k:.0f},{x:.0f},{y:.0f},0,240)\\fad(180,260)"


def subscribe(kind: str, ts, col, esc, rrect, s: float, e: float, W: int, H: int, st: dict) -> list[str]:
    c = _Ctx(ts, col, esc, rrect, s, e, W, H, st)
    fn = {"yt-light": _yt, "yt-dark": _yt, "play-morph": _play_morph, "channel": _channel, "folding": _folding, "3d": _three_d,
          "wave": _wave, "meme": _meme, "social": _social, "lss": _lss}.get(kind)
    if fn:
        fn(c, kind)
    return c.out


def _cursor_path(c: _Ctx, pts: list[tuple[float, float, float]], clicks: list[float], hand: bool = True) -> None:
    """pts: [(zaman, x, y)] - parca parca \\move; clicks: tiklama anlari (sn)."""
    k = c.k
    shape = HAND if hand else CURSOR
    sc = 115 * k
    for (t0, x0, y0), (t1, x1, y1) in zip(pts, pts[1:]):
        tags = (f"\\an7\\move({x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f},0,{c.ms(t1 - t0)})\\p1\\fscx{sc:.0f}\\fscy{sc:.0f}"
                f"\\1c&H00FFFFFF&\\3c&H00000000&\\bord{2.2 * k:.1f}\\shad{2 * k:.1f}\\4c&H80000000&")
        c.ev(9, t0, t1, tags, shape)
    tl, xl, yl = pts[-1]
    clk = ""
    for t in clicks:
        if t >= tl:
            rel = c.ms(t - tl)
            clk += f"\\t({rel},{rel + 80},\\fscx{sc * 0.82:.0f}\\fscy{sc * 0.82:.0f})\\t({rel + 80},{rel + 170},\\fscx{sc:.0f}\\fscy{sc:.0f})"
    c.ev(9, tl, None, f"\\an7\\pos({xl:.0f},{yl:.0f})\\p1\\fscx{sc:.0f}\\fscy{sc:.0f}\\1c&H00FFFFFF&\\3c&H00000000&\\bord{2.2 * k:.1f}"
         f"\\shad{2 * k:.1f}\\4c&H80000000&{clk}\\fad(0,260)", shape)
    for t in clicks:   # tiklama halkasi
        c.ev(8, t, t + 0.35, f"\\an5\\pos({_tip(pts, t)[0] + 8 * k:.0f},{_tip(pts, t)[1] + 4 * k:.0f})\\p1\\1a&HFF&\\3c&H00FFFFFF&\\bord{3 * k:.1f}"
             f"\\fscx{20 * k:.0f}\\fscy{20 * k:.0f}\\t(0,350,\\fscx{70 * k:.0f}\\fscy{70 * k:.0f}\\3a&HFF&)", CIRCLE)


def _tip(pts: list, t: float) -> tuple[float, float]:
    for (t0, x0, y0), (t1, x1, y1) in zip(pts, pts[1:]):
        if t0 <= t <= t1:
            u = (t - t0) / max(1e-3, t1 - t0)
            return x0 + (x1 - x0) * u, y0 + (y1 - y0) * u
    return pts[-1][1], pts[-1][2]


def _timing(c: _Ctx, n: int) -> list[float]:
    """n tiklama icin zaman cizelgesi (klip kisaysa sikistirir)."""
    f = min(1.0, (c.dur - 0.8) / (0.9 + 0.7 * n))
    return [(0.85 + 0.7 * i) * f for i in range(n)]


def _yt(c: _Ctx, kind: str) -> None:
    k, st = c.k, c.st
    dark = kind == "yt-dark"
    pw, ph = 780 * k, 150 * k
    x0, y0 = c.cx - pw / 2, c.cy - ph / 2
    panel, ink = ("&H00212121&", "&H00F1F1F1&") if dark else ("&H00FFFFFF&", "&H000F0F0F&")
    blue = "&H00D45F06&"
    label, done = c.esc(st.get("label", "Abone ol")), c.esc(st.get("done", "Abone olundu"))
    t_like, t_sub, t_bell = _timing(c, 3)
    c.ev(2, 0, None, _enter(c, x0, y0) + f"\\p1\\1c{panel}\\bord0\\shad{6 * k:.0f}\\4c&HA0000000&", c.rrect(pw, ph, 34 * k))
    # begen / begenme + alt cizgi
    lx, ly = x0 + 50 * k, y0 + 45 * k
    sc = 130 * k
    bump = f"\\t({c.ms(t_like)},{c.ms(t_like) + 120},\\1c{blue}\\fscx{sc * 1.25:.0f}\\fscy{sc * 1.25:.0f})\\t({c.ms(t_like) + 120},{c.ms(t_like) + 240},\\fscx{sc:.0f}\\fscy{sc:.0f})"
    c.ev(3, 0, None, _enter(c, lx, ly) + f"\\p1\\1c{ink}\\bord0\\shad0\\fscx{sc:.0f}\\fscy{sc:.0f}{bump}", THUMB)
    c.ev(3, 0, None, _enter(c, lx + 150 * k, ly + 58 * k) + f"\\p1\\1c{ink}\\bord0\\shad0\\fscx{sc:.0f}\\fscy{sc:.0f}\\frz180", THUMB)
    c.ev(3, t_like, None, _enter(c, lx - 6 * k, y0 + ph - 32 * k, 0) + f"\\p1\\1c{blue}\\bord0\\shad0\\fscx0\\t(0,200,\\fscx100)",
         c.rrect(200 * k, 9 * k, 4 * k))
    # abone dugmesi
    bx, bw, bh = x0 + 290 * k, 330 * k, 82 * k
    by = c.cy - bh / 2
    sub_c, sub_t = (("&H00FFFFFF&", "&H000F0F0F&") if dark else ("&H000000CC&", "&H00FFFFFF&"))
    don_c, don_t = (("&H003F3F3F&", "&H00F1F1F1&") if dark else ("&H00505050&", "&H00FFFFFF&"))
    if st.get("color"):
        sub_c = c.col(st["color"])
    c.ev(4, 0, None, _enter(c, bx, by) + f"\\p1\\1c{sub_c}\\bord0\\shad0\\t({c.ms(t_sub)},{c.ms(t_sub) + 140},\\1c{don_c})", c.rrect(bw, bh, bh / 2))
    fs = 40 * k
    c.ev(5, 0, t_sub + 0.07, f"\\an5\\move({bx + bw / 2:.0f},{c.cy + 40 * k:.0f},{bx + bw / 2:.0f},{c.cy:.0f},0,240)\\fad(180,0)\\fn{c.font}\\fs{fs:.0f}\\b1\\bord0\\shad0\\1c{sub_t}", label)
    c.ev(5, t_sub + 0.07, None, f"\\an5\\pos({bx + bw / 2:.0f},{c.cy:.0f})\\fn{c.font}\\fs{fs * 0.9:.0f}\\b1\\bord0\\shad0\\1c{don_t}\\fscx70\\fscy70\\t(0,140,\\fscx100\\fscy100)\\fad(0,260)", done)
    # zil
    zx, zy = bx + bw + 60 * k, c.cy - 34 * k
    ring = "".join(f"\\t({c.ms(t_bell) + i * 70},{c.ms(t_bell) + i * 70 + 70},\\frz{16 if i % 2 else -16})" for i in range(6)) + f"\\t({c.ms(t_bell) + 420},{c.ms(t_bell) + 480},\\frz0)"
    c.ev(4, 0, None, _enter(c, zx, zy) + f"\\p1\\1a&HFF&\\3c{ink}\\bord{3.2 * k:.1f}\\shad0\\fscx{140 * k:.0f}\\fscy{140 * k:.0f}"
         f"\\org({zx + 28 * k:.0f},{zy:.0f})\\t({c.ms(t_bell)},{c.ms(t_bell) + 60},\\1a&H00&\\1c{ink}){ring}", BELL)
    # imlec
    tip = lambda x, y: (x, y)  # noqa: E731
    pts = [(0.25, c.cx + 420 * k, c.cy + 260 * k), (t_like - 0.05, *tip(lx + 22 * k, ly + 30 * k)),
           (t_sub - 0.05, *tip(bx + bw * 0.55, c.cy + 6 * k)), (t_bell - 0.05, *tip(zx + 26 * k, zy + 32 * k))]
    _cursor_path(c, pts, [t_like, t_sub, t_bell])


def _play_morph(c: _Ctx, kind: str) -> None:
    k, st = c.k, c.st
    red = c.col(st.get("color", "#FF0000"))
    bw, bh = 420 * k, 110 * k
    x0 = c.cx - bw / 2
    t_click = _timing(c, 1)[0] + 0.5
    # once kirmizi oynat logosu buyur, sonra yatayda butona acilir
    c.ev(3, 0, None, f"\\an5\\pos({c.cx:.0f},{c.cy:.0f})\\p1\\1c{red}\\bord0\\shad{4 * k:.0f}\\4c&H80000000&"
         f"\\fscx{0:.0f}\\fscy0\\t(0,220,\\fscx{36:.0f}\\fscy{100:.0f})\\t(450,700,\\fscx100)"
         f"\\t({c.ms(t_click)},{c.ms(t_click) + 140},\\1c&H00505050&)\\fad(0,260)", c.rrect(bw, bh, 26 * k))
    c.ev(4, 0.0, 0.75, f"\\an5\\pos({c.cx + 6 * k:.0f},{c.cy:.0f})\\p1\\1c&H00FFFFFF&\\bord0\\shad0\\fscx{120 * k:.0f}\\fscy{120 * k:.0f}"
         f"\\fad(150,120)", PLAY)
    fs = 52 * k
    label, done = c.esc(st.get("label", "ABONE OL")), c.esc(st.get("done", "ABONE OLUNDU"))
    c.ev(5, 0.7, t_click + 0.06, f"\\an5\\pos({c.cx:.0f},{c.cy:.0f})\\fn{c.font}\\fs{fs:.0f}\\b1\\bord0\\shad0\\fsp{3 * k:.0f}\\fad(160,0)", label)
    c.ev(5, t_click + 0.06, None, f"\\an5\\pos({c.cx:.0f},{c.cy:.0f})\\fn{c.font}\\fs{fs * 0.82:.0f}\\b1\\bord0\\shad0\\1c&H00DDDDDD&\\fscx75\\fscy75\\t(0,140,\\fscx100\\fscy100)\\fad(0,260)", done)
    zx, zy = x0 + bw + 50 * k, c.cy - 36 * k
    ring = "".join(f"\\t({250 + i * 70},{320 + i * 70},\\frz{16 if i % 2 else -16})" for i in range(6)) + "\\t(670,720,\\frz0)"
    c.ev(4, t_click + 0.15, None, f"\\an7\\pos({zx:.0f},{zy:.0f})\\p1\\1c&H00FFFFFF&\\bord0\\shad{3 * k:.0f}\\fscx10\\fscy10\\t(0,160,\\fscx{145 * k:.0f}\\fscy{145 * k:.0f})"
         f"\\org({zx + 28 * k:.0f},{zy:.0f}){ring}\\fad(0,260)", BELL)
    _cursor_path(c, [(0.4, c.cx + 380 * k, c.cy + 240 * k), (t_click - 0.05, c.cx + 90 * k, c.cy + 12 * k)], [t_click])


def _channel(c: _Ctx, kind: str) -> None:
    k, st = c.k, c.st
    cw, chh = 820 * k, 170 * k
    x0, y0 = c.cx - cw / 2, c.cy - chh / 2
    c.ev(2, 0, None, _enter(c, x0, y0) + f"\\p1\\1c&H00181818&\\3c&H00303030&\\bord{1.5 * k:.1f}\\shad{6 * k:.0f}\\4c&HA0000000&", c.rrect(cw, chh, 28 * k))
    av = 118 * k
    ax, ay = x0 + 26 * k, c.cy - av / 2
    c.ev(3, 0, None, _enter(c, ax, ay) + f"\\p1\\1c{c.col(st.get('avatarColor', '#8B5CF6'))}\\bord0\\shad0", _ellipse(av, av))
    name = c.esc(st.get("channel", "Kanal Adı"))
    initial = c.esc((st.get("initial") or st.get("channel", "K") or "K")[:1].upper())
    c.ev(4, 0, None, f"\\an5\\move({ax + av / 2:.0f},{c.cy + 40 * k:.0f},{ax + av / 2:.0f},{c.cy:.0f},0,240)\\fad(180,260)\\fn{c.font}\\fs{64 * k:.0f}\\b1\\bord0\\shad0", initial)
    tx = ax + av + 26 * k
    c.ev(4, 0, None, f"\\an1\\move({tx:.0f},{c.cy + 40 * k:.0f},{tx:.0f},{c.cy - 2 * k:.0f},0,240)\\fad(180,260)\\fn{c.font}\\fs{42 * k:.0f}\\b1\\bord0\\shad0", name)
    c.ev(4, 0, None, f"\\an7\\move({tx:.0f},{c.cy + 50 * k:.0f},{tx:.0f},{c.cy + 10 * k:.0f},0,240)\\fad(180,260)\\fn{c.font}\\fs{28 * k:.0f}\\bord0\\shad0\\1c&H00AAAAAA&",
         c.esc(st.get("subs", "1,2 Mn abone")))
    bw, bh = 230 * k, 72 * k
    bx = x0 + cw - bw - 30 * k
    t_click = _timing(c, 1)[0] + 0.3
    c.ev(4, 0, None, _enter(c, bx, c.cy - bh / 2) + f"\\p1\\1c{c.col(st.get('color', '#FF0000'))}\\bord0\\shad0\\t({c.ms(t_click)},{c.ms(t_click) + 140},\\1c&H00404040&)",
         c.rrect(bw, bh, bh / 2))
    c.ev(5, 0, t_click + 0.06, f"\\an5\\move({bx + bw / 2:.0f},{c.cy + 40 * k:.0f},{bx + bw / 2:.0f},{c.cy:.0f},0,240)\\fad(180,0)\\fn{c.font}\\fs{32 * k:.0f}\\b1\\bord0\\shad0",
         c.esc(st.get("label", "Abone ol")))
    c.ev(5, t_click + 0.06, None, f"\\an5\\pos({bx + bw / 2:.0f},{c.cy:.0f})\\fn{c.font}\\fs{28 * k:.0f}\\b1\\bord0\\shad0\\1c&H00DDDDDD&\\fad(0,260)",
         c.esc(st.get("done", "Abone olundu")))
    _cursor_path(c, [(0.3, c.cx + 520 * k, c.cy + 230 * k), (t_click - 0.05, bx + bw * 0.6, c.cy + 8 * k)], [t_click])


def _folding(c: _Ctx, kind: str) -> None:
    k, st = c.k, c.st
    bw, bh = 460 * k, 112 * k
    red = c.col(st.get("color", "#FF1F1F"))
    t_click = _timing(c, 1)[0] + 0.4
    c.ev(3, 0, None, f"\\an5\\pos({c.cx:.0f},{c.cy + 8 * k:.0f})\\p1\\1c&H00000060&\\bord0\\shad0\\fscy0\\t(0,320,\\fscy100)\\fad(0,260)", c.rrect(bw, bh, 18 * k))
    c.ev(4, 0, None, f"\\an5\\pos({c.cx:.0f},{c.cy:.0f})\\p1\\1c{red}\\bord0\\shad0\\fscy0\\t(0,320,\\fscy100)"
         f"\\t({c.ms(t_click)},{c.ms(t_click) + 120},\\fscy0\\1c&H00505050&)\\t({c.ms(t_click) + 120},{c.ms(t_click) + 240},\\fscy100)\\fad(0,260)", c.rrect(bw, bh, 18 * k))
    fs = 54 * k
    c.ev(5, 0.25, t_click + 0.12, f"\\an5\\pos({c.cx:.0f},{c.cy:.0f})\\fn{c.font}\\fs{fs:.0f}\\b1\\bord0\\shad0\\fscy0\\t(0,200,\\fscy100)\\t({c.ms(t_click - 0.25)},{c.ms(t_click - 0.25) + 120},\\fscy0)",
         c.esc(st.get("label", "ABONE OL")))
    c.ev(5, t_click + 0.12, None, f"\\an5\\pos({c.cx:.0f},{c.cy:.0f})\\fn{c.font}\\fs{fs * 0.85:.0f}\\b1\\bord0\\shad0\\1c&H00DDDDDD&\\fscy0\\t(0,120,\\fscy100)\\fad(0,260)",
         c.esc(st.get("done", "ABONE OLUNDU")))
    _cursor_path(c, [(0.35, c.cx + 380 * k, c.cy + 240 * k), (t_click - 0.05, c.cx + 110 * k, c.cy + 10 * k)], [t_click])


def _three_d(c: _Ctx, kind: str) -> None:
    k, st = c.k, c.st
    bw, bh = 470 * k, 115 * k
    red = st.get("color", "#FF1F1F")
    t_click = _timing(c, 1)[0] + 0.4
    depth = int(14 * k)
    bounce = "\\fscx30\\fscy30\\t(0,200,\\fscx112\\fscy112)\\t(200,320,\\fscx96\\fscy96)\\t(320,400,\\fscx100\\fscy100)"
    for i in range(depth, 0, -2):   # ekstrude: koyu kopyalar
        c.ev(2, 0, None, f"\\an5\\pos({c.cx + i * 0.6:.0f},{c.cy + i:.0f})\\p1\\1c&H00000080&\\bord0\\shad0{bounce}\\fad(0,260)", c.rrect(bw, bh, 22 * k))
    press = f"\\t({c.ms(t_click)},{c.ms(t_click) + 90},\\fscx97\\fscy97\\1c&H00505050&)\\t({c.ms(t_click) + 90},{c.ms(t_click) + 200},\\fscx100\\fscy100)"
    c.ev(3, 0, None, f"\\an5\\pos({c.cx:.0f},{c.cy:.0f})\\p1\\1c{c.col(red)}\\bord0\\shad0{bounce}{press}\\fad(0,260)", c.rrect(bw, bh, 22 * k))
    c.ev(3, 0, None, f"\\an5\\pos({c.cx:.0f},{c.cy - bh * 0.28:.0f})\\p1\\1c&H00FFFFFF&\\1a&HC8&\\bord0\\shad0{bounce}\\fad(0,260)", c.rrect(bw * 0.92, bh * 0.3, 12 * k))
    fs = 56 * k
    c.ev(4, 0.15, t_click + 0.06, f"\\an5\\pos({c.cx:.0f},{c.cy:.0f})\\fn{c.font}\\fs{fs:.0f}\\b1\\bord{2 * k:.0f}\\3c&H00000070&\\shad0\\fad(150,0)", c.esc(st.get("label", "ABONE OL")))
    c.ev(4, t_click + 0.06, None, f"\\an5\\pos({c.cx:.0f},{c.cy:.0f})\\fn{c.font}\\fs{fs * 0.85:.0f}\\b1\\bord0\\shad0\\1c&H00DDDDDD&\\fad(0,260)", c.esc(st.get("done", "ABONE OLUNDU")))
    _cursor_path(c, [(0.35, c.cx + 380 * k, c.cy + 240 * k), (t_click - 0.05, c.cx + 120 * k, c.cy + 12 * k)], [t_click])


def _wave(c: _Ctx, kind: str) -> None:
    k, st = c.k, c.st
    text = st.get("label", "ABONE OL")
    fs = 92 * k
    col = c.col(st.get("color", "#FF2E2E"))
    body = ""
    for i, ch in enumerate(text):
        d0 = i * 60
        body += (f"{{\\fscy0\\t({d0},{d0 + 160},\\fscy125)\\t({d0 + 160},{d0 + 260},\\fscy100)"
                 f"\\t({900 + i * 60},{980 + i * 60},\\frz-6)\\t({980 + i * 60},{1060 + i * 60},\\frz0)}}{c.esc(ch)}")
    c.ev(5, 0, None, f"\\an5\\pos({c.cx:.0f},{c.cy:.0f})\\fn{c.st.get('font', 'Arial Black')}\\fs{fs:.0f}\\b1\\1c&H00FFFFFF&\\3c{col}\\bord{6 * k:.0f}\\shad{6 * k:.0f}\\4c&H90000000&\\fad(0,260)", body)
    c.ev(4, 0.6, None, f"\\an5\\pos({c.cx:.0f},{c.cy + fs * 0.62:.0f})\\p1\\1c{col}\\bord0\\shad0\\fscx0\\t(0,280,\\fscx100)\\fad(0,260)", c.rrect(fs * len(text) * 0.62, 12 * k, 6 * k))


def _meme(c: _Ctx, kind: str) -> None:
    k, st = c.k, c.st
    fs = 130 * k
    shake = "".join(f"\\t({i * 50},{i * 50 + 50},\\frz{(3 if i % 2 else -3)})" for i in range(min(60, int(c.dur * 20))))
    c.ev(5, 0, None, f"\\an5\\pos({c.cx:.0f},{c.cy - 40 * k:.0f})\\fn{st.get('font', 'Impact')}\\fs{fs:.0f}\\1c&H00FFFFFF&\\3c&H00000000&\\bord{9 * k:.0f}\\shad0"
         f"\\fscx20\\fscy20\\t(0,120,\\fscx110\\fscy110)\\t(120,200,\\fscx100\\fscy100){shake}\\fad(0,200)", c.esc(st.get("label", "ABONE OL")))
    for i in range(3):
        x = c.cx + (i - 1) * 260 * k
        pulse = "".join(f"\\t({j * 400},{j * 400 + 200},\\fscy{120 * k:.0f})\\t({j * 400 + 200},{j * 400 + 400},\\fscy{100 * k:.0f})" for j in range(int(c.dur * 2.5)))
        c.ev(4, 0.15 + i * 0.08, None, f"\\an8\\pos({x:.0f},{c.cy + 50 * k:.0f})\\p1\\1c&H0000E6FF&\\3c&H00000000&\\bord{4 * k:.0f}\\shad0\\fscx{100 * k:.0f}\\fscy{100 * k:.0f}{pulse}\\fad(100,200)", ARROW_DOWN)


def _social(c: _Ctx, kind: str) -> None:
    k, st = c.k, c.st
    rows = [("YouTube", "#FF0000", st.get("yt", "@kanal")), ("Instagram", "#E1306C", st.get("ig", "@kanal")), ("TikTok", "#111111", st.get("tt", "@kanal"))]
    rows = [r for r in rows if r[2]]
    h, gap = 86 * k, 22 * k
    y = c.cy - (len(rows) * (h + gap) - gap) / 2
    for i, (name, colr, handle) in enumerate(rows):
        t0 = i * 0.25
        x0 = c.cx - 300 * k
        c.ev(3, t0, None, f"\\an7\\move({x0 - 120 * k:.0f},{y:.0f},{x0:.0f},{y:.0f},0,260)\\fad(160,260)\\p1\\1c&H00161616&\\bord0\\shad{5 * k:.0f}\\4c&HA0000000&", c.rrect(600 * k, h, h / 2))
        c.ev(4, t0, None, f"\\an7\\move({x0 - 120 * k + 12 * k:.0f},{y + 12 * k:.0f},{x0 + 12 * k:.0f},{y + 12 * k:.0f},0,260)\\fad(160,260)\\p1\\1c{c.col(colr)}\\bord{2 * k:.0f}\\3c&H00FFFFFF&\\shad0",
             _ellipse(h - 24 * k, h - 24 * k))
        c.ev(5, t0, None, f"\\an4\\move({x0 - 120 * k + h + 10 * k:.0f},{y + h / 2:.0f},{x0 + h + 10 * k:.0f},{y + h / 2:.0f},0,260)\\fad(160,260)\\fn{c.font}\\fs{36 * k:.0f}\\b1\\bord0\\shad0",
             f"{c.esc(handle)}  {{\\1c&H00999999&\\b0\\fs{24 * k:.0f}}}{name}")
        y += h + gap


def _lss(c: _Ctx, kind: str) -> None:
    k, st = c.k, c.st
    items = [(THUMB, st.get("like", "BEĞEN"), "&H00D45F06&"), (SHARE, st.get("share", "PAYLAŞ"), "&H0049C24A&"), (BELL, st.get("label", "ABONE OL"), "&H000000FF&")]
    times = _timing(c, 3)
    pw, ph, gap = 300 * k, 96 * k, 30 * k
    x = c.cx - (3 * pw + 2 * gap) / 2
    pts = [(0.25, c.cx + 520 * k, c.cy + 260 * k)]
    for i, (icon, label, colr) in enumerate(items):
        t = times[i]
        c.ev(3, i * 0.12, None, _enter(c, x, c.cy - ph / 2) + f"\\p1\\1c&H00FFFFFF&\\bord0\\shad{5 * k:.0f}\\4c&HA0000000&\\t({c.ms(t - i * 0.12)},{c.ms(t - i * 0.12) + 140},\\1c{colr})",
             c.rrect(pw, ph, ph / 2))
        c.ev(4, i * 0.12, None, _enter(c, x + 26 * k, c.cy - 26 * k) + f"\\p1\\1c&H00303030&\\bord0\\shad0\\fscx{110 * k:.0f}\\fscy{110 * k:.0f}\\t({c.ms(t - i * 0.12)},{c.ms(t - i * 0.12) + 140},\\1c&H00FFFFFF&)",
             icon)
        c.ev(5, i * 0.12, None, f"\\an4\\move({x + 90 * k:.0f},{c.cy + 40 * k:.0f},{x + 90 * k:.0f},{c.cy:.0f},0,240)\\fad(180,260)\\fn{c.font}\\fs{32 * k:.0f}\\b1\\bord0\\shad0\\1c&H00303030&"
             f"\\t({c.ms(t - i * 0.12)},{c.ms(t - i * 0.12) + 140},\\1c&H00FFFFFF&)", c.esc(label))
        pts.append((t - 0.05, x + pw * 0.45, c.cy + 6 * k))
        x += pw + gap
    _cursor_path(c, pts, times)


# ---------------------------------------------------------------------------------------------------------------
def graphic(kind: str, ts, col, esc, rrect, s: float, e: float, W: int, H: int, st: dict) -> list[str]:
    c = _Ctx(ts, col, esc, rrect, s, e, W, H, st)
    k = c.k
    acc = col(st.get("color", "#8B5CF6"))
    title = esc(st.get("title", ""))
    sub = esc(st.get("sub", ""))
    if kind in ("lower", "lower-min"):
        x0 = W * float(st.get("x", 0.07))
        y0 = H * float(st.get("y", 0.80))
        if kind == "lower":
            c.ev(3, 0, None, f"\\an7\\pos({x0:.0f},{y0:.0f})\\p1\\1c{acc}\\bord0\\shad0\\fscx0\\t(0,260,\\fscx100)\\fad(0,300)", rrect(14 * k, 120 * k, 3 * k))
            bw = max(420, 34 * max(len(st.get("title", "")), len(st.get("sub", "")) * 0.7)) * k
            c.ev(2, 0.1, None, f"\\an7\\pos({x0 + 22 * k:.0f},{y0:.0f})\\p1\\1c&H00101010&\\1a&H30&\\bord0\\shad0"
                 f"\\clip({x0:.0f},{y0:.0f},{x0 + 22 * k:.0f},{y0 + 130 * k:.0f})\\t(0,380,\\clip({x0:.0f},{y0:.0f},{x0 + bw + 80 * k:.0f},{y0 + 130 * k:.0f}))\\fad(0,300)",
                 rrect(bw + 50 * k, 120 * k, 6 * k))
        clip0 = f"\\clip({x0:.0f},{y0 - 10:.0f},{x0 + 30 * k:.0f},{y0 + 140 * k:.0f})\\t(150,600,\\clip({x0:.0f},{y0 - 10:.0f},{x0 + W * 0.8:.0f},{y0 + 140 * k:.0f}))"
        c.ev(4, 0.15, None, f"\\an7\\pos({x0 + 48 * k:.0f},{y0 + 10 * k:.0f})\\fn{c.font}\\fs{50 * k:.0f}\\b1\\bord0\\shad{2 * k:.0f}{clip0}\\fad(0,300)", title or "İsim Soyisim")
        c.ev(4, 0.3, None, f"\\an7\\pos({x0 + 48 * k:.0f},{y0 + 68 * k:.0f})\\fn{c.font}\\fs{30 * k:.0f}\\bord0\\shad{2 * k:.0f}\\1c&H00CCCCCC&{clip0}\\fad(0,300)", sub or "Unvan / açıklama")
    elif kind == "location":
        x0, y0 = W * float(st.get("x", 0.06)), H * float(st.get("y", 0.1))
        c.ev(4, 0, None, f"\\an7\\pos({x0:.0f},{y0:.0f})\\p1\\1c{acc}\\bord0\\shad{2 * k:.0f}\\fscx{160 * k:.0f}\\fscy{160 * k:.0f}\\fscy10\\t(0,200,\\fscy{175 * k:.0f})\\t(200,300,\\fscy{160 * k:.0f})\\fad(0,300)", PIN)
        t = st.get("title", "İstanbul, Türkiye")
        per = 45
        body = "".join(f"{{\\alpha&HFF&\\t({300 + i * per},{301 + i * per},\\alpha&H00&)}}{esc(ch)}" for i, ch in enumerate(t))
        c.ev(4, 0, None, f"\\an4\\pos({x0 + 70 * k:.0f},{y0 + 34 * k:.0f})\\fn{c.font}\\fs{46 * k:.0f}\\b1\\bord{3 * k:.0f}\\shad0\\fad(0,300)", body)
        if sub:
            c.ev(4, 0.3 + len(t) * per / 1000, None, f"\\an4\\pos({x0 + 70 * k:.0f},{y0 + 84 * k:.0f})\\fn{c.font}\\fs{28 * k:.0f}\\bord{2 * k:.0f}\\1c&H00CCCCCC&\\fad(200,300)", sub)
    elif kind == "chapter":
        num = esc(st.get("num", "01"))
        cx, cy = W * float(st.get("x", 0.5)), H * float(st.get("y", 0.5))
        c.ev(2, 0, None, f"\\an5\\pos({cx:.0f},{cy:.0f})\\p1\\1c&H00000000&\\1a&H50&\\bord0\\shad0\\fscy0\\t(0,250,\\fscy100)\\fad(0,350)", rrect(W * 1.1, 260 * k, 0))
        c.ev(4, 0.1, None, f"\\an5\\pos({cx:.0f},{cy - 50 * k:.0f})\\fn{c.font}\\fs{90 * k:.0f}\\b1\\bord0\\shad0\\1c{acc}\\fsp{10 * k:.0f}\\fscx150\\t(0,350,\\fscx100)\\fad(150,350)", num)
        c.ev(4, 0.25, None, f"\\an5\\pos({cx:.0f},{cy + 50 * k:.0f})\\fn{c.font}\\fs{54 * k:.0f}\\b1\\bord0\\shad0\\fsp{6 * k:.0f}\\fad(250,350)", title or "BÖLÜM BAŞLIĞI")
    elif kind == "endscreen":
        bw, bh = W * 0.34, W * 0.34 * 9 / 16
        for i, x in enumerate((W * 0.27, W * 0.73)):
            c.ev(3, i * 0.12, None, f"\\an5\\pos({x:.0f},{H * 0.42:.0f})\\p1\\1a&HFF&\\3c&H00FFFFFF&\\bord{4 * k:.0f}\\shad0\\fscx80\\fscy80\\t(0,250,\\fscx100\\fscy100)\\fad(150,300)",
                 rrect(bw, bh, 16 * k))
            c.ev(4, i * 0.12 + 0.1, None, f"\\an5\\pos({x:.0f},{H * 0.42 + bh / 2 + 40 * k:.0f})\\fn{c.font}\\fs{34 * k:.0f}\\b1\\bord{2 * k:.0f}\\fad(200,300)",
                 esc(st.get("v1" if i == 0 else "v2", "Önerilen video" if i == 0 else "Son video")))
        r = 150 * k
        c.ev(3, 0.3, None, f"\\an5\\pos({W / 2:.0f},{H * 0.82:.0f})\\p1\\1c{acc}\\bord{5 * k:.0f}\\3c&H00FFFFFF&\\shad0\\fscx0\\fscy0\\t(0,220,\\fscx110\\fscy110)\\t(220,320,\\fscx100\\fscy100)\\fad(0,300)",
             _ellipse(r, r))
        if not st.get("avatarImg"):
            c.ev(4, 0.45, None, f"\\an5\\pos({W / 2:.0f},{H * 0.82:.0f})\\fn{c.font}\\fs{28 * k:.0f}\\b1\\bord0\\shad0\\fad(200,300)", esc(st.get("label", "ABONE OL")))
        if st.get("channel"):
            c.ev(4, 0.45, None, f"\\an5\\pos({W / 2:.0f},{H * 0.925:.0f})\\fn{c.font}\\fs{26 * k:.0f}\\b1\\bord{2 * k:.0f}\\shad0\\fad(200,300)", esc(st.get("channel", "")))
    elif kind == "callout":
        x, y = W * float(st.get("x", 0.5)), H * float(st.get("y", 0.5))
        sz = 130 * k * float(st.get("ring", 1))
        c.ev(5, 0, None, f"\\an5\\pos({x:.0f},{y:.0f})\\p1\\1a&HFF&\\3c{acc}\\bord{7 * k:.0f}\\shad0\\fscx{sz / 1:.0f}\\fscy{sz:.0f}"
             f"\\clip({x - sz:.0f},{y - sz:.0f},{x - sz:.0f},{y + sz:.0f})\\t(0,350,\\clip({x - sz:.0f},{y - sz:.0f},{x + sz:.0f},{y + sz:.0f}))\\fad(0,250)", CIRCLE)
        ax, ay = x + sz * 0.9, y + sz * 0.9
        c.ev(5, 0.25, None, f"\\an7\\move({ax + 120 * k:.0f},{ay + 120 * k:.0f},{ax:.0f},{ay:.0f},0,220)\\p1\\1c{acc}\\bord0\\shad{2 * k:.0f}\\frz-135\\fscx{90 * k:.0f}\\fscy{90 * k:.0f}\\fad(0,250)",
             ARROW_DOWN)
        if title:
            c.ev(5, 0.4, None, f"\\an7\\pos({ax + 60 * k:.0f},{ay + 80 * k:.0f})\\fn{c.font}\\fs{44 * k:.0f}\\b1\\bord{4 * k:.0f}\\shad0\\1c&H00FFFFFF&\\fad(150,250)", title)
    elif kind == "progress":
        y = H * float(st.get("y", 0.985))
        bh = 12 * k * float(st.get("thick", 1))
        c.ev(3, 0, None, f"\\an7\\pos(0,{y - bh:.0f})\\p1\\1c&H00FFFFFF&\\1a&HA0&\\bord0\\shad0", rrect(W, bh, 0))
        c.ev(4, 0, None, f"\\an7\\pos(0,{y - bh:.0f})\\p1\\1c{acc}\\bord0\\shad0\\clip(0,0,0,{H})\\t(0,{c.ms(c.dur)},\\clip(0,0,{W},{H}))", rrect(W, bh, 0))
    elif kind == "highlight":
        x, y = W * float(st.get("x", 0.5)), H * float(st.get("y", 0.5))
        t = st.get("title", "ÖNEMLİ NOKTA")
        fs = 64 * k
        w = len(t) * fs * 0.58
        c.ev(3, 0, None, f"\\an5\\pos({x:.0f},{y + fs * 0.08:.0f})\\p1\\1c{col(st.get('color', '#FFE600'))}\\bord0\\shad0\\frz-1.5"
             f"\\clip({x - w / 2 - 20:.0f},0,{x - w / 2 - 20:.0f},{H})\\t(0,320,\\clip({x - w / 2 - 20:.0f},0,{x + w / 2 + 20:.0f},{H}))\\fad(0,250)", rrect(w + 36 * k, fs * 0.9, 6 * k))
        c.ev(4, 0.1, None, f"\\an5\\pos({x:.0f},{y:.0f})\\fn{c.font}\\fs{fs:.0f}\\b1\\bord0\\shad0\\1c&H00111111&\\fad(150,250)", esc(t))
    elif kind == "counter":
        x, y = W * float(st.get("x", 0.5)), H * float(st.get("y", 0.5))
        n0, n1 = float(st.get("from", 0)), float(st.get("to", 1000))
        pre, post = esc(st.get("prefix", "")), esc(st.get("suffix", ""))
        steps = max(2, min(90, int(c.dur * 15)))
        run = min(c.dur * 0.75, 2.5)
        for i in range(steps):
            u = i / (steps - 1)
            u2 = 1 - (1 - u) ** 3
            v = n0 + (n1 - n0) * u2
            t0, t1 = run * i / steps, (run * (i + 1) / steps if i < steps - 1 else c.dur)
            txt = f"{int(round(v)):,}".replace(",", ".")
            c.ev(5, t0, t1, f"\\an5\\pos({x:.0f},{y:.0f})\\fn{c.font}\\fs{110 * k:.0f}\\b1\\bord{6 * k:.0f}\\shad0\\1c{acc}" + ("\\fad(0,250)" if i == steps - 1 else ""), f"{pre}{txt}{post}")
    elif kind == "quote":
        x, y = W * float(st.get("x", 0.5)), H * float(st.get("y", 0.5))
        c.ev(2, 0, None, f"\\an5\\pos({x:.0f},{y:.0f})\\p1\\1c&H00101010&\\1a&H20&\\bord0\\shad{8 * k:.0f}\\4c&HA0000000&\\fscx90\\fscy90\\t(0,250,\\fscx100\\fscy100)\\fad(150,300)",
             rrect(W * 0.62, 280 * k, 20 * k))
        c.ev(3, 0.1, None, f"\\an7\\pos({x - W * 0.29:.0f},{y - 150 * k:.0f})\\fn Georgia\\fs{160 * k:.0f}\\1c{acc}\\bord0\\shad0\\fad(150,300)", "“")
        c.ev(4, 0.2, None, f"\\an5\\pos({x:.0f},{y - 10 * k:.0f})\\fn{c.font}\\fs{42 * k:.0f}\\i1\\bord0\\shad0\\q0\\fad(200,300)", title or "Alıntı metni")
        if sub:
            c.ev(4, 0.4, None, f"\\an6\\pos({x + W * 0.28:.0f},{y + 100 * k:.0f})\\fn{c.font}\\fs{28 * k:.0f}\\bord0\\shad0\\1c&H00AAAAAA&\\fad(200,300)", f"— {sub}")
    return c.out
