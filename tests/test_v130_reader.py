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


def test_lens_table_from_words_and_values():
    from app.core.lens_tools import table_from_words, _cell_value, _num
    W = []
    rows = [["Ürün", "Adet", "Fiyat"], ["Kalem mavi", "3", "12,50"], ["Defter", "10", "1.250"]]
    for r, row in enumerate(rows):
        x = 10
        for c, cell in enumerate(row):
            for word in cell.split():
                W.append({"t": word, "x": x, "y": 20 + r * 30, "w": len(word) * 8, "h": 14})
                x += len(word) * 8 + 5
            x = 10 + (c + 1) * 200
    t = table_from_words(W)
    assert t == rows
    assert _cell_value("12,50") == 12.5 and _cell_value("1.250") == 1250 and _cell_value("Defter") == "Defter"
    assert _num("7.739,10 TL") == 7739.1 and _num("689") == 689


def test_lens_barcodes_qr(tmp_path):
    zx = pytest.importorskip("zxingcpp")
    from app.core.lens_tools import barcodes
    img = zx.write_barcode(zx.BarcodeFormat.QRCode, "https://kami.local/deneme", width=300, height=300)
    from PIL import Image
    p = tmp_path / "qr.png"
    Image.fromarray(img).save(p) if not hasattr(img, "save") else img.save(p)
    r = barcodes(str(p))
    assert r["codes"] and r["codes"][0]["text"] == "https://kami.local/deneme" and r["codes"][0]["kind"] == "url"


def test_price_search_filters_and_sorts(monkeypatch):
    from app.core import lens_tools as lt
    monkeypatch.setattr(lt, "akakce", lambda q, n: [{"src": "Akakçe", "name": "Logitech G102 Lightsync Mouse", "price": 720.0, "url": "u1", "img": "", "note": ""},
                                                    {"src": "Akakçe", "name": "Mouse pad kırmızı", "price": 50.0, "url": "u2", "img": "", "note": ""}])
    monkeypatch.setattr(lt, "trendyol", lambda q, n: [{"src": "Trendyol", "name": "Logitech G G102 Lightsync RGB Oyuncu Mouse", "price": 689.0, "url": "u3", "img": "", "note": ""}])
    r = lt.price_search("logitech g102 lightsync")
    assert [i["url"] for i in r["items"]] == ["u3", "u1"] and r["min"] == 689.0
    assert lt.product_query({"tags": ["kablosuz mouse"], "sites": [{"title": "Logitech G102 fiyatı - Akakçe"}, {"title": "Logitech G102 Lightsync | Trendyol"}]}) == "logitech g102"
