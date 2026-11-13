"""Bunkr: /a/<album> ve /f|/v|/i/<dosya> cozumleyici."""
from __future__ import annotations

import base64
import html
import re
from urllib.parse import urljoin, urlparse

from app.core.cloud import CloudFile, CloudListing, CloudProvider, session


class Bunkr(CloudProvider):
    name = "bunkr"
    hosts = ("bunkr.si", "bunkr.sk", "bunkr.cr", "bunkr.ac", "bunkr.ru",
             "bunkr.la", "bunkr.black", "bunkr.red", "bunkr.ph", "bunkr.fi")
    path_re = re.compile(r"^/(a|f|v|i)/([^/]+)")

    def list(self, url: str) -> CloudListing:
        p = urlparse(url)
        m = self.path_re.match(p.path)
        if not m:
            raise ValueError("Geçersiz Bunkr bağlantısı")
        kind, ident = m.group(1), m.group(2)
        s = session()
        if kind != "a":
            f = self._resolve_item(s, url, ident)
            return CloudListing(self.name, f.rel_path, is_folder=False, files=[f])
        r = s.get(url, timeout=20)
        r.raise_for_status()
        title_m = re.search(r"<h1[^>]*>(.*?)</h1>", r.text, flags=re.S | re.I)
        title = html.unescape(re.sub(r"<[^>]+>", "", title_m.group(1))).strip() if title_m else ident
        hrefs = re.findall(r'href=["\'](/(?:f|v|i)/[^"\']+)["\']', r.text, flags=re.I)
        seen: set[str] = set()
        files: list[CloudFile] = []
        for h in hrefs:
            full = urljoin(f"{p.scheme}://{p.netloc}", h)
            if full in seen:
                continue
            seen.add(full)
            try:
                files.append(self._resolve_item(s, full, h.rsplit("/", 1)[-1]))
            except Exception:
                continue
        return CloudListing(self.name, title or ident, is_folder=True, files=files)

    @staticmethod
    def _resolve_item(s, url: str, ident: str) -> CloudFile:
        p = urlparse(url)
        r = s.get(url, timeout=20)
        r.raise_for_status()
        page = r.text
        name_m = re.search(r"<h1[^>]*>(.*?)</h1>", page, flags=re.S | re.I)
        name = html.unescape(re.sub(r"<[^>]+>", "", name_m.group(1))).strip() if name_m else ident
        # API /api/vs veya doğrudan get.bunkrr.su / <video><source>
        slug_m = re.search(r'data-slug=["\']([^"\']+)["\']', page) or re.search(r"/f/([^/?#]+)", url)
        if slug_m:
            try:
                api_r = s.post(f"{p.scheme}://{p.netloc}/api/vs", json={"slug": slug_m.group(1)},
                               headers={"Referer": url}, timeout=15)
                if api_r.status_code == 200:
                    data = api_r.json()
                    enc = data.get("url") or ""
                    ts = data.get("timestamp")
                    if enc and ts:
                        key = f"SECRET_KEY_{int(ts) // 3600}".encode()
                        raw = base64.b64decode(enc)
                        dec = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw)).decode("utf-8")
                        if dec.startswith("http"):
                            return CloudFile(name or ident, 0, url=dec, headers={"Referer": url})
                    if enc.startswith("http"):
                        return CloudFile(name or ident, 0, url=enc, headers={"Referer": url})
            except Exception:
                pass
        src_m = (re.search(r'<a[^>]+href=["\'](https?://get\.[^"\']+)["\']', page, flags=re.I)
                 or re.search(r'<source[^>]+src=["\'](https?://[^"\']+)["\']', page, flags=re.I)
                 or re.search(r'<img[^>]+src=["\'](https?://[^"\']*bunkr[^"\']+)["\']', page, flags=re.I))
        if not src_m:
            raise RuntimeError(f"Bunkr indirme bağlantısı bulunamadı: {url}")
        return CloudFile(name or ident, 0, url=html.unescape(src_m.group(1)), headers={"Referer": url})


def register(ctx) -> None:
    ctx.register_cloud(Bunkr())
