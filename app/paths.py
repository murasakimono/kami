"""Uygulama yollari. PyInstaller ile dondurulmus calismayi da destekler."""
from __future__ import annotations

import ctypes
import os
import sys
import uuid
from pathlib import Path

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent.parent

BIN_DIR = ROOT / "bin"
DATA_DIR = Path(os.environ["KAMI_DATA_DIR"]) if os.environ.get("KAMI_DATA_DIR") else ROOT / "data"   # testler: ayri klasor
PLUGINS_DIR = ROOT / "plugins"
WEB_DIR = ROOT / "app" / "ui" / "web"

ARIA2_EXE = BIN_DIR / "aria2c.exe"
DB_PATH = DATA_DIR / "kami.db"
SETTINGS_PATH = DATA_DIR / "settings.json"
BRIDGE_INFO_PATH = DATA_DIR / "bridge.json"
LOG_PATH = DATA_DIR / "kami.log"

# FOLDERID_Downloads
_FOLDERID_DOWNLOADS = uuid.UUID("{374DE290-123F-4565-9164-39C4925E467B}")


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def downloads_dir() -> Path:
    """Windows'un gercek Indirilenler klasoru (tasinmis olsa bile)."""
    if os.name == "nt":
        try:
            b = _FOLDERID_DOWNLOADS.bytes_le
            guid = _GUID.from_buffer_copy(b)
            out = ctypes.c_wchar_p()
            shell32 = ctypes.windll.shell32
            if shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out)) == 0:
                path = Path(out.value)
                ctypes.windll.ole32.CoTaskMemFree(out)
                return path
        except Exception:
            pass
    return Path.home() / "Downloads"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
