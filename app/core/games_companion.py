"""Kami Games Companion: HLTB, PCGamingWiki, Save Editoru, Time-Machine (F9), Config/.ini Duzeltici, Kami Mod Rollback ve Bolge Kilitli Oyun Ici OCR."""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
import urllib.parse
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from app import paths

log = logging.getLogger(__name__)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_OCR_LAST: dict[str, str] = {"raw": "", "tr": ""}


def _timemachine_dir() -> Path:
    d = paths.DATA_DIR / "save_timemachine"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _mod_backups_dir() -> Path:
    d = paths.DATA_DIR / "mod_backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


_HLTB_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
    "Referer": "https://howlongtobeat.com/",
    "Origin": "https://howlongtobeat.com",
}
_HLTB_TOKEN: dict[str, Any] = {"tok": "", "t": 0.0}


def _hltb_token(sess: Any, force: bool = False) -> str:
    """v2.5.3: HLTB 2026 akisi - once /api/search/site/init ile kisa omurlu token, sonra x-auth-token basligiyla arama."""
    import time as _t
    if not force and _HLTB_TOKEN["tok"] and _t.time() - _HLTB_TOKEN["t"] < 600:
        return _HLTB_TOKEN["tok"]
    r = sess.get(f"https://howlongtobeat.com/api/search/site/init?t={int(_t.time() * 1000)}", headers=_HLTB_UA, timeout=8)
    r.raise_for_status()
    _HLTB_TOKEN.update(tok=str((r.json() or {}).get("token") or ""), t=_t.time())
    return _HLTB_TOKEN["tok"]


def fetch_hltb_real(title: str) -> dict[str, Any]:
    """HowLongToBeat arama API'sinden ana hikaye / ekstra / %100 surelerini ceker; bulunamazsa found=False + arama linki."""
    import requests
    t = str(title or "").strip()
    if not t:
        return {"ok": False, "error": "empty_title"}
    search_url = f"https://howlongtobeat.com/?q={urllib.parse.quote(t)}"
    body = {
        "searchType": "games", "searchTerms": t.split(), "searchPage": 1, "size": 8,
        "searchOptions": {"games": {"userId": 0, "platform": "", "sortCategory": "popular", "rangeCategory": "main",
                                    "rangeTime": {"min": None, "max": None},
                                    "gameplay": {"perspective": "", "flow": "", "genre": "", "difficulty": ""},
                                    "rangeYear": {"min": "", "max": ""}, "modifier": ""},
                          "users": {"sortCategory": "postcount"}, "lists": {"sortCategory": "follows"},
                          "filter": "", "sort": 0, "randomizer": 0},
        "useCache": True,
    }
    err = ""
    try:
        sess = requests.Session()
        for attempt in (0, 1):
            tok = _hltb_token(sess, force=bool(attempt))
            r = sess.post("https://howlongtobeat.com/api/search/site", json=body, timeout=8,
                          headers={**_HLTB_UA, "x-auth-token": tok})
            if r.status_code == 403 and not attempt:
                continue   # token suresi dolmus
            r.raise_for_status()
            data = (r.json() or {}).get("data") or []
            if data:
                norm = re.sub(r"[^a-z0-9]+", "", t.lower())
                hit = next((g for g in data if re.sub(r"[^a-z0-9]+", "", str(g.get("game_name") or "").lower()) == norm), data[0])

                def _h(v: Any) -> float | None:
                    return round(float(v or 0) / 3600.0, 1) or None
                return {
                    "ok": True, "found": True, "source": "hltb",
                    "title": hit.get("game_name") or t,
                    "main_hours": _h(hit.get("comp_main")),
                    "plus_hours": _h(hit.get("comp_plus")),
                    "completionist_hours": _h(hit.get("comp_100")),
                    "url": f"https://howlongtobeat.com/game/{hit.get('game_id')}" if hit.get("game_id") else search_url,
                }
            break
    except Exception as exc:
        err = str(exc)[:120]
        log.warning("HLTB sorgusu basarisiz: %s", err)
    return {"ok": True, "found": False, "source": "fallback_link", "error": err, "title": t,
            "main_hours": None, "plus_hours": None, "completionist_hours": None, "url": search_url}


def fetch_pcgamingwiki(title: str) -> dict[str, Any]:
    """PCGamingWiki API uzerinden sayfa ve config/save rehber baglantisini getirir."""
    import requests
    t = str(title or "").strip()
    if not t:
        return {"ok": False, "error": "empty_title"}
    fallback_url = f"https://www.pcgamingwiki.com/w/index.php?search={urllib.parse.quote(t)}"
    try:
        r = requests.get(
            "https://www.pcgamingwiki.com/w/api.php",
            params={"action": "opensearch", "search": t, "limit": 3, "format": "json"},
            timeout=8,
            headers={"User-Agent": "Kami/2.5"},
        )
        if r.status_code == 200:
            arr = r.json()
            if isinstance(arr, list) and len(arr) >= 4 and arr[1]:
                matched_title = str(arr[1][0])
                matched_url = str(arr[3][0])
                return {
                    "ok": True,
                    "title": matched_title,
                    "url": matched_url,
                    "map_url": f"https://mapgenie.io/search?q={urllib.parse.quote(matched_title)}",
                    "youtube_url": f"https://www.youtube.com/results?search_query={urllib.parse.quote(matched_title + ' guide walkthrough')}",
                }
    except Exception:
        log.debug("PCGamingWiki sorgusu basarisiz", exc_info=True)
    return {
        "ok": True,
        "title": t,
        "url": fallback_url,
        "map_url": f"https://mapgenie.io/search?q={urllib.parse.quote(t)}",
        "youtube_url": f"https://www.youtube.com/results?search_query={urllib.parse.quote(t + ' guide walkthrough')}",
    }


def save_inspect(path: str) -> dict[str, Any]:
    """Save veya .ini/.json dosyasini guvenli sekilde okuyup duzenlenebilir yapiya cevirir."""
    p = Path(str(path or ""))
    if not p.is_file():
        return {"ok": False, "error": "file_not_found"}
    ext = p.suffix.lower()
    raw = p.read_bytes()
    if ext == ".json":
        try:
            obj = json.loads(raw.decode("utf-8"))
            return {"ok": True, "kind": "json", "path": str(p), "text": json.dumps(obj, ensure_ascii=False, indent=2)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:120]}
    try:
        txt = raw.decode("utf-8")
        return {"ok": True, "kind": "ini" if ext in (".ini", ".cfg", ".conf") else "text", "path": str(p), "text": txt}
    except UnicodeDecodeError:
        return {"ok": True, "kind": "binary", "path": str(p), "size": len(raw), "hex_preview": raw[:256].hex(" ")}


def save_write(path: str, text: str) -> dict[str, Any]:
    """Duzenlenen JSON/INI/metin save dosyasini otomatik .bak yedegi alarak yazar."""
    p = Path(str(path or ""))
    if not p.is_file():
        return {"ok": False, "error": "file_not_found"}
    if p.suffix.lower() == ".json":
        try:
            json.loads(text)
        except Exception as exc:
            return {"ok": False, "error": f"invalid_json: {exc}"}
    bak = p.with_suffix(p.suffix + ".kami.bak")
    if not bak.exists():
        shutil.copy2(p, bak)
    p.write_text(text, encoding="utf-8")
    return {"ok": True, "path": str(p), "backup": str(bak)}


def fix_game_ini(ini_path: str, presets: list[str] | None = None) -> dict[str, Any]:
    """Tek Tik Config / .ini Duzeltici (FPS kilidi, Mouse Smoothing, VSync vb.)."""
    p = Path(str(ini_path or ""))
    if not p.is_file():
        return {"ok": False, "error": "file_not_found"}
    bak = p.with_suffix(p.suffix + ".kami.bak")
    if not bak.exists():
        shutil.copy2(p, bak)

    raw = p.read_bytes()   # v2.5.3: UTF-16 (Unreal) dosyalar UTF-8'e cevrilip bozulmasin; satir sonu korunur
    enc = "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else ("utf-8-sig" if raw[:3] == b"\xef\xbb\xbf" else "utf-8")
    txt = raw.decode(enc, errors="replace")
    nl = "\r\n" if "\r\n" in txt else "\n"
    wanted = set(presets or ["unlock_fps", "disable_mouse_accel", "disable_vsync"])
    replacements: list[tuple[str, str]] = []
    if "unlock_fps" in wanted:
        replacements += [("bSmoothFrameRate", "False"), ("FrameRateLimit", "0.000000")]
    if "disable_mouse_accel" in wanted:
        replacements += [("bEnableMouseSmoothing", "False"), ("MouseAcceleration", "0")]
    if "disable_vsync" in wanted:
        replacements += [("bUseVSync", "False"), ("iPresentInterval", "0"), ("VSync", "0")]

    applied: list[str] = []
    lines = txt.splitlines()
    for key, val in replacements:
        pat = re.compile(rf"^(\s*{re.escape(key)}\s*=\s*).*$", re.I)
        hit = False
        for i, ln in enumerate(lines):
            if pat.match(ln):
                lines[i] = pat.sub(rf"\g<1>{val}", ln)
                hit = True
                applied.append(f"{key}={val}")
        # v2.5.3: dosyada olmayan anahtar SONA EKLENMEZ: [bolum] disina yazilan anahtar oyunlarca yok sayilir ya da
        # baska motorun anahtari (Unreal/Bethesda) ilgisiz bir dosyaya girip onu bozar.
    with open(p, "w", encoding=enc, newline="") as fh:
        fh.write(nl.join(lines) + nl)
    return {"ok": True, "path": str(p), "backup": str(bak), "applied": applied,
            "not_found": [k for k, _ in replacements if not any(a.startswith(k + "=") for a in applied)]}


def snapshot_save(game_key: str, source_path: str) -> dict[str, Any]:
    """Otomatik Save Time-Machine (F9): dosya veya klasorun anlik yedegini alir."""
    src = Path(str(source_path or ""))
    if not src.exists():
        return {"ok": False, "error": "source_not_found"}
    safe_g = re.sub(r"[^a-zA-Z0-9_-]", "_", str(game_key or "game"))
    gdir = _timemachine_dir() / safe_g
    gdir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    zpath = gdir / f"{ts}.zip"
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if src.is_file():
            zf.write(src, arcname=src.name)
        else:
            for f in src.rglob("*"):
                if f.is_file():
                    zf.write(f, arcname=str(f.relative_to(src)))
    # En son 15 anlik goruntuyu koru
    snaps = sorted(gdir.glob("*.zip"), key=lambda x: x.stat().st_mtime, reverse=True)
    for old in snaps[15:]:
        old.unlink(missing_ok=True)
    return {"ok": True, "snapshot": str(zpath), "id": zpath.stem, "game_key": safe_g}


def list_snapshots(game_key: str) -> dict[str, Any]:
    safe_g = re.sub(r"[^a-zA-Z0-9_-]", "_", str(game_key or "game"))
    gdir = _timemachine_dir() / safe_g
    if not gdir.is_dir():
        return {"ok": True, "snapshots": []}
    out = []
    for z in sorted(gdir.glob("*.zip"), key=lambda x: x.stat().st_mtime, reverse=True):
        out.append({"id": z.stem, "path": str(z), "size": z.stat().st_size, "mtime": z.stat().st_mtime})
    return {"ok": True, "snapshots": out}


def _safe_zip_target(dst: Path, member_name: str) -> Path | None:
    """Zip-slip ve Windows surucu-oneki (`C:evil`, `/abs`, `..`) girislerini engeller."""
    raw = str(member_name or "").replace("\\", "/")
    if not raw or raw.startswith("/") or ":" in raw:
        return None
    parts = PurePosixPath(raw).parts
    if not parts or any(p in ("", ".", "..", "/") for p in parts):
        return None
    if Path(raw).is_absolute():
        return None
    base = dst.resolve()
    target = (base / Path(*parts)).resolve()
    if target == base or not target.is_relative_to(base):
        return None
    return target


def restore_snapshot(snapshot_path: str, target_path: str) -> dict[str, Any]:
    zp = Path(str(snapshot_path or ""))
    dst = Path(str(target_path or ""))
    if not zp.is_file():
        return {"ok": False, "error": "snapshot_not_found"}
    if dst.is_file():
        dst = dst.parent
    dst.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zp, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            target = _safe_zip_target(dst, info.filename)
            if target is None:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
    return {"ok": True, "restored_to": str(dst)}


def mod_install_zip(game_key: str, game_dir: str, zip_path: str) -> dict[str, Any]:
    """Kami Mod: .zip yama/modunu orijinal dosyalari yedekleyerek kurar (1-tik Rollback icin)."""
    gdir = Path(str(game_dir or ""))
    zp = Path(str(zip_path or ""))
    if not gdir.is_dir() or not zp.is_file():
        return {"ok": False, "error": "invalid_paths"}
    safe_g = re.sub(r"[^a-zA-Z0-9_-]", "_", str(game_key or "game"))
    mid = f"mod_{int(time.time())}_{uuid.uuid4().hex[:5]}"
    bdir = _mod_backups_dir() / safe_g / mid
    bdir.mkdir(parents=True, exist_ok=True)

    base_gdir = gdir.resolve()
    overwritten: list[str] = []
    added: list[str] = []
    with zipfile.ZipFile(zp, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            target = _safe_zip_target(base_gdir, info.filename)
            if target is None:
                continue
            rel = target.relative_to(base_gdir)
            if target.exists():
                bak = bdir / "orig" / rel
                bak.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, bak)
                overwritten.append(str(rel))
            else:
                added.append(str(rel))
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)

    manifest = {"id": mid, "game_key": safe_g, "game_dir": str(gdir), "zip": zp.name,
                "overwritten": overwritten, "added": added, "ts": time.time()}
    (bdir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "mod_id": mid, "overwritten": len(overwritten), "added": len(added), "backup_dir": str(bdir)}


def mod_rollback(backup_dir: str) -> dict[str, Any]:
    """Kami Mod 1-Tik Rollback: orijinalleri geri yukler, yeni eklenen mod dosyalarini siler."""
    bdir = Path(str(backup_dir or ""))
    mf = bdir / "manifest.json"
    if not mf.is_file():
        return {"ok": False, "error": "manifest_not_found"}
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    gdir = Path(manifest["game_dir"])
    for rel in manifest.get("added", []):
        p = gdir / rel
        if p.is_file():
            p.unlink(missing_ok=True)
    for rel in manifest.get("overwritten", []):
        orig = bdir / "orig" / rel
        if orig.is_file():
            dst = gdir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(orig, dst)
    return {"ok": True, "restored": len(manifest.get("overwritten", [])), "removed": len(manifest.get("added", []))}


def launch_external_tool(exe_path: str) -> dict[str, Any]:
    """Tek kisilik oyunlar icin harici offline arac/trainer baslatir (Kami bellege mudahale etmez)."""
    p = Path(str(exe_path or ""))
    if not p.is_file():
        return {"ok": False, "error": "exe_not_found"}
    subprocess.Popen([str(p)], cwd=str(p.parent), creationflags=NO_WINDOW)
    return {"ok": True, "path": str(p)}


def is_subtitle_candidate(text: str) -> bool:
    """Bolge kilitli OCR'da arac plakasi, hiz/skor ve HUD gurultusunu eler."""
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(s) < 6:
        return False
    # Plaka veya HUD kodu deseni: sadece buyuk harf + rakam + tire/bosluk (or. '34 ABC 123', 'HP 100')
    if len(s) <= 12 and re.fullmatch(r"[A-Z0-9\-\.:/% ]+", s):
        return False
    # En az 2 kelime veya >= 10 harf olmali
    letters = sum(1 for ch in s if ch.isalpha())
    words = [w for w in s.split(" ") if any(c.isalpha() for c in w)]
    return letters >= 5 and (len(words) >= 2 or len(s) >= 12)


def _translate_to_tr(text: str, src: str = "en") -> str:
    import tempfile
    from app.core import aitools
    raw = str(text or "").strip()[:2000]
    if not raw:
        return ""
    vtt = "WEBVTT\n\n00:00:00.000 --> 00:00:05.000\n" + raw.replace("\n\n", "\n") + "\n"
    fd, out = tempfile.mkstemp(prefix="kami_game_ocr_tr_", suffix=".srt")
    os.close(fd)
    try:
        res = aitools.translate_subtitle(vtt, out, str(src or "en")[:5], "tr", "google")
        if "error" in res or not res.get("done"):
            return raw
        done_p = Path(str(res["done"]))
        if not done_p.is_file():
            return raw
        lines = [ln for ln in done_p.read_text(encoding="utf-8", errors="replace").splitlines()
                 if ln.strip() and "-->" not in ln and not ln.strip().isdigit()]
        return "\n".join(lines).strip() or raw
    except Exception:
        return raw
    finally:
        try:
            os.remove(out)
        except OSError:
            pass


def game_ocr_translate(roi: list[float] | None = None, lang: str = "en") -> dict[str, Any]:
    """Ekranin yalnizca kilitli altyazi bolgesini okuyup plaka/HUD gurultusunu eleyerek Turkceye cevirir."""
    from PIL import ImageGrab
    from app.core import ocr

    box = roi if roi and len(roi) == 4 else [0.15, 0.74, 0.70, 0.22]
    img = ImageGrab.grab()
    w, h = img.size
    x1 = max(0, min(w - 10, int(w * float(box[0]))))
    y1 = max(0, min(h - 10, int(h * float(box[1]))))
    x2 = max(x1 + 10, min(w, int(w * (float(box[0]) + float(box[2])))))
    y2 = max(y1 + 10, min(h, int(h * (float(box[1]) + float(box[3])))))
    crop = img.crop((x1, y1, x2, y2))

    tmp_png = paths.DATA_DIR / "game_ocr_crop.png"
    tmp_png.parent.mkdir(parents=True, exist_ok=True)
    crop.save(tmp_png)
    res = ocr.read_text(str(tmp_png), lang=lang)
    raw = re.sub(r"\s+", " ", str(res.get("text") or "")).strip()
    if not is_subtitle_candidate(raw):
        return {"ok": True, "skipped": True, "raw": raw, "translated": ""}
    if raw == _OCR_LAST["raw"] and _OCR_LAST["tr"]:
        return {"ok": True, "cached": True, "raw": raw, "translated": _OCR_LAST["tr"]}

    tr_txt = _translate_to_tr(raw, src=lang)
    _OCR_LAST["raw"] = raw
    _OCR_LAST["tr"] = tr_txt
    return {"ok": True, "raw": raw, "translated": tr_txt}
