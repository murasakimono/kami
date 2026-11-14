"""Kami Studio Is Akisi & Kutuphane Araclari (Dalga 7):
- Hyperbrew Version Raptor: akilli proje surum yukseltme & disk cakisma kontrolu
- Hyperbrew Pro IO: wildcard disa aktarim yolu sablonu ({name}_v{ver}_{w}x{h}_{date})
- PluginPlay Copy Pasta: alpha destekli PNG pano kopyala / yapistir koprusu
- Mister Horse / AEJuice / PluginPlay: Stagger, Align, Anchor 9-pt, Copy Ease, Variations, Purge Unused
- Soundly Audio Toolbox: yerel klasorde benzer ses arama (spectral centroid + RMS benzerligi)
- AEJuice Export GIF / WebP & Open Icons / Noto Emoji (Iconify API)
"""
from __future__ import annotations

import copy
import datetime as _dt
import json
import os
import random
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"


# ---------------------------------------------------------------------------------------------------------------
# Hyperbrew Version Raptor + Pro IO
def next_version_path(path: str | Path, mode: str = "smart", save_dir: str | Path = "") -> dict[str, Any]:
    """Proje dosya yolunun sonraki surum adini ve diskte ust surum uyarisi olup olmadigini hesaplar."""
    p = Path(path) if path else Path(save_dir or ".") / "proje.kstudio.json"
    name = p.name
    suf = ".kstudio.json" if name.endswith(".kstudio.json") else p.suffix
    stem = name[: -len(suf)] if suf and name.endswith(suf) else p.stem
    parent = Path(save_dir) if save_dir else p.parent

    m = re.search(r"(.*?)([_-]?v)(\d+)$", stem, re.I)
    if mode == "add" or not m:
        cur_num = int(m.group(3)) if m else 1
        base = m.group(1) if m else stem
        sep = m.group(2) if m else "_v"
        pad = len(m.group(3)) if m else 2
    else:
        base, sep, cur_num, pad = m.group(1), m.group(2), int(m.group(3)), max(2, len(m.group(3)))

    nxt = cur_num + 1
    existing: list[int] = []
    if parent.is_dir():
        pat = re.compile(rf"^{re.escape(base)}{re.escape(sep)}(\d+){re.escape(suf)}$", re.I)
        for fp in parent.iterdir():
            mm = pat.match(fp.name)
            if mm:
                existing.append(int(mm.group(1)))
    highest = max(existing, default=cur_num)
    conflict = any(n > cur_num for n in existing)
    target_num = max(nxt, highest + 1) if conflict and mode == "safe" else nxt
    while (parent / f"{base}{sep}{target_num:0{pad}d}{suf}").exists() and mode == "smart":
        target_num += 1
    out_path = parent / f"{base}{sep}{target_num:0{pad}d}{suf}"
    return {
        "ok": True,
        "current_ver": cur_num,
        "next_ver": target_num,
        "highest_on_disk": highest,
        "conflict": conflict,
        "path": str(out_path),
        "filename": out_path.name,
    }


def version_up_project(project: dict[str, Any], cur_path: str = "", mode: str = "smart",
                       save_dir: str | Path = "") -> dict[str, Any]:
    """Projeyi artirilmis surum adiyla diske kaydeder."""
    from app.core import studio
    info = next_version_path(cur_path or (studio.projects_dir() / f"{project.get('name') or 'proje'}.kstudio.json"), mode, save_dir)
    out = Path(info["path"])
    out.parent.mkdir(parents=True, exist_ok=True)
    pr = copy.deepcopy(project)
    pr["ver_num"] = info["next_ver"]
    saved = studio.save_project(str(out), pr)
    sp = Path(saved)
    return {**info, "path": str(sp), "filename": sp.name, "project": pr}


def pro_io_export_path(project: dict[str, Any], pattern: str = "{name}_v{ver}_{w}x{h}_{date}",
                       ext: str = "mp4", out_dir: str | Path = "", cur_path: str = "") -> dict[str, Any]:
    """Hyperbrew Pro IO wildcard cikti yolu olusturucusu."""
    now = _dt.datetime.now()
    m = re.search(r"[_-]?v(\d+)", Path(cur_path).stem, re.I) if cur_path else None
    ver = int(project.get("ver_num") or (m.group(1) if m else 1))
    safe_name = re.sub(r'[\\/:*?"<>|]+', "_", str(project.get("name") or "kami_video")).strip() or "kami_video"
    tokens = {
        "name": safe_name,
        "ver": f"{ver:02d}",
        "date": now.strftime("%Y%m%d"),
        "time": now.strftime("%H%M%S"),
        "w": str(int(project.get("w") or 1920)),
        "h": str(int(project.get("h") or 1080)),
        "fps": str(int(project.get("fps") or 30)),
        "preset": str(project.get("deliver_preset") or "mp4"),
    }
    pat = str(pattern or "{name}_v{ver}").strip()
    for k, v in tokens.items():
        pat = pat.replace("{" + k + "}", v)
    pat = re.sub(r'[\\/:*?"<>|]+', "_", pat).strip("._ ") or safe_name
    ext_clean = re.sub(r"[^a-z0-9]", "", str(ext or "mp4").lower()) or "mp4"
    base_dir = Path(out_dir) if out_dir else (Path(cur_path).parent if cur_path else Path.home() / "Videos")
    out = base_dir / f"{pat}.{ext_clean}"
    return {"ok": True, "path": str(out), "filename": out.name, "tokens": tokens}


# ---------------------------------------------------------------------------------------------------------------
# PluginPlay Copy Pasta (Windows Clipboard <-> Studio)
def clipboard_copy_frame(project: dict[str, Any], t: float, studio_obj: Any,
                         selected_ids: list[str] | None = None, out_dir: str | Path = "") -> dict[str, Any]:
    """Oynatma kafasindaki kareyi (veya yalniz secili klipleri) PNG'ye isler ve Windows panosuna koyar."""
    pr = copy.deepcopy(project)
    if selected_ids:
        keep = set(str(x) for x in selected_ids)
        pr["clips"] = [c for c in pr.get("clips", []) if str(c.get("id")) in keep]
        if not pr["clips"]:
            return {"ok": False, "error": "no_matching_clips"}
    import tempfile
    d = Path(out_dir) if out_dir else Path(tempfile.gettempdir())
    d.mkdir(parents=True, exist_ok=True)
    png = d / f"kami_copy_{int(t * 1000)}.png"
    studio_obj.frame(pr, float(t), str(png))
    if not png.is_file():
        return {"ok": False, "error": "render_failed"}
    copied = _win_copy_image(png)
    return {"ok": True, "copied": copied, "path": str(png)}


def _win_copy_image(png_path: Path) -> bool:
    if os.name != "nt":
        return False
    ps_path = str(png_path).replace("'", "''")
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "Add-Type -AssemblyName System.Drawing; "
        f"$img = [System.Drawing.Image]::FromFile('{ps_path}'); "
        "$do = New-Object System.Windows.Forms.DataObject; "
        "$do.SetImage($img); "
        "$fl = New-Object System.Collections.Specialized.StringCollection; "
        f"$fl.Add('{ps_path}'); "
        "$do.SetFileDropList($fl); "
        "[System.Windows.Forms.Clipboard]::SetDataObject($do, $true); "
        "$img.Dispose()"
    )
    try:
        r = subprocess.run(["powershell", "-STA", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=12, creationflags=NO_WINDOW)
        return r.returncode == 0
    except Exception:
        return False


def clipboard_paste_image(dest_dir: str | Path) -> dict[str, Any]:
    """Windows panosundaki gorseli veya kopyalanan resim dosyasini seffaf PNG olarak diske kaydeder."""
    d = Path(dest_dir)
    d.mkdir(parents=True, exist_ok=True)
    ts = int(_dt.datetime.now().timestamp() * 1000)
    out = d / f"clipboard_{ts}.png"
    try:
        from PIL import Image, ImageGrab
        grab = ImageGrab.grabclipboard()
        if isinstance(grab, list):
            for fp in grab:
                p = Path(fp)
                if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
                    im = Image.open(p).convert("RGBA")
                    im.save(out, "PNG")
                    return {"ok": True, "path": str(out), "w": im.width, "h": im.height, "source": "clipboard-file"}
        elif grab is not None:
            im = grab.convert("RGBA")
            im.save(out, "PNG")
            return {"ok": True, "path": str(out), "w": im.width, "h": im.height, "source": "clipboard-bitmap"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:180]}
    return {"ok": False, "error": "clipboard_empty"}


# ---------------------------------------------------------------------------------------------------------------
# Mister Horse Shifter, Align, 9-pt Anchor, AEJuice Copy Ease / Purge / PluginPlay Variations
ANCHOR_PTS = {
    "tl": (0.18, 0.18), "tc": (0.5, 0.18), "tr": (0.82, 0.18),
    "ml": (0.18, 0.50), "center": (0.5, 0.50), "mr": (0.82, 0.50),
    "bl": (0.18, 0.82), "bc": (0.5, 0.82), "br": (0.82, 0.82),
}


def anchor_9pt(project: dict[str, Any], clip_id: str, point: str = "center") -> dict[str, Any]:
    """Klibi / metni 9 noktali sabitleme hizasina gore konumlandirir."""
    pt = ANCHOR_PTS.get(point, (0.5, 0.5))
    c = next((x for x in project.get("clips", []) if x.get("id") == clip_id), None)
    if not c:
        return {"ok": False, "error": "clip_not_found"}
    c["anchor"] = point
    if any(k in c for k in ("text", "words", "graphic", "sticker", "subscribe", "style")):
        st = c.setdefault("style", {})
        st["pos"] = "custom"
        st["x"] = pt[0]
        st["y"] = pt[1]
    else:
        c["cx"] = pt[0]
        c["cy"] = pt[1]
    return {"ok": True, "clip_id": clip_id, "point": point, "x": pt[0], "y": pt[1]}


def stagger_clips(project: dict[str, Any], clip_ids: list[str] | None = None, step: float = 0.08,
                  order: str = "asc", align: str = "", shift_frames: int = 0) -> dict[str, Any]:
    """Mister Horse Transition Shifter: secili klipleri basamaklar, hizalar veya kare bazli kaydirir."""
    all_clips = project.get("clips", [])
    targets = [c for c in all_clips if not clip_ids or c.get("id") in clip_ids]
    if not targets:
        return {"ok": False, "count": 0, "error": "no_clips"}
    fps = max(1, int(project.get("fps") or 30))
    targets.sort(key=lambda c: float(c.get("start", 0)))
    base = float(targets[0].get("start", 0))
    if shift_frames:
        dt = float(shift_frames) / fps
        for c in targets:
            c["start"] = round(max(0.0, float(c.get("start", 0)) + dt), 4)
        return {"ok": True, "count": len(targets), "shifted_sec": round(dt, 4)}
    if align in ("left", "center", "right"):
        if align == "left":
            anchor = min(float(c.get("start", 0)) for c in targets)
            for c in targets:
                c["start"] = round(anchor, 4)
        elif align == "right":
            end_t = max(float(c.get("start", 0)) + float(c.get("dur", 1)) for c in targets)
            for c in targets:
                c["start"] = round(max(0.0, end_t - float(c.get("dur", 1))), 4)
        else:
            mid = sum(float(c.get("start", 0)) + float(c.get("dur", 1)) / 2 for c in targets) / len(targets)
            for c in targets:
                c["start"] = round(max(0.0, mid - float(c.get("dur", 1)) / 2), 4)
        return {"ok": True, "count": len(targets), "aligned": align}

    ordered = list(targets)
    if order == "desc":
        ordered = ordered[::-1]
    elif order == "random":
        random.Random(42).shuffle(ordered)
    elif order == "pyramid":
        mid_out: list[dict[str, Any]] = []
        lo, hi = 0, len(ordered) - 1
        while lo <= hi:
            mid_out.append(ordered[lo])
            if lo != hi:
                mid_out.append(ordered[hi])
            lo += 1
            hi -= 1
        ordered = mid_out
    step = float(step or 0.08)
    for idx, c in enumerate(ordered):
        c["start"] = round(max(0.0, base + idx * step), 4)
    return {"ok": True, "count": len(ordered), "order": order, "step": step}


def copy_ease_apply(project: dict[str, Any], src_clip_id: str, dst_clip_ids: list[str],
                    include_style: bool = True) -> dict[str, Any]:
    """AEJuice Copy Ease: kaynak klibin keyframe/zoom/animasyon/stili hedef kliplere orantili uygular."""
    clips = {c.get("id"): c for c in project.get("clips", [])}
    src = clips.get(src_clip_id)
    if not src:
        return {"ok": False, "error": "source_not_found"}
    sdur = max(0.05, float(src.get("dur") or 1.0))
    applied: list[str] = []
    for did in dst_clip_ids:
        if did == src_clip_id or did not in clips:
            continue
        dst = clips[did]
        ddur = max(0.05, float(dst.get("dur") or 1.0))
        ratio = ddur / sdur
        for kname in ("kf", "zoom"):
            if isinstance(src.get(kname), list) and src[kname]:
                cloned = []
                for pt in src[kname]:
                    np = copy.deepcopy(pt)
                    if "t" in np:
                        t_v = float(np["t"])
                        np["t"] = round(t_v * ratio, 4) if t_v >= 0 else t_v
                    cloned.append(np)
                dst[kname] = cloned
        if include_style:
            for fld in ("anim", "fx", "grade", "adj", "blend", "trans"):
                if fld in src and src[fld] is not None:
                    dst[fld] = copy.deepcopy(src[fld])
        applied.append(did)
    return {"ok": True, "source": src_clip_id, "applied": applied}


ASPECT_PRESETS = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
    "16:9": (1920, 1080),
}


def create_variations(project: dict[str, Any], presets: list[str] | None = None,
                      save_dir: str | Path = "", cur_path: str = "") -> dict[str, Any]:
    """AtomX Auto-Resize + PluginPlay Variations: coklu en-boy projeleri uretir."""
    from app.core import studio
    targets = [p for p in (presets or ["9:16", "1:1", "4:5"]) if p in ASPECT_PRESETS]
    if not targets:
        return {"ok": False, "error": "no_valid_presets"}
    src_w = max(1, int(project.get("w") or 1920))
    src_h = max(1, int(project.get("h") or 1080))
    out_dir = Path(save_dir) if save_dir else (Path(cur_path).parent if cur_path else studio.projects_dir())
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"\.kstudio$", "", Path(cur_path).stem if cur_path else str(project.get("name") or "proje"))
    results: list[dict[str, Any]] = []
    for key in targets:
        nw, nh = ASPECT_PRESETS[key]
        pr = copy.deepcopy(project)
        pr["w"], pr["h"] = nw, nh
        pr["name"] = f"{project.get('name') or stem} ({key})"
        # Metin boyutunu dikey/kare oranda okunur kil
        scale_f = max(0.75, min(1.25, (nh / src_h) * (src_w / nw) ** 0.25))
        for c in pr.get("clips", []):
            if nw < nh and c.get("fit") == "contain":
                c["fit"] = "cover"
            if isinstance(c.get("style"), dict):
                st = c["style"]
                if "size" in st:
                    st["size"] = round(float(st["size"]) * scale_f, 2)
                if nw < nh and st.get("pos") == "bottom":
                    st["y"] = 0.78
                    st["pos"] = "custom"
                    st.setdefault("x", 0.5)
        slug = key.replace(":", "x")
        fp = out_dir / f"{stem}_{slug}.kstudio.json"
        saved_fp = studio.save_project(str(fp), pr)
        results.append({"preset": key, "w": nw, "h": nh, "path": saved_fp})
    return {"ok": True, "variations": results}


def purge_unused_assets(project: dict[str, Any]) -> dict[str, Any]:
    """AEJuice Clean Unused Assets: zaman cizelgesinde hic kullanilmayan medya varliklarini temizler."""
    assets = project.get("assets") or {}
    used = {c.get("asset") for c in project.get("clips", []) if c.get("asset")}
    unused = [aid for aid in list(assets.keys()) if aid not in used]
    for aid in unused:
        del assets[aid]
    return {"ok": True, "removed_count": len(unused), "removed_ids": unused, "remaining": len(assets)}


# ---------------------------------------------------------------------------------------------------------------
# Soundly Find Similar + Export GIF/WebP + Open Icons (Iconify)
def _audio_signature(path: Path, ffmpeg_bin: str) -> tuple[float, float, float] | None:
    if not path.is_file():
        return None
    try:
        r = subprocess.run(
            [ffmpeg_bin, "-v", "error", "-t", "6", "-i", str(path), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
            capture_output=True, timeout=8, creationflags=NO_WINDOW,
        )
        if r.returncode != 0 or len(r.stdout) < 64:
            return None
        import numpy as np
        arr = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(arr * arr) + 1e-12))
        zcr = float(np.mean(arr[1:] * arr[:-1] < 0))
        dur_est = len(arr) / 16000.0
        return (rms, zcr, dur_est)
    except Exception:
        return None


def find_similar_sounds(target_path: str, search_dirs: list[str | Path], ffmpeg_bin: str,
                        limit: int = 12) -> dict[str, Any]:
    """Secili ses dosyasinin enerji / tiz / sure karakterine en yakin yerel sesleri listeler."""
    tp = Path(target_path)
    sig0 = _audio_signature(tp, ffmpeg_bin)
    if sig0 is None:
        return {"ok": False, "error": "cannot_read_target"}
    exts = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac"}
    cands: list[Path] = []
    for sd in search_dirs:
        p = Path(sd)
        if not p.is_dir():
            continue
        for fp in p.rglob("*"):
            if fp.is_file() and fp.suffix.lower() in exts and fp.resolve() != tp.resolve():
                cands.append(fp)
                if len(cands) >= 120:
                    break
    scored: list[dict[str, Any]] = []
    for fp in cands:
        s1 = _audio_signature(fp, ffmpeg_bin)
        if s1 is None:
            continue
        d = (
            abs(s1[0] - sig0[0]) * 2.5
            + abs(s1[1] - sig0[1]) * 4.0
            + min(3.0, abs(s1[2] - sig0[2]) / max(0.3, sig0[2]))
        )
        scored.append({"name": fp.stem, "path": str(fp), "score": round(max(0.0, 1.0 - d / 5.0), 3), "dur": round(s1[2], 2)})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return {"ok": True, "matches": scored[:limit]}


def export_gif_webp(project: dict[str, Any], out_path: str, ffmpeg_bin: str, studio_obj: Any,
                    fmt: str = "gif", fps: int = 15, width: int = 720, loop: int = 0) -> dict[str, Any]:
    """AEJuice Export GIF / WebP: 2 gecisli palettegen GIF veya animasyonlu WebP ciktisi."""
    import tempfile
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fmt_c = "webp" if str(fmt).lower() == "webp" or out.suffix.lower() == ".webp" else "gif"
    with tempfile.TemporaryDirectory(prefix="kgif_") as td:
        tmp_mp4 = Path(td) / "base.mp4"
        jid = studio_obj.export(project, str(tmp_mp4), {"preset": "fast", "hw": False})
        import time as _t
        while True:
            st = studio_obj.job(jid)
            if st.get("state") in ("done", "error", "cancelled"):
                break
            _t.sleep(0.15)
        if st.get("state") != "done" or not tmp_mp4.is_file():
            return {"ok": False, "error": st.get("error") or "base_export_failed"}
        fps_c = max(6, min(30, int(fps or 15)))
        w_c = max(160, min(1920, int(width or 720)))
        if fmt_c == "webp":
            cmd = [
                ffmpeg_bin, "-v", "error", "-y", "-i", str(tmp_mp4),
                "-vf", f"fps={fps_c},scale={w_c}:-2:flags=lanczos",
                "-c:v", "libwebp", "-lossless", "0", "-q:v", "82", "-loop", str(int(loop)), str(out),
            ]
        else:
            pal = Path(td) / "pal.png"
            r1 = subprocess.run(
                [ffmpeg_bin, "-v", "error", "-y", "-i", str(tmp_mp4),
                 "-vf", f"fps={fps_c},scale={w_c}:-2:flags=lanczos,palettegen=stats_mode=diff", str(pal)],
                capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW,
            )
            if r1.returncode != 0 or not pal.is_file():
                return {"ok": False, "error": r1.stderr[-200:]}
            cmd = [
                ffmpeg_bin, "-v", "error", "-y", "-i", str(tmp_mp4), "-i", str(pal),
                "-lavfi", f"fps={fps_c},scale={w_c}:-2:flags=lanczos[x];[x][1:v]paletteuse=dither=sierra2_4a",
                "-loop", str(int(loop)), str(out),
            ]
        r2 = subprocess.run(cmd, capture_output=True, text=True, timeout=90, creationflags=NO_WINDOW)
        if r2.returncode != 0 or not out.is_file():
            return {"ok": False, "error": r2.stderr[-250:]}
    return {"ok": True, "path": str(out), "format": fmt_c, "size": out.stat().st_size}


def search_open_icons(query: str, prefix: str = "", limit: int = 36) -> dict[str, Any]:
    """Acik kaynak Iconify (Material Icons, Noto Emoji, Twemoji, Lucide) ucretsiz vektor aramasi."""
    q = urllib.parse.quote(str(query or "star").strip() or "star")
    p_param = f"&prefix={urllib.parse.quote(prefix)}" if prefix else "&prefixes=mdi,lucide,noto,twemoji,solar"
    url = f"https://api.iconify.design/search?query={q}{p_param}&limit={min(64, max(1, int(limit or 36)))}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        icons = data.get("icons") or []
        return {
            "ok": True,
            "icons": [
                {"id": ic, "svg_url": f"https://api.iconify.design/{ic.replace(':', '/')}.svg"}
                for ic in icons
            ],
        }
    except Exception as exc:
        return {"ok": False, "icons": [], "error": str(exc)[:180]}


def fetch_open_icon_file(icon_id: str, dest_dir: str | Path, color: str = "", size: int = 512,
                         png_b64: str = "") -> dict[str, Any]:
    """Secili Iconify SVG/PNG varligini seffaf dosya olarak indirir (veya UI canvas PNG'sini kaydeder)."""
    d = Path(dest_dir)
    d.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", icon_id) or "icon"
    if png_b64 and str(png_b64).startswith("data:image/png"):
        import base64
        out = d / f"{slug}.png"
        out.write_bytes(base64.b64decode(png_b64.split(",", 1)[1]))
        return {"ok": True, "path": str(out), "kind": "image"}
    path_part = icon_id.replace(":", "/")
    col_q = f"?color={urllib.parse.quote(color)}&height={int(size)}" if color else f"?height={int(size)}"
    url = f"https://api.iconify.design/{path_part}.svg{col_q}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=10) as resp:
            svg_txt = resp.read().decode("utf-8")
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:180]}
    svg_file = d / f"{slug}.svg"
    svg_file.write_text(svg_txt, encoding="utf-8")
    # Headless Playwright varsa PNG rasterizasyonu dene (FFmpeg girisi olarak da dogrudan kullanilabilsin diye)
    png_file = d / f"{slug}.png"
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            br = p.chromium.launch()
            pg = br.new_page(viewport={"width": int(size), "height": int(size)})
            pg.set_content(f"<html><body style='margin:0;background:transparent'>{svg_txt}</body></html>")
            pg.locator("svg").first.screenshot(path=str(png_file), omit_background=True)
            br.close()
        if png_file.is_file():
            return {"ok": True, "path": str(png_file), "svg_path": str(svg_file), "kind": "image"}
    except Exception:
        pass
    return {"ok": True, "path": str(svg_file), "kind": "svg"}
