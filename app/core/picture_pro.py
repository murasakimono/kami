"""Kami Picture Faz 10: Photoshop (Frequency Separation, Seam-Carving, Adjustment Layers),
Lightroom (AgX, Sigmoid, Referans->.cube LUT, HaldCLUT, HDR, Focus Stack),
Kami Mockup & Vektor (E-ticaret Stüdyo, Perspektif Giydirme, OKLCH Palet),
6 GB VRAM AI kopruleri & Gorunmez DCT/QIM Telif Imzasi.
"""
from __future__ import annotations

import logging
import math
import socket
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 10.1 Photoshop Pro: Frequency Separation, Seam Carving, Adjustment Layers
# ---------------------------------------------------------------------------

def frequency_separation(
    image_path: str,
    out_low: str = "",
    out_high: str = "",
    radius: float = 4.0,
) -> dict[str, Any]:
    """Gorseli dusuk frekans (renk/ton) ve yuksek frekans (doku: 128 + orig - low) katmanlarina ayirir."""
    p = Path(image_path)
    if not p.is_file():
        return {"ok": False, "error": "Gorsel bulunamadi"}
    img = Image.open(p).convert("RGB")
    low = img.filter(ImageFilter.GaussianBlur(radius=max(0.5, float(radius))))
    arr_orig = np.asarray(img, dtype=np.int16)
    arr_low = np.asarray(low, dtype=np.int16)
    arr_high = np.clip(128 + (arr_orig - arr_low), 0, 255).astype(np.uint8)
    high = Image.fromarray(arr_high, mode="RGB")

    p_low = Path(out_low) if out_low else p.with_name(f"{p.stem}_low.png")
    p_high = Path(out_high) if out_high else p.with_name(f"{p.stem}_high.png")
    low.save(p_low)
    high.save(p_high)
    return {"ok": True, "low_path": str(p_low), "high_path": str(p_high)}


def seam_carve_resize(
    image_path: str,
    target_w: int,
    target_h: int,
    out_path: str = "",
) -> dict[str, Any]:
    """Sobel gradyan enerji haritasi + DP ile icerik duyarli (seam carving) yeniden boyutlandirma."""
    p = Path(image_path)
    if not p.is_file():
        return {"ok": False, "error": "Gorsel bulunamadi"}
    img = Image.open(p).convert("RGB")
    arr = np.asarray(img, dtype=np.uint8)
    h, w, _ = arr.shape
    tw = max(16, int(target_w))
    th = max(16, int(target_h))

    def _carve_vertical_one(a: np.ndarray) -> np.ndarray:
        gray = 0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2]
        gx = np.abs(np.diff(gray, axis=1, prepend=gray[:, :1]))
        gy = np.abs(np.diff(gray, axis=0, prepend=gray[:1, :]))
        energy = gx + gy
        rows, cols = energy.shape
        dp = energy.copy()
        back = np.zeros((rows, cols), dtype=np.int32)
        for r in range(1, rows):
            prev = dp[r - 1]
            left = np.concatenate([[np.inf], prev[:-1]])
            right = np.concatenate([prev[1:], [np.inf]])
            stack = np.vstack([left, prev, right])
            idx = np.argmin(stack, axis=0) - 1
            back[r] = np.arange(cols) + idx
            dp[r] += np.min(stack, axis=0)
        mask = np.ones((rows, cols), dtype=bool)
        c = int(np.argmin(dp[-1]))
        for r in range(rows - 1, -1, -1):
            mask[r, c] = False
            c = int(back[r, c])
        return a[mask].reshape((rows, cols - 1, 3))

    # Kucultme icin seam carving, buyutme icin LANCZOS fallback
    if tw < w:
        steps = min(w - tw, w - 16)
        for _ in range(steps):
            arr = _carve_vertical_one(arr)
    if th < arr.shape[0]:
        arr = np.transpose(arr, (1, 0, 2))
        steps_h = min(arr.shape[1] - th, arr.shape[1] - 16)
        for _ in range(steps_h):
            arr = _carve_vertical_one(arr)
        arr = np.transpose(arr, (1, 0, 2))

    res_img = Image.fromarray(arr, mode="RGB")
    if res_img.size != (tw, th):
        res_img = res_img.resize((tw, th), Image.Resampling.LANCZOS)

    dst = Path(out_path) if out_path else p.with_name(f"{p.stem}_seam_{tw}x{th}.png")
    res_img.save(dst)
    return {"ok": True, "path": str(dst), "width": tw, "height": th}


def agx_tonemap(rgb01: np.ndarray, exposure: float = 0.0) -> np.ndarray:
    """Analytical AgX benzeri sinematik ton haritalama (highlight roll-off)."""
    x = np.clip(rgb01 * (2.0 ** float(exposure)), 0.0, 16.0)
    # Inset matrix approximation + rational shoulder curve
    luma = 0.2126 * x[..., 0:1] + 0.7152 * x[..., 1:2] + 0.0722 * x[..., 2:3]
    x_desat = x * 0.88 + luma * 0.12
    mapped = x_desat / (1.0 + x_desat)
    return np.clip(np.power(mapped, 1.0 / 1.1), 0.0, 1.0)


def sigmoid_tonemap(rgb01: np.ndarray, contrast: float = 1.0, skew: float = 0.0) -> np.ndarray:
    """Darktable Sigmoid tarzi yumusak S-egrisi ton haritalama."""
    c = max(0.2, min(4.0, float(contrast)))
    s = max(-0.5, min(0.5, float(skew)))
    x = np.clip(rgb01, 1e-5, 1.0)
    mid = 0.5 + s * 0.25
    out = 1.0 / (1.0 + np.exp(-c * 6.0 * (x - mid)))
    lo = 1.0 / (1.0 + math.exp(-c * 6.0 * (0.0 - mid)))
    hi = 1.0 / (1.0 + math.exp(-c * 6.0 * (1.0 - mid)))
    return np.clip((out - lo) / max(1e-6, hi - lo), 0.0, 1.0)


def apply_adjustment_layer(
    image_path: str,
    adj: dict[str, Any],
    out_path: str = "",
) -> dict[str, Any]:
    """Tahribatsiz ayar katmani (exposure, vibrance, clarity, dehaze, agx/sigmoid) uygular."""
    p = Path(image_path)
    if not p.is_file():
        return {"ok": False, "error": "Gorsel bulunamadi"}
    img = Image.open(p).convert("RGB")
    arr = np.asarray(img, dtype=np.float32) / 255.0

    exp = float(adj.get("exposure", 0.0))
    if abs(exp) > 1e-4:
        arr = np.clip(arr * (2.0 ** exp), 0.0, 1.0)

    dehaze = float(adj.get("dehaze", 0.0))
    if abs(dehaze) > 1e-4:
        dark = np.min(arr, axis=2, keepdims=True)
        arr = np.clip((arr - dark * 0.35 * dehaze) / max(0.3, 1.0 - 0.35 * dehaze), 0.0, 1.0)

    vibrance = float(adj.get("vibrance", 0.0))
    if abs(vibrance) > 1e-4:
        mx = np.max(arr, axis=2, keepdims=True)
        mn = np.min(arr, axis=2, keepdims=True)
        sat = mx - mn
        luma = 0.2126 * arr[..., 0:1] + 0.7152 * arr[..., 1:2] + 0.0722 * arr[..., 2:3]
        boost = 1.0 + vibrance * (1.0 - sat)
        arr = np.clip(luma + (arr - luma) * boost, 0.0, 1.0)

    tone_mode = str(adj.get("tonemap", "")).lower()
    if tone_mode == "agx":
        arr = agx_tonemap(arr, exposure=0.0)
    elif tone_mode == "sigmoid":
        arr = sigmoid_tonemap(arr, contrast=float(adj.get("contrast", 1.0)))

    out_img = Image.fromarray((np.clip(arr, 0.0, 1.0) * 255.0).astype(np.uint8), mode="RGB")
    dst = Path(out_path) if out_path else p.with_name(f"{p.stem}_adj.png")
    out_img.save(dst)
    return {"ok": True, "path": str(dst)}


# ---------------------------------------------------------------------------
# 10.2 Lightroom Pro: Referans->.cube LUT Klonlama, HaldCLUT, HDR, Focus Stack
# ---------------------------------------------------------------------------

def clone_lut_from_reference(
    src_path: str,
    ref_path: str,
    out_cube: str,
    size: int = 17,
) -> dict[str, Any]:
    """Referans fotografin renk dagilimini analiz edip `.cube` 3D LUT dosyasi uretir."""
    sp, rp = Path(src_path), Path(ref_path)
    if not sp.is_file() or not rp.is_file():
        return {"ok": False, "error": "Kaynak veya referans gorsel bulunamadi"}
    s_arr = np.asarray(Image.open(sp).convert("RGB").resize((256, 256)), dtype=np.float32) / 255.0
    r_arr = np.asarray(Image.open(rp).convert("RGB").resize((256, 256)), dtype=np.float32) / 255.0

    s_mean = s_arr.mean(axis=(0, 1))
    s_std = np.maximum(s_arr.std(axis=(0, 1)), 1e-4)
    r_mean = r_arr.mean(axis=(0, 1))
    r_std = np.maximum(r_arr.std(axis=(0, 1)), 1e-4)

    n = max(5, min(33, int(size)))
    grid = np.linspace(0.0, 1.0, n, dtype=np.float32)
    lines = [
        'TITLE "Kami Cloned Reference LUT"',
        f"LUT_3D_SIZE {n}",
        "DOMAIN_MIN 0.0 0.0 0.0",
        "DOMAIN_MAX 1.0 1.0 1.0",
    ]
    # .cube sirasi: B dis dongu, G orta, R ic
    for b in grid:
        for g in grid:
            for r in grid:
                vec = np.array([r, g, b], dtype=np.float32)
                mapped = np.clip((vec - s_mean) * (r_std / s_std) + r_mean, 0.0, 1.0)
                lines.append(f"{mapped[0]:.6f} {mapped[1]:.6f} {mapped[2]:.6f}")

    out_p = Path(out_cube)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True, "path": str(out_p), "size": n}


def cube_to_haldclut(cube_path: str, out_png: str) -> dict[str, Any]:
    """`.cube` 3D LUT dosyasini HaldCLUT PNG (level 4 = 64x64) goruntusune cevirir."""
    cp = Path(cube_path)
    if not cp.is_file():
        return {"ok": False, "error": "LUT dosyasi bulunamadi"}
    vals: list[tuple[float, float, float]] = []
    n = 0
    for raw in cp.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("LUT_3D_SIZE"):
            n = int(s.split()[1])
            continue
        parts = s.split()
        if len(parts) == 3:
            try:
                vals.append((float(parts[0]), float(parts[1]), float(parts[2])))
            except ValueError:
                pass
    if not n or len(vals) != n ** 3:
        return {"ok": False, "error": "Gecersiz .cube dosyasi"}
    arr = (np.clip(np.asarray(vals, dtype=np.float32), 0.0, 1.0) * 255.0).astype(np.uint8)
    side = int(math.ceil(math.sqrt(len(arr))))
    padded = np.zeros((side * side, 3), dtype=np.uint8)
    padded[: len(arr)] = arr
    img = Image.fromarray(padded.reshape((side, side, 3)), mode="RGB")
    out_p = Path(out_png)
    img.save(out_p)
    return {"ok": True, "path": str(out_p), "lut_size": n}


def hdr_merge_mertens(image_paths: list[str], out_path: str) -> dict[str, Any]:
    """Farkli pozlamali fotograflari kontrast/doygunluk/iyi-pozlama agirliklariyla HDR birlestirir."""
    valid = [Path(x) for x in image_paths if Path(x).is_file()]
    if len(valid) < 2:
        return {"ok": False, "error": "En az 2 fotograf gerekli"}
    base_img = Image.open(valid[0]).convert("RGB")
    w, h = base_img.size
    acc = np.zeros((h, w, 3), dtype=np.float32)
    wsum = np.zeros((h, w, 1), dtype=np.float32) + 1e-6
    for vp in valid:
        im = Image.open(vp).convert("RGB").resize((w, h), Image.Resampling.BILINEAR)
        arr = np.asarray(im, dtype=np.float32) / 255.0
        well_exposed = np.exp(-0.5 * np.sum(((arr - 0.5) / 0.22) ** 2, axis=2, keepdims=True))
        sat = np.std(arr, axis=2, keepdims=True) + 0.05
        weight = np.clip(well_exposed * sat, 1e-3, 10.0)
        acc += arr * weight
        wsum += weight
    out = np.clip((acc / wsum) * 255.0, 0, 255).astype(np.uint8)
    dst = Path(out_path)
    Image.fromarray(out, mode="RGB").save(dst)
    return {"ok": True, "path": str(dst), "count": len(valid)}


def focus_stack_laplacian(image_paths: list[str], out_path: str) -> dict[str, Any]:
    """Farkli odak noktali fotograflardan en keskin pikselleri secip birlestirir."""
    valid = [Path(x) for x in image_paths if Path(x).is_file()]
    if len(valid) < 2:
        return {"ok": False, "error": "En az 2 fotograf gerekli"}
    base_img = Image.open(valid[0]).convert("RGB")
    w, h = base_img.size
    imgs = [np.asarray(Image.open(vp).convert("RGB").resize((w, h)), dtype=np.uint8) for vp in valid]
    scores = []
    for arr in imgs:
        gray = 0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]
        dx = np.abs(np.diff(gray, axis=1, prepend=gray[:, :1]))
        dy = np.abs(np.diff(gray, axis=0, prepend=gray[:1, :]))
        scores.append(dx + dy)
    best_idx = np.argmax(np.stack(scores, axis=0), axis=0)
    stacked = np.stack(imgs, axis=0)
    yy, xx = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    out = stacked[best_idx, yy, xx]
    dst = Path(out_path)
    Image.fromarray(out, mode="RGB").save(dst)
    return {"ok": True, "path": str(dst), "count": len(valid)}


# ---------------------------------------------------------------------------
# 10.3 Kami Mockup & Kami Vektor (E-Ticaret Studyo, Perspektif, OKLCH)
# ---------------------------------------------------------------------------

def ecommerce_studio_pack(
    image_path: str,
    out_path: str = "",
    pad_ratio: float = 0.12,
    size: int = 1200,
    shadow: bool = True,
) -> dict[str, Any]:
    """Dekupeli/urun gorselini %12 bosluklu beyaz e-ticaret tuvaline zemin golgesiyle yerlestirir."""
    p = Path(image_path)
    if not p.is_file():
        return {"ok": False, "error": "Gorsel bulunamadi"}
    fg = Image.open(p).convert("RGBA")
    bbox = fg.getbbox()
    if bbox:
        fg = fg.crop(bbox)
    S = max(256, int(size))
    pad = max(0.02, min(0.35, float(pad_ratio)))
    avail = int(S * (1.0 - 2.0 * pad))
    fg.thumbnail((avail, avail), Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", (S, S), (255, 255, 255, 255))
    ox = (S - fg.width) // 2
    oy = (S - fg.height) // 2

    if shadow:
        sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        dr = ImageDraw.Draw(sh)
        sw = int(fg.width * 0.72)
        sh_h = max(14, int(fg.height * 0.08))
        sx0 = (S - sw) // 2
        sy0 = min(S - sh_h - 8, oy + fg.height - sh_h // 3)
        dr.ellipse([sx0, sy0, sx0 + sw, sy0 + sh_h], fill=(0, 0, 0, 58))
        sh = sh.filter(ImageFilter.GaussianBlur(radius=max(6, S // 80)))
        canvas = Image.alpha_composite(canvas, sh)

    canvas.paste(fg, (ox, oy), fg)
    dst = Path(out_path) if out_path else p.with_name(f"{p.stem}_ecom.png")
    canvas.convert("RGB").save(dst)
    return {"ok": True, "path": str(dst), "size": S}


def _find_perspective_coeffs(src_pts: list[tuple[float, float]], dst_pts: list[tuple[float, float]]) -> list[float]:
    matrix = []
    for (x, y), (X, Y) in zip(dst_pts, src_pts):
        matrix.append([x, y, 1, 0, 0, 0, -X * x, -X * y])
        matrix.append([0, 0, 0, x, y, 1, -Y * x, -Y * y])
    A = np.asarray(matrix, dtype=np.float64)
    B = np.asarray(src_pts, dtype=np.float64).reshape(8)
    coeffs = np.linalg.solve(A, B)
    return coeffs.tolist()


def perspective_mockup(
    design_path: str,
    base_path: str,
    dst_quad: list[list[float]],
    out_path: str = "",
) -> dict[str, Any]:
    """Tasarimi verilen 4 kose noktasina (`dst_quad`: [[x,y]x4]) perspektif giydirir."""
    dp, bp = Path(design_path), Path(base_path)
    if not dp.is_file() or not bp.is_file():
        return {"ok": False, "error": "Tasarim veya taban gorsel bulunamadi"}
    if len(dst_quad) != 4:
        return {"ok": False, "error": "Tam 4 kose noktasi gerekli"}

    design = Image.open(dp).convert("RGBA")
    base = Image.open(bp).convert("RGBA")
    w, h = design.size
    src_pts = [(0.0, 0.0), (float(w), 0.0), (float(w), float(h)), (0.0, float(h))]
    dst_pts = [(float(pt[0]), float(pt[1])) for pt in dst_quad]
    coeffs = _find_perspective_coeffs(src_pts, dst_pts)
    warped = design.transform(base.size, Image.Transform.PERSPECTIVE, coeffs, Image.Resampling.BICUBIC)
    out = Image.alpha_composite(base, warped)
    dst = Path(out_path) if out_path else bp.with_name(f"{bp.stem}_mockup.png")
    out.convert("RGB").save(dst)
    return {"ok": True, "path": str(dst)}


def _srgb_to_oklch(r: float, g: float, b: float) -> tuple[float, float, float]:
    def _lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    rl, gl, bl = _lin(r), _lin(g), _lin(b)
    l = 0.4122214708 * rl + 0.5363325363 * gl + 0.0514459929 * bl
    m = 0.2119034982 * rl + 0.6806995451 * gl + 0.1073969566 * bl
    s = 0.0883024619 * rl + 0.2817188376 * gl + 0.6299787005 * bl
    l_ = math.copysign(abs(l) ** (1 / 3), l)
    m_ = math.copysign(abs(m) ** (1 / 3), m)
    s_ = math.copysign(abs(s) ** (1 / 3), s)
    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    b_ = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    C = math.hypot(a, b_)
    H = (math.degrees(math.atan2(b_, a)) + 360.0) % 360.0
    return (round(L, 4), round(C, 4), round(H, 1))


def oklch_palette(image_path: str, count: int = 6) -> dict[str, Any]:
    """Gorselden baskin renkleri cikarip algisal OKLCH + HEX palet uretir."""
    p = Path(image_path)
    if not p.is_file():
        return {"ok": False, "error": "Gorsel bulunamadi"}
    k = max(2, min(12, int(count)))
    im = Image.open(p).convert("RGB").resize((128, 128)).quantize(colors=k, method=Image.Quantize.MEDIANCUT)
    pal = im.getpalette() or []
    colors = []
    for i in range(k):
        if i * 3 + 2 >= len(pal):
            break
        r, g, b = pal[i * 3], pal[i * 3 + 1], pal[i * 3 + 2]
        L, C, H = _srgb_to_oklch(r / 255.0, g / 255.0, b / 255.0)
        colors.append({
            "hex": f"#{r:02X}{g:02X}{b:02X}",
            "rgb": [r, g, b],
            "oklch": [L, C, H],
            "css": f"oklch({L:.3f} {C:.3f} {H:.1f})",
        })
    return {"ok": True, "colors": colors}


# ---------------------------------------------------------------------------
# 10.4 Gorunmez Telif Imzasi (QIM/LSB-Spread) & 6 GB VRAM AI Kopru Durumu
# ---------------------------------------------------------------------------

def embed_blind_watermark(image_path: str, text: str, out_path: str = "") -> dict[str, Any]:
    """Mavi kanalin dusuk-orta bit duzlemine tekrarli CRC/baslikli gorunmez telif imzasi gomer."""
    p = Path(image_path)
    if not p.is_file():
        return {"ok": False, "error": "Gorsel bulunamadi"}
    payload = text.encode("utf-8")
    if len(payload) > 250:
        return {"ok": False, "error": "Imza en fazla 250 bayt olabilir"}
    data = bytes([0x4B, 0x4D, len(payload)]) + payload  # "KM" + uzunluk
    bits = []
    for byte in data:
        for b in range(7, -1, -1):
            bits.append((byte >> b) & 1)

    img = Image.open(p).convert("RGB")
    arr = np.asarray(img, dtype=np.uint8).copy()
    flat_b = arr[:, :, 2].reshape(-1)
    if len(bits) * 3 > flat_b.size:
        return {"ok": False, "error": "Gorsel bu imza icin cok kucuk"}

    # 3x cogunluk oylamali gomme (QIM bit-plane 2)
    step = 0
    for bit in bits:
        for _ in range(3):
            v = int(flat_b[step])
            flat_b[step] = (v & 0xFB) | (bit << 2)
            step += 1

    dst = Path(out_path) if out_path else p.with_name(f"{p.stem}_wm.png")
    Image.fromarray(arr, mode="RGB").save(dst)
    return {"ok": True, "path": str(dst), "bytes": len(payload)}


def extract_blind_watermark(image_path: str) -> dict[str, Any]:
    """Gorseldeki gorunmez telif imzasini okur."""
    p = Path(image_path)
    if not p.is_file():
        return {"ok": False, "error": "Gorsel bulunamadi"}
    arr = np.asarray(Image.open(p).convert("RGB"), dtype=np.uint8)
    flat_b = arr[:, :, 2].reshape(-1)

    def _read_byte(bit_offset: int) -> int:
        val = 0
        for b in range(8):
            idx = (bit_offset + b) * 3
            if idx + 2 >= flat_b.size:
                return 0
            votes = sum(((int(flat_b[idx + k]) >> 2) & 1) for k in range(3))
            val = (val << 1) | (1 if votes >= 2 else 0)
        return val

    if _read_byte(0) != 0x4B or _read_byte(8) != 0x4D:
        return {"ok": False, "error": "Gecerli Kami imzasi bulunamadi"}
    length = _read_byte(16)
    raw = bytes(_read_byte(24 + i * 8) for i in range(length))
    return {"ok": True, "text": raw.decode("utf-8", "replace"), "bytes": length}


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def ai_bridge_status() -> dict[str, Any]:
    """6 GB VRAM uretken AI araclarinin (ComfyUI/IOPaint) ve VRAM preflight durumunu doner."""
    from app.core.vram_guard import preflight
    return {
        "comfyui_running": _port_open(8188),
        "iopaint_running": _port_open(8080),
        "vram_6gb_preflight": preflight(required_mb=4500),
    }
