"""Win32 pencere yardimcilari (ctypes). GUI is parcacigini BEKLEMEZ.

Neden: pywebview'in on_top/restore/show cagrilari WinForms Invoke ile arayuz is parcacigini bekliyor;
kopru is parcacigindan cagrilinca evaluate_js ile kilitlendi (defter 23, py-spy). Burada sadece
ShowWindowAsync / SetForegroundWindow gibi beklemeyen ya da kisa Win32 cagrilari var.
"""
from __future__ import annotations

import ctypes
import logging
import os
import threading
from ctypes import wintypes

log = logging.getLogger(__name__)

SW_HIDE, SW_SHOW, SW_RESTORE = 0, 5, 9
ASFW_ANY = 0xFFFFFFFF

if os.name == "nt":
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [_EnumProc, wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
    user32.IsWindow.argtypes = [wintypes.HWND]
else:   # testler / diger sistemler
    user32 = kernel32 = None


def find_window(title: str, pid: int | None = None) -> int:
    """Bu surece (pid) ait, basligi tam olarak `title` olan ust duzey pencere (gorunmez olabilir)."""
    if user32 is None:
        return 0
    pid = pid or os.getpid()
    found: list[int] = []

    def cb(hwnd, _):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            if buf.value == title:
                found.append(hwnd)
                return False
        return True

    user32.EnumWindows(_EnumProc(cb), 0)
    return found[0] if found else 0


def allow_foreground(pid: int | None = None) -> None:
    """On plandaki surec (orn. ikinci Kami ornegi) calisan Kami'nin one gelmesine izin verir."""
    if user32 is not None:
        user32.AllowSetForegroundWindow(int(pid) if pid else ASFW_ANY)


def is_visible(hwnd: int) -> bool:
    return bool(user32 and hwnd and user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd))


def is_foreground(hwnd: int) -> bool:
    return bool(user32 and hwnd and user32.GetForegroundWindow() == hwnd)


def hide(hwnd: int) -> None:
    if user32 and hwnd:
        user32.ShowWindowAsync(hwnd, SW_HIDE)


def bring_to_front(hwnd: int) -> bool:
    """Gizliyse goster, kucultulmusse geri getir, one al. Arayuz is parcacigini beklemez
    (ShowWindowAsync); SetForegroundWindow reddedilirse on plandaki is parcacigina baglanip dener."""
    if not (user32 and hwnd and user32.IsWindow(hwnd)):
        return False
    user32.ShowWindowAsync(hwnd, SW_RESTORE if user32.IsIconic(hwnd) else SW_SHOW)
    if user32.SetForegroundWindow(hwnd):
        return True
    fg = user32.GetForegroundWindow()
    fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    me = kernel32.GetCurrentThreadId()
    attached = bool(fg_tid and fg_tid != me and user32.AttachThreadInput(me, fg_tid, True))
    try:
        user32.BringWindowToTop(hwnd)
        ok = bool(user32.SetForegroundWindow(hwnd))
    finally:
        if attached:
            user32.AttachThreadInput(me, fg_tid, False)
    return ok


class WindowFront:
    """Kopru/olay is parcaciklarindan 'pencereyi one getir': hemen doner, isi tek bir yardimci
    is parcacigi yapar (ust uste istekler birlesir). Cagirani asla bekletmez."""

    def __init__(self, title: str) -> None:
        self.title = title
        self.hwnd = 0
        self._pending = threading.Event()
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None

    def _hwnd(self) -> int:
        if not (self.hwnd and user32 and user32.IsWindow(self.hwnd)):
            self.hwnd = find_window(self.title)
        return self.hwnd

    def request(self) -> None:
        self._pending.set()
        with self._lock:
            if self._worker and self._worker.is_alive():
                return
            self._worker = threading.Thread(target=self._run, name="kami-front", daemon=True)
            self._worker.start()

    def _run(self) -> None:
        while self._pending.is_set():
            self._pending.clear()
            try:
                if not bring_to_front(self._hwnd()):
                    log.info("Pencere one getirilemedi (Windows izin vermedi ya da pencere yok)")
            except Exception:
                log.exception("Pencere one getirme hatasi")


def pid_alive(pid: int) -> bool:
    """Surec hala calisiyor mu (kurulum --quit beklemesi icin)."""
    import ctypes
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, int(pid))   # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = ctypes.c_ulong()
        return bool(k32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259   # STILL_ACTIVE
    finally:
        k32.CloseHandle(h)
