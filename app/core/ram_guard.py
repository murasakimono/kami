"""Kami RAM Yonetimi & Oyun Kalkani: hafif bellek olcumu, bos pencere temizligi ve oyun algilama."""
from __future__ import annotations

import gc
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

MODULE_WIN_ATTRS: tuple[tuple[str, str], ...] = (
    ("player", "_player_win"),
    ("picture", "_picture_win"),
    ("studio", "_studio_win"),
    ("reader", "_reader_win"),
    ("games", "_games_win"),
    ("music", "_music_win"),
    ("cleaner", "_cleaner_win"),
    ("enhance", "_enhance_win"),
    ("musictag", "_musictag_win"),
    ("room", "_room_win"),
)

KNOWN_COMPETITIVE_EXES: frozenset[str] = frozenset({
    "cs2.exe",
    "csgo.exe",
    "league of legends.exe",
    "valorant.exe",
    "valorant-win64-shipping.exe",
    "r5apex.exe",
    "overwatch.exe",
    "dota2.exe",
    "rainbowsix.exe",
    "rainbowsix_vulkan.exe",
    "fortniteclient-win64-shipping.exe",
    "tslgame.exe",
    "pubg.exe",
    "rocketleague.exe",
})

_IGNORE_EXES: frozenset[str] = frozenset({
    "",
    "kami.exe",
    "python.exe",
    "pythonw.exe",
    "msedgewebview2.exe",
    "explorer.exe",
    "dwm.exe",
    "shellexperiencehost.exe",
    "searchhost.exe",
    "applicationframehost.exe",
    "lockapp.exe",
    "taskmgr.exe",
    "cmd.exe",
    "powershell.exe",
    "pwsh.exe",
    "windowsterminal.exe",
    "code.exe",
    "brave.exe",
    "chrome.exe",
    "msedge.exe",
})


def _open_window_names(api: Any) -> list[str]:
    if api is None:
        return []
    out: list[str] = []
    for name, attr in MODULE_WIN_ATTRS:
        if getattr(api, attr, None) is not None:
            out.append(name)
    return out


def _ctypes_process_rss_mb(pid: int) -> float:
    """psutil olmadan da mevcut surec RSS bilgisini okuyabilmek icin hafif ctypes yedegi."""
    if os.name != "nt":
        return 0.0
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        h = k32.OpenProcess(0x0400 | 0x0010, False, pid)
        if not h:
            return 0.0
        try:
            pmc = PROCESS_MEMORY_COUNTERS()
            pmc.cb = ctypes.sizeof(pmc)
            if psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb):
                return float(pmc.WorkingSetSize) / (1024.0 * 1024.0)
        finally:
            k32.CloseHandle(h)
    except Exception:
        pass
    return 0.0


def get_memory_stats(api: Any = None) -> dict[str, Any]:
    """Kami Python sureci ve bagli WebView2 cocuk sureclerinin anlik RAM kullanimi (MB)."""
    py_mb = 0.0
    wv_mb = 0.0
    wv_procs = 0
    child_mb = 0.0
    pid = os.getpid()
    try:
        import psutil

        me = psutil.Process(pid)
        py_mb = me.memory_info().rss / (1024.0 * 1024.0)
        for ch in me.children(recursive=True):
            try:
                nm = (ch.name() or "").lower()
                rss_mb = ch.memory_info().rss / (1024.0 * 1024.0)
                if "msedgewebview2" in nm:
                    wv_mb += rss_mb
                    wv_procs += 1
                else:
                    child_mb += rss_mb
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        py_mb = _ctypes_process_rss_mb(pid)

    total_mb = py_mb + wv_mb + child_mb
    return {
        "total_mb": round(total_mb, 1),
        "python_mb": round(py_mb, 1),
        "webview_mb": round(wv_mb, 1),
        "other_mb": round(child_mb, 1),
        "webview_procs": wv_procs,
        "open_windows": _open_window_names(api),
    }


def has_active_background_work(api: Any = None) -> dict[str, Any]:
    """Asla kesilmemesi gereken aktif arka plan islerini kontrol eder (AI/indirme/ses/render)."""
    dl_active = False
    ai_active = False
    audio_active = False
    enhance_active = False
    conv_active = False

    if api is not None:
        audio_active = bool(getattr(api, "_thumb_playing", False))
        mgr = getattr(api, "_manager", None)
        if mgr is not None:
            try:
                for d in mgr.snapshot():
                    st = getattr(getattr(d, "status", None), "value", getattr(d, "status", ""))
                    if str(st) == "active":
                        dl_active = True
                    ex = getattr(d, "extra", None) or {}
                    for ak in ("whisper", "uvr", "lyrics"):
                        if ex.get(f"ai_{ak}") in ("running", "queued"):
                            ai_active = True
            except Exception:
                pass
        if getattr(api, "_lrc_cancels", None):
            ai_active = True
        ai_q = getattr(api, "_ai", None)
        if ai_q is not None and getattr(ai_q, "_cancel", None) is not None:
            ai_active = True
        try:
            with getattr(api, "_conv_lock", threading.Lock()):
                for cj in getattr(api, "_conv_jobs", []) or []:
                    if cj.get("state") in ("running", "queued"):
                        conv_active = True
                        break
        except Exception:
            pass

    ve = sys.modules.get("app.core.video_enhance")
    if ve is not None:
        try:
            with ve._LOCK:
                enhance_active = any(j.get("state") == "running" for j in ve._JOBS.values())
        except Exception:
            pass

    return {
        "downloads": dl_active,
        "ai": ai_active,
        "audio": audio_active,
        "enhance": enhance_active,
        "converter": conv_active,
        "any_busy": any((dl_active, ai_active, audio_active, enhance_active, conv_active)),
    }


def evaluate_foreground(
    exe_name: str,
    known_game_exes: set[str] | frozenset[str] = frozenset(),
    profiles: dict[str, str] | None = None,
    exe_full_path: str = "",
    known_game_dirs: tuple[str, ...] | list[str] = (),
) -> tuple[str, str]:
    """On plandaki .exe'yi oyun kalkanina gore siniflandirir -> (exe, 'competitive'|'story') | ('', '')."""
    base = Path(str(exe_name or "").strip()).name.lower()
    if not base or base in _IGNORE_EXES:
        return ("", "")

    prof_map = {str(k).strip().lower(): str(v).strip().lower() for k, v in (profiles or {}).items() if str(k).strip()}
    if base in prof_map:
        p = prof_map[base]
        if p == "off":
            return ("", "")
        if p in ("competitive", "story"):
            return (base, p)

    if base in KNOWN_COMPETITIVE_EXES:
        return (base, "competitive")

    known_low = {str(x).strip().lower() for x in (known_game_exes or ()) if str(x).strip()}
    if base in known_low:
        return (base, "story")

    full_low = str(exe_full_path or "").strip().lower()
    if full_low and known_game_dirs:
        for pfx in known_game_dirs:
            norm_pfx = str(pfx or "").strip().lower()
            if len(norm_pfx) > 4 and full_low.startswith(norm_pfx):
                return (base, "story")

    return ("", "")


def _foreground_process_paths() -> tuple[str, str]:
    """Windows on plan penceresinin (exe_adi, tam_yol) bilgisini doner."""
    if os.name != "nt":
        return ("", "")
    try:
        import ctypes
        from ctypes import wintypes

        u32 = ctypes.WinDLL("user32", use_last_error=True)
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        hwnd = u32.GetForegroundWindow()
        if not hwnd:
            return ("", "")
        pid = wintypes.DWORD(0)
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value or pid.value == os.getpid():
            return ("", "")
        h = k32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ("", "")
        try:
            buf = ctypes.create_unicode_buffer(520)
            sz = wintypes.DWORD(len(buf))
            if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(sz)):
                full = str(buf.value or "")
                return (Path(full).name, full)
        finally:
            k32.CloseHandle(h)
    except Exception:
        pass
    return ("", "")


class GameShield:
    """Oyun acildiginda bos arayuzu uyutan hafif arka plan gozlemcisi."""

    def __init__(
        self,
        settings: Any,
        on_enter: Callable[[str, str], None] | None = None,
        on_leave: Callable[[], None] | None = None,
        interval: float = 5.0,
    ) -> None:
        self.settings = settings
        self.on_enter = on_enter
        self.on_leave = on_leave
        self.interval = max(1.0, float(interval))
        self.active = False
        self.active_exe = ""
        self.active_profile = ""
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._game_dirs_cache: list[str] = []
        self._game_dirs_t = 0.0

    def _known_dirs(self) -> list[str]:
        now = time.time()
        if self._game_dirs_cache and now - self._game_dirs_t < 300:
            return self._game_dirs_cache
        dirs: list[str] = []
        try:
            from app.core import games as gm
            pm = getattr(getattr(gm, "TRACKER", None), "_pm", None) or []
            if pm:
                dirs = [str(row[0]) for row in pm if row and len(str(row[0])) > 4]
            else:
                custom = gm._load_json(gm._custom_games_path()).get("items") or []
                for g in gm._scan_steam() + gm._scan_epic() + gm._scan_gog() + gm._scan_riot() + custom:
                    p = str(g.get("path") or "").strip().lower().rstrip("\\/")
                    if len(p) > 4:
                        dirs.append(p + os.sep)
        except Exception:
            pass
        self._game_dirs_cache = dirs
        self._game_dirs_t = now
        return dirs

    def tick_once(
        self,
        fg_exe: str | None = None,
        fg_path: str | None = None,
        known_game_exes: set[str] | frozenset[str] = frozenset(),
    ) -> tuple[str, str]:
        if not bool(self.settings.get("game_shield_enabled", True)):
            if self.active:
                self.active = False
                self.active_exe = ""
                self.active_profile = ""
                if callable(self.on_leave):
                    try:
                        self.on_leave()
                    except Exception:
                        log.debug("game shield on_leave", exc_info=True)
            return ("", "")

        if fg_exe is None:
            fg_exe, fg_path = _foreground_process_paths()
        profiles = self.settings.get("game_shield_profiles") or {}
        known_dirs = self._known_dirs() if (fg_path or "") else ()
        exe, prof = evaluate_foreground(
            fg_exe or "",
            known_game_exes=known_game_exes,
            profiles=profiles,
            exe_full_path=fg_path or "",
            known_game_dirs=known_dirs,
        )
        if exe and (not self.active or self.active_exe != exe or self.active_profile != prof):
            self.active = True
            self.active_exe = exe
            self.active_profile = prof
            if callable(self.on_enter):
                try:
                    self.on_enter(exe, prof)
                except Exception:
                    log.debug("game shield on_enter", exc_info=True)
        elif not exe and self.active:
            self.active = False
            self.active_exe = ""
            self.active_profile = ""
            if callable(self.on_leave):
                try:
                    self.on_leave()
                except Exception:
                    log.debug("game shield on_leave", exc_info=True)
        return (self.active_exe, self.active_profile)

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.tick_once()
            except Exception:
                log.debug("game shield tick", exc_info=True)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="kami-game-shield", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


_MODULE_WIN_TITLES: dict[str, str] = {
    "player": "Kami Player",
    "picture": "Kami Picture",
    "studio": "Kami Studio",
    "reader": "Kami Reader",
    "games": "Kami Games",
    "music": "Kamify",
    "cleaner": "Kami Cleaner",
    "enhance": "Kami İyileştirici",
    "musictag": "Kami Müzik Etiket",
    "room": "Kami Oda",
}


def purge_idle_windows(api: Any = None, include_visible: bool = False) -> dict[str, Any]:
    """Gizli / bos modül WebView2 pencerelerini bellegi iade edecek sekilde kapatir (aktif sese/ise dokunmaz)."""
    before = get_memory_stats(api)
    work = has_active_background_work(api)
    closed: list[str] = []
    skipped: list[str] = []

    if api is not None:
        winwin = None
        if os.name == "nt":
            try:
                from app.core import winwin as _ww
                winwin = _ww
            except Exception:
                winwin = None
        for mod_name, attr in MODULE_WIN_ATTRS:
            w = getattr(api, attr, None)
            if w is None or w is getattr(api, "_window", None):
                continue
            if mod_name == "music" and work.get("audio"):
                skipped.append(mod_name)
                continue
            if not include_visible and winwin is not None:
                title = _MODULE_WIN_TITLES.get(mod_name, "")
                if title:
                    try:
                        hwnd = winwin.find_window(title)
                        if hwnd and winwin.is_visible(hwnd):
                            skipped.append(mod_name)
                            continue
                    except Exception:
                        pass
            try:
                setattr(w, "_kami_allow_destroy", True)
                w.destroy()
                setattr(api, attr, None)
                closed.append(mod_name)
            except Exception:
                log.debug("bos pencere kapatilamadi: %s", mod_name, exc_info=True)

    gc.collect()
    if os.name == "nt":
        try:
            import ctypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.SetProcessWorkingSetSize(k32.GetCurrentProcess(), ctypes.c_size_t(-1), ctypes.c_size_t(-1))
        except Exception:
            pass

    after = get_memory_stats(api)
    freed = max(0.0, round(before["total_mb"] - after["total_mb"], 1))
    return {
        "ok": True,
        "closed": closed,
        "skipped": skipped,
        "before_mb": before["total_mb"],
        "after_mb": after["total_mb"],
        "freed_mb": freed,
        "stats": after,
        "work": work,
    }

