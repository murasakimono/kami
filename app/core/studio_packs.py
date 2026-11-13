"""Faz 5b veri paketleri: zoom sablonlari (ZOOM3) ve altyazi on ayarlari (CAPTIONS2).
CAPTIONS2: her biri mevcut bir davranisa (b) eslenir + varsayilan stil; _captions basinda:
    if mode in CAPTIONS2: p = CAPTIONS2[mode]; st = {**p["st"], **st}; mode = p["b"]
Fontlar staging/fonts (Turkce glif dogrulandi)."""

ZOOM3 = [
    {"id": "push-fast", "name": "Hızlı yaklaş", "kf": [{"t": 0, "z": 1}, {"t": 0.35, "z": 1.3, "e": "inout"}]},
    {"id": "pull-fast", "name": "Hızlı uzaklaş", "kf": [{"t": 0, "z": 1.3}, {"t": 0.35, "z": 1, "e": "inout"}]},
    {"id": "crash", "name": "Çarpma zoom (crash)", "kf": [{"t": 0, "z": 1}, {"t": 0.06, "z": 1.6, "e": "out"}, {"t": 0.5, "z": 1.5}]},
    {"id": "wobble", "name": "Sallanan zoom", "kf": [{"t": 0, "z": 1.1}, {"t": 0.15, "z": 1.18}, {"t": 0.3, "z": 1.1}, {"t": 0.45, "z": 1.18}, {"t": 0.6, "z": 1.1}]},
    {"id": "beat4", "name": "4 vuruş (1 sn)", "kf": [{"t": 0, "z": 1}, {"t": 0.04, "z": 1.12, "e": "out"}, {"t": 0.24, "z": 1}, {"t": 0.29, "z": 1.12, "e": "out"},
                                                     {"t": 0.49, "z": 1}, {"t": 0.54, "z": 1.12, "e": "out"}, {"t": 0.74, "z": 1}, {"t": 0.79, "z": 1.12, "e": "out"}, {"t": 0.99, "z": 1}]},
    {"id": "step3", "name": "Basamaklı yaklaş", "kf": [{"t": 0, "z": 1}, {"t": 0.08, "z": 1.15, "e": "out"}, {"t": 0.4, "z": 1.15}, {"t": 0.48, "z": 1.3, "e": "out"},
                                                       {"t": 0.8, "z": 1.3}, {"t": 0.88, "z": 1.45, "e": "out"}]},
    {"id": "reveal-out", "name": "Yakından açıl (yavaş)", "kf": [{"t": 0, "z": 1.6}, {"t": -0.001, "z": 1, "e": "out"}]},
    {"id": "kb-tb", "name": "Ken Burns yukarıdan aşağı", "kf": [{"t": 0, "z": 1.2, "cx": 0.5, "cy": 0.35}, {"t": -0.001, "z": 1.2, "cx": 0.5, "cy": 0.65}]},
    {"id": "kb-zoom-lr", "name": "Ken Burns yaklaş + kay", "kf": [{"t": 0, "z": 1.05, "cx": 0.42, "cy": 0.5}, {"t": -0.001, "z": 1.3, "cx": 0.58, "cy": 0.48}]},
    {"id": "dive-tr", "name": "Sağ üste dal", "kf": [{"t": 0, "z": 1, "cx": 0.5, "cy": 0.5}, {"t": 0.5, "z": 1.6, "cx": 0.7, "cy": 0.3, "e": "inout"}]},
    {"id": "dive-bl", "name": "Sol alta dal", "kf": [{"t": 0, "z": 1, "cx": 0.5, "cy": 0.5}, {"t": 0.5, "z": 1.6, "cx": 0.3, "cy": 0.7, "e": "inout"}]},
    {"id": "eyes", "name": "Gözlere yaklaş", "kf": [{"t": 0, "z": 1, "cx": 0.5, "cy": 0.5}, {"t": 0.6, "z": 2.2, "cx": 0.5, "cy": 0.33, "e": "inout"}]},
    {"id": "reaction", "name": "Tepki (şok yaklaş)", "kf": [{"t": 0, "z": 1}, {"t": 0.1, "z": 1.4, "e": "out"}, {"t": 0.2, "z": 1.35}, {"t": 0.3, "z": 1.5, "e": "out"}]},
    {"id": "dolly-in", "name": "Dolly yaklaş (yumuşak)", "kf": [{"t": 0, "z": 1}, {"t": -0.001, "z": 1.25, "e": "inout"}]},
    {"id": "pan-lr", "name": "Pan soldan sağa (yakın)", "kf": [{"t": 0, "z": 1.4, "cx": 0.3, "cy": 0.5}, {"t": -0.001, "z": 1.4, "cx": 0.7, "cy": 0.5, "e": "inout"}]},
    {"id": "pan-rl", "name": "Pan sağdan sola (yakın)", "kf": [{"t": 0, "z": 1.4, "cx": 0.7, "cy": 0.5}, {"t": -0.001, "z": 1.4, "cx": 0.3, "cy": 0.5, "e": "inout"}]},
    {"id": "tilt-down", "name": "Aşağı süzül", "kf": [{"t": 0, "z": 1.3, "cx": 0.5, "cy": 0.32}, {"t": -0.001, "z": 1.3, "cx": 0.5, "cy": 0.68, "e": "inout"}]},
    {"id": "breath", "name": "Nefes (yavaş nabız)", "kf": [{"t": 0, "z": 1}, {"t": 1, "z": 1.06, "e": "inout"}, {"t": 2, "z": 1, "e": "inout"}, {"t": 3, "z": 1.06, "e": "inout"}]},
    {"id": "drop", "name": "Drop (yaklaş-bırak)", "kf": [{"t": 0, "z": 1}, {"t": 0.5, "z": 1.35, "e": "in"}, {"t": 0.55, "z": 1, "e": "out"}]},
    {"id": "glide-in", "name": "Süzülerek yaklaş (sağa)", "kf": [{"t": 0, "z": 1, "cx": 0.5, "cy": 0.5}, {"t": -0.001, "z": 1.35, "cx": 0.62, "cy": 0.5, "e": "inout"}]},
]

CAPTIONS2 = {
    "beast-yellow": {"name": "Sarı kalın (Beast)", "b": "mrbeast", "st": {"font": "Luckiest Guy", "highlight": "#FFE600", "perLine": 2}},
    "anton-punch": {"name": "Anton vurgu", "b": "hormozi", "st": {"font": "Anton", "highlight": "#00E5FF", "perLine": 2, "size": 9}},
    "bebas-clean": {"name": "Bebas sade", "b": "plain", "st": {"font": "Bebas Neue", "upper": True, "size": 9, "outline": 5}},
    "poppins-pill": {"name": "Poppins hap", "b": "highlight", "st": {"font": "Poppins ExtraBold", "highlight": "#FF3B7F", "upper": False}},
    "montserrat-pop": {"name": "Montserrat pop", "b": "hormozi", "st": {"font": "Montserrat Black", "highlight": "#2EE66B", "perLine": 3}},
    "comic-pow": {"name": "Çizgi roman", "b": "mrbeast", "st": {"font": "Bangers", "highlight": "#FF4040", "perLine": 2}},
    "typewriter": {"name": "Daktilo", "b": "reveal", "st": {"font": "Special Elite", "upper": False, "size": 6.5, "outline": 3}},
    "neon-pink": {"name": "Neon pembe", "b": "neon", "st": {"font": "Monoton", "glowColor": "#FF2BD6", "size": 7}},
    "retro-pixel": {"name": "Retro piksel", "b": "hormozi", "st": {"font": "Press Start 2P", "highlight": "#FFD400", "size": 5, "perLine": 2}},
    "handwritten": {"name": "El yazısı", "b": "reveal", "st": {"font": "Caveat Bold", "upper": False, "size": 8, "outline": 4}},
    "karaoke-blue": {"name": "Karaoke mavi", "b": "karaoke", "st": {"font": "Poppins Bold", "highlight": "#3BA7FF"}},
    "boxed-white": {"name": "Beyaz kutu", "b": "boxed", "st": {"font": "Inter SemiBold", "color": "#111111", "boxColor": "#FFFFFF", "upper": False}},
    "horror": {"name": "Korku", "b": "word", "st": {"font": "Nosifer", "color": "#D10000", "size": 9}},
    "elegant": {"name": "Zarif serif", "b": "cinema", "st": {"font": "Kami Serif", "size": 5.5}},
    "gamer": {"name": "Oyuncu", "b": "hormozi", "st": {"font": "Black Ops One", "highlight": "#39FF14", "perLine": 2}},
    "hollow-anton": {"name": "Boş Anton", "b": "hollow", "st": {"font": "Anton", "highlight": "#FF3B5C", "size": 9}},
}
