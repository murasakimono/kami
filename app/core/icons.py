"""Kami modul ve dosya turu ikonlari (tek kaynak: pencere ikonlari + kurulum <app>\\icons\\*.ico).

2x supersampling (512->256) ile cizilir ve 16/32/48/256 cok katmanli .ico olarak kaydedilir.
"""
from __future__ import annotations

from pathlib import Path

ICON_SIZES: list[tuple[int, int]] = [(16, 16), (32, 32), (48, 48), (256, 256)]

MODULES: dict[str, tuple[str, tuple[int, int, int]]] = {
    "player": ("Kami Player", (46, 230, 166)),     # Zumrut yesili
    "studio": ("Kami Studio", (167, 139, 250)),    # Mor
    "picture": ("Kami Picture", (56, 189, 248)),   # Gok mavisi
    "reader": ("Kami Reader", (245, 158, 11)),     # Kehribar / Altin
    "games": ("Kami Games", (129, 140, 248)),      # Indigo
    "music": ("Kamify", (232, 121, 249)),          # Orkide / Magenta
    "cleaner": ("Kami Cleaner", (251, 113, 133)),  # Mercan pembe
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


def write_ico(key: str, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    im = render_icon_image(key, size=256)
    im.save(out_path, format="ICO", sizes=ICON_SIZES)
    return out_path


def export_all(icons_dir: Path) -> list[Path]:
    """Tum modul .ico dosyalarini hedef klasore uretir."""
    icons_dir.mkdir(parents=True, exist_ok=True)
    return [write_ico(key, icons_dir / f"{key}.ico") for key in MODULES]
