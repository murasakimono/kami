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
