<p align="center">
  <img src="extension/icons/128.png" width="96" alt="Kami">
</p>

<h1 align="center">Kami</h1>

<p align="center">
  <b>Hızlı indirme yöneticisi + yerleşik medya oynatıcı — tek programda.</b><br>
  Windows için. Türkçe / English.
</p>

<p align="center">
  <a href="https://github.com/murasakimono/kami/releases/latest"><b>⬇ Son sürümü indir</b></a>
</p>

---

Kami, tarayıcınızdaki indirmeleri devralıp çok bağlantıyla hızlandıran bir indirme yöneticisi ve indirdiklerinizi (indirme sürerken bile) açabileceğiniz tam donanımlı bir medya oynatıcıdır. Karşınızda canlı bir maskot, sıvı gibi dolan indirme şeritleri ve koyu, mor-yeşil bir arayüz var.

## İndirme

- **Çok bağlantılı hızlı indirme** — dosya başına 16 bağlantı; sunucu sınırlarsa kendini ayarlar
- **Tarayıcı eklentisi** (Brave / Chrome / Edge) — indirmeleri otomatik devralır, sağ tık menüsü, video üstünde "Kami ile indir" düğmesi (MP4 / MP3 / Kami'de seç), magnet algılama, açılır pencerede süren indirmeler
- **Video siteleri** — YouTube ve yüzlerce site: MP4 / MP3, altyazı, kapak, bölümler, zaman aralığı, SponsorBlock
- **Bulut bağlantıları** — Yandex Disk, MEGA, Cloud Mail.ru, Dropbox, Google Drive, Mediafire, Pixeldrain, GoFile
- **Real-Debrid** — bağlantıyı yapıştırın, gerisini Kami halleder; linkten doğrudan izleme
- **Torrent / magnet**
- **İnerken izle** — dosya inerken oynatıcıda açılır
- Zamanlayıcı, bitince bilgisayarı kapatma, pano izleme, Ctrl+K komut paleti, son klasörler, silinen dosyalar Geri Dönüşüm Kutusu'na
- Telefon bildirimi (ntfy) ve telefondan uzaktan kontrol

## Kami Player

- **Her formatı oynatır** — MKV, HEVC, AC3/DTS dahil; gerekirse ekran kartıyla (NVENC/QSV/AMF) anında dönüştürür
- **Altyazı** — ASS/SSA orijinal stiliyle, dosya içi altyazılar, ikinci altyazı (DUAL), kaydırma, sese otomatik hizalama, Türkçeye çeviri (yerel NLLB ya da Google), Whisper ile altyazı üretme
- **Kinetik altyazı** — fısıltıda incelir, bağırmada titrer, bas vuruşunda parlar, vokalde glitch yapar
- **Kelimeye tıkla → sözlük** — çevrimdışı Vikisözlük (Japonca dahil)
- **Ekrandaki yazıyı oku** — bir bölge seçin, yazıyı okuyup Türkçeye çevirir
- **Müzik modu** — zamanlı şarkı sözü paneli ve karaoke (LRCLIB / yan .lrc / yapıştır), kapak rengine göre parlayan arka plan, albüm ızgarası, boşluksuz geçiş ve crossfade, sözden şarkı bulma
- **Mini oynatıcı** — çerçevesiz, hep üstte, sürüklenebilir kart (YouTube PiP gibi)
- **Kütüphane** — dizileri otomatik gruplar, AniList posterleri, izlemeye devam rafı, izlendi işaretleri, oynatma listeleri ve klasör listeleri
- **Anime için** — intro / kapanış atlama (AniSkip), bölüm işaretleri
- **Ses ve görüntü** — 10 bantlı ekolayzır, gece modu, normalleştirme, %200 ses, 5.1 → kulaklık diyalog karışımı, döndür / ayna, ortam ışığı, oran / yakınlaştırma / renk
- **Araçlar** — kayıpsız klip, GIF, "Discord'a sığdır" (10 MB), sesi çıkar, bozuk dosya onarımı
- Özelleştirilebilir kısayollar, kaldığı yerden devam, çökme kurtarma, varsayılan oynatıcı olarak ayarlanabilir

## Kurulum

1. [Son sürümden](https://github.com/murasakimono/kami/releases/latest) `Kami-Setup-x.y.z.exe` dosyasını indirip çalıştırın.
2. Tarayıcı eklentisi için: `brave://extensions` (ya da `chrome://extensions`) → Geliştirici modu → **Paketlenmemiş öğe yükle** → Kami'nin kurulum klasöründeki `extension` klasörü.

Kami güncellemeleri kendisi kontrol eder.

## Geliştirme

Python 3.12 + pywebview, arayüz HTML/CSS/JS; indirme motoru aria2, medya için yt-dlp ve ffmpeg.

```
uv sync
.venv\Scripts\python.exe -m pytest -q
uv run python packaging/build.py   # kurulum dosyası
```

Eklentiler `plugins/<ad>/plugin.py` içinde `register(ctx)` ile yazılır; sözleşme `app/core/plugin_api.py`.
