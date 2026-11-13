import time
from io import BytesIO
from unittest.mock import MagicMock, patch

from PIL import Image

import app.core.ghost as ghost
import app.core.hardsub as hardsub
import app.core.jobs as jobs_mod
import app.core.kami_hunter as kami_hunter
import app.core.link_check as link_check
import app.core.phone as phone_mod


def test_job_manager_start_and_cancel():
    jm = jobs_mod.JobManager()

    def quick(ctx):
        ctx.set(50, "yarida")
        return {"ok": True, "val": 42}

    jid = jm.start("test", "Hızlı İş", quick)
    for _ in range(30):
        rec = jm.get(jid)
        if rec and rec["status"] == "done":
            break
        time.sleep(0.05)
    assert jm.get(jid)["status"] == "done"
    assert jm.get(jid)["result"]["val"] == 42

    def slow(ctx):
        while not ctx.cancelled.is_set():
            time.sleep(0.05)
        return {"ok": False}

    jid2 = jm.start("test", "Yavaş İş", slow)
    assert jm.cancel(jid2) is True
    for _ in range(30):
        rec2 = jm.get(jid2)
        if rec2 and rec2["status"] == "cancelled":
            break
        time.sleep(0.05)
    assert jm.get(jid2)["status"] == "cancelled"


def test_link_check_counts_alive_and_dead():
    def fake_head(url, **kwargs):
        r = MagicMock()
        if "good" in url:
            r.ok = True
            r.status_code = 200
            r.headers = {"Content-Length": "1048576"}
            r.url = url
        else:
            r.ok = False
            r.status_code = 404
            r.headers = {}
            r.url = url
        return r

    with patch("app.core.link_check.requests.head", side_effect=fake_head):
        res = link_check.check_links(["https://example.com/good.zip", "https://example.com/dead.zip"])
    assert res["ok"] is True
    assert res["alive"] == 1
    assert res["total"] == 2


def test_ghost_inspect_and_folder(tmp_path):
    d = tmp_path / "imgs"
    d.mkdir()
    im = Image.new("RGB", (20, 20), (120, 40, 200))
    p1 = d / "a.png"
    p2 = d / "b.png"
    im.save(p1)
    im.save(p2)

    insp = ghost.inspect_metadata(str(p1))
    assert insp["ok"] is True
    assert insp["has_gps"] is False

    res = ghost.process_folder(str(d))
    assert res["ok"] is True
    assert res["count"] == 2


def test_hardsub_color_filter():
    im = Image.new("RGB", (10, 10), (0, 0, 0))
    im.putpixel((2, 2), (250, 250, 250))
    buf = BytesIO()
    im.save(buf, format="PNG")
    out = hardsub._filter_sub_image(buf.getvalue(), "both")
    res_im = Image.open(BytesIO(out))
    assert res_im.getpixel((2, 2)) == 0
    assert res_im.getpixel((0, 0)) == 255


def test_hunter_preview_archive_org():
    r = MagicMock()
    r.ok = True
    r.json.return_value = {"files": [{"name": "track.mp3"}]}
    with patch("app.core.kami_hunter.requests.get", return_value=r):
        res = kami_hunter.preview_url("https://archive.org/details/demo-id")
    assert res["ok"] is True
    assert "archive.org/download/demo-id/track.mp3" in res["stream"]


def test_phone_bridge_https_and_query_key():
    html = phone_mod._BRIDGE_HTML
    assert "navigator.mediaDevices.getUserMedia" in html
    assert 'accept="audio/*" capture' in html
    assert "URLSearchParams(location.search).get('k')" in html


def test_link_check_content_range_and_html():
    from app.core import link_check
    head_r = MagicMock(status_code=405, ok=False, headers={})
    get_r = MagicMock(
        status_code=206,
        ok=True,
        url="https://cdn.example.com/file.zip",
        headers={"Content-Length": "1", "Content-Range": "bytes 0-0/12345", "Content-Type": "application/zip"},
    )
    with patch("app.core.link_check.requests.head", return_value=head_r), \
         patch("app.core.link_check.requests.get", return_value=get_r):
        res = link_check._check_one("https://cdn.example.com/file.zip")
    assert res["ok"] is True
    assert res["size"] == 12345

    html_r = MagicMock(
        status_code=200,
        ok=True,
        url="https://cloud.example.com/dead",
        headers={"Content-Length": "4096", "Content-Type": "text/html; charset=utf-8"},
    )
    with patch("app.core.link_check.requests.head", return_value=html_r):
        res2 = link_check._check_one("https://cloud.example.com/dead")
    assert res2["ok"] is False
    assert res2["html"] is True


def test_pdf_ocr_invalid_file_no_fitz(tmp_path):
    from app.core import pdf_ocr
    bad = tmp_path / "not_a_pdf.txt"
    bad.write_text("hello", encoding="utf-8")
    res = pdf_ocr.make_searchable_pdf(str(bad))
    assert res["ok"] is False
    assert "PDF" in res["error"]


def test_kami_mod_running_game_exe_empty(tmp_path):
    from app.core import kami_mod
    assert kami_mod._running_game_exe(tmp_path) == ""


def test_pdf_ocr_turkish_searchable(tmp_path):
    import pypdfium2 as pdfium
    from app.core import pdf_ocr
    src = tmp_path / "scan.pdf"
    doc = pdfium.PdfDocument.new()
    doc.new_page(300, 400)
    doc.save(str(src))
    doc.close()
    with patch("app.core.pdf_ocr.ocr.recognize", return_value={"ok": True, "text": "şirket öğrenci İSTANBUL"}):
        res = pdf_ocr.make_searchable_pdf(str(src))
    assert res["ok"] is True
    assert res["pages_ocr"] == 1
    out_doc = pdfium.PdfDocument(res["out"])
    extracted = out_doc[0].get_textpage().get_text_range()
    out_doc.close()
    assert "şirket" in extracted
    assert "öğrenci" in extracted


def test_link_check_cloud_provider():
    from app.core import link_check
    prov = MagicMock()
    prov.name = "gofile"
    f1 = MagicMock(size=2048, name="demo.zip")
    prov.list.return_value = MagicMock(title="Demo", files=[f1])
    cs = MagicMock()
    cs.provider_for.return_value = prov
    res = link_check._check_one("https://gofile.io/d/abc", cloud_service=cs)
    assert res["ok"] is True
    assert res["size"] == 2048
    assert res["cloud"] == "gofile"
