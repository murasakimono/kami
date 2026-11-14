"""Kami Studio Dalga 4 (Pro & Viral) genisletilmis katalog paketi:
- FX_PRO (+22 efekt: halation, prism-split, neon-aura, crisp-4k, rgb-tear, crt-phosphor, vb.)
- TRANS_PRO + trans_in_pro (+12 gecis: page-curl, cube-l, cube-r, rgb-tear, zoom-spin, lens-flare, vb.)
- CLIP_IN_PRO / CLIP_OUT_PRO / CLIP_LOOP_PRO (+26 klip animasyonu)
- TEXT_IN_PRO / TEXT_OUT_PRO / TEXT_LOOP_PRO (+14 yazi animasyonu)
- ZOOM_PRO (+9 zoom sablonu)
- CAPTIONS_PRO (+6 altyazi stili)
- SFX_PRO + SFX_CAT_PRO (+18 telifsiz FFmpeg meme/fragmovie/gecis sesi)
- AUDIO_FIX_PRO (+4 ses efekti)
- TEMPLATES_PRO (+6 hazir kurgu sablonu)
- RECIPES_PRO (+6 viral recete)
"""
from __future__ import annotations

_CB = lambda **k: "colorbalance=" + ":".join(f"{p}={v}" for p, v in k.items())

FX_PRO = {
    # Işık & Aura
    "halation-pro": {
        "name": "Halation Pro (Kırmızı Halo)",
        "pack": "Işık",
        "ff": "split[hp0][hp1];[hp1]colorchannelmixer=rr=1.0:gg=0.12:bb=0.05,gblur=sigma=14,eq=brightness=-0.04[hp2];[hp0][hp2]blend=all_mode=screen:all_opacity=0.45",
        "css": "contrast(1.06) saturate(1.12)",
        "ov": ["bloom", "warm-tint"],
    },
    "prism-split": {
        "name": "Prizma Kırılması (RGB Edge)",
        "pack": "Işık",
        "ff": "rgbashift=rh=-8:bh=8:gv=-5:bv=3,eq=saturation=1.22:contrast=1.08",
        "css": "saturate(1.22) contrast(1.08)",
        "ov": ["rgb-strong", "bloom"],
    },
    "neon-aura": {
        "name": "Neon Aura (Siber Işık)",
        "pack": "Işık",
        "ff": _CB(rs=0.14, gs=-0.06, bs=0.28, rh=0.16, bh=0.24) + ",split[na0][na1];[na1]gblur=sigma=16,eq=saturation=1.5[na2];[na0][na2]blend=all_mode=screen:all_opacity=0.55",
        "css": "saturate(1.5) hue-rotate(-14deg) brightness(1.06)",
        "ov": ["bloom"],
    },
    "starburst-glint": {
        "name": "Yıldız Parlaması (Glint)",
        "pack": "Işık",
        "ff": "split[sb0][sb1];[sb1]avgblur=sizeX=24:sizeY=2,eq=brightness=0.12[sb2];[sb0][sb2]blend=all_mode=screen:all_opacity=0.42",
        "css": "brightness(1.08) contrast(1.06)",
        "ov": ["bloom"],
    },
    "flash-white-soft": {
        "name": "Yumuşak Beyaz Flaş",
        "pack": "Edit",
        "ff": "eq=brightness='max(0,0.55*(1-(t-S)/0.32))':eval=frame",
        "css": "brightness(1.12)",
        "ov": ["flash"],
    },
    "flash-gold": {
        "name": "Altın Vuruş Flaşı",
        "pack": "Edit",
        "ff": "eq=brightness='max(0,0.42*(1-(t-S)/0.26))':gamma_r='1+max(0,0.9*(1-(t-S)/0.26))':gamma_g='1+max(0,0.55*(1-(t-S)/0.26))':eval=frame",
        "css": "sepia(.3) saturate(1.4) brightness(1.1)",
        "ov": ["flash", "warm-tint"],
    },
    # Bozulma & Glitch & Retro
    "rgb-tear": {
        "name": "RGB Yırtılma (Signal Tear)",
        "pack": "Bozulma",
        "ff": "rgbashift=rh=12:bh=-12:edge=wrap,crop=iw-16:ih:8+8*sin(t*31):0,scale=W:H,noise=alls=14:allf=t",
        "css": "contrast(1.14) saturate(1.25)",
        "ov": ["rgb-strong", "glitch-bars"],
    },
    "vhs-tracking": {
        "name": "VHS Tracking Çizgisi",
        "pack": "Retro",
        "ff": "rgbashift=rh=-4:bh=4,drawbox=x=0:y='mod(t*ih*0.6,ih)':w=iw:h=16:c=white@0.25:t=fill,noise=alls=14:allf=t",
        "css": "saturate(1.15) contrast(1.05)",
        "ov": ["rgb", "scan", "vhs-jitter", "grain"],
    },
    "crt-phosphor": {
        "name": "CRT Fosfor Tarama",
        "pack": "Retro",
        "ff": "drawgrid=w=4:h=4:t=1:c=0x00ff88@0.18,lenscorrection=k1=0.14:k2=0.02,eq=contrast=1.18:saturation=1.15,vignette=PI/3.5",
        "css": "contrast(1.18) saturate(1.15)",
        "ov": ["scan", "vignette-hard"],
    },
    "freeze-trail": {
        "name": "Ghost Trail (Hareket İzi)",
        "pack": "Bozulma",
        "ff": "tmix=frames=5:weights='1 1 2 3 5',eq=saturation=1.12",
        "css": "saturate(1.12)",
        "ov": ["double"],
    },
    # Netlik & Sinematik & Düzeltme
    "crisp-4k": {
        "name": "4K Ultra Netlik (Crisp)",
        "pack": "Düzelt",
        "ff": "unsharp=5:5:1.4:5:5:0,eq=contrast=1.08:saturation=1.1",
        "css": "contrast(1.12) saturate(1.1)",
        "ov": ["crisp"],
    },
    "clean-studio": {
        "name": "Temiz Stüdyo Aydınlık",
        "pack": "Düzelt",
        "ff": "hqdn3d=2:2:4:4," + _CB(rm=0.04, gm=0.02, bm=-0.03) + ",eq=brightness=0.04:contrast=1.06:saturation=1.06",
        "css": "brightness(1.06) contrast(1.06) saturate(1.06)",
        "ov": [],
    },
    "teal-cinema": {
        "name": "Sinema Teal & Amber Pro",
        "pack": "Sinematik",
        "ff": _CB(rs=-0.1, bs=0.16, gs=0.04, rh=0.14, gh=0.04, bh=-0.14) + ",curves=preset=medium_contrast,eq=saturation=1.18",
        "css": "contrast(1.12) saturate(1.18) sepia(.12)",
        "ov": ["teal", "vignette"],
    },
    "emerald-mood": {
        "name": "Zümrüt Atmosfer",
        "pack": "Mevsim",
        "ff": _CB(rs=-0.08, gs=0.12, bs=0.04, gm=0.08) + ",eq=saturation=0.92:contrast=1.12,vignette=PI/4",
        "css": "hue-rotate(-16deg) contrast(1.12) saturate(.95)",
        "ov": ["vignette"],
    },
    "dark-luxury": {
        "name": "Koyu Lüks (İman Tarzı)",
        "pack": "Sinematik",
        "ff": _CB(rs=0.03, bs=-0.03) + ",eq=contrast=1.22:saturation=0.86:brightness=-0.06,vignette=PI/3.2",
        "css": "contrast(1.22) saturate(.86) brightness(.92)",
        "ov": ["vignette-hard"],
    },
    "vignette-oval": {
        "name": "Oval Sinema Vinyeti",
        "pack": "Sinematik",
        "ff": "vignette=PI/2.9",
        "css": "contrast(1.04)",
        "ov": ["vignette-hard"],
    },
    # Bulanıklık & Düzen & Çerçeve
    "whip-blur-v": {
        "name": "Dikey Savurma Bulanı",
        "pack": "Bulanık",
        "ff": "avgblur=sizeX=2:sizeY=20",
        "css": "blur(2.5px)",
        "ov": ["zoom"],
    },
    "radial-soft": {
        "name": "Yumuşak Odak Halo",
        "pack": "Bulanık",
        "ff": "split[rs0][rs1];[rs1]gblur=sigma=12[rs2];[rs0][rs2]blend=all_mode=screen:all_opacity=0.3",
        "css": "blur(.6px) brightness(1.06)",
        "ov": ["bloom"],
    },
    "duo-violet": {
        "name": "Çift Ton Mor-Camgöbeği",
        "pack": "Sanat",
        "ff": "hue=s=0," + _CB(rs=0.18, bs=0.38, gm=-0.1, rh=-0.12, gh=0.12, bh=0.22) + ",eq=contrast=1.2",
        "css": "grayscale(1) sepia(1) hue-rotate(220deg) saturate(2.8) contrast(1.2)",
        "ov": [],
    },
    "frame-rec": {
        "name": "REC Kırmızı Çerçeve",
        "pack": "Çerçeve",
        "ff": "drawbox=x=20:y=20:w=iw-40:h=ih-40:c=white@0.45:t=2,drawbox=x=44:y=42:w=16:h=16:c=0xff2a2a@0.95:t=fill",
        "css": "contrast(1.04)",
        "ov": ["frame-rec"],
    },
    "frame-916-blur": {
        "name": "9:16 Dikey Odak + Arka Blur",
        "pack": "Düzen",
        "ff": "split[fb0][fb1];[fb1]gblur=sigma=28,eq=brightness=-0.12[fb2];[fb0]crop=ih*9/16:ih:(iw-ih*9/16)/2:0[fb3];[fb2][fb3]overlay=(W-w)/2:0",
        "css": "",
        "ov": ["pillarbox-9x16"],
    },
    "vignette-neon": {
        "name": "Mor Neon Vinyet",
        "pack": "Parti",
        "ff": _CB(rs=0.16, bs=0.26) + ",vignette=PI/3.4,eq=saturation=1.25",
        "css": "saturate(1.25) hue-rotate(-10deg)",
        "ov": ["vignette", "bloom"],
    },
}

TRANS_PRO = {
    "page-curl": "Sayfa Çevirme",
    "cube-l": "3B Küp Sola",
    "cube-r": "3B Küp Sağa",
    "rgb-tear": "RGB Yırtılma Geçişi",
    "zoom-spin": "Dönerek Zoom",
    "lens-flare": "Mercek Parlaması (Flare)",
    "burn-wipe": "Yanarak Geçiş",
    "split-curtain": "İkiye Bölünme (Perde)",
    "glitch-snap": "Sert Glitch Atışı",
    "iris-in": "İris Odak Açılışı",
    "flash-warm": "Sıcak Altın Flaş",
    "whip-blur-fast": "Süper Hızlı Whip Blur",
}


def trans_in_pro(kind: str, d: float, W: int, H: int, tag: str = "t", c0: float = 0.0, fps: int = 30) -> str:
    u = f"min(1,max(0,(t+{c0:.4f})/{d:.4f}))"
    e = f"(1-pow(1-{u},3))"
    U = f"min(1,max(0,(T+{c0:.4f})/{d:.4f}))"
    E = f"(1-pow(1-{U},3))"
    en = f"enable='lt(t,{max(0.001, d - c0):.4f})'"
    if kind == "page-curl":
        return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lt(X/W+Y/(H*2),1.5*{E}),alpha(X,Y),0)':{en}"
    if kind in ("cube-l", "cube-r"):
        xs = f"(W/2+(X-W/2)/max(0.05,{E}))"
        shift = f"(1-{E})*W*{0.45 if kind == 'cube-l' else -0.45}"
        x2 = f"({xs}+({shift}))"
        inside = f"between({x2},0,W-1)*between(Y,0,H-1)"
        return f"geq=r='r({x2},Y)':g='g({x2},Y)':b='b({x2},Y)':a='if({inside},alpha({x2},Y),0)':{en}"
    if kind == "rgb-tear":
        dx = f"24*(1-{E})*sin(Y/12+T*40)"
        return (f"geq=r='r(clip(X+{dx},0,W-1),Y)':g='g(X,Y)':b='b(clip(X-{dx},0,W-1),Y)'"
                f":a='alpha(X,Y)':{en}")
    if kind == "zoom-spin":
        z = f"(1.6-0.6*{e})"
        ang = f"-(1-{e})*PI*0.75"
        return (f"scale=w='max(2,2*floor(iw*({z})/2))':h='max(2,2*floor(ih*({z})/2))':eval=frame,"
                f"crop={W}:{H},rotate=a='{ang}':c=black@0:{en}")
    if kind == "lens-flare":
        return f"eq=brightness='0.65*exp(-pow(({u}-0.15)*4,2))':gamma_r='1+0.8*(1-{u})':eval=frame:{en}"
    if kind == "burn-wipe":
        return (f"eq=brightness='0.4*(1-{u})':saturation='1+1.5*(1-{u})':eval=frame,"
                f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lt(X,W*{E}),alpha(X,Y),0)':{en}")
    if kind == "split-curtain":
        return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(gt(abs(X-W/2),(1-{E})*W/2),alpha(X,Y),0)':{en}"
    if kind == "glitch-snap":
        dx = f"26*(1-{E})*sin(trunc(Y/16)*7+T*55)"
        return (f"geq=r='r(clip(X+{dx},0,W-1),Y)':g='g(X,Y)':b='b(clip(X-{dx},0,W-1),Y)'"
                f":a='alpha(X,Y)':{en},noise=alls=30:allf=t:{en}")
    if kind == "iris-in":
        return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lt(hypot(X-W/2,Y-H/2),{E}*hypot(W,H)*0.55),alpha(X,Y),0)':{en}"
    if kind == "flash-warm":
        return f"eq=brightness='0.55*(1-{u})':gamma_r='1+1.1*(1-{u})':gamma_g='1+0.6*(1-{u})':eval=frame:{en}"
    if kind == "whip-blur-fast":
        return f"pad=iw*2:ih:iw:0:color=black@0,crop={W}:{H}:x='iw/2*{e}':y=0,avgblur=sizeX=24:sizeY=2:{en}"
    return "null"


CLIP_IN_PRO = {
    "snap-zoom-in": {"name": "Ani Snap Zoom", "s": 0.45, "ease": "back"},
    "rotate-drop": {"name": "Dönerek Düş", "y": -0.45, "r": -25, "ease": "bounce"},
    "glitch-slam": {"name": "Glitch Çarpma", "s": 1.45, "x": 0.04, "shake": 1, "a": 1},
    "swing-right": {"name": "Sağdan Sarkaç", "r": 28, "ease": "elastic"},
    "elastic-rise": {"name": "Elastik Yükseliş", "y": 0.25, "ease": "elastic", "a": 1},
    "blur-snap": {"name": "Hızlı Blur Açılış", "b": 34, "s": 1.18, "a": 1},
    "slide-up-bounce": {"name": "Alttan Zıplayarak", "y": 0.85, "ease": "bounce"},
    "flip-diagonal": {"name": "Çapraz Çevir (3B)", "sx": 0.0, "r": -12, "a": 1},
    "card-deal": {"name": "Kart Dağıtım", "x": -0.7, "y": -0.25, "r": -18, "ease": "back"},
    "warp-in": {"name": "Warp Çekim", "sx": 0.15, "sy": 1.85, "ease": "elastic"},
}

CLIP_OUT_PRO = {
    "snap-zoom-out": {"name": "Ani Uzaklaş", "s": 0.25, "a": 1},
    "glitch-vanish": {"name": "Glitch Kaybol", "x": 0.05, "shake": 1, "a": 1},
    "spin-away-ccw": {"name": "Ters Dönerek Git", "r": -270, "s": 0.1, "a": 1},
    "slide-down-back": {"name": "Aşağı Fırla", "y": 1.0, "ease": "back"},
    "blur-fade-fast": {"name": "Hızlı Blur Kaybol", "b": 36, "a": 1},
    "flip-away": {"name": "Katlanarak Git", "sy": 0.0, "a": 1},
    "drop-fade": {"name": "Düş & Kaybol", "y": 0.45, "r": 12, "a": 1},
    "whip-up": {"name": "Yukarı Savrul", "y": -1.1, "b": 28},
}

CLIP_LOOP_PRO = {
    "amv-float": {"name": "AMV Süzülme (Float)", "y": 0.022, "f": 0.8},
    "shake-impact": {"name": "Impact Titreşim", "x": 0.015, "y": 0.012, "f": 20},
    "swing-wide": {"name": "Geniş Salıncak", "r": 11, "f": 0.55},
    "heartbeat-duo": {"name": "Çift Kalp Nabzı", "beat": 0.11, "f": 1.5},
    "drift-zoom": {"name": "Sürekli Yavaş Yaklaş", "grow": 0.2},
    "wiggle-snap": {"name": "Wiggle Snap", "r": 5, "x": 0.008, "f": 3.5},
    "neon-breathe": {"name": "Yumuşak Neon Nefes", "s": 0.04, "f": 0.65},
    "shake-vertical": {"name": "Dikey Sarsıntı", "y": 0.014, "f": 15},
}

TEXT_IN_PRO = {
    "slide-pop": "Kayarak Pop",
    "blur-pop": "Bulanıktan Pop",
    "scale-drop": "Yukarıdan Çarp",
    "wave-in": "Dalgalanarak Gir",
    "cinema-track": "Genişleyerek (Sinema)",
    "glitch-flash": "Glitch + Flaş",
}

TEXT_OUT_PRO = {
    "blur-zoom": "Bulanık Büyü & Git",
    "drop-spin": "Dönerek Düş",
    "shrink-fast": "Hızla Küçül",
    "glitch-fade": "Glitch Karar",
}

TEXT_LOOP_PRO = {
    "bounce-soft": "Hafif Zıpla",
    "slam-pulse": "Sert Beat Nabzı",
    "float-tilt": "Süzül & Eğil",
    "chroma-jitter": "Hızlı Titreşim",
}

ZOOM_PRO = [
    {"id": "whip-snap-zoom", "name": "Whip Çarpma (1.55x -> 1x)", "kf": [{"t": 0, "z": 1.55, "e": "out"}, {"t": 0.18, "z": 1.0, "e": "inout"}]},
    {"id": "slow-creeper", "name": "Gerilim Yaklaş (1.0 -> 1.32x)", "kf": [{"t": 0, "z": 1.0}, {"t": -0.001, "z": 1.32, "e": "in"}]},
    {"id": "heartbeat-triple", "name": "Üçlü Nabız Vuruşu", "kf": [{"t": 0, "z": 1}, {"t": 0.08, "z": 1.14, "e": "out"}, {"t": 0.22, "z": 1.0}, {"t": 0.35, "z": 1.18, "e": "out"}, {"t": 0.5, "z": 1.0}, {"t": 0.62, "z": 1.24, "e": "out"}, {"t": 0.85, "z": 1.0}]},
    {"id": "ken-burns-center", "name": "Ken Burns Merkez (1.0 -> 1.22x)", "kf": [{"t": 0, "z": 1.0, "cx": 0.5, "cy": 0.5}, {"t": -0.001, "z": 1.22, "cx": 0.5, "cy": 0.45, "e": "inout"}]},
    {"id": "drop-slam", "name": "Beat Drop Çarpma (1 -> 1.75x)", "kf": [{"t": 0, "z": 1}, {"t": 0.07, "z": 1.75, "e": "out"}, {"t": 0.35, "z": 1.2, "e": "inout"}]},
    {"id": "bounce-settle", "name": "Yaylanarak Otur", "kf": [{"t": 0, "z": 1.45}, {"t": 0.14, "z": 1.04, "e": "out"}, {"t": 0.24, "z": 1.12}, {"t": 0.38, "z": 1.0}]},
    {"id": "tilt-left-pan", "name": "Sol Köşe Odak (1.45x)", "kf": [{"t": 0, "z": 1, "cx": 0.5, "cy": 0.5}, {"t": 0.5, "z": 1.45, "cx": 0.3, "cy": 0.45, "e": "inout"}]},
    {"id": "tilt-right-pan", "name": "Sağ Köşe Odak (1.45x)", "kf": [{"t": 0, "z": 1, "cx": 0.5, "cy": 0.5}, {"t": 0.5, "z": 1.45, "cx": 0.7, "cy": 0.45, "e": "inout"}]},
    {"id": "micro-pump-duo", "name": "Çift Mikro Pump", "kf": [{"t": 0, "z": 1}, {"t": 0.06, "z": 1.15, "e": "out"}, {"t": 0.16, "z": 1.02}, {"t": 0.24, "z": 1.18, "e": "out"}, {"t": 0.38, "z": 1.0}]},
]

CAPTIONS_PRO = {
    "amv-glow": {"name": "AMV Parlak Söz", "b": "neon", "st": {"font": "Anton", "glowColor": "#A855F7", "color": "#FFFFFF", "size": 8}},
    "roblox-pop": {"name": "Roblox Renkli Pop", "b": "mrbeast", "st": {"font": "Baloo 2 ExtraBold", "highlight": "#00E5FF", "perLine": 2}},
    "subzero-ice": {"name": "Buz Mavisi Vurgu", "b": "hormozi", "st": {"font": "Montserrat Black", "highlight": "#38BDF8", "perLine": 3}},
    "doc-serif": {"name": "Belgesel Altın Serif", "b": "cinema", "st": {"font": "Kami Serif", "color": "#FDE68A", "size": 5.8}},
    "meme-stroke": {"name": "Kalın Siyah Meme", "b": "mrbeast", "st": {"font": "Archivo Black", "highlight": "#FF3B30", "perLine": 2, "bold": False}},
    "cyber-cyan": {"name": "Siber Camgöbeği", "b": "neon", "st": {"font": "Audiowide", "glowColor": "#00F5D4", "color": "#E0FBFC", "size": 7}},
}

SFX_PRO = {
    "metal-pipe": ("aevalsrc='0.7*(sin(2*PI*920*t)+0.8*sin(2*PI*1490*t)+0.65*sin(2*PI*2210*t)+0.5*sin(2*PI*3120*t))*exp(-t*2.1)+0.35*(random(0)-0.5)*exp(-t*35)':d=2.2,aecho=0.8:0.7:28|52:0.5|0.35,asoftclip=type=tanh", "Metal Boru (Meme)"),
    "rizz-synth": ("aevalsrc='0.45*sin(2*PI*(220+8*t)*t)*sin(PI*min(1,t/1.8))+0.3*sin(2*PI*440*t)*exp(-t*0.8)+0.2*sin(2*PI*660*t)*exp(-t*1.1)':d=2.0,aecho=0.8:0.6:60|120:0.45|0.3", "Rizz Yükseliş (Synth)"),
    "boing-spring": ("aevalsrc='0.85*sin(2*PI*(260+180*sin(2*PI*14*t)*exp(-t*2.5))*t)*exp(-t*2.2)':d=0.95", "Yaylı Zıplama (Boing)"),
    "slide-whistle": ("aevalsrc='0.7*sin(2*PI*(420+900*sin(PI*t/1.1))*t)*sin(PI*t/1.1)':d=1.1", "Kaygan Düdük (Slide)"),
    "sad-violin": ("aevalsrc='0.5*(sin(2*PI*440*t)*(1+0.012*sin(2*PI*5.5*t))*lt(t,0.7)+sin(2*PI*415.3*t)*gte(t,0.72)*lt(t,1.35)+sin(2*PI*392*t)*gte(t,1.38))*exp(-max(0,t-1.6)*2.5)':d=2.4,lowpass=f=2400", "Dramatik Keman"),
    "anime-wow": ("aevalsrc='0.65*sin(2*PI*(520+420*exp(-t*6)+120*sin(2*PI*9*t))*t)*sin(PI*min(1,t/0.85))*exp(-t*1.6)':d=0.85,aecho=0.7:0.5:35:0.35", "Anime Şaşkınlık"),
    "error-xp": ("aevalsrc='0.7*(sin(2*PI*330*t)+0.45*sin(2*PI*660*t))*exp(-t*5)*lt(t,0.18)+0.75*(sin(2*PI*247*t)+0.4*sin(2*PI*494*t))*exp(-(t-0.18)*3.8)*gte(t,0.18)':d=0.75", "Sistem Hata Sesi"),
    "crowd-gasp": ("anoisesrc=d=0.85:c=pink:a=0.95,bandpass=f=1100:w=900,volume='26*sin(PI*t/0.85)^1.4':eval=frame,alimiter=limit=0.92", "Şaşkınlık Nefesi (Gasp)"),
    "vine-reverb": ("aevalsrc='1.0*sin(2*PI*(66-26*t)*t)*exp(-t*2.6)+0.35*sin(2*PI*132*t)*exp(-t*6)':d=2.2,aecho=0.8:0.85:45|110|190:0.55|0.4|0.25,asoftclip=type=tanh", "Vine Boom (Uzun Yankı)"),
    "mehter-hit": ("aevalsrc='1.1*sin(2*PI*(52-18*t)*t)*exp(-t*2.8)+0.4*(random(0)-0.5)*exp(-t*18)':d=1.6,aecho=0.8:0.7:40|95:0.45|0.25,asoftclip=type=tanh", "Kös / Mehter Vuruşu"),
    "sniper-bolt": ("aevalsrc='0.85*(random(0)-0.5)*exp(-t*120)*lt(t,0.05)+0.7*sin(2*PI*1800*(t-0.08))*exp(-(t-0.08)*80)*gte(t,0.08)*lt(t,0.16)+0.85*(random(0)-0.5)*exp(-(t-0.19)*90)*gte(t,0.19)':d=0.35", "Sniper Kurma Sesi"),
    "sub-impact-whoosh": ("anoisesrc=d=0.9:c=pink:a=0.7,bandpass=f=900:w=1200,volume='exp(-abs(t-0.32)*9)':eval=frame[w];aevalsrc='1.0*sin(2*PI*(62-20*max(0,t-0.3))*t)*exp(-max(0,t-0.3)*3.5)*gte(t,0.3)':d=1.4,asoftclip=type=tanh[b];[w][b]amix=inputs=2:normalize=0", "Whoosh + Sub Darbe"),
    "tape-stop": ("aevalsrc='0.75*sin(2*PI*max(30,520*(1-t/0.85))*t)*exp(-t*1.2)+0.25*(random(0)-0.5)*exp(-t*4)':d=0.9,lowpass=f=2400", "Kaset Durma (Tape Stop)"),
    "rewind-scratch": ("aevalsrc='0.7*sin(2*PI*(220+980*(t/0.55))*t)*(1-t/0.55)+0.35*(random(0)-0.5)':d=0.55,highpass=f=450,lowpass=f=3600,volume=1.2,asoftclip=type=tanh", "Hızlı Geri Sarma"),
    "glass-shatter": ("aevalsrc='0.9*(random(0)-0.5)*exp(-t*7)+0.5*(sin(2*PI*4200*t)+sin(2*PI*5600*t))*exp(-t*12)':d=0.75,highpass=f=1600", "Cam Kırılması"),
    "cyber-zap": ("aevalsrc='0.85*sin(2*PI*(2400*exp(-t*9))*t)*exp(-t*7)':d=0.38,asoftclip=type=tanh", "Siber Lazer Zap"),
    "bass-riser-fast": ("aevalsrc='0.75*sin(2*PI*(55+220*(t/1.2)^2)*t)*(t/1.2)+0.3*(random(0)-0.5)*(t/1.2)':d=1.2,asoftclip=type=tanh", "Hızlı Bas Riser"),
    "coin-collect": ("aevalsrc='0.65*sin(2*PI*987.8*t)*lt(t,0.09)+0.65*sin(2*PI*1318.5*t)*gte(t,0.09)*exp(-(t-0.09)*9)':d=0.48", "Oyun Altın Sesi"),
}

SFX_CAT_PRO = {
    "metal-pipe": "Meme & Shitpost",
    "rizz-synth": "Meme & Shitpost",
    "boing-spring": "Meme & Shitpost",
    "slide-whistle": "Meme & Shitpost",
    "sad-violin": "Dramatik & Gerilim",
    "anime-wow": "Meme & Shitpost",
    "error-xp": "UI & Oyun",
    "crowd-gasp": "Meme & Shitpost",
    "vine-reverb": "Meme & Shitpost",
    "mehter-hit": "Vuruş & Darbe",
    "sniper-bolt": "Vuruş & Darbe",
    "sub-impact-whoosh": "Geçiş & Hareket",
    "tape-stop": "Geçiş & Hareket",
    "rewind-scratch": "Geçiş & Hareket",
    "glass-shatter": "Vuruş & Darbe",
    "cyber-zap": "UI & Oyun",
    "bass-riser-fast": "Dramatik & Gerilim",
    "coin-collect": "UI & Oyun",
}

AUDIO_FIX_PRO = {
    "concert-hall": "aecho=0.8:0.88:55|115|180:0.42|0.3|0.18",
    "underwater": "lowpass=f=380,aecho=0.7:0.6:35:0.35,volume=0.85",
    "compressor-punch": "acompressor=threshold=-16dB:ratio=5:attack=2:release=70:makeup=6,alimiter=limit=0.95",
    "walkie-crush": "highpass=f=600,lowpass=f=2400,acrusher=bits=6:mode=lin:aa=1",
}
AUDIO_FIX_NAMES_PRO = {
    "concert-hall": "Konser Salonu (Geniş Yankı)",
    "underwater": "Su Altı Boğuk",
    "compressor-punch": "Sert Punch Kompresör",
    "walkie-crush": "Lo-Fi / Bitcrush Telsiz",
}

TEMPLATES_PRO = [
    {"id": "shorts-countdown", "group": "Shorts", "name": "3-2-1 Geri Sayım Hook", "items": [
        {"t": 0.0, "text": "3", "dur": 0.45, "style": {"font": "Anton", "size": 16, "anim": "pop", "pos": "center", "color": "#FFE600"}},
        {"t": 0.45, "text": "2", "dur": 0.45, "style": {"font": "Anton", "size": 16, "anim": "pop", "pos": "center", "color": "#FF6B00"}},
        {"t": 0.90, "text": "1", "dur": 0.45, "style": {"font": "Anton", "size": 18, "anim": "pop", "pos": "center", "color": "#FF2E88"}},
        {"t": 0.0, "sfx": "pop"}, {"t": 0.45, "sfx": "pop"}, {"t": 0.90, "sfx": "vine-boom"}]},
    {"id": "yt-subscribe-bar", "group": "YouTube", "name": "Alt Bant Takip Çağrısı", "items": [
        {"t": 0, "graphic": "lower", "dur": 4.0, "style": {"title": "BEĞEN & ABONE OL", "sub": "Bildirimleri açmayı unutma"}},
        {"t": 0, "sfx": "zil"}]},
    {"id": "game-combo", "group": "Oyun & meme", "name": "Combo x2 Hit", "items": [
        {"t": 0, "mode": "flash-gold", "dur": 0.35},
        {"t": 0, "text": "COMBO x2!", "dur": 1.1, "style": {"font": "Bangers", "size": 13, "anim": "bounce", "pos": "custom", "x": .5, "y": .35, "color": "#FFE600", "outline": 7}},
        {"t": 0, "sfx": "sniper-bolt"}]},
    {"id": "amv-beat-flash", "group": "Oyun & meme", "name": "AMV Beat Flaş + Neon", "items": [
        {"t": 0, "mode": "neon-aura", "dur": 0.65},
        {"t": 0, "mode": "flash-white-soft", "dur": 0.25},
        {"t": 0, "sfx": "sub-impact-whoosh"}]},
    {"id": "doc-year-stamp", "group": "Vlog & belgesel", "name": "Tarih / Yıl Damgası", "items": [
        {"t": 0, "text": "2026", "dur": 2.4, "style": {"font": "Special Elite", "size": 10, "anim": "type", "pos": "center", "color": "#FDE68A", "outline": 4}},
        {"t": 0, "sfx": "daktilo"}]},
    {"id": "meme-record-freeze", "group": "Oyun & meme", "name": "Plak Durma + Şok (Lo-Fi)", "items": [
        {"t": 0, "mode": "meme-muffle-bw", "dur": 1.6},
        {"t": 0, "text": "NE?!", "dur": 1.4, "style": {"font": "Impact", "size": 15, "anim": "shake", "pos": "center", "color": "#FFFFFF", "outline": 9, "bold": False}},
        {"t": 0, "sfx": "record-scratch"}]},
]

RECIPES_PRO = {
    "amv_flow": {
        "id": "amv_flow",
        "name": "🌀 AMV Flow (Neon Aura + Whip)",
        "desc": "Neon aura parıltısı, yüksek doygunluk, 270° shutter blur ve whip snap çarpma zoom.",
        "grade": {"con": 0.24, "sat": 1.35, "exp": 0.02},
        "zoom_preset": "whip-snap-zoom",
        "trans_in": "whip",
        "fx": ["neon-aura", "prism-split"],
        "audio_fx": ["compressor-punch"],
        "sub_style": "amv-glow",
        "shutter_angle": 270,
        "lufs": -12.5,
    },
    "valorant_ace": {
        "id": "valorant_ace",
        "name": "🎯 Valorant / CS2 Ace Crisp (4K)",
        "desc": "4K Ultra Netlik, RGB yırtılma geçişi, beat drop zoom ve sert punch kompresör.",
        "grade": {"con": 0.2, "sat": 1.25},
        "zoom_preset": "drop-slam",
        "trans_in": "rgb-tear",
        "fx": ["crisp-4k", "whip-blur"],
        "audio_fx": ["compressor-punch"],
        "sub_style": "none",
        "shutter_angle": 300,
        "lufs": -11.0,
    },
    "tr_vlog_fast": {
        "id": "tr_vlog_fast",
        "name": "🎬 Hızlı TR Vlog (Stüdyo & Altın)",
        "desc": "Temiz stüdyo aydınlatması, yumuşak dolly yaklaşma ve net konuşma ses zinciri.",
        "grade": {"con": 0.1, "sat": 1.12, "temp": 0.06, "exp": 0.04},
        "zoom_preset": "dolly-in",
        "trans_in": "fade",
        "fx": ["crisp-4k", "clean-studio"],
        "audio_fx": ["voice"],
        "sub_style": "poppins-pill",
        "shutter_angle": 180,
        "lufs": -14.0,
    },
    "brainrot_max": {
        "id": "brainrot_max",
        "name": "🧠 Brainrot / TikTok Hızlı Kanca",
        "desc": "Süper hızlı bounce zoom, Roblox pop altyazı ve maksimum loudness (-9.5 LUFS).",
        "grade": {"con": 0.18, "sat": 1.32, "exp": 0.05},
        "zoom_preset": "micro-pump-duo",
        "trans_in": "pop-in",
        "anim_loop": "shake-impact",
        "audio_fx": ["hot-montage"],
        "sub_style": "roblox-pop",
        "shutter_angle": 180,
        "lufs": -9.5,
    },
    "documentary_film": {
        "id": "documentary_film",
        "name": "🎞 Belgesel Sinema (Halation + Serif)",
        "desc": "Halation Pro kırmızı film halosu, oval vinyet, Ken Burns ve zarif belgesel serif altyazı.",
        "grade": {"con": 0.16, "sat": 0.94, "temp": -0.04},
        "zoom_preset": "ken-burns-center",
        "trans_in": "wipe-soft",
        "fx": ["halation-pro", "vignette-oval"],
        "audio_fx": ["voice"],
        "sub_style": "doc-serif",
        "shutter_angle": 180,
        "lufs": -14.0,
    },
    "aesthetic_lofi": {
        "id": "aesthetic_lofi",
        "name": "☕ Lo-Fi Estetik (Pastel + Yumuşak Halo)",
        "desc": "Yumuşak odak halosu, sıcak pastel tonlar ve yavaş nefes zoom.",
        "grade": {"con": -0.04, "sat": 0.85, "temp": 0.08, "exp": 0.04},
        "zoom_preset": "breath",
        "trans_in": "fade",
        "fx": ["radial-soft", "fadefilm"],
        "audio_fx": [],
        "sub_style": "elegant",
        "shutter_angle": 180,
        "lufs": -16.0,
    },
}
