"""Bulut paylasim linkleri (Yandex Disk, Mail.ru, Pixeldrain, GoFile, Dropbox, Drive, Mediafire, MEGA).

Akis: link -> CloudProvider.list() -> CloudListing (dosya agaci) -> arayuzde secim
      -> secilen her dosya icin CloudProvider.file_request() -> aria2 kuyrugu (cok baglanti).
Klasor paylasimlari alt klasor yapisi korunarak <indirme klasoru>/<paylasim adi>/<alt yol> altina iner.
"""
from __future__ import annotations

import logging
import re
import secrets
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")


class CloudError(Exception):
    """Kullaniciya gosterilecek hata. code arayuzde err_<code> olarak cevrilir."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


@dataclass
class CloudFile:
    path: str                      # paylasim kokune gore "alt/klasor/dosya.ext"
    size: int = 0
    url: str = ""                  # dogrudan link (bos = file_request() cozer)
    headers: dict[str, str] = field(default_factory=dict)
    ref: Any = None                # saglayiciya ozel (dosya kimligi, anahtar ...)

    @property
    def name(self) -> str:
        return self.path.rsplit("/", 1)[-1]

    @property
    def folder(self) -> str:
        return self.path.rsplit("/", 1)[0] if "/" in self.path else ""


@dataclass
class CloudListing:
    provider: str
    title: str                     # paylasim adi (klasor adi ya da dosya adi)
    files: list[CloudFile]
    is_folder: bool = True
    url: str = ""
    note: str = ""                 # arayuzde gosterilecek kisa not (orn. "zip olarak iner")
    ctx: dict[str, Any] = field(default_factory=dict)   # saglayiciya ozel (token, cerez ...)

    def public(self, token: str) -> dict[str, Any]:
        return {"token": token, "provider": self.provider, "title": self.title, "is_folder": self.is_folder,
                "note": self.note, "total": sum(f.size for f in self.files),
                "files": [{"path": f.path, "size": f.size} for f in self.files]}


class CloudProvider(ABC):
    name: str = "cloud"
    hosts: tuple[str, ...] = ()            # bu alan adlari ve alt alan adlari
    path_re: re.Pattern | None = None      # istege bagli: yol da uymali

    def can_handle(self, url: str) -> bool:
        p = urlparse(url)
        host = (p.hostname or "").lower()
        if not any(host == h or host.endswith("." + h) for h in self.hosts):
            return False
        return self.path_re is None or bool(self.path_re.search(p.path + ("#" + p.fragment if p.fragment else "")))

    @abstractmethod
    def list(self, url: str) -> CloudListing: ...

    def file_request(self, listing: CloudListing, f: CloudFile) -> tuple[str, dict[str, str], dict[str, Any]]:
        """-> (dogrudan url, basliklar, options). options Download.options'a yazilir (son islem icin)."""
        if not f.url:
            raise CloudError("cloud_failed", f"link yok: {f.path}")
        return f.url, dict(f.headers), {}


def session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = UA
    return s


def get_json(s: requests.Session, url: str, *, method: str = "GET", **kw: Any) -> Any:
    kw.setdefault("timeout", 20)
    r = s.request(method, url, **kw)
    if r.status_code == 404:
        raise CloudError("cloud_not_found", url)
    if r.status_code in (401, 403):
        raise CloudError("cloud_denied", f"{r.status_code} {url}")
    r.raise_for_status()
    return r.json()


def join(*parts: str) -> str:
    return "/".join(p.strip("/") for p in parts if p and p.strip("/"))


class CloudService:
    """Saglayicilari bulur, listeleri kisa sure bellekte tutar (arayuz sadece token + secilen siralari yollar)."""

    TTL = 3600

    def __init__(self, providers: list[CloudProvider]) -> None:
        self.providers = providers
        self._cache: dict[str, tuple[float, CloudListing]] = {}
        self._lock = threading.Lock()

    def provider_for(self, url: str) -> CloudProvider | None:
        for p in self.providers:
            try:
                if p.can_handle(url):
                    return p
            except Exception:
                log.exception("can_handle hata verdi: %s", p.name)
        return None

    def list(self, url: str) -> tuple[str, CloudListing]:
        p = self.provider_for(url)
        if p is None:
            raise CloudError("cloud_unsupported", url)
        try:
            listing = p.list(url)
        except CloudError:
            raise
        except requests.RequestException as exc:
            log.warning("Bulut listesi alinamadi (%s): %s", p.name, exc)
            raise CloudError("cloud_failed", str(exc)) from exc
        except Exception as exc:
            log.exception("Bulut listesi alinamadi: %s", p.name)
            raise CloudError("cloud_failed", f"{type(exc).__name__}: {exc}") from exc
        listing.provider = p.name
        listing.url = url
        if not listing.files:
            raise CloudError("cloud_empty", url)
        log.info("Bulut listelendi (%s): %s | %d dosya, %d bayt%s", p.name, listing.title,
                 len(listing.files), sum(f.size for f in listing.files), " (klasor)" if listing.is_folder else "")
        token = secrets.token_hex(8)
        now = time.time()
        with self._lock:
            self._cache = {k: v for k, v in self._cache.items() if now - v[0] < self.TTL}
            self._cache[token] = (now, listing)
        return token, listing

    def get(self, token: str) -> tuple[CloudProvider, CloudListing]:
        with self._lock:
            item = self._cache.get(token)
        if not item:
            raise CloudError("cloud_expired")
        listing = item[1]
        p = next((x for x in self.providers if x.name == listing.provider), None)
        if p is None:
            raise CloudError("cloud_unsupported")
        return p, listing
