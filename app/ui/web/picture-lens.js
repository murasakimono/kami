// Kami Lens araclari (v1.30): Lens panelinin ustunde fiyat bul (Akakce + Trendyol), metni cikar, tabloyu Excel'e, QR/barkod.
"use strict";
(() => {
  const css = document.createElement("style");
  css.textContent = `
  .lt-bar{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:12px}
  .lt-bar button{border:1px solid var(--line);background:#1a1325;color:var(--text);padding:8px;border-radius:8px;cursor:pointer;font:inherit;font-size:13px;text-align:left}
  .lt-bar button:hover{border-color:#8B5CF6}.lt-out{margin-bottom:14px}
  .lt-q{display:flex;gap:6px;margin:6px 0}.lt-q input{flex:1;background:#0b0912;border:1px solid var(--line);color:var(--text);border-radius:6px;padding:6px 8px}
  .lt-q button{border:1px solid var(--line);background:#6D28D9;color:#fff;border-radius:6px;padding:6px 10px;cursor:pointer}
  .lt-it{display:grid;grid-template-columns:44px 1fr auto;gap:8px;align-items:center;padding:6px;border:1px solid var(--line);border-radius:8px;margin:5px 0;cursor:pointer}
  .lt-it:hover{border-color:#8B5CF6}.lt-it img{width:44px;height:44px;object-fit:contain;background:#fff;border-radius:4px}
  .lt-it b{font-size:12px;display:block;max-height:32px;overflow:hidden}.lt-it small{color:var(--mute);font-size:11px}
  .lt-it .p{font-weight:700;color:#2EE6A6;white-space:nowrap;text-align:right}.lt-it .p small{display:block;font-weight:400}
  .lt-sum{font-size:12px;color:var(--mute);margin:4px 0}
  .lt-txt{width:100%;min-height:120px;background:#0b0912;border:1px solid var(--line);color:var(--text);border-radius:6px;padding:8px;font:13px/1.45 inherit;box-sizing:border-box}
  .lt-tbl{border-collapse:collapse;font-size:11px;width:100%;margin-top:6px}.lt-tbl td{border:1px solid var(--line);padding:3px 5px}
  .lt-code{padding:8px;border:1px solid var(--line);border-radius:8px;margin:5px 0;word-break:break-all;font-size:13px}.lt-code small{color:var(--mute);display:block}`;
  document.head.appendChild(css);
  const tl = (n) => n.toLocaleString("tr-TR", { minimumFractionDigits: n % 1 ? 2 : 0, maximumFractionDigits: 2 }) + " TL";

  async function job(name, ...args) {
    const j = await api.job_start(name, args);
    if (!j?.ok) return { ok: false, error: j?.error || "job_failed" };
    for (let w = 80; ; w = Math.min(w * 1.5, 500)) {
      await new Promise((r) => setTimeout(r, w));
      const r = await api.job_result(j.job);
      if (r?.state === "done") return r.result;
      if (r?.state === "lost") return { ok: false, error: "job_lost" };
    }
  }
  const cur = () => PC.list[PC.i];

  function bar() {
    const box = document.getElementById("pcLens"); if (!box || box.querySelector(".lt-bar")) return;
    const b = document.createElement("div"); b.className = "lt-bar";
    b.innerHTML = `<button data-lt="price">🛒 ${L("Fiyat bul", "Find price")}</button><button data-lt="text">📝 ${L("Metni çıkar", "Extract text")}</button>
      <button data-lt="table">📊 ${L("Tabloyu Excel'e", "Table to Excel")}</button><button data-lt="codes">▦ ${L("QR / barkod", "QR / barcode")}</button>`;
    const out = document.createElement("div"); out.className = "lt-out"; out.id = "ltOut";
    box.prepend(out); box.prepend(b);
  }
  const _draw = drawLens;
  window.drawLens = drawLens = function () { _draw.apply(this, arguments); bar(); };
  const _run = runLens;
  window.runLens = runLens = async function () { const p = _run.apply(this, arguments); bar(); return p; };

  async function price(q) {
    const out = document.getElementById("ltOut");
    out.innerHTML = `<div class="ln-load"><i></i>${L("Akakçe ve Trendyol'da aranıyor…", "Searching Akakçe and Trendyol…")}</div>`;
    const r = await job("lens_price", q || "", cur() || "");
    const qv = r?.query || q || "";
    const head = `<h3>${L("Fiyatlar", "Prices")}</h3><div class="lt-q"><input id="ltQ" value="${esc(qv)}" placeholder="${L("Ürün adı (düzeltebilirsin)", "Product name (editable)")}"><button id="ltGo">${L("Ara", "Search")}</button></div>`;
    if (!r?.ok) { out.innerHTML = head + `<p class="ln-err">${r?.error === "sorgu" ? L("Ürünü tanıyamadım; adını yazıp Ara'ya bas.", "Couldn't identify the product; type its name and search.") : esc(r?.error || "")}</p>`; wire(); return; }
    const errs = Object.keys(r.errors || {});
    out.innerHTML = head + (r.items.length ? `<div class="lt-sum">${L("En düşük", "Lowest")} <b style="color:#2EE6A6">${tl(r.min)}</b> · ${L("orta", "median")} ${tl(r.median)} · ${r.items.length} ${L("sonuç", "results")}</div>` +
      r.items.map((i) => `<div class="lt-it" data-url="${esc(i.url)}"><img src="${esc(i.img)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.style.visibility='hidden'">
        <div><b>${esc(i.name)}</b><small>${esc(i.src)}${i.note ? " · " + esc(i.note) : ""}</small></div><div class="p">${tl(i.price)}<small>${esc(i.src)}</small></div></div>`).join("")
      : `<p class="ln-err">${L("Sonuç yok; adı sadeleştirip tekrar dene.", "No results; simplify the name and retry.")}</p>`) +
      (errs.length ? `<p class="ln-err">${L("Yanıt vermeyen", "Not responding")}: ${esc(errs.join(", "))}</p>` : "");
    wire();
  }
  function wire() {
    const go = document.getElementById("ltGo"), q = document.getElementById("ltQ");
    if (go) go.onclick = () => price(q.value.trim());
    if (q) q.onkeydown = (e) => { if (e.key === "Enter") price(q.value.trim()); };
  }

  document.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-lt]"); if (!b) return;
    const p = cur(); if (!p) return;
    const out = document.getElementById("ltOut"), k = b.dataset.lt;
    if (k === "price") return price("");
    if (k === "text") {
      out.innerHTML = `<div class="ln-load"><i></i>${L("Yazı okunuyor…", "Reading text…")}</div>`;
      const r = await job("lens_text", p);
      out.innerHTML = `<h3>${L("Metin", "Text")} <small>(${L("düzenleyebilirsin", "editable")})</small></h3><textarea class="lt-txt" id="ltTxt">${esc(r?.text || "")}</textarea>
        <div class="lt-q"><button id="ltCopy">${L("Kopyala", "Copy")}</button><button id="ltPrice">🛒 ${L("Bu metinle fiyat ara", "Search price with this")}</button></div>`;
      document.getElementById("ltCopy").onclick = async () => { await navigator.clipboard?.writeText(document.getElementById("ltTxt").value).catch(() => api.copy_text?.(document.getElementById("ltTxt").value)); toast(L("Kopyalandı", "Copied")); };
      document.getElementById("ltPrice").onclick = () => price(document.getElementById("ltTxt").value.split("\n").find((x) => x.trim().length > 3) || "");
      if (!r?.text) toast(L("Yazı bulunamadı", "No text found"));
    } else if (k === "table") {
      out.innerHTML = `<div class="ln-load"><i></i>${L("Tablo çıkarılıyor…", "Extracting table…")}</div>`;
      const r = await job("lens_table", p);
      if (!r?.ok) { out.innerHTML = `<p class="ln-err">${esc(r?.error || "")}</p>`; return; }
      out.innerHTML = `<h3>${L("Tablo", "Table")} · ${r.rows}×${r.cols}</h3><table class="lt-tbl">${r.preview.map((row) => `<tr>${row.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`).join("")}</table>
        <div class="lt-q"><button data-open="${esc(r.path)}">📂 ${L("Excel dosyasını aç", "Open Excel file")}</button></div>`;
      out.querySelector("[data-open]").onclick = () => api.open_path(r.path);
    } else if (k === "codes") {
      const r = await job("lens_codes", p);
      if (!r?.ok || !r.codes?.length) { out.innerHTML = `<p class="ln-err">${L("Kod bulunamadı", "No code found")}${r?.error ? ": " + esc(r.error) : ""}</p>`; return; }
      out.innerHTML = `<h3>QR / ${L("barkod", "barcode")}</h3>` + r.codes.map((c) => `<div class="lt-code"><small>${esc(c.format)}</small>${esc(c.text)}
        <div class="lt-q">${c.kind === "url" ? `<button data-url="${esc(c.text)}">${L("Aç", "Open")} ↗</button>` : ""}${c.kind === "product" ? `<button data-pq="${esc(c.text)}">🛒 ${L("Fiyat ara", "Find price")}</button>` : ""}<button data-copy="${esc(c.text)}">${L("Kopyala", "Copy")}</button></div></div>`).join("");
      out.querySelectorAll("[data-pq]").forEach((x) => x.onclick = () => price(x.dataset.pq));
      out.querySelectorAll("[data-copy]").forEach((x) => x.onclick = () => navigator.clipboard?.writeText(x.dataset.copy).then(() => toast(L("Kopyalandı", "Copied"))));
    }
  });
})();
