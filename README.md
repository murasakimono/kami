# Kami — Kami Download Manager (KDM)

Kişisel, tek parça, eklentilerle genişleyen indirme yöneticisi.

- Çok bağlantılı hızlı indirme (aria2, dosya başına 16 bağlantı; sunucu sınırlarsa otomatik 16→4→1)
- Brave/Chrome eklentisi: tarayıcı indirmelerini otomatik devralma, sağ tık, video/ses üstü indir butonu, magnet algılama
- YouTube ve diğer siteler: MP4/MP3, altyazı, kapak/etiket/bölüm, zaman aralığı, SponsorBlock (yt-dlp + ffmpeg)
- Bulut: Yandex Disk, MEGA, Cloud Mail.ru, Dropbox, Google Drive, Mediafire, Pixeldrain, GoFile
- Real-Debrid: yapıştır-geç, otomatik hoster yönlendirme (isteğe bağlı)
- Torrent / magnet
- Arayüz: pywebview + HTML/CSS, Türkçe / English, koyu / açık tema

Durum: **Aşama 1 tamam** (çekirdek, aria2 motoru, arayüz kabuğu, native host, eklenti: otomatik yakalama + sağ tık).
Proje defteri: `C:\Users\fluvoksamine\Scripts\projeler\indirici.md`

## Kurulum (bir kez)

1. Python ortamı: `uv sync` (Python 3.12 venv, `.venv`)
2. `bin\aria2c.exe`: aria2 1.37.0 win-64 (GitHub releases, SHA256 `67d01530…b288`). Repoda yok, elle konur.
3. Tarayıcı köprüsü: `native_host\kur_host.bat` (Brave + Chrome + Edge, sadece bu kullanıcı; kaldırmak: `kur_host.bat kaldir`)
4. Eklenti: Brave'de `brave://extensions` → Geliştirici modu → **Paketlenmemiş öğe yükle** → `extension` klasörü.
   Eklenti ID'si manifest'teki sabit anahtardan gelir: `aanjhajdcflkkppfpmoagpbbcdpffapi`.

## Çalıştırma

`Kami.bat` (konsolsuz). Zaten açıksa pencere öne gelir.

## Tarayıcı davranışı

- Kami açıkken tarayıcıda başlayan indirmeler sormadan Kami'ye geçer.
- Tarayıcıda kalanlar: Kami kapalıyken başlayanlar, `blob:`/`data:` linkleri, ayardaki boyuttan küçük dosyalar
  (varsayılan 1 MB), hariç tutulan siteler, **Alt basılıyken tıklananlar**.
- `.exe/.msi/.apk/.bat…` gibi program dosyaları Kami'de onay bekler.
- Çerezler ve User-Agent Kami'ye aktarılır (giriş gerektiren indirmeler çalışır).

## Geliştirme

- Testler: `.venv\Scripts\python.exe -m pytest -q` (aria2 + yerel HTTP sunucusuyla uçtan uca dahil)
- Eklenti uçtan uca: `tests\e2e\ext_e2e.js` (geçici profilli Chrome, puppeteer-core), arayüz köprüsü: `tests\e2e\ui_bridge_check.py`
- Eklenti simgeleri: `tools\make_icons.py`
- Eklenti yazmak: `plugins/<ad>/plugin.py` içinde `register(ctx)`; sözleşme `app/core/plugin_api.py`
