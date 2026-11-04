"""Kami native host kaydi (Brave + Chrome + Edge, sadece HKCU).

  python native_host/install.py            -> kaydet
  python native_host/install.py --remove   -> kaldir
  python native_host/install.py --check    -> durumu yazdir
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import winreg
from pathlib import Path

HOST_NAME = "com.metehan.kami"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MANIFEST_OUT = HERE / f"{HOST_NAME}.json"
LAUNCHER = HERE / "kami_host.bat"
EXT_MANIFEST = ROOT / "extension" / "manifest.json"

REG_PATHS = {
    "Brave": rf"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\{HOST_NAME}",
    "Chrome": rf"Software\Google\Chrome\NativeMessagingHosts\{HOST_NAME}",
    "Edge": rf"Software\Microsoft\Edge\NativeMessagingHosts\{HOST_NAME}",
}


def extension_id_from_key(key_b64: str) -> str:
    """Chromium eklenti ID'si: genel anahtarin (DER) SHA-256'sinin ilk 32 hex hanesi, 0-f -> a-p."""
    digest = hashlib.sha256(base64.b64decode(key_b64)).hexdigest()[:32]
    return "".join(chr(ord("a") + int(c, 16)) for c in digest)


def extension_id() -> str:
    manifest = json.loads(EXT_MANIFEST.read_text(encoding="utf-8"))
    return extension_id_from_key(manifest["key"])


def install() -> None:
    ext_id = extension_id()
    host_manifest = {
        "name": HOST_NAME,
        "description": "Kami Download Manager",
        "path": str(LAUNCHER),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{ext_id}/"],
    }
    MANIFEST_OUT.write_text(json.dumps(host_manifest, indent=2), encoding="utf-8")
    for browser, sub in REG_PATHS.items():
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, sub) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, str(MANIFEST_OUT))
        print(f"  {browser}: kaydedildi")
    print(f"Eklenti ID: {ext_id}")
    print(f"Host manifest: {MANIFEST_OUT}")


def remove() -> None:
    for browser, sub in REG_PATHS.items():
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
            print(f"  {browser}: kaldirildi")
        except FileNotFoundError:
            print(f"  {browser}: zaten yok")


def check() -> int:
    ok = True
    for browser, sub in REG_PATHS.items():
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub) as k:
                val, _ = winreg.QueryValueEx(k, "")
            exists = Path(val).is_file()
            print(f"  {browser}: {val} {'(var)' if exists else '(DOSYA YOK)'}")
            ok &= exists
        except FileNotFoundError:
            print(f"  {browser}: kayit yok")
            ok = False
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.remove:
        remove()
        return 0
    if a.check:
        return check()
    install()
    return 0


if __name__ == "__main__":
    sys.exit(main())
