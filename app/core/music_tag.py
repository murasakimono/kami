"""Muzik etiket / kapak / isimlendirme araclari (MP3tag mantigi).

- parse_name / format_name: dosya adindan sanatci + feat + baslik cozme ve kanonik isim uretme.
- rename_plan: klasordeki ses dosyalari icin "eski -> yeni" isim plani (onizleme).
- cover_embed / cover_batch: MP3 (APIC), FLAC (PICTURE), M4A (covr) kapak gomme.
- m3u_export: klasorden .m3u calma listesi.
"""
from __future__ import annotations

import base64
import logging
import os
import re
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

AUDIO_EXT = {".mp3", ".flac", ".wav", ".ogg", ".oga", ".opus", ".m4a", ".aac",
             ".wma", ".ape", ".alac", ".aiff", ".aif", ".mka", ".wv"}
FEAT_RE = re.compile(r"\b(?:ft|feat|featuring)\b\.?", re.IGNORECASE)


def _split_feat(s: str) -> list[str]:
    # virgul, & ve "ve" ile ayrilan feat listesi
    return [x.strip() for x in re.split(r"\s*[,&]\s*|\s+\bve\b\s+", s, flags=re.IGNORECASE) if x.strip()]


def parse_name(name: str) -> dict[str, Any]:
    """'Eypio ft. Ahmet, Emre - Napıyorsun Lan?' ya da 'Eypio - Napıyorsun Lan? (ft. Ahmet, Emre)'
    -> {'artist': 'Eypio', 'feat': ['Ahmet', 'Emre'], 'title': 'Napıyorsun Lan?'}"""
    root = os.path.basename(name or "").strip()
    base, ext = os.path.splitext(root)
    if ext.lower() in AUDIO_EXT:   # yalnizca gercek ses uzantisiysa kirp; "ft." noktasi uzanti degil
        root = base.strip()
    artist, title = "", root
    for sep in (" - ", " – ", " — ", " -- ", " | "):
        if sep in root:
            artist, title = root.split(sep, 1)
            break
    feat: list[str] = []
    # feat sanatcidan sonra: "Eypio ft. Ahmet, Emre"
    m = FEAT_RE.search(artist)
    if m:
        feat = _split_feat(artist[m.end():])
        artist = artist[:m.start()].strip()
    # feat sonda parantez icinde: "Napıyorsun Lan? (ft. Ahmet, Emre)"
    m = re.search(r"[\[(]\s*(?:ft|feat|featuring)\.?\s+(.*?)\s*[\])]\s*$", title, flags=re.IGNORECASE)
    if m:
        feat = _split_feat(m.group(1))
        title = title[:m.start()].strip()
    return {"artist": artist.strip(), "feat": feat, "title": title.strip()}


def format_name(p: dict[str, Any], style: str) -> str:
    """style: 'feat_after' -> 'Sanatci ft. A, B - Baslik'; 'feat_parens' -> 'Sanatci - Baslik (ft. A, B)'."""
    artist = str(p.get("artist") or "").strip()
    title = str(p.get("title") or "").strip()
    feat = [x.strip() for x in (p.get("feat") or []) if x.strip()]
    if not artist:
        return title or ""
    if feat:
        if style == "feat_parens":
            return f"{artist} - {title} (ft. {', '.join(feat)})"
        return f"{artist} ft. {', '.join(feat)} - {title}"
    return f"{artist} - {title}"


def audio_files(folder: str, recursive: bool = False) -> list[str]:
    base = Path(folder)
    if not base.is_dir():
        return []
    if recursive:
        return [str(p) for p in sorted(base.rglob("*")) if p.is_file() and p.suffix.lower() in AUDIO_EXT]
    return [str(p) for p in sorted(base.iterdir()) if p.is_file() and p.suffix.lower() in AUDIO_EXT]


def rename_plan(folder: str, style: str, recursive: bool = False) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for path in audio_files(folder, recursive):
        old = os.path.basename(path)
        parsed = parse_name(old)
        new_base = format_name(parsed, style)
        if not new_base:
            continue
        ext = os.path.splitext(old)[1]
        new = new_base + ext
        changed = os.path.normcase(new) != os.path.normcase(old)
        items.append({"path": path, "old_name": old, "new_name": new, "artist": parsed["artist"],
                      "feat": parsed["feat"], "title": parsed["title"], "changed": changed})
    return {"ok": True, "style": style, "items": items}


def cover_embed(path: str, data: bytes) -> bool:
    ext = os.path.splitext(path)[1].lower()
    mime = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"
    try:
        if ext == ".mp3":
            from mutagen.id3 import APIC, ID3, ID3NoHeaderError
            try:
                tags = ID3(path)
            except ID3NoHeaderError:
                tags = ID3()
            tags.delall("APIC")
            tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=data))
            tags.save(path, v2_version=3)
            return True
        if ext == ".flac":
            from mutagen.flac import FLAC, Picture
            f = FLAC(path)
            pic = Picture()
            pic.type = 3
            pic.mime = mime
            pic.desc = "Cover"
            pic.data = data
            f.clear_pictures()
            f.add_picture(pic)
            f.save()
            return True
        if ext in (".m4a", ".mp4", ".aac", ".alac"):
            from mutagen.mp4 import MP4, MP4Cover
            f = MP4(path)
            if f.tags is None:
                f.add_tags()
            fmt = MP4Cover.FORMAT_PNG if mime == "image/png" else MP4Cover.FORMAT_JPEG
            f.tags["covr"] = [MP4Cover(data, imageformat=fmt)]
            f.save()
            return True
        return False  # ogg/wav vb. kapak gomme desteklenmez; sessizce atlanir
    except Exception:
        log.exception("Kapak gomulemedi: %s", os.path.basename(path))
        return False


def cover_batch(folder: str, image_b64: str, recursive: bool = False) -> dict[str, Any]:
    files = audio_files(folder, recursive)
    if not files:
        return {"ok": False, "error": "empty_folder"}
    try:
        data = base64.b64decode(str(image_b64 or "").split(",", 1)[-1])
    except ValueError:
        return {"ok": False, "error": "bad_image"}
    if not data:
        return {"ok": False, "error": "bad_image"}
    done, skipped = [], []
    for path in files:
        (done if cover_embed(path, data) else skipped).append(path)
    return {"ok": True, "done": done, "skipped": skipped}


def read_id3_summary(path: str) -> dict[str, Any]:
    """Ses dosyasindaki mevcut etiketleri ve kapak durumunu okur."""
    ext = os.path.splitext(path)[1].lower()
    out = {"artist": "", "title": "", "album": "", "year": "", "has_cover": False}
    try:
        if ext == ".mp3":
            from mutagen.id3 import ID3
            t = ID3(path)
            out["artist"] = str(t.get("TPE1") or "").strip()
            out["title"] = str(t.get("TIT2") or "").strip()
            out["album"] = str(t.get("TALB") or "").strip()
            out["year"] = str(t.get("TDRC") or t.get("TYER") or "").strip()[:4]
            out["has_cover"] = bool(t.getall("APIC"))
        elif ext == ".flac":
            from mutagen.flac import FLAC
            f = FLAC(path)
            out["artist"] = str((f.get("artist") or [""])[0]).strip()
            out["title"] = str((f.get("title") or [""])[0]).strip()
            out["album"] = str((f.get("album") or [""])[0]).strip()
            out["year"] = str((f.get("date") or [""])[0]).strip()[:4]
            out["has_cover"] = bool(f.pictures)
        elif ext in (".m4a", ".mp4", ".aac", ".alac"):
            from mutagen.mp4 import MP4
            f = MP4(path)
            tg = f.tags or {}
            out["artist"] = str((tg.get("\xa9ART") or [""])[0]).strip()
            out["title"] = str((tg.get("\xa9nam") or [""])[0]).strip()
            out["album"] = str((tg.get("\xa9alb") or [""])[0]).strip()
            out["year"] = str((tg.get("\xa9day") or [""])[0]).strip()[:4]
            out["has_cover"] = bool(tg.get("covr"))
    except Exception:
        pass
    return out


def write_id3_tags(
    path: str,
    *,
    artist: str = "",
    title: str = "",
    album: str = "",
    year: str = "",
    overwrite: bool = False,
) -> bool:
    """Ses dosyasina ID3v2.3 / Vorbis / MP4 etiketlerini yazar (varsayilan sadece eksikleri doldurur)."""
    ext = os.path.splitext(path)[1].lower()
    cur = read_id3_summary(path)
    a = artist.strip() if (overwrite or not cur["artist"]) and artist.strip() else cur["artist"]
    t = title.strip() if (overwrite or not cur["title"]) and title.strip() else cur["title"]
    al = album.strip() if (overwrite or not cur["album"]) and album.strip() else cur["album"]
    y = year.strip()[:4] if (overwrite or not cur["year"]) and year.strip() else cur["year"]
    try:
        if ext == ".mp3":
            from mutagen.id3 import ID3, ID3NoHeaderError, TALB, TDRC, TIT2, TPE1
            try:
                tags = ID3(path)
            except ID3NoHeaderError:
                tags = ID3()
            if a:
                tags.setall("TPE1", [TPE1(encoding=3, text=a)])
            if t:
                tags.setall("TIT2", [TIT2(encoding=3, text=t)])
            if al:
                tags.setall("TALB", [TALB(encoding=3, text=al)])
            if y:
                tags.setall("TDRC", [TDRC(encoding=3, text=y)])
            tags.save(path, v2_version=3)
            return True
        if ext == ".flac":
            from mutagen.flac import FLAC
            f = FLAC(path)
            if a:
                f["artist"] = a
            if t:
                f["title"] = t
            if al:
                f["album"] = al
            if y:
                f["date"] = y
            f.save()
            return True
        if ext in (".m4a", ".mp4", ".aac", ".alac"):
            from mutagen.mp4 import MP4
            f = MP4(path)
            if f.tags is None:
                f.add_tags()
            if a:
                f.tags["\xa9ART"] = [a]
            if t:
                f.tags["\xa9nam"] = [t]
            if al:
                f.tags["\xa9alb"] = [al]
            if y:
                f.tags["\xa9day"] = [y]
            f.save()
            return True
    except Exception:
        log.exception("ID3 yazilamadi: %s", os.path.basename(path))
    return False


def fetch_hires_cover(artist: str, title: str, album: str = "") -> dict[str, Any]:
    """Tek tikla yuksek cozunurluklu kapak + temel metadata getirir (iTunes + CoverArtArchive)."""
    import requests
    a = str(artist or "").strip()
    t = str(title or "").strip()
    al = str(album or "").strip()
    q = " ".join(x for x in (a, t or al) if x).strip()
    if not q:
        return {"ok": False, "error": "empty_query"}

    try:
        r = requests.get(
            "https://itunes.apple.com/search",
            params={"term": q, "entity": "song", "limit": 5},
            timeout=10,
            headers={"User-Agent": "Kami/2.5"},
        )
        if r.status_code == 200:
            results = r.json().get("results") or []
            for hit in results:
                art_url = str(hit.get("artworkUrl100") or "").strip()
                if not art_url:
                    continue
                hi_url = art_url.replace("100x100bb", "1200x1200bb")
                img = requests.get(hi_url, timeout=12, headers={"User-Agent": "Kami/2.5"})
                if img.status_code != 200 or not img.content:
                    img = requests.get(art_url.replace("100x100bb", "600x600bb"), timeout=12)
                if img.status_code == 200 and img.content:
                    mime = "image/png" if img.content[:4] == b"\x89PNG" else "image/jpeg"
                    b64 = f"data:{mime};base64,{base64.b64encode(img.content).decode('ascii')}"
                    return {
                        "ok": True,
                        "source": "itunes",
                        "data_url": b64,
                        "artist": str(hit.get("artistName") or a),
                        "title": str(hit.get("trackName") or t),
                        "album": str(hit.get("collectionName") or al),
                        "year": str(hit.get("releaseDate") or "")[:4],
                    }
    except Exception:
        log.debug("iTunes kapak aramasi basarisiz", exc_info=True)

    try:
        from app.core import musicarchive
        mb = musicarchive.lookup(a, t or al)
        if mb and mb.get("release"):
            raw = musicarchive.cover(mb["release"])
            if raw:
                mime = "image/png" if raw[:4] == b"\x89PNG" else "image/jpeg"
                b64 = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
                return {
                    "ok": True,
                    "source": "musicbrainz",
                    "data_url": b64,
                    "artist": mb.get("artist") or a,
                    "title": mb.get("title") or t,
                    "album": mb.get("album") or al,
                    "year": mb.get("date") or "",
                }
    except Exception:
        log.debug("CoverArtArchive yedegi basarisiz", exc_info=True)

    return {"ok": False, "error": "not_found"}


def auto_tag_plan(folder: str, recursive: bool = False) -> dict[str, Any]:
    """Klasordeki sarkilarin mevcut vs dosya adindan cikarilan ID3 planini hazirlar."""
    items: list[dict[str, Any]] = []
    for path in audio_files(folder, recursive):
        cur = read_id3_summary(path)
        parsed = parse_name(os.path.basename(path))
        prop_artist = parsed["artist"] or os.path.basename(os.path.dirname(path))
        prop_title = parsed["title"] or os.path.splitext(os.path.basename(path))[0]
        needs_tag = (not cur["artist"]) or (not cur["title"])
        items.append({
            "path": path,
            "file": os.path.basename(path),
            "cur_artist": cur["artist"],
            "cur_title": cur["title"],
            "cur_album": cur["album"],
            "has_cover": cur["has_cover"],
            "artist": cur["artist"] or prop_artist,
            "title": cur["title"] or prop_title,
            "album": cur["album"],
            "needs_tag": needs_tag,
        })
    return {"ok": True, "items": items}


def auto_tag_apply(items: list[dict[str, Any]], fetch_covers: bool = False, overwrite: bool = False) -> dict[str, Any]:
    """Toplu ID3 doldurma ve istege bagli Hi-Res kapak gomme uygular."""
    done = 0
    covers = 0
    errors: list[str] = []
    cover_cache: dict[tuple[str, str], bytes | None] = {}

    for it in items or []:
        path = str(it.get("path") or "")
        if not path or not os.path.isfile(path):
            continue
        artist = str(it.get("artist") or "").strip()
        title = str(it.get("title") or "").strip()
        album = str(it.get("album") or "").strip()
        year = str(it.get("year") or "").strip()
        ok = write_id3_tags(path, artist=artist, title=title, album=album, year=year, overwrite=overwrite)
        if ok:
            done += 1
        else:
            errors.append(os.path.basename(path))

        if fetch_covers and (overwrite or not it.get("has_cover")):
            ck = (artist.lower(), (album or title).lower())
            if ck not in cover_cache:
                fetched = fetch_hires_cover(artist, title, album)
                if fetched.get("ok") and fetched.get("data_url"):
                    try:
                        cover_cache[ck] = base64.b64decode(fetched["data_url"].split(",", 1)[-1])
                    except ValueError:
                        cover_cache[ck] = None
                else:
                    cover_cache[ck] = None
            raw = cover_cache.get(ck)
            if raw and cover_embed(path, raw):
                covers += 1

    return {"ok": True, "done": done, "covers": covers, "errors": errors}



def m3u_export(folder: str, recursive: bool = False, name: str = "") -> dict[str, Any]:
    files = audio_files(folder, recursive)
    if not files:
        return {"ok": False, "error": "empty_folder"}
    folder_name = os.path.basename(os.path.normpath(folder)) or "Kami"
    lines = ["#EXTM3U"]
    lines += [os.path.relpath(path, folder).replace("\\", "/") for path in files]
    out_path = os.path.join(folder, (name or folder_name) + ".m3u")
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError as exc:
        return {"ok": False, "error": str(exc)[:120]}
    return {"ok": True, "path": out_path, "count": len(files)}
