// Kami Ctrl+K komut paleti: ekrandaki dugmeler + saglayicilar (window.KPAL: indirmeler, oynatici eylemleri,
// son izlenenler, ayar bolumleri). Kami ve Kami Player'da ayni dosya.
"use strict";
(() => {
  const L = (tr, en) => ((typeof state !== "undefined" && state.lang === "en") || document.documentElement.lang === "en" ? en : tr);
  window.KPAL = window.KPAL || [];   // [() => [{t, sub, run}]]
  const extra = () => [
    { t: L("Kami Player'ı aç (kütüphane)", "Open Kami Player (library)"), run: () => window.pywebview?.api?.player_show({ library: true }) },
    { t: L("Ayarlar", "Settings"), run: () => document.getElementById("settings")?.showModal?.() },
  ];
  const label = (b) => (b.getAttribute("title") || b.getAttribute("aria-label") || b.textContent || "").replace(/\s+/g, " ").trim();
  function items() {
    const seen = new Set(), out = [];
    for (const f of window.KPAL) { try { out.push(...(f() || [])); } catch { /* saglayici hatasi */ } }
    if (!window.KAMI_PLAYER_WINDOW) out.push(...extra());
    for (const b of document.querySelectorAll("button, [role=button], a[href='#']")) {
      if (b.closest("#kpal") || b.disabled || !b.offsetParent) continue;
      const t = label(b); if (!t || t.length < 2 || t.length > 70 || seen.has(t)) continue;
      seen.add(t); out.push({ t, run: () => b.click() });
    }
    return out;
  }
  let box, list, inp, cur = [], sel = 0;
  function render() {
    const q = inp.value.toLowerCase().trim();
    const norm = (x) => x.toLocaleLowerCase("tr").normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/ı/g, "i");
    const qq = norm(q).split(/\s+/).filter(Boolean);
    cur = items().filter((x) => { const h = norm(x.t + " " + (x.sub || "")); return qq.every((w) => h.includes(w)); }).slice(0, 14);
    sel = Math.min(sel, Math.max(0, cur.length - 1));
    const esc = (t) => String(t).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
    list.innerHTML = cur.map((x, i) => `<div class="kp-i${i === sel ? " on" : ""}" data-i="${i}">${x.ic ? `<em>${x.ic}</em>` : ""}<span>${esc(x.t)}</span>${x.sub ? `<small>${esc(x.sub)}</small>` : ""}</div>`).join("") || `<div class="kp-e">${L("Sonuç yok", "No results")}</div>`;
  }
  function close() { box?.remove(); box = null; }
  function open() {
    if (box) return close();
    box = document.createElement("div"); box.id = "kpal";
    box.innerHTML = `<div class="kp-w"><input placeholder="${L("Dosya, özellik ya da komut ara… (Esc kapatır)", "Search files, features, commands… (Esc)")}"><div class="kp-l"></div></div>`;
    document.body.appendChild(box);
    inp = box.querySelector("input"); list = box.querySelector(".kp-l");
    box.addEventListener("click", (e) => { const it = e.target.closest(".kp-i"); if (it) { const x = cur[+it.dataset.i]; close(); x?.run(); } else if (e.target === box) close(); });
    inp.addEventListener("input", () => { sel = 0; render(); });
    inp.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { sel = Math.min(cur.length - 1, sel + 1); render(); e.preventDefault(); }
      else if (e.key === "ArrowUp") { sel = Math.max(0, sel - 1); render(); e.preventDefault(); }
      else if (e.key === "Enter") { const x = cur[sel]; close(); x?.run(); }
      else if (e.key === "Escape") close();
      e.stopPropagation();
    });
    render(); inp.focus();
  }
  document.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); e.stopPropagation(); open(); } }, true);
  const st = document.createElement("style");
  st.textContent = `#kpal{position:fixed;inset:0;z-index:9999;background:rgba(5,4,8,.55);backdrop-filter:blur(3px);display:flex;justify-content:center;padding-top:14vh}
  #kpal .kp-w{width:min(560px,90vw);height:max-content;background:#0F0B16;border:1px solid rgba(167,139,250,.4);border-radius:12px;box-shadow:0 20px 60px rgba(0,0,0,.6),0 0 30px rgba(124,58,237,.25);overflow:hidden;font:14px "Segoe UI",system-ui,sans-serif;color:#EDE9F6}
  #kpal input{width:100%;box-sizing:border-box;padding:14px 16px;border:0;border-bottom:1px solid #2B2238;background:none;color:#fff;font:600 15px "Chakra Petch","Segoe UI",sans-serif;outline:none}
  #kpal .kp-l{max-height:50vh;overflow:auto;padding:6px}
  #kpal .kp-i{padding:8px 12px;border-radius:8px;cursor:pointer;display:flex;align-items:center;gap:10px}
  #kpal .kp-i em{font-style:normal;width:18px;text-align:center;opacity:.85}#kpal .kp-i span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  #kpal .kp-i small{color:#8E86A3;font-size:11.5px;max-width:45%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}#kpal .kp-i.on,#kpal .kp-i:hover{background:#3B1580}
  #kpal .kp-e{padding:12px;color:#8E86A3}`;
  document.head.appendChild(st);
})();
