// Kami Player penceresi (ayri pywebview penceresi, ayni Kami sureci). Sunak'in app.js'i yuklenmez;
// oynaticinin ihtiyac duydugu kucuk yardimcilar burada. Acilacak dosyalar Python kuyrugundan (player_poll) gelir.
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const state = { lang: "tr", settings: {} };
const STATE_HOOKS = [];
let api = null;
let toastTimer = 0;
window.KAMI_PLAYER_WINDOW = true;   // player.js: tam ekran = pencere tam ekrani, kapat = pencereyi kapat

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function toast(msg, isErr = false) {
  const el = $("#toast");
  el.textContent = msg; el.classList.toggle("err", isErr); el.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { el.hidden = true; }, 3200);
}
async function slow(name, ...args) {   // uzun isler: is kimligi al, sonucu yokla (app.js ile ayni)
  const j = await api.job_start(name, args);
  if (!j || !j.ok) return { ok: false, error: (j && j.error) || "job_failed" };
  for (let wait = 60; ; wait = Math.min(wait * 1.5, 400)) {
    await new Promise((r) => setTimeout(r, wait));
    const r = await api.job_result(j.job);
    if (r.state === "done") return r.result;
    if (r.state === "lost") return { ok: false, error: "job_lost" };
  }
}

async function shellPoll() {
  try {
    const q = await api.player_poll();
    for (const it of q || []) {
      if (it.path) await playerOpenPath(it.path, it.queue);
      else if (it.url) await playerOpenUrl(it.url);
      if (it.library) plDrawer("lib");
    }
  } catch (e) { /* pencere kapanirken */ }
  setTimeout(shellPoll, 400);
}

window.addEventListener("pywebviewready", async () => {
  api = window.pywebview.api;
  try { state.settings = await api.get_settings(); state.lang = state.settings.language || "tr"; } catch { /* varsayilan */ }
  plBuild();
  plIdle(true);
  shellPoll();
});

// bos durum: dosya yokken kutuphane + ipucu
function plIdle(on) {
  const el = $("#plEmpty");
  if (el) el.hidden = !on;
  const pl = $("#player");
  if (pl) { pl.hidden = false; pl.classList.toggle("is-empty", on); }
}
