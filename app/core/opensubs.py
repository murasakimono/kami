"""OpenSubtitles.com resmi REST API: altyazisi olmayan videoya Turkce (ya da secilen dilde) altyazi bulur.
Anahtar kullanicinin (opensubtitles.com/consumers), DPAPI ile saklanir. Hash: OpenSubtitles video hash'i."""
from __future__ import annotations

import os
import re
import struct
from pathlib import Path

import requests

API = "https://api.opensubtitles.com/api/v1"
UA = "Kami v1.3"


def movie_hash(path: str) -> str:
    size = os.path.getsize(path)
    if size < 131072:
        return ""
    h = size
    with open(path, "rb") as f:
        for off in (0, max(0, size - 65536)):
            f.seek(off)
            buf = f.read(65536)
            for (q,) in struct.iter_unpack("<Q", buf[: len(buf) // 8 * 8]):
                h = (h + q) & 0xFFFFFFFFFFFFFFFF
    return f"{h:016x}"


def _query(path: str) -> str:
    s = Path(path).stem
    s = re.sub(r"[\[(].*?[\])]", " ", s)
    s = re.sub(r"\b(1080p|720p|2160p|4k|x26[45]|hevc|web[- ]?dl|bluray|webrip|aac|ddp?5\.1|10bit)\b.*", " ", s, flags=re.I)
    return re.sub(r"[._]+", " ", s).strip()


EP_PATTERNS = [
    r"[Ss](\d{1,2})\s*[Ee](\d{1,3})",                                  # S01E02
    r"\b(\d{1,2})x(\d{1,3})\b",                                        # 1x02
    r"(\d{1,2})\s*\.?\s*[Ss]ezon\s*(\d{1,3})\s*\.?\s*[Bb][öo]l[üu]m",     # 1. Sezon 2. Bolum
    r"[Ss]ezon\s*(\d{1,2})\D{1,6}?[Bb][öo]l[üu]m\s*(\d{1,3})",           # Sezon 1 Bolum 2
    r"[Ss]eason\s*(\d{1,2})\D{1,6}?[Ee]pisode\s*(\d{1,3})",              # Season 1 Episode 2
]


def parse(path: str, title: str = "") -> dict:
    """Dosya adi / oynaticidaki baslik -> {show, season, episode, year}. Dizi degilse season/episode None."""
    for src in [x for x in (title, Path(path).stem) if x]:
        text = re.sub(r"[._]+", " ", src)
        for pat in EP_PATTERNS:
            m = re.search(pat, text)
            if m:
                show = re.sub(r"[\[(].*?[\])]", " ", text[:m.start()])
                show = re.sub(r"[-–:|]+\s*$", "", show).strip()
                return {"show": show or _query(path), "season": int(m.group(1)), "episode": int(m.group(2)), "year": None}
    q = _query(path)
    y = re.search(r"\b(19|20)\d{2}\b", q)
    return {"show": re.sub(r"\b(19|20)\d{2}\b.*", "", q).strip() or q, "season": None, "episode": None,
            "year": int(y.group(0)) if y else None}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _similar(a: str, b: str) -> float:
    """Kelime siniri duyarli benzerlik: kisa dizi adlarinin ('see', 'it') rastgele metin icinde substring eslesmesini onler."""
    from difflib import SequenceMatcher
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ta, tb = a.split(), b.split()
    if len(ta) >= 1 and len(tb) >= 1:
        # Sadece tam kelime dizisi (word-boundary) geciyorsa yuksek puan ver; aksi halde SequenceMatcher
        sa, sb = f" {a} ", f" {b} "
        if (len(a) >= 4 and sa in sb) or (len(b) >= 4 and sb in sa):
            shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
            return max(0.72, len(shorter) / len(longer))
    return SequenceMatcher(None, a, b).ratio()


def _judge(item: dict, info: dict) -> tuple[bool, float]:
    """Sonuc bu dosyaya mi ait? (gecerli, puan). Dizi: sezon/bolum ve dizi adi tutmali."""
    at = item.get("attributes") or {}
    fd = at.get("feature_details") or {}
    names = [fd.get("parent_title"), fd.get("title"), fd.get("movie_name"), at.get("release")]
    sim = max(_similar(info["show"], n or "") for n in names)
    if info["season"] is not None:
        if fd.get("season_number") not in (None, info["season"]) or fd.get("episode_number") not in (None, info["episode"]):
            return False, 0.0
        if fd.get("season_number") is None and not re.search(rf"[Ss]0?{info['season']}[Ee]0?{info['episode']}\b", at.get("release") or ""):
            return False, 0.0
    if sim < 0.65:
        return False, 0.0
    score = sim * 3 + (2 if at.get("moviehash_match") else 0) + min(2.0, (at.get("download_count") or 0) / 5000)
    return True, score


def search(path: str, key: str, lang: str = "tr", title: str = "") -> dict:
    """Dogrulanmis adaylar (en iyi once). Hash eslesmesi bile olsa adi/bolumu tutmayan elenir."""
    hdr = {"Api-Key": key, "User-Agent": UA, "Accept": "application/json"}
    info = parse(path, title)
    base = {"languages": lang, "order_by": "download_count"}
    tries: list[dict] = []
    mh = movie_hash(path)
    if mh:
        tries.append({"moviehash": mh})
    if info["season"] is not None:
        tries.append({"query": info["show"], "season_number": info["season"], "episode_number": info["episode"], "type": "episode"})
    else:
        tries.append({"query": info["show"], **({"year": info["year"]} if info["year"] else {})})
    seen: set = set()
    cands: list[dict] = []
    for extra in tries:
        try:
            r = requests.get(f"{API}/subtitles", params={**base, **extra}, headers=hdr, timeout=15)
        except requests.RequestException as exc:
            return {"ok": False, "error": f"net: {exc.__class__.__name__}"}
        if r.status_code in (401, 403):
            return {"ok": False, "error": "bad_key"}
        if r.status_code != 200:
            continue
        for it in r.json().get("data") or []:
            at = it.get("attributes") or {}
            files = at.get("files") or []
            if not files or files[0]["file_id"] in seen:
                continue
            ok, score = _judge(it, info)
            seen.add(files[0]["file_id"])
            fd = at.get("feature_details") or {}
            name = fd.get("parent_title") or fd.get("movie_name") or fd.get("title") or ""
            ep = f" S{fd['season_number']:02d}E{fd['episode_number']:02d}" if fd.get("season_number") and fd.get("episode_number") else ""
            cands.append({"file_id": files[0]["file_id"], "ok": ok, "score": score, "title": f"{name}{ep}".strip(),
                          "release": at.get("release", ""), "downloads": at.get("download_count") or 0,
                          "hash": bool(at.get("moviehash_match"))})
    cands.sort(key=lambda c: (not c["ok"], -c["score"]))
    return {"ok": True, "info": info, "candidates": cands[:8]}


def download(path: str, key: str, file_id: int, lang: str = "tr", release: str = "") -> dict:
    hdr = {"Api-Key": key, "User-Agent": UA, "Accept": "application/json", "Content-Type": "application/json"}
    try:
        r = requests.post(f"{API}/download", json={"file_id": int(file_id), "sub_format": "srt"}, headers=hdr, timeout=15)
        if r.status_code != 200:
            return {"ok": False, "error": "quota" if r.status_code in (406, 429) else f"download_{r.status_code}"}
        link = r.json().get("link")
        srt = requests.get(link, timeout=20).content.decode("utf-8", "replace") if link else ""
    except (requests.RequestException, ValueError) as exc:
        return {"ok": False, "error": f"net: {exc.__class__.__name__}"}
    if not srt.strip():
        return {"ok": False, "error": "empty"}
    p = Path(path)
    out = p.with_name(f"{p.stem}.{lang}.srt")
    if out.exists():
        out = p.with_name(f"{p.stem}.{lang}.opensubtitles.srt")
    out.write_text(srt, encoding="utf-8")
    return {"ok": True, "path": str(out), "srt": srt, "release": release}


def find_and_download(path: str, key: str, lang: str = "tr", title: str = "") -> dict:
    """Otomatik: yalnizca DOGRULANMIS en iyi aday indirilir; yoksa not_found (yanlis dizinin altyazisi inmez)."""
    res = search(path, key, lang, title)
    if not res.get("ok"):
        return res
    best = next((c for c in res["candidates"] if c["ok"]), None)
    if not best:
        return {"ok": False, "error": "not_found"}
    return download(path, key, best["file_id"], lang, best["release"])
