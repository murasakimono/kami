"""Coklu profil izolasyonu (Kisisel / Icerik Uretimi / Magaza-Is + ozel profiller).

Her profil kendi indirme alt klasoru, vurgu rengi (accent_theme) ve calisma alani
meta verisini izole eder; mevcut settings.json varsayilanlarini bozmaz.
"""
from __future__ import annotations

import copy
import json
import logging
import re
import threading
from pathlib import Path
from typing import Any

from app import paths

log = logging.getLogger(__name__)

BUILTIN_PROFILES: dict[str, dict[str, Any]] = {
    "kisisel": {
        "id": "kisisel",
        "name": "Kişisel",
        "accent_theme": "mor",
        "download_subfolder": "",
        "builtin": True,
        "badge": "K",
    },
    "icerik": {
        "id": "icerik",
        "name": "İçerik Üretimi",
        "accent_theme": "kizil",
        "download_subfolder": "İçerik Üretimi",
        "builtin": True,
        "badge": "İ",
    },
    "magaza": {
        "id": "magaza",
        "name": "Mağaza-İş",
        "accent_theme": "altin",
        "download_subfolder": "Mağaza-İş",
        "builtin": True,
        "badge": "M",
    },
}

_SAFE_ID_RE = re.compile(r"[^a-z0-9_-]+")
_VALID_ACCENTS = frozenset({"mor", "kizil", "buz", "altin", "gece"})


def _slugify(name: str) -> str:
    tr_map = str.maketrans("çğıöşüÇĞİÖŞÜ ", "cgiosucgiosu-")
    s = name.translate(tr_map).lower().strip("-")
    s = _SAFE_ID_RE.sub("-", s).strip("-")
    return s or "profil"


class ProfileStore:
    """Profil listesi, aktif profil ve profil bazli indirme klasoru cozumleme."""

    def __init__(self, path: Path | None = None, settings=None) -> None:
        self.path = path or (paths.DATA_DIR / "profiles.json")
        self.settings = settings
        self._lock = threading.RLock()
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        profiles = copy.deepcopy(BUILTIN_PROFILES)
        active = "kisisel"
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    for pid, pdata in (raw.get("profiles") or {}).items():
                        if isinstance(pdata, dict) and pid:
                            base = copy.deepcopy(BUILTIN_PROFILES.get(pid, {}))
                            merged = {**base, **pdata, "id": pid}
                            if pid in BUILTIN_PROFILES:
                                merged["builtin"] = True
                            profiles[pid] = merged
                    if raw.get("active") in profiles:
                        active = str(raw["active"])
            except (OSError, json.JSONDecodeError):
                log.warning("profiles.json okunamadi, varsayilan kullaniliyor", exc_info=True)
        if self.settings is not None:
            s_active = self.settings.get("active_profile")
            if isinstance(s_active, str) and s_active in profiles:
                active = s_active
        return {"active": active, "profiles": profiles}

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            log.warning("profiles.json yazilamadi", exc_info=True)

    def list_profiles(self) -> list[dict[str, Any]]:
        with self._lock:
            active = self._data["active"]
            out = []
            for pid, p in self._data["profiles"].items():
                item = copy.deepcopy(p)
                item["active"] = pid == active
                out.append(item)
            return out

    def active_id(self) -> str:
        with self._lock:
            return str(self._data["active"])

    def active_profile(self) -> dict[str, Any]:
        with self._lock:
            pid = self._data["active"]
            p = copy.deepcopy(self._data["profiles"].get(pid) or BUILTIN_PROFILES["kisisel"])
            p["active"] = True
            return p

    def switch_profile(self, profile_id: str) -> dict[str, Any]:
        with self._lock:
            pid = str(profile_id or "").strip()
            if pid not in self._data["profiles"]:
                raise KeyError(f"Profil bulunamadi: {pid}")
            self._data["active"] = pid
            prof = copy.deepcopy(self._data["profiles"][pid])
            self._save()
            if self.settings is not None:
                self.settings.set("active_profile", pid)
                self.settings.set("accent_theme", prof.get("accent_theme", "mor"))
            prof["active"] = True
            return prof

    def create_profile(self, name: str, accent_theme: str = "mor", download_subfolder: str | None = None) -> dict[str, Any]:
        with self._lock:
            clean_name = str(name or "").strip()
            if not clean_name:
                raise ValueError("Profil adi bos olamaz")
            base_id = _slugify(clean_name)
            pid = base_id
            idx = 2
            while pid in self._data["profiles"]:
                pid = f"{base_id}-{idx}"
                idx += 1
            accent = accent_theme if accent_theme in _VALID_ACCENTS else "mor"
            sub = clean_name if download_subfolder is None else str(download_subfolder).strip()
            # klasor adi: Windows'ta yasak karakterler ve ust dizine cikis (.., /, \) temizlenir
            sub = re.sub(r"\.{2,}", ".", re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", sub)).strip(" .-")
            sub = "" if sub in ("", ".", "..") else sub
            prof = {
                "id": pid,
                "name": clean_name,
                "accent_theme": accent,
                "download_subfolder": sub,
                "builtin": False,
                "badge": clean_name[:1].upper(),
            }
            self._data["profiles"][pid] = prof
            self._save()
            return copy.deepcopy(prof)

    def delete_profile(self, profile_id: str) -> bool:
        with self._lock:
            pid = str(profile_id or "").strip()
            prof = self._data["profiles"].get(pid)
            if not prof or prof.get("builtin"):
                return False
            del self._data["profiles"][pid]
            if self._data["active"] == pid:
                self._data["active"] = "kisisel"
                if self.settings is not None:
                    self.settings.set("active_profile", "kisisel")
                    self.settings.set("accent_theme", BUILTIN_PROFILES["kisisel"]["accent_theme"])
            self._save()
            return True

    def effective_download_dir(self, base_dir: Path | str | None = None) -> Path:
        """Aktif profilin alt klasoruyle birlikte indirme kok klasorunu doner."""
        if base_dir:
            root = Path(base_dir)
        elif self.settings is not None and self.settings.get("download_dir"):
            root = Path(str(self.settings.get("download_dir")))
        else:
            root = paths.downloads_dir()
        sub = (self.active_profile().get("download_subfolder") or "").strip()
        return (root / sub) if sub else root
