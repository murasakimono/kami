"""Muzik arsivcisi: MusicBrainz ile dogru etiket -> <muzik klasoru>/<Sanatci>/<Album>/<NN Baslik>.mp3 + kapak.

MusicBrainz kurali: anlamli User-Agent + saniyede en fazla 1 istek. Kapak: Cover Art Archive (front-500).
Eslesme puani dusukse (<85) dosyaya DOKUNULMAZ (yanlis etiket yazmaktansa birak).
"""
from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from typing import Any

import requests

from app.core import media_meta

log = logging.getLogger(__name__)

MB = "https://musicbrainz.org/ws/2"
CAA = "https://coverartarchive.org/release"
MIN_SCORE = 85
_rate = threading.Lock()
_last = [0.0]


def _get(session: requests.Session, url: str, **kw: Any) -> requests.Response:
    with _rate:   # 1 istek/sn
        wait = 1.05 - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()
    from app.core.lyrics import _ua
    kw.setdefault("timeout", 20)
    kw.setdefault("headers", {})["User-Agent"] = _ua()
    return session.get(url, **kw)


def _q(s: str) -> str:
    return '"' + s.replace("\\", " ").replace('"', " ") + '"'


def lookup(artist: str, title: str, duration: float = 0, session: requests.Session | None = None) -> dict | None:
    """-> {artist, title, album, date, track, recording, release} ya da None."""
    s = session or requests.Session()
    q = f"recording:{_q(title)}" + (f" AND artist:{_q(artist)}" if artist else "")
    try:
        r = _get(s, f"{MB}/recording", params={"query": q, "fmt": "json", "limit": 25})
        if r.status_code == 503:   # hiz siniri: bir kez daha
            r = _get(s, f"{MB}/recording", params={"query": q, "fmt": "json", "limit": 25})
        recs = r.json().get("recordings") or [] if r.status_code == 200 else []
    except (requests.RequestException, ValueError):
        log.warning("MusicBrainz arama hatasi", exc_info=True)
        return None
    # Arama sonuclari derlemelerle dolu: tum uygun kayitlarin yayinlarini topla, en "orijinal"i sec
    # (resmi > derleme degil > album > tekli > en eski tarih). Sure 10 sn'den fazla farkliysa ele.
    def rel_rank(rel: dict) -> tuple:
        rg = rel.get("release-group") or {}
        return (rel.get("status") != "Official", bool(rg.get("secondary-types")),
                {"Album": 0, "Single": 1, "EP": 2}.get(rg.get("primary-type") or "", 3), rel.get("date") or "9999")
    pairs: list[tuple[dict, dict | None]] = []
    for rec in recs:
        if int(rec.get("score") or 0) < MIN_SCORE:
            continue
        length = (rec.get("length") or 0) / 1000
        if duration and length and abs(length - duration) > 10:
            continue
        # "Various Artists" derlemeleri album sayilmaz (yanlis album/kapak yazmaktansa Tekliler klasoru)
        # Yayinin sanatcisi kaydin sanatcisiyla ayni olmali (MB, ayniysa yayinda artist-credit vermez);
        # "Various Artists" / "8TNT presents..." gibi derlemeler elenir.
        names = lambda ac: [c.get("name") for c in ac or []]   # noqa: E731
        rels = [r for r in rec.get("releases") or []
                if "artist-credit" not in r or names(r["artist-credit"]) == names(rec.get("artist-credit"))]
        pairs += [(rec, r) for r in rels] or [(rec, None)]
    if not pairs:
        return None
    with_rel = [p for p in pairs if p[1]]
    best = min(with_rel, key=lambda p: rel_rank(p[1])) if with_rel else pairs[0]
    rec, rel = best
    credit = rec.get("artist-credit") or []
    art = "".join(str(c.get("name") or "") + str(c.get("joinphrase") or "") for c in credit).strip() or artist
    out = {"artist": art, "title": rec.get("title") or title, "album": "", "date": "", "track": "",
           "recording": rec.get("id") or "", "release": ""}
    if rel:
        out.update(album=rel.get("title") or "", date=(rel.get("date") or "")[:4], release=rel.get("id") or "")
        media = rel.get("media") or []
        if media and media[0].get("track"):
            out["track"] = str(media[0]["track"][0].get("number") or "")
    return out


def cover(release_id: str, session: requests.Session | None = None) -> bytes | None:
    if not release_id:
        return None
    s = session or requests.Session()
    try:
        r = s.get(f"{CAA}/{release_id}/front-500", timeout=20, allow_redirects=True)
        if r.status_code == 200 and r.content[:3] in (b"\xff\xd8\xff", b"\x89PN"):
            return r.content
    except requests.RequestException:
        log.info("Kapak alinamadi", exc_info=True)
    return None


def archive(path: str, music_dir: str, title_hint: str = "", move: bool = True,
            session: requests.Session | None = None) -> dict[str, Any]:
    """Etiketle + kapak gom + Sanatci/Album klasorune tasi. -> {archive: ok|nomatch|error, path}"""
    g = media_meta.guess(path, title_hint)
    if not g["title"]:
        return {"archive": "nomatch"}
    s = session or requests.Session()
    m = lookup(g["artist"], g["title"], g.get("duration", 0), s)
    if not m:
        return {"archive": "nomatch", "artist": g["artist"], "title": g["title"]}
    img = cover(m["release"], s)
    if path.lower().endswith(".mp3"):
        media_meta.write_mp3_tags(path, artist=m["artist"], title=m["title"], album=m["album"], date=m["date"],
                                  track=m["track"], cover=img, mb_recording=m["recording"])
    else:
        media_meta.write_generic_tags(path, artist=m["artist"], title=m["title"], album=m["album"],
                                      date=m["date"], track=m["track"])
    new_path = path
    if move and music_dir:
        folder = os.path.join(music_dir, media_meta.safe_name(m["artist"]),
                              media_meta.safe_name(m["album"] or "Tekliler"))
        num = f"{int(m['track']):02d} " if (m["track"] or "").isdigit() else ""
        ext = os.path.splitext(path)[1]
        dest = os.path.join(folder, media_meta.safe_name(num + m["title"]) + ext)
        if os.path.normcase(os.path.abspath(dest)) != os.path.normcase(os.path.abspath(path)):
            os.makedirs(folder, exist_ok=True)
            base, i = dest, 2
            while os.path.exists(dest):
                dest = f"{os.path.splitext(base)[0]} ({i}){ext}"
                i += 1
            shutil.move(path, dest)
            lrc = os.path.splitext(path)[0] + ".lrc"   # soz dosyasi da beraber gitsin
            if os.path.isfile(lrc):
                shutil.move(lrc, os.path.splitext(dest)[0] + ".lrc")
            new_path = dest
        if img and not os.path.exists(os.path.join(folder, "cover.jpg")):
            try:
                with open(os.path.join(folder, "cover.jpg"), "wb") as f:
                    f.write(img)
            except OSError:
                pass
    log.info("Arsivlendi: %s - %s (%s)", m["artist"], m["title"], m["album"] or "-")
    return {"archive": "ok", "path": new_path, "artist": m["artist"], "title": m["title"], "album": m["album"]}
