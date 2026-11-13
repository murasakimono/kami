"""Kami Studio Faz 9.5: Marka Kiti (Brand Kit) ve 5 Viral Kurgu Paketi (`run_recipe`)."""
from __future__ import annotations

import copy
import json
import logging
import threading
import uuid
from pathlib import Path
from typing import Any

from app import paths

log = logging.getLogger(__name__)

DEFAULT_BRAND_KIT: dict[str, Any] = {
    "name": "Varsayılan Marka",
    "primary": "#7C3AED",
    "accent": "#2EE6A6",
    "text_color": "#FFFFFF",
    "font": "Chakra Petch",
    "logo_path": "",
    "safe_zone": "reels_9_16",
}

VIRAL_RECIPES: dict[str, dict[str, Any]] = {
    "iman_gadzhi": {
        "id": "iman_gadzhi",
        "name": "Iman Gadzhi (Hızlı Kanca & Punch-In)",
        "desc": "Keskin kontrast, hızlı punch-in zoom (push-fast) ve yüksek okunaklı kelime altyazısı.",
        "grade": {"con": 0.16, "sat": 0.92, "exp": -0.05},
        "zoom_preset": "push-fast",
        "sub_style": "word_pop",
        "shutter_angle": 180,
        "lufs": -14.0,
    },
    "magnates_media": {
        "id": "magnates_media",
        "name": "MagnatesMedia (Belgesel 2.5D & Film)",
        "desc": "Teal-turuncu sinematik ton, Ken Burns (kb-zoom-lr) ve dramatik hareket bulanıklığı.",
        "grade": {"con": 0.12, "sat": 1.08, "temp": -0.08},
        "zoom_preset": "kb-zoom-lr",
        "sub_style": "cinematic",
        "shutter_angle": 180,
        "lufs": -14.0,
    },
    "ali_abdaal": {
        "id": "ali_abdaal",
        "name": "Ali Abdaal (Temiz Eğitici & Pop)",
        "desc": "Sıcak aydınlık tonlar ve yumuşak yaklaşma (dolly-in).",
        "grade": {"exp": 0.08, "temp": 0.06, "sat": 1.05},
        "zoom_preset": "dolly-in",
        "sub_style": "clean_box",
        "shutter_angle": 144,
        "lufs": -14.0,
    },
    "fps_frag": {
        "id": "fps_frag",
        "name": "Valorant / CS2 Frag (Hız + Shutter Blur)",
        "desc": "Yüksek shutter motion blur, çarpma zoom (crash) ve yüksek doygunluk.",
        "grade": {"con": 0.2, "sat": 1.22},
        "zoom_preset": "crash",
        "sub_style": "none",
        "shutter_angle": 270,
        "lufs": -13.0,
    },
    "minimal_shorts": {
        "id": "minimal_shorts",
        "name": "Minimal Shorts / Reels (9:16 Odak)",
        "desc": "Dikey güvenli alan uyumlu merkez tipografi ve nefes zoom (breath).",
        "grade": {"con": 0.08, "sat": 1.04},
        "zoom_preset": "breath",
        "sub_style": "classic",
        "shutter_angle": 180,
        "lufs": -14.0,
    },
}


class BrandKitStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (paths.DATA_DIR / "brand_kits.json")
        self._lock = threading.RLock()

    def load(self, profile_id: str = "kisisel") -> dict[str, Any]:
        with self._lock:
            all_kits: dict[str, Any] = {}
            if self.path.exists():
                try:
                    raw = json.loads(self.path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        all_kits = raw
                except (OSError, json.JSONDecodeError):
                    pass
            kit = copy.deepcopy(DEFAULT_BRAND_KIT)
            if isinstance(all_kits.get(profile_id), dict):
                kit.update(all_kits[profile_id])
            kit["profile_id"] = profile_id
            return kit

    def save(self, profile_id: str, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            all_kits: dict[str, Any] = {}
            if self.path.exists():
                try:
                    raw = json.loads(self.path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        all_kits = raw
                except (OSError, json.JSONDecodeError):
                    pass
            merged = {**DEFAULT_BRAND_KIT, **(all_kits.get(profile_id) or {}), **(data or {})}
            merged.pop("profile_id", None)
            all_kits[profile_id] = merged
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(all_kits, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
            return {**merged, "profile_id": profile_id}


def list_recipes() -> list[dict[str, Any]]:
    return [copy.deepcopy(v) for v in VIRAL_RECIPES.values()]


def apply_viral_recipe(project: dict[str, Any], recipe_id: str, brand_kit: dict[str, Any] | None = None) -> dict[str, Any]:
    """Projeye secilen viral kurgu recetesini (grade, shutter, marka rengi) uygular."""
    if recipe_id not in VIRAL_RECIPES:
        raise KeyError(f"Bilinmeyen recete: {recipe_id}")
    rec = VIRAL_RECIPES[recipe_id]
    pr = copy.deepcopy(project)
    pr["recipe"] = recipe_id
    pr["shutterAngle"] = rec["shutter_angle"]
    if brand_kit:
        pr["brandKit"] = copy.deepcopy(brand_kit)
    from app.core.studio_packs import ZOOM3
    zoom_map = {z["id"]: copy.deepcopy(z["kf"]) for z in ZOOM3 if "id" in z and "kf" in z}
    zoom_kf = zoom_map.get(rec["zoom_preset"], [])
    applied_clips = 0
    for c in pr.get("clips") or []:
        if c.get("kind") in (None, "video", "image"):
            g = dict(c.get("grade") or {})
            for k, v in rec["grade"].items():
                g[k] = v
            c["grade"] = g
            c["shutterAngle"] = rec["shutter_angle"]
            if zoom_kf:
                c["zoom"] = copy.deepcopy(zoom_kf)
            applied_clips += 1
    pr.setdefault("markers", []).append({
        "id": f"m_{uuid.uuid4().hex[:6]}",
        "t": 0.0,
        "kind": "recipe",
        "label": rec["name"],
    })
    return {"ok": True, "recipe": rec["id"], "applied_clips": applied_clips, "project": pr}
