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
        r = subprocess.run(args, capture_output=True, text=True, timeout=6)
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


def disk_treemap(root: str = "") -> dict[str, Any]:
    base = Path(root) if root and Path(root).is_dir() else Path.home()
    buckets: list[dict[str, Any]] = []
    try:
        with os.scandir(base) as it:
            for ent in it:
                sz = 0
                if ent.is_file(follow_symlinks=False):
                    try:
                        sz = ent.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
                elif ent.is_dir(follow_symlinks=False):
                    st = [ent.path]
                    n = 0
                    while st and n < 4000:
                        d = st.pop()
                        try:
                            with os.scandir(d) as sub:
                                for s in sub:
                                    n += 1
                                    if s.is_file(follow_symlinks=False):
                                        try:
                                            sz += s.stat(follow_symlinks=False).st_size
                                        except OSError:
                                            pass
                                    elif s.is_dir(follow_symlinks=False):
                                        st.append(s.path)
                        except OSError:
                            pass
                buckets.append({"name": ent.name, "path": ent.path, "size": sz, "dir": ent.is_dir(follow_symlinks=False)})
    except OSError as exc:
        return {"ok": False, "error": str(exc)[:120], "items": []}
    buckets.sort(key=lambda x: x["size"], reverse=True)
    return {"ok": True, "root": str(base), "items": buckets[:24]}


def trash_path(path: str) -> dict[str, Any]:
    """Kalici silmez, Windows Geri Donusum Kutusu'na gonderir."""
    p = str(path or "").strip()
    if not p or not os.path.exists(p):
        return {"ok": False, "error": "not_found"}
    try:
        ps = (
            "Add-Type -AssemblyName Microsoft.VisualBasic; "
            f"$p = '{p.replace(chr(39), chr(39)*2)}'; "
            "if (Test-Path -LiteralPath $p -PathType Container) { "
            "[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory($p,'OnlyErrorDialogs','SendToRecycleBin') } "
            "else { [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($p,'OnlyErrorDialogs','SendToRecycleBin') }"
        )
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=15)
        return {"ok": r.returncode == 0}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}
