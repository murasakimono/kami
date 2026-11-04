// Desteklenen bulut paylasim sayfalari. KAYNAK: Kami'deki plugins/*/plugin.json "url_patterns".
// Kami'ye her baglanista (ping) guncel liste gelir ve chrome.storage.local.kamiSites'a yazilir;
// bu dosyayi yeni site icin ELLE GUNCELLEMEK GEREKMEZ. Asagidaki liste sadece Kami'ye hic baglanilmadiysa yedek.
// kamiCloudSite(url) -> {kind: "share" | "personal", name} | null ; kamiCloudKind(url) -> "share" | "personal" | ""
// Desen anlami (Python match_patterns ile ayni): host = alan adi regex'i; share/personal = yol + ?sorgu + #parca regex'i.
// Service worker (importScripts) ve icerik betikleri ortak kullanir.
(() => {
  "use strict";
  const FALLBACK = [
    { name: "Yandex Disk", host: "(^|\\.)(disk(\\.360)?\\.yandex\\.[a-z.]+|yadi\\.sk)$", share: "^/(d|i|public)/", personal: "^/client/" },
    { name: "Mail.ru Cloud", host: "^cloud\\.mail\\.ru$", share: "^/public/[^/]+/[^/]+", personal: "^/(home|trashbin|shared)" },
    { name: "MediaFire", host: "(^|\\.)mediafire\\.com$", share: "^/(folder|file|file_premium|view|download)/|^/\\?\\w" },
    { name: "MEGA", host: "(^|\\.)(mega\\.nz|mega\\.co\\.nz|mega\\.io)$", share: "^/(file|folder|embed)/[^/#]+|^/?#F?!", personal: "^/fm(/|$|\\?|#)" },
    { name: "Google Drive", host: "^drive\\.google\\.com$", share: "^/(file/d/[\\w-]{10,}|drive/(u/\\d+/)?folders/[\\w-]{10,})|^/(uc|open)\\?(.*&)?id=",
      personal: "^/drive/(u/\\d+/)?(my-drive|home|recent|starred)" },
    { name: "Dropbox", host: "(^|\\.)dropbox\\.com$", share: "^/(s|sh|scl/fi|scl/fo)/", personal: "^/home" },
    { name: "Pixeldrain", host: "(^|\\.)(pixeldrain\\.(com|net)|pixeldra\\.in)$", share: "^/(u|l|d)/[^/]+" },
  ];

  const compile = (list) => (list || []).map((s) => {
    try {
      return { name: s.name || "", host: new RegExp(s.host), share: s.share ? new RegExp(s.share) : null,
               personal: s.personal ? new RegExp(s.personal) : null };
    } catch (_) { return null; }
  }).filter(Boolean);

  let SITES = compile(FALLBACK);
  try {
    chrome.storage.local.get("kamiSites").then((g) => { if (Array.isArray(g.kamiSites) && g.kamiSites.length) SITES = compile(g.kamiSites); });
    chrome.storage.onChanged.addListener((ch, area) => {
      if (area === "local" && ch.kamiSites && Array.isArray(ch.kamiSites.newValue)) SITES = compile(ch.kamiSites.newValue);
    });
  } catch (_) { /* storage yoksa yedek liste */ }

  function kamiCloudSite(url) {
    let u;
    try { u = new URL(url); } catch (_) { return null; }
    if (!/^https?:$/.test(u.protocol)) return null;
    const host = u.hostname.toLowerCase();
    const tail = u.pathname + u.search + u.hash;
    for (const s of SITES) {
      if (!s.host.test(host)) continue;
      if (s.share && s.share.test(tail)) return { kind: "share", name: s.name };
      if (s.personal && s.personal.test(tail)) return { kind: "personal", name: s.name };
    }
    return null;
  }

  globalThis.kamiCloudSite = kamiCloudSite;
  globalThis.kamiCloudKind = (url) => (kamiCloudSite(url) || {}).kind || "";
})();
