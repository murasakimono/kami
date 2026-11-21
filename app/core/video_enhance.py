"""Kami Video Iyilestirici: eski/bozuk videoyu temizler, buyutur, akicilastirir.

Neden gercek zamanli degil: oynatma sirasinda kare basina ~16 ms butce var (60 fps); o butcede
yalnizca shader tabanli upscaler'lar (Anime4K, FSR) calisir ve bunlar denoise / deblock / detay
kurtarma YAPMAZ -- sadece kenari keskinlestirir. Burada butce yok: kare basina saniyeler harcanabilir.

Iki yol var:

1) FILTRE (model gerekmez, TEK ffmpeg gecisi, gecici dosya YOK):
   bwdif (interlace) + hqdn3d / atadenoise (gurultu) + istege bagli lanczos buyutme.
   "Sadece Sinema HD'den iyisi" isteyen icin en hizli gercek kazanc.

2) KARE HATTI (ncnn-vulkan; Python/torch/CUDA kurulumu GEREKMEZ):
   ffmpeg kareleri cikarir -> Real-ESRGAN buyutur -> RIFE ara kare uretir -> ffmpeg birlestirir + sesi geri takar.
   Uzun video parca parca (chunk) islenir: disk sismez, bellek patlamaz.

Cikti: ~/Videos/Kami Studio/Iyilestirilmis

Sozlesme: is (job) sozlugu {"id","state","p","line","cancel":Event,"result","error","info"}.
Durumlar: running -> done | error | cancelled
"""
from __future__ import annotations

import json
import math
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from app.core import studio_enhance as se

log = logging.getLogger(__name__)

NO_WINDOW = se.NO_WINDOW
OUT_SUBDIR = "İyileştirilmiş"
WORK_ENV = "KAMI_ENH_WORK"   # gecici klasor kokunu degistirir (testler icin; varsayilan sistem temp)
MAX_SINGLE_FRAMES = 6000     # bu sayiya kadar tek gecis; ustunde parcalanir
CHUNK_FRAMES = 3000          # parca boyu (kare)

# Presetler tek kaynak: arayuz bu listeyi cizer, motor bunu calistirir.
PRESETS: dict[str, dict[str, Any]] = {
    "temizle": {
        "ad": "Temizle", "model": False, "upscale": 0, "interp": 0,
        "aciklama": "Interlace taranmasini ve gurultuyu temizler; boyut ayni kalir. Model gerekmez, hizli.",
    },
    "hizli": {
        "ad": "Hizli buyut", "model": False, "upscale": 2, "interp": 0,
        "aciklama": "2x lanczos buyutme + keskinlestirme. Model gerekmez, cok hizli; detay kurtarmaz.",
    },
    "netlestir": {
        "ad": "Netlestir (AI)", "model": True, "upscale": 2, "interp": 0,
        "aciklama": "Real-ESRGAN ile 2x/4x yapay zeka buyutme. Titrek (flicker) olabilir; test et.",
    },
    "akici": {
        "ad": "Akicilastir", "model": True, "upscale": 0, "interp": 2,
        "aciklama": "RIFE ile 60 fps ara kare; cozunurluk ayni kalir.",
    },
    "sinema": {
        "ad": "Sinema (AI)", "model": True, "upscale": 2, "interp": 2,
        "aciklama": "Temizle + Real-ESRGAN 2x + 60 fps. En iyi klasik sonuc, yavas.",
    },
    "yeniden": {
        "ad": "Yeniden üret (AI 4x)", "model": True, "flashvsr": True, "upscale": 4, "interp": 0,
        "aciklama": "FlashVSR difuzyon: kareyi bastan cizer, 4x buyutur. En guclu sonuc ama cok yavas; "
                    "yuz ve yazi degisebilir. Deneysel.",
    },
    "trt": {
        "ad": "Netleştir (TRT)", "model": True, "trt": True, "upscale": 2, "interp": 0,
        "aciklama": "TensorRT + VapourSynth ile 2x buyutme (ayni agirliklar, boru hatti). "
                    "Olculen hiz farki kucuk; alternatif motor.",
    },
}

_JOBS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


class _Cancelled(Exception):
    """Kullanici isi iptal etti (kill edilen alt surec)."""


# ------------------------------------------------------------------ genel

def presets() -> list[dict[str, Any]]:
    """Arayuz icin preset listesi (JSON'a uygun)."""
    return [{"id": k, "ad": v["ad"], "aciklama": v["aciklama"], "model": bool(v["model"]),
             "upscale": int(v["upscale"]), "interp": int(v["interp"]),
             "flashvsr": bool(v.get("flashvsr")), "trt": bool(v.get("trt"))}
            for k, v in PRESETS.items()]


def tools() -> dict[str, bool]:
    """Hangi motorlar kurulu."""
    from app.core import flashvsr as fv, vs_trt
    return {"esrgan": se.installed("esrgan"), "rife": se.installed("rife"),
            "flashvsr": fv.installed(), "trt": vs_trt.installed()}


def _tool_ok(tool: str) -> bool:
    if tool == "flashvsr":
        from app.core import flashvsr as fv
        return fv.installed()
    if tool == "trt":
        from app.core import vs_trt
        return vs_trt.installed()
    return se.installed(tool)


def install(tool: str, progress=lambda s: None) -> bool:
    """Real-ESRGAN / RIFE ikilisini indirir (ilk kullanim, ~45 MB / ~430 MB)."""
    if str(tool) not in ("esrgan", "rife"):
        raise RuntimeError("bilinmeyen arac")
    return se.install(str(tool), progress)


def required_tools(preset: str) -> list[str]:
    """Preset icin gereken motorlar (bos = model gerekmez)."""
    p = PRESETS.get(str(preset)) or {}
    if not p or not p.get("model"):
        return []
    if p.get("flashvsr"):
        return ["flashvsr"]
    if p.get("trt"):
        return ["trt"]
    out: list[str] = []
    if p.get("upscale"):
        out.append("esrgan")
    if p.get("interp"):
        out.append("rife")
    return out


# ------------------------------------------------------------------ prob

def _ffprobe(ffmpeg: str) -> str | None:
    """ffmpeg'in yanindaki ffprobe (Gyan full build'de var)."""
    cand = Path(ffmpeg).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
    return str(cand) if cand.is_file() else None


def probe(ffmpeg: str, path: str) -> dict[str, Any]:
    """Video bilgisi: boyut, fps, kare sayisi, interlace mi, ses var mi."""
    out: dict[str, Any] = {"width": 0, "height": 0, "fps": 30.0, "frames": 0, "duration": 0.0,
                           "interlaced": False, "vcodec": "", "acodec": "", "audio": False}
    fp = _ffprobe(ffmpeg)
    if fp:
        try:
            r = subprocess.run([fp, "-v", "error", "-show_entries",
                                "stream=codec_type,codec_name,width,height,r_frame_rate,field_order,nb_frames"
                                ":format=duration", "-of", "json", str(path)],
                               capture_output=True, timeout=60, creationflags=NO_WINDOW)
            data = json.loads(r.stdout.decode("utf-8", "replace") or "{}")
            for s in data.get("streams") or []:
                if s.get("codec_type") == "video" and not out["vcodec"]:
                    out["vcodec"] = str(s.get("codec_name") or "")
                    out["width"] = int(s.get("width") or 0)
                    out["height"] = int(s.get("height") or 0)
                    out["interlaced"] = str(s.get("field_order") or "progressive").lower() not in ("progressive", "unknown", "")
                    try:
                        out["frames"] = int(s.get("nb_frames") or 0)
                    except (TypeError, ValueError):
                        out["frames"] = 0
                    num, _, den = str(s.get("r_frame_rate") or "30/1").partition("/")
                    try:
                        out["fps"] = (float(num) / float(den)) if float(den or 0) else 30.0
                    except (TypeError, ValueError):
                        out["fps"] = 30.0
                elif s.get("codec_type") == "audio" and not out["acodec"]:
                    out["acodec"] = str(s.get("codec_name") or "")
                    out["audio"] = True
            out["duration"] = float((data.get("format") or {}).get("duration") or 0.0)
        except Exception:
            pass
    if not out["duration"] or not out["frames"] or not out["width"]:
        # yedek: 'ffmpeg -i' ciktisini ayikla (ffprobe yoksa)
        try:
            r = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)],
                               capture_output=True, timeout=60, creationflags=NO_WINDOW)
            txt = r.stderr.decode("utf-8", "replace")
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", txt)
            if m and not out["duration"]:
                out["duration"] = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
            m = re.search(r"([\d.]+) fps", txt)
            if m and not out["frames"]:
                out["fps"] = float(m.group(1))
            if not out["width"]:
                m = re.search(r",\s*(\d{2,5})x(\d{2,5})", txt)
                if m:
                    out["width"], out["height"] = int(m.group(1)), int(m.group(2))
        except Exception:
            pass
    if not out["frames"] and out["duration"] and out["fps"]:
        out["frames"] = int(out["duration"] * out["fps"])
    return out


# ------------------------------------------------------------------ filtre zinciri

def target_fps(info: dict[str, Any], opts: dict[str, Any] | None = None) -> float:
    """Cikti fps'i: opts['fps'] verildiyse o, yoksa kaynagin fps'i."""
    tf = int((opts or {}).get("fps") or 0)
    return float(tf) if tf >= 10 else float(info.get("fps") or 30.0)


def filters(preset: str, info: dict[str, Any], opts: dict[str, Any] | None = None) -> list[str]:
    """ffmpeg video filtresi listesi. Saf fonksiyon: test edilebilir."""
    p = PRESETS.get(str(preset)) or {}
    o = dict(opts or {})
    vf: list[str] = []

    # 0) Kare hizi dusurme: 60 fps kaynagi 30'a indirmek kare sayisini (ve isi) YARIYA indirir.
    #    En basa konur ki sonraki tum adimlar daha az kareyle calissin.
    tf = int(o.get("fps") or 0)
    if tf >= 10:
        vf.append(f"fps={tf}")

    # 1) Interlace: auto -> kaynak interlaced ise, on -> her zaman, off -> hic
    mode = str(o.get("deinterlace") or "auto").lower()
    if mode == "on" or (mode != "off" and bool(info.get("interlaced"))):
        vf.append("bwdif=mode=send_frame:parity=auto:deint=all")

    # 2) Denoise: -1 = presetin varsayilani (AI yolu daha temiz girdi sever)
    dn = int(o.get("denoise", -1))
    if dn < 0:
        dn = 2 if p.get("model") else 1
    dn = max(0, min(3, dn))
    if dn:
        table = {1: "1.5:1.5:6:6", 2: "3:3:9:9", 3: "4.5:4.5:12:12"}
        vf.append("hqdn3d=" + table[dn])
        if dn >= 3:
            vf.append("atadenoise=0a=0.02:0b=0.04:1a=0.02:1b=0.04")

    # 3) Buyutme: yalniz filtre yolunda (AI yolunda model buyutur)
    if not p.get("model") and p.get("upscale"):
        s = 2
        vf.append(f"scale=trunc(iw*{s}/2)*2:trunc(ih*{s}/2)*2:flags=lanczos")
        vf.append("unsharp=5:5:0.6:5:5:0.0")
    return vf


# ------------------------------------------------------------------ yardimcilar

def _count(d: Path) -> int:
    try:
        return sum(1 for _ in os.scandir(d))
    except OSError:
        return 0


def _drop_partial(job: dict) -> None:
    """Iptal/hata sonrasi YARIM cikti dosyasini siler.

    Temizle/Hizli buyut yollari ciktiyi dogrudan hedefe yazar; iptal edilince
    yarim (oynatilamayan) bir mp4 kaliyordu. Kullanici artik bozuk dosya gormez.
    """
    p = job.get("_out")
    if not p:
        return
    try:
        f = Path(str(p))
        if f.is_file():
            f.unlink()
            log.info("yarim cikti silindi: %s", f)
    except OSError as exc:
        log.warning("yarim cikti silinemedi: %s (%s)", p, exc)


def _rm_dir(path: Path, job: dict | None = None, attempts: int = 3) -> bool:
    """Gecici klasoru siler; BASARISIZ olursa sessizce yutMAZ (log + job['leftover']).

    Iki gercek sorun vardi:
    1) `shutil.rmtree(ignore_errors=True)` kilitli dosyada hatayi yutuyordu -> GB'larca PNG
       kaliyor, "temizlendi" gorunuyordu.
    2) Tek deneme yetmiyor: yeni yazilmis mp4'u antivirus/indeksleyici bir an tutuyor,
       ilk rmtree dusuyor ama 200 ms sonra basarili oluyor. Kisa araliklarla tekrar denenir.
    """
    p = Path(path) if path else None
    if not p or not p.exists():
        return True
    last: OSError | None = None
    for i in range(max(1, int(attempts))):
        try:
            shutil.rmtree(p)
            return True
        except OSError as exc:
            last = exc
            if not p.exists():      # kismen silinmis ama hedefe ulasilmis
                return True
            if i + 1 < int(attempts):
                time.sleep(0.2 * (i + 1))
    log.warning("gecici klasor silinemedi: %s (%s)", p, last)
    log.warning("elle temizlik: Remove-Item '%s' -Recurse -Force", p)
    if job is not None:
        job["leftover"] = int(job.get("leftover") or 0) + 1
        job["leftover_path"] = str(p)
    return False


def _workdir() -> Path:
    """Gecici calisma klasoru. KAMI_ENH_WORK verilirse orada, yoksa sistem temp'inde."""
    base = os.environ.get(WORK_ENV)
    if base:
        root = Path(base)
        root.mkdir(parents=True, exist_ok=True)
        d = root / f"kami_enh_{uuid.uuid4().hex[:10]}"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return Path(tempfile.mkdtemp(prefix="kami_enh_"))


def _out_path(out_dir: Path, src: str, tag: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^\w\-]+", "_", Path(src).stem)[:40] or "video"
    stamp = time.strftime("%H%M%S")
    p = out_dir / f"{stem}_{tag}_{stamp}.mp4"
    i = 2
    while p.exists():
        p = out_dir / f"{stem}_{tag}_{stamp}_{i}.mp4"
        i += 1
    return p


def _audio_copy_ok(acodec: str) -> bool:
    """mp4 icine oldugu gibi konabilecek ses kodekleri."""
    return str(acodec).lower() in ("aac", "mp3", "ac3", "eac3", "opus", "alac", "mp2")


def _exec_progress(job: dict, cmd: list[str], total: float, p0: float = 0.0, p1: float = 1.0) -> int:
    """ffmpeg'i -progress pipe:1 ile calistirir, yuzdeyi gunceller. -9 = iptal."""
    total = max(0.001, float(total or 0.001))
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=NO_WINDOW)
    err: list[bytes] = []
    threading.Thread(target=lambda: err.append(proc.stderr.read() if proc.stderr else b""), daemon=True).start()
    if proc.stdout is not None:
        for raw in proc.stdout:
            if job["cancel"].is_set():
                proc.kill()
                proc.wait(timeout=10)
                return -9
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith(("out_time_us=", "out_time_ms=")):
                v = line.split("=", 1)[1]
                if v.isdigit():   # "-12884901886"/"N/A" elenir
                    sec = int(v) / 1e6
                    job["p"] = round(p0 + (p1 - p0) * min(0.99, sec / total), 4)
    rc = proc.wait()
    if job["cancel"].is_set():
        return -9
    if rc != 0:
        job["_err"] = b"".join(err).decode("utf-8", "replace")[-300:]
    return rc


def _run_tool(job: dict, args: list[str], ex: Path, out_dir: Path, expect: int,
              p0: float, p1: float) -> None:
    """ncnn ikilisini calistirir; cikti dosya sayisindan yuzde hesaplar."""
    proc = subprocess.Popen(args, cwd=str(ex.parent), stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, creationflags=NO_WINDOW)
    err: list[bytes] = []
    threading.Thread(target=lambda: err.append(proc.stderr.read() if proc.stderr else b""), daemon=True).start()
    while proc.poll() is None:
        if job["cancel"].wait(0.6):
            proc.kill()
            proc.wait(timeout=10)
            raise _Cancelled()
        if expect:
            job["p"] = round(p0 + (p1 - p0) * min(1.0, _count(out_dir) / expect), 4)
    if proc.returncode != 0:
        tail = b"".join(err).decode("utf-8", "replace")[-200:]
        raise RuntimeError("arac hatasi: " + (tail or str(proc.returncode)))


# ------------------------------------------------------------------ iki yol

def _run_filter_only(job: dict, ffmpeg: str, preset: str, path: str, opts: dict[str, Any],
                     info: dict[str, Any], out_dir: Path) -> Path:
    """Tek ffmpeg gecisi: gecici kare dosyasi yok."""
    vf = filters(preset, info, opts)
    start = max(0.0, float(opts.get("start") or 0))
    dur = float(opts.get("duration") or 0) or max(0.001, float(info.get("duration") or 0))
    tag = re.sub(r"[^\w]+", "", str(PRESETS[preset]["ad"]).split()[0]).lower() or "temiz"
    dst = _out_path(out_dir, path, tag)
    job["_out"] = str(dst)
    job["line"] = "İşleniyor (tek geçiş, geçici dosya yok)"
    acodec = "copy" if (info.get("audio") and _audio_copy_ok(info.get("acodec", ""))) else "aac"
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-t", f"{dur:.3f}", "-i", str(path)]
    cmd += ["-vf", ",".join(vf) if vf else "null"]
    cmd += ["-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p"]
    cmd += ["-c:a", "copy"] if acodec == "copy" else ["-c:a", "aac", "-b:a", "192k"]
    cmd += ["-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(dst)]
    rc = _exec_progress(job, cmd, dur)
    if rc == -9:
        raise _Cancelled()
    if rc != 0:
        raise RuntimeError("ffmpeg hatasi: " + (job.pop("_err", "") or str(rc)))
    return dst


def _segment(job: dict, ffmpeg: str, preset: str, path: str, opts: dict[str, Any],
             info: dict[str, Any], work: Path, start: float, dur: float,
             base: str, with_audio: bool, p0: float, p1: float, label: str = "",
             cleanup: bool = True) -> Path:
    """Bir araligi kare hattindan gecirip mp4 dondurur (parcali modda sesis).

    cleanup=True: bu araligin PNG klasorleri mp4 yazildiktan HEMEN sonra silinir.
    Parcali islemede disk, tum videonun kareleri yerine tek parcanin kareleri kadar kalir.
    """
    p = PRESETS[preset]
    pre = (label + " · ") if label else ""
    src = work / f"in_{base}"
    src.mkdir(parents=True, exist_ok=True)
    tmp_dirs: list[Path] = [src]
    vf = filters(preset, info, opts)
    scale = 4 if (p.get("upscale") and int(opts.get("scale", 2)) == 4) else 2
    if p.get("upscale") and info["width"] > 3840 // scale:   # 4K'yi asma
        vf.append(f"scale='min(iw,{3840 // scale})':-2")
    job["line"] = pre + "kareler çıkarılıyor"
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y"]
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-t", f"{max(0.001, dur):.3f}", "-i", str(path)]
    cmd += ["-vf", ",".join(vf) if vf else "null", "-fps_mode", "cfr"]
    cmd += ["-progress", "pipe:1", "-nostats", str(src / "%08d.png")]
    rc = _exec_progress(job, cmd, dur, p0, p0 + (p1 - p0) * 0.30)
    if rc == -9:
        raise _Cancelled()
    if rc != 0:
        raise RuntimeError("kare cikarma hatasi: " + (job.pop("_err", "") or str(rc)))
    n_in = _count(src)
    if not n_in:
        raise RuntimeError("kare cikmadi (kaynak okunamadi?)")

    cur, n_cur = src, n_in
    span = p1 - p0
    if p.get("upscale"):
        ex = se.exe("esrgan")
        if not ex:
            raise RuntimeError("Real-ESRGAN kurulu degil")
        out = work / f"up_{base}"
        out.mkdir(parents=True, exist_ok=True)
        tmp_dirs.append(out)
        model = "realesrgan-x4plus" if str(opts.get("model")) == "photo" else "realesr-animevideov3"
        sc = 4 if model == "realesrgan-x4plus" else scale
        job["line"] = pre + f"netleştiriliyor ({n_cur} kare)"
        _run_tool(job, se.esrgan_args(str(ex), cur, out, model, sc), ex, out, n_cur,
                  p0 + span * 0.30, p0 + span * (0.72 if p.get("interp") else 0.95))
        cur = out
    if p.get("interp"):
        ex = se.exe("rife")
        if not ex:
            raise RuntimeError("RIFE kurulu degil")
        factor = 4 if int(opts.get("factor", 2)) >= 4 else 2
        out = work / f"rife_{base}"
        out.mkdir(parents=True, exist_ok=True)
        tmp_dirs.append(out)
        expect = _count(cur) * factor
        job["line"] = pre + f"ara kareler üretiliyor ({expect} kare)"
        _run_tool(job, se.rife_args(str(ex), cur, out, expect), ex, out, expect,
                  p0 + span * (0.72 if p.get("upscale") else 0.30), p0 + span * 0.95)
        cur, n_cur = out, expect
        out_fps = target_fps(info, opts) * factor
    else:
        out_fps = target_fps(info, opts)

    job["line"] = pre + "video birleştiriliyor"
    dst = work / f"{base}.mp4"
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-framerate", f"{out_fps:.5f}",
           "-i", str(cur / "%08d.png")]
    if with_audio:
        if info.get("audio") and _audio_copy_ok(info.get("acodec", "")):
            cmd += ["-ss", f"{max(0.0, start):.3f}", "-t", f"{max(0.001, dur):.3f}", "-i", str(path),
                    "-map", "0:v", "-map", "1:a?", "-c:a", "copy", "-shortest"]
        else:
            cmd += ["-ss", f"{max(0.0, start):.3f}", "-t", f"{max(0.001, dur):.3f}", "-i", str(path),
                    "-map", "0:v", "-map", "1:a?", "-c:a", "aac", "-b:a", "192k", "-shortest"]
    cmd += ["-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(dst)]
    r = subprocess.run(cmd, capture_output=True, timeout=7200, creationflags=NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError("birlestirme hatasi: " + r.stderr.decode("utf-8", "replace")[-200:])
    if cleanup:   # parca bitti: bu araligin PNG'leri artik gereksiz -> disk sabit kalir
        for d in tmp_dirs:
            _rm_dir(d, job)
    return dst


def _mux_audio(ffmpeg: str, video: Path, source: str, start: float, dur: float,
               info: dict[str, Any]) -> Path:
    """Difuzyon/TRT yollari sesis video uretir: orijinal sesi geri takar."""
    if not (info.get("audio") and video.is_file()):
        return video
    acodec = "copy" if _audio_copy_ok(info.get("acodec", "")) else "aac"
    mux = video.with_name(video.stem + ".mux.mp4")
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-i", str(video),
           "-ss", f"{max(0.0, start):.3f}", "-t", f"{max(0.001, dur):.3f}", "-i", str(source),
           "-map", "0:v", "-map", "1:a?", "-shortest"]
    cmd += ["-c:a", "copy"] if acodec == "copy" else ["-c:a", "aac", "-b:a", "192k"]
    cmd += ["-c:v", "copy", "-movflags", "+faststart", str(mux)]
    r = subprocess.run(cmd, capture_output=True, timeout=3600, creationflags=NO_WINDOW)
    if r.returncode == 0 and mux.is_file() and mux.stat().st_size > 1024:
        shutil.move(str(mux), str(video))
    else:
        mux.unlink(missing_ok=True)
    return video


def _run_trt(job: dict, ffmpeg: str, path: str, opts: dict[str, Any],
             info: dict[str, Any], out_dir: Path, work: Path) -> Path:
    """TensorRT yolu: vspipe -> ffmpeg boru hatti (kare basina disk trafigi yok)."""
    from app.core import vs_trt
    start = max(0.0, float(opts.get("start") or 0))
    total = float(info.get("duration") or 0)
    dur = float(opts.get("duration") or 0) or max(0.001, total)
    src = str(path)
    if start or (total and dur < total - 0.02):      # kesme gerekiyorsa once ffmpeg ile kes
        job["line"] = "Girdi hazırlanıyor"
        tmp = work / "girdi.mp4"
        cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y"]
        if start:
            cmd += ["-ss", f"{start:.3f}"]
        cmd += ["-t", f"{dur:.3f}", "-i", str(path), "-c:v", "libx264", "-crf", "12",
                "-preset", "veryfast", "-pix_fmt", "yuv420p", "-an", str(tmp)]
        r = subprocess.run(cmd, capture_output=True, timeout=3600, creationflags=NO_WINDOW)
        if r.returncode != 0:
            raise RuntimeError("girdi hazirlanamadi: " + r.stderr.decode("utf-8", "replace")[-160:])
        src = str(tmp)
    dst = _out_path(out_dir, path, "trt")
    job["_out"] = str(dst)
    o = dict(opts)
    o["frames"] = int(info.get("frames") or 0)
    try:
        out = vs_trt.run_video(job, ffmpeg, src, o, work, dst,
                              width=int(info.get("width") or 1280), height=int(info.get("height") or 720))
    except vs_trt._Cancelled:
        raise _Cancelled() from None
    job["line"] = "Ses ekleniyor"
    return _mux_audio(ffmpeg, out, str(path), start, dur, info)


def _run_flashvsr(job: dict, ffmpeg: str, preset: str, path: str, opts: dict[str, Any],
                  info: dict[str, Any], out_dir: Path, work: Path) -> Path:
    """Difuzyon yolu: 4x uretir. Cikti 4K'yi asmasin diye girdi gerekirse kucultulur/kesilir."""
    from app.core import flashvsr as fv
    start = max(0.0, float(opts.get("start") or 0))
    total = float(info.get("duration") or 0)
    dur = float(opts.get("duration") or 0) or max(0.001, total)
    maxw = 3840 // 4                                  # 4x sonrasi 3840'i asmasin
    src = str(path)
    cut = bool(start) or (total and dur < total - 0.02)
    if cut or info["width"] > maxw:
        job["line"] = "Girdi hazırlanıyor"
        tmp = work / "girdi.mp4"
        cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y"]
        if start:
            cmd += ["-ss", f"{start:.3f}"]
        cmd += ["-t", f"{dur:.3f}", "-i", str(path)]
        if info["width"] > maxw:
            cmd += ["-vf", f"scale='min(iw,{maxw})':-2"]
        cmd += ["-c:v", "libx264", "-crf", "12", "-preset", "veryfast",
                "-pix_fmt", "yuv420p", "-an", str(tmp)]
        r = subprocess.run(cmd, capture_output=True, timeout=3600, creationflags=NO_WINDOW)
        if r.returncode != 0:
            raise RuntimeError("girdi hazirlanamadi: " + r.stderr.decode("utf-8", "replace")[-160:])
        src = str(tmp)
    dst = _out_path(out_dir, path, "yeniden")
    job["_out"] = str(dst)
    try:
        out = fv.run_video(job, ffmpeg, src, opts, work, dst)
    except fv._Cancelled:
        raise _Cancelled() from None

    # FlashVSR sesis video uretir: orijinal sesi geri tak
    job["line"] = "Ses ekleniyor"
    return _mux_audio(ffmpeg, out, str(path), start, dur, info)


def _run_model(job: dict, ffmpeg: str, preset: str, path: str, opts: dict[str, Any],
               info: dict[str, Any], out_dir: Path, work: Path) -> Path:
    """Kare hatti: gerekiyorsa parcali, degilse tek gecis."""
    base_dir = Path(out_dir)
    start = max(0.0, float(opts.get("start") or 0))
    dur = float(opts.get("duration") or 0) or max(0.001, float(info.get("duration") or 0))
    total = int(info.get("frames") or 0) or int(max(0.001, dur) * float(info.get("fps") or 30))
    tag = re.sub(r"[^\w]+", "", str(PRESETS[preset]["ad"]).split()[0]).lower() or "ai"

    forced = int(opts.get("chunk_frames") or 0)       # test / ince ayar: parca boyunu zorla
    limit = forced or MAX_SINGLE_FRAMES
    if total > limit:
        return _run_chunked(job, ffmpeg, preset, path, opts, info, base_dir, work, start, dur,
                            forced or CHUNK_FRAMES, tag)
    dst = _out_path(base_dir, path, tag)
    job["_out"] = str(dst)
    seg = _segment(job, ffmpeg, preset, path, opts, info, work, start, dur, "full", True, 0.0, 1.0)
    shutil.move(str(seg), str(dst))
    return dst


def _run_chunked(job: dict, ffmpeg: str, preset: str, path: str, opts: dict[str, Any],
                 info: dict[str, Any], out_dir: Path, work: Path, start: float, dur: float,
                 chunk: int, tag: str) -> Path:
    """Uzun video: parca parca isle, sonra birlestir + sesi geri tak."""
    chunk = max(120, int(chunk))
    fps = float(info["fps"] or 30.0)
    total = int(info.get("frames") or 0) or int(max(0.001, dur) * fps)
    n = max(1, math.ceil(total / chunk))
    job["line"] = f"{n} parçada işleniyor"
    parts: list[Path] = []
    for i in range(n):
        t0 = start + i * chunk / fps
        left = dur - (t0 - start)
        if left <= 0.02:
            break
        fdur = min(chunk / fps, left)
        p0 = 0.02 + 0.93 * (i / n)
        p1 = 0.02 + 0.93 * ((i + 1) / n)
        parts.append(_segment(job, ffmpeg, preset, path, opts, info, work, t0, fdur,
                              f"p{i:03d}", False, p0, p1, label=f"Parça {i + 1}/{n}"))
    if not parts:
        raise RuntimeError("parca uretilemedi")

    job["line"] = "Parçalar birleştiriliyor"
    lst = work / "parcalar.txt"
    lst.write_text("\n".join(f"file '{q.as_posix()}'" for q in parts), "utf-8")
    joined = work / "joined.mp4"
    r = subprocess.run([ffmpeg, "-hide_banner", "-nostdin", "-y", "-f", "concat", "-safe", "0",
                        "-i", str(lst), "-c", "copy", str(joined)],
                       capture_output=True, timeout=7200, creationflags=NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError("parca birlestirme hatasi: " + r.stderr.decode("utf-8", "replace")[-200:])

    dst = _out_path(out_dir, path, tag)
    job["_out"] = str(dst)
    acodec = "copy" if (info.get("audio") and _audio_copy_ok(info.get("acodec", ""))) else "aac"
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-i", str(joined)]
    if info.get("audio"):
        cmd += ["-ss", f"{start:.3f}", "-t", f"{max(0.001, dur):.3f}", "-i", str(path),
                "-map", "0:v", "-map", "1:a?"]
        cmd += ["-c:a", "copy"] if acodec == "copy" else ["-c:a", "aac", "-b:a", "192k"]
    cmd += ["-c:v", "copy", "-movflags", "+faststart", str(dst)]
    r = subprocess.run(cmd, capture_output=True, timeout=7200, creationflags=NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError("ses birlestirme hatasi: " + r.stderr.decode("utf-8", "replace")[-200:])
    return dst


# ------------------------------------------------------------------ is yonetimi

def _pub(job: dict) -> dict[str, Any]:
    return {"id": job["id"], "state": job["state"], "p": float(job.get("p") or 0.0),
            "line": str(job.get("line") or ""), "error": str(job.get("error") or ""),
            "result": job.get("result"), "info": job.get("info")}


def _new_job(line: str) -> str:
    """Yeni is kaydi acar (en fazla 40 kayit tutulur)."""
    jid = "ve" + uuid.uuid4().hex[:10]
    with _LOCK:
        _JOBS[jid] = {"id": jid, "state": "running", "p": 0.0, "line": line,
                      "cancel": threading.Event(), "error": "", "result": None, "info": None}
        while len(_JOBS) > 40:
            _JOBS.pop(next(iter(_JOBS)))
    return jid


def job(jid: str) -> dict[str, Any]:
    """Arayuzun yokladigi durum (JSON'a uygun; Event sizmaz)."""
    with _LOCK:
        j = _JOBS.get(str(jid))
    return _pub(j) if j else {"id": str(jid), "state": "error", "error": "bulunamadi", "p": 0.0}


def cancel(jid: str) -> None:
    with _LOCK:
        j = _JOBS.get(str(jid))
    if j:
        j["cancel"].set()


def jobs() -> list[dict[str, Any]]:
    with _LOCK:
        return [_pub(j) for j in _JOBS.values()]


def _worker(job: dict, ffmpeg: str, preset: str, path: str, opts: dict[str, Any], out_dir: Path) -> None:
    work = _workdir()
    try:
        if str(preset) not in PRESETS:
            raise RuntimeError("bilinmeyen preset: " + str(preset))
        info = probe(ffmpeg, path)
        if not info.get("width"):
            raise RuntimeError("video okunamadi")
        job["info"] = info
        need = [t for t in required_tools(preset) if not _tool_ok(t)]
        if need:
            raise RuntimeError("motor kurulu degil: " + ",".join(need))
        if PRESETS[preset].get("flashvsr"):
            dst = _run_flashvsr(job, ffmpeg, preset, path, opts, info, out_dir, work)
        elif PRESETS[preset].get("trt"):
            dst = _run_trt(job, ffmpeg, path, opts, info, out_dir, work)
        elif PRESETS[preset]["model"]:
            dst = _run_model(job, ffmpeg, preset, path, opts, info, out_dir, work)
        else:
            dst = _run_filter_only(job, ffmpeg, preset, path, opts, info, out_dir)
        job.update(state="done", p=1.0, line="Bitti",
                   result={"path": str(dst), "info": probe(ffmpeg, str(dst))})
    except _Cancelled:
        _drop_partial(job)
        job.update(state="cancelled", line="İptal edildi")
    except Exception as exc:
        _drop_partial(job)
        log.exception("video iyilestirme hatasi (preset=%s)", preset)
        job.update(state="error", error=str(exc)[:300], line="Hata")
    finally:
        if not _rm_dir(work, job):
            job.update(line="Uyarı: geçici dosyalar silinemedi (elle temizlenebilir)")


def start(preset: str, path: str, ffmpeg: str, opts: dict[str, Any] | None = None,
          out_dir: Path | None = None) -> dict[str, Any]:
    """Isi baslatir, {ok, job} dondurur. Arac eksikse {ok:False, error:'need_tool', tool}."""
    if str(preset) not in PRESETS:
        return {"ok": False, "error": "bad_preset"}
    if not Path(str(path)).is_file():
        return {"ok": False, "error": "dosya_yok"}
    need = [t for t in required_tools(preset) if not _tool_ok(t)]
    if need:
        return {"ok": False, "error": "need_tool", "tool": need[0], "tools": need}
    jid = _new_job("Başlıyor")
    jb = _JOBS[jid]
    threading.Thread(target=_worker, name=f"video-enhance-{jid}",
                     args=(jb, str(ffmpeg), str(preset), str(path), dict(opts or {}),
                           Path(out_dir) if out_dir else Path.home() / "Videos" / "Kami Studio" / OUT_SUBDIR),
                     daemon=True).start()
    return {"ok": True, "job": jid}


def install_start(tool: str) -> dict[str, Any]:
    """Motoru arka planda kurar; ilerleme ayni enhance_job ucundan izlenir."""
    tool = str(tool)
    if tool not in ("esrgan", "rife", "flashvsr", "trt"):
        return {"ok": False, "error": "bad_tool"}
    jid = _new_job(f"{tool} kuruluyor")
    jb = _JOBS[jid]

    def run() -> None:
        try:
            if tool == "flashvsr":
                from app.core import flashvsr as fv
                ok = fv.install(lambda s: jb.update(line=str(s)[-160:]))
                err = "" if ok else (fv.LAST_ERROR.get("flashvsr") or "kurulamadi")
            elif tool == "trt":
                from app.core import vs_trt
                ok = vs_trt.install(lambda s: jb.update(line=str(s)[-160:]))
                err = "" if ok else (vs_trt.LAST_ERROR.get("trt") or "kurulamadi")
            else:
                ok = se.install(tool, lambda s: jb.update(line=str(s)[-160:]))
                err = "" if ok else "kurulamadi"
            jb.update(state="done" if ok else "error", p=1.0,
                      line="Kuruldu" if ok else "Kurulamadı",
                      error=err, result={"tool": tool} if ok else None)
        except Exception as exc:
            jb.update(state="error", error=str(exc)[:200], line="Hata")
    threading.Thread(target=run, name=f"video-enhance-install-{tool}", daemon=True).start()
    return {"ok": True, "job": jid}

