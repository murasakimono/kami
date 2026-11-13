"""Kami Studio faz 5 efekt paketi (studio.FX'e eklenir).

Ilke: sayi doldurmak yerine gercek is goren efektler. "Duzelt" paketi bozuk cekimi kurtarir
(gurultu, sallanti, titreme, pus, karanlik), "Film" paketi bilinen film stoklarinin tonunu verir,
"Sosyal" paketi kisa video trendlerini karsilar. ff: ffmpeg zinciri (W/H/S yer tutucu), css/ov: onizleme.
"""
from __future__ import annotations

FX3 = {
    # ---- duzelt: telefon cekimini kurtar (onizlemede yalniz yaklasik; asil sonuc disa aktarimda)
    "denoise": {"name": "Gürültü azalt", "pack": "Düzelt", "ff": "hqdn3d=4:3:6:4.5", "css": "blur(.25px)", "ov": []},
    "deshake": {"name": "Sallantı azalt", "pack": "Düzelt", "ff": "deshake=rx=32:ry=32:edge=mirror", "css": "", "ov": []},
    "deflicker": {"name": "Işık titremesini gider", "pack": "Düzelt", "ff": "deflicker=size=7:mode=am", "css": "", "ov": []},
    "autolevel": {"name": "Otomatik ışık", "pack": "Düzelt", "ff": "normalize=blackpt=black:whitept=white:smoothing=24:independence=0.3",
                  "css": "contrast(1.08) brightness(1.03)", "ov": []},
    "dehaze": {"name": "Pus gider", "pack": "Düzelt", "ff": "colorlevels=rimin=0.06:gimin=0.06:bimin=0.06,eq=contrast=1.1:saturation=1.18",
               "css": "contrast(1.16) saturate(1.18)", "ov": []},
    "lowlight": {"name": "Karanlığı aç", "pack": "Düzelt", "ff": "curves=all='0/0 0.25/0.36 0.6/0.72 1/1',hqdn3d=3:2:4:3",
                 "css": "brightness(1.18) contrast(.95)", "ov": []},
    "skin": {"name": "Ten yumuşat", "pack": "Düzelt", "ff": "bilateral=sigmaS=5:sigmaR=0.06,eq=saturation=1.04",
             "css": "blur(.35px) saturate(1.04)", "ov": []},
    "clarity": {"name": "Netlik (detay)", "pack": "Düzelt", "ff": "unsharp=7:7:0.9:5:5:0,eq=contrast=1.04", "css": "contrast(1.06)", "ov": []},
    # ---- film stoklari (yaklasik tonlar)
    "portra": {"name": "Portra (sıcak ten)", "pack": "Film", "ff": "curves=all='0/0.04 0.5/0.52 1/0.96',colorbalance=rs=0.06:bs=-0.04:rm=0.05:gm=0.02:bm=-0.05,eq=saturation=0.92",
               "css": "sepia(.15) saturate(.95) contrast(.95)", "ov": []},
    "fuji": {"name": "Fuji (yeşil-camgöbeği)", "pack": "Film", "ff": "colorbalance=gs=0.05:bs=0.06:rh=-0.03:gh=0.03,curves=preset=lighter,eq=saturation=1.05",
             "css": "hue-rotate(-8deg) saturate(1.05) brightness(1.03)", "ov": []},
    "cinestill": {"name": "CineStill gece (halation)", "pack": "Film",
                  "ff": "split[h0][h1];[h1]colorchannelmixer=rr=1:gg=0.15:bb=0.1,gblur=sigma=12[h2];[h0][h2]blend=all_mode=screen:all_opacity=0.35,"
                        "colorbalance=bs=0.08:bm=0.05,eq=contrast=1.08",
                  "css": "contrast(1.08) saturate(1.1)", "ov": ["bloom"]},
    "kodachrome": {"name": "Kodachrome (doygun retro)", "pack": "Film", "ff": "curves=preset=strong_contrast,colorbalance=rs=0.08:bs=-0.06:rh=0.04,eq=saturation=1.3",
                   "css": "contrast(1.2) saturate(1.3) sepia(.1)", "ov": []},
    # ---- sosyal / kisa video
    "y2k": {"name": "Y2K parlak", "pack": "Sosyal", "ff": "colorbalance=rs=0.12:bs=0.18:gs=-0.06,split[y0][y1];[y1]gblur=sigma=8[y2];[y0][y2]blend=all_mode=screen:all_opacity=0.3,eq=saturation=1.3",
            "css": "saturate(1.3) hue-rotate(-12deg) brightness(1.06)", "ov": ["bloom"]},
    "disposable": {"name": "Tek kullanımlık kamera", "pack": "Sosyal", "ff": "eq=contrast=1.12:saturation=1.15:gamma_r=1.06,noise=alls=12:allf=t,vignette=PI/4.5",
                   "css": "contrast(1.12) saturate(1.15) sepia(.1)", "ov": ["grain", "vignette"]},
    "bluehour": {"name": "Mavi saat", "pack": "Sosyal", "ff": "colorbalance=rs=-0.08:bs=0.16:rh=0.08:bh=-0.04,eq=saturation=1.1:brightness=-0.02",
                 "css": "hue-rotate(10deg) saturate(1.1) brightness(.98)", "ov": ["blue-tint"]},
    "hdr-look": {"name": "HDR görünüm", "pack": "Sosyal", "ff": "unsharp=5:5:1.1,curves=preset=increase_contrast,eq=saturation=1.25",
                 "css": "contrast(1.18) saturate(1.25)", "ov": []},
}
