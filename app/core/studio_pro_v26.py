"""Kami Studio v1.26.0 — Pro & Otonom Kurgu Motoru.

Ozellikler:
- inspect_video_for_ai: Tasarimci Dayi / Video Use yontemi (2 sn kare seridi + ses enerji haritasi + meta)
- apply_audio_reactive: aeon-music-video / Araba & Futbol editleri (bas/RMS nabzina gore zoom + flash)
- auto_reframe_plan: 16:9 -> 9:16 yuz/hareket merkezli dinamik kadraj anahtar kareleri
- SPEED_RAMP_PRESETS: CapCut Pro hiz egrileri (Montage, Hero, Bullet, Jump Cut, Flash In/Out, Velocity)
- PRO_STYLES_V26: Spunkram Araba/Futbol, Iman Gadzhi, MagnatesMedia, Vox, Finzar, Dehancer 35mm, Ali Abdaal
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import struct
import subprocess
from pathlib import Path
from typing import Any

NO_WINDOW = 0x08000000 if hasattr(subprocess, "STARTUPINFO") else 0


# ---------------------------------------------------------------------------
# 1. CapCut Pro Hiz Egrisi (Speed Ramp) Hazir Profilleri -> c.ramp [[t_norm, speed], ...]
# ---------------------------------------------------------------------------
SPEED_RAMP_PRESETS: dict[str, dict[str, Any]] = {
    "montage": {
        "name": "Montage (Hızlı → Yavaş → Hızlı)",
        "pts": [[0.0, 2.2], [0.25, 0.5], [0.65, 0.5], [1.0, 2.0]],
    },
    "hero": {
        "name": "Hero (Giriş Hızlı → Zirve Ağır → Çıkış)",
        "pts": [[0.0, 1.8], [0.35, 2.4], [0.5, 0.35], [0.75, 0.45], [1.0, 1.8]],
    },
    "bullet": {
        "name": "Bullet (Ani Yavaşlama → Patlama)",
        "pts": [[0.0, 2.5], [0.3, 0.3], [0.6, 0.3], [0.85, 2.5], [1.0, 1.2]],
    },
    "jump_cut": {
        "name": "Jump Cut (Vuruşlu Hızlanma)",
        "pts": [[0.0, 1.0], [0.4, 2.4], [0.55, 0.6], [0.85, 2.2], [1.0, 1.0]],
    },
    "flash_in": {
        "name": "Flash In (Hızlı Giriş → Normal)",
        "pts": [[0.0, 3.0], [0.28, 1.0], [1.0, 1.0]],
    },
    "flash_out": {
        "name": "Flash Out (Normal → Hızlı Çıkış)",
        "pts": [[0.0, 1.0], [0.72, 1.0], [1.0, 3.0]],
    },
    "car_velocity": {
        "name": "🏎️ Araba / Futbol Velocity (Spunkram)",
        "pts": [[0.0, 2.6], [0.22, 0.4], [0.45, 0.4], [0.62, 2.8], [0.82, 0.5], [1.0, 2.2]],
    },
}


# ---------------------------------------------------------------------------
# 2. Pro Edit Tarzlari & Receteleri (v1.26.0)
# ---------------------------------------------------------------------------
PRO_STYLES_V26: dict[str, dict[str, Any]] = {
    "car_football_velocity": {
        "id": "car_football_velocity",
        "name": "🏎️ Araba & Futbol Velocity (Spunkram)",
        "desc": "Hero/Velocity hız rampası, bas vuruşuna göre zoom + RGB prizma, halation parlama ve -10 LUFS punch.",
        "grade": {"con": 0.22, "sat": 1.18, "exp": 0.04, "halation": 0.35, "prism": 0.25},
        "zoom_preset": "micro-pump-duo",
        "trans_in": "zoom-in",
        "fx": ["rgb-prism", "motion-glow"],
        "audio_fx": ["hot-montage"],
        "sub_style": "roblox-pop",
        "speed_ramp": "car_velocity",
        "shutter_angle": 220,
        "lufs": -10.0,
    },
    "iman_gadzhi_doc": {
        "id": "iman_gadzhi_doc",
        "name": "🎩 Lüks Belgesel (Iman Gadzhi)",
        "desc": "Koyu sinematik kontrast, hafif film greni, 35mm vinyet, net vokal ve vurgulu kelime altyazısı.",
        "grade": {"con": 0.24, "sat": 0.88, "exp": -0.05, "temp": -0.04, "vignette": 0.45, "grain": 0.18},
        "zoom_preset": "ken-burns-center",
        "trans_in": "fade",
        "audio_fx": ["voice", "podcast-warm"],
        "sub_style": "hormozi-yellow",
        "shutter_angle": 180,
        "lufs": -14.0,
    },
    "magnates_cinema": {
        "id": "magnates_cinema",
        "name": "🎬 Karanlık Belgesel (MagnatesMedia)",
        "desc": "Derin glow, yüksek kontrast, dramatik vinyet, yavaş gerilim zoom ve sinematik ses.",
        "grade": {"con": 0.30, "sat": 0.78, "exp": -0.08, "halation": 0.40, "vignette": 0.55},
        "zoom_preset": "dramatic",
        "trans_in": "burn-warm",
        "fx": ["noir-edge"],
        "audio_fx": ["concert-hall"],
        "sub_style": "doc-serif",
        "shutter_angle": 240,
        "lufs": -13.0,
    },
    "vox_explainer": {
        "id": "vox_explainer",
        "name": "🗺️ Bilgi & Harita Kurgu (Vox)",
        "desc": "Temiz yüksek okunaklı renk, net konuşma, keskin geçişler ve sade belgesel altyazı.",
        "grade": {"con": 0.12, "sat": 1.06, "exp": 0.02},
        "zoom_preset": "ease-in",
        "trans_in": "directional-wipe",
        "audio_fx": ["voice"],
        "sub_style": "clean-box",
        "lufs": -14.0,
    },
    "finzar_gaming": {
        "id": "finzar_gaming",
        "name": "🔥 Hızlı Oyun / Yorum (Finzar)",
        "desc": "Yüksek doygunluk, hızlı zoom-pop, zıplayan oyun altyazısı ve punch ses.",
        "grade": {"con": 0.16, "sat": 1.28, "exp": 0.04},
        "zoom_preset": "zoom-pop-in",
        "trans_in": "swirl-spin",
        "audio_fx": ["voice", "hot-montage"],
        "sub_style": "roblox-pop",
        "lufs": -12.0,
    },
    "dehancer_kodak": {
        "id": "dehancer_kodak",
        "name": "🎞️ 35mm Kodak Film (Dehancer)",
        "desc": "Analog Kodak sıcaklığı, kırmızı highlight halation, organik film greni ve doğal 180° hareket bulanıklığı.",
        "grade": {"con": 0.14, "sat": 0.96, "temp": 0.08, "halation": 0.45, "grain": 0.28, "vignette": 0.30},
        "trans_in": "dreamy-fade",
        "shutter_angle": 180,
        "lufs": -14.0,
    },
    "ali_abdaal_cozy": {
        "id": "ali_abdaal_cozy",
        "name": "☕ Temiz Eğitim & Vlog (Ali Abdaal)",
        "desc": "Yumuşak sıcak aydınlık, net stüdyo mikrofonu ve göz yormayan akıcı geçiş.",
        "grade": {"con": 0.08, "sat": 1.08, "exp": 0.05, "temp": 0.04},
        "zoom_preset": "ease-in",
        "trans_in": "morph-warp",
        "audio_fx": ["voice"],
        "sub_style": "minimal-clean",
        "lufs": -14.0,
    },
}


# ---------------------------------------------------------------------------
# 3. AI 3-in-1 Vision Pack (Tasarimci Dayi / Video Use yontemi)
# ---------------------------------------------------------------------------
def inspect_video_for_ai(ffmpeg: str, path: str, out_dir: Path,
                         interval_s: float = 2.0, max_frames: int = 36) -> dict[str, Any]:
    """Videodan AI ajani icin 2 sn'de bir kare seridi (contact sheet) + ses enerji haritasi + meta cikarir."""
    src = Path(path)
    if not src.is_file():
        return {"ok": False, "error": "file_not_found"}

    out_dir.mkdir(parents=True, exist_ok=True)
    # 1) Sure ve temel stream bilgisi
    pr = subprocess.run([ffmpeg, "-hide_banner", "-i", str(src)], capture_output=True, timeout=30, creationflags=NO_WINDOW)
    txt = pr.stderr.decode("utf-8", "replace")
    m_dur = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", txt)
    dur = int(m_dur.group(1)) * 3600 + int(m_dur.group(2)) * 60 + float(m_dur.group(3)) if m_dur else 0.0
    m_res = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", txt)
    w, h = (int(m_res.group(1)), int(m_res.group(2))) if m_res else (0, 0)
    has_audio = bool(re.search(r"Stream #\S+: Audio", txt))

    # 2) Kare seridi (contact sheet)
    step = max(0.5, float(interval_s))
    if dur > 0 and dur / step > max_frames:
        step = round(dur / max_frames, 2)
    hsh = hashlib.sha1(f"{src}:{src.stat().st_mtime}:{step}".encode()).hexdigest()[:10]
    sheet_path = out_dir / f"{src.stem[:24]}_{hsh}_sheet.jpg"
    cols = 6
    rows = max(1, math.ceil(min(max_frames, max(1, dur / step)) / cols))
    if w > 0 and not sheet_path.is_file():
        vf = f"fps=1/{step:.3f},scale=320:-2,tile={cols}x{rows}:padding=2:color=0x0D0A14"
        subprocess.run(
            [ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-i", str(src),
             "-frames:v", "1", "-vf", vf, "-q:v", "4", str(sheet_path)],
            capture_output=True, timeout=120, creationflags=NO_WINDOW,
        )

    # 3) Ses enerji haritasi (1 sn'lik RMS dB dilimleri)
    energy_map: list[dict[str, Any]] = []
    if has_audio:
        sr = 4000
        au = subprocess.run(
            [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(src),
             "-vn", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
            capture_output=True, timeout=60, creationflags=NO_WINDOW,
        )
        raw = au.stdout[: len(au.stdout) // 2 * 2]
        samples = struct.unpack(f"<{len(raw) // 2}h", raw) if raw else ()
        for sec in range(0, max(1, len(samples) // sr)):
            chunk = samples[sec * sr : (sec + 1) * sr]
            if not chunk:
                continue
            rms = math.sqrt(sum(x * x for x in chunk) / len(chunk)) / 32768.0
            db = round(20.0 * math.log10(max(1e-5, rms)), 1)
            energy_map.append({"t": sec, "db": db, "speech_like": db > -34.0, "peak": db > -14.0})

    return {
        "ok": True,
        "path": str(src),
        "duration": round(dur, 2),
        "w": w,
        "h": h,
        "has_audio": has_audio,
        "step_s": step,
        "contact_sheet": str(sheet_path) if sheet_path.is_file() else "",
        "energy_summary": {
            "total_secs": len(energy_map),
            "quiet_secs": [e["t"] for e in energy_map if not e["speech_like"]][:40],
            "peak_secs": [e["t"] for e in energy_map if e["peak"]][:30],
        },
        "energy_map": energy_map[:180],
    }


# ---------------------------------------------------------------------------
# 4. Audio-Reactive Zoom / Pulse Keyframes (aeon-music-video tarzi)
# ---------------------------------------------------------------------------
def build_audio_reactive_kf(ffmpeg: str, path: str, start: float = 0.0, dur: float = 10.0,
                            clip_dur: float = 10.0, strength: float = 0.14) -> list[dict[str, Any]]:
    """Ses enerjisine gore klibe otomatik {t, z, cx, cy} nabiz anahtar kareleri uretir."""
    sr = 8000
    hop_s = 0.12
    hop = int(sr * hop_s)
    r = subprocess.run(
        [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error",
         "-ss", f"{max(0.0, start):.3f}", "-t", f"{max(0.2, dur):.3f}", "-i", path,
         "-vn", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
        capture_output=True, timeout=60, creationflags=NO_WINDOW,
    )
    raw = r.stdout[: len(r.stdout) // 2 * 2]
    if len(raw) < hop * 4:
        return []
    samples = struct.unpack(f"<{len(raw) // 2}h", raw)
    envs: list[float] = []
    for i in range(0, len(samples) - hop, hop):
        chunk = samples[i : i + hop]
        rms = math.sqrt(sum(x * x for x in chunk) / hop) / 32768.0
        envs.append(rms)
    if not envs:
        return []
    mx = max(envs) or 1e-4
    amp = max(0.03, min(0.45, float(strength)))
    out: list[dict[str, Any]] = []
    prev_z = 1.0
    for idx, val in enumerate(envs):
        t_local = round((idx * hop_s) * (clip_dur / max(0.2, dur)), 3)
        if t_local > clip_dur:
            break
        norm = min(1.0, val / mx)
        target_z = 1.0 + (norm ** 1.4) * amp
        smooth_z = round(prev_z * 0.35 + target_z * 0.65, 3)
        prev_z = smooth_z
        out.append({"t": t_local, "z": smooth_z, "cx": 0.5, "cy": 0.5})
    return out


# ---------------------------------------------------------------------------
# 5. Akilli Oto-Reframe (16:9 -> 9:16 Yuz/Hareket Merkezleme)
# ---------------------------------------------------------------------------
def auto_reframe_plan(path: str, start: float = 0.0, dur: float = 10.0,
                      sample_step: float = 0.5) -> dict[str, Any]:
    """OpenCV varsa yuz/hareket merkezini izler, yoksa merkez/kural tabanli {t, x, y} dondurur."""
    try:
        import cv2
    except Exception:
        return {"ok": True, "method": "center", "kf": [{"t": 0.0, "x": 0.0, "y": 0.0}]}

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return {"ok": False, "error": "video_open_failed"}
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cascade_path = getattr(cv2.data, "haarcascades", "") + "haarcascade_frontalface_default.xml"
    face_det = cv2.CascadeClassifier(cascade_path) if os.path.isfile(cascade_path) else None

    kf: list[dict[str, Any]] = []
    t = 0.0
    last_cx = 0.5
    while t < dur:
        cap.set(cv2.CAP_PROP_POS_MSEC, (start + t) * 1000.0)
        ok, frame = cap.read()
        if not ok:
            break
        h, w = frame.shape[:2]
        cx = last_cx
        if face_det is not None:
            gray = cv2.cvtColor(cv2.resize(frame, (320, max(180, int(320 * h / max(1, w))))), cv2.COLOR_BGR2GRAY)
            faces = face_det.detectMultiScale(gray, 1.15, 4, minSize=(24, 24))
            if len(faces):
                fx, _fy, fw, _fh = max(faces, key=lambda b: b[2] * b[3])
                cx = max(0.2, min(0.8, (fx + fw / 2.0) / 320.0))
        # Kami x ofseti: -0.5..+0.5 merkezden kayma
        off_x = round((0.5 - cx) * 0.65, 3)
        kf.append({"t": round(t, 3), "x": off_x, "y": 0.0})
        last_cx = cx
        t += max(0.25, float(sample_step))
    cap.release()
    return {"ok": True, "method": "face_track" if face_det else "center", "kf": kf or [{"t": 0.0, "x": 0.0, "y": 0.0}]}


# ---------------------------------------------------------------------------
# 6. gl-transitions Tarzi 12 Yeni Gecis (TRANS_V26 + trans_in_v26)
# ---------------------------------------------------------------------------
TRANS_V26: dict[str, str] = {
    "directional-wipe": "Yönlü Silme (GL)",
    "morph-warp": "Morph Esneme (GL)",
    "dreamy-fade": "Rüya Bulanık Geçiş (GL)",
    "cube-rotate": "3D Küp Çevirme (GL)",
    "swirl-spin": "Girdap Bükme (GL)",
    "pixelize-dissolve": "Piksel Dağılma (GL)",
    "window-slice": "Pencere Dilimleri (GL)",
    "radial-wipe": "Saat Radiali (GL)",
    "burn-warm": "Sıcak Film Yanığı (GL)",
    "doom-melt": "Eriyerek Düşüş (GL)",
    "cross-hatch": "Çapraz Tarama (GL)",
    "circle-open": "Merkezden Daire (GL)",
}


def trans_in_v26(kind: str, d: float, W: int, H: int, tag: str = "t", c0: float = 0.0, fps: int = 30) -> str:
    """gl-transitions tarzi gecisler icin FFmpeg filtre zinciri."""
    u = f"min(1,max(0,(t+{c0:.4f})/{d:.4f}))"
    U = f"min(1,max(0,(T+{c0:.4f})/{d:.4f}))"
    e = f"(1-pow(1-{u},3))"
    E = f"(1-pow(1-{U},3))"
    en = f"enable='lt(t,{max(0.001, d - c0):.4f})'"

    if kind == "directional-wipe":
        return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*min(1,max(0,(X/W*0.7+Y/H*0.3-({E}*1.25-0.25))*-5))':{en}"
    if kind == "morph-warp":
        return f"gblur=sigma=8:enable='lt(t,{max(0.001, d - c0):.4f})',eq=brightness='0.1*(1-{u})':eval=frame:{en}"
    if kind == "dreamy-fade":
        return f"gblur=sigma=12:enable='lt(t,{max(0.001, d - c0):.4f})',eq=brightness='0.18*(1-{u})':saturation='1+0.4*(1-{u})':eval=frame:{en}"
    if kind == "cube-rotate":
        sx = f"max(0.05,{E})"
        xs = f"(W/2+(X-W/2)/{sx})"
        return f"geq=r='r({xs},Y)':g='g({xs},Y)':b='b({xs},Y)':a='if(between({xs},0,W-1),alpha({xs},Y),0)':{en}"
    if kind == "swirl-spin":
        return f"rotate=a='(1-{e})*0.65':c=black@0:{en}"
    if kind == "pixelize-dissolve":
        return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lt(mod(floor(X/16)*11+floor(Y/16)*17,23)/23,{E}*1.06),alpha(X,Y),0)':{en}"
    if kind == "window-slice":
        return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lt(mod(X,W/12),{E}*(W/12)+1),alpha(X,Y),0)':{en}"
    if kind == "radial-wipe":
        return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lt((atan2(Y-H/2,X-W/2)+PI)/(2*PI),{E}*1.02),alpha(X,Y),0)':{en}"
    if kind == "burn-warm":
        return f"eq=brightness='0.35*(1-{u})':gamma_r='1+1.1*(1-{u})':gamma_g='1+0.3*(1-{u})':gamma_b='1-0.4*(1-{u})':eval=frame:{en}"
    if kind == "doom-melt":
        return f"pad=iw:ih*2:0:0:color=black@0,crop={W}:{H}:x=0:y='ih/2*(1-{e})'"
    if kind == "cross-hatch":
        return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lt(mod(abs(X-Y),24)/24,{E}*1.05),alpha(X,Y),0)':{en}"
    if kind == "circle-open":
        return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lt(hypot(X-W/2,Y-H/2),{E}*hypot(W/2,H/2)),alpha(X,Y),0)':{en}"
    return "null"

