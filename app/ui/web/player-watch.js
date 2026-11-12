// Kami Oda: Oynaticidan canli yayin (Discord "Go Live" gibi). Player odaya "yayinci" olarak katilir,
// videonun goruntu+sesini WebRTC ile gonderir; izleyen kendi kalitesini secer.
"use strict";
const WP = { core: null, stream: null, sid: "", room: null, tracks: new Map() };

function wpCapture() {
  const v = $("#plVideo");
  const st = v.captureStream ? v.captureStream() : v.mozCaptureStream?.();
  if (!st) throw new Error("captureStream yok");
  // ileri sarma/kaynak degisince izler yenilenir: gondericide eskisinin yerine yenisini koy
  st.addEventListener("addtrack", (e) => {
    const old = WP.tracks.get(e.track.kind);
    if (old && old !== e.track && WP.core) WP.core.replaceTrack(WP.sid, old, e.track);
    WP.tracks.set(e.track.kind, e.track);
    wpPad(st);
  });
  return st;
}
// yayin akisinda hem ses hem goruntu izi hep olsun (bazi kaynaklarda izler gec gelir)
function wpPad(st) { st.getTracks().forEach((t) => WP.tracks.set(t.kind, t)); }

async function wpStart() {
  if (!PL.open) { toast(plL("Önce bir video aç", "Open a video first")); return; }
  const r = await api.room_open(true);
  if (!r?.on) { toast(plL("Oda açılamadı", "Could not open room"), true); return; }
  WP.room = r;
  WP.stream = wpCapture(); wpPad(WP.stream);
  WP.core = new KamiRoom({ base: r.local, name: (r.name || "Kami") + " · " + plL("Oynatıcı", "Player"), kind: "stream", on: {
    quality: (from, q) => wpBadge(q),
    msg: (from, m) => wpCtl(from, m),
    roster: () => setTimeout(() => wpState(true), 1500),
  } });
  WP.sid = WP.core.addLocal("player", WP.stream);
  await WP.core.join();
  wpBtn(true);
}
// izleyenlere oynatici durumu: oynuyor mu, sure, altyazi listesi ve o anki satir (altyazi goruntuye girmiyor)
function wpState(force) {
  if (!WP.core) return;
  const v = $("#plVideo");
  const st = { paused: v.paused, t: +plNow().toFixed(1), dur: +(PL.dur || 0).toFixed(1),
    subs: (PL.subList || []).map((x) => x.label), sub: PL.subIdx ?? -1,
    line: ($("#plSubs")?.innerText || "").trim(), title: PL.info?.title || "" };
  const key = JSON.stringify([st.paused, Math.round(st.t / 5), st.sub, st.line, st.subs.length]);
  if (!force && key === WP.lastKey) return;
  WP.lastKey = key;
  WP.core.broadcast({ k: "pl", st });
}
function wpCtl(from, m) {
  if (!m || m.k !== "plc") return;
  const v = $("#plVideo");
  if (m.act === "toggle") { if (v.paused) v.play().catch(() => {}); else v.pause(); }
  else if (m.act === "seek" && isFinite(m.v)) plSeek(Math.max(0, Math.min(PL.dur || 1e9, +m.v)), !v.paused);
  else if (m.act === "skip" && isFinite(m.v)) plSeek(Math.max(0, plNow() + +m.v), !v.paused);
  else if (m.act === "sub") { const sel = $("#plSub"); if (sel) { sel.value = String(m.v); plLoadSub(+m.v); } }
  setTimeout(() => wpState(true), 400);
}
setInterval(() => wpState(false), 500);
setInterval(() => wpState(true), 5000);

async function wpStop() {
  if (!WP.core) return;
  WP.core.removeLocal(WP.sid); await WP.core.leave();
  WP.core = null; WP.stream = null; WP.tracks.clear();
  wpBtn(false);
}
function wpBadge(q) { const b = document.querySelector(".pl-wp em"); if (b) b.textContent = q === "src" ? "" : q + "p"; }
function wpBtn(on) {
  const b = document.querySelector(".pl-wp"); if (!b) return;
  b.classList.toggle("live", on);
  b.querySelector("span").textContent = on ? plL("Yayında · durdur", "Live · stop") : plL("Odada yayınla", "Go live in room");
}
window.KPAL = window.KPAL || [];
window.KPAL.push(() => [
  { ic: "📡", t: plL("Odada yayınla (Kami Oda)", "Go live in Kami Room"), sub: plL("sesli oda + oynatıcı yayını", "voice room + player stream"), run: () => (WP.core ? wpStop() : wpStart()) },
  { ic: "🎙", t: plL("Kami Oda'yı aç", "Open Kami Room"), sub: plL("sesli konuşma, ekran paylaşımı", "voice chat, screen share"), run: () => api.room_open(true) },
]);
(function wpButton() {
  const top = document.querySelector(".pl-top");
  if (!top) { setTimeout(wpButton, 500); return; }
  if (top.querySelector(".pl-wp")) return;
  const b = document.createElement("button");
  b.className = "pl-wp"; b.title = plL("Kami Oda: oynatıcıyı canlı yayınla", "Kami Room: stream the player live");
  b.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="2.5"/><path d="M7.8 7.8a6 6 0 0 0 0 8.4M16.2 7.8a6 6 0 0 1 0 8.4M5 5a10 10 0 0 0 0 14M19 5a10 10 0 0 1 0 14"/></svg><span>${plL("Odada yayınla", "Go live in room")}</span><em></em>`;
  b.onclick = (e) => { e.stopPropagation(); WP.core ? wpStop() : wpStart(); };
  top.querySelector(".pl-title")?.after(b);
})();
window.addEventListener("beforeunload", () => WP.core?.leave());
