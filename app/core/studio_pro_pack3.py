"""Kami Studio Dalga 8 — Paid NLE Plugins & Motion Packs Master Catalog.

Adds genuine FFmpeg filterchains, animated transitions, Soundly/Perfect-Pitch audio fixes,
and AtomX/Spunkram/AEJuice/Envato templates (100% copyright-free native synthesis).
"""
from __future__ import annotations

import math

_CB = lambda **k: "colorbalance=" + ":".join(f"{p}={v}" for p, v in k.items())

FX_PACK3 = {
    # PluginPlay Grainiac + Halation + Cinema
    "grainiac-35mm": {
        "name": "Grainiac 35mm HDR Film",
        "pack": "Sinema & Analog",
        "ff": "split[g0][g1];[g1]gblur=sigma=14,eq=brightness=0.05," + _CB(rh=0.22, gh=0.06, bh=-0.12) + "[g2];[g0][g2]blend=all_mode=screen:all_opacity=0.35,noise=alls=14:allf=t,eq=contrast=1.12:saturation=1.08",
        "css": "contrast(1.12) saturate(1.1)",
        "ov": ["grain", "halation", "vignette"],
    },
    "halation-16mm": {
        "name": "Halation 16mm Kırmızı Parlama",
        "pack": "Sinema & Analog",
        "ff": "split[h0][h1];[h1]gblur=sigma=20,eq=contrast=1.35:brightness=-0.04," + _CB(rh=0.38, gh=-0.08, bh=-0.2) + "[h2];[h0][h2]blend=all_mode=screen:all_opacity=0.45",
        "css": "contrast(1.1) saturate(1.15)",
        "ov": ["halation", "bloom"],
    },
    "vhs-camcorder": {
        "name": "VHS El Kamerası (1998)",
        "pack": "Sinema & Analog",
        "ff": "rgbashift=rh=4:bh=-4,eq=contrast=1.1:saturation=0.88:brightness=0.02,noise=alls=16:allf=t,drawgrid=w=4:h=3:t=1:c=black@0.2",
        "css": "contrast(1.1) saturate(0.88) sepia(0.14)",
        "ov": ["scan", "vhs-jitter", "frame-rec"],
    },
    "aerochrome-ir": {
        "name": "Kızılötesi Aerochrome",
        "pack": "Sinema & Analog",
        "ff": "hue=h=145,eq=saturation=1.45:contrast=1.16," + _CB(rs=0.24, gs=-0.18, bs=0.14),
        "css": "hue-rotate(145deg) saturate(1.45) contrast(1.16)",
        "ov": ["grain"],
    },
    "noir-contrast": {
        "name": "Kara Film (Sin City Noir)",
        "pack": "Sinema & Analog",
        "ff": "hue=s=0,eq=contrast=1.65:brightness=-0.05,vignette=PI/3",
        "css": "grayscale(1) contrast(1.65) brightness(0.95)",
        "ov": ["vignette-hard", "grain"],
    },
    # AEJuice CRT / Terminal / Cyber
    "crt-hack-green": {
        "name": "Hacker Terminali (Yeşil Fosfor)",
        "pack": "CRT & Glitch",
        "ff": "hue=s=0," + _CB(rs=-0.45, gs=0.42, bs=-0.42, rm=-0.3, gm=0.32, bm=-0.3) + ",drawgrid=w=4:h=4:t=1:c=black@0.35,eq=contrast=1.3",
        "css": "grayscale(1) sepia(1) hue-rotate(72deg) saturate(2.5) contrast(1.3)",
        "ov": ["scan", "bloom"],
    },
    "amber-terminal": {
        "name": "Kehribar Terminal (1984)",
        "pack": "CRT & Glitch",
        "ff": "hue=s=0," + _CB(rs=0.38, gs=0.16, bs=-0.45) + ",drawgrid=w=5:h=4:t=1:c=black@0.32,eq=contrast=1.25",
        "css": "grayscale(1) sepia(1) hue-rotate(-10deg) saturate(2.4) contrast(1.25)",
        "ov": ["scan"],
    },
    # PluginPlay Prism / Glass / Gradient / Sketch / Outlines
    "broken-prism": {
        "name": "Kırık Prizma Dağılımı",
        "pack": "Optik",
        "ff": "split[bp0][bp1];[bp1]crop=iw-24:ih-24:12:12,scale=W:H,rgbashift=rh=16:bh=-16:edge=smear[bp2];[bp0][bp2]blend=all_mode=screen:all_opacity=0.45,eq=saturation=1.3",
        "css": "saturate(1.3) contrast(1.14)",
        "ov": ["rgb-strong", "prism"],
    },
    "leak-anamorphic-gold": {
        "name": "Altın Anamorfik Işık",
        "pack": "Optik",
        "ff": "split[la0][la1];[la1]avgblur=sizeX=42:sizeY=2," + _CB(rs=0.36, gs=0.22, bs=-0.2, rh=0.32, gh=0.18) + "[la2];[la0][la2]blend=all_mode=screen:all_opacity=0.48",
        "css": "contrast(1.08) saturate(1.2) sepia(0.14)",
        "ov": ["bloom", "warm-tint"],
    },
    "mesh-cyber-duo": {
        "name": "İki Ton Siber (Mor / Turkuaz)",
        "pack": "Renk & Gradyan",
        "ff": "hue=s=0.15," + _CB(rs=0.24, gs=-0.12, bs=0.35, rh=-0.22, gh=0.24, bh=0.28) + ",eq=contrast=1.28:saturation=1.4",
        "css": "contrast(1.28) saturate(1.4) hue-rotate(-18deg)",
        "ov": ["bloom"],
    },
    "mesh-sunset-duo": {
        "name": "İki Ton Gün Batımı (Turuncu / Mor)",
        "pack": "Renk & Gradyan",
        "ff": _CB(rs=0.18, gs=-0.1, bs=0.28, rh=0.32, gh=0.12, bh=-0.18) + ",eq=contrast=1.22:saturation=1.32",
        "css": "contrast(1.22) saturate(1.32) sepia(0.18)",
        "ov": ["warm-tint"],
    },
    "ballpoint-sketch": {
        "name": "Tükenmez Kalem Çizim (Ballpoint)",
        "pack": "Stilize",
        "ff": "edgedetect=low=0.09:high=0.24:mode=wires,negate,eq=contrast=1.35:brightness=0.04",
        "css": "grayscale(1) contrast(2.2) invert(0.85)",
        "ov": ["paper-grain"],
    },
    "comic-halftone": {
        "name": "Çizgi Roman Baskı (Comic)",
        "pack": "Stilize",
        "ff": "eq=contrast=1.45:saturation=1.7,unsharp=5:5:1.8:5:5:0,drawgrid=w=6:h=6:t=1:c=black@0.18",
        "css": "contrast(1.45) saturate(1.75)",
        "ov": ["grain"],
    },
    "white-stroke-edge": {
        "name": "Parlak Beyaz Kontur (Outlines)",
        "pack": "Stilize",
        "ff": "split[ws0][ws1];[ws1]edgedetect=low=0.12:high=0.35:mode=wires,dilation[ws2];[ws0][ws2]blend=all_mode=screen:all_opacity=0.8",
        "css": "contrast(1.25)",
        "ov": ["bloom"],
    },
    "path-blur-fast": {
        "name": "Hız Yönü Bulanıklığı (Path Blur)",
        "pack": "VFX",
        "ff": "split[pb0][pb1];[pb1]avgblur=sizeX=28:sizeY=2[pb2];[pb0][pb2]blend=all_mode=lighten:all_opacity=0.52,eq=contrast=1.1",
        "css": "contrast(1.1) saturate(1.15)",
        "ov": ["zoom"],
    },
    # AEJuice Weather & Particles
    "weather-rain": {
        "name": "Sağanak Yağmur Efekti",
        "pack": "Atmosfer",
        "ff": _CB(rs=-0.14, gs=-0.02, bs=0.2) + ",eq=contrast=1.12:saturation=0.82",
        "css": "contrast(1.12) saturate(0.84) brightness(0.94)",
        "ov": ["rain", "cool-tint"],
    },
    "weather-snow": {
        "name": "Lapa Lapa Kar Yağışı",
        "pack": "Atmosfer",
        "ff": _CB(bs=0.16, bh=0.12) + ",eq=brightness=0.05:saturation=0.92",
        "css": "brightness(1.06) saturate(0.92)",
        "ov": ["snow", "cool-tint"],
    },
    "fire-sparks": {
        "name": "Ateş Kıvılcımları (Ember)",
        "pack": "Atmosfer",
        "ff": _CB(rs=0.22, gs=0.05, bs=-0.16, rh=0.18) + ",eq=contrast=1.16:saturation=1.22",
        "css": "contrast(1.16) saturate(1.24) sepia(0.12)",
        "ov": ["sparks", "warm-tint"],
    },
}

TRANS_PACK3 = {
    "prism-whip": "Prizma Savurma",
    "broken-glass-cut": "Kırık Cam Kesmesi",
    "burning-edge": "Alev Kenar Silmesi",
    "liquid-splash-wipe": "Sıvı Sıçrama Açılışı",
    "retro-tv-off": "Eski TV Kapanışı",
    "kinetic-tile-flip": "Karo Çevirme (6×4)",
    "ink-splatter-wipe": "Mürekkep Sıçraması",
    "datamosh-cut": "Datamosh Sıçraması",
    "cyberpunk-slice": "Siber Dilimli Kayma",
    "camera-flash-bulb": "Stüdyo Flaş Patlaması",
}


def trans_in_pack3(kind: str, d: float, W: int, H: int, tag: str, c0: float, fps: float) -> str:
    """FFmpeg filter string for Wave 8 paid transitions."""
    d = max(0.05, float(d))
    u = f"min(1,max(0,(t-{c0:.4f})/{d:.4f}))"
    e = f"(1-pow(1-{u},3))"
    E = f"(1-pow(1-min(1,max(0,(T-{c0:.4f})/{d:.4f})),3))"
    en = f"enable='between(t,{c0:.4f},{c0 + d:.4f})'"

    if kind == "prism-whip":
        return f"rgbashift=rh=16:bh=-16:edge=smear:{en},gblur=sigma=14:{en}"
    if kind == "broken-glass-cut":
        return f"rgbashift=rh=14:bh=-14:{en},eq=brightness='0.35*(1-{u})':contrast='1+0.4*(1-{u})':eval=frame:{en}"
    if kind == "burning-edge":
        return (
            f"geq=r='clip(r(X,Y)+180*exp(-pow((X-W*{E})/(W*0.08),2)),0,255)'"
            f":g='clip(g(X,Y)+95*exp(-pow((X-W*{E})/(W*0.08),2)),0,255)'"
            f":b='b(X,Y)':a='if(lt(X,W*{E}),alpha(X,Y),0)':{en}"
        )
    if kind == "liquid-splash-wipe":
        return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lt(Y,H*{E}+sin(X*0.03)*H*0.08*(1-{E})),alpha(X,Y),0)':{en}"
    if kind == "retro-tv-off":
        return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lt(abs(Y-H/2),max(3,{E}*H/2)),alpha(X,Y),0)':{en}"
    if kind == "kinetic-tile-flip":
        return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lt(mod(X,W/6),{E}*(W/6)),alpha(X,Y),0)':{en}"
    if kind == "ink-splatter-wipe":
        r_max = math.hypot(W, H) * 0.62
        return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lt(hypot(X-W/2,Y-H/2),{E}*{r_max:.1f}+sin(atan2(Y-H/2,X-W/2)*7)*{W*0.05:.1f}),alpha(X,Y),0)':{en}"
    if kind == "datamosh-cut":
        return f"rgbashift=rh=18:bv=-14:edge=smear:{en},tmix=frames=4:{en}"
    if kind == "cyberpunk-slice":
        return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lt(mod(floor(Y/(H/8)),2)*0.45+(X/W),{E}*1.45),alpha(X,Y),0)':{en},rgbashift=rh=10:bh=-10:{en}"
    if kind == "camera-flash-bulb":
        return f"eq=brightness='0.82*exp(-pow({u}*4.5,2))':eval=frame:{en}"
    return f"fade=t=in:st={c0:.4f}:d={d:.4f}"


AUDIO_FIX_PACK3 = {
    "soundly-denoise": "highpass=f=85,afftdn=nr=18:nf=-40:tn=1",
    "soundly-dereverb": "highpass=f=90,agate=threshold=0.02:ratio=4:attack=3:release=90,afftdn=nr=14:nf=-38",
    "soundly-lufs-yt": "loudnorm=I=-14:TP=-1.5:LRA=9",
    "soundly-lufs-pod": "highpass=f=80,acompressor=threshold=-20dB:ratio=3:makeup=3,loudnorm=I=-16:TP=-1.5:LRA=7",
    "place-concert": "highpass=f=70,aecho=0.75:0.8:55|115|180:0.42|0.32|0.22,lowpass=f=11000",
    "place-car": "highpass=f=120,lowpass=f=4800,equalizer=f=220:t=q:w=1.5:g=4,aecho=0.85:0.6:18|32:0.25|0.15",
    "place-subway": "highpass=f=140,lowpass=f=6500,aecho=0.8:0.85:70|150|240:0.48|0.36|0.25",
    "place-stadium": "highpass=f=240,lowpass=f=5200,acompressor=threshold=-16dB:ratio=5,aecho=0.7:0.88:110|230:0.45|0.32",
    "perfect-pitch-up2": "asetrate=48000*1.122462,aresample=48000,atempo=0.890899",
    "perfect-pitch-down2": "asetrate=48000*0.890899,aresample=48000,atempo=1.122462",
}

AUDIO_FIX_NAMES_PACK3 = {
    "soundly-denoise": "Soundly: Ses Temizle (FFT Denoise)",
    "soundly-dereverb": "Soundly: Yankı Sil (De-Reverb)",
    "soundly-lufs-yt": "Soundly: YouTube -14 LUFS",
    "soundly-lufs-pod": "Soundly: Podcast -16 LUFS",
    "place-concert": "Place it: Konser Salonu",
    "place-car": "Place it: Araba İçi Kabin",
    "place-subway": "Place it: Metro İstasyonu",
    "place-stadium": "Place it: Stadyum Anonsu",
    "perfect-pitch-up2": "Perfect Pitch: +2 Yarım Ton (Tempo Sabit)",
    "perfect-pitch-down2": "Perfect Pitch: -2 Yarım Ton (Tempo Sabit)",
}

TEMPLATES_PACK3 = [
    {"id": "gadzhi-doodle-hook", "group": "Sosyal & YouTube Pro", "name": "Iman Gadzhi Kağıt & Vurgu Kancası", "needs": "", "items": [
        {"t": 0, "fx": "paper-rip", "dur": 2.4},
        {"t": 0, "graphic": "highlight", "dur": 2.2, "style": {"title": "SIRRINI AÇIKLIYORUM", "y": 0.42}},
        {"t": 0, "sfx": "whoosh"}, {"t": 1.1, "sfx": "kalem-cizim"}]},
    {"id": "cyberpunk-hud-intro", "group": "CRT & Siber", "name": "Siber Terminal Giriş Sahnesi", "needs": "", "items": [
        {"t": 0, "fx": "crt-hack-green", "dur": 3.0},
        {"t": 0, "text": ">> SİSTEM BAŞLATILIYOR...", "dur": 2.8, "style": {"font": "VT323", "size": 52, "color": "#2EE6A6", "y": 0.5}},
        {"t": 0, "sfx": "glitch"}, {"t": 0.4, "sfx": "bass-boom"}]},
    {"id": "history-timeline-era", "group": "Belgesel & Tarih", "name": "Tarihsel Zaman Çizelgesi Kartı", "needs": "", "items": [
        {"t": 0, "fx": "grainiac-35mm", "dur": 4.0},
        {"t": 0, "graphic": "chapter", "dur": 3.5, "style": {"num": "1994", "title": "DÖNÜM NOKTASI"}},
        {"t": 0, "sfx": "plak"}, {"t": 0.5, "sfx": "deklansor"}]},
    {"id": "breaking-news-flash", "group": "Belgesel & Tarih", "name": "Son Dakika Haber Kuşağı", "needs": "", "items": [
        {"t": 0, "graphic": "lower", "dur": 4.5, "style": {"title": "SON DAKİKA GELİŞMESİ", "sub": "CANLI YAYIN ANALİZİ"}},
        {"t": 0, "sfx": "haber-flas"}, {"t": 0.25, "sfx": "whoosh"}]},
    {"id": "anime-speed-impact", "group": "Oyun & meme", "name": "Anime Hız Tüneli & Vuruş", "needs": "clip", "items": [
        {"t": 0, "fx": "radial-speed", "dur": 1.8},
        {"t": 0, "sfx": "sub-drop"}, {"t": 0.15, "sfx": "vine-boom"}]},
    {"id": "noir-crime-doc", "group": "Sinema & Belgesel", "name": "Kara Film Alıntı & Tanık Kartı", "needs": "", "items": [
        {"t": 0, "fx": "noir-contrast", "dur": 4.0},
        {"t": 0, "graphic": "quote", "dur": 3.8, "style": {"title": "Gerçek her zaman gölgede saklanır.", "sub": "Arşiv Dosyası"}},
        {"t": 0, "sfx": "gerilim-vurdu"}]},
]
