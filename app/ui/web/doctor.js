// Kami Doktor: Ayarlar > Hakkinda'daki dugme ve Ctrl+K "Kami Doktor". Kontrolleri calistirir, sonucu gosterir,
// guvenli onarimlari tek tikla uygular. (Gorunum sade; Antigravity'de cilalanabilir.)
"use strict";
(() => {
  const ICON = { ok: "✓", warn: "!", fail: "✕", info: "i" };
  const FIXL = { copy_virtual_keys: "Anahtarları kopyala", room_relink: "Linki yenile", open_wv2: "WebView2'yi indir", restart_aria2: "Motoru Başlat", ollama_start: "Başlat", clear_logs: "Temizle", report: "Sorun paketi" };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  function css() {
    if (document.getElementById("kdocCss")) return;
    const st = document.createElement("style"); st.id = "kdocCss";
    st.textContent = `
#kdoc{position:fixed;inset:0;z-index:9000;display:grid;place-items:center;background:rgba(6,4,10,.66)}
#kdoc .kd, #ecoDocHost .kd{width:min(760px,92vw);max-height:86vh;display:flex;flex-direction:column;background:var(--panel,#15111C);border:1px solid var(--line,#2A2236);color:var(--text,#E7E2EF);font:13px var(--font,system-ui)}
#kdoc header, #ecoDocHost header{display:flex;align-items:center;gap:12px;padding:14px 16px;border-bottom:1px solid var(--line,#2A2236)}
#kdoc header b, #ecoDocHost header b{font:600 16px var(--font-display,system-ui)} #kdoc header .sp, #ecoDocHost header .sp{flex:1}
#kdoc .sum, #ecoDocHost .sum{color:var(--muted,#9A91AB)} #kdoc .list, #ecoDocHost .list{overflow:auto;padding:6px 0}
#kdoc .it, #ecoDocHost .it{display:grid;grid-template-columns:26px 190px 1fr auto;gap:10px;align-items:start;padding:8px 16px;border-bottom:1px solid rgba(255,255,255,.03)}
#kdoc .ic, #ecoDocHost .ic{width:20px;height:20px;display:grid;place-items:center;font-weight:700;font-size:12px;border:1px solid currentColor}
#kdoc .ok .ic, #ecoDocHost .ok .ic{color:var(--ok,#5FD3A0)} #kdoc .warn .ic, #ecoDocHost .warn .ic{color:#F5B94A} #kdoc .fail .ic, #ecoDocHost .fail .ic{color:#FF6B81} #kdoc .info .ic, #ecoDocHost .info .ic{color:var(--muted,#9A91AB)}
#kdoc .nm, #ecoDocHost .nm{font-weight:600} #kdoc .dt, #ecoDocHost .dt{color:var(--muted,#9A91AB);word-break:break-word}
#kdoc button, #ecoDocHost button{background:var(--raised,#1D1727);color:var(--text,#E7E2EF);border:1px solid var(--line,#2A2236);padding:6px 10px;cursor:pointer;font:inherit}
#kdoc button.pri, #ecoDocHost button.pri{background:var(--btn,#7C4DFF);color:#fff;border-color:transparent} #kdoc button:disabled, #ecoDocHost button:disabled{opacity:.5}`;
    document.head.appendChild(st);
  }
  function syncDot(r) {
    const dot = document.getElementById("skDocDot");
    if (!dot) return;
    const fails = Number(r?.summary?.fail || 0);
    dot.hidden = fails <= 0;
    if (fails > 0) dot.title = `Kami Doktor: ${fails} sorun tespit edildi (tıkla)`;
  }
  function render(box, r) {
    syncDot(r);
    const s = r.summary || {};
    box.querySelector(".sum").textContent = `Kami ${r.version} · ${s.ok || 0} sağlam · ${s.warn || 0} uyarı · ${s.fail || 0} sorun`;
    box.querySelector(".list").innerHTML = (r.checks || []).map((c) => `<div class="it ${esc(c.status)}">
      <span class="ic">${ICON[c.status] || "?"}</span><span class="nm">${esc(c.name)}</span><span class="dt">${esc(c.detail)}</span>
      <span>${c.fix ? `<button data-fix="${esc(c.fix)}">${esc(FIXL[c.fix] || "Onar")}</button>` : ""}</span></div>`).join("");
  }
  async function run(box) {
    box.querySelector(".sum").textContent = "Kontrol ediliyor…";
    box.querySelector(".list").innerHTML = "";
    try { render(box, await window.pywebview.api.doctor_run()); }
    catch (e) { box.querySelector(".sum").textContent = "Doktor çalışmadı: " + (e?.message || e); }
  }
  function bindBox(box) {
    box.addEventListener("click", async (e) => {
      if (e.target.closest(".again")) { run(box); return; }
      const b = e.target.closest("[data-fix]"); if (!b) return;
      b.disabled = true;
      try {
        const r = await window.pywebview.api.doctor_fix(b.dataset.fix);
        b.textContent = r?.ok ? "Tamam ✓" : "Olmadı";
        if (r?.ok && b.dataset.fix !== "report" && b.dataset.fix !== "open_wv2") setTimeout(() => run(box), 600);
      } catch { b.textContent = "Olmadı"; }
    });
  }
  function renderInto(host) {
    if (!host || !window.pywebview?.api?.doctor_run) return;
    css();
    host.innerHTML = `<div class="kd" style="width:100%;max-height:none;border:0;background:transparent">
      <header style="padding:4px 0 10px"><b>Kami Doktor</b><span class="sum"></span><span class="sp"></span>
      <button class="again">Yeniden tara</button><button data-fix="report">Sorun paketi</button></header><div class="list"></div></div>`;
    const box = host.querySelector(".kd");
    bindBox(box);
    run(box);
  }
  async function checkDot() {
    if (!window.pywebview?.api?.doctor_run) return;
    try { syncDot(await window.pywebview.api.doctor_run()); } catch {}
  }
  function open() {
    if (!window.pywebview?.api?.doctor_run) return;
    css();
    document.getElementById("kdoc")?.remove();
    const wrap = document.createElement("div"); wrap.id = "kdoc";
    wrap.innerHTML = `<div class="kd"><header><b>Kami Doktor</b><span class="sum"></span><span class="sp"></span>
      <button class="again">Yeniden tara</button><button data-fix="report">Sorun paketi</button><button class="pri close">Kapat</button></header><div class="list"></div></div>`;
    document.body.appendChild(wrap);
    const box = wrap.querySelector(".kd");
    bindBox(box);
    wrap.addEventListener("click", (e) => { if (e.target === wrap || e.target.closest(".close")) wrap.remove(); });
    document.addEventListener("keydown", function k(e) { if (e.key === "Escape") { wrap.remove(); document.removeEventListener("keydown", k); } });
    run(box);
  }
  function mountButton() {
    const rep = document.getElementById("reportBtn");
    if (!rep || document.getElementById("doctorBtn")) return;
    const row = document.createElement("div"); row.className = "row";
    row.innerHTML = `<span class="hint">Kami'nin her parçasını kontrol eder, bulduğu sorunları tek tıkla onarır.</span>
      <button type="button" class="btn ghost" id="doctorBtn">Kami Doktor</button>`;
    rep.closest(".row")?.after(row);
    row.querySelector("button").addEventListener("click", open);
  }
  window.KPAL = window.KPAL || [];
  window.KPAL.push(() => [{ t: "Kami Doktor", sub: "Sağlık kontrolü ve onarım", run: open }]);
  const initDoc = () => { mountButton(); setTimeout(checkDot, 6000); setInterval(() => { if (!document.hidden) checkDot(); }, 1800000); };   // v2.5.3: 5 dk yerine 30 dk, pencere gizliyken calismaz (21 kontrol + ag denemesi)
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initDoc); else initDoc();
  window.KamiDoctor = { open, renderInto, checkDot };
})();
