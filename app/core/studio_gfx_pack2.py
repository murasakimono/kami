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

    return False
