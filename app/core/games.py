"""Kami Oyun: Steam / Epic / GOG yerel tarama, kesin tekillestirme, SteamGridDB/Steam Web API, oynama suresi & auto-replay."""
from __future__ import annotations

import json
import logging
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

log = logging.getLogger(__name__)


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


def _last_played_path() -> Path:
    from app import paths
    return paths.DATA_DIR / "game_last_played.json"


def _favorites_path() -> Path:
    from app import paths
    return paths.DATA_DIR / "game_favorites.json"


def _record_last_played(key: str) -> None:
    if not key:
        return
    lp = _load_json(_last_played_path())
    lp[key] = int(time.time())
    _save_json(_last_played_path(), lp)


def toggle_favorite(key: str) -> dict[str, Any]:
    k = str(key or "").strip()
    if not k:
        return {"ok": False}
    favs = _load_json(_favorites_path())
    cur = not bool(favs.get(k))
    if cur:
        favs[k] = True
    else:
        favs.pop(k, None)
    _save_json(_favorites_path(), favs)
    return {"ok": True, "favorite": cur}


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
        cache[ek] = ""   # basarisizi da hatirla: her acilista 2 x 5 sn beklemesin
        return ""


_SGDB_BG = {"busy": False}


def _sgdb_background(titles: list[str], sgdb_key: str) -> None:
    """Kapagi olmayan oyunlari arka planda SteamGridDB'den doldurur; sonraki acilista hazir olur."""
    if _SGDB_BG["busy"]:
        return
    _SGDB_BG["busy"] = True

    def run():
        try:
            cache = _load_json(_covers_cache_path())
            for i, t in enumerate(dict.fromkeys(titles)):
                if _exact_title(t) not in cache:
                    _sgdb_cover(t, sgdb_key, cache)
                if i % 20 == 19:
                    _save_json(_covers_cache_path(), cache)
            _save_json(_covers_cache_path(), cache)
        except Exception:
            pass
        finally:
            _SGDB_BG["busy"] = False
    threading.Thread(target=run, name="kami-sgdb-covers", daemon=True).start()


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
                if t.get("arguments") or (t.get("workingDir") and t["workingDir"] != str(Path(t["path"]).parent)):
                    # v2.5.3: DOSBox/ScummVM gibi argumanli gorevler exe tek basina acilinca calismaz -> Galaxy baslatsin
                    return f"goggalaxy://openGameView/{pid}"
                return str(Path(install) / t["path"])
    except (OSError, ValueError):
        pass
    return f"goggalaxy://openGameView/{pid}" if pid else ""   # birincil gorevi olmayan oyun da baslatilabilsin


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


_RIOT_TITLES = {
    "league_of_legends": "League of Legends",
    "valorant": "VALORANT",
    "bacon": "Legends of Runeterra",
    "lion": "2XKO",
}


def _scan_riot() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    rc_path = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "Riot Games/RiotClientInstalls.json"
    if not rc_path.is_file():
        return out
    try:
        rc = json.loads(rc_path.read_text(encoding="utf-8", errors="ignore"))
        rc_exe = str(rc.get("rc_live") or rc.get("rc_default") or "").strip()
        seen_p: set[str] = set()
        for gdir, _exe in (rc.get("associated_client") or {}).items():
            prod = ""
            low = str(gdir).lower()
            for k in _RIOT_TITLES:
                if k.replace("_", " ") in low or k in low:
                    prod = k
                    break
            if not prod or prod in seen_p:
                continue
            seen_p.add(prod)
            out.append({
                "store": "Riot Games",
                "id": prod,
                "title": _RIOT_TITLES[prod],
                "path": str(gdir),
                "size": 0,
                "installed": Path(str(gdir)).is_dir(),
                "launch": f"riot://{prod}",
                "cover": "",
                "genres": ["Action", "Competitive"],
            })
        meta = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "Riot Games/Metadata"
        if meta.is_dir():
            for d in meta.iterdir():
                if not d.is_dir():
                    continue
                prod = d.name.split(".")[0]
                if prod in _RIOT_TITLES and prod not in seen_p and rc_exe:
                    seen_p.add(prod)
                    out.append({
                        "store": "Riot Games",
                        "id": prod,
                        "title": _RIOT_TITLES[prod],
                        "path": "",
                        "size": 0,
                        "installed": True,
                        "launch": f"riot://{prod}",
                        "cover": "",
                        "genres": ["Action", "Competitive"],
                    })
    except Exception:
        pass
    return out


def _read_litedb_docs(db_path: Path) -> list[dict[str, Any]]:
    import struct
    import uuid
    if not db_path.is_file():
        return []
    data = db_path.read_bytes()
    docs: list[dict[str, Any]] = []

    def parse_bson(buf: bytes, pos: int) -> dict[str, Any] | None:
        end = pos + struct.unpack_from("<i", buf, pos)[0]
        if end > len(buf) or end - pos < 5 or buf[end - 1] != 0:
            return None
        p = pos + 4
        out: dict[str, Any] = {}
        while p < end - 1:
            t = buf[p]; p += 1
            z = buf.find(b"\x00", p, end)
            if z < 0:
                return None
            k = buf[p:z].decode("utf-8", "replace"); p = z + 1
            if t == 0x02:
                sl = struct.unpack_from("<i", buf, p)[0]; p += 4
                if sl < 1 or p + sl > end:
                    return None
                out[k] = buf[p:p + sl - 1].decode("utf-8", "replace"); p += sl
            elif t == 0x08:
                out[k] = bool(buf[p]); p += 1
            elif t == 0x10:
                out[k] = struct.unpack_from("<i", buf, p)[0]; p += 4
            elif t in (0x12, 0x09):
                out[k] = struct.unpack_from("<q", buf, p)[0]; p += 8
            elif t == 0x01:
                out[k] = struct.unpack_from("<d", buf, p)[0]; p += 8
            elif t == 0x05:
                bl = struct.unpack_from("<i", buf, p)[0]; st = buf[p + 4]; p += 5
                if st == 0x04 and bl == 16:
                    out[k] = str(uuid.UUID(bytes_le=buf[p:p + 16]))
                p += bl
            elif t in (0x03, 0x04):
                sub = parse_bson(buf, p)
                if sub is None:
                    return None
                out[k] = list(sub.values()) if t == 0x04 else sub
                p += struct.unpack_from("<i", buf, p)[0]
            elif t == 0x0A:
                out[k] = None
            elif t == 0x07:
                p += 12
            else:
                return None
        return out

    # LiteDB v4 (Playnite): 4 KB sayfa, 25 bayt baslik; veri sayfasi (tip 4) bloklari
    # [idx u16][extendPage u32][size u16][veri]; buyuk kayitlar
    # tip-5 "extend" sayfalarina zincirlenir. Eskiden tek sayfaya sigmayan kayitlar (uzun
    # aciklamali oyunlar: Hogwarts Legacy vb.) sessizce atlaniyordu.
    PS, NONE = 4096, 0xFFFFFFFF
    n_pages = len(data) // PS
    by_id: dict[str, dict[str, Any]] = {}
    loose: list[dict[str, Any]] = []
    for pg in range(n_pages):
        off = pg * PS
        try:
            pid, typ, _prev, _nxt, cnt, _free = struct.unpack_from("<IBIIHH", data, off)
        except struct.error:
            break
        if typ != 4 or pid != pg:
            continue
        i = off + 25
        for _ in range(cnt):
            if i + 8 > off + PS:
                break
            _idx, extp, size = struct.unpack_from("<HIH", data, i)
            i += 8
            if i + size > off + PS:
                break
            buf = bytearray(data[i:i + size])
            i += size
            q, hops = extp, 0
            while q != NONE and q < n_pages and hops < 2000:
                qo = q * PS
                _qid, qt, _qp, qn, qc, _qf = struct.unpack_from("<IBIIHH", data, qo)
                if qt != 5:
                    break
                buf += data[qo + 25:qo + 25 + min(qc, PS - 25)]
                q, hops = qn, hops + 1
            if len(buf) < 5:
                continue
            try:
                d = parse_bson(bytes(buf), 0)
            except Exception:
                d = None
            if not d or not ("Name" in d or "_id" in d):
                continue
            if "_id" in d:
                by_id[str(d["_id"])] = d
            else:
                loose.append(d)
    docs = list(by_id.values()) + loose
    return docs


def _playnite_cache_path() -> Path:
    from app import paths
    return paths.DATA_DIR / "playnite_import.json"


def _custom_games_path() -> Path:
    from app import paths
    return paths.DATA_DIR / "custom_games.json"


_PN_CACHE_V = 3


def import_playnite_library(lib_dir: str = "") -> dict[str, Any]:
    """Playnite LiteDB veritabanindan tum Epic/GOG/Steam/Riot oyunlarini ve turlerini kalici olarak ice aktarir."""
    base = Path(lib_dir) if lib_dir else (Path(os.environ.get("APPDATA", "")) / "Playnite/library")
    gdb = base / "games.db"
    if not gdb.is_file():
        return {"ok": False, "error": "playnite_db_not_found"}
    sources = {d["_id"]: d["Name"] for d in _read_litedb_docs(base / "sources.db") if "_id" in d and "Name" in d}
    genres = {d["_id"]: d["Name"] for d in _read_litedb_docs(base / "genres.db") if "_id" in d and "Name" in d}
    cats = {d["_id"]: d["Name"] for d in _read_litedb_docs(base / "categories.db") if "_id" in d and "Name" in d}
    raw_games = [d for d in _read_litedb_docs(gdb) if "Name" in d and "GameId" in d]
    items: list[dict[str, Any]] = []
    for g in raw_games:
        if g.get("Hidden"):   # Playnite'ta kullanicinin gizledigi kayitlar (cekilis, editor araci vb.)
            continue
        store = str(sources.get(g.get("SourceId"), "") or "Diğer")
        if store == "Steam Family Sharing":
            store = "Steam"
        gid = str(g.get("GameId") or "")
        inst = bool(g.get("IsInstalled"))
        cover = ""
        ci = str(g.get("CoverImage") or "")
        if ci and not ci.lower().startswith("http"):
            cf = base / "files" / ci.replace("\\", "/")
            if cf.is_file():
                cover = cf.as_uri()   # Playnite'in diskteki kapagi: aninda, ag yok
        elif ci.lower().startswith("http"):
            cover = ci
        if not cover and store == "Steam" and gid.isdigit():
            cover = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{gid}/library_600x900.jpg"
        launch = ""
        if store == "Steam" and gid.isdigit():
            launch = f"steam://rungameid/{gid}" if inst else f"steam://install/{gid}"
        elif store == "Epic" and gid:
            launch = f"com.epicgames.launcher://apps/{gid}?action=launch&silent=true"
        elif store == "GOG" and gid:
            launch = f"goggalaxy://openGameView/{gid}"
        elif store == "Riot Games" and gid:
            prod = gid.split(".")[0].lower()
            if prod in _RIOT_TITLES:
                launch = f"riot://{prod}"
        items.append({
            "store": store,
            "id": gid,
            "title": str(g.get("Name") or "").strip(),
            "path": str(g.get("InstallDirectory") or ""),
            "size": int(g.get("InstallSize") or 0),
            "installed": inst,
            "playtime_sec": int(g.get("Playtime") or 0),
            "favorite": bool(g.get("Favorite")),
            "genres": [genres[x] for x in (g.get("GenreIds") or []) if x in genres],
            "categories": [cats[x] for x in (g.get("CategoryIds") or []) if x in cats],
            "launch": launch,
            "cover": cover,
        })
    _save_json(_playnite_cache_path(), {"items": items, "count": len(items), "v": _PN_CACHE_V})
    return {"ok": True, "count": len(items)}


def add_custom_game(title: str, exe_path: str, store: str = "Özel") -> dict[str, Any]:
    t = str(title or "").strip()
    ex = str(exe_path or "").strip().strip('"')
    if not t or not ex or not Path(ex).is_file():
        return {"ok": False, "error": "Gecerli ad ve .exe/.lnk yolu gerekli"}
    p = _custom_games_path()
    cur = (_load_json(p).get("items") or [])
    cur.append({
        "store": store,
        "id": ex,
        "title": t,
        "path": str(Path(ex).parent),
        "size": 0,
        "installed": True,
        "launch": ex,
        "cover": "",
        "genres": ["Özel"],
    })
    _save_json(p, {"items": cur})
    return {"ok": True, "count": len(cur)}


_NOT_GAME = re.compile(r"\b(test server|experimental server|public test|dedicated server|sdk|redistributables?|benchmark)\b|\(test\)$", re.I)
# arka planda surekli acik duran uygulamalar oynama suresi saymasin
_TRACK_IGNORE = re.compile(r"^(wallpaper engine|steamvr|soundpad|blender|obs studio|aseprite|fpsvr|lossless scaling)\b", re.I)
_TOOL_PATTERNS = re.compile(
    r"^(wallpaper engine|steamvr|soundpad|blender|obs studio|aseprite|fpsvr|lossless scaling|sharex|vtube studio|ovr toolkit|borderless gaming|displayfusion|3dmark|pcmark|krita|substance|godot engine)\b",
    re.I,
)


def list_games(include_owned: bool = True) -> dict[str, Any]:
    raw = _scan_steam() + _scan_epic() + _scan_gog() + _scan_riot()
    raw += (_load_json(_custom_games_path()).get("items") or [])
    pl_cache = _playnite_cache_path()
    pn_db = Path(os.environ.get("APPDATA", "")) / "Playnite/library/games.db"
    if pn_db.is_file():
        # onbellek yoksa, eski okuyucuyla (v<2, buyuk kayitlari atliyordu) yapildiysa
        # ya da Playnite veritabani sonradan degistiyse yeniden ice aktar
        try:
            stale = (not pl_cache.is_file() or _load_json(pl_cache).get("v") != _PN_CACHE_V
                     or pn_db.stat().st_mtime > pl_cache.stat().st_mtime)
        except OSError:
            stale = True
        if stale:
            try:
                import_playnite_library()
            except Exception:
                pass
    pl_items = (_load_json(pl_cache).get("items") or [])
    if include_owned:
        raw += _scan_steam_owned()
        raw += pl_items
    else:
        raw += [x for x in pl_items if x.get("installed")]
    playtimes = _load_json(_playtime_path())
    last_played = _load_json(_last_played_path())
    favs = _load_json(_favorites_path())
    sgdb_key = _token_store("sgdb_key.bin").load() or ""
    cov_cache = _load_json(_covers_cache_path())
    cov_custom = _load_json(Path(os.path.dirname(_covers_cache_path())) / "game_covers_custom.json")
    cov_dirty = False
    sgdb_deadline = time.monotonic() + 2.0
    sgdb_later: list[str] = []

    merged: dict[str, dict[str, Any]] = {}
    exact_to_key: dict[str, str] = {}
    steam_ids: set[str] = set()

    # v2.5.3: kurulu Steam oyununun sahiplik kaydi atlandigi icin Steam'in toplam oynama suresi kayboluyordu
    steam_owned_mins = {str(x.get("id")): int(x.get("steam_mins") or 0) for x in raw
                        if x.get("store") == "Steam" and not x.get("installed") and x.get("steam_mins")}
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
                ek_c = _exact_title(title_clean)
                if ek_c in cov_cache:
                    cover = str(cov_cache[ek_c] or "")
                elif time.monotonic() < sgdb_deadline:
                    cover = _sgdb_cover(title_clean, sgdb_key, cov_cache)
                    cov_dirty = True
                else:
                    sgdb_later.append(title_clean)   # v1.35.4: kalanlar arka planda; liste beklemez
            # en buyuk deger: Kami'nin olctugu birkac saniye Steam'in yillik toplamini ezmesin
            st_min = int(g.get("steam_mins") or steam_owned_mins.get(str(g.get("id")), 0) if g.get("store") == "Steam" else g.get("steam_mins") or 0)
            pt_sec = max(int(playtimes.get(key, 0)), st_min * 60, int(g.get("playtime_sec") or 0))
            merged[key] = {
                "key": key,
                "title": title_clean,
                "stores": [{"store": g["store"], "launch": g.get("launch", ""), "path": g.get("path", ""), "installed": bool(g.get("installed", True))}],
                "installed": bool(g.get("installed", True)),
                "size": int(g.get("size") or 0),
                "cover": str(cov_custom.get(key) or cover),
                "path": g.get("path") or "",
                "playtime_sec": pt_sec,
                "last_played": int(last_played.get(key, 0)),
                "genres": list(dict.fromkeys(g.get("genres") or [])),
                "categories": list(dict.fromkeys(g.get("categories") or [])),
                "favorite": bool(favs[key]) if key in favs else bool(g.get("favorite")),
                "is_tool": bool(_TOOL_PATTERNS.search(title_clean)),
            }
        else:
            if g.get("installed"):
                cur["installed"] = True
            if all(s["store"] != g["store"] for s in cur["stores"]):
                cur["stores"].append({"store": g["store"], "launch": g.get("launch", ""), "path": g.get("path", ""), "installed": bool(g.get("installed", True))})
            elif g.get("installed"):
                for s in cur["stores"]:
                    if s["store"] == g["store"] and not s.get("installed") and g.get("launch"):
                        s.update(launch=g["launch"], path=g.get("path", ""), installed=True)
            if not cur["cover"] and g.get("cover"):
                cur["cover"] = g["cover"]
            if not cur["path"] and g.get("path"):
                cur["path"] = g["path"]
            if g.get("favorite"):
                cur["favorite"] = True
            for gn in (g.get("genres") or []):
                if gn not in cur["genres"]:
                    cur["genres"].append(gn)
            for ct in (g.get("categories") or []):
                if ct not in cur["categories"]:
                    cur["categories"].append(ct)
            cur["playtime_sec"] = max(cur["playtime_sec"], int(g.get("playtime_sec") or 0))

    if cov_dirty:
        _save_json(_covers_cache_path(), cov_cache)
    if sgdb_later and sgdb_key:
        _sgdb_background(sgdb_later, sgdb_key)

    # v1.35.1: test sunuculari / SDK / dedicated server oyun degil
    games = sorted((g for g in merged.values() if not _NOT_GAME.search(g["title"])),
                   key=lambda x: (not x["installed"], x["title"].lower()))
    return {"ok": True, "games": games, "count": len(games)}


def launch_game(launch_target: str, key: str = "") -> dict[str, Any]:
    t = str(launch_target or "").strip()
    if not t:
        return {"ok": False, "error": "empty"}
    if t.startswith("riot://"):
        prod = t[7:].strip().lower()
        if prod not in _RIOT_TITLES:
            return {"ok": False, "error": "unsupported_riot"}
        rc_path = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "Riot Games/RiotClientInstalls.json"
        try:
            rc = json.loads(rc_path.read_text(encoding="utf-8", errors="ignore"))
            rc_exe = str(rc.get("rc_live") or rc.get("rc_default") or "").strip()
            if rc_exe and Path(rc_exe).is_file():
                subprocess.Popen([rc_exe, f"--launch-product={prod}", "--launch-patchline=live"])
                _record_last_played(key)
                return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:120]}
        return {"ok": False, "error": "riot_client_missing"}
    # yalniz oyun mağazasi linkleri ya da var olan exe/kisayol (rastgele yol/komut degil)
    if not (re.match(r"^(steam|com\.epicgames\.launcher|goggalaxy)://", t, re.I)
            or (Path(t).suffix.lower() in (".exe", ".lnk", ".url") and Path(t).is_file())):
        return {"ok": False, "error": "unsupported_target"}
    try:
        if Path(t).suffix.lower() == ".exe":   # v2.5.3: calisma klasoru oyunun klasoru olsun (cogu oyun dosyalarini bulamiyordu)
            try:
                os.startfile(t, cwd=str(Path(t).parent))
            except TypeError:
                os.startfile(t)
        else:
            os.startfile(t)
        _record_last_played(key)
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


def sgdb_search_covers(query: str, sgdb_key: str = "") -> dict[str, Any]:
    """SteamGridDB (anahtar varsa) + Steam Store aramasi ile kapak secenekleri dondurur."""
    q = str(query or "").strip()
    if not q:
        return {"ok": False, "items": []}
    key = sgdb_key or (_token_store("sgdb_key.bin").load() or "")
    out: list[dict[str, Any]] = []
    if key:
        headers = {"Authorization": f"Bearer {key}", "User-Agent": "Kami/1.38"}
        try:
            req = urllib.request.Request(f"https://www.steamgriddb.com/api/v2/search/autocomplete/{urllib.parse.quote(q)}", headers=headers)
            with urllib.request.urlopen(req, timeout=5) as r:
                hits = (json.loads(r.read().decode("utf-8")).get("data") or [])[:2]
            for h in hits:
                gid = h.get("id")
                if not gid:
                    continue
                req2 = urllib.request.Request(f"https://www.steamgriddb.com/api/v2/grids/game/{gid}?dimensions=600x900", headers=headers)
                with urllib.request.urlopen(req2, timeout=5) as r2:
                    for g in (json.loads(r2.read().decode("utf-8")).get("data") or [])[:8]:
                        if g.get("url"):
                            out.append({"url": g["url"], "thumb": g.get("thumb") or g["url"], "source": "SteamGridDB", "title": h.get("name", q)})
        except Exception:
            pass
    try:
        req3 = urllib.request.Request(
            f"https://store.steampowered.com/api/storesearch/?term={urllib.parse.quote(q)}&l=english&cc=US",
            headers={"User-Agent": "Kami/1.38"},
        )
        with urllib.request.urlopen(req3, timeout=5) as r3:
            for item in (json.loads(r3.read().decode("utf-8")).get("items") or [])[:8]:
                aid = item.get("id")
                if not aid:
                    continue
                out.append({
                    "url": f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{aid}/library_600x900.jpg",
                    "thumb": item.get("tiny_image") or f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{aid}/header.jpg",
                    "source": "Steam Store",
                    "title": item.get("name", q),
                })
    except Exception:
        pass
    seen: set[str] = set()
    uniq = []
    for x in out:
        if x["url"] not in seen:
            seen.add(x["url"])
            uniq.append(x)
    return {"ok": True, "items": uniq[:16]}


def set_custom_cover(key: str, cover_url: str) -> dict[str, Any]:
    k = str(key or "").strip()
    u = str(cover_url or "").strip()
    if not k or not u:
        return {"ok": False, "error": "empty"}
    p = Path(os.path.dirname(_covers_cache_path())) / "game_covers_custom.json"
    cur = _load_json(p)
    cur[k] = u
    _save_json(p, cur)
    return {"ok": True, "key": k, "cover": u}


def _snap_dir(key: str) -> Path:
    from app import paths
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(key or "game")).strip("_") or "game"
    return paths.DATA_DIR / "save_backups" / slug


def create_save_snapshot(key: str, title: str = "", src_dir: str = "") -> dict[str, Any]:
    """Zaman damgali save snapshot'i olusturur (verilen klasor veya Ludusavi)."""
    import shutil
    root = _snap_dir(key)
    snap_id = time.strftime("%Y%m%d_%H%M%S")
    dest = root / snap_id
    dest.mkdir(parents=True, exist_ok=True)
    src = Path(src_dir) if src_dir else None
    copied = 0
    total_sz = 0
    if src and src.is_dir():
        files_dest = dest / "files"
        shutil.copytree(src, files_dest, dirs_exist_ok=True)
        for fp in files_dest.rglob("*"):
            if fp.is_file():
                copied += 1
                total_sz += fp.stat().st_size
        meta = {"id": snap_id, "key": key, "title": title, "src_dir": str(src), "ts": int(time.time()), "files": copied, "size": total_sz, "method": "folder"}
        _save_json(dest / "meta.json", meta)
        return {"ok": True, **meta}
    lud = backup_save_ludusavi(title or key, str(dest / "ludusavi"))
    for fp in dest.rglob("*"):
        if fp.is_file():
            copied += 1
            total_sz += fp.stat().st_size
    meta = {"id": snap_id, "key": key, "title": title, "src_dir": "", "ts": int(time.time()), "files": copied, "size": total_sz, "method": "ludusavi", "ludusavi_ok": bool(lud.get("ok")), "error": lud.get("error", "")}
    _save_json(dest / "meta.json", meta)
    return {"ok": bool(lud.get("ok")), **meta}


def list_save_snapshots(key: str) -> list[dict[str, Any]]:
    root = _snap_dir(key)
    if not root.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for d in sorted(root.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        meta = _load_json(d / "meta.json")
        out.append({
            "id": d.name,
            "ts": int(meta.get("ts") or d.stat().st_mtime),
            "files": int(meta.get("files") or 0),
            "size": int(meta.get("size") or 0),
            "src_dir": meta.get("src_dir", ""),
            "method": meta.get("method", "folder"),
        })
    return out


def restore_save_snapshot(key: str, snap_id: str, dest_dir: str = "") -> dict[str, Any]:
    """Secili save snapshot'ini geri yuklemeden once mevcut durumu otomatik yedekler."""
    import shutil
    snap_dir = _snap_dir(key) / os.path.basename(str(snap_id or ""))
    if not snap_dir.is_dir():
        return {"ok": False, "error": "snapshot_not_found"}
    meta = _load_json(snap_dir / "meta.json")
    if meta.get("method") == "ludusavi" and (snap_dir / "ludusavi").is_dir() and not dest_dir:
        # v2.5.3: ludusavi ile alinan yedek ludusavi ile geri yuklenir (eskiden yalniz files/ okunup "hedef yok" donuyordu)
        try:
            r = subprocess.run(["ludusavi", "restore", "--force", "--path", str(snap_dir / "ludusavi"), str(meta.get("title") or key)],
                               capture_output=True, text=True, timeout=180,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return {"ok": r.returncode == 0, "restored": snap_id, "target": "ludusavi",
                    "error": "" if r.returncode == 0 else (r.stderr or r.stdout or "ludusavi_failed")[-200:]}
        except FileNotFoundError:
            return {"ok": False, "error": "ludusavi_missing"}
    target = Path(dest_dir or meta.get("src_dir") or "")
    files_src = snap_dir / "files"
    if not target or not files_src.is_dir():
        return {"ok": False, "error": "missing_target_dir"}
    pre_snap = ""
    if target.is_dir():
        pre_dir = _snap_dir(key) / f"pre_restore_{time.strftime('%Y%m%d_%H%M%S')}"
        pre_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(target, pre_dir / "files", dirs_exist_ok=True)
        _save_json(pre_dir / "meta.json", {"id": pre_dir.name, "key": key, "src_dir": str(target), "ts": int(time.time()), "method": "pre_restore"})
        pre_snap = pre_dir.name
    shutil.copytree(files_src, target, dirs_exist_ok=True)
    return {"ok": True, "restored": snap_id, "target": str(target), "pre_backup": pre_snap}


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
        self.on_active_change: Any = None

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
        # kutuphane taramasi (tum .acf / GOG / Riot / Ozel) 5 dk onbellekli; surec kontrolu her 10 sn
        if not getattr(self, "_pm", None) or time.time() - getattr(self, "_pm_t", 0) > 300:
            pm: list[tuple[str, str, str]] = []
            custom = _load_json(_custom_games_path()).get("items") or []
            for g in _scan_steam() + _scan_epic() + _scan_gog() + _scan_riot() + custom:
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
                        if _TRACK_IGNORE.match(title):
                            continue
                        if exe.startswith(pfx):
                            found_key, found_title = k, title
                            break
                    if found_key:
                        break
                except Exception:
                    continue

        prev_key = self._active_key
        self._active_key = found_key
        self._active_title = found_title
        if found_key != prev_key and callable(self.on_active_change):
            try:
                self.on_active_change(found_key, found_title)
            except Exception:
                pass
        if found_key:
            pt = _load_json(_playtime_path())
            pt[found_key] = int(pt.get(found_key, 0)) + 10
            _save_json(_playtime_path(), pt)
            _record_last_played(found_key)
            if self._auto_replay and self._replay_started_for != found_key:
                self._replay_started_for = found_key
                # Recorder ornegini main.py olusturur (api.recorder); burada modul kaydindan alinir.
                # Eskiden `from recorder import RECORDER` vardi - o isim hic tanimli degildi ve
                # `except: pass` hatayi yutuyordu; ozellik sessizce hic calismiyordu.
                try:
                    from app.core import recorder as _rec
                    rec = _rec.active()
                    if rec is None:
                        log.debug("otomatik replay: Recorder ornegi baglanmamis (main.py set_active)")
                    else:
                        rec.start_replay()
                except Exception:
                    log.exception("otomatik replay baslatilamadi: %s", found_key)
        else:
            self._replay_started_for = ""


TRACKER = GamePlayTracker()


# ---------- Kami 2.0: Magazasiz Oyun Klasoru Tarayicisi (Shelf) & HLTB Tahmini ----------
_SKIP_EXE_WORDS = {
    "unins", "uninst", "crash", "report", "redist", "vcredist", "dxsetup", "setup", "install",
    "unitycrash", "cefsharp", "updater", "patcher", "benchmark", "config", "launcher_helper",
}


def scan_folder_for_games(folder: str, auto_add: bool = True) -> dict[str, Any]:
    """Shelf tarzi magazasiz oyun klasoru tarayicisi: C:\\Games veya secilen klasorun 1-2 seviye altindaki
    oyun klasorlerini ve ana .exe dosyalarini otomatik bulup Ozel Oyun listesine ekler."""
    root = Path(str(folder or "").strip().strip('"'))
    if not root.is_dir():
        return {"ok": False, "error": "Klasör bulunamadı", "found": []}
    found: list[dict[str, Any]] = []
    try:
        subdirs = [Path(e.path) for e in os.scandir(root) if e.is_dir(follow_symlinks=False) and not e.name.startswith(".")]
    except OSError:
        subdirs = []
    for d in subdirs[:120]:
        exes: list[tuple[int, Path]] = []
        try:
            for p in d.glob("*.exe"):
                low = p.stem.lower()
                if not any(w in low for w in _SKIP_EXE_WORDS):
                    exes.append((int(p.stat().st_size), p))
            for sub in d.iterdir():
                if sub.is_dir() and sub.name.lower() in ("bin", "binaries", "win64", "x64", "game"):
                    for p in sub.rglob("*.exe"):
                        low = p.stem.lower()
                        if not any(w in low for w in _SKIP_EXE_WORDS):
                            exes.append((int(p.stat().st_size), p))
        except OSError:
            continue
        if not exes:
            continue
        exes.sort(key=lambda x: x[0], reverse=True)
        best_exe = exes[0][1]
        title = re.sub(r"[._-]+", " ", d.name).strip()
        found.append({"title": title, "exe": str(best_exe), "dir": str(d), "size": exes[0][0]})
        if auto_add:
            try:
                add_custom_game(title, str(best_exe))
            except Exception:
                pass
    return {"ok": True, "root": str(root), "found": found, "count": len(found)}


def estimate_hltb(title: str) -> dict[str, Any]:
    """HLTB sure tahmini — gercek HLTB API'si yok; uydurma sure URETMEZ, yalnizca arama baglantisi doner."""
    t = str(title or "").strip()
    if not t:
        return {"ok": False}
    return {
        "ok": True,
        "title": t,
        "main_hours": None,
        "completionist_hours": None,
        "url": f"https://howlongtobeat.com/?q={urllib.parse.quote(t)}",
    }

