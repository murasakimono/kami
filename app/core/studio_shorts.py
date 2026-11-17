"""Uzun videodan otomatik kisa klipler (v1.30) — duzenlenebilir Studio projeleri olarak (pisirilmis dosya degil).

1) Analiz: Whisper kuruluysa kelime zamanli transkript (auto_captions), degilse ses enerjisi (ebur128 momentary).
2) Aday pencereler: ifade (nefes) sinirlarinda baslayip cumle sonunda biten 20-60 sn araliklar; puan = ilk ifadede kanca
   (soru, 'neden/nasil/sakin/asla/gizli/hata'...), rakam, konusma yogunlugu, baglacla baslamama; ses modunda ortalama
   yukseklik + degiskenlik. Ortusmeyen en iyi N tanesi.
3) Her biri icin 9:16 proje: tek klip (in/dur penceresi), kadraji doldur, varsa ilgili kelimelerden altyazi (hormozi),
   bolum basligi icin ilk ifade isarete yazilir. Proje yollari doner; Studio'da acip son rotus yapilir.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from app.core import studio as S
from app.core.studio_mcp import N, STR, _ffmpeg, load, save, tool
from app.core.studio_mcp_pro import B, caption_words, pack_phrases

_HOOK = re.compile(r"\b(neden|nas[ıi]l|niye|sak[ıi]n|asla|dikkat|gizli|s[ıi]r|hata|mutlaka|en iyi|en k[öo]t[üu]|inan[ıi]lmaz|"
                   r"kimse|herkes|ger[çc]ek|ilk kez|why|how|secret|never|mistake|best|worst|nobody|everyone|truth)\b", re.I)
_CONJ = re.compile(r"^(ve|ama|fakat|ancak|[çc][üu]nk[üu]|yani|sonra|da|de|and|but|so|because|then)\b", re.I)
_END = re.compile(r"[.!?…]$")


def score_windows(phrases: list[dict], min_sec: float = 20, max_sec: float = 60, count: int = 3) -> list[dict]:
    cands = []
    for i, p in enumerate(phrases):
        s = p["s"]
        e, words, txt, j = p["e"], p["n"], [p["text"]], i
        while e - s < min_sec and j + 1 < len(phrases) and phrases[j + 1]["e"] - s <= max_sec:
            j += 1
            e, words = phrases[j]["e"], words + phrases[j]["n"]
            txt.append(phrases[j]["text"])
        # cumle sonuna kadar uzat (max_sec'i asmadan)
        while not _END.search(txt[-1].strip()) and j + 1 < len(phrases) and phrases[j + 1]["e"] - s <= max_sec:
            j += 1
            e, words = phrases[j]["e"], words + phrases[j]["n"]
            txt.append(phrases[j]["text"])
        dur = e - s
        if dur < min_sec * 0.7:
            continue
        first = p["text"].strip()
        sc = 3.0 * len(_HOOK.findall(first)) + (2.0 if "?" in first else 0) + (1.0 if re.search(r"\d", first) else 0)
        sc += min(3.0, words / max(1.0, dur) / 1.0)            # konusma yogunlugu (kelime/sn)
        sc += 1.0 if _END.search(txt[-1].strip()) else -0.5   # temiz bitis
        sc -= 2.0 if _CONJ.search(first) else 0
        sc += 0.5 * len(_HOOK.findall(" ".join(txt[1:])))
        cands.append({"s": round(max(0.0, s - 0.15), 2), "e": round(e + 0.25, 2), "score": round(sc, 2), "hook": first[:120], "text": " ".join(txt)[:400]})
    cands.sort(key=lambda c: -c["score"])
    out: list[dict] = []
    for c in cands:
        if all(c["e"] <= o["s"] or c["s"] >= o["e"] for o in out):
            out.append(c)
        if len(out) >= count:
            break
    return sorted(out, key=lambda c: c["s"])


def energy_windows(ff: str, file: str, dur: float, clip_sec: float = 40, count: int = 3) -> list[dict]:
    """Transkript yoksa: 1 sn'lik momentary loudness; en canli (yuksek + degisken) pencereler."""
    from app.core import studio_finish as SF
    err = SF._ff(ff, ["-i", file, "-vn", "-af", "ebur128=peak=none", "-f", "null", "-"], 900)
    vals = [float(m.group(1)) for m in re.finditer(r"M:\s*(-?[\d.]+)", err or "")]
    if not vals:
        step = max(clip_sec, dur / max(1, count))
        return [{"s": round(i * step, 2), "e": round(min(dur, i * step + clip_sec), 2), "score": 0, "hook": f"Klip {i + 1}", "text": ""}
                for i in range(count) if i * step < dur]
    per = max(1, int(len(vals) / max(1.0, dur)))           # ebur128 ~10 olcum/sn
    sec = [sum(vals[k:k + per]) / per for k in range(0, len(vals), per)]
    w = int(clip_sec)
    cands = []
    for st in range(0, max(1, len(sec) - w), max(1, w // 4)):
        seg = [v for v in sec[st:st + w] if v > -70]
        if len(seg) < w * 0.6:
            continue
        mean = sum(seg) / len(seg)
        var = (sum((v - mean) ** 2 for v in seg) / len(seg)) ** 0.5
        cands.append({"s": float(st), "e": float(min(dur, st + w)), "score": round(mean + var * 1.5, 2), "hook": "", "text": ""})
    cands.sort(key=lambda c: -c["score"])
    out: list[dict] = []
    for c in cands:
        if all(c["e"] <= o["s"] or c["s"] >= o["e"] for o in out):
            out.append(c)
        if len(out) >= count:
            break
    return sorted(out, key=lambda c: c["s"])


def build_short(file: str, win: dict, words: list[dict], idx: int, stem: str, w: int = 1080, h: int = 1920,
                caption: str = "hormozi") -> str:
    from app.core.studio_mcp import ST as STE
    info = STE.info(file)
    name = f"{stem} - Kısa {idx + 1}"
    safe = re.sub(r'[<>:"/\\|?*]+', "_", name)[:80]
    proj = S.save_project(str(S.home_dir() / "Projeler" / f"{safe}{S.PROJECT_EXT}"), S.new_project(name, w, h, 30))
    p, pr = load(proj)
    aid = S.add_asset(pr, info)
    dur = round(win["e"] - win["s"], 3)
    clip = S.add_clip(pr, asset=aid, track=S.track_for(pr, info["kind"]), start=0.0, dur=dur, **{"in": float(win["s"])})
    clip["fit"] = "cover"
    sub = [{"w": x["w"], "s": round(x["s"] - win["s"], 3), "e": round(x["e"] - win["s"], 3)} for x in words if x["s"] >= win["s"] and x["e"] <= win["e"]]
    if sub:
        S.add_clip(pr, words=sub, start=0.0, dur=dur, style={"caption": caption})
    pr.setdefault("markers", []).append({"t": 0.0, "label": (win.get("hook") or "Kanca")[:60], "color": "#2EE6A6", "kind": "chapter"})
    pr["meta"] = {**(pr.get("meta") or {}), "short_of": file, "window": [win["s"], win["e"]], "score": win.get("score")}
    save(p, pr)
    return proj


@tool("make_shorts", "Uzun videodan otomatik kısa klipler: en vurucu 20-60 sn anları (kanca, soru, yoğunluk, temiz bitiş) bulur ve her biri için "
      "9:16 düzenlenebilir proje açar (kadraj dolu, varsa altyazı). Whisper kuruluysa transkriptle, değilse ses enerjisiyle seçer.",
      {"file": STR, "count": N, "min_sec": N, "max_sec": N, "captions": B, "w": N, "h": N}, ["file"])
def t_shorts(file: str, count: float = 3, min_sec: float = 20, max_sec: float = 60, captions: bool = True, w: float = 1080, h: float = 1920) -> Any:
    from app.core import aitools
    from app.core import studio_mcp as M
    from app.core.studio_mcp import ST as STE
    src = Path(file)
    if not src.is_file():
        raise ValueError("dosya yok")
    info = STE.info(str(src))
    if not info.get("ok"):
        raise ValueError(info.get("error") or "okunamadı")
    count = max(1, min(10, int(count)))
    words: list[dict] = []
    mode = "enerji"
    if captions and aitools.installed("whisper"):
        stamp = time.strftime("%Y%m%d-%H%M%S")
        tmp = S.save_project(str(S.CACHE / f"shorts-analiz-{stamp}{S.PROJECT_EXT}"), S.new_project("analiz", 1920, 1080, 30))
        r = M.TOOLS["import_media"]["fn"](paths=[str(src)], append=True, path=tmp)
        cid = next((x.get("clip") for x in r if x.get("clip")), "")
        if cid:
            M.TOOLS["auto_captions"]["fn"](clip=cid, path=tmp)
            _, apr = load(tmp)
            words = caption_words(apr)
        try:
            Path(tmp).unlink()
        except OSError:
            pass
    if words:
        mode = "transkript"
        wins = score_windows(pack_phrases(words, 0.6), float(min_sec), float(max_sec), count)
    else:
        wins = energy_windows(_ffmpeg(), str(src), float(info.get("dur") or 0), (float(min_sec) + float(max_sec)) / 2, count)
    projects = [build_short(str(src), win, words, i, src.stem, int(w), int(h)) for i, win in enumerate(wins)]
    rec = {"mode": mode, "shorts": [{"project": p, "start": wn["s"], "end": wn["e"], "score": wn["score"], "hook": wn["hook"]} for p, wn in zip(projects, wins)]}
    (S.CACHE / "son_kisalar.json").write_text(json.dumps(rec, ensure_ascii=False), "utf-8")
    return rec
