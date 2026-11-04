// Sayfadaki magnet: ve .torrent linklerini bulur, arka plana bildirir (popup'ta "Real-Debrid'e gonder").
// Sayfayi degistirmez; dinamik sayfalar icin DOM degisince (seyrek) yeniden tarar.
(() => {
  "use strict";
  if (window.top !== window) return;   // sadece ana cerceve
  const MAX = 200;
  let last = null;   // ilk tarama bos olsa da bildirilir (onceki sayfanin listesi silinsin)

  function isTorrentHref(href) {
    if (/^magnet:\?/i.test(href)) return true;
    try { return /\.torrent$/i.test(new URL(href, location.href).pathname); } catch (_) { return false; }
  }

  function scan() {
    const seen = new Set(), links = [];
    for (const a of document.querySelectorAll('a[href^="magnet:"], a[href*=".torrent"]')) {
      const href = a.href || a.getAttribute("href") || "";
      if (!href || seen.has(href) || !isTorrentHref(href)) continue;
      seen.add(href);
      let text = (a.textContent || a.title || "").trim().replace(/\s+/g, " ");
      if (/^magnet:/i.test(href) && (!text || text.length < 3)) {
        const dn = /[?&]dn=([^&]+)/i.exec(href);
        if (dn) try { text = decodeURIComponent(dn[1].replace(/\+/g, " ")); } catch (_) {}
      }
      links.push({ url: href, text: text.slice(0, 160) });
      if (links.length >= MAX) break;
    }
    const key = links.map((l) => l.url).join("\n");
    if (key === last) return;
    last = key;
    chrome.runtime.sendMessage({ type: "torrent-links", links }).catch(() => {});
  }

  scan();
  // adres degisti (SPA dahil): arka plan listeyi sildi, yeniden bildir
  chrome.runtime.onMessage.addListener((msg) => { if (msg && msg.type === "torrent-rescan") { last = null; scan(); } });
  let timer = 0;
  new MutationObserver(() => {
    if (timer) return;
    timer = setTimeout(() => { timer = 0; scan(); }, 2000);
  }).observe(document.documentElement, { childList: true, subtree: true });
})();
