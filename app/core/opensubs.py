"""OpenSubtitles.com resmi REST API: altyazisi olmayan videoya Turkce (ya da secilen dilde) altyazi bulur.
Anahtar kullanicinin (opensubtitles.com/consumers), DPAPI ile saklanir. Hash: OpenSubtitles video hash'i."""
from __future__ import annotations

import os
import re
import struct
from pathlib import Path

import requests

API = "https://api.opensubtitles.com/api/v1"
UA = "Kami v1.1"


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


def find_and_download(path: str, key: str, lang: str = "tr") -> dict:
    hdr = {"Api-Key": key, "User-Agent": UA, "Accept": "application/json"}
    params = {"languages": lang, "order_by": "download_count"}
    mh = movie_hash(path)
    tries = ([{"moviehash": mh}] if mh else []) + [{"query": _query(path)}]
    data = []
    for extra in tries:
        try:
            r = requests.get(f"{API}/subtitles", params={**params, **extra}, headers=hdr, timeout=15)
        except requests.RequestException as exc:
            return {"ok": False, "error": f"net: {exc.__class__.__name__}"}
        if r.status_code == 401 or r.status_code == 403:
            return {"ok": False, "error": "bad_key"}
        if r.status_code != 200:
            continue
        data = r.json().get("data") or []
        if data:
            break
    if not data:
        return {"ok": False, "error": "not_found"}
    files = (data[0].get("attributes") or {}).get("files") or []
    if not files:
        return {"ok": False, "error": "not_found"}
    try:
        r = requests.post(f"{API}/download", json={"file_id": files[0]["file_id"], "sub_format": "srt"}, headers={**hdr, "Content-Type": "application/json"}, timeout=15)
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
    return {"ok": True, "path": str(out), "srt": srt, "release": (data[0].get("attributes") or {}).get("release", "")}
