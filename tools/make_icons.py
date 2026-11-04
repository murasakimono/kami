"""Eklenti simgelerini (16/32/48/128 PNG) saf Python ile uretir. Arayuzdeki marka isaretinin aynisi:
koyu zemin uzerinde kivrik koseli kagit + asagi ok.

  .venv\\Scripts\\python.exe tools\\make_icons.py
"""
from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "extension" / "icons"

BG = (0x1A, 0x1C, 0x24)
PAPER = (0xE6, 0xE8, 0xEF)
ACCENT = (0x4C, 0xC3, 0xD9)

# 32x32 tasarim izgarasinda cizgiler (arayuzdeki SVG ile ayni)
PAGE = [((6, 5), (20, 5)), ((20, 5), (26, 11)), ((26, 11), (26, 27)), ((26, 27), (6, 27)), ((6, 27), (6, 5)),
        ((20, 5), (20, 11)), ((20, 11), (26, 11))]
ARROW = [((16, 13), (16, 22)), ((12, 18), (16, 22)), ((16, 22), (20, 18))]


def _seg_dist(px, py, a, b):
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _rounded_rect_inside(x, y, size, r):
    cx = min(max(x, r), size - r)
    cy = min(max(y, r), size - r)
    return math.hypot(x - cx, y - cy) <= r


def render(size: int) -> bytes:
    ss = 4  # alt ornekleme (yumusak kenar)
    scale = size / 32
    # kucuk boyutlarda cizgiler kalinlassin ki okunabilsin
    w_page = 2.0 if size >= 48 else 2.6
    w_arrow = 2.4 if size >= 48 else 3.0
    radius = 7 * scale
    rows = []
    for y in range(size):
        row = bytearray([0])  # filtre baytı
        for x in range(size):
            acc = [0.0, 0.0, 0.0, 0.0]
            for sy in range(ss):
                for sx in range(ss):
                    px = (x + (sx + .5) / ss)
                    py = (y + (sy + .5) / ss)
                    if not _rounded_rect_inside(px, py, size, radius):
                        continue
                    gx, gy = px / scale, py / scale
                    color = BG
                    if min(_seg_dist(gx, gy, a, b) for a, b in PAGE) <= w_page / 2:
                        color = PAPER
                    if min(_seg_dist(gx, gy, a, b) for a, b in ARROW) <= w_arrow / 2:
                        color = ACCENT
                    acc[0] += color[0]; acc[1] += color[1]; acc[2] += color[2]; acc[3] += 255
            n = ss * ss
            alpha = acc[3] / n
            if alpha:
                row += bytes([round(acc[0] / (acc[3] / 255)), round(acc[1] / (acc[3] / 255)),
                              round(acc[2] / (acc[3] / 255)), round(alpha)])
            else:
                row += b"\0\0\0\0"
        rows.append(bytes(row))
    return _png(size, size, b"".join(rows))


def _png(w: int, h: int, raw: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)  # 8 bit RGBA
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for s in (16, 32, 48, 128):
        (OUT / f"{s}.png").write_bytes(render(s))
        print("yazildi:", OUT / f"{s}.png")
