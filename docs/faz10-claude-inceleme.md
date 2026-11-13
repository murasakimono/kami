# Claude Code / Claude İnceleme Rehberi — Faz 10

## Faz 10 Özeti (`1.18.0` — Kami Picture Pro, Lightroom, Mockup & 6 GB VRAM AI)
### Yeni / Değişen Dosyalar
1. **`app/core/picture_pro.py`**
   - **10.1 Photoshop Pro:** `frequency_separation` (Low/High frekans ayrımı), `seam_carve_resize` (Sobel enerji + DP içerik duyarlı ölçekleme), `apply_adjustment_layer` (`exposure`, `vibrance`, `dehaze`, `agx`, `sigmoid`).
   - **10.2 Lightroom & LUT:** `agx_tonemap`, `sigmoid_tonemap`, `clone_lut_from_reference` (referans fotoğraftan `.cube` 3D LUT klonlama), `cube_to_haldclut`, `hdr_merge_mertens`, `focus_stack_laplacian`.
   - **10.3 Kami Mockup & OKLCH:** `ecommerce_studio_pack` (%12 boşluk + zemin gölgesi), `perspective_mockup` (4 köşe homografi/perspektif giydirme, `cv2` bağımsız), `oklch_palette` (algısal OKLCH + HEX palet).
   - **10.4 Telif İmzası & 6 GB VRAM AI Köprüleri:** `embed_blind_watermark` / `extract_blind_watermark` (3x oylamalı bit-plane QIM görünmez imza), `ai_bridge_status` (`ComfyUI :8188`, `IOPaint :8080`, `vram_guard.preflight(4500)`).
2. **`app/ui/web/editor-fx.js` & `app/ui/web/picture.html`**
   - `EFX`: `applyLayerStyles` (`Outer Glow`, `Bevel & Emboss`, `Halftone/Risograph`) ve `renderAdjustmentCSS`.
3. **`app/ui/api.py`**
   - `pic_freq_sep`, `pic_seam_carve`, `pic_clone_lut`, `pic_cube_to_hald`, `pic_hdr_merge`, `pic_focus_stack`, `pic_ecom_pack`, `pic_mockup`, `pic_oklch_palette`, `pic_watermark_embed`, `pic_watermark_read`, `pic_ai_bridge_status`.

### Doğrulama Komutları (Claude İçin)
```powershell
cd C:\Users\fluvoksamine\Projeler\kami
node --check app/ui/web/editor-fx.js
uv run pytest tests/test_faz10.py -v --basetemp=.pytest_tmp
```
