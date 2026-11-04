"use strict";
const t = (k) => chrome.i18n.getMessage(k);
const ask = (payload) => chrome.runtime.sendMessage({ type: "popup", payload });

document.getElementById("captureLabel").textContent = t("popup_capture");
document.getElementById("open").textContent = t("popup_open");
document.getElementById("hint").textContent = t("popup_alt_hint");

// "Bu sayfayi Kami ile indir": sag tiki kendi menusuyle ezen siteler (Yandex Disk vb.) icin
let pageTab = null;
async function setupPage() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const b = document.getElementById("page");
  if (!tab || !/^https?:/i.test(tab.url || "")) { b.hidden = true; return; }
  pageTab = tab;
  const site = kamiCloudSite(tab.url);
  b.textContent = site && site.kind === "share" ? chrome.i18n.getMessage("popup_page_cloud", [site.name]) : t("popup_page");
  b.addEventListener("click", async () => {
    b.disabled = true;
    const res = await chrome.runtime.sendMessage({ type: "page-add", url: tab.url, title: tab.title });
    const ok = res && res.ok && res.accepted;
    b.classList.add(ok ? "ok" : "err");
    b.textContent = ok ? "✓" : "✕";
    if (ok) setTimeout(() => window.close(), 700);
  });
}

async function refresh() {
  const res = await ask({ type: "ping" });
  const status = document.getElementById("status");
  const text = document.getElementById("statusText");
  const capture = document.getElementById("capture");
  const open = document.getElementById("open");
  document.getElementById("page").disabled = !(res && res.ok && pageTab);
  if (res && res.ok) {
    status.className = "status on";
    text.textContent = t("popup_connected") + (res.version ? ` (${res.version})` : "");
    capture.disabled = false;
    capture.checked = !!res.capture_enabled;
    open.disabled = false;
    return true;
  } else {
    status.className = "status off";
    text.textContent = res && res.error === "nohost" ? t("popup_nohost") : t("popup_offline");
    capture.disabled = true;
    open.disabled = true;
    return false;
  }
}

document.getElementById("capture").addEventListener("change", async (e) => {
  const res = await ask({ type: "set_capture", enabled: e.target.checked });
  if (!res || !res.ok) refresh();
});
document.getElementById("open").addEventListener("click", async () => {
  await ask({ type: "show" });
  window.close();
});

const fmtSize = (n) => !n ? "" : n > 1 << 30 ? (n / (1 << 30)).toFixed(1) + " GB" : (n / (1 << 20)).toFixed(1) + " MB";
const nameOf = (u) => { try { const x = new URL(u); return decodeURIComponent(x.pathname.split("/").pop() || x.hostname); } catch (_) { return u; } };

async function showMedia(online) {
  const box = document.getElementById("media");
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) return;
  const list = await chrome.runtime.sendMessage({ type: "get-media", tabId: tab.id }) || [];
  box.hidden = false;
  document.getElementById("mediaTitle").textContent = t("popup_media");
  const empty = document.getElementById("mediaEmpty");
  empty.hidden = list.length > 0;
  empty.textContent = t("popup_media_none");
  const ul = document.getElementById("mediaList");
  ul.innerHTML = "";
  for (const m of list) {
    const li = document.createElement("li");
    const nm = document.createElement("div"); nm.className = "nm"; nm.textContent = nameOf(m.url); nm.title = m.url;
    const kd = document.createElement("div"); kd.className = "kd";
    kd.textContent = [m.kind.toUpperCase(), fmtSize(m.size)].filter(Boolean).join(" · ");
    const acts = document.createElement("div"); acts.className = "acts";
    for (const [mode, label] of [["mp4", "MP4"], ["mp3", "MP3"], ["choose", t("popup_choose")]]) {
      const b = document.createElement("button");
      b.textContent = label; b.disabled = !online;
      b.addEventListener("click", async () => {
        b.disabled = true;
        const res = await chrome.runtime.sendMessage({ type: "media-add", url: m.url, pageUrl: m.pageUrl || tab.url, mode, title: tab.title });
        b.textContent = res && res.ok && res.accepted ? "✓" : "✕";
      });
      acts.appendChild(b);
    }
    li.append(nm, acts, kd);
    ul.appendChild(li);
  }
}

setupPage().then(refresh).then((online) => showMedia(online));
