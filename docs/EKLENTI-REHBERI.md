# Kami eklenti rehberi

Yeni bir site ya da özellik eklemek için **sadece bu rehber + `plugins/_sablon`** yeter. Kami'nin geri kalanını,
proje defterini, tarayıcı eklentisini (`extension/`) ya da arayüzü (`app/ui/web/`) okumak veya değiştirmek GEREKMEZ.
Claude Code'da kısayolu: `/eklenti <fikir>`. Başka bir yapay zekâ (Gemini vb.) ya da elle yazan biri de bu rehberle,
uyumlu bir klasörü `plugins/` içine koyarak eklenti yapabilir.

## 1. Üç komut

```bash
uv run python -m tools.yeni_eklenti ornek_site "Örnek Site"   # plugins/ornek_site iskeleti
uv run python -m tools.eklenti_test ornek_site                # denetim + testler (ağsız)
uv run python -m tools.eklenti_test ornek_site --ag            # gerçek ağ testleri de
```

`uv run python -m tools.eklenti_test --hepsi` bütün eklentileri dener. Kami açıksa: **Ayarlar > Eklentiler > Yeniden yükle**
(Kami'yi kapatmadan yeni kod devreye girer). Yeni klasör eklendiyse Kami'yi bir kez yeniden aç.

## 2. Klasör

```
plugins/ornek_site/
  plugin.json      # TEK BİLGİ KAYNAĞI: ad, sürüm, URL desenleri, ayar şeması
  plugin.py        # def register(ctx): ...
  test_plugin.py   # pytest; `plugin` fikstürü hazır gelir
```

Klasör adı = eklenti kimliği: küçük harfle başlar, sadece `a-z 0-9 _` (ör. `ornek_site`). `_` ile başlayan klasörler
(şablon) yüklenmez.

## 3. plugin.json

```json
{
  "name": "Örnek Site",
  "version": "0.1.0",
  "description": "Örnek Site paylaşım linklerini indirir.",
  "author": "",
  "kami_min": "0.7.1",
  "enabled": true,
  "kinds": ["cloud"],
  "url_patterns": [
    {
      "name": "Örnek Site",
      "host": "(^|\\.)ornek\\.com$",
      "share": "^/(f|d)/[^/]+",
      "personal": "^/hesabim",
      "examples": {"match": ["https://ornek.com/f/abc123"], "no_match": ["https://ornek.com/hakkinda"]}
    }
  ],
  "settings": [
    {"key": "use_api", "type": "bool", "default": true,
     "label": {"tr": "Resmi API'yi kullan", "en": "Use the official API"},
     "help": {"tr": "Kapalıysa sayfa bilgisinden çözülür.", "en": "If off, the page info is used."}},
    {"key": "api_key", "type": "secret", "label": {"tr": "API anahtarı (isteğe bağlı)", "en": "API key (optional)"}}
  ],
  "permissions": ["network"]
}
```

- **kinds**: `cloud` (bulut paylaşım linki → dosya listesi), `resolver` (link → indirme istekleri), `postprocessor`
  (indirme bitince), `engine` (aria2 dışı motor), `tab` (kendi arayüz sekmesi). Çoğu site eklentisi `cloud`.
- **url_patterns**: Kami bunları **tarayıcı eklentisine kendisi gönderir** (bağlanınca ping yanıtında) → sağ tık,
  sayfa üstü "Kami ile indir" düğmesi ve popup yeni siteyi tanır. `extension/cloud_sites.js` ELLE GÜNCELLENMEZ.
  - `host`: alan adı regex'i (`re.search`; JS'te `RegExp.test`). Alt alan adı için `(^|\\.)site\\.com$`.
  - `share`: indirilebilir paylaşım linki; **yol + `?sorgu` + `#parça`** üzerinde regex (ör. `^/(file|folder)/`).
  - `personal`: (isteğe bağlı) kişisel disk sayfası → eklenti "paylaşım linki gerekir" der, indirmez.
  - Desenler Python VE JavaScript'te çalışmalı: adlı grup `(?P<..>)`, `(?<=..)`, satır içi bayrak `(?i)` KULLANMA.
  - `examples` zorunlu sayılır: test komutu her örneği hem desenle hem `can_handle` ile dener.
- **settings**: Ayarlar > Eklentiler'de form **otomatik çizilir**. Türler: `bool`, `int` (`min`/`max`), `str`,
  `choice` (`choices` listesi), `secret` (DPAPI ile şifreli saklanır, arayüzde gösterilmez).
  Kodda okuma: `ctx.setting("use_api")`, `ctx.secret("api_key")`.

## 4. plugin.py (bulut eklentisi)

```python
from app.core.cloud import CloudError, CloudFile, CloudListing, CloudProvider, get_json, session


class OrnekSite(CloudProvider):
    name = "ornek_site"          # klasör adıyla aynı
    # hosts boş bırakılırsa eşleşme plugin.json url_patterns ile yapılır

    def __init__(self, ctx):
        self.ctx = ctx

    def list(self, url: str) -> CloudListing:
        s = session()                                   # tarayıcı User-Agent'lı requests.Session
        data = get_json(s, "https://api.ornek.com/share", params={"url": url})   # 404/401/403 -> CloudError
        files = [CloudFile(f["path"], int(f["size"]), url=f["download_url"]) for f in data["files"]]
        if not files:
            raise CloudError("cloud_empty")
        return CloudListing(self.name, data["title"], files)


def register(ctx):
    ctx.register_cloud(OrnekSite(ctx))
```

- `CloudFile(path, size, url="", headers={}, ref=None)`: `path` paylaşım köküne göre `"alt/klasor/dosya.zip"`
  (klasör yapısı korunarak iner). Link sonradan çözülecekse `url` boş + `ref` doldur, `file_request()`'i yaz:
  `def file_request(self, listing, f) -> (url, headers, options)`.
- `CloudListing(provider, title, files, is_folder=True, note="")`: `note` arayüzde kısa not (ör. "zip olarak iner").
- Hata kodları (arayüzde çevrilir): `cloud_failed`, `cloud_not_found`, `cloud_denied`, `cloud_empty`,
  `cloud_unsupported`, `cloud_password`, `cloud_quota`. `CloudError("cloud_denied", "ayrıntı")`.
- Kayıt (ctx): `register_cloud`, `register_resolver`, `register_postprocessor`, `register_engine`, `register_tab`.
  Sözleşmeler: `app/core/plugin_api.py` (Resolver: `can_handle(request)`, `resolve(request) -> [DownloadRequest]`;
  PostProcessor: `applies(download)`, `process(download)`).
- Günlük: `ctx.log.info(...)` (Kami'nin log dosyasına `kami_plugins.<ad>` olarak düşer).

## 5. test_plugin.py

```python
import pytest

def test_desenler(plugin):                      # plugin.json + can_handle birlikte denenir
    assert plugin.matches("https://ornek.com/f/abc123")
    assert not plugin.matches("https://ornek.com/hakkinda")

@pytest.mark.network                            # sadece --ag ile
def test_gercek_link(plugin):
    assert plugin.cloud.list("https://ornek.com/f/gercek").files
```

`plugin` fikstürü: `.matches(url)`, `.cloud` (ilk bulut sağlayıcı), `.clouds`, `.resolvers`, `.postprocessors`, `.info`.

## 6. Kurallar

- Sadece kendi klasörüne yaz. Ortak dosyalara (çekirdek, arayüz, tarayıcı eklentisi) dokunma; gerekiyorsa önce sor.
- Gizli bilgi (token, şifre) koda/commit'e yazılmaz → `type: "secret"` ayar.
- Sınır: DRM kırma ve korsan indeks/yayın sitesine özel çıkarıcı yazılmaz.
- Sitenin resmi API'si varsa onu kullan; yoksa herkese açık paylaşım sayfası. Hız sınırı varsa uy.
- Bozuk eklenti Kami'yi düşürmez: hata Ayarlar > Eklentiler'de kırmızı görünür.
- Bitti sayılması için: `tools.eklenti_test <ad>` GEÇTİ + mümkünse bir gerçek linkle `--ag`.
