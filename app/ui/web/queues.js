/* Kami v1.29 - Coklu kuyruk (IDM tarzi). Arac cubugunda "Kuyruklar" dugmesi + filtre cipleri,
   listede sag tik / coklu secim -> "Kuyruga tasi", kuyruk yonetimi penceresi.
   Arka uc: api.queue_list / queue_save / queue_assign / queue_run (app/core/queues.py). */
(function () {
  const Q = { list: [], filter: "", menu: null };
  const en = () => (document.documentElement.lang || "tr").startsWith("en");
  const L = (tr, e) => (en() ? e : tr);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const DAYS = () => (en() ? ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"] : ["Pt", "Sa", "Ça", "Pe", "Cu", "Ct", "Pz"]);

  window.kamiQueueName = (id) => Q.list.find((q) => q.id === id)?.name || id;
  window.kamiQueueFilter = (d) => !Q.filter || (Q.filter === "main" ? !d.extra?.queue : d.extra?.queue === Q.filter);

  const css = document.createElement("style");
  css.textContent = `
  .qbar{display:flex;gap:6px;align-items:center;flex-wrap:wrap;padding:0 0 8px}
  .qbar[hidden]{display:none}
  .qchip{border:1px solid var(--line);background:var(--raised);color:var(--muted);border-radius:999px;padding:4px 10px;font:inherit;font-size:12px;cursor:pointer;display:inline-flex;gap:6px;align-items:center}
  .qchip.on{border-color:var(--accent);color:var(--text);background:var(--accent-soft)}
  .qchip .qdot{width:7px;height:7px;border-radius:50%;background:var(--muted)}
  .qchip .qdot.run{background:var(--ok);box-shadow:0 0 6px var(--ok)}
  .qchip .qgo{margin-left:2px;color:var(--accent-2)}
  .qbadge{color:var(--accent-2)}.qbadge.hold{color:var(--muted)}
  #qMenu{position:fixed;z-index:9999;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:4px;min-width:190px;box-shadow:0 10px 30px #0008}
  #qMenu button{display:block;width:100%;text-align:left;background:none;border:0;color:var(--text);padding:7px 10px;border-radius:6px;font:inherit;cursor:pointer}
  #qMenu button:hover{background:var(--accent-soft)}#qMenu .sep{height:1px;background:var(--line);margin:4px 0}
  #qMenu .hd{font-size:11px;color:var(--muted);padding:6px 10px 2px}
  #qDlg{width:min(720px,94vw)}#qDlg .qrow{display:grid;grid-template-columns:1.4fr .6fr .8fr 1.6fr 1fr auto;gap:8px;align-items:center;padding:8px 0;border-bottom:1px solid var(--line)}
  #qDlg input,#qDlg select{width:100%;box-sizing:border-box}#qDlg .qdays{display:flex;gap:2px}#qDlg .qdays label{font-size:11px;display:flex;flex-direction:column;align-items:center}
  #qDlg .qtime{display:flex;gap:4px}#qDlg small{color:var(--muted)}`;
  document.head.appendChild(css);

  async function refresh() {
    try { Q.list = (await api.queue_list?.()) || []; } catch { Q.list = []; }
    if (Q.filter && Q.filter !== "main" && !Q.list.some((q) => q.id === Q.filter)) Q.filter = "";
    drawBar();
  }

  function drawBar() {
    let bar = document.getElementById("qBar");
    const list = document.getElementById("list");
    if (!list) return;
    if (!bar) { bar = document.createElement("div"); bar.id = "qBar"; bar.className = "qbar"; list.parentNode.insertBefore(bar, document.getElementById("liveList") || list); }
    bar.hidden = !Q.list.length;
    const chip = (id, name, q) => `<button class="qchip ${Q.filter === id ? "on" : ""}" data-qf="${esc(id)}">` +
      (q ? `<i class="qdot ${q.running ? "run" : ""}"></i>` : "") + esc(name) +
      (q ? ` <small>${q.done}/${q.total}</small><span class="qgo" data-qrun="${esc(q.id)}" title="${q.running ? L("Durdur", "Stop") : L("Başlat", "Start")}">${q.running ? "⏸" : "▶"}</span>` : "") + `</button>`;
    bar.innerHTML = chip("", L("Tümü", "All")) + chip("main", L("Ana kuyruk", "Main queue")) +
      Q.list.map((q) => chip(q.id, q.name, q)).join("") +
      `<button class="qchip" data-qmanage>⚙ ${L("Kuyruklar", "Queues")}</button>`;
  }

  document.addEventListener("click", async (e) => {
    const run = e.target.closest("[data-qrun]");
    if (run) { e.stopPropagation(); const q = Q.list.find((x) => x.id === run.dataset.qrun); const r = await api.queue_run(q.id, !q.running); Q.list = r.queues || Q.list; drawBar(); return; }
    const f = e.target.closest("[data-qf]");
    if (f) { Q.filter = f.dataset.qf; drawBar(); window.render?.(); return; }
    if (e.target.closest("[data-qmanage]")) { openDlg(); return; }
    if (Q.menu && !Q.menu.contains(e.target)) closeMenu();
  });

  // ---- sag tik: kuyruga tasi (secili ogeler varsa hepsi; yoksa tiklanan)
  function selectedIds(li) {
    const sel = [...document.querySelectorAll("#list .item.selected, #list .item.sel")].map((x) => +x.dataset.id);
    return sel.length && sel.includes(+li.dataset.id) ? sel : [+li.dataset.id];
  }
  function closeMenu() { Q.menu?.remove(); Q.menu = null; }
  document.addEventListener("contextmenu", (e) => {
    const li = e.target.closest("#list .item");
    if (!li || e.target.closest("input,textarea")) return;
    e.preventDefault(); closeMenu();
    const ids = selectedIds(li);
    const m = document.createElement("div"); m.id = "qMenu";
    m.innerHTML = `<div class="hd">${L("Kuyruğa taşı", "Move to queue")}${ids.length > 1 ? ` (${ids.length})` : ""}</div>` +
      `<button data-qa="main">${L("Ana kuyruk", "Main queue")}</button>` +
      Q.list.map((q) => `<button data-qa="${esc(q.id)}">⧉ ${esc(q.name)}</button>`).join("") +
      `<div class="sep"></div><button data-qa="__new">＋ ${L("Yeni kuyruk…", "New queue…")}</button>`;
    document.body.appendChild(m); Q.menu = m;
    const r = m.getBoundingClientRect();
    m.style.left = Math.min(e.clientX, innerWidth - r.width - 6) + "px";
    m.style.top = Math.min(e.clientY, innerHeight - r.height - 6) + "px";
    m.onclick = async (ev) => {
      const b = ev.target.closest("[data-qa]"); if (!b) return;
      let qid = b.dataset.qa; closeMenu();
      if (qid === "__new") {
        const name = prompt(L("Kuyruk adı", "Queue name"), L("Gece", "Night")); if (!name) return;
        const before = new Set(Q.list.map((q) => q.id));
        Q.list = await api.queue_save([...Q.list, { name, max_active: 2 }]);
        qid = Q.list.find((q) => !before.has(q.id))?.id; if (!qid) return;
      }
      await api.queue_assign(ids, qid); await refresh(); window.tick?.();
    };
  }, true);
  window.addEventListener("blur", closeMenu);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMenu(); });

  // ---- yonetim penceresi
  function openDlg() {
    let d = document.getElementById("qDlg");
    if (!d) { d = document.createElement("dialog"); d.id = "qDlg"; document.body.appendChild(d); }
    const rows = (Q.list.length ? Q.list : []).map((q, i) => `
      <div class="qrow" data-i="${i}">
        <div><input data-k="name" value="${esc(q.name)}"><small>${q.total} ${L("iş", "jobs")} · ${q.active} ${L("inen", "active")} · ${q.waiting} ${L("sırada", "queued")}</small></div>
        <div><small>${L("Aynı anda", "Parallel")}</small><input data-k="max_active" type="number" min="1" max="16" value="${q.max_active}"></div>
        <div><small>${L("Hız KB/s (0=∞)", "Speed KB/s (0=∞)")}</small><input data-k="limit_kib" type="number" min="0" value="${q.limit_kib}"></div>
        <div><small>${L("Saat (boş = elle)", "Hours (empty = manual)")}</small><div class="qtime"><input data-k="start" type="time" value="${q.start}"><input data-k="stop" type="time" value="${q.stop}"></div>
          <div class="qdays">${DAYS().map((n, di) => `<label>${n}<input type="checkbox" data-day="${di}" ${q.days.includes(di) ? "checked" : ""}></label>`).join("")}</div></div>
        <div><small>${L("Bitince", "When done")}</small><select data-k="on_done"><option value="">—</option><option value="notify" ${q.on_done === "notify" ? "selected" : ""}>${L("Bildir", "Notify")}</option><option value="shutdown" ${q.on_done === "shutdown" ? "selected" : ""}>${L("PC'yi kapat", "Shut down")}</option></select></div>
        <button class="btn ghost" data-del="${i}" title="${L("Sil (işleri ana kuyruğa döner)", "Delete (jobs return to main)")}">✕</button>
      </div>`).join("");
    d.innerHTML = `<h2>${L("Kuyruklar", "Queues")}</h2>
      <p><small>${L("Ana kuyruk her zamanki gibi çalışır. Adlı kuyruklar kendi sırası, aynı anda sınırı, hız sınırı ve saat aralığıyla ayrı çalışır; bir işi sağ tıklayıp kuyruğa taşı. Gün seçilmezse her gün.", "The main queue works as usual. Named queues run on their own order, parallel limit, speed cap and schedule; right-click a job to move it. No day selected = every day.")}</small></p>
      <div id="qRows">${rows || `<p><small>${L("Henüz kuyruk yok.", "No queues yet.")}</small></p>`}</div>
      <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:12px">
        <button class="btn ghost" id="qAdd">＋ ${L("Yeni kuyruk", "New queue")}</button><span style="flex:1"></span>
        <button class="btn ghost" id="qCancel">${L("Kapat", "Close")}</button><button class="btn" id="qSave">${L("Kaydet", "Save")}</button></div>`;
    const collect = () => [...d.querySelectorAll(".qrow")].map((row) => {
      const q = { ...Q.list[+row.dataset.i] };
      row.querySelectorAll("[data-k]").forEach((el) => { q[el.dataset.k] = el.type === "number" ? +el.value : el.value; });
      q.days = [...row.querySelectorAll("[data-day]:checked")].map((x) => +x.dataset.day);
      return q;
    });
    d.querySelector("#qAdd").onclick = () => { Q.list = [...collect(), { id: "", name: L("Yeni kuyruk", "New queue"), max_active: 2, limit_kib: 0, start: "", stop: "", days: [], on_done: "", total: 0, active: 0, waiting: 0 }]; openDlg(); };
    d.querySelectorAll("[data-del]").forEach((b) => b.onclick = () => { const all = collect(); all.splice(+b.dataset.del, 1); Q.list = all; openDlg(); });
    d.querySelector("#qCancel").onclick = () => { d.close(); refresh(); };
    d.querySelector("#qSave").onclick = async () => { Q.list = await api.queue_save(collect()); drawBar(); d.close(); window.tick?.(); };
    if (!d.open) d.showModal();
  }

  const start = () => { refresh(); setInterval(refresh, 3000); };
  window.addEventListener("pywebviewready", () => setTimeout(start, 500));
})();
