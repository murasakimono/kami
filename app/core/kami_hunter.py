"""Kami Hunter: Internet Archive, Wayback CDX, Dailymotion, SoundCloud, Bandcamp, Ok.ru, VK, Mail.ru ve Reddit uzerinden kayip medya arama."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import html
import re
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def _search_archive_org(query: str, sess: requests.Session) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        r = sess.get(
            "https://archive.org/advancedsearch.php",
            params={
                "q": f"({query}) AND mediatype:(audio OR movies)",
                "fl[]": ["identifier", "title", "mediatype", "date"],
                "rows": 12,
                "output": "json",
            },
            timeout=12,
        )
        if not r.ok:
            return out
        docs = ((r.json().get("response") or {}).get("docs")) or []
        for d in docs:
            ident = d.get("identifier") or ""
            if not ident:
                continue
            out.append({
                "title": str(d.get("title") or ident),
                "url": f"https://archive.org/details/{ident}",
                "source": "Internet Archive",
                "kind": str(d.get("mediatype") or "audio"),
                "date": str(d.get("date") or "")[:10],
            })
    except Exception:
        pass
    return out


def _search_dailymotion(query: str, sess: requests.Session) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        r = sess.get(
            "https://api.dailymotion.com/videos",
            params={"search": query, "limit": 10, "fields": "id,title,url,created_time"},
            timeout=12,
        )
        if not r.ok:
            return out
        for it in r.json().get("list") or []:
            u = it.get("url") or ""
            if u:
                out.append({
                    "title": str(it.get("title") or u),
                    "url": u,
                    "source": "Dailymotion",
                    "kind": "video",
                    "date": "",
                })
    except Exception:
        pass
    return out


def _search_wayback(site: str, sess: requests.Session) -> tuple[list[dict[str, Any]], str]:
    out: list[dict[str, Any]] = []
    prefix = str(site or "").strip().removeprefix("https://").removeprefix("http://").strip("/")
    if not prefix:
        return out, ""
    try:
        r = sess.get(
            "https://web.archive.org/cdx/search/cdx",
            params={
                "url": f"{prefix}/*",
                "filter": "mimetype:(audio/.*|video/.*)",
                "output": "json",
                "limit": 12,
                "collapse": "urlkey",
            },
            timeout=12,
        )
        if not r.ok:
            return out, f"Wayback: HTTP {r.status_code}"
        rows = r.json() or []
        for row in rows[1:]:
            if len(row) >= 3:
                ts, orig = row[1], row[2]
                out.append({
                    "title": orig.rsplit("/", 1)[-1] or orig,
                    "url": f"https://web.archive.org/web/{ts}id_/{orig}",
                    "source": "Wayback Media",
                    "kind": "archive",
                    "date": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}" if len(ts) >= 8 else "",
                })
    except Exception:
        return out, "Wayback: bağlantı hatası"
    return out, ""


def _search_reddit(query: str, sess: requests.Session) -> tuple[list[dict[str, Any]], str]:
    out: list[dict[str, Any]] = []
    try:
        r = sess.get(
            "https://www.reddit.com/search.json",
            params={"q": query, "limit": 10, "sort": "relevance"},
            headers={"User-Agent": "KamiHunter/1.0"},
            timeout=12,
        )
        if not r.ok:
            return out, f"Reddit: girişsiz istek reddedildi (HTTP {r.status_code})"
        children = ((r.json().get("data") or {}).get("children")) or []
        for ch in children:
            d = ch.get("data") or {}
            u = d.get("url_overridden_by_dest") or d.get("url") or ""
            if not u or "reddit.com/r/" in u and "/comments/" in u:
                continue
            out.append({
                "title": str(d.get("title") or u),
                "url": u,
                "source": "Reddit",
                "kind": "link",
                "date": "",
            })
    except Exception:
        return out, "Reddit: bağlantı hatası"
    return out, ""


def _search_soundcloud(query: str, sess: requests.Session) -> tuple[list[dict[str, Any]], str]:
    out: list[dict[str, Any]] = []
    try:
        r = sess.get("https://soundcloud.com/search/sounds", params={"q": query}, timeout=12)
        if not r.ok:
            return out, f"SoundCloud: HTTP {r.status_code}"
        body = r.text if isinstance(getattr(r, "text", None), str) else ""
        for m in re.finditer(r'href="(https?://soundcloud\.com/[^/"\s]+/[^/"\s]+)"', body):
            u = m.group(1)
            if "/search" in u or "/tags" in u:
                continue
            slug = u.rsplit("/", 1)[-1].replace("-", " ").title()
            out.append({"title": slug, "url": u, "source": "SoundCloud", "kind": "audio", "date": ""})
            if len(out) >= 8:
                break
    except Exception:
        return out, "SoundCloud: bağlantı hatası"
    return out, ""


def _search_bandcamp(query: str, sess: requests.Session) -> tuple[list[dict[str, Any]], str]:
    out: list[dict[str, Any]] = []
    try:
        r = sess.get("https://bandcamp.com/search", params={"q": query, "item_type": "t"}, timeout=12)
        if not r.ok:
            return out, f"Bandcamp: HTTP {r.status_code}"
        body = r.text if isinstance(getattr(r, "text", None), str) else ""
        for m in re.finditer(r'href="(https?://[^"]+\.bandcamp\.com/(?:track|album)/[^"?]+)"', body):
            u = m.group(1)
            slug = u.rsplit("/", 1)[-1].replace("-", " ").title()
            out.append({"title": slug, "url": u, "source": "Bandcamp", "kind": "audio", "date": ""})
            if len(out) >= 8:
                break
    except Exception:
        return out, "Bandcamp: bağlantı hatası"
    return out, ""


def _search_okru(query: str, sess: requests.Session) -> tuple[list[dict[str, Any]], str]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        r = sess.get("https://ok.ru/video/search", params={"st.query": query}, timeout=12)
        if not r.ok:
            return out, f"Ok.ru: HTTP {r.status_code}"
        body = r.text if isinstance(getattr(r, "text", None), str) else ""
        for m in re.finditer(r'<a[^>]+href=["\'](/video/(\d+))["\'][^>]*>(.*?)</a>', body, flags=re.S | re.I):
            vid = m.group(2)
            if vid in seen:
                continue
            seen.add(vid)
            title = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", m.group(3)))).strip()
            out.append({
                "title": title or f"Ok.ru {vid}",
                "url": f"https://ok.ru/video/{vid}",
                "source": "Ok.ru",
                "kind": "video",
                "date": "",
            })
            if len(out) >= 8:
                break
    except Exception:
        return out, "Ok.ru: bağlantı hatası"
    return out, ""


def _search_vk(query: str, sess: requests.Session) -> tuple[list[dict[str, Any]], str]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        r = sess.get("https://vkvideo.ru/", params={"q": query}, timeout=12, allow_redirects=True)
        if not r.ok:
            return out, f"VK: HTTP {r.status_code}"
        final_u = str(getattr(r, "url", "") or "").lower()
        if "/login" in final_u or "login.vk.com" in final_u:
            return out, "VK: giriş istendi"
        body = r.text if isinstance(getattr(r, "text", None), str) else ""
        for m in re.finditer(r'<a[^>]+href=["\'](?:https?://(?:vk\.com|vkvideo\.ru))?/video(-?\d+_\d+)[^"\']*["\'][^>]*>(.*?)</a>', body, flags=re.S | re.I):
            oid_id = m.group(1)
            if oid_id in seen:
                continue
            seen.add(oid_id)
            title = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", m.group(2)))).strip()
            out.append({
                "title": title or f"VK {oid_id}",
                "url": f"https://vk.com/video{oid_id}",
                "source": "VK Video",
                "kind": "video",
                "date": "",
            })
            if len(out) >= 8:
                break
    except Exception:
        return out, "VK: bağlantı hatası"
    return out, ""


def _search_mailru(query: str, sess: requests.Session) -> tuple[list[dict[str, Any]], str]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        r = sess.get("https://my.mail.ru/video/search", params={"q": query}, timeout=12)
        if not r.ok:
            return out, f"Mail.ru: HTTP {r.status_code}"
        body = r.text if isinstance(getattr(r, "text", None), str) else ""
        for m in re.finditer(r'<a[^>]+href=["\']((?:https?://my\.mail\.ru)?/(?:mail|bk|inbox|list)/[^/"\'\s]+/video/[^"\'\s]+\.html)["\'][^>]*>(.*?)</a>', body, flags=re.S | re.I):
            u = urljoin("https://my.mail.ru", html.unescape(m.group(1)))
            if u in seen:
                continue
            seen.add(u)
            title = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", m.group(2)))).strip()
            out.append({
                "title": title or u.rsplit("/", 1)[-1],
                "url": u,
                "source": "Mail.ru",
                "kind": "video",
                "date": "",
            })
            if len(out) >= 8:
                break
    except Exception:
        return out, "Mail.ru: bağlantı hatası"
    return out, ""


def preview_url(url: str) -> dict[str, Any]:
    """Onizleme icin dogrudan ses/video akis adresini cozer (Archive.org / Ok.ru / VK / Mail.ru / yt-dlp)."""
    u = str(url or "").strip()
    if not u:
        return {"ok": False, "error": "Adres boş"}
    if "archive.org/details/" in u:
        ident = u.rstrip("/").rsplit("/", 1)[-1]
        try:
            r = requests.get(f"https://archive.org/metadata/{ident}", timeout=10)
            if r.ok:
                for f in (r.json().get("files") or []):
                    name = str(f.get("name") or "")
                    if name.lower().endswith((".mp3", ".ogg", ".m4a", ".wav")):
                        return {"ok": True, "stream": f"https://archive.org/download/{ident}/{quote(name)}"}
        except Exception:
            pass
    host = (urlparse(u).hostname or "").lower()
    if host.endswith(("ok.ru", "odnoklassniki.ru", "vk.com", "vkvideo.ru", "my.mail.ru")):
        try:
            from app.core import season_scraper
            direct = season_scraper.resolve_embed(u)
            if direct:
                return {"ok": True, "stream": direct}
        except Exception:
            pass
    try:
        from app.engines import ytdlp_engine as yt
        info = yt.probe(u) if hasattr(yt, "probe") else None
        if isinstance(info, dict) and info.get("url"):
            return {"ok": True, "stream": info["url"]}
    except Exception:
        pass
    return {"ok": False, "error": "Önizleme akışı çözülemedi"}


def _norm_track_key(title: str) -> str:
    import unicodedata

    t = str(title or "").translate(str.maketrans("ÇĞİIÖŞÜçğıöşüÂÎÛâîû", "cgiiouucgiosuaiuaiu")).lower()
    t = "".join(ch for ch in unicodedata.normalize("NFKD", t) if not unicodedata.combining(ch))
    t = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", t)
    for noise in ("official", "video", "audio", "lyrics", "sözleri", "sozleri", "hd", "hq", "192kbps", "320kbps", "underground", "rap"):
        t = re.sub(rf"\b{noise}\b", " ", t)
    t = re.sub(r"[^a-z0-9]+", " ", t).strip()
    return t


_SOURCE_QUALITY = {
    "Bandcamp": 95,
    "Archive.org": 92,
    "SoundCloud": 84,
    "VK": 74,
    "Ok.ru": 70,
    "Mail.ru": 66,
    "Dailymotion": 62,
    "Wayback": 55,
    "Reddit": 48,
}


def _score_item(it: dict[str, Any], query: str = "") -> int:
    src = str(it.get("source") or "")
    score = _SOURCE_QUALITY.get(src, 40)
    title = str(it.get("title") or "").lower()
    if any(k in title for k in ("flac", "wav", "lossless", "320")):
        score += 12
    if any(k in title for k in ("live", "konser", "remix", "nightcore", "slowed")):
        score -= 6
    dur = float(it.get("duration") or 0)
    if 60 <= dur <= 420:
        score += 6
    q_words = [w for w in _norm_track_key(query).split() if len(w) >= 2]
    nkey = _norm_track_key(title)
    if q_words and all(w in nkey for w in q_words):
        score += 10
    return score


def cluster_and_rank_items(items: list[dict[str, Any]], query: str = "") -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Benzer/ayna kayitlari normalize basliga gore kumeler ve kalite puanina gore siralar."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for it in items:
        copy = dict(it)
        copy["quality_score"] = _score_item(copy, query)
        key = _norm_track_key(copy.get("title") or "") or str(copy.get("url") or "")
        groups.setdefault(key, []).append(copy)

    clusters: list[dict[str, Any]] = []
    for key, grp in groups.items():
        grp.sort(key=lambda x: int(x.get("quality_score") or 0), reverse=True)
        best = dict(grp[0])
        best["mirrors_count"] = len(grp)
        best["cluster_key"] = key
        clusters.append({"key": key, "best": best, "mirrors": grp})
    clusters.sort(key=lambda cl: int(cl["best"].get("quality_score") or 0), reverse=True)
    ranked_best = [cl["best"] for cl in clusters]
    return ranked_best, clusters


def archive_underground_track(
    url_or_path: str,
    title: str = "",
    artist: str = "",
    out_dir: str = "",
    lyrics: str = "",
) -> dict[str, Any]:
    """Underground parcayi indirir/kopyalar, ID3 etiketlerini isler ve varsa .lrc/.lyrics.txt yan dosyasi yazar."""
    import shutil
    import subprocess
    from pathlib import Path
    from app import paths
    from app.engines.ytdlp_engine import find_ffmpeg

    src_in = str(url_or_path or "").strip()
    if not src_in:
        return {"ok": False, "error": "Kaynak adres veya dosya gerekli"}

    dest_dir = Path(out_dir) if out_dir else (paths.downloads_dir() / "Müzik" / "Kami Hunter Arşiv")
    dest_dir.mkdir(parents=True, exist_ok=True)
    base_name = re.sub(r'[<>:"/\\|?*]+', "_", f"{artist + ' - ' if artist else ''}{title or 'underground_track'}").strip(" .")[:100] or "underground_track"
    dst = dest_dir / f"{base_name}.mp3"

    src_file = Path(src_in)
    if src_file.is_file():
        tmp_src = src_file
    else:
        stream = src_in
        pr = preview_url(src_in)
        if pr.get("ok") and pr.get("stream"):
            stream = pr["stream"]
        tmp_dl = dest_dir / f".{base_name}_raw.tmp"
        try:
            with requests.get(stream, stream=True, timeout=25, headers={"User-Agent": UA}) as resp:
                resp.raise_for_status()
                with open(tmp_dl, "wb") as f:
                    for chunk in resp.iter_content(65536):
                        if chunk:
                            f.write(chunk)
        except Exception:
            try:
                import yt_dlp
                opts = {"quiet": True, "no_warnings": True, "outtmpl": str(dest_dir / f".{base_name}_yt.%(ext)s"), "format": "bestaudio/best"}
                ff = find_ffmpeg()
                if ff:
                    opts["ffmpeg_location"] = ff
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([src_in])
                cands = sorted(dest_dir.glob(f".{base_name}_yt.*"), key=lambda x: x.stat().st_mtime, reverse=True)
                if cands:
                    tmp_dl = cands[0]
            except Exception as exc:
                return {"ok": False, "error": f"İndirme hatası: {str(exc)[:120]}"}
        if not tmp_dl.is_file():
            return {"ok": False, "error": "Ses dosyası indirilemedi"}
        tmp_src = tmp_dl

    ff = find_ffmpeg()
    meta_ok = False
    if ff and tmp_src != dst:
        nowin = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        cmd = [ff, "-y", "-i", str(tmp_src), "-vn", "-b:a", "192k"]
        if title:
            cmd += ["-metadata", f"title={title}"]
        if artist:
            cmd += ["-metadata", f"artist={artist}"]
        cmd += ["-metadata", "genre=Underground Rap", str(dst)]
        r = subprocess.run(cmd, capture_output=True, creationflags=nowin)
        meta_ok = r.returncode == 0 and dst.is_file()
    if not meta_ok and tmp_src != dst:
        shutil.copy2(tmp_src, dst)
    if tmp_src != src_file and tmp_src.is_file() and tmp_src != dst:
        try:
            tmp_src.unlink()
        except OSError:
            pass

    sidecar = ""
    if lyrics and str(lyrics).strip():
        sc = dst.with_suffix(".lrc" if "[" in lyrics else ".lyrics.txt")
        sc.write_text(str(lyrics).strip(), encoding="utf-8")
        sidecar = str(sc)

    return {"ok": dst.is_file(), "path": str(dst), "title": title, "artist": artist, "lyrics_path": sidecar}


def search(query: str, *, site: str = "", session: requests.Session | None = None, cluster: bool = True) -> dict[str, Any]:
    q = " ".join(str(query or "").split()).strip()
    if len(q) < 2:
        return {"ok": False, "error": "En az 2 karakter girin", "items": [], "clusters": [], "notes": []}

    def _run(fn):
        s = session or requests.Session()
        if session is None:
            s.headers["User-Agent"] = UA
        arg = site if fn is _search_wayback else q
        res = fn(arg, s)
        return res if isinstance(res, tuple) else (res, "")

    items: list[dict[str, Any]] = []
    notes: list[str] = []
    with ThreadPoolExecutor(max_workers=9) as pool:
        for res, note in pool.map(
            _run,
            (
                _search_archive_org,
                _search_dailymotion,
                _search_soundcloud,
                _search_bandcamp,
                _search_okru,
                _search_vk,
                _search_mailru,
                _search_wayback,
                _search_reddit,
            ),
        ):
            items.extend(res)
            if note:
                notes.append(note)

    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for it in items:
        u = it.get("url") or ""
        if u and u not in seen:
            seen.add(u)
            uniq.append(it)
    if cluster:
        ranked, clusters = cluster_and_rank_items(uniq, query=q)
        return {"ok": True, "query": q, "items": ranked, "clusters": clusters, "notes": notes}
    return {"ok": True, "query": q, "items": uniq, "clusters": [], "notes": notes}
