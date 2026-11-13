"""GoFile: misafir token ile /d/<id> icerigini (alt klasorleriyle) cozer."""
from __future__ import annotations

import re
import threading
import time
from urllib.parse import urlparse

from app.core.cloud import CloudFile, CloudListing, CloudProvider, join, session

API = "https://api.gofile.io"
_FALLBACK_WT = "4fd6sg89d7s6"
_CACHE_LOCK = threading.Lock()
_WT_CACHE: tuple[float, str] = (0.0, "")
_TOKEN_CACHE: tuple[float, str] = (0.0, "")


def _get_wt(s) -> str:
    global _WT_CACHE
    now = time.time()
    with _CACHE_LOCK:
        if _WT_CACHE[1] and now - _WT_CACHE[0] < 3600:
            return _WT_CACHE[1]
    wt = _FALLBACK_WT
    try:
        r = s.get("https://gofile.io/dist/js/global.js", timeout=10)
        if r.ok:
            m = re.search(r'\bwt\s*[:=]\s*["\']([A-Za-z0-9_-]{6,})["\']', r.text)
            if m:
                wt = m.group(1)
    except Exception:
        pass
    with _CACHE_LOCK:
        _WT_CACHE = (now, wt)
    return wt


def _get_token(s, *, force_refresh: bool = False) -> str:
    global _TOKEN_CACHE
    now = time.time()
    with _CACHE_LOCK:
        if not force_refresh and _TOKEN_CACHE[1] and now - _TOKEN_CACHE[0] < 3600:
            return _TOKEN_CACHE[1]
    acc = s.post(f"{API}/accounts", timeout=15).json()
    token = ((acc.get("data") or {}).get("token")) or ""
    if not token:
        raise RuntimeError("GoFile misafir oturumu alınamadı")
    with _CACHE_LOCK:
        _TOKEN_CACHE = (now, token)
    return token


class GoFile(CloudProvider):
    name = "gofile"
    hosts = ("gofile.io",)
    path_re = re.compile(r"^/d/([^/]+)")

    def list(self, url: str) -> CloudListing:
        m = self.path_re.match(urlparse(url).path)
        if not m:
            raise ValueError("Geçersiz GoFile bağlantısı")
        cid = m.group(1)
        s = session()
        wt = _get_wt(s)
        token = _get_token(s)
        headers = {"Authorization": f"Bearer {token}", "Cookie": f"accountToken={token}"}
        r = s.get(f"{API}/contents/{cid}", params={"wt": wt}, headers=headers, timeout=20).json()
        st = str(r.get("status") or "")
        if st != "ok" and any(k in st.lower() for k in ("auth", "token")):
            # Yalnızca yetki/token hatasinda 1 kez misafir anahtarini yenile
            token = _get_token(s, force_refresh=True)
            headers = {"Authorization": f"Bearer {token}", "Cookie": f"accountToken={token}"}
            r = s.get(f"{API}/contents/{cid}", params={"wt": wt}, headers=headers, timeout=20).json()
        if r.get("status") != "ok":
            raise RuntimeError(f"GoFile hatası: {r.get('status')}")
        root = r.get("data") or {}
        files: list[CloudFile] = []
        self._walk(s, root, "", headers, wt, files)
        return CloudListing(self.name, root.get("name") or cid, is_folder=True, files=files)

    def _walk(self, s, node: dict, rel: str, headers: dict, wt: str, out: list[CloudFile]) -> None:
        children = node.get("children") or {}
        for item in (children.values() if isinstance(children, dict) else children):
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("id") or "file"
            if item.get("type") == "folder":
                sub_id = item.get("id")
                sub = item
                if sub_id and not item.get("children"):
                    try:
                        res = s.get(f"{API}/contents/{sub_id}", params={"wt": wt},
                                    headers=headers, timeout=20).json()
                        if res.get("status") == "ok":
                            sub = res.get("data") or item
                    except Exception:
                        pass
                self._walk(s, sub, join(rel, name), headers, wt, out)
            else:
                link = item.get("link") or item.get("directLink") or ""
                if link:
                    out.append(CloudFile(
                        join(rel, name), int(item.get("size") or 0),
                        url=link, headers=dict(headers),
                    ))


def register(ctx) -> None:
    ctx.register_cloud(GoFile())
