"""Veri modelleri."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Status(StrEnum):
    CONFIRM = "confirm"      # kullanici onayi bekliyor (calistirilabilir dosya vb.)
    QUEUED = "queued"        # motora verilmeyi bekliyor
    WAITING = "waiting"      # motorda sirada
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETE = "complete"
    ERROR = "error"
    REMOVED = "removed"

    @property
    def is_finished(self) -> bool:
        return self in (Status.COMPLETE, Status.ERROR, Status.REMOVED)


@dataclass
class DownloadRequest:
    """Bir indirme istegi: tarayicidan, arayuzden ya da bir Resolver'dan gelir."""
    url: str
    filename: str = ""                 # bos = sunucudan/URL'den belirlenir
    referer: str = ""
    headers: dict[str, str] = field(default_factory=dict)   # Cookie, User-Agent ...
    size: int = 0                      # biliniyorsa bayt
    mime: str = ""
    source: str = "ui"                 # ui | browser | context_menu | plugin:<ad>
    directory: str = ""                # bos = kategori klasoru
    page_url: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    kind: str = "file"                 # file (aria2) | media (yt-dlp)
    options: dict[str, Any] = field(default_factory=dict)   # medya secenekleri


@dataclass
class Download:
    id: int
    url: str
    filename: str
    directory: str
    category: str
    status: Status
    size: int = 0
    downloaded: int = 0
    speed: int = 0                     # bayt/sn (kalici degil)
    connections: int = 0               # anlik baglanti sayisi (kalici degil)
    gid: str = ""
    error: str = ""
    referer: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    source: str = "ui"
    page_url: str = ""
    max_conn: int = 0                  # 0 = ayardaki deger; sunucu sinirlarsa otomatik dusurulur
    created_at: float = 0.0
    finished_at: float = 0.0
    kind: str = "file"                 # file (aria2) | media (yt-dlp)
    options: dict[str, Any] = field(default_factory=dict)
    phase: str = ""                    # medya: downloading | processing (kalici degil)
    position: float = 0.0              # liste sirasi (buyuk = ustte)
    extra: dict[str, Any] = field(default_factory=dict)   # scan, sha256, checksum ...

    @property
    def path(self) -> str:
        import os
        return os.path.join(self.directory, self.filename) if self.filename else ""

    def to_public(self) -> dict[str, Any]:
        """Arayuze gonderilecek hali (basliklar/cerezler gizli)."""
        d = asdict(self)
        d.pop("headers", None)
        opts = d.pop("options", None) or {}
        d["media_format"] = opts.get("format", "")
        d["status"] = str(self.status)
        d["path"] = self.path
        return d
