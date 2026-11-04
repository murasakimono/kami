"""Windows Guvenlik Duvari: aria2c.exe'ye gelen baglanti izni (torrent eslerinin bize baglanabilmesi).

Kural eklemek yonetici ister -> kullanici Ayarlar'dan butona basinca UAC penceresi (runas) acilir.
Kontrol yonetici istemez.
"""
from __future__ import annotations

import ctypes
import logging
import os
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

RULE = "Kami aria2 (torrent)"
CREATE_NO_WINDOW = 0x08000000


def has_rule() -> bool:
    if os.name != "nt":
        return False
    try:
        r = subprocess.run(["netsh", "advfirewall", "firewall", "show", "rule", f"name={RULE}"],
                           capture_output=True, timeout=10, creationflags=CREATE_NO_WINDOW)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def request_rule(exe: Path) -> bool:
    """UAC ile netsh calistirir (kullanici onaylarsa kural eklenir). True: istem gosterildi."""
    if os.name != "nt":
        return False
    args = (f'advfirewall firewall add rule name="{RULE}" dir=in action=allow '
            f'program="{Path(exe).resolve()}" enable=yes profile=private,public')
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", "netsh", args, None, 0)
    log.info("Guvenlik duvari kurali istendi (ShellExecute %s)", rc)
    return rc > 32
