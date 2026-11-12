"""Lyric video (HyperFrames): senkron sozlerden (LRC / SRT) MP4.

Proje klasoru kurulur (index.html + assets), sonra `npx hyperframes render` calisir. Node.js gerekir;
HyperFrames ilk kullanimda npx ile iner, Chrome'u `hyperframes browser ensure` kurar.
Stiller: kinetic (kelime kelime ziplar), simple (ortada satir), karaoke (dolan renk).
Oran: 16:9 (1920x1080) ya da 9:16 (1080x1920, Reels/TikTok; secilen 15-60 sn).
"""
from __future__ import annotations

import html
import json
import logging
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Callable

from app import paths

log = logging.getLogger("kami")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
HF_VERSION = "0.9"


def parse_lrc(text: str) -> list[tuple[float, str]]:
    out: list[tuple[float, str]] = []
    for line in (text or "").splitlines():
        stamps = re.findall(r"\[(\d+):(\d+(?:[.:]\d+)?)\]", line)
        words = re.sub(r"\[[^\]]*\]", "", line).strip()
        for m, s in stamps:
            out.append((int(m) * 60 + float(s.replace(":", ".")), words))
    return sorted(out)


def parse_srt(text: str) -> list[tuple[float, str]]:
    out = []
    for blk in re.split(r"\n\s*\n", (text or "").replace("\r", "")):
        m = re.search(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->", blk)
        if m:
            t = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) + int(m[4]) / 1000
            body = " ".join(x for x in blk.split("\n")[2:] if x.strip())
            out.append((t, re.sub(r"<[^>]+>", "", body).strip()))
    return out


def find_node() -> str:
    for c in (shutil.which("npx.cmd"), shutil.which("npx"),
              os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "nodejs", "npx.cmd")):
        if c and os.path.isfile(c):
            return c
    return ""


STYLE_CSS = {
    "kinetic": ".line{font-size:var(--fs);font-weight:700;letter-spacing:-.5px}.line .w{display:inline-block;margin:0 .14em}",
    "simple": ".line{font-size:calc(var(--fs) * .82);font-weight:600}",
    "karaoke": ".line{font-size:calc(var(--fs) * .86);font-weight:700;position:relative}.line .base{color:rgba(255,255,255,.35)}"
               ".line .fill{position:absolute;left:0;top:0;right:0;color:#2EE6A6;clip-path:inset(0 100% 0 0);text-shadow:0 0 18px rgba(46,230,166,.55)}",
}


def build(job_dir: Path, audio: str, lines: list[tuple[float, str]], title: str, cover: str, ffmpeg: str,
          style: str = "kinetic", vertical: bool = False, start: float = 0.0, length: float = 0.0) -> float:
    """Projeyi kurar, sureyi dondurur."""
    assets = job_dir / "assets"
    (assets / "fonts").mkdir(parents=True, exist_ok=True)
    W, H = (1080, 1920) if vertical else (1920, 1080)
    # ses: (dikeyde) secilen aralik kesilir, m4a
    dur_full = _duration(ffmpeg, audio)
    if not length or length <= 0:
        length = max(1.0, dur_full - start)
    length = min(length, max(1.0, dur_full - start))
    subprocess.run([ffmpeg, "-v", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", audio, "-vn",
                    "-c:a", "aac", "-b:a", "256k", str(assets / "song.m4a")], check=True, creationflags=NO_WINDOW)
    # kapak: yoksa gomulu kapak, o da yoksa Kami logosu; arka plan onceden bulaniklastirilir
    cov = assets / "cover.jpg"
    src_cover = cover if cover and os.path.isfile(cover) else ""
    if not src_cover:
        subprocess.run([ffmpeg, "-v", "error", "-y", "-i", audio, "-map", "0:v:0", "-frames:v", "1", str(cov)],
                       creationflags=NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not cov.exists():
            src_cover = str(paths.WEB_DIR / "kami.png")
    if src_cover:
        subprocess.run([ffmpeg, "-v", "error", "-y", "-i", src_cover, "-vf", "scale=1024:-2", str(cov)], check=True, creationflags=NO_WINDOW)
    subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(cov), "-vf",
                    f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=40:3,eq=brightness=-0.22:saturation=1.25",
                    str(assets / "bg.jpg")], check=True, creationflags=NO_WINDOW)
    shutil.copy(paths.WEB_DIR / "vendor" / "gsap" / "gsap.min.js", assets / "gsap.min.js")
    shutil.copy(paths.WEB_DIR / "fonts" / "ChakraPetch-Bold.ttf", assets / "fonts" / "ChakraPetch-Bold.ttf")

    # satirlar: aralik icindekiler, bitis = sonraki satir (en fazla 8 sn)
    sel = [(t - start, s) for t, s in lines if start - 0.01 <= t < start + length and s.strip()]
    items = []
    for i, (t, s) in enumerate(sel):
        nxt = sel[i + 1][0] if i + 1 < len(sel) else length
        items.append((max(0.0, t), min(nxt, t + 8.0, length), s))
    fs = 74 if vertical else 92
    body, js = [], []
    for i, (t0, t1, s) in enumerate(items):
        d = max(0.4, t1 - t0)
        txt = html.escape(s)
        if style == "kinetic":
            inner = "".join(f'<span class="w">{html.escape(w)}</span>' for w in s.split())
        elif style == "karaoke":
            inner = f'<span class="base">{txt}</span><span class="fill" id="f{i}">{txt}</span>'
        else:
            inner = txt
        body.append(f'<div id="l{i}" class="clip line" data-start="{t0:.3f}" data-duration="{d:.3f}"><div class="in" id="li{i}">{inner}</div></div>')
        if style == "kinetic":
            js.append(f'tl.from("#li{i} .w",{{y:60,opacity:0,scale:.7,rotation:()=>0,duration:.35,stagger:{min(0.12, d * 0.5 / max(1, len(s.split()))):.3f},ease:"back.out(2)"}},{t0:.3f});'
                      f'tl.to("#li{i}",{{opacity:0,y:-30,duration:.25,ease:"power2.in"}},{t0 + d - 0.27:.3f});')
        elif style == "karaoke":
            js.append(f'tl.from("#li{i}",{{opacity:0,y:20,duration:.25}},{t0:.3f});'
                      f'tl.to("#f{i}",{{clipPath:"inset(0 0% 0 0)",duration:{max(0.3, d - 0.35):.3f},ease:"none"}},{t0 + 0.1:.3f});'
                      f'tl.to("#li{i}",{{opacity:0,duration:.2}},{t0 + d - 0.22:.3f});')
        else:
            js.append(f'tl.from("#li{i}",{{opacity:0,y:24,duration:.4,ease:"power2.out"}},{t0:.3f});'
                      f'tl.to("#li{i}",{{opacity:0,duration:.25}},{t0 + d - 0.27:.3f});')
    cov_sz = 300 if vertical else 220
    doc = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
@font-face{{font-family:"Chakra Petch";src:url("assets/fonts/ChakraPetch-Bold.ttf");font-weight:700}}
html,body{{margin:0;background:#08070C}}
#root{{position:relative;width:{W}px;height:{H}px;overflow:hidden;font-family:"Chakra Petch",sans-serif;color:#fff;--fs:{fs}px}}
#bg{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
#shade{{position:absolute;inset:0;background:radial-gradient(ellipse at center,rgba(8,7,12,.15),rgba(8,7,12,.75))}}
#cov{{position:absolute;{"left:50%;top:180px;margin-left:-150px" if vertical else "left:90px;bottom:80px"};width:{cov_sz}px;height:{cov_sz}px;object-fit:cover;border-radius:18px;box-shadow:0 20px 60px rgba(0,0,0,.6),0 0 0 2px rgba(139,92,246,.6)}}
#ttl{{position:absolute;{"left:0;right:0;top:" + str(180 + cov_sz + 30) + "px;text-align:center" if vertical else "left:" + str(90 + cov_sz + 34) + "px;bottom:96px"};font-size:{30 if vertical else 34}px;line-height:1.25;color:#EDE9F6}}
#ttl small{{display:block;font-size:.62em;color:#A78BFA;letter-spacing:2px;text-transform:uppercase}}
.line{{position:absolute;left:8%;right:8%;top:{"50%" if vertical else "40%"};text-align:center;line-height:1.2;text-shadow:0 4px 24px rgba(0,0,0,.6)}}
.line .in{{transform-origin:50% 50%}}
{STYLE_CSS.get(style, STYLE_CSS["kinetic"])}
</style></head><body>
<div id="root" data-composition-id="main" data-width="{W}" data-height="{H}" data-duration="{length:.3f}" data-fps="30">
<img id="bg" class="clip" src="assets/bg.jpg" data-start="0" data-duration="{length:.3f}">
<div id="shade" class="clip" data-start="0" data-duration="{length:.3f}"></div>
<img id="cov" class="clip" src="assets/cover.jpg" data-start="0" data-duration="{length:.3f}">
<div id="ttl" class="clip" data-start="0" data-duration="{length:.3f}"><small>Kami</small>{html.escape(title)}</div>
{chr(10).join(body)}
<audio id="music" class="clip" src="assets/song.m4a" data-start="0" data-duration="{length:.3f}"></audio>
</div>
<script src="assets/gsap.min.js"></script>
<script>
const tl = gsap.timeline({{paused:true}});
tl.from("#cov",{{scale:.9,opacity:0,duration:.8,ease:"power3.out"}},0);
tl.to("#cov",{{scale:1.04,duration:{length:.3f},ease:"none"}},0.8);
tl.from("#ttl",{{opacity:0,x:-20,duration:.6}},0.3);
{chr(10).join(js)}
window.__timelines = window.__timelines || {{}};
window.__timelines["main"] = tl;
</script></body></html>"""
    (job_dir / "index.html").write_text(doc, encoding="utf-8")
    (job_dir / "kami.json").write_text(json.dumps({"lines": len(items), "length": length, "style": style}), encoding="utf-8")
    return length


def _duration(ffmpeg: str, src: str) -> float:
    ffprobe = str(Path(ffmpeg).with_name("ffprobe" + Path(ffmpeg).suffix))
    if not os.path.isfile(ffprobe):
        ffprobe = shutil.which("ffprobe") or ffprobe
    try:
        r = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src],
                           capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW)
        return float(r.stdout.strip() or 0)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 0.0


def render(job_dir: Path, out: str, on_line: Callable[[str], None], cancel: threading.Event,
           browser: str = "") -> dict:
    npx = find_node()
    if not npx:
        return {"ok": False, "error": "node_yok"}
    env = {**os.environ, "HYPERFRAMES_TELEMETRY": "0", "DO_NOT_TRACK": "1"}
    if browser:
        env["HYPERFRAMES_BROWSER_PATH"] = browser
    tmp_out = job_dir / "out.mp4"
    cmd = [npx, "-y", f"hyperframes@{HF_VERSION}", "render", "--quality", "looks", "-o", str(tmp_out)]
    tail: list[str] = []
    try:
        p = subprocess.Popen(cmd, cwd=str(job_dir), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             encoding="utf-8", errors="replace", env=env, creationflags=NO_WINDOW)
        threading.Thread(target=lambda: (cancel.wait(), p.poll() is None and p.kill()), daemon=True).start()
        for line in p.stdout or []:
            line = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", line).strip()
            if line:
                tail = (tail + [line])[-10:]
                on_line(line)
        rc = p.wait()
    except OSError as exc:
        return {"ok": False, "error": str(exc)[:160]}
    if cancel.is_set():
        return {"ok": False, "error": "cancelled"}
    if rc != 0 or not tmp_out.exists() or tmp_out.stat().st_size < 1000:
        log.warning("HyperFrames basarisiz rc=%s: %s", rc, " | ".join(tail))
        return {"ok": False, "error": (tail[-1] if tail else f"rc={rc}")[:200]}
    shutil.move(str(tmp_out), out)
    return {"ok": True, "out": out}


def edge_path() -> str:
    for c in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        if os.path.isfile(c):
            return c
    return ""
