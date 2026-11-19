/* Kami Cleaner v1.38.0: Surucu Ozeti, 2D Squarified Treemap Canvas, 6 Analiz Sekmesi, Kopya/Benzer Gorsel & Space QuickLook. */
"use strict";
(() => {
  const api = () => window.pywebview?.api;
  const esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const fmt = (b) => {
    const n = Number(b || 0);
    if (n <= 0) return "0 B";
    const u = ["B", "KB", "MB", "GB", "TB"];
    let i = 0, v = n;
    while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
    return (i === 0 ? Math.round(v) : v.toFixed(v < 10 ? 2 : 1)) + " " + u[i];
  };

  const CL = {
    tab: "treemap",
    selectedPath: "",
    rects: [],
    hoverRect: null,
    crumbs: [],
    lastTree: null,
    checked: new Set(),
  };

  if (!document.getElementById("clV138Style")) {
    const st = document.createElement("style");
    st.id = "clV138Style";
    st.textContent = `
      [hidden] { display: none !important; }
      body { padding: 14px 16px !important; }
      .cl-drives { display: grid; grid-template-columns: repeat(auto-fill, minmax(195px, 1fr)); gap: 8px; margin-bottom: 10px; }
      .cl-dcard {
        background: #141020; border: 1px solid rgba(157,107,255,.22); border-radius: 9px;
        padding: 9px 11px; cursor: pointer; display: flex; flex-direction: column; gap: 5px;
        transition: border-color .15s ease, transform .15s ease;
      }
      .cl-dcard:hover { border-color: #2EE6A6; transform: translateY(-1px); }
      .cl-dcard-hd { display: flex; justify-content: space-between; align-items: baseline; font-size: 12.5px; }
      .cl-dcard-hd b { color: #EDE9F6; }
      .cl-dcard-hd small { color: #2EE6A6; font-size: 11px; }
      .cl-dbar { height: 5px; border-radius: 99px; background: rgba(255,255,255,.08); overflow: hidden; }
      .cl-dbar i { display: block; height: 100%; background: linear-gradient(90deg, #8B5CF6, #2EE6A6); }
      .cl-dmeta { font-size: 10.5px; color: #9088A6; display: flex; justify-content: space-between; }
      .cl-places { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; }
      .cl-chip {
        background: #171224; border: 1px solid rgba(157,107,255,.25); color: #D8D2E8;
        border-radius: 99px; padding: 4px 10px; font: 600 11px "Chakra Petch", sans-serif; cursor: pointer;
      }
      .cl-chip:hover { border-color: #2EE6A6; color: #2EE6A6; }
      .cl-tabs { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; align-items: center; }
      .cl-tab {
        background: #151022; border: 1px solid rgba(157,107,255,.24); color: #A39BB5;
        border-radius: 8px; padding: 6px 12px; font: 600 12px "Chakra Petch", sans-serif; cursor: pointer;
      }
      .cl-tab.on { background: #261947; border-color: #9D6BFF; color: #EDE9F6; }
      .cl-crumb { display: flex; gap: 5px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; font-size: 11.5px; }
      .cl-crumb button {
        background: #1A1429; border: 1px solid rgba(255,255,255,.1); color: #C4B5FD;
        border-radius: 5px; padding: 2px 7px; font: inherit; cursor: pointer;
      }
      .cl-crumb button:hover { border-color: #2EE6A6; }
      .cl-tree-wrap { position: relative; background: #0B0812; border: 1px solid rgba(157,107,255,.22); border-radius: 9px; overflow: hidden; margin-bottom: 10px; }
      #clTreeCanvas { width: 100%; height: 270px; display: block; cursor: pointer; }
      .cl-tip {
        position: absolute; pointer-events: none; z-index: 5;
        background: rgba(11,8,18,.95); border: 1px solid #2EE6A6; border-radius: 6px;
        padding: 5px 8px; font-size: 11px; color: #EDE9F6; max-width: 280px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      }
      .cl-stage { background: #120E1D; border: 1px solid rgba(255,255,255,.08); border-radius: 10px; padding: 11px 13px; margin-bottom: 12px; }
      .cl-toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; justify-content: space-between; }
      .cl-row {
        display: grid; grid-template-columns: 20px minmax(0,1fr) auto auto auto; gap: 8px; align-items: center;
        padding: 5px 7px; border-radius: 6px; font-size: 11.5px; cursor: pointer; border: 1px solid transparent;
      }
      .cl-row:hover { background: rgba(157,107,255,.08); }
      .cl-row.sel { border-color: #2EE6A6; background: rgba(46,230,166,.08); }
      .cl-row .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .cl-row .path { font-size: 10px; color: #8A829E; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: block; }
      .cl-grp { background: #0E0B17; border: 1px solid rgba(157,107,255,.2); border-radius: 8px; padding: 8px 10px; margin-bottom: 8px; }
      .cl-grp-hd { display: flex; justify-content: space-between; font-size: 11.5px; color: #C4B5FD; margin-bottom: 5px; }
      .cl-ql {
        position: fixed; inset: 0; z-index: 80; background: rgba(6,4,12,.84); backdrop-filter: blur(8px);
        display: grid; place-items: center; padding: 24px;
      }
      .cl-ql-card {
        width: min(760px, 94vw); max-height: 86vh; overflow: auto;
        background: #120E1E; border: 1px solid rgba(157,107,255,.45); border-radius: 12px; padding: 14px 16px;
        display: flex; flex-direction: column; gap: 10px; color: #EDE9F6;
      }
      .cl-ql-body img { max-width: 100%; max-height: 55vh; object-fit: contain; display: block; margin: auto; border-radius: 8px; }
      .cl-ql-body pre {
        margin: 0; padding: 10px; background: #09070D; border-radius: 8px; overflow: auto;
        max-height: 50vh; font: 12px/1.45 Consolas, monospace; color: #D8D2E8; white-space: pre-wrap; word-break: break-word;
      }
    `;
    document.head.appendChild(st);
  }

  function layoutSquarify(items, total, x, y, w, h) {
    const rects = [];
    if (!items.length || total <= 0 || w <= 2 || h <= 2) return rects;
    const norm = items.filter((it) => Number(it.size) > 0).map((it) => ({
      ...it,
      area: (Number(it.size) / total) * w * h,
    }));
    let rem = [...norm];
    let rx = x, ry = y, rw = w, rh = h;
    while (rem.length) {
      const horiz = rw >= rh;
      const side = horiz ? rh : rw;
      let row = [rem[0]];
      let rowArea = rem[0].area;
      const worst = (r, s, sum) => {
        const l = sum / Math.max(1, s);
        let mx = 0;
        for (const it of r) {
          const b = it.area / Math.max(0.01, l);
          mx = Math.max(mx, l / Math.max(0.01, b), b / Math.max(0.01, l));
        }
        return mx;
      };
      let i = 1;
      while (i < rem.length) {
        const cand = [...row, rem[i]];
        const candSum = rowArea + rem[i].area;
        if (worst(cand, side, candSum) <= worst(row, side, rowArea)) {
          row = cand;
          rowArea = candSum;
          i++;
        } else break;
      }
      const stripLen = rowArea / Math.max(1, side);
      let cursor = horiz ? ry : rx;
      for (const it of row) {
        const itemSpan = it.area / Math.max(0.01, stripLen);
        rects.push(horiz
          ? { ...it, x: rx, y: cursor, w: stripLen, h: itemSpan }
          : { ...it, x: cursor, y: ry, w: itemSpan, h: stripLen });
        cursor += itemSpan;
      }
      if (horiz) { rx += stripLen; rw -= stripLen; }
      else { ry += stripLen; rh -= stripLen; }
      rem = rem.slice(row.length);
    }
    return rects;
  }

  function colorForItem(it, idx) {
    if (it.dir) {
      const pal = ["#3B206D", "#2E3A7A", "#1C4E5A", "#4F2B7F", "#245C53", "#4B2B5E"];
      return pal[idx % pal.length];
    }
    const n = (it.name || "").toLowerCase();
    if (/\.(mp4|mkv|avi|mov|webm)$/.test(n)) return "#6D28D9";
    if (/\.(png|jpe?g|webp|gif|psd)$/.test(n)) return "#0F766E";
    if (/\.(zip|rar|7z|iso)$/.test(n)) return "#9A3412";
    if (/\.(exe|msi)$/.test(n)) return "#9F1239";
    return "#33294D";
  }

  function drawTreemap(items) {
    const cvs = document.getElementById("clTreeCanvas");
    if (!cvs) return;
    const dpr = window.devicePixelRatio || 1;
    const W = Math.max(320, cvs.clientWidth || 720);
    const H = cvs.clientHeight || 270;
    cvs.width = Math.round(W * dpr);
    cvs.height = Math.round(H * dpr);
    const ctx = cvs.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    const sum = (items || []).reduce((a, b) => a + Number(b.size || 0), 0);
    CL.rects = layoutSquarify(items || [], sum, 1, 1, W - 2, H - 2);
    CL.rects.forEach((rc, idx) => {
      const sel = rc.path === CL.selectedPath || rc === CL.hoverRect;
      ctx.fillStyle = colorForItem(rc, idx);
      ctx.fillRect(rc.x + 1, rc.y + 1, Math.max(1, rc.w - 2), Math.max(1, rc.h - 2));
      ctx.strokeStyle = sel ? "#2EE6A6" : "rgba(11,8,18,0.85)";
      ctx.lineWidth = sel ? 2 : 1;
      ctx.strokeRect(rc.x + 1, rc.y + 1, Math.max(1, rc.w - 2), Math.max(1, rc.h - 2));
      if (rc.w > 54 && rc.h > 24) {
        ctx.save();
        ctx.beginPath();
        ctx.rect(rc.x + 4, rc.y + 3, rc.w - 8, rc.h - 6);
        ctx.clip();
        ctx.fillStyle = "#F4F1FC";
        ctx.font = "600 11px 'Chakra Petch', sans-serif";
        ctx.fillText((rc.dir ? "▸ " : "") + rc.name, rc.x + 5, rc.y + 15);
        if (rc.h > 38) {
          ctx.fillStyle = "rgba(237,233,246,0.72)";
          ctx.font = "500 10px 'Chakra Petch', sans-serif";
          ctx.fillText(fmt(rc.size), rc.x + 5, rc.y + 29);
        }
        ctx.restore();
      }
    });
  }

  function renderCrumbs(curRoot) {
    const box = document.getElementById("clCrumb");
    if (!box) return;
    const parts = [];
    if (curRoot) {
      const norm = curRoot.replace(/\//g, "\\");
      const segs = norm.split("\\").filter(Boolean);
      let acc = "";
      segs.forEach((s, idx) => {
        acc = idx === 0 && s.endsWith(":") ? s + "\\" : (acc.endsWith("\\") ? acc + s : (acc ? acc + "\\" + s : "/" + s));
        parts.push({ label: s, path: acc });
      });
    }
    box.innerHTML = `<span style="color:#8A829E">Konum:</span> ` +
      parts.map((pt) => `<button type="button" data-crumb="${esc(pt.path)}">${esc(pt.label)}</button>`).join("<span>›</span>") +
      (CL.lastTree?.approx ? ` <span class="badge" style="color:#FBBF24">Yaklaşık tarama</span>` : "");
    box.querySelectorAll("[data-crumb]").forEach((b) => {
      b.onclick = () => {
        const inp = document.getElementById("root");
        if (inp) inp.value = b.dataset.crumb;
        scanActiveTab();
      };
    });
  }

  async function loadDrives() {
    const box = document.getElementById("clDrives");
    const plBox = document.getElementById("clPlaces");
    if (!box) return;
    const r = await api()?.cleaner_drives?.().catch(() => null);
    if (!r?.ok) {
      box.innerHTML = `<div class="cl-dcard"><div class="cl-dcard-hd"><b>Ana Dizin</b><small>Hazır</small></div><div class="cl-dmeta"><span>Tarama için klasör seç</span></div></div>`;
      return;
    }
    box.innerHTML = (r.drives || []).map((d) => `
      <div class="cl-dcard" data-root="${esc(d.root)}">
        <div class="cl-dcard-hd"><b>Sürücü ${esc(d.letter)}:</b><small>${fmt(d.free)} boş</small></div>
        <div class="cl-dbar"><i style="width:${Math.min(100, d.pct)}%"></i></div>
        <div class="cl-dmeta"><span>Dolu: %${d.pct}</span><span>Toplam ${fmt(d.total)}</span></div>
      </div>`).join("");
    if (plBox) {
      plBox.innerHTML = (r.places || []).map((pl) => `<button type="button" class="cl-chip" data-root="${esc(pl.path)}">${esc(pl.name)}</button>`).join("");
      plBox.querySelectorAll("[data-root]").forEach((el) => {
        el.onclick = () => { document.getElementById("root").value = el.dataset.root; scanActiveTab(); };
      });
    }
    box.querySelectorAll("[data-root]").forEach((el) => {
      el.onclick = () => { document.getElementById("root").value = el.dataset.root; scanActiveTab(); };
    });
  }

  function wireRowSelection(container) {
    container.querySelectorAll("[data-preview-path]").forEach((row) => {
      row.addEventListener("click", (e) => {
        if (e.target.closest("button,input")) return;
        CL.selectedPath = row.dataset.previewPath || "";
        container.querySelectorAll("[data-preview-path]").forEach((r) => r.classList.toggle("sel", r === row));
      });
    });
    container.querySelectorAll("[data-ql]").forEach((btn) => {
      btn.onclick = (e) => { e.stopPropagation(); openQuickLook(btn.dataset.ql); };
    });
    container.querySelectorAll("[data-open-dir]").forEach((btn) => {
      btn.onclick = (e) => { e.stopPropagation(); api()?.cleaner_open_folder?.(btn.dataset.openDir); };
    });
    container.querySelectorAll("[data-tr]").forEach((btn) => {
      btn.onclick = async (e) => {
        e.stopPropagation();
        btn.disabled = true;
        btn.textContent = "…";
        const r = await api()?.cleaner_trash?.(btn.dataset.tr).catch(() => null);
        if (r?.ok) btn.closest(".cl-row")?.remove();
        else { btn.disabled = false; btn.textContent = r?.error === "protected" ? "Korumalı" : "Hata"; }
      };
    });
    container.querySelectorAll("[data-chk]").forEach((cb) => {
      cb.onchange = () => {
        if (cb.checked) CL.checked.add(cb.dataset.chk);
        else CL.checked.delete(cb.dataset.chk);
        updateBulkBtn(container);
      };
    });
  }

  function updateBulkBtn(container) {
    const b = container.querySelector("#clBulkTrash");
    if (b) {
      b.textContent = `Seçilenleri Çöpe Gönder (${CL.checked.size})`;
      b.disabled = CL.checked.size === 0;
    }
  }

  async function bulkTrash(container) {
    const list = [...CL.checked];
    if (!list.length) return;
    const b = container.querySelector("#clBulkTrash");
    if (b) { b.disabled = true; b.textContent = "Siliniyor…"; }
    const r = await api()?.cleaner_trash_many?.(list).catch(() => null);
    CL.checked.clear();
    await scanActiveTab();
    if (b && r) b.textContent = `${r.trashed || 0} öğe Geri Dönüşüm'e gitti`;
  }

  async function renderTreemapTab(stage) {
    const root = (document.getElementById("root")?.value || "").trim();
    stage.innerHTML = `<div class="cl-crumb" id="clCrumb"></div><div class="cl-tree-wrap"><canvas id="clTreeCanvas"></canvas><div class="cl-tip" id="clTip" hidden></div></div><small style="color:#8A829E">İpucu: Tıklayıp <b>Space</b> ile önizle (QuickLook) · Klasöre çift tıkla: içine gir</small>`;
    const r = await api()?.cleaner_treemap?.(root).catch(() => null);
    if (!r?.ok) { stage.innerHTML += `<p style="color:#F87171">Tarama başarısız.</p>`; return; }
    CL.lastTree = r;
    renderCrumbs(r.root);
    drawTreemap(r.items || []);

    const cvs = document.getElementById("clTreeCanvas");
    const tip = document.getElementById("clTip");
    const hitAt = (ev) => {
      const rect = cvs.getBoundingClientRect();
      const x = ev.clientX - rect.left, y = ev.clientY - rect.top;
      return { x, y, hit: CL.rects.find((rc) => x >= rc.x && x <= rc.x + rc.w && y >= rc.y && y <= rc.y + rc.h) || null };
    };
    cvs.onmousemove = (ev) => {
      const { x, y, hit } = hitAt(ev);
      if (hit !== CL.hoverRect) { CL.hoverRect = hit; drawTreemap(CL.lastTree.items || []); }
      if (!hit) { tip.hidden = true; return; }
      tip.hidden = false;
      tip.textContent = `${hit.dir ? "▸ " : ""}${hit.name} · ${fmt(hit.size)}`;
      tip.style.left = Math.min(cvs.clientWidth - 220, Math.max(6, x + 12)) + "px";
      tip.style.top = Math.max(6, y - 28) + "px";
    };
    cvs.onmouseleave = () => { CL.hoverRect = null; if (tip) tip.hidden = true; drawTreemap(CL.lastTree.items || []); };
    cvs.onclick = (ev) => {
      const { hit } = hitAt(ev);
      if (!hit) return;
      CL.selectedPath = hit.path;
      drawTreemap(CL.lastTree.items || []);
    };
    cvs.ondblclick = (ev) => {
      const { hit } = hitAt(ev);
      if (hit?.dir) { document.getElementById("root").value = hit.path; scanActiveTab(); }
      else if (hit?.path) openQuickLook(hit.path);
    };
  }

  async function renderExtTab(stage) {
    const root = (document.getElementById("root")?.value || "").trim();
    stage.innerHTML = `<small style="color:#8A829E">Uzantılar analiz ediliyor…</small>`;
    const r = await api()?.cleaner_by_ext?.(root).catch(() => null);
    if (!r?.ok) { stage.innerHTML = `<small>Analiz alınamadı.</small>`; return; }
    const total = Math.max(1, r.total_size || 1);
    stage.innerHTML = `
      <div class="cl-toolbar"><b>${esc(r.root)} · ${r.total_files} dosya (${fmt(r.total_size)})</b>${r.approx ? `<span style="color:#FBBF24;font-size:11px">Kısmi tarama (süre bütçesi)</span>` : ""}</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px;margin-bottom:10px">
        ${(r.categories || []).map((c) => `
          <div class="cl-dcard" style="cursor:default">
            <div class="cl-dcard-hd"><b>${esc(c.name)}</b><small>${fmt(c.size)}</small></div>
            <div class="cl-dbar"><i style="width:${Math.max(2, Math.round((c.size / total) * 100))}%"></i></div>
            <div class="cl-dmeta"><span>${c.count} dosya</span><span>%${((c.size / total) * 100).toFixed(1)}</span></div>
          </div>`).join("")}
      </div>
      <div style="max-height:240px;overflow:auto">
        ${(r.extensions || []).map((e) => `<div class="cl-row"><span></span><span class="name"><b>${esc(e.ext)}</b> · ${e.count} dosya</span><span>${fmt(e.size)}</span><span>%${((e.size / total) * 100).toFixed(1)}</span><span></span></div>`).join("")}
      </div>`;
  }

  async function renderLargestTab(stage) {
    const root = (document.getElementById("root")?.value || "").trim();
    CL.checked.clear();
    stage.innerHTML = `<small style="color:#8A829E">En büyük dosyalar taranıyor…</small>`;
    const r = await api()?.cleaner_largest?.(root, 100).catch(() => null);
    if (!r?.ok) { stage.innerHTML = `<small>Taranamadı.</small>`; return; }
    stage.innerHTML = `
      <div class="cl-toolbar">
        <b>En Büyük ${r.items.length} Dosya (${esc(r.root)})</b>
        <button class="btn" id="clBulkTrash" disabled>Seçilenleri Çöpe Gönder (0)</button>
      </div>
      <div style="max-height:320px;overflow:auto">
        ${(r.items || []).map((x) => `
          <div class="cl-row" data-preview-path="${esc(x.path)}">
            <input type="checkbox" data-chk="${esc(x.path)}" ${x.protected ? "disabled" : ""}>
            <div style="min-width:0"><span class="name">${esc(x.name)}</span><span class="path">${esc(x.path)}</span></div>
            <b style="color:#2EE6A6">${fmt(x.size)}</b>
            <button class="btn" data-ql="${esc(x.path)}" title="QuickLook (Space)">👁</button>
            <button class="btn" data-tr="${esc(x.path)}" ${x.protected ? "disabled title='Sistem/Kami korumalı'" : "title='Çöpe gönder'"}>🗑</button>
          </div>`).join("") || `<small style="color:#8A829E">Dosya bulunamadı.</small>`}
      </div>`;
    stage.querySelector("#clBulkTrash").onclick = () => bulkTrash(stage);
    wireRowSelection(stage);
  }

  async function renderDuplicatesTab(stage) {
    const root = (document.getElementById("root")?.value || "").trim();
    CL.checked.clear();
    stage.innerHTML = `<small style="color:#8A829E">3 aşamalı SHA-256 kopya taraması sürüyor…</small>`;
    const r = await api()?.cleaner_duplicates?.(root).catch(() => null);
    if (!r?.ok) { stage.innerHTML = `<small>Kopya taraması yapılamadı.</small>`; return; }
    stage.innerHTML = `
      <div class="cl-toolbar">
        <b>${(r.groups || []).length} Kopya Grubu · Geri kazanılabilir: <span style="color:#2EE6A6">${fmt(r.total_wasted)}</span></b>
        <div style="display:flex;gap:6px">
          <button class="btn" id="clDupSmart">İlkini Koru, Kopyaları Seç</button>
          <button class="btn pri" id="clBulkTrash" disabled>Seçilenleri Çöpe Gönder (0)</button>
        </div>
      </div>
      <div style="max-height:320px;overflow:auto">
        ${(r.groups || []).map((g, gi) => `
          <div class="cl-grp">
            <div class="cl-grp-hd"><span>#${gi + 1} · Her biri ${fmt(g.size)} · SHA ${esc(g.hash)}</span><span>Boşa: ${fmt(g.wasted)}</span></div>
            ${g.files.map((f, fi) => `
              <div class="cl-row" data-preview-path="${esc(f.path)}">
                <input type="checkbox" data-chk="${esc(f.path)}" data-dup-keep="${fi === 0 ? "1" : "0"}" ${f.protected ? "disabled" : ""}>
                <div style="min-width:0"><span class="name">${fi === 0 ? "[Asıl] " : ""}${esc(f.name)}</span><span class="path">${esc(f.path)}</span></div>
                <span>${fmt(g.size)}</span>
                <button class="btn" data-ql="${esc(f.path)}">👁</button>
                <button class="btn" data-tr="${esc(f.path)}" ${f.protected ? "disabled" : ""}>🗑</button>
              </div>`).join("")}
          </div>`).join("") || `<small style="color:#2EE6A6">Birebir kopya dosya bulunamadı ✓</small>`}
      </div>`;
    stage.querySelector("#clDupSmart").onclick = () => {
      CL.checked.clear();
      stage.querySelectorAll("[data-chk]").forEach((cb) => {
        const select = cb.dataset.dupKeep === "0" && !cb.disabled;
        cb.checked = select;
        if (select) CL.checked.add(cb.dataset.chk);
      });
      updateBulkBtn(stage);
    };
    stage.querySelector("#clBulkTrash").onclick = () => bulkTrash(stage);
    wireRowSelection(stage);
  }

  async function renderSimilarTab(stage) {
    const root = (document.getElementById("root")?.value || "").trim();
    CL.checked.clear();
    stage.innerHTML = `<small style="color:#8A829E">Görseller 64-bit dHash ile karşılaştırılıyor…</small>`;
    const r = await api()?.cleaner_similar_images?.(root, 8).catch(() => null);
    if (!r?.ok) { stage.innerHTML = `<small>Tarama yapılamadı.</small>`; return; }
    stage.innerHTML = `
      <div class="cl-toolbar">
        <b>${r.scanned || 0} Görsel Tarandı · ${(r.groups || []).length} Benzer Küme</b>
        <div style="display:flex;gap:6px">
          <button class="btn" id="clSimSmart">En Neti Koru, Diğerlerini Seç</button>
          <button class="btn pri" id="clBulkTrash" disabled>Seçilenleri Çöpe Gönder (0)</button>
        </div>
      </div>
      <div style="max-height:320px;overflow:auto">
        ${(r.groups || []).map((g) => `
          <div class="cl-grp">
            <div class="cl-grp-hd"><span>${g.count} Benzer Görsel</span><span>Toplam ${fmt(g.total_size)}</span></div>
            ${g.items.map((it, idx) => `
              <div class="cl-row" data-preview-path="${esc(it.path)}">
                <input type="checkbox" data-chk="${esc(it.path)}" data-sim-keep="${idx === 0 ? "1" : "0"}">
                <div style="min-width:0"><span class="name">${idx === 0 ? "[En Yüksek] " : ""}${esc(it.name)} (${it.width}×${it.height})</span><span class="path">${esc(it.path)}</span></div>
                <span>${fmt(it.size)}</span>
                <button class="btn" data-ql="${esc(it.path)}">👁</button>
                <button class="btn" data-tr="${esc(it.path)}">🗑</button>
              </div>`).join("")}
          </div>`).join("") || `<small style="color:#2EE6A6">Benzer görsel kümesi bulunamadı ✓</small>`}
      </div>`;
    stage.querySelector("#clSimSmart").onclick = () => {
      CL.checked.clear();
      stage.querySelectorAll("[data-chk]").forEach((cb) => {
        const select = cb.dataset.simKeep === "0";
        cb.checked = select;
        if (select) CL.checked.add(cb.dataset.chk);
      });
      updateBulkBtn(stage);
    };
    stage.querySelector("#clBulkTrash").onclick = () => bulkTrash(stage);
    wireRowSelection(stage);
  }

  async function renderCachesTab(stage) {
    CL.checked.clear();
    stage.innerHTML = `<small style="color:#8A829E">Güvenli önbellekler hesaplanıyor…</small>`;
    const r = await api()?.cleaner_caches?.().catch(() => null);
    if (!r?.ok) { stage.innerHTML = `<small>Önbellek okunamadı.</small>`; return; }
    stage.innerHTML = `
      <div class="cl-toolbar">
        <b>Güvenli Temizlenebilir Önbellekler · Toplam <span style="color:#2EE6A6">${fmt(r.total_size)}</span></b>
        <div style="display:flex;gap:6px">
          <button class="btn" id="clCacheAll">Tümünü Seç</button>
          <button class="btn pri" id="clBulkTrash" disabled>Seçilenleri Çöpe Gönder (0)</button>
        </div>
      </div>
      <div style="max-height:320px;overflow:auto">
        ${(r.items || []).map((c) => `
          <div class="cl-row" data-preview-path="${esc(c.path)}">
            <input type="checkbox" data-chk="${esc(c.path)}">
            <div style="min-width:0"><span class="name">${esc(c.label)}</span><span class="path">${esc(c.path)}</span></div>
            <b style="color:#C4B5FD">${fmt(c.size)}</b>
            <button class="btn" data-open-dir="${esc(c.path)}" title="Klasörü aç">↗</button>
            <button class="btn" data-tr="${esc(c.path)}">🗑</button>
          </div>`).join("") || `<small style="color:#2EE6A6">Önbellekler zaten temiz ✓</small>`}
      </div>`;
    stage.querySelector("#clCacheAll").onclick = () => {
      CL.checked.clear();
      stage.querySelectorAll("[data-chk]").forEach((cb) => { cb.checked = true; CL.checked.add(cb.dataset.chk); });
      updateBulkBtn(stage);
    };
    stage.querySelector("#clBulkTrash").onclick = () => bulkTrash(stage);
    wireRowSelection(stage);
  }

  async function openQuickLook(path) {
    if (!path) return;
    let ov = document.getElementById("clQuickLook");
    if (!ov) {
      ov = document.createElement("div");
      ov.id = "clQuickLook";
      ov.className = "cl-ql";
      document.body.appendChild(ov);
      ov.addEventListener("click", (e) => { if (e.target === ov) ov.hidden = true; });
    }
    ov.hidden = false;
    ov.innerHTML = `<div class="cl-ql-card"><div class="cl-toolbar"><b>Yükleniyor…</b><button class="btn" id="clQlX">Kapat (Esc)</button></div></div>`;
    ov.querySelector("#clQlX").onclick = () => { ov.hidden = true; };
    const r = await api()?.cleaner_preview?.(path).catch(() => null);
    let body = `<p style="color:#8A829E">Önizleme oluşturulamadı.</p>`;
    if (r?.ok) {
      if (r.kind === "image" && r.url) body = `<img src="${r.url}" alt="">`;
      else if (r.kind === "text") body = `<pre>${esc(r.text || "")}</pre>`;
      else body = `<p style="color:#C4B5FD">${esc(r.name)} · Tür: ${esc(r.ext || "?")} · Boyut: ${fmt(r.size)}</p>`;
    }
    ov.innerHTML = `
      <div class="cl-ql-card">
        <div class="cl-toolbar">
          <div style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"><b>${esc(r?.name || path.split(/[\\/]/).pop())}</b> <small style="color:#2EE6A6">${fmt(r?.size || 0)}${r?.width ? ` · ${r.width}×${r.height}` : ""}</small></div>
          <div style="display:flex;gap:6px">
            <button class="btn" id="clQlDir">Klasör</button>
            <button class="btn" id="clQlTrash">🗑 Çöp</button>
            <button class="btn" id="clQlX">Kapat</button>
          </div>
        </div>
        <div class="cl-ql-body">${body}</div>
      </div>`;
    ov.querySelector("#clQlX").onclick = () => { ov.hidden = true; };
    ov.querySelector("#clQlDir").onclick = () => api()?.cleaner_open_folder?.(path);
    ov.querySelector("#clQlTrash").onclick = async () => {
      const res = await api()?.cleaner_trash?.(path).catch(() => null);
      if (res?.ok) { ov.hidden = true; scanActiveTab(); }
    };
  }

  async function scanActiveTab() {
    const stage = document.getElementById("clStage");
    if (!stage) return;
    if (CL.tab === "treemap") return renderTreemapTab(stage);
    if (CL.tab === "ext") return renderExtTab(stage);
    if (CL.tab === "largest") return renderLargestTab(stage);
    if (CL.tab === "dups") return renderDuplicatesTab(stage);
    if (CL.tab === "sim") return renderSimilarTab(stage);
    if (CL.tab === "caches") return renderCachesTab(stage);
    if (CL.tab === "dust") return renderDustTab(stage);
    if (CL.tab === "janitor") return renderJanitorTab(stage);
  }

  async function renderDustTab(stage) {
    CL.checked.clear();
    stage.innerHTML = `<small style="color:#8A829E">Kami Dust: Kaldırılmış programların AppData altındaki yetim kalıntıları taranıyor…</small>`;
    const r = await api()?.cleaner_dust?.(21, 128).catch(() => null);
    if (!r?.ok) { stage.innerHTML = `<small>Kami Dust taraması yapılamadı.</small>`; return; }
    stage.innerHTML = `
      <div class="cl-toolbar">
        <b>Kami Dust (Kaldırılan Program Artıkları) · ${r.count || 0} Yetim Klasör · <span style="color:#2EE6A6">${fmt(r.total_size)}</span></b>
        <div style="display:flex;gap:6px">
          <button class="btn" id="clDustAll">Tümünü Seç</button>
          <button class="btn pri" id="clBulkTrash" disabled>Seçilenleri Çöpe Gönder (0)</button>
        </div>
      </div>
      <div style="max-height:320px;overflow:auto">
        ${(r.items || []).map((c) => `
          <div class="cl-row" data-preview-path="${esc(c.path)}">
            <input type="checkbox" data-chk="${esc(c.path)}">
            <div style="min-width:0"><span class="name"><b>${esc(c.name)}</b> <small style="color:#8A829E">(${esc(c.scope)} · ${c.idle_days} gündür dokunulmadı)</small></span><span class="path">${esc(c.path)}</span></div>
            <b style="color:#FB7185">${fmt(c.size)}</b>
            <button class="btn" data-open-dir="${esc(c.path)}" title="Klasörü aç">↗</button>
            <button class="btn" data-tr="${esc(c.path)}" title="Geri Dönüşüm Kutusu'na gönder">🗑</button>
          </div>`).join("") || `<small style="color:#2EE6A6">Kaldırılmış programlardan kalan yetim klasör bulunamadı ✓</small>`}
      </div>`;
    stage.querySelector("#clDustAll").onclick = () => {
      CL.checked.clear();
      stage.querySelectorAll("[data-chk]").forEach((cb) => { cb.checked = true; CL.checked.add(cb.dataset.chk); });
      updateBulkBtn(stage);
    };
    stage.querySelector("#clBulkTrash").onclick = () => bulkTrash(stage);
    wireRowSelection(stage);
  }

  async function renderJanitorTab(stage) {
    stage.innerHTML = `<small style="color:#8A829E">Klasör Bekçisi kuralları simüle ediliyor (aktif indirmelere dokunmaz)…</small>`;
    const r = await api()?.cleaner_janitor?.(true).catch(() => null);
    if (!r?.ok) { stage.innerHTML = `<small>Klasör Bekçisi okunamadı.</small>`; return; }
    stage.innerHTML = `
      <div class="cl-toolbar">
        <b>Hazel 6 Tarzı Otomatik Klasör Bekçisi · ${r.count || 0} Yaşlanmış Dosya (${fmt(r.total_size)})</b>
        <button class="btn pri" id="clJanRun" ${r.count ? "" : "disabled"}>Şimdi Düzenle & Taşı (${r.count || 0})</button>
      </div>
      <p style="margin:0 0 8px;font-size:11px;color:#A39BB5">Kurallar: Masaüstünde 48 saati geçen ekran görüntüleri → <code>Pictures\\Screenshots</code> · 14 günü geçen kurulum (.exe/.msi) → <code>Program\\Eski_Kurulumlar</code> · İndirilenler kökündeki 3+ günlük PDF/EPUB → <code>Belge</code> (Otomatik klasörlendirmeyle çakışmaz).</p>
      <div style="max-height:290px;overflow:auto">
        ${(r.actions || []).map((a) => `
          <div class="cl-row">
            <span>✓</span>
            <div style="min-width:0"><span class="name"><b>${esc(a.name)}</b> · <small style="color:#C4B5FD">${esc(a.rule)}</small></span><span class="path">${esc(a.from)} → ${esc(a.to)}</span></div>
            <b style="color:#2EE6A6">${fmt(a.size)}</b>
            <span></span><span></span>
          </div>`).join("") || `<small style="color:#2EE6A6">Masaüstü ve İndirilenler kök dizini tamamen düzenli ✓</small>`}
      </div>`;
    const runBtn = stage.querySelector("#clJanRun");
    if (runBtn) {
      runBtn.onclick = async () => {
        runBtn.disabled = true;
        runBtn.textContent = "Düzenleniyor…";
        const res = await api()?.cleaner_janitor?.(false).catch(() => null);
        await renderJanitorTab(stage);
        if (res?.ok) alert(`✓ ${res.count || 0} dosya güvenle düzenlendi.`);
      };
    }
  }

  function mount() {
    const cols = document.querySelector(".cols");
    if (!cols || document.getElementById("clDrives")) return;
    const drives = document.createElement("div");
    drives.id = "clDrives";
    drives.className = "cl-drives";
    const places = document.createElement("div");
    places.id = "clPlaces";
    places.className = "cl-places";
    const tabs = document.createElement("div");
    tabs.id = "clTabs";
    tabs.className = "cl-tabs";
    tabs.innerHTML = [
      ["treemap", "Harita (Treemap)"],
      ["ext", "Uzantılar"],
      ["largest", "En Büyükler"],
      ["dups", "Kopyalar (SHA-256)"],
      ["sim", "Benzer Görseller"],
      ["caches", "Güvenli Önbellek"],
      ["dust", "Kami Dust (Yetim Artıklar)"],
      ["janitor", "Klasör Bekçisi (Hazel)"],
    ].map(([id, label]) => `<button type="button" class="cl-tab${id === CL.tab ? " on" : ""}" data-cltab="${id}">${label}</button>`).join("");

    const stage = document.createElement("div");
    stage.id = "clStage";
    stage.className = "cl-stage";

    cols.parentNode.insertBefore(drives, cols);
    cols.parentNode.insertBefore(places, cols);
    cols.parentNode.insertBefore(tabs, cols);
    cols.parentNode.insertBefore(stage, cols);

    tabs.querySelectorAll("[data-cltab]").forEach((b) => {
      b.onclick = () => {
        CL.tab = b.dataset.cltab;
        tabs.querySelectorAll("[data-cltab]").forEach((t) => t.classList.toggle("on", t === b));
        scanActiveTab();
      };
    });

    document.getElementById("scan")?.addEventListener("click", () => {
      setTimeout(() => scanActiveTab(), 30);
    });
    document.getElementById("res")?.addEventListener("click", (e) => {
      const b = e.target.closest("[data-trash]");
      if (b?.dataset.trash) CL.selectedPath = b.dataset.trash;
    });

    document.addEventListener("keydown", (e) => {
      const ql = document.getElementById("clQuickLook");
      if (e.key === "Escape" && ql && !ql.hidden) { ql.hidden = true; return; }
      const tag = (e.target?.tagName || "").toUpperCase();
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.code === "Space") {
        if (ql && !ql.hidden) { e.preventDefault(); ql.hidden = true; return; }
        if (CL.selectedPath) { e.preventDefault(); openQuickLook(CL.selectedPath); }
      }
    });

    loadDrives();
    if (typeof window.pywebview !== "undefined") scanActiveTab();
    window.addEventListener("pywebviewready", () => { loadDrives(); scanActiveTab(); });
    window.addEventListener("resize", () => { if (CL.tab === "treemap" && CL.lastTree) drawTreemap(CL.lastTree.items || []); });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
  else mount();

  window.kamiCleanerV138 = { scanActiveTab, loadDrives, openQuickLook };
})();
