"""Kami Hardsub: videodaki gömülü yabancı altyazıyı OCR ile okuyup Türkçe .srt / maskeli video üretir."""
from __future__ import annotations

import base64
from difflib import SequenceMatcher
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any
from urllib.parse import quote

import requests

from app.core import converter, ocr

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _fmt_ts(sec: float) -> str:
    ms = int(round(max(0.0, sec) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def translate_text(text: str, target: str = "tr") -> str:
    txt = "\n".join(" ".join(ln.split()) for ln in str(text or "").splitlines()).strip()
    if not txt:
        return ""
    try:
        url = (
            f"https://translate.googleapis.com/translate_a/single"
            f"?client=gtx&sl=auto&tl={quote(target)}&dt=t&q={quote(txt)}"
        )
        r = requests.get(url, timeout=10)
        if r.ok:
            data = r.json()
            parts = [seg[0] for seg in (data[0] or []) if seg and seg[0]]
            if parts:
                return "".join(parts).strip()
    except Exception:
        pass
    return txt


def _similar(a: str, b: str) -> bool:
    if not a or not b:
        return False
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= 0.82


def _merge_cues(frames: list[tuple[float, str]]) -> list[tuple[float, float, str]]:
    cues: list[tuple[float, float, str]] = []
    cur_t0 = 0.0
    cur_t1 = 0.0
    cur_txt = ""
    for t, txt in frames:
        clean = " ".join(txt.split()).strip()
        if not clean:
            if cur_txt:
                cues.append((cur_t0, cur_t1 + 0.9, cur_txt))
                cur_txt = ""
            continue
        if not cur_txt:
            cur_t0, cur_t1, cur_txt = t, t, clean
        elif _similar(cur_txt, clean):
            cur_t1 = t
            if len(clean) > len(cur_txt):
                cur_txt = clean
        else:
            cues.append((cur_t0, max(cur_t1 + 0.9, t), cur_txt))
            cur_t0, cur_t1, cur_txt = t, t, clean
    if cur_txt:
        cues.append((cur_t0, cur_t1 + 1.0, cur_txt))
    return cues


def _filter_sub_image(raw_png: bytes, mode: str) -> bytes:
    """OCR oncesi beyaz/sari altyazi piksellerini Pillow kanal islemleriyle hizlica ayiklar ve ters cevirir."""
    if not mode or mode == "none":
        return raw_png
    try:
        from io import BytesIO
        from PIL import Image, ImageChops, ImageOps
        im = Image.open(BytesIO(raw_png)).convert("RGB")
        r, g, b = im.split()
        mask = Image.new("L", im.size, 0)
        if mode in ("white", "both"):
            rw = r.point(lambda v: 255 if v > 185 else 0)
            gw = g.point(lambda v: 255 if v > 185 else 0)
            bw = b.point(lambda v: 255 if v > 185 else 0)
            diff = ImageChops.difference(ImageChops.lighter(ImageChops.lighter(r, g), b),
                                         ImageChops.darker(ImageChops.darker(r, g), b)).point(lambda v: 255 if v < 45 else 0)
            w_mask = ImageChops.darker(ImageChops.darker(rw, gw), ImageChops.darker(bw, diff))
            mask = ImageChops.lighter(mask, w_mask)
        if mode in ("yellow", "both"):
            ry = r.point(lambda v: 255 if v > 180 else 0)
            gy = g.point(lambda v: 255 if v > 165 else 0)
            by = b.point(lambda v: 255 if v < 130 else 0)
            y_mask = ImageChops.darker(ImageChops.darker(ry, gy), by)
            mask = ImageChops.lighter(mask, y_mask)
        # Windows OCR acik zeminde koyu yaziyi daha iyi okur
        inv = ImageOps.invert(mask)
        buf = BytesIO()
        inv.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return raw_png


def translate_batch(texts: list[str], target: str = "tr", *, use_nllb: bool = False, src_lang: str = "en") -> list[str]:
    """Satirlari yerel NLLB (translate_run) veya 25'erli Google gruplariyla cevirir."""
    if use_nllb and texts:
        try:
            import threading
            from app.core import aitools
            tmp_d = Path(tempfile.mkdtemp(prefix="kami_nllb_"))
            in_srt = tmp_d / "in.srt"
            out_srt = tmp_d / "out.srt"
            in_srt.write_text(
                "\n".join(f"{i}\n00:00:0{i % 9},000 --> 00:00:0{i % 9},500\n{' '.join(str(x).split())}\n"
                          for i, x in enumerate(texts, 1)),
                encoding="utf-8",
            )
            res = aitools._run_json(
                ["app.tools.translate_run", str(in_srt), str(out_srt),
                 (src_lang or "en")[:2], (target or "tr")[:2], "nllb", aitools.models_dir("whisper")],
                lambda _m: None, threading.Event(), "whisper",
            )
            if "done" in res and out_srt.is_file():
                blocks = [b.strip() for b in out_srt.read_text(encoding="utf-8").split("\n\n") if b.strip()]
                parsed = [" ".join(b.splitlines()[2:]).strip() for b in blocks if len(b.splitlines()) >= 3]
                shutil.rmtree(tmp_d, ignore_errors=True)
                if len(parsed) == len(texts):
                    return parsed
            shutil.rmtree(tmp_d, ignore_errors=True)
        except Exception:
            pass
    out: list[str] = []
    for i in range(0, len(texts), 25):
        chunk = [" ".join(str(x or "").split()).strip() for x in texts[i:i + 25]]
        joined = "\n".join(chunk)
        tr_joined = translate_text(joined, target)
        parts = [p.strip() for p in tr_joined.splitlines()]
        if len(parts) == len(chunk):
            out.extend(parts)
        else:
            out.extend(translate_text(x, target) for x in chunk)
    return out


def extract_and_translate(
    src: str,
    *,
    lang: str = "",
    burn: bool = False,
    fps: float = 1.0,
    top_pct: float = 0.76,
    height_pct: float = 0.24,
    color_filter: str = "both",
    use_nllb: bool = False,
    mask_mode: str = "delogo",
    tools: dict[str, str] | None = None,
    ctx: Any = None,
) -> dict[str, Any]:
    p = Path(src)
    if not p.is_file():
        return {"ok": False, "error": "Video dosyası bulunamadı"}
    if not tools:
        from app.engines.ytdlp_engine import find_ffmpeg
        tools = {"ffmpeg": find_ffmpeg() or ""}
    ffmpeg = tools.get("ffmpeg") or ""
    if not ffmpeg:
        return {"ok": False, "error": "ffmpeg bulunamadı"}

    tp = max(0.0, min(0.9, float(top_pct)))
    hp = max(0.08, min(0.5, float(height_pct)))
    if tp + hp > 1.0:
        hp = 1.0 - tp

    tmp = tempfile.mkdtemp(prefix="kami_hardsub_")
    try:
        if ctx:
            ctx.set(10, "Videodan kareler çıkarılıyor...")
        pat = os.path.join(tmp, "f_%05d.png")
        cmd_ex = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(p),
            "-vf", f"fps={max(0.5, min(2.0, float(fps)))},crop=iw:ih*{hp:.2f}:0:ih*{tp:.2f}",
            pat,
        ]
        r = ctx.run_proc(cmd_ex) if ctx else subprocess.run(
            cmd_ex, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=None, creationflags=NO_WINDOW,
        )
        if r.returncode != 0:
            return {"ok": False, "error": (r.stderr or "Kare çıkarma başarısız")[:200]}

        pngs = sorted(Path(tmp).glob("f_*.png"))
        if not pngs:
            return {"ok": False, "error": "Hiç kare çıkarılamadı"}

        step = 1.0 / max(0.5, min(2.0, float(fps)))
        raw_frames: list[tuple[float, str]] = []
        total = len(pngs)
        for idx, fp in enumerate(pngs):
            if ctx and ctx.cancelled.is_set():
                return {"ok": False, "error": "İptal edildi"}
            if ctx and idx % 5 == 0:
                ctx.set(15 + int(45 * idx / max(1, total)), f"OCR okunuyor ({idx + 1}/{total})...")
            raw_b = _filter_sub_image(fp.read_bytes(), color_filter)
            b64 = base64.b64encode(raw_b).decode("ascii")
            res = ocr.recognize(b64, lang=lang)
            txt = str(res.get("text") or "").strip() if res.get("ok") else ""
            raw_frames.append((idx * step, txt))

        cues = _merge_cues(raw_frames)
        if not cues:
            return {"ok": False, "error": "Seçilen bölgede okunabilir altyazı bulunamadı"}

        if ctx:
            ctx.set(65, "Altyazılar Türkçeye çevriliyor...")
        srt_path = p.with_suffix(".hardsub.tr.srt")
        translated = translate_batch([orig for _, _, orig in cues], "tr", use_nllb=use_nllb)
        lines = [
            f"{i}\n{_fmt_ts(t0)} --> {_fmt_ts(t1)}\n{tr}\n"
            for i, ((t0, t1, _), tr) in enumerate(zip(cues, translated), 1)
        ]
        srt_path.write_text("\n".join(lines), encoding="utf-8")

        out_video = ""
        note = ""
        if burn:
            if ctx:
                ctx.set(78, "Türkçe altyazı videoya gömülüyor...")
            out_p = converter.out_path(str(p), "mp4", tag="hardsub-tr")
            safe_srt = srt_path.name.replace("'", "\\'")
            use_nvenc = converter.has_nvenc(ffmpeg)
            vcodec = (["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "19", "-b:v", "0"]
                      if use_nvenc else ["-c:v", "libx264", "-preset", "medium", "-crf", "19"])
            if mask_mode == "box":
                mask_f = f"drawbox=x=0:y=ih*{tp:.2f}:w=iw:h=ih*{hp:.2f}:color=black@0.78:t=fill"
            else:
                mask_f = f"delogo=x=2:y=max(2\\,ih*{tp:.2f}):w=iw-4:h=min(ih-4\\,ih*{hp:.2f}):show=0"
            vf = (
                f"{mask_f},"
                f"subtitles='{safe_srt}':force_style='FontSize=20,PrimaryColour=&H00FFFFFF,Outline=1'"
            )
            cmd_b = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(p),
                     "-vf", vf, *vcodec, "-pix_fmt", "yuv420p", "-c:a", "copy", str(out_p)]
            rb = ctx.run_proc(cmd_b, cwd=str(srt_path.parent)) if ctx else subprocess.run(
                cmd_b, cwd=str(srt_path.parent), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=None, creationflags=NO_WINDOW,
            )
            if rb.returncode != 0:
                out_p.unlink(missing_ok=True)
                return {"ok": False, "error": (rb.stderr or "Altyazı gömme başarısız")[:200], "srt": str(srt_path)}
            out_video = str(out_p)

        return {"ok": True, "srt": str(srt_path), "cues": len(cues), "video": out_video}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
