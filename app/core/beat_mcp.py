"""Kami Beat MCP / AI Miks Koprusu: dogal dil veya JSON direktifiyle vokal/beat miksleme."""
from __future__ import annotations

from typing import Any

from app.core import beat_studio


def apply_ai_mix_instruction(project_id: str, instruction: str, track_id: str = "vocal1") -> dict[str, Any]:
    """Kullanici veya AI (Claude/Antigravity) direktifini kanal FX zincirine cevirip uygular."""
    loaded = beat_studio.load_project(project_id)
    if not loaded.get("ok"):
        return loaded
    proj = loaded["project"]
    tr = next((t for t in proj.get("tracks", []) if t.get("id") == track_id), None)
    if tr is None:
        return {"ok": False, "error": "track_not_found"}

    inst = str(instruction or "").lower()
    actions: list[str] = []

    if any(k in inst for k in ("atk", "gürültü", "gurultu", "temizle", "denoise", "iphone")):
        p = beat_studio.VOCAL_PRESETS["atk_n9_cleanup"]
        tr["preset"] = "atk_n9_cleanup"
        tr["denoise"] = True
        tr["fx"] = list(p["fx"])
        actions.append("ATK N9 / AI gürültü temizleme + HPF + De-Esser uygulandı")
    elif any(k in inst for k in ("trap", "melodik", "parlak", "geniş", "genis")):
        p = beat_studio.VOCAL_PRESETS["melodic_trap"]
        tr["preset"] = "melodic_trap"
        tr["fx"] = list(p["fx"])
        actions.append("Melodik / Trap şablonu yüklendi")
    elif any(k in inst for k in ("lofi", "lo-fi", "duygusal", "sıcak", "sicak")):
        p = beat_studio.VOCAL_PRESETS["lofi_emotional"]
        tr["preset"] = "lofi_emotional"
        tr["fx"] = list(p["fx"])
        actions.append("Lo-Fi / Duygusal şablonu yüklendi")
    elif any(k in inst for k in ("temiz rap", "kuru", "dry", "punch")):
        p = beat_studio.VOCAL_PRESETS["clean_rap"]
        tr["preset"] = "clean_rap"
        tr["fx"] = list(p["fx"])
        actions.append("Temiz Rap (Dry & Punchy) şablonu yüklendi")

    fx = tr.setdefault("fx", [])
    if any(k in inst for k in ("öne çıkar", "one cikar", "vokal ses", "vokal yükselt", "vokal art")):
        tr["volume_db"] = round(min(6.0, float(tr.get("volume_db") or 0.0) + 2.0), 1)
        actions.append(f"Vokal seviyesi {tr['volume_db']} dB yapıldı")
    if any(k in inst for k in ("beat kıs", "beat kis", "altyapı kıs", "altyapi kis")):
        for bt in proj.get("tracks", []):
            if bt.get("role") == "beat":
                bt["volume_db"] = round(max(-12.0, float(bt.get("volume_db") or 0.0) - 2.0), 1)
                actions.append(f"Beat seviyesi {bt['volume_db']} dB yapıldı")
    if "reverb" in inst and any(k in inst for k in ("azalt", "kıs", "kis", "kuru")):
        for node in fx:
            if node.get("type") == "reverb":
                node["wet_level"] = max(0.03, round(float(node.get("wet_level", 0.15)) * 0.5, 2))
        actions.append("Reverb wet seviyesi düşürüldü")
    elif "reverb" in inst and any(k in inst for k in ("art", "ekle", "büyüt", "buyut")):
        rev = next((n for n in fx if n.get("type") == "reverb"), None)
        if rev:
            rev["wet_level"] = min(0.45, round(float(rev.get("wet_level", 0.12)) + 0.1, 2))
        else:
            fx.append({"type": "reverb", "room_size": 0.45, "wet_level": 0.2, "dry_level": 0.88})
        actions.append("Reverb artırıldı")
    if "delay" in inst and any(k in inst for k in ("ekle", "art", "aç", "ac")):
        if not any(n.get("type") == "delay" for n in fx):
            fx.append({"type": "delay", "delay_seconds": 0.25, "feedback": 0.2, "mix": 0.15})
        actions.append("Delay eklendi")
    if "sert" in inst or "agresif" in inst or "saturasyon" in inst:
        dist = next((n for n in fx if n.get("type") == "distortion"), None)
        if dist:
            dist["drive_db"] = min(10.0, float(dist.get("drive_db", 3.0)) + 2.5)
        else:
            fx.append({"type": "distortion", "drive_db": 4.5})
        actions.append("Harmonik saturasyon artırıldı")

    if not actions:
        # Varsayilan iyilestirme
        tr["fx"] = list(beat_studio.VOCAL_PRESETS["clean_rap"]["fx"])
        actions.append("Varsayılan Temiz Rap vokal zinciri uygulandı")

    beat_studio.save_project(proj)
    return {"ok": True, "actions": actions, "project": proj}
