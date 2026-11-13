# Claude Code / Claude İnceleme Rehberi — Faz 7 & Faz 8

> Sunucu 502 kesintisi nedeniyle bu dosya, Claude geri döndüğünde **Faz 7 (`v1.15.0`)** ve **Faz 8 (`v1.16.0`)** eklemelerini tek okumada kontrol edebilmesi için hazırlandı.

## 1. Faz 7 Özeti (`v1.15.0` — commit `549e8ea`)
* **7.1 COOP/COEP + `SharedArrayBuffer`:** `app/core/web_isolation.py` (`UiIsolationServer`, tercih edilen port `47395` + fallback) ve `app/core/media_server.py` (`Cross-Origin-Resource-Policy: cross-origin`). Mevcut `file://` kökenindeki `localStorage` anahtarlarını (`kami.*`, `kst*`) bozmadan izole worker/iframe bağlamı sunar.
* **7.2 Canlı VRAM/NVENC HUD:** `app/core/vram_guard.py` (`nvidia-ml-py` + `psutil`). `snapshot()` ve `preflight(required_mb)` 6 GB RTX 4050 için OOM ön-kontrolü yapar; üst çubuktaki `#vramHud` güncellenir.
* **7.3 WebGL2 FBO & SmartCache:** `app/ui/web/studio-gl.js` (`ensureFbo`, `processToFbo`, `disposeFbo`) ve `app/ui/web/studio-fx.js` (`SmartCache` LRU kare önbelleği + `webCodecsInfo()`).
* **7.4 Çoklu Profil İzolasyonu:** `app/core/profiles.py` (`ProfileStore`: `Kişisel`, `İçerik Üretimi`, `Mağaza-İş` + özel profiller). İndirme alt klasörünü ve `accent_theme` ayarını izole eder.
* **7.5 Masaüstü Mini-Ada:** `app/ui/web/mini-island.html`, `app/main.py`, `app/ui/api.py` (`mini_island_state`, `mini_island_toggle`). `440x52` her zaman üstte şerit.

---

## 2. Faz 8 Özeti (`v1.16.0` — Premiere Kurgu, Metin Montaj & Broadcast Ses)
### Yeni / Değişen Dosyalar
1. **`app/core/studio_edit.py`**
   - `transcript_to_cuts(words, keep_indices, total_dur, pad, merge_gap)`: Metin tabanlı kurgu (silinen kelimeleri çıkarıp kalan aralıkları birleştirir).
   - `remap_captions_for_cuts(captions, cuts)`: Kesim sonrası altyazıları yeni zaman çizelgesine kaydırır.
   - `compute_audio_offset(ref, target, sample_rate)` & `multicam_sync(ffmpeg, paths)`: `8000 Hz` mono PCM üzerinden FFT çapraz-korelasyon (numpy + saf Python fallback) ile milisaniye düzeyinde multi-cam gecikme tespiti.
   - `apply_timeline_edit(clips, mode, clip_id, delta, edge)`: `ripple`, `roll`, `slip`, `slide` zaman çizelgesi kurgu operatörleri.
   - `apply_jl_cut(clip, audio_lead, audio_tail)`: J-Cut / L-Cut ses giriş/çıkış ofsetleri.
   - `create_compound_clip` & `expand_compound_clip`: Bileşik klip paketleme ve geri açma.
   - `build_smart_cut_cmd` & `smart_cut`: Yeniden kodlamadan (`-c copy -avoid_negative_ts make_zero`) kayıpsız kesim.
2. **`app/core/studio_audio.py`**
   - `loudnorm_filter`, `voice_enhance_filter`, `build_ducking_filter`: `-14 LUFS` EBU R128, `highpass=f=85 + afftdn + acompressor + equalizer`, ve `sidechaincompress` otomatik ducking.
   - `enhance_audio_file`, `duck_music_with_voice`: Gerçek `ffmpeg` çalıştırıcıları.
   - `assign_speakers`, `build_bilingual_ass`, `build_bilingual_srt`, `subtitle_edit_convert`: Çoklu konuşmacı renkli ASS ve çift dilli ASS/SRT motoru + opsiyonel `SubtitleEdit CLI` köprüsü.
3. **`app/ui/api_studio.py`**
   - Eklenen `Api` metotları: `studio_transcript_cuts`, `studio_multicam_sync`, `studio_timeline_edit`, `studio_jl_cut`, `studio_compound_create`, `studio_compound_expand`, `studio_smart_cut`, `studio_audio_enhance`, `studio_audio_duck`, `studio_bilingual_subs`, `studio_subtitle_edit`.
   - `STUDIO_JOBS` içine eklendi: `studio_multicam_sync`, `studio_smart_cut`, `studio_audio_enhance`, `studio_audio_duck`.
4. **`app/ui/web/studio.html` & `app/ui/web/studio.js`**
   - `#tlbar` içine `#editModeSel` (`Normal/Ripple/Roll/Slip/Slide`), `⚡ SmartCut`, `🎙 Netleştir`, `⧉ Bileşik` kontrolleri eklendi.

### Kontrol & Doğrulama Komutları (Claude İçin)
```powershell
cd C:\Users\fluvoksamine\Projeler\kami
node --check app/ui/web/studio.js
node --check app/ui/web/studio-gl.js
node --check app/ui/web/studio-fx.js
uv run pytest tests/test_faz7.py tests/test_faz8.py -v
uv run pytest -q
```

### Not Edilen Bilinçli Kapsam Sınırları
- `apply_timeline_edit` şu an API üzerinden tam deterministik çalışır; `studio.js` içinde `#editModeSel` UI durumu (`ST.editMode`) tutarlıdır, sürükle-bırak kenar tutamaçlarının doğrudan `roll/slip/slide` çağrısına bağlanması Faz 9'daki Bezier/Graph etkileşimiyle genişletilebilir.
- `faster-whisper` / `DeepFilterNet` / `NeMo Sortformer` / `SubtitleEdit.exe` kullanıcı ortamında kurulu olmasa bile tüm Faz 8 fonksiyonları yerleşik `ffmpeg` + `numpy`/Python zincirleriyle %100 çalışır (sıfır çökme).
