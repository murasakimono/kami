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
    "notify_on_complete": True,    # Windows bildirimi (tepsi simgesi uzerinden)
    "notify_on_error": True,
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
    # Real-Debrid (token burada DEGIL: data/rd_token.bin, DPAPI)
    "rd_mode": "ask",              # RD destekli hoster + magnet/.torrent: auto | ask | off
    # Yerel torrent (aria2)
    "torrent_stop_seeding": True,  # indirme bitince paylasimi durdur (kapali: oran 1.0'a kadar paylas)
    "torrent_upload_limit_kib": 0, # 0 = sinirsiz (KiB/s, toplam)
    "torrent_port": 0,             # 0 = otomatik (6881-6999); degisiklik Kami yeniden acilinca gecerli
    "torrent_port_last": 0,        # otomatikte bir kez secilen port (DHT/guvenlik duvari icin sabit kalsin)
    "torrent_tracker_update": True,# guncel herkese acik izleyici listesini gunde bir indir
    # Asama 6a: uygulama temelleri
    "tray_enabled": True,          # sistem tepsisi simgesi (bildirimler de bunun uzerinden)
    "close_to_tray": True,         # X: kapatma yerine tepsiye gizle
    "autostart": False,            # Windows'la baslama (HKCU Run; tepside baslar)
    "hotkey_enabled": True,
    "hotkey": "ctrl+alt+k",        # genel kisayol: Kami'yi one getir + panodaki linki sor
    "speed_limit_preset_kib": 2048,# arac cubugundaki "hiz siniri" dugmesinin degeri
    "schedule_enabled": False,     # zamanlayici: baslangicta tumunu surdur, bitiste duraklat
    "schedule_start": "02:00",
    "schedule_stop": "08:00",
    "defender_mode": "exec_archive",  # off | exec_archive (calistirilabilir + arsiv) | all
    "checksum_verify": True,       # site/link SHA256 verdiyse indirme bitince dogrula
    "update_check": True,          # GitHub Releases'ta yeni surum var mi (gunde bir)
    "update_last": 0,
    # Ag: bazi sunucularin IPv6 adresi bu agda cevapsiz (RD: 21 sn x adres). Kapali = aria2 sadece IPv4.
    "aria2_ipv6": False,           # degisiklik Kami yeniden acilinca gecerli
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
        elif key == "torrent_port" and not (v == 0 or 1024 <= v <= 65535):
            raise ValueError("torrent_port")
        elif v < 0:
            v = 0
        return v
    if isinstance(default, list):
        if isinstance(value, str):
            value = [x.strip() for x in value.replace("\n", ",").split(",")]
        return [str(x).strip().lower() for x in value if str(x).strip()]
    if key == "rd_mode" and str(value) not in ("auto", "ask", "off"):
        raise ValueError("rd_mode")
    if key == "defender_mode" and str(value) not in ("off", "exec_archive", "all"):
        raise ValueError("defender_mode")
    if key in ("schedule_start", "schedule_stop"):
        from app.core.extras import _hm
        _hm(value)   # gecersizse ValueError
        h, m = str(value).strip().split(":")
        return f"{int(h):02d}:{m}"
    if key == "hotkey":
        from app.core.desktop import parse_hotkey
        parse_hotkey(str(value))
        return str(value).strip().lower().replace(" ", "")
    return str(value)
