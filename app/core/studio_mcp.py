"""Kami Studio MCP sunucusu (stdio). Claude, Studio'da acik projeyi okur/duzenler; Studio dosya degisince kendini yeniler.

Calistirma: gelistirmede `python -m app.core.studio_mcp`, kurulu Kami'de `Kami.exe --studio-mcp`.
Bagimliliksiz, satir basina bir JSON-RPC mesaji (MCP stdio tasimasi).
"""
from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any, Callable

from app.core import studio as S

PROTO = "2025-06-18"
CURRENT = S.CACHE / "current.json"


def _ffmpeg() -> str:
    try:
        from app.engines.ytdlp_engine import find_ffmpeg
        return find_ffmpeg()
    except Exception:
        import shutil
        return shutil.which("ffmpeg") or ""


ST = S.Studio(_ffmpeg)


def cur_path(path: str = "") -> str:
    if path:
        return path
    try:
        p = json.loads(CURRENT.read_text("utf-8")).get("path", "")
    except (OSError, ValueError):
        p = ""
    if not p or not os.path.isfile(p):
        raise RuntimeError("Studio'da açık proje yok. Önce new_project ya da open_project kullan (veya Kami Studio'da bir proje aç).")
    return p


def load(path: str = "") -> tuple[str, dict]:
    p = cur_path(path)
    return p, S.load_project(p)


def save(p: str, pr: dict) -> None:
    S.save_project(p, pr)


def _set_current(p: str) -> None:
    CURRENT.parent.mkdir(parents=True, exist_ok=True)
    CURRENT.write_text(json.dumps({"path": p, "by": "mcp", "t": time.time()}), "utf-8")


# ---------------------------------------------------------------------------------------------------------------
TOOLS: dict[str, dict[str, Any]] = {}


def tool(name: str, desc: str, props: dict[str, Any], required: list[str] | None = None):
    def deco(fn: Callable[..., Any]):
        TOOLS[name] = {"fn": fn, "schema": {"name": name, "description": desc,
                                            "inputSchema": {"type": "object", "properties": props, "required": required or []}}}
        return fn
    return deco


N = {"type": "number"}
STR = {"type": "string"}
PATH = {"type": "string", "description": "Proje yolu (boş: Studio'da açık olan)"}


@tool("get_project", "Açık projenin özeti: izler, varlıklar (assets), klipler (zaman sn), işaretler. Düzenlemeden önce çağır.", {"path": PATH})
def t_get(path: str = "") -> Any:
    p, pr = load(path)
    return {"path": p, **S.summary(pr)}


@tool("get_clip", "Bir klibin tüm alanları (stil, zoom kareleri, efektler).", {"id": STR, "path": PATH}, ["id"])
def t_get_clip(id: str, path: str = "") -> Any:
    _, pr = load(path)
    return S.find_clip(pr, id)


@tool("catalog", "Kullanılabilir efekt modları (fx), geçişler, zoom şablonları, altyazı stilleri, metin animasyonları, abone animasyonları, "
      "çıkartmalar (stickers), karışım modları (blends), maskeler, bezier önayarları (bezierPresets), EQ/ses eğrileri ve fontlar.", {})
def t_catalog() -> Any:
    c = S.catalog()
    return {"fx": {k: f"{v['name']} [{v['pack']}]" for k, v in c["fx"].items()}, "trans": c["trans"],
            "zoom": [{"id": z["id"], "name": z["name"]} for z in c["zoom"]], "captions": c["captions"], "anims": c["anims"],
            "subscribe": c["subscribe"], "graphics": c["graphics"], "stickers": {k: v["name"] for k, v in c.get("stickers", {}).items()},
            "templates": c["templates"], "afx": c["afx"], "deliver": c["deliver"],
            "blends": c["blends"], "masks": c["masks"], "bezierPresets": c["bezierPresets"],
            "eqPresets": c["eqPresets"], "audioCurves": c["audioCurves"],
            "tanim": c["tanim"], "canim": {k: ({i: (v["name"] if isinstance(v, dict) else v) for i, v in d.items()}) for k, d in c["canim"].items()}}


@tool("new_project", "Yeni proje oluşturur ve Studio'nun açık projesi yapar. Dikey video için w=1080,h=1920.",
      {"name": STR, "w": N, "h": N, "fps": N, "path": STR}, ["name"])
def t_new(name: str, w: float = 1920, h: float = 1080, fps: float = 30, path: str = "") -> Any:
    pr = S.new_project(name, int(w), int(h), int(fps))
    p = path or str(S.home_dir() / "Projeler" / f"{name}{S.PROJECT_EXT}")
    p = S.save_project(p, pr)
    _set_current(p)
    return {"path": p}


@tool("open_project", "Var olan .kstudio projesini açık proje yapar.", {"path": STR}, ["path"])
def t_open(path: str) -> Any:
    S.load_project(path)
    _set_current(path)
    return {"path": path}


@tool("list_projects", "Projeler klasöründeki .kstudio dosyaları.", {})
def t_list() -> Any:
    return [str(p) for p in sorted((S.home_dir() / "Projeler").glob("*" + S.PROJECT_EXT), key=lambda q: -q.stat().st_mtime)][:40]


@tool("import_media", "Dosyaları projeye varlık (asset) olarak ekler; isteğe bağlı olarak zaman çizelgesinin sonuna dizer.",
      {"paths": {"type": "array", "items": STR}, "append": {"type": "boolean"}, "path": PATH}, ["paths"])
def t_import(paths: list[str], append: bool = False, path: str = "") -> Any:
    p, pr = load(path)
    out = []
    for f in paths:
        i = ST.info(f)
        if not i.get("ok"):
            out.append({"path": f, "error": i.get("error")})
            continue
        aid = S.add_asset(pr, i)
        item = {"asset": aid, "kind": i["kind"], "dur": i["dur"]}
        if append:
            tr = S.track_for(pr, i["kind"])
            end = max([c["start"] + c["dur"] for c in pr["clips"] if c["track"] == tr] or [0])
            item["clip"] = S.add_clip(pr, asset=aid, track=tr, start=end, dur=i["dur"])["id"]
        out.append(item)
    save(p, pr)
    return out


@tool("add_clip", "Varlıktan klip ekler. track boşsa türüne göre seçilir. in=kaynak başlangıcı (sn).",
      {"asset": STR, "start": N, "dur": N, "in": N, "track": STR, "speed": N, "vol": N, "path": PATH}, ["asset", "start"])
def t_add_clip(asset: str, start: float, dur: float = 0, track: str = "", path: str = "", **kw: Any) -> Any:
    p, pr = load(path)
    a = pr["assets"][asset]
    d = dur or max(0.1, a.get("dur", 3) - float(kw.get("in", 0)))
    args = {"asset": asset, "start": float(start), "dur": float(d), **{k: v for k, v in kw.items() if v is not None}}
    if track:
        args["track"] = track
    c = S.add_clip(pr, **args)
    save(p, pr)
    return c


@tool("update_clip", "Klip alanlarını değiştirir (start, dur, in, speed, vol, fadeIn, fadeOut, fadeCurve, pan, eq, x, y, scale, rot, opacity, fit, adj{bri,con,sat,hue,temp,blur}, "
      "mask{type,x,y,w,h,rot,feather,invert}, blend, shutterAngle, optFlow, stabilize, parent, kf{x,y,scale,rot,opacity}, fx[], fxAt{<fx>:{at:in|out|all,d}}, "
      "anim{in,out,loop,inDur,outDur,inEase,outEase,loopAmt,loopSpeed} (video/görsel: catalog.canim), trans{in,dur}, "
      "text, style{font,size,color,outline,outlineColor,glow,animIn,animOut,animLoop,inDur,outDur (catalog.tanim),pos,x,y,caption,highlight,...}, mode, zoom[]). "
      "null verilen alan silinir.", {"id": STR, "set": {"type": "object"}, "path": PATH}, ["id", "set"])
def t_update(id: str, set: dict, path: str = "") -> Any:
    p, pr = load(path)
    c = S.find_clip(pr, id)
    for k, v in set.items():
        if k == "id":
            continue
        if v is None:
            c.pop(k, None)
        elif k == "style" and isinstance(v, dict):
            c["style"] = {**(c.get("style") or {}), **v}
        else:
            c[k] = v
    save(p, pr)
    return c


@tool("split_clip", "Klibi zaman çizelgesindeki t anında böler.", {"id": STR, "t": N, "path": PATH}, ["id", "t"])
def t_split(id: str, t: float, path: str = "") -> Any:
    p, pr = load(path)
    n = S.split_clip(pr, id, float(t))
    save(p, pr)
    return {"right": n["id"] if n else None}


@tool("delete_clips", "Klipleri siler; ripple=true ise aynı izdeki sonraki klipler boşluğu kapatır.",
      {"ids": {"type": "array", "items": STR}, "ripple": {"type": "boolean"}, "path": PATH}, ["ids"])
def t_delete(ids: list[str], ripple: bool = False, path: str = "") -> Any:
    p, pr = load(path)
    for cid in ids:
        c = S.find_clip(pr, cid)
        pr["clips"].remove(c)
        if ripple:
            S.ripple_close(pr, c["track"], c["start"] + c["dur"], c["dur"])
    save(p, pr)
    return {"ok": True}


@tool("add_text", "Metin klibi ekler. style: font, size (ekran yüksekliği %), color, outline, outlineColor, glow, glowColor, "
      "animIn / animOut / animLoop (giriş/çıkış/döngü; adlar catalog.tanim), inDur, outDur, pos (top/center/bottom ya da x,y 0-1).",
      {"text": STR, "start": N, "dur": N, "style": {"type": "object"}, "path": PATH}, ["text", "start"])
def t_text(text: str, start: float, dur: float = 3, style: dict | None = None, path: str = "") -> Any:
    p, pr = load(path)
    c = S.add_clip(pr, text=text, start=float(start), dur=float(dur), style=style or {"anim": "pop", "pos": "center"})
    save(p, pr)
    return c


@tool("add_subscribe", "Abone ol animasyonu ekler (kind: classic/neon/pill/bounce/glitch/bell/like/corner).",
      {"kind": STR, "start": N, "dur": N, "style": {"type": "object"}, "path": PATH}, ["start"])
def t_sub(start: float, kind: str = "classic", dur: float = 4, style: dict | None = None, path: str = "") -> Any:
    p, pr = load(path)
    c = S.add_clip(pr, subscribe=kind, start=float(start), dur=float(dur), style=style or {"y": 0.8})
    save(p, pr)
    return c


@tool("add_effect", "Efekt modu uygular: clip verilirse o klibe (fx listesine), yoksa efekt izine start/dur aralığında.",
      {"mode": STR, "clip": STR, "start": N, "dur": N, "path": PATH}, ["mode"])
def t_fx(mode: str, clip: str = "", start: float = 0, dur: float = 2, path: str = "") -> Any:
    if mode not in S.FX:
        raise ValueError(f"bilinmeyen efekt: {mode}. catalog'a bak")
    p, pr = load(path)
    if clip:
        c = S.find_clip(pr, clip)
        c["fx"] = list(dict.fromkeys([*(c.get("fx") or []), mode]))
    else:
        c = S.add_clip(pr, mode=mode, start=float(start), dur=float(dur))
    save(p, pr)
    return c


@tool("set_zoom", "Klibe zoom uygular: preset (catalog.zoom id) ya da kf=[{t (klip içi sn, negatif=sondan), z, cx, cy (0-1), e (in/out/inout)}].",
      {"clip": STR, "preset": STR, "kf": {"type": "array", "items": {"type": "object"}}, "path": PATH}, ["clip"])
def t_zoom(clip: str, preset: str = "", kf: list | None = None, path: str = "") -> Any:
    p, pr = load(path)
    c = S.find_clip(pr, clip)
    if preset:
        z = next((z for z in S.ZOOM_PRESETS + S.load_templates() if z["id"] == preset or z["name"] == preset), None)
        if not z:
            raise ValueError("zoom şablonu yok")
        kf = z["kf"]
    c["zoom"] = kf or None
    save(p, pr)
    return {"id": clip, "zoom": c["zoom"]}


@tool("cut_silences", "Klipteki sessiz bölümleri kırpar (ripple). db: eşik (-35), min_len sn, pad_after/pad_before: konuşma öncesi/sonrası pay sn.",
      {"clip": STR, "db": N, "min_len": N, "pad_after": N, "pad_before": N, "path": PATH}, ["clip"])
def t_sil(clip: str, db: float = -35, min_len: float = 0.45, pad_after: float = 0.08, pad_before: float = 0.08, path: str = "") -> Any:
    p, pr = load(path)
    c = S.find_clip(pr, clip)
    a = pr["assets"][c["asset"]]
    sp = float(c.get("speed", 1) or 1)
    rng = ST.silences(a["path"], float(c.get("in", 0)), c["dur"] * sp, float(db), float(min_len))
    n = S.remove_ranges(pr, clip, rng, pad=float(pad_after), pad_before=float(pad_before))
    save(p, pr)
    return {"removed": n, "silences": len(rng), "end": round(S.project_end(pr), 2)}


@tool("cut_freezes", "Donuk/boş sahneleri kırpar (görüntü değişmeyen bölümler).", {"clip": STR, "min_len": N, "path": PATH}, ["clip"])
def t_frz(clip: str, min_len: float = 1.0, path: str = "") -> Any:
    p, pr = load(path)
    c = S.find_clip(pr, clip)
    a = pr["assets"][c["asset"]]
    rng = ST.freezes(a["path"], float(c.get("in", 0)), c["dur"] * float(c.get("speed", 1) or 1), float(min_len))
    n = S.remove_ranges(pr, clip, rng, pad=0.0)
    save(p, pr)
    return {"removed": n}


@tool("detect_beats", "Ses/video varlığındaki vuruşları bulur ve zaman çizelgesine işaret koyar (clip: o klibin konumuna göre).",
      {"clip": STR, "onsets": {"type": "boolean", "description": "true: düzensiz güçlü vuruşlar, false: tempo ızgarası"}, "path": PATH}, ["clip"])
def t_beats(clip: str, onsets: bool = False, path: str = "") -> Any:
    p, pr = load(path)
    c = S.find_clip(pr, clip)
    b = ST.beats(pr["assets"][c["asset"]]["path"])
    sp = float(c.get("speed", 1) or 1)
    src = b["onsets"] if onsets else b["beats"]
    ts = [round(c["start"] + (t - float(c.get("in", 0))) / sp, 3) for t in src]
    ts = [t for t in ts if c["start"] <= t <= c["start"] + c["dur"]]
    pr["markers"] = [m for m in pr.get("markers") or [] if m.get("kind") != "beat"] + [{"t": t, "kind": "beat"} for t in ts]
    save(p, pr)
    return {"bpm": b["bpm"], "markers": len(ts)}


@tool("cut_to_beats", "Klibi işaretli vuruşlarda böler (every: kaç vuruşta bir).", {"clip": STR, "every": N, "path": PATH}, ["clip"])
def t_ctb(clip: str, every: float = 1, path: str = "") -> Any:
    p, pr = load(path)
    c = S.find_clip(pr, clip)
    beats = sorted(m["t"] for m in pr.get("markers") or [] if m.get("kind") == "beat")[:: max(1, int(every))]
    n, cur = 0, c
    for t in beats:
        r = S.split_clip(pr, cur["id"], t)
        if r:
            cur, n = r, n + 1
    save(p, pr)
    return {"cuts": n}


@tool("auto_captions", "Whisper ile kelime zamanlı otomatik altyazı ekler (klibin sesinden). style.caption: hormozi/word/karaoke/plain/neon/boxed.",
      {"clip": STR, "lang": STR, "style": {"type": "object"}, "path": PATH}, ["clip"])
def t_caps(clip: str, lang: str = "auto", style: dict | None = None, path: str = "") -> Any:
    from app.core import aitools
    if not aitools.installed("whisper"):
        raise RuntimeError("Whisper kurulu değil: Kami Studio'da Altyazı panelinden bir kez kur.")
    p, pr = load(path)
    c = S.find_clip(pr, clip)
    a = pr["assets"][c["asset"]]
    sp = float(c.get("speed", 1) or 1)
    fd, out = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    import threading
    from app import paths
    try:
        st = json.loads(paths.SETTINGS_PATH.read_text("utf-8"))
    except (OSError, ValueError):
        st = {}
    res = aitools._run_json(["app.tools.studio_words_run", a["path"], out, f"{float(c.get('in', 0)):.3f}", f"{c['dur'] * sp:.3f}", lang,
                             st.get("whisper_model") or "large-v3-turbo", aitools.models_dir("whisper"), _ffmpeg()],
                            lambda m: None, threading.Event(), "whisper")
    if "done" not in res:
        raise RuntimeError(str(res.get("error")))
    words = json.loads(Path(out).read_text("utf-8"))["words"]
    os.remove(out)
    words = [{**w, "s": round(w["s"] / sp, 3), "e": round(w["e"] / sp, 3)} for w in words]
    t = S.add_clip(pr, words=words, start=c["start"], dur=c["dur"], style={"caption": "hormozi", **(style or {})})
    save(p, pr)
    return {"clip": t["id"], "words": len(words)}


@tool("render_frame", "Zaman çizelgesinin t anını PNG olarak gösterir (sonucu görmek için).", {"t": N, "width": N, "path": PATH}, ["t"])
def t_frame(t: float, width: float = 640, path: str = "") -> Any:
    _, pr = load(path)
    fd, out = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        ST.frame(pr, float(t), out)
        if width and width < pr.get("w", 1920):
            from PIL import Image
            im = Image.open(out)
            im = im.resize((int(width), int(im.height * width / im.width)))
            im.save(out)
        return {"_image": base64.b64encode(Path(out).read_bytes()).decode()}
    finally:
        os.remove(out)


@tool("export_video", "Projeyi MP4 olarak dışa aktarır (bitene kadar bekler). out boşsa Çıktılar klasörüne.",
      {"out": STR, "quality": {"type": "string", "enum": ["high", "medium"]}, "start": N, "end": N, "path": PATH})
def t_export(out: str = "", quality: str = "high", start: float | None = None, end: float | None = None, path: str = "") -> Any:
    _, pr = load(path)
    out = out or str(S.home_dir() / "Çıktılar" / f"{pr.get('name', 'video')}.mp4")
    opts: dict[str, Any] = {"quality": quality}
    if start is not None or end is not None:
        opts["range"] = [float(start or 0), float(end if end is not None else S.project_end(pr))]
    jid = ST.export(pr, out, opts)
    while ST.job(jid)["state"] == "running":
        time.sleep(0.5)
    j = ST.job(jid)
    if j["state"] != "done":
        raise RuntimeError(j.get("error") or j["state"])
    return {"out": out, "secs": j.get("secs"), "encoder": j.get("encoder")}


@tool("set_project", "Proje ayarları: name, w, h, fps, bg (#rrggbb).", {"set": {"type": "object"}, "path": PATH}, ["set"])
def t_setp(set: dict, path: str = "") -> Any:
    p, pr = load(path)
    for k in ("name", "w", "h", "fps", "bg"):
        if k in set:
            pr[k] = set[k]
    save(p, pr)
    return {k: pr[k] for k in ("name", "w", "h", "fps", "bg")}


@tool("apply_template", "Hazır şablonu t anına ekler (catalog.templates). 'freeze' için clip gerekir (kare dondur + zoom + tık).",
      {"id": STR, "t": N, "clip": STR, "path": PATH}, ["id", "t"])
def t_tpl(id: str, t: float, clip: str = "", path: str = "") -> Any:
    p, pr = load(path)
    added = S.apply_template(pr, id, float(t), _ffmpeg(), clip, info=ST.info)
    save(p, pr)
    return {"added": added}


@tool("add_graphic", "Hareketli grafik ekler: lower, lower-min, location, chapter, endscreen, callout, progress, highlight, counter, quote. "
      "style: title, sub, num, from/to/prefix/suffix, color, x, y, size, font.", {"kind": STR, "start": N, "dur": N, "style": {"type": "object"}, "path": PATH}, ["kind", "start"])
def t_gfx(kind: str, start: float, dur: float = 4, style: dict | None = None, path: str = "") -> Any:
    p, pr = load(path)
    c = S.add_clip(pr, graphic=kind, start=float(start), dur=float(dur), style=style or {})
    save(p, pr)
    return c


@tool("set_grade", "Renk düzeltme: exp (-2..2), con (-0.6..0.8), sat (0..2), temp/tint (-1..1), lift/gamma/gain [r,g,b] (-0.5..0.5), lut (Videolar\\Kami Studio\\LUT içindeki .cube adı), lutMix (0..1).",
      {"clip": STR, "grade": {"type": "object"}, "path": PATH}, ["clip", "grade"])
def t_grade(clip: str, grade: dict, path: str = "") -> Any:
    p, pr = load(path)
    c = S.find_clip(pr, clip)
    c["grade"] = {**(c.get("grade") or {}), **grade}
    save(p, pr)
    return c["grade"]


@tool("set_ramp", "Hız rampası: points=[{p: 0-1 kaynak konumu, s: hız}] (ör. montaj: [{p:0,s:3},{p:.4,s:.35},{p:.6,s:.35},{p:1,s:3}]). Boş liste rampayı kaldırır.",
      {"clip": STR, "points": {"type": "array", "items": {"type": "object"}}, "path": PATH}, ["clip", "points"])
def t_ramp(clip: str, points: list, path: str = "") -> Any:
    p, pr = load(path)
    c = S.find_clip(pr, clip)
    if not points:
        if c.get("srcLen"):
            c["dur"] = c["srcLen"] / float(c.get("speed", 1) or 1)
        c.pop("ramp", None)
        c.pop("srcLen", None)
    else:
        c.setdefault("srcLen", c["dur"] * float(c.get("speed", 1) or 1))
        c["ramp"] = points
        c["dur"] = round(S.ramp_duration(c), 3)
    save(p, pr)
    return {"dur": c["dur"]}


@tool("set_audio_fix", "Klip ses düzeltmeleri: fx listesi (catalog.afx). Ayrıca duck_track ile bir izi müzik olarak işaretle (konuşmada kısılır).",
      {"clip": STR, "fx": {"type": "array", "items": STR}, "duck_track": STR, "lufs": N, "path": PATH})
def t_afx(clip: str = "", fx: list | None = None, duck_track: str = "", lufs: float | None = None, path: str = "") -> Any:
    p, pr = load(path)
    if clip:
        S.find_clip(pr, clip)["afx"] = [f for f in (fx or []) if f in S.AUDIO_FIX]
    if duck_track:
        for t in pr["tracks"]:
            if t["id"] == duck_track:
                t["duck"] = True
    if lufs is not None:
        pr.setdefault("master", {})["lufs"] = float(lufs) or None
    save(p, pr)
    return {"ok": True}


@tool("set_track_state", "İz durumu ayarla: mute (sessiz), solo (sadece bu iz), duck (konuşmada kıs), lock (kilit), hide (gizli), vol (0-2).",
      {"track": STR, "mute": {"type": "boolean"}, "solo": {"type": "boolean"}, "duck": {"type": "boolean"},
       "lock": {"type": "boolean"}, "hide": {"type": "boolean"}, "vol": N, "path": PATH}, ["track"])
def t_track_state(track: str, mute: bool | None = None, solo: bool | None = None, duck: bool | None = None,
                  lock: bool | None = None, hide: bool | None = None, vol: float | None = None, path: str = "") -> Any:
    p, pr = load(path)
    tk = next((t for t in pr["tracks"] if t["id"] == track), None)
    if not tk:
        raise KeyError(track)
    for k, v in (("mute", mute), ("solo", solo), ("duck", duck), ("lock", lock), ("hide", hide)):
        if v is not None:
            tk[k] = bool(v)
    if vol is not None:
        tk["vol"] = max(0.0, min(2.0, float(vol)))
    save(p, pr)
    return tk


@tool("close_gaps", "Belirtilen izdeki klipler arasındaki tüm boşlukları baştan sona kapatır.", {"track": STR, "path": PATH}, ["track"])
def t_close_gaps(track: str, path: str = "") -> Any:
    p, pr = load(path)
    moved = S.ripple_close_gaps(pr, track)
    save(p, pr)
    return {"moved": moved, "end": round(S.project_end(pr), 2)}


@tool("set_key", "Yeşil/mavi perde silme: on, color (#00ff00), sim (0.01-0.6), smooth (0-0.4), spill.", {"clip": STR, "key": {"type": "object"}, "path": PATH}, ["clip", "key"])
def t_key(clip: str, key: dict, path: str = "") -> Any:
    p, pr = load(path)
    c = S.find_clip(pr, clip)
    c["key"] = {**(c.get("key") or {}), **key}
    save(p, pr)
    return c["key"]


@tool("list_recipes", "Tüm viral kurgu paketlerini listeler (26 paket: iman_gadzhi, fps_frag, amv_flow, valorant_ace, brainrot_max, documentary_film vb.).", {})
def t_list_recipes() -> Any:
    from app.core.studio_brand import list_recipes
    return list_recipes()


@tool("run_recipe", "Acik projeye tek tikla viral kurgu recetesi (renk grade, shutter blur, marka rengi) uygular.",
      {"recipe": STR, "path": PATH}, ["recipe"])
def t_run_recipe(recipe: str, path: str = "") -> Any:
    from app.core.studio_brand import BrandKitStore, apply_viral_recipe
    p, pr = load(path)
    kit = BrandKitStore().load("kisisel")
    res = apply_viral_recipe(pr, recipe, brand_kit=kit)
    save(p, res["project"])
    return {"ok": True, "recipe": res["recipe"], "applied_clips": res["applied_clips"]}


@tool("version_up_project", "Hyperbrew Version Raptor: açık projeyi sürüm numarası artırarak kaydeder (smart/add/safe).",
      {"mode": STR, "path": PATH})
def t_version_up(mode: str = "smart", path: str = "") -> Any:
    from app.core.studio_workflow import version_up_project
    p, pr = load(path)
    res = version_up_project(pr, cur_path=p, mode=mode)
    _set_current(res["path"])
    return {k: v for k, v in res.items() if k != "project"}


@tool("pro_io_path", "Hyperbrew Pro IO: wildcard ({name}_v{ver}_{w}x{h}_{date}) dosya yolu üretir.",
      {"pattern": STR, "ext": STR, "out_dir": STR, "path": PATH})
def t_pro_io_path(pattern: str = "{name}_v{ver}_{w}x{h}_{date}", ext: str = "mp4", out_dir: str = "", path: str = "") -> Any:
    from app.core.studio_workflow import pro_io_export_path
    p, pr = load(path)
    return pro_io_export_path(pr, pattern=pattern, ext=ext, out_dir=out_dir, cur_path=p)


@tool("create_variations", "AtomX / Variations: projeyi dikey (9:16), kare (1:1) veya portre (4:5) otomatik sürümlere çoğaltır.",
      {"presets": {"type": "array", "items": STR}, "path": PATH})
def t_create_variations(presets: list[str] | None = None, path: str = "") -> Any:
    from app.core.studio_workflow import create_variations
    p, pr = load(path)
    return create_variations(pr, presets=presets, cur_path=p)


@tool("batch_style_copy", "AEJuice Copy Ease: kaynak klibin keyframe/ease/zoom/efekt/renk stilini hedef kliplere süresine orantılı kopyalar.",
      {"src_id": STR, "dst_ids": {"type": "array", "items": STR}, "include_style": {"type": "boolean"}, "path": PATH}, ["src_id", "dst_ids"])
def t_batch_style_copy(src_id: str, dst_ids: list[str], include_style: bool = True, path: str = "") -> Any:
    from app.core.studio_workflow import copy_ease_apply
    p, pr = load(path)
    res = copy_ease_apply(pr, src_id, dst_ids, include_style=include_style)
    if res.get("ok"):
        save(p, pr)
    return res


@tool("stagger_clips", "Mister Horse Shifter: seçili klipleri asc/desc/pyramid/random sırasıyla basamaklar, hizalar veya kare bazlı kaydırır.",
      {"clip_ids": {"type": "array", "items": STR}, "step": N, "order": STR, "align": STR, "shift_frames": N, "path": PATH})
def t_stagger_clips(clip_ids: list[str] | None = None, step: float = 0.08, order: str = "asc",
                    align: str = "", shift_frames: int = 0, path: str = "") -> Any:
    from app.core.studio_workflow import stagger_clips
    p, pr = load(path)
    res = stagger_clips(pr, clip_ids=clip_ids, step=float(step or 0.08), order=order, align=align, shift_frames=int(shift_frames or 0))
    if res.get("ok"):
        save(p, pr)
    return res


@tool("anchor_clip", "Klibi/metni 9 noktalı sabitleme (tl/tc/tr/ml/center/mr/bl/bc/br) konumuna oturtur.",
      {"id": STR, "point": STR, "path": PATH}, ["id"])
def t_anchor_clip(id: str, point: str = "center", path: str = "") -> Any:
    from app.core.studio_workflow import anchor_9pt
    p, pr = load(path)
    res = anchor_9pt(pr, id, point=point)
    if res.get("ok"):
        save(p, pr)
    return res


@tool("add_sticker", "Zaman çizelgesine vektör veya rozet çıkartma (catalog.stickers) ekler.",
      {"sticker": STR, "start": N, "dur": N, "x": N, "y": N, "color": STR, "title": STR, "path": PATH}, ["sticker"])
def t_add_sticker(sticker: str, start: float = 0.0, dur: float = 3.0, x: float = 0.5, y: float = 0.5,
                  color: str = "", title: str = "", path: str = "") -> Any:
    p, pr = load(path)
    tr = next((t["id"] for t in pr["tracks"] if t["kind"] == "text"), "t1")
    st: dict[str, Any] = {"x": float(x), "y": float(y)}
    if color:
        st["color"] = color
    if title:
        st["title"] = title
    c = {"id": S._nid(pr), "track": tr, "sticker": sticker, "start": float(start), "dur": float(dur), "style": st}
    pr["clips"].append(c)
    save(p, pr)
    return {"id": c["id"], "sticker": sticker}


@tool("tts_voiceover", "Metinden ücretsiz seslendirme (edge-tts / Windows SAPI) üretip ses izine ekler.",
      {"text": STR, "start": N, "voice": STR, "rate": STR, "path": PATH}, ["text"])
def t_tts_voiceover(text: str, start: float = 0.0, voice: str = "tr-TR-EmelNeural", rate: str = "+0%", path: str = "") -> Any:
    from app.ui.api_studio import StudioMixin
    p, pr = load(path)
    mx = StudioMixin()
    res = mx.studio_tts(text, voice=voice, rate=rate)
    if not res.get("ok"):
        return res
    aid = S.add_asset(pr, res)
    tr = next((t["id"] for t in pr["tracks"] if t["kind"] == "audio"), "a1")
    c = {"id": S._nid(pr), "track": tr, "asset": aid, "start": float(start), "dur": float(res.get("dur") or 2.0), "in": 0.0, "speed": 1.0, "vol": 1.0}
    pr["clips"].append(c)
    save(p, pr)
    return {"id": c["id"], "asset": aid, "path": res.get("path"), "dur": c["dur"]}


@tool("apply_voice_dsp", "Soundly Place it / Shape it: klibe akustik mekan (place-*), Mono Sum, Faz Tersleme, Dry/Wet Mix veya EQ önayarı uygular.",
      {"id": STR, "afx": {"type": "array", "items": STR}, "eq_preset": STR, "mix": N, "mono_sum": {"type": "boolean"},
       "phase_invert": {"type": "boolean"}, "path": PATH}, ["id"])
def t_apply_voice_dsp(id: str, afx: list[str] | None = None, eq_preset: str = "", mix: float = 1.0,
                      mono_sum: bool = False, phase_invert: bool = False, path: str = "") -> Any:
    from app.core import studio_fx_adv
    p, pr = load(path)
    c = S.find_clip(pr, id)
    if afx is not None:
        c["afx"] = list(afx)
    if eq_preset and eq_preset in studio_fx_adv.EQ_PRESETS:
        c["eq"] = list(studio_fx_adv.EQ_PRESETS[eq_preset][1])
    c["afxMix"] = max(0.0, min(1.0, float(mix)))
    c["monoSum"] = bool(mono_sum)
    c["phaseInvert"] = bool(phase_invert)
    save(p, pr)
    return {"ok": True, "id": id, "afx": c.get("afx"), "eq_preset": eq_preset, "afxMix": c["afxMix"],
            "monoSum": c["monoSum"], "phaseInvert": c["phaseInvert"]}


@tool("purge_unused_assets", "AEJuice Clean Unused: projede hiç klipte kullanılmayan medya varlıklarını temizler.", {"path": PATH})
def t_purge_unused(path: str = "") -> Any:
    from app.core.studio_workflow import purge_unused_assets
    p, pr = load(path)
    res = purge_unused_assets(pr)
    save(p, pr)
    return res


@tool("export_gif", "AEJuice Export GIF / WebP: projeyi 2 geçişli yüksek kaliteli GIF veya animasyonlu WebP olarak dışa aktarır.",
      {"out_path": STR, "fmt": STR, "fps": N, "width": N, "path": PATH}, ["out_path"])
def t_export_gif(out_path: str, fmt: str = "gif", fps: float = 15, width: float = 720, path: str = "") -> Any:
    from app.core.studio_workflow import export_gif_webp
    _, pr = load(path)
    return export_gif_webp(pr, out_path, ST.ffmpeg(), ST, fmt=fmt, fps=int(fps or 15), width=int(width or 720))


@tool("search_open_assets", "Google Material Icons, Noto Emoji, Twemoji ve Lucide içinde ücretsiz açık kaynak ikon/emoji arar.",
      {"query": STR, "prefix": STR, "limit": N}, ["query"])
def t_search_open_assets(query: str, prefix: str = "", limit: float = 24) -> Any:
    from app.core.studio_workflow import search_open_icons
    return search_open_icons(query, prefix=prefix, limit=int(limit or 24))


@tool("fetch_open_asset", "Seçili Iconify varlığını (örn. mdi:fire veya noto:rocket) indirip opsiyonel olarak zaman çizelgesine ekler.",
      {"icon_id": STR, "color": STR, "add_to_timeline": {"type": "boolean"}, "start": N, "dur": N, "path": PATH}, ["icon_id"])
def t_fetch_open_asset(icon_id: str, color: str = "", add_to_timeline: bool = False,
                       start: float = 0.0, dur: float = 3.0, path: str = "") -> Any:
    from app.core.studio_workflow import fetch_open_icon_file
    res = fetch_open_icon_file(icon_id, S.home_dir() / "Simgeler", color=color)
    if not res.get("ok") or not add_to_timeline:
        return res
    p, pr = load(path)
    fp = res["path"]
    if fp.lower().endswith(".png"):
        info = ST.info(fp)
        if info.get("ok"):
            aid = S.add_asset(pr, info)
            tr = next((t["id"] for t in pr["tracks"] if t["kind"] == "overlay"), next((t["id"] for t in pr["tracks"] if t["kind"] == "video"), "v1"))
            c = {"id": S._nid(pr), "track": tr, "asset": aid, "start": float(start), "dur": float(dur), "in": 0.0, "speed": 1.0, "scale": 0.4}
            pr["clips"].append(c)
            save(p, pr)
            return {**res, "clip_id": c["id"], "asset_id": aid}
    return res


@tool("clipboard_bridge", "PluginPlay Copy Pasta: 'copy' modunda t anındaki kareyi panoya kopyalar; 'paste' modunda panodaki görseli varlık olarak ekler.",
      {"action": STR, "t": N, "selected_ids": {"type": "array", "items": STR}, "add_to_timeline": {"type": "boolean"}, "path": PATH}, ["action"])
def t_clipboard_bridge(action: str, t: float = 0.0, selected_ids: list[str] | None = None,
                       add_to_timeline: bool = False, path: str = "") -> Any:
    from app.core.studio_workflow import clipboard_copy_frame, clipboard_paste_image
    p, pr = load(path)
    if action == "copy":
        return clipboard_copy_frame(pr, float(t or 0.0), ST, selected_ids=selected_ids, out_dir=S.cache_dir() / "clipboard")
    if action == "paste":
        res = clipboard_paste_image(S.home_dir() / "Pano")
        if res.get("ok") and add_to_timeline:
            info = ST.info(res["path"])
            if info.get("ok"):
                aid = S.add_asset(pr, info)
                tr = next((tr_["id"] for tr_ in pr["tracks"] if tr_["kind"] == "overlay"), "v1")
                c = {"id": S._nid(pr), "track": tr, "asset": aid, "start": float(t or 0.0), "dur": 3.0, "in": 0.0, "speed": 1.0}
                pr["clips"].append(c)
                save(p, pr)
                return {**res, "clip_id": c["id"], "asset_id": aid}
        return res
    return {"ok": False, "error": "action_must_be_copy_or_paste"}


@tool("beatshift_sync", "PluginPlay Beatshift: müzik/ses dosyasındaki vuruşları (BPM) algılar ve zaman çizelgesine işaret/zoom/flaş/kesim uygular.",
      {"media_path": STR, "clip_id": STR, "mode": STR, "step": N, "zoom_amt": N, "sensitivity": N, "path": PATH}, ["media_path"])
def t_beatshift_sync(media_path: str, clip_id: str = "", mode: str = "markers", step: int = 1,
                     zoom_amt: float = 1.14, sensitivity: float = 1.35, path: str = "") -> Any:
    from app.core.studio_pro_plugins import apply_beat_sync, detect_audio_beats
    det = detect_audio_beats(_ffmpeg(), media_path, sensitivity=float(sensitivity or 1.35))
    if not det.get("ok"):
        return det
    p, pr = load(path)
    res = apply_beat_sync(pr, det["beats"], clip_id=clip_id, mode=mode, step=int(step or 1), zoom_amt=float(zoom_amt or 1.14))
    save(p, pr)
    return {**res, "bpm": det.get("bpm"), "beat_count": det.get("beat_count")}


@tool("pixel_sort_clip", "PluginPlay Pixel Sorting: video karesindeki parlaklık eşiğindeki pikselleri dikey/yatay gerçek zamanlı sıralar ve zaman çizelgesine ekler.",
      {"src_path": STR, "low_thr": N, "high_thr": N, "direction": STR, "reverse": {"type": "boolean"}, "add_to_timeline": {"type": "boolean"}, "start": N, "path": PATH}, ["src_path"])
def t_pixel_sort_clip(src_path: str, low_thr: float = 0.25, high_thr: float = 0.85, direction: str = "vertical",
                      reverse: bool = False, add_to_timeline: bool = True, start: float = 0.0, path: str = "") -> Any:
    from app.core.studio_pro_plugins import pixel_sort_video
    res = pixel_sort_video(_ffmpeg(), src_path, low_thr=float(low_thr), high_thr=float(high_thr),
                           direction=direction, reverse=bool(reverse))
    if not res.get("ok") or not add_to_timeline:
        return res
    p, pr = load(path)
    info = ST.info(res["path"])
    aid = S.add_asset(pr, info)
    c = {"id": S._nid(pr), "track": "v1", "asset": aid, "start": float(start), "dur": float(info.get("dur") or 3.0), "in": 0.0, "speed": 1.0}
    pr["clips"].append(c)
    save(p, pr)
    return {**res, "clip_id": c["id"], "asset_id": aid}


@tool("datamosh_clip", "PluginPlay Datamosh 2: MPEG-4 I-frame düşürerek gerçek datamosh hareket izi/sürükleme üretir.",
      {"src_path": STR, "mode": STR, "intensity": N, "add_to_timeline": {"type": "boolean"}, "start": N, "path": PATH}, ["src_path"])
def t_datamosh_clip(src_path: str, mode: str = "i_frame_drop", intensity: float = 0.6,
                    add_to_timeline: bool = True, start: float = 0.0, path: str = "") -> Any:
    from app.core.studio_pro_plugins import datamosh_video
    res = datamosh_video(_ffmpeg(), src_path, mode=mode, intensity=float(intensity or 0.6))
    if not res.get("ok") or not add_to_timeline:
        return res
    p, pr = load(path)
    info = ST.info(res["path"])
    aid = S.add_asset(pr, info)
    c = {"id": S._nid(pr), "track": "v1", "asset": aid, "start": float(start), "dur": float(info.get("dur") or 3.0), "in": 0.0, "speed": 1.0}
    pr["clips"].append(c)
    save(p, pr)
    return {**res, "clip_id": c["id"], "asset_id": aid}


@tool("generate_chart_graphic", "PluginPlay Chartist / The Parliament / Multistage Timer: veriye dayalı şeffaf animasyonlu grafik/meclis/sayaç katmanı üretip ekler.",
      {"kind": STR, "data": {"type": "object"}, "dur": N, "start": N, "add_to_timeline": {"type": "boolean"}, "path": PATH}, ["kind"])
def t_generate_chart(kind: str, data: dict[str, Any] | None = None, dur: float = 4.0, start: float = 0.0,
                     add_to_timeline: bool = True, path: str = "") -> Any:
    from app.core.studio_pro_plugins import generate_data_graphic
    p, pr = load(path)
    res = generate_data_graphic(_ffmpeg(), kind=kind, data=data, w=int(pr.get("w") or 1280), h=int(pr.get("h") or 720), dur=float(dur or 4.0))
    if not res.get("ok") or not add_to_timeline:
        return res
    info = ST.info(res["path"])
    info["alpha"] = True
    aid = S.add_asset(pr, info)
    tr = next((t["id"] for t in pr["tracks"] if t["kind"] == "overlay"), "v1")
    c = {"id": S._nid(pr), "track": tr, "asset": aid, "start": float(start), "dur": float(res["dur"]), "in": 0.0, "speed": 1.0}
    pr["clips"].append(c)
    save(p, pr)
    return {**res, "clip_id": c["id"], "asset_id": aid}


@tool("layout_clips", "PluginPlay Layout / GridSmith / Anti-Static: seçili klipleri ızgara, daire (radial), satır/sütun veya eşit dağılımla hizalar.",
      {"ids": {"type": "array", "items": STR}, "mode": STR, "cols": N, "gap": N, "path": PATH}, ["ids"])
def t_layout_clips(ids: list[str], mode: str = "grid", cols: int = 3, gap: float = 0.04, path: str = "") -> Any:
    from app.core.studio_pro_plugins import layout_clips
    p, pr = load(path)
    res = layout_clips(pr, ids, mode=mode, cols=int(cols or 3), gap=float(gap or 0.04))
    if res.get("ok"):
        save(p, pr)
    return {k: v for k, v in res.items() if k != "project"}


@tool("duplicate_rename_clips", "PluginPlay Duplicate & Rename: seçili klipleri numaralandırma şablonuyla kopyalar.",
      {"ids": {"type": "array", "items": STR}, "count": N, "pattern": STR, "time_offset": N, "path": PATH}, ["ids"])
def t_duplicate_rename(ids: list[str], count: int = 1, pattern: str = "{name} #{n}", time_offset: float = 0.25, path: str = "") -> Any:
    from app.core.studio_pro_plugins import duplicate_rename_clips
    p, pr = load(path)
    res = duplicate_rename_clips(pr, ids, count=int(count or 1), pattern=pattern, time_offset=float(time_offset or 0.25))
    if res.get("ok"):
        save(p, pr)
    return {k: v for k, v in res.items() if k != "project"}


@tool("power_loop", "PluginPlay Power Loop / AEJuice Loop: klibin anahtar karelerini tüm klip boyunca tekrarlar veya ping-pong döngüye sokar.",
      {"id": STR, "mode": STR, "period_s": N, "path": PATH}, ["id"])
def t_power_loop(id: str, mode: str = "pingpong", period_s: float = 1.0, path: str = "") -> Any:
    from app.core.studio_pro_plugins import apply_power_loop
    p, pr = load(path)
    res = apply_power_loop(pr, id, mode=mode, period_s=float(period_s or 1.0))
    if res.get("ok"):
        save(p, pr)
    return {k: v for k, v in res.items() if k != "project"}


@tool("set_adaptive_timing", "AtomX / Spunkram Adaptive Markers: klip süresi uzayıp kısaldığında giriş/çıkış animasyonlarını uçlara sabitler.",
      {"id": STR, "in_dur": N, "out_dur": N, "new_dur": N, "path": PATH}, ["id"])
def t_adaptive_timing(id: str, in_dur: float = 0.45, out_dur: float = 0.45, new_dur: float | None = None, path: str = "") -> Any:
    from app.core.studio_pro_plugins import set_adaptive_timing
    p, pr = load(path)
    res = set_adaptive_timing(pr, id, in_dur=float(in_dur or 0.45), out_dur=float(out_dur or 0.45), new_dur=new_dur)
    if res.get("ok"):
        save(p, pr)
    return {k: v for k, v in res.items() if k != "project"}


@tool("user_preset", "Mister Horse / AEJuice My Pack: klip önayarını kişisel pakete kaydet, listele, sil veya klibe uygula.",
      {"action": STR, "name": STR, "preset_id": STR, "clip_id": STR, "pack": STR, "color": STR, "path": PATH}, ["action"])
def t_user_preset(action: str, name: str = "", preset_id: str = "", clip_id: str = "",
                  pack: str = "Benim Paketim", color: str = "#7C3AED", path: str = "") -> Any:
    from app.core.studio_pro_plugins import apply_user_preset, delete_user_preset, list_user_presets, save_user_preset
    if action == "list":
        return list_user_presets(pack=pack if pack != "*" else "")
    if action == "delete":
        return delete_user_preset(preset_id)
    p, pr = load(path)
    if action == "save":
        cl = S.find_clip(pr, clip_id)
        payload = {k: cl[k] for k in ("fx", "grade", "anim", "style", "afx", "eq", "zoom", "trans", "adaptive") if k in cl}
        return save_user_preset(name or f"Klip Önayar", payload, pack=pack, color=color)
    if action == "apply":
        res = apply_user_preset(pr, clip_id, preset_id)
        if res.get("ok"):
            save(p, pr)
        return {k: v for k, v in res.items() if k != "project"}
    return {"ok": False, "error": "action_must_be_list_save_apply_delete"}


@tool("audio_pro_process", "Soundly Pro + Perfect Pitch: ses klibini FFT denoise, dereverb, LUFS normalize veya perde (pitch) kaydırmayla işler.",
      {"src_path": STR, "preset": STR, "pitch_semitones": N, "target_lufs": N}, ["src_path"])
def t_audio_pro_process(src_path: str, preset: str = "denoise_voice", pitch_semitones: float = 0.0, target_lufs: float | None = None) -> Any:
    from app.core.studio_pro_plugins import process_audio_clip_pro
    return process_audio_clip_pro(_ffmpeg(), src_path, preset=preset, pitch_semitones=float(pitch_semitones or 0.0), target_lufs=target_lufs)


# Kami Picture Pro + Makro MCP araclari (tek MCP baglantisindan tam kontrol)
from app.core import picture_mcp as _pic_mcp  # noqa: E402
TOOLS.update(_pic_mcp.TOOLS)


# ---------------------------------------------------------------------------------------------------------------
def _io():
    """Pencereli (PyInstaller) Kami.exe'de sys.stdin/stdout None olur: devralinan boru tutamaclarini ac."""
    if sys.stdin is not None and sys.stdout is not None:
        return sys.stdin.buffer, sys.stdout.buffer
    import ctypes
    import msvcrt
    k = ctypes.windll.kernel32
    fi = msvcrt.open_osfhandle(k.GetStdHandle(-10), os.O_RDONLY)
    fo = msvcrt.open_osfhandle(k.GetStdHandle(-11), 0)
    return os.fdopen(fi, "rb", buffering=0), os.fdopen(fo, "wb", buffering=0)


def handle(msg: dict) -> dict | None:
    mid, method = msg.get("id"), msg.get("method", "")
    if mid is None:
        return None   # bildirim
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": (msg.get("params") or {}).get("protocolVersion") or PROTO,
            "capabilities": {"tools": {}}, "serverInfo": {"name": "kami-studio", "version": "1.0"},
            "instructions": "Kami Studio video editörü. Önce get_project ile durumu oku, catalog ile efekt adlarını öğren; "
                            "düzenlemeler Studio penceresinde anında görünür. Sonucu görmek için render_frame kullan. Zamanlar saniye."}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": [t["schema"] for t in TOOLS.values()]}}
    if method == "tools/call":
        prm = msg.get("params") or {}
        t = TOOLS.get(prm.get("name", ""))
        if not t:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": "bilinmeyen araç"}}
        try:
            res = t["fn"](**(prm.get("arguments") or {}))
            if isinstance(res, dict) and "_image" in res:
                content = [{"type": "image", "data": res["_image"], "mimeType": "image/png"}]
            else:
                content = [{"type": "text", "text": json.dumps(res, ensure_ascii=False, separators=(",", ":"))}]
            return {"jsonrpc": "2.0", "id": mid, "result": {"content": content}}
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": mid, "result": {"isError": True, "content": [
                {"type": "text", "text": f"{type(exc).__name__}: {exc}"}]}}
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"yok: {method}"}}


def main() -> int:
    fin, fout = _io()
    for raw in iter(fin.readline, b""):
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except ValueError:
            continue
        try:
            out = handle(msg)
        except Exception:
            out = {"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32603, "message": traceback.format_exc()[-400:]}}
        if out is not None:
            fout.write((json.dumps(out, ensure_ascii=False) + "\n").encode("utf-8"))
            fout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
