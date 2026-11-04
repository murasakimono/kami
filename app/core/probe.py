"""Link yoklama: indirmeden once tek kisa istekle linkin ne oldugunu ogren (IDM'in yaptigi gibi).

GET + 'Range: bytes=0-0' gonderilir, govde okunmaz:
  - 206 -> sunucu parcali indirmeyi destekler (cok baglanti + devam mumkun)
  - 200 -> desteklemez (tek baglanti, duraklatinca bastan)
  - Content-Type text/html -> bu bir web sayfasi, dosya degil
"""
from __future__ import annotations

import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.message import Message
from urllib.parse import unquote

log = logging.getLogger(__name__)

_CONTENT_RANGE_TOTAL = re.compile(r"/(\d+)\s*$")


@dataclass
class ProbeResult:
    ok: bool = False
    status: int = 0
    content_type: str = ""
    filename: str = ""
    size: int = 0
    ranges: bool = False
    final_url: str = ""
    error: str = ""

    @property
    def is_html(self) -> bool:
        return self.content_type in ("text/html", "application/xhtml+xml")


def _fix_mojibake(name: str) -> str:
    """urllib basliklari latin-1 cozer; sunucu ham UTF-8 gonderdiyse duzelt."""
    try:
        return name.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def filename_from_disposition(value: str) -> str:
    if not value:
        return ""
    msg = Message()
    msg["content-disposition"] = value
    name = msg.get_filename() or ""   # filename* (RFC 5987) dahil
    if not name:
        return ""
    if "filename*" not in value.lower():
        name = _fix_mojibake(name)
    return unquote(name) if "%" in name and "filename*" not in value.lower() else name


def probe(url: str, headers: dict[str, str] | None = None, referer: str = "", timeout: float = 6.0) -> ProbeResult:
    h = {"Range": "bytes=0-0", "Accept-Encoding": "identity"}
    h.update({k: v for k, v in (headers or {}).items() if k.lower() not in ("range", "accept-encoding")})
    if referer:
        h.setdefault("Referer", referer)
    h.setdefault("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Kami/0.1")
    req = urllib.request.Request(url, headers=h, method="GET")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        return ProbeResult(ok=False, status=exc.code, error=f"HTTP {exc.code}")
    except Exception as exc:  # ag hatasi: yoklama bilgisiz gecer, motor kendisi dener
        return ProbeResult(ok=False, error=f"{type(exc).__name__}: {exc}")
    try:
        status = resp.status
        ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        size = 0
        if status == 206:
            m = _CONTENT_RANGE_TOTAL.search(resp.headers.get("Content-Range") or "")
            size = int(m.group(1)) if m else 0
        else:
            size = int(resp.headers.get("Content-Length") or 0)
        return ProbeResult(
            ok=True, status=status, content_type=ctype,
            filename=filename_from_disposition(resp.headers.get("Content-Disposition") or ""),
            size=size, ranges=status == 206, final_url=resp.geturl(),
        )
    finally:
        resp.close()  # govdeyi okumadan kapat (200 donduyse butun dosyayi cekmeyelim)
