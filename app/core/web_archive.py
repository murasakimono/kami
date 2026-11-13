"""Faz 11.3 — Canli Yayin DVR (--live-from-start) ve Tek-Dosya HTML Web Arsivi.

Mevcut mediatools.py SponsorBlock yapisina dokunmaz; canli DVR icin yt-dlp
--live-from-start + --embed-chapters seceneklerini hazirlar ve web sayfalarini
SingleFile CLI (varsa) veya yerlesik Python HTML paketleyicisiyle arsivler.
"""
from __future__ import annotations

import base64
import html
import logging
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

from app.core.link_crawler import is_safe_public_url

log = logging.getLogger(__name__)

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0 Safari/537.36"


def build_live_dvr_opts(out_dir: str | Path, *, from_start: bool = True, embed_chapters: bool = True) -> dict[str, Any]:
    """yt-dlp canli yayin DVR secenekleri (SponsorBlock'a dokunmaz)."""
    target = Path(out_dir)
    opts: dict[str, Any] = {
        "outtmpl": str(target / "%(title).120s [DVR-%(id)s].%(ext)s"),
        "live_from_start": bool(from_start),
        "concurrent_fragment_downloads": 4,
        "hls_use_mpegts": True,
        "continuedl": True,
        "noplaylist": True,
    }
    if embed_chapters:
        opts["postprocessors"] = [{"key": "FFmpegMetadata", "add_chapters": True}]
    return opts


def start_live_dvr(url: str, out_dir: str | Path, *, from_start: bool = True, embed_chapters: bool = True) -> dict[str, Any]:
    """Canli yayini baslangictan itibaren (DVR) indirir."""
    if not is_safe_public_url(url):
        return {"ok": False, "error": "Gecersiz veya ozel ag URL'si"}
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    opts = build_live_dvr_opts(target, from_start=from_start, embed_chapters=embed_chapters)
    try:
        from app.engines.ytdlp_engine import _ytdlp, find_ffmpeg
        ff = find_ffmpeg()
        if ff:
            opts["ffmpeg_location"] = ff
        yt_dlp = _ytdlp()
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info) if info else ""
        return {"ok": True, "path": filename, "title": (info or {}).get("title", "")}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}


def _find_singlefile() -> str:
    for name in ("single-file", "single-file-cli", "single-file.exe"):
        hit = shutil.which(name)
        if hit:
            return hit
    return ""


def _inline_css_and_images(raw_html: str, base_url: str, session: requests.Session) -> str:
    """Harici CSS ve kucuk gorselleri (<512 KB) tek HTML icine gomer."""
    def _repl_css(m: re.Match[str]) -> str:
        href = urljoin(base_url, html.unescape(m.group(1)))
        if not is_safe_public_url(href):
            return m.group(0)
        try:
            r = session.get(href, timeout=6)
            if r.status_code == 200 and len(r.content) < 512_000:
                css = r.text.replace("</style>", "<\\/style>")
                return f"<style data-kami-src=\"{html.escape(href)}\">\n{css}\n</style>"
        except requests.RequestException:
            pass
        return m.group(0)

    def _repl_img(m: re.Match[str]) -> str:
        prefix, src, suffix = m.group(1), m.group(2), m.group(3)
        if src.startswith("data:"):
            return m.group(0)
        abs_src = urljoin(base_url, html.unescape(src))
        if not is_safe_public_url(abs_src):
            return m.group(0)
        try:
            r = session.get(abs_src, timeout=5)
            ctype = (r.headers.get("Content-Type") or "image/png").split(";")[0].strip()
            if r.status_code == 200 and ctype.startswith("image/") and len(r.content) < 512_000:
                b64 = base64.b64encode(r.content).decode("ascii")
                return f"{prefix}data:{ctype};base64,{b64}{suffix}"
        except requests.RequestException:
            pass
        return m.group(0)

    out = re.sub(r'<link[^>]+rel=["\']stylesheet["\'][^>]+href=["\']([^"\']+)["\'][^>]*>', _repl_css, raw_html, flags=re.I)
    out = re.sub(r'(<img\b[^>]*\bsrc=["\'])([^"\']+)(["\'][^>]*>)', _repl_img, out, flags=re.I)
    meta = f'<meta name="kami-archived-at" content="{time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}">\n<base href="{html.escape(base_url)}">\n'
    if re.search(r"<head[^>]*>", out, re.I):
        out = re.sub(r"(<head[^>]*>)", r"\1\n" + meta, out, count=1, flags=re.I)
    else:
        out = meta + out
    return out


def archive_webpage(url: str, out_path: str | Path, *, prefer_cli: bool = True) -> dict[str, Any]:
    """Web sayfasini tek HTML dosyasi olarak arsivler (SingleFile CLI veya yerlesik paketleyici)."""
    if not is_safe_public_url(url):
        return {"ok": False, "error": "Gecersiz veya ozel ag URL'si"}
    dst = Path(out_path)
    dst.parent.mkdir(parents=True, exist_ok=True)

    cli = _find_singlefile() if prefer_cli else ""
    if cli:
        try:
            r = subprocess.run([cli, url, str(dst)], capture_output=True, timeout=90, creationflags=NO_WINDOW)
            if r.returncode == 0 and dst.is_file() and dst.stat().st_size > 0:
                return {"ok": True, "path": str(dst), "method": "single-file", "bytes": dst.stat().st_size}
        except Exception as exc:
            log.warning("SingleFile CLI yedek yola dusuyor: %s", exc)

    try:
        sess = requests.Session()
        sess.headers.update({"User-Agent": _UA})
        resp = sess.get(url, timeout=15)
        resp.raise_for_status()
        packed = _inline_css_and_images(resp.text, resp.url or url, sess)
        dst.write_text(packed, encoding="utf-8")
        return {"ok": True, "path": str(dst), "method": "builtin", "bytes": dst.stat().st_size}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}
