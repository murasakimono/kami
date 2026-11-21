// Faz 16.3 — Kami Pano (Sunak Uyumlu Yüzen Raf)
"use strict";
(() => {
  const PANO = { items: [], open: false, q: "", selectedId: "" };

  function kindBadge(v, ocr) {
    const s = String(v || "").trim();
    if (/youtube\.com|youtu\.be/i.test(s)) return { ic: "🎬", dl: true };
    if (/\.(png|jpe?g|webp|gif|bmp)(\?|$)/i.test(s)) return { ic: ocr ? "🖼🔤" : "🖼", dl: true };
    if (/^https?:\/\//i.test(s) || /^magnet:\?/i.test(s)) return { ic: "🔗", dl: true };
    return { ic: "📝", dl: false };
  }

  function cleanUrlParams(raw) {
    const u = new URL(String(raw || "").trim());
    const bad = new Set(["fbclid", "gclid", "dclid", "yclid", "igshid", "si", "ref", "ref_src", "mc_cid", "mc_eid", "spm", "_hsenc", "_hsmi"]);
    for (const k of [...u.searchParams.keys()]) {
      if (k.toLowerCase().startsWith("utm_") || bad.has(k.toLowerCase())) u.searchParams.delete(k);
    }
    return u.toString();
  }

  function encodeB64Utf8(str) {
    const bytes = new TextEncoder().encode(str);
    let bin = "";
    for (const b of bytes) bin += String.fromCharCode(b);
    return btoa(bin);
  }

  function decodeB64Utf8(str) {
    const bin = atob(str.trim());
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  }

  function toggleCase(str) {
    if (str !== str.toUpperCase()) return str.toUpperCase();
    return str.toLowerCase();
  }

  async function runTransform(mode) {
    const msg = document.getElementById("kpMsg");
    const setMsg = (txt, err = false) => {
      if (!msg) return;
      msg.textContent = txt;
      msg.style.color = err ? "#FF7A99" : "#2EE6A6";
    };
    const sel = PANO.items.find((x) => x.id === PANO.selectedId) || PANO.items.find((x) => x.value);
    let src = sel?.value || "";
    if (!src && navigator.clipboard?.readText) {
      try { src = await navigator.clipboard.readText(); } catch {}
    }
    if (!src) return setMsg("Dönüştürülecek metin bulunamadı", true);
    let out = "";
    let lbl = "";
    try {
      if (mode === "json") {
        out = JSON.stringify(JSON.parse(src), null, 2);
        lbl = "JSON biçimlendi";
      } else if (mode === "url") {
        out = cleanUrlParams(src);
        lbl = "URL temizlendi";
      } else if (mode === "b64") {
        const clean = src.trim();
        if (/^[A-Za-z0-9+/]{4,}={0,2}$/.test(clean) && clean.length % 4 === 0) {
          try {
            out = decodeB64Utf8(clean);
            lbl = "Base64 çözüldü";
          } catch {
            out = encodeB64Utf8(src);
            lbl = "Base64 kodlandı";
          }
        } else {
          out = encodeB64Utf8(src);
          lbl = "Base64 kodlandı";
        }
      } else if (mode === "case") {
        out = toggleCase(src);
        lbl = "Harf büyüklüğü değişti";
      }
    } catch (e) {
      return setMsg("Dönüşüm hatası: geçersiz biçim", true);
    }
    if (!out) return;
    try { await navigator.clipboard?.writeText?.(out); } catch {}
    if (typeof api !== "undefined" && api?.pano_shelf_add) {
      await api.pano_shelf_add("text", out, lbl).catch(() => {});
      await refresh();
    }
    setMsg(`${lbl} · panoya kopyalandı ✓`);
  }

  // ---------- Ekran olcu (dikdortgen) & OKLCH renk sec ----------
  const PTOOL = { on: false, mode: "", overlay: null, hint: null, box: null, s0: null };
  function ptCancel() {
    PTOOL.on = false; PTOOL.s0 = null;
    [PTOOL.overlay, PTOOL.hint, PTOOL.box].forEach((n) => { if (n) n.remove(); });
    PTOOL.overlay = PTOOL.hint = PTOOL.box = null;
  }
  function ptShowPick(r) {
    const msg = document.getElementById("kpMsg");
    if (!r?.ok) { if (msg) { msg.textContent = "Renk alınamadı: " + (r?.error || ""); msg.style.color = "#FF7A99"; } return; }
    if (msg) { msg.style.color = "#2EE6A6"; msg.innerHTML = `<i style="display:inline-block;width:12px;height:12px;border-radius:3px;background:${r.hex};vertical-align:-1px"></i> ${r.hex} · ${r.css || ""}`; }
  }
  function ptShowMeasure(r) {
    const msg = document.getElementById("kpMsg");
    if (!r?.ok || !msg) return;
    msg.style.color = "#2EE6A6";
    msg.textContent = `Ölçü: ${r.width}×${r.height} px · Çapraz ${r.diagonal} px · Oran ${r.aspect}`;
  }
  function ptStart(mode) {
    if (PTOOL.on) return ptCancel();
    PTOOL.on = true; PTOOL.mode = mode; PTOOL.s0 = null;
    const dpr = window.devicePixelRatio || 1;
    const ov = document.createElement("div");
    ov.style.cssText = "position:fixed;inset:0;z-index:9001;cursor:crosshair;background:rgba(6,4,10,.18)";
    ov.tabIndex = 0;
    const hint = document.createElement("div");
    hint.style.cssText = "position:fixed;top:12px;left:50%;transform:translateX(-50%);z-index:9002;background:rgba(13,10,20,.95);border:1px solid rgba(139,92,246,.6);color:#EDE9F6;font:12px 'Chakra Petch',sans-serif;padding:6px 12px;border-radius:8px;pointer-events:none";
    hint.textContent = mode === "measure" ? "Ölçülecek alanı sürükleyerek seç (Esc iptal)" : "Rengini alacağın piksele tıkla (Esc iptal)";
    const bx = document.createElement("div");
    bx.style.cssText = "position:fixed;display:none;border:2px solid #2EE6A6;background:rgba(46,230,166,.14);z-index:9002;pointer-events:none";
    document.body.appendChild(hint); document.body.appendChild(bx); document.body.appendChild(ov);
    PTOOL.overlay = ov; PTOOL.hint = hint; PTOOL.box = bx;
    ov.addEventListener("pointerdown", (e) => { PTOOL.s0 = { sx: e.screenX, sy: e.screenY, cx: e.clientX, cy: e.clientY }; });
    ov.addEventListener("pointermove", (e) => {
      if (mode !== "measure" || !PTOOL.s0) return;
      const x0 = PTOOL.s0.cx, y0 = PTOOL.s0.cy, x1 = e.clientX, y1 = e.clientY;
      bx.style.left = Math.min(x0, x1) + "px"; bx.style.top = Math.min(y0, y1) + "px";
      bx.style.width = Math.abs(x1 - x0) + "px"; bx.style.height = Math.abs(y1 - y0) + "px";
      bx.style.display = "block";
    });
    ov.addEventListener("pointerup", async (e) => {
      if (mode === "pick") {
        const x = Math.round(e.screenX * dpr), y = Math.round(e.screenY * dpr);
        ptCancel();
        const r = await api?.pano_pick_oklch?.(x, y).catch(() => null);
        ptShowPick(r);
      } else {
        if (!PTOOL.s0) return ptCancel();
        const x0 = Math.round(PTOOL.s0.sx * dpr), y0 = Math.round(PTOOL.s0.sy * dpr);
        const x1 = Math.round(e.screenX * dpr), y1 = Math.round(e.screenY * dpr);
        ptCancel();
        const r = await api?.pano_measure_rect?.(x0, y0, x1, y1).catch(() => null);
        ptShowMeasure(r);
      }
    });
    ov.addEventListener("keydown", (e) => { if (e.key === "Escape") ptCancel(); });
    ov.focus();
  }

  function renderList() {
    const list = document.getElementById("kpList");
    if (!list) return;
    list.replaceChildren();
    const q = (PANO.q || "").trim().toLowerCase();
    const view = q
      ? PANO.items.filter((x) =>
          (x.label || "").toLowerCase().includes(q) ||
          (x.value || "").toLowerCase().includes(q) ||
          (x.ocr_text || "").toLowerCase().includes(q))
      : PANO.items;
    if (!view.length) {
      const em = document.createElement("div");
      em.style.cssText = "color:#8A829E;font-size:11px;padding:10px 4px;text-align:center";
      em.textContent = q ? "Aramanızla eşleşen öğe yok" : "Raf boş — kopyalanan link veya notlar buraya gelir";
      list.appendChild(em);
      return;
    }
    for (const x of view) {
      const kb = kindBadge(x.value, x.ocr_text);
      const isSel = PANO.selectedId === x.id;
      const d = document.createElement("div");
      d.style.cssText = `padding:6px 8px;min-width:0;overflow:hidden;background:${isSel ? "rgba(139,92,246,.22)" : "rgba(139,92,246,.08)"};border:1px solid ${isSel ? "#2EE6A6" : "rgba(139,92,246,.22)"};clip-path:polygon(6px 0,100% 0,100% calc(100% - 6px),calc(100% - 6px) 100%,0 100%,0 6px);display:flex;justify-content:space-between;align-items:center;gap:6px;cursor:pointer;font-size:11px`;
      const col = document.createElement("div");
      col.style.cssText = "min-width:0;flex:1;display:flex;flex-direction:column;gap:2px";
      const sp = document.createElement("span");
      sp.style.cssText = "min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap";
      sp.textContent = `${kb.ic} ${x.label || x.value || ""}`;
      col.appendChild(sp);
      if (x.ocr_text) {
        const oc = document.createElement("small");
        oc.style.cssText = "color:#2EE6A6;font-size:9.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap";
        oc.textContent = `OCR: ${x.ocr_text.replace(/\s+/g, " ").slice(0, 64)}`;
        col.appendChild(oc);
      }
      d.title = (x.value || x.label || "") + (x.ocr_text ? `\n[OCR]\n${x.ocr_text.slice(0, 200)}` : "");
      d.onclick = () => {
        PANO.selectedId = x.id || "";
        const copyVal = x.ocr_text && !/^https?:/i.test(x.value) && x.kind === "file" ? x.ocr_text : x.value;
        if (copyVal && navigator.clipboard?.writeText) {
          navigator.clipboard.writeText(copyVal).catch(() => {});
          d.style.borderColor = "#2EE6A6";
          setTimeout(() => renderList(), 450);
        } else {
          renderList();
        }
      };
      d.appendChild(col);
      if (kb.dl && x.value) {
        const dl = document.createElement("button");
        dl.type = "button";
        dl.textContent = "⬇";
        dl.title = "İndirme kutusuna al";
        dl.style.cssText = "background:#2A1650;border:1px solid rgba(157,107,255,.45);color:#EDE9F6;border-radius:5px;padding:1px 6px;cursor:pointer;font-size:10px";
        dl.onclick = (ev) => {
          ev.stopPropagation();
          const inp = document.getElementById("addInput");
          if (inp) { inp.value = x.value; inp.focus(); }
        };
        d.appendChild(dl);
      }
      if (x.id) {
        const rm = document.createElement("button");
        rm.type = "button";
        rm.textContent = "✕";
        rm.title = "Raftan kaldır";
        rm.style.cssText = "background:none;border:none;color:#8A829E;cursor:pointer;font-size:11px;padding:0 3px";
        rm.onclick = async (ev) => {
          ev.stopPropagation();
          await api?.pano_shelf_remove?.(x.id).catch(() => {});
          refresh();
        };
        d.appendChild(rm);
      }
      list.appendChild(d);
    }
  }

  async function refresh() {
    if (typeof api !== "undefined" && api.pano_shelf_list) {
      try {
        const r = await api.pano_shelf_list();
        PANO.items = r?.items || [];
      } catch { PANO.items = []; }
    }
    renderList();
  }

  function mountPano() {
    if (document.getElementById("kamiPanoDock")) return;
    const ico = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/></svg>`;
    const rail = document.getElementById("skDock");
    const dock = document.createElement("button");
    dock.id = "kamiPanoDock";
    dock.type = "button";
    dock.title = "Kami Pano Rafı";
    dock.setAttribute("aria-label", "Kami Pano Rafı");
    if (rail) {   // v1.31.1: sag altigen menude, diger simgelerle ayni gorunum (eskiden komut satirinin Indir dugmesine biniyordu)
      dock.dataset.sk = "pano";
      dock.innerHTML = ico;
      const st = rail.querySelector('[data-sk="settings"]');
      rail.insertBefore(dock, st || null);
    } else {
      dock.style.cssText = "position:fixed;right:18px;top:50%;z-index:55;width:36px;height:36px;display:grid;place-items:center;background:rgba(17,14,23,.92);border:1px solid rgba(139,92,246,.45);color:#C4B5FD;cursor:pointer;border-radius:10px";
      dock.innerHTML = ico.replace("<svg ", '<svg width="16" height="16" ');
      document.body.appendChild(dock);
    }

    const drawer = document.createElement("div");
    drawer.id = "kamiPanoDrawer";
    drawer.style.cssText = "position:fixed;z-index:56;width:320px;max-height:420px;overflow:auto;background:rgba(13,10,20,.96);border:1px solid rgba(139,92,246,.5);padding:10px;color:#EDE9F6;font:12px 'Chakra Petch',sans-serif;display:none;gap:8px;clip-path:polygon(10px 0,100% 0,100% calc(100% - 10px),calc(100% - 10px) 100%,0 100%,0 10px);box-shadow:0 12px 32px rgba(0,0,0,.6)";
    drawer.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid rgba(139,92,246,.25);padding-bottom:6px"><b style="color:#C4B5FD;letter-spacing:.05em">PANO RAFI</b><span style="flex:1"></span><button id="kpClear" type="button" title="Rafı temizle" style="background:none;border:1px solid rgba(139,92,246,.35);color:#A39BB5;cursor:pointer;font-size:10px;padding:1px 6px;margin-right:6px">Temizle</button><button id="kpClose" type="button" style="background:none;border:none;color:#A39BB5;cursor:pointer;font-size:13px">✕</button></div><input id="kpSearch" type="search" placeholder="Metin, link veya görsel OCR ara..." style="width:100%;box-sizing:border-box;padding:5px 8px;border-radius:6px;border:1px solid rgba(139,92,246,.3);background:#08060D;color:#EDE9F6;font:inherit;font-size:11px;outline:none"><div id="kpTools" style="display:flex;gap:4px;flex-wrap:wrap"><button type="button" data-tr="json" style="background:#1A132B;border:1px solid rgba(139,92,246,.32);color:#D8D2E8;border-radius:5px;padding:2px 6px;font-size:10px;cursor:pointer">JSON Biçimle</button><button type="button" data-tr="url" style="background:#1A132B;border:1px solid rgba(139,92,246,.32);color:#D8D2E8;border-radius:5px;padding:2px 6px;font-size:10px;cursor:pointer">URL Temizle</button><button type="button" data-tr="b64" style="background:#1A132B;border:1px solid rgba(139,92,246,.32);color:#D8D2E8;border-radius:5px;padding:2px 6px;font-size:10px;cursor:pointer">Base64</button><button type="button" data-tr="case" style="background:#1A132B;border:1px solid rgba(139,92,246,.32);color:#D8D2E8;border-radius:5px;padding:2px 6px;font-size:10px;cursor:pointer">BÜYÜK/küçük</button><button type="button" data-pt="pick" style="background:#1A132B;border:1px solid rgba(139,92,246,.32);color:#D8D2E8;border-radius:5px;padding:2px 6px;font-size:10px;cursor:pointer">🎨 Renk Seç</button><button type="button" data-pt="measure" style="background:#1A132B;border:1px solid rgba(139,92,246,.32);color:#D8D2E8;border-radius:5px;padding:2px 6px;font-size:10px;cursor:pointer">📏 Ölç</button></div><div id="kpMsg" style="font-size:10px;color:#2EE6A6;min-height:13px"></div><div id="kpList" style="display:grid;grid-template-columns:minmax(0,1fr);gap:5px;min-width:0"></div>`;
    const place = () => {   // dugmenin soluna, ekrandan tasmadan
      const r = dock.getBoundingClientRect();
      drawer.style.right = Math.max(8, innerWidth - r.left + 10) + "px";
      drawer.style.top = Math.max(8, Math.min(innerHeight - 430, r.top - 140)) + "px";
    };
    const close = () => { PANO.open = false; drawer.style.display = "none"; dock.classList.remove("on"); };
    dock.onclick = async (e) => {
      e.stopPropagation();
      PANO.open = !PANO.open;
      if (!PANO.open) return close();
      place(); drawer.style.display = "grid"; dock.classList.add("on");
      await refresh();
    };
    document.body.appendChild(drawer);
    document.getElementById("kpSearch")?.addEventListener("input", (e) => { PANO.q = e.target.value || ""; renderList(); });
    drawer.querySelectorAll("#kpTools [data-tr]").forEach((btn) => { btn.onclick = (e) => { e.stopPropagation(); runTransform(btn.dataset.tr); }; });
    drawer.querySelectorAll("#kpTools [data-pt]").forEach((btn) => { btn.onclick = (e) => { e.stopPropagation(); ptStart(btn.dataset.pt); }; });
    document.getElementById("kpClose")?.addEventListener("click", close);
    document.getElementById("kpClear")?.addEventListener("click", async (e) => { e.stopPropagation(); await api?.pano_shelf_clear?.().catch(() => {}); refresh(); });
    setInterval(() => { if (PANO.open) refresh(); }, 2500);   // acikken yeni kopyalar canli gelsin
    document.addEventListener("click", (e) => { if (PANO.open && !drawer.contains(e.target) && e.target !== dock) close(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && PANO.open) close(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && PTOOL.on) ptCancel(); });
    addEventListener("resize", () => PANO.open && place());
  }

  function boot() { if (document.getElementById("skDock") || document.readyState === "complete") mountPano(); else setTimeout(boot, 200); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();

  window.KamiPano = { state: PANO, mountPano, refresh };
})();
