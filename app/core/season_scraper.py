"""Gomulu oynatici ve tam sezon kaziyici (PlayerJS / Dzen / VidMoly / Sibnet / TauVideo)."""
from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

_EP_LINK_RE = re.compile(
    r'(?:/episode/\d+|/bolum[-_/]?\d+|/b[oö]l[uü]m[-_/]?\d+|s\d+e\d+|ep[-_]?\d+|\d+[-_]bolum)',
    flags=re.I,
)
_EMBED_RE = re.compile(
    r'(?:https?:)?//(?:www\.)?(?:vidmoly\.(?:to|net|me)|video\.sibnet\.ru|dzen\.ru|tau-video\.xyz|ok\.ru|vk\.com)/[^"\'\s<>]+',
    flags=re.I,
)


def _clean_title(raw_html: str) -> str:
    m = re.search(r"<h1[^>]*>(.*?)</h1>", raw_html, flags=re.S | re.I) or re.search(r"<title>(.*?)</title>", raw_html, flags=re.S | re.I)
    if not m:
        return ""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", m.group(1)))).strip()


def resolve_embed(embed_url: str, session: requests.Session | None = None, referer: str = "") -> str:
    """VidMoly / Sibnet / Dzen / TauVideo / PlayerJS gomulu sayfasindan gercek akisi (.m3u8/.mp4) cikarir."""
    if embed_url.startswith("//"):
        embed_url = "https:" + embed_url
    s = session or requests.Session()
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    try:
        r = s.get(embed_url, headers=headers, timeout=15)
        if r.status_code != 200:
            return ""
        page = r.text
    except requests.RequestException:
        return ""

    # PlayerJS / JWPlayer / videojs kaynaklari
    for pat in (
        r'sources\s*:\s*\[\s*\{\s*file\s*:\s*["\']([^"\']+\.(?:m3u8|mp4|txt)[^"\']*)["\']',
        r'new\s+Playerjs\s*\(\s*\{[^}]*file\s*:\s*["\']([^"\']+)["\']',
        r'player\.src\s*\(\s*["\']([^"\']+\.(?:mp4|m3u8)[^"\']*)["\']',
        r'<source[^>]+src=["\']([^"\']+\.(?:mp4|m3u8)[^"\']*)["\']',
        r'["\'](https?://[^"\']+\.(?:m3u8|mp4)(?:\?[^"\']*)?)["\']',
    ):
        m = re.search(pat, page, flags=re.I)
        if m:
            u = html.unescape(m.group(1)).replace("\\/", "/")
            return urljoin(embed_url, u) if u.startswith("/") else u
    return ""


def _ep_num(url: str, label: str = "") -> int:
    for src in (url, label):
        m = re.search(r"(?:episode/|bolum[-_/]?|s\d+e|ep[-_]?|\b)(\d{1,4})(?:\b|$)", src, flags=re.I)
        if m:
            return int(m.group(1))
    return 0


def scrape_season(url: str, session: requests.Session | None = None, limit: int = 100) -> dict[str, Any]:
    """Dizi/sezon sayfasindaki tum bolumleri ve gomulu akislari cozer."""
    s = session or requests.Session()
    try:
        r = s.get(url, headers={"User-Agent": UA}, timeout=20)
        r.raise_for_status()
    except requests.RequestException as exc:
        return {"ok": False, "error": str(exc)[:180], "episodes": []}

    page = r.text
    show_title = _clean_title(page) or urlparse(url).hostname or "Dizi"
    base_host = (urlparse(url).hostname or "").lower()

    links: list[tuple[int, str, str]] = []
    seen: set[str] = set()
    for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', page, flags=re.S | re.I):
        href = html.unescape(m.group(1)).strip()
        label = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", m.group(2)))).strip()
        full = urljoin(url, href)
        p = urlparse(full)
        if (p.hostname or "").lower() != base_host or full in seen:
            continue
        if _EP_LINK_RE.search(p.path) or _EP_LINK_RE.search(label):
            seen.add(full)
            links.append((_ep_num(p.path, label), label, full))

    if not links:
        links = [(1, show_title, url)]
    else:
        links.sort(key=lambda x: (x[0] == 0, x[0], x[2]))
        links = links[:limit]

    episodes: list[dict[str, Any]] = []
    for idx, (num, label, ep_url) in enumerate(links, 1):
        ep_html = page if ep_url == url else ""
        if not ep_html:
            try:
                er = s.get(ep_url, headers={"User-Agent": UA, "Referer": url}, timeout=15)
                if er.status_code == 200:
                    ep_html = er.text
            except requests.RequestException:
                continue
        embeds = [u if u.startswith("http") else "https:" + u for u in _EMBED_RE.findall(ep_html)]
        stream = ""
        used_embed = ""
        for emb in embeds[:4]:
            stream = resolve_embed(emb, session=s, referer=ep_url)
            if stream:
                used_embed = emb
                break
        if not stream:
            stream = resolve_embed(ep_url, session=s, referer=url)
        ep_no = num or idx
        episodes.append({
            "episode": ep_no,
            "title": label or f"{show_title} - Bölüm {ep_no:02d}",
            "page_url": ep_url,
            "embed_url": used_embed,
            "stream_url": stream,
        })

    return {"ok": True, "title": show_title, "episodes": episodes}
