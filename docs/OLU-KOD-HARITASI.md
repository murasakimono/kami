# Kami — Versiyon Sonekli Dosyalar: Aktif / Ölü Kod Haritası

Tarih: 20.11.2026 · Tarama: app/**/*.py (import) + app/ui/web/*.js (HTML script + dinamik yükleme)

## Sonuç (özet)

- **Hiçbir versiyon sonekli dosya ÖLÜ değil.** Tümü aktif olarak import ediliyor / yükleniyor.
- Ölü Python modülü: **0** · Ölü JS dosyası: **0**
- Gerçek sorun "ölü kod" değil, **birikme (accretion)**: aynı modül için çok sayıda parça dosya yan yana duruyor.
  Silinecek dosya YOK; ama birleştirme/veriye dönüştürme fırsatı var (aşağıda).

## Python — app/core/studio_*.py (hepsi AKTİF)

Sonek = içerik paketi "dalgası". studio.py hepsini import edip tek katalogda birleştirir.

| Dosya | İçerik | Kim import ediyor |
|---|---|---|
| studio_fx2/3/4.py + studio_fx_adv.py | FX efekt dalgaları 2-4 + gelişmiş | studio.py (fx_adv ayrıca studio_mcp.py) |
| studio_pro_pack.py / _pack2 / _pack3 / _pro_v26.py / _pro_plugins.py | Pro paket dalgaları (1.26 Pro dahil) | studio.py, studio_anim, studio_brand, studio_fx_adv, studio_motion, api_studio, studio_mcp |
| studio_gfx.py / _gfx_pack2.py | Grafik paketleri | studio.py (gfx_pack2 studio_gfx.py'den) |
| studio_anim.py / _anim_pack.py | Animasyon paketleri | studio.py (birbirini de) |
| studio_trans2.py | Geçişler | studio.py |
| studio_motion/workflow/edit/audio/enhance/finish/packs/shorts/brand/tr_memes.py | Alt modüller | api_studio.py + studio_mcp(_pro).py + studio.py |
| studio_mcp.py / studio_mcp_pro.py | MCP araçları | main.py, api_studio.py, flow_chain, local_copilot, studio_shorts |

## JS — app/ui/web/* (hepsi AKTİF)

-v138 = 1.38 arayüz dalgasının **güncel** dosyaları (eski değil; baz dosyadan SONRA yüklenip üzerine genişletir).
-plus/-pro/-extra/-extra30 = artımlı özellik eklemeleri (baz dosyanın yanında yüklenir).

| Modül | Yüklenen parça dosyalar | Adet |
|---|---|---|
| Player (player.html) | player, player-lib, player-music, player-extra, player-pro, player-plus, player-watch, player-v138, player-shell | 9 player*.js |
| Studio (studio.html) | studio, studio-fx, studio-gl, studio-scopes, studio-panels, studio-pages, studio-ux, studio-finish, studio-extra30, studio-v138 | 10 studio*.js |
| Picture (picture.html) | picture, picture-lens, picture-v138 + editor, editor-fx, editor-ai, editor-pro, editor-photopea | 3 picture + 5 editor |
| Kamify (music.html) | kamify-v138 (tek parça) | 1 |
| Reader (reader.html) | reader, reader-plus, reader-curl | 3 |

## Neden sonekli isimler var

- fx2/3/4, pro_pack 1/2/3, pro_v26: içerik paketleri zamanla eklendikçe dosya dosya büyüdü; studio.py hepsini birleştiren tek "birleşim noktası".
- -v138, -plus, -pro, -extra30: arayüz/özellik dalgaları baz dosyaya dokunmadan yan dosya olarak eklendi (çakışmayı önlemek için).

## Öneri (silme YOK)

1. **İsimler yanıltıcı:** -v138 "eski sürüm" gibi okunuyor ama güncel dosya. Birleştirme sırasında sonekleri kaldır.
2. **Birleştirme adayları:** Player 9 → player-core + player-music + player-watch; Studio 10 → studio-core + studio-fx + studio-pro; Picture editor 5 → editor-core + editor-ai + editor-photopea.
3. **Python paketlerini veriye çevir:** studio_fx*/pro_pack* içerikleri çoğunlukla sözlük (katalog) — koda değil JSON/veri dosyasına taşınabilir; studio.py tek yükleyici olur.
