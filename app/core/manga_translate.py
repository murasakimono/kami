"""Faz 15.2 — Kami Manga Cevirici: Konusma balonu tespiti, inpaint & Turkce TrueType dizgi."""
from __future__ import annotations

import logging
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Any, Callable

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

log = logging.getLogger(__name__)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_TTF_CANDIDATES = (
    Path(r"C:\Windows\Fonts\arial.ttf"),
    Path(r"C:\Windows\Fonts\segoeui.ttf"),
    Path(r"C:\Windows\Fonts\calibri.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
)


def _find_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for fp in _TTF_CANDIDATES:
        if fp.is_file():
            try:
                return ImageFont.truetype(str(fp), size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def _translate_ollama_or_keep(text: str, target_lang: str, ollama_ready: bool) -> str:
    clean = (text or "").strip()
    if not clean or not ollama_ready:
        return clean
    try:
        r = requests.post(
            "http://127.0.0.1:11434/api/generate",
            json={
                "model": "qwen2.5:7b",
                "prompt": f"Su manga konusma balonunu dogal {target_lang} diline cevir, sadece ceviri metnini dondur:\n{clean}",
                "stream": False,
            },
            timeout=20,
        )
        if r.status_code == 200:
            out = (r.json().get("response") or "").strip()
            if out:
                return out
    except Exception:
        pass
    return clean


def _sample_border_color(arr: np.ndarray, x1: int, y1: int, x2: int, y2: int) -> tuple[int, int, int]:
    h, w, _ = arr.shape
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w - 1, x2), min(h - 1, y2)
    ring = np.concatenate([arr[y1, x1:x2 + 1], arr[y2, x1:x2 + 1]], axis=0)
    if len(ring) == 0:
        return (255, 255, 255)
    med = np.median(ring, axis=0).astype(int)
    return (int(med[0]), int(med[1]), int(med[2]))


def _draw_wrapped_text(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, fg: tuple[int, int, int] = (15, 15, 20)) -> None:
    x1, y1, x2, y2 = box
    bw = max(20, x2 - x1)
    bh = max(20, y2 - y1)
    font_size = max(11, min(28, int(bh * 0.24)))
    font = _find_font(font_size)
    chars_per_line = max(6, int(bw / max(6, font_size * 0.58)))
    wrapped = "\n".join(textwrap.wrap(text, width=chars_per_line)) or text
    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, align="center")
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = x1 + max(0, (bw - tw) // 2)
    ty = y1 + max(0, (bh - th) // 2)
    draw.multiline_text((tx, ty), wrapped, fill=fg, font=font, align="center")


def translate_manga_page(
    image_path: str | Path,
    out_path: str | Path = "",
    *,
    target_lang: str = "tr",
    regions: list[dict[str, Any]] | None = None,
    translate_fn: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """Manga sayfasini cevirir: manga-image-translator varsa onu, yoksa balon temizleme + Turkce dizgi uygular."""
    p = Path(image_path)
    if not p.is_file():
        return {"ok": False, "error": "Manga gorseli bulunamadi"}
    dst = Path(out_path) if out_path else p.with_name(f"{p.stem}_{target_lang}.png")
    dst.parent.mkdir(parents=True, exist_ok=True)

    # 1) Harici manga-image-translator CLI varsa ve ozel regions verilmediyse onu dene
    if regions is None:
        mit = shutil.which("manga-image-translator") or shutil.which("manga_translator")
        if mit:
            try:
                r = subprocess.run(
                    [mit, "-i", str(p), "-o", str(dst.parent), "-l", target_lang.upper()],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180, creationflags=NO_WINDOW,
                )
                if r.returncode == 0 and dst.is_file():
                    return {"ok": True, "path": str(dst), "engine": "manga_image_translator", "bubbles": 1}
            except Exception:
                pass

    with Image.open(p) as raw_im:
        im = ImageOps.exif_transpose(raw_im).convert("RGB")
    arr = np.asarray(im, dtype=np.uint8)
    w, h = im.size

    work_regions = list(regions or [])
    if not work_regions:
        # Yerlesik balon tespiti yok: sayfanin tum metnini rastgele bir kutuya basmak cizimi kapatir.
        # Metni yalnizca okuyup dondur; sayfa ancak balon kutulari (regions) verilince ya da
        # manga-image-translator kuruluyken degistirilir.
        text = ""
        try:
            from app.core import ocr
            text = str(ocr.read_text(str(p), lang="ja").get("text") or "")
        except Exception:
            pass
        return {"ok": False, "engine": "builtin", "bubbles": 0, "ocr_text": text,
                "error": "Balon tespiti icin manga-image-translator gerekli ya da balon kutulari secilmeli"}

    ollama_ready = False
    if translate_fn is None:
        try:
            ollama_ready = requests.get("http://127.0.0.1:11434/api/tags", timeout=1.0).status_code == 200
        except Exception:
            ollama_ready = False

    draw = ImageDraw.Draw(im)
    translated_items: list[dict[str, Any]] = []
    for reg in work_regions:
        bbox = reg.get("bbox") or [0, 0, w // 2, h // 4]
        x1, y1, x2, y2 = [int(v) for v in bbox[:4]]
        src_txt = str(reg.get("text") or "").strip()
        tr_txt = str(reg.get("translated") or "").strip()
        if not tr_txt:
            tr_txt = translate_fn(src_txt) if translate_fn else _translate_ollama_or_keep(src_txt, target_lang, ollama_ready)

        bg = _sample_border_color(arr, x1, y1, x2, y2)
        luma = 0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]
        fg = (15, 15, 20) if luma >= 128 else (245, 245, 250)
        draw.rectangle([x1, y1, x2, y2], fill=bg)
        _draw_wrapped_text(draw, (x1 + 4, y1 + 4, x2 - 4, y2 - 4), tr_txt, fg=fg)
        translated_items.append({"bbox": [x1, y1, x2, y2], "source": src_txt, "translated": tr_txt})

    im.save(dst)
    return {"ok": True, "path": str(dst), "engine": "builtin", "bubbles": len(translated_items), "items": translated_items}
