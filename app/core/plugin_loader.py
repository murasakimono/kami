"""plugins/ klasorundeki eklentileri bulur ve yukler. Bozuk eklenti uygulamayi dusurmez."""
from __future__ import annotations

import importlib.util
import json
import logging
import sys
import types
from pathlib import Path

from app.core.events import EventBus
from app.core.plugin_api import PluginContext, PluginInfo, PluginRegistry
from app.core.settings import Settings

log = logging.getLogger(__name__)


def load_plugins(plugins_dir: Path, events: EventBus, settings: Settings,
                 registry: PluginRegistry | None = None) -> PluginRegistry:
    registry = registry or PluginRegistry()
    if not plugins_dir.is_dir():
        return registry
    # Eklentiler 'kami_plugins.<ad>' paketi olarak yuklenir; boylece kendi icinde 'from . import x' calisir.
    if "kami_plugins" not in sys.modules:
        parent = types.ModuleType("kami_plugins")
        parent.__path__ = [str(plugins_dir)]  # type: ignore[attr-defined]
        sys.modules["kami_plugins"] = parent

    for folder in sorted(p for p in plugins_dir.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))):
        entry = folder / "plugin.py"
        if not entry.is_file():
            continue
        meta = _read_meta(folder)
        info = PluginInfo(
            id=folder.name,
            name=meta.get("name", folder.name),
            version=str(meta.get("version", "0.0.0")),
            description=meta.get("description", ""),
            path=folder,
            enabled=bool(meta.get("enabled", True)),
        )
        registry.plugins.append(info)
        if not info.enabled:
            continue
        try:
            module_name = f"kami_plugins.{folder.name}"
            spec = importlib.util.spec_from_file_location(
                module_name, entry, submodule_search_locations=[str(folder)])
            if spec is None or spec.loader is None:
                raise ImportError("spec olusturulamadi")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            register = getattr(module, "register", None)
            if not callable(register):
                raise AttributeError("plugin.py icinde register(ctx) yok")
            register(PluginContext(registry, info, events, settings))
            log.info("Eklenti yuklendi: %s %s", info.id, info.version)
        except Exception as exc:  # bozuk eklenti digerlerini etkilemesin
            info.error = f"{type(exc).__name__}: {exc}"
            log.exception("Eklenti yuklenemedi: %s", folder.name)
    return registry


def _read_meta(folder: Path) -> dict:
    meta_file = folder / "plugin.json"
    if meta_file.is_file():
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            log.warning("plugin.json okunamadi: %s", meta_file)
    return {}
