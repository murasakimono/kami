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
    "turn_key.bin": "Kami Oda TURN (mobil veri bağlantısı)",
    "rd_token.bin": "Real-Debrid",
    "yt_cookies.bin": "YouTube çerezleri",
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
        return _r("webview2", "WebView2", "info", "Windows dışı")
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
        return _r("webview2", "WebView2", "fail", "WebView2 Runtime bulunamadı: arayüz açılmaz.", "open_wv2")
    major = int(ver.split(".")[0]) if ver.split(".")[0].isdigit() else 0
    args = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
    occl = "CalculateNativeWinOcclusion" in args
    if major and major < 120:
        return _r("webview2", "WebView2", "warn", f"Sürüm {ver} eski; güncelleme önerilir.", "open_wv2")
    return _r("webview2", "WebView2", "ok" if occl else "warn",
              f"Sürüm {ver}" + ("" if occl else " · küçültme düzeltmesi (occlusion) devre dışı"))


def check_gpu() -> dict[str, Any]:
    if os.name != "nt":
        return _r("gpu", "Ekran kartı", "info", "Windows dışı")
    out = _run(["powershell", "-NoProfile", "-Command",
                "Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name + '|' + $_.DriverVersion + '|' + $_.DriverDate }"],
               timeout=12)
    rows = [ln.split("|") for ln in out.splitlines() if "|" in ln]
    if not rows:
        return _r("gpu", "Ekran kartı", "warn", "Ekran kartı bilgisi okunamadı")
    names = [r[0].strip() for r in rows]
    hybrid = len(rows) > 1 and any("nvidia" in n.lower() or "radeon rx" in n.lower() for n in names)
    detail = " + ".join(f"{r[0].strip()} ({r[1].strip()})" for r in rows)
    if hybrid:
        detail += " · hibrit: Kami'yi NVIDIA Denetim Masası'ndan yüksek performanslı GPU'ya atamak beyaz ekran riskini azaltır"
    return _r("gpu", "Ekran kartı", "ok", detail)


def check_disk(download_dir: str = "") -> dict[str, Any]:
    probs, parts = [], []
    for label, p in (("İndirme", download_dir or str(paths.downloads_dir())), ("Veri", str(paths.DATA_DIR))):
        try:
            free = shutil.disk_usage(p).free / 1024**3
            parts.append(f"{label}: {free:.0f} GB boş")
            if free < 10:
                probs.append(label)
        except OSError:
            parts.append(f"{label}: okunamadı")
    return _r("disk", "Disk alanı", "warn" if probs else "ok", " · ".join(parts))


def check_data_dir() -> dict[str, Any]:
    d = paths.DATA_DIR
    try:
        d.mkdir(parents=True, exist_ok=True)
        t = d / f".doctor_{os.getpid()}.tmp"
        t.write_text("ok", encoding="utf-8")
        t.unlink()
        return _r("datadir", "Veri klasörü", "ok", str(d))
    except OSError as exc:
        return _r("datadir", "Veri klasörü", "fail", f"{d} yazılamıyor: {exc}")


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
                  "Başka bir uygulamanın içinden çalışan Kami ayarları gizli klasöre kaydetmiş, gerçek Kami göremiyor: "
                  + ", ".join(missing), "copy_virtual_keys")
    return _r("virtual", "Gizli (sanal) kopya", "warn",
              "Gizli klasörde eski bir Kami kopyası var (zararsız, silinebilir): " + ", ".join(str(v) for v in vdirs))


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
    return _r("keys", "Kayıtlı anahtarlar", "info",
              ("Var: " + ", ".join(have) if have else "Hiçbiri yok") + (" · Yok: " + ", ".join(miss) if miss else ""))


# ---------------------------------------------------------------- araclar
def check_ffmpeg() -> dict[str, Any]:
    try:
        from app.engines.ytdlp_engine import find_ffmpeg
        ff = find_ffmpeg() or ""
    except Exception:
        ff = shutil.which("ffmpeg") or ""
    if not ff:
        return _r("ffmpeg", "FFmpeg", "fail", "Bulunamadı: dönüştürme, Studio ve birleştirme çalışmaz")
    m = re.search(r"ffmpeg version (?:n)?(\d+)\.(\d+)", _run([ff, "-hide_banner", "-version"]))
    if not m:
        return _r("ffmpeg", "FFmpeg", "warn", f"Sürüm okunamadı: {ff}")
    ver = (int(m.group(1)), int(m.group(2)))
    if ver < (7, 1):
        return _r("ffmpeg", "FFmpeg", "warn", f"{ver[0]}.{ver[1]}: Studio'nun uzun projeleri için 7.1+ gerekir ({ff})")
    return _r("ffmpeg", "FFmpeg", "ok", f"{ver[0]}.{ver[1]}")


def check_ytdlp() -> dict[str, Any]:
    try:
        import yt_dlp.version as v
        ver = v.__version__
    except Exception:
        return _r("ytdlp", "yt-dlp", "fail", "Yüklü değil: video sitelerinden indirme çalışmaz")
    m = re.match(r"(\d{4})\.(\d{2})\.(\d{2})", ver)
    if m:
        age = (time.time() - time.mktime((int(m.group(1)), int(m.group(2)), int(m.group(3)), 0, 0, 0, 0, 0, -1))) / 86400
        if age > 60:
            return _r("ytdlp", "yt-dlp", "warn", f"{ver} ({age:.0f} gün önce): YouTube değişikliklerinde bozulabilir; Kami'yi güncelle")
    return _r("ytdlp", "yt-dlp", "ok", ver)


def check_bins() -> dict[str, Any]:
    want = {"aria2c": "indirme motoru", "deno": "YouTube imza çözücü"}
    miss = [f"{n} ({why})" for n, why in want.items()
            if not ((paths.BIN_DIR / f"{n}.exe").is_file() or (paths.BIN_DIR / n).is_file() or shutil.which(n))]
    return _r("bins", "Yardımcı programlar", "fail" if miss else "ok", "Eksik: " + ", ".join(miss) if miss else "aria2c, deno")


def check_engine(engine: Any) -> dict[str, Any]:
    try:
        ok = bool(engine and engine.running)
    except Exception:
        ok = False
    return _r("aria2", "İndirme motoru (aria2)", "ok" if ok else "fail",
              "Çalışıyor" if ok else "Çalışmıyor: indirmeler başlamaz",
              "" if ok else "restart_aria2")


def check_native_host() -> dict[str, Any]:
    if os.name != "nt":
        return _r("host", "Tarayıcı eklentisi bağlantısı", "info", "Windows dışı")
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
        return _r("host", "Tarayıcı eklentisi bağlantısı", "warn", "Hiçbir tarayıcıya kayıtlı değil (sağ tık / otomatik yakalama çalışmaz)")
    return _r("host", "Tarayıcı eklentisi bağlantısı", "ok", ", ".join(found))


def _find_ollama_exe() -> str:
    exe = shutil.which("ollama")
    if exe:
        return exe
    cand = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
    return str(cand) if cand.is_file() else ""


def check_ollama() -> dict[str, Any]:
    try:
        import urllib.request
        with urllib.request.urlopen((os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434") + "/api/tags", timeout=1.5) as r:
            models = [m.get("name", "") for m in json.loads(r.read()).get("models", [])]
        return _r("ollama", "Yerel yapay zeka (Ollama)", "ok", ", ".join(models[:6]) or "Çalışıyor, model yok")
    except Exception:
        if _find_ollama_exe():
            return _r("ollama", "Yerel yapay zeka (Ollama)", "warn", "Kurulu ama kapalı", "ollama_start")
        return _r("ollama", "Yerel yapay zeka (Ollama)", "info", "Kurulu değil (isteğe bağlı: yerel Copilot)")


def check_network() -> dict[str, Any]:
    res = []
    for host in ("github.com", "api.cloudflare.com"):
        t0 = time.monotonic()
        try:
            socket.create_connection((host, 443), timeout=3).close()
            res.append(f"{host} {int((time.monotonic() - t0) * 1000)} ms")
        except OSError:
            res.append(f"{host} ULAŞILAMIYOR")
    bad = any("ULAŞILAMIYOR" in x for x in res)
    return _r("net", "İnternet", "warn" if bad else "ok", " · ".join(res))


def check_room() -> dict[str, Any]:
    try:
        from app.core import room
        st = room.SERVER.status()
    except Exception as exc:
        return _r("room", "Kami Oda", "info", f"Durum okunamadı: {type(exc).__name__}")
    if not st.get("on"):
        return _r("room", "Kami Oda", "info", "Kapalı")
    if st.get("stable"):
        return _r("room", "Kami Oda", "ok", "Açık · sabit link çalışıyor" + (" · TURN var" if st.get("turn") else " · TURN yok (mobil veride bağlanamayabilir)"))
    return _r("room", "Kami Oda", "warn", "Açık ama geçici link kullanılıyor (sabit link güncellenemedi)", "room_relink")


def check_log_errors() -> dict[str, Any]:
    f = paths.DATA_DIR / "kami.log"
    if not f.is_file():
        return _r("log", "Son hatalar", "info", "Log yok")
    try:
        with f.open("rb") as fh:
            fh.seek(max(0, f.stat().st_size - 400_000))
            tail = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return _r("log", "Son hatalar", "info", "Log okunamadı")
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
                return _r("spotify", "Spotify PKCE", "warn", "Oturum süresi dolmuş (Kamify'dan tekrar bağlan)")
            return _r("spotify", "Spotify PKCE", "info", "Oturum açılmamış")
        ex = ThreadPoolExecutor(max_workers=1)
        try:
            res = ex.submit(music_hub.spotify_devices).result(timeout=3.0) or {}
        finally:
            ex.shutdown(wait=False, cancel_futures=True)
        devs = res.get("devices") or [] if isinstance(res, dict) else (res or [])
        active = sum(1 for d in devs if d.get("active") or d.get("is_active"))
        return _r("spotify", "Spotify PKCE", "ok", f"Bağlı · {len(devs)} cihaz ({active} aktif)")
    except Exception as exc:
        return _r("spotify", "Spotify PKCE", "warn", f"Durum alınamadı: {type(exc).__name__}")


def check_librespot() -> dict[str, Any]:
    try:
        from app.core import librespot_host
        has_bin = bool(librespot_host.find_binary())
        if not has_bin:
            return _r("librespot", "Dahili oynatıcı (go-librespot)", "info", "Binary yok (Kamify açılınca indirilir)")
        running = bool(librespot_host.is_running())
        paired = bool(librespot_host.has_credentials())
        if running:
            return _r("librespot", "Dahili oynatıcı (go-librespot)", "ok",
                      "Çalışıyor" + (" · eşleşmiş" if paired else " · eşleşme bekliyor"))
        return _r("librespot", "Dahili oynatıcı (go-librespot)", "info",
                  "Hazır (kapalı)" + (" · eşleşmiş" if paired else ""))
    except Exception as exc:
        return _r("librespot", "Dahili oynatıcı (go-librespot)", "warn", f"Durum okunamadı: {type(exc).__name__}")


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
                parts.append(f"son içe aktarma: {ts} ({cnt} kayıt)")
            except Exception:
                parts.append("playnite_import.json okunamadı")
        else:
            parts.append("içe aktarma yok")
        st = "ok" if db.is_file() else "info"
        return _r("playnite", "Playnite kütüphanesi", st, " · ".join(parts))
    except Exception as exc:
        return _r("playnite", "Playnite kütüphanesi", "warn", f"Okunamadı: {type(exc).__name__}")


def check_media_server(media: Any = None) -> dict[str, Any]:
    port = int(getattr(media, "port", 0) or 0)
    if not port:
        return _r("media", "Medya sunucusu", "fail" if media is not None else "info",
                  "Medya sunucusu kapalı" if media is not None else "Başlatılmadı")
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2.0):
            return _r("media", "Medya sunucusu", "ok", f"127.0.0.1:{port} dinliyor")
    except OSError:
        return _r("media", "Medya sunucusu", "fail", f"127.0.0.1:{port} yanıt vermiyor")


def check_bridge_server(bridge: Any = None) -> dict[str, Any]:
    port = int(getattr(bridge, "port", 0) or 0)
    if not port and paths.BRIDGE_INFO_PATH.is_file():
        try:
            port = int(json.loads(paths.BRIDGE_INFO_PATH.read_text("utf-8")).get("port") or 0)
        except Exception:
            port = 0
    if not port:
        return _r("bridge", "Tarayıcı köprüsü", "fail" if bridge is not None else "info", "Port yok")
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2.0):
            return _r("bridge", "Tarayıcı köprüsü", "ok", f"127.0.0.1:{port} dinliyor")
    except OSError:
        return _r("bridge", "Tarayıcı köprüsü", "fail", f"127.0.0.1:{port} yanıt vermiyor")


def check_module_windows(api: Any = None) -> dict[str, Any]:
    if api is None:
        return _r("modwins", "Modül pencereleri", "info", "Kontrol dışı")
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
        return _r("modwins", "Modül pencereleri", "fail", "Yanıt vermeyen: " + ", ".join(bad))
    if open_ok:
        return _r("modwins", "Modül pencereleri", "ok", "Açık & sağlam: " + ", ".join(open_ok))
    return _r("modwins", "Modül pencereleri", "info", "Açık modül penceresi yok")


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
            log.exception("Doktor kontrolü patladı")
            return _r(getattr(fn, "__name__", "?"), getattr(fn, "__name__", "?"), "warn", f"Kontrol çalışmadı: {type(exc).__name__}")

    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(safe, checks))
    ui = list(ui_errors or [])[-10:]
    results.append(_r("ui", "Arayüz (JS) hataları", "warn" if ui else "ok",
                      (f"{len(ui)} hata · son: [{ui[-1]['page']}] {ui[-1]['msg'][:140]}" if ui else "Bu oturumda yok")
                      + (f" · {recoveries} kez kendini toparladı" if recoveries else "")))
    from app.core.extras import APP_VERSION
    summary = {s: sum(1 for r in results if r["status"] == s) for s in ("ok", "warn", "fail", "info")}
    return {"ok": True, "version": APP_VERSION, "python": sys.version.split()[0], "at": int(time.time()),
            "summary": summary, "checks": results, "ui_errors": ui}


def fix_ollama_start() -> dict[str, Any]:
    exe = _find_ollama_exe()
    if not exe:
        return {"ok": False, "message": "Ollama bulunamadı"}
    env = dict(os.environ)
    env.setdefault("OLLAMA_KEEP_ALIVE", "2m")
    subprocess.Popen([exe, "serve"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    return {"ok": True, "message": "Ollama başlatıldı (2 dk VRAM koruma modu)"}


FIXES: dict[str, Callable[[], dict[str, Any]]] = {"copy_virtual_keys": fix_copy_virtual_keys, "ollama_start": fix_ollama_start}
