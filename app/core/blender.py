"""Blender ile 3D muzik videosu: Blender'i bul, app/tools/blender_viz.py'yi arka planda calistir, ilerlemeyi izle."""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable

from app import paths

log = logging.getLogger("kami")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
QUALITY = {"fast": (1280, 720, 8), "hd": (1920, 1080, 10), "max": (1920, 1080, 32)}


def _steam_libraries() -> list[Path]:
    libs: list[Path] = []
    for root in (Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam",
                 Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Steam"):
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if root.is_dir():
            libs.append(root)
        try:
            libs += [Path(p.replace("\\\\", "\\")) for p in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text(errors="ignore"))]
        except OSError:
            pass
    return libs


def find_blender(custom: str = "") -> str:
    """Ayardaki yol > PATH > Program Files\\Blender Foundation\\* > Steam kutuphaneleri."""
    if custom and os.path.isfile(custom):
        return custom
    w = shutil.which("blender")
    if w:
        return w
    cands: list[Path] = []
    for pf in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", "")):
        if pf:
            cands += sorted((Path(pf) / "Blender Foundation").glob("Blender*/blender.exe"), reverse=True)
    cands += [lib / "steamapps" / "common" / "Blender" / "blender.exe" for lib in _steam_libraries()]
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs"
    cands += sorted(local.glob("Blender*/blender.exe"), reverse=True)
    return next((str(c) for c in cands if c.is_file()), "")


def output_path(src: str) -> str:
    p = Path(src)
    out = p.with_name(f"{p.stem} (Kami 3D).mp4")
    n = 2
    while out.exists():
        out = p.with_name(f"{p.stem} (Kami 3D {n}).mp4")
        n += 1
    return str(out)


def render(blender: str, src: str, out: str, title: str, ffmpeg: str, quality: str,
           on_progress: Callable[[str, int, int], None], cancel: threading.Event, limit: float = 0) -> dict:
    """Blender'i calistirir. on_progress(asama, kare, toplam). Donus: {"ok": True, "out": ...} | {"ok": False, "error": ...}."""
    w, h, samples = QUALITY.get(quality, QUALITY["hd"])
    script = paths.TOOLSRC_DIR / "app" / "tools" / "blender_viz.py"
    job = {"src": src, "out": out, "title": title, "ffmpeg": ffmpeg, "fps": 30, "w": w, "h": h, "samples": samples,
           "font": str(paths.WEB_DIR / "fonts" / "ChakraPetch-Bold.ttf"),
           "fallback_cover": str(paths.WEB_DIR / "kami.png"), "limit": limit or None}
    fd, jf = tempfile.mkstemp(prefix="kami_viz_", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False)
    tail: list[str] = []
    total = 0
    try:
        p = subprocess.Popen([blender, "-b", "--factory-startup", "-P", str(script), "--", jf],
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        threading.Thread(target=lambda: (cancel.wait(), p.poll() is None and p.kill()), daemon=True).start()
        for line in p.stdout or []:
            line = line.strip()
            if line.startswith("KAMI_STAGE"):
                parts = line.split()
                if parts[1] == "render" and len(parts) > 2:
                    total = int(parts[2])
                on_progress(parts[1], 0, total)
            elif line.startswith("KAMI_FRAME"):
                done, total = (int(x) for x in line.split()[1].split("/"))
                on_progress("render", done, total)
            elif line:
                tail = (tail + [line])[-8:]
        rc = p.wait()
    except OSError as exc:
        return {"ok": False, "error": f"blender_start: {exc}"}
    finally:
        try:
            os.remove(jf)
        except OSError:
            pass
    if cancel.is_set():
        try:
            os.remove(out)
        except OSError:
            pass
        return {"ok": False, "error": "cancelled"}
    if rc != 0 or not os.path.isfile(out):
        log.warning("Blender basarisiz (rc=%s): %s", rc, " | ".join(tail))
        return {"ok": False, "error": (tail[-1] if tail else f"rc={rc}")[:200]}
    return {"ok": True, "out": out}
