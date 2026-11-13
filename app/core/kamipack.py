"""Faz 18.3 — .kamipack Guvenli Recete & Akis Paketi (imzali/SHA-256 dogrulamali)."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

PACK_FORMAT = "kamipack/v1"
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024  # 50 MB
BLOCKED_EXTENSIONS = {
    ".py", ".pyc", ".pyo", ".bat", ".cmd", ".ps1", ".psm1",
    ".exe", ".dll", ".so", ".dylib", ".msi", ".vbs", ".vbe",
    ".js", ".mjs", ".cjs", ".sh", ".bash", ".zsh", ".jar",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_safe_member(name: str) -> tuple[bool, str]:
    if not name or name.startswith("/") or name.startswith("\\") or ":" in name:
        return False, f"Gecersiz arsiv yolu: {name}"
    p = PurePosixPath(name.replace("\\", "/"))
    if ".." in p.parts:
        return False, f"Dizin atlama engellendi: {name}"
    if p.suffix.lower() in BLOCKED_EXTENSIONS:
        return False, f"Guvenlik nedeniyle engellenen uzanti ({p.suffix}): {name}"
    return True, ""


def export_kamipack(
    name: str,
    payload: dict[str, Any],
    out_path: str | Path,
    *,
    kind: str = "workflow",
    author: str = "",
    description: str = "",
    assets: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Recete veya akis grafini SHA-256 manifestli guvenli .kamipack arsivine yazar."""
    dst = Path(out_path)
    if dst.suffix.lower() != ".kamipack":
        dst = dst.with_suffix(".kamipack")
    dst.parent.mkdir(parents=True, exist_ok=True)

    payload_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    hashes: dict[str, str] = {"payload.json": _sha256_bytes(payload_bytes)}
    asset_blobs: list[tuple[str, bytes]] = []

    for rel_name, src_file in (assets or {}).items():
        ok, err = _is_safe_member(rel_name)
        if not ok:
            return {"ok": False, "error": err}
        sp = Path(src_file)
        if not sp.is_file():
            return {"ok": False, "error": f"Ek dosya bulunamadi: {sp}"}
        raw = sp.read_bytes()
        arc_name = f"assets/{PurePosixPath(rel_name.replace(chr(92), '/')).name}"
        hashes[arc_name] = _sha256_bytes(raw)
        asset_blobs.append((arc_name, raw))

    manifest = {
        "format": PACK_FORMAT,
        "name": (name or "kami-pack").strip(),
        "kind": kind,
        "author": author,
        "description": description,
        "sha256": hashes,
    }
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")

    with zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", manifest_bytes)
        zf.writestr("payload.json", payload_bytes)
        for arc_name, raw in asset_blobs:
            zf.writestr(arc_name, raw)

    return {"ok": True, "path": str(dst), "manifest": manifest}


def inspect_kamipack(pack_path: str | Path) -> dict[str, Any]:
    """Bir .kamipack dosyasini guvenlik ve SHA-256 butunlugu acisindan dogrular."""
    src = Path(pack_path)
    if not src.is_file():
        return {"ok": False, "error": "Paket dosyasi bulunamadi"}

    try:
        with zipfile.ZipFile(src, "r") as zf:
            infos = zf.infolist()
            total_size = sum(i.file_size for i in infos)
            if total_size > MAX_UNCOMPRESSED_BYTES:
                return {"ok": False, "error": "Paket acilmis boyutu siniri asiyor"}

            names = {i.filename for i in infos}
            for info in infos:
                if info.is_dir():
                    continue
                ok, err = _is_safe_member(info.filename)
                if not ok:
                    return {"ok": False, "error": err}

            if "manifest.json" not in names or "payload.json" not in names:
                return {"ok": False, "error": "Eksik manifest.json veya payload.json"}

            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            if manifest.get("format") != PACK_FORMAT:
                return {"ok": False, "error": f"Desteklenmeyen format: {manifest.get('format')}"}

            expected_hashes = manifest.get("sha256") or {}
            for member, expected in expected_hashes.items():
                if member not in names:
                    return {"ok": False, "error": f"Manifestte yer alan dosya arsivde yok: {member}"}
                actual = _sha256_bytes(zf.read(member))
                if actual != expected:
                    return {"ok": False, "error": f"SHA-256 butunluk hatasi: {member}"}

            payload = json.loads(zf.read("payload.json").decode("utf-8"))
            return {"ok": True, "manifest": manifest, "payload": payload}
    except zipfile.BadZipFile:
        return {"ok": False, "error": "Bozuk .kamipack arsivi"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def import_kamipack(pack_path: str | Path, dest_dir: str | Path | None = None) -> dict[str, Any]:
    """Dogrulanmis .kamipack paketini iceri aktarir (varsa guvenli assetleri cikarir)."""
    res = inspect_kamipack(pack_path)
    if not res.get("ok"):
        return res

    extracted: list[str] = []
    if dest_dir:
        out_root = Path(dest_dir).resolve()
        out_root.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(pack_path, "r") as zf:
            for info in zf.infolist():
                if info.is_dir() or not info.filename.startswith("assets/"):
                    continue
                target = (out_root / info.filename).resolve()
                if not str(target).startswith(str(out_root)):
                    return {"ok": False, "error": f"Guvenli olmayan cikarma yolu: {info.filename}"}
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(info.filename))
                extracted.append(str(target))

    return {
        "ok": True,
        "manifest": res["manifest"],
        "payload": res["payload"],
        "extracted_assets": extracted,
    }
