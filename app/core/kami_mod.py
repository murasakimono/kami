"""Kami Mod: 1-tik oyun modu & Turkce yama kurucu (otomatik yedekleme + rollback)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any
import zipfile

from app import paths


def _backups_root() -> Path:
    d = paths.DATA_DIR / "mod_backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_extract_zip(archive: Path, tmp_dir: Path) -> list[Path]:
    extracted: list[Path] = []
    base = tmp_dir.resolve()
    with zipfile.ZipFile(archive, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            target = (base / info.filename).resolve()
            if not str(target).startswith(str(base) + os.sep) and target != base:
                raise ValueError(f"Güvensiz arşiv yolu: {info.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted.append(target)
    return extracted


def _strip_single_root(tmp_dir: Path) -> Path:
    entries = list(tmp_dir.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return tmp_dir


def find_steam_games() -> list[dict[str, str]]:
    """Steam libraryfolders.vdf okuyarak kurulu oyun klasorlerini listeler."""
    import re
    roots: list[Path] = []
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
                sp, _ = winreg.QueryValueEx(k, "SteamPath")
                if sp:
                    roots.append(Path(sp))
        except Exception:
            pass
    for cand in (Path(r"C:\Program Files (x86)\Steam"), Path(r"D:\SteamLibrary"), Path(r"E:\SteamLibrary")):
        if cand.is_dir() and cand not in roots:
            roots.append(cand)
    libs: list[Path] = []
    for rt in roots:
        vdf = rt / "steamapps" / "libraryfolders.vdf"
        if vdf.is_file():
            try:
                txt = vdf.read_text(encoding="utf-8", errors="ignore")
                for m in re.finditer(r'"path"\s+"([^"]+)"', txt):
                    p = Path(m.group(1).replace("\\\\", "\\")) / "steamapps"
                    if p.is_dir() and p not in libs:
                        libs.append(p)
            except Exception:
                pass
        sa = rt / "steamapps"
        if sa.is_dir() and sa not in libs:
            libs.append(sa)
    games: list[dict[str, str]] = []
    seen: set[str] = set()
    for sa in libs:
        for acf in sa.glob("appmanifest_*.acf"):
            try:
                txt = acf.read_text(encoding="utf-8", errors="ignore")
                nm = re.search(r'"name"\s+"([^"]+)"', txt)
                id_m = re.search(r'"installdir"\s+"([^"]+)"', txt)
                if nm and id_m:
                    gdir = sa / "common" / id_m.group(1)
                    if gdir.is_dir():
                        gstr = str(gdir.resolve())
                        if gstr not in seen:
                            seen.add(gstr)
                            games.append({"name": nm.group(1), "dir": gstr})
            except Exception:
                continue
    return sorted(games, key=lambda x: x["name"].lower())


def list_mods() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    root = _backups_root()
    for mf in sorted(root.glob("*/manifest.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
            out.append(data)
        except Exception:
            continue
    return out


def _running_game_exe(gdir: Path) -> str:
    if os.name != "nt":
        return ""
    exes = {p.name.lower() for p in gdir.glob("*.exe")}
    if not exes:
        return ""
    try:
        import subprocess
        nowin = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        r = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=5, creationflags=nowin)
        for ln in (r.stdout or "").splitlines():
            name = ln.split(",", 1)[0].strip('" ').lower()
            if name in exes:
                return name
    except Exception:
        pass
    return ""


def install_mod(archive_path: str, game_dir: str) -> dict[str, Any]:
    arch = Path(archive_path)
    gdir = Path(game_dir)
    if not arch.is_file():
        return {"ok": False, "error": "Mod arşivi bulunamadı"}
    if not gdir.is_dir():
        return {"ok": False, "error": "Oyun klasörü bulunamadı"}
    if arch.suffix.lower() != ".zip":
        return {"ok": False, "error": "Şu an yalnızca .zip mod arşivleri destekleniyor"}
    running = _running_game_exe(gdir)
    if running:
        return {"ok": False, "error": f"Önce oyunu kapat ({running})"}

    mod_id = f"{arch.stem}_{int(time.time())}"
    bdir = _backups_root() / mod_id
    bfiles = bdir / "files"
    bfiles.mkdir(parents=True, exist_ok=True)

    tmp = Path(tempfile.mkdtemp(prefix="kami_mod_"))
    backed_up: list[str] = []
    added: list[str] = []
    try:
        _safe_extract_zip(arch, tmp)
        src_root = _strip_single_root(tmp)

        for src_file in src_root.rglob("*"):
            if not src_file.is_file():
                continue
            rel = src_file.relative_to(src_root)
            dst_file = gdir / rel
            if dst_file.exists():
                bak = bfiles / rel
                bak.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dst_file, bak)
                backed_up.append(rel.as_posix())
            else:
                added.append(rel.as_posix())
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            if dst_file.exists():
                dst_file.unlink()
            try:
                os.link(src_file, dst_file)
            except OSError:
                shutil.copy2(src_file, dst_file)

        manifest = {
            "id": mod_id,
            "name": arch.stem,
            "game_dir": str(gdir.resolve()),
            "installed_at": time.time(),
            "backed_up": backed_up,
            "added": added,
        }
        (bdir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, **manifest}
    except Exception as exc:
        for rel in backed_up:
            bak = bfiles / rel
            dst = gdir / rel
            if bak.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(bak, dst)
        for rel in added:
            dst = gdir / rel
            if dst.is_file():
                dst.unlink(missing_ok=True)
        shutil.rmtree(bdir, ignore_errors=True)
        return {"ok": False, "error": str(exc)[:200]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def rollback_mod(mod_id: str) -> dict[str, Any]:
    bdir = _backups_root() / mod_id
    mf = bdir / "manifest.json"
    if not mf.is_file():
        return {"ok": False, "error": "Mod yedek kaydı bulunamadı"}
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    gdir = Path(manifest["game_dir"])
    bfiles = bdir / "files"

    my_files = set(manifest.get("backed_up") or []) | set(manifest.get("added") or [])
    my_ts = float(manifest.get("installed_at") or 0)
    for other in list_mods():
        if other.get("id") == mod_id:
            continue
        if other.get("game_dir") == manifest.get("game_dir") and float(other.get("installed_at") or 0) > my_ts:
            other_files = set(other.get("backed_up") or []) | set(other.get("added") or [])
            if my_files & other_files:
                return {"ok": False, "error": f"Çakışan daha yeni mod var ({other.get('name')}); önce onu geri al"}

    restored = 0
    for rel in manifest.get("backed_up") or []:
        bak = bfiles / rel
        dst = gdir / rel
        if bak.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bak, dst)
            restored += 1

    removed = 0
    for rel in manifest.get("added") or []:
        dst = gdir / rel
        if dst.is_file():
            dst.unlink()
            removed += 1

    shutil.rmtree(bdir, ignore_errors=True)
    return {"ok": True, "id": mod_id, "restored": restored, "removed": removed}
