// Birlikte izle (sunucu tarafi oynatici): oda ac, baglanti paylas, oynat/durdur/atla esitle, sohbet.
"use strict";
const WP = { on: false, v: 0, n: 0, st: null, applying: 0, panel: null, unread: 0, lastSent: 0 };

function wpPanel() {
  if (WP.panel) return WP.panel;
  const p = document.createElement("div");
  p.id = "wpPanel"; p.className = "wp-panel"; p.hidden = true;
  p.innerHTML = `<div class="wp-head"><b>${plL("Birlikte izle", "Watch together")}</b><span id="wpWho"></span><button id="wpMin" title="${plL("Küçült", "Minimise")}">–</button></div>
    <div class="wp-link"><input id="wpUrl" readonly value="${plL("Bağlantı hazırlanıyor…", "Preparing link…")}"><button id="wpCopy">${plL("Kopyala", "Copy")}</button></div>
    <p class="wp-hint" id="wpHint">${plL("Bağlantıyı gönder; açan kişi tarayıcıdan katılır. Oynat, durdur ve ileri sar herkeste aynı anda olur.", "Send the link; the other person joins from a browser. Play, pause and seeking stay in sync.")}</p>
    <div class="wp-chat" id="wpChat"></div>
    <form class="wp-send" id="wpSend"><input id="wpMsg" placeholder="${plL("Mesaj…", "Message…")}" maxlength="500" autocomplete="off"><button>➤</button></form>
    <button class="wp-stop" id="wpStop">${plL("Odayı kapat", "Close room")}</button>`;
  document.body.appendChild(p);
  p.querySelector("#wpCopy").onclick = () => { const u = $("#wpUrl").value; if (!u.startsWith("http")) return; navigator.clipboard?.writeText(u).catch(() => api.copy_text(u)); $("#wpCopy").textContent = plL("Kopyalandı", "Copied"); setTimeout(() => ($("#wpCopy").textContent = plL("Kopyala", "Copy")), 1500); };
  p.querySelector("#wpStop").onclick = wpStop;
  p.querySelector("#wpMin").onclick = () => p.classList.toggle("min");
  p.querySelector("#wpSend").onsubmit = (e) => { e.preventDefault(); const t = $("#wpMsg").value.trim(); if (t) { api.watch_act("chat", false, 0, t); $("#wpMsg").value = ""; } };
  p.addEventListener("keydown", (e) => e.stopPropagation());   // oynatici kisayollari mesaj yazarken calismasin
  WP.panel = p;
  return p;
}

async function wpStart() {
  if (!PL.open || !PL.info) return;
  const i = PL.info;
  const info = { title: i.title, kind: i.kind, mode: PL.mode, duration: PL.dur, direct_url: i.direct_url, stream_url: i.stream_url,
    cover: i.cover || "", audio: i.audio || [], subs: (PL.subList || []).map((s) => ({ label: s.label, url: s.url })) };
  const p = wpPanel(); p.hidden = false; p.classList.remove("min");
  const r = await api.watch_start(info, true);
  if (!r?.on) { $("#wpUrl").value = plL("Açılamadı: ", "Failed: ") + (r?.error || ""); return; }
  WP.on = true; WP.v = 0; WP.n = 0; $("#wpChat").innerHTML = "";
  api.watch_act("state", !$("#plVideo").paused, plNow());
  wpLoop();
}
async function wpStop() {
  WP.on = false; await api.watch_stop();
  if (WP.panel) WP.panel.hidden = true;
}
function wpTarget(st) { return st.t + (st.playing ? Math.max(0, Date.now() / 1000 + WP.skew - st.at) : 0); }

async function wpLoop() {
  while (WP.on) {
    try {
      const r = await api.watch_poll(WP.v, WP.n);
      if (!r?.on) { WP.on = false; break; }
      WP.skew = r.now - Date.now() / 1000;
      const s = r.status || {};
      $("#wpUrl").value = s.url || (s.tunnel === "installing" ? plL("Cloudflare aracı indiriliyor (ilk sefer, ~30 MB)…", "Downloading Cloudflare tool (first time)…")
        : s.tunnel === "error" ? plL("Tünel açılamadı: ", "Tunnel failed: ") + s.error + " · " + plL("yerel: ", "local: ") + s.local
          : plL("Bağlantı hazırlanıyor…", "Preparing link…"));
      $("#wpWho").textContent = r.people?.length ? "· " + r.people.join(", ") : "· " + plL("kimse yok", "nobody yet");
      if (r.state.v > WP.v) {
        WP.v = r.state.v; WP.st = r.state;
        if (r.state.by !== "host") wpApply(r.state);
      }
      for (const e of r.events || []) {
        WP.n = Math.max(WP.n, e.n);
        const el = document.createElement("div");
        el.className = "wp-msg" + (e.kind === "sys" ? " sys" : "");
        el.innerHTML = `<b>${escapeHtml(e.who)}</b> ${escapeHtml(e.text)}`;
        $("#wpChat").appendChild(el); $("#wpChat").scrollTop = 1e9;
        if (e.kind !== "sys" && WP.panel.classList.contains("min")) wpBubble(e);
      }
    } catch { /* gec */ }
    await new Promise((ok) => setTimeout(ok, 400));
    wpWatchLocal();
  }
}
function wpBubble(e) {
  const b = document.createElement("div"); b.className = "wp-bubble";
  b.innerHTML = `<b>${escapeHtml(e.who)}</b> ${escapeHtml(e.text)}`;
  document.body.appendChild(b); setTimeout(() => b.remove(), 6000);
}
function wpApply(st) {
  WP.applying = Date.now();
  const v = $("#plVideo"), t = wpTarget(st);
  if (Math.abs(plNow() - t) > 1.5) plSeek(t, st.playing);
  else if (st.playing && v.paused) v.play().catch(() => {});
  else if (!st.playing && !v.paused) v.pause();
}
// yerelde oynat/durdur/atla olduysa odaya bildir (uzaktan gelen uygulamasini ve tamponlamayi yok say)
function wpWatchLocal() {
  if (!WP.on || !WP.st || Date.now() - WP.applying < 1800 || $("#plSpin")?.classList.contains("on")) return;
  const v = $("#plVideo"), playing = !v.paused, t = plNow();
  const exp = wpTarget(WP.st);
  if (playing !== WP.st.playing || Math.abs(t - exp) > 2.5) {
    WP.st = { playing, t, at: Date.now() / 1000 + (WP.skew || 0), by: "host", v: WP.st.v };
    api.watch_act("state", playing, t);
  }
}

window.KPAL = window.KPAL || [];
window.KPAL.push(() => [{ ic: "👥", t: plL("Birlikte izle", "Watch together"), sub: plL("bağlantı paylaş, eşli izle", "share a link, watch in sync"), run: () => (WP.on ? (WP.panel.hidden = false) : wpStart()) }]);

// ust cubuga dugme
(function wpButton() {
  const top = document.querySelector(".pl-top");
  if (!top) { setTimeout(wpButton, 500); return; }
  if (top.querySelector(".pl-wp")) return;
  const b = document.createElement("button");
  b.className = "pl-wp"; b.title = plL("Birlikte izle", "Watch together");
  b.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="9" cy="8" r="3.2"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6"/><circle cx="17" cy="9" r="2.6"/><path d="M15.5 14.2A5 5 0 0 1 21 19"/></svg><span>${plL("Birlikte izle", "Watch together")}</span>`;
  b.onclick = (e) => { e.stopPropagation(); if (WP.on) { WP.panel.hidden = !WP.panel.hidden; } else wpStart(); };
  top.querySelector(".pl-title")?.after(b);
})();
