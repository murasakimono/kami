"""Otomatik ayna bulma (coklu kaynakli indirme): aria2'ye ayni dosyanin birden cok adresi verilir,
hizli olani daha cok kullanilir (--uri-selector=adaptive).
  - Metalink/HTTP (RFC 6249): sunucu 'Link: <...>; rel=duplicate' basliklariyla aynalari bildirir (MirrorBrain: openSUSE, VLC, GNOME ...)
  - SourceForge: dosya bilinen buyuk aynalardan da istenir."""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)
SF_MIRRORS = ("netcologne", "freefr", "kumisystems", "deac-fra", "altushost-swe", "netix", "jaist", "liquidtelecom")
_LINK = re.compile(r"<([^>]+)>\s*;([^,]*)")


def _sourceforge(url: str) -> list[str]:
    u = urlparse(url)
    m = re.match(r"^/projects/([^/]+)/files/(.+?)(?:/download)?$", u.path) if u.netloc.endswith("sourceforge.net") else None
    if m:
        proj, rest = m.group(1), m.group(2)
    else:
        m = re.match(r"^/project/([^/]+)/(.+)$", u.path) if (u.netloc.endswith("dl.sourceforge.net") or u.netloc == "downloads.sourceforge.net") else None
        if not m:
            return []
        proj, rest = m.group(1), m.group(2)
    return [f"https://{mir}.dl.sourceforge.net/project/{proj}/{rest}" for mir in SF_MIRRORS]


def find(url: str, headers: dict | None = None, limit: int = 6) -> list[str]:
    """Ana adres disindaki ayna adresleri (bulunamazsa bos). Hizli: en fazla ~3 sn."""
    if not url.lower().startswith(("http://", "https://")):
        return []
    out = _sourceforge(url)
    if not out:
        try:
            r = requests.head(url, headers={**(headers or {}), "Accept": "application/metalink4+xml, */*;q=0.1", "Want-Digest": "SHA-256"},
                              allow_redirects=True, timeout=3)
            for h in r.headers.get("Link", "").split(",") if r.headers.get("Link") else []:
                m = _LINK.search(h)
                if m and "duplicate" in m.group(2).lower() and m.group(1).startswith("http"):
                    out.append(m.group(1))
        except requests.RequestException:
            return []
    seen, res = {url}, []
    for x in out:
        if x not in seen:
            seen.add(x); res.append(x)
    return res[:limit]
