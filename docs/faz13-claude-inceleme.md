# Faz 13 — Claude İnceleme Özeti (`1.21.0-dev`)

## Kapsam (Kullanıcı Kısıtlarına Uygun Faz 13)
- Kullanıcı isteği üzerine **"Kami Wrapped" istatistik kartı eklenmedi** ve aktif çalışma yapılan **`room.js`, `room-core.js`, `room.py`, `mini-island`** dosyalarına dokunulmadı.

1. **13.1 Kami Kasa Semantik Arama (`app/core/semantic_vault.py`):**
   - `SQLite FTS5` + WAL (`data/kami_kasa.db`) + opsiyonel vektör embedding (`SigLIP`) kosinüs benzerliği.
   - `index_segment()`, `index_video_scenes()` (`scene_detect.detect_scenes()` ile sahne bazlı indeksleme) ve `search()` (BM25 + vektör skoru ile doğrudan `start_sec` sahne saniyesi döndürür).

2. **13.2 50.000+ `VirtualGrid` & Akıllı Oto-Bölümlendirme (`app/ui/web/virtual-grid.js`, `app/core/semantic_vault.py`):**
   - `KamiVirtualGrid`: DOM geri dönüşümü (viewport windowing + overscan) ile 50.000+ öğede akıcı kaydırma.
   - `auto_chapters()`: Transkript zaman pencerelerine göre otomatik bölüm başlığı ve özet (`Ollama qwen2.5:7b` açıksa yerel LLM, değilse extractive yedek).

3. **API & Testler (`app/ui/api.py`, `tests/test_faz13.py`):**
   - `kasa_index_media`, `kasa_search`, `kasa_auto_chapters`, `kasa_stats`.
   - `pytest tests/test_faz7.py .. tests/test_faz13.py`: **26/26 passed**.
