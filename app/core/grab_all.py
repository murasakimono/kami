"""Kami Grab-All: gallery-dl ile Instagram / X / TikTok / Pinterest / Reddit profil & pano indirici."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app import paths
from app.core import aitools
from app.core.procjob import attach

NOWIN = 0x08000000 if os.name == "nt" else 0
SUPPORTED_RE = re.compile(
    r"(^|\.)(instagram\.com|x\.com|twitter\.com|tiktok\.com|pinterest\.[a-z.]+|reddit\.com)$",
    flags=re.I,
)


def is_supported(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return bool(SUPPORTED_RE.search(host))


def _uv_exe() -> str | None:
    bundled = paths.BIN_DIR / "uv.exe"
    if bundled.is_file():
        return str(bundled)
    return shutil.which("uv")


def _tool_cmd() -> list[str] | None:
    """gallery-dl calistirmak icin [exe] veya [kpython, -m, gallery_dl] dondurur."""
    env_dir = aitools.tool_env("gallery_dl")
    site_pkg = env_dir / "Lib" / "site-packages" / "gallery_dl"
    if site_pkg.is_dir():
        py = aitools.fix_venv_home("gallery_dl") if paths.FROZEN else str(env_dir / "Scripts" / "python.exe")
        if py and os.path.isfile(py):
            return [py, "-m", "gallery_dl"]
    if not paths.FROZEN:
        p = shutil.which("gallery-dl")
        if p:
            return [p]
        cand = Path(sys.executable).parent / ("gallery-dl.exe" if os.name == "nt" else "gallery-dl")
        if cand.is_file():
            return [str(cand)]
    return None


def find_gallery_dl() -> str | None:
    cmd = _tool_cmd()
    return cmd[0] if cmd else None


def ensure_gallery_dl() -> tuple[bool, list[str] | str]:
    cmd = _tool_cmd()
    if cmd:
        return True, cmd
    uv = _uv_exe()
    if not uv:
        return False, "uv.exe bulunamadı (bin klasörü)"
    env_dir = aitools.tool_env("gallery_dl")
    py = env_dir / "Scripts" / "python.exe"
    try:
        if not py.is_file():
            env_dir.parent.mkdir(parents=True, exist_ok=True)
            r = subprocess.run([uv, "venv", "--python", "3.12", "--seed", str(env_dir)],
                               capture_output=True, text=True, timeout=180, creationflags=NOWIN)
            if r.returncode != 0 or not py.is_file():
                return False, (r.stderr or r.stdout or "Python ortamı oluşturulamadı")[:200]
        r2 = subprocess.run([uv, "pip", "install", "--python", str(py), "gallery-dl"],
                            capture_output=True, text=True, timeout=180, creationflags=NOWIN)
        if r2.returncode == 0:
            cmd = _tool_cmd()
            if cmd:
                return True, cmd
        return False, (r2.stderr or r2.stdout or "gallery-dl kurulamadı")[:200]
    except Exception as exc:
        return False, str(exc)[:200]


def _write_cookies(url: str) -> str:
    """Tarayici cerezlerinden gecici Netscape cookies.txt olusturur (yoksa '')."""
    try:
        from app.engines import ytdlp_engine as yt
        from app.core.vault import group_of, to_netscape
        if yt.COOKIES is None:
            return ""
        g = group_of(url)
        if not g:
            return ""
        cookies = [c for c in yt.COOKIES.load() if group_of(str(c.get("domain") or "")) == g]
        if not cookies:
            return ""
        fd, path = tempfile.mkstemp(prefix="kami_ga_", suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(to_netscape(cookies))
        return path
    except Exception:
        return ""


def default_dest(base_dir: str) -> str:
    d = Path(base_dir) / "Grab-All"
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


def start(url: str, dest_dir: str, limit: int = 0) -> dict[str, Any]:
    if not is_supported(url):
        return {"ok": False, "error": "Desteklenmeyen site (IG, X, TikTok, Pinterest, Reddit desteklenir)"}
    ok, cmd_or_err = ensure_gallery_dl()
    if not ok:
        return {"ok": False, "error": str(cmd_or_err)}
    os.makedirs(dest_dir, exist_ok=True)
    cmd = list(cmd_or_err) + ["--dest", dest_dir, "--write-metadata"]
    cookie_file = _write_cookies(url)
    if cookie_file:
        cmd += ["--cookies", cookie_file]
    if limit > 0:
        cmd += ["--range", f"1-{int(limit)}"]
    cmd.append(url)
    env = aitools._clean_env() if paths.FROZEN else None
    proc = attach(subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
        creationflags=NOWIN, env=env,
    ))
    return {"ok": True, "pid": proc.pid, "dest": dest_dir, "proc": proc, "cookie_file": cookie_file}
