"""Kami Lattice: cihazlar arası klasör senkron çekirdeği.

Manifest tabanlı değişiklik algılama + çakışma çözümü (yeni kazanır).
Taşıma (push/pull) taşınabilir arayüzle ayrı katman; P2P/room üzerine kurulur.
"""
from __future__ import annotations

import hashlib
import os
from typing import Any

_IGNORE = {".DS_Store", "Thumbs.db", "desktop.ini"}


def scan_folder(root: str, *, ignore: set[str] | None = None) -> dict[str, dict[str, Any]]:
    """Klasör manifesti: {rel_path: {size, mtime, sha1}}. Gizli klasörler atlanır."""
    ig = ignore or _IGNORE
    man: dict[str, dict[str, Any]] = {}
    if not os.path.isdir(root):
        return man
    for dp, dn, fn in os.walk(root):
        dn[:] = [x for x in dn if not x.startswith(".")]
        for name in fn:
            if name in ig or name.startswith("._"):
                continue
            p = os.path.join(dp, name)
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            try:
                st = os.stat(p)
                man[rel] = {"size": st.st_size, "mtime": int(st.st_mtime), "sha1": _sha1(p)}
            except OSError:
                continue
    return man


def _sha1(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def diff(local: dict[str, dict[str, Any]], remote: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """İki manifest arası fark.

    to_push: yalnızca localde olan ya da local daha yeni.
    to_pull: yalnızca remote'ta olan ya da remote daha yeni.
    conflicts: iki taraf da değişmiş (mtime eşit ama hash farklı) -> çakışma.
    """
    to_push, to_pull, conflicts = [], [], []
    for k in sorted(set(local) | set(remote)):
        l, r = local.get(k), remote.get(k)
        if l is None:
            to_pull.append(k)
        elif r is None:
            to_push.append(k)
        elif l["sha1"] != r["sha1"]:
            if l["mtime"] > r["mtime"]:
                to_push.append(k)
            elif r["mtime"] > l["mtime"]:
                to_pull.append(k)
            else:
                conflicts.append(k)
    return {"to_push": to_push, "to_pull": to_pull, "conflicts": conflicts}


def resolve_conflicts(local: dict, remote: dict, conflicts: list[str], *, prefer: str = "newer") -> dict[str, str]:
    """Çakışma çözümü: {rel_path: 'local'|'remote'}. prefer: newer|local|remote."""
    out: dict[str, str] = {}
    for k in conflicts:
        l, r = local.get(k), remote.get(k)
        if prefer == "local":
            out[k] = "local"
        elif prefer == "remote":
            out[k] = "remote"
        else:
            out[k] = "local" if (l and r and l["mtime"] >= r["mtime"]) else "remote"
    return out


def sync_plan(local: dict, remote: dict, *, prefer: str = "newer") -> dict[str, Any]:
    """Tam senkron planı: push/pull listeleri + çözülmüş çakışmalar."""
    d = diff(local, remote)
    resolved = resolve_conflicts(local, remote, d["conflicts"], prefer=prefer)
    push = d["to_push"] + [k for k, v in resolved.items() if v == "local"]
    pull = d["to_pull"] + [k for k, v in resolved.items() if v == "remote"]
    return {"push": sorted(set(push)), "pull": sorted(set(pull)), "conflicts": resolved}
