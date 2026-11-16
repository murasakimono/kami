// Gizlilik Kalkani (secenek): secilen gorsellerde yuz, e-posta, telefon, TC kimlik, IBAN ve kart numaralarini
// pikseller, konum (GPS) dahil EXIF'i siler; "_gizli" kopyasini yazar. Ctrl+K "Gizlilik Kalkanı".
"use strict";
(() => {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const A = () => window.pywebview?.api;
  const NAMES = { face: "yüz", email: "e-posta", phone: "telefon", tc: "TC no", iban: "IBAN", card: "kart", manual: "elle" };
  const KINDS = [["faces", "Yüzler"], ["email", "E-posta"], ["phone", "Telefon"], ["tc", "TC kimlik"], ["iban", "IBAN"], ["card", "Kart no"]];
  function open() {
    if (!A()?.privacy_shield) return;
    document.getElementById("kpriv")?.remove();
    const w = document.createElement("div"); w.id = "kpriv";
    w.style.cssText = "position:fixed;inset:0;z-index:9000;display:grid;place-items:center;background:rgba(6,4,10,.66)";
    w.innerHTML = `<div style="width:min(620px,94vw);max-height:84vh;display:flex;flex-direction:column;background:var(--panel,#15111C);border:1px solid var(--line,#2A2236);color:var(--text,#E7E2EF);font:13px var(--font,system-ui)">
      <div style="display:flex;align-items:center;gap:10px;padding:12px 14px;border-bottom:1px solid var(--line,#2A2236)"><b style="flex:1;font-size:16px">Gizlilik Kalkanı</b>
        <button class="go" style="background:var(--btn,#7C4DFF);color:#fff;border:0;padding:8px 12px;cursor:pointer">Görsel seç</button>
        <button class="x" style="background:var(--raised,#1D1727);color:inherit;border:1px solid var(--line,#2A2236);padding:8px 12px;cursor:pointer">Kapat</button></div>
      <div style="padding:10px 14px;display:flex;flex-wrap:wrap;gap:12px;border-bottom:1px solid var(--line,#2A2236)">
        ${KINDS.map(([k, t]) => `<label style="display:flex;gap:6px;align-items:center"><input type="checkbox" value="${k}" checked> ${t}</label>`).join("")}</div>
      <div class="res" style="overflow:auto;padding:6px 0"><p style="color:var(--muted,#9A91AB);padding:12px 14px;margin:0">Orijinal dosyaya dokunulmaz; yanına "_gizli" kopyası yazılır. Konum ve kamera bilgileri (EXIF) de silinir.</p></div></div>`;
    document.body.appendChild(w);
    w.addEventListener("click", async (e) => {
      if (e.target === w || e.target.closest(".x")) { w.remove(); return; }
      const rv = e.target.closest("[data-path]"); if (rv) { A().privacy_reveal(rv.dataset.path); return; }
      if (!e.target.closest(".go")) return;
      const kinds = [...w.querySelectorAll("input[type=checkbox]:checked")].map((x) => x.value);
      const res = w.querySelector(".res");
      res.innerHTML = `<p style="padding:12px 14px;margin:0">Taranıyor…</p>`;
      const r = await A().privacy_shield([], kinds);
      if (!r?.ok) { res.innerHTML = `<p style="padding:12px 14px;margin:0">${r?.error === "cancelled" ? "Vazgeçildi." : "Olmadı: " + esc(r?.error)}</p>`; return; }
      res.innerHTML = r.items.map((it) => {
        const f = it.found || {}, parts = Object.entries(f).map(([k, n]) => `${n} ${NAMES[k] || k}`);
        return `<div style="display:grid;grid-template-columns:1fr auto;gap:8px;padding:9px 14px;border-bottom:1px solid rgba(255,255,255,.04)">
          <div><b style="word-break:break-all">${esc(it.src.split(/[\\/]/).pop())}</b><div style="color:var(--muted,#9A91AB);font-size:12px">${it.ok ? (parts.length ? "Gizlendi: " + parts.join(", ") : "Hassas bilgi bulunamadı (EXIF yine silindi)") + (it.ocr ? "" : " · yazı okunamadı") : "Hata: " + esc(it.error)}</div></div>
          ${it.ok ? `<button data-path="${esc(it.path)}" style="background:var(--raised,#1D1727);color:inherit;border:1px solid var(--line,#2A2236);padding:6px 10px;cursor:pointer">Göster</button>` : ""}</div>`;
      }).join("");
    });
  }
  window.KPAL = window.KPAL || [];
  window.KPAL.push(() => [{ t: "Gizlilik Kalkanı", sub: "Görselde yüz, telefon, TC, IBAN... bulanıklaştır", run: open }]);
  window.KamiPrivacy = { open };
})();
