"""Kami Studio Dalga 7 (AtomX / Spunkram / Mister Horse / AEJuice / PluginPlay / Soundly / Envato uyumlu paket):
- FX_PACK2 (+30 efekt -> Optik/Cam, CRT/Dijital, Basili/Analog, VFX)
- TRANS_PACK2 + trans_in_pack2 (+22 gecis)
- SFX_PACK2 + SFX_CAT_PACK2 (+25 telifsiz FFmpeg sentezi)
- AUDIO_FIX_PACK2 + AUDIO_FIX_NAMES_PACK2 (+14 Soundly Place it akustik mekan & hoparlor profili)
- BEZIER_PACK2 (+8) / EQ_PACK2 (+6) / ZOOM_PACK2 (+10) / CAPTIONS_PACK2 (+6)
- CLIP_*_PACK2 / TEXT_*_PACK2 / TEMPLATES_PACK2 (+21) / RECIPES_PACK2 (+6)
"""
from __future__ import annotations

_CB = lambda **k: "colorbalance=" + ":".join(f"{p}={v}" for p, v in k.items())

FX_PACK2 = {
    # Optik & Cam (AEJuice Liquid Glass / PluginPlay Prism)
    "liquid-glass": {
        "name": "Sıvı Cam Kırılması (Liquid Glass)",
        "pack": "Optik",
        "ff": "split[lg0][lg1];[lg1]gblur=sigma=8,crop=iw-24:ih-24:12+10*sin(t*3):12+10*cos(t*2.4),scale=W:H[lg2];[lg0][lg2]blend=all_mode=overlay:all_opacity=0.62",
        "css": "contrast(1.08) saturate(1.16) brightness(1.04)",
        "ov": ["bloom", "rgb-soft"],
    },
    "prism-refract": {
        "name": "Prizma Işık Kırılması",
        "pack": "Optik",
        "ff": "rgbashift=rh=11:bh=-11:gv=5:bv=-5:edge=smear,eq=saturation=1.28:contrast=1.08",
        "css": "saturate(1.28) contrast(1.08)",
        "ov": ["rgb-strong", "bloom"],
    },
    "kaleidoscope-mirror": {
        "name": "Kaleydoskop Ayna",
        "pack": "Optik",
        "ff": "crop=iw/2:ih/2:0:0,split[km0][km1];[km1]hflip[km2];[km0][km2]hstack[kmt];[kmt]split[kmu][kmd];[kmd]vflip[kmv];[kmu][kmv]vstack,scale=W:H",
        "css": "saturate(1.22) contrast(1.12)",
        "ov": ["prism"],
    },
    "cracked-glass": {
        "name": "Çatlak Cam / Darbe",
        "pack": "Optik",
        "ff": "rgbashift=rh=6:bh=-6,unsharp=5:5:1.6:5:5:0,vignette=PI/4",
        "css": "contrast(1.22) saturate(0.92)",
        "ov": ["vignette", "rgb-soft"],
    },
    "lens-frost": {
        "name": "Buzlu Lens (Frost Halo)",
        "pack": "Optik",
        "ff": "split[lf0][lf1];[lf1]gblur=sigma=18,eq=brightness=0.06:saturation=0.85[lf2];[lf0][lf2]blend=all_mode=screen:all_opacity=0.4",
        "css": "brightness(1.06) contrast(0.95) saturate(0.9)",
        "ov": ["bloom"],
    },
    "chromatic-vignette": {
        "name": "Kromatik Vinyet",
        "pack": "Optik",
        "ff": "rgbashift=rh=-5:bh=5,vignette=PI/3.2,eq=contrast=1.08:saturation=1.14",
        "css": "contrast(1.1) saturate(1.14)",
        "ov": ["vignette", "rgb-soft"],
    },
    "anamorphic-flare": {
        "name": "Anamorfik Mavi Flare",
        "pack": "Optik",
        "ff": "split[af0][af1];[af1]avgblur=sizeX=38:sizeY=1," + _CB(rs=-0.12, gs=0.08, bs=0.35, bh=0.4) + "[af2];[af0][af2]blend=all_mode=screen:all_opacity=0.5",
        "css": "contrast(1.08) saturate(1.18)",
        "ov": ["bloom"],
    },
    # CRT & Dijital (AEJuice CRT / PluginPlay PixGlyph & Datamosh)
    "crt-pixel": {
        "name": "Piksel CRT Monitör",
        "pack": "CRT & Glitch",
        "ff": "scale=iw/3:ih/3:flags=neighbor,scale=W:H:flags=neighbor,drawgrid=w=4:h=4:t=1:c=black@0.32,rgbashift=rh=3:bh=-3",
        "css": "contrast(1.16) saturate(1.24)",
        "ov": ["scanlines", "rgb-soft"],
    },
    "pixel-sort-glitch": {
        "name": "Pixel Sort Şeritleri",
        "pack": "CRT & Glitch",
        "ff": "rgbashift=rh=14:bh=-14:edge=smear,avgblur=sizeX=22:sizeY=1,eq=contrast=1.22:saturation=1.35",
        "css": "contrast(1.22) saturate(1.35)",
        "ov": ["glitch-bars", "rgb-strong"],
    },
    "datamosh-smear": {
        "name": "Datamosh Hareket İzi",
        "pack": "CRT & Glitch",
        "ff": "tmix=frames=5:weights='1 2 4 2 1',rgbashift=rh=7:bh=-7:edge=smear,eq=contrast=1.18",
        "css": "contrast(1.16) saturate(1.2)",
        "ov": ["glitch-bars"],
    },
    "ascii-glyph": {
        "name": "Terminal / Matrix Izgara",
        "pack": "CRT & Glitch",
        "ff": "scale=iw/6:ih/6:flags=neighbor,scale=W:H:flags=neighbor," + _CB(rs=-0.35, gs=0.28, bs=-0.35, rm=-0.25, gm=0.25, bm=-0.25) + ",drawgrid=w=10:h=14:t=1:c=black@0.42",
        "css": "contrast(1.3) hue-rotate(85deg) saturate(1.4)",
        "ov": ["scanlines"],
    },
    "led-matrix": {
        "name": "LED Pano Ekranı",
        "pack": "CRT & Glitch",
        "ff": "scale=iw/4:ih/4:flags=neighbor,scale=W:H:flags=neighbor,drawgrid=w=6:h=6:t=1:c=black@0.45,eq=brightness=0.05:contrast=1.15:saturation=1.25",
        "css": "contrast(1.18) saturate(1.25)",
        "ov": ["scanlines"],
    },
    "cctv-night": {
        "name": "CCTV Gece Görüşü",
        "pack": "CRT & Glitch",
        "ff": "hue=s=0," + _CB(rs=-0.3, gs=0.32, bs=-0.25, rm=-0.2, gm=0.24, bm=-0.2) + ",noise=alls=22:allf=t,vignette=PI/3",
        "css": "grayscale(1) sepia(1) hue-rotate(68deg) saturate(2.4) contrast(1.2)",
        "ov": ["scanlines", "vignette"],
        "ass": "rec",
    },
    "thermal-cam": {
        "name": "Termal Kamera (Predator)",
        "pack": "CRT & Glitch",
        "ff": "eq=contrast=1.35:saturation=2.6,hue=h=190",
        "css": "contrast(1.4) saturate(2.5) hue-rotate(185deg)",
        "ov": ["scanlines"],
    },
    "cyber-grid-glow": {
        "name": "Siber Neon Izgara",
        "pack": "CRT & Glitch",
        "ff": _CB(rs=0.18, gs=-0.12, bs=0.32, bm=0.22) + ",drawgrid=w=64:h=64:t=1:c=#8B5CF6@0.18,eq=contrast=1.14:saturation=1.28",
        "css": "contrast(1.14) saturate(1.3) hue-rotate(-10deg)",
        "ov": ["bloom"],
    },
    # Basılı & Analog (AEJuice Paper / Newspaper / Mister Horse Film)
    "paper-rip": {
        "name": "Kağıt Doku (Kraft Grain)",
        "pack": "Basılı & Film",
        "ff": "eq=contrast=1.08:saturation=0.82:brightness=0.03,noise=alls=14:allf=u,vignette=PI/4.2",
        "css": "sepia(.18) contrast(1.08) saturate(0.86)",
        "ov": ["grain", "warm-tint"],
    },
    "newspaper-ink": {
        "name": "Gazete Baskı (Halftone S/B)",
        "pack": "Basılı & Film",
        "ff": "hue=s=0,eq=contrast=1.42:brightness=0.02,noise=alls=18:allf=u,vignette=PI/4",
        "css": "grayscale(1) contrast(1.45)",
        "ov": ["grain", "vignette"],
    },
    "risograph-grain": {
        "name": "Risograph Poster Dokusu",
        "pack": "Basılı & Film",
        "ff": "eq=contrast=1.24:saturation=1.32,noise=alls=16:allf=t," + _CB(rs=0.1, gs=-0.04, bs=0.14),
        "css": "contrast(1.24) saturate(1.32)",
        "ov": ["grain"],
    },
    "kodachrome-70": {
        "name": "Kodachrome 1970 Film",
        "pack": "Basılı & Film",
        "ff": "eq=contrast=1.18:saturation=1.12," + _CB(rs=0.12, gs=0.04, bs=-0.12, rh=0.14, bh=-0.1) + ",vignette=PI/4.5",
        "css": "sepia(.2) contrast(1.16) saturate(1.14)",
        "ov": ["warm-tint", "grain"],
    },
    "super8-gate": {
        "name": "Super 8mm Nostalji",
        "pack": "Basılı & Film",
        "ff": "eq=contrast=1.14:saturation=0.86," + _CB(rs=0.14, gs=0.06, bs=-0.14) + ",noise=alls=18:allf=t,vignette=PI/2.8",
        "css": "sepia(.28) contrast(1.14) saturate(0.88)",
        "ov": ["warm-tint", "grain", "vignette"],
    },
    "polaroid-fade": {
        "name": "Polaroid Soluk Pastel",
        "pack": "Basılı & Film",
        "ff": "eq=brightness=0.06:contrast=0.92:saturation=0.82," + _CB(rs=0.05, gs=0.05, bs=0.14),
        "css": "brightness(1.06) contrast(0.92) saturate(0.84) sepia(.12)",
        "ov": ["warm-tint"],
    },
    # VFX & Stilize (PluginPlay Outlines / InkBloom / Extendo / Spunkram)
    "neon-outline": {
        "name": "Neon Kenar Çizgisi (Edge Glow)",
        "pack": "VFX",
        "ff": "edgedetect=low=0.08:high=0.25:mode=colormix," + _CB(bs=0.35, rs=0.2, gs=0.05) + ",eq=contrast=1.35:saturation=1.8",
        "css": "contrast(1.45) saturate(1.9)",
        "ov": ["bloom"],
    },
    "glow-edge-bloom": {
        "name": "Parlak Kenar (Soft Edge Bloom)",
        "pack": "VFX",
        "ff": "split[ge0][ge1];[ge1]edgedetect=low=0.1:high=0.3,gblur=sigma=5[ge2];[ge0][ge2]blend=all_mode=screen:all_opacity=0.6",
        "css": "contrast(1.12) brightness(1.05)",
        "ov": ["bloom"],
    },
    "ink-bloom": {
        "name": "Mürekkep Yayılımı (Ink Bloom)",
        "pack": "VFX",
        "ff": "split[ib0][ib1];[ib1]gblur=sigma=12,eq=contrast=1.4:brightness=-0.06[ib2];[ib0][ib2]blend=all_mode=multiply:all_opacity=0.55",
        "css": "contrast(1.24) saturate(1.1)",
        "ov": ["vignette"],
    },
    "heat-wave": {
        "name": "Sıcaklık Dalgası (Heat Haze)",
        "pack": "VFX",
        "ff": "crop=iw-12:ih-12:6+5*sin(t*14):6+5*cos(t*11),scale=W:H," + _CB(rs=0.16, gs=0.04, bs=-0.12),
        "css": "sepia(.16) saturate(1.22) contrast(1.08)",
        "ov": ["warm-tint"],
    },
    "radial-speed": {
        "name": "Hız Tüneli (Action Lines)",
        "pack": "VFX",
        "ff": "split[rs0][rs1];[rs1]avgblur=sizeX=20:sizeY=20,eq=contrast=1.18[rs2];[rs0][rs2]blend=all_mode=screen:all_opacity=0.32,vignette=PI/2.8",
        "css": "contrast(1.14) saturate(1.16)",
        "ov": ["vignette"],
    },
    "underwater-caustic": {
        "name": "Su Altı Derin Mavi",
        "pack": "VFX",
        "ff": _CB(rs=-0.22, gs=0.14, bs=0.32, rm=-0.16, bm=0.25) + ",gblur=sigma=1.1,eq=contrast=1.08",
        "css": "hue-rotate(-25deg) saturate(1.24) contrast(1.08)",
        "ov": ["cool-tint", "bloom"],
    },
    "god-rays": {
        "name": "Tanrı Işıkları (Altın Süzme)",
        "pack": "VFX",
        "ff": "split[gr0][gr1];[gr1]gblur=sigma=26,eq=brightness=0.1," + _CB(rh=0.18, gh=0.1, bh=-0.08) + "[gr2];[gr0][gr2]blend=all_mode=screen:all_opacity=0.5",
        "css": "brightness(1.08) sepia(.14) saturate(1.18)",
        "ov": ["bloom", "warm-tint"],
    },
    "strobe-impact": {
        "name": "Strobe Kulüp Flaşı",
        "pack": "Edit",
        "ff": "eq=brightness='if(lt(mod(t-S,0.22),0.09),0.28,0)':contrast='if(lt(mod(t-S,0.22),0.09),1.28,1)':eval=frame",
        "css": "contrast(1.2) brightness(1.08)",
        "ov": ["flash"],
    },
    "sketch-pencil": {
        "name": "Kara Kalem Eskiz",
        "pack": "VFX",
        "ff": "edgedetect=low=0.09:high=0.22:mode=wires,negate,hue=s=0,eq=contrast=1.35",
        "css": "grayscale(1) contrast(2) brightness(1.15)",
        "ov": [],
    },
}


TRANS_PACK2 = {
    "morph-zoom": "Morph Zoom Geçişi",
    "liquid-drip": "Sıvı Eriyerek Açılış",
    "glass-shatter": "Cam Kırılması Geçişi",
    "crt-off": "CRT TV Kapanış Çizgisi",
    "crt-on": "CRT TV Açılış Çizgisi",
    "ink-splat": "Mürekkep Sıçrama Maskesi",
    "strip-blind-v": "Jaluzi Dikey Şeritler",
    "strip-blind-h": "Jaluzi Yatay Şeritler",
    "kaleido-spin": "Kaleydoskop Dönüş",
    "elastic-pop": "Elastik Sıçrama",
    "hyper-whip-r": "Hyper Whip Sağa Savurma",
    "hyper-whip-l": "Hyper Whip Sola Savurma",
    "prism-swipe": "Prizma RGB Kaydırma",
    "paper-tear-slide": "Kağıt Yırtık Geçiş",
    "glitch-tear-v": "Dikey Glitch Yırtığı",
    "burn-flash": "Film Yanığı (Light Burn)",
    "burn-orange": "Turuncu Ateş Geçişi",
    "zoom-elastic-out": "Geri Seken Hızlı Zoom",
    "squeeze-h": "Yatay Sıkıştırma (Squeeze)",
    "squeeze-v": "Dikey Sıkıştırma (Squeeze)",
    "checker-dissolve": "Dama Kare Açılışı",
    "tile-flip": "Karo Mozaik Dönüş",
}


def trans_in_pack2(kind: str, d: float, W: int, H: int, tag: str = "t", c0: float = 0.0, fps: int = 30) -> str:
    u = f"min(1,max(0,(t+{c0:.4f})/{d:.4f}))"
    e = f"(1-pow(1-{u},3))"
    U = f"min(1,max(0,(T+{c0:.4f})/{d:.4f}))"
    E = f"(1-pow(1-{U},3))"
    en = f"enable='lt(t,{max(0.001, d - c0):.4f})'"
    e_zp = f"(1-pow(1-min(1,max(0,(on/{fps}+{c0:.4f})/{d:.4f})),3))"
    if kind == "morph-zoom":
        return f"zoompan=z='max(1,1.65-0.65*{e_zp})':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={W}x{H}:fps={fps},format=rgba,gblur=sigma=8:{en}"
    if kind == "liquid-drip":
        wave = f"H*{E}+36*sin(X/28+T*8)*(1-{E})"
        return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lt(Y,{wave}),alpha(X,Y),0)':{en}"
    if kind == "glass-shatter":
        dx = f"28*(1-{E})*sin(trunc(X/48)*3+trunc(Y/48)*5)"
        return f"geq=r='r(clip(X+{dx},0,W-1),Y)':g='g(X,Y)':b='b(clip(X-{dx},0,W-1),Y)':a='if(gt({E},0.12),alpha(X,Y),0)':{en}"
    if kind == "crt-off":
        return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lt(abs(Y-H/2),max(3,H*0.5*(1-{E}))),alpha(X,Y),0)':{en}"
    if kind == "crt-on":
        return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lt(abs(Y-H/2),max(3,H*0.5*{E})),alpha(X,Y),0)':{en}"
    if kind == "ink-splat":
        rad = f"({E}*hypot(W,H)*0.6+28*sin(atan2(Y-H/2,X-W/2)*7)*(1-{E}))"
        return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lt(hypot(X-W/2,Y-H/2),{rad}),alpha(X,Y),0)':{en}"
    if kind == "strip-blind-v":
        return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lt(mod(X,W/8),{E}*(W/8)),alpha(X,Y),0)':{en}"
    if kind == "strip-blind-h":
        return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lt(mod(Y,H/6),{E}*(H/6)),alpha(X,Y),0)':{en}"
    if kind == "kaleido-spin":
        return f"rotate=a='(1-{e})*PI':c=black@0:{en},rgbashift=rh=10:bh=-10:{en}"
    e_zp = f"(1-pow(1-min(1,max(0,(on/{fps}+{c0:.4f})/{d:.4f})),3))"
    if kind == "elastic-pop":
        return f"zoompan=z='max(1,1.45-0.45*{e_zp})':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={W}x{H}:fps={fps},format=rgba"
    if kind == "hyper-whip-r":
        return f"pad=iw*2:ih:0:0:color=black@0,crop={W}:{H}:x='iw/2*(1-{e})':y=0,avgblur=sizeX=32:sizeY=2:{en}"
    if kind == "hyper-whip-l":
        return f"pad=iw*2:ih:iw:0:color=black@0,crop={W}:{H}:x='iw/2*{e}':y=0,avgblur=sizeX=32:sizeY=2:{en}"
    if kind == "prism-swipe":
        return f"pad=iw*2:ih:iw:0:color=black@0,crop={W}:{H}:x='iw/2*{e}':y=0,rgbashift=rh=18:bh=-18:edge=wrap:{en}"
    if kind == "paper-tear-slide":
        edge = f"(W*{E}+18*sin(Y/14))"
        return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lt(X,{edge}),alpha(X,Y),0)':{en}"
    if kind == "glitch-tear-v":
        dy = f"26*(1-{E})*sin(trunc(X/18)*5+T*60)"
        return f"geq=r='r(X,clip(Y+{dy},0,H-1))':g='g(X,Y)':b='b(X,clip(Y-{dy},0,H-1))':a='alpha(X,Y)':{en}"
    if kind == "burn-flash":
        return f"eq=brightness='0.75*(1-{u})':contrast='1+0.6*(1-{u})':eval=frame:{en}"
    if kind == "burn-orange":
        return f"eq=brightness='0.35*(1-{u})':gamma_r='1+1.2*(1-{u})':gamma_g='1+0.45*(1-{u})':gamma_b='1-0.5*(1-{u})':eval=frame:{en}"
    if kind == "zoom-elastic-out":
        return f"zoompan=z='max(1,1+0.45*(1-{e_zp}))':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={W}x{H}:fps={fps},format=rgba"
    if kind == "squeeze-h":
        return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lt(abs(X-W/2),{E}*W/2),alpha(X,Y),0)':{en}"
    if kind == "squeeze-v":
        return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lt(abs(Y-H/2),{E}*H/2),alpha(X,Y),0)':{en}"
    if kind == "checker-dissolve":
        cidx = "mod(floor(X/48)+floor(Y/48),2)"
        return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(gt({E},0.5*{cidx}),alpha(X,Y),0)':{en}"
    if kind == "tile-flip":
        return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lt(mod(X,W/6)+mod(Y,H/4),{E}*(W/6+H/4)),alpha(X,Y),0)':{en}"
    return "null"


SFX_PACK2 = {
    # Risers & Impacts (Spunkram / Soundly)
    "cinematic-braam": ("aevalsrc='0.9*(sin(2*PI*55*t)+0.6*sin(2*PI*110*t)+0.35*sgn(sin(2*PI*55.4*t)))*exp(-t*0.65)*(1-exp(-t*8))':d=2.8,lowpass=f=900,asoftclip=type=tanh", "Sinematik Braam (Trailer)"),
    "mega-boom": ("aevalsrc='1.1*sin(2*PI*(62-36*t*0.4)*t)*exp(-t*1.6)+0.5*(random(0)-0.5)*exp(-t*12)':d=2.4,asoftclip=type=tanh", "Mega Darbe Boom"),
    "metallic-slam": ("aevalsrc='0.8*(sin(2*PI*180*t)*exp(-t*7)+0.5*sin(2*PI*620*t)*exp(-t*14)+0.4*(random(0)-0.5)*exp(-t*18))':d=0.9,asoftclip=type=tanh", "Metalik Çarpma"),
    "glass-break-sfx": ("aevalsrc='0.75*(random(0)-0.5)*exp(-t*9)+0.4*sin(2*PI*4200*t)*exp(-t*22)+0.35*sin(2*PI*5800*(t-0.06))*exp(-(t-0.06)*18)*gte(t,0.06)':d=0.7,highpass=f=1200", "Cam Kırılması"),
    "thunder-crack": ("anoisesrc=d=2.2:c=brown:a=0.95,volume='(exp(-t*1.8)+0.7*exp(-(t-0.18)*2.5)*gte(t,0.18))':eval=frame,lowpass=f=850", "Gök Gürültüsü"),
    "reverse-cymbal": ("anoisesrc=d=1.6:c=white:a=0.8,highpass=f=2400,volume='pow(t/1.6,2.8)':eval=frame", "Ters Zil Yükselişi"),
    "riser-tension-4s": ("aevalsrc='0.55*sin(2*PI*(90*t+110*t*t))*pow(t/3.6,1.4)+0.3*(random(0)-0.5)*pow(t/3.6,2)':d=3.6,lowpass=f=4500", "Gerilim Riser (3.6sn)"),
    "riser-glitch": ("aevalsrc='0.5*sgn(sin(2*PI*(160+600*t+200*floor(random(0)*3))*t))*(t/1.8)':d=1.8,bandpass=f=1800:w=2400", "Glitch Yükseliş"),
    # UI / Tech / Interface
    "hud-beep": ("aevalsrc='0.7*sin(2*PI*1960*t)*exp(-t*28)':d=0.14", "HUD Kısa Bip"),
    "radar-ping": ("aevalsrc='0.65*sin(2*PI*1396.9*t)*exp(-t*3.2)+0.2*sin(2*PI*2793.8*t)*exp(-t*5)':d=1.2", "Radar Ping (Sonar)"),
    "typewriter-burst": ("aevalsrc='0.65*(random(0)-0.5)*exp(-mod(t,0.065)*110)':d=0.65,highpass=f=1600", "Hızlı Daktilo Dizisi"),
    "digital-lock": ("aevalsrc='0.65*sin(2*PI*980*t)*lt(t,0.08)+0.75*sin(2*PI*1470*t)*gte(t,0.1)*lt(t,0.22)':d=0.25", "Dijital Kilit Sesi"),
    "error-beep": ("aevalsrc='0.7*sgn(sin(2*PI*210*t))*(lt(t,0.12)+gte(t,0.18)*lt(t,0.34))':d=0.4,lowpass=f=1800", "Sistem Hata Bipi"),
    "unlock-chime": ("aevalsrc='0.6*sin(2*PI*1046.5*t)*exp(-t*8)*lt(t,0.12)+0.6*sin(2*PI*1318.5*(t-0.1))*exp(-(t-0.1)*6)*gte(t,0.1)':d=0.5", "Kilidi Açma Çanı"),
    "camera-zoom-whir": ("aevalsrc='0.55*sin(2*PI*(240+420*t)*t)*sin(PI*t/0.45)':d=0.45,bandpass=f=700:w=800", "Lens Motor Sesi"),
    "message-sent": ("aevalsrc='0.65*sin(2*PI*(780+620*t)*t)*exp(-t*18)':d=0.18", "Mesaj Gönderildi (Swoop)"),
    "message-received": ("aevalsrc='0.6*sin(2*PI*1174*t)*exp(-t*16)*lt(t,0.1)+0.65*sin(2*PI*1568*(t-0.09))*exp(-(t-0.09)*12)*gte(t,0.09)':d=0.35", "Mesaj Geldi (Ding-Pop)"),
    # Foley / Transition / Humor
    "paper-rip-sfx": ("anoisesrc=d=0.32:c=white:a=0.85,bandpass=f=2400:w=2200,volume='exp(-t*7)*sin(PI*t/0.32)':eval=frame", "Kağıt Yırtma"),
    "tape-stop": ("aevalsrc='0.75*sin(2*PI*(440*(1-0.82*t))*t)*exp(-t*2.2)':d=0.85", "Kaset Durma (Tape Stop)"),
    "tape-start": ("aevalsrc='0.7*sin(2*PI*(95+340*t)*t)*(1-exp(-t*8))*exp(-max(0,t-0.35)*3)':d=0.7", "Kaset Başlama"),
    "swish-air": ("anoisesrc=d=0.28:c=pink:a=0.85,bandpass=f=1500:w=1600,volume='sin(PI*t/0.28)^2':eval=frame", "Hızlı Hava Swish"),
    "whoosh-deep": ("anoisesrc=d=0.85:c=brown:a=0.95,lowpass=f=550,volume='sin(PI*t/0.85)^2':eval=frame", "Derin Bas Whoosh"),
    "sparkle-magic": ("aevalsrc='0.45*sin(2*PI*(1760+880*floor(mod(t*14,4)))*t)*exp(-t*2.4)':d=0.8", "Sihirli Işıltı (Sparkle)"),
    "countdown-tick": ("aevalsrc='0.8*sin(2*PI*1600*t)*exp(-mod(t,1.0)*45)':d=3.1", "Geri Sayım Tik (3sn)"),
    "coin-combo": ("aevalsrc='0.65*sin(2*PI*987.8*t)*lt(t,0.09)+0.7*sin(2*PI*1318.5*t)*gte(t,0.09)*exp(-(t-0.09)*7)':d=0.45", "Puan / Coin (+1)"),
}

SFX_CAT_PACK2 = {
    "cinematic-braam": "Dramatik & Gerilim", "mega-boom": "Vuruş & Darbe", "metallic-slam": "Vuruş & Darbe",
    "glass-break-sfx": "Foley & Efekt", "thunder-crack": "Dramatik & Gerilim", "reverse-cymbal": "Geçiş & Hareket",
    "riser-tension-4s": "Dramatik & Gerilim", "riser-glitch": "Geçiş & Hareket",
    "hud-beep": "UI & Oyun", "radar-ping": "UI & Oyun", "typewriter-burst": "UI & Oyun",
    "digital-lock": "UI & Oyun", "error-beep": "UI & Oyun", "unlock-chime": "UI & Oyun",
    "camera-zoom-whir": "Foley & Efekt", "message-sent": "UI & Oyun", "message-received": "UI & Oyun",
    "paper-rip-sfx": "Foley & Efekt", "tape-stop": "Geçiş & Hareket", "tape-start": "Geçiş & Hareket",
    "swish-air": "Geçiş & Hareket", "whoosh-deep": "Geçiş & Hareket", "sparkle-magic": "UI & Oyun",
    "countdown-tick": "UI & Oyun", "coin-combo": "UI & Oyun",
}

# Soundly Place it (40 mekan/hoparlor konseptinden en pratik 14 FFmpeg akustik DSP zinciri)
AUDIO_FIX_PACK2 = {
    "place-phone-1970": "highpass=f=620,lowpass=f=2400,equalizer=f=1300:t=q:w=1.8:g=5,acompressor=threshold=-20dB:ratio=6,asoftclip=type=tanh",
    "place-megaphone": "highpass=f=500,lowpass=f=3200,equalizer=f=1800:t=q:w=1.4:g=7,acompressor=threshold=-16dB:ratio=8:makeup=4,aecho=0.8:0.7:45:0.25",
    "place-am-radio": "highpass=f=450,lowpass=f=2600,acompressor=threshold=-18dB:ratio=5,tremolo=f=6:d=0.12",
    "place-car-cabin": "highpass=f=120,lowpass=f=6500,equalizer=f=240:t=q:w=1.2:g=3,aecho=0.85:0.7:18|34:0.22|0.12",
    "place-bathroom-tile": "highpass=f=140,aecho=0.8:0.88:32|68|115:0.42|0.28|0.18",
    "place-cathedral": "highpass=f=90,lowpass=f=11000,aecho=0.8:0.9:75|160|290|440:0.45|0.34|0.24|0.14",
    "place-subway-station": "highpass=f=110,lowpass=f=7800,aecho=0.8:0.85:60|140|240:0.45|0.32|0.2",
    "place-small-studio": "highpass=f=85,lowpass=f=16000,equalizer=f=220:t=q:w=1.2:g=-2,equalizer=f=4200:t=q:w=1.2:g=2.5,acompressor=threshold=-19dB:ratio=3:makeup=3",
    "place-stadium-pa": "highpass=f=180,lowpass=f=5500,aecho=0.8:0.86:95|220|380:0.5|0.35|0.22,acompressor=threshold=-16dB:ratio=5",
    "place-cassette-deck": "highpass=f=140,lowpass=f=5800,equalizer=f=320:t=q:w=1:g=2.5,acompressor=threshold=-19dB:ratio=3.5",
    "place-vinyl-crackle": "highpass=f=180,lowpass=f=4800,equalizer=f=1100:t=q:w=1:g=2,acompressor=threshold=-20dB:ratio=3",
    "place-intercom": "highpass=f=520,lowpass=f=2900,equalizer=f=1600:t=q:w=1.6:g=5,aecho=0.8:0.7:35:0.28,acompressor=threshold=-18dB:ratio=6",
    "place-underwater": "lowpass=f=360,lowpass=f=360,aecho=0.85:0.75:40|90:0.35|0.2,volume=0.85",
    "place-whisper-air": "highpass=f=220,equalizer=f=6500:t=q:w=1:g=5,acompressor=threshold=-24dB:ratio=4:makeup=4",
}

AUDIO_FIX_NAMES_PACK2 = {
    "place-phone-1970": "Mekan: Eski Telefon Ahizesi",
    "place-megaphone": "Mekan: Sokak Megafonu",
    "place-am-radio": "Mekan: AM Radyo Vericisi",
    "place-car-cabin": "Mekan: Araba İçi Akustik",
    "place-bathroom-tile": "Mekan: Fayans Banyo Yankısı",
    "place-cathedral": "Mekan: Büyük Salon / Katedral",
    "place-subway-station": "Mekan: Metro İstasyonu",
    "place-small-studio": "Mekan: Kayıt Kabini (Dead Room)",
    "place-stadium-pa": "Mekan: Stadyum Hoparlörü (PA)",
    "place-cassette-deck": "Mekan: Kaset Çalar",
    "place-vinyl-crackle": "Mekan: Eski Plak Sıcaklığı",
    "place-intercom": "Mekan: Apartman / Okul Diyafonu",
    "place-underwater": "Mekan: Su Altı Boğuk",
    "place-whisper-air": "Ses: Hava / ASMR Fısıltı",
}

BEZIER_PACK2 = {
    "expoIn": (0.7, 0.0, 0.84, 0.0),
    "expoInOut": (0.87, 0.0, 0.13, 1.0),
    "backOut": (0.34, 1.56, 0.64, 1.0),
    "backInOut": (0.68, -0.6, 0.32, 1.6),
    "circOut": (0.0, 0.55, 0.45, 1.0),
    "quintOut": (0.22, 1.0, 0.36, 1.0),
    "anticipate": (0.36, -0.45, 0.66, 1.0),
    "heavyPunch": (0.08, 1.28, 0.24, 1.0),
}

EQ_PACK2 = {
    "phone-cut": ("Telefon Bant Kesimi", [-18, -18, -12, -2, 6, 8, 5, -10, -18, -18]),
    "presence-air": ("Vokal Parlaklık & Hava", [-4, -3, -2, 0, 1, 2, 3, 4, 6, 7]),
    "warm-narrator": ("Sıcak Belgesel Anlatıcı", [2, 3, 2, -2, 0, 1, 2, 3, 2, 1]),
    "de-mud": ("Çamur Temizle (250Hz Cut)", [-2, -1, 0, -5, -3, 0, 2, 3, 2, 1]),
    "club-sub": ("Kulüp Sub Bas + Parlak", [7, 6, 4, 1, -2, -1, 1, 3, 4, 4]),
    "crisp-asmr": ("ASMR Mikrofon Detayı", [-8, -6, -4, -2, 0, 2, 4, 6, 7, 7]),
}

ZOOM_PACK2 = [
    {"id": "atom-punch", "name": "AtomX Sert Punch", "kf": [{"t": 0, "z": 1.0}, {"t": 0.1, "z": 1.42, "e": "out"}, {"t": 0.45, "z": 1.08}]},
    {"id": "atom-glide", "name": "AtomX Akıcı Yaklaş", "kf": [{"t": 0, "z": 1.0}, {"t": -0.001, "z": 1.24, "e": "inout"}]},
    {"id": "spunkram-slam", "name": "Spunkram İçe Çarpma", "kf": [{"t": 0, "z": 1.65}, {"t": 0.16, "z": 1.0, "e": "out"}, {"t": 0.3, "z": 1.06}, {"t": 0.5, "z": 1.0}]},
    {"id": "iman-slow-push", "name": "Iman Gadzhi Yavaş Push", "kf": [{"t": 0, "z": 1.04}, {"t": -0.001, "z": 1.19, "e": "out"}]},
    {"id": "corner-focus-tl", "name": "Sol Üst Köşeye Odak", "kf": [{"t": 0, "z": 1.0, "cx": 0.5, "cy": 0.5}, {"t": 0.4, "z": 1.7, "cx": 0.28, "cy": 0.28, "e": "inout"}]},
    {"id": "corner-focus-br", "name": "Sağ Alt Köşeye Odak", "kf": [{"t": 0, "z": 1.0, "cx": 0.5, "cy": 0.5}, {"t": 0.4, "z": 1.7, "cx": 0.72, "cy": 0.72, "e": "inout"}]},
    {"id": "crash-out", "name": "Hızlı Geri Açılış", "kf": [{"t": 0, "z": 1.85}, {"t": 0.24, "z": 1.0, "e": "out"}]},
    {"id": "pulse-3beat", "name": "3 Vuruşlu Ritim", "kf": [{"t": 0, "z": 1.0}, {"t": 0.12, "z": 1.18}, {"t": 0.26, "z": 1.04}, {"t": 0.42, "z": 1.24}, {"t": 0.65, "z": 1.06}]},
    {"id": "sway-cinematic", "name": "Sinematik Yatay Süzül", "kf": [{"t": 0, "z": 1.16, "cx": 0.42, "cy": 0.5}, {"t": 0.5, "z": 1.2, "cx": 0.58, "cy": 0.48, "e": "inout"}, {"t": -0.001, "z": 1.16, "cx": 0.46, "cy": 0.5}]},
    {"id": "flash-cut-zoom", "name": "Flaş Kesme Step", "kf": [{"t": 0, "z": 1.28}, {"t": 0.35, "z": 1.28}, {"t": 0.4, "z": 1.05}]},
]

CAPTIONS_PACK2 = {
    "iman-clean": {"name": "Iman Beyaz Temiz (Pop)", "b": "word", "st": {"font": "Poppins Bold", "size": 6.2, "color": "#FFFFFF", "highlight": "#2EE6A6", "outline": 4}},
    "spunkram-gold": {"name": "Spunkram Altın Vurgu", "b": "hormozi", "st": {"font": "Montserrat Black", "size": 6.8, "color": "#FFFFFF", "highlight": "#FFD60A", "outline": 6}},
    "newspaper-sub": {"name": "Gazete Serif Kutu", "b": "boxed", "st": {"font": "Kami Serif", "size": 5.5, "color": "#111111", "highlight": "#FFE600", "boxColor": "#F5F0E6"}},
    "neon-cyber-sub": {"name": "Cyber Neon Mor", "b": "neon", "st": {"font": "Chakra Petch", "size": 6.4, "color": "#F3E8FF", "highlight": "#C084FC", "outline": 4, "outlineColor": "#6D28D9"}},
    "podcast-pill": {"name": "Podcast Koyu Hap", "b": "boxed", "st": {"font": "Inter SemiBold", "size": 5.2, "color": "#FFFFFF", "highlight": "#38BDF8", "boxColor": "#0F172A"}},
    "comic-boom-sub": {"name": "Çizgi Roman Sarı", "b": "mrbeast", "st": {"font": "Bangers", "size": 7.6, "color": "#FFE600", "highlight": "#FF2E4C", "outline": 7}},
}

CLIP_IN_PACK2 = {
    "atom-whip-scale": {"name": "AtomX Whip Ölçek", "x": 0.65, "s": 0.55, "b": 18, "ease": "back", "a": 1},
    "liquid-drop-in": {"name": "Sıvı Damla Giriş", "y": -0.5, "sx": 0.7, "sy": 1.4, "ease": "elastic", "a": 1},
    "corner-peek-tl": {"name": "Sol Üstten Uzat", "x": -0.35, "y": -0.35, "s": 0.6, "ease": "out", "a": 1},
    "horizon-unfold": {"name": "Yatay Açılma", "sx": 0.05, "ease": "out", "a": 1},
    "vertical-unfold": {"name": "Dikey Açılma", "sy": 0.05, "ease": "out", "a": 1},
}
CLIP_OUT_PACK2 = {
    "atom-whip-out": {"name": "AtomX Sola Fırla", "x": -0.75, "s": 0.7, "b": 16, "ease": "linear", "a": 1},
    "horizon-fold": {"name": "Yatay Kapanma", "sx": 0.02, "ease": "out", "a": 1},
    "drop-spin-out": {"name": "Dönerek Aşağı Düş", "y": 0.7, "r": 22, "ease": "back", "a": 1},
    "shrink-vanish": {"name": "Küçülüp Kaybol", "s": 0.1, "b": 12, "a": 1},
}
CLIP_LOOP_PACK2 = {
    "breathe-scale": {"name": "Nefes Alan Ölçek", "grow": 0.07, "f": 0.45},
    "pendulum-swing": {"name": "Sarkaç Salınım", "r": 2.4, "f": 0.55},
    "handheld-cam": {"name": "El Kamerası (Vlog)", "x": 0.005, "y": 0.004, "f": 1.4, "r": 0.4},
    "neon-pulse": {"name": "Hafif Vurgu Nabzı", "grow": 0.04, "f": 1.2},
}

TEXT_IN_PACK2 = {
    "iman-drop": {"name": "Iman Temiz Düşüş", "dy": -36, "blur": 8, "fade": True},
    "elastic-squash": {"name": "Elastik Sıkışma", "sy": 180, "sx": 50, "fade": True},
    "words-slide": {"name": "Kelimeler Kayarak", "per_word": True, "dy": 22, "fade": True},
    "cyber-flicker": {"name": "Siber Kırpışma", "blur": 14, "fade": True},
}
TEXT_OUT_PACK2 = {
    "iman-lift": {"name": "Yukarı Silin", "dy": -32, "blur": 8, "fade": True},
    "squash-down": {"name": "Aşağı Sıkış", "sy": 0, "sx": 140, "fade": True},
    "words-fade": {"name": "Kelimeler Solsun", "per_word": True, "fade": True},
}
TEXT_LOOP_PACK2 = {
    "subtle-float": {"name": "Zarif Süzülme", "dy": 8, "period": 1800},
    "glitch-micro": {"name": "Mikro Sinyal", "jitter": 4, "period": 450},
    "pulse-soft": {"name": "Yumuşak Nabız", "scale": 106, "period": 1100},
}

TEMPLATES_PACK2 = [
    {"id": "newspaper-story", "group": "Belgesel & Bilgi", "name": "Gazete Kupürü Hikayesi", "items": [
        {"t": 0, "mode": "newspaper-ink", "dur": 4.0},
        {"t": 0, "graphic": "newspaper-cut", "dur": 4.0, "style": {"title": "BÜYÜK GELİŞME", "sub": "2026 · ÖZEL HABER RAPORU"}},
        {"t": 0, "sfx": "paper-rip-sfx"}]},
    {"id": "timeline-era", "group": "Belgesel & Bilgi", "name": "Tarih Zaman Çizelgesi", "items": [
        {"t": 0, "graphic": "history-timeline", "dur": 4.2, "style": {"title": "2018 → 2026", "sub": "Sürecin dönüm noktaları"}},
        {"t": 0, "sfx": "whoosh"}]},
    {"id": "chat-reveal", "group": "Sosyal & Mesaj", "name": "Sohbet Balonu Açılışı", "items": [
        {"t": 0, "graphic": "chat-bubble", "dur": 3.4, "style": {"title": "Bunu duydun mu?", "sub": "Az önce · Görüldü ✓✓"}},
        {"t": 0, "sfx": "message-received"}]},
    {"id": "neon-promo", "group": "Tasarım & VFX", "name": "Neon Tabela Tanıtım", "items": [
        {"t": 0, "mode": "cyber-grid-glow", "dur": 3.2},
        {"t": 0, "graphic": "neon-sign", "dur": 3.2, "style": {"title": "YENİ SERİ", "color": "#C084FC"}},
        {"t": 0, "sfx": "sparkle-magic"}]},
    {"id": "bar-chart-data", "group": "Belgesel & Bilgi", "name": "Animasyonlu Çubuk Grafik", "items": [
        {"t": 0, "graphic": "bar-chart", "dur": 3.8, "style": {"title": "BÜYÜME ORANI", "sub": "Ocak - Aralık (%86)"}},
        {"t": 0, "sfx": "unlock-chime"}]},
    {"id": "speaker-card", "group": "Vlog & belgesel", "name": "Podcast Konuşmacı Kartı", "items": [
        {"t": 0, "graphic": "podcast-card", "dur": 4.5, "style": {"title": "Konuk Adı", "sub": "Kurucu & Editör"}},
        {"t": 0, "sfx": "swoosh-sol"}]},
    {"id": "price-drop", "group": "Mağaza & Reklam", "name": "Kampanya İndirim Etiketi", "items": [
        {"t": 0, "graphic": "sale-badge", "dur": 3.0, "style": {"title": "%50 İNDİRİM", "sub": "SINIRLI SÜRE"}},
        {"t": 0, "sfx": "cash-register"}]},
    {"id": "crt-boot", "group": "Tasarım & VFX", "name": "Retro CRT Sistem Açılışı", "items": [
        {"t": 0, "mode": "crt-pixel", "dur": 2.8},
        {"t": 0, "graphic": "glitch-title", "dur": 2.8, "style": {"title": "SYSTEM ONLINE"}},
        {"t": 0, "sfx": "digital-lock"}]},
    {"id": "comment-pin", "group": "Sosyal & Mesaj", "name": "Sabitlenen İzleyici Yorumu", "items": [
        {"t": 0, "graphic": "social-comment", "dur": 4.0, "style": {"title": "@izleyici", "sub": "Bu sahne gerçekten efsane olmuş!"}},
        {"t": 0, "sfx": "pop"}]},
    {"id": "iman-point", "group": "Shorts", "name": "Iman Tarzı Vurgu Kutusu", "items": [
        {"t": 0, "graphic": "whiteboard-sketch", "dur": 3.2, "style": {"title": "3 ALTIN KURAL", "sub": "1. Hızlı Kanca  2. Ritim  3. Ses"}},
        {"t": 0, "sfx": "hud-beep"}]},
    {"id": "cctv-breach", "group": "Tasarım & VFX", "name": "CCTV Güvenlik Kamerası", "items": [
        {"t": 0, "mode": "cctv-night", "dur": 4.5},
        {"t": 0, "sfx": "radar-ping"}]},
    {"id": "arcade-level", "group": "Oyun & meme", "name": "Oyun Level Up (+XP)", "items": [
        {"t": 0, "mode": "flash-gold", "dur": 0.35},
        {"t": 0, "text": "LEVEL UP! +500 XP", "dur": 2.0, "style": {"font": "Press Start 2P", "size": 5.2, "anim": "bounce", "pos": "center", "color": "#2EE6A6"}},
        {"t": 0, "sfx": "coin-combo"}]},
    {"id": "cyberpunk-opener", "group": "YouTube", "name": "Siberpunk Giriş Paketi", "items": [
        {"t": 0, "mode": "prism-refract", "dur": 2.6},
        {"t": 0, "graphic": "glitch-title", "dur": 2.6, "style": {"title": "BÖLÜM 01"}},
        {"t": 0, "sfx": "cinematic-braam"}]},
    {"id": "strobe-impact", "group": "Oyun & meme", "name": "Beat Strobe Patlaması", "items": [
        {"t": 0, "mode": "strobe-impact", "dur": 1.6},
        {"t": 0, "sfx": "mega-boom"}]},
    {"id": "countdown-5s", "group": "Shorts", "name": "5 Saniye Geri Sayım Sayacı", "items": [
        {"t": 0, "graphic": "countdown-timer", "dur": 3.2, "style": {"from": 3, "to": 0, "color": "#FF2E4C"}},
        {"t": 0, "sfx": "countdown-tick"}]},
    {"id": "review-pros-cons", "group": "Belgesel & Bilgi", "name": "Önce / Sonra Karşılaştırma", "items": [
        {"t": 0, "graphic": "split-compare", "dur": 3.8, "style": {"title": "ÖNCE", "sub": "SONRA"}},
        {"t": 0, "sfx": "swish-air"}]},
    {"id": "map-route", "group": "Vlog & belgesel", "name": "Harita Rota Pin Kartı", "items": [
        {"t": 0, "graphic": "map-pin", "dur": 3.5, "style": {"title": "ANKARA → İSTANBUL", "sub": "450 KM · 4 SAAT"}},
        {"t": 0, "sfx": "whoosh-deep"}]},
    {"id": "breaking-alert", "group": "Shorts", "name": "Kırmızı Flaş Uyarı Damgası", "items": [
        {"t": 0, "graphic": "kinetic-stamp", "dur": 2.2, "style": {"title": "ONAYLANDI", "color": "#2EE6A6"}},
        {"t": 0, "sfx": "metallic-slam"}]},
    {"id": "notif-pop", "group": "Sosyal & Mesaj", "name": "Telefon Bildirim Kartı", "items": [
        {"t": 0, "graphic": "device-notif", "dur": 3.0, "style": {"title": "Yeni Bildirim", "sub": "Yükleme tamamlandı • Şimdi"}},
        {"t": 0, "sfx": "message-sent"}]},
    {"id": "audio-visualizer", "group": "Vlog & belgesel", "name": "Ses Dalgası Spektrumu", "items": [
        {"t": 0, "graphic": "audio-spec", "dur": 4.5, "style": {"title": "NOW PLAYING", "color": "#8B5CF6"}}]},
    {"id": "chapter-bar-tpl", "group": "YouTube", "name": "Modern Üst Bölüm Çubuğu", "items": [
        {"t": 0, "graphic": "chapter-bar", "dur": 3.4, "style": {"title": "02 · Kurgu Sırları", "color": "#8B5CF6"}},
        {"t": 0, "sfx": "hud-beep"}]},
]

RECIPES_PACK2 = {
    "iman_gadzhi_doc": {
        "id": "iman_gadzhi_doc",
        "name": "📰 Iman Gadzhi / Basılı Bilgi",
        "desc": "Kağıt dokusu, yavaş zoom, temiz beyaz alt yazı ve kayıt kabini net vokal zinciri.",
        "grade": {"con": 0.14, "sat": 0.96, "temp": 0.04},
        "zoom_preset": "iman-slow-push",
        "trans_in": "paper-tear-slide",
        "fx": ["paper-rip", "crisp-4k"],
        "audio_fx": ["place-small-studio"],
        "sub_style": "iman-clean",
        "shutter_angle": 180,
        "lufs": -14.0,
    },
    "liquid_glass_reel": {
        "id": "liquid_glass_reel",
        "name": "🫧 Sıvı Cam Estetiği (2026 Reel)",
        "desc": "Liquid Glass kırılması, akıcı zoom, prizma kaydırma ve ASMR net ses.",
        "grade": {"con": 0.12, "sat": 1.18},
        "zoom_preset": "atom-glide",
        "trans_in": "morph-zoom",
        "fx": ["liquid-glass", "anamorphic-flare"],
        "audio_fx": ["place-whisper-air"],
        "sub_style": "neon-cyber-sub",
        "shutter_angle": 240,
        "lufs": -13.0,
    },
    "crt_retro_horror": {
        "id": "crt_retro_horror",
        "name": "📺 CRT / Analog Korku",
        "desc": "Piksel CRT ekran, diyafon/radyo sesi ve CRT açılış geçişi.",
        "grade": {"con": 0.25, "sat": 0.78},
        "zoom_preset": "sway-cinematic",
        "trans_in": "crt-on",
        "fx": ["crt-pixel", "vhs-tracking"],
        "audio_fx": ["place-am-radio"],
        "sub_style": "newspaper-sub",
        "shutter_angle": 180,
        "lufs": -14.5,
    },
    "spunkram_hype_ad": {
        "id": "spunkram_hype_ad",
        "name": "⚡ Spunkram Hype Reklam",
        "desc": "AtomX sert punch zoom, hyper whip geçiş ve maksimum loudness (-10 LUFS).",
        "grade": {"con": 0.22, "sat": 1.28, "exp": 0.04},
        "zoom_preset": "atom-punch",
        "trans_in": "hyper-whip-r",
        "fx": ["prism-refract", "crisp-4k"],
        "audio_fx": ["hot-montage"],
        "sub_style": "spunkram-gold",
        "shutter_angle": 270,
        "lufs": -10.5,
    },
    "podcast_pro_clip": {
        "id": "podcast_pro_clip",
        "name": "🎙 Podcast Viral Kesit",
        "desc": "Kayıt kabini akustik zinciri, koyu hap altyazı ve hafif el kamerası hareketi.",
        "grade": {"con": 0.1, "sat": 1.08, "temp": 0.05},
        "zoom_preset": "iman-slow-push",
        "trans_in": "fade",
        "fx": ["clean-studio"],
        "anim_loop": "handheld-cam",
        "audio_fx": ["place-small-studio"],
        "sub_style": "podcast-pill",
        "shutter_angle": 180,
        "lufs": -14.0,
    },
    "vintage_70s_film": {
        "id": "vintage_70s_film",
        "name": "🎞 1970 Kodachrome Vlog",
        "desc": "Kodachrome film tonları, kaset çalar sıcaklığı ve yumuşak açılış.",
        "grade": {"con": 0.15, "sat": 1.06, "temp": 0.12},
        "zoom_preset": "sway-cinematic",
        "trans_in": "burn-orange",
        "fx": ["kodachrome-70", "god-rays"],
        "audio_fx": ["place-cassette-deck"],
        "sub_style": "doc-serif",
        "shutter_angle": 180,
        "lufs": -15.0,
    },
}
