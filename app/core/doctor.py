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
    return _r("aria2", "Indirme motoru (aria2)", "ok" if ok else "fail",
              "Calisiyor" if ok else "Calismiyor: indirmeler baslamaz",
              "" if ok else "restart_aria2")


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
        if shutil.which("ollama"):
            return _r("ollama", "Yerel yapay zeka (Ollama)", "warn", "Kurulu ama kapali", "ollama_start")
        return _r("ollama", "Yerel yapay zeka (Ollama)", "info", "Kurulu degil (istege bagli: yerel Copilot)")


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
    from app.core.extras import APP_VERSION
    cutoff = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() - 86400))
    ver_tag = f"Kami {APP_VERSION}"
    start_idx = next((i for i, ln in enumerate(tail) if ver_tag in ln), 0)
    errs = [ln for ln in tail[start_idx:] if " ERROR " in ln and ln[:16] >= cutoff]
    if not errs:
        return _r("log", "Son hatalar (24 sa)", "ok", "Hata yok")
    last = re.sub(r"^\S+ \S+ ERROR ", "", errs[-1])[:160]
    return _r("log", "Son hatalar (24 sa)", "warn", f"{len(errs)} hata · son: {last}")


def check_spotify() -> dict[str, Any]:
    try:
        from app.core import music_hub
        st = music_hub.spotify_oauth_status()
        if not st.get("connected"):
            if st.get("expired"):
                return _r("spotify", "Spotify PKCE", "warn", "Oturum suresi dolmus (Kamify'dan tekrar baglan)")
            return _r("spotify", "Spotify PKCE", "info", "Oturum acilmamis")
        ex = ThreadPoolExecutor(max_workers=1)
        try:
            res = ex.submit(music_hub.spotify_devices).result(timeout=3.0) or {}
        finally:
            ex.shutdown(wait=False, cancel_futures=True)
        devs = res.get("devices") or [] if isinstance(res, dict) else (res or [])
        active = sum(1 for d in devs if d.get("active") or d.get("is_active"))
        return _r("spotify", "Spotify PKCE", "ok", f"Bagli · {len(devs)} cihaz ({active} aktif)")
    except Exception as exc:
        return _r("spotify", "Spotify PKCE", "warn", f"Durum alinamadi: {type(exc).__name__}")


def check_librespot() -> dict[str, Any]:
    try:
        from app.core import librespot_host
        has_bin = bool(librespot_host.find_binary())
        if not has_bin:
            return _r("librespot", "Dahili oynatici (go-librespot)", "info", "Binary yok (Kamify acilinca indirilir)")
        running = bool(librespot_host.is_running())
        paired = bool(librespot_host.has_credentials())
        if running:
            return _r("librespot", "Dahili oynatici (go-librespot)", "ok",
                      "Calisiyor" + (" · eslesmis" if paired else " · eslesme bekliyor"))
        return _r("librespot", "Dahili oynatici (go-librespot)", "info",
                  "Hazir (kapali)" + (" · eslesmis" if paired else ""))
    except Exception as exc:
        return _r("librespot", "Dahili oynatici (go-librespot)", "warn", f"Durum okunamadi: {type(exc).__name__}")


def check_playnite() -> dict[str, Any]:
    try:
        db = Path(os.environ.get("APPDATA", "")) / "Playnite" / "library" / "games.db"
        imp = paths.DATA_DIR / "playnite_import.json"
        parts = []
        if db.is_file():
            parts.append("games.db var")
        else:
            parts.append("Playnite games.db yok")
        if imp.is_file():
            try:
                data = json.loads(imp.read_text("utf-8"))
                cnt = len(data.get("games") or data) if isinstance(data, (dict, list)) else 0
                ts = time.strftime("%d.%m %H:%M", time.localtime(imp.stat().st_mtime))
                parts.append(f"son ice aktarma: {ts} ({cnt} kayit)")
            except Exception:
                parts.append("playnite_import.json okunamadi")
        else:
            parts.append("ice aktarma yok")
        st = "ok" if db.is_file() else "info"
        return _r("playnite", "Playnite kutuphanesi", st, " · ".join(parts))
    except Exception as exc:
        return _r("playnite", "Playnite kutuphanesi", "warn", f"Okunamadi: {type(exc).__name__}")


def check_media_server(media: Any = None) -> dict[str, Any]:
    port = int(getattr(media, "port", 0) or 0)
    if not port:
        return _r("media", "Medya sunucusu", "fail" if media is not None else "info",
                  "Medya sunucusu kapali" if media is not None else "Baslatilmadi")
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2.0):
            return _r("media", "Medya sunucusu", "ok", f"127.0.0.1:{port} dinliyor")
    except OSError:
        return _r("media", "Medya sunucusu", "fail", f"127.0.0.1:{port} yanit vermiyor")


def check_bridge_server(bridge: Any = None) -> dict[str, Any]:
    port = int(getattr(bridge, "port", 0) or 0)
    if not port and paths.BRIDGE_INFO_PATH.is_file():
        try:
            port = int(json.loads(paths.BRIDGE_INFO_PATH.read_text("utf-8")).get("port") or 0)
        except Exception:
            port = 0
    if not port:
        return _r("bridge", "Tarayici koprusu", "fail" if bridge is not None else "info", "Port yok")
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2.0):
            return _r("bridge", "Tarayici koprusu", "ok", f"127.0.0.1:{port} dinliyor")
    except OSError:
        return _r("bridge", "Tarayici koprusu", "fail", f"127.0.0.1:{port} yanit vermiyor")


def check_module_windows(api: Any = None) -> dict[str, Any]:
    if api is None:
        return _r("modwins", "Modul pencereleri", "info", "Kontrol disi")
    mods = ("player", "studio", "picture", "reader", "games", "music", "cleaner")
    open_ok, bad = [], []
    for m in mods:
        w = getattr(api, f"_{m}_win", None)
        if w is None:
            continue
        ex = ThreadPoolExecutor(max_workers=1)
        try:
            res = ex.submit(w.evaluate_js, "1+1").result(timeout=2.5)
            if res == 2:
                open_ok.append(m)
            else:
                bad.append(m)
        except Exception:
            bad.append(m)
        finally:
            ex.shutdown(wait=False, cancel_futures=True)
    if bad:
        return _r("modwins", "Modul pencereleri", "fail", "Yanit vermeyen: " + ", ".join(bad))
    if open_ok:
        return _r("modwins", "Modul pencereleri", "ok", "Acik & saglam: " + ", ".join(open_ok))
    return _r("modwins", "Modul pencereleri", "info", "Acik modul penceresi yok")


# ---------------------------------------------------------------- calistirici
def run_all(engine: Any = None, ui_errors: list[dict[str, Any]] | None = None, recoveries: int = 0,
            download_dir: str = "", media: Any = None, bridge: Any = None, api: Any = None) -> dict[str, Any]:
    checks: list[Callable[[], dict[str, Any]]] = [
        check_webview2, check_gpu, lambda: check_disk(download_dir), check_data_dir, check_virtual_copies, check_keys,
        check_ffmpeg, check_ytdlp, check_bins, lambda: check_engine(engine), check_native_host, check_ollama,
        check_network, check_room, check_spotify, check_librespot, check_playnite,
        lambda: check_media_server(media), lambda: check_bridge_server(bridge),
        lambda: check_module_windows(api), check_log_errors,
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


def fix_ollama_start() -> dict[str, Any]:
    exe = shutil.which("ollama")
    if not exe:
        return {"ok": False, "message": "Ollama bulunamadi"}
    subprocess.Popen([exe, "serve"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"ok": True, "message": "Ollama baslatildi"}


FIXES: dict[str, Callable[[], dict[str, Any]]] = {"copy_virtual_keys": fix_copy_virtual_keys, "ollama_start": fix_ollama_start}
