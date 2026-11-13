"""Kami Bypass eklentisi: Resolver onceligi 40 ile ara linkleri hedefe cevirir."""
from __future__ import annotations

from dataclasses import replace

from app.core import bypass
from app.core.manager import CaptureRejected
from app.core.models import DownloadRequest
from app.core.plugin_api import Resolver


class BypassResolver(Resolver):
    name = "bypass"
    priority = 40

    def can_handle(self, request: DownloadRequest) -> bool:
        return bypass.is_bypassable(request.url)

    def resolve(self, request: DownloadRequest) -> list[DownloadRequest]:
        res = bypass.resolve(request.url)
        target = res.get("url") or ""
        if not res.get("ok") or not target or target == request.url or bypass.is_bypassable(target):
            err = res.get("error") or "cozulemedi"
            raise CaptureRejected(f"bypass_failed:{err}")
        return [replace(request, url=target, page_url=request.page_url or request.url)]


def register(ctx) -> None:
    ctx.register_resolver(BypassResolver())
