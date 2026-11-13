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
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

from app.core.link_crawler import is_safe_public_url

log = logging.getLogger(__name__)

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0 Safari/537.36"
_DVR_JOBS: dict[str, dict[str, Any]] = {}
_DVR_LOCK = threading.Lock()


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


def start_live_dvr(
    url: str,
    out_dir: str | Path,
    *,
    from_start: bool = True,
    embed_chapters: bool = True,
    background: bool = True,
) -> dict[str, Any]:
    """Canli yayini baslangictan itibaren (DVR) indirir; varsayilan olarak arka planda calisir."""
    if not is_safe_public_url(url):
        return {"ok": False, "error": "Gecersiz veya ozel ag URL'si"}
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    opts = build_live_dvr_opts(target, from_start=from_start, embed_chapters=embed_chapters)
    job_id = uuid.uuid4().hex[:10]
    cancel_ev = threading.Event()

    def _run_job() -> dict[str, Any]:
        try:
            from app.engines.ytdlp_engine import _ytdlp, find_ffmpeg
            ff = find_ffmpeg()
            if ff:
                opts["ffmpeg_location"] = ff

            def _hook(d: dict[str, Any]) -> None:
                if cancel_ev.is_set():
                    raise RuntimeError("DVR iptal edildi")

            opts["progress_hooks"] = [_hook]
            yt_dlp = _ytdlp()
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info) if info else ""
            res = {"ok": True, "path": filename, "title": (info or {}).get("title", ""), "status": "done"}
        except Exception as exc:
            res = {"ok": False, "error": str(exc)[:300], "status": "cancelled" if cancel_ev.is_set() else "error"}
        with _DVR_LOCK:
            if job_id in _DVR_JOBS:
                _DVR_JOBS[job_id].update(res)
        return res

    with _DVR_LOCK:
        _DVR_JOBS[job_id] = {"job_id": job_id, "url": url, "status": "running", "cancel": cancel_ev}

    if not background:
        return _run_job()

    t = threading.Thread(target=_run_job, name=f"kami-dvr-{job_id}", daemon=True)
    t.start()
    return {"ok": True, "started": True, "job_id": job_id, "status": "running"}


def cancel_live_dvr(job_id: str) -> dict[str, Any]:
    with _DVR_LOCK:
        job = _DVR_JOBS.get(job_id)
        if not job:
            return {"ok": False, "error": "DVR isi bulunamadi"}
        job["cancel"].set()
        return {"ok": True, "job_id": job_id, "cancelling": True}


def list_live_dvr() -> list[dict[str, Any]]:
    with _DVR_LOCK:
        return [{k: v for k, v in j.items() if k != "cancel"} for j in _DVR_JOBS.values()]


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
                if not r.encoding or r.encoding.lower() == "iso-8859-1":
                    r.encoding = r.apparent_encoding or "utf-8"
                css = r.text.replace("</style>", "<\\/style>")
                # CSS icindeki goreli url(...) adreslerini mutlak yap
                css = re.sub(
                    r'url\((["\']?)(?!data:|https?:)([^)"\']+)\1\)',
                    lambda um: f'url("{urljoin(href, um.group(2))}")',
                    css,
                )
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
        if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
            resp.encoding = resp.apparent_encoding or "utf-8"
        packed = _inline_css_and_images(resp.text, resp.url or url, sess)
        dst.write_text(packed, encoding="utf-8")
        return {"ok": True, "path": str(dst), "method": "builtin", "bytes": dst.stat().st_size}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}
