// Sayfadaki indirilebilir adresler (icerik betigi yanit vermezse: eklenti guncellendi, sekme eski).
// chrome.scripting.executeScript({files:["grab_dom.js"]}) son ifadenin degerini dondurur.
(() => {
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
  
})();
