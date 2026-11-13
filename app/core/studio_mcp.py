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


@tool("catalog", "Kullanılabilir efekt modları (fx), geçişler, zoom şablonları, altyazı stilleri, metin animasyonları, abone animasyonları, fontlar.", {})
def t_catalog() -> Any:
    c = S.catalog()
    return {"fx": {k: f"{v['name']} [{v['pack']}]" for k, v in c["fx"].items()}, "trans": c["trans"],
            "zoom": [{"id": z["id"], "name": z["name"]} for z in c["zoom"]], "captions": c["captions"], "anims": c["anims"],
            "subscribe": c["subscribe"], "graphics": c["graphics"], "templates": c["templates"], "afx": c["afx"], "deliver": c["deliver"],
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


@tool("update_clip", "Klip alanlarını değiştirir (start, dur, in, speed, vol, fadeIn, fadeOut, x, y, scale, rot, opacity, fit, adj{bri,con,sat,hue,temp,blur}, "
      "fx[], fxAt{<fx>:{at:in|out|all,d}}, anim{in,out,loop,inDur,outDur,inEase,outEase,loopAmt,loopSpeed} (video/görsel: catalog.canim), "
      "trans{in,dur}, text, style{font,size,color,outline,outlineColor,glow,animIn,animOut,animLoop,inDur,outDur (catalog.tanim),pos,x,y,caption,highlight,...}, mode, zoom[]). "
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


@tool("cut_silences", "Klipteki sessiz bölümleri kırpar (ripple). db: eşik (-35), min_len sn.",
      {"clip": STR, "db": N, "min_len": N, "path": PATH}, ["clip"])
def t_sil(clip: str, db: float = -35, min_len: float = 0.45, path: str = "") -> Any:
    p, pr = load(path)
    c = S.find_clip(pr, clip)
    a = pr["assets"][c["asset"]]
    sp = float(c.get("speed", 1) or 1)
    rng = ST.silences(a["path"], float(c.get("in", 0)), c["dur"] * sp, float(db), float(min_len))
    n = S.remove_ranges(pr, clip, rng)
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


@tool("set_audio_fix", "Klip ses düzeltmeleri: fx listesi (nr1, nr2, voice, gate, bass, radio, phone, cave). Ayrıca duck_track ile bir izi müzik olarak işaretle (konuşmada kısılır).",
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


@tool("set_key", "Yeşil/mavi perde silme: on, color (#00ff00), sim (0.01-0.6), smooth (0-0.4), spill.", {"clip": STR, "key": {"type": "object"}, "path": PATH}, ["clip", "key"])
def t_key(clip: str, key: dict, path: str = "") -> Any:
    p, pr = load(path)
    c = S.find_clip(pr, clip)
    c["key"] = {**(c.get("key") or {}), **key}
    save(p, pr)
    return c["key"]


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
