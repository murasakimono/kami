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
    # v2.5.3 GUVENLIK: eskiden yol PowerShell betigine metin olarak gomuluyordu; ’ (U+2019) gibi tirnaklar kacisi
    # atlatip komut calistirabiliyordu (or. "a’;Start-Process calc;’.mp4"). Artik dogrudan SHFileOperationW (betik yok).
    try:
        from app.core.mediatools import to_trash
        ok = to_trash([p])
        return {"ok": bool(ok and not os.path.exists(p))} if ok else {"ok": False, "error": "trash_failed"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}


_EXT_CATEGORIES: dict[str, set[str]] = {
    "Video": {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v", ".ts"},
    "Görsel": {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg", ".ico", ".psd", ".tiff", ".heic"},
    "Ses": {".mp3", ".flac", ".wav", ".aac", ".ogg", ".opus", ".m4a", ".alac"},
    "Arşiv": {".zip", ".rar", ".7z", ".tar", ".gz", ".xz", ".bz2", ".iso"},
    "Program": {".exe", ".msi", ".msix", ".bat", ".cmd", ".ps1", ".whl", ".dll"},
    "Belge": {".pdf", ".docx", ".doc", ".xlsx", ".pptx", ".epub", ".txt", ".md", ".csv", ".json"},
}
_SKIP_DIR_NAMES = {"$recycle.bin", "system volume information", "winsxs", "windows", "programdata"}


def _iter_files_bounded(root: str = "", max_files: int = 25000, budget_s: float = 10.0):
    """Sinirli sure/dosya butcesiyle hizli dosya gezgini (approx bayragi dondurur)."""
    import time
    base = Path(root) if root and Path(root).is_dir() else Path.home()
    t_end = time.monotonic() + max(0.5, float(budget_s))
    stack = [str(base)]
    seen = 0
    approx = False
    while stack:
        if seen >= max_files or time.monotonic() > t_end:
            approx = True
            break
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for ent in it:
                    if seen >= max_files or time.monotonic() > t_end:
                        approx = True
                        break
                    try:
                        if ent.is_symlink():
                            continue
                        if ent.is_dir(follow_symlinks=False):
                            if ent.name.lower() in _SKIP_DIR_NAMES or ent.name.startswith("$"):
                                continue
                            stack.append(ent.path)
                        elif ent.is_file(follow_symlinks=False):
                            st = ent.stat(follow_symlinks=False)
                            seen += 1
                            yield ent.path, ent.name, int(st.st_size), int(st.st_mtime)
                    except OSError:
                        continue
        except OSError:
            continue
    return base, approx


def drive_summary() -> dict[str, Any]:
    """Tum bagli suruculeri ve hizli kullanici klasorlerini listeler."""
    import shutil
    drives: list[dict[str, Any]] = []
    if os.name == "nt":
        import ctypes
        mask = int(ctypes.windll.kernel32.GetLogicalDrives() or 0)
        for i in range(26):
            if not (mask & (1 << i)):
                continue
            letter = chr(65 + i)
            root = f"{letter}:\\"
            try:
                du = shutil.disk_usage(root)
                if du.total <= 0:
                    continue
                used = max(0, du.total - du.free)
                drives.append({
                    "letter": letter,
                    "root": root,
                    "total": int(du.total),
                    "used": int(used),
                    "free": int(du.free),
                    "pct": round((used / du.total) * 100, 1),
                })
            except OSError:
                continue
    else:
        du = shutil.disk_usage("/")
        used = max(0, du.total - du.free)
        drives.append({"letter": "/", "root": "/", "total": int(du.total), "used": int(used), "free": int(du.free),
                       "pct": round((used / max(1, du.total)) * 100, 1)})

    home = Path.home()
    places: list[dict[str, Any]] = []
    for lbl, cand in (
        ("İndirilenler", home / "Downloads"),
        ("Masaüstü", home / "Desktop"),
        ("Belgeler", home / "Documents"),
        ("Videolar", home / "Videos"),
        ("Resimler", home / "Pictures"),
    ):
        if cand.is_dir():
            places.append({"name": lbl, "path": str(cand)})
    return {"ok": True, "drives": drives, "places": places}


def by_ext(root: str = "", max_files: int = 30000, budget_s: float = 10.0) -> dict[str, Any]:
    """Dosyalari uzanti ve tur kategorisine gore toplar."""
    import time
    base = Path(root) if root and Path(root).is_dir() else Path.home()
    t_end = time.monotonic() + budget_s
    cat_map: dict[str, dict[str, Any]] = {k: {"name": k, "size": 0, "count": 0} for k in _EXT_CATEGORIES}
    cat_map["Diğer"] = {"name": "Diğer", "size": 0, "count": 0}
    ext_map: dict[str, dict[str, Any]] = {}
    total_size = 0
    total_files = 0
    approx = False
    stack = [str(base)]
    while stack:
        if total_files >= max_files or time.monotonic() > t_end:
            approx = True
            break
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for ent in it:
                    if total_files >= max_files or time.monotonic() > t_end:
                        approx = True
                        break
                    try:
                        if ent.is_symlink():
                            continue
                        if ent.is_dir(follow_symlinks=False):
                            if ent.name.lower() in _SKIP_DIR_NAMES or ent.name.startswith("$"):
                                continue
                            stack.append(ent.path)
                        elif ent.is_file(follow_symlinks=False):
                            sz = int(ent.stat(follow_symlinks=False).st_size)
                            ext = Path(ent.name).suffix.lower() or "(yok)"
                            total_size += sz
                            total_files += 1
                            e = ext_map.setdefault(ext, {"ext": ext, "size": 0, "count": 0})
                            e["size"] += sz
                            e["count"] += 1
                            placed = False
                            for cname, sset in _EXT_CATEGORIES.items():
                                if ext in sset:
                                    cat_map[cname]["size"] += sz
                                    cat_map[cname]["count"] += 1
                                    placed = True
                                    break
                            if not placed:
                                cat_map["Diğer"]["size"] += sz
                                cat_map["Diğer"]["count"] += 1
                    except OSError:
                        continue
        except OSError:
            continue
    cats = sorted([v for v in cat_map.values() if v["count"] > 0], key=lambda x: x["size"], reverse=True)
    exts = sorted(ext_map.values(), key=lambda x: x["size"], reverse=True)[:40]
    return {"ok": True, "root": str(base), "total_size": total_size, "total_files": total_files, "approx": approx,
            "categories": cats, "extensions": exts}


def largest_files(root: str = "", limit: int = 100, max_files: int = 35000, budget_s: float = 10.0) -> dict[str, Any]:
    """Klasordeki en buyuk dosyalari dondurur."""
    import heapq
    import time
    base = Path(root) if root and Path(root).is_dir() else Path.home()
    t_end = time.monotonic() + budget_s
    lim = max(1, min(500, int(limit or 100)))
    heap: list[tuple[int, str, str, int]] = []
    scanned = 0
    approx = False
    stack = [str(base)]
    while stack:
        if scanned >= max_files or time.monotonic() > t_end:
            approx = True
            break
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for ent in it:
                    if scanned >= max_files or time.monotonic() > t_end:
                        approx = True
                        break
                    try:
                        if ent.is_symlink():
                            continue
                        if ent.is_dir(follow_symlinks=False):
                            if ent.name.lower() in _SKIP_DIR_NAMES or ent.name.startswith("$"):
                                continue
                            stack.append(ent.path)
                        elif ent.is_file(follow_symlinks=False):
                            st = ent.stat(follow_symlinks=False)
                            scanned += 1
                            row = (int(st.st_size), ent.path, ent.name, int(st.st_mtime))
                            if len(heap) < lim:
                                heapq.heappush(heap, row)
                            elif row[0] > heap[0][0]:
                                heapq.heapreplace(heap, row)
                    except OSError:
                        continue
        except OSError:
            continue
    items = []
    for sz, p, name, mt in sorted(heap, reverse=True):
        items.append({"path": p, "name": name, "size": sz, "ext": Path(name).suffix.lower(), "mtime": mt, "protected": _protected(p)})
    return {"ok": True, "root": str(base), "scanned": scanned, "approx": approx, "items": items}


def _partial_hash(path: str, size: int) -> str:
    import hashlib
    h = hashlib.blake2b(digest_size=16)
    with open(path, "rb") as fh:
        h.update(fh.read(8192))
        if size > 16384:
            fh.seek(max(0, size - 8192))
            h.update(fh.read(8192))
    return h.hexdigest()


def _full_sha256(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def find_duplicates(root: str = "", min_size: int = 4096, max_files: int = 15000, budget_s: float = 12.0) -> dict[str, Any]:
    """3 asamali birebir dosya kopya bulucu: boyut -> 8KB bas+son -> tam SHA-256."""
    import time
    base = Path(root) if root and Path(root).is_dir() else Path.home()
    t_end = time.monotonic() + budget_s
    by_size: dict[int, list[tuple[str, str, int]]] = {}
    scanned = 0
    approx = False
    stack = [str(base)]
    while stack:
        if scanned >= max_files or time.monotonic() > t_end:
            approx = True
            break
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for ent in it:
                    if scanned >= max_files or time.monotonic() > t_end:
                        approx = True
                        break
                    try:
                        if ent.is_symlink():
                            continue
                        if ent.is_dir(follow_symlinks=False):
                            if ent.name.lower() in _SKIP_DIR_NAMES or ent.name.startswith("$"):
                                continue
                            stack.append(ent.path)
                        elif ent.is_file(follow_symlinks=False):
                            st = ent.stat(follow_symlinks=False)
                            scanned += 1
                            sz = int(st.st_size)
                            if sz >= min_size:
                                by_size.setdefault(sz, []).append((ent.path, ent.name, int(st.st_mtime)))
                    except OSError:
                        continue
        except OSError:
            continue

    groups = []
    total_wasted = 0
    for sz in sorted((k for k, v in by_size.items() if len(v) >= 2), reverse=True):
        if time.monotonic() > t_end:
            approx = True
            break
        partial_buckets: dict[str, list[tuple[str, str, int]]] = {}
        for p, name, mt in by_size[sz]:
            try:
                ph = _partial_hash(p, sz)
                partial_buckets.setdefault(ph, []).append((p, name, mt))
            except OSError:
                continue
        for pb in partial_buckets.values():
            if len(pb) < 2:
                continue
            full_buckets: dict[str, list[tuple[str, str, int]]] = {}
            for p, name, mt in pb:
                if time.monotonic() > t_end:
                    approx = True
                    break
                try:
                    fh_hex = _full_sha256(p)
                    full_buckets.setdefault(fh_hex, []).append((p, name, mt))
                except OSError:
                    continue
            for fh_hex, files in full_buckets.items():
                if len(files) >= 2:
                    files_sorted = sorted(files, key=lambda x: x[2])
                    wasted = sz * (len(files_sorted) - 1)
                    total_wasted += wasted
                    groups.append({
                        "hash": fh_hex[:16],
                        "size": sz,
                        "wasted": wasted,
                        "files": [{"path": f[0], "name": f[1], "mtime": f[2], "protected": _protected(f[0])} for f in files_sorted],
                    })
    groups.sort(key=lambda g: g["wasted"], reverse=True)
    return {"ok": True, "root": str(base), "scanned": scanned, "approx": approx, "groups": groups[:80], "total_wasted": total_wasted}


def _dhash64(path: str) -> tuple[int, int, int] | None:
    from PIL import Image
    with Image.open(path) as im:
        w, h = im.size
        small = im.convert("L").resize((9, 8), Image.Resampling.BILINEAR)
        px = list(small.get_flattened_data()) if hasattr(small, "get_flattened_data") else list(small.getdata())
    bits = 0
    idx = 0
    for row in range(8):
        off = row * 9
        for col in range(8):
            if px[off + col] > px[off + col + 1]:
                bits |= (1 << idx)
            idx += 1
    return bits, w, h


def find_similar_images(root: str = "", threshold: int = 8, max_images: int = 2500, budget_s: float = 12.0) -> dict[str, Any]:
    """Pillow 64-bit dHash ile gorsel olarak benzer veya yeniden boyutlandirilmis fotograflari kumeler."""
    import time
    base = Path(root) if root and Path(root).is_dir() else (Path.home() / "Pictures" if (Path.home() / "Pictures").is_dir() else Path.home())
    t_end = time.monotonic() + budget_s
    img_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    records: list[dict[str, Any]] = []
    approx = False
    stack = [str(base)]
    while stack:
        if len(records) >= max_images or time.monotonic() > t_end:
            approx = True
            break
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for ent in it:
                    if len(records) >= max_images or time.monotonic() > t_end:
                        approx = True
                        break
                    try:
                        if ent.is_symlink():
                            continue
                        if ent.is_dir(follow_symlinks=False):
                            if ent.name.lower() in _SKIP_DIR_NAMES or ent.name.startswith("."):
                                continue
                            stack.append(ent.path)
                        elif ent.is_file(follow_symlinks=False) and Path(ent.name).suffix.lower() in img_exts:
                            dh = _dhash64(ent.path)
                            if dh is None:
                                continue
                            sz = int(ent.stat(follow_symlinks=False).st_size)
                            bits, w, h = dh
                            records.append({"path": ent.path, "name": ent.name, "size": sz, "width": w, "height": h, "hash": bits})
                    except Exception:
                        continue
        except OSError:
            continue

    n = len(records)
    parent = list(range(n))

    def find_root(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    th = max(0, min(20, int(threshold)))
    for i in range(n):
        hi = records[i]["hash"]
        if time.monotonic() > t_end:
            approx = True
            break
        for j in range(i + 1, n):
            if (hi ^ records[j]["hash"]).bit_count() <= th:
                ri, rj = find_root(i), find_root(j)
                if ri != rj:
                    parent[rj] = ri

    clusters: dict[int, list[dict[str, Any]]] = {}
    for i, rec in enumerate(records):
        r = find_root(i)
        clusters.setdefault(r, []).append(rec)

    groups = []
    for items in clusters.values():
        if len(items) < 2:
            continue
        items_sorted = sorted(items, key=lambda x: (x["width"] * x["height"], x["size"]), reverse=True)
        groups.append({
            "count": len(items_sorted),
            "total_size": sum(x["size"] for x in items_sorted),
            "items": [{k: v for k, v in it.items() if k != "hash"} | {"hash": f"{it['hash']:016x}"} for it in items_sorted],
        })
    groups.sort(key=lambda g: g["total_size"], reverse=True)
    return {"ok": True, "root": str(base), "scanned": n, "approx": approx, "groups": groups[:60]}


def _dir_size(path: Path, budget_s: float = 1.5) -> tuple[int, int]:
    import time
    t_end = time.monotonic() + budget_s
    total, cnt = 0, 0
    stack = [str(path)]
    while stack and time.monotonic() < t_end:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for ent in it:
                    if time.monotonic() >= t_end:
                        break
                    try:
                        if ent.is_file(follow_symlinks=False):
                            total += int(ent.stat(follow_symlinks=False).st_size)
                            cnt += 1
                        elif ent.is_dir(follow_symlinks=False):
                            stack.append(ent.path)
                    except OSError:
                        continue
        except OSError:
            continue
    return total, cnt


def scan_safe_caches() -> dict[str, Any]:
    """Yalnızca guvenli, yeniden uretilebilir uygulama/tarayici onbelleklerini tarar (_protected disinda)."""
    import tempfile
    local = Path(os.environ.get("LOCALAPPDATA", "") or (Path.home() / "AppData" / "Local"))
    candidates = [
        ("Sistem Geçici Klasörü (%TEMP%)", Path(tempfile.gettempdir())),
        ("pip İndirme Önbelleği", local / "pip" / "cache"),
        ("npm Önbelleği", Path(os.environ.get("APPDATA", "") or (Path.home() / "AppData" / "Roaming")) / "npm-cache"),
        ("Brave Code Cache", local / "BraveSoftware" / "Brave-Browser" / "User Data" / "Default" / "Code Cache"),
        ("Chrome Code Cache", local / "Google" / "Chrome" / "User Data" / "Default" / "Code Cache"),
        ("Edge Code Cache", local / "Microsoft" / "Edge" / "User Data" / "Default" / "Code Cache"),
        ("DirectX Shader Önbelleği", local / "D3DSCache"),
        ("CrashDumps", local / "CrashDumps"),
    ]
    items: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for label, p in candidates:
        if not p.exists():
            continue
        sp = str(p)
        if sp.lower() in seen_paths:
            continue
        seen_paths.add(sp.lower())
        if _protected(sp):
            # Kok klasor korumaliysa (ornek: Temp), altindaki eski guvenli ogeleri teklif et
            try:
                children = []
                for ent in os.scandir(p):
                    if not _protected(ent.path):
                        sz = int(ent.stat(follow_symlinks=False).st_size) if ent.is_file(follow_symlinks=False) else _dir_size(Path(ent.path), 0.35)[0]
                        children.append((sz, ent.path, ent.name))
                children.sort(reverse=True)
                for sz, cp, cname in children[:12]:
                    if sz > 0:
                        items.append({"label": f"Geçici: {cname}", "path": cp, "size": sz, "count": 1, "safe": True})
            except OSError:
                pass
            continue
        sz, cnt = _dir_size(p, 1.2)
        if sz > 0:
            items.append({"label": label, "path": sp, "size": sz, "count": cnt, "safe": True})
    items.sort(key=lambda x: x["size"], reverse=True)
    return {"ok": True, "items": items, "total_size": sum(x["size"] for x in items)}


def preview_file(path: str) -> dict[str, Any]:
    """QuickLook (Space) icin gorsel kucuk resim, metin kesiti veya dosya ozeti dondurur."""
    import base64
    import io
    p = Path(str(path or ""))
    if not p.is_file():
        return {"ok": False, "error": "not_found"}
    try:
        st = p.stat()
    except OSError as exc:
        return {"ok": False, "error": str(exc)[:120]}
    ext = p.suffix.lower()
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
        try:
            from PIL import Image
            with Image.open(p) as im:
                w, h = im.size
                im_copy = im.copy()
                im_copy.thumbnail((920, 720))
                buf = io.BytesIO()
                im_copy.convert("RGBA" if ext == ".png" else "RGB").save(buf, format="PNG")
                url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
            return {"ok": True, "kind": "image", "name": p.name, "size": int(st.st_size), "width": w, "height": h, "url": url}
        except Exception:
            pass
    text_exts = {".txt", ".md", ".log", ".json", ".py", ".js", ".ts", ".css", ".html", ".xml", ".csv", ".ini", ".yaml", ".yml", ".srt", ".ass", ".lrc"}
    if ext in text_exts or int(st.st_size) < 65536:
        try:
            with open(p, "rb") as fh:
                raw = fh.read(16384)
            if b"\x00" not in raw:
                return {"ok": True, "kind": "text", "name": p.name, "size": int(st.st_size),
                        "text": raw.decode("utf-8", errors="replace")}
        except OSError:
            pass
    return {"ok": True, "kind": "meta", "name": p.name, "ext": ext, "size": int(st.st_size), "mtime": int(st.st_mtime)}


# ---------- Kami 2.0: C12 "Kami Dust" (Kaldirilan Programlarin Yetim Artik Avcisi) ----------
_SAFE_KEEP_VENDORS = {
    "microsoft", "windows", "google", "bravesoftware", "brave-browser", "mozilla", "kami", "murasakimono",
    "nvidia", "nvidia corporation", "amd", "intel", "valve", "steam", "epicgameslauncher", "epic games",
    "discord", "spotify", "python", "pip", "uv", "npm", "npm-cache", "nodejs", "git", "github",
    "ollama", "adobe", "apple", "apple computer", "packages", "programs", "temp", "d3dscache", "crashdumps",
    "connecteddevicesplatform", "comms", "publishers", " peerdistrepub", " diagnostics", "fontcache",
    "squirreltemp", "cef", "webview2", "ebwebview", "realtek", "omen", "hp", "hewlett-packard", "atk",
}


def _installed_program_tokens() -> set[str]:
    """Kurulu programlarin (Winreg Uninstall + Program Files + Calisan surecler) normalize edilmis ad anahtarlarini toplar."""
    import re
    tokens: set[str] = set(_SAFE_KEEP_VENDORS)

    def add_tok(raw: str) -> None:
        s = str(raw or "").strip().lower()
        if not s:
            return
        tokens.add(s)
        clean = re.sub(r"[^a-z0-9]+", "", s)
        if len(clean) >= 3:
            tokens.add(clean)
        for part in re.split(r"[^a-z0-9]+", s):
            if len(part) >= 3:
                tokens.add(part)

    for env in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        root = os.environ.get(env)
        if root and os.path.isdir(root):
            try:
                for ent in os.scandir(root):
                    if ent.is_dir(follow_symlinks=False):
                        add_tok(ent.name)
            except OSError:
                pass
    local_progs = Path(os.environ.get("LOCALAPPDATA", "") or (Path.home() / "AppData" / "Local")) / "Programs"
    if local_progs.is_dir():
        try:
            for ent in os.scandir(local_progs):
                if ent.is_dir(follow_symlinks=False):
                    add_tok(ent.name)
        except OSError:
            pass
    if os.name == "nt":
        try:
            import winreg
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                for sub in (
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
                ):
                    try:
                        with winreg.OpenKey(hive, sub) as k:
                            for i in range(winreg.QueryInfoKey(k)[0]):
                                try:
                                    sk_name = winreg.EnumKey(k, i)
                                    add_tok(sk_name)
                                    with winreg.OpenKey(k, sk_name) as sk:
                                        for val_name in ("DisplayName", "Publisher", "InstallLocation"):
                                            try:
                                                v = str(winreg.QueryValueEx(sk, val_name)[0] or "")
                                                if val_name == "InstallLocation" and v:
                                                    add_tok(Path(v).name)
                                                else:
                                                    add_tok(v)
                                            except OSError:
                                                pass
                                except OSError:
                                    pass
                    except OSError:
                        pass
        except ImportError:
            pass
    return tokens


def scan_kami_dust(min_idle_days: int = 21, min_size_kb: int = 128) -> dict[str, Any]:
    """C12 Kami Dust: %APPDATA% ve %LOCALAPPDATA% altindaki kaldirilmis programlardan kalan yetim klasorleri bulur.
    Yalnizca kurulu program listesinde eslesmeyen, icinde aktif .exe bulunmayan ve `min_idle_days` gundur dokunulmamis
    klasorleri listeler. Silme islemi her zaman Geri Donusum Kutusu'na (`trash_path`) gider."""
    import re
    import time

    tokens = _installed_program_tokens()
    now = time.time()
    cutoff = now - max(1, int(min_idle_days)) * 86400
    min_bytes = max(1024, int(min_size_kb) * 1024)

    roaming = Path(os.environ.get("APPDATA", "") or (Path.home() / "AppData" / "Roaming"))
    local = Path(os.environ.get("LOCALAPPDATA", "") or (Path.home() / "AppData" / "Local"))

    orphans: list[dict[str, Any]] = []
    for scope_lbl, root in (("AppData\\Roaming", roaming), ("AppData\\Local", local)):
        if not root.is_dir():
            continue
        try:
            entries = list(os.scandir(root))
        except OSError:
            continue
        for ent in entries:
            try:
                if not ent.is_dir(follow_symlinks=False) or ent.is_symlink():
                    continue
                nm = ent.name
                low = nm.lower().strip()
                if low.startswith((".", "$", "_")) or low in _SAFE_KEEP_VENDORS:
                    continue
                norm = re.sub(r"[^a-z0-9]+", "", low)
                if not norm or norm in tokens or low in tokens:
                    continue
                parts = [p for p in re.split(r"[^a-z0-9]+", low) if len(p) >= 4]
                if any(p in tokens for p in parts):
                    continue
                st = ent.stat(follow_symlinks=False)
                if st.st_mtime > cutoff:
                    continue
                p_obj = Path(ent.path)
                # Icinde dogrudan calistirilabilir .exe varsa yetim degil, portable uygulamadir -> koru
                has_exe = False
                try:
                    for sub in os.scandir(p_obj):
                        if sub.is_file(follow_symlinks=False) and sub.name.lower().endswith(".exe"):
                            has_exe = True
                            break
                except OSError:
                    pass
                if has_exe:
                    continue
                sz, cnt = _dir_size(p_obj, budget_s=0.45)
                if sz < min_bytes:
                    continue
                idle_days = int((now - st.st_mtime) // 86400)
                orphans.append({
                    "name": nm,
                    "scope": scope_lbl,
                    "path": ent.path,
                    "size": sz,
                    "count": cnt,
                    "idle_days": idle_days,
                    "mtime": int(st.st_mtime),
                })
            except OSError:
                continue

    orphans.sort(key=lambda x: x["size"], reverse=True)
    return {
        "ok": True,
        "feature": "Kami Dust",
        "items": orphans[:80],
        "total_size": sum(x["size"] for x in orphans[:80]),
        "count": len(orphans[:80]),
    }


def run_folder_janitor(download_dir: str = "", dry_run: bool = False) -> dict[str, Any]:
    """C9 Hazel 6 Tarzi Otomatik Klasor Bekcisi:
    Kami'nin otomatik indirme klasorlendirmesiyle (Video, Muzik, Arsiv, Program, Belge, Torrent) ASLA cakismaz;
    aktif indirmelere (.aria2 / .part / .crdownload) dokunmaz.
    Kurallar:
    1) Masaustunde 48 saatten eski ekran goruntulerini (Screenshot / Ekran Goruntusu *.png/*.jpg) Pictures\\Screenshots altina tasir.
    2) Downloads veya Downloads\\Program altinda 14 gunden eski kurulum dosyalarini (.exe/.msi) listeler / Arsiv_Kurulumlar altina tasir.
    3) Masaustu veya Downloads kokundeki 3 gunden eski ders/makale PDF'lerini Downloads\\Belge altina duzenler (ve Reader'a indeksler)."""
    import shutil
    import time

    now = time.time()
    home = Path.home()
    dl_base = Path(download_dir) if download_dir and Path(download_dir).is_dir() else (home / "Downloads")
    desktop = home / "Desktop"
    screenshots_dst = home / "Pictures" / "Screenshots"

    actions: list[dict[str, Any]] = []

    def is_busy_download(p: Path) -> bool:
        if p.suffix.lower() in (".aria2", ".part", ".crdownload", ".tmp"):
            return True
        return p.with_suffix(p.suffix + ".aria2").exists() or p.with_suffix(".aria2").exists()

    # Kural 1: Masaustu 48s+ ekran goruntuleri
    if desktop.is_dir():
        try:
            for ent in os.scandir(desktop):
                if not ent.is_file(follow_symlinks=False):
                    continue
                p = Path(ent.path)
                nm = p.name.lower()
                if p.suffix.lower() in (".png", ".jpg", ".jpeg") and any(
                    k in nm for k in ("screenshot", "ekran görüntüsü", "ekran_goruntusu", "kamicapture", "snag")
                ):
                    st = ent.stat(follow_symlinks=False)
                    if (now - st.st_mtime) >= 48 * 3600 and not is_busy_download(p):
                        dst = screenshots_dst / p.name
                        if not dry_run:
                            screenshots_dst.mkdir(parents=True, exist_ok=True)
                            if not dst.exists():
                                shutil.move(str(p), str(dst))
                        actions.append({"rule": "Masaüstü Ekran Görüntüsü (>48 sa)", "name": p.name, "from": str(p), "to": str(dst), "size": int(st.st_size)})
        except OSError:
            pass

    # Kural 2: 14 gunden eski .exe/.msi kurulum dosyalari
    old_inst_dir = dl_base / "Program" / "Eski_Kurulumlar"
    for scan_dir in (dl_base, dl_base / "Program"):
        if not scan_dir.is_dir():
            continue
        try:
            for ent in os.scandir(scan_dir):
                if not ent.is_file(follow_symlinks=False):
                    continue
                p = Path(ent.path)
                if p.suffix.lower() in (".exe", ".msi") and not is_busy_download(p):
                    st = ent.stat(follow_symlinks=False)
                    if (now - st.st_mtime) >= 14 * 86400:
                        dst = old_inst_dir / p.name
                        if not dry_run:
                            old_inst_dir.mkdir(parents=True, exist_ok=True)
                            if not dst.exists():
                                shutil.move(str(p), str(dst))
                        actions.append({"rule": "Eski Kurulum Dosyası (>14 gün)", "name": p.name, "from": str(p), "to": str(dst), "size": int(st.st_size)})
        except OSError:
            pass

    # Kural 3: Downloads kokunde kalmis 3 gunden eski PDF/EPUB dosyalari -> Downloads\Belge
    belge_dir = dl_base / "Belge"
    if dl_base.is_dir():
        try:
            for ent in os.scandir(dl_base):
                if not ent.is_file(follow_symlinks=False):
                    continue
                p = Path(ent.path)
                if p.suffix.lower() in (".pdf", ".epub") and not is_busy_download(p):
                    st = ent.stat(follow_symlinks=False)
                    if (now - st.st_mtime) >= 3 * 86400:
                        dst = belge_dir / p.name
                        if not dry_run:
                            belge_dir.mkdir(parents=True, exist_ok=True)
                            if not dst.exists():
                                shutil.move(str(p), str(dst))
                        actions.append({"rule": "Kök Dizin PDF/EPUB (>3 gün → Belge)", "name": p.name, "from": str(p), "to": str(dst), "size": int(st.st_size)})
        except OSError:
            pass

    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "actions": actions[:60],
        "count": len(actions),
        "total_size": sum(x["size"] for x in actions),
    }

