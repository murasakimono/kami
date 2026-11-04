// Desteklenen bulut paylasim sayfalari (Kami'deki plugins/*/plugin.py can_handle kaliplarinin aynasi).
// kamiCloudKind(url) -> "share" (Kami cozebilir) | "personal" (kisisel disk: paylasim linki gerekir) | ""
// Service worker (importScripts) ve icerik betikleri ortak kullanir.
(() => {
  "use strict";
  const SITES = [
    { name: "Yandex Disk", host: /(^|\.)(disk(\.360)?\.yandex\.[a-z.]+|yadi\.sk)$/,
      share: (p) => /^\/(d|i|public)\//.test(p), personal: (p) => /^\/client\//.test(p) },
    { name: "Mail.ru Cloud", host: /^cloud\.mail\.ru$/,
      share: (p) => /^\/public\/[^/]+\/[^/]+/.test(p), personal: (p) => /^\/(home|trashbin|shared)/.test(p) },
    { name: "MediaFire", host: /(^|\.)mediafire\.com$/,
      share: (p, u) => /^\/(folder|file|file_premium|view|download)\//.test(p) || /^\/\?\w/.test(p + u.search) },
    { name: "MEGA", host: /(^|\.)(mega\.nz|mega\.co\.nz|mega\.io)$/,
      share: (p, u) => /^\/(file|folder|embed)\/[^/#]+/.test(p) || /^#F?!/.test(u.hash),
      personal: (p) => /^\/fm(\/|$)/.test(p) },
    { name: "Google Drive", host: /^drive\.google\.com$/,
      share: (p, u) => /^\/(file\/d\/|drive\/(u\/\d+\/)?folders\/|uc$|open$)/.test(p) && (!/^\/(uc|open)$/.test(p) || u.searchParams.has("id")),
      personal: (p) => /^\/drive\/(u\/\d+\/)?(my-drive|home|recent|starred)/.test(p) },
    { name: "Dropbox", host: /(^|\.)dropbox\.com$/, share: (p) => /^\/(s|sh|scl\/fi|scl\/fo)\//.test(p),
      personal: (p) => /^\/home/.test(p) },
    { name: "Pixeldrain", host: /(^|\.)(pixeldrain\.(com|net)|pixeldra\.in)$/, share: (p) => /^\/(u|l|d)\/[^/]+/.test(p) },
  ];

  function kamiCloudSite(url) {
    let u;
    try { u = new URL(url); } catch (_) { return null; }
    if (!/^https?:$/.test(u.protocol)) return null;
    const host = u.hostname.toLowerCase();
    const site = SITES.find((s) => s.host.test(host));
    if (!site) return null;
    if (site.share(u.pathname, u)) return { kind: "share", name: site.name };
    if (site.personal && site.personal(u.pathname, u)) return { kind: "personal", name: site.name };
    return null;
  }

  globalThis.kamiCloudSite = kamiCloudSite;
  globalThis.kamiCloudKind = (url) => (kamiCloudSite(url) || {}).kind || "";
})();
