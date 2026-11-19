"""Kami Picture: Katmanli Adobe Photoshop (.psd) okuyucu.

Sifir zorunlu dis bagimlilik:
- Ortamda `psd-tools` kuruluysa oncelikli olarak onu kullanir.
- Kurulu degilse saf Python + Pillow ile Adobe PSD ikili dosya formatini (8BPS v1, RGB/Grayscale,
  PackBits RLE ve RAW kanal verisi, katman adi, konum, opaklik, gorunurluk ve karisim modu) cozer.
- Katman blogu olmayan / desteklenmeyen renk modlu PSD'lerde Pillow birlesik goruntusuyle tek katman doner.
"""
from __future__ import annotations

import base64
import io
import os
import struct
from typing import Any

from PIL import Image


_BLEND_MAP = {
    b"norm": "source-over",
    b"mul ": "multiply",
    b"scrn": "screen",
    b"over": "overlay",
    b"dark": "darken",
    b"lite": "lighten",
    b"div ": "color-dodge",
    b"idiv": "color-burn",
    b"hLit": "hard-light",
    b"sLit": "soft-light",
    b"diff": "difference",
    b"hue ": "hue",
    b"colr": "color",
    b"lum ": "luminosity",
}


def _img_to_data_url(im: Image.Image) -> str:
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _unpack_bits(data: bytes, expected: int) -> bytes:
    out = bytearray()
    i = 0
    n = len(data)
    while i < n and len(out) < expected:
        b = data[i]
        i += 1
        if b < 128:
            cnt = b + 1
            out.extend(data[i : i + cnt])
            i += cnt
        elif b > 128:
            cnt = 257 - b
            if i < n:
                out.extend(bytes([data[i]]) * cnt)
                i += 1
    if len(out) < expected:
        out.extend(b"\x00" * (expected - len(out)))
    return bytes(out[:expected])


def _read_psd_native(path: str) -> dict[str, Any]:
    with open(path, "rb") as f:
        raw = f.read()
    if len(raw) < 26 or raw[:4] != b"8BPS":
        return {"ok": False, "error": "invalid_psd"}
    version = struct.unpack(">H", raw[4:6])[0]
    if version != 1:
        return {"ok": False, "error": "psb_fallback"}
    channels, height, width, depth, color_mode = struct.unpack(">HIIHH", raw[12:26])
    if depth != 8 or color_mode not in (1, 3):  # Grayscale=1, RGB=3
        return {"ok": False, "error": "mode_fallback"}

    pos = 26
    # Color Mode Data
    cm_len = struct.unpack(">I", raw[pos : pos + 4])[0]
    pos += 4 + cm_len
    # Image Resources
    ir_len = struct.unpack(">I", raw[pos : pos + 4])[0]
    pos += 4 + ir_len
    # Layer and Mask Information
    if pos + 4 > len(raw):
        return {"ok": False, "error": "no_layers"}
    lm_len = struct.unpack(">I", raw[pos : pos + 4])[0]
    pos += 4
    if lm_len <= 4 or pos + lm_len > len(raw):
        return {"ok": False, "error": "no_layers"}

    layer_info_len = struct.unpack(">I", raw[pos : pos + 4])[0]
    pos += 4
    if layer_info_len <= 2:
        return {"ok": False, "error": "no_layers"}
    layer_count = struct.unpack(">h", raw[pos : pos + 2])[0]
    pos += 2
    layer_count = abs(layer_count)
    if layer_count == 0 or layer_count > 120:
        return {"ok": False, "error": "no_layers"}

    records: list[dict[str, Any]] = []
    for _ in range(layer_count):
        top, left, bottom, right = struct.unpack(">iiii", raw[pos : pos + 16])
        pos += 16
        ch_count = struct.unpack(">H", raw[pos : pos + 2])[0]
        pos += 2
        ch_info: list[tuple[int, int]] = []
        for _ in range(ch_count):
            cid, clen = struct.unpack(">hI", raw[pos : pos + 6])
            pos += 6
            ch_info.append((cid, clen))
        sig = raw[pos : pos + 4]
        if sig != b"8BIM":
            return {"ok": False, "error": "corrupt_layer_record"}
        pos += 4
        blend_key = raw[pos : pos + 4]
        pos += 4
        opacity, clipping, flags, _filler = struct.unpack(">BBBB", raw[pos : pos + 4])
        pos += 4
        extra_len = struct.unpack(">I", raw[pos : pos + 4])[0]
        pos += 4
        extra_end = pos + extra_len

        # Layer mask data
        mask_len = struct.unpack(">I", raw[pos : pos + 4])[0]
        pos += 4 + mask_len
        # Blending ranges
        br_len = struct.unpack(">I", raw[pos : pos + 4])[0]
        pos += 4 + br_len
        # Pascal layer name (padded to 4 bytes)
        name_len = raw[pos]
        name_bytes = raw[pos + 1 : pos + 1 + name_len]
        name = name_bytes.decode("latin-1", "replace")
        padded = ((1 + name_len + 3) // 4) * 4
        pos += padded

        # Additional layer info (luni = Unicode name)
        while pos + 12 <= extra_end:
            asig = raw[pos : pos + 4]
            if asig not in (b"8BIM", b"8B64"):
                break
            akey = raw[pos + 4 : pos + 8]
            alen = struct.unpack(">I", raw[pos + 8 : pos + 12])[0]
            pos += 12
            adata = raw[pos : pos + alen]
            if akey == b"luni" and len(adata) >= 4:
                ucount = struct.unpack(">I", adata[:4])[0]
                if 4 + ucount * 2 <= len(adata):
                    uname = adata[4 : 4 + ucount * 2].decode("utf-16-be", "replace").rstrip("\x00")
                    if uname:
                        name = uname
            pos += alen + (alen & 1)
        pos = extra_end

        records.append({
            "name": name or "Katman",
            "top": top,
            "left": left,
            "bottom": bottom,
            "right": right,
            "channels": ch_info,
            "blend": _BLEND_MAP.get(blend_key, "source-over"),
            "op": round(opacity / 255.0, 3),
            "vis": not bool(flags & 0x02),
            "clip": bool(clipping),
        })

    layers_out: list[dict[str, Any]] = []
    for rec in records:
        lw = max(0, rec["right"] - rec["left"])
        lh = max(0, rec["bottom"] - rec["top"])
        ch_planes: dict[int, bytes] = {}
        for cid, clen in rec["channels"]:
            ch_end = pos + clen
            if clen >= 2 and lw > 0 and lh > 0 and ch_end <= len(raw):
                comp = struct.unpack(">H", raw[pos : pos + 2])[0]
                if comp == 0:
                    plane = raw[pos + 2 : pos + 2 + lw * lh]
                    if len(plane) < lw * lh:
                        plane = plane + b"\x00" * (lw * lh - len(plane))
                    ch_planes[cid] = plane
                elif comp == 1:
                    row_lens = struct.unpack(f">{lh}H", raw[pos + 2 : pos + 2 + lh * 2])
                    rpos = pos + 2 + lh * 2
                    rows = bytearray()
                    for rl in row_lens:
                        rows.extend(_unpack_bits(raw[rpos : rpos + rl], lw))
                        rpos += rl
                    ch_planes[cid] = bytes(rows)
            pos = ch_end

        if lw <= 0 or lh <= 0:
            continue
        if color_mode == 3 and 0 in ch_planes and 1 in ch_planes and 2 in ch_planes:
            r_im = Image.frombytes("L", (lw, lh), ch_planes[0])
            g_im = Image.frombytes("L", (lw, lh), ch_planes[1])
            b_im = Image.frombytes("L", (lw, lh), ch_planes[2])
            a_im = Image.frombytes("L", (lw, lh), ch_planes[-1]) if -1 in ch_planes else Image.new("L", (lw, lh), 255)
            im = Image.merge("RGBA", (r_im, g_im, b_im, a_im))
        elif color_mode == 1 and 0 in ch_planes:
            g_im = Image.frombytes("L", (lw, lh), ch_planes[0])
            a_im = Image.frombytes("L", (lw, lh), ch_planes[-1]) if -1 in ch_planes else Image.new("L", (lw, lh), 255)
            im = Image.merge("RGBA", (g_im, g_im, g_im, a_im))
        else:
            continue

        layers_out.append({
            "name": rec["name"],
            "x": rec["left"],
            "y": rec["top"],
            "w": lw,
            "h": lh,
            "op": rec["op"],
            "vis": rec["vis"],
            "blend": rec["blend"],
            "clip": rec["clip"],
            "png": _img_to_data_url(im),
        })

    if not layers_out:
        return {"ok": False, "error": "empty_layers"}
    return {
        "ok": True,
        "W": int(width),
        "H": int(height),
        "name": os.path.splitext(os.path.basename(path))[0],
        "layers": layers_out,
    }


def read_psd_layers(path: str) -> dict[str, Any]:
    """PSD dosyasini katmanli (yoksa duzlestirilmis tek katman) Kami Picture formatinda okur."""
    p = os.path.abspath(str(path or ""))
    if not p or not os.path.isfile(p):
        return {"ok": False, "error": "not_found"}

    # 1) psd-tools varsa onu kullan
    try:
        from psd_tools import PSDImage  # type: ignore

        psd = PSDImage.open(p)
        layers_out: list[dict[str, Any]] = []
        for layer in psd.descendants():
            if layer.is_group():
                continue
            im = layer.composite()
            if im is None or im.width <= 0 or im.height <= 0:
                continue
            if im.mode != "RGBA":
                im = im.convert("RGBA")
            layers_out.append({
                "name": layer.name or "Katman",
                "x": int(layer.left),
                "y": int(layer.top),
                "w": int(im.width),
                "h": int(im.height),
                "op": round(float(layer.opacity) / 255.0, 3),
                "vis": bool(layer.visible),
                "blend": "source-over",
                "clip": bool(getattr(layer, "clipping", False)),
                "png": _img_to_data_url(im),
            })
        if layers_out:
            return {
                "ok": True,
                "W": int(psd.width),
                "H": int(psd.height),
                "name": os.path.splitext(os.path.basename(p))[0],
                "layers": layers_out,
            }
    except Exception:
        pass

    # 2) Saf Python + Pillow katmanli PSD okuyucu
    try:
        res = _read_psd_native(p)
        if res.get("ok"):
            return res
    except Exception:
        pass

    # 3) Yedek: Pillow duzlestirilmis tek katman
    try:
        with Image.open(p) as im:
            rgba = im.convert("RGBA")
            return {
                "ok": True,
                "W": int(rgba.width),
                "H": int(rgba.height),
                "name": os.path.splitext(os.path.basename(p))[0],
                "layers": [{
                    "name": "Arka plan",
                    "x": 0,
                    "y": 0,
                    "w": int(rgba.width),
                    "h": int(rgba.height),
                    "op": 1.0,
                    "vis": True,
                    "blend": "source-over",
                    "clip": False,
                    "png": _img_to_data_url(rgba),
                }],
            }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:180]}
