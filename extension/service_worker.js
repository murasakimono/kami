// Kami eklentisi - arka plan (MV3 service worker)
// Tarayici indirmelerini yakalar, sag tik menusu ekler, native host uzerinden Kami'ye iletir.
"use strict";
importScripts("cloud_sites.js");   // kamiCloudSite / kamiCloudKind

const HOST = "com.metehan.kami";
const SKIP_SCHEMES = /^(blob:|data:|file:|chrome|brave|edge|about:|javascript:)/i;
const ALT_BYPASS_MS = 4000;

// ---------- native host ----------
async function native1(msg) {
  try {
    const res = await chrome.runtime.sendNativeMessage(HOST, msg);
    if (res && res.ok && Array.isArray(res.sites)) chrome.storage.local.set({ kamiSites: res.sites });   // eklenti desenleri
    if (!res) return { ok: false, error: "offline", detail: "Host bos yanit verdi (lastError: " + (chrome.runtime.lastError && chrome.runtime.lastError.message || "yok") + ")" };
    return res;
  } catch (e) {
    // host kayitli degil ya da baslatilamadi; GERCEK mesaj detail'de (popup gosterir)
    const text = String(e && e.message || e);
    return { ok: false, error: /not found|forbidden|Specified native messaging host/i.test(text) ? "nohost" : "offline", detail: text };
  }
}

// Kami acilirken/yeniden baslarken ilk deneme kacabilir: offline ise 3 kez daha dene (1.5 sn arayla)
async function native(msg, retries = 3) {
  let res = await native1(msg);
  for (let i = 0; i < retries && !res.ok && res.error === "offline"; i++) {
    await new Promise((r) => setTimeout(r, 1500));
    res = await native1(msg);
  }
  return res;
}

async function requestHeaders(url) {
  const headers = { "User-Agent": navigator.userAgent };
  try {
    const cookies = await chrome.cookies.getAll({ url });
    if (cookies.length) headers["Cookie"] = cookies.map((c) => `${c.name}=${c.value}`).join("; ");
  } catch (_) { /* cerez izni yoksa bos gec */ }
  return headers;
}

// ---------- YouTube/Google oturum cerezleri -> Kami (DPAPI ile saklar, yt-dlp cookiefile) ----------
// YouTube bu agda cerezsiz istekleri "bot musun" diye reddediyor; Brave'deki oturum cerezleri gerekiyor.
const YT_RE = /(^|\.)(youtube\.com|youtu\.be|youtube-nocookie\.com)$/i;
// Site gruplari (Kami vault.SITE_GROUPS ile ayni). Instagram/X/TikTok: hikaye/reels/ozel gonderi icin oturum gerekir.
const COOKIE_GROUPS = {
  youtube: { domains: ["youtube.com", "google.com"], login: /^(SAPISID|__Secure-3PAPISID|LOGIN_INFO|SID)$/ },
  instagram: { domains: ["instagram.com"], login: /^sessionid$/ },
  x: { domains: ["x.com", "twitter.com"], login: /^auth_token$/ },
  tiktok: { domains: ["tiktok.com"], login: /^(sessionid|sessionid_ss|sid_tt)$/ },
};
const lastCookieSync = {};
function cookieGroupOf(u) {
  let h = "";
  try { h = new URL(u).hostname; } catch (_) { h = String(u || "").replace(/^\./, ""); }
  if (YT_RE.test(h)) return "youtube";
  for (const [g, v] of Object.entries(COOKIE_GROUPS)) if (v.domains.some((d) => h === d || h.endsWith("." + d))) return g;
  return "";
}

function isYouTube(u) {
  try { return YT_RE.test(new URL(u).hostname); } catch (_) { return false; }
}

async function syncCookies(force = false, group = "youtube") {
  const G = COOKIE_GROUPS[group];
  if (!G) return;
  if (!force && Date.now() - (lastCookieSync[group] || 0) < 60000) return;
  lastCookieSync[group] = Date.now();
  try {
    const all = [];
    for (const domain of G.domains) all.push(...await chrome.cookies.getAll({ domain }));
    if (!all.some((c) => G.login.test(c.name))) return; // giris yok
    const cookies = all.map((c) => ({
      name: c.name, value: c.value, domain: c.domain, path: c.path, secure: c.secure,
      hostOnly: c.hostOnly, session: c.session, expirationDate: c.expirationDate || 0,
    }));
    await native({ type: "cookies", cookies });
  } catch (_) { /* Kami kapali ya da izin yok */ }
}

let cookieTimer = null;
chrome.cookies.onChanged.addListener(({ cookie }) => {
  const g = cookieGroupOf(cookie.domain.replace(/^\./, ""));
  if (!g) return;
  if (g === "youtube" && !/^(SAPISID|__Secure-[13]PAPISID|__Secure-[13]PSID\w*|LOGIN_INFO|SID|HSID|SSID|APISID)$/.test(cookie.name)) return;
  if (g !== "youtube" && !COOKIE_GROUPS[g].login.test(cookie.name)) return;
  clearTimeout(cookieTimer);
  cookieTimer = setTimeout(() => syncCookies(true, g), 5000);
});
chrome.runtime.onStartup.addListener(() => { syncCookies(true); native({ type: "ping" }); });

async function sendToKami({ url, filename = "", referrer = "", pageUrl = "", size = 0, mime = "", source }) {
  { const g = cookieGroupOf(url) || cookieGroupOf(pageUrl); if (g) await syncCookies(true, g); }
  const headers = await requestHeaders(url);
  return native({
    type: "add", url, filename, referer: referrer, page_url: pageUrl || referrer,
    size: size > 0 ? size : 0, mime, headers, source,
  });
}

function flashBadge(text, color, ms = 2500, title = "") {
  chrome.action.setBadgeBackgroundColor({ color });
  chrome.action.setBadgeText({ text });
  if (title) chrome.action.setTitle({ title: `Kami — ${title}` });
  setTimeout(() => {
    chrome.action.setBadgeText({ text: "" });
    if (title) chrome.action.setTitle({ title: "" });   // manifest varsayilanina don
  }, ms);
}

// ---------- Alt + tik = tarayici indirsin ----------
async function altBypassActive() {
  const { altUntil = 0 } = await chrome.storage.session.get("altUntil");
  return Date.now() < altUntil;
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.type === "alt-bypass") {
    chrome.storage.session.set({ altUntil: Date.now() + ALT_BYPASS_MS });
  } else if (msg && msg.type === "popup") {
    native(msg.payload).then(sendResponse);
    return true; // asenkron yanit
  } else if (msg && msg.type === "get-media") {
    getTabMedia(msg.tabId).then(sendResponse);
    return true;
  } else if (msg && msg.type === "media-add") {      // acilir penceredeki yakalanan akis
    sendMedia({ url: msg.url, pageUrl: msg.pageUrl, mode: msg.mode, title: msg.title }).then(sendResponse);
    return true;
  } else if (msg && msg.type === "page-add") {      // bulut sayfa butonu / popup "Bu sayfayi Kami ile indir"
    sendPage(msg.url || (sender.tab && sender.tab.url) || "").then(sendResponse);
    return true;
  } else if (msg && msg.type === "video-button") {   // video ustu buton
    onVideoButton(msg, sender).then(sendResponse);
    return true;
  } else if (msg && msg.type === "torrent-links") {  // icerik betigi: sayfadaki magnet/.torrent linkleri
    if (sender.tab) saveTorrentLinks(sender.tab.id, msg.links || []);
  } else if (msg && msg.type === "get-torrents") {
    chrome.storage.session.get(tlKey(msg.tabId)).then((g) => sendResponse(g[tlKey(msg.tabId)] || []));
    return true;
  } else if (msg && msg.type === "rd-send") {        // popup "RD'ye gonder"
    sendRd(msg.url, msg.pageUrl || "").then(sendResponse);
    return true;
  }
  return false;
});

// ---------- medya trafigi izleme (her sitede MP4 / HLS / DASH / ses) ----------
const MEDIA_EXT = /\.(mp4|m4v|webm|mkv|mov|flv|mp3|m4a|aac|ogg|oga|opus|wav|flac)$/i;
const MANIFEST_EXT = /\.(m3u8|mpd)$/i;
const SEGMENT = /\.(ts|m4s|aac\.ts|cmfv|cmfa)$|[?&](range|bytes)=|\/range\/|\/seg(ment)?[-_]?\d+|[-_]frag(ment)?\d+/i;
// YouTube akis parcalari googlevideo'dan gelir: orada sayfa linki (yt-dlp) kullanilir
const SKIP_HOST = /(^|\.)(googlevideo\.com|ytimg\.com|doubleclick\.net|googlesyndication\.com|googleadservices\.com)$/i;
const KNOWN_SITE = /(^|\.)(youtube\.com|youtu\.be|youtube-nocookie\.com|vimeo\.com|dailymotion\.com|twitch\.tv|x\.com|twitter\.com|instagram\.com|tiktok\.com|reddit\.com|facebook\.com|soundcloud\.com|bilibili\.com|kick\.com|streamable\.com)$/i;
const MIN_FILE = 512 * 1024;
const MAX_PER_TAB = 25;

function hdr(headers, name) {
  const h = (headers || []).find((x) => x.name.toLowerCase() === name);
  return h ? h.value : "";
}

function classify(url, ct, size) {
  let u;
  try { u = new URL(url); } catch (_) { return null; }
  if (SKIP_HOST.test(u.hostname)) return null;
  const path = u.pathname.toLowerCase();
  ct = (ct || "").toLowerCase().split(";")[0].trim();
  if (/mpegurl/.test(ct) || path.endsWith(".m3u8")) return "hls";
  if (/dash\+xml/.test(ct) || path.endsWith(".mpd")) return "dash";
  if (SEGMENT.test(path + u.search) || /mp2t|iso\.segment/.test(ct)) return null;
  const isMedia = /^(video|audio)\//.test(ct) || (MEDIA_EXT.test(path) && !/^(text|image)\//.test(ct));
  if (!isMedia) return null;
  if (size && size < MIN_FILE) return null;
  return /^audio\//.test(ct) || /\.(mp3|m4a|aac|ogg|oga|opus|wav|flac)$/.test(path) ? "audio" : "video";
}

const mediaKey = (tabId) => `media:${tabId}`;

async function getTabMedia(tabId) {
  const key = mediaKey(tabId);
  const got = await chrome.storage.session.get(key);
  return got[key] || [];
}

async function setBadgeCount(tabId, n) {
  try {
    let text = n ? String(n) : "";
    if (!text) {   // medya yoksa: bulut paylasim sayfasi rozeti, o da yoksa torrent/magnet rozeti
      const tab = await chrome.tabs.get(tabId);
      if (kamiCloudKind(tab.url || "") === "share") text = "☁";
      else if (((await chrome.storage.session.get(tlKey(tabId)))[tlKey(tabId)] || []).length) text = "🧲";
    }
    await chrome.action.setBadgeBackgroundColor({ tabId, color: "#7C4DFF" });
    await chrome.action.setBadgeText({ tabId, text });
  } catch (_) { /* sekme kapandi */ }
}

// sayfa (sekme) linkini Kami'ye: bulut paylasimi -> secim penceresi, video sayfasi -> medya penceresi
async function sendPage(url) {
  if (!/^https?:/i.test(url)) return { ok: true, accepted: false, reason: "bad_url" };
  const res = await sendToKami({ url, referrer: url, pageUrl: url, source: "context_menu" });
  if (res.ok && res.accepted) flashBadge("✓", "#7C4DFF");
  else flashBadge(res.ok ? "✕" : "!", "#F0626F");
  return res;
}

let mediaChain = Promise.resolve();   // ayni sekmeye esz amanli yazimlar karismasin
chrome.webRequest.onHeadersReceived.addListener((d) => {
  if (d.tabId < 0 || (d.statusCode !== 200 && d.statusCode !== 206)) return;
  const ct = hdr(d.responseHeaders, "content-type");
  const range = hdr(d.responseHeaders, "content-range");
  const size = Number((range.split("/")[1]) || hdr(d.responseHeaders, "content-length") || 0) || 0;
  const kind = classify(d.url, ct, size);
  if (!kind) return;
  mediaChain = mediaChain.then(async () => {
    const list = await getTabMedia(d.tabId);
    const base = d.url.split("#")[0];
    if (list.some((m) => m.url === base)) return;
    let pageUrl = "";
    try { pageUrl = (await chrome.tabs.get(d.tabId)).url || ""; } catch (_) { return; }
    list.unshift({ url: base, kind, size, mime: ct.split(";")[0], pageUrl, at: Date.now() });
    list.length = Math.min(list.length, MAX_PER_TAB);
    await chrome.storage.session.set({ [mediaKey(d.tabId)]: list });
    setBadgeCount(d.tabId, list.length);
  }).catch(() => {});
}, { urls: ["<all_urls>"], types: ["media", "xmlhttprequest", "other", "object"] }, ["responseHeaders"]);

const pageOf = (u) => { try { const x = new URL(u); return x.origin + x.pathname + (/youtube\.com$/.test(x.hostname) ? x.search : ""); } catch (_) { return u; } };
chrome.tabs.onUpdated.addListener((tabId, info) => {
  if (!info.url) return;
  chrome.storage.session.remove(tlKey(tabId)).then(() => {   // onceki sayfanin magnet/.torrent listesi
    chrome.tabs.sendMessage(tabId, { type: "torrent-rescan" }).catch(() => {});
  });
  getTabMedia(tabId).then((list) => { if (!list.length) setBadgeCount(tabId, 0); });   // bulut rozeti
  getTabMedia(tabId).then((list) => {
    if (list.length && list.every((m) => pageOf(m.pageUrl) !== pageOf(info.url))) {
      chrome.storage.session.remove(mediaKey(tabId));
      setBadgeCount(tabId, 0);
    }
  });
});
chrome.tabs.onRemoved.addListener((tabId) => { chrome.storage.session.remove([mediaKey(tabId), tlKey(tabId)]); });

// ---------- Real-Debrid: sayfadaki magnet / .torrent linkleri ----------
const tlKey = (tabId) => `tl:${tabId}`;
async function saveTorrentLinks(tabId, links) {
  await chrome.storage.session.set({ [tlKey(tabId)]: links.slice(0, 200) });
  const media = await getTabMedia(tabId);
  if (!media.length) setBadgeCount(tabId, 0);
}

function toBase64(buf) {
  const bytes = new Uint8Array(buf);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}

// magnet -> RD; .torrent -> dosya tarayicinin oturumuyla (cerezler) burada indirilir, Kami'ye icerik gider;
// diger linkler (hoster) -> RD unrestrict. Sonuc Kami'de bildirim olarak gorunur.
async function sendRd(url, pageUrl = "") {
  let msg = { type: "rd", url, page_url: pageUrl };
  if (/^https?:/i.test(url) && /\.torrent$/i.test(new URL(url).pathname)) {
    try {
      const r = await fetch(url, { credentials: "include", referrer: pageUrl || undefined });
      const buf = await r.arrayBuffer();
      if (r.ok && buf.byteLength > 0 && buf.byteLength < 6 * 1024 * 1024 && new Uint8Array(buf)[0] === 0x64) {   // 'd' (bencode)
        msg = { type: "rd", torrent_b64: toBase64(buf), name: decodeURIComponent(new URL(url).pathname.split("/").pop()) };
      }
    } catch (_) { /* olmazsa Kami linki kendisi indirmeyi dener */ }
  }
  const res = await native(msg);
  // Rozet + simge ipucu (sag tikta popup yok): basarili mor ✓, RD reddi kirmizi ✕ ve sebebi ipucunda
  if (res.ok && res.accepted) flashBadge("✓", "#7C4DFF", 4000, rdText(res));
  else flashBadge(res.ok ? "✕" : "!", "#F0626F", 8000, rdText(res));
  return res;
}

function rdText(res) {
  const g = (k) => chrome.i18n.getMessage(k);
  if (!res.ok) return g(res.error === "nohost" ? "rd_err_nohost" : "rd_err_offline");
  if (res.accepted) return g(res.pending ? "rd_ok_pending" : res.kind === "queued" ? "rd_ok_queued" : "rd_ok_torrent");
  const code = res.reason || "rd_failed";
  return (g("rd_err_" + code) || g("rd_err_rd_failed")) + (res.detail && (code === "rd_failed" || !g("rd_err_" + code)) ? ` (${res.detail})` : "");
}

// ---------- medyayi Kami'ye gonder (yt-dlp) ----------
async function sendMedia({ url, pageUrl = "", mode = "choose", title = "" }) {
  { const g = cookieGroupOf(url) || cookieGroupOf(pageUrl); if (g) await syncCookies(true, g); }
  const headers = await requestHeaders(url);
  if (pageUrl && pageUrl !== url) headers["Referer"] = pageUrl;
  return native({ type: "media", url, page_url: pageUrl, mode, title, headers });
}

async function onVideoButton(msg, sender) {
  const pageUrl = msg.pageUrl || (sender.tab && sender.tab.url) || "";
  const src = msg.src || "";
  let url = pageUrl, title = "";
  let host = "";
  try { host = new URL(pageUrl).hostname; } catch (_) {}
  if (/^https?:/i.test(src) && !SKIP_HOST.test(new URL(src).hostname) && !KNOWN_SITE.test(host)) {
    url = src; title = msg.title || "";              // dogrudan dosya (generic)
  } else if (!KNOWN_SITE.test(host) && sender.tab) {
    const streams = (await getTabMedia(sender.tab.id)).filter((m) => m.kind === "hls" || m.kind === "dash");
    if (streams.length) { url = streams[0].url; title = msg.title || ""; }   // en son yakalanan akis
  }
  const res = await sendMedia({ url, pageUrl, mode: msg.mode, title });
  if (res.ok && res.accepted) flashBadge("✓", "#7C4DFF");
  return res;
}

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
  syncCookies(true);
  native({ type: "ping" });   // eklenti URL desenlerini Kami'den al
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "kami-download",
      title: chrome.i18n.getMessage("menu_download"),
      contexts: ["link", "video", "audio", "image"],
    });
    chrome.contextMenus.create({   // magnet, .torrent ya da RD destekli hoster linki
      id: "kami-rd",
      title: chrome.i18n.getMessage("menu_rd"),
      contexts: ["link"],
    });
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => { onMenuClicked(info, tab); });

async function onMenuClicked(info, tab) {
  if (info.menuItemId === "kami-rd") {
    if (info.linkUrl) await sendRd(info.linkUrl, info.frameUrl || info.pageUrl || (tab && tab.url) || "");
    return;
  }
  if (info.menuItemId !== "kami-download") return;
  const pageUrl = info.frameUrl || info.pageUrl || (tab && tab.url) || "";
  const url = info.linkUrl || info.srcUrl;
  if (!info.linkUrl && (info.mediaType === "video" || info.mediaType === "audio") && (!url || /^blob:/i.test(url))) {
    // MSE oynatici (YouTube vb.): sayfa linki yt-dlp ile cozulsun, Kami'de secim penceresi acilir
    const res = await sendMedia({ url: pageUrl, pageUrl, mode: "choose" });
    flashBadge(res.ok && res.accepted ? "✓" : "!", res.ok && res.accepted ? "#7C4DFF" : "#F0626F");
    return;
  }
  if (!url || SKIP_SCHEMES.test(url)) return;
  const res = await sendToKami({ url, referrer: pageUrl, pageUrl, source: "context_menu" });
  if (res.ok && res.accepted) {
    flashBadge(res.confirm ? "?" : "✓", res.confirm ? "#E8B86A" : "#7C4DFF");
  } else if (res.ok) {
    // Kami acik ama reddetti (orn. link bir web sayfasi): tarayiciya da indirtme
    flashBadge("✕", "#F0626F");
  } else {
    // Kami kapali: kullanici bos donmesin, tarayici indirsin
    flashBadge("!", "#F0626F");
    chrome.downloads.download({ url });
  }
}
