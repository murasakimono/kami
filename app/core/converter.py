"""Donusturucu: gorsel / ses / video (ffmpeg + Pillow), PDF (pypdf + pypdfium2), Office (LibreOffice), metadata temizleme.

Cikti kaynak dosyanin yanina yazilir (ad cakisirsa ' (2)' eklenir); kaynaga asla dokunulmaz.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Callable

log = logging.getLogger("kami")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

IMAGE_IN = {".png", ".jpg", ".jpeg", ".webp", ".avif", ".heic", ".heif", ".bmp", ".tif", ".tiff", ".gif", ".ico", ".jfif"}
AUDIO_IN = {".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".wma", ".aiff", ".aif", ".alac", ".ape"}
VIDEO_IN = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".wmv", ".flv", ".m4v", ".ts", ".mpg", ".mpeg", ".3gp"}
PDF_IN = {".pdf"}
OFFICE_IN = {".docx", ".doc", ".odt", ".rtf", ".pptx", ".ppt", ".odp", ".xlsx", ".xls", ".ods", ".txt", ".csv", ".epub"}

IMAGE_OUT = ["png", "jpg", "webp", "avif", "bmp", "tiff", "ico", "gif", "pdf"]
AUDIO_OUT = ["mp3", "flac", "wav", "m4a", "opus", "ogg"]
VIDEO_OUT = ["mp4", "mkv", "webm", "mov", "gif"]
WRITER = {".docx", ".doc", ".odt", ".rtf", ".txt", ".epub"}
CALC = {".xlsx", ".xls", ".ods", ".csv"}
IMPRESS = {".pptx", ".ppt", ".odp"}


def kind(path: str) -> str:
    e = Path(path).suffix.lower()
    for k, s in (("image", IMAGE_IN), ("audio", AUDIO_IN), ("video", VIDEO_IN), ("pdf", PDF_IN), ("office", OFFICE_IN)):
        if e in s:
            return k
    return "other"


def targets(path: str) -> list[str]:
    """Bir dosya icin sunulan cikti secenekleri ('pdf:merge' gibi araclar dahil)."""
    e, k = Path(path).suffix.lower(), kind(path)
    out: list[str] = []
    if k == "image":
        out = IMAGE_OUT
    elif k == "audio":
        out = AUDIO_OUT
    elif k == "video":
        out = VIDEO_OUT + AUDIO_OUT
    elif k == "pdf":
        out = ["png", "jpg", "docx", "txt", "pdf:compress", "pdf:split", "pdf:merge"]
    elif k == "office":
        if e in WRITER:
            out = ["pdf", "docx", "odt", "rtf", "txt", "html"]
        elif e in CALC:
            out = ["pdf", "xlsx", "ods", "csv"]
        elif e in IMPRESS:
            out = ["pdf", "pptx", "odp", "png"]
    if k in ("image", "audio", "video", "pdf"):
        out = out + ["meta:strip"]
    same = {"jpeg": "jpg", "jfif": "jpg", "tif": "tiff"}.get(e.lstrip("."), e.lstrip("."))
    return [t for t in out if t != same]


def out_path(src: str, ext: str, tag: str = "", folder: str = "") -> Path:
    p = Path(src)
    base = Path(folder) if folder else p.parent
    stem = p.stem + (f" ({tag})" if tag else "")
    cand = base / f"{stem}.{ext}"
    n = 2
    while cand.exists() or cand.resolve() == p.resolve():
        cand = base / f"{stem} ({n}).{ext}"
        n += 1
    return cand


# ---------------- ffmpeg ----------------
def _duration(ffprobe: str, src: str) -> float:
    try:
        r = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src],
                           capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW)
        return float(r.stdout.strip() or 0)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 0.0


def _ffmpeg(ffmpeg: str, args: list[str], dur: float, on_p: Callable[[float], None], cancel: threading.Event) -> None:
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-progress", "pipe:1", "-nostats", *args]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                         errors="replace", creationflags=NO_WINDOW)
    err: list[str] = []
    threading.Thread(target=lambda: err.extend((p.stderr.read() or "").splitlines()[-6:]), daemon=True).start()
    for line in p.stdout or []:
        if cancel.is_set():
            p.kill()
            break
        if line.startswith("out_time_us=") and dur > 0:
            try:
                on_p(min(0.99, int(line.split("=")[1]) / 1e6 / dur))
            except ValueError:
                pass
    rc = p.wait()
    if cancel.is_set():
        raise InterruptedError
    if rc != 0:
        raise RuntimeError((err[-1] if err else f"ffmpeg rc={rc}")[:200])


AUDIO_ARGS = {
    "mp3": ["-c:a", "libmp3lame", "-q:a", "0"], "flac": ["-c:a", "flac", "-compression_level", "8"],
    "wav": ["-c:a", "pcm_s16le"], "m4a": ["-c:a", "aac", "-b:a", "256k"], "opus": ["-c:a", "libopus", "-b:a", "160k"],
    "ogg": ["-c:a", "libvorbis", "-q:a", "6"],
}
CRF = {"high": 18, "normal": 23, "small": 28}


def _media(src: str, ext: str, opts: dict, tools: dict, on_p, cancel) -> Path:
    out = out_path(src, ext, folder=opts.get("folder", ""))
    dur = _duration(tools["ffprobe"], src)
    q = opts.get("quality", "normal")
    height = int(opts.get("height") or 0)
    vf = [f"scale=-2:{height}"] if height else []
    if ext in AUDIO_ARGS:
        args = ["-i", src, "-vn", "-map", "0:a:0", *AUDIO_ARGS[ext]]
        if ext == "mp3" and q == "small":
            args[-2:] = ["-b:a", "128k"]
        args += ["-map_metadata", "0", str(out)]
    elif ext == "gif":
        fps = 15 if q != "high" else 24
        w = height or 480
        flt = f"fps={fps},scale=-2:{w}:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer"
        args = ["-i", src, "-an", "-filter_complex", flt, str(out)]
    elif ext == "webm":
        args = ["-i", src, *(["-vf", ",".join(vf)] if vf else []), "-c:v", "libvpx-vp9", "-b:v", "0",
                "-crf", str(CRF[q] + 12), "-row-mt", "1", "-deadline", "good", "-cpu-used", "4", "-c:a", "libopus", "-b:a", "128k", str(out)]
    else:   # mp4 / mkv / mov: H.264 + AAC
        args = ["-i", src, *(["-vf", ",".join(vf)] if vf else []), "-c:v", "libx264", "-preset", "medium",
                "-crf", str(CRF[q]), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"]
        if ext in ("mp4", "mov"):
            args += ["-movflags", "+faststart"]
        args += [str(out)]
    try:
        _ffmpeg(tools["ffmpeg"], args, dur, on_p, cancel)
    except BaseException:
        out.unlink(missing_ok=True)
        raise
    return out


# ---------------- gorsel ----------------
def _open_image(src: str, tools: dict):
    from PIL import Image
    try:
        im = Image.open(src)
        im.load()
        return im
    except Exception:   # HEIC vb.: ffmpeg ile PNG'ye cozulur
        tmp = out_path(src, "png", tag="kami-tmp")
        subprocess.run([tools["ffmpeg"], "-v", "error", "-y", "-i", src, "-frames:v", "1", str(tmp)],
                       creationflags=NO_WINDOW, check=True)
        im = Image.open(tmp)
        im.load()
        tmp.unlink(missing_ok=True)
        return im


def _image(src: str, ext: str, opts: dict, tools: dict) -> Path:
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(_open_image(src, tools))
    mw = int(opts.get("max_width") or 0)
    if mw and im.width > mw:
        im = im.resize((mw, round(im.height * mw / im.width)), Image.LANCZOS)
    q = {"high": 95, "normal": 88, "small": 72}[opts.get("quality", "normal")]
    out = out_path(src, ext, folder=opts.get("folder", ""))
    keep = {} if opts.get("strip", True) else ({"exif": im.info["exif"]} if im.info.get("exif") else {})
    if ext in ("jpg", "pdf", "bmp") and im.mode not in ("RGB", "L"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.convert("RGBA").split()[-1])
        im = bg
    fmt = {"jpg": "JPEG", "tiff": "TIFF", "ico": "ICO"}.get(ext, ext.upper())
    kw: dict = {}
    if ext == "jpg":
        kw = {"quality": q, "optimize": True, "progressive": True, **keep}
    elif ext in ("webp", "avif"):
        kw = {"quality": q, **keep}
    elif ext == "png":
        kw = {"optimize": True}
    elif ext == "ico":
        kw = {"sizes": [(s, s) for s in (16, 24, 32, 48, 64, 128, 256) if s <= max(im.size)]}
    elif ext == "pdf":
        kw = {"resolution": 150}
    im.save(out, fmt, **kw)
    return out


def images_to_pdf(srcs: list[str], opts: dict, tools: dict) -> Path:
    from PIL import ImageOps
    pages = []
    for s in srcs:
        im = ImageOps.exif_transpose(_open_image(s, tools))
        pages.append(im.convert("RGB"))
    out = out_path(srcs[0], "pdf", tag=f"{len(srcs)} sayfa" if len(srcs) > 1 else "", folder=opts.get("folder", ""))
    pages[0].save(out, "PDF", save_all=True, append_images=pages[1:], resolution=150)
    return out


# ---------------- PDF ----------------
def _pdf_render(src: str, ext: str, opts: dict) -> Path:
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(src)
    folder = out_path(src, "", tag="sayfalar", folder=opts.get("folder", "")).with_suffix("")
    folder.mkdir(parents=True, exist_ok=True)
    scale = {"high": 300, "normal": 200, "small": 110}[opts.get("quality", "normal")] / 72
    for i in range(len(doc)):
        img = doc[i].render(scale=scale).to_pil()
        if ext == "jpg":
            img.convert("RGB").save(folder / f"{i + 1:03d}.jpg", "JPEG", quality=90)
        else:
            img.save(folder / f"{i + 1:03d}.png", "PNG")
    doc.close()
    return folder


def _pdf_text(src: str, opts: dict) -> Path:
    from pypdf import PdfReader
    out = out_path(src, "txt", folder=opts.get("folder", ""))
    out.write_text("\n\n".join((p.extract_text() or "") for p in PdfReader(src).pages), encoding="utf-8")
    return out


def pdf_merge(srcs: list[str], opts: dict) -> Path:
    from pypdf import PdfWriter
    w = PdfWriter()
    for s in srcs:
        w.append(s)
    out = out_path(srcs[0], "pdf", tag="birlesik", folder=opts.get("folder", ""))
    with open(out, "wb") as f:
        w.write(f)
    return out


def _pdf_split(src: str, opts: dict) -> Path:
    from pypdf import PdfReader, PdfWriter
    r = PdfReader(src)
    folder = out_path(src, "", tag="bolunmus", folder=opts.get("folder", "")).with_suffix("")
    folder.mkdir(parents=True, exist_ok=True)
    for i, page in enumerate(r.pages):
        w = PdfWriter()
        w.add_page(page)
        with open(folder / f"{Path(src).stem} - {i + 1:03d}.pdf", "wb") as f:
            w.write(f)
    return folder


def _pdf_compress(src: str, opts: dict) -> Path:
    from pypdf import PdfWriter
    q = {"high": 85, "normal": 70, "small": 50}[opts.get("quality", "normal")]
    w = PdfWriter(clone_from=src)
    for page in w.pages:
        for img in page.images:
            try:
                im = img.image
                if im.width > 1800:
                    im = im.resize((1800, round(im.height * 1800 / im.width)))
                img.replace(im.convert("RGB") if im.mode not in ("RGB", "L") else im, quality=q)
            except Exception:
                continue
        page.compress_content_streams()
    w.compress_identical_objects(remove_identicals=True, remove_orphans=True)
    out = out_path(src, "pdf", tag="kucuk", folder=opts.get("folder", ""))
    with open(out, "wb") as f:
        w.write(f)
    if out.stat().st_size >= Path(src).stat().st_size:   # kuculmediyse kopyayi tutma
        out.unlink()
        raise RuntimeError("zaten_kucuk")
    return out


# ---------------- metadata ----------------
def _strip_jpeg(src: str, out: Path) -> None:
    """JPEG: yeniden sikistirmadan APP1-APP15 (EXIF, XMP, GPS) ve yorum bolumlerini atar. ICC (APP2) tutulur."""
    data = Path(src).read_bytes()
    if data[:2] != b"\xff\xd8":
        raise ValueError("jpeg degil")
    res, i = bytearray(b"\xff\xd8"), 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            break
        m = data[i + 1]
        if m == 0xDA:   # tarama basladi: kalan veri oldugu gibi
            res += data[i:]
            break
        ln = int.from_bytes(data[i + 2:i + 4], "big")
        seg = data[i:i + 2 + ln]
        drop = (0xE1 <= m <= 0xEF and not (m == 0xE2 and seg[4:16] == b"ICC_PROFILE\x00")) or m == 0xFE
        if not drop:
            res += seg
        i += 2 + ln
    out.write_bytes(bytes(res))


def _strip(src: str, opts: dict, tools: dict) -> Path:
    k, e = kind(src), Path(src).suffix.lower()
    out = out_path(src, e.lstrip("."), tag="temiz", folder=opts.get("folder", ""))
    if e in (".jpg", ".jpeg", ".jfif"):
        _strip_jpeg(src, out)
    elif k == "image":
        from PIL import Image
        im = Image.open(src)
        im.save(out, im.format or e.lstrip(".").upper(), **({"icc_profile": im.info["icc_profile"]} if im.info.get("icc_profile") else {}))
    elif k in ("audio", "video"):
        subprocess.run([tools["ffmpeg"], "-v", "error", "-y", "-i", src, "-map", "0", "-map_metadata", "-1",
                        "-map_chapters", "-1", "-c", "copy", str(out)], creationflags=NO_WINDOW, check=True)
    elif k == "pdf":
        from pypdf import PdfWriter
        w = PdfWriter(clone_from=src)
        w.metadata = None
        w.add_metadata({"/Producer": ""})
        with open(out, "wb") as f:
            w.write(f)
    else:
        raise RuntimeError("desteklenmiyor")
    return out


# ---------------- Office (LibreOffice) ----------------
def find_soffice() -> str:
    for c in (shutil.which("soffice"),
              os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "LibreOffice", "program", "soffice.exe"),
              os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "LibreOffice", "program", "soffice.exe")):
        if c and os.path.isfile(c):
            return c
    return ""


def _office(src: str, ext: str, opts: dict, cancel: threading.Event) -> Path:
    so = find_soffice()
    if not so:
        raise RuntimeError("libreoffice_yok")
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="kami_conv_"))
    filt = ext
    if Path(src).suffix.lower() == ".pdf":
        if ext == "docx":
            filt = 'docx:"MS Word 2007 XML"'
        args = [so, "--headless", "--norestore", "--infilter=writer_pdf_import", "--convert-to", filt, "--outdir", str(tmp), src]
    else:
        args = [so, "--headless", "--norestore", "--convert-to", filt, "--outdir", str(tmp), src]
    profile = Path(tempfile.gettempdir()) / "kami_lo_profile"   # kullanicinin acik LibreOffice'ini engellemesin
    args.insert(1, "-env:UserInstallation=" + profile.as_uri())
    p = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=NO_WINDOW)
    while p.poll() is None:
        if cancel.wait(0.3):
            p.kill()
            shutil.rmtree(tmp, ignore_errors=True)
            raise InterruptedError
    made = next(iter(tmp.glob("*")), None)
    if not made:
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError("libreoffice_hata")
    out = out_path(src, made.suffix.lstrip("."), folder=opts.get("folder", ""))
    shutil.move(str(made), out)
    shutil.rmtree(tmp, ignore_errors=True)
    return out


# ---------------- tek dosya ----------------
def convert_one(src: str, target: str, opts: dict, tools: dict, on_p: Callable[[float], None], cancel: threading.Event) -> Path:
    k = kind(src)
    if target == "meta:strip":
        return _strip(src, opts, tools)
    if k == "pdf":
        if target in ("png", "jpg"):
            return _pdf_render(src, target, opts)
        if target == "txt":
            return _pdf_text(src, opts)
        if target == "pdf:split":
            return _pdf_split(src, opts)
        if target == "pdf:compress":
            return _pdf_compress(src, opts)
        if target == "docx":
            return _office(src, "docx", opts, cancel)
    if k == "image" and target in IMAGE_OUT:
        return _image(src, target, opts, tools)
    if k in ("audio", "video") and (target in AUDIO_OUT or target in VIDEO_OUT):
        return _media(src, target, opts, tools, on_p, cancel)
    if k == "office":
        return _office(src, target, opts, cancel)
    raise RuntimeError("desteklenmiyor")


def safe_name(s: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", s)
