"""Kami Suzgec: hizli dosya arama (Everything es.exe veya scandir), disk agac haritasi ve guvenli Cop Kutusu temizligi."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any


def search_files(query: str, root: str = "", limit: int = 80) -> dict[str, Any]:
    q = str(query or "").strip()
    if not q:
        return {"ok": False, "items": []}
    # Everything CLI (es.exe) varsa milisaniyede ara
    try:
        args = ["es.exe", "-n", str(int(limit)), q]
        if root:
            args = ["es.exe", "-n", str(int(limit)), "-path", root, q]
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=6, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode == 0 and r.stdout.strip():
            items = []
            for line in r.stdout.splitlines()[:limit]:
                p = Path(line.strip())
                try:
                    sz = p.stat().st_size if p.is_file() else 0
                except OSError:
                    sz = 0
                items.append({"path": str(p), "name": p.name, "size": sz, "dir": p.is_dir()})
            return {"ok": True, "engine": "everything", "items": items}
    except Exception:
        pass
    base = Path(root) if root and Path(root).is_dir() else Path.home()
    ql = q.lower()
    items = []
    stack = [base]
    scanned = 0
    while stack and len(items) < limit and scanned < 25000:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for ent in it:
                    scanned += 1
                    if ql in ent.name.lower():
                        try:
                            sz = ent.stat(follow_symlinks=False).st_size if ent.is_file(follow_symlinks=False) else 0
                        except OSError:
                            sz = 0
                        items.append({"path": ent.path, "name": ent.name, "size": sz, "dir": ent.is_dir(follow_symlinks=False)})
                        if len(items) >= limit:
                            break
                    elif ent.is_dir(follow_symlinks=False) and not ent.name.startswith("."):
                        stack.append(Path(ent.path))
        except OSError:
            continue
    return {"ok": True, "engine": "scandir", "items": items}


def disk_treemap(root: str = "", budget_s: float = 12.0) -> dict[str, Any]:
    """Kokteki ogeleri boyuta gore siralar. Klasor basina sabit oge siniri YOK (buyuk klasorler kucuk gorunuyordu);
    toplam sure butcesi asilirsa kalan klasorler 'approx' isaretlenir."""
    import time
    base = Path(root) if root and Path(root).is_dir() else Path.home()
    t_end = time.monotonic() + budget_s
    buckets: list[dict[str, Any]] = []
    try:
        entries = list(os.scandir(base))
    except OSError as exc:
        return {"ok": False, "error": str(exc)[:120], "items": []}
    for ent in entries:
        sz, approx = 0, False
        try:
            is_dir = ent.is_dir(follow_symlinks=False)
            if not is_dir:
                sz = ent.stat(follow_symlinks=False).st_size
        except OSError:
            continue
        if is_dir:
            st = [ent.path]
            while st:
                if time.monotonic() > t_end:
                    approx = True
                    break
                d = st.pop()
                try:
                    with os.scandir(d) as sub:
                        for x in sub:
                            try:
                                if x.is_file(follow_symlinks=False):
                                    sz += x.stat(follow_symlinks=False).st_size
                                elif x.is_dir(follow_symlinks=False):
                                    st.append(x.path)
                            except OSError:
                                pass
                except OSError:
                    pass
        buckets.append({"name": ent.name, "path": ent.path, "size": sz, "dir": is_dir, "approx": approx})
    buckets.sort(key=lambda x: x["size"], reverse=True)
    return {"ok": True, "root": str(base), "items": buckets[:24], "approx": any(x["approx"] for x in buckets)}


def _protected(p: str) -> bool:
    """Surucu koku, kullanici klasoru, Windows/Program Files ve Kami'nin veri klasoru asla cope gitmez."""
    from app import paths
    rp = Path(p).resolve()
    if rp.parent == rp:   # surucu koku
        return True
    bad = [Path.home(), paths.DATA_DIR]
    for env in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData", "USERPROFILE", "APPDATA", "LOCALAPPDATA"):
        v = os.environ.get(env)
        if v:
            bad.append(Path(v))
    for b in bad:
        try:
            br = b.resolve()
        except OSError:
            continue
        if rp == br or (b in (paths.DATA_DIR,) and br in rp.parents):
            return True
        if env_root := os.environ.get("SystemRoot"):
            if Path(env_root).resolve() in rp.parents or rp == Path(env_root).resolve():
                return True
    return False


def trash_path(path: str) -> dict[str, Any]:
    """Kalici silmez, Windows Geri Donusum Kutusu'na gonderir."""
    p = str(path or "").strip()
    if not p or not os.path.exists(p):
        return {"ok": False, "error": "not_found"}
    if _protected(p):
        return {"ok": False, "error": "protected"}
    try:
        ps = (
            "Add-Type -AssemblyName Microsoft.VisualBasic; "
            f"$p = '{p.replace(chr(39), chr(39)*2)}'; "
            "if (Test-Path -LiteralPath $p -PathType Container) { "
            "[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory($p,'OnlyErrorDialogs','SendToRecycleBin') } "
            "else { [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($p,'OnlyErrorDialogs','SendToRecycleBin') }"
        )
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return {"ok": r.returncode == 0}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}
