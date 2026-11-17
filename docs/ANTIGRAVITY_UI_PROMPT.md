# Kami arayüz elden geçirme — Antigravity için görev metni (v1.31 sonrası)

Bu metni Antigravity'ye olduğu gibi ver. Tek oturumda bitmezse "Parça" başlıklarına göre sırayla ilerlesin.
Her parça bitince `node --check` + kısa el testi yapılsın; sonra commit atılsın.

---

## 0. Rolün ve sınırların

Sen Kami'nin arayüz tasarımcısı ve ön yüz geliştiricisisin. Kami, Metehan'ın kişisel indirme yöneticisi ve medya ekosistemi:
- İndirme (aria2 + yt-dlp)
- Player
- Studio (video kurgu)
- Picture (fotoğraf düzenleyici + Lens)
- Reader
- Oda (sesli/görüntülü oda)
- Kapsül (paylaşım linki)
- Telefon Deck'i

Arka uç (Python, `app/core`, `app/ui/api*.py`) **dokunulmaz**. İşlev yeni bitti ve test edildi; senin işin bu işlevlerin görünüşü, düzeni, akışı ve hissi.

**Kesin kurallar:**
1. **Python dosyalarına dokunma.** `app/core/deck_page.py` ve `app/core/phone.py` içindeki HTML/CSS metinleri istisnadır: sadece HTML/CSS/JS metnini değiştir, Python mantığına ve uç adlarına (`/deck/run`, `/dl/action` vb.) dokunma.
2. **JS'nin bağlandığı kimlikleri koru.** `id`, `data-*` öznitelikleri ve `api.xxx(...)` çağrıları değişmeyecek. Bir öğeyi taşıyabilir, sarabilir, yeniden stillendirebilirsin; adını ve davranışını değiştirme. Bir kimliği değiştirmen gerekiyorsa, onu kullanan bütün JS'yi aynı commit'te güncelle.
3. **Yeni ağır kütüphane yok.** CDN yok; her şey yerel. Animasyon için CSS ve Web Animations API yeter. Mevcut PixiJS (Sunak) ve GSAP varsa onlar kullanılabilir.
4. **TR/EN iki dil.** Yeni metinlerin hepsi mevcut `L(tr, en)` / `edL` / `T()` yardımcılarıyla yazılsın. Sabit Türkçe metin bırakma.
5. **Erişilebilirlik:**
   - Her düğmenin metni ya da `title`/`aria-label`'ı olsun.
   - Klavye ile gezilebilsin.
   - Odak halkası görünsün.
   - Kontrast WCAG AA.
6. **Performans:**
   - 60 fps.
   - Liste ve panellerde gereksiz yeniden çizim yok.
   - `backdrop-filter` yalnızca küçük yüzeylerde kullanılsın.
   - Büyük gölgeler ve blur'ler animasyonda değişmesin.
7. **Tasarım dili (Metehan'ın açık isteği):**
   - Her ekranda aynı "üst bar + yan menü + liste" kalıbını tekrarlama. Her modül kendi karakterini taşısın; gerçekten farklı yerleşimler öner.
   - Kaliteyi yüksek tut. Basit elle çizilmiş SVG logo/karakter "Paint'te yapılmış" görünüyor: ya profesyonel ikon seti kullan ya da hiç kullanma.
   - Mor-yeşil Kami paleti korunur (`--accent #9D6BFF`, `--em/--ok #2EE6A6`, morumsu siyah zemin). Bu palet içinde derinlik ve hiyerarşi kur.
   - Yazı tipleri: başlıklarda Chakra Petch ve Damnation (mevcut), gövdede Segoe UI Variable.
8. **Studio'yu kırma.** `studio.js`'deki `ST`, `modal()`, `busy()`, `toast()`, `AI_TOOLS`, `aiAction` sözleşmeleri aynı kalsın. Akıllı araç kartları `AI_TOOLS.push([...])` ile geliyor; kart görünümünü değiştirebilirsin, diziyi değil.

---

## Parça 1 — Ana pencere (indirme listesi): yeni öğeler

**Dosyalar:** `index.html`, `styles.css`, `app.js` (yalnız görünüm), `queues.js`, `rss.js`, `perfmon.js`, `palette.js`

**1.1 Çoklu kuyruk (`queues.js`)** — şu an liste üstünde basit çip sırası, sağ tık menüsü (`#qMenu`) ve yönetim penceresi (`#qDlg`) var.
- Çipleri (`#qBar .qchip`, `data-qf`, `data-qrun`, `data-qmanage`) kuyruğun durumunu anlatan küçük "rozet kartlara" dönüştür:
  - çalışıyor / bekliyor / zamanlandı
  - ilerleme halkası: `done/total`
  - hız sınırı ikonu
  - saat penceresi
- Başlat/durdur dokunuşu belirgin olsun.
- Listede `qbadge` / `.qbadge.hold` rozetini satır tasarımına yerleştir.
- `#qDlg` satırları (`.qrow`) şu an 6 sütunlu sıkışık bir ızgara. Bunu kart-düzenleyiciye çevir:
  - gün seçici: yuvarlak gün düğmeleri
  - saat aralığı: zaman çizelgesinde sürüklenebilir bir bant görseli. İşlev aynı kalsın: `[data-k=start]` / `[data-k=stop]` time input'ları gizlenebilir ama değerleri bant ile senkron olmalı.

**1.2 RSS akışları (`rss.js`, Takip görünümünün altındaki `#rssSec`)**
- Akış kartları:
  - son çekim zamanı
  - eşleşen/indirilen sayısı
  - filtre rozetleri (içersin / içermesin)
  - kuyruk seçici
- Önizleme (`#rssPrev`, şu an düz metin) eşleşenleri yeşil "✓", eşleşmeyenleri soluk gösteren tablo/liste olsun.
- Filtre düzenleme şu an `prompt()` ile yapılıyor. Bunu satır içi düzenlemeye çevir; `api.rss_update(id, {include, exclude, max_mb})` çağrısı aynı kalsın.

**1.3 İndirme satırı rozetleri** — `app.js` `metaFor`:
- `⚠ bozuk` / `✓` (bütünlük)
- `bozuk, yeniden deneniyor`
- kuyruk rozeti

Bunlar tutarlı bir rozet dili içinde görünsün; renkler anlam taşısın (hata kırmızı, doğrulandı yeşil, kuyruk mor).

**1.4 Performans izleyici (`perfmon.js`, `#kperf`, Ctrl+Shift+P)** — şu an sade bir panel.
- Kompakt ve şık bir "HUD": küçük halka göstergeler (CPU/RAM/GPU) ve alt kırılım çubukları:
  - WebView2
  - aria2
  - ffmpeg
  - yt-dlp
  - yapay zekâ
- 60 sn grafiği (`canvas`) korunur.
- Sürüklenebilirlik korunur.

**1.5 Ctrl+K paleti (`palette.js`, `#kpal`)** — artık uzaktan sonuç da geliyor: `remote: true` öğeler; ikonlar 📄📖🎬📚📡⬇.
- Sonuçları "Komutlar" ve "Dosyalar ve içerik" diye iki bölüme ayır (görsel başlıklarla).
- Klavye gezinmesi (↑↓ Enter) korunur.
- Yerel sonuçlar hemen, uzaktan sonuçlar 180 ms sonra geliyor. Kayma olmasın: sabit yükseklikli satırlar ve yükleniyor iskeleti kullan.

---

## Parça 2 — Telefon: Kami Deck (`app/core/deck_page.py` içindeki `DECK_HTML`) ve eski Pad sayfası (`phone.py` `_BRIDGE_HTML`)

- Deck, Stream Deck hissi vermeli:
  - tuşlar fiziksel tuş gibi (basınca içe gömülme, `navigator.vibrate` mevcut)
  - basma geri bildirimi: `.key.ok` / `.key.err`
  - profil sekmeleri
  - düzenleme modu (titreyen tuşlar, ✕ sil, ◀ ▶ taşı, renk seçici)
- Tuşa ikon yanında küçük etiket gelsin. Emoji yerine ikon seti kullanılabilir; seçim katalogtaki `icon` alanını görsel olarak eşlemeli (eşleme tablosunu JS'de tut).
- İndirmeler sekmesi: kart başına ilerleme halkası; duraklat/sürdür/öne al/kaldır büyük dokunmatik hedefler olsun (en az 44 px).
- iPhone güvenli alanları (`env(safe-area-inset-*)`) korunur.
- **Uçlar:** `POST /deck/data`, `/deck/run {a,arg}`, `/deck/save {profiles,cols}`, `/dl/action {id,action}`, `POST /send`. Başlık: `X-Kami-Key`.

---

## Parça 3 — Tarayıcı eklentisi (`extension/`)

- `popup.html`: yeni `#grabAll` düğmesi ("Sayfadaki her şeyi listele"). Popup'ın hiyerarşisinde doğru yere otursun; birincil eylem "Bu sayfayı Kami ile indir" kalır.
- `grab.html` / `grab.js` ("Tümünü indir" paneli):
  - Tür çipleri sayaçlı geliyor; tablo daha okunur olsun: dosya türü ikonları, satır seçili hali, Shift+tık ile aralık seçme.
  - Filtre çubuğu yapışkan kalsın; 2000+ satırda akıcı kalsın (sanal liste önerilir).
  - `chrome.runtime.sendMessage({type:"grab-send", ...})` sözleşmesi aynı kalır.

---

## Parça 4 — Reader (`reader.html`, `reader.css`, `reader-plus.js`)

- **Kitaplık ana ekranı:** okuma istatistikleri (`#rpPanels .rp-card`) ve seriler artık rafın üstünde.
  - İstatistik kartı: büyük "bugün" sayısı, seri (alev/şerit metaforu, abartmadan), son 14 gün çubukları (`.rp-bars`).
  - Seriler: kapak/afiş alanı, "yeni bölüm" rozetleri (`.rp-badge`), yeni bölüm düğmeleri (`[data-ch]`).
  - Raf (`.rh-shelf`) tasarımı korunabilir ya da iyileştirilebilir; kitap kapakları gerçek kitap gibi derinlikli.
- **Okuma ekranı:** otomatik kaydırma HUD'u (`#rpHud`) küçük ve şık olsun, hız göstergesi görsel. E-kitap yazı boyutu (`,` `.`) için görünür A−/A+ kontrolü ekle; `epubFont(±1)` mantığına bağla. Bunu yalnızca `RD.doc.ebook` olduğunda göster.

---

## Parça 5 — Picture (`picture.html`, `picture.css`, `editor.css`, `editor-pro.js`, `picture-lens.js`)

- **Katman şeridi** (`#edLayers`) yeni düğmeleri `.ed-addly.pro` satırında topluyor: maske, seçimden maske, ayar katmanı seçici, geçmiş, toplu işlem. Bunları Photoshop/Picsart düzeyinde düzenle:
  - katman kartında maske küçük resmi
  - ayar katmanı ikonu (◐)
  - maske düzenleme modunda yeşil kenar (`.badges i.edit`)
- **Maske düzenleme HUD'u** (`#edMaskHud`) ve **geçmiş paneli** (`#edHist`): şık, yarı saydam, sürüklenebilir; geçmişte gelecek adımlar soluk.
- **Toplu işlem penceresi** (`#edBatch`):
  - adım adım sihirbaz: Görseller → Görünüm → Boyut → Filigran → Biçim
  - önizleme: ilk görselde sonucun küçük örneği
  - ilerleme çubuğu
- **Lens paneli** (`#pcLens`): üstte 4 araç (`.lt-bar [data-lt=price|text|table|codes]`).
  - Fiyat sonuçları (`.lt-it`) alışveriş karşılaştırma kartı gibi olsun: Akakçe/Trendyol rozetleri, en düşük fiyat vurgusu, puan/satıcı notu.
  - Tablo önizlemesi (`.lt-tbl`) temiz bir ızgara olsun.
  - QR sonuçları kart halinde.

---

## Parça 6 — Studio (`studio.html`, `studio.css`, `studio-finish.js`, `studio-extra30.js`)

- **Akıllı araçlar** artık çok kalabalık (30+ kart). Kategorilere ayır: Kurgu, Ses, Görüntü, Yapay zekâ, Yayın, Otomasyon. Arama kutusu ve "son kullanılanlar" ekle. Kart verisi `AI_TOOLS` dizisinden gelir: `[id, başlık, açıklama]`. Kategoriyi JS'de id → kategori eşlemesiyle yap; diziyi değiştirme.
- **Çoklu kamera ekranı** (`studio-extra30.js` içindeki tam ekran kutu):
  - Kamera ızgarası yayın masası gibi olsun: canlı kamera kırmızı/yeşil çerçeve, numara rozetleri.
  - Alt kesim şeridi (`#mcBar`) renkli çekim blokları (renkler kamera başına sabit).
  - Klavye ipucu çubuğu.
- **Seslendirme kaydı:** kayıt HUD'u kırmızı "ON AIR" hissi taşısın (yanıp sönme hafif); mikrofon seviyesi göstergesi eklenebilir. Bunu `getUserMedia` akışından `AnalyserNode` ile, yalnızca görsel amaçla yap.
- **Bölümler + açıklama penceresi:** zaman/başlık satırları zaman çizelgesi üstünde nokta olarak da görünsün (isteğe bağlı). YouTube kuralı uyarısı satır içi gösterilsin.
- **Şablonlar:** şablon kartlarına küçük önizleme (boyut, öğe sayısı, renk) ekle.
- **Kısa klipler sonuç penceresi:** her klip için kanca metni, süre çubuğu, "Aç" düğmesi.

---

## Parça 7 — Oda, Kapsül, Player+

- **Oda** (`room.html`, `room.css`, `room.js`):
  - mesaj tepkileri/yanıt/sabitleme (`.rx`, `#pins`, `#replyBar`) ve sohbet arama
  - YouTube birlikte izleme kutucuğu
  - ses efektleri seçimi (`#sVfx`)
  - kişi başı ses kaydırıcısı: artık %0–200; 100 noktasına işaret koy, üstü "güçlendirme" rengi
  - Bunların hepsinin tutarlı bir mesajlaşma dili olsun: Discord/Telegram kalitesinde ama Kami'nin kendi kimliğiyle.
- **Kapsül paylaşım sayfası** (`kapsul.py` içindeki sayfa HTML'i): çok dosya listesi, zip indirme, yorumlar. Karşı tarafın gördüğü sayfa; profesyonel, sade ve güven veren bir indirme sayfası olsun.
- **Player+** (`player-plus.js`, `player.css`):
  - devam rafı, sıradaki bölüm ve akıllı raflar
  - TV/IPTV sekmesi: kanal ızgarası, EPG şimdi/sonra şeridi
  - DLNA yayın seçicisi
  - intro atla düğmesi

---

## Kabul ölçütleri (her parça için)

1. `node --check` tüm değişen JS dosyalarında temiz.
2. Kami'yi aç, ilgili pencerede her yeni öğeye tıkla:
   - konsol hatası yok
   - `api.*` çağrıları aynı
   - TR/EN dil değişince metinler değişiyor
3. 1366×768 ve 2560×1440'ta taşma yok. Telefon Deck'i 375 px genişlikte düzgün.
4. Klavye: Tab ile gezilebiliyor, odak görünür, kısayollar aynı:
   - Studio: `1-9`, `K`, `X`, `H`, `A`, `[ ]`, `, .`
   - Genel: `Ctrl+K`, `Ctrl+Shift+P`
5. Commit mesajı Türkçe ve neyin değiştiğini söylesin; arayüz dışı dosyaya dokunulmadığı belirtilsin.

**Takıldığın yerde:** bir işlevin nasıl çalıştığından emin değilsen ilgili JS dosyasının başındaki açıklama yorumunu oku. Yine emin değilsen o öğeyi olduğu gibi bırak ve commit mesajında not düş. Claude sonra bakar.
