"""Kami ayar ve veri yedegi (.kamibak = zip + manifest.json).

- kami.db sqlite3.Connection.backup API ile guvenli kopyalanir (canli DB dogrudan ziplenmez).
- DPAPI .bin gizli dosyalari yedeklenmez (baska PC/kullanicida acilmaz); geri yuklemede kullaniciya liste gosterilir.
- Geri yuklemeden once mevcut veri data/restore_backup_<tarih>/ altina kopyalanir.
- Yeni surum eski yedegi acar; eski surum yeni yedeği reddeder.
"""
from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

from app import paths
from app.core.extras import APP_VERSION, _ver

log = logging.getLogger(__name__)

SQLITE_DB_FILES: tuple[str, ...] = ("kami.db", "history.db")

JSON_DATA_FILES: tuple[str, ...] = (
    "settings.json",
    "game_covers_cache.json",
    "playnite_import.json",
    "game_playtime.json",
    "game_last_played.json",
    "game_favorites.json",
    "custom_games.json",
    "ytm_playlists.json",
    "music_folders.json",
    "playlists.json",
    "media_meta.json",
    "intro_marks.json",
)

DPAPI_KEY_LABELS: dict[str, str] = {
    "rd_token.bin": "Real-Debrid",
    "spotify_oauth.bin": "Spotify (PKCE)",
    "spotify_token.bin": "Spotify (Token)",
    "sgdb_key.bin": "SteamGridDB",
    "steam_web.bin": "Steam API",
    "tmdb_key.bin": "TMDB",
    "opensubtitles_key.bin": "OpenSubtitles",
    "genius_token.bin": "Genius",
    "freesound_key.bin": "Freesound",
    "yt_cookies.bin": "YouTube çerezleri",
    "room_worker.bin": "Kami Oda sabit link",
    "turn_key.bin": "Kami Oda TURN",
    "ntfy_topic.bin": "ntfy",
    "phone_key.bin": "Kami Telefon",
    "listenbrainz_token.bin": "ListenBrainz",
    "archive_passwords.bin": "Arşiv parolaları",
}


def _sqlite_backup(src_db: Path, dst_db: Path) -> None:
    import contextlib
    dst_db.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.closing(sqlite3.connect(str(src_db), timeout=10.0)) as src, \
            contextlib.closing(sqlite3.connect(str(dst_db), timeout=10.0)) as dst:
        src.backup(dst)


def _studio_projects_list() -> list[dict[str, Any]]:
    try:
        from app.core import studio
        proj_dir = studio.home_dir() / "Projeler"
        if not proj_dir.is_dir():
            return []
        out = []
        for p in sorted(proj_dir.glob(f"*{studio.PROJECT_EXT}"), key=lambda x: x.stat().st_mtime, reverse=True):
            st = p.stat()
            out.append({"name": p.stem, "file": p.name, "mtime": int(st.st_mtime), "size": int(st.st_size)})
        return out
    except Exception:
        return []


def create_backup(
    dest_path: Path | str | None = None,
    data_dir: Path | None = None,
    db_path: Path | None = None,
    version: str = APP_VERSION,
    local_storage: dict[str, Any] | str | None = None,
) -> dict[str, Any]:
    dd = Path(data_dir) if data_dir else paths.DATA_DIR
    ts = time.strftime("%Y%m%d_%H%M%S")
    if dest_path:
        out = Path(dest_path)
        if out.suffix.lower() != ".kamibak":
            out = out.with_suffix(".kamibak")
    else:
        bdir = dd / "backups"
        bdir.mkdir(parents=True, exist_ok=True)
        out = bdir / f"kami_backup_{ts}.kamibak"
    out.parent.mkdir(parents=True, exist_ok=True)

    included: list[str] = []
    excluded_dpapi = [label for fname, label in DPAPI_KEY_LABELS.items() if (dd / fname).is_file()]

    with tempfile.TemporaryDirectory() as tmpd:
        tmp_path = Path(tmpd)
        tmp_zip = out.with_suffix(".kamibak.tmp")
        with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for fname in JSON_DATA_FILES:
                fp = dd / fname
                if fp.is_file():
                    zf.write(fp, arcname=f"data/{fname}")
                    included.append(fname)
            for dbname in SQLITE_DB_FILES:
                dbf = Path(db_path) if (db_path and dbname == "kami.db") else (dd / dbname)
                if dbf.is_file():
                    db_snap = tmp_path / dbname
                    _sqlite_backup(dbf, db_snap)
                    zf.write(db_snap, arcname=f"data/{dbname}")
                    included.append(dbname)
            if local_storage:
                ls_str = local_storage if isinstance(local_storage, str) else json.dumps(local_storage, ensure_ascii=False)
                zf.writestr("data/localstorage_backup.json", ls_str)
                included.append("localstorage_backup.json")
            studio_list = _studio_projects_list()
            if studio_list:
                zf.writestr("data/studio_projects_list.json", json.dumps(studio_list, ensure_ascii=False, indent=2))
                included.append("studio_projects_list.json")

            manifest = {
                "format": "kamibak",
                "format_version": 1,
                "version": str(version),
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "files": included,
                "excluded_dpapi": excluded_dpapi,
            }
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        tmp_zip.replace(out)

    return {"ok": True, "path": str(out), "files": included, "count": len(included), "excluded_dpapi": excluded_dpapi}


def _backup_existing_for_restore(target_dir: Path) -> Path:
    ts = time.strftime("%Y%m%d_%H%M%S")
    snap_dir = target_dir / f"restore_backup_{ts}"
    snap_dir.mkdir(parents=True, exist_ok=True)
    for fname in JSON_DATA_FILES:
        fp = target_dir / fname
        if fp.is_file():
            shutil.copy2(fp, snap_dir / fname)
    for dbname in SQLITE_DB_FILES:
        db = target_dir / dbname
        if db.is_file():
            _sqlite_backup(db, snap_dir / dbname)
    return snap_dir


def _inspect_kamibak(src: Path, current_version: str) -> tuple[dict[str, Any] | None, str | None]:
    if not src.is_file():
        return None, "file_not_found"
    try:
        with zipfile.ZipFile(src, "r") as zf:
            if "manifest.json" not in zf.namelist():
                return None, "missing_manifest"
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
    except zipfile.BadZipFile:
        return None, "bad_zip"
    except Exception:
        return None, "bad_manifest"
    bver = str(manifest.get("version") or "0.0.0")
    if _ver(bver) > _ver(current_version):
        return manifest, "newer_version"
    return manifest, None


def stage_restore(
    src_path: Path | str,
    target_dir: Path | None = None,
    current_version: str = APP_VERSION,
) -> dict[str, Any]:
    """Canli calisan Kami'de dosyalarin ustune yazmadan once dogrular ve pending_restore.kamibak olarak siraya alir."""
    src = Path(src_path)
    td = Path(target_dir) if target_dir else paths.DATA_DIR
    td.mkdir(parents=True, exist_ok=True)
    manifest, err = _inspect_kamibak(src, current_version)
    if err:
        out: dict[str, Any] = {"ok": False, "error": err}
        if err == "newer_version" and manifest:
            out["backup_version"] = str(manifest.get("version") or "")
            out["current_version"] = current_version
        return out
    assert manifest is not None
    pending = td / "pending_restore.kamibak"
    tmp_p = td / "pending_restore.kamibak.tmp"
    shutil.copy2(src, tmp_p)
    tmp_p.replace(pending)
    reenter = list(dict.fromkeys(
        list(manifest.get("excluded_dpapi") or [])
        + [label for fname, label in DPAPI_KEY_LABELS.items() if not (td / fname).is_file()]
    ))
    return {
        "ok": True,
        "staged": True,
        "backup_version": str(manifest.get("version") or ""),
        "restored": list(manifest.get("files") or []),
        "reenter_keys": reenter,
        "restart_required": True,
    }


def apply_pending_restore(
    target_dir: Path | None = None,
    current_version: str = APP_VERSION,
) -> dict[str, Any] | None:
    """Acilista Settings ve SQLite DB acilmadan once pending_restore.kamibak varsa uygular."""
    td = Path(target_dir) if target_dir else paths.DATA_DIR
    pending = td / "pending_restore.kamibak"
    if not pending.is_file():
        return None
    res = restore_backup(pending, target_dir=td, current_version=current_version)
    try:
        pending.unlink()
    except OSError:
        pass
    return res


def restore_backup(
    src_path: Path | str,
    target_dir: Path | None = None,
    current_version: str = APP_VERSION,
) -> dict[str, Any]:
    src = Path(src_path)
    if not src.is_file():
        return {"ok": False, "error": "file_not_found"}
    td = Path(target_dir) if target_dir else paths.DATA_DIR
    td.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(src, "r") as zf:
            if "manifest.json" not in zf.namelist():
                return {"ok": False, "error": "missing_manifest"}
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            bver = str(manifest.get("version") or "0.0.0")
            if _ver(bver) > _ver(current_version):
                return {
                    "ok": False,
                    "error": "newer_version",
                    "backup_version": bver,
                    "current_version": current_version,
                }

            safety_dir = _backup_existing_for_restore(td)
            for dbname in SQLITE_DB_FILES:
                for suf in ("-wal", "-shm"):
                    wf = td / f"{dbname}{suf}"
                    if wf.is_file():
                        try:
                            wf.unlink()
                        except OSError:
                            pass
            restored: list[str] = []
            for info in zf.infolist():
                if info.is_dir() or not info.filename.startswith("data/"):
                    continue
                rel = info.filename[len("data/"):]
                if not rel or "/" in rel or "\\" in rel or ".." in rel or rel.endswith(".bin"):
                    continue
                out_name = "pending_localstorage.json" if rel == "localstorage_backup.json" else rel
                dst = (td / out_name).resolve()
                if td.resolve() not in dst.parents:
                    continue
                tmp_dst = dst.with_name(dst.name + ".restore_tmp")
                with zf.open(info, "r") as rfh, open(tmp_dst, "wb") as wfh:
                    shutil.copyfileobj(rfh, wfh)
                tmp_dst.replace(dst)
                restored.append(rel)
    except zipfile.BadZipFile:
        return {"ok": False, "error": "bad_zip"}
    except Exception as exc:
        log.exception("Yedek geri yukleme hatasi")
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:140]}"}

    reenter = list(dict.fromkeys(
        list(manifest.get("excluded_dpapi") or [])
        + [label for fname, label in DPAPI_KEY_LABELS.items() if not (td / fname).is_file()]
    ))
    return {
        "ok": True,
        "backup_version": bver,
        "restored": restored,
        "safety_backup": str(safety_dir),
        "reenter_keys": reenter,
        "restart_recommended": True,
    }


def maybe_auto_backup(
    settings_obj: Any,
    data_dir: Path | None = None,
    keep: int = 4,
    local_storage: dict[str, Any] | str | None = None,
) -> dict[str, Any] | None:
    if not settings_obj.get("auto_backup", True):
        return None
    last = int(settings_obj.get("auto_backup_last") or 0)
    now = int(time.time())
    if now - last < 7 * 86400:
        return None
    dd = Path(data_dir) if data_dir else paths.DATA_DIR
    bdir = dd / "backups"
    bdir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    res = create_backup(bdir / f"auto_{ts}.kamibak", data_dir=dd, local_storage=local_storage)
    if res.get("ok"):
        settings_obj.set("auto_backup_last", now)
        autos = sorted(bdir.glob("auto_*.kamibak"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in autos[keep:]:
            try:
                old.unlink()
            except OSError:
                pass
    return res
