"""Kami Grab-All: gallery-dl ile Instagram / X / TikTok / Pinterest / Reddit profil & pano indirici."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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


def find_gallery_dl() -> str | None:
    p = shutil.which("gallery-dl")
    if p:
        return p
    cand = Path(sys.executable).parent / ("gallery-dl.exe" if os.name == "nt" else "gallery-dl")
    return str(cand) if cand.is_file() else None


def ensure_gallery_dl() -> tuple[bool, str]:
    exe = find_gallery_dl()
    if exe:
        return True, exe
    uv = shutil.which("uv")
    if not uv:
        return False, "gallery-dl ve uv bulunamadı"
    try:
        r = subprocess.run([uv, "pip", "install", "--python", sys.executable, "gallery-dl"],
                           capture_output=True, text=True, timeout=180, creationflags=NOWIN)
        if r.returncode == 0:
            exe = find_gallery_dl()
            if exe:
                return True, exe
        return False, (r.stderr or r.stdout or "gallery-dl kurulamadı")[:200]
    except Exception as exc:
        return False, str(exc)[:200]


def default_dest(base_dir: str) -> str:
    d = Path(base_dir) / "Grab-All"
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


def start(url: str, dest_dir: str, limit: int = 0) -> dict[str, Any]:
    if not is_supported(url):
        return {"ok": False, "error": "Desteklenmeyen site (IG, X, TikTok, Pinterest, Reddit desteklenir)"}
    ok, exe_or_err = ensure_gallery_dl()
    if not ok:
        return {"ok": False, "error": exe_or_err}
    os.makedirs(dest_dir, exist_ok=True)
    cmd = [exe_or_err, "--dest", dest_dir, "--write-metadata"]
    if limit > 0:
        cmd += ["--range", f"1-{int(limit)}"]
    cmd.append(url)
    proc = attach(subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, creationflags=NOWIN))
    return {"ok": True, "pid": proc.pid, "dest": dest_dir, "proc": proc}
