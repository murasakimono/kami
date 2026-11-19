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
from typing import Callable
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
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.c_void_p]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.c_void_p]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.GetDpiForWindow.argtypes = [wintypes.HWND]
    user32.GetDpiForWindow.restype = wintypes.UINT
    user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HANDLE, wintypes.BOOL]
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    gdi32.CreateRoundRectRgn.restype = wintypes.HANDLE
    gdi32.CreateRoundRectRgn.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
else:   # testler / diger sistemler
    user32 = kernel32 = gdi32 = dwmapi = None


def set_caption_color(title: str = "", hwnd: int = 0, rgb: tuple[int, int, int] = (13, 10, 18)) -> bool:
    """Windows 11 DWM baslik cubugu ve kenarlik rengini uygulama temasiyla eslestirir (#0D0A12)."""
    if not (user32 and dwmapi):
        return False
    h = int(hwnd or find_window(title))
    if not (h and user32.IsWindow(h)):
        return False
    r, g, b = rgb
    colorref = ctypes.c_uint32((b << 16) | (g << 8) | r)
    try:
        dwmapi.DwmSetWindowAttribute(h, 35, ctypes.byref(colorref), ctypes.sizeof(colorref))  # DWMWA_CAPTION_COLOR
        border = ctypes.c_uint32((0x36 << 16) | (0x22 << 8) | 0x2A)  # #2A2236
        dwmapi.DwmSetWindowAttribute(h, 34, ctypes.byref(border), ctypes.sizeof(border))      # DWMWA_BORDER_COLOR
        return True
    except Exception:
        return False


def round_pill(title: str, hwnd: int = 0) -> bool:
    """Mini-Ada vb. cercevesiz pencereleri tam hap (kapsul) seklinde kirpar; dis kose dikdortgeni gorunmez."""
    if not (user32 and gdi32):
        return False
    h = int(hwnd or find_window(title))
    if not (h and user32.IsWindow(h)):
        return False
    r = _RECT()
    if not user32.GetClientRect(h, ctypes.byref(r)):
        return False
    w, hh = max(2, int(r.right - r.left)), max(2, int(r.bottom - r.top))
    if dwmapi is not None:
        try:   # DWMWCP_DONOTROUND (1): Win11 DWM kapsul rgn disina ikinci dikdortgen golge/cerceve cizmesin
            pref = ctypes.c_int(1)
            dwmapi.DwmSetWindowAttribute(h, 33, ctypes.byref(pref), ctypes.sizeof(pref))
        except Exception:
            pass
    rgn = gdi32.CreateRoundRectRgn(0, 0, w + 1, hh + 1, hh, hh)
    if not rgn:
        return False
    return bool(user32.SetWindowRgn(h, rgn, True))


def resize_pill(title: str, width: int, height: int, hwnd: int = 0) -> bool:
    """Mini-Ada vb. cercevesiz hapi yatay merkezini koruyarak yeniden boyutlandirir ve maskeler."""
    if not (user32 and gdi32):
        return False
    h = int(hwnd or find_window(title))
    if not (h and user32.IsWindow(h)):
        return False
    try:
        dpi = user32.GetDpiForWindow(h) or 96
    except Exception:
        dpi = 96
    scale = dpi / 96.0
    pw = max(120, int(round(width * scale)))
    ph = max(28, int(round(height * scale)))
    rc = _RECT()
    if not user32.GetWindowRect(h, ctypes.byref(rc)):
        return False
    cx = (rc.left + rc.right) // 2
    nx = max(0, cx - pw // 2)
    user32.SetWindowPos(h, 0, nx, rc.top, pw, ph, 0x0004 | 0x0010 | 0x0020)  # NOZORDER|NOACTIVATE|FRAMECHANGED
    return round_pill(title, hwnd=h)


def foreground_process_name() -> str:
    """Aktif on plan penceresinin surec adini dondurur (parola yoneticisi pano dislama icin)."""
    if not user32:
        return ""
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""
        hproc = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not hproc:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(512)
            sz = wintypes.DWORD(512)
            if kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(sz)):
                return os.path.basename(buf.value).lower()
        finally:
            kernel32.CloseHandle(hproc)
    except Exception:
        pass
    return ""


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


_TINTED: set[int] = set()
CAPTION_BG = (11, 9, 16)      # Sunak arka plani (#0B0910) ile ayni: baslik cubugu uygulamanin devami gibi gorunur
CAPTION_FG = (226, 220, 240)
CAPTION_BORDER = (28, 18, 40)


def _colorref(rgb: tuple[int, int, int]) -> ctypes.c_uint:
    r, g, b = rgb
    return ctypes.c_uint(r | (g << 8) | (b << 16))


def tint_caption(hwnd: int, bg: tuple[int, int, int] = CAPTION_BG, fg: tuple[int, int, int] = CAPTION_FG) -> bool:
    """Windows 11: standart baslik cubugunu (gri #202020) uygulama rengine boyar. Win10'da sadece koyu mod uygulanir."""
    if not (dwmapi and hwnd):
        return False
    ok = False
    try:
        h = wintypes.HWND(int(hwnd))
        dark = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(h, 20, ctypes.byref(dark), ctypes.sizeof(dark))   # DWMWA_USE_IMMERSIVE_DARK_MODE
        for attr, val in ((35, _colorref(bg)), (36, _colorref(fg)), (34, _colorref(CAPTION_BORDER))):   # CAPTION / TEXT / BORDER
            ok = (dwmapi.DwmSetWindowAttribute(h, attr, ctypes.byref(val), ctypes.sizeof(val)) == 0) or ok
    except Exception:
        log.debug("tint_caption", exc_info=True)
    return ok


def tint_own_windows(pid: int | None = None) -> int:
    """Bu surecin gorunur, baslik cubuklu tum pencerelerini bir kez boyar (yeni acilan modul pencereleri dahil)."""
    if user32 is None:
        return 0
    pid = pid or os.getpid()
    for dead in [h for h in _TINTED if not user32.IsWindow(h)]:   # kapanan pencerenin tutamaci yeniden kullanilabilir
        _TINTED.discard(dead)
    todo: list[int] = []

    def cb(hwnd, _):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and int(hwnd) not in _TINTED and user32.IsWindowVisible(hwnd):
            style = user32.GetWindowLongW(hwnd, -16)
            if style & 0x00C00000 == 0x00C00000:   # WS_CAPTION
                todo.append(int(hwnd))
        return True

    user32.EnumWindows(_EnumProc(cb), 0)
    for h in todo:
        tint_caption(h)
        _TINTED.add(h)
    return len(todo)


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
        self.on_missing: Callable[[], None] | None = None   # pencere yoksa (kapanmis) yeniden kurar

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
                hwnd = self._hwnd()
                if not hwnd and self.on_missing is not None:
                    # Pencere yok edilmis ama surec (tepsi/mini kart) yasiyor: "hic gelmiyor" yerine yeniden kur
                    log.warning("%s penceresi bulunamadi; yeniden olusturuluyor", self.title)
                    self.on_missing()
                    continue
                if not bring_to_front(hwnd):
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


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _MONINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", _RECT), ("rcWork", _RECT), ("dwFlags", wintypes.DWORD)]


class MiniWindow:
    """Kami Player'i YouTube PiP'i gibi kucuk, cercevesiz, hep ustte bir karta cevirir; geri alinca eski haline doner.
    Pencere stilini Win32 ile degistirir (GWL_STYLE), boyut/konum SetWindowPos ile (is parcacigindan guvenli)."""
    GWL_STYLE = -16
    FRAME = 0x00C00000 | 0x00040000 | 0x00020000 | 0x00010000 | 0x00080000   # CAPTION|THICKFRAME|MIN|MAX|SYSMENU
    SWP_NOSIZE, SWP_NOZORDER, SWP_FRAMECHANGED, SWP_SHOWWINDOW, SWP_ASYNC = 0x1, 0x4, 0x20, 0x40, 0x4000

    def __init__(self, title: str) -> None:
        self.title = title
        self.saved: tuple | None = None

    def _hwnd(self) -> int:
        return find_window(self.title)

    @staticmethod
    def _api():
        u = user32
        u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        u.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        u.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        u.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(_RECT)]
        u.MonitorFromWindow.restype = wintypes.HANDLE
        u.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        u.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MONINFO)]
        u.IsZoomed.argtypes = [wintypes.HWND]
        u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        u.GetDpiForWindow.argtypes = [wintypes.HWND]
        u.GetDpiForWindow.restype = wintypes.UINT
        return u

    def _work(self, hwnd: int) -> _RECT:
        u = self._api()
        mi = _MONINFO(); mi.cbSize = ctypes.sizeof(_MONINFO)
        u.GetMonitorInfoW(u.MonitorFromWindow(hwnd, 2), ctypes.byref(mi))
        return mi.rcWork

    def _scale(self, hwnd: int) -> float:
        try:
            return (self._api().GetDpiForWindow(hwnd) or 96) / 96
        except Exception:
            return 1.0

    def enter(self, width: int, height: int) -> bool:
        if user32 is None:
            return False
        hwnd = self._hwnd()
        if not hwnd:
            return False
        u = self._api()
        if u.IsZoomed(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        if self.saved is None:
            r = _RECT(); u.GetWindowRect(hwnd, ctypes.byref(r))
            self.saved = (u.GetWindowLongPtrW(hwnd, self.GWL_STYLE), r.left, r.top, r.right - r.left, r.bottom - r.top)
        style = self.saved[0]
        u.SetWindowLongPtrW(hwnd, self.GWL_STYLE, style & ~self.FRAME)
        k = self._scale(hwnd)
        w, h = int(width * k), int(height * k)
        wa = self._work(hwnd)
        x, y = wa.right - w - int(16 * k), wa.bottom - h - int(16 * k)
        u.SetWindowPos(hwnd, -1, x, y, w, h, self.SWP_FRAMECHANGED | self.SWP_SHOWWINDOW | self.SWP_ASYNC)   # HWND_TOPMOST
        try:   # Windows 11: yuvarlak koseler
            pref = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), 33, ctypes.byref(pref), ctypes.sizeof(pref))
        except Exception:
            pass
        return True

    def resize(self, width: int, height: int) -> None:
        hwnd = self._hwnd()
        if not hwnd or self.saved is None:
            return
        u = self._api()
        r = _RECT(); u.GetWindowRect(hwnd, ctypes.byref(r))
        k = self._scale(hwnd)
        w, h = int(width * k), int(height * k)
        u.SetWindowPos(hwnd, -1, r.right - w, r.bottom - h, w, h, self.SWP_ASYNC)

    def move(self, dx: int, dy: int) -> None:
        hwnd = self._hwnd()
        if not hwnd or self.saved is None:
            return
        u = self._api()
        r = _RECT(); u.GetWindowRect(hwnd, ctypes.byref(r))
        k = self._scale(hwnd)
        u.SetWindowPos(hwnd, 0, r.left + int(dx * k), r.top + int(dy * k), 0, 0, self.SWP_NOSIZE | self.SWP_NOZORDER | self.SWP_ASYNC)

    def leave(self) -> bool:
        hwnd = self._hwnd()
        if not hwnd or self.saved is None:
            self.saved = None
            return False
        u = self._api()
        style, x, y, w, h = self.saved
        self.saved = None
        u.SetWindowLongPtrW(hwnd, self.GWL_STYLE, style)
        u.SetWindowPos(hwnd, -2, x, y, w, h, self.SWP_FRAMECHANGED | self.SWP_SHOWWINDOW | self.SWP_ASYNC)   # HWND_NOTOPMOST
        return True
