"""Kami Beat Asama 2a: tarz onayarlari, adlib hizli efektleri ve efekt atmalari (throws).

Tarz onayari = sirali adim listesi. Her adim "tercih edilen VST3 + yedek yerlesik efekt" ciftidir:
- kullanicinin makinesinde (scan_vst3) tercih edilen eklenti kuruluysa o eklenir. Bilinen parametreler
  (mix/depth/width gibi 0..1 ham degerli olanlar) eklentinin GERCEK parametre listesinde ada gore aranir
  (beat_fx.vst_params, onbellekli) ve bulunursa ayarlanir; bulunamazsa eklenti varsayilaniyla eklenir ve
  "ayari eklenti penceresinden incelt" notu dusulur (adim ve not arayuzde gorunur).
- eklenti yoksa FX_SCHEMA'daki esdeger yerlesik efekt (pedalboard) bilinen degerleriyle eklenir. Boylece her
  makinede calisir; "Kurulu eklentileri kullan" kapatilirsa tum zincir yerlesik (birebir ayarli) kurulur.
- Yogunluk (0-100, 50 = tasarlanan): wet/mix, kompresyon orani/esigi ve saturasyon surusu olceklenir.
- Katman esleniği: ayni onayarin double/adlib/chant turevi (ince + genis / bant + delay / koro + genis reverb).
- Kullanici onayarlari: DATA_DIR/beat_settings/user_presets.json (kayitlar/projeler disinda), listenin basinda.

Adlib hizli efektleri ve atmalar klip fx'i olarak eklenir (R4 klip fx altyapisi); delay suresi proje BPM'ine
kilitli (1/4, 1/8, noktali 1/8). Atmalarda bolge region_split ile ayri klip olur, ortadaki parcaya efekt ve
kuyruk (tail_sec; ters reverb'de head_sec) yazilir: render kuyrugu klip sonrasina tasir.
"""
from __future__ import annotations

import copy
import json
import logging
import math
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from app import paths
from app.core import beat_clips, beat_fx

log = logging.getLogger(__name__)

DEFAULT_INTENSITY = 50
LAYER_KINDS = ("double", "adlib", "chant")
KIND_NAMES = {"double": "Double", "adlib": "Adlib", "chant": "Chant"}

# ---------------- Kullanicinin VST3 eklentileri (dosya adina gore eslesme) ----------------
VST_CATALOG: dict[str, dict[str, str]] = {
    "graillon": {"label": "Graillon 3", "re": r"graillon"},
    "mautopitch": {"label": "MAutoPitch", "re": r"^mautopitch"},
    "nova": {"label": "TDR Nova", "re": r"^tdr\s*nova"},
    "tilt": {"label": "Tilt EQ", "re": r"tilt\s*eq"},
    "mequalizer": {"label": "MEqualizer", "re": r"^mequalizer"},
    "kotelnikov": {"label": "TDR Kotelnikov", "re": r"kotelnikov"},
    "mjuc": {"label": "MJUCjr", "re": r"^mjuc"},
    "mcompressor": {"label": "MCompressor", "re": r"^mcompressor"},
    "ivgi": {"label": "IVGI2", "re": r"^ivgi"},
    "tsat": {"label": "T-Saturator", "re": r"^t-?\s*saturator"},
    "msaturator": {"label": "MSaturator", "re": r"^msaturator"},
    "tdeess": {"label": "T-De-Esser 2", "re": r"^t-?\s*de-?\s*esser"},
    "supermassive": {"label": "Valhalla Supermassive", "re": r"supermassive"},
    "mcharmverb": {"label": "MCharmVerb", "re": r"^mcharmverb"},
    "mdelay": {"label": "MDelay", "re": r"^mdelay"},
    "ott": {"label": "OTT", "re": r"^(xfer\s*)?ott$|^ott\b"},
    "wider": {"label": "Wider", "re": r"^wider"},
    "doubler": {"label": "Vocal Doubler", "re": r"vocal\s*doubler"},
    "mstereoexpander": {"label": "MStereoExpander", "re": r"^mstereoexpander"},
}


def installed_map(plugins: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    """{katalog anahtari: eklenti kaydi (name, path)} — scan_vst3()['plugins'] verilir."""
    out: dict[str, dict[str, Any]] = {}
    for p in plugins or []:
        stem = str(p.get("name") or Path(str(p.get("path") or "")).stem).strip().lower()
        if not stem:
            continue
        for k, spec in VST_CATALOG.items():
            if k not in out and re.search(spec["re"], stem):
                out[k] = p
    return out


# ---------------- yerlesik efekt kisayollari ----------------
def _hpf(hz): return {"type": "highpass", "cutoff_hz": float(hz)}
def _lpf(hz): return {"type": "lowpass", "cutoff_hz": float(hz)}
def _peak(hz, db, q=1.0): return {"type": "peak", "cutoff_hz": float(hz), "gain_db": float(db), "q": float(q)}
def _hshelf(hz, db): return {"type": "highshelf", "cutoff_hz": float(hz), "gain_db": float(db), "q": 0.707}
def _deess(hz, db): return {"type": "deesser", "freq_hz": float(hz), "gain_db": float(db)}
def _comp(thr, ratio, att, rel): return {"type": "compressor", "threshold_db": float(thr), "ratio": float(ratio),
                                         "attack_ms": float(att), "release_ms": float(rel)}
def _dist(db): return {"type": "distortion", "drive_db": float(db)}
def _verb(room, wet, damp=0.5, dry=0.92): return {"type": "reverb", "room_size": float(room), "damping": float(damp),
                                                  "wet_level": float(wet), "dry_level": float(dry), "width": 1.0}
def _delay(sec, fb, mix): return {"type": "delay", "delay_seconds": float(sec), "feedback": float(fb), "mix": float(mix)}
def _chorus(rate=0.6, depth=0.15, mix=0.25): return {"type": "chorus", "rate_hz": rate, "depth": depth,
                                                     "centre_delay_ms": 9.0, "feedback": 0.0, "mix": mix}
def _lim(thr=-1.0): return {"type": "limiter", "threshold_db": float(thr), "release_ms": 100.0}


def _st(role: str, label: str, fallback: list[dict[str, Any]] | None, vst: tuple[str, ...] = (),
        want: list[tuple[tuple[str, ...], float]] | None = None, bypass: bool = False, note: str = "",
        sync: str = "", fb_note: str = "") -> dict[str, Any]:
    """Onayar adimi. want: [(ad kaliplari, ham 0..1 deger)] — eklentinin parametre adinda kalip aranir."""
    return {"role": role, "label": label, "fallback": fallback or [], "vst": tuple(vst), "want": list(want or []),
            "bypass": bool(bypass), "note": note, "sync": sync, "fb_note": fb_note}


# adim fabrikalari (tipik zincir sirasi: ton -> HPF -> de-esser -> kompresor -> EQ -> renk -> OTT -> reverb/delay -> genislik)
def tune(on: bool = False):
    return _st("tune", "Ton düzeltme", None, ("graillon", "mautopitch"), bypass=not on,
               note="Ton/ölçeği eklenti penceresinden seç" + ("" if on else " (kapalı eklendi: LED ile aç)"))
def hpf(hz): return _st("hpf", f"HPF {int(hz)} Hz", [_hpf(hz)])
def lpf(hz): return _st("lpf", f"LPF {hz / 1000:g} kHz", [_lpf(hz)])
def mud(hz, db): return _st("eq", f"Çamur kesimi {int(hz)} Hz", [_peak(hz, db, 1.3)])
def presence(hz, db): return _st("eq", f"Varlık {hz / 1000:g} kHz", [_peak(hz, db, 1.0)])
def deess(hz, db): return _st("deess", "De-esser", [_deess(hz, db)], ("tdeess",))
def comp(thr, ratio, att, rel, prefer=("mjuc", "kotelnikov", "mcompressor")):
    return _st("comp", "Kompresör", [_comp(thr, ratio, att, rel)], prefer)
def bright(hz, db, prefer=("nova", "tilt", "mequalizer")):
    return _st("bright", f"Parlaklık {hz / 1000:g} kHz", [_peak(hz, db, 0.8)], prefer)
def sat(db, prefer=("ivgi", "tsat", "msaturator")):
    return _st("sat", "Saturasyon", [_dist(db)], prefer)
def ott(depth):
    return _st("ott", "OTT", [_comp(-26.0, 2.5, 3.0, 60.0)], ("ott",), [(("depth",), depth)],
               fb_note="yerleşik yedek: hafif paralel-benzeri kompresyon")
def verb(room, wet, damp=0.5, prefer=("supermassive", "mcharmverb")):
    return _st("verb", "Reverb", [_verb(room, wet, damp)], prefer, [(("mix", "dry_wet", "wet"), wet * 1.6)])
def delay(sync, fb, mix, sec=0.25):
    return _st("delay", f"Delay {sync}", [_delay(sec, fb, mix)], ("mdelay",), [(("dry_wet", "mix", "wet"), mix * 1.6)],
               sync=sync)
def wide(prefer=("wider", "doubler", "mstereoexpander")):
    return _st("wide", "Genişlik", [_chorus()], prefer, [(("width", "amount"), 0.6)])
def limit(thr=-1.0): return _st("limit", "Limiter", [_lim(thr)])


PRESETS: list[dict[str, Any]] = [
    {"id": "temiz_trap", "name": "Temiz Trap", "genre": "Trap", "kind": "vocal",
     "desc": "Net, parlak, hafif oda — modern trap vokali.",
     "why": "HPF + de-esser temiz zemin; 4:1 kompresör seviyeyi sabitler; 7 kHz hava trap'in parlak tonunu verir, kısa 1/8 delay boşlukları doldurur.",
     "steps": [tune(False), hpf(90), deess(6800, -4), comp(-18, 4, 8, 85), mud(350, -2.5), bright(7000, 3.0),
               sat(2.5), verb(0.35, 0.12), delay("1/8", 0.2, 0.1), limit()]},
    {"id": "karanlik_drill", "name": "Karanlık Drill", "genre": "Drill", "kind": "vocal",
     "desc": "Koyu, sert, önde — UK/NY drill teslimatı.",
     "why": "Tepe frekanslar hafif kısılır (11 kHz LPF), 2.5 kHz varlık korunur; hızlı ataklı sert kompresör agresif teslimatı öne iter, noktalı 1/8 delay drill kaymasına uyar.",
     "steps": [tune(False), hpf(100), deess(6500, -5), comp(-20, 5, 5, 70, ("kotelnikov", "mjuc", "mcompressor")),
               mud(300, -3), presence(2500, 2.0), lpf(11000), sat(4.0, ("tsat", "ivgi", "msaturator")),
               verb(0.5, 0.1, 0.7), delay("1/8d", 0.25, 0.12), limit()]},
    {"id": "hyperpop", "name": "Hyperpop", "genre": "Hyperpop", "kind": "vocal",
     "desc": "Belirgin ton düzeltme, çok parlak, sıkıştırılmış.",
     "why": "Graillon açık (robotik ton), 9 kHz +5 dB parlaklık, yoğun saturasyon ve OTT (düşük mix) yüzeyi parlatır; geniş reverb + 1/8 delay hyperpop boşluğunu verir.",
     "steps": [tune(True), hpf(120), deess(7500, -6), comp(-22, 6, 3, 60), bright(9000, 5.0),
               sat(6.0, ("tsat", "ivgi", "msaturator")), ott(0.35), verb(0.4, 0.15), delay("1/8", 0.3, 0.15), limit()]},
    {"id": "boom_bap", "name": "Boom Bap", "genre": "Boom Bap", "kind": "vocal",
     "desc": "Sıcak, analog, kısa oda — 90'lar rap.",
     "why": "Yavaş ataklı 3.5:1 kompresör geçişleri korur, IVGI analog doygunluk ve 14 kHz LPF sıcaklık verir; reverb neredeyse kuru.",
     "steps": [tune(False), hpf(80), deess(6500, -3), comp(-16, 3.5, 15, 120), mud(400, -1.5), presence(3000, 1.5),
               sat(4.0), lpf(14000), verb(0.15, 0.07), limit()]},
    {"id": "lofi", "name": "Lo-fi", "genre": "Lo-fi", "kind": "vocal",
     "desc": "Bant genişliği dar, doygun, derin reverb.",
     "why": "150 Hz–7.5 kHz bant eski kayıt hissi verir; yumuşak kompresör + belirgin saturasyon, koyu uzun reverb ve 1/4 delay.",
     "steps": [tune(False), hpf(150), lpf(7500), comp(-16, 3, 14, 120), sat(7.0, ("tsat", "ivgi", "msaturator")),
               verb(0.6, 0.22, 0.7), delay("1/4", 0.3, 0.15), limit(-1.5)]},
    {"id": "phonk", "name": "Phonk", "genre": "Phonk", "kind": "vocal",
     "desc": "Memphis tadında bant, ağır saturasyon, OTT.",
     "why": "180 Hz–9 kHz bant ve ağır T-Saturator kirli Memphis tonunu verir; OTT detayı öne çeker, noktalı 1/8 delay kuyruğu.",
     "steps": [tune(False), hpf(180), lpf(9000), deess(6500, -4), comp(-20, 5, 4, 70, ("kotelnikov", "mjuc", "mcompressor")),
               sat(10.0, ("tsat", "ivgi", "msaturator")), ott(0.3), delay("1/8d", 0.35, 0.2), verb(0.45, 0.15), limit()]},
    {"id": "disstrack", "name": "Disstrack", "genre": "Diss", "kind": "vocal",
     "desc": "Agresif, en önde, hafif distortion.",
     "why": "Sert kompresör (6:1) ve 4 kHz varlık vokali beat'in önüne koyar; IVGI ile hafif distortion agresyon katar; reverb neredeyse yok ki sözler net kalsın.",
     "steps": [tune(False), hpf(100), deess(6800, -5), comp(-22, 6, 3, 60, ("kotelnikov", "mjuc", "mcompressor")),
               mud(320, -3), bright(4000, 2.5), sat(8.0), verb(0.12, 0.05), limit()]},
    {"id": "hard", "name": "Hard", "genre": "Rage / Hard", "kind": "vocal",
     "desc": "Yoğun kompresyon + parlaklık + OTT.",
     "why": "8:1 hızlı kompresör ve OTT seviyeyi duvar gibi sabitler; 8 kHz +4.5 dB parlaklık kalabalık beat'te vokali keser; reverb kısa.",
     "steps": [tune(False), hpf(100), deess(7000, -6), comp(-24, 8, 2, 50), bright(8000, 4.5), sat(5.0), ott(0.3),
               verb(0.25, 0.08), limit()]},
    {"id": "soft", "name": "Soft", "genre": "R&B / Melodik", "kind": "vocal",
     "desc": "Yumuşak, daha fazla reverb, az kompresyon.",
     "why": "2.5:1 yavaş kompresör dinamiği korur; üstte hafif hava, geniş Supermassive reverb ve 1/4 delay yumuşak bir alan açar.",
     "steps": [tune(False), hpf(80), deess(6500, -3), comp(-14, 2.5, 15, 150), bright(9000, 1.5), verb(0.65, 0.25),
               delay("1/4", 0.25, 0.12), limit()]},
    {"id": "storytelling", "name": "Storytelling", "genre": "Hikâye", "kind": "vocal",
     "desc": "Net, kuru, anlaşılır; az efekt.",
     "why": "Her kelime duyulsun diye çamur kesilir ve 3.5 kHz anlaşılırlık bölgesi hafif açılır; reverb neredeyse kuru, delay yok.",
     "steps": [tune(False), hpf(90), deess(6500, -4), comp(-18, 3.5, 10, 100), mud(350, -2), presence(3500, 2.0),
               verb(0.1, 0.04), limit()]},
    {"id": "sinematik", "name": "Sinematik Dramatik", "genre": "NF tarzı", "kind": "vocal",
     "desc": "Koyu büyük reverb, double genişliği, dramatik.",
     "why": "Büyük ve koyu reverb (oda 0.85) sinematik alan, 1/4 delay ve genişlik eklentisi (Wider/Doubler) NF tarzı geniş double hissi verir.",
     "steps": [tune(False), hpf(100), deess(6800, -4), comp(-20, 4, 8, 90, ("kotelnikov", "mjuc", "mcompressor")),
               mud(300, -2), bright(6000, 2.0), sat(2.0), verb(0.85, 0.3, 0.6), delay("1/4", 0.35, 0.15), wide(), limit()]},
    {"id": "telefon_radyo", "name": "Telefon / Radyo", "genre": "Adlib", "kind": "adlib",
     "desc": "Dar bant, kirli — adlib ve ara sesler için.",
     "why": "450 Hz–3.4 kHz bant telefon hoparlörünü taklit eder, 1.8 kHz tepe ve ağır saturasyon radyo kirliliği verir.",
     "steps": [hpf(450), lpf(3400), _st("eq", "Telefon tepesi 1.8 kHz", [_peak(1800, 5.0, 1.0)]),
               sat(10.0, ("tsat", "ivgi", "msaturator")), comp(-20, 6, 3, 60), verb(0.2, 0.08), limit()]},
]
_BY_ID = {p["id"]: p for p in PRESETS}


# ---------------- BPM'e kilitli delay ----------------
SYNC_NOTES = {"1/4": 1.0, "1/8": 0.5, "1/8d": 0.75, "1/16": 0.25, "1/2": 2.0}
SYNC_LABELS = {"1/4": "1/4", "1/8": "1/8", "1/8d": "nokta 1/8", "1/16": "1/16", "1/2": "1/2"}


def delay_time(bpm: float, note: str = "1/8") -> float:
    """Proje BPM'ine kilitli delay suresi (sn). BPM yoksa 120. Delay semasi araligina (0.01-2 sn) sikistirilir."""
    try:
        b = float(bpm)
    except (TypeError, ValueError):
        b = 0.0
    if not math.isfinite(b) or b <= 0:
        b = 120.0
    beats = SYNC_NOTES.get(str(note or "1/8"), 0.5)
    return round(max(0.01, min(2.0, 60.0 / b * beats)), 6)


def delay_tail(sec: float, feedback: float, floor_db: float = -60.0, cap: float = 8.0) -> float:
    """Geri beslemeli delay kuyrugunun -60 dB'e inme suresi (yankilarin sayisi x sure), ust sinirli."""
    fb = max(0.01, min(0.95, float(feedback)))
    n = math.ceil(math.log(10 ** (floor_db / 20.0)) / math.log(fb))
    return round(max(0.1, min(cap, float(sec) * (n + 1))), 3)


# ---------------- yogunluk olcekleme ----------------
_WET_PARAM = ("mix", "wet", "depth", "amount", "width")


def scale_fx(fx: dict[str, Any], intensity: float) -> dict[str, Any]:
    """Tek modulu yogunluga gore olcekler (kopya). 50 = tasarlanan; 0 = en hafif; 100 = iki kat.
    wet/mix: x f; kompresor: oran 1+(r-1)f, esik t(0.5+0.5f); saturasyon surusu x f; VST'de mix/depth/width ham x f."""
    f = max(0.0, min(100.0, float(intensity))) / 50.0
    out = copy.deepcopy(fx)
    t = str(out.get("type") or "").lower()
    if t == "reverb" or t == "reverse_reverb":
        out["wet_level"] = float(out.get("wet_level", 0.12)) * f
    elif t in ("delay", "chorus"):
        out["mix"] = float(out.get("mix", 0.15)) * f
    elif t == "compressor":
        out["ratio"] = 1.0 + (float(out.get("ratio", 4.0)) - 1.0) * f
        out["threshold_db"] = float(out.get("threshold_db", -18.0)) * (0.5 + 0.5 * f)
    elif t == "distortion":
        out["drive_db"] = float(out.get("drive_db", 3.0)) * f
    elif t == "vst3" and isinstance(out.get("params"), dict):
        for k in list(out["params"]):
            if any(w in k.lower() for w in _WET_PARAM):
                out["params"][k] = float(out["params"][k]) * f
    return beat_fx.clamp_fx(out)


def scale_chain(fx_list: list[dict[str, Any]], intensity: float) -> list[dict[str, Any]]:
    return [scale_fx(f, intensity) for f in fx_list or [] if isinstance(f, dict)]


# ---------------- cozumleme ----------------
def _default_lookup(path: str) -> list[str] | None:
    r = beat_fx.vst_params(path, limit=1000)
    if not r.get("ok"):
        return None
    return [str(p.get("key") or "") for p in r.get("params") or []]


def _match_param(keys: list[str], patterns: tuple[str, ...]) -> str | None:
    norm = [(k, re.sub(r"[^a-z0-9]+", "_", k.lower())) for k in keys]
    for pat in patterns:
        for k, n in norm:
            if pat in n:
                return k
    return None


def _sync_fx(fx: dict[str, Any], sync: str, bpm: float) -> dict[str, Any]:
    if sync and fx.get("type") == "delay":
        fx["delay_seconds"] = delay_time(bpm, sync)
        fx["sync"] = sync
    return fx


def resolve_steps(steps: list[dict[str, Any]], plugins: list[dict[str, Any]] | None = None, use_vst: bool = True,
                  bpm: float = 0.0, param_lookup: Callable[[str], list[str] | None] | None = None) -> dict[str, Any]:
    """Adim listesi -> fx zinciri + adim raporu. VST kuruluysa o (bilinen parametreler ada gore eslesir),
    yoksa yerlesik yedek; ikisi de yoksa adim atlanir."""
    inst = installed_map(plugins) if use_vst else {}
    lookup = param_lookup or _default_lookup
    fx_out: list[dict[str, Any]] = []
    report: list[dict[str, Any]] = []
    vst_total = vst_inst = 0
    for st in steps:
        if st["vst"]:
            vst_total += 1
        key = next((k for k in st["vst"] if k in inst), None)
        if key:
            vst_inst += 1
            plg = inst[key]
            path = str(plg.get("path") or "")
            fx: dict[str, Any] = {"type": "vst3", "path": path, "name": VST_CATALOG[key]["label"], "style_role": st["role"]}
            note = st["note"]
            if st["want"]:
                keys = None
                try:
                    keys = lookup(path)
                except Exception:
                    log.debug("VST parametre listesi okunamadi: %s", path, exc_info=True)
                params: dict[str, float] = {}
                missing = []
                for pats, raw in st["want"]:
                    k = _match_param(keys, pats) if keys is not None else None
                    if k:
                        params[k] = max(0.0, min(1.0, float(raw)))
                    else:
                        missing.append(pats[0])
                if params:
                    fx["params"] = params
                if missing:
                    note = (note + "; " if note else "") + "ayarı eklenti penceresinden incelt (" + ", ".join(missing) + ")"
            else:
                note = (note + "; " if note else "") + "eklenti varsayılanıyla eklendi — ayarı pencereden incelt"
            if st["bypass"]:
                fx["bypass"] = True
            fx_out.append(fx)
            report.append({"role": st["role"], "label": st["label"], "engine": "vst", "plugin": VST_CATALOG[key]["label"],
                           "note": note})
            continue
        if not st["fallback"]:
            report.append({"role": st["role"], "label": st["label"], "engine": "skip", "plugin": "",
                           "note": "eklenti kurulu değil, yerleşik karşılığı yok — atlandı"})
            continue
        for fb in st["fallback"]:
            f = _sync_fx(dict(fb), st.get("sync", ""), bpm)
            f["style_role"] = st["role"]
            if st["bypass"]:
                f["bypass"] = True
            fx_out.append(beat_fx.clamp_fx(f))
        report.append({"role": st["role"], "label": st["label"], "engine": "builtin", "plugin": "",
                       "note": st.get("fb_note") or ("" if not st["vst"] else "tercih edilen eklenti yok — yerleşik efekt")})
    return {"fx": fx_out, "steps": report, "vst_total": vst_total, "vst_installed": vst_inst}


# ---------------- katman esleniği ----------------
def _mul(fx: dict[str, Any], key: str, k: float, default: float) -> None:
    fx[key] = float(fx.get(key, default)) * k


def _wide_fx(plugins: list[dict[str, Any]] | None, use_vst: bool, lookup) -> list[dict[str, Any]]:
    return resolve_steps([wide(("doubler", "wider", "mstereoexpander"))], plugins, use_vst, 0.0, lookup)["fx"]


def counterpart_fx(fx_list: list[dict[str, Any]], kind: str, plugins: list[dict[str, Any]] | None = None,
                   use_vst: bool = True, bpm: float = 0.0, lookup=None) -> list[dict[str, Any]]:
    """Ana vokal zincirinden katman esleniği:
    double: daha ince (HPF +40 Hz), daha sikisik (oran x1.25, esik -2 dB), daha kuru (reverb/delay x0.6) + genislik
    adlib : bant (HPF >= 220 Hz, LPF 7.5 kHz), daha cok delay (1/8, mix >= 0.2), reverb x1.3
    chant : HPF >= 160 Hz, koro (chorus) + daha genis reverb (x1.4, oda +0.15) + genislik"""
    out = [copy.deepcopy(f) for f in fx_list or [] if isinstance(f, dict)]
    for f in out:
        t = str(f.get("type") or "").lower()
        role = f.get("style_role", "")
        if t == "highpass":
            hz = float(f.get("cutoff_hz", 90.0))
            f["cutoff_hz"] = hz + 40.0 if kind == "double" else max(hz, 220.0 if kind == "adlib" else 160.0)
        elif t == "compressor" and kind == "double":
            f["ratio"] = float(f.get("ratio", 4.0)) * 1.25
            f["threshold_db"] = float(f.get("threshold_db", -18.0)) - 2.0
        elif t == "reverb":
            if kind == "double":
                _mul(f, "wet_level", 0.6, 0.12)
            elif kind == "adlib":
                _mul(f, "wet_level", 1.3, 0.12)
            else:
                _mul(f, "wet_level", 1.4, 0.12)
                f["room_size"] = float(f.get("room_size", 0.3)) + 0.15
        elif t == "delay":
            if kind == "double":
                _mul(f, "mix", 0.6, 0.15)
            elif kind == "adlib":
                f["mix"] = max(float(f.get("mix", 0.15)) * 1.4, 0.2)
        elif t == "vst3" and role in ("verb", "delay") and isinstance(f.get("params"), dict):
            k = {"double": 0.6, "adlib": 1.3, "chant": 1.4}[kind]
            for pk in list(f["params"]):
                if any(w in pk.lower() for w in ("mix", "wet")):
                    f["params"][pk] = float(f["params"][pk]) * k
    out = [beat_fx.clamp_fx(f) for f in out]
    types_ = [str(f.get("type") or "") for f in out]
    roles = [f.get("style_role", "") for f in out]

    def insert_before_space(items: list[dict[str, Any]]) -> None:
        i = next((j for j, f in enumerate(out) if f.get("style_role") in ("verb", "delay") or f.get("type") in ("reverb", "delay")), None)
        if i is None:
            i = next((j for j, f in enumerate(out) if f.get("type") == "limiter"), len(out))
        out[i:i] = items

    if kind == "adlib":
        if "lowpass" not in types_:
            i = next((j + 1 for j, t in enumerate(types_) if t == "highpass"), 0)
            out.insert(i, {"type": "lowpass", "cutoff_hz": 7500.0, "style_role": "lpf"})
        if "delay" not in types_ and "delay" not in roles:
            insert_before_space([{"type": "delay", "delay_seconds": delay_time(bpm, "1/8"), "feedback": 0.3, "mix": 0.2,
                                  "sync": "1/8", "style_role": "delay"}])
    if kind == "chant" and "chorus" not in types_:
        insert_before_space([dict(_chorus(0.8, 0.2, 0.25), style_role="chorus")])
    if kind in ("double", "chant") and "wide" not in roles:
        w = _wide_fx(plugins, use_vst, lookup)
        i = next((j for j, f in enumerate(out) if f.get("type") == "limiter"), len(out))
        out[i:i] = w
    return out


# ---------------- kullanici onayarlari ----------------
_USER_LOCK = threading.Lock()


def settings_dir() -> Path:
    d = paths.DATA_DIR / "beat_settings"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _user_file() -> Path:
    return settings_dir() / "user_presets.json"


def load_user_presets() -> list[dict[str, Any]]:
    fp = _user_file()
    if not fp.is_file():
        return []
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        log.warning("user_presets.json okunamadi", exc_info=True)
        return []
    items = data.get("presets") if isinstance(data, dict) else data
    return [p for p in items or [] if isinstance(p, dict) and p.get("id") and isinstance(p.get("fx"), list)]


def _save_user_presets(items: list[dict[str, Any]]) -> None:
    fp = _user_file()
    tmp = fp.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version": 1, "presets": items}, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(fp)


def save_user_preset(name: str, fx: list[dict[str, Any]], desc: str = "", genre: str = "",
                     denoise: bool = False, kind: str = "vocal") -> dict[str, Any]:
    nm = str(name or "").strip()[:60]
    if not nm:
        return {"ok": False, "error": "name_required"}
    chain = [beat_fx.clamp_fx(dict(f)) for f in fx or [] if isinstance(f, dict)]
    if not chain:
        return {"ok": False, "error": "empty_chain"}
    with _USER_LOCK:
        items = load_user_presets()
        same = next((p for p in items if p.get("name", "").lower() == nm.lower()), None)
        rec = {"id": same["id"] if same else "u_" + uuid.uuid4().hex[:8], "name": nm, "desc": str(desc or "")[:160],
               "genre": str(genre or "Kendi")[:30], "kind": kind if kind in ("vocal", "adlib") else "vocal",
               "denoise": bool(denoise), "fx": chain, "created": time.time()}
        items = [p for p in items if p["id"] != rec["id"]]
        items.insert(0, rec)
        _save_user_presets(items)
    return {"ok": True, "preset": rec}


def delete_user_preset(pid: str) -> dict[str, Any]:
    with _USER_LOCK:
        items = load_user_presets()
        left = [p for p in items if p.get("id") != pid]
        if len(left) == len(items):
            return {"ok": False, "error": "not_found"}
        _save_user_presets(left)
    return {"ok": True}


# ---------------- genel arayuz ----------------
def _split_id(preset_id: str) -> tuple[str, str]:
    base, _, kind = str(preset_id or "").partition(":")
    return base, (kind if kind in LAYER_KINDS else "")


def list_presets(plugins: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Kart izgarasi icin: kullanici onayarlari once, sonra yerlesik tarzlar (kurulu eklenti sayaciyla)."""
    inst = installed_map(plugins)
    out = []
    for u in load_user_presets():
        out.append({"id": u["id"], "name": u["name"], "desc": u.get("desc") or f"{len(u['fx'])} modül", "why": "",
                    "genre": u.get("genre") or "Kendi", "kind": u.get("kind") or "vocal", "user": True,
                    "vst_total": 0, "vst_installed": 0, "plugins": []})
    for p in PRESETS:
        want = [s for s in p["steps"] if s["vst"]]
        have = [VST_CATALOG[next(k for k in s["vst"] if k in inst)]["label"] for s in want if any(k in inst for k in s["vst"])]
        out.append({"id": p["id"], "name": p["name"], "desc": p["desc"], "why": p["why"], "genre": p["genre"],
                    "kind": p["kind"], "user": False, "vst_total": len(want), "vst_installed": len(have), "plugins": have})
    return {"ok": True, "presets": out, "intensity": DEFAULT_INTENSITY}


def resolve(preset_id: str, plugins: list[dict[str, Any]] | None = None, intensity: float = DEFAULT_INTENSITY,
            use_vst: bool = True, bpm: float = 0.0, param_lookup=None, use_sends: bool = False) -> dict[str, Any]:
    """Onayar kimligi ('hard', 'hard:double', 'u_ab12cd34') -> {fx, steps, name, ...}. Yogunluk en son uygulanir.
    2b: use_sends=True ise kanal sonundaki reverb/delay adimlari zincirden cikar, Reverb/Delay bus send'ine
    (dB) donusur -> sonucta 'sends'."""
    base, kind = _split_id(preset_id)
    user = next((u for u in load_user_presets() if u["id"] == base), None) if base.startswith("u_") else None
    if user is None and base not in _BY_ID:
        return {"ok": False, "error": "preset_not_found"}
    if user is not None:
        fx = [beat_fx.clamp_fx(dict(f)) for f in user["fx"]]
        res = {"fx": fx, "steps": [], "vst_total": 0, "vst_installed": 0}
        name, denoise, why = user["name"], bool(user.get("denoise")), user.get("desc") or ""
    else:
        p = _BY_ID[base]
        res = resolve_steps(p["steps"], plugins, use_vst, bpm, param_lookup)
        name, denoise, why = p["name"], False, p["why"]
    fx = res["fx"]
    if kind:
        fx = counterpart_fx(fx, kind, plugins, use_vst, bpm, param_lookup)
        name = f"{name} {KIND_NAMES[kind]}"
    fx = scale_chain(fx, intensity)
    notes = [f"{s['label']}: {s['note']}" for s in res["steps"] if s.get("note")]
    sends: dict[str, float] = {}
    if use_sends:
        from app.core import beat_mixbus
        fx, sends = beat_mixbus.chain_to_sends(fx)
        if sends:
            notes.append("Reverb/Delay kanal sonunda değil, bus send'i olarak: " + ", ".join(
                f"{'Reverb' if k == 'reverb' else 'Delay'} {v:+.0f} dB" for k, v in sends.items()))
    return {"ok": True, "id": preset_id, "base": base, "kind": kind, "name": name, "why": why, "fx": fx,
            "denoise": denoise, "steps": res["steps"], "vst_total": res["vst_total"],
            "vst_installed": res["vst_installed"], "notes": notes, "intensity": float(intensity), "use_vst": bool(use_vst),
            "use_sends": bool(use_sends), "sends": sends}


def layer_suggestions(tracks: list[dict[str, Any]], main_tid: str, preset_id: str) -> list[dict[str, Any]]:
    """Ana vokale tarz uygulaninca, ona bagli katman kanallarina (double/adlib/chant) esleniği onerisi."""
    base, kind = _split_id(preset_id)
    if kind:
        return []
    main = next((t for t in tracks or [] if t.get("id") == main_tid), None)
    if not main or main.get("layer"):
        return []
    known = {p["id"]: p["name"] for p in PRESETS}
    known.update({u["id"]: u["name"] for u in load_user_presets()})
    nm = known.get(base, base)
    out = []
    for t in tracks or []:
        lay = t.get("layer")
        if lay in LAYER_KINDS and (t.get("layer_of") or "vocal1") == main_tid:
            out.append({"track_id": t.get("id"), "track_name": t.get("name") or t.get("id"), "kind": lay,
                        "preset_id": f"{base}:{lay}", "name": f"{nm} {KIND_NAMES[lay]}"})
    return out


# ---------------- adlib hizli efektleri + efekt atmalari ----------------
def _phone_fx() -> list[dict[str, Any]]:
    return [_hpf(450), _lpf(3400), _peak(1800, 5.0, 1.0), _dist(8.0)]


ADLIB_KINDS = {
    "phone": "Telefon", "high": "İnce ses", "low": "Kalın ses", "whisper": "Fısıltı / yakın",
    "autopan": "Otomatik pan", "echo_tail": "Yankı kuyruğu",
}
THROW_KINDS = {"delay": "Yankı at", "reverb": "Reverb at", "phone": "Telefon at", "reverse": "Ters reverb"}
PITCH_HIGH, PITCH_LOW = 4.0, -4.0           # yarim ton (formant korumasi yok: duz PitchShift)
AUTOPAN_AMOUNT = 0.5


def quick_fx(kind: str, bpm: float = 0.0, note: str = "1/8d") -> dict[str, Any]:
    """Adlib hizli efekti ya da atma tarifi: {fx, tail_sec, head_sec, label, mode}.
    mode: 'append' (klip fx'ine eklenir) | 'autopan' (klip pan'i) | 'throw' (bolge bolunur, ortaya efekt + kuyruk)."""
    k = str(kind or "")
    if k.startswith("throw_"):
        t = k[6:]
        if t == "delay":
            sec = delay_time(bpm, note)
            fb = 0.45
            return {"ok": True, "kind": k, "mode": "throw", "label": f"{THROW_KINDS['delay']} ({SYNC_LABELS.get(note, note)})",
                    "fx": [dict(_delay(sec, fb, 0.3), sync=note), {"type": "gain", "gain_db": 2.5}],
                    "tail_sec": delay_tail(sec, fb), "head_sec": 0.0}
        if t == "reverb":
            return {"ok": True, "kind": k, "mode": "throw", "label": THROW_KINDS["reverb"],
                    "fx": [_verb(0.85, 0.45, 0.4, 1.0)], "tail_sec": 3.0, "head_sec": 0.0}
        if t == "phone":
            return {"ok": True, "kind": k, "mode": "throw", "label": THROW_KINDS["phone"], "fx": _phone_fx(),
                    "tail_sec": 0.0, "head_sec": 0.0}
        if t == "reverse":
            return {"ok": True, "kind": k, "mode": "throw", "label": THROW_KINDS["reverse"],
                    "fx": [{"type": "reverse_reverb", "room_size": 0.85, "damping": 0.5, "wet_level": 0.6, "dry_level": 1.0}],
                    "tail_sec": 0.0, "head_sec": 1.2}
        return {"ok": False, "error": "unknown_kind"}
    if k == "phone":
        return {"ok": True, "kind": k, "mode": "append", "label": ADLIB_KINDS[k], "fx": _phone_fx(), "tail_sec": 0.0, "head_sec": 0.0}
    if k in ("high", "low"):
        st = PITCH_HIGH if k == "high" else PITCH_LOW
        return {"ok": True, "kind": k, "mode": "append", "label": f"{ADLIB_KINDS[k]} ({st:+g} yarım ton)",
                "fx": [{"type": "pitchshift", "semitones": st}], "tail_sec": 0.0, "head_sec": 0.0}
    if k == "whisper":
        return {"ok": True, "kind": k, "mode": "append", "label": ADLIB_KINDS[k],
                "fx": [_hpf(300), _dist(5.0), _hshelf(8000, 3.0), _verb(0.25, 0.15, 0.5, 0.95)], "tail_sec": 0.6, "head_sec": 0.0}
    if k == "autopan":
        return {"ok": True, "kind": k, "mode": "autopan", "label": ADLIB_KINDS[k], "fx": [], "amount": AUTOPAN_AMOUNT,
                "tail_sec": 0.0, "head_sec": 0.0}
    if k == "echo_tail":
        r = quick_fx("throw_delay", bpm, note)
        r.update(kind=k, mode="echo_tail", label=f"{ADLIB_KINDS[k]} ({SYNC_LABELS.get(note, note)})",
                 region_sec=round(60.0 / (float(bpm) if bpm and float(bpm) > 0 else 120.0), 6))
        return r
    return {"ok": False, "error": "unknown_kind"}


def _set_tail(c: dict[str, Any], recipe: dict[str, Any]) -> None:
    if recipe.get("tail_sec"):
        c["tail_sec"] = max(float(c.get("tail_sec") or 0.0), float(recipe["tail_sec"]))
    if recipe.get("head_sec"):
        c["head_sec"] = max(float(c.get("head_sec") or 0.0), float(recipe["head_sec"]))


def apply_throw(clips: list[dict[str, Any]], clip_id: str, t0: float, t1: float, recipe: dict[str, Any],
                ids: Any = None) -> dict[str, Any]:
    """Atma: [t0, t1) bolgesi ayri klip olur (region_split, 10 ms capraz gecis), ortadaki parcaya tarifin fx'i
    ve kuyrugu (tail_sec / head_sec) yazilir. Dondurur {clips, mid_id}."""
    r = beat_clips.region_split(clips, clip_id, t0, t1, beat_clips.XFADE, ids, recipe.get("fx") or [])
    if r["mid_id"]:
        for c in r["clips"]:
            if c.get("id") == r["mid_id"]:
                _set_tail(c, recipe)
    return r


def alternate_pan(clips: list[dict[str, Any]], ids: list[str], amount: float = AUTOPAN_AMOUNT) -> list[dict[str, Any]]:
    """Otomatik pan (pedalboard'da kanal pan otomasyonu yok): hedef klipler baslangic sirasina gore donusumlu
    sol/sag (-amount, +amount, ...). Ayni destedeki take'ler ayni pan'i alir."""
    out = [dict(c) for c in clips]
    want = set(ids or [])
    tg = [c for c in out if c.get("id") in want]
    groups: list[str] = []
    for c in sorted(tg, key=lambda x: (float(x.get("start") or 0.0), str(x.get("id")))):
        g = str(c.get("stack_id") or c.get("id"))
        if g not in groups:
            groups.append(g)
    a = max(0.0, min(1.0, float(amount)))
    for c in tg:
        i = groups.index(str(c.get("stack_id") or c.get("id")))
        c["pan"] = beat_clips.r6(-a if i % 2 == 0 else a)
    return out


def apply_adlib(clips: list[dict[str, Any]], ids: list[str], recipe: dict[str, Any], id_gen: Any = None) -> dict[str, Any]:
    """Adlib hizli efektini hedef kliplere uygular (tek islem = tek geri al). Dondurur {clips, ids}."""
    mode = recipe.get("mode")
    if mode == "autopan":
        return {"clips": alternate_pan(clips, ids, float(recipe.get("amount", AUTOPAN_AMOUNT))), "ids": list(ids)}
    if mode == "echo_tail":
        out = [dict(c) for c in clips]
        made = []
        reg = float(recipe.get("region_sec") or 0.5)
        tg = sorted([c for c in out if c.get("id") in set(ids)], key=lambda x: -float(x.get("start") or 0.0))
        for c in tg:
            s, e = beat_clips.clip_bounds(c)
            r = apply_throw(out, c["id"], max(s, e - reg), e, recipe, id_gen)
            out = r["clips"]
            if r["mid_id"]:
                made.append(r["mid_id"])
        return {"clips": out, "ids": made}
    out = []
    want = set(ids or [])
    for c in clips:
        d = dict(c)
        if d.get("id") in want:
            d["fx"] = [dict(f) for f in (d.get("fx") or []) if isinstance(f, dict)] + [dict(f) for f in recipe.get("fx") or []]
            _set_tail(d, recipe)
        out.append(d)
    return {"clips": out, "ids": list(ids)}


def catalog() -> dict[str, Any]:
    return {"ok": True, "adlib": [{"kind": k, "label": v} for k, v in ADLIB_KINDS.items()],
            "throws": [{"kind": "throw_" + k, "label": v} for k, v in THROW_KINDS.items()],
            "sync": [{"note": k, "label": SYNC_LABELS[k]} for k in ("1/4", "1/8", "1/8d")]}
