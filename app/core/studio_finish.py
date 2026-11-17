"""Kami Studio: yayin oncesi kontrol, kapak karesi, referans videodan stil cikarma.

Fikirler: herk-edit-kit (dogrulama listesi, konusma temizligi kurali), brag (kapak karesi 0. kareye),
rea-video (referans videonun temposunu/rengini/sesini olcup projeye uygulama). Kod Kami'nin kendisi;
numpy yok, yalniz ffmpeg ve saf Python.
"""
from __future__ import annotations

import math
import re
import subprocess
from pathlib import Path
from typing import Any

NO_WINDOW = 0x08000000 if hasattr(subprocess, "STARTUPINFO") else 0

# platform hedefleri: entegre ses yuksekligi (LUFS), tepe (dBTP)
PLATFORMS: dict[str, dict[str, Any]] = {
    "youtube": {"name": "YouTube", "lufs": -14.0, "tp": -1.0},
    "shorts": {"name": "Shorts / Reels / TikTok", "lufs": -14.0, "tp": -1.0, "vertical": True},
    "podcast": {"name": "Podcast / Spotify", "lufs": -16.0, "tp": -1.0},
    "tv": {"name": "TV (EBU R128)", "lufs": -23.0, "tp": -1.0},
}


def _ff(ffmpeg: str, args: list[str], timeout: float = 1800) -> str:
    r = subprocess.run([ffmpeg, "-hide_banner", "-nostdin", *args], capture_output=True, timeout=timeout,
                       creationflags=NO_WINDOW)
    return r.stderr.decode("utf-8", "replace")


def _ff_raw(ffmpeg: str, args: list[str], timeout: float = 600) -> bytes:
    r = subprocess.run([ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", *args], capture_output=True,
                       timeout=timeout, creationflags=NO_WINDOW)
    return r.stdout


def _duration(txt: str) -> float:
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", txt)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def _pairs(txt: str, key: str, total: float) -> list[list[float]]:
    out, cur = [], None
    for m in re.finditer(key + r"_(start|end): ?(-?[\d.]+)", txt):
        t = float(m.group(2))
        if m.group(1) == "start":
            cur = max(0.0, t)
        elif cur is not None:
            out.append([round(cur, 2), round(t, 2)])
            cur = None
    if cur is not None and total:
        out.append([round(cur, 2), round(total, 2)])
    return out


def parse_ebur128(txt: str) -> dict[str, Any]:
    """Ozet (I, LRA, tepe) + 0.1 sn'lik anlik ses (M) dizisi."""
    summ = txt[txt.rfind("Summary:"):] if "Summary:" in txt else ""
    def num(pat: str, src: str) -> float | None:
        m = re.search(pat, src)
        return float(m.group(1)) if m else None
    mom = [(float(m.group(1)), float(m.group(2))) for m in re.finditer(r"t: *([\d.]+) .*?M: *(-?[\d.]+|-inf)", txt)
           if m.group(2) != "-inf"]
    return {"i": num(r"I: *(-?[\d.]+) LUFS", summ), "lra": num(r"LRA: *([\d.]+) LU", summ),
            "tp": num(r"Peak: *(-?[\d.]+|-inf) dBFS", summ), "mom": mom}


def frame_stats(ffmpeg: str, path: str, t: float = 0.0, w: int = 64, h: int = 36) -> dict[str, float]:
    """Tek karenin parlaklik ortalamasi / sapmasi (0-255). t=0 ise gercekten ilk kare."""
    pre = ["-ss", f"{t:.3f}"] if t > 0 else []
    raw = _ff_raw(ffmpeg, [*pre, "-i", path, "-frames:v", "1", "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo", "-"])
    if not raw:
        return {"mean": 0.0, "std": 0.0, "ok": 0.0}
    n = len(raw)
    mean = sum(raw) / n
    std = math.sqrt(sum((b - mean) ** 2 for b in raw) / n)
    return {"mean": round(mean, 1), "std": round(std, 1), "ok": 1.0}


def first_frame_verdict(st: dict[str, float]) -> str:
    """'' iyi; aksi halde neden. Siyah/duz ilk kare akista kapak olarak kotu gorunur."""
    if not st.get("ok"):
        return "okunamadi"
    if st["mean"] < 14:
        return "siyah"
    if st["std"] < 7:
        return "duz"
    return ""


def risk_moments(loud: dict[str, Any], silences: list[list[float]], blacks: list[list[float]],
                 freezes: list[list[float]], total: float, limit: int = 5) -> list[dict[str, Any]]:
    """'Dinlemen/bakman gereken anlar': ani ses sicramalari, uzun sessizlik, siyah/donuk kare. Puanli, birbirinden 2 sn uzak."""
    cand: list[tuple[float, float, str]] = []
    mom = loud.get("mom") or []
    integ = loud.get("i")
    for k in range(10, len(mom)):   # ilk 1 sn: sesin baslamasi sicrama sayilmaz
        t, m = mom[k]
        prev = max(-45.0, sum(x[1] for x in mom[k - 5:k]) / 5)   # sessizlikten giris sicrama sayilmasin diye taban
        if t > 0.6 and m - prev >= 10 and m > -30:
            cand.append((m - prev, t, f"Ani ses sıçraması (+{m - prev:.0f} dB)"))
        if integ is not None and m - integ >= 8:
            cand.append((m - integ - 2, t, f"Çok yüksek an ({m:.0f} LUFS)"))
    for a, b in silences:
        if 0.3 < a < total - 0.5:
            cand.append((4 + (b - a), a, f"Sessizlik {b - a:.1f} sn"))
    for a, b in blacks:
        if a > 0.2 and b < total - 0.2:
            cand.append((8 + (b - a), a, f"Siyah kare {b - a:.1f} sn"))
    for a, b in freezes:
        cand.append((5 + (b - a), a, f"Donuk görüntü {b - a:.1f} sn"))
    out: list[dict[str, Any]] = []
    for score, t, why in sorted(cand, key=lambda x: -x[0]):
        if all(abs(t - o["t"]) > 2 for o in out):
            out.append({"t": round(max(0.0, t - 0.5), 2), "why": why})
        if len(out) >= limit:
            break
    return sorted(out, key=lambda o: o["t"])


def media_qc(ffmpeg: str, path: str, platform: str = "youtube") -> dict[str, Any]:
    """Disa aktarilmis dosyanin yayin oncesi kontrolu. Tek ffmpeg gecisi (goruntu + ses) + ilk kare."""
    tgt = PLATFORMS.get(platform) or PLATFORMS["youtube"]
    txt = _ff(ffmpeg, ["-i", path, "-vf", "scale=320:-2,blackdetect=d=0.2:pix_th=0.08,freezedetect=n=0.002:d=1.5",
                       "-af", "ebur128=peak=true,silencedetect=n=-50dB:d=1.2", "-f", "null", "-"])
    total = _duration(txt)
    has_v = bool(re.search(r"Stream #\S+: Video", txt))
    has_a = bool(re.search(r"Stream #\S+: Audio", txt))
    blacks = [[round(float(a), 2), round(float(b), 2)] for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", txt)]
    freezes = _pairs(txt, "lavfi.freezedetect.freeze", total) or _pairs(txt, "freeze", total)
    silences = _pairs(txt, "silence", total)
    loud = parse_ebur128(txt) if has_a else {"i": None, "lra": None, "tp": None, "mom": []}
    ff = frame_stats(ffmpeg, path) if has_v else {"ok": 0.0}
    issues: list[dict[str, Any]] = []

    def add(level: str, msg: str, t: float | None = None, fix: str = "") -> None:
        issues.append({"level": level, "msg": msg, "t": t, "fix": fix})

    v = first_frame_verdict(ff) if has_v else ""
    if v in ("siyah", "duz"):
        add("warn", "İlk kare " + ("siyah" if v == "siyah" else "düz/boş") + ": akışta ve önizlemede kapak böyle görünür.", 0.0, "poster")
    for a, b in blacks:
        if a < 0.05:
            add("warn", f"Video siyahla başlıyor ({b:.1f} sn).", 0.0)
        elif b > total - 0.1:
            add("info", f"Video siyahla bitiyor ({b - a:.1f} sn).", a)
        else:
            add("err", f"Ortada siyah kare: {b - a:.2f} sn.", a)
    for a, b in freezes:
        add("warn", f"Görüntü {b - a:.1f} sn donuk.", a)
    for a, b in silences:
        if a > 0.3 and b < total - 0.3:
            add("warn", f"Ortada {b - a:.1f} sn sessizlik.", a)
    if has_a and loud["i"] is not None:
        d = loud["i"] - tgt["lufs"]
        if abs(d) > 1.5:
            add("warn", f"Ses yüksekliği {loud['i']:.1f} LUFS, {tgt['name']} hedefi {tgt['lufs']:.0f}. "
                + ("Platform kısacak, dinamik boşa gider." if d > 0 else "Diğer videoların yanında kısık kalır."), None, "loudness")
        if loud["tp"] is not None and loud["tp"] > tgt["tp"]:
            add("err", f"Gerçek tepe {loud['tp']:.1f} dBTP (sınır {tgt['tp']:.0f}): sıkıştırılınca cızırdar.", None, "loudness")
    elif not has_a:
        add("info", "Ses izi yok.")
    order = {"err": 0, "warn": 1, "info": 2}
    issues.sort(key=lambda x: (order[x["level"]], x["t"] if x["t"] is not None else -1))
    return {"ok": True, "duration": round(total, 2), "platform": platform, "target": tgt, "loudness": {k: loud[k] for k in ("i", "lra", "tp")},
            "first_frame": ff, "issues": issues, "listen": risk_moments(loud, silences, blacks, freezes, total)}


def project_qc(project: dict[str, Any]) -> list[dict[str, Any]]:
    """Proje duzeyi kurgu kontrolu: ayni gecis arka arkaya, guvenli alan disi yazi, cok uzun cekim, gec ilk kesim."""
    out: list[dict[str, Any]] = []
    W, H = (project.get("size") or [1920, 1080])[:2]
    vertical = H > W
    clips = sorted(project.get("clips") or [], key=lambda c: float(c.get("start", 0) or 0))
    vids = [c for c in clips if str(c.get("track", "")).startswith("v") and not c.get("text") and not c.get("words")]
    main = [c for c in vids if c.get("track") == "v1"] or vids
    run, last = 0, ""
    for c in main:
        tin = str((c.get("trans") or {}).get("in") or "")
        if tin and tin == last:
            run += 1
            if run == 2:
                out.append({"level": "info", "msg": f"Aynı geçiş (“{tin}”) üst üste 3 kez: tekrar eden geçiş amatör durur.", "t": c.get("start")})
        else:
            run = 0
        last = tin
    if vertical:
        for c in main:
            if float(c.get("dur", 0) or 0) > 3.5 and not c.get("zoom") and not c.get("kf"):
                out.append({"level": "info", "msg": f"{float(c['dur']):.1f} sn hareketsiz çekim (dikeyde ~3 sn üstü izleyiciyi kaçırır). Zoom/kesme düşün.", "t": c.get("start")})
        if main and float(main[0].get("dur", 0) or 0) > 2.0:
            out.append({"level": "info", "msg": "İlk kesim 2 sn'den geç: ilk saniyede bir değişim tutma oranını artırır.", "t": 0.0})
    for c in clips:
        st = c.get("style") or {}
        if not (c.get("text") or c.get("words")):
            continue
        y = float(st.get("y", 0.8 if c.get("words") else 0.5) or 0)
        pos = st.get("pos", "custom")
        if pos == "bottom":
            y = 0.9
        elif pos == "top":
            y = 0.08
        if vertical and (y > 0.82 or y < 0.1):
            out.append({"level": "warn", "msg": "Yazı Shorts/TikTok arayüzünün altında kalabilir (güvenli alan dışı).", "t": c.get("start")})
        size = float(st.get("size", 7) or 7)
        if size < 3.2:
            out.append({"level": "info", "msg": f"Yazı çok küçük (boyut {size:g}); telefonda okunmaz.", "t": c.get("start")})
    return out[:40]


def bake_poster_cmd(ffmpeg: str, src: str, t: float, out: str) -> list[str]:
    """Secilen kareyi videonun 0. karesine yazar (kapak/onizleme iyi gorunsun); ses kopyalanir."""
    return [ffmpeg, "-hide_banner", "-nostdin", "-y", "-i", src, "-ss", f"{max(0.0, t):.3f}", "-i", src,
            "-filter_complex", "[1:v]trim=end_frame=1,setpts=PTS-STARTPTS[p];[0:v][p]overlay=0:0:enable='eq(n,0)':eof_action=repeat[v]",
            "-map", "[v]", "-map", "0:a?", "-c:a", "copy", "-c:v", "libx264", "-crf", "16", "-preset", "medium",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]


def best_poster_time(ffmpeg: str, path: str, total: float, n: int = 12) -> float:
    """Ilk %40'ta en canli (sapmasi yuksek, karanlik olmayan) kare."""
    best, bt = -1.0, 0.0
    for k in range(n):
        t = 0.3 + (max(0.5, total * 0.4) - 0.3) * k / max(1, n - 1)
        s = frame_stats(ffmpeg, path, t)
        score = s["std"] - (30 if s["mean"] < 25 else 0)
        if score > best:
            best, bt = score, t
    return round(bt, 2)


def bake_poster(ffmpeg: str, src: str, t: float | None = None, out: str = "") -> dict[str, Any]:
    p = Path(src)
    if t is None or t < 0:
        t = best_poster_time(ffmpeg, src, _duration(_ff(ffmpeg, ["-i", src])))
    dst = out or str(p.with_name(p.stem + "_kapak" + p.suffix))
    r = subprocess.run(bake_poster_cmd(ffmpeg, src, float(t), dst), capture_output=True, timeout=3600, creationflags=NO_WINDOW)
    if r.returncode != 0 or not Path(dst).is_file():
        return {"ok": False, "error": r.stderr.decode("utf-8", "replace")[-300:]}
    return {"ok": True, "path": dst, "t": t}


# ---------------------------------------------------------------- referans video stili
def color_stats(ffmpeg: str, path: str, total: float, n: int = 10, w: int = 48, h: int = 27) -> dict[str, Any]:
    """Esit aralikli karelerden kanal ortalamasi/sapmasi (0-1) + doygunluk."""
    sums = [0.0, 0.0, 0.0]
    sq = [0.0, 0.0, 0.0]
    sat, cnt = 0.0, 0
    for k in range(n):
        t = total * (k + 0.5) / n if total > 0 else 0
        raw = _ff_raw(ffmpeg, ["-ss", f"{t:.3f}", "-i", path, "-frames:v", "1", "-vf", f"scale={w}:{h},format=rgb24", "-f", "rawvideo", "-"])
        for i in range(0, len(raw) - 2, 3):
            r, g, b = raw[i] / 255, raw[i + 1] / 255, raw[i + 2] / 255
            for ch, v in enumerate((r, g, b)):
                sums[ch] += v
                sq[ch] += v * v
            mx, mn = max(r, g, b), min(r, g, b)
            sat += (mx - mn) / mx if mx > 1e-6 else 0
            cnt += 1
    if not cnt:
        return {"mean": [0.5] * 3, "std": [0.25] * 3, "sat": 0.0}
    mean = [s / cnt for s in sums]
    std = [math.sqrt(max(1e-6, q / cnt - m * m)) for q, m in zip(sq, mean)]
    return {"mean": [round(x, 4) for x in mean], "std": [round(x, 4) for x in std], "sat": round(sat / cnt, 4)}


def transfer_lut(src: dict[str, Any], ref: dict[str, Any], size: int = 17, strength: float = 0.8) -> list[tuple[float, float, float]]:
    """Kanal bazli ortalama/sapma aktarimi (Reinhard'in RGB sadelestirmesi). Asiri esnemeyi sinirlar."""
    ms, ss, mr, sr = src["mean"], src["std"], ref["mean"], ref["std"]
    gain = [max(0.6, min(1.6, sr[c] / max(1e-3, ss[c]))) for c in range(3)]
    s_sat, r_sat = float(src.get("sat") or 0), float(ref.get("sat") or 0)
    sat_k = max(0.6, min(1.5, r_sat / s_sat)) if s_sat > 0.02 else 1.0
    out = []
    for b in range(size):
        for g in range(size):
            for r in range(size):
                v = [r / (size - 1), g / (size - 1), b / (size - 1)]
                t = [(v[c] - ms[c]) * gain[c] + mr[c] for c in range(3)]
                y = 0.2126 * t[0] + 0.7152 * t[1] + 0.0722 * t[2]
                t = [y + (x - y) * sat_k for x in t]
                o = [max(0.0, min(1.0, v[c] + (t[c] - v[c]) * strength)) for c in range(3)]
                out.append((o[0], o[1], o[2]))
    return out


def write_cube(path: Path, data: list[tuple[float, float, float]], size: int, title: str = "Kami Ref") -> Path:
    lines = [f'TITLE "{title}"', f"LUT_3D_SIZE {size}"] + [f"{r:.5f} {g:.5f} {b:.5f}" for r, g, b in data]
    path.write_text("\n".join(lines) + "\n", "utf-8")
    return path


def pacing(cuts: list[float], total: float) -> dict[str, Any]:
    edges = [0.0] + sorted(c for c in cuts if 0.05 < c < total - 0.05) + [total]
    shots = [b - a for a, b in zip(edges, edges[1:]) if b - a > 0.04]
    if not shots:
        return {"shots": 0, "avg": 0.0, "median": 0.0, "per_min": 0.0, "first_cut": 0.0}
    srt = sorted(shots)
    return {"shots": len(shots), "avg": round(sum(shots) / len(shots), 2), "median": round(srt[len(srt) // 2], 2),
            "per_min": round(len(shots) / max(1e-3, total / 60), 1), "first_cut": round(edges[1] if len(edges) > 2 else total, 2),
            "max": round(srt[-1], 2)}


def reference_profile(ffmpeg: str, path: str) -> dict[str, Any]:
    """Referans videonun kurgu temposu, ses yuksekligi ve renk karakteri."""
    txt = _ff(ffmpeg, ["-i", path, "-vf", "scale=160:-2,select='gt(scene,0.3)',showinfo", "-af", "ebur128", "-f", "null", "-"])
    total = _duration(txt)
    cuts = [float(m.group(1)) for m in re.finditer(r"pts_time:([\d.]+)", txt)]
    loud = parse_ebur128(txt)
    return {"ok": True, "duration": round(total, 2), "pacing": pacing(cuts, total), "lufs": loud["i"], "lra": loud["lra"],
            "color": color_stats(ffmpeg, path, total), "vertical": _is_vertical(txt)}


def _is_vertical(txt: str) -> bool:
    m = re.search(r"Video: .*?(\d{2,5})x(\d{2,5})", txt)
    return bool(m and int(m.group(2)) > int(m.group(1)))


# ---------------------------------------------------------------- konusma temizligi (onayli)
FILLER_RE = re.compile(r"^(ı+h*|i{2,}|e{2,}h*|eh+|a{2,}h*|öh+|ö{2,}|hı+m+|hm+|ım{2,}|mm+|um+|uh+m*|erm+|ee+m+)$", re.I)


_SHORT = {"bu", "şu", "ve", "de", "da", "ki", "ne", "mi", "mı", "mu", "mü", "bir", "ben", "sen", "biz", "siz", "çok", "her",
          "the", "an", "to", "in", "on", "and", "but", "for"}


def _norm(w: str) -> str:
    return re.sub(r"[^\w]", "", str(w or "").lower().replace("İ", "i").replace("I", "ı"), flags=re.U)


def speech_suggestions(words: list[dict[str, Any]], gap_ok: float = 0.08, long_pause: float = 0.6) -> list[dict[str, Any]]:
    """Kelime zamanlarindan (w, s, e) silme onerileri: dolgu, tekrar, yarim kalan baslangic, uzun duraklama.

    herk-edit-kit kurali: kesim iki yaninda sessizlik varsa guvenlidir (safe); yoksa oneri yine gelir ama
    varsayilan isaretsizdir, cunku ifadenin ortasindan kesmek komsu kelimeyi kirpar.
    """
    ws = [w for w in words if w.get("e", 0) > w.get("s", 0)]
    out: list[dict[str, Any]] = []
    taken: set[int] = set()

    def gap_before(i: int) -> float:
        return ws[i]["s"] - ws[i - 1]["e"] if i > 0 else 9.0

    def gap_after(i: int) -> float:
        return ws[i + 1]["s"] - ws[i]["e"] if i + 1 < len(ws) else 9.0

    def add(kind: str, i0: int, i1: int, label: str) -> None:
        if any(k in taken for k in range(i0, i1 + 1)):
            return
        taken.update(range(i0, i1 + 1))
        out.append({"kind": kind, "i0": i0, "i1": i1, "s": round(ws[i0]["s"], 3), "e": round(ws[i1]["e"], 3),
                    "text": " ".join(str(ws[k].get("w", "")) for k in range(i0, i1 + 1)), "label": label,
                    "safe": gap_before(i0) >= gap_ok and gap_after(i1) >= gap_ok})

    n = [_norm(w.get("w", "")) for w in ws]
    for i, t in enumerate(n):
        if t and FILLER_RE.match(t):
            add("filler", i, i, "Dolgu sesi")
    for i in range(len(ws) - 3):   # iki kelimelik tekrar: "ben de ben de"
        if n[i] and n[i] == n[i + 2] and n[i + 1] and n[i + 1] == n[i + 3]:
            add("repeat", i, i + 1, "Tekrar")
    for i in range(len(ws) - 1):
        a, b = n[i], n[i + 1]
        if not a or not b:
            continue
        raw = str(ws[i].get("w", ""))
        if a == b and len(a) > 1:
            add("repeat", i, i, "Tekrar")
        elif (raw.endswith("-") or (2 <= len(a) <= 3 and a not in _SHORT)) and b.startswith(a) and len(b) > len(a) + 1:
            add("false", i, i, "Yarım başlangıç")
    for i in range(len(ws) - 1):
        g = ws[i + 1]["s"] - ws[i]["e"]
        if g >= long_pause:
            s, e = ws[i]["e"] + 0.12, ws[i + 1]["s"] - 0.12
            out.append({"kind": "pause", "i0": -1, "i1": -1, "s": round(s, 3), "e": round(e, 3), "text": f"{g:.1f} sn",
                        "label": "Uzun duraklama", "safe": True})
    return sorted(out, key=lambda x: x["s"])
