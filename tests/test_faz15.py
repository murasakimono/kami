"""Faz 15 testleri: PDF -> Markdown, Pandoc/HTML belge donusumu & Kami Manga balon cevirisi."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from app.core import doc_studio, manga_translate


def test_pdf_to_markdown_and_md_to_html(tmp_path: Path):
    # Basit bir PDF uret (Pillow ile 1 sayfalik PDF)
    pdf_path = tmp_path / "ornek.pdf"
    img = Image.new("RGB", (400, 200), (255, 255, 255))
    img.save(pdf_path, "PDF")

    md_res = doc_studio.pdf_to_markdown(pdf_path, tmp_path / "ornek.md")
    assert md_res["ok"] is True
    assert Path(md_res["path"]).is_file()

    md_file = tmp_path / "notlar.md"
    md_file.write_text("# Baslik\n\nMerhaba **Kami**\n- Madde 1\n", encoding="utf-8")
    html_res = doc_studio.convert_document(md_file, target_format="html")
    assert html_res["ok"] is True
    html_text = Path(html_res["path"]).read_text(encoding="utf-8")
    assert "<h1>Baslik</h1>" in html_text
    assert "<li>Madde 1</li>" in html_text


def test_manga_translate_page_inpaint_and_typeset(tmp_path: Path):
    page = tmp_path / "manga_p1.png"
    im = Image.new("RGB", (400, 400), (250, 250, 250))
    draw = ImageDraw.Draw(im)
    draw.ellipse([60, 40, 340, 180], outline=(10, 10, 10), fill=(255, 255, 255), width=3)
    draw.text((130, 95), "HELLO!", fill=(10, 10, 10))
    im.save(page)

    out_page = tmp_path / "manga_p1_tr.png"
    res = manga_translate.translate_manga_page(
        page,
        out_page,
        target_lang="tr",
        regions=[{"bbox": [90, 65, 310, 155], "text": "HELLO!"}],
        translate_fn=lambda _s: "MERHABA!",
    )
    assert res["ok"] is True
    assert res["bubbles"] == 1
    assert out_page.is_file()
    assert res["items"][0]["translated"] == "MERHABA!"


def test_convert_document_same_extension_safety(tmp_path):
    from pathlib import Path
    from app.core import doc_studio

    src = tmp_path / "notlar.txt"
    src.write_text("<p>Merhaba</p>", encoding="utf-8")
    res = doc_studio.convert_document(src, "txt")
    assert res["ok"] is True
    out_p = tmp_path / "notlar_donusturuldu.txt"
    assert out_p.is_file()
    assert Path(res["path"]).resolve() == out_p.resolve()
    assert src.read_text(encoding="utf-8") == "<p>Merhaba</p>"
