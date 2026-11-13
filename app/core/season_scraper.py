"""Gomulu oynatici ve tam sezon kaziyici (PlayerJS / Dzen / VidMoly / Sibnet / TauVideo / VK / Ok.ru / Mail.ru)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import html
import json
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
    r'(?:https?:)?//(?:[a-z0-9-]+\.)?(?:vidmoly\.(?:to|net|me)|video\.sibnet\.ru|dzen\.ru|tau-video\.xyz|ok\.ru|odnoklassniki\.ru|vk\.com|vkvideo\.ru|my\.mail\.ru)/[^"\'\s<>]+',
    flags=re.I,
)
_OK_QUAL = {"ultra": 8, "quad": 7, "full": 6, "hd": 5, "sd": 4, "low": 3, "mobile": 2, "lowest": 1}


def _norm_url(raw: str, base: str = "") -> str:
    u = html.unescape(str(raw or "")).strip()
    if not u:
        return ""
    u = (
        u.replace("\\\\/", "/")
        .replace("\\/", "/")
        .replace("\\\\u002F", "/")
        .replace("\\u002F", "/")
        .replace("\\\\u002f", "/")
        .replace("\\u002f", "/")
        .replace("\\\\u0026", "&")
        .replace("\\u0026", "&")
    )
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/") and base:
        return urljoin(base, u)
    return u


def _clean_title(raw_html: str) -> str:
    m = re.search(r"<h1[^>]*>(.*?)</h1>", raw_html, flags=re.S | re.I) or re.search(r"<title>(.*?)</title>", raw_html, flags=re.S | re.I)
    if not m:
        return ""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", m.group(1)))).strip()


def _extract_okru_from_html(page: str, base_url: str) -> str:
    m_opt = re.search(r'data-options=["\']([^"\']+)["\']', page, flags=re.I)
    if m_opt:
        try:
            opts = json.loads(html.unescape(m_opt.group(1)))
            fv = opts.get("flashvars") or {}
            meta = fv.get("metadata")
            if isinstance(meta, str):
                meta = json.loads(meta)
            if isinstance(meta, dict):
                for key in ("hlsManifestUrl", "hlsMasterPlaylistUrl", "ondemandHls"):
                    val = _norm_url(meta.get(key) or "", base_url)
                    if val.startswith("http"):
                        return val
                vids = [v for v in (meta.get("videos") or []) if isinstance(v, dict) and v.get("url")]
                if vids:
                    vids.sort(key=lambda v: _OK_QUAL.get(str(v.get("name") or "").lower(), 0), reverse=True)
                    best = _norm_url(vids[0]["url"], base_url)
                    if best.startswith("http"):
                        return best
        except Exception:
            pass
    for pat in (
        r'"(?:hlsManifestUrl|hlsMasterPlaylistUrl|ondemandHls)"\s*:\s*"([^"]+)"',
        r'\\"(?:hlsManifestUrl|hlsMasterPlaylistUrl|ondemandHls)\\"\s*:\s*\\"((?:[^"\\]|\\[^"])+)\\"',
    ):
        mh = re.search(pat, page, flags=re.I)
        if mh:
            u = _norm_url(mh.group(1), base_url)
            if u.startswith("http"):
                return u
    return ""


def _resolve_okru(embed_url: str, page: str, s: requests.Session, headers: dict[str, str]) -> str:
    found = _extract_okru_from_html(page, embed_url)
    if found:
        return found
    if "/videoembed/" not in embed_url:
        mv = re.search(r"/video/(\d+)", embed_url)
        if mv:
            try:
                er = s.get(f"https://ok.ru/videoembed/{mv.group(1)}", headers=headers, timeout=15)
                if er.status_code == 200:
                    return _extract_okru_from_html(er.text, er.url or embed_url)
            except requests.RequestException:
                pass
    return ""


def _extract_vk_from_html(page: str, base_url: str) -> str:
    for key in ("hls", "hls_ondemand", "hls_fmp4", "hls_live",
                "url2160", "url1440", "url1080", "url720", "url480", "url360", "url240"):
        for pat in (
            rf'["\']{key}["\']\s*:\s*["\']([^"\']+)["\']',
            rf'\\"{key}\\"\s*:\s*\\"((?:[^"\\]|\\[^"])+)\\"',
        ):
            m = re.search(pat, page)
            if m:
                u = _norm_url(m.group(1), base_url)
                if u.startswith("http"):
                    return u
    return ""


def _resolve_vk(embed_url: str, page: str, s: requests.Session, headers: dict[str, str]) -> str:
    found = _extract_vk_from_html(page, embed_url)
    if found:
        return found
    if "video_ext.php" not in embed_url:
        mv = re.search(r"video(-?\d+)_(\d+)", embed_url)
        if mv:
            try:
                ext_url = f"https://vk.com/video_ext.php?oid={mv.group(1)}&id={mv.group(2)}"
                er = s.get(ext_url, headers=headers, timeout=15)
                if er.status_code == 200:
                    return _extract_vk_from_html(er.text, ext_url)
            except requests.RequestException:
                pass
    return ""


def _pick_mailru_videos(vids: list[dict[str, Any]], base_url: str) -> str:
    best_u = ""
    best_q = -1
    for v in vids:
        if not isinstance(v, dict) or not v.get("url"):
            continue
        qm = re.search(r"(\d+)", str(v.get("key") or ""))
        q = int(qm.group(1)) if qm else 0
        if q >= best_q:
            u = _norm_url(v["url"], base_url)
            if u.startswith("http"):
                best_q = q
                best_u = u
    return best_u


def _resolve_mailru(embed_url: str, page: str, s: requests.Session, headers: dict[str, str]) -> str:
    mm = re.search(r'"(?:metadataUrl|metaUrl)"\s*:\s*"([^"]+)"', page)
    if mm:
        meta_url = _norm_url(mm.group(1), embed_url)
        if meta_url.startswith("http"):
            try:
                mr = s.get(meta_url, headers={**headers, "Referer": embed_url}, timeout=12)
                if mr.status_code == 200:
                    data = mr.json()
                    vids = data.get("videos") if isinstance(data, dict) else None
                    if isinstance(vids, list):
                        u = _pick_mailru_videos(vids, meta_url)
                        if u:
                            return u
            except Exception:
                pass
    mv = re.search(r'"videos"\s*:\s*(\[[^\]]+\])', page)
    if mv:
        try:
            vids = json.loads(mv.group(1))
            if isinstance(vids, list):
                u = _pick_mailru_videos(vids, embed_url)
                if u:
                    return u
        except Exception:
            pass
    return ""


def resolve_embed(embed_url: str, session: requests.Session | None = None, referer: str = "") -> str:
    """VidMoly / Sibnet / Dzen / TauVideo / PlayerJS / VK / Ok.ru / Mail.ru gomulu sayfasindan akisi (.m3u8/.mp4) cikarir."""
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

    host = (urlparse(embed_url).hostname or "").lower()
    if host.endswith(("ok.ru", "odnoklassniki.ru")):
        u = _resolve_okru(embed_url, page, s, headers)
        if u:
            return u
    elif host.endswith(("vk.com", "vkvideo.ru")):
        u = _resolve_vk(embed_url, page, s, headers)
        if u:
            return u
    elif host.endswith("my.mail.ru"):
        u = _resolve_mailru(embed_url, page, s, headers)
        if u:
            return u

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
            u = _norm_url(m.group(1), embed_url)
            return u
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

    def _process_ep(item: tuple[int, tuple[int, str, str]]) -> dict[str, Any] | None:
        idx, (num, label, ep_url) = item
        ws = s if session is not None else requests.Session()
        ep_html = page if ep_url == url else ""
        if not ep_html:
            try:
                er = ws.get(ep_url, headers={"User-Agent": UA, "Referer": url}, timeout=15)
                if er.status_code == 200:
                    ep_html = er.text
            except requests.RequestException:
                return None
        embeds = [u if u.startswith("http") else "https:" + u for u in _EMBED_RE.findall(ep_html)]
        stream = ""
        used_embed = ""
        for emb in embeds[:4]:
            stream = resolve_embed(emb, session=ws, referer=ep_url)
            if stream:
                used_embed = emb
                break
        if not stream:
            stream = resolve_embed(ep_url, session=ws, referer=url)
        ep_no = num or idx
        return {
            "episode": ep_no,
            "title": label or f"{show_title} - Bölüm {ep_no:02d}",
            "page_url": ep_url,
            "embed_url": used_embed,
            "stream_url": stream,
        }

    indexed = list(enumerate(links, 1))
    if session is None and len(indexed) > 1:
        with ThreadPoolExecutor(max_workers=4) as pool:
            raw_eps = list(pool.map(_process_ep, indexed))
    else:
        raw_eps = [_process_ep(it) for it in indexed]
    episodes = [ep for ep in raw_eps if ep is not None]

    return {"ok": True, "title": show_title, "episodes": episodes}
