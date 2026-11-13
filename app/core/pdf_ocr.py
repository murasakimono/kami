"""Kami PDF OCR: pypdfium2 + TrueType font ile taranmis PDF sayfalarina Turkce aranabilir gorunmez metin katmani gomer."""
from __future__ import annotations

import base64
import ctypes
from io import BytesIO
from pathlib import Path
from typing import Any

from app.core import ocr

_TTF_CANDIDATES = (
    Path(r"C:\Windows\Fonts\arial.ttf"),
    Path(r"C:\Windows\Fonts\segoeui.ttf"),
    Path(r"C:\Windows\Fonts\calibri.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
)


def _find_ttf() -> Path | None:
    for p in _TTF_CANDIDATES:
        if p.is_file():
            return p
    return None


def make_searchable_pdf(src_pdf: str, *, lang: str = "", ctx: Any = None) -> dict[str, Any]:
    p = Path(src_pdf)
    if not p.is_file() or p.suffix.lower() != ".pdf":
        return {"ok": False, "error": "Geçerli bir PDF dosyası seçin"}
    try:
        import pypdfium2 as pdfium
        import pypdfium2.raw as pdf_raw
    except ImportError as exc:
        return {"ok": False, "error": f"PDF kütüphanesi eksik: {exc}"}

    ttf_path = _find_ttf()
    if ttf_path is None:
        return {"ok": False, "error": "Türkçe destekli sistem yazı tipi (Arial/DejaVuSans) bulunamadı"}

    out = p.with_name(f"{p.stem}_ocr.pdf")
    pdf_doc = pdfium.PdfDocument(str(p))
    total = len(pdf_doc)
    pages_ocr = 0
    font_bytes = ttf_path.read_bytes()
    font_buf = (ctypes.c_uint8 * len(font_bytes)).from_buffer_copy(font_bytes)
    font = pdf_raw.FPDFText_LoadFont(pdf_doc.raw, font_buf, len(font_bytes), pdf_raw.FPDF_FONT_TRUETYPE, True)
    try:
        for i in range(total):
            if ctx and ctx.cancelled.is_set():
                return {"ok": False, "error": "İptal edildi"}
            if ctx:
                ctx.set(int(100 * i / max(1, total)), f"PDF OCR ({i + 1}/{total})...")
            page = pdf_doc[i]
            existing = (page.get_textpage().get_text_range() or "").strip()
            if not existing:
                pil_im = page.render(scale=2.0).to_pil()
                buf = BytesIO()
                pil_im.save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                res = ocr.recognize(b64, lang=lang)
                txt = " ".join(str(res.get("text") or "").split())[:4000] if res.get("ok") else ""
                if txt:
                    obj = pdf_raw.FPDFPageObj_CreateTextObj(pdf_doc.raw, font, 8.0)
                    wide = txt.encode("utf-16-le") + b"\x00\x00"
                    pdf_raw.FPDFText_SetText(obj, ctypes.cast(ctypes.c_char_p(wide), pdf_raw.FPDF_WIDESTRING))
                    pdf_raw.FPDFTextObj_SetTextRenderMode(obj, 3)  # gorunmez metin
                    pdf_raw.FPDFPage_InsertObject(page.raw, obj)
                    pdf_raw.FPDFPage_GenerateContent(page.raw)
                    pages_ocr += 1
        pdf_doc.save(str(out))
    finally:
        if font:
            pdf_raw.FPDFFont_Close(font)
        pdf_doc.close()
    return {"ok": True, "out": str(out), "pages_ocr": pages_ocr, "total_pages": total}
