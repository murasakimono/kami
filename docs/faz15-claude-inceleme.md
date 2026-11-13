# Faz 15 — Claude İnceleme Özeti

## Kapsam
Mevcut `pdf_ocr.py` (Türkçe aranabilir PDF katmanı) ve `ocr.py` korunarak şu modüller eklendi:

1. **15.1 Evrensel Belge Dönüştürücü (`app/core/doc_studio.py`):**
   - `pdf_to_markdown()`: `pymupdf4llm` → `marker_single` → `pypdfium2` sayfa bazlı Markdown yedek zinciri.
   - `convert_document()`: `pandoc` CLI (`MD ↔ DOCX ↔ EPUB ↔ LaTeX ↔ HTML`) + Pandoc yokken yerleşik `MD → HTML` ve `TXT` dönüştürücü.

2. **15.2 `Kami Manga` Çevirici (`app/core/manga_translate.py`):**
   - `translate_manga_page()`: `manga-image-translator` CLI varsa onu, yoksa `ocr.py` + yerel `Ollama qwen2.5:7b` (veya özel çeviri callback'i) + balon çevresi renk örnekleme (`_sample_border_color`) + Türkçe TrueType (`arial.ttf`/`DejaVuSans.ttf`) otomatik satır kırmalı dizgi.

3. **API & Testler (`app/ui/api.py`, `tests/test_faz15.py`):**
   - `doc_pdf_to_markdown`, `doc_convert`, `manga_translate_page`.
   - `pytest tests/test_faz7.py .. tests/test_faz15.py`: **31/31 passed**.
