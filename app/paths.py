r"""Uygulama yollari. PyInstaller ile dondurulmus (kurulu Kami.exe) calismayi da destekler.

Gelistirme:  ROOT = repo, veri = repo/data, kaynaklar = repo.
Kurulu:      ROOT = Kami.exe klasoru (bin/, plugins/, extension/), kaynaklar = _internal (sys._MEIPASS),
             veri = %LOCALAPPDATA%\Kami\data (guncelleme/kaldirma ayarlari ve gecmisi silmez),
             Whisper/UVR araclari = %LOCALAPPDATA%\Kami\tools (ilk kullanimda, onayla).
"""
from __future__ import annotations

import ctypes
import os
import sys
import uuid
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
if FROZEN:
    ROOT = Path(sys.executable).resolve().parent
    RES_DIR = Path(getattr(sys, "_MEIPASS", ROOT))
    USER_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "Kami"
    _default_data = USER_DIR / "data"
else:
    ROOT = Path(__file__).resolve().parent.parent
    RES_DIR = ROOT
    USER_DIR = ROOT
    _default_data = ROOT / "data"

BIN_DIR = ROOT / "bin"
DATA_DIR = Path(os.environ["KAMI_DATA_DIR"]) if os.environ.get("KAMI_DATA_DIR") else _default_data   # testler: ayri klasor
PLUGINS_DIR = ROOT / "plugins"
WEB_DIR = RES_DIR / "app" / "ui" / "web"
TOOLSRC_DIR = RES_DIR / "toolsrc" if FROZEN else ROOT      # alt surec betikleri (app/tools/*.py) duz dosya olarak
# Whisper/UVR: repo .venv'den BAGIMSIZ, arac basina ayri ortam (media-env\whisper, media-env\uvr) -> cuDNN DLL catismasi yok
MEDIA_ENV = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "Kami" / "media-env"
PYLIB_DIR = DATA_DIR / "pylib"                              # kurulu Kami: guncellenmis yt-dlp (PyPI tekerlegi)

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


def setup_frozen() -> None:
    """Kurulu Kami: bin/ PATH'e (ffmpeg, deno, fpcalc yt-dlp'ye gorunsun), guncel yt-dlp onde, ilk acilista
    gelistirme klasorundeki veriler KOPYALANIR (tasinmaz: eski veri yerinde kalir)."""
    if not FROZEN:
        return
    os.environ["PATH"] = str(BIN_DIR) + os.pathsep + os.environ.get("PATH", "")
    if (PYLIB_DIR / "yt_dlp").is_dir():
        sys.path.insert(0, str(PYLIB_DIR))
    migrate_legacy_data()


LEGACY_DATA = [Path.home() / "Projeler" / "kami" / "data"]


def migrate_legacy_data() -> str:
    """DATA_DIR bossa ve eski (gelistirme) veri klasoru varsa icerigini kopyalar. Kopyalanan yol ya da ''."""
    import shutil
    if os.environ.get("KAMI_DATA_DIR") or (DATA_DIR / "settings.json").exists():
        return ""
    for src in LEGACY_DATA:
        if (src / "settings.json").is_file() and src.resolve() != DATA_DIR.resolve():
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            skip = {"bridge.json", "kami.log", "kami.log.1", "kami.log.2", "models", "pylib", "aria2.log"}
            for item in src.iterdir():
                if item.name in skip or item.name.endswith(("-wal", "-shm")) or (DATA_DIR / item.name).exists():
                    continue
                try:
                    if item.suffix == ".db":   # SQLite: tutarli kopya (WAL dahil), acik olsa bile
                        import sqlite3
                        with sqlite3.connect(f"file:{item}?mode=ro", uri=True) as s, \
                                sqlite3.connect(DATA_DIR / item.name) as d:
                            s.backup(d)
                    elif item.is_dir():
                        shutil.copytree(item, DATA_DIR / item.name)
                    else:
                        shutil.copy2(item, DATA_DIR / item.name)
                except OSError:
                    pass
            (DATA_DIR / "migrated_from.txt").write_text(str(src), encoding="utf-8")
            return str(src)
    return ""
