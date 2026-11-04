"""Gizli veri deposu: Windows DPAPI (CryptProtectData, kullanici kapsami) ile sifreli dosyalar.

YouTube/Google oturum cerezleri burada tutulur (data/yt_cookies.bin). Duz metin diske yalnizca
yt-dlp calisirken gecici bir cookies.txt olarak yazilir ve is bitince silinir.
"""
from __future__ import annotations

import contextlib
import ctypes
import ctypes.wintypes as wt
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Iterator

_ENTROPY = b"kami-dpapi-v1"


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> _Blob:
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def _call(fn, data: bytes) -> bytes:
    src, ent, out = _blob(data), _blob(_ENTROPY), _Blob()
    if not fn(ctypes.byref(src), None, ctypes.byref(ent), None, None, 0x01, ctypes.byref(out)):
        raise OSError(ctypes.get_last_error() or "DPAPI hatasi")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def protect(data: bytes) -> bytes:
    return _call(ctypes.windll.crypt32.CryptProtectData, data)


def unprotect(data: bytes) -> bytes:
    return _call(ctypes.windll.crypt32.CryptUnprotectData, data)


# ---------------------------------------------------------------- cerez deposu
# Site gruplari: her grup eklentiden ayri ayri gelir, kaydederken sadece o grubun cerezleri degisir.
SITE_GROUPS: dict[str, tuple[str, ...]] = {
    "youtube": ("youtube.com", "google.com"),
    "instagram": ("instagram.com",),
    "x": ("x.com", "twitter.com"),
    "tiktok": ("tiktok.com",),
}
_COOKIE_DOMAINS = tuple(d for g in SITE_GROUPS.values() for d in g)


def _match(host: str, doms: tuple[str, ...]) -> bool:
    d = host.lstrip(".").lower()
    return any(d == x or d.endswith("." + x) for x in doms)


def _domain_ok(domain: str) -> bool:
    return _match(domain, _COOKIE_DOMAINS)


def group_of(host_or_url: str) -> str:
    from urllib.parse import urlparse
    h = urlparse(host_or_url).hostname if "://" in host_or_url else host_or_url
    for g, doms in SITE_GROUPS.items():
        if h and _match(h, doms):
            return g
    return ""


def to_netscape(cookies: list[dict[str, Any]]) -> str:
    """chrome.cookies nesneleri -> Netscape cookies.txt (yt-dlp'nin bekledigi bicim)."""
    lines = ["# Netscape HTTP Cookie File", ""]
    for c in cookies:
        name, domain = str(c.get("name") or ""), str(c.get("domain") or "")
        if not name or not domain or "\t" in name or "\n" in str(c.get("value", "")):
            continue
        host_only = bool(c.get("hostOnly"))
        if not host_only and not domain.startswith("."):
            domain = "." + domain
        exp = 0 if c.get("session") else int(float(c.get("expirationDate") or 0))
        lines.append("\t".join([
            domain, "FALSE" if host_only else "TRUE", str(c.get("path") or "/"),
            "TRUE" if c.get("secure") else "FALSE", str(exp), name, str(c.get("value") or ""),
        ]))
    return "\n".join(lines) + "\n"


class CookieStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def save(self, cookies: list[dict[str, Any]]) -> int:
        keep = [c for c in cookies if isinstance(c, dict) and _domain_ok(str(c.get("domain") or ""))]
        if not keep:
            return 0
        groups = {group_of(str(c.get("domain") or "")) for c in keep}
        old = [c for c in self.load() if group_of(str(c.get("domain") or "")) not in groups]
        n = len(keep)
        keep = old + keep
        payload = json.dumps({"saved": time.time(), "cookies": keep}).encode("utf-8")
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_bytes(protect(payload))
            os.replace(tmp, self.path)
        return n

    def load(self) -> list[dict[str, Any]]:
        with self._lock:
            try:
                raw = unprotect(self.path.read_bytes())
            except (OSError, ValueError):
                return []
        try:
            return list(json.loads(raw).get("cookies") or [])
        except ValueError:
            return []

    def groups(self) -> list[str]:
        return sorted({group_of(str(c.get("domain") or "")) for c in self.load()} - {""})

    def has_login(self) -> bool:
        names = {c.get("name") for c in self.load() if group_of(str(c.get("domain") or "")) == "youtube"}
        return bool(names & {"SAPISID", "__Secure-3PAPISID", "LOGIN_INFO", "SID"})

    @contextlib.contextmanager
    def cookiefile(self, url: str = "") -> Iterator[str | None]:
        """Gecici duz cookies.txt yolu verir (yoksa None); cikista siler. url verilirse sadece o sitenin grubu."""
        cookies = self.load()
        if url:
            g = group_of(url)
            cookies = [c for c in cookies if group_of(str(c.get("domain") or "")) == g] if g else []
        if not cookies:
            yield None
            return
        fd, name = tempfile.mkstemp(prefix="kami_ck_", suffix=".txt")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(to_netscape(cookies))
            yield name
        finally:
            with contextlib.suppress(OSError):
                os.remove(name)
