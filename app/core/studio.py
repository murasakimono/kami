"""Kami Studio: proje dosyasi, medya analizi (dalga, sessizlik, donuk sahne, vurus), ASS metin katmani ve ffmpeg ile disa aktarim.

Tek dogruluk kaynagi bu dosya: efekt modlari (FX), metin/altyazi -> ASS, zoom anahtar kareleri -> ffmpeg ifadesi.
Arayuz (studio.js) onizlemeyi tuval + JASSUB ile ayni tanimlardan cizer; MCP sunucusu (app/tools/studio_mcp.py)
ayni proje JSON'unu duzenler.

Proje (.kstudio, JSON):
  {v, name, w, h, fps, bg, assets:{id:{path,kind,dur,w,h,audio,name}}, tracks:[{id,kind,name,mute,hide}],
   clips:[{id,track,asset?,start,in,dur,speed,vol,fadeIn,fadeOut,fit,x,y,scale,rot,opacity,zoom[],reframe[],fx[],adj{},
           trans{}, text?, style{}, words[], mode?, amt?}], markers:[{t,kind}]}
Zaman: saniye. Kaynak zamani = in + (zaman - start) * speed.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

from app import paths
from app.core import studio_anim, studio_fx_adv, studio_gfx, studio_motion

log = logging.getLogger(__name__)
NO_WINDOW = 0x08000000 if os.name == "nt" else 0
CACHE = paths.DATA_DIR / "studio"
VIDEO_EXT = {".mp4", ".mkv", ".mov", ".webm", ".m4v", ".avi", ".wmv", ".flv", ".ts", ".mts", ".m2ts", ".3gp"}
AUDIO_EXT = {".mp3", ".wav", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".wma", ".oga"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
PROJECT_EXT = ".kstudio"


def home_dir() -> Path:
    """Videolar\\Kami Studio (Projeler, Sesler, Memeler, Disa aktarilanlar)."""
    base = Path.home() / "Videos"
    d = base / "Kami Studio"
    for sub in ("Projeler", "Sesler", "Memeler", "Çıktılar"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------------------------------------------
# Efekt modlari: ff = ffmpeg zinciri (W,H yerine konur), css = onizleme filtresi, ov = onizleme katmanlari, ass = ust yazi
FX: dict[str, dict[str, Any]] = {
    # korku / found footage
    "vhs": {"name": "VHS kamera", "pack": "Korku", "ff": "rgbashift=rh=-3:bh=3,gblur=sigma=0.7,eq=saturation=1.25:contrast=1.08,"
            "noise=alls=14:allf=t,drawgrid=w=iw:h=4:t=1:c=black@0.22,vignette=PI/5",
            "css": "saturate(1.25) contrast(1.08) blur(0.4px)", "ov": ["rgb", "scan", "grain", "vignette", "vhs-jitter"], "ass": "vhs"},
    "nightvision": {"name": "Gece görüşü (Outlast)", "pack": "Korku",
                    "ff": "hue=s=0,colorchannelmixer=rr=0.25:rg=0.25:rb=0.25:gr=0.45:gg=1.25:gb=0.45:br=0.2:bg=0.2:bb=0.2,"
                          "eq=contrast=1.25:brightness=0.05,noise=alls=26:allf=t,vignette=PI/3.2",
                    "css": "grayscale(1) sepia(1) hue-rotate(60deg) saturate(3) contrast(1.25) brightness(1.1)",
                    "ov": ["grain", "vignette-hard"], "ass": "rec"},
    "bodycam": {"name": "Body-cam", "pack": "Korku", "ff": "lenscorrection=k1=-0.22:k2=-0.03,eq=saturation=0.8:contrast=1.12,"
                "noise=alls=10:allf=t,vignette=PI/4", "css": "saturate(.8) contrast(1.12)", "ov": ["fisheye", "grain", "vignette"], "ass": "bodycam"},
    "cctv": {"name": "Güvenlik kamerası", "pack": "Korku", "ff": "hue=s=0,scale=iw/3:-2,scale=W:H:flags=neighbor,eq=contrast=1.2,noise=alls=18:allf=t",
             "css": "grayscale(1) contrast(1.2)", "ov": ["pixel", "grain", "scan"], "ass": "cctv"},
    "glitch": {"name": "Glitch", "pack": "Korku", "ff": "rgbashift=rh=8:gv=-3:bh=-6,noise=alls=12:allf=t",
               "css": "contrast(1.1)", "ov": ["rgb-strong", "glitch-bars"]},
    "found": {"name": "Found footage", "pack": "Korku", "ff": "eq=saturation=0.55:contrast=1.15:brightness=-0.04,noise=alls=16:allf=t,vignette=PI/3.5",
              "css": "saturate(.55) contrast(1.15) brightness(.96)", "ov": ["grain", "vignette-hard", "shake-soft"], "ass": "rec"},
    # duygu modlari
    "sad": {"name": "Hüzün (siyah-beyaz)", "pack": "Duygu", "ff": "hue=s=0,eq=contrast=1.12:brightness=-0.03,vignette=PI/4",
            "css": "grayscale(1) contrast(1.12) brightness(.97)", "ov": ["vignette"]},
    "rage": {"name": "Rage", "pack": "Duygu", "ff": "eq=saturation=2.2:contrast=1.45,colorbalance=rs=0.45:gs=-0.1:bs=-0.15,"
             "rgbashift=rh=5:bh=-5,crop=iw-24:ih-24:12+12*sin(t*53):12+12*cos(t*47),scale=W:H",
             "css": "saturate(2.2) contrast(1.45) sepia(.35) hue-rotate(-20deg)", "ov": ["rgb", "shake", "red-vignette"]},
    "dream": {"name": "Rüya", "pack": "Duygu", "ff": "split[d0][d1];[d1]gblur=sigma=14[d2];[d0][d2]blend=all_mode=screen:all_opacity=0.55,eq=saturation=1.15:brightness=0.04",
              "css": "brightness(1.08) saturate(1.15)", "ov": ["bloom"]},
    "flashback": {"name": "Geçmiş (flashback)", "pack": "Duygu", "ff": "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131,"
                  "split[f0][f1];[f1]gblur=sigma=8[f2];[f0][f2]blend=all_mode=screen:all_opacity=0.4,vignette=PI/3.5",
                  "css": "sepia(.9) brightness(1.05)", "ov": ["bloom", "vignette-hard"]},
    "cold": {"name": "Soğuk/yalnız", "pack": "Duygu", "ff": "colorbalance=rs=-0.15:bs=0.2:rm=-0.1:bm=0.15,eq=saturation=0.7",
             "css": "saturate(.7) hue-rotate(15deg) brightness(.97)", "ov": ["blue-tint"]},
    "warm": {"name": "Sıcak/nostalji", "pack": "Duygu", "ff": "colorbalance=rs=0.15:bs=-0.12:rm=0.1:bm=-0.1,eq=saturation=1.1",
             "css": "sepia(.25) saturate(1.1)", "ov": ["warm-tint"]},
    # edit / AMV
    "flash": {"name": "Beyaz flaş", "pack": "Edit", "ff": "eq=brightness='max(0,0.9*(1-(t-S)/0.22))':eval=frame",
              "css": "", "ov": ["flash"]},
    "rgbsplit": {"name": "RGB kayma", "pack": "Edit", "ff": "rgbashift=rh=10:bh=-10", "css": "", "ov": ["rgb-strong"]},
    "shake": {"name": "Sarsıntı", "pack": "Edit", "ff": "crop=iw-40:ih-40:20+20*sin(t*61):20+20*cos(t*53),scale=W:H", "css": "", "ov": ["shake"]},
    "zoomblur": {"name": "Zoom bulanık", "pack": "Edit", "ff": "split[z0][z1];[z1]scale=iw*1.08:-2,crop=W:H,gblur=sigma=6[z2];[z0][z2]blend=all_mode=normal:all_opacity=0.5",
                 "css": "blur(1.5px)", "ov": ["zoom"]},
    "invert": {"name": "Ters renk", "pack": "Edit", "ff": "negate", "css": "invert(1)", "ov": []},
    "strobe": {"name": "Strobe", "pack": "Edit", "ff": "eq=brightness='0.6*lt(mod(t*8,1),0.5)':eval=frame", "css": "", "ov": ["strobe"]},
    "mono-pop": {"name": "Renk vurgulu S/B", "pack": "Edit", "ff": "hue=s=0,eq=contrast=1.4", "css": "grayscale(1) contrast(1.4)", "ov": []},
    # sinematik
    "letterbox": {"name": "Sinema şeridi", "pack": "Sinematik", "ff": "drawbox=y=0:w=iw:h=ih*0.11:c=black:t=fill,drawbox=y=ih*0.89:w=iw:h=ih*0.11:c=black:t=fill",
                  "css": "", "ov": ["letterbox"]},
    "tealorange": {"name": "Teal & orange", "pack": "Sinematik", "ff": "colorbalance=rs=0.12:gs=-0.04:bs=-0.14:rh=-0.08:bh=0.12,curves=preset=medium_contrast,eq=saturation=1.15",
                   "css": "contrast(1.1) saturate(1.15) sepia(.15)", "ov": ["teal"]},
    "film": {"name": "Film greni", "pack": "Sinematik", "ff": "noise=alls=9:allf=t,curves=preset=medium_contrast", "css": "contrast(1.06)", "ov": ["grain"]},
    "8mm": {"name": "8mm film", "pack": "Sinematik", "ff": "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131,"
            "eq=brightness='0.04*sin(t*31)':eval=frame,noise=alls=22:allf=t,vignette=PI/3",
            "css": "sepia(.85) contrast(1.05)", "ov": ["grain", "vignette-hard", "flicker", "scratches"]},
    "noir": {"name": "Noir", "pack": "Sinematik", "ff": "hue=s=0,curves=preset=strong_contrast,vignette=PI/3.5", "css": "grayscale(1) contrast(1.5)", "ov": ["vignette-hard"]},
    "bleach": {"name": "Bleach bypass", "pack": "Sinematik", "ff": "eq=saturation=0.45:contrast=1.35", "css": "saturate(.45) contrast(1.35)", "ov": []},
    "slowmo-glow": {"name": "Yumuşak parıltı", "pack": "Sinematik", "ff": "split[g0][g1];[g1]gblur=sigma=10[g2];[g0][g2]blend=all_mode=lighten:all_opacity=0.35",
                    "css": "brightness(1.05)", "ov": ["bloom"]},
    # ekstra
    "anime": {"name": "Anime canlı", "pack": "Ekstra", "ff": "eq=saturation=1.6:contrast=1.15,unsharp=5:5:1.0", "css": "saturate(1.6) contrast(1.15)", "ov": []},
    "retro-game": {"name": "Retro oyun (piksel)", "pack": "Ekstra", "ff": "scale=iw/8:-2,scale=W:H:flags=neighbor,eq=saturation=1.3", "css": "saturate(1.3)", "ov": ["pixel-strong"]},
    "thermal": {"name": "Termal kamera", "pack": "Ekstra", "ff": "hue=s=0,pseudocolor=preset=heat", "css": "grayscale(1) sepia(1) saturate(5) hue-rotate(-30deg)", "ov": []},
    "underwater": {"name": "Su altı", "pack": "Ekstra", "ff": "colorbalance=rs=-0.3:bs=0.25:gs=0.1,gblur=sigma=1.2", "css": "hue-rotate(160deg) saturate(.8) blur(1px)", "ov": ["blue-tint"]},
    "drunk": {"name": "Sarhoş", "pack": "Ekstra", "ff": "split[k0][k1];[k1]crop=iw-30:ih-30:15+15*sin(t*1.7):15+15*cos(t*1.3),scale=W:H[k2];[k0][k2]blend=all_mode=average,gblur=sigma=1.5",
              "css": "blur(1px)", "ov": ["double"]},
    "deepfried": {"name": "Deep fried meme", "pack": "Ekstra", "ff": "eq=saturation=3:contrast=1.8,unsharp=7:7:2.5,noise=alls=20", "css": "saturate(3) contrast(1.8)", "ov": ["grain"]},
}

from app.core.studio_fx2 import FX2 as _FX2  # noqa: E402
FX.update({k: v for k, v in _FX2.items() if k not in FX})
from app.core.studio_fx3 import FX3 as _FX3  # noqa: E402
FX.update({k: v for k, v in _FX3.items() if k not in FX})
from app.core.studio_fx4 import FX4 as _FX4  # noqa: E402
FX.update({k: v for k, v in _FX4.items() if k not in FX})
from app.core.studio_trans2 import TRANS2, trans_in2  # noqa: E402
from app.core.studio_packs import CAPTIONS2, ZOOM3  # noqa: E402
from app.core.studio_pro_pack import (  # noqa: E402
    AUDIO_FIX_NAMES_PRO, AUDIO_FIX_PRO, CAPTIONS_PRO, FX_PRO,
    SFX_CAT_PRO, SFX_PRO, TEMPLATES_PRO, TRANS_PRO, ZOOM_PRO, trans_in_pro,
)
from app.core.studio_tr_memes import (  # noqa: E402
    FX_TR_MEME, SFX_CAT_TR_MEME, SFX_TR_MEME, TEMPLATES_TR_MEME,
)
FX.update({k: v for k, v in FX_PRO.items() if k not in FX})
FX.update({k: v for k, v in FX_TR_MEME.items() if k not in FX})
CAPTIONS2.update({k: v for k, v in CAPTIONS_PRO.items() if k not in CAPTIONS2})

# Gecis (klip girisi): ffmpeg + onizleme ayni adla
TRANS = {"none": "Yok", "fade": "Kararma", "flash": "Beyaz flaş", "zoom": "Zoom vuruşu", "slide": "Kaydırma (sağdan)", "blur": "Bulanık", "glitch": "Glitch",
         # faz 5 paketi: maske / hareket / doku gecisleri (onizleme: studio-fx.js transIn)
         "slide-r": "Kaydırma (soldan)", "slide-u": "Kaydırma (alttan)", "slide-d": "Kaydırma (üstten)", "whip": "Savurma (whip pan)",
         "wipe-r": "Silme →", "wipe-l": "Silme ←", "wipe-d": "Silme ↓", "wipe-u": "Silme ↑", "iris": "Daire açılış",
         "barn-v": "Perde (dikey)", "barn-h": "Perde (yatay)", "eye": "Göz açılışı", "clock": "Saat yönü",
         "spin": "Dönerek", "pixel": "Pikselden netleş", "shake-in": "Sarsıntılı giriş", "lightleak": "Işık sızması", "zoomblur": "Bulanık zoom"}
TRANS.update(TRANS2)   # faz 5b: capraz/sekil/olcek gecisleri (studio_trans2.py)
TRANS.update(TRANS_PRO)
TRANS_FF = set(TRANS) - {"none", "fade"}

# Hazir zoom sablonlari (klibe gore sn); kullanicininkiler CACHE/templates.json'a eklenir
ZOOM_PRESETS = [
    {"id": "punch", "name": "Vuruş zoom", "kf": [{"t": 0, "z": 1}, {"t": 0.12, "z": 1.35, "e": "out"}, {"t": 0.6, "z": 1.25}]},
    {"id": "push", "name": "Yavaş yaklaş", "kf": [{"t": 0, "z": 1}, {"t": -0.001, "z": 1.18}]},   # negatif = klip sonu
    {"id": "pull", "name": "Yavaş uzaklaş", "kf": [{"t": 0, "z": 1.2}, {"t": -0.001, "z": 1}]},
    {"id": "double", "name": "Çift vuruş", "kf": [{"t": 0, "z": 1}, {"t": 0.08, "z": 1.25, "e": "out"}, {"t": 0.3, "z": 1.1}, {"t": 0.38, "z": 1.45, "e": "out"}, {"t": 0.9, "z": 1.3}]},
    {"id": "face", "name": "Yüze dal", "kf": [{"t": 0, "z": 1, "cx": 0.5, "cy": 0.5}, {"t": 0.5, "z": 1.8, "cx": 0.5, "cy": 0.38, "e": "inout"}]},
    {"id": "bounce", "name": "Zıpla", "kf": [{"t": 0, "z": 1.3}, {"t": 0.15, "z": 0.95, "e": "out"}, {"t": 0.3, "z": 1.05}, {"t": 0.45, "z": 1}]},
    # faz 5 paketi
    {"id": "snap", "name": "Ani yaklaş, dur", "kf": [{"t": 0, "z": 1}, {"t": 0.18, "z": 1.25, "e": "out"}]},
    {"id": "reverse-punch", "name": "Yakından aç (ters vuruş)", "kf": [{"t": 0, "z": 1.5}, {"t": 0.25, "z": 1, "e": "out"}]},
    {"id": "heartbeat", "name": "Kalp atışı", "kf": [{"t": 0, "z": 1}, {"t": 0.1, "z": 1.12, "e": "out"}, {"t": 0.25, "z": 1},
                                                     {"t": 0.4, "z": 1.12, "e": "out"}, {"t": 0.6, "z": 1}]},
    {"id": "triple", "name": "Üçlü vuruş", "kf": [{"t": 0, "z": 1}, {"t": 0.06, "z": 1.15, "e": "out"}, {"t": 0.2, "z": 1.05}, {"t": 0.26, "z": 1.3, "e": "out"},
                                                  {"t": 0.4, "z": 1.15}, {"t": 0.46, "z": 1.45, "e": "out"}, {"t": 0.8, "z": 1.35}]},
    {"id": "dramatic", "name": "Dramatik yavaş yaklaş", "kf": [{"t": 0, "z": 1}, {"t": -0.001, "z": 1.4, "e": "inout"}]},
    {"id": "kb-lr", "name": "Ken Burns soldan sağa", "kf": [{"t": 0, "z": 1.15, "cx": 0.38, "cy": 0.5}, {"t": -0.001, "z": 1.15, "cx": 0.62, "cy": 0.5}]},
    {"id": "kb-rl", "name": "Ken Burns sağdan sola", "kf": [{"t": 0, "z": 1.15, "cx": 0.62, "cy": 0.5}, {"t": -0.001, "z": 1.15, "cx": 0.38, "cy": 0.5}]},
    {"id": "tilt-up", "name": "Yukarı süzül", "kf": [{"t": 0, "z": 1.3, "cx": 0.5, "cy": 0.68}, {"t": -0.001, "z": 1.3, "cx": 0.5, "cy": 0.32, "e": "inout"}]},
    {"id": "dive-tl", "name": "Sol üste dal", "kf": [{"t": 0, "z": 1, "cx": 0.5, "cy": 0.5}, {"t": 0.5, "z": 1.6, "cx": 0.3, "cy": 0.3, "e": "inout"}]},
    {"id": "dive-br", "name": "Sağ alta dal", "kf": [{"t": 0, "z": 1, "cx": 0.5, "cy": 0.5}, {"t": 0.5, "z": 1.6, "cx": 0.7, "cy": 0.7, "e": "inout"}]},
    {"id": "drift", "name": "Hafif süzülme (vlog)", "kf": [{"t": 0, "z": 1.08, "cx": 0.46, "cy": 0.5}, {"t": -0.001, "z": 1.1, "cx": 0.54, "cy": 0.48}]},
] + ZOOM3 + ZOOM_PRO

CAPTION_STYLES = {
    "hormozi": "Kelime vurgulu (sarı)", "word": "Tek kelime büyük", "karaoke": "Karaoke dolgu", "plain": "Sade alt yazı",
    "neon": "Neon parlama", "boxed": "Kutulu (TikTok)",
    "mrbeast": "Renkli kelime (YouTube)", "highlight": "Kelime arkası renkli", "reveal": "Kelime kelime belir",
    "hollow": "Boş harf, konuşan dolu", "cinema": "Sinematik ince",
    **{k: v["name"] for k, v in CAPTIONS2.items()},   # faz 5b: font + renk on ayarlari (davranis: CAPTIONS2[k]["b"])
}
TEXT_ANIMS = {"none": "Yok", "pop": "Pop", "fade": "Belir", "slide": "Aşağıdan kay", "type": "Daktilo", "bounce": "Zıpla",
              "shake": "Titreş", "zoom": "Büyüyerek", "glitch": "Glitch"}
SUBSCRIBE = {"classic": "Klasik kırmızı + imleç", "neon": "Neon", "pill": "Hap (minimal)", "bounce": "Zıplayan", "glitch": "Glitch",
             "bell": "Zil + abone", "like": "Beğen + abone", "corner": "Köşe bildirimi"}

FONTS = ["Chakra Petch", "Damnation", "Rubik Glitch", "Impact", "Arial Black", "Arial", "Segoe UI", "Comic Sans MS", "Georgia", "Consolas",
         # faz 5b: Kami ile gelen fontlar (web/fonts, Turkce glif dogrulandi; lisans: web/fonts/FONTS-LICENSE.txt)
         "Montserrat Black", "Montserrat ExtraBold", "Poppins ExtraBold", "Poppins Bold", "Poppins SemiBold", "Inter SemiBold", "Anton",
         "Bebas Neue", "Archivo Black", "Oswald Bold", "Rubik Black", "Luckiest Guy", "Bangers", "Lobster", "Pacifico", "Righteous",
         "Russo One", "Bungee", "Black Ops One", "Audiowide", "Press Start 2P", "VT323", "Rubik Mono One", "Monoton", "Nosifer",
         "Special Elite", "Kalam", "Caveat Bold", "Baloo 2 ExtraBold", "Kami Serif", "Kami Round", "Kami Script"]
WIN_FONTS = {"Impact": "impact.ttf", "Arial Black": "ariblk.ttf", "Arial": "arial.ttf", "Segoe UI": "segoeui.ttf",
             "Comic Sans MS": "comic.ttf", "Georgia": "georgia.ttf", "Consolas": "consola.ttf"}


def font_files() -> list[Path]:
    """JASSUB onizlemesi ve disa aktarim icin font dosyalari (Kami fontlari + Windows'un meme fontlari)."""
    out = [p for p in (paths.WEB_DIR / "fonts").glob("*.ttf")]
    win = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for fn in WIN_FONTS.values():
        if (win / fn).is_file():
            out.append(win / fn)
    for extra in ("arialbd.ttf", "segoeuib.ttf", "comicbd.ttf"):
        if (win / extra).is_file():
            out.append(win / extra)
    return out


def catalog() -> dict[str, Any]:
    return {"fx": {k: {"name": v["name"], "pack": v["pack"], "css": v.get("css", ""), "ov": v.get("ov", []), "ass": v.get("ass", "")}
                   for k, v in FX.items()},
            "trans": TRANS, "zoom": ZOOM_PRESETS + load_templates(), "captions": CAPTION_STYLES, "anims": TEXT_ANIMS,
            "capb": {k: {"b": v["b"], "font": v["st"].get("font", "")} for k, v in CAPTIONS2.items()},
            "subscribe": {**studio_gfx.SUBSCRIBE_PRO, **SUBSCRIBE}, "graphics": studio_gfx.GRAPHICS, "fonts": FONTS,
            "deliver": {k: v["name"] for k, v in DELIVER.items()}, "afx": AUDIO_FIX_NAMES, "templates": TEMPLATE_NAMES,
            "tanim": studio_anim.text_catalog(), "canim": studio_anim.clip_catalog(),
            "blends": {k: v[0] for k, v in studio_fx_adv.BLEND_MODES.items()},
            "masks": studio_fx_adv.MASK_TYPES,
            "bezierPresets": studio_motion.BEZIER_PRESETS,
            "eqBands": studio_fx_adv.EQ_BANDS,
            "eqPresets": studio_fx_adv.EQ_PRESETS,
            "audioCurves": studio_fx_adv.AUDIO_CURVES}


def load_templates() -> list[dict]:
    try:
        return json.loads((CACHE / "templates.json").read_text("utf-8"))
    except (OSError, ValueError):
        return []


def save_template(name: str, kf: list[dict]) -> list[dict]:
    items = [t for t in load_templates() if t.get("name") != name]
    items.append({"id": "u" + str(int(time.time())), "name": name[:40], "kf": kf[:64], "user": True})
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / "templates.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), "utf-8")
    return items


def delete_template(tid: str) -> list[dict]:
    items = [t for t in load_templates() if t.get("id") != tid]
    (CACHE / "templates.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), "utf-8")
    return items


# ---------------------------------------------------------------------------------------------------------------
# Proje
def new_project(name: str = "Yeni proje", w: int = 1920, h: int = 1080, fps: int = 30) -> dict[str, Any]:
    return {"v": 1, "name": name, "w": w, "h": h, "fps": fps, "bg": "#000000", "assets": {},
            "tracks": [{"id": "v2", "kind": "video", "name": "Üst katman"}, {"id": "v1", "kind": "video", "name": "Ana video"},
                       {"id": "tx", "kind": "text", "name": "Metin"}, {"id": "fx", "kind": "fx", "name": "Efekt"},
                       {"id": "a1", "kind": "audio", "name": "Ses"}, {"id": "a2", "kind": "audio", "name": "Ses efekti"}],
            "clips": [], "markers": []}


def load_project(path: str) -> dict[str, Any]:
    p = json.loads(Path(path).read_text("utf-8"))
    if not isinstance(p, dict) or "clips" not in p:
        raise ValueError("Kami Studio projesi degil")
    return p


def save_project(path: str, project: dict[str, Any]) -> str:
    p = Path(path)
    if p.suffix.lower() != PROJECT_EXT:
        p = p.with_suffix(PROJECT_EXT)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(project, ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, p)
    return str(p)


def flatten_clips(clips: list[dict]) -> list[dict]:
    """Bilesik klipleri (kind='compound', children basa gore sn) zaman cizelgesindeki gercek kliplerine acar.
    Disa aktarim, ASS ve sure hesabi bunu kullanir; proje dosyasinda bilesik klip oldugu gibi kalir."""
    out: list[dict] = []
    for c in clips or []:
        if c.get("kind") == "compound":
            base = float(c.get("start", 0) or 0)
            kids = []
            for ch in c.get("children") or []:
                nc = dict(ch)
                nc["start"] = round(base + float(ch.get("start", 0) or 0), 4)
                kids.append(nc)
            out.extend(flatten_clips(kids))
        else:
            out.append(c)
    return out


def project_end(project: dict[str, Any]) -> float:
    return max([float(c["start"]) + float(c.get("dur", 0) or 0) for c in flatten_clips(project.get("clips", []))] or [0.0])


def asset_kind(path: str) -> str:
    ext = Path(path).suffix.lower()
    return "image" if ext in IMAGE_EXT else "audio" if ext in AUDIO_EXT else "video" if ext in VIDEO_EXT else ""


# ---------------------------------------------------------------------------------------------------------------
class Studio:
    """Agir isler (dalga, algilama, vurus, disa aktarim) burada; arayuz api.studio_* uzerinden cagirir."""

    def __init__(self, ffmpeg: Callable[[], str]):
        self.ffmpeg = ffmpeg
        self.jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._enc: str | None = None
        self._fcflag: str | None = None
        CACHE.mkdir(parents=True, exist_ok=True)

    # ---- yardimci
    def ffprobe(self) -> str:
        from app.core.media_server import find_ffprobe
        return find_ffprobe(self.ffmpeg())

    def _run(self, args: list[str], timeout: float = 600) -> subprocess.CompletedProcess:
        return subprocess.run([self.ffmpeg(), "-hide_banner", "-nostdin", *args], capture_output=True, timeout=timeout,
                              creationflags=NO_WINDOW)

    def _fc_file(self, args: list[str], work: Path) -> list[str]:
        """Filtre grafigini dosyaya yazar: uzun projelerde komut satiri 32767 karakteri asiyordu (WinError 206)."""
        if "-filter_complex" not in args:
            return args
        i = args.index("-filter_complex")
        f = work / "graph.txt"
        f.write_text(args[i + 1], "utf-8")
        if self._fcflag is None:
            try:
                r = self._run(["-version"], timeout=20)
                m = re.search(rb"version (?:n)?(\d+)\.(\d+)", r.stdout or b"")
                self._fcflag = "-/filter_complex" if not m or (int(m.group(1)), int(m.group(2))) >= (7, 1) else "-filter_complex_script"
            except Exception:
                self._fcflag = "-/filter_complex"
        return [*args[:i], self._fcflag, str(f), *args[i + 2:]]

    def _cache(self, path: str, tag: str) -> Path:
        st = os.stat(path)
        import hashlib
        h = hashlib.sha1(f"{os.path.abspath(path)}|{st.st_size}|{int(st.st_mtime)}|{tag}".encode()).hexdigest()[:16]
        return CACHE / "cache" / f"{h}.json"

    def _cached(self, path: str, tag: str, fn: Callable[[], Any]) -> Any:
        f = self._cache(path, tag)
        try:
            return json.loads(f.read_text("utf-8"))
        except (OSError, ValueError):
            pass
        data = fn()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(data), "utf-8")
        return data

    # ---- medya
    def info(self, path: str) -> dict[str, Any]:
        from app.core.media_server import probe
        kind = asset_kind(path)
        if not kind or not os.path.isfile(path):
            return {"ok": False, "error": "not_media"}
        i = probe(self.ffprobe(), path)
        if kind == "image" and not i.get("width"):
            try:
                from PIL import Image
                with Image.open(path) as im:
                    i["width"], i["height"] = im.size
            except Exception:
                pass
        gif = path.lower().endswith(".gif")
        dur = float(i.get("duration") or 0)
        if kind == "image" and not (gif and dur > 0.2):
            dur = 5.0
        return {"ok": True, "path": path, "kind": "video" if gif and dur > 0.2 and kind == "image" else kind, "gif": gif,
                "dur": round(dur, 3), "w": int(i.get("width") or 0), "h": int(i.get("height") or 0),
                "audio": bool(i.get("audio")) and kind != "image", "name": Path(path).stem, "vcodec": i.get("vcodec", "")}

    def _pcm(self, path: str, rate: int, start: float = 0.0, dur: float = 0.0, filt: str = "") -> memoryview:
        args = []
        if start:
            args += ["-ss", f"{start:.3f}"]
        args += ["-i", path]
        if dur:
            args += ["-t", f"{dur:.3f}"]
        args += ["-vn", "-ac", "1", "-ar", str(rate)]
        if filt:
            args += ["-af", filt]
        args += ["-f", "s16le", "pipe:1"]
        r = self._run(["-loglevel", "error", *args], timeout=900)
        data = r.stdout[: len(r.stdout) // 2 * 2]
        return memoryview(data).cast("h")

    def peaks(self, path: str, per_sec: int = 100) -> dict[str, Any]:
        """Zaman cizelgesi dalga formu: saniyede per_sec tepe (0-255)."""
        def calc() -> dict[str, Any]:
            rate = 8000
            s = self._pcm(path, rate)
            step = max(1, rate // per_sec)
            out = bytearray()
            n = len(s)
            for i in range(0, n, step):
                chunk = s[i:i + step]
                m = max(max(chunk), -min(chunk)) if len(chunk) else 0
                out.append(min(255, int(math.sqrt(m / 32768) * 255)))
            return {"per_sec": per_sec, "peaks": out.hex()}
        return self._cached(path, f"peaks{per_sec}", calc)

    def silences(self, path: str, start: float, dur: float, db: float = -35.0, min_len: float = 0.45) -> list[list[float]]:
        """Sessiz araliklar (kaynak zamaninda)."""
        r = self._run(["-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", path, "-vn", "-af",
                       f"silencedetect=noise={db}dB:d={min_len}", "-f", "null", "-"], timeout=900)
        txt = r.stderr.decode("utf-8", "replace")
        out, cur = [], None
        for m in re.finditer(r"silence_(start|end): (-?[\d.]+)", txt):
            t = float(m.group(2)) + start
            if m.group(1) == "start":
                cur = max(start, t)
            elif cur is not None:
                out.append([round(cur, 3), round(t, 3)])
                cur = None
        if cur is not None:
            out.append([round(cur, 3), round(start + dur, 3)])
        return out

    def freezes(self, path: str, start: float, dur: float, min_len: float = 1.0) -> list[list[float]]:
        """Donuk/bos sahneler (degismeyen goruntu) - kaynak zamaninda."""
        r = self._run(["-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", path, "-an", "-vf",
                       f"scale=320:-2,freezedetect=n=0.003:d={min_len}", "-f", "null", "-"], timeout=1800)
        txt = r.stderr.decode("utf-8", "replace")
        out, cur = [], None
        for m in re.finditer(r"freeze_(start|end): (-?[\d.]+)", txt):
            t = float(m.group(2)) + start
            if m.group(1) == "start":
                cur = t
            elif cur is not None:
                out.append([round(cur, 3), round(t, 3)])
                cur = None
        if cur is not None:
            out.append([round(cur, 3), round(start + dur, 3)])
        return out

    def scenes(self, path: str, start: float, dur: float, thr: float = 0.35) -> list[float]:
        r = self._run(["-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", path, "-an", "-vf",
                       f"scale=320:-2,select='gt(scene,{thr})',showinfo", "-f", "null", "-"], timeout=1800)
        return [round(float(m.group(1)) + start, 3) for m in re.finditer(r"pts_time:([\d.]+)", r.stderr.decode("utf-8", "replace"))]

    def beats(self, path: str) -> dict[str, Any]:
        """Vurus bulma (numpy'siz): bas bandi + tam bant enerji akisi -> tempo (otokorelasyon) -> izgara, yerel tepeye oturtma."""
        def calc() -> dict[str, Any]:
            rate, hop = 11025, 256
            fps = rate / hop
            full = self._pcm(path, rate)
            low = self._pcm(path, rate, filt="lowpass=f=160")

            def energy(s: memoryview) -> list[float]:
                e = []
                for i in range(0, len(s) - hop, hop):
                    c = s[i:i + hop]
                    e.append(math.log1p(sum(x * x for x in c) / hop))
                return e
            ef, el = energy(full), energy(low)
            n = min(len(ef), len(el))
            if n < fps * 2:
                return {"bpm": 0, "beats": [], "onsets": []}
            env = [max(0.0, ef[i] - ef[i - 1]) + 1.5 * max(0.0, el[i] - el[i - 1]) for i in range(1, n)]
            env = [0.0] + env
            # yerel ortalamayi cikar (yuksek sesli bolumler her yeri vurus sanmasin)
            w = int(fps * 0.5)
            acc = [0.0]
            for v in env:
                acc.append(acc[-1] + v)
            onset = [max(0.0, env[i] - (acc[min(n, i + w)] - acc[max(0, i - w)]) / (min(n, i + w) - max(0, i - w))) for i in range(n)]
            # tempo: 70-180 BPM otokorelasyon (90-160 hafif tercihli)
            best, lag_best = -1.0, 0
            for bpm in range(70, 181):
                lag = fps * 60.0 / bpm
                li = int(round(lag))
                sc = sum(onset[i] * onset[i - li] for i in range(li, n, 2))
                sc *= 1.0 + (0.12 if 90 <= bpm <= 160 else 0.0)
                if sc > best:
                    best, lag_best = sc, lag
            bpm = 60.0 * fps / lag_best if lag_best else 0
            # faz: izgara tepelerinin toplami en buyuk olan baslangic
            ph_best, ph = -1.0, 0
            for p in range(int(lag_best) + 1):
                sc, k = 0.0, float(p)
                while k < n:
                    sc += onset[int(k)]
                    k += lag_best
                if sc > ph_best:
                    ph_best, ph = sc, p
            beats, k = [], float(ph)
            while k < n:
                i = int(k)
                lo, hi = max(0, i - 2), min(n, i + 3)
                j = max(range(lo, hi), key=lambda q: onset[q])
                beats.append(round(j / fps, 3))
                k += lag_best
            # guclu vuruslar (duzensiz parcalar icin): esik ustu yerel tepeler
            mx = max(onset) or 1.0
            ons = [round(i / fps, 3) for i in range(2, n - 2)
                   if onset[i] > 0.35 * mx and onset[i] >= max(onset[i - 2:i + 3])]
            thinned: list[float] = []
            for t in ons:
                if not thinned or t - thinned[-1] > 0.12:
                    thinned.append(t)
            return {"bpm": round(bpm, 1), "beats": beats, "onsets": thinned}
        return self._cached(path, "beats2", calc)

    # ---- kucuk resimler (zaman cizelgesi seridi)
    def thumbs(self, path: str, count: int = 12, height: int = 72) -> dict[str, Any]:
        """Klip seridi: her kare icin hizli arama (-ss girisin onunde), Pillow ile yan yana. Eski yol (fps+tile)
        uzun videoda tum dosyayi cozuyordu, kisa videoda son karo eksik kalinca hic gorsel cikmiyordu."""
        tag = f"thumbs2_{count}x{height}"
        f = self._cache(path, tag)
        try:
            d = json.loads(f.read_text("utf-8"))
            if d.get("sprite"):
                return d
        except (OSError, ValueError):
            pass
        from app.core.media_server import probe
        dur = float(probe(self.ffprobe(), path).get("duration") or 0)
        if dur <= 0:
            return {"step": 0, "sprite": ""}
        step = dur / count

        def one(i: int) -> bytes:
            t = min(max(0.0, dur - 0.08), step * i + step * 0.5)
            for ss in (t, 0.0):   # bozuk/sonda kare yoksa basa dus
                r = self._run(["-loglevel", "error", "-ss", f"{ss:.3f}", "-i", path, "-an", "-frames:v", "1",
                               "-vf", f"scale=-2:{height}", "-q:v", "6", "-f", "image2pipe", "-c:v", "mjpeg", "pipe:1"], timeout=60)
                if r.stdout:
                    return r.stdout
            return b""
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(4) as ex:
            frames = list(ex.map(one, range(count)))
        import base64
        import io
        try:
            from PIL import Image
            ims = [Image.open(io.BytesIO(b)).convert("RGB") if b else None for b in frames]
            ok = [im for im in ims if im]
            if not ok:
                return {"step": step, "count": count, "sprite": ""}
            w = ok[0].width
            sheet = Image.new("RGB", (w * count, height))
            last = ok[0]
            for i, im in enumerate(ims):
                last = im or last
                sheet.paste(last.resize((w, height)) if last.size != (w, height) else last, (i * w, 0))
            buf = io.BytesIO()
            sheet.save(buf, "JPEG", quality=72)
            data = {"step": step, "count": count, "sprite": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()}
        except Exception:
            log.exception("Studio serit")
            return {"step": step, "count": count, "sprite": ""}
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(data), "utf-8")
        return data

    # ---- metin katmani (ASS)
    def ass(self, project: dict[str, Any]) -> str:
        return build_ass(project)

    # ---- disa aktarim
    def encoder(self) -> str:
        if self._enc is None:
            r = self._run(["-loglevel", "error", "-f", "lavfi", "-i", "color=s=256x256:d=0.1", "-frames:v", "2", "-c:v", "h264_nvenc",
                           "-f", "null", "-"], timeout=30)
            self._enc = "h264_nvenc" if r.returncode == 0 else "libx264"
            log.info("Studio kodlayici: %s", self._enc)
        return self._enc

    def export(self, project: dict[str, Any], out: str, opts: dict[str, Any] | None = None) -> str:
        """Arka planda disa aktarir; is kimligi doner. Durum: job(jid)."""
        jid = "e" + str(int(time.time() * 1000))
        job = {"id": jid, "state": "running", "p": 0.0, "out": out, "error": "", "cancel": threading.Event(), "started": time.time()}
        with self._lock:
            self.jobs[jid] = job
        threading.Thread(target=self._export, args=(job, project, out, opts or {}), daemon=True, name="studio-export").start()
        return jid

    def job(self, jid: str) -> dict[str, Any]:
        j = self.jobs.get(jid) or {}
        return {k: v for k, v in j.items() if k != "cancel"}

    def cancel(self, jid: str) -> None:
        j = self.jobs.get(jid)
        if j:
            j["cancel"].set()

    def _export(self, job: dict, project: dict, out: str, opts: dict) -> None:
        import tempfile
        work = Path(tempfile.mkdtemp(prefix="kstudio_"))
        try:
            enc = self.encoder() if opts.get("hw", True) else "libx264"
            for attempt in (enc, "libx264") if enc != "libx264" else ("libx264",):
                args, total = build_export(project, out, work, attempt, opts)
                if not total:
                    raise RuntimeError("Zaman çizelgesi boş")
                args = self._fc_file(args, work)
                log.info("Studio disa aktarim (%s): %s", attempt, out)
                (work / "cmd.json").write_text(json.dumps(args, ensure_ascii=False, indent=0), "utf-8")
                from app.core.procjob import attach
                p = attach(subprocess.Popen([self.ffmpeg(), "-hide_banner", "-nostdin", "-y", "-progress", "pipe:1", "-nostats", *args],
                                            cwd=str(work), stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=NO_WINDOW))
                err: list[str] = []
                threading.Thread(target=lambda: err.extend(l.decode("utf-8", "replace") for l in p.stderr or []), daemon=True).start()
                for line in p.stdout or []:
                    if job["cancel"].is_set():
                        p.kill()
                        break
                    m = re.match(rb"out_time_us=(\d+)", line)
                    if m:
                        job["p"] = min(0.999, int(m.group(1)) / 1e6 / total)
                rc = p.wait()
                if job["cancel"].is_set():
                    job.update(state="cancelled")
                    try:
                        os.remove(out)
                    except OSError:
                        pass
                    return
                if rc == 0:
                    job.update(state="done", p=1.0, secs=round(time.time() - job["started"], 1), encoder=attempt)
                    return
                tail = "".join(err[-12:])
                log.warning("Studio disa aktarim hatasi (%s): %s", attempt, tail[-1500:])
                job["error"] = tail[-400:]
            job["state"] = "error"
        except Exception as exc:
            log.exception("Studio disa aktarim")
            job.update(state="error", error=str(exc)[:300])
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def frame(self, project: dict[str, Any], t: float, out: str) -> str:
        """Tek kare (kapak / MCP'nin goz atmasi icin): ayni grafikle t aninda bir PNG."""
        import tempfile
        work = Path(tempfile.mkdtemp(prefix="kstudio_f_"))
        try:
            args, _ = build_export(project, out, work, "png", {"frame": t})
            args = self._fc_file(args, work)
            r = subprocess.run([self.ffmpeg(), "-hide_banner", "-nostdin", "-y", "-loglevel", "error", *args], cwd=str(work),
                               capture_output=True, timeout=120, creationflags=NO_WINDOW)
            if r.returncode:
                raise RuntimeError(r.stderr.decode("utf-8", "replace")[-300:])
            return out
        finally:
            shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------------------------------------------------------
# Anahtar kare -> ffmpeg ifadesi
def _ease(u: str, e: str) -> str:
    if e == "out":
        return f"(1-(1-{u})*(1-{u}))"
    if e == "in":
        return f"({u}*{u})"
    if e == "inout":
        return f"({u}*{u}*(3-2*{u}))"
    return u


def kf_resolve(kf: list[dict], dur: float) -> list[dict]:
    """Negatif t = klip sonundan geriye (sablonlar her uzunluga uysun)."""
    out = []
    for k in kf or []:
        t = float(k.get("t", 0))
        out.append({**k, "t": max(0.0, dur + t if t < 0 else t)})
    return sorted(out, key=lambda k: k["t"])


def kf_expr(kf: list[dict], key: str, tv: str, default: float) -> str:
    pts = [(k["t"], float(k.get(key, default)), k.get("e", "")) for k in kf if key in k or key == "z"]
    if not pts:
        return f"{default}"
    expr = f"{pts[-1][1]:.4f}"
    for i in range(len(pts) - 1, 0, -1):
        t0, v0, _ = pts[i - 1]
        t1, v1, e = pts[i]
        span = max(1e-3, t1 - t0)
        u = f"(({tv}-{t0:.4f})/{span:.4f})"
        expr = f"if(lt({tv},{t1:.4f}),{v0:.4f}+({v1 - v0:.4f})*{_ease(u, e)},{expr})"
    return f"if(lt({tv},{pts[0][0]:.4f}),{pts[0][1]:.4f},{expr})"


def _q(s: str) -> str:
    """Filtre secenegini tek tirnakla koru (virgul/iki nokta icerir)."""
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _fpath(p: str) -> str:
    return p.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def _atempo(speed: float) -> str:
    parts, s = [], speed
    while s > 2.0:
        parts.append("atempo=2.0")
        s /= 2.0
    while s < 0.5:
        parts.append("atempo=0.5")
        s /= 0.5
    parts.append(f"atempo={s:.4f}")
    return ",".join(parts)


def _track_order(project: dict) -> dict[str, int]:
    """Listede ustteki iz ustte cizilir: cizim sirasi = ters liste sirasi."""
    tr = project.get("tracks", [])
    return {t["id"]: len(tr) - i for i, t in enumerate(tr)}


def trans_tail(c: dict, clips: list[dict], asset: dict) -> float:
    """Gercek klip-klip gecis: ayni izde bitisik sonraki klibin giris gecisi varsa (trans.over kapali degilse) bu klip
    gecis suresi kadar altta devam eder; yeni klip onun ustune maske/saydamlikla gelir (CapCut gibi A->B). Kaynakta
    yeterli kare yoksa kalan kadar uzar; donuk kare / hiz rampasi kliplerinde uzatilmaz. Onizleme: studio.js transTail."""
    if c.get("freeze") or c.get("ramp"):
        return 0.0
    end = float(c["start"]) + float(c["dur"])
    nxt = next((n for n in clips if n is not c and n.get("track") == c.get("track") and abs(float(n["start"]) - end) < 0.05), None)
    tr = (nxt or {}).get("trans") or {}
    if not tr.get("in") or tr.get("in") == "none" or tr.get("over") is False:
        return 0.0
    want = float(tr.get("dur", 0.35) or 0.35)
    if asset.get("kind") == "image" or asset.get("gif"):
        return want
    sp = max(0.1, float(c.get("speed", 1) or 1))
    left = (float(asset.get("dur", 0) or 0) - float(c.get("in", 0)) - float(c["dur"]) * sp) / sp
    return max(0.0, min(want, left))


def build_export(project: dict, out: str, work: Path, enc: str, opts: dict) -> tuple[list[str], float]:
    W, H, FPS = int(project.get("w", 1920)), int(project.get("h", 1080)), int(project.get("fps", 30))
    W -= W % 2
    H -= H % 2
    tracks = {t["id"]: t for t in project.get("tracks", [])}
    order = _track_order(project)
    assets = project.get("assets", {})
    clips = [c for c in flatten_clips(project.get("clips", [])) if not tracks.get(c.get("track"), {}).get("hide")]
    frame_t = opts.get("frame")
    rng = opts.get("range") or [0, project_end(project)]
    T0, T1 = float(rng[0]), float(rng[1])
    if frame_t is not None:
        T0, T1 = float(frame_t), float(frame_t) + 1.0 / FPS
    total = max(0.0, T1 - T0)
    if total <= 0:
        return [], 0.0
    inputs: list[str] = []
    graph: list[str] = []
    n_in = 0

    def add_input(args: list[str]) -> int:
        nonlocal n_in
        inputs.extend(args)
        n_in += 1
        return n_in - 1

    has_solo = any(tk.get("solo") for tk in tracks.values() if tk.get("kind") in ("audio", "video"))

    def _make_pattern_png() -> Path | None:
        pat = str(project.get("bgPattern") or "")
        if project.get("bgMode") != "pattern" or not pat:
            return None
        try:
            from PIL import Image, ImageDraw
            c1 = project.get("bg", "#140D24") or "#140D24"
            c2 = project.get("bg2", "#5B21B6") or "#5B21B6"
            def _rgb(hx: str, fb: tuple[int, int, int]) -> tuple[int, int, int]:
                hx = hx.lstrip("#")
                return tuple(int(hx[i:i+2], 16) for i in (0, 2, 4)) if len(hx) == 6 else fb
            r1, g1, b1 = _rgb(c1, (20, 13, 36))
            r2, g2, b2 = _rgb(c2, (91, 33, 182))
            img = Image.new("RGB", (W, H), (r1, g1, b1))
            dr = ImageDraw.Draw(img)
            if pat.startswith("gradient") or pat == "aurora":
                cols = {
                    "gradient-violet": ((20, 11, 46), (109, 40, 217)),
                    "gradient-sunset": ((35, 11, 46), (236, 72, 153)),
                    "gradient-neon": ((9, 24, 44), (16, 185, 129)),
                    "aurora": ((10, 18, 38), (124, 58, 237)),
                }.get(pat, ((r1, g1, b1), (r2, g2, b2)))
                a, b = cols
                for y in range(0, H, 2):
                    u = y / max(1, H - 1)
                    col = (int(a[0] + (b[0] - a[0]) * u), int(a[1] + (b[1] - a[1]) * u), int(a[2] + (b[2] - a[2]) * u))
                    dr.line([(0, y), (W, y)], fill=col, width=2)
            elif pat == "grid":
                step = max(24, W // 24)
                for x in range(0, W, step):
                    dr.line([(x, 0), (x, H)], fill=(r2, g2, b2), width=2)
                for y in range(0, H, step):
                    dr.line([(0, y), (W, y)], fill=(r2, g2, b2), width=2)
            elif pat == "dots":
                step = max(24, W // 24)
                rad = max(2, step // 10)
                for x in range(step // 2, W, step):
                    for y in range(step // 2, H, step):
                        dr.ellipse([x - rad, y - rad, x + rad, y + rad], fill=(r2, g2, b2))
            elif pat == "stripes":
                step = max(28, W // 20)
                for x in range(-H, W + H, step):
                    dr.line([(x, 0), (x + H, H)], fill=(r2, g2, b2), width=max(4, step // 3))
            out = work / "bg_pattern.png"
            img.save(out)
            return out
        except Exception:
            return None

    pat_png = _make_pattern_png()
    if pat_png:
        pidx = add_input(["-loop", "1", "-t", f"{total:.3f}", "-i", str(pat_png)])
        graph.append(f"[{pidx}:v]scale={W}:{H},fps={FPS},format=yuva420p[base0]")
    else:
        graph.append(f"color=c={project.get('bg', '#000000').replace('#', '0x')}:s={W}x{H}:r={FPS}:d={total:.3f},format=yuva420p[base0]")
    cur = "base0"
    vis = [c for c in clips if tracks.get(c["track"], {}).get("kind") == "video" and c.get("asset") in assets]
    vis.sort(key=lambda c: (order.get(c["track"], 0), c["start"]))
    by_id = {str(x["id"]): x for x in vis if "id" in x}
    bg_blur_pct = float(project.get("bgBlur", 45) or 0) if project.get("bgMode") == "blur" else 0.0
    audio_parts: list[str] = []
    k = 0
    for c in vis:
        a = assets[c["asset"]]
        s, d = float(c["start"]), float(c["dur"])
        tail = trans_tail(c, vis, a)                 # gercek gecis: sonraki klip girerken bu klip altta devam eder
        if s + d + tail <= T0 or s >= T1:
            continue
        speed = max(0.1, float(c.get("speed", 1) or 1))
        cut0 = max(0.0, T0 - s)                      # aralik basindan kirpilan kisim (zaman cizelgesi)
        src_in = float(c.get("in", 0)) + cut0 * speed
        seg = min(d + tail - cut0, T1 - max(s, T0))
        if seg <= 0:
            continue
        ramp = ramp_table(c) if c.get("ramp") and a["kind"] == "video" and not a.get("gif") else None
        vin = ["-c:v", "libvpx-vp9"] if a.get("alpha") else []          # seffaf WebM (arka plani silinmis / Lottie)
        if c.get("freeze"):
            ii = add_input(["-ss", f"{float(c.get('in', 0)):.3f}", "-t", "0.3", *vin, "-i", a["path"]])
            ch = ["trim=end_frame=1", "setpts=PTS-STARTPTS", f"tpad=stop_mode=clone:stop_duration={seg + 0.2:.3f}"]
        elif a["kind"] == "image" and not a.get("gif"):
            ii = add_input(["-loop", "1", "-framerate", str(FPS), "-t", f"{seg:.3f}", "-i", a["path"]])
            ch = ["setpts=PTS-STARTPTS"]
        elif a.get("gif"):
            ii = add_input(["-ignore_loop", "0", "-t", f"{seg:.3f}", "-i", a["path"]])
            ch = ["setpts=PTS-STARTPTS"]
        elif ramp:
            segs = _ramp_window(ramp, cut0, seg)
            src0 = float(c.get("in", 0)) + segs[0][2]
            span = segs[-1][3] - segs[0][2]
            src_in = src0
            ii = add_input(["-ss", f"{src0:.3f}", "-t", f"{span + 0.05:.3f}", *vin, "-i", a["path"]])
            base = segs[0][2]
            expr = f"{segs[-1][1] - cut0:.4f}"
            for t0_, t1_, a0, a1, sp in reversed(segs):
                expr = f"if(lt(T,{a1 - base:.4f}),{t0_ - cut0:.4f}+(T-{a0 - base:.4f})/{sp:.4f},{expr})"
            ch = [f"setpts='({expr})/TB'"]
        else:
            ii = add_input(["-ss", f"{src_in:.3f}", "-t", f"{seg * speed + 0.05:.3f}", *vin, "-i", a["path"]])
            ch = [f"setpts=(PTS-STARTPTS)/{speed:.4f}" if a["kind"] == "video" and not a.get("gif") else "setpts=PTS-STARTPTS"]
        rf = c.get("reframe") or []
        if rf:   # dikey otomatik cerceve: kaynak zamaninda yatay merkez
            cx = kf_expr(sorted([{"t": float(r["t"]), "cx": float(r["cx"])} for r in rf], key=lambda r: r["t"]), "cx",
                         f"(t*{speed:.4f}+{src_in:.4f})", 0.5)
            ch.append(f"crop=w='min(iw,ih*{W}/{H})':h='min(ih,iw*{H}/{W})':x={_q(f'max(0,min(iw-ow,({cx})*iw-ow/2))')}:y=(ih-oh)/2")
        key = c.get("key") or {}
        if key.get("on"):   # yesil/mavi perde
            kc = str(key.get("color", "#00ff00")).replace("#", "0x")
            ch.append(f"format=yuva420p,chromakey=color={kc}:similarity={float(key.get('sim', 0.15)):.3f}:blend={float(key.get('smooth', 0.08)):.3f}")
            if key.get("spill", True):
                g = str(key.get("color", "#00ff00")).lstrip("#")
                ch.append("despill=type=" + ("blue" if len(g) == 6 and int(g[4:6], 16) > int(g[2:4], 16) else "green"))
        if c.get("stabilize") and a["kind"] == "video" and not a.get("gif"):
            ch.append("deshake=rx=32:ry=32:edge=mirror")
        if c.get("optFlow") and a["kind"] == "video" and not a.get("gif") and (speed < 0.99 or ramp):
            ch.append(f"minterpolate=fps={FPS}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1")
        ch.append(f"fps={FPS}")
        fit = c.get("fit", "cover" if tracks[c["track"]].get("id") == "v1" or len([t for t in tracks.values() if t['kind'] == 'video']) == 1 else "contain")
        if c.get("crop") in ("half-w", "half-h"):   # yan yana / ust-alt
            bw, bh = (W // 2 // 2 * 2, H) if c["crop"] == "half-w" else (W, H // 2 // 2 * 2)
            ch.append(f"scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},format=rgba")
        elif fit == "contain":
            ch.append(f"scale={W}:{H}:force_original_aspect_ratio=decrease,format=rgba,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black@0")
        elif fit == "stretch":
            ch.append(f"scale={W}:{H},format=rgba")
        else:
            ch.append(f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},format=rgba")
        ch.extend(studio_fx_adv.adj_filters(c.get("adj")))
        gr = c.get("grade") or {}
        if grade_active(gr):
            bake_grade(gr, work / f"g{k}.cube")
            ch.append(f"lut3d=file=g{k}.cube:interp=tetrahedral")
        shutter_ang = float(c.get("shutterAngle") or 0)
        if shutter_ang >= 45 and a["kind"] == "video" and not a.get("gif"):
            n_tm = 2 if shutter_ang < 135 else 3 if shutter_ang < 270 else 4
            wts = " ".join(["1 2 1", "1 2 2 1"][n_tm - 3].split()[:n_tm]) if n_tm >= 3 else "1 1"
            ch.append(f"tmix=frames={n_tm}:weights='{wts}'")
        zk = kf_resolve(c.get("zoom") or [], d)
        if zk:
            tv = f"(on/{FPS}+{cut0:.4f})"
            z = kf_expr(zk, "z", tv, 1.0)
            cxe = kf_expr(zk, "cx", tv, 0.5) if any("cx" in q for q in zk) else "0.5"
            cye = kf_expr(zk, "cy", tv, 0.5) if any("cy" in q for q in zk) else "0.5"
            ch.append(f"zoompan=z={_q(f'max(1,{z})')}:x={_q(f'max(0,min(iw-iw/zoom,({cxe})*iw-iw/zoom/2))')}:"
                      f"y={_q(f'max(0,min(ih-ih/zoom,({cye})*ih-ih/zoom/2))')}:d=1:s={W}x{H}:fps={FPS},format=rgba")
        fxat = c.get("fxAt") or {}
        for fid in c.get("fx") or []:
            fx = FX.get(fid)
            if not fx:
                continue
            pl = fxat.get(fid) or {}
            at, fd = pl.get("at", "all"), max(0.05, float(pl.get("d", 1.0) or 1.0))
            if at in ("in", "out"):   # efekt yalniz klibin basinda / sonunda
                a0 = 0.0 if at == "in" else max(0.0, d - fd)
                a1 = min(d, fd) if at == "in" else d
                if a1 - cut0 <= 0:
                    continue
                tg = f"c{k}{re.sub(r'[^a-z0-9]', '', fid)}"
                ch.append(f"split[{tg}A][{tg}B];[{tg}B]{_fx_chain(fx['ff'], W, H, a0 - cut0, tg + 'f')},format=rgba[{tg}C];"
                          f"[{tg}A][{tg}C]overlay=enable='between(t,{a0 - cut0:.4f},{a1 - cut0:.4f})'")
            else:
                ch.append(_fx_chain(fx["ff"], W, H, 0.0, f"c{k}{fid}"))
        mf = studio_fx_adv.mask_filter(c.get("mask"), W, H)
        if mf:
            ch.append(mf)
        anf, _ = studio_anim.clip_filters(c, d, cut0, FPS, W, H, f"an{k}")
        ch += anf
        if c.get("flipH"):
            ch.append("hflip")
        if c.get("flipV"):
            ch.append("vflip")
        ukf = kf_resolve(c.get("kf") or [], d)
        t_clip = f"(t+{cut0:.4f})"
        sc, rot = float(c.get("scale", 1) or 1), float(c.get("rot", 0) or 0)
        px_parent = py_parent = None
        if c.get("parent") and str(c["parent"]) in by_id:
            sc_ex, has_ksc, rot_ex, has_krot, px_parent, py_parent = studio_fx_adv.resolve_parent_xform(
                c, by_id, kf_resolve, T0, off, cut0, W, H
            )
            if has_ksc or sc_ex != "1.0000":
                ch.append(f"scale=w='max(2,2*floor(iw*({sc_ex})/2))':h='max(2,2*floor(ih*({sc_ex})/2))':eval=frame")
            arot = studio_anim.clip_exprs(c, d, t_clip)["r"] if anf else ""
            if has_krot or rot_ex != "0.0000" or arot:
                a_expr = f"({rot_ex})*PI/180" + (f"+({arot})*PI/180" if arot else "")
                ch.append(f"rotate=a='{a_expr}':c=black@0:ow='hypot(iw,ih)':oh='hypot(iw,ih)'")
        else:
            if any("scale" in q for q in ukf):
                sc_ex = studio_fx_adv.kf_expr_adv(ukf, "scale", t_clip, sc)
                ch.append(f"scale=w='max(2,2*floor(iw*({sc_ex})/2))':h='max(2,2*floor(ih*({sc_ex})/2))':eval=frame")
            elif abs(sc - 1) > 1e-3:
                ch.append(f"scale=iw*{sc:.4f}:ih*{sc:.4f}")
            arot = studio_anim.clip_exprs(c, d, t_clip)["r"] if anf else ""
            has_krot = any("rot" in q for q in ukf)
            if has_krot or arot:
                rot_ex = studio_fx_adv.kf_expr_adv(ukf, "rot", t_clip, rot) if has_krot else f"{rot:.4f}"
                a_expr = f"({rot_ex})*PI/180" + (f"+({arot})*PI/180" if arot else "")
                ch.append(f"rotate=a='{a_expr}':c=black@0:ow='hypot(iw,ih)':oh='hypot(iw,ih)'")
            elif abs(rot) > 0.01:
                ch.append(f"rotate={math.radians(rot):.5f}:c=black@0:ow=rotw({math.radians(rot):.5f}):oh=roth({math.radians(rot):.5f})")
        op = float(c.get("opacity", 1) if c.get("opacity") is not None else 1)
        if any("opacity" in q for q in ukf):
            op_ex = studio_fx_adv.kf_expr_adv(ukf, "opacity", f"(T+{cut0:.4f})", op)
            ch.append(f"format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*clip({op_ex},0,1)'")
        elif op < 0.999:
            ch.append(f"colorchannelmixer=aa={op:.3f}")
        fi, fo = float(c.get("fadeIn", 0) or 0), float(c.get("fadeOut", 0) or 0)
        tr = (c.get("trans") or {})
        tdur = float(tr.get("dur", 0.35) or 0.35)
        if tr.get("in") == "fade":
            fi = max(fi, tdur)
        if fi > 0 and cut0 < fi:
            ch.append(f"fade=t=in:st={-cut0:.3f}:d={fi:.3f}:alpha=1")
        if fo > 0:
            ch.append(f"fade=t=out:st={d - cut0 - fo:.3f}:d={fo:.3f}:alpha=1")
        tin = tr.get("in")
        if tin in TRANS_FF and cut0 < tdur:
            ch.append(_trans_in(tin, tdur, W, H, f"tr{k}", cut0, FPS))
        off = max(s, T0) - T0
        ch.append(f"setpts=PTS+{off:.4f}/TB")
        if bg_blur_pct > 0 and order.get(c["track"], 0) == 0:
            sig = max(1.0, bg_blur_pct * 0.65)
            graph.append(f"[{ii}:v]" + ",".join(ch) + f",split[c{k}][bg{k}]")
            graph.append(f"[bg{k}]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma={sig:.1f},eq=brightness=-0.10[bgo{k}]")
            graph.append(f"[{cur}][bgo{k}]overlay=eof_action=pass:enable='between(t,{off:.4f},{off + seg:.4f})'[bgc{k}]")
            cur = f"bgc{k}"
        else:
            graph.append(f"[{ii}:v]" + ",".join(ch) + f"[c{k}]")
        t_pos = f"(t-{off:.4f}+{cut0:.4f})"
        if px_parent is not None:
            ox = f"(W-w)/2+{px_parent}"
            oy = f"(H-h)/2+{py_parent}"
        else:
            x_ex = studio_fx_adv.kf_expr_adv(ukf, "x", t_pos, float(c.get("x", 0) or 0)) if any("x" in q for q in ukf) else f"{float(c.get('x', 0) or 0):.4f}"
            y_ex = studio_fx_adv.kf_expr_adv(ukf, "y", t_pos, float(c.get("y", 0) or 0)) if any("y" in q for q in ukf) else f"{float(c.get('y', 0) or 0):.4f}"
            ox = f"(W-w)/2+({x_ex})*{W}"
            oy = f"(H-h)/2+({y_ex})*{H}"
        if anf:
            aex = studio_anim.clip_exprs(c, d, t_pos)
            if aex["x"]:
                ox += f"+({aex['x']})*{W}"
            if aex["y"]:
                oy += f"+({aex['y']})*{H}"
        graph.extend(studio_fx_adv.blend_composite_chain(
            cur, f"c{k}", f"b{k}", k, c.get("blend", "normal"),
            ox, oy, f"between(t,{off:.4f},{off + seg:.4f})", W, H, FPS
        ))
        cur = f"b{k}"
        if (a.get("audio") and not c.get("freeze") and not tracks[c["track"]].get("mute")
                and (not has_solo or tracks[c["track"]].get("solo"))
                and float(c.get("vol", 1) if c.get("vol") is not None else 1) > 0 and frame_t is None):
            cv = {**c, "vol": float(c.get("vol", 1) if c.get("vol") is not None else 1) * float(tracks[c["track"]].get("vol", 1) or 0)}
            audio_parts.append((_audio_chain(ii, cv, cut0, seg, off, speed, ramp), bool(tracks[c["track"]].get("duck"))))
        k += 1
    # efekt / ayar katmani izi: zaman araliginda tum goruntuye uygula
    for c in sorted([c for c in clips if tracks.get(c["track"], {}).get("kind") == "fx"], key=lambda c: (order.get(c["track"], 0), c["start"])):
        s, d = float(c["start"]) - T0, float(c["dur"])
        if s + d <= 0 or s >= total:
            continue
        ach: list[str] = []
        ach.extend(studio_fx_adv.adj_filters(c.get("adj")))
        gr_fx = c.get("grade") or {}
        if grade_active(gr_fx):
            bake_grade(gr_fx, work / f"gfx{k}.cube")
            ach.append(f"lut3d=file=gfx{k}.cube:interp=tetrahedral")
        fids = ([c["mode"]] if c.get("mode") and c.get("mode") != "adjustment" else []) + [x for x in (c.get("fx") or []) if x != c.get("mode")]
        for fid in fids:
            fx = FX.get(fid)
            if fx:
                ach.append(_fx_chain(fx["ff"], W, H, s, f"x{k}_{re.sub(r'[^a-z0-9]', '', fid)}"))
        if not ach:
            continue
        fx_op = float(c.get("opacity", 1) if c.get("opacity") is not None else 1)
        if fx_op < 0.999:
            ach.append(f"format=rgba,colorchannelmixer=aa={fx_op:.3f}")
        graph.append(f"[{cur}]split[fa{k}][fb{k}]")
        graph.append(f"[fb{k}]{','.join(ach)}[fc{k}]")
        graph.extend(studio_fx_adv.blend_composite_chain(
            f"fa{k}", f"fc{k}", f"b{k}", k, c.get("blend", "normal"),
            "0", "0", f"between(t,{max(0, s):.4f},{s + d:.4f})", W, H, FPS
        ))
        cur = f"b{k}"
        k += 1
    # metin / altyazi / abone animasyonu / mod yazilari: ASS
    ass = build_ass(project, 0.0)   # mutlak zaman: animasyonlar aralik basinda yeniden baslamasin
    if "Dialogue:" in ass:
        (work / "k.ass").write_text(ass, "utf-8-sig")
        fd = work / "fonts"
        fd.mkdir(exist_ok=True)
        used = set(re.findall(r"\\fn([^\\}]+)", ass)) | {"Chakra Petch"}
        idx = fonts_index()
        files = {Path(idx[f]) for f in used if f in idx} | set(font_files()[:12])
        for f in files:
            try:
                shutil.copy2(f, fd / f.name)
            except OSError:
                pass
        sh = f"setpts=PTS+{T0:.4f}/TB," if T0 > 0 else ""
        un = f",setpts=PTS-{T0:.4f}/TB" if T0 > 0 else ""
        graph.append(f"[{cur}]{sh}subtitles=k.ass:fontsdir=fonts{un}[b{k}]")
        cur = f"b{k}"
        k += 1
    # kanal profil fotografi (endscreen / channel sablonlari icin dairesel avatar)
    for c in clips:
        st = c.get("style") or {}
        av = st.get("avatarImg")
        if not av or (c.get("graphic") != "endscreen" and c.get("subscribe") != "channel"):
            continue
        s, d = float(c["start"]) - T0, float(c["dur"])
        if s + d <= 0 or s >= total:
            continue
        try:
            from PIL import Image, ImageDraw
            import base64, io
            if str(av).startswith("data:image"):
                raw = base64.b64decode(str(av).split(",", 1)[1])
                im = Image.open(io.BytesIO(raw)).convert("RGBA")
            elif Path(str(av)).is_file():
                im = Image.open(str(av)).convert("RGBA")
            else:
                continue
            sz = max(48, int(round(126 * (H / 1080.0) * (float(st.get("size", 100) or 100) / 100.0))))
            im = im.resize((sz, sz), Image.LANCZOS)
            mask = Image.new("L", (sz, sz), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, sz - 1, sz - 1), fill=255)
            im.putalpha(mask)
            avp = work / f"avatar_{k}.png"
            im.save(avp)
            aidx = add_input(["-loop", "1", "-t", f"{total:.3f}", "-i", str(avp)])
            if c.get("graphic") == "endscreen":
                ax, ay = int(round(W / 2 - sz / 2)), int(round(H * 0.82 - sz / 2))
            else:
                ax = int(round(W * float(st.get("x", 0.5)) - 225 * (H / 1080.0) - sz / 2))
                ay = int(round(H * float(st.get("y", 0.8)) - sz / 2))
            graph.append(f"[{cur}][{aidx}:v]overlay=x={ax}:y={ay}:enable='between(t,{max(0, s):.4f},{s + d:.4f})'[b{k}]")
            cur = f"b{k}"
            k += 1
        except Exception:
            pass
    graph.append(f"[{cur}]format=yuv420p[vout]")
    # ses
    for c in clips:
        t = tracks.get(c.get("track"), {})
        if t.get("kind") != "audio" or t.get("mute") or t.get("hide") or (has_solo and not t.get("solo")) or c.get("asset") not in assets or frame_t is not None:
            continue
        a = assets[c["asset"]]
        s, d = float(c["start"]), float(c["dur"])
        if s + d <= T0 or s >= T1:
            continue
        speed = max(0.1, float(c.get("speed", 1) or 1))
        cut0 = max(0.0, T0 - s)
        seg = min(d - cut0, T1 - max(s, T0))
        src_in = float(c.get("in", 0)) + cut0 * speed
        ii = add_input(["-ss", f"{src_in:.3f}", "-t", f"{seg * speed + 0.05:.3f}", "-i", a["path"]])
        cv = {**c, "vol": float(c.get("vol", 1) if c.get("vol") is not None else 1) * float(t.get("vol", 1) if t.get("vol") is not None else 1)}
        audio_parts.append((_audio_chain(ii, cv, cut0, seg, max(s, T0) - T0, speed), bool(t.get("duck"))))
    if frame_t is not None:
        return [*inputs, "-filter_complex", ";".join(graph), "-map", "[vout]", "-frames:v", "1", out], total
    master = project.get("master") or {}
    lufs = master.get("lufs") if "lufs" in master else opts.get("lufs")
    tail = (f"loudnorm=I={float(lufs):.1f}:TP=-1.5:LRA=11," if lufs else "") + f"alimiter=limit=0.97,apad,atrim=0:{total:.3f}"
    if audio_parts:
        for i, (part, _m) in enumerate(audio_parts):
            graph.append(part + f"[a{i}]")
        music = [i for i, (_p, m) in enumerate(audio_parts) if m]
        voice = [i for i, (_p, m) in enumerate(audio_parts) if not m]
        if music and voice:   # muzik konusmanin altina girsin (sidechain)
            graph.append("".join(f"[a{i}]" for i in voice) + f"amix=inputs={len(voice)}:normalize=0:dropout_transition=0,asplit=2[vb][vk]")
            graph.append("".join(f"[a{i}]" for i in music) + f"amix=inputs={len(music)}:normalize=0:dropout_transition=0[mb]")
            amt = float(master.get("duck", 0.6))
            graph.append(f"[mb][vk]sidechaincompress=threshold={0.02 + 0.08 * (1 - amt):.3f}:ratio={2 + 10 * amt:.1f}:attack=20:release=450:makeup=1[md]")
            graph.append(f"[vb][md]amix=inputs=2:normalize=0:dropout_transition=0,{tail}[aout]")
        else:
            mix = "".join(f"[a{i}]" for i in range(len(audio_parts)))
            graph.append(f"{mix}amix=inputs={len(audio_parts)}:normalize=0:dropout_transition=0,{tail}[aout]")
    else:
        graph.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{total:.3f}[aout]")
    return [*inputs, *_deliver_args(graph, opts, enc, W, H, FPS, total, out)], total


DELIVER = {
    "youtube": {"name": "YouTube 1080p/4K (H.264)", "format": "mp4", "lufs": -14},
    "shorts": {"name": "Shorts / Reels / TikTok", "format": "mp4", "lufs": -14, "size": [1080, 1920]},
    "hevc": {"name": "Yüksek verim (H.265)", "format": "hevc", "lufs": -14},
    "prores": {"name": "ProRes 422 HQ (kurgu arşivi)", "format": "prores"},
    "gif": {"name": "GIF (480p, 15 fps)", "format": "gif"},
    "webm": {"name": "WebM (VP9)", "format": "webm"},
    "mp3": {"name": "Sadece ses MP3 320k", "format": "mp3", "lufs": -14},
    "wav": {"name": "Sadece ses WAV", "format": "wav"},
}


def _deliver_args(graph: list[str], opts: dict, enc: str, W: int, H: int, FPS: int, total: float, out: str) -> list[str]:
    fmt = opts.get("format", "mp4")
    q = opts.get("quality", "high")
    size = opts.get("size")
    if size and fmt != "gif" and [int(size[0]), int(size[1])] != [W, H]:
        w2, h2 = int(size[0]) // 2 * 2, int(size[1]) // 2 * 2
        graph.append(f"[vout]scale={w2}:{h2}:force_original_aspect_ratio=decrease:flags=lanczos,pad={w2}:{h2}:(ow-iw)/2:(oh-ih)/2,setsar=1[vsz]")
        vmap = "[vsz]"
    else:
        vmap = "[vout]"
    t = ["-t", f"{total:.3f}"]
    if fmt in ("mp3", "wav"):
        a = ["-c:a", "libmp3lame", "-b:a", "320k"] if fmt == "mp3" else ["-c:a", "pcm_s16le"]
        graph.append(f"{vmap}nullsink")
        return ["-filter_complex", ";".join(graph), "-map", "[aout]", *a, "-ar", "48000", *t, out]
    if fmt == "gif":
        graph.append(f"{vmap}fps=15,scale=480:-2:flags=lanczos,split[g0][g1];[g0]palettegen=stats_mode=diff[gp];[g1][gp]paletteuse=dither=bayer:bayer_scale=4[gif]")
        graph.append("[aout]anullsink")
        return ["-filter_complex", ";".join(graph), "-map", "[gif]", "-loop", "0", *t, out]
    if fmt == "prores":
        v = ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le"]
        a = ["-c:a", "pcm_s16le"]
    elif fmt == "webm":
        v = ["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0", "-row-mt", "1", "-pix_fmt", "yuv420p"]
        a = ["-c:a", "libopus", "-b:a", "192k"]
    elif fmt == "hevc":
        v = (["-c:v", "hevc_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "20" if q == "high" else "26", "-b:v", "0", "-tag:v", "hvc1"]
             if enc == "h264_nvenc" else ["-c:v", "libx265", "-preset", "medium", "-crf", "20" if q == "high" else "25", "-tag:v", "hvc1"])
        v += ["-pix_fmt", "yuv420p"]
        a = ["-c:a", "aac", "-b:a", "320k"]
    else:
        if enc == "h264_nvenc":
            v = ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "17" if q == "high" else "23",
                 "-b:v", "0", "-profile:v", "high", "-spatial-aq", "1", "-temporal-aq", "1", "-bf", "2"]
        else:
            v = ["-c:v", "libx264", "-preset", "medium" if q == "high" else "veryfast", "-crf", "17" if q == "high" else "22"]
        v += ["-pix_fmt", "yuv420p"]
        a = ["-c:a", "aac", "-b:a", "320k"]
    mov = ["-movflags", "+faststart"] if fmt in ("mp4", "hevc") else []
    return ["-filter_complex", ";".join(graph), "-map", vmap, "-map", "[aout]", *v, "-r", str(FPS), *a, "-ar", "48000", *mov, *t, out]


# ---------------------------------------------------------------------------------------------------------------
# Hiz rampasi: c.ramp = [{p: 0-1 (kaynak araligi), s: hiz}], c.srcLen = kapsanan kaynak sn
RAMP_N = 24


def ramp_speed(points: list[dict], p: float) -> float:
    pts = sorted(points, key=lambda q: q["p"])
    if p <= pts[0]["p"]:
        return float(pts[0]["s"])
    for a, b in zip(pts, pts[1:]):
        if p <= b["p"]:
            u = (p - a["p"]) / max(1e-6, b["p"] - a["p"])
            return float(a["s"]) + (float(b["s"]) - float(a["s"])) * u
    return float(pts[-1]["s"])


def ramp_table(c: dict) -> list[tuple[float, float, float, float, float]]:
    """[(tl0, tl1, src0, src1, hiz)] klibe gore (src: in'den itibaren)."""
    L = float(c.get("srcLen") or c["dur"] * float(c.get("speed", 1) or 1))
    out, t = [], 0.0
    for i in range(RAMP_N):
        a0, a1 = L * i / RAMP_N, L * (i + 1) / RAMP_N
        sp = max(0.05, ramp_speed(c["ramp"], (i + 0.5) / RAMP_N))
        d = (a1 - a0) / sp
        out.append((t, t + d, a0, a1, sp))
        t += d
    return out


def ramp_duration(c: dict) -> float:
    return ramp_table(c)[-1][1]


def _ramp_window(tab: list, cut0: float, seg: float) -> list[tuple[float, float, float, float, float]]:
    """Disa aktarim araligina dusen dilimler (kirpilmis)."""
    out = []
    w0, w1 = cut0, cut0 + seg
    for t0, t1, a0, a1, sp in tab:
        if t1 <= w0 or t0 >= w1:
            continue
        nt0, nt1 = max(t0, w0), min(t1, w1)
        out.append((nt0, nt1, a0 + (nt0 - t0) * sp, a0 + (nt1 - t0) * sp, sp))
    return out or [(cut0, cut0 + seg, 0.0, seg, 1.0)]


# ---------------------------------------------------------------------------------------------------------------
# Renk: tekerlekler + LUT -> tek 3D LUT (onizleme shader'i ayni matematigi kullanir)
LUT_N = 33


def grade_active(g: dict) -> bool:
    if not g:
        return False
    if g.get("lut") and float(g.get("lutMix", 1)) > 0:
        return True
    for k in ("exp", "con", "temp", "tint"):
        if abs(float(g.get(k, 0) or 0)) > 1e-4:
            return True
    if abs(float(g.get("sat", 1) if g.get("sat") is not None else 1) - 1) > 1e-4:
        return True
    return any(abs(float(v)) > 1e-4 for w in ("lift", "gamma", "gain") for v in (g.get(w) or [0, 0, 0]))


def lut_dir() -> Path:
    d = home_dir() / "LUT"
    d.mkdir(parents=True, exist_ok=True)
    return d


def parse_cube(path: Path) -> tuple[int, list[tuple[float, float, float]]]:
    n, data = 0, []
    for line in Path(path).read_text("utf-8", "replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.upper().startswith("LUT_3D_SIZE"):
            n = int(line.split()[1])
            continue
        if line[0].isalpha():
            continue
        parts = line.split()
        if len(parts) >= 3:
            try:
                data.append((float(parts[0]), float(parts[1]), float(parts[2])))
            except ValueError:
                pass
    if not n or len(data) < n ** 3:
        raise ValueError("gecersiz .cube (yalniz 3D LUT)")
    return n, data[: n ** 3]


def _lut_sample(n: int, data: list, r: float, g: float, b: float) -> tuple[float, float, float]:
    """Trilinear; .cube sirasi: r en hizli degisen."""
    def idx(i: int, j: int, k: int) -> tuple[float, float, float]:
        return data[i + j * n + k * n * n]
    x, y, z = r * (n - 1), g * (n - 1), b * (n - 1)
    i0, j0, k0 = min(int(x), n - 2), min(int(y), n - 2), min(int(z), n - 2)
    fx, fy, fz = x - i0, y - j0, z - k0
    out = []
    for ch in range(3):
        c000, c100 = idx(i0, j0, k0)[ch], idx(i0 + 1, j0, k0)[ch]
        c010, c110 = idx(i0, j0 + 1, k0)[ch], idx(i0 + 1, j0 + 1, k0)[ch]
        c001, c101 = idx(i0, j0, k0 + 1)[ch], idx(i0 + 1, j0, k0 + 1)[ch]
        c011, c111 = idx(i0, j0 + 1, k0 + 1)[ch], idx(i0 + 1, j0 + 1, k0 + 1)[ch]
        c00, c10 = c000 + (c100 - c000) * fx, c010 + (c110 - c010) * fx
        c01, c11 = c001 + (c101 - c001) * fx, c011 + (c111 - c011) * fx
        c0, c1 = c00 + (c10 - c00) * fy, c01 + (c11 - c01) * fy
        out.append(c0 + (c1 - c0) * fz)
    return out[0], out[1], out[2]


def grade_pixel(g: dict, r: float, gg: float, b: float, lut: tuple | None = None) -> tuple[float, float, float]:
    """studio.js glsl 'grade()' ile birebir ayni."""
    e = 2.0 ** float(g.get("exp", 0) or 0)
    c = [r * e, gg * e, b * e]
    tmp, tint = float(g.get("temp", 0) or 0), float(g.get("tint", 0) or 0)
    c[0] *= 1 + 0.12 * tmp
    c[2] *= 1 - 0.12 * tmp
    c[1] *= 1 - 0.10 * tint
    lift, gam, gain = (g.get("lift") or [0, 0, 0]), (g.get("gamma") or [0, 0, 0]), (g.get("gain") or [0, 0, 0])
    for i in range(3):
        v = c[i] * (1 + float(gain[i])) + float(lift[i]) * (1 - c[i])
        v = min(1.0, max(0.0, v))
        c[i] = v ** (1.0 / max(0.05, 1 + float(gam[i])))
    con = float(g.get("con", 0) or 0)
    c = [(v - 0.5) * (1 + con) + 0.5 for v in c]
    sat = float(g.get("sat", 1) if g.get("sat") is not None else 1)
    y = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    c = [min(1.0, max(0.0, y + (v - y) * sat)) for v in c]
    if lut:
        n, data, mix = lut
        lr = _lut_sample(n, data, *c)
        c = [c[i] + (min(1.0, max(0.0, lr[i])) - c[i]) * mix for i in range(3)]
    return c[0], c[1], c[2]


def bake_grade(g: dict, out: Path) -> Path:
    lut = None
    if g.get("lut"):
        f = lut_dir() / Path(str(g["lut"])).name
        if f.is_file():
            n, data = parse_cube(f)
            lut = (n, data, float(g.get("lutMix", 1)))
    n = LUT_N
    lines = [f"LUT_3D_SIZE {n}"]
    for bi in range(n):
        for gi in range(n):
            for ri in range(n):
                r, gg, b = grade_pixel(g, ri / (n - 1), gi / (n - 1), bi / (n - 1), lut)
                lines.append(f"{r:.5f} {gg:.5f} {b:.5f}")
    Path(out).write_text("\n".join(lines) + "\n", "ascii")
    return Path(out)


def _fx_chain(ff: str, W: int, H: int, start: float, tag: str) -> str:
    """Zincirdeki W/H/S yer tutucularini ve ic etiketleri (split[d0]...) tekil yap."""
    s = re.sub(r"\bW\b", str(W), ff)
    s = re.sub(r"\bH\b", str(H), s)
    s = re.sub(r"\bS\b", f"{start:.4f}", s)
    s = re.sub(r"\[([a-z]\d)\]", lambda m: f"[{tag}{m.group(1)}]", s)
    return s


def _trans_in(kind: str, d: float, W: int, H: int, tag: str = "t", c0: float = 0.0, fps: int = 30) -> str:
    """Klip girisi gecisi. Akisin t=0 ani klibin c0. saniyesi (bastan kirpilmissa); onizleme: studio-fx.js transIn.
    u = 0..1 ilerleme, e = cubic ease-out (onizleme ile ayni egri)."""
    def prog(v: str) -> tuple[str, str]:
        u = f"min(1,max(0,({v}+{c0:.4f})/{d:.4f}))"
        return u, f"(1-pow(1-{u},3))"
    u, e = prog("t")                   # eq/crop/rotate ifadeleri
    U, E = prog("T")                   # geq/blend ifadeleri
    end = max(0.001, d - c0)
    en = f"enable='lt(t,{end:.4f})'"
    if kind == "flash":
        return f"eq=brightness='0.9*(1-{u})':eval=frame"
    if kind == "lightleak":            # sicak turuncu patlama, sonra normale don
        return f"eq=brightness='0.3*(1-{u})':gamma_r='1+0.9*(1-{u})':gamma_b='1-0.35*(1-{u})':eval=frame"
    if kind in ("blur", "pixel", "zoomblur"):
        # gblur sigma ifade almaz: bulanik/pikselli kopya ile zamanla karisim
        soft = f"scale=iw/32:-2,scale={W}:{H}:flags=neighbor" if kind == "pixel" else "gblur=sigma=24"
        pre = ""
        if kind == "zoomblur":
            pre = (f"zoompan=z='max(1,1.35-0.35*(1-pow(1-min(1,max(0,(on/{fps}+{c0:.4f})/{d:.4f})),3)))':"
                   f"x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={W}x{H}:fps={fps},format=rgba,")
        return (f"{pre}split[{tag}a][{tag}b];[{tag}b]{soft},format=rgba[{tag}c];"
                f"[{tag}a][{tag}c]blend=all_expr='A*{U}+B*(1-{U})'")
    if kind == "zoom":
        return (f"zoompan=z='max(1,1.35-0.35*(1-pow(1-min(1,max(0,(on/{fps}+{c0:.4f})/{d:.4f})),3)))':"
                f"x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={W}x{H}:fps={fps},format=rgba")
    if kind == "glitch":
        return f"rgbashift=rh=12:bh=-12:{en}"
    if kind in ("slide", "slide-r", "whip"):   # slide/whip: sagdan gelir; slide-r: soldan
        x = f"iw/2*(1-{e})" if kind == "slide-r" else f"iw/2*{e}"
        pad = "0:0" if kind == "slide-r" else "iw:0"
        out = f"pad=iw*2:ih:{pad}:color=black@0,crop={W}:{H}:x='{x}':y=0"
        return out + (f",gblur=sigma=36:sigmaV=0.5:{en}" if kind == "whip" else "")
    if kind in ("slide-u", "slide-d"):
        y = f"ih/2*{e}" if kind == "slide-u" else f"ih/2*(1-{e})"
        pad = "0:ih" if kind == "slide-u" else "0:0"
        return f"pad=iw:ih*2:{pad}:color=black@0,crop={W}:{H}:x=0:y='{y}'"
    if kind == "spin":
        return f"rotate=a='-(1-{e})*PI/2':c=black@0:{en}"
    if kind == "shake-in":             # sonradan kalici zoom olmasin diye yalniz gecis suresince bindirilir
        k = f"max(0,1-({e}))"
        return (f"split[{tag}a][{tag}b];[{tag}b]crop=iw-48:ih-48:x='24+24*sin(t*73)*{k}':y='24+24*cos(t*61)*{k}',"
                f"scale={W}:{H},format=rgba[{tag}c];[{tag}a][{tag}c]overlay={en}")
    masks = {
        "wipe-r": f"lt(X,W*{E})", "wipe-l": f"gt(X,W*(1-{E}))", "wipe-d": f"lt(Y,H*{E})", "wipe-u": f"gt(Y,H*(1-{E}))",
        "iris": f"lt(hypot(X-W/2,Y-H/2),{E}*hypot(W,H)/2)",
        "barn-v": f"lt(abs(X-W/2),{E}*W/2)", "barn-h": f"lt(abs(Y-H/2),{E}*H/2)",
        "eye": f"lt(abs(Y-H/2),{E}*H*1.2*sqrt(max(0,1-pow((X-W/2)/(W*0.62),2))))",
        "clock": f"lt(mod(atan2(X-W/2,H/2-Y)+2*PI,2*PI),{E}*2*PI)",
    }
    if kind in masks:
        return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if({masks[kind]},alpha(X,Y),0)':{en}"
    if kind in TRANS_PRO:
        return trans_in_pro(kind, d, W, H, tag, c0, fps)
    return trans_in2(kind, d, W, H, tag, c0, fps)


AUDIO_FIX = {
    "nr1": "afftdn=nr=12:nf=-42:tn=1",
    "nr2": "afftdn=nr=24:nf=-36:tn=1,afftdn=nr=10:nf=-40",
    "voice": "highpass=f=80,lowpass=f=15000,equalizer=f=250:t=q:w=1:g=-2.5,equalizer=f=3200:t=q:w=1.2:g=3,"
             "deesser=i=0.35,acompressor=threshold=-21dB:ratio=3:attack=8:release=160:makeup=4",
    "gate": "agate=threshold=0.015:ratio=3:attack=5:release=180",
    "bass": "bass=g=4:f=110",
    "radio": "highpass=f=400,lowpass=f=3200,acompressor=threshold=-18dB:ratio=6",
    "phone": "highpass=f=500,lowpass=f=2800,aformat=sample_rates=8000,aresample=48000",
    "cave": "aecho=0.8:0.85:60|120:0.35|0.25",
    "hot-montage": "acompressor=threshold=-14dB:ratio=4:attack=3:release=80:makeup=5,alimiter=limit=0.95",
    "meme-earrape": "bass=g=11:f=85,acompressor=threshold=-12dB:ratio=8:makeup=8,asoftclip=type=tanh,alimiter=limit=0.98",
    "muffle": "lowpass=f=650,volume=0.55",
    **AUDIO_FIX_PRO,
}


def _audio_chain(ii: int, c: dict, cut0: float, seg: float, off: float, speed: float, ramp: list | None = None) -> str:
    vol = float(c.get("vol", 1) if c.get("vol") is not None else 1)
    if ramp:   # hiz rampasi: dilim dilim atempo + birlestir
        segs = _ramp_window(ramp, cut0, seg)
        base = segs[0][2]
        n = len(segs)
        parts = [f"[{ii}:a]asetpts=PTS-STARTPTS,asplit={n}" + "".join(f"[r{ii}_{j}]" for j in range(n))]
        for j, (_t0, _t1, a0, a1, sp) in enumerate(segs):
            parts.append(f"[r{ii}_{j}]atrim={a0 - base:.4f}:{a1 - base:.4f},asetpts=PTS-STARTPTS,{_atempo(sp)}[q{ii}_{j}]")
        parts.append("".join(f"[q{ii}_{j}]" for j in range(n)) + f"concat=n={n}:v=0:a=1[rr{ii}]")
        head = ";".join(parts) + f";[rr{ii}]"
        ch = ["anull"]
    else:
        head = f"[{ii}:a]"
        ch = ["asetpts=PTS-STARTPTS"]
        if abs(speed - 1) > 1e-3:
            ch.append(_atempo(speed))
    ch.append(f"atrim=0:{seg:.3f}")
    for fx in (c.get("afx") or []):
        if fx in AUDIO_FIX:
            ch.append(AUDIO_FIX[fx])
    ch.extend(studio_fx_adv.eq_filters(c.get("eq")))
    ukf_a = kf_resolve(c.get("kf") or [], float(c.get("dur", 0) or 0))
    if any("vol" in q for q in ukf_a):
        v_ex = studio_fx_adv.kf_expr_adv(ukf_a, "vol", f"(t+{cut0:.4f})", vol)
        ch.append(f"volume='{v_ex}':eval=frame")
    elif abs(vol - 1) > 1e-3:
        ch.append(f"volume={vol:.3f}")
    fi, fo = float(c.get("fadeIn", 0) or 0), float(c.get("fadeOut", 0) or 0)
    fcurve = c.get("fadeCurve", "tri")
    c_opt = f":curve={fcurve}" if fcurve in studio_fx_adv.AUDIO_CURVES and fcurve != "tri" else ""
    d = float(c["dur"])
    if fi > cut0:
        ch.append(f"afade=t=in:st=0:d={fi - cut0:.3f}{c_opt}")
    if fo > 0:
        ch.append(f"afade=t=out:st={max(0, d - cut0 - fo):.3f}:d={fo:.3f}{c_opt}")
    ch.append("aresample=48000,aformat=channel_layouts=stereo")
    pf = studio_fx_adv.pan_filter(c.get("pan"))
    if pf:
        ch.append(pf)
    ms = int(round(off * 1000))
    if ms > 0:
        ch.append(f"adelay={ms}|{ms}")
    return head + ",".join(ch)


# ---------------------------------------------------------------------------------------------------------------
# ASS
def _ts(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _col(hexc: str, alpha: float = 0.0) -> str:
    """#RRGGBB -> &HAABBGGRR (ASS)."""
    h = (hexc or "#ffffff").lstrip("#")
    if len(h) == 3:
        h = "".join(x * 2 for x in h)
    h = (h + "ffffff")[:6]
    a = max(0, min(255, int(alpha * 255)))
    return f"&H{a:02X}{h[4:6]}{h[2:4]}{h[0:2]}&".upper().replace("&H", "&H", 1)


def tr_upper(s: str) -> str:
    """Turkce buyuk harf: i -> İ, ı -> I (str.upper i'yi I yapar)."""
    return s.replace("i", "İ").replace("ı", "I").upper()


_GLYPH: dict[tuple[str, str], bool] = {}
_FB_FONTS = ("Chakra Petch", "Arial", "Segoe UI")


def _has_glyph(family: str, ch: str) -> bool | None:
    """Fontta karakter var mi (Pillow: eksik karakter .notdef kutusunu cizer). Font bulunamazsa None."""
    key = (family.lower(), ch)
    if key in _GLYPH:
        return _GLYPH[key]
    try:
        idx = {k.lower(): v for k, v in fonts_index().items()}
        path = idx.get(family.lower())
        if not path:
            _GLYPH[key] = None   # type: ignore[assignment]
            return None
        from PIL import ImageFont
        f = ImageFont.truetype(path, 48, layout_engine=ImageFont.Layout.BASIC)   # raqm harfi parcalayip (I + nokta) var sanmasin
        def sig(c: str):
            m = f.getmask(c)
            return m.size, bytes(m)
        nd = _GLYPH.get((family.lower(), "\0nd"))
        if nd is None:
            nd = sig("\U0010FFFD")
            _GLYPH[(family.lower(), "\0nd")] = nd   # type: ignore[assignment]
        ok = sig(ch) != nd
    except Exception:
        ok = None
    _GLYPH[key] = ok   # type: ignore[assignment]
    return ok


def _glyph_fallback(line: str) -> str:
    """Secili fontta olmayan harfleri (orn. İ, ş) yedek fonta gecirir: hem onizleme (JASSUB) hem disa aktarim ayni ASS'i kullanir."""
    if not line.startswith("Dialogue:"):
        return line
    parts = line.split(",", 9)
    if len(parts) < 10 or not any(ord(ch) > 127 for ch in parts[9]):
        return line
    cur, out = "Chakra Petch", []
    for tok in re.split(r"(\{[^}]*\})", parts[9]):
        if tok.startswith("{"):
            m = re.findall(r"\\fn([^\\}]+)", tok)
            if m:
                cur = m[-1]
            out.append(tok)
            continue
        i = 0
        while i < len(tok):
            ch = tok[i]
            if ch == "\\" and i + 1 < len(tok):
                out.append(tok[i:i + 2])
                i += 2
                continue
            if ord(ch) > 127 and _has_glyph(cur, ch) is False:
                fb = next((f for f in _FB_FONTS if f.lower() != cur.lower() and _has_glyph(f, ch)), None)
                if fb:
                    out.append(f"{{\\fn{fb}}}{ch}{{\\fn{cur}}}")
                    i += 1
                    continue
            out.append(ch)
            i += 1
    parts[9] = "".join(out)
    return ",".join(parts)


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def build_ass(project: dict, t0: float = 0.0) -> str:
    W, H = int(project.get("w", 1920)), int(project.get("h", 1080))
    tracks = {t["id"]: t for t in project.get("tracks", [])}
    head = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n"
            "YCbCr Matrix: TV.709\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
            "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: Default,Chakra Petch,{int(H * 0.06)},&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{max(2, H // 270)},0,2,40,40,{int(H * 0.08)},1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    ev: list[str] = []
    clips = sorted(flatten_clips(project.get("clips", [])), key=lambda c: c["start"])
    for c in clips:
        tr = tracks.get(c.get("track"), {})
        if tr.get("hide"):
            continue
        s, e = float(c["start"]) - t0, float(c["start"]) + float(c["dur"]) - t0
        if e <= 0:
            continue
        if tr.get("kind") == "text":
            if c.get("subscribe") in studio_gfx.SUBSCRIBE_PRO:
                ev += studio_gfx.subscribe(c["subscribe"], _ts, _col, _esc, _rrect, s, e, W, H, c.get("style") or {})
            elif c.get("subscribe"):
                ev += _subscribe(c["subscribe"], s, e, W, H, c.get("style") or {})
            elif c.get("graphic"):
                ev += studio_gfx.graphic(c["graphic"], _ts, _col, _esc, _rrect, s, e, W, H, c.get("style") or {})
            elif c.get("words"):
                ev += _captions(c, s, e, W, H)
            elif c.get("text"):
                ev += _text(c, s, e, W, H)
        elif tr.get("kind") == "fx":
            kind = FX.get(c.get("mode", ""), {}).get("ass")
            if kind:
                ev += _fx_text(kind, s, e, W, H, c)
    for c in clips:   # klip ustu mod yazilari (VHS tarih vb.)
        tr = tracks.get(c.get("track"), {})
        if tr.get("kind") == "video" and not tr.get("hide"):
            for fid in c.get("fx") or []:
                kind = FX.get(fid, {}).get("ass")
                if kind:
                    ev += _fx_text(kind, float(c["start"]) - t0, float(c["start"]) + float(c["dur"]) - t0, W, H, c)
    ev = [_glyph_fallback(x) for x in ev]
    return head + "\n".join(ev) + ("\n" if ev else "")


def _pos(st: dict, W: int, H: int) -> tuple[int, float, float]:
    """(an, x, y): x/y orani 0-1 (merkez); pos hazir konumlari."""
    p = st.get("pos", "custom" if "x" in st else "bottom")
    if p == "top":
        return 8, W / 2, H * 0.1
    if p == "center":
        return 5, W / 2, H / 2
    if p == "bottom":
        return 2, W / 2, H * 0.88
    return 5, W * float(st.get("x", 0.5)), H * float(st.get("y", 0.5))


def _style_tags(st: dict, H: int) -> str:
    size = float(st.get("size", 7)) * H / 100      # boyut: ekran yuksekliginin yuzdesi
    font = st.get("font", "Chakra Petch")
    col = _col(st.get("color", "#FFFFFF"))
    oc = _col(st.get("outlineColor", "#000000"))
    bord = float(st.get("outline", 6)) * H / 1080
    shad = float(st.get("shadow", 0)) * H / 1080
    tags = f"\\fn{font}\\fs{size:.0f}\\1c{col}\\3c{oc}\\bord{bord:.1f}\\shad{shad:.1f}\\b{1 if st.get('bold', True) else 0}"
    if st.get("italic"):
        tags += "\\i1"
    if st.get("glow"):
        tags += f"\\blur{max(2, bord):.0f}"
    if st.get("spacing"):
        tags += f"\\fsp{float(st['spacing']):.0f}"
    if st.get("rot"):
        tags += f"\\frz{float(st['rot']):.1f}"
    if st.get("shadowColor"):
        tags += f"\\4c{_col(st['shadowColor'])}"
    if st.get("box"):
        tags += f"\\3c{_col(st.get('boxColor', '#000000'))}\\bord{size * 0.25:.0f}"
    return tags


def _anim(anim: str, dur_ms: int, x: float, y: float) -> str:
    if anim == "pop":
        return "\\fscx40\\fscy40\\t(0,110,\\fscx115\\fscy115)\\t(110,190,\\fscx100\\fscy100)"
    if anim == "fade":
        return "\\fad(250,250)"
    if anim == "slide":
        return f"\\move({x:.0f},{y + 80:.0f},{x:.0f},{y:.0f},0,260)\\fad(150,150)"
    if anim == "bounce":
        return f"\\move({x:.0f},{y - 140:.0f},{x:.0f},{y:.0f},0,220)\\t(220,300,\\fscy85\\fscx110)\\t(300,380,\\fscy100\\fscx100)"
    if anim == "zoom":
        return f"\\fscx60\\fscy60\\t(0,{min(dur_ms, 600)},\\fscx100\\fscy100)\\fad(120,150)"
    if anim == "shake":
        seq = "".join(f"\\t({i * 60},{i * 60 + 60},\\frz{(-4 if i % 2 else 4)})" for i in range(min(40, dur_ms // 60)))
        return seq
    if anim == "glitch":
        return "".join(f"\\t({i * 90},{i * 90 + 45},\\fax{0.3 if i % 2 else -0.3}\\fscx{110 if i % 3 == 0 else 100})" for i in range(min(30, dur_ms // 90)))
    return ""


def _text(c: dict, s: float, e: float, W: int, H: int) -> list[str]:
    st = c.get("style") or {}
    an, x, y = _pos(st, W, H)
    anim = st.get("anim", "pop")
    dur_ms = int((e - s) * 1000)
    base = f"\\an{an}\\pos({x:.0f},{y:.0f})" + _style_tags(st, H)
    out = []
    text = str(c.get("text", ""))
    if any(k in st for k in ("animIn", "animOut", "animLoop")):   # yeni: giris / cikis / dongu
        from app.core.studio_anim import text_events
        if st.get("glow"):
            gc = _col(st.get("glowColor", st.get("color", "#FFFFFF")))
            out += text_events(text, st, s, e, x, y, W, H, base.replace(f"\\pos({x:.0f},{y:.0f})", ""), _esc, _ts, 4,
                               f"\\3c{gc}\\1c{gc}\\blur{int(H / 60)}\\bord{int(H / 90)}")
        out += text_events(text, st, s, e, x, y, W, H, base.replace(f"\\pos({x:.0f},{y:.0f})", ""), _esc, _ts, 5)
        return out
    if anim == "type":
        n = max(1, len(text))
        per = min(80, max(25, int(min(dur_ms * 0.6, 1600) / n)))
        body = "".join(f"{{\\alpha&HFF&\\t({i * per},{i * per + 1},\\alpha&H00&)}}{_esc(ch)}" for i, ch in enumerate(text))
        out.append(f"Dialogue: 5,{_ts(s)},{_ts(e)},Default,,0,0,0,,{{{base}}}{body}")
        return out
    a = _anim(anim, dur_ms, x, y)
    if "\\move" in a:
        base = base.replace(f"\\pos({x:.0f},{y:.0f})", "")
    if st.get("glow"):   # parlama: arkada bulanik renkli kopya
        gc = _col(st.get("glowColor", st.get("color", "#FFFFFF")))
        out.append(f"Dialogue: 4,{_ts(s)},{_ts(e)},Default,,0,0,0,,{{{base}{a}\\3c{gc}\\1c{gc}\\blur{int(H / 60)}\\bord{int(H / 90)}}}{_esc(text)}")
    out.append(f"Dialogue: 5,{_ts(s)},{_ts(e)},Default,,0,0,0,,{{{base}{a}}}{_esc(text)}")
    return out


def _captions(c: dict, s: float, e: float, W: int, H: int) -> list[str]:
    """Kelime zamanli altyazi (Whisper). words: [{w, s, e}] klip basina gore sn."""
    st = c.get("style") or {}
    mode = st.get("caption", "hormozi")
    if mode in CAPTIONS2:   # on ayar: varsayilan stil + mevcut bir davranis; kullanicinin ayarlari ustte
        st = {**CAPTIONS2[mode]["st"], **{k: v for k, v in st.items() if k != "caption"}}
        mode = CAPTIONS2[mode]["b"]
    words = [w for w in c.get("words") or [] if str(w.get("w", "")).strip()]
    an, x, y = _pos({**st, "pos": st.get("pos", "custom"), "y": st.get("y", 0.72)}, W, H)
    per_line = int(st.get("perLine", {"word": 1, "mrbeast": 2, "reveal": 4, "cinema": 6}.get(mode, 3)))
    hi = _col(st.get("highlight", {"highlight": "#7C3AED", "hollow": "#FFE600"}.get(mode, "#FFE600")))
    size = {"word": 10, "mrbeast": 9, "cinema": 5.2}.get(mode, 7.5)
    base = f"\\an{an}\\pos({x:.0f},{y:.0f})" + _style_tags({"size": size, "outline": 7, "font": "Chakra Petch", **st}, H)
    # faz 5 stilleri: temel etiketlere ek (kullanici stili _style_tags ile yine gecerli)
    thin = f"\\bord{H / 300:.1f}"
    base += {"mrbeast": f"\\bord{H / 80:.0f}\\shad{H / 150:.0f}", "highlight": thin + "\\shad0", "hollow": f"\\1a&HFF&\\3c&HFFFFFF&\\bord{H / 380:.1f}\\shad0",
             "cinema": f"\\bord0\\shad{H / 500:.1f}\\fsp{H / 400:.1f}" + ("" if st.get("font") else "\\fnGeorgia")}.get(mode, "")
    up = st.get("upper", mode in ("hormozi", "word", "mrbeast"))
    palette = [_col(c) for c in ("#FFE600", "#2EE66B", "#FF3B5C")]
    out = []
    i = 0
    while i < len(words):
        grp = words[i:i + per_line]
        i += per_line
        g0 = s + float(grp[0]["s"])
        g1 = s + float(grp[-1]["e"])
        if i < len(words):
            g1 = max(g1, min(s + float(words[i]["s"]), g1 + 0.4))
        g0, g1 = max(s, g0), min(e, g1)
        if g1 <= g0:
            continue
        txt = [(tr_upper(str(w["w"]).strip()) if up else str(w["w"]).strip()) for w in grp]
        if mode == "karaoke":
            body = "".join(f"{{\\kf{max(1, int((float(w['e']) - float(w['s'])) * 100))}}}{_esc(t)} " for w, t in zip(grp, txt))
            out.append(f"Dialogue: 5,{_ts(g0)},{_ts(g1)},Default,,0,0,0,,{{{base}\\2c{_col(st.get('color', '#FFFFFF'))}\\1c{hi}\\fad(80,80)}}{body.strip()}")
            continue
        if mode == "cinema":
            out.append(f"Dialogue: 5,{_ts(g0)},{_ts(g1)},Default,,0,0,0,,{{{base}\\fad(140,140)}}{_esc(' '.join(txt))}")
            continue
        if mode in ("plain", "boxed", "neon"):
            extra = ""
            if mode == "boxed":
                extra = f"\\3c{_col(st.get('boxColor', '#000000'))}\\bord{H / 70:.0f}\\shad0"
                out.append(f"Dialogue: 4,{_ts(g0)},{_ts(g1)},Default,,0,0,0,,{{{base}{extra}\\fad(60,60)\\4a&HFF&}}{_esc(' '.join(txt))}")
                continue
            if mode == "neon":
                gc = _col(st.get("glowColor", "#2EE6A6"))
                out.append(f"Dialogue: 4,{_ts(g0)},{_ts(g1)},Default,,0,0,0,,{{{base}\\1c{gc}\\3c{gc}\\blur{H / 50:.0f}\\bord{H / 120:.0f}}}{_esc(' '.join(txt))}")
            out.append(f"Dialogue: 5,{_ts(g0)},{_ts(g1)},Default,,0,0,0,,{{{base}\\fad(60,60)}}{_esc(' '.join(txt))}")
            continue
        # hormozi / word: o anda konusulan kelime vurgulu + pop
        for j, w in enumerate(grp):
            w0 = max(g0, s + float(w["s"]))
            w1 = min(g1, s + float(grp[j + 1]["s"])) if j + 1 < len(grp) else g1
            if w1 <= w0:
                continue
            parts = []
            fg = _col(st.get("color", "#FFFFFF"))
            for q, t in enumerate(txt):
                if mode == "reveal":       # konusulan kelimeye kadar gorunur, sonrasi saydam (satir yerlesimi sabit kalir)
                    parts.append(_esc(t) if q <= j else (("{\\alpha&HFF&}" if q == j + 1 else "") + _esc(t)))
                elif q != j:
                    parts.append(_esc(t))
                elif mode == "mrbeast":
                    col = palette[(i - per_line + j) % len(palette)]
                    parts.append(f"{{\\1c{col}\\fscx125\\fscy125}}{_esc(t)}{{\\1c{fg}\\fscx100\\fscy100}}")
                elif mode == "highlight":  # konusulan kelimenin arkasinda renkli kalin kontur (hap gibi)
                    parts.append(f"{{\\3c{hi}\\bord{H / 42:.0f}}}{_esc(t)}{{\\3c&H000000&{thin}}}")
                elif mode == "hollow":     # hepsi bos harf, konusulan dolu
                    parts.append(f"{{\\1a&H00&\\1c{hi}}}{_esc(t)}{{\\1a&HFF&}}")
                else:
                    parts.append(f"{{\\1c{hi}\\fscx112\\fscy112}}{_esc(t)}{{\\1c{fg}\\fscx100\\fscy100}}")
            pop = ("\\fscx70\\fscy70\\t(0,90,\\fscx105\\fscy105)\\t(90,150,\\fscx100\\fscy100)"
                   if (j == 0 and mode != "reveal") or mode in ("word", "mrbeast") else "")
            out.append(f"Dialogue: 5,{_ts(w0)},{_ts(w1)},Default,,0,0,0,,{{{base}{pop}}}{' '.join(parts)}")
    return out


def _rrect(w: float, h: float, r: float) -> str:
    r = min(r, h / 2, w / 2)
    return (f"m {r:.0f} 0 l {w - r:.0f} 0 b {w:.0f} 0 {w:.0f} 0 {w:.0f} {r:.0f} l {w:.0f} {h - r:.0f} b {w:.0f} {h:.0f} {w:.0f} {h:.0f} {w - r:.0f} {h:.0f} "
            f"l {r:.0f} {h:.0f} b 0 {h:.0f} 0 {h:.0f} 0 {h - r:.0f} l 0 {r:.0f} b 0 0 0 0 {r:.0f} 0")


CURSOR = "m 0 0 l 0 34 l 9 26 l 15 40 l 21 37 l 15 24 l 27 24"
BELL = ("m 20 0 b 23 0 24 2 24 4 b 33 6 37 13 37 22 l 37 34 l 42 40 l 42 43 l -2 43 l -2 40 l 3 34 l 3 22 b 3 13 7 6 16 4 b 16 2 17 0 20 0 "
        "m 14 46 l 26 46 b 26 50 23 53 20 53 b 17 53 14 50 14 46")
THUMB = "m 0 18 l 8 18 l 8 44 l 0 44 m 11 18 l 20 0 b 26 0 27 5 26 10 l 24 16 l 40 16 b 45 16 46 21 44 24 l 38 42 b 37 44 35 45 33 45 l 11 45"


def _subscribe(kind: str, s: float, e: float, W: int, H: int, st: dict) -> list[str]:
    """Abone ol animasyonlari (vektor, ASS cizimi). Konum: style.x/y (merkez, 0-1); boyut style.size (yukseklik %)."""
    k = H / 1080 * float(st.get("size", 100)) / 100
    cx, cy = W * float(st.get("x", 0.5)), H * float(st.get("y", 0.8))
    bw, bh = 420 * k, 110 * k
    x0, y0 = cx - bw / 2, cy - bh / 2
    label = _esc(st.get("label", "ABONE OL"))
    done = _esc(st.get("done", "ABONE OLUNDU"))
    red, grey = _col(st.get("color", "#FF1F1F")), _col("#3A3A3A")
    font = st.get("font", "Chakra Petch")
    out: list[str] = []
    T = lambda a, b: f"{_ts(s + a)},{_ts(min(e, s + b))}"  # noqa: E731
    dur = e - s
    click = min(1.4, dur * 0.45)
    fs = 58 * k
    if kind in ("classic", "bounce", "glitch", "like", "bell"):
        enter = ("\\fscx20\\fscy20\\t(0,180,\\fscx110\\fscy110)\\t(180,260,\\fscx100\\fscy100)" if kind != "bounce"
                 else f"\\move({cx:.0f},{cy + 300 * k:.0f},{cx:.0f},{cy:.0f},0,260)\\t(260,340,\\fscy80\\fscx115)\\t(340,420,\\fscy100\\fscx100)")
        if kind == "glitch":
            enter += "".join(f"\\t({i * 70},{i * 70 + 35},\\fax{0.4 if i % 2 else -0.4})" for i in range(8)) + "\\t(560,561,\\fax0)"
        pos = "" if "\\move" in enter else f"\\pos({cx:.0f},{cy:.0f})"
        shape = _rrect(bw, bh, 18 * k)
        # buton (kirmizi -> gri)
        out.append(f"Dialogue: 6,{T(0, dur)},Default,,0,0,0,,{{\\an5{pos}{enter}\\p1\\bord0\\shad{4 * k:.0f}\\4c&H80000000&\\1c{red}"
                   f"\\t({int(click * 1000)},{int(click * 1000) + 120},\\1c{grey})\\fad(0,200)}}{shape}{{\\p0}}")
        out.append(f"Dialogue: 7,{T(0, click + 0.06)},Default,,0,0,0,,{{\\an5{pos}{enter}\\fn{font}\\fs{fs:.0f}\\b1\\bord0\\shad0\\1c&H00FFFFFF&}}{label}")
        out.append(f"Dialogue: 7,{T(click + 0.06, dur)},Default,,0,0,0,,{{\\an5\\pos({cx:.0f},{cy:.0f})\\fn{font}\\fs{fs * 0.82:.0f}\\b1\\bord0\\shad0"
                   f"\\1c&H00DDDDDD&\\fscx80\\fscy80\\t(0,120,\\fscx100\\fscy100)\\fad(0,200)}}{done}")
        # imlec: sagdan gelir, tiklar
        cxe, cye = x0 + bw * 0.72, y0 + bh * 0.62
        out.append(f"Dialogue: 8,{T(0.25, dur)},Default,,0,0,0,,{{\\an7\\move({cxe + 320 * k:.0f},{cye + 200 * k:.0f},{cxe:.0f},{cye:.0f},0,{int((click - 0.25) * 1000 - 80)})"
                   f"\\p1\\fscx{140 * k:.0f}\\fscy{140 * k:.0f}\\1c&H00FFFFFF&\\3c&H00000000&\\bord{3 * k:.1f}\\shad0"
                   f"\\t({int((click - 0.25) * 1000)},{int((click - 0.25) * 1000) + 90},\\fscx{115 * k:.0f}\\fscy{115 * k:.0f})"
                   f"\\t({int((click - 0.25) * 1000) + 90},{int((click - 0.25) * 1000) + 180},\\fscx{140 * k:.0f}\\fscy{140 * k:.0f})\\fad(0,200)}}{CURSOR}")
        # tik halkasi
        out.append(f"Dialogue: 7,{T(click, click + 0.35)},Default,,0,0,0,,{{\\an5\\pos({cxe:.0f},{cye:.0f})\\p1\\1a&HFF&\\3c&H00FFFFFF&\\bord{4 * k:.0f}"
                   f"\\fscx30\\fscy30\\t(0,350,\\fscx160\\fscy160\\3a&HFF&)}}m -20 0 b -20 -27 20 -27 20 0 b 20 27 -20 27 -20 0")
        if kind in ("bell", "classic"):
            bx = x0 + bw + 70 * k
            ring = "".join(f"\\t({int((click + 0.3 + i * 0.08) * 1000)},{int((click + 0.3 + i * 0.08) * 1000) + 80},\\frz{18 if i % 2 else -18})" for i in range(6))
            out.append(f"Dialogue: 6,{T(click + 0.2, dur)},Default,,0,0,0,,{{\\an5\\pos({bx:.0f},{cy:.0f})\\p1\\fscx{150 * k:.0f}\\fscy{150 * k:.0f}"
                       f"\\1c&H00FFFFFF&\\bord0\\shad{3 * k:.0f}\\org({bx:.0f},{cy - 40 * k:.0f})\\fscx10\\fscy10\\t(0,150,\\fscx{150 * k:.0f}\\fscy{150 * k:.0f}){ring}\\fad(0,200)}}{BELL}")
        if kind == "like":
            lx = x0 - 90 * k
            out.append(f"Dialogue: 6,{T(0.1, dur)},Default,,0,0,0,,{{\\an5\\pos({lx:.0f},{cy:.0f})\\p1\\fscx{150 * k:.0f}\\fscy{150 * k:.0f}\\1c&H00FFFFFF&\\bord0"
                       f"\\t({int(click * 500)},{int(click * 500) + 150},\\1c&H00FF8A2B&\\fscx{185 * k:.0f}\\fscy{185 * k:.0f})"
                       f"\\t({int(click * 500) + 150},{int(click * 500) + 260},\\fscx{150 * k:.0f}\\fscy{150 * k:.0f})\\fad(0,200)}}{THUMB}")
    elif kind == "neon":
        gc = _col(st.get("color", "#FF2E88"))
        shape = _rrect(bw, bh, bh / 2)
        flick = "".join(f"\\t({i * 60},{i * 60 + 30},\\alpha&H{('A0' if i % 2 else '00')}&)" for i in range(7)) + "\\t(420,421,\\alpha&H00&)"
        out.append(f"Dialogue: 5,{T(0, dur)},Default,,0,0,0,,{{\\an5\\pos({cx:.0f},{cy:.0f})\\p1\\1a&HFF&\\3c{gc}\\bord{6 * k:.0f}\\blur{14 * k:.0f}{flick}\\fad(0,250)}}{shape}")
        out.append(f"Dialogue: 6,{T(0, dur)},Default,,0,0,0,,{{\\an5\\pos({cx:.0f},{cy:.0f})\\p1\\1a&HFF&\\3c&H00FFFFFF&\\bord{2.5 * k:.1f}{flick}\\fad(0,250)}}{shape}")
        out.append(f"Dialogue: 7,{T(0, dur)},Default,,0,0,0,,{{\\an5\\pos({cx:.0f},{cy:.0f})\\fn{font}\\fs{fs:.0f}\\b1\\1c&H00FFFFFF&\\3c{gc}\\bord{3 * k:.0f}\\blur{6 * k:.0f}{flick}\\fad(0,250)}}{label}")
    elif kind == "pill":
        shape = _rrect(bw * 0.8, bh * 0.62, bh * 0.31)
        out.append(f"Dialogue: 6,{T(0, dur)},Default,,0,0,0,,{{\\an5\\move({cx:.0f},{cy + 80 * k:.0f},{cx:.0f},{cy:.0f},0,300)\\p1\\1c{red}\\bord0\\shad0\\fad(250,250)}}{shape}")
        out.append(f"Dialogue: 7,{T(0, dur)},Default,,0,0,0,,{{\\an5\\move({cx:.0f},{cy + 80 * k:.0f},{cx:.0f},{cy:.0f},0,300)\\fn{font}\\fs{fs * 0.62:.0f}\\b1\\bord0\\shad0\\fsp{4 * k:.0f}\\fad(250,250)}}{label}")
    elif kind == "corner":
        px, py = W - 40 * k, H - 60 * k
        cw, chh = 520 * k, 120 * k
        out.append(f"Dialogue: 6,{T(0, dur)},Default,,0,0,0,,{{\\an3\\move({px + cw:.0f},{py:.0f},{px:.0f},{py:.0f},0,350)\\p1\\1c&H00241A14&\\3c{red}\\bord{3 * k:.0f}\\shad{6 * k:.0f}\\fad(0,300)}}{_rrect(cw, chh, 16 * k)}")
        out.append(f"Dialogue: 7,{T(0, dur)},Default,,0,0,0,,{{\\an6\\move({px - 30 * k + cw:.0f},{py - chh / 2:.0f},{px - 30 * k:.0f},{py - chh / 2:.0f},0,350)\\fn{font}\\fs{fs * 0.62:.0f}\\b1\\bord0\\shad0\\fad(0,300)}}"
                   f"{label}  {{\\1c{red}}}►")
    return out


def _fx_text(kind: str, s: float, e: float, W: int, H: int, c: dict) -> list[str]:
    """Mod ust yazilari: VHS (PLAY + tarih), REC, CCTV kamera adi + saat, body-cam."""
    fs = H * 0.045
    mono = "Consolas"
    out = []
    date = c.get("date") or time.strftime("%d.%m.%Y")
    if kind == "vhs":
        out.append(f"Dialogue: 9,{_ts(s)},{_ts(e)},Default,,0,0,0,,{{\\an7\\pos({W * 0.05:.0f},{H * 0.06:.0f})\\fn{mono}\\fs{fs:.0f}\\bord{H / 400:.1f}\\shad{H / 300:.1f}\\4c&H80FF00FF&\\blur1}}PLAY ►")
        out.append(f"Dialogue: 9,{_ts(s)},{_ts(e)},Default,,0,0,0,,{{\\an1\\pos({W * 0.05:.0f},{H * 0.94:.0f})\\fn{mono}\\fs{fs:.0f}\\bord{H / 400:.1f}\\shad{H / 300:.1f}\\4c&H80FF00FF&\\blur1}}"
                   f"{date}   AM 03:13")
    elif kind == "rec":
        blink = "".join(f"\\t({i * 1000},{i * 1000 + 1},\\alpha&HFF&)\\t({i * 1000 + 500},{i * 1000 + 501},\\alpha&H00&)" for i in range(int(e - s) + 1)) if e - s < 60 else ""
        out.append(f"Dialogue: 9,{_ts(s)},{_ts(e)},Default,,0,0,0,,{{\\an7\\pos({W * 0.05:.0f},{H * 0.06:.0f})\\p1\\1c&H000000FF&\\bord0\\shad0{blink}}}m 0 {fs * 0.5:.0f} b 0 0 {fs * 0.6:.0f} 0 {fs * 0.6:.0f} {fs * 0.5:.0f} b {fs * 0.6:.0f} {fs:.0f} 0 {fs:.0f} 0 {fs * 0.5:.0f}")
        out.append(f"Dialogue: 9,{_ts(s)},{_ts(e)},Default,,0,0,0,,{{\\an7\\pos({W * 0.05 + fs * 0.9:.0f},{H * 0.058:.0f})\\fn{mono}\\fs{fs:.0f}\\bord{H / 500:.1f}\\shad0}}REC")
    elif kind == "cctv":
        out.append(f"Dialogue: 9,{_ts(s)},{_ts(e)},Default,,0,0,0,,{{\\an7\\pos({W * 0.04:.0f},{H * 0.05:.0f})\\fn{mono}\\fs{fs * 0.85:.0f}\\bord{H / 500:.1f}\\shad0}}"
                   f"{_esc(c.get('cam', 'CAM 03'))}")
        out.append(f"Dialogue: 9,{_ts(s)},{_ts(e)},Default,,0,0,0,,{{\\an9\\pos({W * 0.96:.0f},{H * 0.05:.0f})\\fn{mono}\\fs{fs * 0.85:.0f}\\bord{H / 500:.1f}\\shad0}}{date} 02:47:13")
    elif kind == "bodycam":
        out.append(f"Dialogue: 9,{_ts(s)},{_ts(e)},Default,,0,0,0,,{{\\an9\\pos({W * 0.96:.0f},{H * 0.05:.0f})\\fn{mono}\\fs{fs * 0.75:.0f}\\bord{H / 500:.1f}\\shad0}}"
                   f"AXON BODY 3  X{(abs(hash(str(c.get('id')))) % 90000 + 10000)}\\N{date} T23:41:07Z")
    return out


# ---------------------------------------------------------------------------------------------------------------
# Duzenleme islemleri (MCP sunucusu kullanir; arayuzde studio.js'te aynilari var)
def _nid(project: dict, prefix: str = "c") -> str:
    ids = {c["id"] for c in project.get("clips", [])}
    i = len(ids) + 1
    while f"{prefix}{i}" in ids:
        i += 1
    return f"{prefix}{i}"


def find_clip(project: dict, cid: str) -> dict:
    for c in project.get("clips", []):
        if c["id"] == cid:
            return c
    raise KeyError(f"klip yok: {cid}")


def add_asset(project: dict, info: dict) -> str:
    for k, a in project["assets"].items():
        if a.get("path") == info["path"]:
            return k
    aid = "a" + str(len(project["assets"]) + 1)
    while aid in project["assets"]:
        aid += "x"
    project["assets"][aid] = {k: info[k] for k in ("path", "kind", "dur", "w", "h", "audio", "name", "gif") if k in info}
    return aid


def track_for(project: dict, kind: str) -> str:
    want = "video" if kind in ("video", "image") else kind
    for t in reversed(project["tracks"]) if want == "video" else project["tracks"]:
        if t["kind"] == want:
            return t["id"]
    tid = want[0] + str(len(project["tracks"]) + 1)
    project["tracks"].append({"id": tid, "kind": want, "name": want})
    return tid


def add_clip(project: dict, **kw: Any) -> dict:
    c = {"id": _nid(project), "start": 0.0, "dur": 3.0, "in": 0.0, "speed": 1.0, **kw}
    if "track" not in c:
        a = project["assets"].get(c.get("asset", ""), {})
        c["track"] = track_for(project, "text" if "text" in c or "subscribe" in c or "words" in c or "graphic" in c else "fx" if "mode" in c else a.get("kind", "video"))
    project["clips"].append(c)
    return c


def split_clip(project: dict, cid: str, t: float) -> dict | None:
    import copy
    import uuid
    c = find_clip(project, cid)
    if not c["start"] + 0.02 < t < c["start"] + c["dur"] - 0.02:
        return None
    left = t - c["start"]
    n = json.loads(json.dumps(c))
    n["id"] = _nid(project)
    n["start"] = t
    n["dur"] = c["dur"] - left
    n["in"] = float(c.get("in", 0)) + left * float(c.get("speed", 1) or 1)
    if n.get("words"):
        n["words"] = [{**w, "s": w["s"] - left, "e": w["e"] - left} for w in n["words"] if w["e"] > left]
        c["words"] = [w for w in c["words"] if w["s"] < left]
    if c.get("zoom"):
        n["zoom"] = [{**k, "t": k["t"] - left} for k in kf_resolve(c["zoom"], c["dur"]) if k["t"] >= left] or None
    n["fadeIn"] = 0
    c["fadeOut"] = 0
    c["dur"] = left
    project["clips"].append(n)
    return n


def ripple_close(project: dict, track: str, t0: float, gap: float) -> None:
    for c in project["clips"]:
        if c["track"] == track and c["start"] >= t0 - 1e-6:
            c["start"] = round(c["start"] - gap, 4)
    for ct in project.get("cuts") or []:
        if ct.get("track") == track and ct.get("seamStart", 0) >= t0 - 1e-6:
            ct["seamStart"] = round(ct["seamStart"] - gap, 4)


def ripple_close_gaps(project: dict, track: str) -> int:
    """Belirtilen izdeki klipler arasindaki tum bosluklari bastan sona kapatir; kaydirilan klip sayisini doner."""
    seq = sorted([c for c in project.get("clips") or [] if c.get("track") == track], key=lambda c: float(c.get("start", 0)))
    cur = 0.0
    moved = 0
    for c in seq:
        st = round(cur, 4)
        if abs(float(c.get("start", 0)) - st) > 1e-4:
            c["start"] = st
            moved += 1
        cur = st + float(c.get("dur", 0))
    return moved


def ripple_open(project: dict, track: str, t0: float, gap: float) -> None:
    for c in project["clips"]:
        if c["track"] == track and c["start"] >= t0 - 1e-6:
            c["start"] = round(c["start"] + gap, 4)
    for ct in project.get("cuts") or []:
        if ct.get("track") == track and ct.get("seamStart", 0) >= t0 - 1e-6:
            ct["seamStart"] = round(ct["seamStart"] + gap, 4)


def remove_ranges(
    project: dict,
    cid: str,
    ranges: list[list[float]],
    ripple: bool = True,
    pad: float = 0.08,
    pad_before: float | None = None,
) -> int:
    """Kaynak zamanindaki araliklari kliplerden cikar (sessizlik / donuk sahne kirpma). Kac parca silindigini doner."""
    import copy
    import uuid
    c = find_clip(project, cid)
    sp = float(c.get("speed", 1) or 1)
    pb = pad if pad_before is None else pad_before
    removed = 0
    cuts = project.setdefault("cuts", [])
    for a, b in sorted(ranges, key=lambda r: -r[0]):   # sondan basa: onceki zamanlar kaymaz
        a, b = a + pad, b - pb
        if b - a < 0.08:
            continue
        clips = [x for x in project["clips"] if x["track"] == c["track"] and x.get("asset") == c.get("asset")]
        for x in clips:
            xs, xi = x["start"], float(x.get("in", 0))
            t0, t1 = xs + (a - xi) / sp, xs + (b - xi) / sp
            if t1 <= xs or t0 >= xs + x["dur"]:
                continue
            t0, t1 = max(xs, t0), min(xs + x["dur"], t1)
            mid = split_clip(project, x["id"], t0) if t0 > xs + 0.02 else x
            if mid is None:
                continue
            if t1 < mid["start"] + mid["dur"] - 0.02:
                split_clip(project, mid["id"], t1)
            cut_snap = copy.deepcopy(mid)
            project["clips"].remove(mid)
            if ripple:
                ripple_close(project, c["track"], t1, t1 - t0)
            cuts.append({
                "id": f"cut_{uuid.uuid4().hex[:8]}",
                "track": c["track"],
                "seamStart": round(t0, 4),
                "dur": round(cut_snap["dur"], 4),
                "clip": cut_snap,
            })
            removed += 1
            break
    return removed


def restore_cuts(project: dict, cut_ids: list[str]) -> list[str]:
    """Secili kesilmis bolgeleri zaman cizelgesinde sadece o bolgeler icin eski haline getirir."""
    import copy
    wanted = set(cut_ids)
    cuts = project.get("cuts") or []
    targets = sorted(
        [ct for ct in cuts if ct.get("id") in wanted],
        key=lambda ct: -float(ct.get("seamStart", 0)),
    )
    restored_ids: list[str] = []
    for ct in targets:
        seam = float(ct.get("seamStart", 0))
        clip = copy.deepcopy(ct["clip"])
        dur = float(clip["dur"])
        ripple_open(project, ct["track"], seam, dur)
        clip["start"] = round(seam, 4)
        project["clips"].append(clip)
        cuts.remove(ct)
        restored_ids.append(clip["id"])
    return restored_ids


def summary(project: dict) -> dict:
    """Az token: kliplerin sadece anlamli alanlari."""
    keep = ("id", "track", "asset", "start", "dur", "in", "speed", "text", "mode", "subscribe", "fx", "vol", "zoom", "trans")
    return {"name": project.get("name"), "size": f"{project.get('w')}x{project.get('h')}@{project.get('fps')}",
            "end": round(project_end(project), 2),
            "tracks": [f"{t['id']}:{t['kind']}" + (" (muted)" if t.get("mute") else "") for t in project["tracks"]],
            "assets": {k: f"{a.get('kind')} {a.get('dur', 0):.1f}s {a.get('name', '')}" for k, a in project["assets"].items()},
            "clips": [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in c.items() if k in keep and v not in (None, [], {}, 0, 1.0) or k in ("start", "id", "track")}
                      for c in sorted(project["clips"], key=lambda c: (c["track"], c["start"]))],
            "markers": len(project.get("markers") or [])}


# ---------------------------------------------------------------------------------------------------------------
# Yerlesik ses efektleri (ffmpeg ile sentezlenir: telifsiz, ilk kullanimda Sesler\Kami Paketi'ne yazilir)
SFX = {
    "tik": ("aevalsrc='0.9*sin(2*PI*2400*t)*exp(-t*160)+0.4*(random(0)-0.5)*exp(-t*300)':d=0.06", "Tık"),
    "fare-tik": ("aevalsrc='0.8*sin(2*PI*2900*t)*exp(-t*220)*lt(t,0.03)+0.6*sin(2*PI*2200*(t-0.09))*exp(-(t-0.09)*220)*gte(t,0.09)':d=0.16", "Fare tıkı"),
    "deklansor": ("aevalsrc='(random(0)-0.5)*1.4*(exp(-t*45)*lt(t,0.06)+exp(-(t-0.11)*40)*gte(t,0.11))':d=0.25", "Deklanşör"),
    "whoosh": ("anoisesrc=d=0.7:c=pink:a=0.9,bandpass=f=900:w=1400,volume='sin(PI*t/0.7)^2':eval=frame", "Whoosh"),
    "hizli-whoosh": ("anoisesrc=d=0.35:c=pink:a=1,highpass=f=500,volume='sin(PI*t/0.35)^2':eval=frame", "Hızlı whoosh"),
    "bass-boom": ("aevalsrc='0.95*sin(2*PI*(58-25*t)*t)*exp(-t*3.2)':d=1.6,asoftclip=type=tanh", "Bas boom"),
    "vine-boom": ("aevalsrc='0.9*sin(2*PI*(70-30*t)*t)*exp(-t*4)+0.3*sin(2*PI*140*t)*exp(-t*9)':d=1.4,aecho=0.8:0.6:40|90:0.4|0.25,asoftclip", "Boom (meme)"),
    "riser": ("aevalsrc='0.5*sin(2*PI*(180*t+260*t*t))*(t/2.2)+0.35*(random(0)-0.5)*(t/2.2)^2':d=2.2,highpass=f=120", "Yükselen (riser)"),
    "ding": ("aevalsrc='0.6*sin(2*PI*1320*t)*exp(-t*4)+0.35*sin(2*PI*1980*t)*exp(-t*6)':d=1.2", "Ding"),
    "pop": ("aevalsrc='0.9*sin(2*PI*(900-700*t*8)*t)*exp(-t*35)':d=0.12", "Pop"),
    "zil": ("aevalsrc='0.5*sin(2*PI*1568*t)*exp(-t*3)+0.3*sin(2*PI*2093*t)*exp(-t*4)+0.2*sin(2*PI*3136*t)*exp(-t*6)':d=1.4", "Bildirim zili"),
    "glitch": ("aevalsrc='0.5*sgn(sin(2*PI*(220+880*floor(random(0)*4))*t))*lt(mod(t,0.07),0.05)':d=0.45,lowpass=f=6000", "Glitch"),
    "daktilo": ("aevalsrc='0.7*(random(0)-0.5)*exp(-mod(t,0.11)*90)':d=0.9,highpass=f=1200", "Daktilo"),
    "kalp": ("aevalsrc='0.9*sin(2*PI*48*t)*(exp(-mod(t,0.85)*18)+0.7*exp(-mod(t-0.18,0.85)*18)*gte(mod(t,0.85),0.18))':d=1.7", "Kalp atışı"),
    "plak": ("aevalsrc='0.6*(random(0)-0.5)*sin(PI*t/0.5)+0.4*sin(2*PI*(600-900*t)*t)*exp(-t*3)':d=0.5,bandpass=f=1800:w=2500", "Plak cızırtısı"),
    "swoosh-sol": ("anoisesrc=d=0.5:c=white:a=0.6,lowpass=f=3000,volume='sin(PI*t/0.5)^3':eval=frame", "Swoosh"),
    # ---- Meme / Shitpost / Oyun / Fragmovie paketi (telifsiz FFmpeg sentezi)
    "vine-boom-heavy": ("aevalsrc='1.1*sin(2*PI*(64-28*t)*t)*exp(-t*3.2)+0.45*sin(2*PI*128*t)*exp(-t*7)':d=1.5,aecho=0.8:0.65:35|85:0.4|0.2,asoftclip=type=tanh", "Vine Boom (Baslı)"),
    "bruh-horn": ("aevalsrc='0.8*sin(2*PI*(115-28*t)*t)*(1+0.3*sin(2*PI*230*t))*exp(-t*2.4)':d=0.7,asoftclip=type=tanh", "Bruh Korn (Düşük)"),
    "taco-bell": ("aevalsrc='0.65*sin(2*PI*494*t)*exp(-t*1.8)+0.4*sin(2*PI*988*t)*exp(-t*2.6)+0.25*sin(2*PI*1480*t)*exp(-t*3.5)':d=2.2", "Taco Bell Çanı"),
    "wrong-buzzer": ("aevalsrc='0.65*(sgn(sin(2*PI*145*t))+0.6*sgn(sin(2*PI*152*t)))*exp(-t*1.4)':d=0.85,lowpass=f=2600", "Hatalı Buzzer (Bip)"),
    "bonk-meme": ("aevalsrc='0.95*sin(2*PI*(520-380*t*3)*t)*exp(-t*22)+0.3*(random(0)-0.5)*exp(-t*55)':d=0.28", "Bonk (Kafa)"),
    "oof-retro": ("aevalsrc='0.85*sin(2*PI*(340-210*t)*t)*exp(-t*8)+0.25*sin(2*PI*680*t)*exp(-t*12)':d=0.35,lowpass=f=2400", "Retro Oof"),
    "airhorn-mlg": ("aevalsrc='0.55*(sgn(sin(2*PI*466*t))+0.7*sgn(sin(2*PI*587*t))+0.6*sgn(sin(2*PI*700*t)))*exp(-t*1.8)':d=0.9,bandpass=f=1200:w=2200,asoftclip=type=tanh", "MLG Hava Kornası"),
    "dramatic-dun": ("aevalsrc='0.75*(sin(2*PI*110*t)*lt(t,0.22)+sin(2*PI*103.8*gte(t,0.28)*lt(t,0.5)*t)*gte(t,0.28)*lt(t,0.5)+sin(2*PI*92.5*t)*gte(t,0.55)*exp(-(t-0.55)*2.2))':d=1.8,asoftclip=type=tanh", "Dramatik Dun-Dun-Dun"),
    "sad-trombone": ("aevalsrc='0.65*(sin(2*PI*293.7*t)*lt(t,0.35)+sin(2*PI*277.2*t)*gte(t,0.38)*lt(t,0.72)+sin(2*PI*261.6*t)*gte(t,0.75)*lt(t,1.1)+sin(2*PI*(246.9-18*(t-1.15))*t)*gte(t,1.15)*exp(-(t-1.15)*1.8))':d=2.2,lowpass=f=2200", "Üzgün Trombon (Wah)"),
    "discord-ping": ("aevalsrc='0.65*sin(2*PI*880*t)*exp(-t*14)*lt(t,0.12)+0.7*sin(2*PI*1318.5*(t-0.11))*exp(-(t-0.11)*10)*gte(t,0.11)':d=0.45", "Bildirim (Discord Ping)"),
    "flashbang": ("aevalsrc='0.8*(random(0)-0.5)*exp(-t*12)+0.55*sin(2*PI*3650*t)*exp(-t*1.6)':d=2.4,highpass=f=300", "Flashbang Çınlaması"),
    "hitmarker": ("aevalsrc='0.9*(random(0)-0.5)*exp(-t*140)+0.6*sin(2*PI*3200*t)*exp(-t*160)':d=0.07", "FPS Hitmarker"),
    "anime-teleport": ("aevalsrc='0.7*sin(2*PI*(1900-1400*t*3)*t)*exp(-t*10)+0.35*(random(0)-0.5)*exp(-t*14)':d=0.35", "Anime Işınlanma"),
    "anime-punch": ("aevalsrc='1.0*sin(2*PI*(140-90*t)*t)*exp(-t*14)+0.65*(random(0)-0.5)*exp(-t*28)':d=0.32,asoftclip=type=tanh", "Anime Ağır Yumruk"),
    "sub-drop": ("aevalsrc='0.95*sin(2*PI*(95-58*t*0.5)*t)*exp(-t*2.0)':d=2.0,asoftclip=type=tanh", "808 Sub Drop"),
    "whip-crack": ("anoisesrc=d=0.28:c=white:a=0.9,bandpass=f=2200:w=2600,volume='exp(-t*16)*4':eval=frame", "Kamçı / Hızlı Geçiş"),
    "cash-register": ("aevalsrc='0.5*(random(0)-0.5)*exp(-t*45)*lt(t,0.09)+0.65*sin(2*PI*2637*(t-0.1))*exp(-(t-0.1)*4)*gte(t,0.1)+0.45*sin(2*PI*3951*(t-0.1))*exp(-(t-0.1)*5)*gte(t,0.1)':d=0.9", "Kasa Sesi (Cha-Ching)"),
    "record-scratch": ("aevalsrc='0.65*sin(2*PI*(420+260*sin(2*PI*11*t))*t)*exp(-t*5)+0.35*(random(0)-0.5)*exp(-t*6)':d=0.45,bandpass=f=1500:w=2200", "Plak Durma (Scratch)"),
    **SFX_PRO,
    **SFX_TR_MEME,
}

SFX_CAT = {
    "tik": "UI & Oyun", "fare-tik": "UI & Oyun", "deklansor": "UI & Oyun", "ding": "UI & Oyun",
    "zil": "UI & Oyun", "discord-ping": "UI & Oyun", "flashbang": "UI & Oyun", "hitmarker": "UI & Oyun", "cash-register": "UI & Oyun",
    "whoosh": "Geçiş & Hareket", "hizli-whoosh": "Geçiş & Hareket", "swoosh-sol": "Geçiş & Hareket",
    "anime-teleport": "Geçiş & Hareket", "whip-crack": "Geçiş & Hareket", "glitch": "Geçiş & Hareket",
    "bass-boom": "Vuruş & Darbe", "sub-drop": "Vuruş & Darbe", "anime-punch": "Vuruş & Darbe", "pop": "Vuruş & Darbe",
    "vine-boom": "Meme & Shitpost", "vine-boom-heavy": "Meme & Shitpost", "bruh-horn": "Meme & Shitpost",
    "taco-bell": "Meme & Shitpost", "wrong-buzzer": "Meme & Shitpost", "bonk-meme": "Meme & Shitpost",
    "oof-retro": "Meme & Shitpost", "airhorn-mlg": "Meme & Shitpost", "sad-trombone": "Meme & Shitpost",
    "record-scratch": "Meme & Shitpost", "plak": "Meme & Shitpost",
    "riser": "Dramatik & Gerilim", "kalp": "Dramatik & Gerilim", "dramatic-dun": "Dramatik & Gerilim", "daktilo": "Dramatik & Gerilim",
    **SFX_CAT_PRO,
    **SFX_CAT_TR_MEME,
}


def sfx_dir() -> Path:
    d = home_dir() / "Sesler" / "Kami Paketi"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_sfx(ffmpeg: str, name: str = "") -> dict[str, str]:
    """Eksik efektleri uretir; {ad: yol}."""
    out = {}
    for key, (expr, label) in SFX.items():
        if name and key != name:
            continue
        safe_lbl = re.sub(r'[<>:"/\\|?*]+', "-", label).strip() or key
        f = sfx_dir() / f"{safe_lbl}.wav"
        if not f.is_file() and ffmpeg:
            subprocess.run([ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-f", "lavfi", "-i", expr,
                            "-af", "aformat=channel_layouts=stereo,aresample=48000,afade=t=out:st=0:d=0.02:curve=nofade,alimiter=limit=0.95",
                            "-ar", "48000", str(f)], capture_output=True, timeout=60, creationflags=NO_WINDOW)
        if f.is_file():
            out[key] = str(f)
    return out


AUDIO_FIX_NAMES = {"nr1": "Gürültü azalt (hafif)", "nr2": "Gürültü azalt (güçlü)", "voice": "Ses netleştir (EQ + kompresör + de-esser)",
                   "gate": "Kapı (nefes/arka sesi kes)", "bass": "Bas güçlendir", "radio": "Telsiz", "phone": "Telefon", "cave": "Mağara yankısı",
                   "hot-montage": "Sıcak montaj (-10 LUFS + Limiter)", "meme-earrape": "Meme Bas / Kulak Patlatan (-7 LUFS)", "muffle": "Meme duraksama (Lo-Pass Boğuk)",
                   **AUDIO_FIX_NAMES_PRO}


# ---------------------------------------------------------------------------------------------------------------
# Hazir sablonlar: oynatma kafasina eklenen klip gruplari ('sfx' = yerlesik ses efekti adi)
TEMPLATES = [
    # Shorts / Reels / TikTok
    {"id": "shorts-hook", "group": "Shorts", "name": "Hook başlığı", "items": [
        {"t": 0, "text": "BUNU KİMSE SÖYLEMİYOR", "dur": 2.4, "style": {"font": "Anton", "size": 8.5, "anim": "pop", "pos": "custom", "x": .5, "y": .2, "outline": 8, "color": "#FFFFFF"}},
        {"t": 0, "sfx": "whoosh"}]},
    {"id": "shorts-end", "group": "Shorts", "name": "Bitiş: takip et + tekrar izle", "items": [
        {"t": 0, "subscribe": "yt-dark", "dur": 3.5, "style": {"y": .72, "size": 120}},
        {"t": 0, "text": "↻ TEKRAR İZLE", "dur": 3.5, "style": {"font": "Anton", "size": 6, "anim": "bounce", "pos": "custom", "x": .5, "y": .3}},
        {"t": 0.85, "sfx": "fare-tik"}, {"t": 1.55, "sfx": "fare-tik"}, {"t": 2.25, "sfx": "zil"}]},
    {"id": "shorts-punch", "group": "Shorts", "name": "Vurgulu kelime (ekran ortası)", "items": [
        {"t": 0, "graphic": "highlight", "dur": 1.6, "style": {"title": "ÖNEMLİ", "y": .45}}, {"t": 0, "sfx": "pop"}]},
    # YouTube
    {"id": "yt-intro", "group": "YouTube", "name": "Glitch intro", "items": [
        {"t": 0, "mode": "glitch", "dur": 0.45}, {"t": 0.4, "mode": "flash", "dur": 0.3},
        {"t": 0.35, "text": "KANAL ADI", "dur": 2.4, "style": {"font": "Rubik Glitch", "size": 12, "anim": "glitch", "pos": "center", "outline": 4, "outlineColor": "#FF2E88"}},
        {"t": 0, "sfx": "glitch"}, {"t": 0.35, "sfx": "bass-boom"}]},
    {"id": "yt-end", "group": "YouTube", "name": "Bitiş ekranı (20 sn)", "items": [
        {"t": 0, "graphic": "endscreen", "dur": 20, "style": {}}, {"t": 0.3, "sfx": "ding"}]},
    {"id": "yt-chapter", "group": "YouTube", "name": "Bölüm başlığı", "items": [
        {"t": 0, "graphic": "chapter", "dur": 2.6, "style": {"num": "01", "title": "BÖLÜM BAŞLIĞI"}}, {"t": 0, "sfx": "whoosh"}]},
    {"id": "yt-lower", "group": "YouTube", "name": "İsim alt bandı", "items": [
        {"t": 0, "graphic": "lower", "dur": 4, "style": {"title": "İsim Soyisim", "sub": "Unvan"}}, {"t": 0, "sfx": "swoosh-sol"}]},
    {"id": "yt-sub", "group": "YouTube", "name": "Video ortası abone hatırlatma", "items": [
        {"t": 0, "subscribe": "yt-light", "dur": 3.4, "style": {"y": .82, "size": 80}},
        {"t": 0.85, "sfx": "fare-tik"}, {"t": 1.55, "sfx": "fare-tik"}, {"t": 2.25, "sfx": "zil"}]},
    # Oyun / highlight / meme
    {"id": "freeze", "group": "Oyun & meme", "name": "Kare dondur + zoom + tık", "needs": "clip", "items": [{"t": 0, "sfx": "deklansor"}]},
    {"id": "rage", "group": "Oyun & meme", "name": "Rage anı", "items": [
        {"t": 0, "mode": "rage", "dur": 1.6}, {"t": 0, "text": "AAAAAA!", "dur": 1.6, "style": {"font": "Impact", "size": 14, "anim": "shake", "pos": "center", "color": "#FF2A2A", "outline": 8, "bold": False}},
        {"t": 0, "sfx": "bass-boom"}]},
    {"id": "kill", "group": "Oyun & meme", "name": "Kill vuruşu", "items": [
        {"t": 0, "mode": "flash", "dur": 0.25}, {"t": 0, "mode": "rgbsplit", "dur": 0.35},
        {"t": 0, "text": "+1", "dur": 1.0, "style": {"font": "Anton", "size": 12, "anim": "zoom", "pos": "custom", "x": .5, "y": .4, "color": "#FFE600"}},
        {"t": 0, "sfx": "vine-boom"}]},
    {"id": "meme-stop", "group": "Oyun & meme", "name": "“O anlar…” (S/B + plak)", "items": [
        {"t": 0, "mode": "sad", "dur": 3}, {"t": 0.2, "text": "o anlar...", "dur": 2.8, "style": {"font": "Georgia", "size": 6, "anim": "type", "pos": "bottom", "italic": True, "bold": False}},
        {"t": 0, "sfx": "plak"}]},
    {"id": "bruh", "group": "Oyun & meme", "name": "BRUH (deep fried)", "items": [
        {"t": 0, "mode": "deepfried", "dur": 1.2}, {"t": 0, "text": "BRUH", "dur": 1.2, "style": {"font": "Impact", "size": 16, "anim": "none", "pos": "center", "outline": 10, "bold": False}},
        {"t": 0, "sfx": "vine-boom"}]},
    # Vlog / podcast / belgesel
    {"id": "location", "group": "Vlog & belgesel", "name": "Konum etiketi", "items": [
        {"t": 0, "graphic": "location", "dur": 3.5, "style": {"title": "İstanbul, Türkiye", "sub": "Kadıköy"}}, {"t": 0, "sfx": "pop"}]},
    {"id": "doc-open", "group": "Vlog & belgesel", "name": "Belgesel açılışı", "items": [
        {"t": 0, "mode": "letterbox", "dur": 6}, {"t": 0, "mode": "film", "dur": 6},
        {"t": 1.2, "text": "BİR HİKÂYE", "dur": 4, "style": {"font": "Georgia", "size": 5, "anim": "fade", "pos": "center", "spacing": 14, "outline": 0, "shadow": 3, "bold": False}},
        {"t": 0, "sfx": "riser"}]},
    {"id": "podcast", "group": "Vlog & belgesel", "name": "Podcast: iki konuşmacı bandı", "items": [
        {"t": 0, "graphic": "lower-min", "dur": 4, "style": {"title": "Konuk", "sub": "Unvan", "x": .06, "y": .82}},
        {"t": 0, "graphic": "lower-min", "dur": 4, "style": {"title": "Sunucu", "sub": "Kanal", "x": .56, "y": .82}}]},
    {"id": "quote", "group": "Vlog & belgesel", "name": "Alıntı kartı", "items": [
        {"t": 0, "graphic": "quote", "dur": 5, "style": {"title": "Kaybetmekten korkma.", "sub": "Biri"}}, {"t": 0, "sfx": "ding"}]},
    {"id": "counter", "group": "Vlog & belgesel", "name": "Sayaç (istatistik)", "items": [
        {"t": 0, "graphic": "counter", "dur": 3, "style": {"from": 0, "to": 1000000, "suffix": " izlenme"}}, {"t": 0, "sfx": "riser"}]},
] + TEMPLATES_PRO + TEMPLATES_TR_MEME
TEMPLATE_NAMES = [{"id": t["id"], "group": t["group"], "name": t["name"], "needs": t.get("needs", "")} for t in TEMPLATES]


def apply_template(project: dict, tid: str, t: float, ffmpeg: str = "", clip_id: str = "", info: Callable | None = None) -> list[str]:
    """Sablonu t anina ekler; eklenen klip kimliklerini doner."""
    tpl = next((x for x in TEMPLATES if x["id"] == tid), None)
    if not tpl:
        raise KeyError(tid)
    added: list[str] = []

    def place(kind: str, c: dict) -> dict:
        tr = [x for x in project["tracks"] if x["kind"] == kind]
        for x in tr:
            if not any(o["track"] == x["id"] and o["start"] < c["start"] + c["dur"] - 1e-3 and o["start"] + o["dur"] > c["start"] + 1e-3 for o in project["clips"]):
                c["track"] = x["id"]
                break
        else:
            tid2 = kind[0] + str(len(project["tracks"]) + 1)
            project["tracks"].append({"id": tid2, "kind": kind, "name": kind})
            c["track"] = tid2
        c["id"] = _nid(project)
        project["clips"].append(c)
        added.append(c["id"])
        return c

    if tid == "freeze":
        c = find_clip(project, clip_id) if clip_id else None
        if not c or project["assets"].get(c.get("asset", ""), {}).get("kind") != "video":
            raise ValueError("Kare dondurmak için bir video klibi seç")
        if not (c["start"] < t < c["start"] + c["dur"]):
            t = c["start"] + c["dur"] / 2
        right = split_clip(project, c["id"], t)
        fd = 1.4
        for o in project["clips"]:   # sonrakileri kaydir
            if o["track"] == c["track"] and o["start"] >= t - 1e-6 and o is not c:
                o["start"] = round(o["start"] + fd, 4)
        src = float(c.get("in", 0)) + (t - c["start"]) * float(c.get("speed", 1) or 1)
        fz = {"id": _nid(project), "track": c["track"], "asset": c["asset"], "start": t, "dur": fd, "in": round(src, 3), "speed": 1, "freeze": True,
              "zoom": [{"t": 0, "z": 1}, {"t": 0.12, "z": 1.35, "e": "out"}, {"t": fd, "z": 1.45}], "trans": {"in": "flash", "dur": 0.2}, "fx": ["mono-pop"]}
        project["clips"].append(fz)
        added.append(fz["id"])
        if right:
            added.append(right["id"])
    sfx = ensure_sfx(ffmpeg) if any("sfx" in i for i in tpl["items"]) else {}
    for it in tpl["items"]:
        it = json.loads(json.dumps(it))
        start = round(t + float(it.pop("t", 0)), 3)
        if "sfx" in it:
            p = sfx.get(it["sfx"])
            if not p:
                continue
            meta = info(p) if info else {"path": p, "kind": "audio", "dur": 1.0, "audio": True, "name": Path(p).stem}
            aid = add_asset(project, meta)
            place("audio", {"asset": aid, "start": start, "dur": float(meta.get("dur", 1.0)), "in": 0.0, "speed": 1.0, "vol": 0.9})
            continue
        kind = "fx" if "mode" in it else "text"
        place(kind, {"start": start, "dur": float(it.pop("dur", 3)), "in": 0.0, "speed": 1.0, **it})
    return added


# ---------------------------------------------------------------------------------------------------------------
# Fontlar: sistem + kullanici + Kami + Kami Studio\Fontlar; ucretsiz Google Fonts paketi
GOOGLE_FONTS = {
    "Anton": "ofl/anton/Anton-Regular.ttf", "Bebas Neue": "ofl/bebasneue/BebasNeue-Regular.ttf",
    "Bangers": "ofl/bangers/Bangers-Regular.ttf", "Luckiest Guy": "apache/luckiestguy/LuckiestGuy-Regular.ttf",
    "Permanent Marker": "apache/permanentmarker/PermanentMarker-Regular.ttf", "Poppins Black": "ofl/poppins/Poppins-Black.ttf",
    "Poppins Bold": "ofl/poppins/Poppins-Bold.ttf", "Archivo Black": "ofl/archivoblack/ArchivoBlack-Regular.ttf",
    "Lilita One": "ofl/lilitaone/LilitaOne-Regular.ttf", "Titan One": "ofl/titanone/TitanOne-Regular.ttf",
    "Russo One": "ofl/russoone/RussoOne-Regular.ttf", "Black Ops One": "ofl/blackopsone/BlackOpsOne-Regular.ttf",
    "Creepster": "ofl/creepster/Creepster-Regular.ttf", "Press Start 2P": "ofl/pressstart2p/PressStart2P-Regular.ttf",
    "Pacifico": "ofl/pacifico/Pacifico-Regular.ttf", "Montserrat": "ofl/montserrat/Montserrat%5Bwght%5D.ttf",
    "Oswald": "ofl/oswald/Oswald%5Bwght%5D.ttf", "Caveat": "ofl/caveat/Caveat%5Bwght%5D.ttf",
    "Rubik Mono One": "ofl/rubikmonoone/RubikMonoOne-Regular.ttf", "Bowlby One": "ofl/bowlbyone/BowlbyOne-Regular.ttf",
}


def font_dir() -> Path:
    d = home_dir() / "Fontlar"
    d.mkdir(parents=True, exist_ok=True)
    return d


def fonts_index(refresh: bool = False) -> dict[str, str]:
    """{aile adi: dosya}. Pillow ile ad okunur; sonuc onbellekte (klasor degisim zamanlarina gore)."""
    dirs = [paths.WEB_DIR / "fonts", font_dir()]
    if os.name == "nt":
        dirs += [Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts",
                 Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts"]
    stamp = "|".join(f"{d}:{int(d.stat().st_mtime) if d.is_dir() else 0}" for d in dirs)
    cf = CACHE / "fonts.json"
    if not refresh:
        try:
            c = json.loads(cf.read_text("utf-8"))
            if c.get("stamp") == stamp:
                return c["fonts"]
        except (OSError, ValueError):
            pass
    out: dict[str, str] = {}
    try:
        from PIL import ImageFont
    except Exception:
        ImageFont = None   # noqa: N806
    for d in dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if f.suffix.lower() not in (".ttf", ".otf", ".ttc"):
                continue
            fam = None
            if ImageFont:
                try:
                    fam, style = ImageFont.truetype(str(f), 12).getname()
                    if style and style.lower() not in ("regular", "normal", "book", "roman") and fam in out:
                        continue
                except Exception:
                    fam = None
            fam = fam or f.stem
            out.setdefault(fam, str(f))
    CACHE.mkdir(parents=True, exist_ok=True)
    cf.write_text(json.dumps({"stamp": stamp, "fonts": out}, ensure_ascii=False), "utf-8")
    return out


def download_google_fonts(names: list[str] | None = None) -> list[str]:
    import urllib.request
    got = []
    for name, rel in GOOGLE_FONTS.items():
        if names and name not in names:
            continue
        dst = font_dir() / (name.replace(" ", "") + ".ttf")
        if dst.is_file():
            got.append(name)
            continue
        try:
            data = urllib.request.urlopen(f"https://raw.githubusercontent.com/google/fonts/main/{rel}", timeout=30).read()
            if len(data) > 1000:
                dst.write_bytes(data)
                got.append(name)
        except Exception as exc:
            log.warning("Font indirilemedi %s: %s", name, exc)
    fonts_index(True)
    return got
