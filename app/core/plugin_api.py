"""Eklenti sozlesmesi.

Her eklenti plugins/<ad>/ klasorunde durur ve en az su dosyayi icerir:

    plugins/<ad>/plugin.py   ->  def register(ctx: PluginContext) -> None

Istege bagli plugins/<ad>/plugin.json:
    {"name": "...", "version": "0.1.0", "description": "...", "enabled": true}

Eklenti register() icinde ctx uzerinden su parcalari kaydeder:
  - Resolver:      bir sayfa/paylasim linkini gercek indirme isteklerine cevirir (YouTube, Yandex Disk ...)
  - Engine:        aria2 disinda bir indirme motoru (yt-dlp, torrent ...)
  - PostProcessor: indirme bitince calisir (etiket gomme, vokal ayirma ...)
  - Tab:           arayuzde kendi sekmesi (HTML dosyasi + Python API nesnesi)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

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


class PluginContext:
    """Eklentiye verilen nesne. Eklentiler cekirdege sadece bunun uzerinden dokunur."""

    def __init__(self, registry: "PluginRegistry", info: PluginInfo, events: "EventBus", settings: "Settings") -> None:
        self._registry = registry
        self.info = info
        self.events = events
        self.settings = settings
        self.plugin_dir = info.path

    def register_resolver(self, resolver: Resolver) -> None:
        self._registry.resolvers.append(resolver)
        self._registry.resolvers.sort(key=lambda r: r.priority)
        self.info.resolvers.append(resolver.name)

    def register_engine(self, engine: Engine) -> None:
        self._registry.engines.append(engine)
        self.info.engines.append(engine.name)

    def register_postprocessor(self, pp: PostProcessor) -> None:
        self._registry.postprocessors.append(pp)
        self.info.postprocessors.append(pp.name)

    def register_tab(self, tab: Tab) -> None:
        self._registry.tabs.append(tab)
        self.info.tabs.append(tab.id)


@dataclass
class PluginRegistry:
    resolvers: list[Resolver] = field(default_factory=list)
    engines: list[Engine] = field(default_factory=list)
    postprocessors: list[PostProcessor] = field(default_factory=list)
    tabs: list[Tab] = field(default_factory=list)
    plugins: list[PluginInfo] = field(default_factory=list)
