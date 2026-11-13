"""Kami Studio güncel Türkçe meme, slow-motion AI böcek, shitpost ve ses paketi.

Bu dosya tek doğruluk kaynağı olarak şunları içerir:
- SFX_TR_MEME / SFX_CAT_TR_MEME: FFmpeg ile üretilen telifsiz meme/shitpost ses efektleri (+18)
- FX_TR_MEME: Slow-Mo AI Böcek, 2000'ler TV, kulak patlatan fry, 240p cursed, racon noir (+5)
- TEMPLATES_TR_MEME: Tek tıkla zaman çizelgesine eklenen TR meme & shitpost şablonları (+5)
- RECIPES_TR_MEME: Güncel TR viral reçeteler (AI Böcek Slow-Mo, Brainrot 2026, Racon, Earrape) (+4)
- TR_MEME_SOUNDS: Doğrulanmış canlı Myinstants TR + global meme ses efektleri kataloğu (kategorili)
- TR_MEME_VIDEOS: Doğrulanmış YouTube Türkçe yeşil ekran, AI hamam böceği ve shitpost derleme klipleri
- AI_MEME_PROMPTS: Gemini / Veo / Flow için hazır AI Böcek & Türkçe meme video promptları
"""
from __future__ import annotations

SFX_TR_MEME: dict[str, tuple[str, str]] = {
    "slowmo-drop": (
        "anoisesrc=d=1.1:c=pink:a=0.75,lowpass=f=1200,volume='exp(-abs(t-0.35)*6)':eval=frame[w];"
        "aevalsrc='1.05*sin(2*PI*(110*exp(-t*1.9))*t)*exp(-t*1.8)':d=1.9,asoftclip=type=tanh[b];"
        "[w][b]amix=inputs=2:normalize=0",
        "AI Böcek Slow-Mo Düşüş",
    ),
    "slowmo-choir": (
        "aevalsrc='0.35*(sin(2*PI*220*t)+0.8*sin(2*PI*277.18*t)+0.75*sin(2*PI*329.63*t)+0.5*sin(2*PI*110*t))*"
        "(1+0.02*sin(2*PI*5*t))*sin(PI*min(1,t/2.6))':d=2.6,lowpass=f=2200,aecho=0.8:0.88:60|130:0.45|0.3",
        "Slow-Mo Dramatik Koro",
    ),
    "bass-earrape-hit": (
        "aevalsrc='1.4*sin(2*PI*(58-24*t)*t)*exp(-t*2.6)+0.5*(random(0)-0.5)*exp(-t*12)':d=1.3,"
        "asoftclip=type=tanh,volume=1.8",
        "Patlak Shitpost Bass",
    ),
    "censor-bleep": (
        "aevalsrc='0.75*sin(2*PI*1000*t)':d=0.65",
        "Sansür Bip (1kHz)",
    ),
    "fart-reverb": (
        "aevalsrc='0.9*sin(2*PI*(95-35*t+18*sin(2*PI*26*t))*t)*exp(-t*2.5)+0.35*(random(0)-0.5)*exp(-t*4)':d=1.2,"
        "lowpass=f=900,aecho=0.8:0.85:45|105|180:0.55|0.4|0.25,asoftclip=type=tanh",
        "Yankılı Meme Pırt",
    ),
    "oiia-spin": (
        "aevalsrc='0.7*sin(2*PI*(540+190*lt(mod(t,0.14),0.07))*t)*exp(-mod(t,0.07)*16)':d=1.4,asoftclip=type=tanh",
        "OIIA Dönen Kedi Synth",
    ),
    "turkish-horn": (
        "aevalsrc='0.65*(sgn(sin(2*PI*311*t))+0.85*sgn(sin(2*PI*392*t)))*sin(PI*min(1,t/1.1))':d=1.1,"
        "bandpass=f=1000:w=1800,asoftclip=type=tanh",
        "Çift Ton Tır Kornası",
    ),
    "akbil-error": (
        "aevalsrc='0.75*sin(2*PI*420*t)*lt(t,0.12)+0.75*sin(2*PI*310*t)*gte(t,0.16)*lt(t,0.42)':d=0.45",
        "Yetersiz Bakiye (Bip-Bop)",
    ),
    "eba-chime": (
        "aevalsrc='0.55*sin(2*PI*523.25*t)*exp(-t*5)*lt(t,0.22)+0.55*sin(2*PI*659.25*(t-0.22))*exp(-(t-0.22)*5)*gte(t,0.22)*lt(t,0.45)+"
        "0.6*sin(2*PI*783.99*(t-0.45))*exp(-(t-0.45)*3.2)*gte(t,0.45)':d=1.2",
        "Okul Bildirim Melodisi",
    ),
    "yesilcam-dram": (
        "aevalsrc='0.55*(sin(2*PI*440*t)*(1+0.025*sin(2*PI*7*t))*lt(t,0.5)+sin(2*PI*493.88*t)*gte(t,0.52)*lt(t,1.0)+"
        "sin(2*PI*415.3*t)*gte(t,1.02)*exp(-(t-1.02)*2.2))':d=1.9,lowpass=f=2600,aecho=0.8:0.7:50:0.35",
        "Yeşilçam Dramatik Yaylı",
    ),
    "kurtlar-racon": (
        "aevalsrc='0.85*sin(2*PI*73.4*t)*exp(-t*1.6)+0.4*sin(2*PI*220*t)*exp(-mod(t,0.38)*10)*lt(t,1.2)':d=1.8,"
        "aecho=0.8:0.75:65:0.4,asoftclip=type=tanh",
        "Karanlık Racon Bas",
    ),
    "tiktok-pop-spam": (
        "aevalsrc='0.85*sin(2*PI*(920-650*mod(t,0.12)*6)*t)*exp(-mod(t,0.12)*36)*lt(t,0.5)':d=0.52",
        "4lü TikTok Yorum Pop",
    ),
    "sigma-phonk-hit": (
        "aevalsrc='0.65*(sin(2*PI*540*t)+0.7*sin(2*PI*800*t))*exp(-t*14)+1.0*sin(2*PI*(68-25*t)*t)*exp(-t*3.2)':d=1.1,"
        "asoftclip=type=tanh",
        "Sigma Phonk Cowbell + 808",
    ),
    "brainrot-chaos": (
        "aevalsrc='0.6*sgn(sin(2*PI*(240+920*floor(random(0)*5))*t))*lt(mod(t,0.055),0.04)+0.8*sin(2*PI*62*t)*exp(-t*5)':d=0.65,"
        "asoftclip=type=tanh",
        "Brainrot Glitch Patlama",
    ),
    "bruh-double": (
        "aevalsrc='0.85*sin(2*PI*(120-30*mod(t,0.45))*t)*exp(-mod(t,0.45)*4.5)':d=0.95,asoftclip=type=tanh",
        "Çift Yankılı Bruh",
    ),
    "suspense-sting": (
        "aevalsrc='0.55*(sin(2*PI*233.1*t)+sin(2*PI*246.9*t)+sin(2*PI*466.2*t))*exp(-t*1.9)':d=1.6,lowpass=f=2400",
        "Şok Zoom Gerilim Akoru",
    ),
    "sad-meow": (
        "aevalsrc='0.55*sin(2*PI*(620-160*(t/1.3)+22*sin(2*PI*6*t))*t)*sin(PI*min(1,t/1.3))':d=1.35,lowpass=f=2200",
        "Hüzünlü Kedi & Hamster",
    ),
    "clock-tick-panic": (
        "aevalsrc='0.8*(random(0)-0.5)*exp(-mod(t,0.28-0.12*t/1.6)*110)*lt(t,1.6)+0.6*sin(2*PI*2100*t)*exp(-mod(t,0.28-0.12*t/1.6)*140)':d=1.6",
        "Panik Saat Tıkırtısı",
    ),
}

SFX_CAT_TR_MEME: dict[str, str] = {
    "slowmo-drop": "AI Böcek & Slow-Mo",
    "slowmo-choir": "AI Böcek & Slow-Mo",
    "bass-earrape-hit": "TR Meme & Shitpost",
    "censor-bleep": "TR Meme & Shitpost",
    "fart-reverb": "TR Meme & Shitpost",
    "oiia-spin": "TR Meme & Shitpost",
    "turkish-horn": "TR Meme & Shitpost",
    "akbil-error": "TR Meme & Shitpost",
    "eba-chime": "TR Meme & Shitpost",
    "yesilcam-dram": "TR Meme & Shitpost",
    "kurtlar-racon": "TR Meme & Shitpost",
    "tiktok-pop-spam": "UI & Oyun",
    "sigma-phonk-hit": "Vuruş & Darbe",
    "brainrot-chaos": "TR Meme & Shitpost",
    "bruh-double": "TR Meme & Shitpost",
    "suspense-sting": "Dramatik & Gerilim",
    "sad-meow": "AI Böcek & Slow-Mo",
    "clock-tick-panic": "Dramatik & Gerilim",
}

FX_TR_MEME: dict[str, dict] = {
    "slowmo-bug-dram": {
        "name": "AI Böcek Dramatik Glow",
        "pack": "Meme",
        "ff": "eq=contrast=1.24:saturation=1.18:brightness=-0.04,colorbalance=rs=0.12:gs=0.05:bs=-0.12,"
              "split[sb0][sb1];[sb1]gblur=sigma=14[sb2];[sb0][sb2]blend=all_mode=screen:all_opacity=0.38,vignette=PI/3.2",
        "css": "contrast(1.24) saturate(1.18) brightness(.96)",
        "ov": ["bloom", "vignette-hard"],
    },
    "tr-tv-2006": {
        "name": "2006 Türk Dizisi (VHS)",
        "pack": "Meme",
        "ff": "eq=saturation=0.85:contrast=1.12,colorbalance=rs=0.1:gs=0.06:bs=-0.1,gblur=sigma=0.8,"
              "noise=alls=16:allf=t,drawgrid=w=iw:h=4:t=1:c=black@0.22",
        "css": "sepia(.28) saturate(.85) contrast(1.12) blur(.5px)",
        "ov": ["scan", "grain", "vignette"],
    },
    "earrape-fry": {
        "name": "Kulak Patlatan Kızartma",
        "pack": "Meme",
        "ff": "eq=saturation=2.6:contrast=1.55,colorbalance=rs=0.45:gs=-0.08:bs=-0.12,rgbashift=rh=9:bh=-9,"
              "crop=iw-24:ih-24:12+12*sin(t*59):12+12*cos(t*53),scale=W:H",
        "css": "saturate(2.6) contrast(1.55) hue-rotate(-14deg)",
        "ov": ["rgb-strong", "shake", "red-vignette"],
    },
    "cursed-240p": {
        "name": "İnternet Kafe 240p",
        "pack": "Meme",
        "ff": "scale=iw/6:-2,scale=W:H:flags=neighbor,eq=contrast=1.28:saturation=1.35,noise=alls=14:allf=t",
        "css": "contrast(1.28) saturate(1.35)",
        "ov": ["pixel-strong", "grain"],
    },
    "racon-noir": {
        "name": "Kurtlar / Racon Sinema",
        "pack": "Meme",
        "ff": "hue=s=0.18,eq=contrast=1.32:brightness=-0.05,"
              "drawbox=y=0:w=iw:h=ih*0.11:c=black:t=fill,drawbox=y=ih*0.89:w=iw:h=ih*0.11:c=black:t=fill,vignette=PI/3.5",
        "css": "grayscale(.82) contrast(1.32) brightness(.95)",
        "ov": ["letterbox", "vignette-hard"],
    },
}

TEMPLATES_TR_MEME: list[dict] = [
    {
        "id": "ai-bocek-slowmo",
        "group": "Oyun & meme",
        "name": "🐛 AI Böcek Slow-Mo Anı",
        "items": [
            {"t": 0.0, "mode": "slowmo-bug-dram", "dur": 2.8},
            {"t": 0.1, "text": "BURALARI Bİ AYDINLAT HELE", "dur": 2.4,
             "style": {"font": "Anton", "size": 9.5, "anim": "blur", "pos": "bottom", "color": "#FDE68A", "outline": 7}},
            {"t": 0.0, "sfx": "slowmo-drop"},
            {"t": 0.25, "sfx": "slowmo-choir"},
        ],
    },
    {
        "id": "tr-shitpost-sok",
        "group": "Oyun & meme",
        "name": "💀 TR Shitpost Şok / Duraksama",
        "items": [
            {"t": 0.0, "mode": "meme-muffle-bw", "dur": 1.6},
            {"t": 0.0, "text": "NE DİYOOO?!", "dur": 1.5,
             "style": {"font": "Archivo Black", "size": 14, "anim": "shake", "pos": "center", "color": "#FFFFFF", "outline": 9, "bold": False}},
            {"t": 0.0, "sfx": "vine-boom-heavy"},
        ],
    },
    {
        "id": "tr-pov-alarm",
        "group": "Oyun & meme",
        "name": "📱 POV: 4 Saat Sonra Alarm Var",
        "items": [
            {"t": 0.0, "mode": "tr-tv-2006", "dur": 3.0},
            {"t": 0.0, "text": "POV: 4 saat sonra alarm varken Reels...", "dur": 2.8,
             "style": {"font": "Poppins Black", "size": 6.8, "anim": "type", "pos": "top", "color": "#FFFFFF", "outline": 6}},
            {"t": 0.0, "sfx": "clock-tick-panic"},
        ],
    },
    {
        "id": "tr-racon-ani",
        "group": "Oyun & meme",
        "name": "🐺 Racon / Yeşilçam Sahnesi",
        "items": [
            {"t": 0.0, "mode": "racon-noir", "dur": 3.2},
            {"t": 0.3, "text": "SENİ HİÇ ALAKADAR ETMEZ", "dur": 2.6,
             "style": {"font": "Georgia", "size": 7.5, "anim": "fade", "pos": "bottom", "color": "#F5F5F4", "outline": 5, "italic": True, "bold": False}},
            {"t": 0.0, "sfx": "kurtlar-racon"},
        ],
    },
    {
        "id": "tr-brainrot-kaos",
        "group": "Oyun & meme",
        "name": "🧠 TR Brainrot Kaos (Hızlı)",
        "items": [
            {"t": 0.0, "mode": "earrape-fry", "dur": 0.9},
            {"t": 0.0, "text": "KAOS", "dur": 0.45, "style": {"font": "Archivo Black", "size": 16, "anim": "pop", "pos": "center", "color": "#FFE600", "outline": 9, "bold": False}},
            {"t": 0.45, "text": "BİN", "dur": 0.45, "style": {"font": "Archivo Black", "size": 17, "anim": "glitch", "pos": "center", "color": "#FF2E88", "outline": 9, "bold": False}},
            {"t": 0.0, "sfx": "brainrot-chaos"},
            {"t": 0.35, "sfx": "bass-earrape-hit"},
        ],
    },
]

RECIPES_TR_MEME: dict[str, dict] = {
    "ai_bocek_slowmo": {
        "id": "ai_bocek_slowmo",
        "name": "🐛 Slow-Mo AI Böcek / Absürt",
        "desc": "Altın dramatik halo, sert vinyet, Ken Burns yaklaşma ve sinematik slow-mo kontrastı.",
        "grade": {"con": 0.22, "sat": 1.18, "temp": 0.08, "exp": -0.04},
        "zoom_preset": "ken-burns-center",
        "trans_in": "fade",
        "fx": ["slowmo-bug-dram"],
        "audio_fx": ["concert-hall"],
        "sub_style": "doc-serif",
        "shutter_angle": 270,
        "lufs": -12.0,
    },
    "tr_brainrot_2026": {
        "id": "tr_brainrot_2026",
        "name": "🧠 TR Brainrot 2026 (240p + Glitch)",
        "desc": "İnternet kafe 240p efekti, RGB yırtılma geçişi, çift mikro pump zoom ve -8.5 LUFS ses.",
        "grade": {"con": 0.24, "sat": 1.38, "exp": 0.04},
        "zoom_preset": "micro-pump-duo",
        "trans_in": "rgb-tear",
        "fx": ["cursed-240p"],
        "anim_loop": "shake-impact",
        "audio_fx": ["hot-montage"],
        "sub_style": "roblox-pop",
        "shutter_angle": 180,
        "lufs": -8.5,
    },
    "yesilcam_racon": {
        "id": "yesilcam_racon",
        "name": "🐺 Yeşilçam / Racon 2.39:1",
        "desc": "Racon sinema şeridi, soğuk düşük satürasyon, yavaş dramatik yaklaşma ve punch kompresör.",
        "grade": {"con": 0.28, "sat": 0.45, "exp": -0.06, "temp": -0.06},
        "zoom_preset": "dramatic",
        "trans_in": "fade",
        "fx": ["racon-noir"],
        "audio_fx": ["compressor-punch"],
        "sub_style": "doc-serif",
        "shutter_angle": 180,
        "lufs": -13.0,
    },
    "tr_shitpost_2026": {
        "id": "tr_shitpost_2026",
        "name": "💥 TR Shitpost Bass Boost (-7 LUFS)",
        "desc": "Kulak patlatan kızartma efekti, rage titreşim, beat drop zoom ve -7 LUFS bas patlaması.",
        "grade": {"con": 0.3, "sat": 1.6, "exp": 0.06},
        "zoom_preset": "drop-slam",
        "trans_in": "glitch-snap",
        "fx": ["earrape-fry"],
        "anim_loop": "rage-shake",
        "audio_fx": ["meme-earrape"],
        "sub_style": "meme-stroke",
        "shutter_angle": 180,
        "lufs": -7.0,
    },
}

# Doğrulanmış canlı Myinstants TR + küresel meme sesleri (tek tıkla önizle veya Sesler\TR Meme klasörüne indir)
TR_MEME_SOUNDS: list[dict[str, str]] = [
    # ---- AI Böcek & Slow-Mo
    {"id": "kurban-oldugum", "cat": "🐛 AI Böcek & Slow-Mo", "name": "Kurban olduğum şuraları bi aydınlat hele", "url": "https://www.myinstants.com/media/sounds/kurban-oldugum-suralari-bi-aydinlat-hele.mp3"},
    {"id": "degirmenci-dayi-bass", "cat": "🐛 AI Böcek & Slow-Mo", "name": "Değirmenci Dayı BASS", "url": "https://www.myinstants.com/media/sounds/degirmenci-dayi-bass.mp3"},
    {"id": "slow-motion-slow-to-fast", "cat": "🐛 AI Böcek & Slow-Mo", "name": "Slow Motion (Slow to Fast)", "url": "https://www.myinstants.com/media/sounds/slow-motion-slow-to-fast.mp3"},
    {"id": "slow-motion-punch", "cat": "🐛 AI Böcek & Slow-Mo", "name": "Slow Motion Punch", "url": "https://www.myinstants.com/media/sounds/slow-motion-punch.mp3"},
    {"id": "that-slow-motion-song", "cat": "🐛 AI Böcek & Slow-Mo", "name": "That Slow Motion Running Song", "url": "https://www.myinstants.com/media/sounds/that-slow-motion-running-song-ii.mp3"},
    {"id": "slow-motion-roblox-rizz", "cat": "🐛 AI Böcek & Slow-Mo", "name": "Slow Motion (Roblox Rizz)", "url": "https://www.myinstants.com/media/sounds/slow-motion-roblox-rizz-song.mp3"},
    {"id": "faaaaah", "cat": "🐛 AI Böcek & Slow-Mo", "name": "FAHHHHHHHHHHHHHH", "url": "https://www.myinstants.com/media/sounds/fahhhhhhhhhhhhhh.mp3"},
    {"id": "tiki-tiki-boosted", "cat": "🐛 AI Böcek & Slow-Mo", "name": "Tiki tiki boosted", "url": "https://www.myinstants.com/media/sounds/tiki-tiki-boosted.mp3"},
    {"id": "pocikerim", "cat": "🐛 AI Böcek & Slow-Mo", "name": "POCİKERİM", "url": "https://www.myinstants.com/media/sounds/pocikerim.mp3"},
    # ---- Güncel TR Viral (2025-2026)
    {"id": "yetersiz-bakiye-iett", "cat": "🇹🇷 TR Viral", "name": "Yetersiz bakiye IETT", "url": "https://www.myinstants.com/media/sounds/yetersiz-bakiye-iett.mp3"},
    {"id": "merve-mikrofonun-acik", "cat": "🇹🇷 TR Viral", "name": "Merveee mikrofonun açık", "url": "https://www.myinstants.com/media/sounds/merveee-mikrofonun-acik.mp3"},
    {"id": "yarim-ekmek-75-milyon", "cat": "🇹🇷 TR Viral", "name": "Lan oğlum yarım ekmek nasıl 75 milyon", "url": "https://www.myinstants.com/media/sounds/lan-oglum-yarim-ekmek-nasil-75-milyon.mp3"},
    {"id": "ben-divayim-diva", "cat": "🇹🇷 TR Viral", "name": "Ben divayım diva", "url": "https://www.myinstants.com/media/sounds/ben-divayim-diva.mp3"},
    {"id": "bekle-beni-muhammet", "cat": "🇹🇷 TR Viral", "name": "BEKLE BENİ MUHAMMET", "url": "https://www.myinstants.com/media/sounds/bekle-beni-muhammet.mp3"},
    {"id": "keloglan-jenerik-bass", "cat": "🇹🇷 TR Viral", "name": "Keloğlan Jenerik (Sesi Fulleyin)", "url": "https://www.myinstants.com/media/sounds/keloglan-jenerik-sesi-fulleyin.mp3"},
    {"id": "ismail-kartal-kante", "cat": "🇹🇷 TR Viral", "name": "İsmail Kartal Engolo Kante", "url": "https://www.myinstants.com/media/sounds/ismail-kartal-engolo-kante.mp3"},
    {"id": "lvbel-c5-sezen-aksu", "cat": "🇹🇷 TR Viral", "name": "LVBEL C5 - Sezen Aksu", "url": "https://www.myinstants.com/media/sounds/lvbel-c5-sezen-aksu.mp3"},
    {"id": "manifest-ses-sistemi", "cat": "🇹🇷 TR Viral", "name": "Manifest ses sistemi", "url": "https://www.myinstants.com/media/sounds/manifest-ses-sistemi.mp3"},
    {"id": "zencolar-keremi", "cat": "🇹🇷 TR Viral", "name": "Zencolar Keremi", "url": "https://www.myinstants.com/media/sounds/zencolar-keremi.mp3"},
    {"id": "duktur-nerde", "cat": "🇹🇷 TR Viral", "name": "Duktur nerde", "url": "https://www.myinstants.com/media/sounds/duktur-nerde.mp3"},
    {"id": "ne-diyooo-oglum", "cat": "🇹🇷 TR Viral", "name": "NE DİYOOO OĞLUM", "url": "https://www.myinstants.com/media/sounds/ne-diyooo-oglum.mp3"},
    {"id": "ezi-kuzi-ciye-te", "cat": "🇹🇷 TR Viral", "name": "Ezi kuzi ciye te", "url": "https://www.myinstants.com/media/sounds/ezi-kuzi-ciye-te.mp3"},
    {"id": "mimar-selim-kamonn", "cat": "🇹🇷 TR Viral", "name": "MİMAR SELİM KAMONN", "url": "https://www.myinstants.com/media/sounds/mimar-selim-kamonn.mp3"},
    {"id": "kastamonu-sarimsak", "cat": "🇹🇷 TR Viral", "name": "Kastamonu Taşköprü Sarımsak Geldi", "url": "https://www.myinstants.com/media/sounds/kastamonu-taskopru-sarimsak-geldi.mp3"},
    {"id": "tezgah-lan-bu", "cat": "🇹🇷 TR Viral", "name": "Tezgah lan buuu", "url": "https://www.myinstants.com/media/sounds/tezgah-lan-buuu_xHz2vwL.mp3"},
    {"id": "abi-geldiler-abi", "cat": "🇹🇷 TR Viral", "name": "Abi geldiler abi", "url": "https://www.myinstants.com/media/sounds/abi-geldiler-abi.mp3"},
    {"id": "allah-diyen-kurt-adam", "cat": "🇹🇷 TR Viral", "name": "Allah diyen kurt adam", "url": "https://www.myinstants.com/media/sounds/allah-diyen-kurt-adam.mp3"},
    {"id": "icardi-bilmiyorum", "cat": "🇹🇷 TR Viral", "name": "Icardi bilmiyorum diyor", "url": "https://www.myinstants.com/media/sounds/icardi-bilmiyorum-diyor_cpCdxfp.mp3"},
    {"id": "icardi-adam-ya-geldi", "cat": "🇹🇷 TR Viral", "name": "Adam ya geldi adammm", "url": "https://www.myinstants.com/media/sounds/adam-ya-geldi-adammm.mp3"},
    # ---- Replik, Dizi & Yayıncı
    {"id": "aykut-elmas-hosgeldiniz", "cat": "🎭 TR Replik & Dizi", "name": "Aykut Elmas - Hoşgeldiniz", "url": "https://www.myinstants.com/media/sounds/aykut-elmas-haber-blteni-allar.mp3"},
    {"id": "aykut-elmas-oc-geliyor", "cat": "🎭 TR Replik & Dizi", "name": "Aykut Elmas - Oç geliyor", "url": "https://www.myinstants.com/media/sounds/aykut-elmas-oc-geliyor.mp3"},
    {"id": "aykut-aglama-hadi-oyna", "cat": "🎭 TR Replik & Dizi", "name": "Aykut Elmas - Ağlama hadi oyna", "url": "https://www.myinstants.com/media/sounds/aglama-hadi-oyna_BWQJFo1.mp3"},
    {"id": "aykut-bana-para-ver", "cat": "🎭 TR Replik & Dizi", "name": "Bana para veeğğrr!!!", "url": "https://www.myinstants.com/media/sounds/bana-para-veeggrr.mp3"},
    {"id": "kadir-hoca-hayirli", "cat": "🎭 TR Replik & Dizi", "name": "Kadir Hoca - Hayırlı günler", "url": "https://www.myinstants.com/media/sounds/kadir-hoca-hayirli-gunler.mp3"},
    {"id": "recep-ivedik-bu-geliyor", "cat": "🎭 TR Replik & Dizi", "name": "Recep İvedik - Bu geliyor bu gidiyor", "url": "https://www.myinstants.com/media/sounds/recep-ivedik-bu-geliyor-bu-gidiyor.mp3"},
    {"id": "recep-ivedik-gulus", "cat": "🎭 TR Replik & Dizi", "name": "Recep İvedik Gülüş", "url": "https://www.myinstants.com/media/sounds/recep-ivedik-gulus.mp3"},
    {"id": "kv-operasyon-bitmistir", "cat": "🎭 TR Replik & Dizi", "name": "Kurtlar Vadisi - Operasyon Bitmiştir", "url": "https://www.myinstants.com/media/sounds/kurtlar-vadisi-operasyonu-bitmistir.mp3"},
    {"id": "kv-seni-hic-alakadar", "cat": "🎭 TR Replik & Dizi", "name": "Seni Hiç Alakadar Etmez (BASS)", "url": "https://www.myinstants.com/media/sounds/seni-hic-alakadar-etmez-bass-boosted.mp3"},
    {"id": "akasya-sasirma", "cat": "🎭 TR Replik & Dizi", "name": "Akasya Durağı - Şaşırma Efekti", "url": "https://www.myinstants.com/media/sounds/akasya-durag-sasrma-efekti.mp3"},
    {"id": "akasya-operasyon", "cat": "🎭 TR Replik & Dizi", "name": "Akasya Durağı - Operasyon Müziği", "url": "https://www.myinstants.com/media/sounds/akasya-duragi-operasyon-muzigi.mp3"},
    {"id": "ezel-dizi-muzigi", "cat": "🎭 TR Replik & Dizi", "name": "Ezel Dizi Müziği", "url": "https://www.myinstants.com/media/sounds/ezel-dizi-muzigi.mp3"},
    {"id": "ramiz-dayi-alarm", "cat": "🎭 TR Replik & Dizi", "name": "Ramiz Dayı Alarm", "url": "https://www.myinstants.com/media/sounds/ramiz-dayi-alarm.mp3"},
    {"id": "telefonum-calcaksa", "cat": "🎭 TR Replik & Dizi", "name": "Telefonum çalcaksa böyle çalsın", "url": "https://www.myinstants.com/media/sounds/telefonum-calcaksa-boyle-calsin.mp3"},
    # ---- Earrape & Bass Boosted
    {"id": "turkcell-earrape", "cat": "📢 Earrape & Bass", "name": "Turkcell'le bağlan hayata (EARRAPE)", "url": "https://www.myinstants.com/media/sounds/turkcellle-baglan-hayata-earrape.mp3"},
    {"id": "whatsapp-bass-boosted", "cat": "📢 Earrape & Bass", "name": "WhatsApp Bass Boosted", "url": "https://www.myinstants.com/media/sounds/whatsapp-bass-boosted.mp3"},
    {"id": "ampul-adam-bass", "cat": "📢 Earrape & Bass", "name": "AMPUL ADAM (BASS)", "url": "https://www.myinstants.com/media/sounds/ampul-adam-bass.mp3"},
    {"id": "eyvah-tufan-bass", "cat": "📢 Earrape & Bass", "name": "Eyvah Tufan Eyvah (Bass Boosted)", "url": "https://www.myinstants.com/media/sounds/eyvah-tufan-eyvah-bass-boosted.mp3"},
    {"id": "eba-zil-yuksek", "cat": "📢 Earrape & Bass", "name": "EBA Zil Sesi (Ses Yükseltili)", "url": "https://www.myinstants.com/media/sounds/eba-zil-sesi-ses-yukseltili.mp3"},
    {"id": "ceddin-deden", "cat": "📢 Earrape & Bass", "name": "CEDDİN DEDEN", "url": "https://www.myinstants.com/media/sounds/ceddin-deden.mp3"},
    # ---- Brainrot & Global Meme
    {"id": "oiia-cat", "cat": "💀 Brainrot & Global", "name": "OIIA OIIA Dönen Kedi", "url": "https://www.myinstants.com/media/sounds/oiia-oiia-sound.mp3"},
    {"id": "sneaky-golem", "cat": "💀 Brainrot & Global", "name": "Sneaky Golem", "url": "https://www.myinstants.com/media/sounds/sneaky-golem.mp3"},
    {"id": "vine-boom-classic", "cat": "💀 Brainrot & Global", "name": "Vine Boom (Orijinal)", "url": "https://www.myinstants.com/media/sounds/vine-boom.mp3"},
    {"id": "metal-pipe-clang", "cat": "💀 Brainrot & Global", "name": "Metal Pipe Falling", "url": "https://www.myinstants.com/media/sounds/metal-pipe-clang.mp3"},
    {"id": "rizz-sound-effect", "cat": "💀 Brainrot & Global", "name": "Rizz Sound Effect", "url": "https://www.myinstants.com/media/sounds/rizz-sound-effect.mp3"},
    {"id": "anime-wow-sfx", "cat": "💀 Brainrot & Global", "name": "Anime Wow", "url": "https://www.myinstants.com/media/sounds/anime-wow-sound-effect.mp3"},
    {"id": "among-us-reveal", "cat": "💀 Brainrot & Global", "name": "Among Us Role Reveal", "url": "https://www.myinstants.com/media/sounds/among-us-role-reveal-sound.mp3"},
    {"id": "cat-laugh-meme", "cat": "💀 Brainrot & Global", "name": "Kedi Kahkaha (Cat Laugh)", "url": "https://www.myinstants.com/media/sounds/cat-laugh-meme-1.mp3"},
    {"id": "dexter-meme", "cat": "💀 Brainrot & Global", "name": "Dexter Meme", "url": "https://www.myinstants.com/media/sounds/dexter-meme.mp3"},
    {"id": "nokia-arabic", "cat": "💀 Brainrot & Global", "name": "Nokia Arabic Ringtone", "url": "https://www.myinstants.com/media/sounds/nokia-ringtone-arabic.mp3"},
    {"id": "dry-fart", "cat": "💀 Brainrot & Global", "name": "Dry Fart", "url": "https://www.myinstants.com/media/sounds/dry-fart.mp3"},
    {"id": "osssuruk-yankili", "cat": "💀 Brainrot & Global", "name": "Yankılı Pırt Meme", "url": "https://www.myinstants.com/media/sounds/ossssuruk-sesi-yankili-cok-komik-ses-efektii.mp3"},
]

# Doğrulanmış YouTube Türkçe meme, yeşil ekran ve AI böcek klipleri (yt-dlp ile Memeler klasörüne iner)
TR_MEME_VIDEOS: list[dict] = [
    # ---- AI Böcek & Hamam Böceği
    {"id": "sxJAjcsoilI", "cat": "🐛 AI Böcek & Slow-Mo", "name": "Hamam Böcekleri Çıldırdı (AI Derleme)", "dur": 282, "greenscreen": False, "url": "https://www.youtube.com/watch?v=sxJAjcsoilI"},
    {"id": "6GVrM9w7Vpo", "cat": "🐛 AI Böcek & Slow-Mo", "name": "En Komik Hamam Böceği Videoları", "dur": 1037, "greenscreen": False, "url": "https://www.youtube.com/watch?v=6GVrM9w7Vpo"},
    {"id": "ZHrvm_6C0Z0", "cat": "🐛 AI Böcek & Slow-Mo", "name": "En Komik Hamam Böceği Videoları #2", "dur": 1088, "greenscreen": False, "url": "https://www.youtube.com/watch?v=ZHrvm_6C0Z0"},
    {"id": "7tCL-N9nPug", "cat": "🐛 AI Böcek & Slow-Mo", "name": "Dans Eden Hamam Böceği HD", "dur": 63, "greenscreen": False, "url": "https://www.youtube.com/watch?v=7tCL-N9nPug"},
    {"id": "4_mUH23uIxM", "cat": "🐛 AI Böcek & Slow-Mo", "name": "Uçan Hamam Böceği Meme Klibi", "dur": 23, "greenscreen": False, "url": "https://www.youtube.com/watch?v=4_mUH23uIxM"},
    # ---- Türkçe & Global Yeşil Ekran (Chroma Key hazır!)
    {"id": "089d627yozk", "cat": "🟩 Yeşil Ekran (TR)", "name": "Toqtir - Ses Yapıyosun Yeşil Ekran", "dur": 5, "greenscreen": True, "url": "https://www.youtube.com/watch?v=089d627yozk"},
    {"id": "hblZIfoN9Bc", "cat": "🟩 Yeşil Ekran (TR)", "name": "Dost Kayaoğlu Dans Yeşil Ekran", "dur": 7, "greenscreen": True, "url": "https://www.youtube.com/watch?v=hblZIfoN9Bc"},
    {"id": "JdW-06AaMa4", "cat": "🟩 Yeşil Ekran (TR)", "name": "Eren Karayılan - Karım Nerede Yeşil Ekran", "dur": 6, "greenscreen": True, "url": "https://www.youtube.com/watch?v=JdW-06AaMa4"},
    {"id": "77AA3vxtzww", "cat": "🟩 Yeşil Ekran (TR)", "name": "Çorba İçin Deliren Adam Yeşil Ekran", "dur": 2, "greenscreen": True, "url": "https://www.youtube.com/watch?v=77AA3vxtzww"},
    {"id": "SdPbCJ8Wshc", "cat": "🟩 Yeşil Ekran (TR)", "name": "Türkçe Abone Ol & Like Yeşil Ekran", "dur": 11, "greenscreen": True, "url": "https://www.youtube.com/watch?v=SdPbCJ8Wshc"},
    {"id": "WlAUOJTG_q4", "cat": "🟩 Yeşil Ekran (TR)", "name": "Abone Ol Yeşil Perde 4K 60 FPS", "dur": 6, "greenscreen": True, "url": "https://www.youtube.com/watch?v=WlAUOJTG_q4"},
    {"id": "ammR4cpxiQA", "cat": "🟩 Yeşil Ekran (TR)", "name": "LoL Zafer (Victory) Türkçe Yeşil Ekran", "dur": 38, "greenscreen": True, "url": "https://www.youtube.com/watch?v=ammR4cpxiQA"},
    {"id": "I68Ehtbu84M", "cat": "🟩 Yeşil Ekran (Global)", "name": "OIIA Dönen Kedi Yeşil Ekran", "dur": 7, "greenscreen": True, "url": "https://www.youtube.com/watch?v=I68Ehtbu84M"},
    {"id": "rXh8Hvo7gfs", "cat": "🟩 Yeşil Ekran (Global)", "name": "Maxwell Kedi Dans Yeşil Ekran", "dur": 15, "greenscreen": True, "url": "https://www.youtube.com/watch?v=rXh8Hvo7gfs"},
    {"id": "NsAsFNsk9es", "cat": "🟩 Yeşil Ekran (Global)", "name": "Popüler Meme Yeşil Ekran Paketi", "dur": 193, "greenscreen": True, "url": "https://www.youtube.com/watch?v=NsAsFNsk9es"},
    # ---- Türkçe Shitpost & Derleme / Replik
    {"id": "rxTMi6jeQ44", "cat": "🇹🇷 TR Shitpost & Klip", "name": "TR Shitpost Derleme #69", "dur": 251, "greenscreen": False, "url": "https://www.youtube.com/watch?v=rxTMi6jeQ44"},
    {"id": "q7VW-O2kaRQ", "cat": "🇹🇷 TR Shitpost & Klip", "name": "TR Shitpost Derleme #71", "dur": 327, "greenscreen": False, "url": "https://www.youtube.com/watch?v=q7VW-O2kaRQ"},
    {"id": "sNJafr-ncvk", "cat": "🇹🇷 TR Shitpost & Klip", "name": "TR Shitpost Gönderi Derlemesi #10", "dur": 665, "greenscreen": False, "url": "https://www.youtube.com/watch?v=sNJafr-ncvk"},
    {"id": "O2HUJ9eJMeg", "cat": "🇹🇷 TR Shitpost & Klip", "name": "Sıfır Bir Gökhan-Cio Adana Şiveli İngilizce Dublaj", "dur": 43, "greenscreen": False, "url": "https://www.youtube.com/watch?v=O2HUJ9eJMeg"},
    {"id": "GIvkL5UjqaU", "cat": "🇹🇷 TR Shitpost & Klip", "name": "Top 20 Viral Meme SFX (2026)", "dur": 79, "greenscreen": False, "url": "https://www.youtube.com/watch?v=GIvkL5UjqaU"},
]

# Gemini / Veo / Flow için tek-tık hazır AI Böcek & TR Meme promptları
AI_MEME_PROMPTS: list[dict[str, str]] = [
    {
        "title": "🐛 Hamam Böceği Maç İzliyor (Slow-Mo)",
        "prompt": "Hyper-realistic cinematic slow-motion video, 9:16 vertical, a brown cockroach wearing a tiny red-and-white Turkish football jersey sitting upright on a living room sofa holding a remote, intensely watching a football match on TV, dramatic warm rim lighting, shallow depth of field, 120fps silky slow motion.",
    },
    {
        "title": "☕ Türk Kahvesi İçen Hamam Böceği",
        "prompt": "Photorealistic macro slow-motion shot of an anthropomorphic cockroach sitting at a rustic Turkish cafe table at dusk, lifting a tiny copper cup of Turkish coffee in ultra slow motion, steam rising in golden light, absurd deadpan serious cinema mood, 35mm lens.",
    },
    {
        "title": "📱 Gece 03:00 Reels Kaydıran Böcek",
        "prompt": "Realistic dimly lit bedroom close-up in slow motion: a cockroach lying in bed under a blanket staring at a glowing vertical smartphone screen scrolling short videos, screen light illuminating its antennae, 4 hours left until alarm clock mood, cinematic bokeh.",
    },
    {
        "title": "🦸 Epik Süper Kahraman Böcek (Dramatik)",
        "prompt": "Extreme slow-motion epic movie trailer shot: a giant glossy beetle standing heroically on a rainy Istanbul rooftop at night while wind blows its tiny cape, dramatic lightning flash behind, rain droplets frozen mid-air, anamorphic lens flare.",
    },
    {
        "title": "🛸 Anadolu'da UFO & Esnaf (Shitpost)",
        "prompt": "Found-footage handheld camera aesthetic: a Turkish roadside tea house garden at night as a glowing retro spaceship hovers quietly above the plastic tables while a calm man sips tea from a tulip glass, hilarious deadpan absurd realism.",
    },
]
