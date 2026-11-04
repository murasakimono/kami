"""Ag yardimcilari.

IPv6 sorunu (04.11 olculdu): bu agda AAAA kaydi donuyor ama IPv6 baglantisi yok. Windows her IPv6 adresine
~21 sn TCP zaman asimi bekliyor -> api.real-debrid.com (2 IPv6 adresi) = 42 sn bekleme, sonra IPv4 0.05 sn.
Cozum: surec icinde getaddrinfo sonucunu IPv4 once siralar (IPv6 yine denenir, sadece sonra). IPv6 hic
calismiyorsa aria2'ye --disable-ipv6 verilir (ipv6_works ile olculur).
"""
from __future__ import annotations

import logging
import socket

log = logging.getLogger(__name__)

_orig_getaddrinfo = socket.getaddrinfo
_patched = False


def _v4_first(*args, **kwargs):
    res = _orig_getaddrinfo(*args, **kwargs)
    # kararli siralama: IPv4 adresleri basa, kendi aralarindaki sira korunur
    return sorted(res, key=lambda r: 0 if r[0] == socket.AF_INET else 1)


def prefer_ipv4() -> None:
    global _patched
    if not _patched:
        socket.getaddrinfo = _v4_first
        _patched = True


def ipv6_works(timeout: float = 1.5) -> bool:
    """Genel bir IPv6 adresine (Cloudflare DNS, 443) kisa baglanti denemesi. Ag yoksa ya da IPv6 yoksa False."""
    for addr in ("2606:4700:4700::1111", "2001:4860:4860::8888"):
        s = None
        try:
            s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((addr, 443))
            return True
        except OSError:
            continue
        finally:
            if s is not None:
                s.close()
    return False
