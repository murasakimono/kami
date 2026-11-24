"use strict";
/* Kami Beat Asama 1e: Beat rafi (lisans takibi) + Fikir rafi (kisa sesli notlar).
   beat.js init sirasinda BeatLibrary.init(ctx) cagirir; proje durumunu degistiren isler ctx.serverMutate ile
   (tek geri al adimi) yapilir. Derlemesiz duz JS. */
(function (root) {
  const LIC_SHORT = { free_profit: "Ücretsiz · ticari", credit_required: "Kredi zorunlu", free_nonprofit: "Kâr amaçsız",
    lease_required: "Lisans gerekli", unknown: "Lisans ?" };
  const LIC_LONG = { free_profit: "Ücretsiz · ticari dahil", credit_required: "Ücretsiz · kredi zorunlu",
    free_nonprofit: "Ücretsiz · yalnız kâr amacı gütmeyen", lease_required: "Lisans gerekli (lease / satın al)", unknown: "Bilinmiyor" };
  const QUICK_MAX = 30;
  const MT_SHELF = "application/x-kami-shelf", MT_IDEA = "application/x-kami-idea";

  function init(ctx) {
    const { $, esc } = ctx;
    const api = () => ctx.api();
    const fmt = (s) => { s = Math.max(0, Number(s) || 0); return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`; };
    let SHELF = [], EDIT = "", IDEAS = [], LINES = {}, IREC = null, IEDIT = "";
    let shelfT = 0, ideaT = 0;

    // ---------------- Beat rafi ----------------
    function shelfFilters() {
      return [$("#shelfQ").value.trim(), +$("#shelfBpmMin").value || 0, +$("#shelfBpmMax").value || 0,
        $("#shelfKey").value.trim(), $("#shelfLic").value];
    }
    async function refreshShelf() {
      const r = await api()?.beat_shelf_list?.(...shelfFilters()).catch(() => null);
      SHELF = r?.items || [];
      renderShelf();
    }
    function licChip(it) {
      const L = it.license || {};
      const k = L.kind || "unknown";
      const tip = `${LIC_LONG[k]}${L.guessed ? " — açıklamadan TAHMİN (tıkla: düzelt)" : L.user_set ? " — elle düzeltildi" : ""}`;
      return `<span class="kb-lic ${esc(k)} ${L.guessed ? "guess" : ""}" data-sedit="${esc(it.id)}" title="${esc(tip)}">${LIC_SHORT[k]}</span>`;
    }
    function shelfEditForm(it) {
      const L = it.license || {};
      const opts = Object.keys(LIC_LONG).map((k) => `<option value="${k}" ${L.kind === k ? "selected" : ""}>${LIC_LONG[k]}</option>`).join("");
      return `<div class="kb-card-edit" data-sform="${esc(it.id)}">
        <input class="wide" data-f="title" value="${esc(it.title)}" placeholder="Başlık">
        <input data-f="producer" value="${esc(it.producer)}" placeholder="Yapımcı">
        <input data-f="credit" value="${esc(L.credit_text || "")}" placeholder="Kredi metni (prod. by …)">
        <input data-f="bpm" type="number" min="0" max="300" step="0.1" value="${it.bpm || ""}" placeholder="BPM">
        <input data-f="key" value="${esc(it.key || "")}" maxlength="4" placeholder="Ton">
        <select class="wide" data-f="kind">${opts}</select>
        <textarea class="wide" data-f="note" rows="2" placeholder="Not">${esc(it.note || "")}</textarea>
        <div class="kb-pop-btns wide"><button type="button" class="btn ok" data-ssave="${esc(it.id)}">Kaydet</button><button type="button" class="btn" data-scancel="1">Vazgeç</button></div>
      </div>`;
    }
    function renderShelf() {
      $("#shelfCount").textContent = String(SHELF.length);
      $("#shelfList").innerHTML = SHELF.map((it) => {
        const L = it.license || {};
        const meta = [it.producer ? esc(it.producer) : "", it.bpm ? `${Math.round(it.bpm)} BPM` : "", it.key ? esc(it.key) : "",
          it.duration ? fmt(it.duration) : ""].filter(Boolean).join(" · ");
        return `<div class="kb-card ${it.exists ? "" : "missing"}" draggable="${it.exists ? "true" : "false"}" data-shelf="${esc(it.id)}">
          <div class="kb-card-top"><b title="${esc(it.title)}">${esc(it.title || "Beat")}</b>
            <button type="button" class="btn ic" data-splay="${esc(it.id)}" title="Dinle" ${it.exists ? "" : "disabled"}>▶</button></div>
          <div class="kb-card-meta">${meta}${meta ? " · " : ""}${licChip(it)}</div>
          ${L.evidence?.length && L.guessed ? `<div class="kb-card-ev" title="${esc(L.evidence.join(" | "))}">“${esc(L.evidence[0])}”</div>` : ""}
          ${it.note ? `<div class="kb-card-meta">${esc(it.note)}</div>` : ""}
          ${EDIT === it.id ? shelfEditForm(it) : `<div class="kb-card-btns">
            <button type="button" class="btn ok" data-sadd="${esc(it.id)}" ${it.exists ? "" : "disabled"} title="Beat kanalına klip olarak ekle (kanal doluysa sonuna)">Projeye ekle</button>
            <button type="button" class="btn" data-sedit="${esc(it.id)}">Düzenle</button>
            ${L.credit_text ? `<button type="button" class="btn" data-scopy="${esc(it.id)}" title="${esc(L.credit_text)}">Krediyi kopyala</button>` : ""}
            <button type="button" class="btn ic" data-sdel="${esc(it.id)}" title="Raftan kaldır">🗑</button></div>`}
        </div>`;
      }).join("") || `<div class="kb-mut">Raf boş. Bir YouTube beat bağlantısı yapıştırıp “İndir”e bas.</div>`;
    }
    async function addToProject(id, t) {
      const P = ctx.getProj();
      if (!P) return;
      const it = SHELF.find((x) => x.id === id);
      ctx.setStatus("Beat projeye ekleniyor (BPM/ton analizi)…");
      const r = await ctx.serverMutate(`✓ Beat eklendi: ${it?.title || ""} — lisans: ${LIC_LONG[it?.license?.kind || "unknown"]}`,
        () => ctx.runJob("beat_shelf_to_project", [P.id, id, t == null ? -1 : t]));
      if (r?.ok) ctx.onBeatAdded?.();
      if (!r?.ok) ctx.setStatus("Beat eklenemedi: " + ({ file_missing: "dosya bulunamadı", not_found: "raf öğesi yok" }[r?.error] || r?.error || "?"));
    }
    async function copyText(txt) {
      let ok = false;
      try { await navigator.clipboard.writeText(txt); ok = true; } catch {}
      if (!ok) ok = !!(await api()?.copy_text?.(txt).catch(() => false));
      ctx.setStatus(ok ? `Kopyalandı: ${txt}` : "Kopyalanamadı");
      return ok;
    }
    $("#shelfList").addEventListener("click", async (e) => {
      const b = e.target.closest("[data-splay],[data-sadd],[data-sedit],[data-sdel],[data-ssave],[data-scancel],[data-scopy]");
      if (!b) return;
      const d = b.dataset;
      if (d.splay) { const it = SHELF.find((x) => x.id === d.splay); if (it) ctx.playPath(it.file, it.title); }
      else if (d.sadd) addToProject(d.sadd, null);
      else if (d.sedit) { EDIT = EDIT === d.sedit ? "" : d.sedit; renderShelf(); }
      else if (d.scancel) { EDIT = ""; renderShelf(); }
      else if (d.scopy) { const it = SHELF.find((x) => x.id === d.scopy); if (it) copyText(it.license?.credit_text || ""); }
      else if (d.sdel) {
        const it = SHELF.find((x) => x.id === d.sdel);
        if (!confirm(`“${it?.title || "Beat"}” raftan kaldırılsın mı? (Dosya diskte kalır; projelerdeki klipler çalmaya devam eder.)`)) return;
        await api()?.beat_shelf_remove?.(d.sdel, false).catch(() => null);
        refreshShelf();
      } else if (d.ssave) {
        const f = $(`[data-sform="${CSS.escape(d.ssave)}"]`);
        const v = (k) => f.querySelector(`[data-f="${k}"]`).value;
        const r = await api()?.beat_shelf_update?.(d.ssave, { title: v("title"), producer: v("producer"), bpm: +v("bpm") || 0,
          key: v("key"), note: v("note"), license: { kind: v("kind"), credit_text: v("credit") } }).catch(() => null);
        EDIT = "";
        if (r?.ok) ctx.setStatus("Raf öğesi güncellendi (lisans elle düzeltildi).");
        refreshShelf();
      }
    });
    $("#shelfList").addEventListener("dragstart", (e) => {
      const c = e.target.closest(".kb-card[data-shelf]");
      if (!c) return;
      e.dataTransfer.effectAllowed = "copy";
      try { e.dataTransfer.setData(MT_SHELF, c.dataset.shelf); e.dataTransfer.setData("text/plain", "kami-shelf:" + c.dataset.shelf); } catch {}
    });
    for (const id of ["#shelfQ", "#shelfBpmMin", "#shelfBpmMax", "#shelfKey"]) {
      $(id).addEventListener("input", () => { clearTimeout(shelfT); shelfT = setTimeout(refreshShelf, 250); });
    }
    $("#shelfLic").onchange = refreshShelf;
    let DL = false;
    async function download() {
      const url = $("#shelfUrl").value.trim();
      if (!/^https?:\/\//i.test(url)) { ctx.setStatus("Geçerli bir bağlantı yapıştır (https://…)."); return; }
      if (DL) return;
      DL = true;
      $("#shelfGet").disabled = true;
      $("#shelfProg").hidden = false;
      const lbl = { info: "Bilgi alınıyor…", download: "İndiriliyor (yalnız ses)…", convert: "Dönüştürülüyor…", analyze: "BPM / ton…" };
      try {
        const r = await ctx.runJob("beat_shelf_add_url", [url], async () => {
          const p = await api()?.beat_shelf_progress?.().catch(() => null);
          if (!p) return;
          $("#shelfProgBar").style.width = `${p.pct || 0}%`;
          $("#shelfProgTxt").textContent = `${lbl[p.phase] || "…"}${p.title ? " · " + p.title : ""}`;
        });
        if (r?.ok) {
          const L = r.item.license || {};
          ctx.setStatus(`✓ Rafa indi: ${r.item.title} — lisans tahmini: ${LIC_LONG[L.kind || "unknown"]}${L.credit_text ? ` (${L.credit_text})` : ""}`);
          $("#shelfUrl").value = "";
          refreshShelf();
        } else ctx.setStatus("İndirilemedi: " + (r?.detail || r?.error || "?"));
      } finally {
        DL = false;
        $("#shelfGet").disabled = false;
        $("#shelfProg").hidden = true;
      }
    }
    $("#shelfGet").onclick = download;
    $("#shelfUrl").addEventListener("keydown", (e) => { if (e.key === "Enter") download(); });
    $("#shelfFile").onclick = async () => {
      const r = await api()?.beat_pick_audio?.().catch(() => null);
      if (!r?.path) return;
      const a = await api()?.beat_shelf_add_file?.(r.path).catch(() => null);
      if (a?.ok) { ctx.setStatus("✓ Dosya rafa eklendi (lisans bilinmiyor — düzenle)."); refreshShelf(); }
    };

    // ---------------- Fikirler ----------------
    async function refreshIdeas() {
      const [r, lp] = await Promise.all([
        api()?.beat_ideas_list?.($("#ideaQ").value.trim(), $("#ideaTag").value, "").catch(() => null),
        ctx.getProj() ? api()?.beat_ideas_for_project?.(ctx.getProj().id).catch(() => null) : null,
      ]);
      IDEAS = r?.items || [];
      const tags = r?.tags || [];
      const cur = $("#ideaTag").value;
      $("#ideaTag").innerHTML = `<option value="">Tüm etiketler</option>` + tags.map((t) => `<option value="${esc(t)}" ${t === cur ? "selected" : ""}>#${esc(t)}</option>`).join("");
      LINES = lp?.lines || {};
      renderIdeas();
      ctx.onLinksChanged?.();
    }
    function lineOpts(it) {
      const P = ctx.getProj();
      const lines = ctx.lyricLines();
      const cur = it.link && P && it.link.project === P.id ? it.link.line : -1;
      return `<option value="-1">Söz satırına bağla…</option>` + lines.map((l) =>
        `<option value="${l.n}" ${l.n === cur ? "selected" : ""}>${l.n + 1}. ${esc(l.text.slice(0, 38))}</option>`).join("")
        + (it.link && (!P || it.link.project !== P.id) ? `<option value="-2" selected>Başka projede bağlı</option>` : "");
    }
    function renderIdeas() {
      $("#ideaCount").textContent = String(IDEAS.length);
      $("#ideaList").innerHTML = IDEAS.map((it) => `
        <div class="kb-card ${it.exists ? "" : "missing"}" draggable="${it.exists ? "true" : "false"}" data-idea="${esc(it.id)}">
          <div class="kb-card-top"><b title="${esc(it.name)} — çift tık: yeniden adlandır" data-iname="${esc(it.id)}">${esc(it.name)}</b>
            <span class="kb-num kb-mut">${fmt(it.duration)}</span></div>
          <canvas class="kb-idea-wave" data-iwave="${esc(it.id)}" title="Tıkla: çal"></canvas>
          ${IEDIT === it.id ? `<div class="kb-card-edit">
              <input class="wide" data-f="tags" value="${esc((it.tags || []).join(", "))}" placeholder="Etiketler (virgülle)">
              <textarea class="wide" data-f="note" rows="2" placeholder="Not">${esc(it.note || "")}</textarea>
              <div class="kb-pop-btns wide"><button type="button" class="btn ok" data-isave="${esc(it.id)}">Kaydet</button><button type="button" class="btn" data-icancel="1">Vazgeç</button></div>
            </div>` : `${it.tags?.length ? `<div class="kb-idea-tags">${it.tags.map((t) => `<span>#${esc(t)}</span>`).join("")}</div>` : ""}
            ${it.note ? `<div class="kb-card-meta">${esc(it.note)}</div>` : ""}`}
          <div class="kb-card-btns">
            <button type="button" class="btn ok" data-iadd="${esc(it.id)}" ${it.exists ? "" : "disabled"} title="Seçili kanala, çalma çizgisine klip olarak ekle">Projeye ekle</button>
            <select class="kb-sel" data-ilink="${esc(it.id)}" title="Söz satırına bağla — satırın yanında 🎙 çıkar">${lineOpts(it)}</select>
            <button type="button" class="btn ic" data-iedit="${esc(it.id)}" title="Etiket / not">✎</button>
            <button type="button" class="btn ic" data-idel="${esc(it.id)}" title="Sil">🗑</button>
          </div>
        </div>`).join("") || `<div class="kb-mut">Henüz fikir yok. “Hızlı fikir kaydet”e bas ya da bir ses dosyası bırak.</div>`;
      requestAnimationFrame(() => {
        for (const cv of $("#ideaList").querySelectorAll("canvas[data-iwave]")) {
          const it = IDEAS.find((x) => x.id === cv.dataset.iwave);
          if (it) ctx.drawWaveform(cv, it.peaks || [], "#F59E0B", true);
        }
      });
    }
    $("#ideaList").addEventListener("click", async (e) => {
      const P = ctx.getProj();
      const cv = e.target.closest("canvas[data-iwave]");
      if (cv) {
        const it = IDEAS.find((x) => x.id === cv.dataset.iwave);
        const rc = cv.getBoundingClientRect();
        if (it) ctx.playPath(it.file, `💡 ${it.name}`, Math.max(0, Math.min(0.98, (e.clientX - rc.left) / Math.max(1, rc.width))));
        return;
      }
      const b = e.target.closest("[data-iadd],[data-iedit],[data-idel],[data-isave],[data-icancel]");
      if (!b) return;
      const d = b.dataset;
      if (d.iadd && P) {
        const it = IDEAS.find((x) => x.id === d.iadd);
        const tid = ctx.selTrackId();
        const t = ctx.playhead();
        await ctx.serverMutate(`✓ Fikir “${it?.name}” → ${tid} @ ${t.toFixed(2)} sn`, () => ctx.runJob("beat_idea_to_project", [P.id, d.iadd, tid, t]));
      } else if (d.iedit) { IEDIT = IEDIT === d.iedit ? "" : d.iedit; renderIdeas(); }
      else if (d.icancel) { IEDIT = ""; renderIdeas(); }
      else if (d.isave) {
        const card = b.closest(".kb-card");
        await api()?.beat_idea_update?.(d.isave, { tags: card.querySelector('[data-f="tags"]').value, note: card.querySelector('[data-f="note"]').value }).catch(() => null);
        IEDIT = "";
        refreshIdeas();
      } else if (d.idel) {
        const it = IDEAS.find((x) => x.id === d.idel);
        if (!confirm(`“${it?.name || "Fikir"}” silinsin mi? (ses dosyası da silinir)`)) return;
        await api()?.beat_idea_remove?.(d.idel).catch(() => null);
        refreshIdeas();
      }
    });
    $("#ideaList").addEventListener("change", async (e) => {
      const s = e.target.closest("select[data-ilink]");
      const P = ctx.getProj();
      if (!s || !P) return;
      const n = +s.value;
      if (n === -2) return;
      await api()?.beat_idea_link?.(s.dataset.ilink, n >= 0 ? P.id : "", n).catch(() => null);
      ctx.setStatus(n >= 0 ? `Fikir ${n + 1}. söz satırına bağlandı — satırdaki 🎙 ile çal` : "Fikir bağlantısı kaldırıldı");
      refreshIdeas();
    });
    $("#ideaList").addEventListener("dblclick", (e) => {
      const b = e.target.closest("[data-iname]");
      if (!b) return;
      const it = IDEAS.find((x) => x.id === b.dataset.iname);
      const inp = document.createElement("input");
      inp.className = "kb-rename"; inp.value = it?.name || ""; inp.maxLength = 60;
      b.replaceWith(inp); inp.focus(); inp.select();
      const done = async (save) => {
        if (save && inp.value.trim()) await api()?.beat_idea_update?.(it.id, { name: inp.value.trim() }).catch(() => null);
        refreshIdeas();
      };
      inp.addEventListener("keydown", (ev) => { if (ev.key === "Enter") done(true); else if (ev.key === "Escape") done(false); ev.stopPropagation(); });
      inp.addEventListener("blur", () => done(true), { once: true });
    });
    $("#ideaList").addEventListener("dragstart", (e) => {
      const c = e.target.closest(".kb-card[data-idea]");
      if (!c) return;
      e.dataTransfer.effectAllowed = "copy";
      try { e.dataTransfer.setData(MT_IDEA, c.dataset.idea); e.dataTransfer.setData("text/plain", "kami-idea:" + c.dataset.idea); } catch {}
    });
    $("#ideaQ").addEventListener("input", () => { clearTimeout(ideaT); ideaT = setTimeout(refreshIdeas, 250); });
    $("#ideaTag").onchange = refreshIdeas;

    // hizli kayit (PC mikrofonu, en fazla 30 sn)
    async function ideaRecStop(cancel) {
      if (!IREC) return;
      clearInterval(IREC.timer);
      IREC = null;
      const b = $("#ideaRec");
      b.classList.remove("live"); b.textContent = "🎙 Hızlı fikir kaydet";
      const r = await api()?.beat_idea_quick_stop?.("", !!cancel).catch(() => null);
      if (cancel) return;
      if (r?.ok) { ctx.setStatus(`✓ Fikir kaydedildi: ${r.item.name} (${fmt(r.item.duration)})`); refreshIdeas(); }
      else ctx.setStatus("Fikir kaydı başarısız: " + (r?.error || "?"));
    }
    $("#ideaRec").onclick = async () => {
      if (IREC) { ideaRecStop(false); return; }
      if (ctx.isRecording()) { ctx.setStatus("Kayıt sürüyor — bitince fikir kaydedebilirsin."); return; }
      const r = await api()?.beat_idea_quick_start?.(ctx.micId()).catch(() => null);
      if (!r?.ok) { ctx.setStatus("Mikrofon açılamadı: " + (r?.error || "?")); return; }
      const t0 = Date.now();
      const b = $("#ideaRec");
      b.classList.add("live");
      IREC = { timer: setInterval(() => {
        const s = (Date.now() - t0) / 1000;
        b.textContent = `⏹ Durdur · ${Math.floor(s)} / ${QUICK_MAX} sn`;
        if (s >= QUICK_MAX) ideaRecStop(false);
      }, 200) };
      b.textContent = `⏹ Durdur · 0 / ${QUICK_MAX} sn`;
    };

    // dosya birakma: Python tarafi (pywebview DOM drop) tam yollari kutuya koyar, burada yoklanir
    async function pollDrop(kind) {
      for (let i = 0; i < 8; i++) {
        await new Promise((res) => setTimeout(res, 200));
        const got = await api()?.beat_drop_inbox?.().catch(() => []) || [];
        if (!got.length) continue;
        for (const p of got) {
          if (kind === "idea") {
            const r = await api()?.beat_idea_add_file?.(p, "", [], "").catch(() => null);
            if (r?.ok) ctx.setStatus(`✓ Fikir eklendi: ${r.item.name}${r.long ? " (30 sn'den uzun — kısa not önerilir)" : ""}`);
          } else {
            const r = await api()?.beat_shelf_add_file?.(p).catch(() => null);
            if (r?.ok) ctx.setStatus(`✓ Rafa eklendi: ${r.item.title}`);
          }
        }
        if (kind === "idea") refreshIdeas(); else refreshShelf();
        return;
      }
      ctx.setStatus("Bırakılan dosyanın yolu alınamadı — 📂 ile seç.");
    }
    const dz = $("#ideaDrop");
    dz.addEventListener("dragover", (e) => { if (e.dataTransfer?.types?.includes("Files")) { e.preventDefault(); dz.classList.add("over"); } });
    dz.addEventListener("dragleave", () => dz.classList.remove("over"));
    dz.addEventListener("drop", (e) => { e.preventDefault(); dz.classList.remove("over"); pollDrop("idea"); });
    dz.addEventListener("click", async () => {
      const r = await api()?.beat_pick_audio?.().catch(() => null);
      if (!r?.path) return;
      const a = await api()?.beat_idea_add_file?.(r.path, "", [], "").catch(() => null);
      if (a?.ok) { ctx.setStatus(`✓ Fikir eklendi: ${a.item.name}`); refreshIdeas(); }
    });
    const sl = $("#shelfList");
    sl.addEventListener("dragover", (e) => { if (e.dataTransfer?.types?.includes("Files")) e.preventDefault(); });
    sl.addEventListener("drop", (e) => { if (e.dataTransfer?.types?.includes("Files")) { e.preventDefault(); pollDrop("shelf"); } });

    // ---------------- zaman cizelgesine birakma ----------------
    function dragKind(e) {
      const ty = e.dataTransfer?.types || [];
      return ty.includes(MT_SHELF) ? "shelf" : ty.includes(MT_IDEA) ? "idea" : "";
    }
    async function dropOnTimeline(e, at) {
      const P = ctx.getProj();
      if (!P) return false;
      let id = "", kind = "";
      try { id = e.dataTransfer.getData(MT_SHELF); kind = id ? "shelf" : ""; } catch {}
      if (!id) { try { id = e.dataTransfer.getData(MT_IDEA); kind = id ? "idea" : ""; } catch {} }
      if (!id) {
        const tp = String(e.dataTransfer.getData("text/plain") || "");
        const m = /^kami-(shelf|idea):(.+)$/.exec(tp);
        if (m) { kind = m[1]; id = m[2]; }
      }
      if (!id) return false;
      if (kind === "shelf") { await addToProject(id, at.t); return true; }
      const tracks = P.tracks || [];
      const lane = tracks.find((t) => t.id === at.lane);
      const tid = lane && lane.role !== "beat" ? lane.id : ctx.selTrackId();
      const it = IDEAS.find((x) => x.id === id);
      await ctx.serverMutate(`✓ Fikir “${it?.name || ""}” → ${tid} @ ${at.t.toFixed(2)} sn`, () => ctx.runJob("beat_idea_to_project", [P.id, id, tid, at.t]));
      return true;
    }

    // soz paneli: satira bagli fikirler
    function lineIdeas(n) { return LINES[String(n)] || []; }

    function ideasChanged(item) {
      if (item) ctx.setStatus(`✓ iPhone'dan fikir geldi: ${item.name}`);
      refreshIdeas();
    }

    refreshShelf();
    refreshIdeas();
    return { refreshShelf, refreshIdeas, lineIdeas, ideasChanged, dropOnTimeline, dragKind, copyText,
      busy: () => !!IREC, licLabel: (k) => LIC_LONG[k] || LIC_LONG.unknown };
  }

  root.BeatLibrary = { init };
})(window);
