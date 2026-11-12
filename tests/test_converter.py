"""Donusturucu: gorsel, PDF, metadata, ses (ffmpeg varsa)."""
import shutil
import subprocess
import threading
from pathlib import Path

import pytest
from PIL import Image

from app.core import converter as cv

NOOP = lambda p: None  # noqa: E731


def _img(tmp: Path, name="a.png", exif=False) -> Path:
    p = tmp / name
    im = Image.new("RGB", (640, 400), (120, 40, 200))
    if exif:
        ex = Image.Exif()
        ex[0x010F] = "KameraMarka"     # Make
        im.save(p, "JPEG", exif=ex.tobytes())
    else:
        im.save(p)
    return p


def test_targets_by_kind(tmp_path):
    assert "webp" in cv.targets(str(tmp_path / "x.png")) and "png" not in cv.targets(str(tmp_path / "x.png"))
    assert "jpg" not in cv.targets(str(tmp_path / "x.jpeg"))
    assert "mp3" in cv.targets(str(tmp_path / "x.mkv")) and "mp4" in cv.targets(str(tmp_path / "x.mkv"))
    assert "pdf:merge" in cv.targets(str(tmp_path / "x.pdf"))
    assert cv.targets(str(tmp_path / "x.docx"))[0] == "pdf"
    assert cv.kind("x.zip") == "other" and cv.targets("x.zip") == []


@pytest.mark.parametrize("ext,fmt", [("jpg", "JPEG"), ("webp", "WEBP"), ("ico", "ICO"), ("bmp", "BMP"), ("pdf", None)])
def test_image_convert(tmp_path, ext, fmt):
    src = _img(tmp_path)
    out = cv.convert_one(str(src), ext, {"max_width": 320}, {}, NOOP, threading.Event())
    assert out.exists() and out.suffix == "." + ext and src.exists()
    if fmt:
        with Image.open(out) as im:
            assert im.format == fmt
            if ext != "ico":
                assert im.width == 320


def test_no_overwrite(tmp_path):
    src = _img(tmp_path)
    a = cv.convert_one(str(src), "jpg", {}, {}, NOOP, threading.Event())
    b = cv.convert_one(str(src), "jpg", {}, {}, NOOP, threading.Event())
    assert a != b and a.exists() and b.exists()


def test_jpeg_exif_strip_lossless(tmp_path):
    src = _img(tmp_path, "foto.jpg", exif=True)
    assert b"KameraMarka" in src.read_bytes()
    out = cv.convert_one(str(src), "meta:strip", {}, {}, NOOP, threading.Event())
    data = out.read_bytes()
    assert b"KameraMarka" not in data
    assert src.read_bytes().split(b"\xff\xda", 1)[1] == data.split(b"\xff\xda", 1)[1]   # goruntu verisi ayni


def test_pdf_tools(tmp_path):
    a, b = _img(tmp_path, "a.png"), _img(tmp_path, "b.png")
    pdf = cv.images_to_pdf([str(a), str(b)], {}, {})
    from pypdf import PdfReader
    assert len(PdfReader(pdf).pages) == 2
    merged = cv.pdf_merge([str(pdf), str(pdf)], {})
    assert len(PdfReader(merged).pages) == 4
    split = cv.convert_one(str(merged), "pdf:split", {}, {}, NOOP, threading.Event())
    assert len(list(split.glob("*.pdf"))) == 4
    pages = cv.convert_one(str(pdf), "png", {"quality": "small"}, {}, NOOP, threading.Event())
    assert len(list(pages.glob("*.png"))) == 2
    clean = cv.convert_one(str(pdf), "meta:strip", {}, {}, NOOP, threading.Event())
    assert clean.exists()


@pytest.mark.skipif(not shutil.which("ffmpeg") and not Path("bin/ffmpeg.exe").exists(), reason="ffmpeg yok")
def test_audio_convert(tmp_path):
    ff = str(Path("bin/ffmpeg.exe").resolve()) if Path("bin/ffmpeg.exe").exists() else shutil.which("ffmpeg")
    fp = str(Path(ff).with_name("ffprobe.exe" if ff.endswith(".exe") else "ffprobe"))
    wav = tmp_path / "ton.wav"
    subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(wav)], check=True)
    seen = []
    out = cv.convert_one(str(wav), "mp3", {}, {"ffmpeg": ff, "ffprobe": fp}, seen.append, threading.Event())
    assert out.exists() and out.stat().st_size > 1000
