"""Kurulum / kaldirma isleri (Inno Setup cagirir):  Kami.exe --setup register | unregister

register:   native host (Brave + Chrome + Edge, HKCU) -> <kurulum>\\kami_host.exe; magnet: isleyicisi -> Kami.exe
unregister: ikisini de kaldirir (sadece bizim kayitlarimiz; magnet baska programa aitse dokunulmaz).
Ayarlar ve gecmis (%LOCALAPPDATA%\\Kami\\data) SILINMEZ.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import sys
import winreg
from pathlib import Path

from app import paths

log = logging.getLogger(__name__)

HOST_NAME = "com.metehan.kami"
REG_PATHS = {
    "Brave": rf"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\{HOST_NAME}",
    "Chrome": rf"Software\Google\Chrome\NativeMessagingHosts\{HOST_NAME}",
    "Edge": rf"Software\Microsoft\Edge\NativeMessagingHosts\{HOST_NAME}",
}
MAGNET = r"Software\Classes\magnet"


def extension_id(manifest: Path | None = None) -> str:
    m = json.loads((manifest or paths.ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(base64.b64decode(m["key"])).hexdigest()[:32]
    return "".join(chr(ord("a") + int(c, 16)) for c in digest)


def host_manifest_path() -> Path:
    return paths.USER_DIR / f"{HOST_NAME}.json"


def register(exe_dir: Path | None = None) -> list[str]:
    exe_dir = exe_dir or paths.ROOT
    done = []
    host_exe = exe_dir / "kami_host.exe"
    manifest = {"name": HOST_NAME, "description": "Kami Download Manager", "path": str(host_exe),
                "type": "stdio", "allowed_origins": [f"chrome-extension://{extension_id(exe_dir / 'extension' / 'manifest.json')}/"]}
    mp = host_manifest_path()
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    for browser, sub in REG_PATHS.items():
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, sub) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, str(mp))
        done.append(f"native host: {browser}")
    kami = str(exe_dir / "Kami.exe")
    vals = [(MAGNET, "", "URL:Magnet Protocol"), (MAGNET, "URL Protocol", ""),
            (MAGNET + r"\DefaultIcon", "", f'"{kami}",0'),
            (MAGNET + r"\shell\open", "FriendlyAppName", "Kami"),
            (MAGNET + r"\shell\open\command", "", f'"{kami}" --magnet "%1"')]
    for sub, name, val in vals:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, sub) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, val)
    done.append("magnet: Kami")
    return done


def _delete_tree(root, sub: str) -> None:
    try:
        with winreg.OpenKey(root, sub, 0, winreg.KEY_ALL_ACCESS) as k:
            while True:
                try:
                    child = winreg.EnumKey(k, 0)
                except OSError:
                    break
                _delete_tree(root, sub + "\\" + child)
        winreg.DeleteKey(root, sub)
    except FileNotFoundError:
        pass


def _magnet_is_ours() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, MAGNET + r"\shell\open\command") as k:
            val, _ = winreg.QueryValueEx(k, "")
        return "kami" in str(val).lower()
    except FileNotFoundError:
        return False


def unregister() -> list[str]:
    done = []
    for browser, sub in REG_PATHS.items():
        _delete_tree(winreg.HKEY_CURRENT_USER, sub)
        done.append(f"native host kaldirildi: {browser}")
    try:
        host_manifest_path().unlink()
    except OSError:
        pass
    if _magnet_is_ours():
        _delete_tree(winreg.HKEY_CURRENT_USER, MAGNET)
        done.append("magnet kaldirildi")
    return done


def run(argv: list[str]) -> int:
    """main'den: --setup register|unregister. Sonuc data/setup.log'a."""
    action = argv[argv.index("--setup") + 1] if "--setup" in argv and argv.index("--setup") + 1 < len(argv) else ""
    try:
        res = register() if action == "register" else unregister() if action == "unregister" else ["?"]
        log.info("Kurulum isi %s: %s", action, res)
        return 0
    except Exception:
        log.exception("Kurulum isi basarisiz: %s", action)
        return 1


if __name__ == "__main__":   # gelistirme: python -m app.core.setup_tasks --setup register
    sys.exit(run(sys.argv))
