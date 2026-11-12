"""Masaustu butunlesmesi: sistem tepsisi (+ bildirim), Windows'la baslama, genel kisayol.

Hicbiri arayuz (WinForms) is parcacigini beklemez; tepsi ve kisayolun kendi is parcaciklari var.
"""
from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
from ctypes import wintypes
from pathlib import Path
from typing import Callable

from app import paths

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "Kami"


# ---------------------------------------------------------------- Windows'la baslama
def autostart_command() -> str:
    scripts = paths.ROOT / ".venv" / "Scripts"
    exe = scripts / "Kami.exe"   # pythonw kopyasi: Gorev Yoneticisi'nde "Kami" gorunur
    if not exe.exists():
        exe = scripts / "pythonw.exe"
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --tray'
    # gelistirme kopyasi calistirilsa bile kurulu Kami varsa baslangic kaydi ona gitsin
    # (yoksa PC acilisinda .venv'deki surum baslar, kurulu olanin yerine)
    installed = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Kami" / "Kami.exe"
    if installed.is_file():
        return f'"{installed}" --tray'
    return f'"{exe}" "{paths.ROOT / "kami_open.pyw"}" --tray'


def autostart_enabled() -> bool:
    if os.name != "nt":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            val, _ = winreg.QueryValueEx(k, RUN_NAME)
            return bool(val)
    except OSError:
        return False


def set_autostart(enabled: bool) -> None:
    if os.name != "nt":
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, RUN_NAME)
            except FileNotFoundError:
                pass
    log.info("Windows'la baslama: %s", "acik" if enabled else "kapali")


# ---------------------------------------------------------------- sistem tepsisi
class Tray:
    """pystray simgesi. Menu: Goster / Tumunu duraklat / Tumunu surdur / Cikis. Bildirimler bunun uzerinden."""

    def __init__(self, on_show: Callable[[], None], on_pause_all: Callable[[], None],
                 on_resume_all: Callable[[], None], on_quit: Callable[[], None],
                 lang: Callable[[], str]) -> None:
        self.on_show, self.on_pause_all, self.on_resume_all, self.on_quit = on_show, on_pause_all, on_resume_all, on_quit
        self.lang = lang
        self.icon = None
        self._thread: threading.Thread | None = None

    def _text(self, tr: str, en: str) -> str:
        return tr if self.lang() == "tr" else en

    def start(self) -> None:
        if self.icon is not None:
            return
        try:
            import pystray
            from PIL import Image
        except ImportError:
            log.warning("pystray/pillow yok: sistem tepsisi kapali")
            return
        img_path = paths.WEB_DIR / "kami.png"   # uygulama logosu (eklenti simgesi ayri)
        image = Image.open(img_path) if img_path.exists() else Image.new("RGBA", (32, 32), (124, 77, 255, 255))
        M = pystray.MenuItem
        menu = pystray.Menu(
            M(lambda _: self._text("Kami'yi göster", "Show Kami"), lambda: self.on_show(), default=True),
            M(lambda _: self._text("Tümünü duraklat", "Pause all"), lambda: self.on_pause_all()),
            M(lambda _: self._text("Tümünü sürdür", "Resume all"), lambda: self.on_resume_all()),
            pystray.Menu.SEPARATOR,
            M(lambda _: self._text("Çıkış", "Quit"), lambda: self.on_quit()),
        )
        self.icon = pystray.Icon("kami", image, "Kami", menu)
        self._thread = threading.Thread(target=self.icon.run, name="kami-tray", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.icon = None

    @property
    def running(self) -> bool:
        return self.icon is not None

    def notify(self, title: str, message: str) -> bool:
        if self.icon is None:
            return False
        try:
            self.icon.notify(message[:250], title[:60])
            return True
        except Exception:
            log.exception("Bildirim gosterilemedi")
            return False


# ---------------------------------------------------------------- genel kisayol
MOD = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "shift": 0x4, "win": 0x8}
MOD_NOREPEAT = 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012


def parse_hotkey(text: str) -> tuple[int, int]:
    """'ctrl+alt+k' -> (mods, vk). Gecersizse ValueError."""
    parts = [p.strip().lower() for p in (text or "").split("+") if p.strip()]
    if len(parts) < 2:
        raise ValueError("hotkey")
    mods = 0
    for p in parts[:-1]:
        if p not in MOD:
            raise ValueError("hotkey")
        mods |= MOD[p]
    key = parts[-1]
    if len(key) == 1 and key.isascii() and key.isalnum():
        vk = ord(key.upper())
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x70 + int(key[1:]) - 1
    else:
        raise ValueError("hotkey")
    if not mods:
        raise ValueError("hotkey")
    return mods, vk


class HotKey:
    """RegisterHotKey + kendi mesaj dongusu (ayri is parcacigi)."""

    def __init__(self, callback: Callable[[], None]) -> None:
        self.callback = callback
        self._thread: threading.Thread | None = None
        self._tid = 0
        self.error = ""

    def start(self, text: str) -> bool:
        self.stop()
        if os.name != "nt":
            return False
        try:
            mods, vk = parse_hotkey(text)
        except ValueError:
            self.error = "bad"
            return False
        ready = threading.Event()
        result = {"ok": False}

        def run() -> None:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            self._tid = ctypes.windll.kernel32.GetCurrentThreadId()
            ok = user32.RegisterHotKey(None, 1, mods | MOD_NOREPEAT, vk)
            result["ok"] = bool(ok)
            ready.set()
            if not ok:
                log.warning("Genel kisayol kaydedilemedi (%s): baska program kullaniyor olabilir", text)
                return
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    try:
                        self.callback()
                    except Exception:
                        log.exception("Kisayol islemi hata verdi")
            user32.UnregisterHotKey(None, 1)

        self._thread = threading.Thread(target=run, name="kami-hotkey", daemon=True)
        self._thread.start()
        ready.wait(3)
        self.error = "" if result["ok"] else "taken"
        if result["ok"]:
            log.info("Genel kisayol: %s", text)
        return result["ok"]

    def stop(self) -> None:
        if self._thread and self._thread.is_alive() and self._tid:
            ctypes.windll.user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
            self._thread.join(2)
        self._thread = None
        self._tid = 0


def icon_path() -> Path:
    return paths.ROOT / "extension" / "icons" / "128.png"


# ---------------------------------------------------------------- dugmeli Windows bildirimi
def toast(title: str, body: str, actions: list[tuple[str, str]] | None = None, launch: str = "kami://show") -> bool:
    """WinRT ToastNotification (PowerShell). Dugmeler kami:// linki acar -> calisan Kami islem yapar."""
    import base64
    import subprocess
    import xml.sax.saxutils as su
    if os.name != "nt":
        return False
    acts = "".join(f'<action content="{su.escape(lbl)}" activationType="protocol" arguments="{su.escape(uri)}"/>' for lbl, uri in (actions or [])[:3])
    xml = (f'<toast activationType="protocol" launch="{su.escape(launch)}"><visual><binding template="ToastGeneric">'
           f'<text>{su.escape(title[:80])}</text><text>{su.escape(body[:200])}</text></binding></visual>'
           + (f"<actions>{acts}</actions>" if acts else "") + "</toast>")
    ps = ("[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;"
          "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null;"
          "$x = New-Object Windows.Data.Xml.Dom.XmlDocument; $x.LoadXml([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String([Console]::In.ReadToEnd().Trim())));"
          "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Kami.DownloadManager').Show([Windows.UI.Notifications.ToastNotification]::new($x))")
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps], input=base64.b64encode(xml.encode("utf-8")),
                           capture_output=True, timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.returncode == 0
    except Exception:
        log.exception("Bildirim gosterilemedi")
        return False
