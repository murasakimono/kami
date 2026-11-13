"""Kemono & Coomer: acik API uzerinden uretici arşivi ve gonderi medya cozumleyici."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from app.core.cloud import CloudError, CloudFile, CloudListing, CloudProvider, get_json, head_size, session

_PATH_RE = re.compile(r"^/([a-z0-9_-]+)/user/([^/?#]+)(?:/post/([^/?#]+))?", flags=re.I)
_HOST_RE = re.compile(r"^(?:www\.)?(?:kemono\.(?:su|cr|party)|coomer\.(?:su|st|party))$", flags=re.I)
_MAX_PAGES = 5  # onizleme suresini hizli tutmak icin 250 gonderi siniri (sinirsiz arsiv icin Grab-All)


def _safe_seg(name: str) -> str:
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(name or "")).strip()
    return clean or "dosya"


def _collect_post(post: dict, origin: str, hdrs: dict[str, str], seen_urls: set[str], out: list[CloudFile]) -> None:
    pid = str(post.get("id") or "")
    pub = str(post.get("published") or "")[:10]
    prefix = f"{pub}_{pid}" if pub and pid else (pid or "post")
    entries: list[dict] = []
    f0 = post.get("file")
    if isinstance(f0, dict) and f0.get("path"):
        entries.append(f0)
    for att in post.get("attachments") or []:
        if isinstance(att, dict) and att.get("path"):
            entries.append(att)
    for idx, item in enumerate(entries, 1):
        p = str(item.get("path") or "").strip()
        if not p:
            continue
        if not p.startswith("/"):
            p = "/" + p
        full_url = f"{origin}/data{p}" if not p.startswith("/data/") else f"{origin}{p}"
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)
        raw_name = str(item.get("name") or p.rsplit("/", 1)[-1] or f"file_{idx}")
        rel_name = f"{prefix}/{idx:02d}_{_safe_seg(raw_name)}"
        out.append(CloudFile(rel_name, 0, url=full_url, headers=hdrs))


class KemonoCoomer(CloudProvider):
    name = "kemono"
    hosts = ("kemono.su", "kemono.cr", "kemono.party", "coomer.su", "coomer.st", "coomer.party")
    path_re = _PATH_RE

    def can_handle(self, url: str) -> bool:
        p = urlparse(url)
        host = (p.hostname or "").lower()
        return bool(_HOST_RE.match(host) and _PATH_RE.match(p.path))

    def list(self, url: str) -> CloudListing:
        p = urlparse(url)
        m = _PATH_RE.match(p.path)
        if not m:
            raise CloudError("cloud_not_found", url)
        service, user_id, post_id = m.group(1), m.group(2), m.group(3)
        origin = f"{p.scheme or 'https'}://{p.netloc}"
        s = session()
        hdrs = {"Referer": f"{origin}/"}
        api_hdrs = {"Accept": "application/json", "Referer": f"{origin}/"}

        if post_id:
            data = get_json(s, f"{origin}/api/v1/{service}/user/{user_id}/post/{post_id}", headers=api_hdrs)
            post = data.get("post") if isinstance(data, dict) and isinstance(data.get("post"), dict) else data
            if not isinstance(post, dict):
                raise CloudError("cloud_empty", url)
            files: list[CloudFile] = []
            _collect_post(post, origin, hdrs, set(), files)
            if not files:
                raise CloudError("cloud_empty", url)
            if len(files) <= 10:
                for cf in files:
                    cf.size = head_size(s, cf.url, hdrs)
            title = str(post.get("title") or f"{user_id} - {post_id}").strip()
            return CloudListing(self.name, title, files=files, is_folder=len(files) > 1)

        creator_name = f"{service}/{user_id}"
        try:
            prof = get_json(s, f"{origin}/api/v1/{service}/user/{user_id}/profile", headers=api_hdrs)
            if isinstance(prof, dict) and prof.get("name"):
                creator_name = f"{prof['name']} ({service})"
        except Exception:
            pass

        files = []
        seen: set[str] = set()
        note = ""
        use_alt_posts = False
        for page_idx in range(_MAX_PAGES):
            offset = page_idx * 50
            ep = f"{origin}/api/v1/{service}/user/{user_id}" if use_alt_posts else f"{origin}/api/v1/{service}/user/{user_id}/posts"
            try:
                raw_posts = get_json(s, ep, params={"o": offset}, headers=api_hdrs)
            except CloudError as exc:
                if exc.code == "cloud_not_found" and not use_alt_posts and page_idx == 0:
                    use_alt_posts = True
                    raw_posts = get_json(s, f"{origin}/api/v1/{service}/user/{user_id}", params={"o": offset}, headers=api_hdrs)
                else:
                    raise
            posts = raw_posts.get("posts") if isinstance(raw_posts, dict) else raw_posts
            if not isinstance(posts, list) or not posts:
                break
            for post in posts:
                if isinstance(post, dict):
                    _collect_post(post, origin, hdrs, seen, files)
            if len(posts) < 50:
                break
            if page_idx == _MAX_PAGES - 1:
                note = "İlk 250 gönderi listelendi (tüm arşiv için Grab-All kullan)."

        if not files:
            raise CloudError("cloud_empty", url)
        return CloudListing(self.name, creator_name, files=files, is_folder=True, note=note)


def register(ctx) -> None:
    ctx.register_cloud(KemonoCoomer())
