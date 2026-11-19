/* Kami Picture v1.38.0: Akilli kontroller, Beautify Background bestecisi, Ekrana Sabitleme (Pin) ve Lens Quick Capturer. */
"use strict";
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const tr = () => (navigator.language || "tr").toLowerCase().startsWith("tr");
  const T = (a, b) => (tr() ? a : b);

  if (!document.getElementById("picV138Style")) {
    const st = document.createElement("style");
    st.id = "picV138Style";
    st.textContent = `
      [hidden] { display: none !important; }
      .pc-top button[disabled] { opacity: .34; cursor: not-allowed; pointer-events: none; filter: saturate(.4); }
      .pc-nav[hidden] { display: none !important; }
      .pc-top button svg { flex: none; }
      .pc-beautify {
        width: 332px; max-width: 38vw; flex: none;
        background: #0D0A14; border-left: 1px solid rgba(157,107,255,.22);
        display: flex; flex-direction: column; gap: 10px; padding: 12px 14px;
        overflow-y: auto; color: #EDE9F6; font: 500 12px "Chakra Petch", system-ui, sans-serif;
      }
      .pcb-hd { display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,.08); padding-bottom: 8px; }
      .pcb-hd b { font-size: 13px; color: #C4B5FD; letter-spacing: .04em; }
      .pcb-close { background: none; border: 1px solid rgba(255,255,255,.12); color: #A39BB5; border-radius: 6px; padding: 2px 7px; cursor: pointer; font: inherit; }
      .pcb-prev {
        width: 100%; aspect-ratio: 16/10; background: #07050B; border: 1px solid rgba(157,107,255,.22);
        border-radius: 10px; display: grid; place-items: center; overflow: hidden; padding: 6px;
      }
      .pcb-prev canvas { max-width: 100%; max-height: 100%; display: block; border-radius: 6px; }
      .pcb-lbl { font-size: 11px; color: #A39BB5; display: flex; justify-content: space-between; align-items: center; }
      .pcb-presets { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
      .pcb-sw {
        height: 28px; border-radius: 7px; border: 1.5px solid rgba(255,255,255,.14); cursor: pointer;
        position: relative; overflow: hidden; padding: 0;
      }
      .pcb-sw.on { border-color: #2EE6A6; box-shadow: 0 0 0 1px #2EE6A6; }
      .pcb-rng { width: 100%; accent-color: #8B5CF6; cursor: pointer; }
      .pcb-chk { display: flex; align-items: center; gap: 8px; font-size: 11.5px; color: #D8D2E8; cursor: pointer; }
      .pcb-acts { display: flex; gap: 7px; margin-top: 4px; }
      .pcb-btn {
        flex: 1; padding: 8px 10px; border-radius: 7px; border: 1px solid rgba(157,107,255,.35);
        background: #1A132B; color: #EDE9F6; font: 600 11.5px "Chakra Petch", sans-serif; cursor: pointer;
      }
      .pcb-btn.pri { background: linear-gradient(135deg, #6D28D9, #2EE6A6); color: #09070E; border: 0; }
      .pcb-msg { font-size: 11px; color: #2EE6A6; min-height: 15px; }
    `;
    document.head.appendChild(st);
  }

  const PRESETS = [
    { id: "obsidian", name: "Obsidian Aura", c1: "#0D0A12", c2: "#29144E", c3: "#0A2A22" },
    { id: "emerald", name: "Emerald Prism", c1: "#071814", c2: "#105946", c3: "#0D0A14" },
    { id: "violet", name: "Sunak Violet", c1: "#1D1036", c2: "#6D28D9", c3: "#120B21" },
    { id: "crimson", name: "Ruh Atesi", c1: "#1A0A14", c2: "#6B1237", c3: "#120D1A" },
    { id: "carbon", name: "Carbon Minimal", c1: "#131218", c2: "#24222D", c3: "#111015" },
    { id: "frost", name: "Light Frost", c1: "#F4F1FC", c2: "#DDD6FE", c3: "#C7F9E5" },
  ];

  const B = {
    open: false,
    path: "",
    img: null,
    preset: "obsidian",
    pad: 64,
    radius: 16,
    shadow: 36,
    scale: 0.96,
    frame: true,
  };

  function getActivePC() {
    const empty = $("#pcEmpty");
    const hasEmpty = empty && !empty.hidden;
    const imgEl = $("#pcImg");
    const hasImg = !hasEmpty && Boolean(imgEl?.getAttribute("src") || (window.PC?.list?.length));
    const count = Number(window.PC?.list?.length || 0);
    return { hasImg, count };
  }

  function syncControls(pc) {
    const empty = $("#pcEmpty");
    const count = pc ? (pc.list || []).length : getActivePC().count;
    const hasImg = pc
      ? Boolean((pc.list || []).length && pc.list[pc.i])
      : Boolean(empty && empty.hidden);

    document.querySelectorAll(".pc-top button[data-need-img]").forEach((btn) => {
      btn.disabled = !hasImg;
    });
    document.querySelectorAll(".pc-nav").forEach((nav) => {
      nav.hidden = !(hasImg && count >= 2);
    });
    if (!hasImg && B.open) closeBeautify();
  }

  function roundRectPath(ctx, x, y, w, h, r) {
    const rr = Math.min(r, w / 2, h / 2);
    ctx.beginPath();
    ctx.moveTo(x + rr, y);
    ctx.arcTo(x + w, y, x + w, y + h, rr);
    ctx.arcTo(x + w, y + h, x, y + h, rr);
    ctx.arcTo(x, y + h, x, y, rr);
    ctx.arcTo(x, y, x + w, y, rr);
    ctx.closePath();
  }

  function composeCanvas(forExport = false) {
    const cvs = $("#pcbCvs");
    const img = B.img;
    if (!cvs || !img) return null;
    const maxSide = forExport ? 2200 : 720;
    const ratio = Math.min(1, maxSide / Math.max(img.naturalWidth || 1, img.naturalHeight || 1));
    const iw = Math.max(32, Math.round((img.naturalWidth || 400) * ratio * B.scale));
    const ih = Math.max(32, Math.round((img.naturalHeight || 300) * ratio * B.scale));
    const pad = Math.round(B.pad * (forExport ? ratio : Math.max(0.45, ratio)));
    const cw = iw + pad * 2;
    const ch = ih + pad * 2;
    const out = forExport ? document.createElement("canvas") : cvs;
    out.width = cw;
    out.height = ch;
    const ctx = out.getContext("2d");
    const pr = PRESETS.find((p) => p.id === B.preset) || PRESETS[0];

    const gr = ctx.createLinearGradient(0, 0, cw, ch);
    gr.addColorStop(0, pr.c1);
    gr.addColorStop(0.55, pr.c2);
    gr.addColorStop(1, pr.c3);
    ctx.fillStyle = gr;
    ctx.fillRect(0, 0, cw, ch);

    const orb1 = ctx.createRadialGradient(cw * 0.2, ch * 0.22, 0, cw * 0.2, ch * 0.22, Math.max(cw, ch) * 0.65);
    orb1.addColorStop(0, "rgba(157,107,255,0.22)");
    orb1.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = orb1;
    ctx.fillRect(0, 0, cw, ch);

    const r = Math.round(B.radius * (forExport ? ratio : Math.max(0.5, ratio)));
    ctx.save();
    ctx.shadowColor = "rgba(0,0,0,0.58)";
    ctx.shadowBlur = Math.round(B.shadow * (forExport ? ratio : Math.max(0.5, ratio)));
    ctx.shadowOffsetY = Math.round(B.shadow * 0.28 * (forExport ? ratio : 0.6));
    roundRectPath(ctx, pad, pad, iw, ih, r);
    ctx.fillStyle = "#000";
    ctx.fill();
    ctx.restore();

    ctx.save();
    roundRectPath(ctx, pad, pad, iw, ih, r);
    ctx.clip();
    ctx.drawImage(img, pad, pad, iw, ih);
    ctx.restore();

    if (B.frame) {
      ctx.save();
      roundRectPath(ctx, pad + 0.5, pad + 0.5, iw - 1, ih - 1, r);
      ctx.strokeStyle = B.preset === "frost" ? "rgba(15,10,30,0.16)" : "rgba(255,255,255,0.16)";
      ctx.lineWidth = Math.max(1, Math.round(ratio * 1.5));
      ctx.stroke();
      ctx.restore();
    }
    return out;
  }

  function closeBeautify() {
    B.open = false;
    const panel = $("#pcBeautify");
    if (panel) panel.hidden = true;
    document.querySelector('[data-a="beautify"]')?.classList.remove("on");
  }

  async function openBeautify(path) {
    const panel = $("#pcBeautify");
    if (!panel || !path) return;
    if (B.open && B.path === path) return closeBeautify();
    const lens = $("#pcLens");
    if (lens && !lens.hidden) {
      lens.hidden = true;
      document.querySelector('[data-a="lens"]')?.classList.remove("on");
    }
    B.open = true;
    B.path = path;
    document.querySelector('[data-a="beautify"]')?.classList.add("on");
    panel.hidden = false;
    panel.innerHTML = `
      <div class="pcb-hd"><b>BEAUTIFY ARKA PLAN</b><button class="pcb-close" id="pcbClose">✕</button></div>
      <div class="pcb-prev"><canvas id="pcbCvs"></canvas></div>
      <div class="pcb-lbl"><span>${T("Tema", "Backdrop")}</span><span id="pcbThemeName"></span></div>
      <div class="pcb-presets">${PRESETS.map((p) => `<button type="button" class="pcb-sw${p.id === B.preset ? " on" : ""}" data-pre="${p.id}" title="${p.name}" style="background:linear-gradient(135deg,${p.c1},${p.c2},${p.c3})"></button>`).join("")}</div>
      <label class="pcb-lbl"><span>${T("Dış Boşluk", "Padding")}</span><b id="pcbPadV">${B.pad}px</b></label>
      <input class="pcb-rng" id="pcbPad" type="range" min="16" max="140" value="${B.pad}">
      <label class="pcb-lbl"><span>${T("Köşe Ovalliği", "Radius")}</span><b id="pcbRadV">${B.radius}px</b></label>
      <input class="pcb-rng" id="pcbRad" type="range" min="0" max="40" value="${B.radius}">
      <label class="pcb-lbl"><span>${T("Gölge", "Shadow")}</span><b id="pcbShdV">${B.shadow}px</b></label>
      <input class="pcb-rng" id="pcbShd" type="range" min="0" max="72" value="${B.shadow}">
      <label class="pcb-chk"><input type="checkbox" id="pcbFrame" ${B.frame ? "checked" : ""}> ${T("İnce cam kenarlık", "Subtle glass border")}</label>
      <div class="pcb-acts">
        <button type="button" class="pcb-btn" id="pcbCopy">${T("Panoya Kopyala", "Copy PNG")}</button>
        <button type="button" class="pcb-btn pri" id="pcbSave">${T("PNG Kaydet", "Save PNG")}</button>
      </div>
      <div class="pcb-msg" id="pcbMsg"></div>
    `;

    $("#pcbClose").onclick = closeBeautify;
    const updTheme = () => {
      const pr = PRESETS.find((x) => x.id === B.preset);
      const tn = $("#pcbThemeName");
      if (tn && pr) tn.textContent = pr.name;
    };
    updTheme();
    panel.querySelectorAll("[data-pre]").forEach((sw) => {
      sw.onclick = () => {
        B.preset = sw.dataset.pre;
        panel.querySelectorAll("[data-pre]").forEach((s) => s.classList.toggle("on", s === sw));
        updTheme();
        composeCanvas(false);
      };
    });
    $("#pcbPad").oninput = (e) => { B.pad = Number(e.target.value); $("#pcbPadV").textContent = B.pad + "px"; composeCanvas(false); };
    $("#pcbRad").oninput = (e) => { B.radius = Number(e.target.value); $("#pcbRadV").textContent = B.radius + "px"; composeCanvas(false); };
    $("#pcbShd").oninput = (e) => { B.shadow = Number(e.target.value); $("#pcbShdV").textContent = B.shadow + "px"; composeCanvas(false); };
    $("#pcbFrame").onchange = (e) => { B.frame = e.target.checked; composeCanvas(false); };

    $("#pcbCopy").onclick = async () => {
      const out = composeCanvas(true);
      const msg = $("#pcbMsg");
      if (!out) return;
      try {
        const blob = await new Promise((res) => out.toBlob(res, "image/png"));
        if (blob && navigator.clipboard && window.ClipboardItem) {
          await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
          if (msg) msg.textContent = T("Panoya kopyalandı ✓", "Copied to clipboard ✓");
          return;
        }
      } catch { /* fallback below */ }
      try {
        const r = await window.pywebview?.api?.picture_save_data_url?.(out.toDataURL("image/png"), B.path, "_beautify");
        if (msg) msg.textContent = r?.ok ? `${T("Kaydedildi:", "Saved:")} ${r.path}` : (r?.error || T("Kopyalanamadı", "Failed"));
      } catch (err) {
        if (msg) msg.textContent = String(err || "Hata");
      }
    };

    $("#pcbSave").onclick = async () => {
      const out = composeCanvas(true);
      const msg = $("#pcbMsg");
      if (!out) return;
      const res = await window.pywebview?.api?.picture_save_data_url?.(out.toDataURL("image/png"), B.path, "_beautify");
      if (msg) msg.textContent = res?.ok ? `${T("Kaydedildi:", "Saved:")} ${res.path.split(/[\\/]/).pop()}` : (res?.error || T("Kaydedilemedi", "Failed"));
    };

    // Load taint-free image source via backend base64 or #pcImg fallback
    let src = "";
    try {
      const d = await window.pywebview?.api?.picture_data_url?.(path);
      if (d?.ok && d.url) src = d.url;
    } catch { /* fallback */ }
    if (!src) src = $("#pcImg")?.src || "";
    if (!src) return;
    const im = new Image();
    im.onload = () => { B.img = im; composeCanvas(false); };
    im.src = src;
  }

  async function action(a, path) {
    const bridge = window.pywebview?.api;
    if (a === "grab") {
      await bridge?.lens_capture_quick?.().catch(() => {});
      return;
    }
    if (!path) return;
    if (a === "beautify") return openBeautify(path);
    if (a === "pin") {
      await bridge?.picture_pin?.(path).catch(() => {});
    }
  }

  function boot() {
    syncControls(null);
    const empty = $("#pcEmpty");
    if (empty && window.MutationObserver) {
      new MutationObserver(() => syncControls(null)).observe(empty, { attributes: true, attributeFilter: ["hidden"] });
    }
    document.addEventListener("keydown", (e) => {
      const tag = (e.target?.tagName || "").toUpperCase();
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "Escape" && B.open) { closeBeautify(); return; }
      const p = window.PC?.list?.[window.PC?.i];
      if (!p) return;
      if (e.key === "b" || e.key === "B") openBeautify(p);
      else if (e.key === "p" || e.key === "P") action("pin", p);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();

  window.kamiPicV138 = { syncControls, action, openBeautify, closeBeautify };
})();
