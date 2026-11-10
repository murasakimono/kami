"""Asama 6a yardimcilari: zamanlayici, Defender taramasi, SHA256, guncelleme denetimi, sorun paketi.

Hepsi arka plan is parcaciginda calisir; ayarlardan acilip kapanir.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import os
import platform
import re
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Callable

from app import paths

log = logging.getLogger(__name__)

APP_VERSION = "0.9.2"
GITHUB_REPO = "murasakimono/kami"
CREATE_NO_WINDOW = 0x08000000


# ---------------------------------------------------------------- zamanlayici
def _hm(text: str) -> int:
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", str(text or "").strip())
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise ValueError("time")
    return int(m.group(1)) * 60 + int(m.group(2))


def in_window(now_min: int, start: str, stop: str) -> bool:
    """[start, stop) araliginda mi? Gece yarisini asabilir (02:00-08:00, 23:00-07:00)."""
    a, b = _hm(start), _hm(stop)
    if a == b:
        return True
    return a <= now_min < b if a < b else (now_min >= a or now_min < b)


class Scheduler:
    """Baslangic saatinde tum duraklatilmislari surdurur, bitis saatinde tumunu duraklatir.
    Sadece GECISLERDE davranir (acilista mevcut duruma dokunmaz)."""

    def __init__(self, settings, on_start: Callable[[], None], on_stop: Callable[[], None]) -> None:
        self.settings = settings
        self.on_start, self.on_stop = on_start, on_stop
        self._last: bool | None = None
        self._stop = threading.Event()

    def check(self, now: dt.datetime | None = None) -> str:
        if not self.settings.get("schedule_enabled"):
            self._last = None
            return ""
        now = now or dt.datetime.now()
        try:
            inside = in_window(now.hour * 60 + now.minute, self.settings.get("schedule_start"),
                               self.settings.get("schedule_stop"))
        except ValueError:
            return ""
        prev, self._last = self._last, inside
        if prev is None or prev == inside:
            return ""
        log.info("Zamanlayici: %s", "baslat" if inside else "durdur")
        (self.on_start if inside else self.on_stop)()
        return "start" if inside else "stop"

    def start(self) -> None:
        def loop() -> None:
            while not self._stop.wait(20):
                try:
                    self.check()
                except Exception:
                    log.exception("Zamanlayici hatasi")
        threading.Thread(target=loop, name="kami-schedule", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()


# ---------------------------------------------------------------- Defender
EXEC_ARCHIVE_EXT = {
    "exe", "msi", "msix", "appx", "bat", "cmd", "com", "scr", "ps1", "vbs", "js", "jse", "wsf", "hta", "jar",
    "dll", "sys", "lnk", "reg", "apk", "iso", "img", "vhd",
    "zip", "rar", "7z", "tar", "gz", "tgz", "bz2", "xz", "cab", "zst",
}


def should_scan(path: str, mode: str) -> bool:
    if mode == "off" or not path:
        return False
    if mode == "all" or os.path.isdir(path):
        return True
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return ext in EXEC_ARCHIVE_EXT


def mpcmdrun() -> str:
    base = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Microsoft" / "Windows Defender" / "Platform"
    try:
        vers = sorted((p for p in base.iterdir() if (p / "MpCmdRun.exe").exists()), key=lambda p: p.name)
        if vers:
            return str(vers[-1] / "MpCmdRun.exe")
    except OSError:
        pass
    p = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Windows Defender" / "MpCmdRun.exe"
    return str(p) if p.exists() else ""


def defender_scan(path: str, timeout: float = 600) -> str:
    """'clean' | 'threat' | 'error' | 'unavailable'. Tehdit bulunursa Defender kendisi karantinaya alir."""
    exe = mpcmdrun()
    if not exe or not os.path.exists(path):
        return "unavailable"
    try:
        r = subprocess.run([exe, "-Scan", "-ScanType", "3", "-File", path], capture_output=True,
                           timeout=timeout, creationflags=CREATE_NO_WINDOW)
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("Defender taramasi calismadi: %s", type(exc).__name__)
        return "error"
    if r.returncode == 0:
        return "clean"
    if r.returncode == 2:
        log.warning("Defender tehdit buldu: %s", path)
        return "threat"
    log.warning("Defender taramasi kod %s: %s", r.returncode, path)
    return "error"


# ---------------------------------------------------------------- SHA256
def sha256_file(path: str, chunk: int = 4 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def norm_hash(text: str) -> str:
    """'sha256:ABC..' / 'SHA-256=abc..' / bosluklu -> 64 hane kucuk; gecersizse ''."""
    t = re.sub(r"^(sha-?256)\s*[:=]\s*", "", str(text or "").strip(), flags=re.I).replace(" ", "").lower()
    return t if re.fullmatch(r"[0-9a-f]{64}", t) else ""


# ---------------------------------------------------------------- guncelleme
def _ver(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:4]) or (0,)


def _gh() -> str:
    import shutil
    return shutil.which("gh") or ""


def _gh_latest(repo: str) -> dict | None:
    """Ozel repo: anonim API 404 verir -> girisli GitHub CLI (gh) ile oku. Yoksa None."""
    import json as _json
    import subprocess
    gh = _gh()
    if not gh:
        return None
    try:
        r = subprocess.run([gh, "api", f"repos/{repo}/releases/latest"], capture_output=True, text=True,
                           timeout=20, creationflags=0x08000000)
        return _json.loads(r.stdout) if r.returncode == 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def check_update(current: str = APP_VERSION, repo: str = GITHUB_REPO) -> dict[str, Any]:
    """GitHub Releases'taki son surum. {'available': bool, 'version', 'url', 'notes', 'asset'} ya da {'error'}.
    Repo ozelse (anonim 404) girisli `gh` ile denenir."""
    import requests
    try:
        r = requests.get(f"https://api.github.com/repos/{repo}/releases/latest", timeout=10,
                         headers={"Accept": "application/vnd.github+json", "User-Agent": "Kami-updater"})
    except requests.RequestException as exc:
        return {"available": False, "error": type(exc).__name__}
    j = r.json() if r.status_code == 200 else (_gh_latest(repo) if r.status_code == 404 else None)
    if j is None and r.status_code == 404:
        return {"available": False, "version": "", "none": True}
    if j is None:
        return {"available": False, "error": f"http_{r.status_code}"}
    tag = str(j.get("tag_name") or "")
    url = str(j.get("html_url") or "")
    if not url.startswith(f"https://github.com/{repo}/"):
        url = f"https://github.com/{repo}/releases"
    asset = next((a for a in j.get("assets") or [] if re.fullmatch(r"Kami-Setup-[\d.]+\.exe", a.get("name", ""))), {})
    return {"available": _ver(tag) > _ver(current), "version": tag.lstrip("v"), "url": url,
            "notes": str(j.get("body") or "")[:600], "asset": asset.get("name", ""), "tag": tag,
            "asset_url": asset.get("browser_download_url", "")}


def download_update(info: dict[str, Any], dest_dir: Path, repo: str = GITHUB_REPO) -> Path:
    """Kurulum dosyasini indir (herkese acik: dogrudan; ozel repo: gh release download). -> yol"""
    import subprocess
    import requests
    name = str(info.get("asset") or "")
    if not re.fullmatch(r"Kami-Setup-[\d.]+\.exe", name):
        raise ValueError("asset")
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / name
    url = str(info.get("asset_url") or "")
    if url.startswith(f"https://github.com/{repo}/releases/download/"):
        r = requests.get(url, timeout=600, stream=True)
        if r.status_code == 200:
            with open(out, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
            return out
    gh = _gh()
    if not gh:
        raise RuntimeError("gh_missing")
    r2 = subprocess.run([gh, "release", "download", str(info.get("tag") or ""), "--repo", repo, "--pattern", name,
                         "--dir", str(dest_dir), "--clobber"], capture_output=True, text=True, timeout=900,
                        creationflags=0x08000000)
    if r2.returncode != 0 or not out.is_file():
        raise RuntimeError("download_failed: " + (r2.stderr or "")[-200:])
    return out


# ---------------------------------------------------------------- sorun paketi
_SECRET_PATTERNS = [
    (re.compile(r"(?i)(token|secret|password|passwd|auth|authorization|cookie|session|apikey|api_key|key|sig|signature)"
                r"(\"?\s*[:=]\s*\"?)([^\s\"&,;]+)"), r"\1\2[gizli]"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"), r"\1[gizli]"),
    (re.compile(r"(https?://[^\s\"'?#]+)\?[^\s\"']*"), r"\1?[sorgu gizli]"),   # imzali linkler
    (re.compile(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@"), r"\1[gizli]@"),       # kullanici:sifre@
    (re.compile(r"\b[A-Za-z0-9_\-]{40,}\b"), "[gizli]"),                        # uzun anahtar/cerez benzeri
]


def mask(text: str) -> str:
    for pat, rep in _SECRET_PATTERNS:
        text = pat.sub(rep, text)
    return text


def _tail(path: Path, limit: int) -> str:
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - limit))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def build_report(state: dict[str, Any], out_dir: Path) -> Path:
    """Log + durum paketi (zip). Gizli bilgiler maskelenir; DPAPI dosyalari, cerezler, token EKLENMEZ."""
    from app.core.watchdog import thread_dump
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"Kami_sorun_{time.strftime('%Y%m%d_%H%M%S')}.zip"
    d = paths.DATA_DIR
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name in ("kami.log.2", "kami.log.1", "kami.log"):
            if (d / name).exists():
                z.writestr(name + ".txt", mask(_tail(d / name, 3_000_000)))
        if (d / "aria2.log").exists():
            z.writestr("aria2.log.txt", mask(_tail(d / "aria2.log", 500_000)))
        if paths.SETTINGS_PATH.exists():
            z.writestr("settings.json", mask(paths.SETTINGS_PATH.read_text(encoding="utf-8", errors="replace")))
        z.writestr("state.json", mask(json.dumps(state, ensure_ascii=False, indent=1, default=str)))
        info = {
            "kami": APP_VERSION, "python": sys.version, "platform": platform.platform(),
            "frozen": bool(getattr(sys, "frozen", False)),
        }
        try:
            from importlib.metadata import version
            for pkg in ("pywebview", "yt-dlp", "pystray"):
                try:
                    info[pkg] = version(pkg)
                except Exception:
                    pass
        except Exception:
            pass
        z.writestr("system.json", json.dumps(info, indent=1))
        z.writestr("threads.txt", thread_dump())
    log.info("Sorun paketi olusturuldu: %s", out.name)
    return out
