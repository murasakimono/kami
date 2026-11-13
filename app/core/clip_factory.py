"""Faz 14.1 & 14.2 — Kami Klip Fabrikasi: 9:16 Yuz Takipli Dikey Kurgu & E-Ticaret UGC Hook Matrisi."""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# TikTok / Reels / Shorts arayuz bindirme guvenli alan oranlari (ust, alt, sol, sag)
SAFE_ZONES: dict[str, dict[str, float]] = {
    "tiktok": {"top": 0.13, "bottom": 0.24, "left": 0.04, "right": 0.14},
    "reels": {"top": 0.14, "bottom": 0.22, "left": 0.04, "right": 0.12},
    "shorts": {"top": 0.12, "bottom": 0.20, "left": 0.04, "right": 0.12},
}


def _ffmpeg() -> str:
    try:
        from app.engines.ytdlp_engine import find_ffmpeg
        return find_ffmpeg() or ""
    except Exception:
        import shutil
        return shutil.which("ffmpeg") or ""


def _ffprobe() -> str:
    ff = _ffmpeg()
    if ff:
        cand = Path(ff).with_name("ffprobe.exe" if ff.lower().endswith(".exe") else "ffprobe")
        if cand.is_file():
            return str(cand)
    import shutil
    return shutil.which("ffprobe") or ""


def safe_zone_rect(platform: str = "tiktok", width: int = 1080, height: int = 1920) -> dict[str, int]:
    """Dikey videoda arayuz butonlarinin kapatmadigi guvenli piksel dikdortgenini doner."""
    z = SAFE_ZONES.get((platform or "tiktok").lower(), SAFE_ZONES["tiktok"])
    x1 = int(width * z["left"])
    y1 = int(height * z["top"])
    x2 = int(width * (1.0 - z["right"]))
    y2 = int(height * (1.0 - z["bottom"]))
    return {"x": x1, "y": y1, "width": max(1, x2 - x1), "height": max(1, y2 - y1)}


def _probe_size(video_path: Path) -> tuple[int, int, float]:
    fp = _ffprobe()
    if not fp:
        return (1920, 1080, 0.0)
    r = subprocess.run(
        [fp, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
         "-of", "default=noprint_wrappers=1:nokey=0", str(video_path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15, creationflags=NO_WINDOW,
    )
    w, h, dur = 1920, 1080, 0.0
    for ln in (r.stdout or "").splitlines():
        if ln.startswith("width="):
            w = int(ln.split("=", 1)[1] or 1920)
        elif ln.startswith("height="):
            h = int(ln.split("=", 1)[1] or 1080)
        elif ln.startswith("duration="):
            try:
                dur = float(ln.split("=", 1)[1] or 0.0)
            except ValueError:
                pass
    return (w, h, dur)


def _detect_subject_x_ratio(video_path: Path) -> float:
    """MediaPipe/OpenCV varsa yuz merkez X oranini (0..1) bulur; yoksa 0.5 doner."""
    try:
        import cv2
        import mediapipe as mp
        cap = cv2.VideoCapture(str(video_path))
        ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            return 0.5
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        with mp.solutions.face_detection.FaceDetection(min_detection_confidence=0.5) as fd:
            res = fd.process(rgb)
            if res.detections:
                box = res.detections[0].location_data.relative_bounding_box
                return max(0.15, min(0.85, float(box.xmin + box.width * 0.5)))
    except Exception:
        pass
    return 0.5


def auto_vertical_reframe(
    video_path: str | Path,
    out_path: str | Path = "",
    *,
    x_ratio: float | None = None,
    target_w: int = 1080,
    target_h: int = 1920,
) -> dict[str, Any]:
    """Yatay videoyu yuz/nesne merkezli 9:16 dikey formata kirpar."""
    src = Path(video_path)
    if not src.is_file():
        return {"ok": False, "error": "Video dosyasi bulunamadi"}
    ff = _ffmpeg()
    if not ff:
        return {"ok": False, "error": "FFmpeg bulunamadi"}

    w, h, _ = _probe_size(src)
    ratio = _detect_subject_x_ratio(src) if x_ratio is None else max(0.0, min(1.0, float(x_ratio)))
    crop_w = min(w, max(64, int(round(h * 9 / 16)) // 2 * 2))
    crop_h = min(h, max(64, h // 2 * 2))
    max_x = max(0, w - crop_w)
    crop_x = int(max(0, min(max_x, round(w * ratio - crop_w / 2))))

    dst = Path(out_path) if out_path else src.with_name(f"{src.stem}_9x16.mp4")
    vf = f"crop={crop_w}:{crop_h}:{crop_x}:0,scale={target_w}:{target_h}:flags=lanczos"
    r = subprocess.run(
        [ff, "-y", "-i", str(src), "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-c:a", "aac", "-b:a", "192k", str(dst)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600, creationflags=NO_WINDOW,
    )
    if r.returncode != 0 or not dst.is_file():
        return {"ok": False, "error": (r.stderr or "").splitlines()[-1:] or "Dikey kirpma hatasi"}
    return {"ok": True, "path": str(dst), "crop_x": crop_x, "crop_w": crop_w, "width": target_w, "height": target_h}


def score_highlight_segments(
    transcript_segments: list[dict[str, Any]],
    *,
    clip_sec: float = 35.0,
    max_clips: int = 3,
) -> list[dict[str, Any]]:
    """Transkriptten kanca kelimeleri ve yogunluga gore en vurucu klip araliklarini secer."""
    if not transcript_segments:
        return []
    hook_words = re.compile(r"\b(neden|nasil|sakın|asla|dikkat|gizli|hata|mutlaka|en iyi|inanilmaz|why|how|secret|never|mistake|best)\b|[!?]", re.I)
    scored: list[dict[str, Any]] = []
    for seg in transcript_segments:
        st = float(seg.get("start", 0.0))
        txt = str(seg.get("text") or "").strip()
        if not txt:
            continue
        hits = len(hook_words.findall(txt))
        score = hits * 3.0 + min(3.0, len(txt.split()) / 12.0)
        scored.append({"start": round(max(0.0, st - 1.0), 2), "end": round(st + clip_sec, 2), "score": round(score, 2), "hook": txt[:120]})

    scored.sort(key=lambda x: x["score"], reverse=True)
    chosen: list[dict[str, Any]] = []
    for cand in scored:
        if all(abs(cand["start"] - c["start"]) >= clip_sec * 0.7 for c in chosen):
            chosen.append(cand)
        if len(chosen) >= max_clips:
            break
    return chosen


def extract_viral_clips(
    video_path: str | Path,
    out_dir: str | Path,
    *,
    transcript_segments: list[dict[str, Any]] | None = None,
    max_clips: int = 3,
    clip_sec: float = 35.0,
) -> dict[str, Any]:
    """Uzun videodan en vurucu anlari kesip 9:16 dikey viral kliplere cevirir."""
    src = Path(video_path)
    if not src.is_file():
        return {"ok": False, "error": "Video dosyasi bulunamadi", "clips": []}
    ff = _ffmpeg()
    if not ff:
        return {"ok": False, "error": "FFmpeg bulunamadi", "clips": []}

    dst_dir = Path(out_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    _, _, dur = _probe_size(src)

    windows = score_highlight_segments(transcript_segments or [], clip_sec=clip_sec, max_clips=max_clips)
    if not windows:
        # Transkript yoksa videoyu esit pencerelere bol
        step = max(clip_sec, (dur or clip_sec) / max(1, max_clips))
        windows = [
            {"start": round(i * step, 2), "end": round(i * step + clip_sec, 2), "score": 1.0, "hook": f"Klip {i + 1}"}
            for i in range(max_clips)
            if not dur or i * step < dur
        ]

    ratio = _detect_subject_x_ratio(src)
    clips: list[dict[str, Any]] = []
    for idx, w in enumerate(windows):
        seg_tmp = dst_dir / f"_tmp_seg_{idx}.mp4"
        out_clip = dst_dir / f"{src.stem}_viral_{idx + 1}.mp4"
        span = max(2.0, float(w["end"]) - float(w["start"]))
        rc = subprocess.run(
            [ff, "-y", "-ss", str(w["start"]), "-t", str(span), "-i", str(src),
             "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", str(seg_tmp)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, creationflags=NO_WINDOW,
        )
        if rc.returncode != 0 or not seg_tmp.is_file():
            continue
        reframed = auto_vertical_reframe(seg_tmp, out_clip, x_ratio=ratio)
        seg_tmp.unlink(missing_ok=True)
        if reframed.get("ok"):
            clips.append({"path": str(out_clip), "start": w["start"], "end": w["end"], "score": w["score"], "hook": w["hook"]})

    return {"ok": len(clips) > 0, "clips": clips}


def render_ugc_matrix(
    hooks: list[str],
    body: str,
    ctas: list[str],
    out_dir: str | Path,
    *,
    platform: str = "tiktok",
) -> dict[str, Any]:
    """E-ticaret UGC A/B testi icin Hook x Govde x CTA kombinasyonlarini tek tikla dikey renderlar."""
    ff = _ffmpeg()
    if not ff:
        return {"ok": False, "error": "FFmpeg bulunamadi", "outputs": []}

    valid_hooks = [Path(h) for h in hooks if Path(h).is_file()]
    body_p = Path(body)
    valid_ctas = [Path(c) for c in ctas if Path(c).is_file()]
    if not valid_hooks or not body_p.is_file() or not valid_ctas:
        return {"ok": False, "error": "Gecerli hook, govde ve CTA videolari secin", "outputs": []}

    dst_dir = Path(out_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    sz = safe_zone_rect(platform)
    outputs: list[dict[str, Any]] = []

    norm = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30"
    for hi, hp in enumerate(valid_hooks):
        for ci, cp in enumerate(valid_ctas):
            out_p = dst_dir / f"ugc_h{hi + 1}_c{ci + 1}_{platform}.mp4"
            fc = (
                f"[0:v]{norm}[v0];[1:v]{norm}[v1];[2:v]{norm}[v2];"
                f"[0:a]aresample=48000[a0];[1:a]aresample=48000[a1];[2:a]aresample=48000[a2];"
                f"[v0][a0][v1][a1][v2][a2]concat=n=3:v=1:a=1[v][a]"
            )
            r = subprocess.run(
                [ff, "-y", "-i", str(hp), "-i", str(body_p), "-i", str(cp),
                 "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "192k", str(out_p)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600, creationflags=NO_WINDOW,
            )
            if r.returncode == 0 and out_p.is_file():
                outputs.append({"path": str(out_p), "hook": hp.name, "cta": cp.name, "safe_zone": sz})

    return {"ok": len(outputs) > 0, "platform": platform, "safe_zone": sz, "outputs": outputs}
