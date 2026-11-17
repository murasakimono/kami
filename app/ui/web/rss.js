/* Kami - RSS otomatik indirme: Takip gorunumunun altinda "RSS akislari" bolumu.
   Satir ici filtre duzenleme, eslesme rozetleri ve tablo onizleme. Arka uc app/core/rss.py */
(function () {
  const en = () => (document.documentElement.lang || "tr").startsWith("en");
  const L = (tr, e) => (en() ? e : tr);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const R = { list: [], queues: [], editing: null };
  const ago = (ts) => { if (!ts) return "—"; const m = Math.round((Date.now() / 1000 - ts) / 60); return m < 60 ? `${m} ${L("dk", "min")}` : `${Math.round(m / 60)} ${L("sa", "h")}`; };

  const css = document.createElement("style");
  css.textContent = `
  .rss-card{display:grid;gap:8px;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:rgba(19,15,30,.85);margin-bottom:8px}
  .rss-top{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
  .rss-title{flex:1;min-width:180px}
  .rss-title b{display:block;font-size:13px;color:var(--text)}
  .rss-pills{display:flex;gap:6px;flex-wrap:wrap;margin-top:4px;font-size:11px}
  .rss-pill{padding:2px 7px;border-radius:999px;background:rgba(157,107,255,.12);border:1px solid rgba(157,107,255,.28);color:#C4B5FD}
  .rss-pill.exc{background:rgba(255,77,106,.1);border-color:rgba(255,77,106,.3);color:#FF8FA3}
  .rss-pill.ok{background:rgba(46,230,166,.1);border-color:rgba(46,230,166,.3);color:#2EE6A6}
  .rss-acts{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
  .rss-inline{display:grid;grid-template-columns:1fr 1fr 110px auto auto;gap:6px;padding-top:8px;border-top:1px solid rgba(255,255,255,.06);align-items:center}
  .rss-prev-tbl{width:100%;border-collapse:collapse;font-size:12px;margin-top:8px}
  .rss-prev-tbl td{padding:5px 8px;border-bottom:1px solid rgba(255,255,255,.05)}
  .rss-prev-tbl tr.hit td:first-child{color:#2EE6A6;font-weight:700}
  .rss-prev-tbl tr.miss{opacity:.52}`;
  document.head.appendChild(css);

  function mount() {
    const view = document.getElementById("followView");
    if (!view || document.getElementById("rssSec")) return;
    const sec = document.createElement("div");
    sec.id = "rssSec"; sec.style.marginTop = "22px";
    sec.innerHTML = `
      <div class="rd-head"><h2>${L("RSS akışları", "RSS feeds")}</h2><span class="hint">${L("Torrent akışı ya da podcast: yeni çıkan, filtrene uyan otomatik iner.", "Torrent feed or podcast: matching items download automatically.")}</span><span class="spacer"></span>
        <button type="button" class="btn ghost" id="rssCheckAll">${L("Hepsini şimdi yokla", "Check all now")}</button></div>
      <form class="fw-add" id="rssForm" autocomplete="off" style="flex-wrap:wrap">
        <input id="rssUrl" type="text" spellcheck="false" placeholder="https://nyaa.si/?page=rss&q=… / podcast RSS" style="flex:2;min-width:260px" aria-label="RSS URL">
        <input id="rssInc" type="text" placeholder="${L("İçersin (ör. 1080p, /regex/)", "Include (e.g. 1080p, /regex/)")}" style="flex:1;min-width:180px" aria-label="${L("İçersin", "Include")}">
        <input id="rssExc" type="text" placeholder="${L("İçermesin (ör. 720p, batch)", "Exclude (e.g. 720p, batch)")}" style="flex:1;min-width:140px" aria-label="${L("İçermesin", "Exclude")}">
        <label class="tb-conc"><span>${L("Geriye", "Backfill")}</span><input id="rssBack" type="number" min="0" max="30" value="0"></label>
        <button type="submit" class="btn primary">${L("Ekle", "Add")}</button>
      </form>
      <ul class="rd-list" id="rssList" style="list-style:none;padding:0"></ul>
      <p class="hint" id="rssEmpty" hidden>${L("Henüz RSS akışı yok.", "No RSS feeds yet.")}</p>
      <div id="rssPrev" style="max-height:240px;overflow:auto"></div>`;
    view.appendChild(sec);
    bind();
  }

  async function refresh() {
    mount();
    try { [R.list, R.queues] = await Promise.all([api.rss_list(), api.queue_list?.() || []]); } catch { return; }
    const ul = document.getElementById("rssList"); if (!ul) return;
    document.getElementById("rssEmpty").hidden = R.list.length > 0;
    const qopt = (f) => `<select data-rss="queue" data-id="${f.id}" aria-label="${L("Kuyruk seç", "Select queue")}"><option value="">${L("Ana kuyruk", "Main queue")}</option>` +
      R.queues.map((q) => `<option value="${esc(q.id)}"${f.queue === q.id ? " selected" : ""}>⧉ ${esc(q.name)}</option>`).join("") + `</select>`;
    ul.innerHTML = R.list.map((f) => {
      const isEdit = R.editing === f.id;
      return `<li class="rss-card" data-fid="${esc(f.id)}">
        <div class="rss-top">
          <div class="rss-title">
            <b>${esc(f.title || f.url)}</b>
            <div class="rss-pills">
              <span class="rss-pill">${L("son", "last")}: ${ago(f.last)}</span>
              ${f.matched != null ? `<span class="rss-pill ok">${f.matched} ${L("eşleşen", "matched")}</span>` : ""}
              ${f.include ? `<span class="rss-pill">+ ${esc(f.include)}</span>` : ""}
              ${f.exclude ? `<span class="rss-pill exc">− ${esc(f.exclude)}</span>` : ""}
              ${f.max_mb ? `<span class="rss-pill">≤ ${f.max_mb} MB</span>` : ""}
              ${f.error ? `<span class="rss-pill exc">${esc(f.error.slice(0, 60))}</span>` : ""}
            </div>
          </div>
          <div class="rss-acts">
            ${qopt(f)}
            <button type="button" class="btn ghost" data-rss="edit" data-id="${f.id}">${L("Filtre", "Filter")}</button>
            <button type="button" class="btn ghost" data-rss="prev" data-id="${f.id}">${L("Önizle", "Preview")}</button>
            <button type="button" class="btn ghost" data-rss="toggle" data-id="${f.id}">${f.enabled ? L("Açık", "On") : L("Kapalı", "Off")}</button>
            <button type="button" class="btn ghost" data-rss="check" data-id="${f.id}">${L("Yokla", "Check")}</button>
            <button type="button" class="btn ghost danger" data-rss="remove" data-id="${f.id}" aria-label="${L("Kaldır", "Remove")}">✕</button>
          </div>
        </div>
        ${isEdit ? `<div class="rss-inline">
          <input data-rf="inc" value="${esc(f.include || "")}" placeholder="${L("İçersin", "Include")}">
          <input data-rf="exc" value="${esc(f.exclude || "")}" placeholder="${L("İçermesin", "Exclude")}">
          <input data-rf="max" type="number" min="0" value="${f.max_mb || 0}" placeholder="MB (0=∞)">
          <button type="button" class="btn primary" data-rss="save" data-id="${f.id}">${L("Kaydet", "Save")}</button>
          <button type="button" class="btn ghost" data-rss="cancel" data-id="${f.id}">${L("İptal", "Cancel")}</button>
        </div>` : ""}
      </li>`;
    }).join("");
  }

  function showPreview(items) {
    const box = document.getElementById("rssPrev");
    if (!items?.length) { box.innerHTML = ""; return; }
    box.innerHTML = `<table class="rss-prev-tbl"><tbody>${items.map((it) =>
      `<tr class="${it.match ? "hit" : "miss"}"><td style="width:24px">${it.match ? "✓" : "·"}</td><td>${esc(it.title)}</td><td style="text-align:right;white-space:nowrap">${it.size ? `${(it.size / 1048576).toFixed(0)} MB` : ""}</td></tr>`
    ).join("")}</tbody></table>`;
  }

  function bind() {
    document.getElementById("rssForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const url = document.getElementById("rssUrl").value.trim(); if (!url) return;
      const btn = e.target.querySelector("button[type=submit]"); btn.disabled = true;
      try {
        const r = await slow("rss_add", url, { include: document.getElementById("rssInc").value, exclude: document.getElementById("rssExc").value, backfill: +document.getElementById("rssBack").value || 0 });
        if (!r.ok) { toast(L("Akış okunamadı: ", "Feed failed: ") + (r.detail || r.error || ""), true); return; }
        document.getElementById("rssUrl").value = "";
        toast(L(`Eklendi: ${r.feed.title} (${r.items} girdi)`, `Added: ${r.feed.title} (${r.items} items)`));
        showPreview(r.preview); refresh();
      } finally { btn.disabled = false; }
    });
    document.getElementById("rssCheckAll").onclick = async () => { const r = await slow("rss_check", ""); toast(L(`${r.new || 0} yeni`, `${r.new || 0} new`)); refresh(); tick?.(); };
    document.getElementById("rssList").addEventListener("click", async (e) => {
      const b = e.target.closest("button[data-rss]"); if (!b) return;
      const f = R.list.find((x) => x.id === b.dataset.id); if (!f) return;
      const a = b.dataset.rss;
      if (a === "toggle") await api.rss_update(f.id, { enabled: !f.enabled });
      else if (a === "remove") { if (!confirm(L("Akış silinsin mi?", "Remove feed?"))) return; await api.rss_remove(f.id); }
      else if (a === "check") { b.disabled = true; const r = await slow("rss_check", f.id); toast(L(`${r.new || 0} yeni`, `${r.new || 0} new`)); tick?.(); }
      else if (a === "prev") { b.disabled = true; const r = await slow("rss_preview", f.id); b.disabled = false; showPreview(r.items); return; }
      else if (a === "edit") { R.editing = R.editing === f.id ? null : f.id; refresh(); return; }
      else if (a === "cancel") { R.editing = null; refresh(); return; }
      else if (a === "save") {
        const card = b.closest(".rss-card");
        const inc = card.querySelector("[data-rf=inc]").value;
        const exc = card.querySelector("[data-rf=exc]").value;
        const mx = +card.querySelector("[data-rf=max]").value || 0;
        await api.rss_update(f.id, { include: inc, exclude: exc, max_mb: mx });
        R.editing = null;
      }
      refresh();
    });
    document.getElementById("rssList").addEventListener("change", async (e) => {
      const s = e.target.closest("select[data-rss=queue]");
      if (s) { await api.rss_update(s.dataset.id, { queue: s.value }); refresh(); }
    });
  }

  window.kamiRssRefresh = refresh;
  window.addEventListener("pywebviewready", () => setTimeout(refresh, 900));
})();
