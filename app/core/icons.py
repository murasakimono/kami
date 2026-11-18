"""Kami modul ve dosya turu ikonlari (tek kaynak: pencere ikonlari + kurulum <app>\\icons\\*.ico).

2x supersampling (512->256) ile cizilir ve 16/32/48/256 cok katmanli .ico olarak kaydedilir.
"""
from __future__ import annotations

from pathlib import Path

ICON_SIZES: list[tuple[int, int]] = [(16, 16), (32, 32), (48, 48), (256, 256)]

MODULES: dict[str, tuple[str, tuple[int, int, int]]] = {
    "main": ("Kami", (164, 118, 248)),           # Canli Kami moru
    "player": ("Kami Player", (46, 230, 166)),     # Zumrut yesili
    "studio": ("Kami Studio", (167, 139, 250)),    # Mor
    "picture": ("Kami Picture", (56, 189, 248)),   # Gok mavisi
    "reader": ("Kami Reader", (245, 158, 11)),     # Kehribar / Altin
    "games": ("Kami Games", (126, 138, 244)),      # Indigo (games.png ile birebir uyumlu)
    "music": ("Kamify", (232, 121, 249)),          # Orkide / Magenta
    "cleaner": ("Kami Cleaner", (244, 114, 134)),  # Mercan pembe (cleaner.png ile birebir uyumlu)
}


def render_icon_image(key: str, size: int = 256):
    """Belirtilen modul icin RGBA Pillow Image uretir (gomulu PNG varsa onu kullanir)."""
    from PIL import Image, ImageDraw
    from app import paths

    embedded = paths.WEB_DIR / "icons" / f"{key}.png"
    if embedded.is_file():
        im = Image.open(embedded).convert("RGBA")
        if im.size != (size, size):
            im = im.resize((size, size), Image.Resampling.LANCZOS)
        return im

    S = 512  # 2x supersampling
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    _, (r, g, b) = MODULES.get(key, ("Kami", (157, 107, 255)))
    acc = (r, g, b, 255)
    soft = (r, g, b, 55)
    bg = (12, 8, 22, 255)
    bevel = (44, 30, 68, 255)

    # Dis koyu Kami rozeti + neon kenarlik + ic krom cerceve
    d.rounded_rectangle([24, 24, S - 24, S - 24], radius=116, fill=bg, outline=acc, width=22)
    d.rounded_rectangle([54, 54, S - 54, S - 54], radius=92, outline=bevel, width=6)

    if key == "player":
        d.ellipse([112, 112, S - 112, S - 112], fill=soft, outline=acc, width=18)
        d.polygon([(204, 156), (366, 256), (204, 356)], fill=acc)
    elif key == "studio":
        # Klaket govdesi + ust capraz seritler
        d.rounded_rectangle([108, 168, 404, 384], radius=24, fill=soft, outline=acc, width=18)
        d.rounded_rectangle([108, 124, 404, 186], radius=16, fill=bg, outline=acc, width=16)
        for sx in (156, 232, 308):
            d.polygon([(sx, 130), (sx + 34, 130), (sx + 10, 180), (sx - 24, 180)], fill=acc)
        d.polygon([(224, 226), (318, 276), (224, 326)], fill=acc)
    elif key == "picture":
        d.rounded_rectangle([104, 124, 408, 388], radius=26, fill=soft, outline=acc, width=18)
        d.ellipse([146, 162, 206, 222], fill=acc)
        d.polygon([(122, 366), (236, 240), (314, 322), (352, 276), (390, 366)], fill=acc)
    elif key == "reader":
        # Acik iki sayfa kitap + ayraç seridi
        d.rounded_rectangle([96, 132, 256, 376], radius=18, fill=soft, outline=acc, width=16)
        d.rounded_rectangle([256, 132, 416, 376], radius=18, fill=soft, outline=acc, width=16)
        d.line([(256, 136), (256, 372)], fill=acc, width=14)
        for y in (192, 242, 292):
            d.line([(132, y), (222, y)], fill=acc, width=12)
            d.line([(290, y), (380, y)], fill=acc, width=12)
        d.polygon([(332, 132), (368, 132), (368, 208), (350, 188), (332, 208)], fill=(251, 113, 133, 255))
    elif key == "games":
        d.rounded_rectangle([88, 168, 424, 344], radius=78, fill=soft, outline=acc, width=18)
        # D-pad
        d.line([(168, 212), (168, 300)], fill=acc, width=22)
        d.line([(124, 256), (212, 256)], fill=acc, width=22)
        # Aksiyon dugmeleri
        d.ellipse([306, 214, 346, 254], fill=acc)
        d.ellipse([348, 258, 388, 298], fill=acc)
    elif key == "music":
        # Ikili nota + ses dalgasi
        d.ellipse([128, 304, 212, 378], fill=acc)
        d.ellipse([284, 278, 368, 352], fill=acc)
        d.line([(202, 336), (202, 164)], fill=acc, width=20)
        d.line([(358, 310), (358, 138)], fill=acc, width=20)
        d.polygon([(192, 150), (368, 122), (368, 166), (192, 194)], fill=acc)
    elif key == "cleaner":
        # Suzgec + yildiz pariltisi
        d.polygon([(112, 136), (400, 136), (288, 266), (288, 380), (224, 352), (224, 266)],
                  fill=soft, outline=acc, width=18)
        d.polygon([(356, 246), (370, 286), (410, 300), (370, 314), (356, 354), (342, 314), (302, 300), (342, 286)],
                  fill=acc)

    if size != S:
        im = im.resize((size, size), Image.Resampling.LANCZOS)
    return im


def render_compact_icon(key: str, size: int = 32):
    """16 ve 32 px gibi kucuk katmanlar icin boynuzsuz, yuksek kontrastli sade modul simgesi uretir."""
    from PIL import Image, ImageDraw

    S = 128
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    _, (r, g, b) = MODULES.get(key, ("Kami", (164, 118, 248)))
    acc = (r, g, b, 255)
    bg = (14, 10, 26, 255)
    d.rounded_rectangle([6, 6, S - 6, S - 6], radius=30, fill=bg, outline=acc, width=10)

    if key == "main":
        d.ellipse([24, 34, S - 24, S - 34], fill=(46, 230, 166, 255))
        d.ellipse([54, 38, 74, 90], fill=(10, 7, 18, 255))
    elif key == "player":
        d.polygon([(44, 30), (96, 64), (44, 98)], fill=acc)
    elif key == "studio":
        d.rounded_rectangle([26, 34, 102, 94], radius=10, outline=acc, width=10)
        d.line([(26, 52), (102, 52)], fill=acc, width=10)
    elif key == "picture":
        d.rounded_rectangle([26, 30, 102, 98], radius=10, outline=acc, width=10)
        d.ellipse([38, 40, 56, 58], fill=acc)
        d.polygon([(32, 90), (62, 58), (96, 90)], fill=acc)
    elif key == "reader":
        d.rounded_rectangle([26, 28, 64, 100], radius=6, fill=(r, g, b, 70), outline=acc, width=8)
        d.rounded_rectangle([64, 28, 102, 100], radius=6, fill=(r, g, b, 70), outline=acc, width=8)
    elif key == "games":
        d.line([(44, 46), (44, 82)], fill=acc, width=12)
        d.line([(26, 64), (62, 64)], fill=acc, width=12)
        d.ellipse([74, 48, 92, 66], fill=acc)
        d.ellipse([86, 68, 104, 86], fill=acc)
    elif key == "music":
        d.ellipse([28, 74, 54, 98], fill=acc)
        d.ellipse([72, 66, 98, 90], fill=acc)
        d.line([(48, 84), (48, 34), (92, 28), (92, 76)], fill=acc, width=12)
    elif key == "cleaner":
        d.polygon([(26, 32), (102, 32), (72, 68), (72, 98), (56, 90), (56, 68)], fill=acc)
    return im.resize((size, size), Image.Resampling.LANCZOS)


def write_ico(key: str, out_path: Path) -> Path:
    """Tum katmanlarda (16/32/48/256) ayni maskotlu tasarimi tek .ico'da birlestirir."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    im256 = render_icon_image(key, size=256)
    im48 = render_icon_image(key, size=48)
    im32 = render_icon_image(key, size=32)
    im16 = render_icon_image(key, size=16)
    im256.save(out_path, format="ICO", append_images=[im48, im32, im16])
    return out_path


def export_all(icons_dir: Path) -> list[Path]:
    """Tum modul .ico dosyalarini hedef klasore uretir."""
    icons_dir.mkdir(parents=True, exist_ok=True)
    return [write_ico(key, icons_dir / f"{key}.ico") for key in MODULES if key != "main"]
