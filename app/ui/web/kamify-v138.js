// Kamify v2.0.0 — Dinamik Ada Toggle, Type-to-Search, MP3 Whisper Guclu Mod, Canli LRC Editoru & Dinleme Gunlugu
"use strict";
(() => {
  const callApi = () => (typeof api === "function" ? api() : window.pywebview?.api);
  const $id = (s) => document.getElementById(s);
  const css = document.createElement("style");
  css.textContent = `
    #kfTypeFilter{position:fixed;right:20px;bottom:104px;z-index:45;background:rgba(16,12,26,.96);border:1px solid var(--ac);border-radius:10px;padding:6px 10px;display:flex;align-items:center;gap:8px;box-shadow:0 12px 30px rgba(0,0,0,.6);font:600 12px "Chakra Petch",sans-serif}
    #kfTypeFilter b{color:var(--em)}#kfTypeFilter button{border:0;background:none;color:var(--mut);cursor:pointer}
  `;
  document.head.appendChild(css);

  // ---- 1. Dinamik Ada quick toggle ----
  const dynBtn = $id("kfDynAdaBtn");
  if (dynBtn) {
    let dynOn = true;
    const syncDyn = () => {
      dynBtn.classList.toggle("pri", dynOn);
      dynBtn.textContent = dynOn ? "Dinamik Ada: Açık" : "Dinamik Ada: Kapalı";
    };
    const initDyn = async () => {
      try {
        const s = await callApi()?.get_settings?.();
        if (s && "island_music_expand" in s) dynOn = s.island_music_expand !== false;
        syncDyn();
      } catch {}
    };
    dynBtn.onclick = async () => {
      dynOn = !dynOn;
      syncDyn();
      await callApi()?.set_setting?.("island_music_expand", dynOn);
      if (typeof mToast === "function") mToast(dynOn ? "✓ Mini-Ada hover'da kapak rengiyle genişler" : "Mini-Ada sabit kompakt modda kalır");
    };
    window.addEventListener("pywebviewready", initDyn);
    setTimeout(initDyn, 400);
  }

  // ---- 2. Global Type-to-Search Filter (Tauon) ----
  let typeQuery = "", filterBox = null, typeTimer = 0;
  function applyTypeFilter() {
    if (!filterBox && !typeQuery) return;
    if (!filterBox) {
      filterBox = document.createElement("div"); filterBox.id = "kfTypeFilter";
      filterBox.innerHTML = '<span>Süzgeç:</span><b id="kfTfQ"></b><button id="kfTfX">✕</button>';
      document.body.appendChild(filterBox);
      filterBox.querySelector("#kfTfX").onclick = () => { typeQuery = ""; applyTypeFilter(); };
    }
    filterBox.hidden = !typeQuery;
    filterBox.querySelector("#kfTfQ").textContent = typeQuery;
    const low = typeQuery.toLocaleLowerCase("tr");
    document.querySelectorAll("#list .row, #list .acard").forEach((el) => {
      el.hidden = low ? !el.textContent.toLocaleLowerCase("tr").includes(low) : false;
    });
  }
  document.addEventListener("keydown", (e) => {
    if (e.target.matches?.("input, textarea, select") || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "Escape" && typeQuery) { typeQuery = ""; applyTypeFilter(); return; }
    if (e.key === "Backspace" && typeQuery) { typeQuery = typeQuery.slice(0, -1); applyTypeFilter(); e.preventDefault(); return; }
    if (e.key.length === 1 && /[\p{L}\p{N} ]/u.test(e.key)) {
      if (typeQuery.length < 30) { typeQuery += e.key; applyTypeFilter(); }
      clearTimeout(typeTimer); typeTimer = setTimeout(() => { if (filterBox && !typeQuery) filterBox.hidden = true; }, 4000);
    }
  });

  // ---- 6. Kami 2.0: MP3 Whisper Guclu Sarki Modu + Canli LRC Editoru + B8 Dinleme Gunlugu ----
  const lrcCss = document.createElement("style");
  lrcCss.textContent = `
    .kf-lrc-ov { position:fixed; inset:0; z-index:88; background:rgba(5,4,10,.84); backdrop-filter:blur(8px); display:grid; place-items:center; padding:18px; }
    .kf-lrc-box { width:min(760px,95vw); max-height:90vh; background:#120E1D; border:1px solid var(--ac); border-radius:14px; padding:16px 18px; display:flex; flex-direction:column; gap:10px; color:#EDE9F6; }
    .kf-lrc-rows { flex:1; overflow-y:auto; max-height:46vh; display:flex; flex-direction:column; gap:5px; padding-right:4px; }
    .kf-lrc-row { display:grid; grid-template-columns:82px 74px 1fr 28px; gap:7px; align-items:center; background:#181226; border:1px solid var(--line); border-radius:8px; padding:5px 8px; }
    .kf-lrc-row.cur { border-color:var(--em); background:rgba(46,230,166,.08); }
    .kf-lrc-row input { background:#0B0812; border:1px solid var(--line); border-radius:6px; color:#fff; padding:5px 8px; font:inherit; width:100%; }
  `;
  document.head.appendChild(lrcCss);

  function fmtLrcSec(sec) {
    if (sec == null || sec < 0 || !Number.isFinite(sec)) return "--:--.--";
    const m = Math.floor(sec / 60), s = (sec % 60).toFixed(2).padStart(5, "0");
    return `${String(m).padStart(2, "0")}:${s}`;
  }
  function parseLrcSec(str) {
    const m = String(str || "").trim().match(/^(\d+):(\d+(?:\.\d+)?)$/);
    return m ? (parseInt(m[1], 10) * 60 + parseFloat(m[2])) : -1;
  }

  async function openLrcEditor(path, titleHint = "") {
    if (!path) return;
    const r = await callApi()?.music_lrc_read?.(path).catch(() => null);
    let rows = (r?.lines && r.lines.length)
      ? r.lines.map((x) => ({ t: Number(x.t ?? -1), text: String(x.text || "") }))
      : [{ t: 0, text: "" }];
    let activeRow = 0;

    const ov = document.createElement("div");
    ov.className = "kf-lrc-ov";
    ov.innerHTML = `
      <div class="kf-lrc-box">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:8px">
          <b>🎤 Canlı LRC & Zaman Damgası Editörü · <span style="color:var(--em)">${(titleHint || path.split(/[\\/]/).pop()).replace(/</g, "&lt;")}</span></b>
          <button class="btn" id="kfLrcX">✕</button>
        </div>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;background:#0B0812;padding:8px 10px;border-radius:10px;border:1px solid var(--line)">
          <audio id="kfLrcAudio" controls style="flex:1;height:32px"></audio>
          <label style="font-size:11.5px;display:flex;align-items:center;gap:5px"><input type="checkbox" id="kfStrongChk" checked> <b>Güçlü Mod</b> (UVR5 Vokal Ayır + Tam Rap Algılama)</label>
          <button class="btn pri" id="kfRunWhisper">🎙 Whisper ile Söz Çıkar</button>
          <button class="btn" id="kfAlignReal" title="Whisper zaman damgalarını gerçek şarkı sözleriyle hizala">🎯 Söz Eşleştir</button>
          <button class="btn" id="kfWordSync" title="Satırları kelimelere bölerek zamanları otomatik hizala">🔤 Kelime Senkronu</button>
          <button class="btn" id="kfRunOllama" title="Yerel Ollama (qwen2.5:3b) ile yazım hatalarını düzelt">✨ Ollama ile Düzelt</button>
        </div>
        <div id="kfAlignBox" hidden style="display:flex;flex-direction:column;gap:6px;background:#0D0A16;padding:8px 10px;border-radius:10px;border:1px solid rgba(46,230,166,.38)">
          <textarea id="kfAlignTrue" rows="5" placeholder="Gerçek şarkı sözlerini buraya yapıştır (Genius vb.) — mevcut zaman damgalarıyla eşlenecek…" style="width:100%;background:#09070F;border:1px solid var(--line);border-radius:8px;color:#EDE9F6;padding:8px;font:12px Consolas,monospace"></textarea>
          <div style="display:flex;justify-content:flex-end"><button class="btn pri" id="kfAlignGo">⚡ Hizala &amp; Uygula</button></div>
        </div>
        <div style="font-size:11.5px;color:var(--mut);display:flex;justify-content:space-between;align-items:center">
          <span>İpucu: Şarkı çalarken <b>[Damgala (F8)]</b> tuşuyla aktif satıra anlık zaman damgası vurup alt satıra geçebilirsin.</span>
          <div style="display:flex;gap:6px">
            <button class="btn" id="kfAddRow">+ Satır Ekle</button>
            <button class="btn" id="kfRawToggle">Ham .LRC Metni</button>
          </div>
        </div>
        <div class="kf-lrc-rows" id="kfLrcRows"></div>
        <textarea id="kfLrcRaw" rows="10" hidden style="width:100%;background:#09070F;border:1px solid var(--line);border-radius:8px;color:#EDE9F6;padding:10px;font:12.5px Consolas,monospace"></textarea>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span id="kfLrcSt" style="font-size:12px;color:var(--em)"></span>
          <div style="display:flex;gap:8px">
            <button class="btn" id="kfStampNext">⏱ Aktif Satırı Damgala & İlerle (F8)</button>
            <button class="btn pri" id="kfSaveLrc">💾 .LRC + MP3 İçine Kaydet</button>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(ov);

    const aud = ov.querySelector("#kfLrcAudio");
    callApi()?.player_open_path?.(path).then((m) => { if (m?.url) aud.src = m.url; }).catch(() => {});

    const rowsBox = ov.querySelector("#kfLrcRows");
    const rawBox = ov.querySelector("#kfLrcRaw");
    const stEl = ov.querySelector("#kfLrcSt");

    function rowsToRaw() {
      return rows.filter((x) => x.text.trim()).map((x) => (x.t >= 0 ? `[${fmtLrcSec(x.t)}]${x.text.trim()}` : x.text.trim())).join("\n");
    }
    function rawToRows(txt) {
      const out = [];
      for (const ln of String(txt || "").split(/\r?\n/)) {
        const s = ln.trim();
        if (!s) continue;
        const m = s.match(/^\[(\d+:\d+(?:\.\d+)?)\]\s*(.*)$/);
        if (m) out.push({ t: parseLrcSec(m[1]), text: m[2] });
        else if (!s.startsWith("[")) out.push({ t: -1, text: s });
      }
      return out.length ? out : [{ t: 0, text: "" }];
    }

    function drawRows() {
      rowsBox.innerHTML = rows.map((r, i) => `
        <div class="kf-lrc-row${i === activeRow ? " cur" : ""}" data-idx="${i}">
          <input class="ts-in" value="${fmtLrcSec(r.t)}" data-tsi="${i}" title="Zaman (dd:ss.ms)">
          <button class="btn" data-stamp="${i}" style="padding:4px 6px;font-size:11px">⏱ Damgala</button>
          <input class="tx-in" value="${r.text.replace(/"/g, "&quot;")}" data-txi="${i}" placeholder="Şarkı sözü satırı…">
          <button class="btn" data-del="${i}" style="padding:3px 6px;color:#FB7185">✕</button>
        </div>
      `).join("");
      rowsBox.querySelectorAll(".ts-in").forEach((inp) => {
        inp.onchange = () => { rows[+inp.dataset.tsi].t = parseLrcSec(inp.value); };
      });
      rowsBox.querySelectorAll(".tx-in").forEach((inp) => {
        inp.onfocus = () => { activeRow = +inp.dataset.txi; };
        inp.oninput = () => { rows[+inp.dataset.txi].text = inp.value; };
      });
      rowsBox.querySelectorAll("[data-stamp]").forEach((b) => {
        b.onclick = () => {
          const idx = +b.dataset.stamp;
          rows[idx].t = Number(aud.currentTime || 0);
          activeRow = Math.min(rows.length - 1, idx + 1);
          drawRows();
        };
      });
      rowsBox.querySelectorAll("[data-del]").forEach((b) => {
        b.onclick = () => {
          rows.splice(+b.dataset.del, 1);
          if (!rows.length) rows.push({ t: 0, text: "" });
          drawRows();
        };
      });
    }
    drawRows();

    ov.querySelector("#kfAddRow").onclick = () => {
      rows.push({ t: Number(aud.currentTime || 0), text: "" });
      activeRow = rows.length - 1;
      drawRows();
    };
    ov.querySelector("#kfRawToggle").onclick = () => {
      if (rawBox.hidden) {
        rawBox.value = rowsToRaw();
        rawBox.hidden = false;
        rowsBox.hidden = true;
      } else {
        rows = rawToRows(rawBox.value);
        rawBox.hidden = true;
        rowsBox.hidden = false;
        drawRows();
      }
    };
    const stampAndAdvance = () => {
      if (!rawBox.hidden) rows = rawToRows(rawBox.value);
      if (rows[activeRow]) {
        rows[activeRow].t = Number(aud.currentTime || 0);
        activeRow = Math.min(rows.length - 1, activeRow + 1);
        drawRows();
        rowsBox.querySelector(`.kf-lrc-row[data-idx="${activeRow}"]`)?.scrollIntoView({ block: "nearest" });
      }
    };
    ov.querySelector("#kfStampNext").onclick = stampAndAdvance;
    const onKey = (e) => {
      if (e.key === "F8") { e.preventDefault(); stampAndAdvance(); }
      else if (e.key === "Escape") { closeOv(); }
    };
    document.addEventListener("keydown", onKey);
    function closeOv() {
      document.removeEventListener("keydown", onKey);
      try { aud.pause(); } catch {}
      ov.remove();
    }
    ov.querySelector("#kfLrcX").onclick = closeOv;

    ov.querySelector("#kfRunWhisper").onclick = async () => {
      const strong = ov.querySelector("#kfStrongChk").checked;
      stEl.textContent = strong
        ? "🎙 UVR5 ile vokal ayrılıyor + Whisper Güçlü Mod ile tüm satırlar çıkarılıyor…"
        : "🎙 Whisper ile zaman damgalı söz çıkarılıyor…";
      const res = await callApi()?.music_whisper_lrc?.(path, "tr", strong).catch((e) => ({ ok: false, error: String(e) }));
      if (!res?.ok) {
        stEl.textContent = "✕ Hata: " + (res?.error === "tool_missing" ? "Önce Kami AI'dan Whisper aracını kur" : (res?.error || "çıkarılamadı"));
        return;
      }
      let finalRes = res;
      if (res.queued && res.job_id && callApi()?.music_lrc_job_status) {
        for (let step = 0; step < 300; step++) {
          await new Promise((r2) => setTimeout(r2, 1500));
          const jst = await callApi().music_lrc_job_status(res.job_id).catch(() => null);
          if (!jst?.ok) continue;
          if (jst.state === "running") {
            stEl.textContent = `${jst.msg || "İşleniyor…"} · %${Math.round((jst.p || 0) * 100)}`;
            continue;
          }
          finalRes = jst.result || { ok: jst.state === "done", error: jst.msg };
          break;
        }
      }
      if (finalRes?.ok) {
        rows = (finalRes.lines && finalRes.lines.length)
          ? finalRes.lines.map((x) => ({ t: Number(x.t ?? 0), text: String(x.text || "") }))
          : rawToRows(finalRes.lrc_text || "");
        rawBox.value = finalRes.lrc_text || rowsToRaw();
        drawRows();
        stEl.textContent = `✓ ${rows.length} satır çıkarıldı ve .lrc olarak kaydedildi (${finalRes.uvr_used ? "UVR5 Vokal + " : ""}Güçlü Mod)`;
      } else {
        stEl.textContent = "✕ Hata: " + (finalRes?.error === "tool_missing" ? "Önce Kami AI'dan Whisper aracını kur" : (finalRes?.error || "çıkarılamadı"));
      }
    };

    const kfAlignBox = ov.querySelector("#kfAlignBox");
    ov.querySelector("#kfAlignReal").onclick = () => {
      kfAlignBox.hidden = !kfAlignBox.hidden;
      if (!kfAlignBox.hidden) ov.querySelector("#kfAlignTrue")?.focus();
    };
    ov.querySelector("#kfAlignGo").onclick = () => {
      const trueTxt = ov.querySelector("#kfAlignTrue").value.trim();
      const rawTxt = (!rawBox.hidden && rawBox.value.trim()) ? rawBox.value : rowsToRaw();
      if (!trueTxt || !rawTxt.trim()) { stEl.textContent = "Hem zaman damgalı LRC hem gerçek sözler gerekli"; return; }
      if (!window.KamiLrcAlign) { stEl.textContent = "Hizalayıcı yüklenemedi"; return; }
      const aligned = window.KamiLrcAlign(rawTxt, trueTxt);
      rawBox.value = aligned;
      rows = rawToRows(aligned);
      drawRows();
      kfAlignBox.hidden = true;
      stEl.textContent = "✓ Sözler kelime zamanlarıyla hizalandı — Kaydet'e bas!";
    };

    ov.querySelector("#kfRunOllama").onclick = async () => {
      const curRaw = rawBox.hidden ? rowsToRaw() : rawBox.value;
      if (!curRaw.trim()) { stEl.textContent = "Önce söz çıkar veya yapıştır."; return; }
      stEl.textContent = "✨ Yerel Ollama (qwen2.5:3b) ile yazım düzeltiliyor…";
      const res = await callApi()?.music_lrc_polish_ollama?.(curRaw, titleHint, "").catch(() => null);
      if (res?.ok && res.text) {
        rows = rawToRows(res.text);
        rawBox.value = res.text;
        drawRows();
        stEl.textContent = `✓ Ollama (${res.model}) ile düzeltildi`;
      } else {
        stEl.textContent = "✕ Ollama yanıt vermedi (" + (res?.error || "kapalı") + ")";
      }
    };

    ov.querySelector("#kfWordSync").onclick = async () => {
      const curRaw = (!rawBox.hidden && rawBox.value.trim()) ? rawBox.value : rowsToRaw();
      if (!curRaw.trim()) { stEl.textContent = "Önce söz çıkar veya LRC yapıştır."; return; }
      stEl.textContent = "🔤 Kelime zamanları hesaplanıyor…";
      const dur = Number(aud.duration || 0);
      const res = await callApi()?.lyrics_word_sync?.(curRaw, dur).catch(() => null);
      if (res?.ok && Array.isArray(res.lines) && res.lines.length) {
        rows = res.lines.map((x) => ({ t: Number(x.start ?? 0), text: String(x.text || "") }));
        rawBox.value = rowsToRaw();
        drawRows();
        stEl.textContent = `✓ ${res.lines.length} satır kelime zamanlarıyla senkronlandı — Kaydet'e bas!`;
      } else {
        stEl.textContent = "✕ Kelime senkronu başarısız (" + (res?.error || "boş") + ")";
      }
    };

    ov.querySelector("#kfSaveLrc").onclick = async () => {
      const cleanTitle = String(titleHint || "").replace(/\.(mp3|wav|flac|m4a|ogg|opus)$/i, "").trim();
      const payload = (!rawBox.hidden && rawBox.value.trim()) ? rawBox.value : rows;
      const res = await callApi()?.music_lrc_save?.(path, payload, "", cleanTitle).catch(() => null);
      stEl.textContent = res?.ok ? "✓ .LRC dosyasına ve MP3 USLT etiketine kaydedildi!" : ("✕ " + (res?.error || "Kaydedilemedi"));
    };
  }

  window.openKamiLrcEditor = openLrcEditor;

  document.addEventListener("click", async (e) => {
    const wb = e.target.closest("[data-locwhisper]");
    if (wb) {
      e.stopPropagation();
      openLrcEditor(wb.dataset.locwhisper, "");
      setTimeout(() => document.getElementById("kfRunWhisper")?.click(), 180);
      return;
    }
    const eb = e.target.closest("[data-loclrcedit]");
    if (eb) {
      e.stopPropagation();
      openLrcEditor(eb.dataset.loclrcedit, eb.dataset.loctitle || "");
      return;
    }
    const nb = e.target.closest('.nav-b[data-nav="scrobble"]');
    if (nb) {
      document.querySelectorAll(".nav-b[data-nav]").forEach((b) => b.classList.toggle("on", b === nb));
      const vt = document.getElementById("viewTitle");
      if (vt) vt.textContent = "Sistem Sesi Dinleme Günlüğü (Ctrl+Shift+G)";
      const sb = document.getElementById("subBar");
      const listEl = document.getElementById("list");
      if (sb) {
        sb.hidden = false;
        sb.innerHTML = `<button class="btn pri" id="kfScrobNow">🎧 Şimdi Sistem Sesini Tanı & Günlüğe Ekle (Ctrl+Shift+G)</button><small style="color:var(--mut)">10 sn'lik hızlı tanımlama kısayolundan (Ctrl+Shift+S) bağımsız çalışır ve geçmişi kaydeder.</small>`;
        sb.querySelector("#kfScrobNow").onclick = async (ev) => {
          ev.target.disabled = true; ev.target.textContent = "Dinleniyor…";
          const r = await callApi()?.scrobbler_recognize_now?.().catch(() => null);
          ev.target.disabled = false; ev.target.textContent = "🎧 Şimdi Sistem Sesini Tanı & Günlüğe Ekle (Ctrl+Shift+G)";
          if (typeof mToast === "function") mToast(r?.ok ? `✓ Tanındı: ${r.song?.artist} — ${r.song?.title}` : (r?.error || "Şarkı algılanamadı"), !r?.ok);
          nb.click();
        };
      }
      if (listEl) {
        const hist = await callApi()?.scrobbler_history?.().catch(() => []) || [];
        listEl.innerHTML = hist.length ? hist.map((h) => `
          <div class="row">
            <div class="meta"><b>${(h.title || "Bilinmeyen").replace(/</g, "&lt;")}</b><small>${(h.artist || "").replace(/</g, "&lt;")} · ${new Date((h.ts || 0) * 1000).toLocaleString("tr-TR")}</small></div>
            <button class="btn" onclick="document.getElementById('q').value='${(h.artist + " " + h.title).replace(/'/g, "")}';document.getElementById('go').click()">Ara</button>
          </div>
        `).join("") : `<div style="color:var(--mut);padding:14px">Henüz günlük kaydı yok. Yukarıdaki düğmeye veya <b>Ctrl+Shift+G</b> kısayoluna basarak çalan parçaları günlüğe kaydedebilirsin.</div>`;
      }
    }
  });
})();
