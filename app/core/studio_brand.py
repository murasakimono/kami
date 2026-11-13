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
        "name": "Minimal Shorts / Reels",
        "desc": "Dikey güvenli alan uyumlu temiz tipografi ve nefes zoom (breath).",
        "grade": {"con": 0.08, "sat": 1.04},
        "zoom_preset": "breath",
        "sub_style": "classic",
        "shutter_angle": 180,
        "lufs": -14.0,
    },
    "rap_mv_dark": {
        "id": "rap_mv_dark",
        "name": "Rap Klip / 3EVLER Tarzı",
        "desc": "Yüksek kontrast koyu sinematik ton, sert zoom vuruşu (crash) ve keskin flaş geçişi.",
        "grade": {"con": 0.24, "sat": 0.88, "exp": -0.06, "temp": -0.05},
        "zoom_preset": "crash",
        "trans_in": "flash",
        "fx": ["vignette", "film"],
        "sub_style": "none",
        "shutter_angle": 180,
        "lufs": -13.0,
    },
    "roblox_gaming": {
        "id": "roblox_gaming",
        "name": "Roblox / Oyun Hızlı Kurgu",
        "desc": "Canlı doygun renkler, enerjik pop zoom (push-fast) ve sallantı animasyonu.",
        "grade": {"con": 0.14, "sat": 1.25, "exp": 0.05},
        "zoom_preset": "push-fast",
        "trans_in": "pop-in",
        "anim_loop": "wobble",
        "sub_style": "hormozi",
        "shutter_angle": 180,
        "lufs": -14.0,
    },
    "anime_velocity": {
        "id": "anime_velocity",
        "name": "Anime Edit / Velocity",
        "desc": "Parlak neon renkler, sert whip geçişi ve ritmik zoom vuruşu.",
        "grade": {"con": 0.22, "sat": 1.3, "exp": 0.04},
        "zoom_preset": "crash",
        "trans_in": "whip",
        "fx": ["glow"],
        "sub_style": "none",
        "shutter_angle": 270,
        "lufs": -13.5,
    },
    "mrbeast_retention": {
        "id": "mrbeast_retention",
        "name": "MrBeast / Yüksek Tutma",
        "desc": "Parlak net görüntü, hızlı yaklaşma (dolly-in) ve dikkat çekici pop giriş.",
        "grade": {"con": 0.15, "sat": 1.18, "exp": 0.07},
        "zoom_preset": "dolly-in",
        "trans_in": "zoom",
        "sub_style": "hormozi",
        "shutter_angle": 180,
        "lufs": -14.0,
    },
    "podcast_clip": {
        "id": "podcast_clip",
        "name": "Podcast / Kesit Vurgu",
        "desc": "Doğal sıcak cilt tonu, yumuşak nefes zoom ve net konuşma altyazısı.",
        "grade": {"con": 0.1, "sat": 1.02, "temp": 0.05},
        "zoom_preset": "breath",
        "sub_style": "clean_box",
        "shutter_angle": 180,
        "lufs": -14.0,
    },
    "retro_vhs": {
        "id": "retro_vhs",
        "name": "Retro VHS / 90'lar",
        "desc": "VHS renk kayması, tarama çizgileri ve nostaljik salınım (swing).",
        "grade": {"con": 0.1, "sat": 0.9, "temp": 0.08},
        "zoom_preset": "kb-zoom-lr",
        "trans_in": "vhs-roll",
        "fx": ["vhs"],
        "anim_loop": "swing",
        "sub_style": "none",
        "shutter_angle": 180,
        "lufs": -14.5,
    },
    "cinematic_vlog": {
        "id": "cinematic_vlog",
        "name": "Sinematik Vlog / Gezi",
        "desc": "Altın saat sıcaklığı, akıcı Ken Burns hareketi ve yumuşak kararma.",
        "grade": {"con": 0.12, "sat": 1.12, "temp": 0.1, "exp": 0.02},
        "zoom_preset": "kb-zoom-lr",
        "trans_in": "fade",
        "sub_style": "cinematic",
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


def apply_viral_recipe(project: dict[str, Any], recipe_id: str, brand_kit: dict[str, Any] | None = None,
                       clip_ids: list[str] | None = None) -> dict[str, Any]:
    """Projeye (veya sadece secili kliplere) secilen viral kurgu recetesini uygular."""
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
    target_set = set(str(cid) for cid in clip_ids) if clip_ids else None
    applied_clips = 0
    for c in pr.get("clips") or []:
        if target_set is not None and str(c.get("id", "")) not in target_set:
            continue
        if c.get("kind") in (None, "video", "image"):
            g = dict(c.get("grade") or {})
            for k, v in rec["grade"].items():
                g[k] = v
            c["grade"] = g
            c["shutterAngle"] = rec["shutter_angle"]
            if zoom_kf:
                c["zoom"] = copy.deepcopy(zoom_kf)
            if rec.get("trans_in"):
                c["trans"] = {"in": rec["trans_in"], "dur": 0.35, "over": True}
            if rec.get("fx"):
                existing_fx = [f for f in (c.get("fx") or []) if f not in rec["fx"]]
                c["fx"] = existing_fx + list(rec["fx"])
            if rec.get("anim_loop"):
                anim = dict(c.get("anim") or {})
                anim["loop"] = rec["anim_loop"]
                c["anim"] = anim
            applied_clips += 1
    pr.setdefault("markers", []).append({
        "id": f"m_{uuid.uuid4().hex[:6]}",
        "t": 0.0,
        "kind": "recipe",
        "label": rec["name"],
    })
    return {"ok": True, "recipe": rec["id"], "applied_clips": applied_clips, "project": pr}
