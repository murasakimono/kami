"""Erome: /a/<album> video ve gorsel cozumleyici."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import html
import re
from urllib.parse import unquote, urljoin, urlparse

from app.core.cloud import CloudError, CloudFile, CloudListing, CloudProvider, head_size, session

_SKIP_RE = re.compile(r"(?:/assets/|/favicon|avatar|logo|_thumb\.|\.svg(?:$|\?))", re.I)
_VIDEO_EXT_RE = re.compile(r"\.(?:mp4|webm|mov|m4v|mkv|m3u8)(?:$|\?)", re.I)
_MEDIA_HOST_RE = re.compile(r"(?:erome\.com|\.(?:mp4|webm|mov|m4v|jpg|jpeg|png|webp|gif)(?:$|\?))", re.I)


def _clean_name(url: str, idx: int, default_ext: str = ".bin") -> str:
    raw = unquote(urlparse(url).path.rsplit("/", 1)[-1]).strip()
    raw = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", raw)
    if not raw or "." not in raw:
        raw = f"media_{idx:02d}{default_ext}"
    return f"{idx:02d}_{raw}"


def _extract_media(page: str, base_url: str) -> tuple[str, list[str]]:
    title_m = (
        re.search(r"<h1[^>]*>(.*?)</h1>", page, flags=re.S | re.I)
        or re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', page, flags=re.I)
    )
    title = html.unescape(re.sub(r"<[^>]+>", "", title_m.group(1))).strip() if title_m else ""

    urls: list[str] = []
    seen: set[str] = set()

    def _add(raw_u: str) -> None:
        u = html.unescape(str(raw_u or "")).strip()
        if not u or u.startswith("data:"):
            return
        if u.startswith("//"):
            u = "https:" + u
        elif u.startswith("/"):
            u = urljoin(base_url, u)
        if not u.startswith(("http://", "https://")):
            return
        if _SKIP_RE.search(u) or not _MEDIA_HOST_RE.search(u):
            return
        if u not in seen:
            seen.add(u)
            urls.append(u)

    # Videolar (<source src=...> ve <video src=...>)
    for m in re.finditer(r'<source[^>]+src=["\']([^"\']+)["\']', page, flags=re.I):
        _add(m.group(1))
    for m in re.finditer(r'<video[^>]+src=["\']([^"\']+)["\']', page, flags=re.I):
        _add(m.group(1))
    # Gorseller (lazy data-src / src, yalnizca media/img etiketleri)
    for m in re.finditer(r'<img[^>]+class=["\'][^"\']*img-front[^"\']*["\'][^>]+(?:data-src|src)=["\']([^"\']+)["\']', page, flags=re.I):
        _add(m.group(1))
    for m in re.finditer(r'<img[^>]+(?:data-src|src)=["\']([^"\']+)["\'][^>]+class=["\'][^"\']*img-front[^"\']*["\']', page, flags=re.I):
        _add(m.group(1))
    if not urls:
        for m in re.finditer(r'<img[^>]+(?:data-src|src)=["\']([^"\']+)["\']', page, flags=re.I):
            _add(m.group(1))

    return title, urls


class Erome(CloudProvider):
    name = "erome"
    hosts = ("erome.com",)
    path_re = re.compile(r"^/a/[A-Za-z0-9_-]+")

    def list(self, url: str) -> CloudListing:
        s = session()
        r = s.get(url, headers={"Referer": "https://www.erome.com/"}, timeout=20)
        if r.status_code == 404:
            raise CloudError("cloud_not_found", url)
        if r.status_code in (401, 403, 429):
            raise CloudError("cloud_denied", f"{r.status_code} {url}")
        r.raise_for_status()
        title, media_urls = _extract_media(r.text, url)
        if not media_urls:
            raise CloudError("cloud_empty", url)
        hdrs = {"Referer": "https://www.erome.com/"}

        def _build(idx_url: tuple[int, str]) -> CloudFile:
            idx, mu = idx_url
            ext = ".mp4" if _VIDEO_EXT_RE.search(mu) else ".jpg"
            sz = head_size(session(), mu, hdrs) if len(media_urls) <= 40 else 0
            return CloudFile(_clean_name(mu, idx, ext), sz, url=mu, headers=hdrs)

        with ThreadPoolExecutor(max_workers=4) as pool:
            files = list(pool.map(_build, enumerate(media_urls, 1)))
        ident = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
        return CloudListing(self.name, title or ident or "Erome", files=files, is_folder=True)


def register(ctx) -> None:
    ctx.register_cloud(Erome())
