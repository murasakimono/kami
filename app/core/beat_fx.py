"""Kami Beat Revize 4: efekt semasi, efekt zinciri isleme (pedalboard / zarif yedek), VST3 parametreleri ve
eklentinin kendi penceresi.

- FX_SCHEMA: yerlesik efektlerin parametre tablosu (ad, birim, aralik, varsayilan). Anahtarlar mevcut fx
  sozluklerinin (VOCAL_PRESETS, beat_mcp) anahtarlariyla birebir ayni; arayuz (beat.js) surguleri bu tablodan
  kurar (api.beat_fx_schema).
- process(data, sr, fx_list, denoise): (N,2) float32 diziyi zincirden gecirir. pedalboard yoksa (bu Linux
  test ortami gibi) yalniz saf numpy ile birebir yapilabilen efektler (gain) uygulanir, digerleri atlanir ve
  'skipped' olarak bildirilir -> uygulama cokmeden kuru/yarim efektli calar.
- VST3: load_plugin onbellekli havuz (ayni eklenti iki is parcaciginda ayni anda kullanilmaz), durum
  (state_b64 = plugin.raw_state) veya parametre degerleri (params = {ad: raw 0..1}) her islemede uygulanir.
- vst_params(path): eklentinin parametre listesi (onbellekli; onemli ilk 24 + arama).
- open_editor(path, state_b64): plugin.show_editor() bloklar -> ayri SURECTE (python -m app.core.beat_fx
  --vst-editor / Kami.exe --vst-editor) calisir, pencere kapaninca durum JSON dosyasindan geri okunur.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import math
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _p(key: str, label: str, unit: str, lo: float, hi: float, default: float, step: float,
       pb: str | None = None, scale: str = "lin") -> dict[str, Any]:
    return {"key": key, "label": label, "unit": unit, "min": lo, "max": hi, "default": default, "step": step,
            "pb": pb or key, "scale": scale}


# type -> {label, group, pb (pedalboard sinifi), params:[...], fixed:{pb_kwarg: deger}}
FX_SCHEMA: dict[str, dict[str, Any]] = {
    "highpass": {"label": "Highpass", "group": "EQ", "pb": "HighpassFilter", "params": [
        _p("cutoff_hz", "Kesim", "Hz", 20.0, 2000.0, 90.0, 1.0, "cutoff_frequency_hz", "log")]},
    "lowpass": {"label": "Lowpass", "group": "EQ", "pb": "LowpassFilter", "params": [
        _p("cutoff_hz", "Kesim", "Hz", 500.0, 20000.0, 12000.0, 10.0, "cutoff_frequency_hz", "log")]},
    "peak": {"label": "Parametric EQ", "group": "EQ", "pb": "PeakFilter", "params": [
        _p("cutoff_hz", "Frekans", "Hz", 20.0, 20000.0, 1000.0, 1.0, "cutoff_frequency_hz", "log"),
        _p("gain_db", "Kazanç", "dB", -24.0, 24.0, 0.0, 0.1),
        _p("q", "Q", "", 0.1, 10.0, 1.0, 0.01)]},
    "lowshelf": {"label": "Low Shelf", "group": "EQ", "pb": "LowShelfFilter", "params": [
        _p("cutoff_hz", "Frekans", "Hz", 20.0, 2000.0, 150.0, 1.0, "cutoff_frequency_hz", "log"),
        _p("gain_db", "Kazanç", "dB", -24.0, 24.0, 0.0, 0.1),
        _p("q", "Q", "", 0.1, 4.0, 0.707, 0.01)]},
    "highshelf": {"label": "High Shelf", "group": "EQ", "pb": "HighShelfFilter", "params": [
        _p("cutoff_hz", "Frekans", "Hz", 1000.0, 20000.0, 8000.0, 10.0, "cutoff_frequency_hz", "log"),
        _p("gain_db", "Kazanç", "dB", -24.0, 24.0, 0.0, 0.1),
        _p("q", "Q", "", 0.1, 4.0, 0.707, 0.01)]},
    "deesser": {"label": "De-Esser", "group": "Dinamik", "pb": "PeakFilter", "fixed": {"q": 2.2}, "params": [
        _p("freq_hz", "Frekans", "Hz", 2000.0, 12000.0, 6800.0, 10.0, "cutoff_frequency_hz", "log"),
        _p("gain_db", "Azaltma", "dB", -18.0, 0.0, -4.0, 0.1)]},
    "compressor": {"label": "Compressor", "group": "Dinamik", "pb": "Compressor", "params": [
        _p("threshold_db", "Eşik", "dB", -60.0, 0.0, -18.0, 0.1),
        _p("ratio", "Oran", ":1", 1.0, 20.0, 4.0, 0.1),
        _p("attack_ms", "Atak", "ms", 0.1, 200.0, 8.0, 0.1, scale="log"),
        _p("release_ms", "Bırakma", "ms", 5.0, 1000.0, 85.0, 1.0, scale="log")]},
    "noisegate": {"label": "Noise Gate", "group": "Dinamik", "pb": "NoiseGate", "params": [
        _p("threshold_db", "Eşik", "dB", -80.0, 0.0, -42.0, 0.5),
        _p("ratio", "Oran", ":1", 1.0, 20.0, 6.0, 0.1),
        _p("attack_ms", "Atak", "ms", 0.1, 100.0, 1.0, 0.1, scale="log"),
        _p("release_ms", "Bırakma", "ms", 5.0, 1000.0, 100.0, 1.0, scale="log")]},
    "limiter": {"label": "Limiter", "group": "Dinamik", "pb": "Limiter", "params": [
        _p("threshold_db", "Eşik", "dB", -24.0, 0.0, -1.0, 0.1),
        _p("release_ms", "Bırakma", "ms", 1.0, 1000.0, 100.0, 1.0, scale="log")]},
    "gain": {"label": "Gain", "group": "Dinamik", "pb": "Gain", "params": [
        _p("gain_db", "Kazanç", "dB", -24.0, 24.0, 0.0, 0.1)]},
    "distortion": {"label": "Saturator", "group": "Renk", "pb": "Distortion", "params": [
        _p("drive_db", "Sürüş", "dB", 0.0, 40.0, 3.0, 0.1)]},
    "chorus": {"label": "Chorus", "group": "Modülasyon", "pb": "Chorus", "params": [
        _p("rate_hz", "Hız", "Hz", 0.05, 10.0, 1.0, 0.01, scale="log"),
        _p("depth", "Derinlik", "%", 0.0, 1.0, 0.25, 0.01),
        _p("centre_delay_ms", "Gecikme", "ms", 1.0, 30.0, 7.0, 0.1),
        _p("feedback", "Geri besleme", "%", -0.95, 0.95, 0.0, 0.01),
        _p("mix", "Karışım", "%", 0.0, 1.0, 0.5, 0.01)]},
    "pitchshift": {"label": "Pitch Shift", "group": "Pitch", "pb": "PitchShift", "params": [
        _p("semitones", "Yarım ton", "st", -12.0, 12.0, 0.0, 0.1)]},
    "delay": {"label": "Delay", "group": "Alan", "pb": "Delay", "params": [
        _p("delay_seconds", "Süre", "sn", 0.01, 2.0, 0.25, 0.005),
        _p("feedback", "Geri besleme", "%", 0.0, 0.95, 0.2, 0.01),
        _p("mix", "Karışım", "%", 0.0, 1.0, 0.15, 0.01)]},
    "reverb": {"label": "Reverb", "group": "Alan", "pb": "Reverb", "params": [
        _p("room_size", "Oda", "%", 0.0, 1.0, 0.25, 0.01),
        _p("damping", "Sönüm", "%", 0.0, 1.0, 0.5, 0.01),
        _p("wet_level", "Islak", "%", 0.0, 1.0, 0.12, 0.01),
        _p("dry_level", "Kuru", "%", 0.0, 1.0, 0.9, 0.01),
        _p("width", "Genişlik", "%", 0.0, 1.0, 1.0, 0.01)]},
}

VST_PARAM_TOP = 24          # cok parametreli eklentide arayuzde ilk gosterilen
_IMPORTANT = ("mix", "dry", "wet", "gain", "output", "input", "volume", "level", "threshold", "ratio", "attack",
              "release", "knee", "freq", "cutoff", "q", "drive", "sat", "pitch", "correction", "speed", "key",
              "scale", "size", "decay", "time", "feedback", "width", "depth", "rate", "tone", "ceiling", "amount")
_UNIMPORTANT = ("bypass", "midi", "cc ", "program", "preset", "learn", "oversampl", "latency", "ui ", "gui",
                "zoom", "theme", "license", "meter", "display")


def schema_public() -> dict[str, Any]:
    """Arayuz icin sema (pb alan adlari dahil degil; gerek yok ama zarar da yok)."""
    return {k: {"label": v["label"], "group": v["group"],
                "params": [{x: p[x] for x in ("key", "label", "unit", "min", "max", "default", "step", "scale")}
                           for p in v["params"]]}
            for k, v in FX_SCHEMA.items()}


def default_fx(fx_type: str) -> dict[str, Any] | None:
    sc = FX_SCHEMA.get(str(fx_type or "").lower())
    if not sc:
        return None
    out: dict[str, Any] = {"type": str(fx_type).lower()}
    for p in sc["params"]:
        out[p["key"]] = p["default"]
    return out


def _f(v: Any, d: float) -> float:
    if isinstance(v, bool):
        return d
    try:
        x = float(v)
    except (TypeError, ValueError):
        return d
    return x if math.isfinite(x) else d


def clamp_fx(fx: dict[str, Any]) -> dict[str, Any]:
    """Semadaki parametreleri araliga sikistirir (kopya). Bilinmeyen tur / VST oldugu gibi doner."""
    out = dict(fx or {})
    sc = FX_SCHEMA.get(str(out.get("type") or "").lower())
    if not sc:
        if str(out.get("type") or "").lower() == "vst3" and isinstance(out.get("params"), dict):
            out["params"] = {str(k): max(0.0, min(1.0, _f(v, 0.0))) for k, v in out["params"].items()}
        return out
    for p in sc["params"]:
        if p["key"] in out:
            out[p["key"]] = max(p["min"], min(p["max"], _f(out[p["key"]], p["default"])))
    return out


def fx_kwargs(fx: dict[str, Any]) -> tuple[str, dict[str, float]] | None:
    """Yerlesik efekt -> (pedalboard sinif adi, kwargs). Eksik parametre semadaki varsayilan; aralik sinirli."""
    t = str((fx or {}).get("type") or "").lower()
    sc = FX_SCHEMA.get(t)
    if not sc:
        return None
    c = clamp_fx(fx)
    kw = {p["pb"]: float(c.get(p["key"], p["default"])) for p in sc["params"]}
    kw.update(sc.get("fixed") or {})
    return sc["pb"], kw


def active_fx(fx_list: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [fx for fx in (fx_list or []) if isinstance(fx, dict) and not fx.get("bypass")]


def chain_hash(fx_list: list[dict[str, Any]] | None, denoise: bool = False) -> str:
    """Zincirin duyulan icerigini ozetler (bypass'li moduller ve gorsel alanlar haric)."""
    keep = []
    for fx in active_fx(fx_list):
        d = {k: v for k, v in fx.items() if k not in ("name", "ui", "id", "bypass")}
        keep.append(d)
    raw = json.dumps({"fx": keep, "dn": bool(denoise)}, sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


# ---------------- pedalboard erisimi (testte sahte modul enjekte edilebilir) ----------------
_PB_OVERRIDE: Any = None


def pedalboard_module():
    """pedalboard modulu ya da None. Testler _PB_OVERRIDE ile sahte (mock) modul verir."""
    if _PB_OVERRIDE is not None:
        return _PB_OVERRIDE or None
    try:
        import pedalboard as pb
        return pb
    except Exception:
        return None


def available() -> dict[str, Any]:
    pb = pedalboard_module()
    return {"pedalboard": pb is not None, "vst": pb is not None and hasattr(pb, "load_plugin"),
            "editor": pb is not None and os.name == "nt"}


# ---------------- VST3 havuzu ----------------
class _PluginPool:
    """Ayni yoldaki eklenti icin bos ornek havuzu: ayni ornek iki is parcaciginda ayni anda kullanilmaz;
    load_plugin (yavas olabilir) her islemede tekrarlanmaz."""

    def __init__(self) -> None:
        self._free: dict[str, list[Any]] = {}
        self._lock = threading.Lock()

    def acquire(self, pb, path: str):
        with self._lock:
            lst = self._free.get(path) or []
            if lst:
                return lst.pop()
        return pb.load_plugin(path)

    def release(self, path: str, plugin: Any) -> None:
        with self._lock:
            lst = self._free.setdefault(path, [])
            if len(lst) < 3:
                lst.append(plugin)

    def clear(self) -> None:
        with self._lock:
            self._free.clear()


POOL = _PluginPool()


def apply_vst_state(plugin: Any, fx: dict[str, Any]) -> None:
    """state_b64 (eklentinin kendi penceresinden) once, sonra params (surgulerden) uygulanir."""
    st = fx.get("state_b64")
    if st:
        try:
            plugin.raw_state = base64.b64decode(st)
        except Exception:
            log.debug("VST durumu yuklenemedi", exc_info=True)
    params = fx.get("params")
    if isinstance(params, dict) and params:
        table = getattr(plugin, "parameters", {}) or {}
        for k, v in params.items():
            prm = table.get(k)
            if prm is None:
                continue
            try:
                prm.raw_value = max(0.0, min(1.0, float(v)))
            except Exception:
                log.debug("VST parametresi ayarlanamadi: %s", k, exc_info=True)


def build_plugins(pb, fx_list: list[dict[str, Any]] | None) -> tuple[list[Any], list[tuple[str, Any]], list[str]]:
    """pedalboard eklenti listesi + havuza geri verilecek VST'ler + atlanan moduller."""
    plugins: list[Any] = []
    borrowed: list[tuple[str, Any]] = []
    skipped: list[str] = []
    for fx in active_fx(fx_list):
        t = str(fx.get("type") or "").lower()
        try:
            if t == "vst3":
                vp = str(fx.get("path") or "")
                if not vp or not os.path.exists(vp) or not hasattr(pb, "load_plugin"):
                    skipped.append(fx.get("name") or "vst3")
                    continue
                plg = POOL.acquire(pb, vp)
                apply_vst_state(plg, fx)
                plugins.append(plg)
                borrowed.append((vp, plg))
                continue
            spec = fx_kwargs(fx)
            if spec is None or not hasattr(pb, spec[0]):
                skipped.append(t or "?")
                continue
            plugins.append(getattr(pb, spec[0])(**spec[1]))
        except Exception:
            log.debug("FX dugumu eklenemedi: %s", fx, exc_info=True)
            skipped.append(t or "?")
    return plugins, borrowed, skipped


def _numpy_fallback(data, fx: dict[str, Any]):
    """pedalboard yokken birebir yapilabilen efektler (dogrusal). Desteklenmiyorsa None."""
    t = str(fx.get("type") or "").lower()
    if t == "gain":
        g = 10.0 ** (_f(clamp_fx(fx).get("gain_db"), 0.0) / 20.0)
        return (data * g).astype("float32")
    return None


def process(data, sr: int, fx_list: list[dict[str, Any]] | None, denoise: bool = False,
            denoise_fn=None) -> tuple[Any, dict[str, Any]]:
    """(N,2) float32 -> (N,2) float32 (ayni uzunluk). info: {engine, applied, skipped}."""
    import numpy as np
    info: dict[str, Any] = {"engine": "none", "applied": 0, "skipped": []}
    out = np.asarray(data, dtype="float32")
    if denoise and denoise_fn is not None and len(out):
        try:
            out = denoise_fn(out, sr)
            info["applied"] += 1
        except Exception:
            log.debug("denoise atlandi", exc_info=True)
            info["skipped"].append("denoise")
    act = active_fx(fx_list)
    if not act or not len(out):
        return out, info
    pb = pedalboard_module()
    if pb is not None:
        plugins, borrowed, skipped = build_plugins(pb, act)
        info["engine"] = "pedalboard"
        info["skipped"] += skipped
        try:
            if plugins:
                board = pb.Pedalboard(plugins)
                res = board(np.ascontiguousarray(out.T), sr)     # pedalboard (kanal, ornek) bekler
                res = np.asarray(res, dtype="float32").T
                n = len(out)
                if len(res) < n:                                  # uzunluk korunur (zaman hizasi)
                    res = np.concatenate([res, np.zeros((n - len(res), res.shape[1]), dtype="float32")])
                if res.shape[1] == 1:
                    res = np.repeat(res, 2, axis=1)
                out = np.ascontiguousarray(res[:n, :2])
                info["applied"] += len(plugins)
        finally:
            for vp, plg in borrowed:
                POOL.release(vp, plg)
        return out, info
    info["engine"] = "numpy"
    for fx in act:
        r = _numpy_fallback(out, fx)
        if r is None:
            info["skipped"].append(str(fx.get("type") or "?"))
        else:
            out = r
            info["applied"] += 1
    return out, info


# ---------------- VST3 parametreleri ----------------
_PARAM_CACHE: dict[tuple[str, float], list[dict[str, Any]]] = {}
_PARAM_LOCK = threading.Lock()


def _param_score(name: str, idx: int) -> float:
    n = name.lower()
    s = 0.0
    if any(k in n for k in _IMPORTANT):
        s += 10.0
    if any(k in n for k in _UNIMPORTANT):
        s -= 20.0
    return s - idx * 0.01     # esitlikte eklentinin kendi sirasi


def _describe_param(key: str, prm: Any) -> dict[str, Any]:
    def g(attr, d=None):
        try:
            return getattr(prm, attr)
        except Exception:
            return d
    rng = g("range") or (None, None, None)
    vals = g("valid_values") or []
    try:
        vals = [str(v) for v in list(vals)[:64]]
    except Exception:
        vals = []
    return {
        "key": key, "label": str(g("name", key) or key), "unit": str(g("units", "") or g("label", "") or ""),
        "raw": _f(g("raw_value", 0.0), 0.0), "default_raw": _f(g("default_raw_value", g("raw_value", 0.0)), 0.0),
        "text": str(g("string_value", "") or ""),
        "min": rng[0] if isinstance(rng, (tuple, list)) and len(rng) > 0 else None,
        "max": rng[1] if isinstance(rng, (tuple, list)) and len(rng) > 1 else None,
        "boolean": bool(g("is_boolean", False)), "steps": int(_f(g("num_steps", 0), 0)) if g("is_discrete", False) else 0,
        "choices": vals if g("is_discrete", False) and 0 < len(vals) <= 64 else [],
    }


def vst_params(path: str, query: str = "", limit: int = VST_PARAM_TOP, refresh: bool = False) -> dict[str, Any]:
    """Eklentinin parametreleri. Onemli ilk `limit` (query bossa) veya ada gore arama sonuclari.
    Liste (path, mtime) anahtariyla onbelleklenir."""
    pb = pedalboard_module()
    if pb is None or not hasattr(pb, "load_plugin"):
        return {"ok": False, "error": "pedalboard_missing", "params": []}
    if not path or not os.path.exists(path):
        return {"ok": False, "error": "plugin_not_found", "params": []}
    try:
        mt = os.path.getmtime(path)
    except OSError:
        mt = 0.0
    key = (str(path), mt)
    with _PARAM_LOCK:
        cached = None if refresh else _PARAM_CACHE.get(key)
    if cached is None:
        plg = None
        try:
            plg = POOL.acquire(pb, path)
            table = getattr(plg, "parameters", {}) or {}
            cached = [_describe_param(k, prm) for k, prm in table.items()]
        except Exception as exc:
            log.warning("VST parametreleri okunamadi: %s", path, exc_info=True)
            return {"ok": False, "error": str(exc)[:160], "params": []}
        finally:
            if plg is not None:
                POOL.release(path, plg)
        with _PARAM_LOCK:
            _PARAM_CACHE[key] = cached
    q = str(query or "").strip().lower()
    if q:
        hits = [p for p in cached if q in p["key"].lower() or q in p["label"].lower()]
    else:
        order = sorted(range(len(cached)), key=lambda i: -_param_score(cached[i]["label"] or cached[i]["key"], i))
        hits = [cached[i] for i in order]
    lim = max(1, int(limit or VST_PARAM_TOP))
    return {"ok": True, "params": hits[:lim], "total": len(cached), "more": max(0, len(hits) - lim)}


# ---------------- Eklentinin kendi penceresi (ayri surec) ----------------
def _editor_cmd(path: str, in_file: str, out_file: str) -> list[str]:
    from app import paths
    if paths.FROZEN:
        return [sys.executable, "--vst-editor", path, in_file, out_file]
    return [sys.executable, "-m", "app.core.beat_fx", "--vst-editor", path, in_file, out_file]


def open_editor(path: str, state_b64: str = "", params: dict[str, Any] | None = None,
                timeout: float = 6 * 3600) -> dict[str, Any]:
    """Eklentinin kendi penceresini ayri surecte acar; pencere kapaninca {ok, state_b64, params} doner.
    show_editor() bloklar ve kendi mesaj dongusunu ister -> ana surecin (pywebview) donmasini onlemek icin
    ayri surec. Arka plan isi olarak cagrilir (api.job_start)."""
    av = available()
    if not av["pedalboard"]:
        return {"ok": False, "error": "pedalboard_missing"}
    if not av["editor"]:
        return {"ok": False, "error": "editor_windows_only"}
    if not path or not os.path.exists(path):
        return {"ok": False, "error": "plugin_not_found"}
    tmp = Path(tempfile.mkdtemp(prefix="kami_vst_"))
    in_f, out_f = tmp / "in.json", tmp / "out.json"
    in_f.write_text(json.dumps({"state_b64": state_b64 or "", "params": params or {}}), encoding="utf-8")
    try:
        from app import paths
        subprocess.run(_editor_cmd(path, str(in_f), str(out_f)), cwd=str(paths.ROOT), timeout=timeout,
                       creationflags=NO_WINDOW, capture_output=True)
        return read_editor_result(str(out_f))
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "editor_timeout"}
    except Exception as exc:
        log.warning("VST penceresi acilamadi", exc_info=True)
        return {"ok": False, "error": str(exc)[:160]}
    finally:
        for f in (in_f, out_f):
            try:
                f.unlink()
            except OSError:
                pass
        try:
            tmp.rmdir()
        except OSError:
            pass


def read_editor_result(out_file: str) -> dict[str, Any]:
    try:
        d = json.loads(Path(out_file).read_text(encoding="utf-8"))
    except Exception:
        return {"ok": False, "error": "editor_no_result"}
    if not d.get("ok"):
        return {"ok": False, "error": str(d.get("error") or "editor_failed")}
    return {"ok": True, "state_b64": str(d.get("state_b64") or ""), "params": d.get("params") or {}}


def editor_child_main(path: str, in_file: str, out_file: str) -> int:
    """Alt surec: eklentiyi yukle, durumu uygula, show_editor() (pencere kapanana dek bloklar), durumu yaz."""
    res: dict[str, Any] = {"ok": False}
    try:
        pb = pedalboard_module()
        if pb is None:
            raise RuntimeError("pedalboard_missing")
        try:
            inp = json.loads(Path(in_file).read_text(encoding="utf-8"))
        except Exception:
            inp = {}
        plg = pb.load_plugin(path)
        apply_vst_state(plg, {"state_b64": inp.get("state_b64"), "params": inp.get("params")})
        plg.show_editor()
        raw = b""
        try:
            raw = bytes(plg.raw_state)
        except Exception:
            log.debug("raw_state okunamadi", exc_info=True)
        vals: dict[str, float] = {}
        for k, prm in (getattr(plg, "parameters", {}) or {}).items():
            try:
                vals[k] = float(prm.raw_value)
            except Exception:
                continue
        res = {"ok": True, "state_b64": base64.b64encode(raw).decode("ascii") if raw else "", "params": vals}
    except Exception as exc:
        res = {"ok": False, "error": str(exc)[:200]}
    Path(out_file).write_text(json.dumps(res), encoding="utf-8")
    return 0 if res.get("ok") else 1


if __name__ == "__main__":   # python -m app.core.beat_fx --vst-editor <path> <in.json> <out.json>
    if len(sys.argv) >= 5 and sys.argv[1] == "--vst-editor":
        raise SystemExit(editor_child_main(sys.argv[2], sys.argv[3], sys.argv[4]))
    raise SystemExit(2)
