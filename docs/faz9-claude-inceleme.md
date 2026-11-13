# Claude Code / Claude İnceleme Rehberi — Faz 9

> **Not:** Faz 7–8 incelemesi için [faz7-8-claude-inceleme.md](faz7-8-claude-inceleme.md) dosyasına bakın. Kullanıcı kararıyla bundan sonraki GitHub release'leri **Faz 12 sonu**, **Faz 15 sonu** ve **Faz 18 sonu** toplu alınacaktır; ara fazlar `pytest` + `node --check` + `git commit/push` ile doğrulanır.

## Faz 9 Özeti (`1.17.0` — AE Hareket, Scopes, 2.5D/Takip, Marka Kiti & Viral Paketler)
### Yeni / Değişen Dosyalar
1. **`app/core/studio_motion.py`**
   - `cubic_bezier(p1x, p1y, p2x, p2y, t)` & `BEZIER_PRESETS`: Newton-Raphson kübik Bezier çözücü.
   - `shutter_blur_params(shutter_angle, fps)`: After Effects Shutter Angle (0–360°) -> GPU/ffmpeg hareket bulanıklığı parametreleri.
   - `kinetic_text_plan(...)`: Kelime bazlı kinetik tipografi ve değişken font ekseni (`wghtFrom/wghtTo`, `msdf: True`).
   - `cursor_auto_zoom(events, width, height, zoom_scale, hold_sec)`: `.cursor.json` fare tıklama/hareket olaylarından Screen Studio tarzı otomatik zoom/pan keyframe'leri.
   - `parallax_25d_plan(...)`, `gyroflow_status()`, `musetalk_preflight()` (`vram_guard.preflight(required_mb=4200)` entegreli).
2. **`app/core/studio_brand.py`**
   - `BrandKitStore`: `data/brand_kits.json` içinde profil bazlı marka renkleri, font ve safe-zone saklar.
   - `VIRAL_RECIPES` & `apply_viral_recipe`: `iman_gadzhi`, `magnates_media`, `ali_abdaal`, `fps_frag`, `minimal_shorts` (5 tek-tık viral kurgu reçetesi).
3. **`app/ui/web/studio-scopes.js`**
   - `SScopes`: Gerçek zamanlı `Waveform`, `RGB Parade`, `Vectorscope` ve `Histogram` çizici.
4. **`app/core/studio_mcp.py`**
   - `@tool("list_recipes")` ve `@tool("run_recipe")`: MCP üzerinden tek çağrıyla açık projeye viral kurgu paketi uygular.
5. **`app/ui/api_studio.py` + `app/ui/web/studio.html` + `app/ui/web/studio.js`**
   - 10 yeni `studio_*` API metodu (`studio_brand_get/save`, `studio_recipes_list`, `studio_run_recipe`, `studio_cursor_zoom`, `studio_kinetic_text`, `studio_bezier_eval`, `studio_shutter_blur`, `studio_parallax_plan`, `studio_motion_tools_status`) + `📊 Scopes` ve `🔥 Viral` UI butonları.

### Doğrulama Komutları (Claude İçin)
```powershell
cd C:\Users\fluvoksamine\Projeler\kami
node --check app/ui/web/studio.js
node --check app/ui/web/studio-scopes.js
uv run pytest tests/test_faz7.py tests/test_faz8.py tests/test_faz9.py -v
```

### Claude'un İncelemesinde Bildirdiği 4 Maddenin Düzeltmesi (13.11.2026)
1. **Viral reçeteler:** `studio_brand.py` zoom şablonları `studio_packs.ZOOM3` ID'leriyle (`push-fast`, `kb-zoom-lr`, `dolly-in`, `crash`, `breath`) eşlendi ve `apply_viral_recipe` klip `zoom` keyframe'lerini yazıyor; `studio.py` `build_export` içinde `shutterAngle >= 90` ise `tmix=frames=2:weights='1 1'` uygulanıyor.
2. **Ripple / Roll / Slip / Slide:** `studio_edit.py` (`start`/`dur`/`in`) ve `studio.js` (`#editModeSel` + `lanes` `pointerdown/pointermove/pointerup`) doğrudan zaman çizelgesi fare etkileşimine bağlandı.
3. **Smart Cut:** `build_smart_cut_cmd` / `smart_cut` içine `exact: bool = False` (anahtar-kare `-c copy` vs. kare-doğru `libx264`) eklendi; UI etiketi dürüstçe `⚡ Hızlı Kes (Keyframe Copy)` yapıldı.
4. **VRAM temizleme:** `vram_guard.py` içine `active_gpu_processes()` eklendi; `preflight()` ayrı süreçte çalışan Whisper/UVR/IOPaint süreçlerini `external_gpu_procs` ve `note` ile açıkça bildiriyor.
