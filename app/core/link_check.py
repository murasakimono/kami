"""Toplu link saglik ve boyut kontrolu (JDownloader benzeri on-kontrol)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import unquote, urlparse

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def _check_one(url: str, cloud_service: Any = None) -> dict[str, Any]:
    u = str(url or "").strip()
    if not u.startswith(("http://", "https://")):
        return {"url": u, "ok": False, "status": 0, "size": 0, "name": u, "error": "Geçersiz URL"}
    if cloud_service is not None:
        try:
            prov = cloud_service.provider_for(u)
            if prov is not None:
                listing = prov.list(u)
                files = list(getattr(listing, "files", None) or [])
                if files:
                    total_sz = sum(int(getattr(f, "size", 0) or 0) for f in files)
                    nm = str(getattr(listing, "title", "") or getattr(files[0], "name", "") or u)
                    return {"url": u, "ok": True, "status": 200, "size": total_sz, "name": nm[:80], "cloud": prov.name, "files": len(files)}
                return {"url": u, "ok": False, "status": 404, "size": 0, "name": u[:60], "cloud": prov.name, "error": "Dosya bulunamadı"}
        except Exception as exc:
            return {"url": u, "ok": False, "status": 404, "size": 0, "name": u[:60], "error": str(exc)[:80]}
    try:
        r = requests.head(u, allow_redirects=True, timeout=8, headers={"User-Agent": UA})
        used_range = False
        if r.status_code in (405, 501) or (r.ok and not r.headers.get("Content-Length")):
            r = requests.get(u, stream=True, allow_redirects=True, timeout=8,
                             headers={"User-Agent": UA, "Range": "bytes=0-0"})
            used_range = True
            r.close()
        size = 0
        cr = r.headers.get("Content-Range") or ""
        if "/" in cr:
            tail = cr.rsplit("/", 1)[-1].strip()
            if tail.isdigit():
                size = int(tail)
        if not size and not used_range:
            cl = r.headers.get("Content-Length") or ""
            if cl.isdigit():
                size = int(cl)
        ctype = (r.headers.get("Content-Type") or "").lower()
        is_html = "text/html" in ctype
        cd = r.headers.get("Content-Disposition") or ""
        name = ""
        if "filename=" in cd:
            name = cd.split("filename=", 1)[1].strip('"; ')
        if not name:
            name = unquote(urlparse(r.url).path.rsplit("/", 1)[-1]) or urlparse(u).netloc
        return {"url": u, "ok": r.ok and not is_html, "status": r.status_code, "size": size, "name": name[:80], "html": is_html}
    except Exception as exc:
        return {"url": u, "ok": False, "status": 0, "size": 0, "name": u[:60], "error": str(exc)[:80]}


def check_links(urls: list[str], *, cloud_service: Any = None) -> dict[str, Any]:
    clean = [str(u or "").strip() for u in urls if str(u or "").strip()]
    if not clean:
        return {"ok": False, "error": "Kontrol edilecek link yok", "items": []}
    with ThreadPoolExecutor(max_workers=6) as pool:
        items = list(pool.map(lambda u: _check_one(u, cloud_service), clean[:40]))
    alive = sum(1 for it in items if it.get("ok"))
    return {"ok": True, "items": items, "alive": alive, "total": len(items)}
