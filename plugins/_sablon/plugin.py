"""__NAME__ eklentisi (sablondan uretildi: uv run python -m tools.yeni_eklenti __ID__).

Rehber: docs/EKLENTI-REHBERI.md. Sadece bu klasor + plugin.json yeterli; Kami'nin geri kalanina dokunma.
URL desenleri plugin.json "url_patterns"tadir (Kami bunlari tarayici eklentisine de yollar).
"""
from __future__ import annotations

from app.core.cloud import CloudError, CloudFile, CloudListing, CloudProvider, get_json, session


class __CLASS__(CloudProvider):
    name = "__ID__"
    # hosts bos: eslesme plugin.json url_patterns ile yapilir (ctx.register_cloud bunu baglar)

    def __init__(self, ctx) -> None:
        self.ctx = ctx

    def list(self, url: str) -> CloudListing:
        """Paylasim linki -> dosya listesi. Her CloudFile icin dogrudan indirme linki (url) ya da ref."""
        s = session()
        key = self.ctx.secret("api_key")            # gizli ayar (DPAPI)
        if self.ctx.setting("use_api"):              # normal ayar
            # ORNEK: data = get_json(s, f"https://api.ornek.com/share?url={url}", headers={...})
            pass
        _ = (s, key, get_json)
        raise CloudError("cloud_failed", "sablon: list() henuz yazilmadi")
        # return CloudListing(self.name, "Paylasim adi", [CloudFile("klasor/dosya.zip", 1234, url="https://...")])


def register(ctx) -> None:
    ctx.register_cloud(__CLASS__(ctx))
