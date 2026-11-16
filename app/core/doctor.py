"""Kami Doktor: tek tikla saglik raporu ve guvenli otomatik onarimlar.

Her kontrol {id, name, status: ok|warn|fail|info, detail, fix?} doner; biri patlasa da digerleri calisir.
Gizli bilgilerin DEGERI asla okunmaz/donulmez: yalnizca dosyanin var olup olmadigi.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from app import paths

log = logging.getLogger(__name__)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
WV2_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
KEY_FILES = {   # dosya -> ne ise yarar (degeri okunmaz)
    "room_worker.bin": "Kami Oda sabit linki",
    "turn_key.bin": "Kami Oda TURN (mobil veri baglantisi)",
    "rd_token.bin": "Real-Debrid",
    "yt_cookies.bin": "YouTube cerezleri",
}


def _r(cid: str, name: str, status: str, detail: str = "", fix: str = "") -> dict[str, Any]:
    out = {"id": cid, "name": name, "status": status, "detail": detail}
    if fix:
        out["fix"] = fix
    return out


def _run(cmd: list[str], timeout: float = 8.0) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, creationflags=NO_WINDOW)
        return (r.stdout or "") + (r.stderr or "")
    except Exception as exc:
        return f"__err__ {type(exc).__name__}"


# ---------------------------------------------------------------- sistem
def check_webview2() -> dict[str, Any]:
    if os.name != "nt":
        return _r("webview2", "WebView2", "info", "Windows disi")
    import winreg
    ver = ""
    for hive, key in ((winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{WV2_GUID}"),
                      (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WV2_GUID}"),
                      (winreg.HKEY_CURRENT_USER, rf"Software\Microsoft\EdgeUpdate\Clients\{WV2_GUID}")):
        try:
            with winreg.OpenKey(hive, key) as k:
                ver = str(winreg.QueryValueEx(k, "pv")[0] or "")
                if ver and ver != "0.0.0.0":
                    break
        except OSError:
            continue
    if not ver or ver == "0.0.0.0":
        return _r("webview2", "WebView2", "fail", "WebView2 Runtime bulunamadi: arayuz acilmaz.", "open_wv2")
    major = int(ver.split(".")[0]) if ver.split(".")[0].isdigit() else 0
    args = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
    occl = "CalculateNativeWinOcclusion" in args
    if major and major < 120:
        return _r("webview2", "WebView2", "warn", f"Surum {ver} eski; guncelleme onerilir.", "open_wv2")
    return _r("webview2", "WebView2", "ok" if occl else "warn",
              f"Surum {ver}" + ("" if occl else " · kucultme duzeltmesi (occlusion) devre disi"))


def check_gpu() -> dict[str, Any]:
    if os.name != "nt":
        return _r("gpu", "Ekran karti", "info", "Windows disi")
    out = _run(["powershell", "-NoProfile", "-Command",
                "Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name + '|' + $_.DriverVersion + '|' + $_.DriverDate }"],
               timeout=12)
    rows = [ln.split("|") for ln in out.splitlines() if "|" in ln]
    if not rows:
        return _r("gpu", "Ekran karti", "warn", "Ekran karti bilgisi okunamadi")
    names = [r[0].strip() for r in rows]
    hybrid = len(rows) > 1 and any("nvidia" in n.lower() or "radeon rx" in n.lower() for n in names)
    detail = " + ".join(f"{r[0].strip()} ({r[1].strip()})" for r in rows)
    if hybrid:
        detail += " · hibrit: Kami'yi NVIDIA Denetim Masasi'ndan yuksek performansli GPU'ya atamak beyaz ekran riskini azaltir"
    return _r("gpu", "Ekran karti", "ok", detail)


def check_disk(download_dir: str = "") -> dict[str, Any]:
    probs, parts = [], []
    for label, p in (("Indirme", download_dir or str(paths.downloads_dir())), ("Veri", str(paths.DATA_DIR))):
        try:
            free = shutil.disk_usage(p).free / 1024**3
            parts.append(f"{label}: {free:.0f} GB bos")
            if free < 10:
                probs.append(label)
        except OSError:
            parts.append(f"{label}: okunamadi")
    return _r("disk", "Disk alani", "warn" if probs else "ok", " · ".join(parts))


def check_data_dir() -> dict[str, Any]:
    d = paths.DATA_DIR
    try:
        d.mkdir(parents=True, exist_ok=True)
        t = d / f".doctor_{os.getpid()}.tmp"
        t.write_text("ok", encoding="utf-8")
        t.unlink()
        return _r("datadir", "Veri klasoru", "ok", str(d))
    except OSError as exc:
        return _r("datadir", "Veri klasoru", "fail", f"{d} yazilamiyor: {exc}")


# ---------------------------------------------------------------- MSIX sanal kopya tuzagi (13.11 sabit link sorunu)
def _virtual_data_dirs() -> list[Path]:
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "Packages"
    if not base.is_dir():
        return []
    out = []
    for pkg in base.iterdir():
        cand = pkg / "LocalCache" / "Local" / "Kami" / "data"
        if cand.is_dir():
            out.append(cand)
    return out


def check_virtual_copies() -> dict[str, Any]:
    vdirs = _virtual_data_dirs()
    if not vdirs:
        return _r("virtual", "Gizli (sanal) kopya", "ok", "Yok")
    missing = []
    for vd in vdirs:
        for name in KEY_FILES:
            if (vd / name).is_file() and not (paths.DATA_DIR / name).is_file():
                missing.append(f"{KEY_FILES[name]} ({vd.parents[3].name})")
    if missing:
        return _r("virtual", "Gizli (sanal) kopya", "fail",
                  "Baska bir uygulamanin icinden calisan Kami ayarlari gizli klasore kaydetmis, gercek Kami goremiyor: "
                  + ", ".join(missing), "copy_virtual_keys")
    return _r("virtual", "Gizli (sanal) kopya", "warn",
              "Gizli klasorde eski bir Kami kopyasi var (zararsiz, silinebilir): " + ", ".join(str(v) for v in vdirs))


def fix_copy_virtual_keys() -> dict[str, Any]:
    copied = []
    for vd in _virtual_data_dirs():
        for name in KEY_FILES:
            src, dst = vd / name, paths.DATA_DIR / name
            if src.is_file() and not dst.is_file():
                shutil.copy2(src, dst)
                copied.append(KEY_FILES[name])
    return {"ok": True, "copied": copied}


def check_keys() -> dict[str, Any]:
    have = [v for k, v in KEY_FILES.items() if (paths.DATA_DIR / k).is_file()]
    miss = [v for k, v in KEY_FILES.items() if not (paths.DATA_DIR / k).is_file()]
    return _r("keys", "Kayitli anahtarlar", "info",
              ("Var: " + ", ".join(have) if have else "Hicbiri yok") + (" · Yok: " + ", ".join(miss) if miss else ""))


# ---------------------------------------------------------------- araclar
def check_ffmpeg() -> dict[str, Any]:
    try:
        from app.engines.ytdlp_engine import find_ffmpeg
        ff = find_ffmpeg() or ""
    except Exception:
        ff = shutil.which("ffmpeg") or ""
    if not ff:
        return _r("ffmpeg", "FFmpeg", "fail", "Bulunamadi: donusturme, Studio ve birlestirme calismaz")
    m = re.search(r"ffmpeg version (?:n)?(\d+)\.(\d+)", _run([ff, "-hide_banner", "-version"]))
    if not m:
        return _r("ffmpeg", "FFmpeg", "warn", f"Surum okunamadi: {ff}")
    ver = (int(m.group(1)), int(m.group(2)))
    if ver < (7, 1):
        return _r("ffmpeg", "FFmpeg", "warn", f"{ver[0]}.{ver[1]}: Studio'nun uzun projeleri icin 7.1+ gerekir ({ff})")
    return _r("ffmpeg", "FFmpeg", "ok", f"{ver[0]}.{ver[1]}")


def check_ytdlp() -> dict[str, Any]:
    try:
        import yt_dlp.version as v
        ver = v.__version__
    except Exception:
        return _r("ytdlp", "yt-dlp", "fail", "Yuklu degil: video sitelerinden indirme calismaz")
    m = re.match(r"(\d{4})\.(\d{2})\.(\d{2})", ver)
    if m:
        age = (time.time() - time.mktime((int(m.group(1)), int(m.group(2)), int(m.group(3)), 0, 0, 0, 0, 0, -1))) / 86400
        if age > 60:
            return _r("ytdlp", "yt-dlp", "warn", f"{ver} ({age:.0f} gun once): YouTube degisikliklerinde bozulabilir; Kami'yi guncelle")
    return _r("ytdlp", "yt-dlp", "ok", ver)


def check_bins() -> dict[str, Any]:
    want = {"aria2c": "indirme motoru", "deno": "YouTube imza cozucu"}
    miss = [f"{n} ({why})" for n, why in want.items()
            if not ((paths.BIN_DIR / f"{n}.exe").is_file() or (paths.BIN_DIR / n).is_file() or shutil.which(n))]
    return _r("bins", "Yardimci programlar", "fail" if miss else "ok", "Eksik: " + ", ".join(miss) if miss else "aria2c, deno")


def check_engine(engine: Any) -> dict[str, Any]:
    try:
        ok = bool(engine and engine.running)
    except Exception:
        ok = False
    return _r("aria2", "Indirme motoru (aria2)", "ok" if ok else "fail", "Calisiyor" if ok else "Calismiyor: indirmeler baslamaz")


def check_native_host() -> dict[str, Any]:
    if os.name != "nt":
        return _r("host", "Tarayici eklentisi baglantisi", "info", "Windows disi")
    import winreg
    found = []
    for br, key in (("Brave", r"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\com.metehan.kami"),
                    ("Chrome", r"Software\Google\Chrome\NativeMessagingHosts\com.metehan.kami"),
                    ("Edge", r"Software\Microsoft\Edge\NativeMessagingHosts\com.metehan.kami")):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
                manifest = Path(str(winreg.QueryValueEx(k, "")[0]))
            if manifest.is_file():
                found.append(br)
        except OSError:
            continue
    if not found:
        return _r("host", "Tarayici eklentisi baglantisi", "warn", "Hicbir tarayiciya kayitli degil (sag tik / otomatik yakalama calismaz)")
    return _r("host", "Tarayici eklentisi baglantisi", "ok", ", ".join(found))


def check_ollama() -> dict[str, Any]:
    try:
        import urllib.request
        with urllib.request.urlopen((os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434") + "/api/tags", timeout=1.5) as r:
            models = [m.get("name", "") for m in json.loads(r.read()).get("models", [])]
        return _r("ollama", "Yerel yapay zeka (Ollama)", "ok", ", ".join(models[:6]) or "Calisiyor, model yok")
    except Exception:
        return _r("ollama", "Yerel yapay zeka (Ollama)", "info", "Kapali: Copilot ve otomatik bolum basliklari kullanilamaz")


def check_network() -> dict[str, Any]:
    res = []
    for host in ("github.com", "api.cloudflare.com"):
        t0 = time.monotonic()
        try:
            socket.create_connection((host, 443), timeout=3).close()
            res.append(f"{host} {int((time.monotonic() - t0) * 1000)} ms")
        except OSError:
            res.append(f"{host} ULASILAMIYOR")
    bad = any("ULASILAMIYOR" in x for x in res)
    return _r("net", "Internet", "warn" if bad else "ok", " · ".join(res))


def check_room() -> dict[str, Any]:
    try:
        from app.core import room
        st = room.SERVER.status()
    except Exception as exc:
        return _r("room", "Kami Oda", "info", f"Durum okunamadi: {type(exc).__name__}")
    if not st.get("on"):
        return _r("room", "Kami Oda", "info", "Kapali")
    if st.get("stable"):
        return _r("room", "Kami Oda", "ok", "Acik · sabit link calisiyor" + (" · TURN var" if st.get("turn") else " · TURN yok (mobil veride baglanamayabilir)"))
    return _r("room", "Kami Oda", "warn", "Acik ama gecici link kullaniliyor (sabit link guncellenemedi)", "room_relink")


def check_log_errors() -> dict[str, Any]:
    f = paths.DATA_DIR / "kami.log"
    if not f.is_file():
        return _r("log", "Son hatalar", "info", "Log yok")
    try:
        with f.open("rb") as fh:
            fh.seek(max(0, f.stat().st_size - 400_000))
            tail = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return _r("log", "Son hatalar", "info", "Log okunamadi")
    cutoff = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() - 86400))
    errs = [ln for ln in tail if " ERROR " in ln and ln[:16] >= cutoff]
    if not errs:
        return _r("log", "Son hatalar (24 sa)", "ok", "Hata yok")
    last = re.sub(r"^\S+ \S+ ERROR ", "", errs[-1])[:160]
    return _r("log", "Son hatalar (24 sa)", "warn", f"{len(errs)} hata · son: {last}")


# ---------------------------------------------------------------- calistirici
def run_all(engine: Any = None, ui_errors: list[dict[str, Any]] | None = None, recoveries: int = 0,
            download_dir: str = "") -> dict[str, Any]:
    checks: list[Callable[[], dict[str, Any]]] = [
        check_webview2, check_gpu, lambda: check_disk(download_dir), check_data_dir, check_virtual_copies, check_keys,
        check_ffmpeg, check_ytdlp, check_bins, lambda: check_engine(engine), check_native_host, check_ollama,
        check_network, check_room, check_log_errors,
    ]

    def safe(fn):
        try:
            return fn()
        except Exception as exc:
            log.exception("Doktor kontrolu patladi")
            return _r(getattr(fn, "__name__", "?"), getattr(fn, "__name__", "?"), "warn", f"Kontrol calismadi: {type(exc).__name__}")

    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(safe, checks))
    ui = list(ui_errors or [])[-10:]
    results.append(_r("ui", "Arayuz (JS) hatalari", "warn" if ui else "ok",
                      (f"{len(ui)} hata · son: [{ui[-1]['page']}] {ui[-1]['msg'][:140]}" if ui else "Bu oturumda yok")
                      + (f" · {recoveries} kez kendini toparladi" if recoveries else "")))
    from app.core.extras import APP_VERSION
    summary = {s: sum(1 for r in results if r["status"] == s) for s in ("ok", "warn", "fail", "info")}
    return {"ok": True, "version": APP_VERSION, "python": sys.version.split()[0], "at": int(time.time()),
            "summary": summary, "checks": results, "ui_errors": ui}


FIXES: dict[str, Callable[[], dict[str, Any]]] = {"copy_virtual_keys": fix_copy_virtual_keys}
