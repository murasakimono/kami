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
_COOKIE_DOMAINS = ("youtube.com", "google.com")


def _domain_ok(domain: str) -> bool:
    d = domain.lstrip(".").lower()
    return any(d == x or d.endswith("." + x) for x in _COOKIE_DOMAINS)


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
        payload = json.dumps({"saved": time.time(), "cookies": keep}).encode("utf-8")
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_bytes(protect(payload))
            os.replace(tmp, self.path)
        return len(keep)

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

    def has_login(self) -> bool:
        names = {c.get("name") for c in self.load()}
        return bool(names & {"SAPISID", "__Secure-3PAPISID", "LOGIN_INFO", "SID"})

    @contextlib.contextmanager
    def cookiefile(self) -> Iterator[str | None]:
        """Gecici duz cookies.txt yolu verir (yoksa None); cikista siler."""
        cookies = self.load()
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
