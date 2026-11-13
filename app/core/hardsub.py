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
    txt = " ".join(str(text or "").split()).strip()
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


def extract_and_translate(
    src: str,
    *,
    lang: str = "",
    burn: bool = False,
    fps: float = 1.0,
    tools: dict[str, str] | None = None,
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

    tmp = tempfile.mkdtemp(prefix="kami_hardsub_")
    try:
        pat = os.path.join(tmp, "f_%05d.png")
        r = subprocess.run(
            [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(p),
                "-vf", f"fps={max(0.5, min(2.0, float(fps)))},crop=iw:ih*0.24:0:ih*0.76",
                pat,
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=300, creationflags=NO_WINDOW,
        )
        if r.returncode != 0:
            return {"ok": False, "error": (r.stderr or "Kare çıkarma başarısız")[:200]}

        pngs = sorted(Path(tmp).glob("f_*.png"))
        if not pngs:
            return {"ok": False, "error": "Hiç kare çıkarılamadı"}

        step = 1.0 / max(0.5, min(2.0, float(fps)))
        raw_frames: list[tuple[float, str]] = []
        for idx, fp in enumerate(pngs):
            b64 = base64.b64encode(fp.read_bytes()).decode("ascii")
            res = ocr.recognize(b64, lang=lang)
            txt = str(res.get("text") or "").strip() if res.get("ok") else ""
            raw_frames.append((idx * step, txt))

        cues = _merge_cues(raw_frames)
        if not cues:
            return {"ok": False, "error": "Alt bantta okunabilir altyazı bulunamadı"}

        srt_path = p.with_suffix(".tr.srt")
        lines: list[str] = []
        for i, (t0, t1, orig) in enumerate(cues, 1):
            tr = translate_text(orig, "tr")
            lines.append(f"{i}\n{_fmt_ts(t0)} --> {_fmt_ts(t1)}\n{tr}\n")
        srt_path.write_text("\n".join(lines), encoding="utf-8")

        out_video = ""
        if burn:
            out_p = converter.out_path(str(p), "mp4", tag="hardsub-tr")
            esc_srt = str(srt_path).replace("\\", "/").replace(":", "\\:")
            use_nvenc = converter.has_nvenc(ffmpeg)
            vcodec = (["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "19", "-b:v", "0"]
                      if use_nvenc else ["-c:v", "libx264", "-preset", "medium", "-crf", "19"])
            vf = (
                "drawbox=x=0:y=ih*0.78:w=iw:h=ih*0.20:color=black@0.78:t=fill,"
                f"subtitles='{esc_srt}':force_style='FontSize=20,PrimaryColour=&H00FFFFFF,Outline=1'"
            )
            rb = subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(p),
                 "-vf", vf, *vcodec, "-pix_fmt", "yuv420p", "-c:a", "copy", str(out_p)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=600, creationflags=NO_WINDOW,
            )
            if rb.returncode != 0:
                out_p.unlink(missing_ok=True)
                return {"ok": False, "error": (rb.stderr or "Altyazı gömme başarısız")[:200], "srt": str(srt_path)}
            out_video = str(out_p)

        return {"ok": True, "srt": str(srt_path), "cues": len(cues), "video": out_video}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
