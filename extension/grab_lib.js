// Sekmedeki linkleri al: once icerik betigi (grab-all), olmazsa betigi enjekte et (scripting izni).
async function kamiGrabTab(tabId) {
  try {
    const r = await chrome.tabs.sendMessage(tabId, { type: "grab-all" }, { frameId: 0 });
    if (r && r.links) return r;
  } catch (_) { /* eski sekme: alici yok */ }
  const res = await chrome.scripting.executeScript({ target: { tabId }, files: ["grab_dom.js"] });
  const r = res && res[0] && res[0].result;
  if (!r || !r.links) throw new Error("okunamadi");
  return r;
}
const KAMI_FILE_EXT = /\.(exe|msi|msix|apk|dmg|appimage|deb|rpm|zip|7z|rar|tar|gz|tgz|xz|bz2|iso|mp4|mkv|webm|mov|avi|m4v|mp3|m4a|flac|wav|ogg|opus|pdf|epub|cbz|cbr|torrent)$/i;
function kamiFileLinks(links) {   // acilir pencere: yalnizca dosya gibi gorunen linkler (sayfa/gezinme linkleri degil)
  const seen = new Set(), out = [];
  for (const l of links || []) {
    let u; try { u = new URL(l.url); } catch (_) { continue; }
    const path = decodeURIComponent(u.pathname);
    const isFile = KAMI_FILE_EXT.test(path) || /\/releases\/download\//.test(path) || /^magnet:/i.test(l.url) || /\/archive\/refs\/(tags|heads)\/.+\.(zip|tar\.gz)$/.test(path);
    if (!isFile || seen.has(l.url)) continue;
    seen.add(l.url);
    out.push({ url: l.url, name: path.split("/").filter(Boolean).pop() || l.url, text: l.text || "" });
  }
  return out;
}
