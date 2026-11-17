// Kami Kasa: videolarini ve gorsellerini anlamiyla ara ("sahilde gun batimi", "hocanin kalp sesleri anlattigi yer").
// Ctrl+K "Kami Kasa" ya da Ctrl+Shift+K. Sonuca tikla: video o sahnenin saniyesinden Kami Player'da acilir.
// (Gorunum sade; Antigravity'de cilalanabilir.)
"use strict";
(() => {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (t) => { t = Math.max(0, Math.floor(t || 0)); const h = Math.floor(t / 3600), m = Math.floor(t / 60) % 60, s = t % 60; return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(s).padStart(2, "0"); };
  const A = () => window.pywebview?.api;
  let timer = 0, pollT = 0;
  function css() {
    if (document.getElementById("kasaCss")) return;
    const st = document.createElement("style"); st.id = "kasaCss";
    st.textContent = `
#kasa{position:fixed;inset:0;z-index:9000;display:grid;place-items:center;background:rgba(6,4,10,.66)}
#kasa .kb{width:min(980px,94vw);height:min(720px,88vh);display:flex;flex-direction:column;background:var(--panel,#15111C);border:1px solid var(--line,#2A2236);color:var(--text,#E7E2EF);font:13px var(--font,system-ui)}
#kasa header{display:flex;gap:10px;align-items:center;padding:12px 14px;border-bottom:1px solid var(--line,#2A2236)}
#kasa header b{font:600 16px var(--font-display,system-ui)}
#kasa input{flex:1;background:var(--bg,#0D0A12);color:inherit;border:1px solid var(--line,#2A2236);padding:9px 12px;font:inherit;outline:none}
#kasa input:focus{border-color:var(--accent,#9D6BFF)}
#kasa button{background:var(--raised,#1D1727);color:inherit;border:1px solid var(--line,#2A2236);padding:8px 12px;cursor:pointer;font:inherit}
#kasa button.pri{background:var(--btn,#7C4DFF);border-color:transparent;color:#fff}
#kasa .bar{padding:8px 14px;color:var(--muted,#9A91AB);border-bottom:1px solid rgba(255,255,255,.04);display:flex;gap:12px;align-items:center;flex-wrap:wrap}
#kasa .grid{flex:1;overflow:auto;padding:12px;display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;align-content:start}
#kasa .card{cursor:pointer;background:var(--raised,#1D1727);border:1px solid transparent}
#kasa .card:hover{border-color:var(--accent,#9D6BFF)}
#kasa .th{aspect-ratio:16/9;background:#000 center/cover no-repeat;position:relative}
#kasa .th i{position:absolute;right:6px;bottom:6px;background:rgba(0,0,0,.75);padding:1px 6px;font-style:normal;font-size:11px}
#kasa .th em{position:absolute;left:6px;top:6px;background:var(--accent-soft,rgba(157,107,255,.25));color:var(--accent-2,#C9B3FF);padding:1px 6px;font-style:normal;font-size:10px}
#kasa .meta{padding:8px}#kasa .meta b{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#kasa .meta span{color:var(--muted,#9A91AB);font-size:12px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
#kasa .empty{grid-column:1/-1;color:var(--muted,#9A91AB);text-align:center;padding:60px 20px;line-height:1.7}`;
    document.head.appendChild(st);
  }
  async function refresh(box) {
    const st = await A().kasa_setup();
    const bar = box.querySelector(".bar");
    const ix = st.index || {};
    bar.innerHTML = `<span>${st.files || 0} dosya · ${st.segments || 0} sahne</span>
      <span>${st.installed ? "Anlamsal arama: açık" : st.installing ? "Anlamsal arama kuruluyor: " + esc(st.installing) : "Anlamsal arama kapalı (yalnızca kelime)"}</span>
      ${ix.running ? `<span>İndeksleniyor ${ix.done}/${ix.total}: ${esc(ix.current)}</span>` : ""}
      <span style="flex:1"></span>
      ${!st.installed && !st.installing ? `<button class="inst">Anlamsal aramayı kur (~${st.size_gb} GB)</button>` : ""}
      <button class="idx" ${ix.running ? "disabled" : ""}>Klasör ekle</button>`;
    clearTimeout(pollT);
    if (ix.running || st.installing) pollT = setTimeout(() => document.getElementById("kasa") && refresh(box), 2000);
    return st;
  }
  async function search(box) {
    const q = box.querySelector("input").value.trim();
    const grid = box.querySelector(".grid");
    if (!q) { grid.innerHTML = `<div class="empty">Ne aradığını kendi cümlenle yaz: <i>"karla kaplı dağ"</i>, <i>"gitar solosu"</i>, <i>"sınavda çıkan EKG"</i>…<br>Önce "Klasör ekle" ile videolarının ve fotoğraflarının olduğu klasörü indeksle.</div>`; return; }
    grid.innerHTML = `<div class="empty">Aranıyor…</div>`;
    const r = await A().kasa_search(q, 48);
    const res = r?.results || [];
    if (!res.length) { grid.innerHTML = `<div class="empty">Sonuç yok.${r?.semantic ? "" : " (Anlamsal arama kurulu değil: yalnızca kelime eşleşmesi aranıyor.)"}</div>`; return; }
    grid.innerHTML = res.map((x, i) => `<div class="card" data-i="${i}">
      <div class="th" style="${x.thumb_url ? `background-image:url('${x.thumb_url}')` : ""}">${x.kind === "doc" ? `<i>s.${Math.max(1, Math.round(x.start_sec || 1))}</i>` : x.kind !== "image" ? `<i>${fmt(x.start_sec)}</i>` : ""}${x.why ? `<em>${esc(x.why)}</em>` : ""}</div>
      <div class="meta"><b title="${esc(x.path)}">${esc(x.title)}</b><span>${esc(x.snippet || "")}</span></div></div>`).join("");
    grid.onclick = (e) => { const c = e.target.closest(".card"); if (!c) return; const x = res[+c.dataset.i]; A().kasa_open(x.path, x.start_sec || 0); };
  }
  async function open() {
    if (!A()?.kasa_search) return;
    css();
    document.getElementById("kasa")?.remove();
    const wrap = document.createElement("div"); wrap.id = "kasa";
    wrap.innerHTML = `<div class="kb"><header><b>Kami Kasa</b><input placeholder="Anlamıyla ara… (örn. sahilde gün batımı)" autofocus>
      <button class="pri go">Ara</button><button class="close">Kapat</button></header><div class="bar"></div><div class="grid"></div></div>`;
    document.body.appendChild(wrap);
    const box = wrap.querySelector(".kb"), inp = box.querySelector("input");
    inp.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => search(box), 450); });
    inp.addEventListener("keydown", (e) => { if (e.key === "Enter") { clearTimeout(timer); search(box); } if (e.key === "Escape") wrap.remove(); });
    wrap.addEventListener("click", async (e) => {
      if (e.target === wrap || e.target.closest(".close")) { wrap.remove(); return; }
      if (e.target.closest(".go")) { search(box); return; }
      if (e.target.closest(".idx")) { const r = await A().kasa_index_folder(""); if (r?.ok) refresh(box); return; }
      if (e.target.closest(".inst")) {
        const st = await A().kasa_setup();
        const ok = typeof kAsk === "function" ? await kAsk(`Anlamsal arama bir kez kurulacak (~${st.size_gb} GB, işlemcide çalışır). Kurulsun mu?`) : confirm(`Anlamsal arama kurulsun mu? (~${st.size_gb} GB)`);
        if (ok) { await A().ai_install("kasa"); refresh(box); }
      }
    });
    await refresh(box);
    search(box);
    inp.focus();
  }
  window.KPAL = window.KPAL || [];
  window.KPAL.push(() => [{ t: "Kami Kasa", sub: "Videolarını ve fotoğraflarını anlamıyla ara", run: open }]);
  document.addEventListener("keydown", (e) => { if (e.ctrlKey && e.shiftKey && (e.key === "K" || e.key === "k")) { e.preventDefault(); open(); } });
  window.KamiKasa = { open };
})();
