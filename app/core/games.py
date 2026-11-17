"""Kami Oyun: Steam / Epic / GOG yerel tarama, kesin tekillestirme, SteamGridDB/Steam Web API, oynama suresi & auto-replay."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def _norm_title(name: str) -> str:
    s = re.sub(r"[\u2122\u00ae\u00a9:]", " ", str(name or "").lower())
    s = re.sub(r"\b(complete|definitive|goty|game of the year|enhanced|remastered|edition|director'?s cut)\b", "", s)
    return re.sub(r"[^a-z0-9]+", "", s).strip()


def _exact_title(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip().lower())


def _token_store(filename: str):
    from app import paths
    from app.core.debrid import TokenStore
    return TokenStore(paths.DATA_DIR / filename)


def set_sgdb_key(key: str) -> dict[str, Any]:
    k = str(key or "").strip()
    ts = _token_store("sgdb_key.bin")
    if k:
        ts.save(k)
    else:
        ts.clear()
    return {"ok": True, "has_key": bool(k)}


def has_sgdb_key() -> bool:
    return bool(_token_store("sgdb_key.bin").load())


def set_steam_web(api_key: str, steam_id: str) -> dict[str, Any]:
    k = str(api_key or "").strip()
    sid = str(steam_id or "").strip()
    ts = _token_store("steam_web.bin")
    if k and sid:
        ts.save(json.dumps({"key": k, "steam_id": sid}))
    else:
        ts.clear()
    return {"ok": True, "configured": bool(k and sid)}


def has_steam_web() -> dict[str, Any]:
    raw = _token_store("steam_web.bin").load()
    if not raw:
        return {"configured": False, "steam_id": ""}
    try:
        d = json.loads(raw)
        return {"configured": bool(d.get("key") and d.get("steam_id")), "steam_id": d.get("steam_id", "")}
    except Exception:
        return {"configured": False, "steam_id": ""}


def _playtime_path() -> Path:
    from app import paths
    return paths.DATA_DIR / "game_playtime.json"


def _covers_cache_path() -> Path:
    from app import paths
    return paths.DATA_DIR / "game_covers_cache.json"


def _load_json(p: Path) -> dict[str, Any]:
    try:
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_json(p: Path, d: dict[str, Any]) -> None:
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _sgdb_cover(title: str, sgdb_key: str, cache: dict[str, Any]) -> str:
    ek = _exact_title(title)
    if ek in cache:
        return str(cache[ek] or "")
    if not sgdb_key or not title:
        return ""
    headers = {"Authorization": f"Bearer {sgdb_key}", "User-Agent": "Kami/1.33"}
    try:
        q = urllib.parse.quote(title)
        req = urllib.request.Request(f"https://www.steamgriddb.com/api/v2/search/autocomplete/{q}", headers=headers)
        with urllib.request.urlopen(req, timeout=5) as r:
            res = json.loads(r.read().decode("utf-8"))
        gid = ((res.get("data") or [{}])[0]).get("id")
        if not gid:
            cache[ek] = ""
            return ""
        req2 = urllib.request.Request(f"https://www.steamgriddb.com/api/v2/grids/game/{gid}?dimensions=600x900", headers=headers)
        with urllib.request.urlopen(req2, timeout=5) as r2:
            gdata = json.loads(r2.read().decode("utf-8")).get("data") or []
        url = str((gdata[0] if gdata else {}).get("url") or "")
        cache[ek] = url
        return url
    except Exception:
        return ""


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
                if appid == "228980":
                    continue
                install_path = str(lib / "common" / ins.group(1)) if ins else ""
                out.append({
                    "store": "Steam",
                    "id": appid,
                    "title": nm.group(1).strip(),
                    "path": install_path,
                    "size": int(sz.group(1)) if sz else 0,
                    "installed": True,
                    "launch": f"steam://rungameid/{appid}",
                    "cover": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/library_600x900.jpg",
                })
            except OSError:
                continue
    return out


def _scan_steam_owned() -> list[dict[str, Any]]:
    raw_cfg = _token_store("steam_web.bin").load()
    if not raw_cfg:
        return []
    try:
        cfg = json.loads(raw_cfg)
        k, sid = cfg.get("key", ""), cfg.get("steam_id", "")
        if not k or not sid:
            return []
        url = (
            "https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/"
            f"?key={urllib.parse.quote(k)}&steamid={urllib.parse.quote(sid)}"
            "&include_appinfo=1&include_played_free_games=1&format=json"
        )
        with urllib.request.urlopen(url, timeout=8) as r:
            games = (json.loads(r.read().decode("utf-8")).get("response") or {}).get("games") or []
        return [{
            "store": "Steam",
            "id": str(g["appid"]),
            "title": str(g.get("name") or f"App {g['appid']}").strip(),
            "path": "",
            "size": 0,
            "installed": False,
            "steam_mins": int(g.get("playtime_forever") or 0),
            "launch": f"steam://install/{g['appid']}",
            "cover": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{g['appid']}/library_600x900.jpg",
        } for g in games if g.get("appid") and g.get("name")]
    except Exception:
        return []


def _scan_epic() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    mdir = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "Epic/EpicGamesLauncher/Data/Manifests"
    if not mdir.is_dir():
        return out
    for it in mdir.glob("*.item"):
        try:
            d = json.loads(it.read_text(encoding="utf-8", errors="ignore"))
            nm = str(d.get("DisplayName") or "").strip()
            app_name = str(d.get("AppName") or "").strip()
            if not nm or not app_name:
                continue
            out.append({
                "store": "Epic",
                "id": app_name,
                "title": nm,
                "path": d.get("InstallLocation") or "",
                "size": int(d.get("InstallSize") or 0),
                "installed": True,
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
                "title": str(title).strip(),
                "path": str(ipath or ""),
                "size": 0,
                "installed": True,
                "launch": _gog_exe(str(ipath or ""), str(pid)),
                "cover": "",
            })
    except Exception:
        pass
    return out


def list_games(include_owned: bool = True) -> dict[str, Any]:
    raw = _scan_steam() + _scan_epic() + _scan_gog()
    if include_owned:
        raw += _scan_steam_owned()
    playtimes = _load_json(_playtime_path())
    sgdb_key = _token_store("sgdb_key.bin").load() or ""
    cov_cache = _load_json(_covers_cache_path())
    cov_dirty = False

    merged: dict[str, dict[str, Any]] = {}
    exact_to_key: dict[str, str] = {}
    steam_ids: set[str] = set()

    for g in raw:
        title_clean = re.sub(r"\s+", " ", str(g.get("title") or "").strip())
        if not title_clean:
            continue
        exact_k = _exact_title(title_clean)
        # Steam kurulu + owned ayni appid ise atla
        if g["store"] == "Steam" and not g.get("installed") and str(g.get("id")) in steam_ids:
            continue
        if g["store"] == "Steam" and g.get("installed"):
            steam_ids.add(str(g.get("id")))

        norm_k = _norm_title(title_clean) or exact_k
        key = exact_to_key.get(exact_k) or (norm_k if norm_k in merged else norm_k)
        exact_to_key[exact_k] = key

        cur = merged.get(key)
        if not cur:
            cover = g.get("cover") or ""
            if not cover and sgdb_key:
                cover = _sgdb_cover(title_clean, sgdb_key, cov_cache)
                cov_dirty = True
            pt_sec = int(playtimes.get(key, 0))
            if not pt_sec and g.get("steam_mins"):
                pt_sec = int(g["steam_mins"]) * 60
            merged[key] = {
                "key": key,
                "title": title_clean,
                "stores": [{"store": g["store"], "launch": g["launch"], "path": g["path"], "installed": bool(g.get("installed", True))}],
                "installed": bool(g.get("installed", True)),
                "size": int(g.get("size") or 0),
                "cover": cover,
                "path": g.get("path") or "",
                "playtime_sec": pt_sec,
            }
        else:
            if g.get("installed"):
                cur["installed"] = True
            if all(s["store"] != g["store"] for s in cur["stores"]):
                cur["stores"].append({"store": g["store"], "launch": g["launch"], "path": g["path"], "installed": bool(g.get("installed", True))})
            if not cur["cover"] and g.get("cover"):
                cur["cover"] = g["cover"]
            if not cur["path"] and g.get("path"):
                cur["path"] = g["path"]

    if cov_dirty:
        _save_json(_covers_cache_path(), cov_cache)

    games = sorted(merged.values(), key=lambda x: (not x["installed"], x["title"].lower()))
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


class GamePlayTracker:
    """Kurulu oyun sureclerini arka planda izleyip oynama suresini kaydeder ve istege bagli Replay Buffer baslatir."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._auto_replay = False
        self._active_key = ""
        self._active_title = ""
        self._replay_started_for = ""
        self._thread: threading.Thread | None = None

    def ensure_started(self, auto_replay: bool | None = None) -> None:
        with self._lock:
            if auto_replay is not None:
                self._auto_replay = bool(auto_replay)
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._loop, name="KamiGameTracker", daemon=True)
            self._thread.start()

    def set_auto_replay(self, enabled: bool) -> dict[str, Any]:
        self.ensure_started(auto_replay=bool(enabled))
        return {"ok": True, "auto_replay": self._auto_replay}

    def status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "auto_replay": self._auto_replay,
            "active_key": self._active_key,
            "active_title": self._active_title,
        }

    def _loop(self) -> None:
        while self._running:
            try:
                self._tick()
            except Exception:
                pass
            time.sleep(10)

    def _tick(self) -> None:
        import psutil
        # kutuphane taramasi (tum .acf / GOG db) 5 dk onbellekli; surec kontrolu her 10 sn
        if not getattr(self, "_pm", None) or time.time() - getattr(self, "_pm_t", 0) > 300:
            pm: list[tuple[str, str, str]] = []
            for g in _scan_steam() + _scan_epic() + _scan_gog():
                p = str(g.get("path") or "").strip().lower().rstrip("\\/")
                if len(p) > 4:
                    pm.append((p + os.sep, _norm_title(g["title"]) or _exact_title(g["title"]), g["title"]))
            self._pm, self._pm_t = pm, time.time()
        path_map: list[tuple[str, str, str]] = self._pm

        found_key, found_title = "", ""
        if path_map:
            for proc in psutil.process_iter(["exe"]):
                try:
                    exe = str(proc.info.get("exe") or "").lower()
                    if not exe:
                        continue
                    for pfx, k, title in path_map:
                        if exe.startswith(pfx):
                            found_key, found_title = k, title
                            break
                    if found_key:
                        break
                except Exception:
                    continue

        self._active_key = found_key
        self._active_title = found_title
        if found_key:
            pt = _load_json(_playtime_path())
            pt[found_key] = int(pt.get(found_key, 0)) + 10
            _save_json(_playtime_path(), pt)
            if self._auto_replay and self._replay_started_for != found_key:
                self._replay_started_for = found_key
                try:
                    from app.core.recorder import RECORDER
                    RECORDER.start_replay()
                except Exception:
                    pass
        else:
            self._replay_started_for = ""


TRACKER = GamePlayTracker()
