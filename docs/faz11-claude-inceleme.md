# Faz 11 — Claude İnceleme Özeti (`1.19.0-dev`)

## Kapsam (Çakışmasız Sadeleştirilmiş Faz 11)
Mevcut `mediatools.py` (SponsorBlock), `musicarchive.py` (MusicBrainz), `postcomplete.py` (`smart_series_folders`), `torrent.py` (`ngosang/trackerslist`) ve `mirrors.py` modüllerine dokunulmadan şu yeni özellikler eklendi:

1. **11.1 `aria2c` Torrent Önizleme & DHT Kalıcılığı (`app/engines/aria2_engine.py`):**
   - `--file-allocation=none` ve `--dht-file-path` korundu.
   - `--bt-save-metadata=true` eklendi.
   - `build_torrent_options()` içine `bt-prioritize-piece: head=20M` eklendi (`options.prioritize_piece` ile özelleştirilebilir/kapatılabilir).

2. **11.2 JSON `LinkCrawler` & Çoklu Ayna Failover (`app/core/link_crawler.py`):**
   - `data/crawler_rules.json` üzerinden yönetilen eklentisiz JSON kural motoru (`load_rules`, `save_rule`, `delete_rule`, `crawl`, `pick_working_mirror`).
   - `is_safe_public_url()` ile özel/yerel IP SSRF koruması.

3. **11.3 Canlı Yayın DVR & Tek-Dosya Web Arşivi (`app/core/web_archive.py`):**
   - `build_live_dvr_opts()` / `start_live_dvr()`: `yt-dlp` `live_from_start=True` + `FFmpegMetadata` (`add_chapters=True`); SponsorBlock ayarına dokunmaz.
   - `archive_webpage()`: `SingleFile` CLI varsa onu kullanır, yoksa harici CSS ve küçük görselleri `<512 KB` inline `data:` URI olarak gömen yerleşik HTML arşivleyiciye düşer.

4. **11.4 Çift Medya Temizliği, Akıllı Sıkıştırma & Bit-Rot Tarayıcısı (`app/core/library_health.py`):**
   - `find_duplicates()`: SHA-256 birebir + 9×8 `dHash` algısal görsel/video çift dosya tespiti.
   - `smart_compress()` / `measure_vmaf()`: `av1_nvenc` → `hevc_nvenc` → `libx265` sırasıyla kodlama; `libvmaf` filtresi mevcutsa VMAF ölçümü ve hedef altındaysa otomatik kalite artırma.
   - `scan_health()`: `SHA-256` manifest karşılaştırması ile sessiz bozulma (`corrupted_bitrot`) ve isteğe bağlı `ffmpeg -v error` akış kontrolü.

5. **API Köprüsü (`app/ui/api.py`):**
   - `crawler_rules_list`, `crawler_rule_save`, `crawler_rule_delete`, `crawler_crawl`, `dvr_start`, `web_archive_save`, `library_find_duplicates`, `library_smart_compress`, `library_scan_health`.

## Doğrulama
- `pytest tests/test_faz7.py tests/test_faz8.py tests/test_faz9.py tests/test_faz10.py tests/test_faz11.py -v --basetemp=.pytest_tmp`: **20/20 passed**.
- Release notu: Kullanıcı kararı gereği release **Faz 12 sonunda** alınacaktır.
