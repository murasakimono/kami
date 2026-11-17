"""Kami Studio MCP: profesyonel algi + kurgu + otomasyon araclari (v1.26).

Fikirler (kod Kami'nin): Tasarimci Dayi / video-use (model videoyu izlemez: kelime zamanli transkript + kare seridi
+ ses dalgasi okur), DaVinci Resolve MCP (islem zarfi, plan->onay, iz sagligi, isaretler), Premiere Pro MCP
(kontrol noktasi + fark, toplu secim, konusma temizligi planlari), Avenox / Sirio (kapilar: tekrar eden hatayi kurala yaz,
olculebilir kurgu standardi, hareket yogunlugu), Kinocut (kalite kapisi, makbuz).
"""
from __future__ import annotations

import base64
import copy
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from app.core import studio as S
from app.core import studio_finish as SF
from app.core.studio_mcp import N, PATH, ST, STR, _ffmpeg, load, save, tool

NO_WINDOW = SF.NO_WINDOW
B = {"type": "boolean"}
ARR = {"type": "array"}
OBJ = {"type": "object"}


def _ff(args: list[str], timeout: float = 600) -> subprocess.CompletedProcess:
    return subprocess.run([_ffmpeg(), "-hide_banner", "-nostdin", "-loglevel", "error", *args], capture_output=True,
                          timeout=timeout, creationflags=NO_WINDOW)


# ---------------------------------------------------------------- algi: transkript, kare seridi + dalga
def caption_words(pr: dict, t0: float = 0.0, t1: float = 1e9) -> list[dict]:
    """Zaman cizelgesindeki tum altyazi kliplerinin kelimeleri, mutlak zamanla (sirali)."""
    out = []
    for c in pr.get("clips") or []:
        for w in c.get("words") or []:
            s, e = float(c["start"]) + float(w["s"]), float(c["start"]) + float(w["e"])
            if e > t0 and s < t1:
                out.append({"w": str(w.get("w", "")), "s": round(s, 3), "e": round(e, 3)})
    return sorted(out, key=lambda w: w["s"])


def pack_phrases(words: list[dict], gap: float = 0.5) -> list[dict]:
    """Kelime listesini nefes/sessizlik (>= gap sn) ile ifadelere boler: modelin birincil okuma gorunumu."""
    out: list[dict] = []
    for w in words:
        if out and w["s"] - out[-1]["e"] < gap:
            out[-1]["e"] = w["e"]
            out[-1]["text"] += " " + w["w"]
            out[-1]["n"] += 1
        else:
            out.append({"s": w["s"], "e": w["e"], "text": w["w"], "n": 1})
    return out


@tool("get_transcript", "Zaman çizelgesinin kelime zamanlı transkripti. mode=phrases: sessizlikle bölünmüş satırlar "
      "'[012.52-015.36] metin' (kurguyu planlamak için birincil görünüm); words: kelime kelime. Altyazı yoksa önce auto_captions.",
      {"mode": {"type": "string", "enum": ["phrases", "words"]}, "start": N, "end": N, "gap": N, "path": PATH})
def t_transcript(mode: str = "phrases", start: float = 0, end: float = 1e9, gap: float = 0.5, path: str = "") -> Any:
    _, pr = load(path)
    ws = caption_words(pr, float(start), float(end))
    if not ws:
        return {"error": "Altyazı/kelime yok. Önce konuşma klibine auto_captions uygula."}
    if mode == "words":
        return {"words": ws[:4000]}
    ph = pack_phrases(ws, float(gap))
    return {"phrases": [f"[{p['s']:07.2f}-{p['e']:07.2f}] {p['text']}" for p in ph], "count": len(ph),
            "speech_sec": round(sum(w["e"] - w["s"] for w in ws), 1)}


def _strip(video: str, start: float, end: float, frames: int, width: int, wave: bool = True) -> bytes:
    """Kare seridi (frames kare, esit aralik) + altinda ses dalgasi + zaman etiketleri; PNG bayt."""
    from PIL import Image, ImageDraw
    frames = max(2, min(16, int(frames)))
    dur = max(0.1, end - start)
    tw = max(80, int(width) // frames)
    tiles = []
    for k in range(frames):
        t = start + dur * (k + 0.5) / frames
        r = _ff(["-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", "-vf", f"scale={tw}:-2", "-f", "image2", "-c:v", "png", "-"], 60)
        try:
            from io import BytesIO
            tiles.append((t, Image.open(BytesIO(r.stdout)).convert("RGB")))
        except Exception:
            tiles.append((t, Image.new("RGB", (tw, int(tw * 9 / 16)), (20, 16, 30))))
    th = max(im.height for _, im in tiles)
    wh = 90 if wave else 0
    W = tw * frames
    canvas = Image.new("RGB", (W, th + 18 + wh), (13, 10, 20))
    d = ImageDraw.Draw(canvas)
    for k, (t, im) in enumerate(tiles):
        canvas.paste(im, (k * tw, 0))
        d.text((k * tw + 4, th + 3), f"{t:.2f}s", fill=(196, 181, 253))
    if wave:
        r = _ff(["-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", video, "-vn", "-filter_complex",
                 f"aformat=channel_layouts=mono,showwavespic=s={W}x{wh}:colors=#2EE6A6:scale=sqrt", "-frames:v", "1",
                 "-f", "image2", "-c:v", "png", "-"], 120)
        try:
            from io import BytesIO
            canvas.paste(Image.open(BytesIO(r.stdout)).convert("RGB"), (0, th + 18))
        except Exception:
            d.text((6, th + 40), "(ses yok)", fill=(140, 130, 160))
    from io import BytesIO
    buf = BytesIO()
    canvas.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def preview_render(pr: dict, start: float, end: float, height: int = 360) -> str:
    """Projenin [start,end] araligini kucuk ve hizli disa aktarir (algi icin); gecici mp4 yolu."""
    q = copy.deepcopy(pr)
    W, H = int(q.get("w", 1920)), int(q.get("h", 1080))
    fd, out = tempfile.mkstemp(prefix="kmcp_prev_", suffix=".mp4")
    os.close(fd)
    job = {"id": "p", "state": "running", "p": 0.0, "error": "", "cancel": threading.Event(), "started": time.time()}
    ST._export(job, q, out, {"hw": False, "range": [float(start), float(end)], "quality": "medium",
                             "size": [max(2, int(W * height / H)) // 2 * 2, height]})
    if job.get("state") != "done":
        raise RuntimeError("önizleme olmadı: " + str(job.get("error", ""))[-300:])
    return out


@tool("timeline_view", "Zaman çizelgesinin [start,end] aralığını GÖR: işlenmiş sonuçtan (efekt/yazı/renk dahil) kare şeridi + ses dalgası "
      "tek PNG. Kesim noktalarını, yazı okunurluğunu, ses patlamalarını kontrol etmek için. Sürekli tarama için değil, karar anlarında kullan.",
      {"start": N, "end": N, "frames": N, "width": N, "path": PATH}, ["start", "end"])
def t_tview(start: float, end: float, frames: float = 8, width: float = 1280, path: str = "") -> Any:
    _, pr = load(path)
    end = min(float(end), S.project_end(pr))
    if end - float(start) < 0.1:
        raise ValueError("aralık çok kısa")
    tmp = preview_render(pr, float(start), end)
    try:
        png = _strip(tmp, 0.0, end - float(start), int(frames), int(width))
    finally:
        os.remove(tmp)
    return {"_image": base64.b64encode(png).decode()}


@tool("source_view", "Ham kaynak dosyanın (varlık ya da klip) [start,end] aralığının kare şeridi + ses dalgası. Hızlıdır; proje render edilmez.",
      {"asset": STR, "clip": STR, "file": STR, "start": N, "end": N, "frames": N, "width": N, "path": PATH})
def t_sview(asset: str = "", clip: str = "", file: str = "", start: float = 0, end: float = 0, frames: float = 8,
            width: float = 1280, path: str = "") -> Any:
    f = file
    if not f:
        _, pr = load(path)
        if clip:
            asset = S.find_clip(pr, clip).get("asset", "")
        a = (pr.get("assets") or {}).get(asset)
        if not a:
            raise ValueError("asset/clip/file ver")
        f = a["path"]
        end = end or float(a.get("dur") or 10)
    end = end or start + 10
    return {"_image": base64.b64encode(_strip(f, float(start), float(end), int(frames), int(width))).decode()}


@tool("analyze_clip", "Klibin kaynak bölgesinin tek seferde analizi: sessizlikler, sahne kesimleri, donuk görüntüler, BPM/vuruşlar, ses yüksekliği. "
      "Zamanlar ZAMAN ÇİZELGESİ saniyesi.", {"clip": STR, "path": PATH}, ["clip"])
def t_analyze(clip: str, path: str = "") -> Any:
    _, pr = load(path)
    c = S.find_clip(pr, clip)
    a = pr["assets"][c["asset"]]
    sp = float(c.get("speed", 1) or 1)
    i0, dur = float(c.get("in", 0)), float(c["dur"]) * sp
    to_tl = lambda t: round(float(c["start"]) + (t - i0) / sp, 3)   # noqa: E731
    out: dict[str, Any] = {"clip": clip, "kind": a.get("kind")}
    if a.get("audio") or a.get("kind") == "audio":
        out["silences"] = [[to_tl(x), to_tl(y)] for x, y in ST.silences(a["path"], i0, dur)][:200]
        txt = SF._ff(_ffmpeg(), ["-ss", f"{i0:.3f}", "-t", f"{dur:.3f}", "-i", a["path"], "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"])
        e = SF.parse_ebur128(txt)
        out["loudness"] = {"lufs": e["i"], "true_peak": e["tp"], "lra": e["lra"]}
        try:
            b = ST.beats(a["path"])
            out["bpm"] = b.get("bpm")
            out["beats"] = [to_tl(t) for t in b.get("beats", []) if i0 <= t <= i0 + dur][:300]
        except Exception:
            pass
    if a.get("kind") == "video":
        out["scenes"] = [to_tl(t) for t in ST.scenes(a["path"], i0, dur)][:200]
        out["freezes"] = [[to_tl(x), to_tl(y)] for x, y in ST.freezes(a["path"], i0, dur)][:100]
    return out


# ---------------------------------------------------------------- saglik, kalite kapilari, standart
DEFAULT_STANDARD = {"max_shot": 0.0, "motion_min": 0.0, "motion_max": 0.0, "lufs": None, "true_peak": -1.0,
                    "banned_fx": [], "min_text_size": 3.2, "safe_zone": True, "platform": "youtube"}


def motion_events(pr: dict) -> list[float]:
    """Gorsel olay zamanlari: kesim, gecis, zoom/anahtar kare baslangici, yazi/cikartma/grafik girisi, SFX."""
    ev: set[float] = set()
    for c in pr.get("clips") or []:
        s = round(float(c.get("start", 0)), 2)
        tr = str(c.get("track", ""))
        if tr.startswith("v") or c.get("text") or c.get("sticker") or c.get("graphic") or c.get("subscribe") or c.get("mode"):
            ev.add(s)
        if (c.get("trans") or {}).get("in"):
            ev.add(s)
        for z in S.kf_resolve(c.get("zoom") or [], float(c.get("dur", 0) or 0))[1:2]:
            ev.add(round(s + float(z.get("t", 0)), 2))
        if tr.startswith("a") and c.get("asset") and float(c.get("dur", 0)) < 3:   # kisa ses = SFX
            ev.add(s)
    return sorted(ev)


def motion_density(pr: dict, window: float = 10.0) -> dict:
    end = S.project_end(pr)
    ev = motion_events(pr)
    if end <= 0:
        return {"avg_per_10s": 0, "windows": []}
    wins = []
    t = 0.0
    while t < end - 0.5:
        n = sum(1 for e in ev if t <= e < t + window)
        wins.append({"t": round(t, 1), "n": n})
        t += window
    avg = sum(w["n"] for w in wins) / max(1, len(wins))
    return {"avg_per_10s": round(avg, 1), "windows": wins}


def timeline_health(pr: dict) -> dict:
    issues: list[dict] = []
    tracks = {t["id"]: t for t in pr.get("tracks") or []}
    for tid, tr in tracks.items():
        seq = sorted([c for c in pr["clips"] if c.get("track") == tid], key=lambda c: float(c["start"]))
        for a, b in zip(seq, seq[1:]):
            ea = float(a["start"]) + float(a["dur"])
            if float(b["start"]) < ea - 0.02 and tr.get("kind") in ("video", "audio"):
                issues.append({"level": "warn", "msg": f"Çakışma ({tr.get('name', tid)}): {a['id']} ve {b['id']}", "t": float(b["start"])})
            elif tid == "v1" and float(b["start"]) - ea > 0.04:
                issues.append({"level": "warn", "msg": f"Ana videoda {float(b['start']) - ea:.2f} sn boşluk (siyah görünür)", "t": ea})
        for c in seq:
            if tr.get("kind") == "video" and c.get("asset") and float(c["dur"]) < 0.1:
                issues.append({"level": "err", "msg": f"Flaş kare: {c['id']} {float(c['dur']) * 1000:.0f} ms", "t": float(c["start"])})
    for aid, a in (pr.get("assets") or {}).items():
        if a.get("path") and not os.path.isfile(a["path"]) and any(c.get("asset") == aid for c in pr["clips"]):
            issues.append({"level": "err", "msg": f"Medya dosyası yok: {a['path']}", "t": None})
    issues += SF.project_qc({**pr, "size": [pr.get("w", 1920), pr.get("h", 1080)]})
    v1 = sorted([c for c in pr["clips"] if c.get("track") == "v1"], key=lambda c: float(c["start"]))
    shots = [float(c["dur"]) for c in v1]
    return {"issues": issues, "end": round(S.project_end(pr), 2), "shots": len(shots),
            "shot_avg": round(sum(shots) / len(shots), 2) if shots else 0, "shot_max": round(max(shots), 2) if shots else 0,
            "motion": motion_density(pr)}


def gate_check(pr: dict) -> list[str]:
    """Kurgu standardina gore kapilar: gecmezse disa aktarma durur (force ile atlanir)."""
    st = {**DEFAULT_STANDARD, **(pr.get("standard") or {})}
    fails = []
    h = timeline_health(pr)
    fails += [i["msg"] for i in h["issues"] if i["level"] == "err"]
    if st["max_shot"] and h["shot_max"] > float(st["max_shot"]):
        fails.append(f"En uzun çekim {h['shot_max']} sn > standart {st['max_shot']} sn")
    m = h["motion"]["avg_per_10s"]
    if st["motion_min"] and m < float(st["motion_min"]):
        fails.append(f"Hareket yoğunluğu 10 sn'de {m} < {st['motion_min']} (yavaş kalıyor)")
    if st["motion_max"] and m > float(st["motion_max"]):
        fails.append(f"Hareket yoğunluğu 10 sn'de {m} > {st['motion_max']} (fazla yorucu)")
    banned = set(st.get("banned_fx") or [])
    for c in pr.get("clips") or []:
        hit = banned.intersection(c.get("fx") or []) | ({c.get("mode")} & banned)
        if hit:
            fails.append(f"Yasaklı efekt {', '.join(sorted(hit))} ({c['id']})")
        txt = str(c.get("text") or "")
        if txt and re.search(r"[a-zçğöşü]I|I[çğöşü]", txt):
            fails.append(f"Türkçe büyük harf hatası olabilir (I/İ): “{txt[:40]}” ({c['id']})")
    if st.get("safe_zone"):
        fails += [i["msg"] for i in h["issues"] if "güvenli alan" in i["msg"]]
    return fails


@tool("timeline_health", "Zaman çizelgesi sağlığı: çakışma, ana videoda boşluk, flaş kare, eksik medya, tekrar eden geçiş, güvenli alan, "
      "çekim uzunlukları, 10 sn'deki hareket yoğunluğu. Dışa aktarmadan önce çalıştır.", {"path": PATH})
def t_health(path: str = "") -> Any:
    _, pr = load(path)
    return timeline_health(pr)


@tool("edit_standard", "Projenin ölçülebilir kurgu standardını oku/ayarla (Avenox 'kapılar'): max_shot sn, motion_min/motion_max (10 sn'deki görsel olay), "
      "lufs, true_peak, banned_fx [id], min_text_size, safe_zone, platform. Standart dışa aktarmada kapı olur.",
      {"set": OBJ, "path": PATH})
def t_standard(set: dict | None = None, path: str = "") -> Any:
    p, pr = load(path)
    if set:
        pr["standard"] = {**(pr.get("standard") or {}), **{k: v for k, v in set.items() if k in DEFAULT_STANDARD}}
        if "lufs" in set and set["lufs"] is not None:
            pr.setdefault("master", {})["lufs"] = float(set["lufs"])
        save(p, pr)
    return {**DEFAULT_STANDARD, **(pr.get("standard") or {})}


@tool("qc_export", "Dışa aktarılmış dosyanın yayın öncesi kontrolü: siyah/donuk kare, sessizlik, LUFS + gerçek tepe (platform hedefi), siyah ilk kare, "
      "dinlenecek 5 an. platform: youtube|shorts|podcast|tv.", {"file": STR, "platform": STR}, ["file"])
def t_qc(file: str, platform: str = "youtube") -> Any:
    return SF.media_qc(_ffmpeg(), file, platform)


@tool("export_checked", "Kapılı dışa aktarma: önce timeline_health + kurgu standardı; geçmezse durur ve nedenleri döner (force=true atlar). "
      "Sonra render + qc_export. Önce preview=true ile 480p taslak almak hızlıdır.",
      {"out": STR, "preview": B, "force": B, "platform": STR, "path": PATH})
def t_export_checked(out: str = "", preview: bool = False, force: bool = False, platform: str = "", path: str = "") -> Any:
    _, pr = load(path)
    fails = gate_check(pr)
    if fails and not force:
        return {"blocked": True, "gates": fails, "hint": "Düzelt ya da force=true ile bilerek geç."}
    name = pr.get("name", "video") + ("_taslak" if preview else "")
    out = out or str(S.home_dir() / "Çıktılar" / f"{name}.mp4")
    opts: dict[str, Any] = {"quality": "medium" if preview else "high"}
    if preview:
        W, H = int(pr.get("w", 1920)), int(pr.get("h", 1080))
        opts["size"] = [max(2, int(W * 480 / H)) // 2 * 2, 480] if H >= W else [854, max(2, int(H * 854 / W)) // 2 * 2]
    jid = ST.export(pr, out, opts)
    while ST.job(jid)["state"] == "running":
        time.sleep(0.5)
    j = ST.job(jid)
    if j["state"] != "done":
        raise RuntimeError(j.get("error") or j["state"])
    plat = platform or (pr.get("standard") or {}).get("platform") or ("shorts" if int(pr.get("h", 0)) > int(pr.get("w", 0)) else "youtube")
    return {"out": out, "secs": j.get("secs"), "gates_skipped": fails if force else [], "qc": SF.media_qc(_ffmpeg(), out, plat)}


# ---------------------------------------------------------------- kurgu islemleri
def tl_to_src(c: dict, t: float) -> float:
    return float(c.get("in", 0)) + (t - float(c["start"])) * float(c.get("speed", 1) or 1)


@tool("remove_ranges", "Zaman çizelgesi aralıklarını [[t0,t1],...] klipten kes (ripple). Diğer izler (altyazı, yazı, B-roll, bağlı ses) senkron kayar; "
      "müzik yatağı ve kilitli izler yerinde kalır. Kesimleri kelime sınırına oturt; kelimenin içinden kesme.",
      {"clip": STR, "ranges": ARR, "pad": N, "path": PATH}, ["clip", "ranges"])
def t_remove(clip: str, ranges: list, pad: float = 0.0, path: str = "") -> Any:
    p, pr = load(path)
    c = S.find_clip(pr, clip)
    src = [[tl_to_src(c, float(a)), tl_to_src(c, float(b))] for a, b in ranges if float(b) > float(a)]
    n = S.remove_ranges(pr, clip, src, pad=float(pad), pad_before=float(pad))
    save(p, pr)
    return {"removed": n, "end": round(S.project_end(pr), 2)}


@tool("speech_cleanup", "Konuşma temizliği planı: dolgu (ııı/eee), tekrar, yarım başlangıç, uzun duraklama. safe=true olanlar ifade arasında, "
      "kesmek güvenli. apply=true: safe olanları (all=true ise hepsini) keser.",
      {"clip": STR, "apply": B, "all": B, "path": PATH}, ["clip"])
def t_speech(clip: str, apply: bool = False, all: bool = False, path: str = "") -> Any:
    p, pr = load(path)
    c = S.find_clip(pr, clip)
    ws = caption_words(pr, float(c["start"]), float(c["start"]) + float(c["dur"]))
    if not ws:
        return {"error": "Önce auto_captions."}
    sug = SF.speech_suggestions(ws)
    if not apply:
        return {"suggestions": sug}
    pick = [s for s in sug if all or s["safe"]]
    src = [[tl_to_src(c, s["s"]), tl_to_src(c, s["e"])] for s in pick]
    n = S.remove_ranges(pr, clip, src, pad=0.0, pad_before=0.0)
    save(p, pr)
    return {"cut": n, "skipped_unsafe": len(sug) - len(pick), "end": round(S.project_end(pr), 2)}


@tool("markers", "İşaretler: action=add (items:[{t,label,color}]) | list | clear (kind ile). Vuruş, bölüm, not, inceleme için.",
      {"action": {"type": "string", "enum": ["add", "list", "clear"]}, "items": ARR, "kind": STR, "path": PATH}, ["action"])
def t_markers(action: str, items: list | None = None, kind: str = "", path: str = "") -> Any:
    p, pr = load(path)
    ms = pr.setdefault("markers", [])
    if action == "add":
        for it in (items or [])[:500]:
            ms.append({"t": round(float(it.get("t", 0)), 3), "kind": it.get("kind", kind or "note"),
                       **({"label": str(it["label"])[:80]} if it.get("label") else {}), **({"color": it["color"]} if it.get("color") else {})})
        save(p, pr)
    elif action == "clear":
        pr["markers"] = [m for m in ms if kind and m.get("kind") != kind]
        save(p, pr)
    return {"markers": sorted(pr["markers"], key=lambda m: m["t"])[:500]}


def _match(pr: dict, f: dict) -> list[dict]:
    cs = sorted(pr.get("clips") or [], key=lambda c: (str(c.get("track")), float(c.get("start", 0))))
    if f.get("ids"):
        cs = [c for c in cs if c.get("id") in set(f["ids"])]
    if f.get("track"):
        cs = [c for c in cs if c.get("track") == f["track"]]
    if f.get("kind"):
        trk = {t["id"]: t.get("kind") for t in pr.get("tracks") or []}
        cs = [c for c in cs if trk.get(c.get("track")) == f["kind"]]
    if f.get("asset"):
        cs = [c for c in cs if c.get("asset") == f["asset"]]
    if f.get("start") is not None or f.get("end") is not None:
        a, b = float(f.get("start") or 0), float(f.get("end") if f.get("end") is not None else 1e9)
        cs = [c for c in cs if float(c["start"]) < b and float(c["start"]) + float(c["dur"]) > a]
    if f.get("min_dur"):
        cs = [c for c in cs if float(c["dur"]) >= float(f["min_dur"])]
    n = int(f.get("every_nth") or 1)
    if n > 1:
        cs = [c for i, c in enumerate(cs) if (i - int(f.get("offset") or 0)) % n == 0]
    return cs


@tool("batch_update", "Toplu düzenleme: filter {ids, track, kind(video/audio/text/fx), asset, start, end, min_dur, every_nth, offset} ile seçilen "
      "kliplere patch uygular (ör. {grade:{lut:'X.cube'}}, {fx:['vhs']}, {trans:{in:'zoom'}}). Sözlük alanları birleştirilir. dry_run önce dener.",
      {"filter": OBJ, "patch": OBJ, "dry_run": B, "path": PATH}, ["filter", "patch"])
def t_batch(filter: dict, patch: dict, dry_run: bool = False, path: str = "") -> Any:
    p, pr = load(path)
    cs = _match(pr, filter or {})
    if not dry_run:
        for c in cs:
            for k, v in (patch or {}).items():
                if k in ("id", "track", "start"):
                    continue
                c[k] = {**c[k], **v} if isinstance(v, dict) and isinstance(c.get(k), dict) else copy.deepcopy(v)
        save(p, pr)
    return {"matched": [c["id"] for c in cs], "applied": not dry_run}


@tool("reframe_project", "En boy oranını değiştir (ör. 1080x1920 dikey, 1080x1080 kare). Ana video klipleri kadrajı doldurur; face=true "
      "konuşan yüzü takip eder (Whisper ortamı gerekmez, IOPaint ortamı gerekir).", {"w": N, "h": N, "face": B, "path": PATH}, ["w", "h"])
def t_reframe(w: float, h: float, face: bool = False, path: str = "") -> Any:
    p, pr = load(path)
    pr["w"], pr["h"] = int(w) // 2 * 2, int(h) // 2 * 2
    n = 0
    for c in pr.get("clips") or []:
        if c.get("track") == "v1" and c.get("asset"):
            c["fit"] = "cover"
            n += 1
    save(p, pr)
    return {"size": [pr["w"], pr["h"]], "clips": n, "note": "Yüz takibi için Studio'da Akıllı > Dikey çerçeve" if face else ""}


# ---------------------------------------------------------------- kontrol noktasi
def _cp_dir(p: str) -> Path:
    d = S.home_dir() / "Kontrol Noktaları" / re.sub(r"[^\w\-]+", "_", Path(p).stem)[:60]
    d.mkdir(parents=True, exist_ok=True)
    return d


def snapshot_diff(a: dict, b: dict) -> dict:
    ca, cb = {c["id"]: c for c in a.get("clips") or []}, {c["id"]: c for c in b.get("clips") or []}
    added = [i for i in cb if i not in ca]
    removed = [i for i in ca if i not in cb]
    moved = [i for i in cb if i in ca and abs(float(cb[i]["start"]) - float(ca[i]["start"])) > 1e-3]
    trimmed = [i for i in cb if i in ca and (abs(float(cb[i]["dur"]) - float(ca[i]["dur"])) > 1e-3 or
                                            abs(float(cb[i].get("in", 0)) - float(ca[i].get("in", 0))) > 1e-3)]
    changed = [i for i in cb if i in ca and i not in moved and i not in trimmed and cb[i] != ca[i]]
    return {"added": added, "removed": removed, "moved": moved, "trimmed": trimmed, "changed": changed,
            "end_before": round(S.project_end(a), 2), "end_after": round(S.project_end(b), 2)}


@tool("checkpoint", "Riskli düzenlemeden önce kontrol noktası: action=save (name) | list | restore (name) | diff (name: o noktadan bu yana "
      "eklenen/silinen/kayan/kırpılan klipler).", {"action": {"type": "string", "enum": ["save", "list", "restore", "diff"]}, "name": STR,
                                                  "path": PATH}, ["action"])
def t_checkpoint(action: str, name: str = "", path: str = "") -> Any:
    p, pr = load(path)
    d = _cp_dir(p)
    if action == "list":
        return [{"name": f.stem, "t": time.strftime("%d.%m %H:%M", time.localtime(f.stat().st_mtime))}
                for f in sorted(d.glob("*.json"), key=lambda f: -f.stat().st_mtime)][:50]
    name = re.sub(r"[^\w\-]+", "_", name or time.strftime("cp_%H%M%S"))[:40]
    f = d / f"{name}.json"
    if action == "save":
        f.write_text(json.dumps(pr, ensure_ascii=False), "utf-8")
        return {"saved": name}
    if not f.is_file():
        raise ValueError(f"kontrol noktası yok: {name}")
    old = json.loads(f.read_text("utf-8"))
    if action == "diff":
        return snapshot_diff(old, pr)
    (d / "_geri_alma_oncesi.json").write_text(json.dumps(pr, ensure_ascii=False), "utf-8")
    save(p, old)
    return {"restored": name, "diff": snapshot_diff(pr, old)}


# ---------------------------------------------------------------- yeni motorlar (v1.25) MCP'den
def _wait(job: dict, timeout: float = 7200) -> dict:
    t0 = time.time()
    while job.get("state") == "running" and time.time() - t0 < timeout:
        time.sleep(0.5)
    return job


def _new_job() -> dict:
    return {"id": "m", "state": "running", "p": 0.0, "error": "", "cancel": threading.Event(), "line": "", "started": time.time()}


def _replace_asset(pr: dict, c: dict, path_: str) -> str:
    i = ST.info(path_)
    if not i.get("ok"):
        raise RuntimeError("çıktı okunamadı")
    aid = S.add_asset(pr, i)
    c["asset"], c["in"] = aid, 0
    c.pop("speed", None)
    return aid


@tool("enhance_clip", "Yapay zeka ile klip iyileştirme (ekran kartı, ilk kullanımda iner): kind=upscale (opts {model: anime|photo, scale: 2|4}) "
      "Real-ESRGAN netleştirme; kind=slowmo (opts {factor: 2|4, mode: slow|smooth}) RIFE ara kare. Sonuç klibin yerine geçer.",
      {"clip": STR, "kind": {"type": "string", "enum": ["upscale", "slowmo"]}, "opts": OBJ, "path": PATH}, ["clip", "kind"])
def t_enhance(clip: str, kind: str, opts: dict | None = None, path: str = "") -> Any:
    from app.core import studio_enhance as se
    p, pr = load(path)
    c = S.find_clip(pr, clip)
    tool_ = "esrgan" if kind == "upscale" else "rife"
    if not se.installed(tool_):
        se.install(tool_)
    o = dict(opts or {})
    sp = float(c.get("speed", 1) or 1)
    job = _wait(_run_thread(se.run, _new_job(), _ffmpeg(), "upscale" if kind == "upscale" else "interp", pr["assets"][c["asset"]]["path"],
                            float(c.get("in", 0)), float(c["dur"]) * sp, o, S.home_dir() / "Netleştirilmiş"))
    if job["state"] != "done":
        raise RuntimeError(job.get("error") or job["state"])
    old = float(c["dur"])
    _replace_asset(pr, c, job["result"]["path"])
    if kind == "slowmo" and o.get("mode", "slow") == "slow":
        c["dur"] = round(old * (4 if int(o.get("factor", 2)) >= 4 else 2), 3)
        S.ripple_open(pr, c["track"], float(c["start"]) + old, float(c["dur"]) - old)
    save(p, pr)
    return {"clip": clip, "file": job["result"]["path"], "dur": c["dur"]}


def _run_thread(fn, job, *args):
    threading.Thread(target=fn, args=(job, *args), daemon=True).start()
    return job


@tool("track_object", "Hareket takibi: 'video' klibindeki nesneyi (box: [x,y,w,h] 0-1, t anındaki karede) izler ve 'target' klibini "
      "(yazı/çıkartma/görsel) ona yapıştırır. Kutuyu bulmak için önce source_view ile kareye bak.",
      {"target": STR, "video": STR, "t": N, "box": ARR, "path": PATH}, ["target", "video", "t", "box"])
def t_track(target: str, video: str, t: float, box: list, path: str = "") -> Any:
    from app.core import aitools
    p, pr = load(path)
    o, v = S.find_clip(pr, target), S.find_clip(pr, video)
    if not aitools.installed("track"):
        aitools.install("track", lambda s: None)
    sp = float(v.get("speed", 1) or 1)
    src_t = tl_to_src(v, float(t))
    end = min(float(o["start"]) + float(o["dur"]), float(v["start"]) + float(v["dur"]))
    fd, out = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        res = aitools._run_once(["app.tools.studio_track_run", pr["assets"][v["asset"]]["path"], out, f"{src_t:.3f}",
                                 f"{max(0.2, (end - float(t)) * sp):.3f}", *[f"{float(x):.5f}" for x in box[:4]]],
                                lambda m: None, threading.Event(), "track", {})
        if "done" not in res:
            raise RuntimeError(str(res.get("error", "takip olmadı")))
        kf = json.loads(Path(out).read_text("utf-8"))["kf"]
    finally:
        os.remove(out)
    c0 = kf[0]
    sc = float(v.get("scale", 1) or 1)
    rel = [{"t": round(float(v["start"]) + (q["t"] - float(v.get("in", 0))) / sp - float(o["start"]), 3),
            "dx": round((q["cx"] - c0["cx"]) * sc, 4), "dy": round((q["cy"] - c0["cy"]) * sc, 4)} for q in kf]
    rel = [q for q in rel if q["t"] >= 0]
    trk = {x["id"]: x.get("kind") for x in pr.get("tracks") or []}
    if trk.get(o["track"]) == "text":
        o["trackPath"] = rel
    else:
        bx, by = float(o.get("x", 0) or 0), float(o.get("y", 0) or 0)
        o["kf"] = [{"t": q["t"], "x": round(bx + q["dx"], 4), "y": round(by + q["dy"], 4)} for q in rel]
    save(p, pr)
    return {"points": len(rel)}


@tool("reference_style", "Referans videodan stil: kesim temposu, BPM, LUFS, renk. apply_color=[klip id] verilirse rengi LUT olarak o kliplere uygular; "
      "apply_loudness=true ses hedefini referansa eşitler.", {"file": STR, "apply_color": ARR, "apply_loudness": B, "path": PATH}, ["file"])
def t_ref(file: str, apply_color: list | None = None, apply_loudness: bool = False, path: str = "") -> Any:
    prof = SF.reference_profile(_ffmpeg(), file)
    try:
        prof["bpm"] = float(ST.beats(file).get("bpm") or 0)
    except Exception:
        prof["bpm"] = 0.0
    if apply_color or apply_loudness:
        p, pr = load(path)
        if apply_color:
            first = S.find_clip(pr, apply_color[0])
            src_path = pr["assets"][first["asset"]]["path"]
            src = SF.color_stats(_ffmpeg(), src_path, SF._duration(SF._ff(_ffmpeg(), ["-i", src_path])))
            name = re.sub(r'[<>:"/\\|?*]+', "_", "Ref - " + Path(file).stem)[:60]
            SF.write_cube(S.lut_dir() / f"{name}.cube", SF.transfer_lut(src, prof["color"], 17, 0.8), 17, name)
            for cid in apply_color:
                c = S.find_clip(pr, cid)
                c["grade"] = {**(c.get("grade") or {}), "lut": f"{name}.cube", "lutMix": 0.85}
            prof["lut"] = f"{name}.cube"
        if apply_loudness and prof.get("lufs") is not None:
            pr.setdefault("master", {})["lufs"] = round(max(-23.0, min(-9.0, prof["lufs"])), 1)
        save(p, pr)
    return prof


@tool("bake_poster", "Dışa aktarılmış videonun 0. karesine kapak karesi yazar (t verilmezse en canlı kare). Yeni '_kapak' kopyası.",
      {"file": STR, "t": N}, ["file"])
def t_poster(file: str, t: float = -1) -> Any:
    return SF.bake_poster(_ffmpeg(), file, None if t < 0 else float(t))


# ---------------------------------------------------------------- rehber
GUIDE = """KAMI STUDIO KURGU REHBERİ (Claude için; ayrıntı ve sayılar örnek, kural değil)
ALGI: Videoyu izleyemezsin. Sırayla: get_project -> get_transcript (phrases) -> analyze_clip -> karar anlarında source_view / timeline_view.
DÖNGÜ: plan (kullanıcıya düz Türkçe 4-8 cümle) -> onay -> checkpoint save -> düzenle -> timeline_health -> export_checked preview -> timeline_view
ile her kesimi ±1.5 sn kontrol -> düzelt (en çok 3 tur) -> export_checked. Hatayı bir kez gördüysen not et, iki kez gördüysen edit_standard'a kural yaz.
KESİM: Ses önce. Kesimi kelime sınırına oturt, kelimenin içinden kesme; 30-200 ms pay. Dolguyu yalnız iki yanı sessizse kes (speech_cleanup safe).
>=400 ms sessizlik temiz kesimdir, 150-400 ms bak, <150 ms ifade ortası. Konuşmacı geçişinde 400-600 ms nefes bırak. Gülme/vurgu sonrası tepkiyi koru.
Konuşmayı hızlandırma. Uzun duraklamayı 0.2-0.4 sn'ye indir, ritim virgülde kalsın.
SENKRON: remove_ranges diğer izleri otomatik kaydırır (altyazı, yazı, B-roll, bağlı ses). Müzik yatağını ayrı iz + kilit ile koru.
GÖRSEL: 'Sadece dinleyen anlar mı?' Anlıyorsa ekrana metin koyma; anlamıyorsa logo/rakam/kaynak/arayüz göster. Ürün adı geçerse gerçek logo.
Dikey: ilk 0.6-1 sn'de ilk değişim, 3 sn'den uzun hareketsiz çekim yok, liste maddesine bir çekim. Altyazı ağız/çene üstüne gelmesin, Shorts arayüzünün
altına düşmesin (alt %18). Koyu kutu + ince açık kenar her zemin rengine okunur. Yazı büyük harfse Türkçe İ/I doğru olsun.
SES: konuşma -14 LUFS, gerçek tepe -1 dBTP (podcast -16). Müzik hissedilsin fark edilmesin (ducking). SFX görünür bir harekete eşlik eder, her kesime değil.
SON SÖZ: Otomatik kontrol aday sorun bulur, karar kullanıcının. 'Bitti' demeden qc_export sonucunu ve timeline_view'u göster."""


@tool("editing_guide", "Kami Studio kurgu rehberi: algı sırası, kesim kuralları, senkron, görsel, ses, kontrol döngüsü. Kurguya başlamadan bir kez oku.", {})
def t_guide() -> Any:
    return {"guide": GUIDE}


# ---------------------------------------------------------------- otomasyon (boru hatlari)
def pipelines_dir() -> Path:
    d = S.home_dir() / "Otomasyon"
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_pipeline(spec: dict, media: list[str], out_dir: str = "", log=lambda s: None) -> dict:
    """spec: {name, size:[w,h], fps, steps:[{tool, args}], export:{preview, platform, force}}.
    Arg icindeki "$clip" ilk ana video klibi, "$clips" tum ana klipler, "$audio" ilk ses klibi, "$out" cikti yolu olur."""
    from app.core import studio_mcp as M
    name = re.sub(r"[^\w\-]+", "_", spec.get("name") or "otomasyon")[:40]
    stamp = time.strftime("%Y%m%d-%H%M%S")
    w, h = (spec.get("size") or [1920, 1080])[:2]
    # Studio'nun acik projesi degismesin (kullanici o sirada baska projede calisiyor olabilir)
    proj = S.save_project(str(S.home_dir() / "Projeler" / f"{name}-{stamp}{S.PROJECT_EXT}"),
                          S.new_project(f"{name}-{stamp}", int(w), int(h), int(spec.get("fps", 30))))
    M.TOOLS["import_media"]["fn"](paths=list(media), append=True, path=proj)
    od = Path(out_dir or S.home_dir() / "Otomasyon" / "Çıktı")
    od.mkdir(parents=True, exist_ok=True)
    out = str(od / f"{name}-{stamp}.mp4")
    receipt: list[dict] = []

    def subst(v: Any, pr: dict) -> Any:
        v1 = sorted([c for c in pr["clips"] if c.get("track") == "v1"], key=lambda c: float(c["start"]))
        au = [c for c in pr["clips"] if str(c.get("track", "")).startswith("a")]
        if isinstance(v, str):
            return {"$clip": v1[0]["id"] if v1 else "", "$audio": au[0]["id"] if au else "", "$out": out, "$project": proj}.get(v, v) \
                if v != "$clips" else [c["id"] for c in v1]
        if isinstance(v, list):
            return [subst(x, pr) for x in v]
        if isinstance(v, dict):
            return {k: subst(x, pr) for k, x in v.items()}
        return v

    for i, st in enumerate(spec.get("steps") or []):
        nm = st.get("tool", "")
        if nm not in M.TOOLS or nm in ("new_project", "open_project", "export_video"):
            receipt.append({"step": i, "tool": nm, "ok": False, "error": "izin verilmeyen/bilinmeyen araç"})
            continue
        _, pr = load(proj)
        args = {**subst(st.get("args") or {}, pr), "path": proj}
        if "path" not in M.TOOLS[nm]["schema"]["inputSchema"]["properties"]:
            args.pop("path", None)
        log(f"{i + 1}. {nm}")
        try:
            r = M.TOOLS[nm]["fn"](**args)
            receipt.append({"step": i, "tool": nm, "ok": True, "result": _brief(r)})
        except Exception as exc:
            receipt.append({"step": i, "tool": nm, "ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]})
            if st.get("required", True):
                break
    ex = spec.get("export") or {}
    if all(r["ok"] for r in receipt) or ex.get("force"):
        r = t_export_checked(out=out, preview=bool(ex.get("preview")), force=bool(ex.get("force")), platform=ex.get("platform", ""), path=proj)
        receipt.append({"step": "export", "ok": not r.get("blocked"), "result": _brief(r)})
    rec = {"pipeline": name, "project": proj, "out": out if Path(out).is_file() else "", "steps": receipt, "t": stamp}
    (od / f"{name}-{stamp}.makbuz.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), "utf-8")
    return rec


def _brief(r: Any) -> Any:
    s = json.dumps(r, ensure_ascii=False, default=str)
    return r if len(s) < 600 else s[:600] + "…"


@tool("pipeline", "Otomasyon boru hatları (Otomasyon klasöründe .json): action=save (spec: {name, size:[w,h], steps:[{tool, args}], "
      "export:{preview, platform, force}}; argümanlarda $clip/$clips/$audio yer tutucuları) | list | get (name) | run (name, media:[dosya]). "
      "Kayıtlı boru hattına Otomasyon\\<ad> klasörüne dosya bırakmak da onu çalıştırır (Kami açıkken). Her çalıştırma makbuz yazar.",
      {"action": {"type": "string", "enum": ["save", "list", "get", "run"]}, "name": STR, "spec": OBJ, "media": ARR, "out_dir": STR}, ["action"])
def t_pipeline(action: str, name: str = "", spec: dict | None = None, media: list | None = None, out_dir: str = "") -> Any:
    d = pipelines_dir()
    if action == "list":
        return [f.stem for f in sorted(d.glob("*.json"))]
    if action == "save":
        sp = dict(spec or {})
        nm = re.sub(r"[^\w\-]+", "_", name or sp.get("name") or "")[:40]
        if not nm or not isinstance(sp.get("steps"), list):
            raise ValueError("name ve steps gerekli")
        sp["name"] = nm
        (d / f"{nm}.json").write_text(json.dumps(sp, ensure_ascii=False, indent=1), "utf-8")
        (d / nm).mkdir(exist_ok=True)
        return {"saved": nm, "drop_folder": str(d / nm)}
    safe = re.sub(r"[^\w\-]+", "_", name or "")
    f = d / f"{safe}.json"
    if not f.is_file():
        raise ValueError(f"boru hattı yok: {name}")
    sp = json.loads(f.read_text("utf-8"))
    if action == "get":
        return sp
    if not media:
        raise ValueError("media gerekli")
    return run_pipeline(sp, [str(m) for m in media], out_dir)


class DropWatcher:
    """Otomasyon\\<boru hatti adi>\\ klasorune birakilan medya dosyasini o boru hattindan gecirir (Kami acikken).
    Dosya boyutu 3 sn sabit kalinca baslar; islenen dosya 'İşlendi' alt klasorune tasinir."""
    EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".mp3", ".wav", ".m4a", ".flac", ".png", ".jpg", ".jpeg"}

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._seen: dict[str, tuple[int, float]] = {}
        self.busy = False

    def start(self) -> None:
        threading.Thread(target=self._loop, daemon=True, name="kami-otomasyon").start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(3.0):
            try:
                self.scan_once()
            except Exception:
                pass

    def scan_once(self) -> list[dict]:
        done = []
        d = pipelines_dir()
        for spec_f in d.glob("*.json"):
            folder = d / spec_f.stem
            if not folder.is_dir():
                continue
            for f in folder.iterdir():
                if not f.is_file() or f.suffix.lower() not in self.EXT:
                    continue
                st = f.stat()
                prev = self._seen.get(str(f))
                self._seen[str(f)] = (st.st_size, prev[1] if prev and prev[0] == st.st_size else time.time())
                if not prev or prev[0] != st.st_size or time.time() - self._seen[str(f)][1] < 3:
                    continue
                self.busy = True
                try:
                    proc = folder / "İşlendi"
                    proc.mkdir(exist_ok=True)
                    dst = proc / f.name
                    shutil.move(str(f), str(dst))
                    self._seen.pop(str(f), None)
                    rec = run_pipeline(json.loads(spec_f.read_text("utf-8")), [str(dst)], str(folder / "Çıktı"))
                    done.append(rec)
                finally:
                    self.busy = False
        return done
