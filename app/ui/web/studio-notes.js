// Fikir 6 (Klip Notu) + Fikir 8 (Revizyon Günlüğü): Studio'da zaman damgalı notlar + revizyon kaydı.
"use strict";
(() => {
  const KEY_N = "kami.studio.notes";
  const KEY_R = "kami.studio.rev";
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  const btn = document.createElement("button");
  btn.id = "stNotesBtn";
  btn.textContent = "📝 Notlar";
  btn.style.cssText = "position:fixed;right:14px;top:14px;z-index:80;background:rgba(16,12,26,.95);border:1px solid var(--ac,#9D6BFF);border-radius:8px;padding:6px 10px;color:var(--tx,#EDE9F6);font:600 12px 'Chakra Petch',sans-serif;cursor:pointer";
  document.body.appendChild(btn);

  let panel = null;
  const open = () => {
    if (panel) { panel.remove(); panel = null; return; }
    let notes = [], rev = [];
    try { notes = JSON.parse(localStorage.getItem(KEY_N) || "[]"); } catch {}
    try { rev = JSON.parse(localStorage.getItem(KEY_R) || "[]"); } catch {}
    panel = document.createElement("div");
    panel.id = "stNotesPanel";
    panel.style.cssText = "position:fixed;right:14px;top:52px;z-index:80;width:320px;max-height:420px;overflow:auto;background:rgba(16,12,26,.97);border:1px solid var(--ac,#9D6BFF);border-radius:12px;padding:12px;box-shadow:0 16px 40px rgba(0,0,0,.6)";
    panel.innerHTML =
      `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"><b>Notlar & Revizyon</b><button data-x style="border:0;background:none;color:var(--mut);cursor:pointer;font-size:14px">✕</button></div>` +
      `<textarea id="stNoteIn" rows="2" placeholder="Klip notu ekle (zaman damgalı)…" style="width:100%;box-sizing:border-box;background:#0D0A14;border:1px solid var(--ac);border-radius:6px;color:var(--tx);padding:6px;font:500 12px sans-serif"></textarea>` +
      `<button id="stNoteAdd" style="margin-top:6px;width:100%;border:1px solid var(--ac);background:rgba(157,107,255,.18);color:var(--tx);border-radius:6px;padding:5px;cursor:pointer">Not ekle</button>` +
      `<div id="stNoteList" style="margin-top:8px">` +
        (notes.length ? notes.map(n => `<div style="padding:5px 0;border-top:1px solid rgba(157,107,255,.15);font-size:12px">${esc(n.text)}<small style="color:var(--mut)"> · ${new Date(n.t).toLocaleTimeString("tr-TR")}</small></div>`).join("") : `<div style="color:var(--mut);font-size:12px">Henüz not yok.</div>`) +
      `</div>` +
      `<div style="margin-top:10px;border-top:1px solid rgba(157,107,255,.3);padding-top:8px"><b style="font-size:12px">Revizyon Günlüğü</b><div style="margin-top:4px">` +
        (rev.length ? rev.slice(0, 12).map(r => `<div style="font-size:11px;color:var(--mut);padding:2px 0">${new Date(r.t).toLocaleString("tr-TR")} · ${r.clips} klip, ${r.tracks} iz</div>`).join("") : `<div style="color:var(--mut);font-size:11px">Henüz değişiklik yok.</div>`) +
      `</div></div>`;
    document.body.appendChild(panel);
    panel.querySelector("[data-x]").onclick = () => { panel.remove(); panel = null; };
    panel.querySelector("#stNoteAdd").onclick = () => {
      const v = panel.querySelector("#stNoteIn").value.trim();
      if (!v) return;
      try {
        const ns = JSON.parse(localStorage.getItem(KEY_N) || "[]");
        ns.unshift({ t: Date.now(), text: v });
        localStorage.setItem(KEY_N, JSON.stringify(ns.slice(0, 200)));
      } catch {}
      panel.remove(); panel = null; open();
    };
  };
  btn.onclick = open;
})();
