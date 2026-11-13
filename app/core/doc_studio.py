"""Faz 15.1 — Evrensel Belge Donusturucu (PyMuPDF4LLM / Marker / pypdfium2 -> Markdown & Pandoc).

Mevcut pdf_ocr.py (Turkce aranabilir PDF) korunur; bu modul metin/tablo cikarma ve bicim donusumu saglar.
"""
from __future__ import annotations

import html
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def pdf_to_markdown(src_pdf: str | Path, out_md: str | Path = "") -> dict[str, Any]:
    """PDF'i Markdown'a cevirir (PyMuPDF4LLM -> Marker -> pypdfium2 yerlesik yedek)."""
    p = Path(src_pdf)
    if not p.is_file() or p.suffix.lower() != ".pdf":
        return {"ok": False, "error": "Gecerli bir PDF dosyasi secin"}

    dst = Path(out_md) if out_md else p.with_suffix(".md")
    dst.parent.mkdir(parents=True, exist_ok=True)

    try:
        import pymupdf4llm
        md_text = pymupdf4llm.to_markdown(str(p))
        dst.write_text(md_text, encoding="utf-8")
        return {"ok": True, "path": str(dst), "engine": "pymupdf4llm", "chars": len(md_text)}
    except Exception:
        pass

    marker = shutil.which("marker_single") or shutil.which("marker_single.exe")
    if marker:
        try:
            r = subprocess.run(
                [marker, str(p), str(dst.parent)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, creationflags=NO_WINDOW,
            )
            cand = dst.parent / p.stem / f"{p.stem}.md"
            if r.returncode == 0 and cand.is_file():
                md_text = cand.read_text(encoding="utf-8", errors="replace")
                dst.write_text(md_text, encoding="utf-8")
                return {"ok": True, "path": str(dst), "engine": "marker", "chars": len(md_text)}
        except Exception:
            pass

    try:
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(str(p))
        parts: list[str] = [f"# {p.stem}\n"]
        for i in range(len(doc)):
            page = doc[i]
            tp = page.get_textpage()
            txt = (tp.get_text_range() or "").strip()
            tp.close()
            page.close()
            if txt:
                parts.append(f"## Sayfa {i + 1}\n\n{txt}\n")
        doc.close()
        md_text = "\n".join(parts)
        dst.write_text(md_text, encoding="utf-8")
        return {"ok": True, "path": str(dst), "engine": "pypdfium2", "chars": len(md_text)}
    except Exception as exc:
        return {"ok": False, "error": f"PDF okunamadi: {exc}"}


def _md_to_html_builtin(md_text: str, title: str) -> str:
    lines_out: list[str] = []
    for raw in md_text.splitlines():
        s = raw.strip()
        if s.startswith("### "):
            lines_out.append(f"<h3>{html.escape(s[4:])}</h3>")
        elif s.startswith("## "):
            lines_out.append(f"<h2>{html.escape(s[3:])}</h2>")
        elif s.startswith("# "):
            lines_out.append(f"<h1>{html.escape(s[2:])}</h1>")
        elif s.startswith("- ") or s.startswith("* "):
            lines_out.append(f"<li>{html.escape(s[2:])}</li>")
        elif s:
            lines_out.append(f"<p>{html.escape(s)}</p>")
    return (
        f"<!doctype html><html lang='tr'><head><meta charset='utf-8'><title>{html.escape(title)}</title></head>"
        f"<body>\n{chr(10).join(lines_out)}\n</body></html>"
    )


def convert_document(src_path: str | Path, target_format: str = "html", out_path: str | Path = "") -> dict[str, Any]:
    """Belgeleri MD / DOCX / EPUB / LaTeX / HTML arasinda donusturur (Pandoc + yerlesik MD->HTML)."""
    p = Path(src_path)
    if not p.is_file():
        return {"ok": False, "error": "Kaynak belge bulunamadi"}
    fmt = (target_format or "html").strip().lower().lstrip(".")
    ext = "tex" if fmt == "latex" else fmt
    dst = Path(out_path) if out_path else p.with_suffix(f".{ext}")
    if dst.resolve() == p.resolve():
        # Kaynak belgenin uzerine yazmayi onle
        dst = p.with_name(f"{p.stem}_donusturuldu.{ext}")
    dst.parent.mkdir(parents=True, exist_ok=True)

    pandoc = shutil.which("pandoc") or shutil.which("pandoc.exe")
    if pandoc:
        try:
            r = subprocess.run(
                [pandoc, str(p), "-t", fmt, "-o", str(dst)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, creationflags=NO_WINDOW,
            )
            if r.returncode == 0 and dst.is_file():
                return {"ok": True, "path": str(dst), "engine": "pandoc", "format": fmt}
        except Exception:
            pass

    if fmt in ("html", "htm") and p.suffix.lower() in (".md", ".markdown", ".txt"):
        body = _md_to_html_builtin(p.read_text(encoding="utf-8", errors="replace"), p.stem)
        dst.write_text(body, encoding="utf-8")
        return {"ok": True, "path": str(dst), "engine": "builtin_html", "format": fmt}

    if fmt == "txt":
        raw = p.read_text(encoding="utf-8", errors="replace")
        plain = re.sub(r"<[^>]+>", "", raw)
        dst.write_text(plain, encoding="utf-8")
        return {"ok": True, "path": str(dst), "engine": "builtin_txt", "format": fmt}

    return {"ok": False, "error": f"'{fmt}' donusumu icin Pandoc kurulu degil"}
