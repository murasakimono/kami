// Kami Player+ (v1.28): devam rafi + siradaki bolum + akilli listeler, dizi/film bilgisi (TVmaze/TMDB),
// intro/outro ogretme, dosya basina ses gecikmesi, IPTV (m3u + rehber), TV'ye yayin (DLNA). Gorsel cila Antigravity'de.
"use strict";
(() => {
  const LS = (k, d) => { try { return JSON.parse(localStorage.getItem(k) || "null") ?? d; } catch { return d; } };
  const SV = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* yok */ } };
  const E = (s) => escapeHtml(String(s ?? ""));
  const base = (p) => String(p).split(/[\\/]/).pop().replace(/\.[^.]+$/, "");
  const META = { series: {}, movies: {}, asked: new Set() };

  // ---------------------------------------------------------------- oynatma sayaci + dosya basina gecikme
  const _start = plStart;
  plStart = function (r) {   // eslint-disable-line no-func-assign
    _start(r);
    try {
      if (r?.path) {
        const c = LS("kami.plays", {}); c[r.path] = { n: (c[r.path]?.n || 0) + 1, t: Date.now() };
        const ks = Object.keys(c); if (ks.length > 2000) delete c[ks[0]];
        SV("kami.plays", c);
        const d = LS("kami.delay", {})[r.path];
        PP.fileDelay = d ?? null;
        if (d != null && PL.delay) PL.delay.delayTime.setTargetAtTime(d / 1000, PL.ctx.currentTime, 0.02);
      }
    } catch { /* yok */ }
  };
  const PP = { fileDelay: null, intro: null, cast: null };
  function setDelay(ms) {
    ms = Math.max(0, Math.min(3000, Math.round(ms / 10) * 10));
    PP.fileDelay = ms;
    const all = LS("kami.delay", {}); if (PL.info?.path) { all[PL.info.path] = ms; SV("kami.delay", all); }
    window.plAudioGraph?.();
    if (PL.delay) PL.delay.delayTime.setTargetAtTime(ms / 1000, PL.ctx.currentTime, 0.02);
    window.plSyncHud?.(`🔊 ${plL("Ses gecikmesi", "Audio delay")}: ${ms} ms`);
    toast(plL(`Ses gecikmesi: ${ms} ms (bu dosya için kaydedildi)`, `Audio delay: ${ms} ms (saved for this file)`));
  }
  const curDelay = () => PP.fileDelay ?? (PX.cfg.delay || 0);

  // ---------------------------------------------------------------- intro / outro ogretme
  function introMark(kind) {
    if (!PL.open || !PL.info?.path) return;
    const v = $("#plVideo"), t = v.currentTime + (PL.offset || 0);
    if (!PP.intro || PP.intro.kind !== kind) { PP.intro = { kind, start: t }; toast(plL(`${kind === "outro" ? "Jenerik" : "İntro"} başı işaretlendi (${t.toFixed(1)} sn). Bittiği yerde tekrar bas.`, `Marked start. Press again at the end.`), 4000); return; }
    const { start } = PP.intro; PP.intro = null;
    if (t - start < 3) { toast(plL("Aralık çok kısa", "Too short"), true); return; }
    api.player_intro_learn(PL.info.path, start, t, kind).then((r) => {
      toast(r?.ok ? plL(`${kind === "outro" ? "Jenerik" : "İntro"} öğrenildi: dizinin diğer bölümlerinde otomatik atlanır.`, "Learned: skipped in other episodes.")
        : r?.error === "dizi_degil" ? plL("Dosya adından dizi/bölüm anlaşılamadı.", "Could not detect series/episode.") : plL("Kaydedilemedi", "Failed"), 4500);
    });
  }

  // ---------------------------------------------------------------- TV'ye yayin
  async function castMenu() {
    if (!PL.open || !PL.info?.path) { toast(plL("Önce bir dosya aç", "Open a file first")); return; }
    if (PP.cast) { castPanel(); return; }
    toast(plL("Ağdaki TV'ler aranıyor…", "Searching TVs…"), 3500);
    const r = await api.cast_devices();
    const devs = r?.devices || [];
    if (!devs.length) { toast(plL("TV/DLNA cihazı bulunamadı (aynı ağda ve açık olmalı; Windows güvenlik duvarı izni gerekebilir).", "No DLNA device found."), 6000); return; }
    const box = pick(plL("Hangi cihazda oynatılsın?", "Cast to"), devs.map((d) => [d.id, `${d.name}${d.model ? " · " + d.model : ""}`]));
    const id = await box; if (!id) return;
    const v = $("#plVideo"), t = v.currentTime + (PL.offset || 0);
    const res = await api.cast_play(id, PL.info.path, t);
    if (!res?.ok) { toast(plL("Yayın başlamadı: ", "Cast failed: ") + (res?.error || ""), 6000); return; }
    v.pause(); PP.cast = { id, name: devs.find((d) => d.id === id)?.name || "TV" };
    castPanel();
  }
  function castPanel() {
    let p = $("#ppCast");
    if (!p) { p = document.createElement("div"); p.id = "ppCast"; p.className = "pp-cast"; $("#player").appendChild(p); }
    p.innerHTML = `<b>📺 ${E(PP.cast.name)}</b><button data-c="Play">▶</button><button data-c="Pause">❚❚</button><button data-c="back">−30</button><button data-c="fwd">+30</button><button data-c="Stop">${plL("Bitir", "Stop")}</button>`;
    p.onclick = async (e) => {
      const c = e.target.closest("[data-c]")?.dataset.c; if (!c) return;
      if (c === "back" || c === "fwd") { const pos = await api.cast_control("Position"); await api.cast_control("Seek", Math.max(0, (pos?.pos || 0) + (c === "fwd" ? 30 : -30))); return; }
      await api.cast_control(c);
      if (c === "Stop") { PP.cast = null; p.remove(); }
    };
  }
  function pick(title, items) {
    return new Promise((ok) => {
      const m = document.createElement("div"); m.className = "pp-pick";
      m.innerHTML = `<div><h4>${E(title)}</h4>${items.map(([v, l]) => `<button data-v="${E(v)}">${E(l)}</button>`).join("")}<button data-v="">${plL("Vazgeç", "Cancel")}</button></div>`;
      m.onclick = (e) => { const b = e.target.closest("[data-v]"); if (!b && e.target !== m) return; m.remove(); ok(b?.dataset.v || ""); };
      document.body.appendChild(m);
    });
  }

  // ---------------------------------------------------------------- eylemler (kisayol + Ctrl+K)
  Object.assign(PL_ACTIONS, {
    delayminus: ["Ses gecikmesi −50 ms", "Audio delay −50 ms", () => setDelay(curDelay() - 50)],
    delayplus: ["Ses gecikmesi +50 ms", "Audio delay +50 ms", () => setDelay(curDelay() + 50)],
    delayreset: ["Ses gecikmesini sıfırla (bu dosya)", "Reset audio delay", () => setDelay(0)],
    intro: ["İntroyu öğret (başta ve sonda bas)", "Teach intro (press at start and end)", () => introMark("intro")],
    outro: ["Jeneriği öğret (başta ve sonda bas)", "Teach outro", () => introMark("outro")],
    cast: ["TV'ye yayınla (DLNA)", "Cast to TV (DLNA)", castMenu],
    iptv: ["IPTV / m3u kanalları", "IPTV / m3u channels", () => { window.plDrawer?.("tv"); }],
  });
  Object.assign(PL_KEYS_DEFAULT, { "-": "delayminus", "=": "delayplus", y: "intro", t: "cast" });

  // ---------------------------------------------------------------- kutuphane: raflar, bilgi, TV sekmesi
  const _render = pxDrawerRender;
  pxDrawerRender = async function () {   // eslint-disable-line no-func-assign
    const tabs = document.querySelector("#plDrawer .px-tabs");
    if (tabs && !tabs.querySelector('[data-tab="tv"]')) tabs.querySelector('[data-tab="lists"]')?.insertAdjacentHTML("afterend", `<button data-tab="tv">TV</button>`);
    if (PX.libTab === "tv") { $$("#plDrawer .px-tabs [data-tab]").forEach((b) => b.classList.toggle("on", b.dataset.tab === "tv")); return renderTv(); }
    await _render();
    if (PX.libTab !== "lib") return;
    if (PX.libSeries) return decorateSeries();
    decorateLib();
  };

  function shelves(L) {
    const pos = LS("kami.pos", {}), watched = LS("kami.watched", {}), plays = LS("kami.plays", {});
    const items = L.items || [];
    const byPath = new Map(items.map((x) => [x.path, x]));
    const durOf = (x) => x?.duration || 0;
    const cont = Object.entries(pos).filter(([p, t]) => byPath.has(p) && t > 30 && !watched[p] && (!durOf(byPath.get(p)) || t < durOf(byPath.get(p)) * 0.93))
      .sort((a, b) => (plays[b[0]]?.t || 0) - (plays[a[0]]?.t || 0)).slice(0, 12).map(([p]) => p);
    const next = [];
    for (const s of L.series || []) {   // izlenen son bolumden sonraki izlenmemis bolum
      const ps = s.paths || []; let last = -1;
      ps.forEach((p, i) => { if (watched[p]) last = i; });
      if (last >= 0 && last < ps.length - 1 && !watched[ps[last + 1]] && !cont.includes(ps[last + 1])) next.push(ps[last + 1]);
    }
    const week = Date.now() / 1000 - 7 * 86400;
    return {
      [plL("Kaldığın yerden devam et", "Continue watching")]: cont,
      [plL("Sıradaki bölüm", "Next episode")]: next.slice(0, 12),
      [plL("Bu hafta eklenenler", "Added this week")]: items.filter((x) => x.mtime > week).sort((a, b) => b.mtime - a.mtime).slice(0, 15).map((x) => x.path),
      [plL("En çok oynatılanlar", "Most played")]: Object.entries(plays).filter(([p, v]) => byPath.has(p) && v.n > 1).sort((a, b) => b[1].n - a[1].n).slice(0, 12).map(([p]) => p),
      [plL("Hiç açılmamış videolar", "Never played videos")]: items.filter((x) => x.kind === "video" && !plays[x.path] && !pos[x.path]).sort((a, b) => b.mtime - a.mtime).slice(0, 15).map((x) => x.path),
    };
  }
  function decorateLib() {
    const body = $("#pxBody"), L = PX.lib; if (!body || !L) return;
    const sh = shelves(L);
    const html = Object.entries(sh).filter(([, v]) => v.length).map(([t, v]) => `<h4>${E(t)}</h4><div class="px-list pp-shelf">${v.map((p) => `<button class="px-row" data-pp="${E(p)}"><span>${E(base(p))}</span>${LS("kami.watched", {})[p] ? "<small>✓</small>" : ""}</button>`).join("")}</div>`).join("");
    if (html) body.insertAdjacentHTML("afterbegin", `<div class="pp-shelves">${html}</div>`);
    // dizi kartlarina afis + puan
    const names = (L.series || []).map((s) => s.name).filter((n) => !META.asked.has(n)).slice(0, 40);
    const paint = () => body.querySelectorAll(".px-series[data-series]").forEach((b) => {
      const m = META.series[b.dataset.series]; if (!m || b.dataset.pp) return;
      b.dataset.pp = "1";
      if (m.poster) { b.style.backgroundImage = `linear-gradient(180deg,transparent 35%,rgba(7,6,11,.92)),url("${m.poster}")`; b.style.backgroundSize = "cover"; b.style.backgroundPosition = "center"; b.classList.add("pp-poster"); }
      if (m.rating || m.year) b.querySelector("small")?.insertAdjacentHTML("beforeend", ` · ${m.year || ""}${m.rating ? " ★" + m.rating : ""}`);
    });
    paint();
    if (names.length) { names.forEach((n) => META.asked.add(n)); api.library_meta(names, []).then((r) => { Object.assign(META.series, r?.series || {}); paint(); }).catch(() => {}); }
  }
  function decorateSeries() {
    const body = $("#pxBody"), name = PX.libSeries; if (!body) return;
    const draw = () => {
      const m = META.series[name]; if (!m || body.querySelector(".pp-info")) return;
      body.querySelector(".px-back")?.insertAdjacentHTML("afterend", `<div class="pp-info">${m.poster ? `<img src="${E(m.poster)}" alt="">` : ""}<div><b>${E(m.title)}</b> <small>${E(m.year)} ${m.rating ? "★" + m.rating : ""} ${E((m.genres || []).join(", "))}</small><p>${E(m.overview)}</p></div></div>`);
      const s = PX.lib?.series?.find((x) => x.name === name);
      body.querySelectorAll(".px-list .px-row[data-play]").forEach((row) => {
        const p = s?.paths?.[+row.dataset.play]; if (!p) return;
        const nm = String(p).split(/[\\/]/).pop(), mm = nm.match(/[Ss](\d{1,2})[ ._-]?[Ee](\d{1,3})|(\d{1,2})x(\d{1,3})/);
        const ep = mm ? m.episodes?.[`S${+(mm[1] || mm[3])}E${+(mm[2] || mm[4])}`] : null;
        if (ep?.name) row.querySelector("span")?.insertAdjacentHTML("beforeend", `<small> · ${E(ep.name)}</small>`);
        if (LS("kami.watched", {})[p]) row.insertAdjacentHTML("beforeend", "<small>✓</small>");
      });
    };
    if (META.series[name]) draw();
    else if (!META.asked.has(name)) { META.asked.add(name); api.library_meta([name], []).then((r) => { Object.assign(META.series, r?.series || {}); draw(); }).catch(() => {}); }
  }

  // ---------------------------------------------------------------- IPTV
  const TV = { list: null, src: "", q: "", group: "", epg: {} };
  async function renderTv() {
    const body = $("#pxBody"); if (!body) return;
    if (!TV.list) {
      const lists = await api.iptv_lists().catch(() => []);
      body.innerHTML = `<p class="px-hint">${plL("m3u / m3u8 listesi (dosya yolu ya da adres). Kendi aboneliğin ya da açık kanallar (örn. iptv-org).", "m3u / m3u8 playlist (path or URL).")}</p>
        <div class="px-save"><input id="ppTvSrc" placeholder="https://… .m3u  ya da  C:\\…\\liste.m3u" value="${E(TV.src || lists[0] || "")}"><button class="pl-b" data-tv="load">${plL("Aç", "Open")}</button></div>
        ${lists.length ? `<h4>${plL("Son listeler", "Recent")}</h4>` + lists.map((l) => `<button class="px-row" data-tvsrc="${E(l)}"><span>${E(l)}</span></button>`).join("") : ""}`;
      return;
    }
    const L = TV.list, q = TV.q.toLocaleLowerCase("tr");
    const chans = L.channels.filter((c) => (!TV.group || c.group === TV.group) && (!q || c.name.toLocaleLowerCase("tr").includes(q))).slice(0, 400);
    const now = Date.now() / 1000;
    const nowOf = (c) => { const e = TV.epg[c.id] || []; const cur = e.find((p) => p.start <= now && p.stop > now); const nx = e.find((p) => p.start > now); return cur ? `${cur.title}${nx ? " → " + nx.title : ""}` : ""; };
    body.innerHTML = `<div class="px-save"><input id="ppTvQ" placeholder="${plL("Kanal ara", "Search")}" value="${E(TV.q)}"><button class="pl-b" data-tv="close">${plL("Liste değiştir", "Change list")}</button></div>
      ${L.groups.length ? `<div class="pp-groups"><button data-tvg="" class="${TV.group ? "" : "on"}">${plL("Tümü", "All")}</button>${L.groups.slice(0, 60).map((g) => `<button data-tvg="${E(g)}" class="${TV.group === g ? "on" : ""}">${E(g)}</button>`).join("")}</div>` : ""}
      <div class="px-list">${chans.map((c) => `<button class="px-row pp-ch" data-tvurl="${E(c.url)}" data-tvname="${E(c.name)}">${c.logo ? `<img src="${E(c.logo)}" alt="" loading="lazy">` : "<i>📺</i>"}<span>${E(c.name)}${nowOf(c) ? `<small> · ${E(nowOf(c))}</small>` : ""}</span></button>`).join("")}</div>
      <p class="px-hint">${L.channels.length} ${plL("kanal", "channels")}${L.epg ? " · " + plL("rehber yükleniyor/yüklendi", "guide") : ""}</p>`;
    const qi = $("#ppTvQ"); if (qi) { qi.oninput = () => { TV.q = qi.value; clearTimeout(TV.t); TV.t = setTimeout(renderTv, 200); }; }
  }
  document.addEventListener("click", async (e) => {
    const b = e.target.closest("#plDrawer [data-pp], #plDrawer [data-tv], #plDrawer [data-tvsrc], #plDrawer [data-tvg], #plDrawer [data-tvurl]");
    if (!b) return;
    e.stopPropagation();
    if (b.dataset.pp) { playerOpenPath(b.dataset.pp); return; }
    if (b.dataset.tvg != null) { TV.group = b.dataset.tvg; renderTv(); return; }
    if (b.dataset.tvurl) { playerOpenUrl(b.dataset.tvurl); return; }
    if (b.dataset.tv === "close") { TV.list = null; renderTv(); return; }
    const src = b.dataset.tvsrc || $("#ppTvSrc")?.value?.trim(); if (!src) return;
    toast(plL("Liste yükleniyor…", "Loading…"));
    const r = await api.iptv_load(src);
    if (!r?.ok) { toast(plL("Liste açılamadı: ", "Failed: ") + (r?.error || ""), 5000); return; }
    TV.list = r; TV.src = src; TV.group = ""; TV.q = ""; renderTv();
    if (r.epg) api.iptv_epg(r.epg, r.channels.map((c) => c.id).filter(Boolean).slice(0, 3000)).then((x) => { if (x?.ok) { TV.epg = x.epg; if (PX.libTab === "tv") renderTv(); } }).catch(() => {});
  }, true);
})();

// v1.28 Kami Deck: telefondaki tuslar Player komutlarini veri yolundan gonderir
(function deckBus() {
  const tick = async () => {
    try {
      const cmds = (await api.deck_bus_poll?.("player")) || [];
      for (const c of cmds) if (PL_ACTIONS[c]) { PL_ACTIONS[c][2](); plWake?.(); }
    } catch {}
    setTimeout(tick, document.hidden ? 1500 : 400);
  };
  let on = false; const start = () => { if (!on) { on = true; setTimeout(tick, 1000); } };
  window.addEventListener("pywebviewready", start);
  if (window.pywebview?.api) start();
})();
