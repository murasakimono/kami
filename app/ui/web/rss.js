/* Kami v1.29 - RSS otomatik indirme: Takip gorunumunun altinda "RSS akislari" bolumu.
   Torrent akislari (nyaa, tracker RSS, showRSS) ve podcast'ler; filtre, akilli bolum, kuyruk. Arka uc app/core/rss.py */
(function () {
  const en = () => (document.documentElement.lang || "tr").startsWith("en");
  const L = (tr, e) => (en() ? e : tr);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const R = { list: [], queues: [] };
  const ago = (ts) => { if (!ts) return "—"; const m = Math.round((Date.now() / 1000 - ts) / 60); return m < 60 ? `${m} ${L("dk", "min")}` : `${Math.round(m / 60)} ${L("sa", "h")}`; };

  function mount() {
    const view = document.getElementById("followView");
    if (!view || document.getElementById("rssSec")) return;
    const sec = document.createElement("div");
    sec.id = "rssSec"; sec.style.marginTop = "22px";
    sec.innerHTML = `
      <div class="rd-head"><h2>${L("RSS akışları", "RSS feeds")}</h2><span class="hint">${L("Torrent akışı ya da podcast: yeni çıkan, filtrene uyan otomatik iner. Aynı bölümün başka kalitesi tekrar inmez.", "Torrent feed or podcast: new items matching your filter download automatically. Other qualities of the same episode are skipped.")}</span><span class="spacer"></span>
        <button type="button" class="btn ghost" id="rssCheckAll">${L("Hepsini şimdi yokla", "Check all now")}</button></div>
      <form class="fw-add" id="rssForm" autocomplete="off" style="flex-wrap:wrap">
        <input id="rssUrl" type="text" spellcheck="false" placeholder="https://nyaa.si/?page=rss&q=… / podcast RSS" style="flex:2;min-width:260px">
        <input id="rssInc" type="text" placeholder="${L("İçersin (ör. 1080p, dizi adı ya da /regex/)", "Include (e.g. 1080p, show name or /regex/)")}" style="flex:1;min-width:180px">
        <input id="rssExc" type="text" placeholder="${L("İçermesin (ör. 720p, batch)", "Exclude (e.g. 720p, batch)")}" style="flex:1;min-width:140px">
        <label class="tb-conc"><span>${L("Geriye", "Backfill")}</span><input id="rssBack" type="number" min="0" max="30" value="0"></label>
        <button type="submit" class="btn primary">${L("Ekle", "Add")}</button>
      </form>
      <ul class="rd-list" id="rssList"></ul>
      <p class="hint" id="rssEmpty" hidden>${L("Henüz RSS akışı yok.", "No RSS feeds yet.")}</p>
      <div id="rssPrev" class="hint" style="white-space:pre-wrap;max-height:220px;overflow:auto"></div>`;
    view.appendChild(sec);
    bind();
  }

  async function refresh() {
    mount();
    try { [R.list, R.queues] = await Promise.all([api.rss_list(), api.queue_list?.() || []]); } catch { return; }
    const ul = document.getElementById("rssList"); if (!ul) return;
    document.getElementById("rssEmpty").hidden = R.list.length > 0;
    const qopt = (f) => `<select data-rss="queue" data-id="${f.id}"><option value="">${L("Ana kuyruk", "Main queue")}</option>` +
      R.queues.map((q) => `<option value="${esc(q.id)}"${f.queue === q.id ? " selected" : ""}>⧉ ${esc(q.name)}</option>`).join("") + `</select>`;
    ul.innerHTML = R.list.map((f) => rdRow(f.title || f.url,
      `<span>${L("filtre", "filter")}: ${esc(f.include || "—")}${f.exclude ? " / −" + esc(f.exclude) : ""}</span><span>${L("son", "last")}: ${ago(f.last)}</span>` +
      (f.last_new ? `<span>${L("son yeni", "last new")}: ${ago(f.last_new)}</span>` : "") + (f.error ? `<span class="st-error">${esc(f.error.slice(0, 80))}</span>` : ""),
      qopt(f) +
      `<button type="button" class="btn ghost" data-rss="edit" data-id="${f.id}">${L("Filtre", "Filter")}</button>` +
      `<button type="button" class="btn ghost" data-rss="prev" data-id="${f.id}">${L("Önizle", "Preview")}</button>` +
      `<button type="button" class="btn ghost" data-rss="toggle" data-id="${f.id}">${f.enabled ? L("Açık", "On") : L("Kapalı", "Off")}</button>` +
      `<button type="button" class="btn ghost" data-rss="check" data-id="${f.id}">${L("Yokla", "Check")}</button>` +
      `<button type="button" class="btn ghost danger" data-rss="remove" data-id="${f.id}">✕</button>`)).join("");
  }

  function showPreview(items) {
    document.getElementById("rssPrev").textContent = (items || []).map((it) =>
      `${it.match ? "✓" : "·"} ${it.title}${it.size ? `  (${(it.size / 1048576).toFixed(0)} MB)` : ""}`).join("\n");
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
      else if (a === "edit") {
        const inc = prompt(L("İçersin (virgülle ya da /regex/)", "Include (comma or /regex/)"), f.include || ""); if (inc === null) return;
        const exc = prompt(L("İçermesin", "Exclude"), f.exclude || ""); if (exc === null) return;
        const mx = prompt(L("En büyük boyut MB (0 = sınırsız)", "Max size MB (0 = no limit)"), f.max_mb || 0); if (mx === null) return;
        await api.rss_update(f.id, { include: inc, exclude: exc, max_mb: +mx || 0 });
      }
      refresh();
    });
    document.getElementById("rssList").addEventListener("change", async (e) => {
      const s = e.target.closest("select[data-rss=queue]");
      if (s) { await api.rss_update(s.dataset.id, { queue: s.value }); refresh(); }
    });
  }

  const prev = VIEW_OPEN.follow;
  VIEW_OPEN.follow = async () => { if (prev) await prev(); refresh(); };
})();
