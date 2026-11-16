// Kami Kapsul: bir dosyaya sureli, istege bagli sifreli paylasim linki (dosya bilgisayardan cikmaz; Oda tuneli).
// Ctrl+K "Kami Kapsül". (Gorunum sade; Antigravity'de cilalanabilir.)
"use strict";
(() => {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const A = () => window.pywebview?.api;
  const size = (n) => { const u = ["B", "KB", "MB", "GB"]; let i = 0; while (n >= 1024 && i < 3) { n /= 1024; i++; } return (i ? n.toFixed(1) : n) + " " + u[i]; };
  const left = (t) => { const s = t - Date.now() / 1000; return s > 86400 ? Math.floor(s / 86400) + " gün" : s > 3600 ? Math.floor(s / 3600) + " saat" : Math.max(1, Math.floor(s / 60)) + " dk"; };
  let poll = 0;
  function css() {
    if (document.getElementById("kapCss")) return;
    const st = document.createElement("style"); st.id = "kapCss";
    st.textContent = `
#kap{position:fixed;inset:0;z-index:9000;display:grid;place-items:center;background:rgba(6,4,10,.66)}
#kap .kb{width:min(720px,94vw);max-height:86vh;display:flex;flex-direction:column;background:var(--panel,#15111C);border:1px solid var(--line,#2A2236);color:var(--text,#E7E2EF);font:13px var(--font,system-ui)}
#kap header{display:flex;align-items:center;gap:10px;padding:12px 14px;border-bottom:1px solid var(--line,#2A2236)}#kap header b{font:600 16px var(--font-display,system-ui);flex:1}
#kap .form{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;padding:12px 14px;border-bottom:1px solid var(--line,#2A2236)}
#kap .form label{display:grid;gap:4px;color:var(--muted,#9A91AB);font-size:12px}#kap .form .wide{grid-column:1/-1}
#kap input,#kap select{background:var(--bg,#0D0A12);color:var(--text,#E7E2EF);border:1px solid var(--line,#2A2236);padding:7px 8px;font:inherit}
#kap button{background:var(--raised,#1D1727);color:inherit;border:1px solid var(--line,#2A2236);padding:7px 12px;cursor:pointer;font:inherit}#kap button.pri{background:var(--btn,#7C4DFF);border-color:transparent;color:#fff}
#kap .list{overflow:auto}#kap .it{display:grid;grid-template-columns:1fr auto;gap:6px 12px;padding:10px 14px;border-bottom:1px solid rgba(255,255,255,.04)}
#kap .it b{word-break:break-all}#kap .it .m{color:var(--muted,#9A91AB);font-size:12px}#kap .it .u{grid-column:1/-1;display:flex;gap:6px}#kap .it .u input{flex:1}
#kap .empty{padding:30px;text-align:center;color:var(--muted,#9A91AB)}`;
    document.head.appendChild(st);
  }
  async function render(box) {
    const r = await A().kapsul_list();
    const items = r?.items || [];
    clearTimeout(poll);
    if (items.some((x) => !x.url)) poll = setTimeout(() => document.getElementById("kap") && render(box), 2500);
    box.querySelector(".list").innerHTML = items.length ? items.map((x) => `<div class="it" data-id="${esc(x.id)}">
      <div><b>${esc(x.name)}</b><div class="m">${size(x.size)} · ${left(x.expires)} kaldı${x.locked ? " · şifreli" : ""}${x.max_dl ? ` · ${x.downloads}/${x.max_dl} indirme` : ` · ${x.downloads} indirme`}</div></div>
      <div><button class="del">Sil</button></div>
      <div class="u"><input readonly value="${esc(x.url || "Bağlantı hazırlanıyor (tünel açılıyor)…")}"><button class="cp" ${x.url ? "" : "disabled"}>Kopyala</button></div></div>`).join("")
      : `<div class="empty">Henüz kapsül yok. Bir dosya seç; arkadaşına giden link süre dolunca kendiliğinden ölür.</div>`;
  }
  async function open() {
    if (!A()?.kapsul_create) return;
    css();
    document.getElementById("kap")?.remove();
    const wrap = document.createElement("div"); wrap.id = "kap";
    wrap.innerHTML = `<div class="kb"><header><b>Kami Kapsül</b><button class="close">Kapat</button></header>
      <div class="form">
        <label>Süre <select class="h"><option value="1">1 saat</option><option value="24" selected>24 saat</option><option value="72">3 gün</option><option value="168">7 gün</option><option value="720">30 gün</option></select></label>
        <label>Şifre (isteğe bağlı) <input class="pw" type="password" autocomplete="new-password"></label>
        <label>İndirme sınırı <select class="mx"><option value="0">Sınırsız</option><option value="1">1 kez</option><option value="5">5 kez</option><option value="20">20 kez</option></select></label>
        <label>&nbsp;<button class="pri mk">Dosya seç ve paylaş</button></label>
        <label class="wide">Not (sayfada görünür) <input class="nt" maxlength="200"></label>
        <label class="wide" style="display:flex;gap:8px;align-items:center"><input type="checkbox" class="sh" style="width:auto"> Görsellerde Gizlilik Kalkanı uygula (yüz, telefon, e-posta, TC, IBAN, kart bulanık; konum bilgisi silinir)</label>
      </div><div class="list"></div></div>`;
    document.body.appendChild(wrap);
    const box = wrap.querySelector(".kb");
    wrap.addEventListener("click", async (e) => {
      if (e.target === wrap || e.target.closest(".close")) { wrap.remove(); return; }
      if (e.target.closest(".mk")) {
        const r = await A().kapsul_create("", +box.querySelector(".h").value, box.querySelector(".pw").value, +box.querySelector(".mx").value, box.querySelector(".nt").value, box.querySelector(".sh").checked);
        if (r?.ok) { box.querySelector(".pw").value = ""; box.querySelector(".nt").value = ""; if (r.url) { navigator.clipboard?.writeText(r.url).catch(() => A().copy_text(r.url)); window.toast?.("Kapsül linki kopyalandı" + (r.shielded ? ` · ${Object.values(r.shielded).reduce((a, b) => a + b, 0)} bölge gizlendi` : "")); } }
        else if (r?.error && r.error !== "cancelled") window.toast?.("Olmadı: " + r.error, true);
        render(box); return;
      }
      const it = e.target.closest(".it"); if (!it) return;
      if (e.target.closest(".cp")) { const u = it.querySelector("input").value; navigator.clipboard?.writeText(u).catch(() => A().copy_text(u)); e.target.textContent = "Kopyalandı"; return; }
      if (e.target.closest(".del")) { await A().kapsul_delete(it.dataset.id); render(box); }
    });
    document.addEventListener("keydown", function k(e) { if (e.key === "Escape") { wrap.remove(); document.removeEventListener("keydown", k); } });
    render(box);
  }
  window.KPAL = window.KPAL || [];
  window.KPAL.push(() => [{ t: "Kami Kapsül", sub: "Süreli / şifreli paylaşım linki", run: open }]);
  window.KamiKapsul = { open };
})();
