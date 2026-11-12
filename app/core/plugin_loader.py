"""plugins/ klasorundeki eklentileri bulur, dogrular ve yukler. Bozuk eklenti uygulamayi dusurmez.

- Ac/kapat ve eklenti ayarlari data/plugins.json'da (PluginStore); plugin.json'daki "enabled" varsayilandir.
- Gizli ayarlar (type: secret) DPAPI ile data/plugin_secrets/<id>.<key>.bin.
- reload_plugin(): eklentinin kaydettigi nesneler kayittan cikarilir, modul yeniden calistirilir.
"""
from __future__ import annotations

import importlib.util
import json
import logging
import re
import sys
import threading
import types
from pathlib import Path
from typing import Any

from app.core.events import EventBus
from app.core.plugin_api import PluginContext, PluginInfo, PluginRegistry, match_patterns
from app.core.settings import Settings

log = logging.getLogger(__name__)

KINDS = {"cloud", "resolver", "engine", "postprocessor", "tab"}
SETTING_TYPES = {"bool", "int", "str", "choice", "secret"}
ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


class PluginStore:
    """data/plugins.json: {"disabled": [...], "enabled": [...], "values": {id: {key: value}}}"""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {"disabled": [], "enabled": [], "values": {}}
        if path and path.is_file():
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(d, dict):
                    self._data.update({k: d[k] for k in ("disabled", "enabled", "values") if k in d})
            except Exception:
                log.warning("plugins.json okunamadi")

    def _save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def is_enabled(self, pid: str, default: bool) -> bool:
        if pid in self._data["disabled"]:
            return False
        if pid in self._data["enabled"]:
            return True
        return default

    def set_enabled(self, pid: str, on: bool) -> None:
        with self._lock:
            for k in ("disabled", "enabled"):
                if pid in self._data[k]:
                    self._data[k].remove(pid)
            self._data["enabled" if on else "disabled"].append(pid)
            self._save()

    def value(self, pid: str, key: str, default: Any = None) -> Any:
        return (self._data["values"].get(pid) or {}).get(key, default)

    def set_value(self, pid: str, key: str, value: Any) -> None:
        with self._lock:
            self._data["values"].setdefault(pid, {})[key] = value
            self._save()

    def _secret_store(self, pid: str, key: str):
        from app.core.debrid import TokenStore
        base = self.path.parent if self.path else Path(".")
        return TokenStore(base / "plugin_secrets" / f"{pid}.{key}.bin")

    def secret(self, pid: str, key: str) -> str:
        return self._secret_store(pid, key).load() if self.path else ""

    def set_secret(self, pid: str, key: str, value: str) -> None:
        st = self._secret_store(pid, key)
        st.save(value) if value else st.clear()


def validate_meta(meta: dict[str, Any], folder_name: str = "") -> list[str]:
    """plugin.json denetimi -> hata listesi (bos = gecerli). Eklenti test komutu ve yukleyici kullanir."""
    errs: list[str] = []
    if folder_name and not ID_RE.match(folder_name):
        errs.append(f"klasor adi '{folder_name}' kucuk harf/rakam/_ olmali (ornek: ornek_site)")
    for k in ("name", "version"):
        if not isinstance(meta.get(k), str) or not meta.get(k):
            errs.append(f"'{k}' zorunlu (metin)")
    if meta.get("version") and not re.match(r"^\d+\.\d+\.\d+$", str(meta["version"])):
        errs.append("'version' 1.2.3 biciminde olmali")
    for k in meta.get("kinds") or []:
        if k not in KINDS:
            errs.append(f"bilinmeyen kind: {k} (olasi: {sorted(KINDS)})")
    for i, p in enumerate(meta.get("url_patterns") or []):
        if not isinstance(p, dict) or not p.get("host") or not (p.get("share") or p.get("personal")):
            errs.append(f"url_patterns[{i}]: 'host' ve 'share' (ya da 'personal') zorunlu")
            continue
        for f in ("host", "share", "personal"):
            if p.get(f):
                try:
                    re.compile(p[f])
                except re.error as exc:
                    errs.append(f"url_patterns[{i}].{f} gecersiz regex: {exc}")
                if "(?P<" in p[f] or "(?<" in p[f] or "(?i)" in p[f]:
                    errs.append(f"url_patterns[{i}].{f}: JS uyumu icin adli grup/satir ici bayrak kullanma")
        ex = p.get("examples") or {}
        for u in ex.get("match") or []:
            m = match_patterns(u, [p])
            if not m or m[0] != "share":
                errs.append(f"url_patterns[{i}]: ornek eslesmedi: {u}")
        for u in ex.get("no_match") or []:
            m = match_patterns(u, [p])
            if m and m[0] == "share":
                errs.append(f"url_patterns[{i}]: eslesmemesi gereken ornek eslesti: {u}")
    keys = set()
    for i, st in enumerate(meta.get("settings") or []):
        if not isinstance(st, dict) or not st.get("key"):
            errs.append(f"settings[{i}]: 'key' zorunlu")
            continue
        if st["key"] in keys:
            errs.append(f"settings[{i}]: tekrar eden key {st['key']}")
        keys.add(st["key"])
        t = st.get("type", "str")
        if t not in SETTING_TYPES:
            errs.append(f"settings[{i}]: type {t} (olasi: {sorted(SETTING_TYPES)})")
        if t == "choice" and not st.get("choices"):
            errs.append(f"settings[{i}]: choice icin 'choices' listesi zorunlu")
        if not isinstance(st.get("label"), (dict, str)):
            errs.append(f"settings[{i}]: 'label' zorunlu ({{\"tr\": ..., \"en\": ...}})")
    return errs


def coerce_setting(schema: dict[str, Any], value: Any) -> Any:
    t = schema.get("type", "str")
    if t == "bool":
        return bool(value)
    if t == "int":
        v = int(value)
        if schema.get("min") is not None:
            v = max(int(schema["min"]), v)
        if schema.get("max") is not None:
            v = min(int(schema["max"]), v)
        return v
    if t == "choice":
        if str(value) not in [str(c) for c in schema.get("choices") or []]:
            raise ValueError("choice")
        return str(value)
    return str(value)[:2000]


def _ensure_parent(plugins_dir: Path) -> None:
    # Eklentiler 'kami_plugins.<ad>' paketi olarak yuklenir; boylece kendi icinde 'from . import x' calisir.
    if "kami_plugins" not in sys.modules:
        parent = types.ModuleType("kami_plugins")
        parent.__path__ = [str(plugins_dir)]
        sys.modules["kami_plugins"] = parent


def _read_meta(folder: Path) -> dict:
    meta_file = folder / "plugin.json"
    if meta_file.is_file():
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            log.warning("plugin.json okunamadi: %s (%s)", meta_file, exc)
            return {"_error": f"plugin.json okunamadi: {exc}"}
    return {}


def _activate(info: PluginInfo, registry: PluginRegistry, events: EventBus, settings: Settings,
              store: PluginStore | None) -> None:
    folder = info.path
    assert folder is not None
    try:
        if info.meta.get("_error"):
            raise ValueError(info.meta["_error"])
        module_name = f"kami_plugins.{folder.name}"
        for m in [m for m in sys.modules if m == module_name or m.startswith(module_name + ".")]:
            del sys.modules[m]   # yeniden yukleme: alt moduller dahil temiz
        # ayni saniyede ayni boyutta degisen dosyada eski .pyc kullanilmasin
        import shutil
        shutil.rmtree(folder / "__pycache__", ignore_errors=True)
        importlib.invalidate_caches()
        spec = importlib.util.spec_from_file_location(
            module_name, folder / "plugin.py", submodule_search_locations=[str(folder)])
        if spec is None or spec.loader is None:
            raise ImportError("spec olusturulamadi")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        register = getattr(module, "register", None)
        if not callable(register):
            raise AttributeError("plugin.py icinde register(ctx) yok")
        register(PluginContext(registry, info, events, settings, store))
        info.error = ""
        log.info("Eklenti yuklendi: %s %s", info.id, info.version)
    except Exception as exc:  # bozuk eklenti digerlerini etkilemesin
        deactivate(info, registry)
        info.error = f"{type(exc).__name__}: {exc}"
        log.exception("Eklenti yuklenemedi: %s", folder.name)


def deactivate(info: PluginInfo, registry: PluginRegistry) -> None:
    """Eklentinin kaydettigi tum nesneleri kayittan cikar (kapat / yeniden yukle)."""
    for list_name, obj in info.objects:
        lst = getattr(registry, list_name)
        for i, x in enumerate(lst):
            if x is obj:
                del lst[i]
                break
    info.objects.clear()
    for k in ("resolvers", "engines", "postprocessors", "tabs", "clouds"):
        getattr(info, k).clear()


def load_plugins(plugins_dir: Path, events: EventBus, settings: Settings,
                 registry: PluginRegistry | None = None, store: PluginStore | None = None) -> PluginRegistry:
    registry = registry or PluginRegistry()
    if not plugins_dir.is_dir():
        return registry
    _ensure_parent(plugins_dir)
    registry.store = store
    registry.ctx = (events, settings)
    for folder in sorted(p for p in plugins_dir.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))):
        if not (folder / "plugin.py").is_file():
            continue
        meta = _read_meta(folder)
        info = PluginInfo(
            id=folder.name,
            name=meta.get("name", folder.name),
            version=str(meta.get("version", "0.0.0")),
            description=meta.get("description", ""),
            path=folder,
            enabled=store.is_enabled(folder.name, bool(meta.get("enabled", True))) if store
            else bool(meta.get("enabled", True)),
            meta=meta,
        )
        registry.plugins.append(info)
        if info.enabled:
            _activate(info, registry, events, settings, store)
    return registry


def set_enabled(registry: PluginRegistry, pid: str, on: bool) -> PluginInfo | None:
    info = next((p for p in registry.plugins if p.id == pid), None)
    if info is None:
        return None
    store = getattr(registry, "store", None)
    if store is not None:
        store.set_enabled(pid, on)
    info.enabled = on
    if on and not info.objects:
        events, settings = registry.ctx
        _activate(info, registry, events, settings, store)
    elif not on:
        deactivate(info, registry)
        info.error = ""
    return info


def reload_plugin(registry: PluginRegistry, pid: str) -> PluginInfo | None:
    """plugin.json + plugin.py diskten yeniden okunur (Kami'yi kapatmadan)."""
    info = next((p for p in registry.plugins if p.id == pid), None)
    if info is None or info.path is None:
        return None
    deactivate(info, registry)
    meta = _read_meta(info.path)
    info.meta, info.name = meta, meta.get("name", info.id)
    info.version, info.description = str(meta.get("version", "0.0.0")), meta.get("description", "")
    info.error = ""
    if info.enabled:
        events, settings = registry.ctx
        _activate(info, registry, events, settings, getattr(registry, "store", None))
    return info
