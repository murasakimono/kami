"""v1.30 Reader: EPUB (PyMuPDF ile PDF'e dizme), okuma istatistigi, seri / yeni bolum takibi (klasor)."""
import datetime as dt
import json
import zipfile

import pytest


def _epub(path, chapters=3):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        items = "".join(f'<item id="c{i}" href="c{i}.xhtml" media-type="application/xhtml+xml"/>' for i in range(chapters))
        spine = "".join(f'<itemref idref="c{i}"/>' for i in range(chapters))
        z.writestr("OEBPS/content.opf", '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
                   '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Deneme Kitap</dc:title><dc:identifier id="id">x</dc:identifier><dc:language>tr</dc:language></metadata>'
                   f'<manifest>{items}</manifest><spine>{spine}</spine></package>')
        for i in range(chapters):
            body = "".join(f"<p>Bölüm {i} paragraf {k}: çalışkan öğrenci şimdi okuyor.</p>" for k in range(60))
            z.writestr(f"OEBPS/c{i}.xhtml", f'<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>c{i}</title></head><body><h1>Bölüm {i}</h1>{body}</body></html>')


def test_epub_opens_as_pdf_and_font_relayout(tmp_path, monkeypatch):
    pytest.importorskip("pymupdf")
    from app.core import reader
    monkeypatch.setattr(reader, "ROOT", tmp_path / "rd")
    p = tmp_path / "kitap.epub"
    _epub(p)
    d = reader.Doc(str(p))
    try:
        assert d.kind == "pdf" and d.ebook and d.count >= 3
        assert "öğrenci" in d.text(1)
        assert d.search("çalışkan")
        n_small = d.count
    finally:
        d.close()
    big = reader.ebook_pdf(str(p), font_size=18)
    import pypdfium2 as pdfium
    assert len(pdfium.PdfDocument(big)) > n_small        # buyuk punto -> daha cok sayfa


def test_stats_and_streak(tmp_path, monkeypatch):
    from app.core import reader
    monkeypatch.setattr(reader, "ROOT", tmp_path)
    t = dt.date.today()
    days = {(t - dt.timedelta(days=i)).isoformat(): 600 for i in range(3)}
    (tmp_path / "a.json").write_text(json.dumps({"title": "A", "page": 9, "count": 10, "stats": {"secs": 1800, "pages": 40, "days": days}}))
    (tmp_path / "b.json").write_text(json.dumps({"title": "B", "page": 1, "count": 10, "stats": {"secs": 300, "pages": 5, "days": {t.isoformat(): 300}}}))
    s = reader.stats()
    assert s["today"] == 900 and s["streak"] == 3 and s["pages"] == 45 and s["finished"] == 1 and len(s["days"]) == 14
    assert s["top"][0]["title"] == "A"


def test_series_folder_new_chapters(tmp_path, monkeypatch):
    from app.core import reader
    monkeypatch.setattr(reader, "ROOT", tmp_path / "rd")
    monkeypatch.setattr(reader, "SERIES_FILE", tmp_path / "rd" / "series.json")
    lib = tmp_path / "Seri"
    lib.mkdir()
    for n in (1, 2):
        zipfile.ZipFile(lib / f"Seri Chapter {n}.cbz", "w").close()
    r = reader.series_add(str(lib))
    assert r["ok"] and r["series"]["last_n"] == 2
    assert reader.series_check() == []
    zipfile.ZipFile(lib / "Seri Chapter 3.cbz", "w").close()
    found = reader.series_check()
    assert found and found[0]["new"][0]["n"] == 3
    s = reader.series_list()[0]
    assert s["new"] and s["last_n"] == 3
    reader.series_seen(s["id"])
    assert reader.series_list()[0]["new"] == []
    assert not reader.series_add("bos-sey")["ok"]
