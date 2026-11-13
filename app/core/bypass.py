"""Kami Bypass: kisaltma ve reklamli ara baglantilari (ouo.io, tr.link, ay.link, linkvertise, cuty.io, bc.vc, paste) cozer."""
from __future__ import annotations

import base64
import html
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

BYPASS_HOSTS = (
    "ouo.io", "ouo.press", "tr.link", "ay.link", "linkvertise.com",
    "link-hub.net", "link-target.net", "direct-link.net", "cuty.io", "bc.vc",
    "rentry.co", "pastebin.com", "justpaste.it",
)
_PREFER_LINK_RE = re.compile(
    r"(mega\.nz|mediafire\.com|drive\.google\.com|gofile\.io|pixeldrain\.com|qiwi\.gg|"
    r"bunkr|krakenfiles\.com|send\.cm|send\.now|yandex|disk\.yandex|1fichier|rapidgator|nitroflare|"
    r"\.(?:zip|rar|7z|mp4|mkv|avi|mp3|flac|exe|apk|pdf)(?:$|[?#]))",
    flags=re.I,
)


def _pick_paste_link(text: str) -> tuple[str, list[str]]:
    urls = list(dict.fromkeys(re.findall(r"https?://[^\s<>\"')]+", text)))
    if not urls:
        return "", []
    for u in urls:
        if _PREFER_LINK_RE.search(u):
            return u, urls
    return urls[0], urls


def is_bypassable(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return any(host == h or host.endswith("." + h) for h in BYPASS_HOSTS)


def _has_captcha(page: str) -> bool:
    low = page.lower()
    return any(k in low for k in ("g-recaptcha", "hcaptcha.com/1/api.js", "challenges.cloudflare.com/turnstile"))


def _extract_js_target(page: str, base_url: str) -> str:
    for pat in (
        r'<meta[^>]+http-equiv=["\']refresh["\'][^>]+content=["\'][^"\']*url=([^"\';\s]+)',
        r'(?:window\.location(?:\.href)?|location\.replace)\s*[=(]\s*["\'](https?://[^"\']+)["\']',
        r'atob\(\s*["\']([A-Za-z0-9+/=]{12,})["\']\s*\)',
        r'var\s+(?:url|target|redirect_url|go_url)\s*=\s*["\'](https?://[^"\']+)["\']',
    ):
        m = re.search(pat, page, flags=re.I)
        if not m:
            continue
        val = html.unescape(m.group(1)).strip()
        if "atob" in pat:
            try:
                dec = base64.b64decode(val).decode("utf-8", errors="ignore").strip()
                if dec.startswith("http"):
                    return dec
            except Exception:
                continue
        elif val.startswith("http"):
            return val
        elif val.startswith("/"):
            return urljoin(base_url, val)
    return ""


def resolve(url: str, session: requests.Session | None = None, max_hops: int = 5) -> dict[str, Any]:
    """Hedef baglantiyi cozer -> {ok, url, hops, error}."""
    s = session or requests.Session()
    cur = url.strip()
    hops = 0
    candidates: list[str] = []
    for _ in range(max_hops):
        if not cur or not is_bypassable(cur):
            out: dict[str, Any] = {"ok": True, "url": cur, "hops": hops}
            if candidates:
                out["candidates"] = candidates[:20]
            return out
        p = urlparse(cur)
        host = (p.hostname or "").lower()

        # linkvertise ?r=<base64>
        if any(h in host for h in ("linkvertise", "link-hub", "link-target", "direct-link")):
            qs = parse_qs(p.query)
            if "r" in qs and qs["r"]:
                try:
                    raw_r = unquote(qs["r"][0]).strip()
                    pad = "=" * (-len(raw_r) % 4)
                    dec = base64.urlsafe_b64decode(raw_r + pad).decode("utf-8", errors="ignore").strip()
                    if dec.startswith("http"):
                        cur = dec
                        hops += 1
                        continue
                except Exception:
                    pass

        # pastebin / rentry ham metin linki
        if host.endswith("pastebin.com") and "/raw/" not in p.path:
            raw_url = f"https://pastebin.com/raw{p.path}"
            r = s.get(raw_url, headers={"User-Agent": UA}, timeout=15)
            if r.status_code == 200:
                chosen, found = _pick_paste_link(r.text)
                if chosen:
                    candidates = found
                    cur = chosen
                    hops += 1
                    continue

        if host.endswith("rentry.co") and not p.path.rstrip("/").endswith("/raw"):
            raw_url = f"https://{p.netloc}{p.path.rstrip('/')}/raw"
            r = s.get(raw_url, headers={"User-Agent": UA}, timeout=15)
            if r.status_code == 200:
                chosen, found = _pick_paste_link(r.text)
                if chosen:
                    candidates = found
                    cur = chosen
                    hops += 1
                    continue

        try:
            r = s.get(cur, headers={"User-Agent": UA}, allow_redirects=True, timeout=15)
        except requests.RequestException as exc:
            return {"ok": False, "url": cur, "hops": hops, "error": str(exc)[:160]}

        if r.url and r.url != cur and not is_bypassable(r.url):
            return {"ok": True, "url": r.url, "hops": hops + 1}

        page = r.text
        if _has_captcha(page):
            return {"ok": False, "url": cur, "hops": hops, "error": "captcha_required"}

        # ouo.io / ouo.press 2 adimli form
        if "ouo.io" in host or "ouo.press" in host:
            tok_m = re.search(r'name=["\']_token["\'][^>]*value=["\']([^"\']+)["\']', page)
            if tok_m:
                act_m = re.search(r'<form[^>]+action=["\']([^"\']+)["\']', page, flags=re.I)
                post_url = urljoin(r.url, act_m.group(1)) if act_m else r.url
                r2 = s.post(post_url, data={"_token": tok_m.group(1)},
                            headers={"User-Agent": UA, "Referer": r.url}, allow_redirects=False, timeout=15)
                loc = r2.headers.get("Location") or ""
                if loc.startswith("http"):
                    cur = loc
                    hops += 1
                    continue

        nxt = _extract_js_target(page, r.url)
        if nxt and nxt != cur:
            cur = nxt
            hops += 1
            continue
        break

    return {"ok": not is_bypassable(cur), "url": cur, "hops": hops,
            "error": "" if not is_bypassable(cur) else "cozulemedi"}
