"""Kami Studio Dalga 7 Hareketli Grafik & Constructor Ekleri (AtomX / Spunkram / AEJuice / PluginPlay / Envato):
- GRAPHICS_PACK2 (+18 parametrik ASS vektor kart / grafik / constructor)
- STICKERS_PACK2 (+12 vektor / rozet cikartma -> toplam 36)
"""
from __future__ import annotations

GRAPHICS_PACK2 = {
    "newspaper-cut": "Gazete Kupürü (Baskı)",
    "history-timeline": "Zaman Çizelgesi (Timeline)",
    "chat-bubble": "Mesaj / Sohbet Balonu",
    "bar-chart": "Çubuk Grafik (Chartist)",
    "donut-stat": "Halka Yüzde Grafiği",
    "audio-spec": "Ses Spektrum Çubukları",
    "countdown-timer": "Geri Sayım Sayacı",
    "sale-badge": "İndirim / Kampanya Etiketi",
    "neon-sign": "Neon Tabela Başlığı",
    "device-notif": "Telefon Bildirim Kartı",
    "social-comment": "Sabitlenen Sosyal Yorum",
    "chapter-bar": "Üst Bölüm Çubuğu",
    "whiteboard-sketch": "Bilgi / Kurallar Kutusu",
    "kinetic-stamp": "Damga / Onay Mühürü",
    "split-compare": "Önce / Sonra Karşılaştırma",
    "podcast-card": "Podcast Konuşmacı Rozeti",
    "map-pin": "Rota & Konum Kartı",
    "glitch-title": "Siber Glitch Başlık",
}

GRAPHICS_HYPER = {
    "hf-glass-shard": "💎 Cam Parçaları Başlık (HF)",
    "hf-wireframe-portal": "🌀 Portal & Kelime Değişimi (HF)",
    "hf-code-slice": "⬛ Karo 3B Çevirme Başlık (HF)",
    "hf-orbit-carousel": "🪐 Yörünge Küp & Kart (HF)",
    "hf-canopy-part": "🍃 Yaprak Perde Açılış (HF)",
    "hf-matrix-kinetic": "🧬 Matris Çözme & Kinetik Kart (HF)",
}

STICKERS_PACK2 = {
    "hand-circle": {"name": "El Çizimi Halka", "cat": "İşaret", "vec": "ring", "color": "#FFE600"},
    "underline-zig": {"name": "Vurgu Çizgisi", "cat": "İşaret", "vec": "pill", "text": "━━━▶ ÖNEMLİ", "color": "#FF2E4C"},
    "spark-star": {"name": "✨ Parıltı", "cat": "Tasarım", "glyph": "✨", "color": "#FDE047"},
    "live-rec-hd": {"name": "4K 60FPS", "cat": "Sinema", "vec": "pill", "text": "4K • 60FPS", "color": "#0F172A"},
    "subscribe-bell": {"name": "Bildirim Zili", "cat": "Sosyal", "vec": "pill", "text": "🔔 BİLDİRİMLER AÇIK", "color": "#8B5CF6"},
    "target-crosshair": {"name": "🎯 Hedef", "cat": "Oyun", "glyph": "🎯", "color": "#EF4444"},
    "badge-new": {"name": "YENİ Rozeti", "cat": "Mağaza", "vec": "pill", "text": "⚡ YENİ", "color": "#10B981"},
    "badge-free": {"name": "ÜCRETSİZ", "cat": "Mağaza", "vec": "pill", "text": "★ ÜCRETSİZ", "color": "#2563EB"},
    "percent-off": {"name": "%50 İNDİRİM", "cat": "Mağaza", "vec": "pill", "text": "%50 İNDİRİM", "color": "#E11D48"},
    "thumbs-up": {"name": "👍 Beğen", "cat": "Sosyal", "glyph": "👍", "color": "#38BDF8"},
    "rating-5star": {"name": "★★★★★ 5 Yıldız", "cat": "Mağaza", "vec": "pill", "text": "★★★★★ 5.0", "color": "#D97706"},
    "speech-exclaim": {"name": "❗ Ünlem", "cat": "Meme", "glyph": "❗", "color": "#EF4444"},
}


def graphic_pack2(c, kind: str, col, esc, rrect, W: int, H: int, st: dict) -> bool:
    """GRAPHICS_PACK2 ogeleri icin ASS vektor eventleri uretir; eslesirse True doner."""
    k = c.k
    acc = col(st.get("color", "#8B5CF6"))
    title = esc(st.get("title", ""))
    sub = esc(st.get("sub", ""))
    x = W * float(st.get("x", 0.5))
    y = H * float(st.get("y", 0.5))

    if kind == "newspaper-cut":
        t_txt = title or "GAZETE MANŞETİ"
        s_txt = sub or "Özel Sayı • 2026 Arşivi"
        cw = max(W * 0.66, (max(len(t_txt) * 32, len(s_txt) * 18) + 96) * k)
        cw = min(cw, W * 0.92)
        ch = 280 * k
        c.ev(2, 0, None, f"\\an5\\pos({x:.0f},{y:.0f})\\p1\\1c&H00DCE8F2&\\3c&H00262626&\\bord{4 * k:.0f}\\shad{12 * k:.0f}\\frz-1.5\\fscx84\\fscy84\\t(0,220,\\fscx100\\fscy100)\\fad(120,260)", rrect(cw, ch, 8 * k))
        c.ev(3, 0.08, None, f"\\an5\\pos({x:.0f},{y - 62 * k:.0f})\\p1\\1c&H001F1F1F&\\bord0\\shad0\\frz-1.5\\fad(120,260)", rrect(cw - 48 * k, 4 * k, 0))
        c.ev(4, 0.1, None, f"\\an5\\pos({x:.0f},{y - 16 * k:.0f})\\fn Georgia\\fs{56 * k:.0f}\\b1\\bord0\\shad0\\1c&H00111111&\\frz-1.5\\q0\\fad(150,260)", t_txt)
        c.ev(4, 0.2, None, f"\\an5\\pos({x:.0f},{y + 64 * k:.0f})\\fn Georgia\\fs{30 * k:.0f}\\i1\\bord0\\shad0\\1c&H003A3A3A&\\frz-1.5\\q0\\fad(200,260)", s_txt)
        return True

    if kind == "history-timeline":
        bw = W * 0.72
        c.ev(2, 0, None, f"\\an5\\pos({x:.0f},{y:.0f})\\p1\\1c{acc}\\bord0\\shad{4 * k:.0f}\\fscx0\\t(0,320,\\fscx100)\\fad(100,260)", rrect(bw, 8 * k, 4 * k))
        for idx in (-1, 0, 1):
            nx = x + idx * bw * 0.34
            c.ev(3, 0.1 + (idx + 1) * 0.08, None, f"\\an5\\pos({nx:.0f},{y:.0f})\\p1\\1c&H00FFFFFF&\\3c{acc}\\bord{5 * k:.0f}\\fscx0\\fscy0\\t(0,220,\\fscx100\\fscy100)\\fad(100,260)", rrect(26 * k, 26 * k, 13 * k))
        c.ev(4, 0.2, None, f"\\an5\\pos({x:.0f},{y - 68 * k:.0f})\\fn{c.font}\\fs{52 * k:.0f}\\b1\\bord{3 * k:.0f}\\1c&H00FFFFFF&\\fad(150,260)", title or "2018  —  2022  —  2026")
        if sub:
            c.ev(4, 0.3, None, f"\\an5\\pos({x:.0f},{y + 62 * k:.0f})\\fn{c.font}\\fs{30 * k:.0f}\\bord{2 * k:.0f}\\1c&H00D1D5DB&\\fad(180,260)", sub)
        return True

    if kind == "chat-bubble":
        bw, bh = max(460 * k, (len(st.get("title", "Merhaba!")) * 28 + 120) * k), 146 * k
        c.ev(3, 0, None, f"\\an5\\pos({x:.0f},{y:.0f})\\p1\\1c{acc}\\bord0\\shad{8 * k:.0f}\\fscx60\\fscy60\\t(0,180,\\fscx105\\fscy105)\\t(180,260,\\fscx100\\fscy100)\\fad(80,220)", rrect(bw, bh, 28 * k))
        c.ev(4, 0.08, None, f"\\an5\\pos({x:.0f},{y - 14 * k:.0f})\\fn{c.font}\\fs{40 * k:.0f}\\b1\\bord0\\shad0\\1c&H00FFFFFF&\\fad(80,220)", title or "Bu detayı fark ettin mi?")
        c.ev(4, 0.16, None, f"\\an6\\pos({x + bw / 2 - 24 * k:.0f},{y + 42 * k:.0f})\\fn{c.font}\\fs{22 * k:.0f}\\bord0\\shad0\\1c&H00EAEAEA&\\fad(100,220)", sub or "14:22 ✓✓")
        return True

    if kind == "bar-chart":
        cw, ch = W * 0.56, 300 * k
        c.ev(2, 0, None, f"\\an5\\pos({x:.0f},{y:.0f})\\p1\\1c&H0012101C&\\1a&H16&\\3c{acc}\\bord{2 * k:.0f}\\fad(120,260)", rrect(cw, ch, 18 * k))
        c.ev(4, 0.08, None, f"\\an8\\pos({x:.0f},{y - ch / 2 + 18 * k:.0f})\\fn{c.font}\\fs{34 * k:.0f}\\b1\\bord0\\1c&H00FFFFFF&\\fad(150,260)", title or "PERFORMANS KARŞILAŞTIRMASI")
        ratios = (0.38, 0.62, 0.88, 0.52)
        for i, r in enumerate(ratios):
            bx = x - cw * 0.30 + i * (cw * 0.20)
            bh = 165 * k * r
            by = y + ch / 2 - 38 * k - bh / 2
            c.ev(3, 0.12 + i * 0.08, None, f"\\an5\\pos({bx:.0f},{by:.0f})\\p1\\1c{acc}\\bord0\\fscy0\\t(0,300,\\fscy100)\\fad(120,260)", rrect(58 * k, bh, 8 * k))
        if sub:
            c.ev(4, 0.25, None, f"\\an2\\pos({x:.0f},{y + ch / 2 - 10 * k:.0f})\\fn{c.font}\\fs{22 * k:.0f}\\bord0\\1c&H00CBD5E1&\\fad(180,260)", sub)
        return True

    if kind == "donut-stat":
        c.ev(3, 0, None, f"\\an5\\pos({x:.0f},{y:.0f})\\p1\\1a&HFF&\\3c&H00322E44&\\bord{20 * k:.0f}\\fad(100,260)", rrect(220 * k, 220 * k, 110 * k))
        c.ev(4, 0.05, None, f"\\an5\\pos({x:.0f},{y:.0f})\\p1\\1a&HFF&\\3c{acc}\\bord{20 * k:.0f}\\fscx75\\fscy75\\t(0,320,\\fscx100\\fscy100)\\fad(120,260)", rrect(220 * k, 220 * k, 110 * k))
        c.ev(5, 0.12, None, f"\\an5\\pos({x:.0f},{y - 10 * k:.0f})\\fn{c.font}\\fs{62 * k:.0f}\\b1\\bord0\\1c&H00FFFFFF&\\fad(150,260)", title or "%94")
        if sub:
            c.ev(5, 0.2, None, f"\\an5\\pos({x:.0f},{y + 42 * k:.0f})\\fn{c.font}\\fs{24 * k:.0f}\\bord0\\1c&H00CBD5E1&\\fad(180,260)", sub)
        return True

    if kind == "audio-spec":
        n_bars = 14
        bw_tot = n_bars * 26 * k
        heights = (0.35, 0.65, 0.9, 0.5, 0.85, 1.0, 0.6, 0.75, 0.95, 0.55, 0.8, 0.45, 0.7, 0.4)
        for i, h_frac in enumerate(heights):
            bx = x - bw_tot / 2 + i * 26 * k + 10 * k
            bh = 95 * k * h_frac
            c.ev(4, 0.0, None, f"\\an5\\pos({bx:.0f},{y:.0f})\\p1\\1c{acc}\\bord0\\fscy30\\t(0,240,\\fscy100)\\t(240,540,\\fscy50)\\t(540,860,\\fscy100)\\fad(80,220)", rrect(14 * k, bh, 7 * k))
        if title:
            c.ev(5, 0.05, None, f"\\an5\\pos({x:.0f},{y + 82 * k:.0f})\\fn{c.font}\\fs{28 * k:.0f}\\b1\\bord{2 * k:.0f}\\1c&H00FFFFFF&\\fad(100,220)", title)
        return True

    if kind == "countdown-timer":
        n0 = max(1, int(float(st.get("from", 3) or 3)))
        steps = max(2, min(10, n0 + 1))
        step_d = max(0.25, c.dur / steps)
        for i in range(steps):
            val = max(0, n0 - i)
            t0, t1 = i * step_d, (i + 1) * step_d
            c.ev(5, t0, t1, f"\\an5\\pos({x:.0f},{y:.0f})\\fn{c.font}\\fs{150 * k:.0f}\\b1\\bord{8 * k:.0f}\\1c{acc}\\fscx135\\fscy135\\t(0,180,\\fscx100\\fscy100)", str(val))
        return True

    if kind == "sale-badge":
        c.ev(3, 0, None, f"\\an5\\pos({x:.0f},{y:.0f})\\p1\\1c{acc}\\3c&H00FFFFFF&\\bord{4 * k:.0f}\\shad{8 * k:.0f}\\frz-4\\fscx60\\fscy60\\t(0,180,\\fscx108\\fscy108)\\t(180,260,\\fscx100\\fscy100)\\fad(80,220)", rrect(360 * k, 130 * k, 22 * k))
        c.ev(4, 0.06, None, f"\\an5\\pos({x:.0f},{y - 18 * k:.0f})\\fn{c.font}\\fs{48 * k:.0f}\\b1\\bord0\\1c&H00FFFFFF&\\frz-4\\fad(80,220)", title or "%50 İNDİRİM")
        c.ev(4, 0.12, None, f"\\an5\\pos({x:.0f},{y + 32 * k:.0f})\\fn{c.font}\\fs{24 * k:.0f}\\b1\\bord0\\1c&H00FFE600&\\frz-4\\fad(100,220)", sub or "SINIRLI STOK")
        return True

    if kind == "neon-sign":
        t_txt = title or "NEON EDITION"
        c.ev(3, 0, None, f"\\an5\\pos({x:.0f},{y:.0f})\\p1\\1a&HFF&\\3c{acc}\\bord{6 * k:.0f}\\blur6\\shad0\\fad(100,260)", rrect(max(360 * k, len(t_txt) * 44 * k), 120 * k, 18 * k))
        c.ev(4, 0.05, None, f"\\an5\\pos({x:.0f},{y:.0f})\\fn{c.font}\\fs{68 * k:.0f}\\b1\\3c{acc}\\bord{6 * k:.0f}\\blur4\\1c&H00FFFFFF&\\fad(100,260)", t_txt)
        return True

    if kind == "device-notif":
        t_txt = title or "Yeni Mesaj"
        s_txt = sub or "Şimdi • Bildirim önizlemesi"
        cw = min(W * 0.88, max(W * 0.44, (max(len(t_txt) * 20, len(s_txt) * 15) + 84) * k))
        ch = 128 * k
        ny = H * float(st.get("y", 0.14))
        c.ev(3, 0, None, f"\\an5\\move({x:.0f},{ny - 90 * k:.0f},{x:.0f},{ny:.0f},0,240)\\p1\\1c&H0018181B&\\1a&H12&\\3c{acc}\\bord{2 * k:.0f}\\shad{10 * k:.0f}\\fad(80,260)", rrect(cw, ch, 26 * k))
        c.ev(4, 0.06, None, f"\\an4\\pos({x - cw / 2 + 28 * k:.0f},{ny - 20 * k:.0f})\\fn{c.font}\\fs{32 * k:.0f}\\b1\\bord0\\1c&H00FFFFFF&\\fad(120,260)", t_txt)
        c.ev(4, 0.1, None, f"\\an4\\pos({x - cw / 2 + 28 * k:.0f},{ny + 24 * k:.0f})\\fn{c.font}\\fs{24 * k:.0f}\\bord0\\1c&H00CBD5E1&\\fad(120,260)", s_txt)
        return True

    if kind == "social-comment":
        t_txt = title or "@kullanici"
        s_txt = sub or "Bu video harika olmuş!"
        cw = min(W * 0.88, max(W * 0.52, (max(len(t_txt) * 18, len(s_txt) * 20) + 88) * k))
        ch = 150 * k
        c.ev(2, 0, None, f"\\an5\\pos({x:.0f},{y:.0f})\\p1\\1c&H00FFFFFF&\\3c{acc}\\bord{3 * k:.0f}\\shad{8 * k:.0f}\\fscx85\\t(0,200,\\fscx100)\\fad(100,240)", rrect(cw, ch, 20 * k))
        c.ev(4, 0.08, None, f"\\an4\\pos({x - cw / 2 + 26 * k:.0f},{y - 30 * k:.0f})\\fn{c.font}\\fs{28 * k:.0f}\\b1\\bord0\\1c{acc}\\fad(120,240)", t_txt)
        c.ev(4, 0.12, None, f"\\an4\\pos({x - cw / 2 + 26 * k:.0f},{y + 18 * k:.0f})\\fn{c.font}\\fs{32 * k:.0f}\\bord0\\1c&H00111827&\\fad(140,240)", s_txt)
        return True

    if kind == "chapter-bar":
        cy = H * float(st.get("y", 0.09))
        t_txt = title or "01 · BÖLÜM BAŞLIĞI"
        pw = max(320 * k, (len(t_txt) * 24 + 80) * k)
        c.ev(3, 0, None, f"\\an5\\pos({x:.0f},{cy:.0f})\\p1\\1c&H000E0C18&\\1a&H18&\\3c{acc}\\bord{2 * k:.0f}\\fscx70\\t(0,220,\\fscx100)\\fad(80,220)", rrect(pw, 66 * k, 33 * k))
        c.ev(4, 0.05, None, f"\\an5\\pos({x:.0f},{cy:.0f})\\fn{c.font}\\fs{32 * k:.0f}\\b1\\bord0\\1c&H00FFFFFF&\\fad(100,220)", t_txt)
        return True

    if kind == "whiteboard-sketch":
        t_txt = title or "ANA FİKİR"
        s_txt = sub or "Adım 1 • Adım 2 • Adım 3"
        cw = min(W * 0.90, max(W * 0.56, (max(len(t_txt) * 28, len(s_txt) * 19) + 96) * k))
        ch = 220 * k
        c.ev(2, 0, None, f"\\an5\\pos({x:.0f},{y:.0f})\\p1\\1c&H00FAF9F5&\\3c&H001E293B&\\bord{5 * k:.0f}\\shad{8 * k:.0f}\\fad(100,240)", rrect(cw, ch, 14 * k))
        c.ev(4, 0.08, None, f"\\an5\\pos({x:.0f},{y - 34 * k:.0f})\\fn{c.font}\\fs{46 * k:.0f}\\b1\\bord0\\1c{acc}\\fad(120,240)", t_txt)
        c.ev(4, 0.16, None, f"\\an5\\pos({x:.0f},{y + 34 * k:.0f})\\fn{c.font}\\fs{32 * k:.0f}\\bord0\\1c&H001E293B&\\fad(160,240)", s_txt)
        return True

    if kind == "kinetic-stamp":
        t_txt = title or "ONAYLANDI"
        pw = max(300 * k, (len(t_txt) * 42 + 64) * k)
        c.ev(4, 0, None, f"\\an5\\pos({x:.0f},{y:.0f})\\p1\\1a&HFF&\\3c{acc}\\bord{8 * k:.0f}\\frz-8\\fscx180\\fscy180\\t(0,160,\\fscx100\\fscy100)\\fad(40,220)", rrect(pw, 118 * k, 12 * k))
        c.ev(5, 0, None, f"\\an5\\pos({x:.0f},{y:.0f})\\fn{c.font}\\fs{62 * k:.0f}\\b1\\bord0\\1c{acc}\\frz-8\\fscx180\\fscy180\\t(0,160,\\fscx100\\fscy100)\\fad(40,220)", t_txt)
        return True

    if kind == "split-compare":
        c.ev(3, 0, None, f"\\an5\\pos({x:.0f},{y:.0f})\\p1\\1c&H00FFFFFF&\\bord0\\shad{4 * k:.0f}\\fscy0\\t(0,220,\\fscy100)\\fad(80,240)", rrect(6 * k, H * 0.85, 0))
        c.ev(4, 0.08, None, f"\\an5\\pos({x - W * 0.24:.0f},{H * 0.14:.0f})\\fn{c.font}\\fs{46 * k:.0f}\\b1\\bord{4 * k:.0f}\\1c&H00FFFFFF&\\fad(120,240)", title or "ÖNCE")
        c.ev(4, 0.12, None, f"\\an5\\pos({x + W * 0.24:.0f},{H * 0.14:.0f})\\fn{c.font}\\fs{46 * k:.0f}\\b1\\bord{4 * k:.0f}\\1c{acc}\\fad(120,240)", sub or "SONRA")
        return True

    if kind == "podcast-card":
        x0, y0 = W * float(st.get("x", 0.06)), H * float(st.get("y", 0.78))
        bw = max(440 * k, (len(st.get("title", "Konuk")) * 32 + 90) * k)
        c.ev(3, 0, None, f"\\an7\\pos({x0:.0f},{y0:.0f})\\p1\\1c&H000D0B16&\\1a&H14&\\3c{acc}\\bord{3 * k:.0f}\\fscx75\\t(0,220,\\fscx100)\\fad(100,260)", rrect(bw, 118 * k, 18 * k))
        c.ev(4, 0.08, None, f"\\an7\\pos({x0 + 26 * k:.0f},{y0 + 18 * k:.0f})\\fn{c.font}\\fs{40 * k:.0f}\\b1\\bord0\\1c&H00FFFFFF&\\fad(120,260)", title or "Konuk İsim")
        c.ev(4, 0.14, None, f"\\an7\\pos({x0 + 26 * k:.0f},{y0 + 68 * k:.0f})\\fn{c.font}\\fs{26 * k:.0f}\\bord0\\1c{acc}\\fad(160,260)", sub or "Podcast Bölümü #12")
        return True

    if kind == "map-pin":
        cw = max(420 * k, (len(st.get("title", "ANKARA → İSTANBUL")) * 28 + 100) * k)
        c.ev(3, 0, None, f"\\an5\\pos({x:.0f},{y:.0f})\\p1\\1c&H00111827&\\1a&H14&\\3c{acc}\\bord{3 * k:.0f}\\fad(100,240)", rrect(cw, 112 * k, 56 * k))
        c.ev(4, 0.06, None, f"\\an5\\pos({x:.0f},{y - 16 * k:.0f})\\fn{c.font}\\fs{36 * k:.0f}\\b1\\bord0\\1c&H00FFFFFF&\\fad(120,240)", f"📍 {title or 'İSTANBUL'}")
        if sub:
            c.ev(4, 0.12, None, f"\\an5\\pos({x:.0f},{y + 24 * k:.0f})\\fn{c.font}\\fs{24 * k:.0f}\\bord0\\1c&H0038BDF8&\\fad(150,240)", sub)
        return True

    if kind == "glitch-title":
        t_txt = title or "GLITCH TITLE"
        c.ev(3, 0, None, f"\\an5\\pos({x + 6 * k:.0f},{y:.0f})\\fn{c.font}\\fs{96 * k:.0f}\\b1\\bord0\\1c&H0000FFFF&\\fad(60,200)", t_txt)
        c.ev(3, 0, None, f"\\an5\\pos({x - 6 * k:.0f},{y:.0f})\\fn{c.font}\\fs{96 * k:.0f}\\b1\\bord0\\1c&H00FF00FF&\\fad(60,200)", t_txt)
        c.ev(4, 0.06, None, f"\\an5\\pos({x:.0f},{y:.0f})\\fn{c.font}\\fs{96 * k:.0f}\\b1\\bord{4 * k:.0f}\\1c&H00FFFFFF&\\fad(80,220)", t_txt)
        return True

    if kind == "hf-glass-shard":
        t_txt = title or "CAMDA TASARIM"
        s_txt = sub or "Kinetik Parça Efekti"
        bw = min(W * 0.86, max(440 * k, (len(t_txt) * 44 + 120) * k))
        bh = 210 * k
        # 6 acili cam parcasi ucip basligin arkasinda mozaik olusturur
        shards = [
            (-0.36, -0.28, -28, f"m 0 0 l {160 * k:.0f} {18 * k:.0f} l {130 * k:.0f} {110 * k:.0f} l {-18 * k:.0f} {82 * k:.0f}"),
            (0.36, -0.26, 22, f"m 0 0 l {170 * k:.0f} {-14 * k:.0f} l {155 * k:.0f} {95 * k:.0f} l {12 * k:.0f} {105 * k:.0f}"),
            (-0.34, 0.25, 19, f"m 0 0 l {165 * k:.0f} {-10 * k:.0f} l {140 * k:.0f} {90 * k:.0f} l {-20 * k:.0f} {78 * k:.0f}"),
            (0.34, 0.26, -24, f"m 0 0 l {155 * k:.0f} {22 * k:.0f} l {128 * k:.0f} {102 * k:.0f} l {-10 * k:.0f} {88 * k:.0f}"),
            (0.0, -0.32, 14, f"m 0 0 l {190 * k:.0f} {8 * k:.0f} l {168 * k:.0f} {96 * k:.0f} l {16 * k:.0f} {92 * k:.0f}"),
            (0.0, 0.30, -16, f"m 0 0 l {185 * k:.0f} {-12 * k:.0f} l {164 * k:.0f} {88 * k:.0f} l {12 * k:.0f} {96 * k:.0f}"),
        ]
        for idx, (ox, oy, rot, path_d) in enumerate(shards):
            tx = x + (idx % 3 - 1) * (bw * 0.25)
            ty = y + (-38 if idx < 3 else 38) * k
            sx, sy = x + ox * W, y + oy * H
            d0 = idx * 45
            d1 = d0 + 420
            c.ev(2, 0, None,
                 f"\\an5\\move({sx:.0f},{sy:.0f},{tx:.0f},{ty:.0f},{d0},{d1})\\p1\\1c&H00F8FAFC&\\1a&HCE&\\3c{acc}\\3a&H40&\\bord{2.5 * k:.0f}\\shad0"
                 f"\\blur8\\frz{rot * 2}\\fscx35\\fscy35\\t({d0},{d1},0.6,\\blur0\\frz{rot * 0.15:.1f}\\fscx100\\fscy100)\\fad(90,280)",
                 path_d)
        c.ev(3, 0.22, None,
             f"\\an5\\pos({x:.0f},{y:.0f})\\p1\\1c&H0012101C&\\1a&H30&\\3c&H00E2E8F0&\\3a&H55&\\bord{2 * k:.0f}\\shad{12 * k:.0f}"
             f"\\fscx86\\fscy86\\t(0,260,0.6,\\fscx100\\fscy100)\\fad(120,280)", rrect(bw, bh, 20 * k))
        c.ev(5, 0.28, None,
             f"\\an5\\pos({x:.0f},{y - 16 * k:.0f})\\fn{c.font}\\fs{68 * k:.0f}\\b1\\bord{3 * k:.0f}\\3c&H0009070E&\\1c&H00FFFFFF&\\shad{4 * k:.0f}"
             f"\\fscx125\\fscy125\\blur6\\t(0,280,0.6,\\fscx100\\fscy100\\blur0)\\fad(100,260)", t_txt)
        if s_txt:
            c.ev(5, 0.38, None,
                 f"\\an5\\pos({x:.0f},{y + 52 * k:.0f})\\fn{c.font}\\fs{28 * k:.0f}\\b1\\bord0\\1c{acc}\\fsp4\\fad(140,260)", s_txt)
        return True

    if kind == "hf-wireframe-portal":
        p1 = title or "WIREFRAME PORTAL"
        p2 = sub or "YENİ DÖNEM BAŞLADI"
        mid = max(1.1, c.dur * 0.48)
        r1 = 220 * k
        r2 = 170 * k
        hex_p = " ".join(f"{'m' if i == 0 else 'l'} {r1 * __import__('math').cos(i * 1.0472):.0f} {r1 * __import__('math').sin(i * 1.0472):.0f}" for i in range(6)) + " c"
        ring_p = " ".join(f"{'m' if i == 0 else 'l'} {r2 * __import__('math').cos(i * 0.5236):.0f} {r2 * __import__('math').sin(i * 0.5236):.0f}" for i in range(12)) + " c"
        # Dis & ic tel kafes halkalar donerek acilir
        c.ev(2, 0, None,
             f"\\an5\\pos({x:.0f},{y:.0f})\\p1\\1a&HFF&\\3c{acc}\\bord{3.5 * k:.0f}\\shad0\\fscx12\\fscy12\\frz-90"
             f"\\t(0,360,0.5,\\fscx100\\fscy100\\frz0)\\t(360,{int(c.dur * 1000)},\\frz60)\\fad(60,260)", hex_p)
        c.ev(2, 0.06, None,
             f"\\an5\\pos({x:.0f},{y:.0f})\\p1\\1a&HFF&\\3c&H00A6E62E&\\3a&H40&\\bord{2 * k:.0f}\\shad0\\fscx8\\fscy8\\frz120"
             f"\\t(0,420,0.5,\\fscx108\\fscy108\\frz0)\\t(420,{int(c.dur * 1000)},\\frz-75)\\fad(60,260)", ring_p)
        # Faz 1 baslik portaldan cikar ve ortada 90 deg 3D cevirir
        c.ev(5, 0.12, mid,
             f"\\an5\\pos({x:.0f},{y:.0f})\\fn{c.font}\\fs{74 * k:.0f}\\b1\\bord{4 * k:.0f}\\3c&H0009070E&\\1c&H00FFFFFF&"
             f"\\fscx20\\fscy20\\blur10\\t(0,340,0.5,\\fscx100\\fscy100\\blur0)\\t({max(200, int(mid * 1000) - 220)},{int(mid * 1000)},\\fry90\\alpha&HFF&)", p1)
        # Faz 2 degisim cumlesi portala girer
        c.ev(5, max(0.3, mid - 0.05), None,
             f"\\an5\\pos({x:.0f},{y:.0f})\\fn{c.font}\\fs{68 * k:.0f}\\b1\\bord{4 * k:.0f}\\3c&H0009070E&\\1c{acc}"
             f"\\fry-90\\fscx108\\fscy108\\t(0,280,0.5,\\fry0\\fscx100\\fscy100)\\fad(0,260)", p2)
        return True

    if kind == "hf-code-slice":
        front = title or "MAKE IT"
        back = sub or "MATTER."
        mid = max(1.0, c.dur * 0.48)
        tw, th = min(W * 0.78, 900 * k), 220 * k
        cols, rows = 6, 3
        cw, ch = tw / cols, th / rows
        x0, y0 = x - tw / 2, y - th / 2
        # Supurucu dalga karolari hucre hucre 3B cevirir
        for r_i in range(rows):
            for c_i in range(cols):
                cx = x0 + (c_i + 0.5) * cw
                cy = y0 + (r_i + 0.5) * ch
                delay = (c_i + r_i) * 45
                flip_d = int(mid * 1000) + (c_i + r_i) * 40
                c.ev(2, 0, None,
                     f"\\an5\\pos({cx:.0f},{cy:.0f})\\p1\\1c&H00141022&\\1a&H18&\\3c{acc}\\3a&H70&\\bord{1.5 * k:.0f}\\shad0"
                     f"\\fscy0\\t({delay},{delay + 180},\\fscy100)"
                     f"\\t({flip_d},{flip_d + 140},\\frx90\\1c{acc})\\t({flip_d + 140},{flip_d + 300},\\frx0\\1c&H001A1330&)\\fad(40,220)",
                     rrect(cw - 4 * k, ch - 4 * k, 4 * k))
        c.ev(5, 0.14, mid + 0.08,
             f"\\an5\\pos({x:.0f},{y:.0f})\\fn{c.font}\\fs{82 * k:.0f}\\b1\\bord{3 * k:.0f}\\1c&H00FFFFFF&\\fscx88\\t(0,220,\\fscx100)"
             f"\\t({max(100, int(mid * 1000) - 180)},{int(mid * 1000)},\\frx90\\alpha&HFF&)", front)
        c.ev(5, mid + 0.04, None,
             f"\\an5\\pos({x:.0f},{y:.0f})\\fn{c.font}\\fs{84 * k:.0f}\\b1\\bord{3 * k:.0f}\\1c{acc}\\frx-90\\t(0,240,\\frx0)\\fad(0,240)", back)
        return True

    if kind == "hf-orbit-carousel":
        t_txt = title or "YÖRÜNGE ÖZELLİK"
        s_txt = sub or "Küp & Perspektif Akışı"
        # Merkez nokta kure halkalari + donen kartlar
        rad = 175 * k
        orbit_ring = " ".join(
            f"{'m' if i == 0 else 'l'} {rad * 1.45 * __import__('math').cos(i * 0.3927):.0f} {rad * 0.42 * __import__('math').sin(i * 0.3927):.0f}"
            for i in range(16)
        ) + " c"
        c.ev(2, 0, None, f"\\an5\\pos({x:.0f},{y:.0f})\\p1\\1c&H001E1730&\\1a&H50&\\3c{acc}\\bord{2 * k:.0f}\\shad0\\fscx50\\fscy50\\t(0,280,\\fscx100\\fscy100)\\fad(80,220)", rrect(140 * k, 140 * k, 70 * k))
        c.ev(3, 0.04, None, f"\\an5\\pos({x:.0f},{y:.0f})\\p1\\1a&HFF&\\3c&H00C4B5FD&\\3a&H45&\\bord{2.5 * k:.0f}\\shad0\\frz-18\\t(0,{int(c.dur * 1000)},\\frz12)\\fad(100,220)", orbit_ring)
        # Yorumge karti soldan merkeze kavisli kayar
        cw, ch = min(W * 0.54, max(440 * k, (len(t_txt) * 32 + 120) * k)), 148 * k
        c.ev(4, 0.08, None,
             f"\\an5\\move({x - 220 * k:.0f},{y + 30 * k:.0f},{x + 56 * k:.0f},{y - 8 * k:.0f},0,520)\\p1\\1c&H000E0C1A&\\1a&H14&\\3c{acc}\\bord{3 * k:.0f}\\shad{12 * k:.0f}"
             f"\\frz-6\\t(0,480,0.6,\\frz0)\\fad(90,240)", rrect(cw, ch, 18 * k))
        c.ev(5, 0.14, None,
             f"\\an5\\move({x - 220 * k:.0f},{y + 10 * k:.0f},{x + 56 * k:.0f},{y - 24 * k:.0f},0,520)\\fn{c.font}\\fs{44 * k:.0f}\\b1\\bord0\\1c&H00FFFFFF&\\fad(100,240)", t_txt)
        c.ev(5, 0.2, None,
             f"\\an5\\move({x - 220 * k:.0f},{y + 52 * k:.0f},{x + 56 * k:.0f},{y + 22 * k:.0f},0,520)\\fn{c.font}\\fs{26 * k:.0f}\\bord0\\1c&H002EE6A6&\\fad(120,240)", s_txt)
        return True

    if kind == "hf-canopy-part":
        t_txt = title or "SAHNE AÇILIŞI"
        s_txt = sub or "Katmanlı Yaprak Geçişi"
        blade = f"m 0 {-220 * k:.0f} b {180 * k:.0f} {-140 * k:.0f} {220 * k:.0f} {120 * k:.0f} 0 {220 * k:.0f} b {-90 * k:.0f} {90 * k:.0f} {-90 * k:.0f} {-90 * k:.0f} 0 {-220 * k:.0f}"
        # Baslik merkezde belirir, iki katmanli perde/yaprak ortadan iki yana ayrilir
        c.ev(4, 0.18, None,
             f"\\an5\\pos({x:.0f},{y - 20 * k:.0f})\\fn{c.font}\\fs{76 * k:.0f}\\b1\\bord{4 * k:.0f}\\3c&H0009070E&\\1c&H00FFFFFF&"
             f"\\fscx84\\fscy84\\t(0,420,0.5,\\fscx100\\fscy100)\\fad(140,260)", t_txt)
        if s_txt:
            c.ev(4, 0.28, None,
                 f"\\an5\\pos({x:.0f},{y + 52 * k:.0f})\\fn{c.font}\\fs{32 * k:.0f}\\b1\\bord0\\1c{acc}\\fad(160,260)", s_txt)
        for side, col_b in ((-1, "&H00143D2E&"), (-1, acc), (1, "&H00143D2E&"), (1, acc)):
            ox = side * (90 if col_b == acc else 35) * k
            tx = side * (W * 0.44)
            c.ev(5 if col_b != acc else 6, 0, min(1.5, c.dur),
                 f"\\an5\\move({x + ox:.0f},{y:.0f},{x + tx:.0f},{y - 30 * k:.0f},120,760)\\p1\\1c{col_b}\\1a&H28&\\3c&H002EE6A6&\\bord{2 * k:.0f}\\shad0"
                 f"\\frz{side * 14}\\t(120,760,\\frz{side * 42})\\fad(60,320)", blade)
        return True

    if kind == "hf-matrix-kinetic":
        t_txt = title or "SİSTEM ÇÖZÜLDÜ"
        s_txt = sub or "KOD AKIŞI · 100% AKTİF"
        glyphs = "AX#09K$M!7ZQ"
        steps = 8
        sc_dur = min(0.95, c.dur * 0.42)
        bw = min(W * 0.86, max(460 * k, (len(t_txt) * 42 + 120) * k))
        c.ev(2, 0, None,
             f"\\an5\\pos({x:.0f},{y:.0f})\\p1\\1c&H00090710&\\1a&H22&\\3c{acc}\\bord{3 * k:.0f}\\shad{8 * k:.0f}"
             f"\\fscx85\\t(0,200,\\fscx100)\\fad(60,240)", rrect(bw, 184 * k, 12 * k))
        for i in range(steps):
            t0 = sc_dur * i / steps
            t1 = sc_dur * (i + 1) / steps if i < steps - 1 else None
            locked = int(len(t_txt) * (i / max(1, steps - 1)))
            cur = "".join(t_txt[j] if (j < locked or i == steps - 1 or t_txt[j] == " ") else glyphs[(j * 5 + i * 3) % len(glyphs)] for j in range(len(t_txt)))
            c.ev(5, t0, t1,
                 f"\\an5\\pos({x:.0f},{y - 20 * k:.0f})\\fn Consolas\\fs{62 * k:.0f}\\b1\\bord0\\1c&H002EE6A6&"
                 + ("\\fad(0,240)" if t1 is None else ""), cur)
        c.ev(5, sc_dur * 0.5, None,
             f"\\an5\\pos({x:.0f},{y + 44 * k:.0f})\\fn{c.font}\\fs{28 * k:.0f}\\b1\\bord0\\1c{acc}\\fsp3\\fad(120,240)", s_txt)
        return True

    return False
