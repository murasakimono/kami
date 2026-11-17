"""Kami Oyun: Steam / Epic / GOG yerel tarama, tekillestirme, SteamGridDB/CDN kapak ve Ludusavi save yedegi."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
from pathlib import Path
from typing import Any


def _norm_title(name: str) -> str:
    s = re.sub(r"[\u2122\u00ae\u00a9:]", " ", str(name or "").lower())
    s = re.sub(r"\b(complete|definitive|goty|game of the year|enhanced|remastered|edition|director'?s cut)\b", "", s)
    return re.sub(r"[^a-z0-9]+", "", s).strip()


def _scan_steam() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    roots = [Path("C:/Program Files (x86)/Steam"), Path("C:/Program Files/Steam")]
    try:   # Steam baska surucudeyse gercek yeri kayit defterinde
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            sp = Path(winreg.QueryValueEx(k, "SteamPath")[0])
            if sp not in roots:
                roots.insert(0, sp)
    except (OSError, ImportError):
        pass
    libs: list[Path] = []
    for r in roots:
        vdf = r / "steamapps" / "libraryfolders.vdf"
        if vdf.is_file():
            libs.append(r / "steamapps")
            try:
                txt = vdf.read_text(encoding="utf-8", errors="ignore")
                for m in re.finditer(r'"path"\s+"([^"]+)"', txt):
                    p = Path(m.group(1).replace("\\\\", "\\")) / "steamapps"
                    if p.is_dir() and p not in libs:
                        libs.append(p)
            except OSError:
                pass
    for lib in libs:
        for acf in lib.glob("appmanifest_*.acf"):
            try:
                t = acf.read_text(encoding="utf-8", errors="ignore")
                aid = re.search(r'"appid"\s+"(\d+)"', t)
                nm = re.search(r'"name"\s+"([^"]+)"', t)
                ins = re.search(r'"installdir"\s+"([^"]+)"', t)
                sz = re.search(r'"SizeOnDisk"\s+"(\d+)"', t)
                if not aid or not nm:
                    continue
                appid = aid.group(1)
                if appid == "228980":  # Steamworks Common Redistributables
                    continue
                install_path = str(lib / "common" / ins.group(1)) if ins else ""
                out.append({
                    "store": "Steam",
                    "id": appid,
                    "title": nm.group(1),
                    "path": install_path,
                    "size": int(sz.group(1)) if sz else 0,
                    "launch": f"steam://rungameid/{appid}",
                    "cover": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/library_600x900.jpg",
                })
            except OSError:
                continue
    return out


def _scan_epic() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    mdir = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "Epic/EpicGamesLauncher/Data/Manifests"
    if not mdir.is_dir():
        return out
    for it in mdir.glob("*.item"):
        try:
            d = json.loads(it.read_text(encoding="utf-8", errors="ignore"))
            nm = d.get("DisplayName") or ""
            app_name = d.get("AppName") or ""
            if not nm or not app_name:
                continue
            out.append({
                "store": "Epic",
                "id": app_name,
                "title": nm,
                "path": d.get("InstallLocation") or "",
                "size": int(d.get("InstallSize") or 0),
                "launch": f"com.epicgames.launcher://apps/{app_name}?action=launch&silent=true",
                "cover": "",
            })
        except Exception:
            continue
    return out


def _gog_exe(install: str, pid: str) -> str:
    """GOG kurulum klasoru oyun degil; goggame-<id>.info icindeki birincil playTask'in exe'si."""
    import json
    try:
        info = json.loads((Path(install) / f"goggame-{pid}.info").read_text(encoding="utf-8", errors="ignore"))
        for t in info.get("playTasks") or []:
            if t.get("isPrimary") and t.get("path"):
                return str(Path(install) / t["path"])
    except (OSError, ValueError):
        pass
    return ""


def _scan_gog() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    db = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "GOG.com/Galaxy/storage/galaxy-2.0.db"
    if not db.is_file():
        return out
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        rows = con.execute(
            "SELECT p.productId, p.installationPath, ld.title FROM InstalledBaseProducts p "
            "LEFT JOIN LimitedDetails ld ON ld.productId = p.productId"
        ).fetchall()
        con.close()
        for pid, ipath, title in rows:
            if not title:
                continue
            out.append({
                "store": "GOG",
                "id": str(pid),
                "title": str(title),
                "path": str(ipath or ""),
                "size": 0,
                "launch": _gog_exe(str(ipath or ""), str(pid)),
                "cover": "",
            })
    except Exception:
        pass
    return out


def list_games() -> dict[str, Any]:
    raw = _scan_steam() + _scan_epic() + _scan_gog()
    merged: dict[str, dict[str, Any]] = {}
    for g in raw:
        key = _norm_title(g["title"]) or g["title"].lower()
        cur = merged.get(key)
        if not cur:
            merged[key] = {
                "key": key,
                "title": g["title"],
                "stores": [{"store": g["store"], "launch": g["launch"], "path": g["path"]}],
                "size": g["size"],
                "cover": g["cover"],
                "path": g["path"],
            }
        else:
            if all(s["store"] != g["store"] for s in cur["stores"]):
                cur["stores"].append({"store": g["store"], "launch": g["launch"], "path": g["path"]})
            if not cur["cover"] and g["cover"]:
                cur["cover"] = g["cover"]
            if not cur["path"] and g["path"]:
                cur["path"] = g["path"]
    games = sorted(merged.values(), key=lambda x: x["title"].lower())
    return {"ok": True, "games": games, "count": len(games)}


def launch_game(launch_target: str) -> dict[str, Any]:
    t = str(launch_target or "").strip()
    if not t:
        return {"ok": False, "error": "empty"}
    # yalniz oyun mağazasi linkleri ya da var olan exe/kisayol (rastgele yol/komut degil)
    if not (re.match(r"^(steam|com\.epicgames\.launcher|goggalaxy)://", t, re.I)
            or (Path(t).suffix.lower() in (".exe", ".lnk", ".url") and Path(t).is_file())):
        return {"ok": False, "error": "unsupported_target"}
    try:
        os.startfile(t)
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}


def backup_save_ludusavi(title: str, out_dir: str = "") -> dict[str, Any]:
    from app import paths
    dest = Path(out_dir) if out_dir else (paths.DATA_DIR / "game_saves")
    dest.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(["ludusavi", "backup", "--force", "--path", str(dest), title],
                           capture_output=True, text=True, timeout=120,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return {"ok": r.returncode == 0, "dir": str(dest), "out": (r.stdout or r.stderr)[:400]}
    except FileNotFoundError:
        return {"ok": False, "error": "ludusavi_missing", "dir": str(dest)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}
