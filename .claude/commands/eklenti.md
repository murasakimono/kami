---
description: Kami'ye yeni eklenti (site/özellik) ekle - rehber + şablonla, az token
argument-hint: <fikir, ör. "gofile.io paylaşım linklerini indir">
---

Kami'ye yeni bir eklenti ekle: **$ARGUMENTS**

Kurallar (token tasarrufu için ÖNEMLİ):
- SADECE `docs/EKLENTI-REHBERI.md` ve `plugins/_sablon/` oku. Proje defterini, `app/` çekirdeğini, `extension/`
  ve `app/ui/` dosyalarını OKUMA (gerekirse tek bir benzer eklentiye bak: `plugins/pixeldrain/plugin.py` en kısası).
- Sadece yeni eklentinin klasörüne yaz.

Adımlar:
1. Rehberi oku. Fikirden eklenti adını çıkar (küçük harf, `_`), bir cümleyle ne yapacağını söyle.
2. Sitenin resmi/herkese açık API'sini kısaca araştır (WebFetch/arama); DRM ya da korsan indeks sitesiyse DUR ve söyle.
3. `uv run python -m tools.yeni_eklenti <ad> "<Görünen Ad>"`
4. `plugin.json`: gerçek `url_patterns` (+ `examples` match/no_match), gerekiyorsa `settings`.
   `plugin.py`: `list()` (ve gerekirse `file_request()`). `test_plugin.py`: desen testleri + bir `@pytest.mark.network` testi.
5. `uv run python -m tools.eklenti_test <ad>` GEÇENE kadar düzelt; gerçek bir örnek link varsa `--ag` ile de dene.
6. Commit: `Eklenti: <ad> <surum>` (sadece plugins/<ad>/), push.
7. Proje defterinin (C:\Users\fluvoksamine\Scripts\projeler\indirici.md) "Günlük" bölümüne TEK satır ekle
   (önce dosyanın son hâlini oku).
8. Kullanıcıya: Kami'de Ayarlar > Eklentiler > Yeniden yükle (yeni klasörse Kami'yi yeniden aç); tarayıcı eklentisi
   yeni siteyi Kami'ye bağlanınca kendiliğinden öğrenir.
