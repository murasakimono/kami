"""Dosya turune gore kategori ve alt klasor."""
from __future__ import annotations

import os
import re
from urllib.parse import unquote, urlparse

# Klasor adlari defterdeki karara gore (bolum 10): Video, Muzik, Arsiv, Program, Belge, Torrent
CATEGORY_FOLDERS = {
    "video": "Video",
    "music": "Müzik",
    "archive": "Arşiv",
    "program": "Program",
    "document": "Belge",
    "torrent": "Torrent",
    "other": "",  # Indirilenler kokune
}

_EXT = {
    "video": "mp4 mkv webm avi mov wmv flv m4v mpg mpeg ts m2ts 3gp ogv vob",
    "music": "mp3 m4a aac flac wav ogg opus wma alac aiff ape mka",
    "archive": "zip rar 7z tar gz tgz bz2 xz zst iso cab lz lzma",
    "program": "exe msi msix appx apk bat cmd ps1 jar deb rpm dmg",
    "document": "pdf doc docx xls xlsx ppt pptx odt ods odp txt rtf epub mobi csv md",
    "torrent": "torrent",
}
EXT_TO_CATEGORY = {ext: cat for cat, exts in _EXT.items() for ext in exts.split()}

_MIME_PREFIX = {"video/": "video", "audio/": "music"}

_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def extension_of(name: str) -> str:
    name = name.lower()
    # .tar.gz gibi cift uzantilarda son parca yeterli
    _, ext = os.path.splitext(name)
    return ext.lstrip(".")


def category_for(filename: str = "", url: str = "", mime: str = "") -> str:
    for candidate in (filename, filename_from_url(url)):
        ext = extension_of(candidate) if candidate else ""
        if ext in EXT_TO_CATEGORY:
            return EXT_TO_CATEGORY[ext]
    for prefix, cat in _MIME_PREFIX.items():
        if mime.startswith(prefix):
            return cat
    if mime in ("application/x-bittorrent",):
        return "torrent"
    return "other"


def filename_from_url(url: str) -> str:
    if not url:
        return ""
    try:
        path = urlparse(url).path
    except ValueError:
        return ""
    name = unquote(path.rsplit("/", 1)[-1])
    return sanitize_filename(name) if name else ""


def sanitize_filename(name: str) -> str:
    name = _BAD_CHARS.sub("_", name).strip().rstrip(".")
    if not name:
        return ""
    stem = name.split(".", 1)[0].upper()
    if stem in _RESERVED:
        name = "_" + name
    if len(name) > 200:
        base, ext = os.path.splitext(name)
        name = base[: 200 - len(ext)] + ext
    return name


def folder_for(base_dir: str, category: str, use_category_folders: bool = True) -> str:
    sub = CATEGORY_FOLDERS.get(category, "") if use_category_folders else ""
    return os.path.join(base_dir, sub) if sub else base_dir
