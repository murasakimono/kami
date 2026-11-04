"""JSON tabanli ayarlar. Gizli bilgi (token vb.) buraya YAZILMAZ; onlar DPAPI ile ayri saklanir."""
from __future__ import annotations

import copy
import json
import logging
import threading
from pathlib import Path
from typing import Any

from app import paths

log = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    "language": "tr",              # tr | en
    "theme": "dark",               # dark | light
    "download_dir": "",            # bos = Windows Indirilenler klasoru
    "use_category_folders": True,  # Video, Muzik, Arsiv ... alt klasorleri
    "connections": 16,             # dosya basina baglanti (aria2 en fazla 16)
    "max_concurrent": 3,           # ayni anda inen dosya sayisi
    "max_tries": 5,
    "speed_limit_kib": 0,          # 0 = sinirsiz (KiB/s, toplam)
    # Tarayici yakalama
    "capture_enabled": True,
    "capture_min_size_kib": 1024,  # bundan kucuk dosyalari tarayici indirsin (boyut biliniyorsa)
    "capture_exclude_hosts": [],   # ornek: ["example.com"]
    "confirm_extensions": ["exe", "msi", "apk", "bat", "cmd", "ps1", "scr", "vbs", "jar"],
    "notify_on_complete": True,
    "clipboard_watch": True,       # desteklenen link kopyalaninca "indireyim mi?"
    # Medya (yt-dlp)
    "media_format": "mp4",         # mp4 | mp3
    "media_quality": "best",       # best | 2160 | 1440 | 1080 | 720 | 480 | 360
    "media_audio_kbps": 320,       # 320 | 256 | 192 | 128
    "media_subs": True,            # insan yapimi EN/TR altyazi gom (otomatik altyazi yok)
    "media_embed": True,           # kapak + etiket + bolum gom
    "media_sponsorblock": "mark",  # mark | remove | off
    "ytdlp_autoupdate": True,
    "ytdlp_last_update": 0,
}


class Settings:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or paths.SETTINGS_PATH
        self._lock = threading.RLock()
        self._data: dict[str, Any] = copy.deepcopy(DEFAULTS)
        self._listeners: list = []
        self.load()

    def load(self) -> None:
        with self._lock:
            if self.path.exists():
                try:
                    stored = json.loads(self.path.read_text(encoding="utf-8"))
                    if isinstance(stored, dict):
                        for k, v in stored.items():
                            if k in DEFAULTS:
                                self._data[k] = v
                except Exception:
                    log.exception("Ayarlar okunamadi, varsayilanlar kullaniliyor")

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            if key in self._data:
                return copy.deepcopy(self._data[key])
            return default

    def all(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._data)

    def set(self, key: str, value: Any) -> None:
        if key not in DEFAULTS:
            raise KeyError(f"Bilinmeyen ayar: {key}")
        value = _coerce(key, value)
        with self._lock:
            self._data[key] = value
            self.save()
        for cb in list(self._listeners):
            try:
                cb(key, value)
            except Exception:
                log.exception("Ayar dinleyicisi hata verdi")

    def on_change(self, cb) -> None:
        self._listeners.append(cb)


def _coerce(key: str, value: Any) -> Any:
    default = DEFAULTS[key]
    if isinstance(default, bool):
        return bool(value)
    if isinstance(default, int):
        v = int(value)
        if key == "connections":
            v = max(1, min(16, v))
        elif key == "max_concurrent":
            v = max(1, min(20, v))
        elif v < 0:
            v = 0
        return v
    if isinstance(default, list):
        if isinstance(value, str):
            value = [x.strip() for x in value.replace("\n", ",").split(",")]
        return [str(x).strip().lower() for x in value if str(x).strip()]
    return str(value)
