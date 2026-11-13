# Kami — Faz 7–18 Ana Yol Haritası (Birleştirilmiş 12 Ana Faz)

> **Tarih:** 2026-11-13  
> **Durum:** Onaylanmış Nihai Yol Haritası (eski 44 parçalı Faz 7–50 taslağı **12 Ana Faz** halinde birleştirildi; hiçbir özellik çıkarılmadı).  
> **Faz Sonu Kuralı:** Her faz kodlandıktan sonra `pytest` + `node --check` + `packaging/build.ps1` ile derleme (`build`) alınır ve bir sonraki fazda nelerin yapılacağı özetlenir.

## Mimari İlkeler ve Kısıtlar
1. **RTX 4050 (6 GB VRAM) Tavanı:** Tüm yerel AI modelleri FP16 / NF4 / Q4_K_M, `enable_model_cpu_offload()`, `vae.enable_tiling()`, kayan pencere (sliding-window) ve `pynvml` ön-kontrolü ile 6 GB altında çalışır.
2. **Sıfır Ücret & Zero Rive:** Rive (filigran/ücretli katman) kesinlikle kullanılmaz. Tüm araçlar açık kaynak ve ücretsizdir.
3. **Sıfır Uzmanlık UX:** Her karmaşık Premiere/AE/Photoshop/Audio tekniği tek tık **Hazır Şablon / Asistan** ve `studio_mcp.py` **`run_recipe`** doğal dil reçeteleriyle sunulur.

---

## Faz 7 — Çekirdek Altyapı, Performans, VRAM Güvenliği & Masaüstü
* **7.1 WebView2 `SharedArrayBuffer` Kilidi (`app/main.py`):** Yerel sunucu yanıtlarına `Cross-Origin-Opener-Policy: same-origin` ve `Cross-Origin-Embedder-Policy: credentialless` başlıkları eklenir (`ffmpeg.wasm`, `SoundTouch/RubberBand` AudioWorklet, `ONNX Runtime Web` çoklu iş parçacığı açılır).
* **7.2 `pynvml` + `psutil` Canlı VRAM/NVENC Ön-Kontrol HUD'u:** Her AI aracı çalışmadan önce boş VRAM'i ölçer; yetersizse önceki modeli boşaltır (`torch.cuda.empty_cache()`) veya güvenli CPU/int8 moduna düşer (sıfır sessiz OOM).
* **7.3 `WebGL2 FBO` & `WebCodecs` Smart Render Cache (`studio-fx.js`, `studio-gl.js`):** Canvas 2D kare kopyalama darboğazı GPU ping-pong FBO dokularına taşınır; ağır timeline bölümleri arka planda önbelleğe alınır.
* **7.4 Çoklu Profil İzolasyonu:** Tek tıkla **Kişisel / İçerik Üretimi / Mağaza-İş** profilleri (ayrı indirme klasörü, Marka Kiti, Sunak teması, `Kami Kasa` DB).
* **7.5 Masaüstü Mini-Ada Şeridi:** Şeffaf `always-on-top` şeritte indirme hızı, çalan şarkı spektrumu, VRAM göstergesi ve tek tık `30sn Klip` / `Dropover Rafı`.

---

## Faz 8 — Kami Studio: Premiere Pro Kurgu & Ses Restorasyonu
* **8.1 Metin Tabanlı Kurgu (`faster-whisper` + `stable-ts`):** Kelime bazlı transkriptten seç-sil kurgu (`±40ms` mikro crossfade) + `EDL/XML` dışa aktarma.
* **8.2 Multi-Cam Otomatik Ses Senkronu (`scipy.signal.correlate` FFT):** 2–4 kamera/mikrofon kaydını 8 kHz mono PCM korelasyonuyla milisaniye hassasiyetinde hizalama.
* **8.3 Premiere Çekirdek Araçları:** Ripple / Roll / Slip / Slide Trim (`B/N/Y/U`), J-Cut / L-Cut asistanı, `Kdenlive` tarzı **Adjustment Clips** ve **Compound Clips**, `LosslessCut` (`-c copy`) kayıpsız kesim.
* **8.4 Yayın Standardı Ses & Dereverb:** `FFmpeg loudnorm` (-14 LUFS) + `sidechaincompress` (konuşma altında müzik otomatik ducking); `DeepFilterNet` (<1 GB VRAM) + `ClearerVoice MossFormer2_SE_48K` (kayan pencere 6 GB VRAM) yankısız stüdyo mikrofonu restorasyonu.
* **8.5 Podcast Diarization & Altyazı Pro:** `Silero VAD` + `NVIDIA NeMo Sortformer` (token-free konuşmacı ayırma) + `SubtitleEdit CLI` CPS/satır/zamanlama denetimi.

---

## Faz 9 — Kami Studio: After Effects, 3D/2.5D, Scopes & Viral Paketler
* **9.1 Bezier Graph & DAG Düğüm Kompozitör:** Speed/Value Bezier eğri editörü + GPU Shutter Angle Motion Blur (`u_shutterAngle / 360.0`) + `Olive 0.2+` mantığıyla WebGL2 FBO düğüm grafiği.
* **9.2 Kinetik Tipografi (`harfbuzzjs` + `opentype.js` + MSDF):** Değişken font eksen (`wght/wdth/slnt`) keyframe animasyonu ve sınırsız zoom'da keskin MSDF WebGL metin render'ı.
* **9.3 Colorist Scopes Kokpiti (WebGL2 Point-Sprite):** `Waveform`, `RGB Parade`, `Vectorscope`, `Histogram`, `False Color`, `Zebra` (`gl.blendFunc(SRC_ALPHA, ONE)`).
* **9.4 2.5D/3D Kamera, Takip & Talker:**
  * `Depth-Anything-V2-Small` (<2 GB VRAM) → WebGL2 2.5D paralaks kamera + `vt-vl-lab/3d-photo-inpainting` LDI.
  * `Spark.js` (`sparkjsdev/spark`, MIT) `.ply/.spz/.ksplat` 3D Gaussian Splatting sahne gezintisi.
  * `Gyroflow` CLI video stabilizasyonu, `OpenCV ORB + RANSAC` planar tracking, `recorder.py` `.cursor.json` Screen Studio tarzı otomatik fare zoom'u.
  * `MuseTalk` (MIT, `--use_float16` 4–5.5 GB VRAM) dudak senkronu + `LivePortrait` ifade aktarımı.
* **9.5 Marka Kiti & 5 Viral Kurgu Paketi (`studio_mcp.py run_recipe`):** Iman Gadzhi, MagnatesMedia, Ali Abdaal, Valorant/CS2 (RIFE + Saber + Duvar Arkası 3D Metin) ve `@lottiefiles/dotlottie-web` (ThorVG) paketleri.

---

## Faz 10 — Kami Picture: Photoshop, Lightroom, Mockup & 6 GB VRAM AI
* **10.1 Tahribatsız Katmanlar & WebGL2 Stilleri (`editor.js`):** `kind: "adj"` ayar katmanları, WebGL2 `Bevel & Emboss`, `Inner/Outer Glow`, `Halftone/Risograph`, `Frequency Separation`, `seam-carving` içerik duyarlı ölçekleme, `Liquify & Clone Stamp`.
* **10.2 Lightroom, `colour-science` & Tethered Capture:** Analytical `AgX`, `Dehaze + Clarity + Vibrance`, `colour-science` referans fotoğraf → `.cube` 3D LUT klonlama, HaldCLUT ↔ `.cube`, Darktable Sigmoid/Filmic, HDR Merge & Focus Stacking, iPhone Tethered Live Capture.
* **10.3 `Kami Mockup` & `Kami Vektör`:**
  * `BiRefNet` (`studio_matte_run.py`) ortak dekupe + %12 boşluk/zemin gölgesi e-ticaret toplu stüdyosu.
  * `findHomography` + `cv2.remap` kumaş/kupa/kutu giydirme (`automated_mockups`).
  * `vtracer` (Raster→SVG), `mixfont/lens` (görselden font bulma), `OKLCH` algısal palet üretici.
* **10.4 6 GB VRAM Üretken AI, `TripoSR` & Telif İmzası:**
  * `SDXL-Lightning` (4-step) + `ControlNet Canny/Depth` + `Flux.1-dev-nf4` (`enable_model_cpu_offload()` + `vae.enable_tiling()`).
  * `IC-Light` yeniden ışıklandırma + `RealESRGAN/GFPGAN`.
  * `TripoSR` (MIT, ~6 GB VRAM) tek fotoğraftan `.glb` 3D model.
  * `blind-watermark` (DCT+SVD) sıkıştırmaya dayanıklı görünmez telif imzası + `ComfyUI` headless API (`--medvram --force-fp16`) & `IOPaint` köprüsü.

---

## Faz 11 — Downloader, DVR, Web Arşivi & Medya Sağlığı
* **11.1 `aria2c` Torrent Önizleme & DHT Kalıcılığı (`aria2_engine.py`):** `--file-allocation=none` **korunur**; `--bt-prioritize-piece=head=20M` ve `--bt-save-metadata=true --dht-file-path=...` eklenir (`ngosang/trackerslist` zaten `torrent.py`'de mevcut).
* **11.2 JSON `LinkCrawler` & Çoklu Ayna:** Eklentisiz JSON kurallarıyla yeni host/gömülü akış çözme ve ayna failover (`mirrors.py` ile uyumlu).
* **11.3 Canlı Yayın DVR & Web Arşivi:** `yt-dlp --live-from-start` canlı yayın kaydı, tek dosya HTML web arşivi (mevcut `mediatools.py` SponsorBlock yapısına dokunmadan `--embed-chapters`).
* **11.4 Çift Dosya, Akıllı Sıkıştırma & Sağlık:** Algısal hash (`dHash` / FFmpeg kare imzası) çift medya temizliği, `av1_nvenc`/`hevc_nvenc` + `libvmaf ≥ 95` doğrulamalı sıkıştırma, `ffmpeg -v error` + `SHA-256` bit-rot tarayıcısı (TMDB/MusicBrainz/`smart_series_folders` zaten mevcut olduğu için dokunulmaz).

---

## Faz 12 — Player, Canlı DSP, Karaoke & Ses/Müzik Stüdyosu
* **12.1 `libplacebo` Sınıfı WebGL2 Video & Sahne Haritası:** `KrigBilateral`, `SSimSuperRes`, `Adaptive Deband + Grain`, `PySceneDetect` görsel sahne çubuğu.
* **12.2 WebAudio `AudioWorklet` Canlı DSP (`player.js`):** `SoundTouch/RubberBand` WASM (pitch/tempo bağımsız), Canlı Diyalog Netleştirme, `ReplayGain 2.0`.
* **12.3 Karaoke, Beatgrid & Shader Görselleştirici:** Kelime senkronlu karaoke (mevcut `lyrics.py` LRC üzerine), BPM/downbeat/akor haritası (`kami_beat.py` genişletme), saf WebGL2 shader müzik görselleştirici.
* **12.4 `Kami Ses Kutusu` & Tarayıcı DAW:** Spotify `pedalboard` (JUCE VST3 host), `audio-separator` (`Mel-Band RoFormer`/`MDX23C`), Spotify `Basic Pitch` (Audio→MIDI), `Kokoro-82M`/`Piper` TTS, `Stable Audio Open Small` yerli SFX, `Seed-VC` ses dönüşümü, `Tone.js`/WebAudio 16-adımlı davul makinesi & synth.

---

## Faz 13 — Kami Kasa: Semantik Medya Arşivi & Akıllı Özetleyici
* **13.1 Semantik Arama:** `google/siglip-base-patch16-224` (<1 GB VRAM) + `PySceneDetect` + `sqlite-vec` + `SQLite FTS5` WAL (`"gece yağmurda neon sokak"` → doğrudan video saniyesine atla).
* **13.2 50.000+ `VirtualGrid` & Akıllı Özet:** DOM geri dönüşümlü yüksek hızlı ızgara ve uzun kayıt oto-bölümlendirme (`Whisper` + `Qwen2.5` / yerel özetleyici).

---

## Faz 14 — Kami Klip Fabrikası, Oyun Vurgu & Sanal Kamera
* **14.1 Açık Kaynak OpusClip (`supoclip`):** Uzun videodan en vurucu anları seçip `YOLOv8n`/`MediaPipe` yüz takibiyle 9:16 dikey kurguya çevirme.
* **14.2 E-Ticaret UGC A/B Hook Matrisi:** `3–5 Hook × 1 Gövde × 2 CTA` kombinasyonlarını TikTok/Reels safe-zone kontrolüyle tek tıkta toplu render.
* **14.3 Oto Oyun Vurgu & Sanal Kamera:** Mevcut `recorder.py` replay altyapısına otomatik oyun algılama + köşe kill-feed/VICTORY ROI izleme ile oto-`save_replay()`; `pyvirtualcam` + `RobustVideoMatting` sanal web kamerası.

---

## Faz 15 — Kami Belge & Manga Çeviri Stüdyosu
* **15.1 Evrensel Belge Dönüştürücü:** `PyMuPDF4LLM` (hızlı dijital PDF→MD), `Marker`/`Docling` (tablo + LaTeX→MD), `Pandoc` (`MD ↔ DOCX ↔ EPUB ↔ LaTeX`) — `pdf_ocr.py` zaten Türkçe aranabilir PDF ürettiği için korunur.
* **15.2 `Kami Manga` Çevirici:** `zyddnys/manga-image-translator` (6 GB VRAM) ile konuşma balonu tespiti + inpaint + Türkçe dizgi.

---

## Faz 16 — Kami Köprü, LAN Paylaşım, Pano & Sesli Komut
* **16.1 Kablosuz Ekran Yansıtma:** `UxPlay` (iPhone/iPad AirPlay) + `scrcpy` Android yansıtma → doğrudan Studio/Recorder içine kayıt (mevcut `phone.py` Kestirme köprüsüne ek).
* **16.2 LAN P2P Paylaşım (`aiortc`):** Harici sunucusuz aynı ağda 60 FPS ekran ve büyük dosya aktarımı.
* **16.3 `Kami Pano` (`Dropover` Rafı) & Tasarım Yardımcıları:** Yüzen sürükle-bırak rafı, evrensel `OKLCH` renk seçici, piksel cetveli (mevcut `ocr.py` ve `clipboard.py` ile entegre).
* **16.4 "Hey Kami" Sesli Komut:** `Silero VAD` (<0.5 GB) + `faster-whisper-tiny` eller serbest kısayollar.

---

## Faz 17 — Sunak GPU Yükseltmesi & Kukla Maskot
* **17.1 `PixiJS v8` (MIT) GPU Sunak Sahnesi:** Mevcut `sunak.js` DOM katmanını hız halkası, sıvı dolan tılsım şeritleri ve partiküllerle `0.5 ms` GPU render'a yükseltme.
* **17.2 `Inochi2D` / `PixiJS Mesh` Kukla Maskot:** Mevcut `eye/kami_eye.js` ve `sunak-sfx.js` kostüm/ses altyapısını tek gözlü siyah kâğıt-tılsım ruhu + krom boynuzlu eklemli kuklaya yükseltme.

---

## Faz 18 — Yerel Copilot, Akış Zinciri & Başsız SDK
* **18.1 %100 Çevrimdışı Yerel Copilot (`Ollama Qwen2.5:7b` Q4_K_M):** `num_ctx: 8192` ile 6 GB VRAM'de doğrudan mevcut `studio_mcp.py` araçlarını çağıran yerel ajan.
* **18.2 `Kami Akış Zinciri` (`LiteGraph.js` MIT):** Görsel düğüm bağlama ile kişisel klasör/AI/export makroları.
* **18.3 `.kamipack` Güvenli Reçete Pazarı & `kami-cli` SDK:** Şema-doğrulamalı JSON/GLSL paket paylaşımı + GUI açmadan `kami-cli run recipe.json` ile tam otonom **Personal Media OS**.
