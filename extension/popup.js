"use strict";
const t = (k, subs) => chrome.i18n.getMessage(k, subs);
const ask = (payload) => chrome.runtime.sendMessage({ type: "popup", payload });

document.getElementById("captureLabel").textContent = t("popup_capture");
document.getElementById("open").textContent = t("popup_open");
document.getElementById("hint").textContent = t("popup_alt_hint");

// "Bu sayfayi Kami ile indir": sag tiki kendi menusuyle ezen siteler (Yandex Disk vb.) icin
let pageTab = null;
async function setupPage() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const b = document.getElementById("page");
  if (!tab || !/^https?:/i.test(tab.url || "")) {   // brave://, chrome://, Web Store, dosya: icerik betigi yok
    const note = document.getElementById("restricted");
    note.textContent = t("popup_restricted");
    note.hidden = false;
    return;
  }
  if (/^https:\/\/(chrome\.google\.com\/webstore|chromewebstore\.google\.com)\//i.test(tab.url)) {
    const note = document.getElementById("restricted");
    note.textContent = t("popup_restricted");
    note.hidden = false;
  }
  pageTab = tab;
  b.hidden = false;
  const site = kamiCloudSite(tab.url);
  if (site && site.kind === "share") {
    // iki satir: ana metin + altta kucuk site adi (tek satirda tasiyordu)
    const main = document.createElement("span"); main.textContent = t("popup_page_cloud");
    const sub = document.createElement("small"); sub.textContent = site.name;
    b.replaceChildren(main, sub);
  } else b.textContent = t("popup_page");
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
  const res = await ask({ type: "ping" }).catch(() => null);
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
  if (!tab || !pageTab) return;   // kisitli sayfa: medya bolumu gosterme
  const list = await chrome.runtime.sendMessage({ type: "get-media", tabId: tab.id }).catch(() => []) || [];
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

// sayfadaki magnet / .torrent linkleri -> Real-Debrid (Kami uzerinden)
async function showTorrents(online) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) return;
  const list = await chrome.runtime.sendMessage({ type: "get-torrents", tabId: tab.id }).catch(() => []) || [];
  if (!list.length) return;
  const box = document.getElementById("torrents");
  box.hidden = false;
  document.getElementById("torrentsTitle").textContent = `${t("popup_torrents")} (${list.length})`;
  const ul = document.getElementById("torrentList");
  const sendFns = [];
  // Sonuc: buton ✓/✕ + altinda sebep (RD'nin reddi anlasilir metinle; ornek: telif engeli)
  const mark = (b, res, resEl) => {
    const ok = res && res.ok && res.accepted;
    b.textContent = ok ? "✓" : "✕";
    b.classList.toggle("bad", !ok);
    if (resEl) {
      resEl.hidden = false;
      resEl.className = "res " + (ok ? "ok" : "err");
      resEl.textContent = rdResultText(res);
    }
  };
  for (const l of list) {
    const li = document.createElement("li");
    const nm = document.createElement("div"); nm.className = "nm";
    nm.textContent = l.text || nameOf(l.url); nm.title = l.url;
    const kd = document.createElement("div"); kd.className = "kd";
    kd.textContent = /^magnet:/i.test(l.url) ? "MAGNET" : "TORRENT";
    const acts = document.createElement("div"); acts.className = "acts";
    const b = document.createElement("button");
    b.textContent = t("popup_rd_send"); b.disabled = !online;
    acts.appendChild(b);
    const res = document.createElement("div"); res.className = "res"; res.hidden = true;
    li.append(nm, acts, kd, res);
    ul.appendChild(li);
    const send = async () => {
      b.disabled = true;
      b.textContent = "…";
      const r = await chrome.runtime.sendMessage({ type: "rd-send", url: l.url, pageUrl: tab.url });
      mark(b, r, res);
      return r;
    };
    b.addEventListener("click", send);
    sendFns.push(send);
  }
  const all = document.getElementById("rdAll");
  all.textContent = t("popup_rd_all");
  all.hidden = list.length < 2; all.disabled = !online;
  all.addEventListener("click", async () => {
    all.disabled = true;
    let okN = 0;
    for (const fn of sendFns) { const r = await fn(); if (r && r.ok && r.accepted) okN++; }
    all.textContent = t("popup_rd_all_result", [String(okN), String(sendFns.length)]);
  });
}

// RD sonucu -> kisa metin (eklenti dili). Bilinmeyen RD hatasi: genel metin + RD'nin ham hata adi.
function rdResultText(res) {
  if (!res) return t("rd_err_rd_failed");
  if (!res.ok) return t(res.error === "nohost" ? "rd_err_nohost" : "rd_err_offline");
  if (res.accepted) return t(res.pending ? "rd_ok_pending" : res.kind === "queued" ? "rd_ok_queued" : "rd_ok_torrent");
  const code = res.reason || "rd_failed";
  const msg = t("rd_err_" + code);
  if (!msg) return t("rd_err_rd_failed") + (res.detail ? ` (${res.detail})` : ` (${code})`);
  return code === "rd_failed" && res.detail ? `${msg} (${res.detail})` : msg;
}

setupPage().catch(() => {}).then(refresh).then((online) => { showMedia(online); showTorrents(online); });
