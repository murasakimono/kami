"""Ses/video dosyasi etiket yardimcilari (mutagen): sanatci/baslik cikarma, etiket + soz + kapak yazma."""
from __future__ import annotations

import logging
import os
import re
from typing import Any

log = logging.getLogger(__name__)

AUDIO_EXT = {".mp3", ".m4a", ".flac", ".ogg", ".opus", ".wav", ".aac", ".wma"}
VIDEO_EXT = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".ts"}

# YouTube basliklarindaki gurultu: (Official Video), [Lyrics], (HD) ...
_NOISE = re.compile(r"\s*[\(\[\{](?:[^\)\]\}]*?(?:official|video|audio|lyric|lyrics|hd|4k|visualizer|music video|"
                    r"clip|klip|resmi|şarkı sözleri|sözleri|mv|m/v|live|remaster(?:ed)?)[^\)\]\}]*?)[\)\]\}]", re.I)


def kind_of(path: str) -> str:
    ext = os.path.splitext(path or "")[1].lower()
    return "audio" if ext in AUDIO_EXT else "video" if ext in VIDEO_EXT else ""


def clean_title(t: str) -> str:
    t = _NOISE.sub("", t or "")
    t = re.sub(r"\s*\|\s*.*$", "", t)                       # "Sarki | Kanal adi"
    t = re.sub(r"\s+(?:ft\.?|feat\.?)\s+.*$", "", t, flags=re.I)
    return re.sub(r"\s{2,}", " ", t).strip(" -–—_")


def split_artist_title(text: str) -> tuple[str, str]:
    """'Sanatci - Sarki (Official Video)' -> ('Sanatci', 'Sarki'). Ayirac yoksa ('', temiz baslik)."""
    text = os.path.basename(text or "")
    root, ext = os.path.splitext(text)
    if ext.lower() in AUDIO_EXT | VIDEO_EXT:
        text = root
    for sep in (" - ", " – ", " — ", " -- ", " | "):
        if sep in text:
            a, t = text.split(sep, 1)
            return a.strip(), clean_title(t)
    return "", clean_title(text)


def read_tags(path: str) -> dict[str, Any]:
    """{artist, title, album, duration} (bilinmeyen alanlar bos)."""
    out: dict[str, Any] = {"artist": "", "title": "", "album": "", "duration": 0.0}
    try:
        import mutagen
        f = mutagen.File(path, easy=True)
        if f is not None:
            out["duration"] = float(getattr(f.info, "length", 0) or 0)
            tags = f.tags or {}
            for k in ("artist", "title", "album"):
                v = tags.get(k)
                if v:
                    out[k] = str(v[0] if isinstance(v, list) else v)
    except Exception:
        log.debug("Etiket okunamadi: %s", path, exc_info=True)
    return out


def guess(path: str, title_hint: str = "") -> dict[str, Any]:
    """Etiketler + dosya adi -> en iyi sanatci/baslik tahmini."""
    tags = read_tags(path)
    artist, title = tags["artist"], tags["title"]
    if title and not artist:
        a2, t2 = split_artist_title(title)
        if a2:
            artist, title = a2, t2
    if not title or not artist:
        a2, t2 = split_artist_title(title_hint or os.path.basename(path))
        artist = artist or a2
        title = title or t2
    return {**tags, "artist": artist.strip(), "title": clean_title(title)}


def write_mp3_tags(path: str, *, artist: str = "", title: str = "", album: str = "", date: str = "",
                   track: str = "", lyrics: str = "", cover: bytes | None = None,
                   mb_recording: str = "") -> bool:
    """ID3v2.4: TPE1/TIT2/TALB/TDRC/TRCK + USLT (senkron LRC metni de olur; Pure Music okur) + APIC."""
    try:
        from mutagen.id3 import APIC, ID3, ID3NoHeaderError, TALB, TDRC, TIT2, TPE1, TPE2, TRCK, TXXX, USLT
        try:
            tags = ID3(path)
        except ID3NoHeaderError:
            tags = ID3()
        if artist:
            tags.setall("TPE1", [TPE1(encoding=3, text=artist)])
            tags.setall("TPE2", [TPE2(encoding=3, text=artist)])
        if title:
            tags.setall("TIT2", [TIT2(encoding=3, text=title)])
        if album:
            tags.setall("TALB", [TALB(encoding=3, text=album)])
        if date:
            tags.setall("TDRC", [TDRC(encoding=3, text=date)])
        if track:
            tags.setall("TRCK", [TRCK(encoding=3, text=track)])
        if lyrics:
            tags.setall("USLT", [USLT(encoding=3, lang="XXX", desc="", text=lyrics)])
        if cover:
            mime = "image/png" if cover[:4] == b"\x89PNG" else "image/jpeg"
            tags.setall("APIC", [APIC(encoding=3, mime=mime, type=3, desc="Cover", data=cover)])
        if mb_recording:
            tags.setall("TXXX:MusicBrainz Track Id",
                        [TXXX(encoding=3, desc="MusicBrainz Track Id", text=mb_recording)])
        tags.save(path, v2_version=4)
        return True
    except Exception:
        log.exception("MP3 etiketi yazilamadi: %s", os.path.basename(path))
        return False


def write_generic_tags(path: str, **kw: str) -> bool:
    """MP3 disi (m4a/flac/ogg): easy arayuzle temel etiketler + soz (destekleniyorsa)."""
    if path.lower().endswith(".mp3"):
        return write_mp3_tags(path, **kw)
    try:
        import mutagen
        f = mutagen.File(path, easy=True)
        if f is None:
            return False
        for k in ("artist", "title", "album", "date"):
            if kw.get(k):
                f[k] = kw[k]
        if kw.get("track"):
            f["tracknumber"] = kw["track"]
        f.save()
        return True
    except Exception:
        log.exception("Etiket yazilamadi: %s", os.path.basename(path))
        return False


def safe_name(s: str, limit: int = 120) -> str:
    s = "".join(" " if (c in '/:*?"<>|\\' or ord(c) < 32) else c for c in (s or "")).strip(" .")
    s = re.sub(r"\s{2,}", " ", s)
    return s[:limit].rstrip(" .") or "_"
