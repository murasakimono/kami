# Faz 14 — Claude İnceleme Özeti

## Kapsam
1. **14.1 Kami Klip Fabrikası (`app/core/clip_factory.py`):**
   - `auto_vertical_reframe()`: `MediaPipe` yüz merkezi (varsa) veya `x_ratio` ile yatay videoyu 9:16 (`1080×1920`) dikey formata kırpar.
   - `score_highlight_segments()` & `extract_viral_clips()`: Transkript kanca kelimeleri/yoğunluğuna göre en vurucu pencereleri seçip dikey klipler üretir.
2. **14.2 E-Ticaret UGC A/B Hook Matrisi (`app/core/clip_factory.py`):**
   - `safe_zone_rect()` (`tiktok`, `reels`, `shorts` arayüz güvenli alan hesaplayıcı) ve `render_ugc_matrix()` (`Hook × Gövde × CTA` toplu dikey render).
3. **14.3 Oto Oyun Vurgu & Sanal Kamera (`app/core/game_highlight.py`):**
   - `HighlightWatcher`: Windows aktif pencere başlığı (`active_window_title`) oyun eşleşmesi + ROI OCR (`ocr.read_text`) ile `"VICTORY"/"ACE"/"PENTAKILL"` yakalayınca `cooldown_sec` korumalı şekilde mevcut `recorder.save_replay()` tetikler.
   - `virtual_camera_status()`: `pyvirtualcam` ve GPU matting hazırlık durumunu raporlar.
4. **API & Testler (`app/ui/api.py`, `tests/test_faz14.py`):**
   - `clip_factory_vertical`, `clip_factory_highlights`, `clip_factory_ugc_matrix`, `highlight_watcher_start`, `highlight_watcher_stop`, `highlight_watcher_status`, `virtual_cam_status`.
   - `pytest tests/test_faz7.py .. tests/test_faz14.py`: **29/29 passed**.
