// Kami eklentisi - arka plan (MV3 service worker)
// Tarayici indirmelerini yakalar, sag tik menusu ekler, native host uzerinden Kami'ye iletir.
"use strict";

const HOST = "com.metehan.kami";
const SKIP_SCHEMES = /^(blob:|data:|file:|chrome|brave|edge|about:|javascript:)/i;
const ALT_BYPASS_MS = 4000;

// ---------- native host ----------
async function native(msg) {
  try {
    const res = await chrome.runtime.sendNativeMessage(HOST, msg);
    return res || { ok: false, error: "empty" };
  } catch (e) {
    // host kayitli degil ya da baslatilamadi
    const text = String(e && e.message || e);
    return { ok: false, error: /not found|forbidden|Specified native messaging host/i.test(text) ? "nohost" : "offline", detail: text };
  }
}

async function requestHeaders(url) {
  const headers = { "User-Agent": navigator.userAgent };
  try {
    const cookies = await chrome.cookies.getAll({ url });
    if (cookies.length) headers["Cookie"] = cookies.map((c) => `${c.name}=${c.value}`).join("; ");
  } catch (_) { /* cerez izni yoksa bos gec */ }
  return headers;
}

async function sendToKami({ url, filename = "", referrer = "", pageUrl = "", size = 0, mime = "", source }) {
  const headers = await requestHeaders(url);
  return native({
    type: "add", url, filename, referer: referrer, page_url: pageUrl || referrer,
    size: size > 0 ? size : 0, mime, headers, source,
  });
}

function flashBadge(text, color) {
  chrome.action.setBadgeBackgroundColor({ color });
  chrome.action.setBadgeText({ text });
  setTimeout(() => chrome.action.setBadgeText({ text: "" }), 2500);
}

// ---------- Alt + tik = tarayici indirsin ----------
async function altBypassActive() {
  const { altUntil = 0 } = await chrome.storage.session.get("altUntil");
  return Date.now() < altUntil;
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg && msg.type === "alt-bypass") {
    chrome.storage.session.set({ altUntil: Date.now() + ALT_BYPASS_MS });
  } else if (msg && msg.type === "popup") {
    native(msg.payload).then(sendResponse);
    return true; // asenkron yanit
  }
  return false;
});

// ---------- otomatik yakalama ----------
// onDeterminingFilename: yanit basliklari gelmistir -> dosya adi, boyut ve MIME bilinir.
chrome.downloads.onDeterminingFilename.addListener((item, suggest) => {
  handleDownload(item).then((taken) => {
    if (!taken) suggest();
  }).catch(() => suggest());
  return true; // suggest'i asenkron cagiracagiz
});

async function handleDownload(item) {
  if (item.byExtensionId === chrome.runtime.id) return false;       // kendi baslattigimiz (yedek indirme)
  const url = item.finalUrl || item.url;
  if (!url || SKIP_SCHEMES.test(url) || !/^(https?|ftp):/i.test(url)) return false;
  if (item.state && item.state !== "in_progress") return false;
  if (await altBypassActive()) {
    await chrome.storage.session.set({ altUntil: 0 });
    return false;
  }
  const res = await sendToKami({
    url,
    filename: (item.filename || "").split(/[\\/]/).pop(),
    referrer: item.referrer || "",
    size: item.totalBytes || item.fileSize || 0,
    mime: item.mime || "",
    source: "browser",
  });
  if (!res.ok || !res.accepted) return false;                        // Kami kapali ya da kurala takildi

  try { await chrome.downloads.cancel(item.id); } catch (_) {}
  try { await chrome.downloads.erase({ id: item.id }); } catch (_) {}
  flashBadge(res.confirm ? "?" : "✓", res.confirm ? "#E8B86A" : "#7C4DFF");
  return true;
}

// ---------- sag tik menusu ----------
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "kami-download",
      title: chrome.i18n.getMessage("menu_download"),
      contexts: ["link", "video", "audio", "image"],
    });
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => { onMenuClicked(info, tab); });

async function onMenuClicked(info, tab) {
  if (info.menuItemId !== "kami-download") return;
  const url = info.linkUrl || info.srcUrl;
  if (!url || SKIP_SCHEMES.test(url)) return;
  const pageUrl = info.frameUrl || info.pageUrl || (tab && tab.url) || "";
  const res = await sendToKami({ url, referrer: pageUrl, pageUrl, source: "context_menu" });
  if (res.ok && res.accepted) {
    flashBadge(res.confirm ? "?" : "✓", res.confirm ? "#E8B86A" : "#7C4DFF");
  } else {
    // Kami kapali: kullanici bos donmesin, tarayici indirsin
    flashBadge("!", "#F0626F");
    chrome.downloads.download({ url });
  }
}
