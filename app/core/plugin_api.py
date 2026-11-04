"""Eklenti sozlesmesi. Ayrintili rehber: docs/EKLENTI-REHBERI.md

Her eklenti plugins/<ad>/ klasorunde durur:

    plugins/<ad>/plugin.py     ->  def register(ctx: PluginContext) -> None
    plugins/<ad>/plugin.json   ->  TEK BILGI KAYNAGI (meta, URL desenleri, ayar semasi)

plugin.json:
    {"name", "version", "description", "author", "kami_min", "enabled",
     "kinds": ["cloud" | "resolver" | "engine" | "postprocessor" | "tab"],
     "url_patterns": [{"name", "host", "share", "personal", "examples": {"match": [...], "no_match": [...]}}],
     "settings": [{"key", "type": bool|int|str|choice|secret, "default", "label": {tr, en}, "help": {tr, en},
                   "choices": [...], "min", "max"}],
     "permissions": ["network", ...]}
url_patterns Kami'den tarayici eklentisine gider (extension/cloud_sites.js elle guncellenmez).
settings semasindan Ayarlar > Eklentiler otomatik cizilir; deger: ctx.setting("key"), gizli: ctx.secret("key").

Eklenti register() icinde ctx uzerinden su parcalari kaydeder:
  - Resolver:      bir sayfa/paylasim linkini gercek indirme isteklerine cevirir
  - Engine:        aria2 disinda bir indirme motoru
  - PostProcessor: indirme bitince calisir (etiket gomme, vokal ayirma ...)
  - Tab:           arayuzde kendi sekmesi (HTML dosyasi + Python API nesnesi)
  - CloudProvider: bulut paylasim linkini dosya agacina cevirir (app/core/cloud.py)
"""
from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from app.core.models import Download, DownloadRequest

if TYPE_CHECKING:
    from app.core.events import EventBus
    from app.core.settings import Settings


class Resolver(ABC):
    """URL -> bir ya da daha fazla DownloadRequest."""
    name: str = "resolver"
    priority: int = 100  # kucuk = once denenir

    @abstractmethod
    def can_handle(self, request: DownloadRequest) -> bool: ...

    @abstractmethod
    def resolve(self, request: DownloadRequest) -> list[DownloadRequest]: ...


class Engine(ABC):
    """Indirme motoru. Yerlesik motor: aria2."""
    name: str = "engine"

    @abstractmethod
    def can_handle(self, request: DownloadRequest) -> bool: ...

    @abstractmethod
    def start(self, download: Download) -> str:
        """Indirmeyi baslatir, motorun is kimligini (gid) dondurur."""

    @abstractmethod
    def pause(self, gid: str) -> None: ...

    @abstractmethod
    def resume(self, gid: str) -> None: ...

    @abstractmethod
    def remove(self, gid: str) -> None: ...

    @abstractmethod
    def status(self, gids: list[str]) -> dict[str, dict[str, Any]]:
        """gid -> {status, total, completed, speed, connections, error, path}"""

    def shutdown(self) -> None:  # pragma: no cover - istege bagli
        pass


class PostProcessor(ABC):
    name: str = "postprocessor"

    @abstractmethod
    def applies(self, download: Download) -> bool: ...

    @abstractmethod
    def process(self, download: Download) -> None: ...


@dataclass
class Tab:
    id: str
    title: dict[str, str]          # {"tr": "...", "en": "..."}
    html_path: Path                # sekme icerigi (HTML parcasi)
    api: Any = None                # JS'den pywebview.api.plugins.<id> olarak erisilir
    icon: str = ""


@dataclass
class PluginInfo:
    id: str
    name: str
    version: str = "0.0.0"
    description: str = ""
    path: Path | None = None
    enabled: bool = True
    error: str = ""
    resolvers: list[str] = field(default_factory=list)
    engines: list[str] = field(default_factory=list)
    postprocessors: list[str] = field(default_factory=list)
    tabs: list[str] = field(default_factory=list)
    clouds: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)            # plugin.json tamami
    objects: list[tuple[str, Any]] = field(default_factory=list)  # (registry listesi, nesne): kaldirma/yeniden yukleme

    @property
    def url_patterns(self) -> list[dict[str, Any]]:
        return [p for p in self.meta.get("url_patterns") or [] if isinstance(p, dict)]

    @property
    def settings_schema(self) -> list[dict[str, Any]]:
        return [x for x in self.meta.get("settings") or [] if isinstance(x, dict) and x.get("key")]


def _url_parts(url: str) -> tuple[str, str] | None:
    try:
        u = urlparse(url)
    except ValueError:
        return None
    if u.scheme not in ("http", "https"):
        return None
    tail = u.path + (("?" + u.query) if u.query else "") + (("#" + u.fragment) if u.fragment else "")
    return (u.hostname or "").lower(), tail


def match_patterns(url: str, patterns: list[dict[str, Any]]) -> tuple[str, str] | None:
    """plugin.json url_patterns ile eslesme -> (kind: share|personal, ad) ya da None.
    host: alan adi regex'i; share/personal: yol(+?sorgu)(+#parca) regex'i. Ikisi de re.search (JS'te RegExp.test)."""
    parts = _url_parts(url)
    if not parts:
        return None
    host, tail = parts
    for p in patterns:
        try:
            if not p.get("host") or not re.search(p["host"], host):
                continue
            if p.get("share") and re.search(p["share"], tail):
                return "share", p.get("name", "")
            if p.get("personal") and re.search(p["personal"], tail):
                return "personal", p.get("name", "")
        except re.error:
            continue
    return None


class PluginContext:
    """Eklentiye verilen nesne. Eklentiler cekirdege sadece bunun uzerinden dokunur."""

    def __init__(self, registry: "PluginRegistry", info: PluginInfo, events: "EventBus", settings: "Settings",
                 store: Any = None) -> None:
        self._registry = registry
        self.info = info
        self.events = events
        self.settings = settings          # Kami'nin genel ayarlari (salt okunur kullan)
        self.plugin_dir = info.path
        self._store = store               # plugin_loader.PluginStore (eklenti ayarlari + gizliler)
        self.log = logging.getLogger(f"kami_plugins.{info.id}")

    # ---- eklentinin kendi ayarlari (plugin.json "settings" semasi)
    def setting(self, key: str) -> Any:
        default = next((x.get("default") for x in self.info.settings_schema if x["key"] == key), None)
        if self._store is None:
            return default
        return self._store.value(self.info.id, key, default)

    def secret(self, key: str) -> str:
        return self._store.secret(self.info.id, key) if self._store is not None else ""

    @property
    def url_patterns(self) -> list[dict[str, Any]]:
        return self.info.url_patterns

    def matches(self, url: str) -> bool:
        """URL bu eklentinin plugin.json desenlerinden birine (paylasim) uyuyor mu?"""
        m = match_patterns(url, self.info.url_patterns)
        return bool(m and m[0] == "share")

    # ---- kayit (her nesne izlenir: Ayarlar > Eklentiler'den kapat / yeniden yukle)
    def _add(self, list_name: str, obj: Any, name: str, names: list[str]) -> None:
        getattr(self._registry, list_name).append(obj)
        self.info.objects.append((list_name, obj))
        names.append(name)

    def register_resolver(self, resolver: Resolver) -> None:
        self._add("resolvers", resolver, resolver.name, self.info.resolvers)
        self._registry.resolvers.sort(key=lambda r: r.priority)

    def register_engine(self, engine: Engine) -> None:
        self._add("engines", engine, engine.name, self.info.engines)

    def register_postprocessor(self, pp: PostProcessor) -> None:
        self._add("postprocessors", pp, pp.name, self.info.postprocessors)

    def register_tab(self, tab: Tab) -> None:
        self._add("tabs", tab, tab.id, self.info.tabs)

    def register_cloud(self, provider: Any) -> None:
        """provider: app.core.cloud.CloudProvider. hosts bossa plugin.json url_patterns ile eslesir."""
        if not getattr(provider, "hosts", None) and self.info.url_patterns:
            provider.patterns = self.info.url_patterns
        self._add("clouds", provider, provider.name, self.info.clouds)


@dataclass
class PluginRegistry:
    resolvers: list[Resolver] = field(default_factory=list)
    engines: list[Engine] = field(default_factory=list)
    postprocessors: list[PostProcessor] = field(default_factory=list)
    tabs: list[Tab] = field(default_factory=list)
    clouds: list[Any] = field(default_factory=list)
    plugins: list[PluginInfo] = field(default_factory=list)
    store: Any = None             # plugin_loader.PluginStore
    ctx: Any = None               # (events, settings): yeniden yukleme icin

    def url_patterns(self) -> list[dict[str, Any]]:
        """Acik eklentilerin desenleri (tarayici eklentisine gider); 'examples' alani gonderilmez."""
        out = []
        for p in self.plugins:
            if p.enabled and not p.error:
                for pat in p.url_patterns:
                    out.append({k: v for k, v in pat.items() if k in ("name", "host", "share", "personal")}
                               | {"plugin": p.id})
        return out
