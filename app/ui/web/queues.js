/* Kami - Coklu kuyruk (IDM tarzi). Arac cubugunda rozet kartlar + sag tik menusu + kart yonetim penceresi.
   Arka uc: api.queue_list / queue_save / queue_assign / queue_run (app/core/queues.py). */
(function () {
  const Q = { list: [], filter: "", menu: null };
  const en = () => (document.documentElement.lang || "tr").startsWith("en");
  const L = (tr, e) => (en() ? e : tr);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const DAYS = () => (en() ? ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"] : ["Pt", "Sa", "Ça", "Pe", "Cu", "Ct", "Pz"]);

  window.kamiQueueName = (id) => Q.list.find((q) => q.id === id)?.name || id;
  window.kamiQueueFilter = (d) => !Q.filter || (Q.filter === "main" ? !d.extra?.queue : d.extra?.queue === Q.filter);

  const toMin = (hhmm) => {
    const m = /^(\d{1,2}):(\d{2})$/.exec(String(hhmm || ""));
    return m ? Math.min(1440, Math.max(0, +m[1] * 60 + +m[2])) : 0;
  };
  const toHHMM = (min) => {
    const m = Math.max(0, Math.min(1439, Math.round(min / 15) * 15));
    return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
  };

  const css = document.createElement("style");
  css.textContent = `
  .qbar{display:flex;gap:8px;align-items:stretch;flex-wrap:wrap;padding:0 0 10px}
  .qbar[hidden]{display:none}
  .qchip{border:1px solid var(--line);background:rgba(19,15,30,.92);color:var(--muted);border-radius:10px;padding:6px 10px;font:inherit;font-size:12px;cursor:pointer;display:inline-flex;gap:8px;align-items:center;transition:border-color .15s,background .15s,transform .1s}
  .qchip:hover{border-color:rgba(157,107,255,.55);color:var(--text)}
  .qchip:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
  .qchip.on{border-color:var(--accent);color:var(--text);background:rgba(157,107,255,.14);box-shadow:0 0 0 1px rgba(157,107,255,.25)}
  .qchip .qring{width:22px;height:22px;flex-shrink:0;display:grid;place-items:center;position:relative}
  .qchip .qring svg{transform:rotate(-90deg)}
  .qchip .qdot{width:7px;height:7px;border-radius:50%;background:var(--muted);flex-shrink:0}
  .qchip .qdot.run{background:#2EE6A6;box-shadow:0 0 8px #2EE6A6}
  .qchip .qdot.sch{background:#F5B94A;box-shadow:0 0 6px #F5B94A}
  .qchip .qmeta{display:flex;flex-direction:column;align-items:flex-start;line-height:1.2}
  .qchip .qmeta b{font-weight:600;color:var(--text)}
  .qchip .qmeta small{font-size:10.5px;color:var(--muted);display:flex;gap:6px;align-items:center}
  .qchip .qgo{margin-left:2px;width:24px;height:24px;border-radius:6px;display:inline-grid;place-items:center;background:rgba(157,107,255,.18);color:#EDE9F6;border:1px solid rgba(157,107,255,.35);font-size:11px;transition:background .12s}
  .qchip .qgo.run{background:rgba(46,230,166,.18);border-color:rgba(46,230,166,.45);color:#2EE6A6}
  .qchip .qgo:hover{background:var(--accent);color:#fff}
  #qMenu{position:fixed;z-index:9999;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:4px;min-width:190px;box-shadow:0 10px 30px #0008}
  #qMenu button{display:block;width:100%;text-align:left;background:none;border:0;color:var(--text);padding:7px 10px;border-radius:6px;font:inherit;cursor:pointer}
  #qMenu button:hover,#qMenu button:focus-visible{background:var(--accent-soft);outline:none}#qMenu .sep{height:1px;background:var(--line);margin:4px 0}
  #qMenu .hd{font-size:11px;color:var(--muted);padding:6px 10px 2px}
  #qDlg{width:min(760px,94vw)}
  #qDlg .qrow{background:rgba(20,16,32,.85);border:1px solid var(--line);border-radius:10px;padding:12px;margin-bottom:10px;display:grid;gap:10px}
  #qDlg .qtop{display:grid;grid-template-columns:1.5fr .7fr .9fr .9fr auto;gap:8px;align-items:end}
  #qDlg .qsched{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center;padding-top:6px;border-top:1px solid rgba(255,255,255,.06)}
  #qDlg input,#qDlg select{width:100%;box-sizing:border-box}
  #qDlg .qdays{display:flex;gap:4px}
  #qDlg .qdays label{position:relative;cursor:pointer}
  #qDlg .qdays input{position:absolute;opacity:0;pointer-events:none}
  #qDlg .qdays span{width:28px;height:28px;border-radius:50%;border:1px solid var(--line);display:grid;place-items:center;font-size:11px;color:var(--muted);transition:all .12s}
  #qDlg .qdays input:checked + span{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
  #qDlg .qdays input:focus-visible + span{outline:2px solid var(--accent);outline-offset:2px}
  #qDlg .qband{position:relative;height:22px;background:#0B0812;border:1px solid var(--line);border-radius:6px;cursor:pointer;user-select:none;overflow:hidden}
  #qDlg .qband-fill{position:absolute;top:2px;bottom:2px;background:linear-gradient(90deg,#7C3AED,#2EE6A6);border-radius:4px;opacity:.85}
  #qDlg .qband-lbl{position:relative;z-index:1;display:flex;justify-content:space-between;padding:0 8px;font-size:10.5px;line-height:20px;color:#EDE9F6;pointer-events:none}
  #qDlg .qtime{display:flex;gap:6px;margin-top:4px}
  #qDlg small{color:var(--muted);display:block;font-size:11px;margin-bottom:2px}`;
  document.head.appendChild(css);

  async function refresh() {
    try { Q.list = (await api.queue_list?.()) || []; } catch { Q.list = []; }
    if (Q.filter && Q.filter !== "main" && !Q.list.some((q) => q.id === Q.filter)) Q.filter = "";
    drawBar();
  }

  function ringSvg(done, total, running) {
    const pct = total > 0 ? Math.min(1, done / total) : 0;
    const c = 2 * Math.PI * 8.5;
    const stroke = running ? "#2EE6A6" : "#9D6BFF";
    return `<span class="qring" aria-hidden="true"><svg width="22" height="22" viewBox="0 0 22 22"><circle cx="11" cy="11" r="8.5" fill="none" stroke="rgba(255,255,255,.12)" stroke-width="2.5"/><circle cx="11" cy="11" r="8.5" fill="none" stroke="${stroke}" stroke-width="2.5" stroke-dasharray="${c.toFixed(1)}" stroke-dashoffset="${(c * (1 - pct)).toFixed(1)}" stroke-linecap="round"/></svg></span>`;
  }

  function drawBar() {
    let bar = document.getElementById("qBar");
    const list = document.getElementById("list");
    if (!list) return;
    if (!bar) { bar = document.createElement("div"); bar.id = "qBar"; bar.className = "qbar"; list.parentNode.insertBefore(bar, document.getElementById("liveList") || list); }
    bar.hidden = !Q.list.length;
    const chip = (id, name, q) => {
      if (!q) return `<button type="button" class="qchip ${Q.filter === id ? "on" : ""}" data-qf="${esc(id)}"><b>${esc(name)}</b></button>`;
      const sched = q.start && q.stop;
      const dotCls = q.running ? "run" : sched ? "sch" : "";
      const stTxt = q.running ? L("Çalışıyor", "Running") : sched ? `${q.start}–${q.stop}` : L("Bekliyor", "Idle");
      return `<button type="button" class="qchip ${Q.filter === id ? "on" : ""}" data-qf="${esc(id)}" aria-label="${esc(name)} (${q.done}/${q.total})">
        ${ringSvg(q.done, q.total, q.running)}
        <span class="qmeta">
          <b><i class="qdot ${dotCls}" style="display:inline-block;margin-right:5px"></i>${esc(name)}</b>
          <small><span>${q.done}/${q.total}</span><span>· ${esc(stTxt)}</span>${q.limit_kib > 0 ? `<span>· ⚡${q.limit_kib}K</span>` : ""}</small>
        </span>
        <span class="qgo ${q.running ? "run" : ""}" role="button" tabindex="0" data-qrun="${esc(q.id)}" title="${q.running ? L("Durdur", "Stop") : L("Başlat", "Start")}" aria-label="${q.running ? L("Durdur", "Stop") : L("Başlat", "Start")}">${q.running ? "⏸" : "▶"}</span>
      </button>`;
    };
    bar.innerHTML = chip("", L("Tümü", "All")) + chip("main", L("Ana kuyruk", "Main queue")) +
      Q.list.map((q) => chip(q.id, q.name, q)).join("") +
      `<button type="button" class="qchip" data-qmanage title="${L("Kuyrukları yönet", "Manage queues")}">⚙ <b>${L("Kuyruklar", "Queues")}</b></button>`;
  }

  document.addEventListener("click", async (e) => {
    const run = e.target.closest("[data-qrun]");
    if (run) { e.stopPropagation(); const q = Q.list.find((x) => x.id === run.dataset.qrun); const r = await api.queue_run(q.id, !q.running); Q.list = r.queues || Q.list; drawBar(); return; }
    const f = e.target.closest("[data-qf]");
    if (f) { Q.filter = f.dataset.qf; drawBar(); window.render?.(); return; }
    if (e.target.closest("[data-qmanage]")) { openDlg(); return; }
    if (Q.menu && !Q.menu.contains(e.target)) closeMenu();
  });

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

  function syncBand(row) {
    const sEl = row.querySelector("[data-k=start]"), eEl = row.querySelector("[data-k=stop]"), fill = row.querySelector(".qband-fill"), lbl = row.querySelector(".qband-txt");
    if (!sEl || !eEl || !fill) return;
    const s = sEl.value ? toMin(sEl.value) : 0, e = eEl.value ? toMin(eEl.value) : 0;
    if (sEl.value && eEl.value) {
      const l = Math.min(s, e) / 1440 * 100, w = Math.max(2, Math.abs(e - s) / 1440 * 100);
      fill.style.left = l + "%"; fill.style.width = w + "%"; fill.hidden = false;
      if (lbl) lbl.textContent = `${sEl.value} – ${eEl.value}`;
    } else {
      fill.hidden = true;
      if (lbl) lbl.textContent = L("Elle (sürükleyip saat seç)", "Manual (drag to set hours)");
    }
  }

  function openDlg() {
    let d = document.getElementById("qDlg");
    if (!d) { d = document.createElement("dialog"); d.id = "qDlg"; document.body.appendChild(d); }
    const rows = (Q.list.length ? Q.list : []).map((q, i) => `
      <div class="qrow" data-i="${i}">
        <div class="qtop">
          <div><small>${L("Kuyruk adı", "Queue name")} (${q.done || 0}/${q.total || 0})</small><input data-k="name" value="${esc(q.name)}"></div>
          <div><small>${L("Aynı anda", "Parallel")}</small><input data-k="max_active" type="number" min="1" max="16" value="${q.max_active}"></div>
          <div><small>${L("Hız KB/s (0=∞)", "Speed KB/s")}</small><input data-k="limit_kib" type="number" min="0" value="${q.limit_kib}"></div>
          <div><small>${L("Bitince", "When done")}</small><select data-k="on_done"><option value="">—</option><option value="notify" ${q.on_done === "notify" ? "selected" : ""}>${L("Bildir", "Notify")}</option><option value="shutdown" ${q.on_done === "shutdown" ? "selected" : ""}>${L("PC'yi kapat", "Shut down")}</option></select></div>
          <button type="button" class="btn ghost" data-del="${i}" title="${L("Sil (işleri ana kuyruğa döner)", "Delete (jobs return to main)")}" aria-label="${L("Kuyruğu sil", "Delete queue")}">✕</button>
        </div>
        <div class="qsched">
          <div>
            <div class="qband" title="${L("Saat aralığı seçmek için sürükle", "Drag to select schedule window")}"><div class="qband-fill"></div><div class="qband-lbl"><span>00:00</span><span class="qband-txt"></span><span>24:00</span></div></div>
            <div class="qtime"><input data-k="start" type="time" value="${q.start}" aria-label="${L("Başlangıç saati", "Start time")}"><input data-k="stop" type="time" value="${q.stop}" aria-label="${L("Bitiş saati", "Stop time")}"></div>
          </div>
          <div class="qdays" aria-label="${L("Günler", "Days")}">${DAYS().map((n, di) => `<label><input type="checkbox" data-day="${di}" ${q.days.includes(di) ? "checked" : ""}><span>${n}</span></label>`).join("")}</div>
        </div>
      </div>`).join("");
    d.innerHTML = `<h2>${L("Kuyruklar", "Queues")}</h2>
      <p><small>${L("Ana kuyruk her zamanki gibi çalışır. Adlı kuyruklar kendi sırası, aynı anda sınırı, hız sınırı ve saat aralığıyla ayrı çalışır. Gün seçilmezse her gün.", "Main queue works as usual. Named queues run with independent parallel limits, speed caps and schedules. No day = every day.")}</small></p>
      <div id="qRows">${rows || `<p><small>${L("Henüz kuyruk yok.", "No queues yet.")}</small></p>`}</div>
      <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:12px">
        <button type="button" class="btn ghost" id="qAdd">＋ ${L("Yeni kuyruk", "New queue")}</button><span style="flex:1"></span>
        <button type="button" class="btn ghost" id="qCancel">${L("Kapat", "Close")}</button><button type="button" class="btn" id="qSave">${L("Kaydet", "Save")}</button></div>`;
    d.querySelectorAll(".qrow").forEach((row) => {
      syncBand(row);
      row.querySelectorAll("[data-k=start],[data-k=stop]").forEach((el) => el.addEventListener("input", () => syncBand(row)));
      const band = row.querySelector(".qband");
      band.onpointerdown = (ev) => {
        const r = band.getBoundingClientRect();
        const pctAt = (x) => Math.min(1, Math.max(0, (x - r.left) / r.width));
        const m0 = pctAt(ev.clientX) * 1440;
        band.setPointerCapture(ev.pointerId);
        const mv = (e2) => {
          const m1 = pctAt(e2.clientX) * 1440;
          row.querySelector("[data-k=start]").value = toHHMM(Math.min(m0, m1));
          row.querySelector("[data-k=stop]").value = toHHMM(Math.max(m0 + 30, m1));
          syncBand(row);
        };
        const up = () => { band.onpointermove = null; band.onpointerup = null; };
        band.onpointermove = mv; band.onpointerup = up;
      };
    });
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
