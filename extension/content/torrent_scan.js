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
  chrome.runtime.onMessage.addListener((msg, _s, reply) => {
    if (msg && msg.type === "torrent-rescan") { last = null; scan(); }
    if (msg && msg.type === "grab-all") { reply(grabAll()); return true; }   // v1.29 "Tumunu indir" paneli
  });

  // Sayfadaki tum indirilebilir adresler: linkler, video/ses kaynaklari, resimler (istege bagli), srcset en buyugu
  function grabAll() {
    const out = new Map();
    const add = (u, text, tag) => {
      if (!u) return;
      let abs; try { abs = new URL(u, location.href).href; } catch (_) { return; }
      if (!/^(https?|ftp|magnet):/i.test(abs) || out.has(abs)) return;
      out.set(abs, { url: abs, text: String(text || "").trim().replace(/\s+/g, " ").slice(0, 160), tag });
    };
    for (const a of document.querySelectorAll("a[href]")) add(a.getAttribute("href"), a.textContent || a.title || a.download, "a");
    for (const m of document.querySelectorAll("video[src], audio[src], video source[src], audio source[src]")) add(m.getAttribute("src"), document.title, "media");
    for (const im of document.querySelectorAll("img")) {
      let best = im.currentSrc || im.src, bw = 0;
      for (const part of (im.getAttribute("srcset") || "").split(",")) {
        const [u, w] = part.trim().split(/\s+/); const n = parseInt(w) || 0;
        if (u && n > bw) { bw = n; best = u; }
      }
      if (best && !/^data:/i.test(best) && (im.naturalWidth || 0) >= 200) add(best, im.alt, "img");
    }
    for (const el of document.querySelectorAll("[data-src], [data-full], [data-original]"))
      add(el.getAttribute("data-full") || el.getAttribute("data-original") || el.getAttribute("data-src"), el.alt || el.title, "img");
    return { title: document.title, page: location.href, links: [...out.values()].slice(0, 3000) };
  }
  let timer = 0;
  new MutationObserver(() => {
    if (timer) return;
    timer = setTimeout(() => { timer = 0; scan(); }, 2000);
  }).observe(document.documentElement, { childList: true, subtree: true });
})();
