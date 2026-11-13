"""Bunkr: /a/<album> ve /f|/v|/i/<dosya> cozumleyici."""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import html
import re
from urllib.parse import urljoin, urlparse

from app.core.cloud import CloudFile, CloudListing, CloudProvider, head_size, session

HOST_RE = re.compile(r"^([a-z0-9-]+\.)*bunkrr?\.[a-z]{2,}$", flags=re.I)


class Bunkr(CloudProvider):
    name = "bunkr"
    hosts = ("bunkr.si", "bunkr.sk", "bunkr.cr", "bunkr.ac", "bunkr.ru",
             "bunkr.la", "bunkr.black", "bunkr.red", "bunkr.ph", "bunkr.fi")
    path_re = re.compile(r"^/(a|f|v|i)/([^/]+)")

    def can_handle(self, url: str) -> bool:
        p = urlparse(url)
        host = (p.hostname or "").lower()
        return bool(HOST_RE.match(host) and self.path_re.search(p.path))

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
        targets: list[tuple[str, str]] = []
        for h in hrefs:
            full = urljoin(f"{p.scheme}://{p.netloc}", h)
            if full not in seen:
                seen.add(full)
                targets.append((full, h.rsplit("/", 1)[-1]))

        def _worker(item: tuple[str, str]) -> CloudFile | None:
            try:
                return self._resolve_item(session(), item[0], item[1])
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=4) as pool:
            files = [f for f in pool.map(_worker, targets) if f is not None]
        return CloudListing(self.name, title or ident, is_folder=True, files=files)

    @staticmethod
    def _resolve_item(s, url: str, ident: str) -> CloudFile:
        p = urlparse(url)
        r = s.get(url, timeout=20)
        r.raise_for_status()
        page = r.text
        name_m = re.search(r"<h1[^>]*>(.*?)</h1>", page, flags=re.S | re.I)
        name = html.unescape(re.sub(r"<[^>]+>", "", name_m.group(1))).strip() if name_m else ident
        hdrs = {"Referer": url}
        # API /api/vs veya doğrudan get.bunkrr.su / <video><source>
        slug_m = re.search(r'data-slug=["\']([^"\']+)["\']', page) or re.search(r"/f/([^/?#]+)", url)
        if slug_m:
            try:
                api_r = s.post(f"{p.scheme}://{p.netloc}/api/vs", json={"slug": slug_m.group(1)},
                               headers=hdrs, timeout=15)
                if api_r.status_code == 200:
                    data = api_r.json()
                    enc = data.get("url") or ""
                    ts = data.get("timestamp")
                    if enc and ts:
                        key = f"SECRET_KEY_{int(ts) // 3600}".encode()
                        raw = base64.b64decode(enc)
                        dec = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw)).decode("utf-8")
                        if dec.startswith("http"):
                            return CloudFile(name or ident, head_size(s, dec, hdrs), url=dec, headers=hdrs)
                    if enc.startswith("http"):
                        return CloudFile(name or ident, head_size(s, enc, hdrs), url=enc, headers=hdrs)
            except Exception:
                pass
        src_m = (re.search(r'<a[^>]+href=["\'](https?://get\.[^"\']+)["\']', page, flags=re.I)
                 or re.search(r'<source[^>]+src=["\'](https?://[^"\']+)["\']', page, flags=re.I)
                 or re.search(r'<img[^>]+src=["\'](https?://[^"\']*bunkr[^"\']+)["\']', page, flags=re.I))
        if not src_m:
            raise RuntimeError(f"Bunkr indirme bağlantısı bulunamadı: {url}")
        dl = html.unescape(src_m.group(1))
        return CloudFile(name or ident, head_size(s, dl, hdrs), url=dl, headers=hdrs)


def register(ctx) -> None:
    ctx.register_cloud(Bunkr())
