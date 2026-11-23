# DESIGN.md — Kami

Kami'nin tasarım sistemi. Kami'de arayüz değiştiren her ajan (Claude, Antigravity, DeepSeek Harness) önce bu dosyayı okur.
Biçim Google Stitch DESIGN.md düzenini izler. İlham için `C:\Users\fluvoksamine\Projeler\_ref\awesome-design-md` klasörüne bakılabilir,
ama Kami'nin kimliği aşağıdaki kurallardır; başka bir markanın görünümü kopyalanmaz.

## 1. Görsel tema ve atmosfer
- Gece tapınağı / kâğıt tılsım ruhu. Koyu obsidyen zemin, mor krom vurgular, zümrüt yeşili tek "canlı" renk (maskotun gözü, hız, başarı).
- Ana ekran "Sunak" düzenidir: ortada maskot ve hız halkası, indirmeler sıvı gibi dolan tılsım şeritleri. Bu yerleşim korunur.
- Maskot: siyah kâğıt-tılsım ruhu, yanardöner krom boynuzlar, tek yeşil göz (duruma göre canlanır, imleci izler). Rive ile yapılır.
- Logo: Damnation fontu, tek tonlu mor krom. Gökkuşağı gradyanı yok.

## 2. Renk paleti (tek kaynak: `app/ui/web/sunak.css` `--sk-*`)
| Rol | Token | Değer |
|---|---|---|
| Zemin | `--sk-bg` | `#08070C` |
| Yüzey | `--sk-coal` | `#110E17` |
| Yükseltilmiş yüzey | `--sk-plum` | `#1C1228` |
| Çizgi/kenar | `--sk-line` | `#4A3D63` |
| Birincil vurgu | `--sk-violet` | `#8B5CF6` |
| Koyu vurgu | `--sk-royal` | `#6D28D9` |
| Açık vurgu / başlık | `--sk-lav` | `#C4B5FD` |
| Metin | `--sk-text` | `#EDE9F6` |
| İkincil metin | `--sk-mute` | `#A39BB5` |
| Canlı / başarı | `--sk-em` | `#2EE6A6` (koyu: `#0FA37A`) |
| Hata | `--sk-err` | `#FF4D6A` |
| Uyarı | `--sk-warn` | `#F5B94A` |

- Kırmızı yalnız hata içindir; tür/kategori renklerinde kırmızı kullanılmaz (`--cat-*`, `styles.css`).
- Yeni bir renk eklemeden önce yukarıdakilerden birini kullan. Alt pencereler (Cleaner, Enhance, Music Tag, Beat, Companion…) aynı tokenları kullanır; sabit hex yazılmaz.
- Açık tema yoktur (19.11'de kaldırıldı).

## 3. Tipografi
- Arayüz ve başlıklar: **Chakra Petch** (her alt sayfada `@font-face` tanımlı olmalı). Gövde için sistem yedeği: Segoe UI Variable.
- Kamify şarkı sözleri: Chakra Petch.
- Logo: Damnation (yalnız logo).
- Sayılar (hız, süre, boyut): `font-variant-numeric: tabular-nums`.

## 4. Bileşen kuralları
- **Yuvarlatılmış köşeli kutu yok.** Kartlar, paneller ve butonlar keskin köşeli ya da kesik köşeli (chamfer) olur. Eski `--r-sm/--r-md` değerleri yenilerde kullanılmaz.
- Yıldız süsü yok. Maskotun üstünde harf amblemi yok. Korku filmi tarzı kir/pas dokusu yok.
- Butonlar: birincil = mor dolgu + koyu metin; ikincil = şeffaf + `--sk-line` kenar; tehlikeli = `--sk-err` kenar, onay ister (tarayıcı `confirm()` değil, satır içi onay).
- Simge butonlarının hepsinde `aria-label` (Türkçe) ve `title` olur.
- Odak: `:focus-visible` her zaman görünür (2px `--sk-violet` dış çizgi). `outline: none` yazılacaksa yerine odak göstergesi konur.
- Boş ekranlar: büyük ortalanmış küçük yazı yerine maskot pozu + tek net eylem ("URL izle", "Klasör ekle").
- Modül pencerelerinin başlık çubuğu uygulama rengine boyanır (`winwin.tint_own_windows`); gri Windows başlığı kalmaz.

## 5. Yerleşim
- Modül üst sekmeleri: Player, Studio, Picture, Reader, Games, Kamify, Cleaner (+ Beat). Sağ dok çekmeceleri ikincil araçlar içindir.
- Aynı arayüz şablonu her modülde tekrarlanmaz (üst bar + sol menü + liste kalıbı her yerde olmasın); her modül işine uygun düzeni alır (Studio: NLE, Beat: DAW şeridi, Player: tam ekran sahne).
- Uzun listeler (kütüphane, indirme geçmişi, yerel müzik) sanallaştırılır.

## 6. Hareket
- Ortak katman: `kami-motion.css` + `kami-motion.js`. Yeni animasyon önce buraya eklenir.
- Süreler: mikro etkileşim 120–180 ms, panel/çekmece 220–320 ms, sahne geçişi en çok 450 ms. Yaylı (spring) kolaylaştırma tercih edilir.
- `prefers-reduced-motion` ve Kami'nin düşük güç modu (`kamiSetLowPower`) her animasyonu kapatabilmelidir.
- Onaylı yön: "Ruh ateşi" arka planı (maskotun altındaki yeşil alevden yükselen zümrüt duman telleri, hızla büyür, indirme bitince tek parlama). Reddedilen: "Rün çemberi", "Veri akışı".
- HyperFrames canlı arayüzde kullanılmaz; yalnız önceden üretilmiş kısa WebM klipler için.

## 7. Görsel varlıklar
- İkon/görsel arayüze konmadan önce kullanıcıya gösterilir ve onay alınır.
- Kodla çizilmiş 3D karakter veya "paint gibi" el çizimi SVG maskot kullanılmaz.

## 8. Kalite kapısı (her arayüz değişikliğinde)
1. `web-design-guidelines` skill'i ile değişen dosyaları denetle (erişilebilirlik, odak, kontrast).
2. Playwright CLI ile ekran görüntüsü al, gözle kontrol et (bulut düzeneği veya PC'de headless).
3. Kurulu exe'de canlı dene; `kami.log`'da yeni `Arayuz hatasi` satırı olmasın.
