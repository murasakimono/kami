"""Kami 2.0 modul ve dosya turu ikonlari (tek kaynak: pencere ikonlari + packaging/kami.ico + <app>\\icons\\*.ico).

Kullanici secimleri (Kami 2.0):
- Kami Ana (main): M3 (kami.png uzerinden karakterin boynuzlari + mor alev kaslar + 3B zumrut goz makro kesiti).
- Kami Studio (studio): S4 Mavi (tamamen mavi geometrik makas: halkalar #38BDF8, bicaklar #7DD3FC, yesil yok).
- Kami Oda (room): O1 (kompakt canli sinyal (( * ))).
- Diger 6 onayli ikon: Player, Picture, Reader, Games, Kamify (music), Cleaner.
"""
from __future__ import annotations

from pathlib import Path

ICON_SIZES: list[tuple[int, int]] = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

MODULES: dict[str, tuple[str, tuple[int, int, int]]] = {
    "main": ("Kami", (157, 107, 255)),            # M3 Karakter Makro (Boynuz + 3B Zumrut Goz)
    "player": ("Kami Player", (46, 230, 166)),    # Zumrut yesili
    "studio": ("Kami Studio", (56, 189, 248)),    # S4 Tam Mavi Makas (#38BDF8)
    "picture": ("Kami Picture", (244, 114, 182)), # Pembe (#F472B6)
    "reader": ("Kami Reader", (251, 191, 36)),    # Kehribar / Altin (#FBBF24)
    "games": ("Kami Games", (129, 140, 248)),     # Indigo (#818CF8)
    "music": ("Kamify", (29, 185, 84)),           # Zumrut/Spotify Yesili (#1DB954)
    "cleaner": ("Kami Cleaner", (251, 113, 133)), # Mercan Pembe (#FB7185)
    "room": ("Kami Oda", (168, 85, 247)),         # O1 Mor/Zumrut Canli Sinyal (#A855F7)
}


def _draw_horned_chassis(im, d, S: int, accent: tuple[int, int, int], glow: tuple[int, int, int]):
    """512x512 (24x24 koordinat sisteminin 21.333x olcegi) uzerinde boynuzlu sekizgen rozet kasasi cizer."""
    k = S / 24.0
    r, g, b = accent
    gr, gg, gb = glow
    # Boynuzlar (sol ve sag kavisli poligon)
    left_horn = [
        (5.4 * k, 8.2 * k), (4.5 * k, 5.8 * k), (4.8 * k, 3.2 * k),
        (6.2 * k, 1.7 * k), (8.0 * k, 1.3 * k), (7.2 * k, 3.6 * k),
        (7.5 * k, 5.5 * k), (8.8 * k, 6.8 * k),
    ]
    right_horn = [(S - x, y) for (x, y) in left_horn]
    d.polygon(left_horn, fill=(min(255, r + 55), min(255, g + 55), min(255, b + 55), 255))
    d.polygon(right_horn, fill=(min(255, r + 55), min(255, g + 55), min(255, b + 55), 255))

    # Sekizgen rozet govdesi
    oct_pts = [
        (5.2 * k, 5.4 * k), (18.8 * k, 5.4 * k), (21.2 * k, 7.8 * k),
        (21.2 * k, 19.6 * k), (18.8 * k, 22.0 * k), (5.2 * k, 22.0 * k),
        (2.8 * k, 19.6 * k), (2.8 * k, 7.8 * k),
    ]
    d.polygon(oct_pts, fill=(14, 10, 24, 255))
    for i in range(len(oct_pts)):
        p1 = oct_pts[i]
        p2 = oct_pts[(i + 1) % len(oct_pts)]
        d.line([p1, p2], fill=(r, g, b, 255), width=max(2, int(round(1.28 * k))))

    # Ust neon isik cizgisi
    d.line([(5.9 * k, 6.85 * k), (18.1 * k, 6.85 * k)], fill=(gr, gg, gb, 115), width=max(1, int(round(0.85 * k))))


def _render_main_m3(size: int = 256):
    """Kami Ana M3: kami.png uzerinden karakterin boynuzlari + mor alev kaslari + 3B zumrut goz makro kesiti."""
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
    from app import paths

    src = paths.WEB_DIR / "kami.png"
    S = 512
    if src.is_file():
        raw = Image.open(src).convert("RGBA")
        w, h = raw.size
        # M3 Makro Bakis kesiti: x %19..%81, y %11..%63
        crop = raw.crop((int(w * 0.19), int(h * 0.11), int(w * 0.81), int(h * 0.63)))
        r, g, b, a = crop.split()
        rgb = Image.merge("RGB", (r, g, b))
        rgb = ImageEnhance.Contrast(rgb).enhance(1.26)
        rgb = ImageEnhance.Color(rgb).enhance(1.22)
        rgb = ImageEnhance.Sharpness(rgb).enhance(1.48)
        r2, g2, b2 = rgb.split()
        crop = Image.merge("RGBA", (r2, g2, b2, a)).resize((S - 44, S - 44), Image.Resampling.LANCZOS)

        canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(canvas)
        d.rounded_rectangle([18, 18, S - 18, S - 18], radius=110, fill=(13, 9, 22, 255))

        mask = Image.new("L", (S - 44, S - 44), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 45, S - 45], radius=98, fill=255)
        canvas.paste(crop, (22, 22), mask)
        d.rounded_rectangle([18, 18, S - 18, S - 18], radius=110, outline=(157, 107, 255, 255), width=22)
        d.rounded_rectangle([36, 36, S - 36, S - 36], radius=96, outline=(46, 230, 166, 90), width=5)
        out = canvas.resize((size, size), Image.Resampling.LANCZOS)
        if size <= 48:
            out = out.filter(ImageFilter.UnsharpMask(radius=0.65, percent=135, threshold=1))
        return out

    # Yedek (kami.png bulunamazsa)
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    _draw_horned_chassis(im, d, S, (157, 107, 255), (46, 230, 166))
    k = S / 24.0
    d.ellipse([7.7 * k, 9.5 * k, 16.3 * k, 18.1 * k], outline=(196, 181, 253, 255), width=int(1.7 * k))
    d.rounded_rectangle([11.15 * k, 11.3 * k, 12.85 * k, 16.3 * k], radius=int(0.85 * k), fill=(46, 230, 166, 255))
    return im.resize((size, size), Image.Resampling.LANCZOS)


def render_icon_image(key: str, size: int = 256, use_cache: bool = False):
    """Belirtilen modul icin RGBA Pillow Image uretir (512->size supersampling)."""
    from PIL import Image, ImageDraw, ImageFilter

    if key == "main":
        return _render_main_m3(size=size)

    S = 512
    k = S / 24.0
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    _, accent = MODULES.get(key, ("Kami", (157, 107, 255)))
    glow_map = {
        "player": (46, 230, 166),
        "studio": (56, 189, 248),
        "picture": (244, 114, 182),
        "reader": (251, 191, 36),
        "games": (46, 230, 166),
        "music": (46, 230, 166),
        "cleaner": (251, 113, 133),
        "room": (46, 230, 166),
    }
    _draw_horned_chassis(im, d, S, accent, glow_map.get(key, accent))

    if key == "player":
        d.polygon([(9.0 * k, 8.8 * k), (17.6 * k, 13.8 * k), (9.0 * k, 18.8 * k)], fill=(46, 230, 166, 255))
        d.polygon([(11.0 * k, 11.8 * k), (14.5 * k, 13.8 * k), (11.0 * k, 15.8 * k)], fill=(10, 18, 20, 255))
    elif key == "studio":
        # S4 Mavi: Tamamen mavi geometrik makas (Halkalar #38BDF8, Bicaklar #7DD3FC, sifir yesil)
        blue_ring = (56, 189, 248, 255)
        blue_blade = (125, 211, 252, 255)
        w_ring = int(round(1.65 * k))
        w_blade = int(round(1.75 * k))
        # Bicaklar
        d.line([(10.4 * k, 15.3 * k), (15.2 * k, 9.8 * k)], fill=blue_blade, width=w_blade)
        d.line([(13.6 * k, 15.3 * k), (8.8 * k, 9.8 * k)], fill=blue_blade, width=w_blade)
        # Makas halkalari
        for cx, cy in ((9.3 * k, 16.5 * k), (14.7 * k, 16.5 * k)):
            r_px = 1.58 * k
            d.ellipse([cx - r_px, cy - r_px, cx + r_px, cy + r_px], fill=(14, 10, 24, 255), outline=blue_ring, width=w_ring)
    elif key == "picture":
        pink = (244, 114, 182, 255)
        w_ln = int(round(1.7 * k))
        # 4 vizor kosesi
        for pts in (
            [(6.8 * k, 11.4 * k), (6.8 * k, 9.0 * k), (9.4 * k, 9.0 * k)],
            [(14.6 * k, 9.0 * k), (17.2 * k, 9.0 * k), (17.2 * k, 11.4 * k)],
            [(17.2 * k, 16.2 * k), (17.2 * k, 18.6 * k), (14.6 * k, 18.6 * k)],
            [(9.4 * k, 18.6 * k), (6.8 * k, 18.6 * k), (6.8 * k, 16.2 * k)],
        ):
            d.line(pts[:2], fill=pink, width=w_ln)
            d.line(pts[1:], fill=pink, width=w_ln)
        d.polygon([(12.0 * k, 10.7 * k), (14.9 * k, 13.8 * k), (12.0 * k, 16.9 * k), (9.1 * k, 13.8 * k)],
                  fill=(251, 207, 232, 255))
    elif key == "reader":
        amb = (251, 191, 36, 255)
        pts = [(6.2 * k, 10.0 * k), (12.0 * k, 11.6 * k), (17.8 * k, 10.0 * k),
               (17.8 * k, 17.8 * k), (12.0 * k, 19.3 * k), (6.2 * k, 17.8 * k)]
        d.polygon(pts, fill=(42, 31, 10, 255))
        for i in range(len(pts)):
            d.line([pts[i], pts[(i + 1) % len(pts)]], fill=amb, width=int(round(1.6 * k)))
        d.line([(12.0 * k, 11.6 * k), (12.0 * k, 19.2 * k)], fill=(253, 230, 138, 255), width=int(round(1.5 * k)))
    elif key == "games":
        w_ln = int(round(2.0 * k))
        d.line([(9.0 * k, 10.5 * k), (9.0 * k, 17.1 * k)], fill=(199, 210, 254, 255), width=w_ln)
        d.line([(5.7 * k, 13.8 * k), (12.3 * k, 13.8 * k)], fill=(199, 210, 254, 255), width=w_ln)
        r1 = 1.38 * k
        d.ellipse([15.8 * k - r1, 12.2 * k - r1, 15.8 * k + r1, 12.2 * k + r1], fill=(46, 230, 166, 255))
        d.ellipse([17.8 * k - r1, 14.9 * k - r1, 17.8 * k + r1, 14.9 * k + r1], fill=(167, 139, 250, 255))
    elif key == "music":
        bars = [
            (7.2, 13.0, 16.5, (46, 230, 166, 255)),
            (10.4, 9.8, 18.2, (46, 230, 166, 255)),
            (13.6, 11.3, 17.0, (167, 243, 208, 255)),
            (16.8, 9.2, 18.4, (46, 230, 166, 255)),
        ]
        for bx, y1, y2, col in bars:
            d.rounded_rectangle([(bx - 0.95) * k, y1 * k, (bx + 0.95) * k, y2 * k], radius=int(0.95 * k), fill=col)
    elif key == "cleaner":
        cx, cy, rad = 12.0 * k, 13.9 * k, 4.6 * k
        rose = (251, 113, 133, 255)
        d.pieslice([cx - rad, cy - rad, cx + rad, cy + rad], start=-90, end=8, fill=rose)
        d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=rose, width=int(round(1.6 * k)))
        ir = 1.45 * k
        d.ellipse([cx - ir, cy - ir, cx + ir, cy + ir], fill=(13, 9, 22, 255))
    elif key == "room":
        # O1: Kompakt Canlı Sinyal (( * ))
        cx, cy = 12.0 * k, 13.8 * k
        cr = 1.52 * k
        d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=(46, 230, 166, 255))
        ar = 3.35 * k
        w_arc = int(round(1.7 * k))
        lav = (196, 181, 253, 255)
        d.arc([cx - ar, cy - ar, cx + ar, cy + ar], start=138, end=222, fill=lav, width=w_arc)
        d.arc([cx - ar, cy - ar, cx + ar, cy + ar], start=-42, end=42, fill=lav, width=w_arc)

    out = im.resize((size, size), Image.Resampling.LANCZOS)
    if size <= 48:
        out = out.filter(ImageFilter.UnsharpMask(radius=0.6, percent=125, threshold=1))
    return out


def render_compact_icon(key: str, size: int = 32):
    return render_icon_image(key, size=size)


def render_small_icon(key: str, size: int = 32):
    return render_icon_image(key, size=size)


def write_ico(key: str, out_path: Path) -> Path:
    """16/24/32/48/64/128/256 px cok katmanli .ico dosyasi uretir."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    im256 = render_icon_image(key, size=256)
    layers = [
        render_icon_image(key, size=128),
        render_icon_image(key, size=64),
        render_icon_image(key, size=48),
        render_icon_image(key, size=32),
        render_icon_image(key, size=24),
        render_icon_image(key, size=16),
    ]
    im256.save(
        out_path,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        append_images=layers,
    )
    return out_path


def sync_embedded_pngs() -> None:
    """app/ui/web/icons/*.png ve packaging/kami.ico dosyalarini Kami 2.0 tasarimiyla gunceller."""
    from app import paths
    icons_dir = paths.WEB_DIR / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)
    for key in MODULES:
        im = render_icon_image(key, size=256)
        im.save(icons_dir / f"{key}.png", format="PNG")
    pkg_ico = Path(__file__).resolve().parents[2] / "packaging" / "kami.ico"
    if pkg_ico.parent.is_dir():
        write_ico("main", pkg_ico)


def icon_tag() -> str:
    try:
        from app.core.extras import APP_VERSION
        return APP_VERSION.replace(".", "")
    except Exception:
        return "200"


def export_all(icons_dir: Path) -> list[Path]:
    """Tum modul .ico dosyalarini hedef klasore uretir."""
    icons_dir.mkdir(parents=True, exist_ok=True)
    tag = icon_tag()
    return [write_ico(key, icons_dir / f"{key}-{tag}.ico") for key in MODULES if key != "main"]
