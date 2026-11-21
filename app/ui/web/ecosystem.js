"use strict";
(() => {
  let root = null;
  let activeTab = "rec";
  let seasonCache = { title: "", episodes: [] };
  let renderSeq = 0;
  let recMsg = "";
  let grabTimer = null;

  const esc = (s) => (window.escapeHtml ? window.escapeHtml(String(s ?? "")) : String(s ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;"));

  function stopGrabPoll() {
    if (grabTimer) { clearTimeout(grabTimer); grabTimer = null; }
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && root && !root.hidden) {
      e.preventDefault();
      e.stopImmediatePropagation();
      closeModal();
      return;
    }
    const tag = (e.target && e.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || e.target?.isContentEditable) return;
    if (e.altKey && (e.key === "e" || e.key === "E")) {
      e.preventDefault();
      openModal("rec");
    }
  }, true);

  function ensureModal() {
    if (root) return root;
    if (!document.getElementById("ecoV138Style")) {
      const st = document.createElement("style");
      st.id = "ecoV138Style";
      st.textContent = `
        .eco-tabs {
          display: flex !important; flex-direction: column !important;
          justify-content: flex-start !important; align-items: stretch !important;
          align-content: flex-start !important; padding-top: 8px !important;
          overflow-y: auto !important; gap: 4px !important;
        }
        .eco-tgrp {
          font-size: 9.5px; font-weight: 700; letter-spacing: .09em; text-transform: uppercase;
          color: #8A829E; padding: 8px 6px 2px; border-top: 1px solid rgba(157,107,255,.14); margin-top: 4px;
          flex: none;
        }
        .eco-tgrp:first-of-type { border-top: 0; margin-top: 0; padding-top: 2px; }
        .eco-tgrp[hidden], .eco-tab[hidden] { display: none !important; }
        .eco-tfind {
          width: 100%; box-sizing: border-box; padding: 6px 8px; margin-bottom: 4px;
          border-radius: 6px; border: 1px solid rgba(157,107,255,.3);
          background: #0D0A14; color: #EDE9F6; font: 500 11.5px "Chakra Petch", sans-serif;
          outline: none; flex: none;
        }
        .eco-tfind:focus { border-color: #2EE6A6; }
      `;
      document.head.appendChild(st);
    }
    root = document.createElement("div");
    root.className = "eco-ov";
    root.hidden = true;
    root.innerHTML = `
      <div class="eco-box" role="dialog" aria-label="Kami Ekosistem">
        <div class="eco-hd">
          <h3>Kami Ekosistem & Araçlar</h3>
          <button class="eco-btn sec" data-close>Kapat (Esc)</button>
        </div>
        <div class="eco-tabs">
          <input class="eco-tfind" id="ecoTabFilter" type="search" placeholder="Araç ara..." autocomplete="off">
          <div class="eco-tgrp" data-grp="medya">Medya & Yakalama</div>
          <button class="eco-tab on" data-tab="rec" data-grp="medya">Ekran Kaydedici & Geçiş</button>
          <button class="eco-tab" data-tab="hardsub" data-grp="medya">Kami Hardsub</button>
          <button class="eco-tab" data-tab="ghost" data-grp="medya">Kami Ghost</button>
          <div class="eco-tgrp" data-grp="arac">Araç & İndirme</div>
          <button class="eco-tab" data-tab="bypass" data-grp="arac">Kami Bypass</button>
          <button class="eco-tab" data-tab="season" data-grp="arac">Sezon Kazıyıcı</button>
          <button class="eco-tab" data-tab="grab" data-grp="arac">Kami Grab-All</button>
    <button class="eco-tab" data-tab="rename" data-grp="arac">Toplu Adlandır</button>
    <button class="eco-tab" data-tab="subs" data-grp="arac">Altyazı Yöneticisi</button>
    <button class="eco-tab" data-tab="tag" data-grp="arac">Etiket Editörü</button>
    <button class="eco-tab" data-tab="scene" data-grp="arac">Sahne Arama</button>
          <div class="eco-tgrp" data-grp="ses">Ses & Oyun</div>
          <button class="eco-tab" data-tab="beat" data-grp="ses">Kami Beat</button>
          <button class="eco-tab" data-tab="hunter" data-grp="ses">Kami Hunter</button>
          <button class="eco-tab" data-tab="mod" data-grp="ses">Kami Mod</button>
          <div class="eco-tgrp" data-grp="sistem">Sistem</div>
          <button class="eco-tab" data-tab="bridge" data-grp="sistem">Köprü & Sunak</button>
          <button class="eco-tab" data-tab="doctor" data-grp="sistem">Kami Doktor</button>
          <button class="eco-tab" data-tab="jobs" data-grp="sistem">İşler</button>
  <button class="eco-tab" data-tab="echo" data-grp="sistem">Kami Echo</button>
        </div>
        <div class="eco-bd"></div>
      </div>`;
    document.body.appendChild(root);
    const tabsEl = root.querySelector(".eco-tabs");
    if (tabsEl) tabsEl.scrollTop = 0;
    const fEl = root.querySelector("#ecoTabFilter");
    if (fEl) {
      fEl.addEventListener("input", () => {
        const q = fEl.value.trim().toLowerCase();
        const grpVisible = {};
        root.querySelectorAll(".eco-tab").forEach((b) => {
          const hit = !q || b.textContent.toLowerCase().includes(q) || (b.dataset.tab || "").includes(q);
          b.hidden = !hit;
          if (hit) grpVisible[b.dataset.grp] = true;
        });
        root.querySelectorAll(".eco-tgrp").forEach((g) => { g.hidden = !grpVisible[g.dataset.grp]; });
      });
    }
    // v1.32.1: dikey menu — her modulde simge + tek satir aciklama
    const I = (d) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">${d}</svg>`;
    const META = {
      rec: [I('<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3" fill="currentColor"/>'), "Ekranı kaydet, son 30 sn'yi klip yap"],
      bypass: [I('<path d="M13 3 5 14h6l-1 7 8-11h-6z"/>'), "Kısaltma / reklamlı linki çöz"],
      season: [I('<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M8 3v4m8-4v4M3 10h18"/>'), "Bir dizinin tüm bölümlerini bul"],
      grab: [I('<path d="M4 6h16M4 12h16M4 18h10"/>'), "Sayfadaki tüm dosyaları listele"],
      hardsub: [I('<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 15h4m2 0h4"/>'), "Gömülü altyazıyı oku, Türkçeye çevir"],
      ghost: [I('<path d="M6 20V10a6 6 0 0 1 12 0v10l-3-2-3 2-3-2z"/><circle cx="10" cy="10" r="1"/><circle cx="14" cy="10" r="1"/>'), "Metadata temizle, Content-ID kalkanı"],
      beat: [I('<path d="M3 12h3l3-7 4 14 3-7h5"/>'), "Vokal ayır, BPM/ton, mashup"],
      hunter: [I('<circle cx="11" cy="11" r="6"/><path d="m20 20-4-4"/>'), "Kayıp medya ve arşiv arama"],
      mod: [I('<path d="M14 4l6 6-10 10H4v-6z"/>'), "Tek tık mod / Türkçe yama, geri al"],
      bridge: [I('<path d="M4 15c4-6 12-6 16 0M4 15v4m16-4v4M12 11v8"/>'), "iPhone/iPad köprüsü, kostüm, sesler"],
      doctor: [I('<path d="M12 5v14M5 12h14"/><circle cx="12" cy="12" r="9"/>'), "Sağlık kontrolleri ve tek tık onarım"],
      jobs: [I('<path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01"/>'), "Süren arka plan işleri"],
      echo: [I('<path d="M3 12a9 9 0 1 1 18 0 9 9 0 0 1-18 0z"/><path d="M12 8v4l3 2"/>'), "Geri alınabilir taşıma / ad değiştirme işlemleri"],
      rename: [I('<path d="M4 5h16M4 12h10M4 19h16"/><path d="M14 8l4 4-4 4"/>'), "Dosyaları önek + sayaç ile toplu yeniden adlandır (Echo ile geri alınır)"],
      subs: [I('<path d="M4 6h16v12H4zM7 10h10M7 14h6"/>'), "Klasördeki videolara toplu altyazı indir (OpenSubtitles)"],
      tag: [I('<path d="M4 4l7 16h2l7-16h-3l-5 12L7 4z"/>'), "Müzik etiketlerini düzenle (title/artist/album)"],
      scene: [I('<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="11" cy="11" r="4"/><path d="m20 20-4-4"/>'), "Bir kareden hangi video + dakika olduğunu bul (algısal hash)"],
    };
    root.querySelectorAll(".eco-tab").forEach((b) => { const m = META[b.dataset.tab]; if (m) b.innerHTML = `${m[0]}<span><b>${b.textContent}</b><small>${m[1]}</small></span>`; });
    root.addEventListener("click", (e) => {
      if (e.target === root || e.target.closest("[data-close]")) closeModal();
      const tb = e.target.closest("[data-tab]");
      if (tb) { activeTab = tb.dataset.tab; renderTab(); }
    });
    return root;
  }

  function openModal(tab = "rec") {
    ensureModal();
    activeTab = tab;
    root.hidden = false;
    const tabsEl = root.querySelector(".eco-tabs");
    if (tabsEl) tabsEl.scrollTop = 0;
    renderTab();
  }
  function closeModal() {
    stopGrabPoll();
    if (root) root.hidden = true;
  }

  // v1.35.4: sekme acilis verisi gelmezse (kopru takili) sekme sonsuza dek beklemesin; varsayilanla acilir
  const ld = (p, def, ms = 6000) => Promise.race([
    Promise.resolve(p).then((v) => (v == null ? def : v), () => def),
    new Promise((res) => setTimeout(() => res(def), ms)),
  ]);

  async function renderTab() {
    const seq = ++renderSeq;
    stopGrabPoll();
    const bd = root.querySelector(".eco-bd");
    root.querySelectorAll(".eco-tab").forEach((b) => b.classList.toggle("on", b.dataset.tab === activeTab));
    bd.innerHTML = `<div class="eco-card"><div class="eco-hint">Yükleniyor…</div></div>`;   // v1.35.4: eski sekme takili kalmasin

    if (activeTab === "echo") {
      const res = await ld(api.oplog_list?.(20), { ok: true, items: [] });
      if (seq !== renderSeq) return;
      const items = res.items || [];
      const escE = (s) => String(s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
      const rows = items.map((e) => '<div class="eco-row" style="justify-content:space-between"><span>' + escE(e.op === "move" ? "Taşıma" : e.op === "rename" ? "Yeniden adlandırma" : e.op) + ' · <small>' + escE(e.src) + ' → ' + escE(e.dst) + '</small></span><button class="eco-btn sec" data-undo="' + escE(e.id) + '">Geri Al</button></div>').join("");
      bd.innerHTML = '<div class="eco-card"><strong>Kami Echo — Geri Alınabilir İşlemler</strong><div class="eco-hint">Son taşıma / yeniden adlandırma işlemleri. "Geri Al" dosyayı önceki yerine taşır.</div>' + (rows || '<div class="eco-hint">Henüz işlem yok.</div>') + '</div>';
      bd.querySelectorAll("[data-undo]").forEach((b) => b.onclick = async () => { const r = await api.oplog_undo?.(b.dataset.undo).catch(() => null); if (r?.ok) renderTab(); else alert("Geri alınamadı: " + (r?.error || "hata")); });
      return;
    }

    if (activeTab === "doctor") {
      bd.innerHTML = `<div class="eco-card" id="ecoDocHost"><div class="eco-hint">Kontrol ediliyor…</div></div>`;
      window.KamiDoctor?.renderInto?.(bd.querySelector("#ecoDocHost"));
      return;
    }

    if (activeTab === "subs") {
      bd.innerHTML = `<div class="eco-card"><strong>Altyazı Yöneticisi</strong><div class="eco-hint">Klasör seç, eksik altyazılı videoları tara, toplu indir (OpenSubtitles anahtarı gerekli).</div><div class="eco-row"><input class="eco-in" id="subFolder" placeholder="Klasör yolu (örn. C:/Videolar)" style="flex:1"><button class="eco-btn sec" id="subBrowse">Gözat</button><button class="eco-btn" id="subScan">Tara</button></div><div class="eco-hint" id="subStat"></div><div id="subList" style="max-height:260px;overflow:auto"></div><div class="eco-row"><button class="eco-btn" id="subAll">Eksiklerin hepsine altyazı indir</button><span class="eco-hint" id="subProg"></span></div></div>`;
      const escS = s => String(s || "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;" }[c]));
      let missing = [];
      $("#subBrowse").onclick = async () => { const f = await api.choose_folder?.(); if (f) { $("#subFolder").value = f; $("#subScan").click(); } };
      $("#subScan").onclick = async () => { const f = ($("#subFolder").value || "").trim(); if (!f) { alert("Klasör yolu gir"); return; } const r = await ld(api.subtitle_scan?.(f), null); if (!r || !r.ok) { alert("Tarama başarısız: " + ((r && r.error) || "hata")); return; } missing = (r.videos || []).filter(v => !v.has_sub); $("#subStat").textContent = r.total + " video, " + missing.length + " altyazısız"; $("#subList").innerHTML = missing.map(v => '<div class="eco-row"><small>' + escS(v.name) + '</small></div>').join("") || '<div class="eco-hint">Altyazısız video yok.</div>'; };
      $("#subAll").onclick = async () => { if (!missing.length) { alert("Önce tara"); return; } $("#subAll").disabled = true; $("#subProg").textContent = "0/" + missing.length;
        let done = 0, err = 0;
        for (let i = 0; i < missing.length; i++) {
          $("#subProg").textContent = (i + 1) + "/" + missing.length + " · " + escS(missing[i].name);
          const r = await ld(api.subtitle_fetch?.(missing[i].path), null);
          if (r?.ok) done++; else err++;
          const row = $("#subList .eco-row")[i]; if (row) row.innerHTML = '<small>' + escS(missing[i].name) + '</small><span class="eco-tag">' + (r?.ok ? "✓" : "✕") + '</span>';
        }
        $("#subAll").disabled = false;
        $("#subProg").textContent = done + " indi, " + err + " hata";
      };
      return;
    }

    if (activeTab === "tag") {
      bd.innerHTML = `<div class="eco-card"><strong>Etiket Editörü</strong><div class="eco-hint">Müzik dosyasının ID3/FLAC/MP4 etiketlerini düzenle (mutagen). Tek dosya ya da toplu (birden çok dosyaya aynı etiket).</div><div class="eco-row"><input class="eco-in" id="tagPath" placeholder="Dosya yolu (örn. C:/muzik/a.mp3)" style="flex:1"><button class="eco-btn sec" id="tagBrowse">Gözat</button><button class="eco-btn" id="tagRead">Oku</button></div><div class="eco-row" style="margin-top:6px"><input class="eco-in" id="tagTitle" placeholder="Başlık" style="flex:1"><input class="eco-in" id="tagArtist" placeholder="Sanatçı" style="flex:1"><input class="eco-in" id="tagAlbum" placeholder="Albüm" style="flex:1"></div><div class="eco-row" style="margin-top:6px"><input class="eco-in" id="tagYear" placeholder="Yıl" style="width:90px"><input class="eco-in" id="tagTrack" placeholder="Parça no" style="width:90px"><input class="eco-in" id="tagType" placeholder="Tür" style="flex:1"></div><div class="eco-hint" style="margin-top:6px">Toplu: birden çok dosya yapıştır (her satıra bir yol) — aynı etiketler hepsine yazılır.</div><textarea id="tagBatch" class="eco-in" rows="3" placeholder="C:/muzik/a.mp3" style="width:100%;min-height:54px"></textarea><div class="eco-row"><button class="eco-btn" id="tagSave">Kaydet</button><button class="eco-btn sec" id="tagCover">Kapak</button><button class="eco-btn sec" id="tagBatchGo">Toplu uygula</button></div></div>`;
      let cur = "";
      const readInto = (t) => { $("#tagTitle").value = t.title || ""; $("#tagArtist").value = t.artist || ""; $("#tagAlbum").value = t.album || ""; $("#tagYear").value = t.date || t.year || ""; $("#tagTrack").value = t.tracknumber || t.track || ""; $("#tagType").value = t.genre || t.type || ""; };
      const gather = () => ({ title: $("#tagTitle").value.trim(), artist: $("#tagArtist").value.trim(), album: $("#tagAlbum").value.trim(), date: $("#tagYear").value.trim(), tracknumber: $("#tagTrack").value.trim(), genre: $("#tagType").value.trim() });
      $("#tagBrowse").onclick = async () => { const fs = await api.choose_files?.([".mp3", ".flac", ".m4a", ".ogg", ".opus", ".wma"]); if (fs?.length) { $("#tagPath").value = fs[0]; $("#tagBatch").value = fs.join(String.fromCharCode(10)); $("#tagRead").click(); } };
      $("#tagRead").onclick = async () => { cur = ($("#tagPath").value || "").trim(); if (!cur) { alert("Dosya yolu gir"); return; } const r = await ld(api.tag_read?.(cur), null); if (!r || !r.ok) { alert("Okunamadı: " + ((r && r.error) || "hata")); return; } readInto(r.tags || {}); };
      $("#tagSave").onclick = async () => { if (!cur) { alert("Önce oku"); return; } const r = await ld(api.tag_write?.(cur, gather()), null); alert(r && r.ok ? "Kaydedildi" : ("Hata: " + ((r && r.error) || "?"))); };
      $("#tagBatchGo").onclick = async () => { const ps = ($("#tagBatch").value || "").split(String.fromCharCode(10)).map(s => s.trim()).filter(Boolean); if (!ps.length) { alert("Toplu dosya yolu yapıştır"); return; } const tags = gather(); let ok = 0; for (const p of ps) { const r = await ld(api.tag_write?.(p, tags), null); if (r?.ok) ok++; } alert(ok + "/" + ps.length + " dosyaya yazıldı"); };
      $("#tagCover").onclick = async () => { if (!cur) { alert("Önce dosyayı oku"); return; } const fs = await api.choose_files?.([".jpg", ".jpeg", ".png", ".webp"]); if (!fs?.length) return; const im = await ld(api.image_data?.(fs[0], 800), null); if (!im?.ok) { alert("Kapak okunamadı"); return; } const r = await ld(api.tag_cover_write?.(cur, im.url), null); alert(r?.ok ? "Kapak yazıldı" : ("Hata: " + ((r && r.error) || "?"))); };
      return;
    }
    if (activeTab === "scene") {
      bd.innerHTML = `<div class="eco-card"><strong>Sahne Arama</strong><div class="eco-hint">Bir kare (ekran görüntüsü) seç, indirilen videolarda hangi dosya + dakikada olduğunu bul (algısal hash).</div><div class="eco-row"><input class="eco-in" id="sceneImg" placeholder="Kare yolu (örn. C:/ekran.png)" style="flex:1"><button class="eco-btn sec" id="sceneBrowse">Gözat</button></div><div class="eco-row"><input class="eco-in" id="sceneFolder" placeholder="Klasör (boş = indirilenler)" style="flex:1"><button class="eco-btn" id="sceneGo">Ara</button></div><div class="eco-hint" id="sceneMsg"></div></div>`;
      $("#sceneBrowse").onclick = async () => { const fs = await api.choose_files?.([".jpg", ".jpeg", ".png", ".webp"]); if (fs?.length) $("#sceneImg").value = fs[0]; };
      $("#sceneGo").onclick = async () => {
        const img = $("#sceneImg").value.trim(), fol = $("#sceneFolder").value.trim();
        if (!img) { alert("Kare yolu gir ya da Gözat ile seç"); return; }
        $("#sceneMsg").textContent = "Aranıyor… (videolar taranıyor, biraz sürebilir)";
        const r = await ld(api.scene_search?.(img, fol), null);
        $("#sceneMsg").textContent = r?.found ? ("✓ " + r.name + " · ~" + Math.floor((r.seconds || 0) / 60) + ":" + String((r.seconds || 0) % 60).padStart(2, "0")) : ((r?.error) || "Eşleşme bulunamadı");
      };
      return;
    }

    if (activeTab === "rename") {
      bd.innerHTML = `<div class="eco-card"><strong>Toplu Adlandır</strong><div class="eco-hint">Dosya yolu yapıştır, "Gözat" ile seç ya da buraya sürükle. Önek + sayaç ile yeniden adlandırılır; aşağıda eski → yeni ve çakışmalar görünür. Echo ile geri alınabilir.</div><div class="eco-row" style="margin-bottom:6px"><button class="eco-btn sec" id="renBrowse">Gözat (dosya seç)</button><span class="eco-hint">veya dosyaları kutuya sürükle</span></div><textarea id="renPaths" class="eco-in" rows="6" placeholder="C:/videolar/a.mp4" style="width:100%;min-height:90px"></textarea><div class="eco-row" style="margin-top:6px"><input class="eco-in" id="renPrefix" placeholder="Önek (örn. tatil_)" style="flex:1"><input class="eco-in" id="renStart" type="number" value="1" style="width:80px"></div><div class="eco-hint" id="renPrev" style="white-space:pre-wrap;min-height:20px;font-family:monospace;font-size:11px"></div><div class="eco-hint" id="renWarn" style="color:#F5B94A;display:none"></div><div class="eco-row"><button class="eco-btn" id="renGo">Uygula</button><span class="eco-hint">Uzantı korunur; çakışan adlar atlanır (Echo ile geri alınır).</span></div></div>`;
      const paths = () => (($("#renPaths").value || "").split(String.fromCharCode(10)).map(s => s.trim()).filter(Boolean));
      const newName = (f, i, s, p) => { const e = (f.split(".").pop() || "").toLowerCase(); return p + String(s + i).padStart(3, "0") + (e ? "." + e : ""); };
      const refresh = () => {
        const p = ($("#renPrefix").value || "").trim(), s = +$("#renStart").value || 1;
        const ps = paths();
        const seen = new Set(), dup = new Set();
        ps.forEach((f, i) => { const n = newName(f, i, s, p); const key = (f.split(/[\\/]/).slice(0, -1).join("/") || ".") + "/" + n; if (seen.has(key)) dup.add(key); seen.add(key); });
        $("#renPrev").textContent = ps.map((f, i) => (f.split(/[\\/]/).pop()) + "  →  " + newName(f, i, s, p)).join(String.fromCharCode(10));
        $("#renWarn").style.display = dup.size ? "" : "none";
        $("#renWarn").textContent = dup.size ? "⚠ " + dup.size + " dosya aynı hedef ada düşüyor (uygulamada atlanır)" : "";
      };
      ["renPaths", "renPrefix", "renStart"].forEach(id => $("#" + id).addEventListener("input", refresh));
      $("#renBrowse").onclick = async () => { const fs = await api.choose_files?.([".mp4", ".mkv", ".avi", ".mov", ".webm", ".mp3", ".flac", ".wav", ".m4a"]); if (fs?.length) { $("#renPaths").value = (paths().concat(fs)).join(String.fromCharCode(10)); refresh(); } };
      const ta = $("#renPaths");
      ta.addEventListener("dragover", (e) => e.preventDefault());
      ta.addEventListener("drop", (e) => { e.preventDefault(); const fs = [...(e.dataTransfer?.files || [])].map(f => f.path || f.name).filter(Boolean); if (fs.length) { $("#renPaths").value = (paths().concat(fs)).join(String.fromCharCode(10)); refresh(); } });
      refresh();
      $("#renGo").onclick = async () => { const p = ($("#renPrefix").value || "").trim(), s = +$("#renStart").value || 1; const pairs = paths().map((f, i) => ({ path: f, new_name: newName(f, i, s, p) })); if (!pairs.length) { alert("Önce dosya yolu yapıştır ya da seç"); return; } const r = await ld(api.batch_rename?.(pairs), null); alert(r && r.ok ? (r.done.length + " dosya yeniden adlandırıldı" + (r.errors.length ? ", " + r.errors.length + " atlandı" : "")) : "Hata"); };
      return;
    }

    if (activeTab === "rec") {
      const [st, ch] = await Promise.all([ld(api.rec_status?.(), {}), ld(api.chain_get?.(), {})]);
      if (seq !== renderSeq) return;
      bd.innerHTML = `
        <div class="eco-card">
          <div class="eco-row" style="justify-content:space-between">
            <strong>Ekran Kaydedici (ddagrab + WASAPI)</strong>
            <span class="eco-tag">${st.recording ? "KAYITTA" : (st.replay ? "REPLAY AÇIK" : "HAZIR")}</span>
          </div>
          <div class="eco-hint">Kısayollar: Alt+F9 (Başlat/Durdur), Alt+F10 (Replay Klip).</div>
          <div class="eco-row">
            <button class="eco-btn" id="ecoRecToggle">${st.recording ? "Kaydı Durdur (Alt+F9)" : "Kaydı Başlat (Alt+F9)"}</button>
            <button class="eco-btn sec" id="ecoRecReplay">Replay Klip (Alt+F10)</button>
            <button class="eco-btn sec" id="ecoRecBuf">${st.replay ? "Replay Kapat" : "Replay Aç"}</button>
            <button class="eco-btn sec" id="ecoRecDir">Klipler Klasörü</button>
          </div>
          <div class="eco-row">
            <label class="eco-hint">Replay (sn): <input class="eco-in" id="ecoRecSec" type="number" min="15" max="600" value="${Number(ch.rec_replay_seconds) || 30}" style="width:75px"></label>
            <input class="eco-in" id="ecoRecWin" placeholder="Pencere başlığı (opsiyonel, boş=tam ekran)" style="flex:1;min-width:290px;max-width:none">
            <button class="eco-btn sec" id="ecoRecWinGo">Pencere/Bölge Kaydet</button>
          </div>
          <div class="eco-row">
            <input class="eco-in" id="ecoRecFile" placeholder="Son kayıt veya klip yolu (GIF / Discord için)">
            <button class="eco-btn sec" id="ecoRecGif">GIF Yap</button>
            <button class="eco-btn sec" id="ecoRecDisc">Discord'a Sığdır</button>
          </div>
          <div class="eco-row">
            <label class="eco-hint">Planlı kayıt: <input class="eco-in" id="ecoRecSched" placeholder="19:30" style="width:70px"></label>
            <button class="eco-btn sec" id="ecoRecSchedGo">Planla</button>
            <span class="eco-hint" id="ecoRecSchedStat"></span>
          </div>
          <label class="eco-hint" style="display:flex;align-items:center;gap:6px"><input type="checkbox" id="ecoChRecStu" ${ch.chain_rec_studio ? "checked" : ""}> Zincir: Kayıt bitince otomatik Studio'da aç</label>
          <label class="eco-hint" style="display:flex;align-items:center;gap:6px"><input type="checkbox" id="ecoRecZoom" ${ch.rec_cursor_zoom !== false ? "checked" : ""}> Screen Studio Modu: Tıklama noktalarına otomatik yaylı imleç zoom'u uygula</label>
          <div class="eco-hint" id="ecoRecMsg"></div>
        </div>
        <div class="eco-card">
          <strong>Modül Geçişleri</strong>
          <div class="eco-row">
            <button class="eco-btn sec" id="ecoGoStudio">Kami Studio</button>
            <button class="eco-btn sec" id="ecoGoRoom">Kami Oda</button>
            <button class="eco-btn sec" id="ecoGoPic">Kami Picture (Görsel Aç)</button>
          </div>
        </div>`;
      bd.querySelector("#ecoRecMsg").textContent = recMsg;
      bd.querySelector("#ecoRecSec").onchange = (e) => api.chain_set?.("rec_replay_seconds", Math.max(15, Math.min(600, Number(e.target.value || 30))));
      bd.querySelector("#ecoChRecStu").onchange = (e) => api.chain_set?.("chain_rec_studio", e.target.checked);
      bd.querySelector("#ecoRecZoom").onchange = (e) => api.set_setting?.("rec_cursor_zoom", e.target.checked);
      bd.querySelector("#ecoRecToggle").onclick = async () => {
        const r = await api.rec_toggle();
        recMsg = r.recording ? "Kayıt başlatıldı..." : (r.path ? `Kaydedildi: ${r.path}` : (r.error || "Tamamlandı"));
        renderTab();
      };
      bd.querySelector("#ecoRecWinGo").onclick = async () => {
        const wt = bd.querySelector("#ecoRecWin").value.trim();
        const r = await api.rec_start_region?.(0, 0, 1280, 720, wt);
        recMsg = r?.recording ? "Pencere/bölge kaydı başladı..." : (r?.error || "Hata");
        bd.querySelector("#ecoRecMsg").textContent = recMsg;
      };
      bd.querySelector("#ecoRecGif").onclick = async () => {
        const p = bd.querySelector("#ecoRecFile").value.trim();
        if (!p) return;
        bd.querySelector("#ecoRecMsg").textContent = "GIF işi başlatılıyor...";
        const r = await api.rec_export_gif?.(p);
        bd.querySelector("#ecoRecMsg").textContent = r?.job_id ? `İş başlatıldı (${r.job_id}) ✓ — İşler sekmesinden izle.` : (r?.ok ? `GIF hazır: ${r.out}` : (r?.error || "Hata"));
      };
      bd.querySelector("#ecoRecDisc").onclick = async () => {
        const p = bd.querySelector("#ecoRecFile").value.trim();
        if (!p) return;
        bd.querySelector("#ecoRecMsg").textContent = "Discord sıkıştırma işi başlatılıyor...";
        const r = await api.rec_fit_discord?.(p);
        bd.querySelector("#ecoRecMsg").textContent = r?.job_id ? `İş başlatıldı (${r.job_id}) ✓ — İşler sekmesinden izle.` : (r?.ok ? `Hazır (${r.size_mb} MB): ${r.out}` : (r?.error || "Hata"));
      };
      bd.querySelector("#ecoRecReplay").onclick = async () => {
        const r = await api.rec_save_replay();
        recMsg = r.ok ? `Klip kaydedildi: ${r.path}` : `Hata: ${r.error || "Replay kapalı"}`;
        bd.querySelector("#ecoRecMsg").textContent = recMsg;
      };
      bd.querySelector("#ecoRecBuf").onclick = async () => { await api.rec_replay(!st.replay); renderTab(); };
      bd.querySelector("#ecoRecDir").onclick = () => api.rec_open_folder();
      bd.querySelector("#ecoRecSchedGo").onclick = async () => {
        const t = bd.querySelector("#ecoRecSched").value.trim();
        const r = await api.rec_schedule_at?.(t);
        bd.querySelector("#ecoRecSchedStat").textContent = r?.ok ? ("Planlandı: " + r.at + " (iptal için yeniden tıkla)") : ("Hata: " + (r?.error || "?"));
        if (r?.ok) bd.querySelector("#ecoRecSchedGo").textContent = "İptal";
        else bd.querySelector("#ecoRecSchedGo").textContent = "Planla";
      };
      {
        const sc = await api.rec_schedule_status?.().catch(() => null);
        if (sc?.scheduled) { bd.querySelector("#ecoRecSchedStat").textContent = "Planlı: " + sc.at; bd.querySelector("#ecoRecSchedGo").textContent = "İptal"; bd.querySelector("#ecoRecSchedGo").onclick = async () => { await api.rec_schedule_cancel?.(); renderTab(); }; }
      }
      bd.querySelector("#ecoGoStudio").onclick = () => { closeModal(); api.studio_show(""); };
      bd.querySelector("#ecoGoRoom").onclick = () => { closeModal(); api.room_open?.(true); };
      bd.querySelector("#ecoGoPic").onclick = () => { closeModal(); api.picture_open_editor?.(); };
    } else if (activeTab === "bypass") {
      const ch = await ld(api.chain_get?.(), {});
      if (seq !== renderSeq) return;
      bd.innerHTML = `
        <div class="eco-card">
          <strong>Kami Bypass (Kısaltma & Reklamlı Ara Link Çözücü)</strong>
          <div class="eco-hint">Desteklenenler: ouo.io, tr.link, ay.link, linkvertise, cuty.io, bc.vc, pastebin, rentry.</div>
          <div class="eco-row">
            <input class="eco-in" id="ecoByUrl" placeholder="https://ouo.io/... veya https://tr.link/...">
            <button class="eco-btn" id="ecoByGo">Çöz</button>
          </div>
          <div id="ecoByRes" class="eco-hint"></div>
        </div>
        <div class="eco-card">
          <strong>Toplu Link Sağlık Kontrolü & Arşiv Parola Listesi</strong>
          <textarea class="eco-in" id="ecoLkUrls" rows="3" placeholder="Her satıra bir URL yapıştır..." style="width:100%;box-sizing:border-box"></textarea>
          <div class="eco-row" style="margin-top:6px">
            <button class="eco-btn" id="ecoLkGo">Linkleri Kontrol Et</button>
            <input class="eco-in" id="ecoPwList" value="${esc((ch.archive_passwords || []).join(", "))}" placeholder="Arşiv parolaları (virgülle ayır)">
            <button class="eco-btn sec" id="ecoPwSave">Parolaları Kaydet</button>
          </div>
          <div id="ecoLkList" class="eco-list"></div>
        </div>`;
      bd.querySelector("#ecoPwSave").onclick = async () => {
        const arr = bd.querySelector("#ecoPwList").value.split(",").map((x) => x.trim()).filter(Boolean);
        await api.chain_set?.("archive_passwords", arr);
        bd.querySelector("#ecoLkList").innerHTML = `<div class="eco-item eco-ok">Parolalar kaydedildi (${arr.length}) ✓</div>`;
      };
      bd.querySelector("#ecoLkGo").onclick = async () => {
        const urls = bd.querySelector("#ecoLkUrls").value.split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
        const list = bd.querySelector("#ecoLkList");
        if (!urls.length) return;
        list.innerHTML = `<div class="eco-item eco-hint">Kontrol ediliyor...</div>`;
        const r = await api.links_check?.(urls);
        if (seq !== renderSeq) return;
        list.innerHTML = ((r && r.items) || []).map((it) => `
          <div class="eco-item">
            <span class="eco-tag" style="color:${it.ok ? "#2ee6a6" : "#ff6b8b"}">${it.ok ? `OK (${it.status})` : `ÖLÜ (${it.status || "ERR"})`}</span>
            <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(it.name || it.url)}</span>
            <span class="eco-hint">${it.size ? `${(it.size / 1048576).toFixed(1)} MB` : ""}</span>
          </div>`).join("");
      };
      bd.querySelector("#ecoByGo").onclick = async () => {
        const u = bd.querySelector("#ecoByUrl").value.trim();
        const out = bd.querySelector("#ecoByRes");
        if (!u) return;
        out.textContent = "Çözülüyor...";
        const r = await api.bypass_resolve(u);
        if (seq !== renderSeq) return;
        if (r.ok && r.url) {
          out.innerHTML = `<span class="eco-ok">Hedef (${Number(r.hops) || 0} adım):</span> <code id="ecoByCode"></code> <button class="eco-btn" id="ecoByAdd" style="margin-left:8px">Kami'ye Ekle</button> <span id="ecoByAddSt"></span>`;
          out.querySelector("#ecoByCode").textContent = r.url;
          out.querySelector("#ecoByAdd").onclick = async () => {
            const stEl = out.querySelector("#ecoByAddSt");
            const r2 = await api.add_url(r.url);
            stEl.textContent = r2 && r2.ok ? " ✓" : ` (Hata: ${(r2 && r2.error) || "eklenemedi"})`;
            stEl.className = r2 && r2.ok ? "eco-ok" : "eco-err";
          };
        } else {
          out.innerHTML = `<span class="eco-err">Çözülemedi:</span> <span id="ecoByErr"></span>`;
          out.querySelector("#ecoByErr").textContent = r.error || "bilinmiyor";
        }
      };
    } else if (activeTab === "season") {
      bd.innerHTML = `
        <div class="eco-card">
          <strong>Tam Sezon & Gömülü Oynatıcı Kazıyıcı</strong>
          <div class="eco-hint">Dizi/sezon sayfası bağlantısını yapıştır; PlayerJS, VidMoly, Sibnet, Dzen ve TauVideo akışlarını tek seferde çıkar.</div>
          <div class="eco-row">
            <input class="eco-in" id="ecoSeUrl" placeholder="https://.../sezon-1 veya bölüm sayfası">
            <button class="eco-btn" id="ecoSeGo">Bölümleri Bul</button>
            <button class="eco-btn sec" id="ecoSeDl" ${seasonCache.episodes.length ? "" : "disabled"}>Seçilenleri İndir</button>
          </div>
          <div id="ecoSeMsg" class="eco-hint"></div>
          <div class="eco-list" id="ecoSeList"></div>
        </div>`;
      const drawList = () => {
        const list = bd.querySelector("#ecoSeList");
        list.innerHTML = seasonCache.episodes.map((ep, i) => `
          <label class="eco-item">
            <input type="checkbox" data-i="${i}" ${ep.stream_url ? "checked" : "disabled"}>
            <span class="eco-tag">Bölüm ${Number(ep.episode) || 0}</span>
            <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(ep.title)}</span>
            <span class="${ep.stream_url ? "eco-ok" : "eco-err"}">${ep.stream_url ? "Akış hazır" : "Bulunamadı"}</span>
          </label>`).join("");
        bd.querySelector("#ecoSeDl").disabled = !seasonCache.episodes.some((e) => e.stream_url);
      };
      if (seasonCache.episodes.length) drawList();
      bd.querySelector("#ecoSeGo").onclick = async () => {
        const u = bd.querySelector("#ecoSeUrl").value.trim();
        const msg = bd.querySelector("#ecoSeMsg");
        if (!u) return;
        msg.textContent = "Sayfa ve gömülü oynatıcılar taranıyor...";
        const r = await api.season_scrape(u);
        if (seq !== renderSeq) return;
        if (!r.ok) {
          msg.innerHTML = `<span class="eco-err">Hata: ${esc(r.error || "bilinmiyor")}</span>`;
          return;
        }
        seasonCache = { title: r.title || "", episodes: r.episodes || [] };
        msg.textContent = `${seasonCache.title}: ${seasonCache.episodes.length} bölüm bulundu.`;
        drawList();
      };
      bd.querySelector("#ecoSeDl").onclick = async () => {
        const picked = [...bd.querySelectorAll("#ecoSeList input:checked")].map((c) => seasonCache.episodes[Number(c.dataset.i)]);
        const r = await api.season_download(picked, seasonCache.title);
        if (seq !== renderSeq) return;
        bd.querySelector("#ecoSeMsg").textContent = r.ok ? `${r.added} bölüm kuyruğa eklendi ✓` : "Hiçbir bölüm eklenemedi.";
      };
    } else if (activeTab === "grab") {
      let [st, ch] = await Promise.all([ld(api.grab_all_status?.(), {}), ld(api.chain_get?.(), {})]);
      if (seq !== renderSeq) return;
      const profs = ch.grab_follow_profiles || [];
      const formatGrabMsg = (s) => {
        const tail = Array.isArray(s.tail) && s.tail.length ? s.tail.map(esc).join("<br>") : "";
        const statusTxt = s.running
          ? `<span class="eco-ok">Çalışıyor (${Number(s.files_count) || 0} dosya)...</span>`
          : (s.rc === 0 ? `<span class="eco-ok">Son iş tamamlandı (${Number(s.files_count) || 0} dosya).</span>`
            : (typeof s.rc === "number" ? `<span class="eco-err">Son iş hata koduyla bitti (${s.rc}).</span>` : ""));
        return `${statusTxt}${tail ? `<div class="eco-tail">${tail}</div>` : ""}`;
      };
      bd.innerHTML = `
        <div class="eco-card">
          <div class="eco-row" style="justify-content:space-between">
            <strong>Kami Grab-All (gallery-dl Profil & Pano Arşivi)</strong>
            <span class="eco-tag" id="ecoGrBadge">${st.installed ? "gallery-dl Hazır" : "İlk kullanımda kurulur"}</span>
          </div>
          <div class="eco-hint">Instagram, X (Twitter), TikTok, Pinterest, Reddit, Erome, Kemono ve Coomer profillerini / albümlerini indirir (--download-archive ile yinelenenleri atlar).<br>Hedef: <code>${esc(st.dest || "İndirilenler/Grab-All")}</code></div>
          <div class="eco-row">
            <input class="eco-in" id="ecoGrUrl" placeholder="https://www.instagram.com/..., erome.com/a/..., kemono.su/...">
            <input class="eco-in" id="ecoGrLim" type="number" min="0" placeholder="Limit (0=tümü)" style="max-width:110px;flex:0">
            <button class="eco-btn" id="ecoGrGo">Arşivi Başlat</button>
            <button class="eco-btn sec" id="ecoGrFol">Takibe Ekle</button>
          </div>
          <div class="eco-row">
            <select class="eco-in" id="ecoGrType" style="max-width:130px;flex:0">
              <option value="all">Tümü</option><option value="video">Yalnız Video</option><option value="image">Yalnız Görsel</option>
            </select>
            <input class="eco-in" id="ecoGrAfter" placeholder="Sonrası: YYYY-AA-GG" title="Başlangıç tarihi (opsiyonel)">
            <input class="eco-in" id="ecoGrBefore" placeholder="Öncesi: YYYY-AA-GG" title="Bitiş tarihi (opsiyonel)">
          </div>
          <label class="eco-hint" style="display:flex;align-items:center;gap:6px"><input type="checkbox" id="ecoChGrGh" ${ch.chain_grab_ghost ? "checked" : ""}> Zincir: Grab-All bitince klasörü Ghost'tan geçir</label>
          <div id="ecoGrMsg" class="eco-hint">${formatGrabMsg(st)}</div>
          ${profs.length ? `<div class="eco-list">${profs.map((p, i) => `<div class="eco-item"><span style="flex:1">${esc(p)}</span><button class="eco-btn sec" data-grrun="${esc(p)}" style="padding:3px 8px">Güncelle</button><button class="eco-btn sec" data-grdel="${i}" style="padding:3px 8px">Sil</button></div>`).join("")}</div>` : ""}
        </div>`;
      bd.querySelector("#ecoChGrGh").onchange = (e) => api.chain_set?.("chain_grab_ghost", e.target.checked);
      bd.querySelector("#ecoGrFol").onclick = async () => {
        const u = bd.querySelector("#ecoGrUrl").value.trim();
        if (!u || profs.includes(u)) return;
        await api.chain_set?.("grab_follow_profiles", [...profs, u]);
        renderTab();
      };
      bd.querySelectorAll("[data-grrun]").forEach((b) => { b.onclick = () => { bd.querySelector("#ecoGrUrl").value = b.dataset.grrun; bd.querySelector("#ecoGrGo").click(); }; });
      bd.querySelectorAll("[data-grdel]").forEach((b) => { b.onclick = async () => { const n = profs.filter((_, i) => i !== Number(b.dataset.grdel)); await api.chain_set?.("grab_follow_profiles", n); renderTab(); }; });
      const pollGrab = () => {
        stopGrabPoll();
        grabTimer = setTimeout(async () => {
          if (!root || root.hidden || activeTab !== "grab" || seq !== renderSeq) return;
          const next = await api.grab_all_status().catch(() => null);
          if (!next || seq !== renderSeq || activeTab !== "grab") return;
          st = next;
          const badge = bd.querySelector("#ecoGrBadge");
          const msgEl = bd.querySelector("#ecoGrMsg");
          if (badge) badge.textContent = st.installed ? "gallery-dl Hazır" : "İlk kullanımda kurulur";
          if (msgEl) msgEl.innerHTML = formatGrabMsg(st);
          if (st.running) pollGrab();
        }, 2000);
      };
      if (st.running) pollGrab();
      bd.querySelector("#ecoGrGo").onclick = async () => {
        const u = bd.querySelector("#ecoGrUrl").value.trim();
        const lim = Number(bd.querySelector("#ecoGrLim").value || 0);
        const mtype = bd.querySelector("#ecoGrType")?.value || "all";
        const da = (bd.querySelector("#ecoGrAfter")?.value || "").trim();
        const db = (bd.querySelector("#ecoGrBefore")?.value || "").trim();
        const msg = bd.querySelector("#ecoGrMsg");
        if (!u) return;
        msg.textContent = st.installed
          ? "Başlatılıyor..."
          : "gallery-dl aracı kuruluyor (ilk seferde ~1-3 dk sürebilir)...";
        const r = await api.grab_all_start(u, lim, mtype, da, db);
        if (seq !== renderSeq) return;
        if (r.ok) {
          st.installed = true;
          const badge = bd.querySelector("#ecoGrBadge");
          if (badge) badge.textContent = "gallery-dl Hazır";
          msg.innerHTML = `<span class="eco-ok">İndirme başladı (PID ${Number(r.pid) || 0}).</span> Hedef: <code>${esc(r.dest)}</code>`;
          pollGrab();
        } else {
          msg.innerHTML = `<span class="eco-err">Hata:</span> ${esc(r.error || "bilinmiyor")}`;
        }
      };
    } else if (activeTab === "hardsub") {
      bd.innerHTML = `
        <div class="eco-card">
          <strong>Kami Hardsub (Gömülü Altyazı OCR & Türkçe Çeviri)</strong>
          <div class="eco-hint">Seçilen bölgedeki gömülü altyazıyı okur, yerel NLLB veya Google ile çevirir; varsayılan hızlı delogo veya kara bant uygular.</div>
          <div class="eco-row">
            <input class="eco-in" id="ecoHsPath" placeholder="C:\\Users\\...\\video.mp4">
            <input class="eco-in" id="ecoHsLang" placeholder="Dil (boş=oto, en, ja)" style="max-width:140px;flex:0">
          </div>
          <div class="eco-row">
            <label class="eco-hint">Üst %: <input class="eco-in" id="ecoHsTop" type="number" min="0" max="90" value="76" style="width:65px"></label>
            <label class="eco-hint">Boy %: <input class="eco-in" id="ecoHsH" type="number" min="8" max="50" value="24" style="width:65px"></label>
            <select class="eco-in" id="ecoHsCol" style="max-width:150px">
              <option value="both">Beyaz+Sarı Filtre</option><option value="white">Sadece Beyaz</option><option value="yellow">Sadece Sarı</option><option value="none">Filtresiz</option>
            </select>
            <select class="eco-in" id="ecoHsMask" style="max-width:165px">
              <option value="delogo">Hızlı Delogo (Önerilen)</option><option value="box">Kara Bant</option>
            </select>
          </div>
          <div class="eco-row">
            <label class="eco-hint" style="display:flex;align-items:center;gap:6px"><input type="checkbox" id="ecoHsNllb"> Yerel NLLB Çeviri</label>
            <label class="eco-hint" style="display:flex;align-items:center;gap:6px"><input type="checkbox" id="ecoHsBurn"> Videoya göm</label>
            <button class="eco-btn" id="ecoHsGo" style="margin-left:auto">İş Başlat</button>
          </div>
          <div id="ecoHsMsg" class="eco-hint"></div>
        </div>`;
      bd.querySelector("#ecoHsGo").onclick = async () => {
        const p = bd.querySelector("#ecoHsPath").value.trim();
        if (!p) return;
        const r = await api.hardsub_start?.(
          p, bd.querySelector("#ecoHsLang").value.trim(), bd.querySelector("#ecoHsBurn").checked,
          Number(bd.querySelector("#ecoHsTop").value || 76) / 100,
          Number(bd.querySelector("#ecoHsH").value || 24) / 100,
          bd.querySelector("#ecoHsCol").value, bd.querySelector("#ecoHsNllb").checked,
          bd.querySelector("#ecoHsMask").value
        );
        bd.querySelector("#ecoHsMsg").innerHTML = r?.ok
          ? `<span class="eco-ok">İş başlatıldı (${esc(r.job_id)}) ✓</span> İlerlemeyi <strong>İşler</strong> sekmesinden izleyebilirsin.`
          : `<span class="eco-err">Hata:</span> ${esc(r?.error || "bilinmiyor")}`;
      };
    } else if (activeTab === "ghost") {
      bd.innerHTML = `
        <div class="eco-card">
          <strong>Kami Ghost (Metadata Temizleyici & Content-ID Kalkanı)</strong>
          <div class="eco-hint">Tek dosya veya bütün klasörden EXIF/GPS/ID3 parmak izlerini siler.</div>
          <div class="eco-row">
            <input class="eco-in" id="ecoGhPath" placeholder="Dosya veya klasör yolu (C:\\Users\\...)">
            <button class="eco-btn sec" id="ecoGhScan">Metadata Tara</button>
          </div>
          <div class="eco-row">
            <label class="eco-hint" style="display:flex;align-items:center;gap:6px"><input type="checkbox" id="ecoGhShield"> Content-ID Kalkanı (mikro pitch/piksel)</label>
            <button class="eco-btn" id="ecoGhGo" style="margin-left:auto">Dosyayı Temizle</button>
            <button class="eco-btn sec" id="ecoGhDir">Klasörü Temizle</button>
          </div>
          <div id="ecoGhMsg" class="eco-hint"></div>
        </div>`;
      bd.querySelector("#ecoGhScan").onclick = async () => {
        const p = bd.querySelector("#ecoGhPath").value.trim();
        const msg = bd.querySelector("#ecoGhMsg");
        if (!p) return;
        const r = await api.ghost_inspect?.(p);
        if (!r?.ok) { msg.innerHTML = `<span class="eco-err">${esc(r?.error || "Taranamadı")}</span>`; return; }
        const gps = r.has_gps ? `<div class="eco-err" style="font-weight:700">⚠ UYARI: Bu dosyada GPS konum bilgisi tespit edildi!</div>` : "";
        const rows = Object.entries(r.fields || {}).map(([k, v]) => `<code>${esc(k)}</code>: ${esc(v)}`).join("<br>") || "Hassas etiket bulunamadı.";
        msg.innerHTML = `${gps}<div>${rows}</div>`;
      };
      bd.querySelector("#ecoGhGo").onclick = async () => {
        const p = bd.querySelector("#ecoGhPath").value.trim();
        const shield = bd.querySelector("#ecoGhShield").checked;
        const msg = bd.querySelector("#ecoGhMsg");
        if (!p) return;
        msg.textContent = "İşleniyor...";
        const r = await api.ghost_process(p, shield);
        if (seq !== renderSeq) return;
        msg.innerHTML = r.ok ? `<span class="eco-ok">Hazır:</span> <code>${esc(r.out)}</code>` : `<span class="eco-err">Hata:</span> ${esc(r.error || "bilinmiyor")}`;
      };
      bd.querySelector("#ecoGhDir").onclick = async () => {
        const p = bd.querySelector("#ecoGhPath").value.trim();
        const shield = bd.querySelector("#ecoGhShield").checked;
        if (!p) return;
        const r = await api.ghost_folder_start?.(p, shield);
        bd.querySelector("#ecoGhMsg").innerHTML = r?.ok
          ? `<span class="eco-ok">Klasör işi başlatıldı (${esc(r.job_id)}) ✓</span> <strong>İşler</strong> sekmesinden izle.`
          : `<span class="eco-err">${esc(r?.error || "Hata")}</span>`;
      };
    } else if (activeTab === "beat") {
      bd.innerHTML = `
        <div class="eco-card">
          <strong>Kami Beat (UVR5 + BPM/Key + Matchering Mashup Stüdyosu)</strong>
          <div class="eco-hint">İki şarkıdan UVR5 ile vokal/beat ayırır, BPM & ton (Key) eşler ve isteğe bağlı Matchering referans master alır.</div>
          <div class="eco-row">
            <input class="eco-in" id="ecoBtVoc" placeholder="1. Şarkı / Vokal (C:\\...\\vocal.wav)">
            <input class="eco-in" id="ecoBtBeat" placeholder="2. Şarkı / Beat (C:\\...\\beat.mp3)">
          </div>
          <div class="eco-row">
            <input class="eco-in" id="ecoBtVbpm" type="number" step="0.1" placeholder="Vokal BPM (0=oto)" style="max-width:120px">
            <input class="eco-in" id="ecoBtBbpm" type="number" step="0.1" placeholder="Beat BPM (0=oto)" style="max-width:120px">
            <input class="eco-in" id="ecoBtSemi" type="number" step="0.5" placeholder="Perde (±ton)" style="max-width:110px">
            <input class="eco-in" id="ecoBtOff" type="number" step="0.1" placeholder="Kaydır (sn)" style="max-width:105px">
          </div>
          <div class="eco-row">
            <input class="eco-in" id="ecoBtRef" placeholder="Matchering referans parçası (opsiyonel)">
            <label class="eco-hint" style="display:flex;align-items:center;gap:5px"><input type="checkbox" id="ecoBtUvr"> UVR5 Oto-Ayır</label>
          </div>
          <div class="eco-row">
            <button class="eco-btn" id="ecoBtGo">Mashup Üret (İş)</button>
            <button class="eco-btn sec" id="ecoBtKey">Ton (Key) Ölç</button>
            <button class="eco-btn sec" id="ecoBtStems">1. Şarkıyı 4 Kanala Ayır</button>
          </div>
          <div id="ecoBtMsg" class="eco-hint"></div>
        </div>`;
      bd.querySelector("#ecoBtKey").onclick = async () => {
        const voc = bd.querySelector("#ecoBtVoc").value.trim();
        const beat = bd.querySelector("#ecoBtBeat").value.trim();
        const [k1, k2] = await Promise.all([voc ? api.beat_key?.(voc) : null, beat ? api.beat_key?.(beat) : null]);
        bd.querySelector("#ecoBtMsg").textContent =
          `Vokal Key: ${k1?.key || "-"} (${k1?.camelot || "-"}) · Beat Key: ${k2?.key || "-"} (${k2?.camelot || "-"})`;
      };
      bd.querySelector("#ecoBtStems").onclick = async () => {
        const voc = bd.querySelector("#ecoBtVoc").value.trim();
        if (!voc) return;
        const r = await api.beat_stems?.(voc);
        bd.querySelector("#ecoBtMsg").innerHTML = r?.ok ? `<span class="eco-ok">4-Kanal ayrıştırma başlatıldı (${esc(r.job_id)}) ✓</span>` : esc(r?.error || "Hata");
      };
      bd.querySelector("#ecoBtGo").onclick = async () => {
        const voc = bd.querySelector("#ecoBtVoc").value.trim();
        const beat = bd.querySelector("#ecoBtBeat").value.trim();
        if (!voc || !beat) return;
        const r = await api.beat_mashup_start?.(
          voc, beat, Number(bd.querySelector("#ecoBtVbpm").value || 0), Number(bd.querySelector("#ecoBtBbpm").value || 0),
          Number(bd.querySelector("#ecoBtSemi").value || 0), Number(bd.querySelector("#ecoBtOff").value || 0),
          bd.querySelector("#ecoBtUvr").checked, bd.querySelector("#ecoBtRef").value.trim()
        );
        bd.querySelector("#ecoBtMsg").innerHTML = r?.ok
          ? `<span class="eco-ok">Mashup işi başlatıldı (${esc(r.job_id)}) ✓</span> <strong>İşler</strong> sekmesinden izle.`
          : `<span class="eco-err">Hata:</span> ${esc(r?.error || "bilinmiyor")}`;
      };
    } else if (activeTab === "hunter") {
      bd.innerHTML = `
        <div class="eco-card">
          <strong>Kami Hunter (Kayıp Medya & Yeraltı Arşiv Arama)</strong>
          <div class="eco-hint">Internet Archive, Dailymotion, SoundCloud, Bandcamp, Ok.ru, VK, Mail.ru, Reddit ve (isteğe bağlı site adresiyle) Wayback Media üzerinde arar.</div>
          <div class="eco-row">
            <input class="eco-in" id="ecoHuQ" placeholder="Sanatçı, parça adı veya arşiv anahtarı...">
            <input class="eco-in" id="ecoHuSite" placeholder="Wayback site (ör: site.com, opsiyonel)" style="max-width:220px">
            <button class="eco-btn" id="ecoHuGo">Ara</button>
          </div>
          <div id="ecoHuMsg" class="eco-hint"></div>
          <audio id="ecoHuAud" controls hidden style="width:100%;margin-top:6px"></audio>
          <div class="eco-list" id="ecoHuList"></div>
        </div>`;
      bd.querySelector("#ecoHuGo").onclick = async () => {
        const q = bd.querySelector("#ecoHuQ").value.trim();
        const site = bd.querySelector("#ecoHuSite").value.trim();
        const msg = bd.querySelector("#ecoHuMsg");
        const list = bd.querySelector("#ecoHuList");
        if (!q) return;
        msg.textContent = "Arşivler taranıyor...";
        const r = await api.hunter_search(q, site);
        if (seq !== renderSeq) return;
        const items = (r && r.items) || [];
        const notes = (r && r.notes && r.notes.length) ? ` (${r.notes.join(" · ")})` : "";
        msg.textContent = r.ok ? `${items.length} sonuç bulundu.${notes}` : (r.error || "Arama başarısız");
        list.innerHTML = items.map((it, idx) => `
          <div class="eco-item">
            <span class="eco-tag">${esc(it.source)}</span>
            <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(it.url)}">${esc(it.title)}${it.quality_score ? ` · Skor ${esc(String(it.quality_score))}` : ""}${it.mirrors_count > 1 ? ` · ${it.mirrors_count} ayna` : ""}</span>
            <button class="eco-btn sec" data-huprev="${idx}" style="padding:4px 8px">▶ Dinle</button>
            <button class="eco-btn sec" data-huadd="${idx}" style="padding:4px 8px">İndir</button>
            <button class="eco-btn sec" data-huarc="${idx}" style="padding:4px 8px" title="Underground Rap / Etiket + LRC Arşivle">📦 Arşivle</button>
          </div>`).join("");
        list.querySelectorAll("[data-huprev]").forEach((btn) => {
          btn.onclick = async () => {
            const it = items[Number(btn.dataset.huprev)];
            btn.textContent = "...";
            const pr = await api.hunter_preview?.(it.url);
            if (pr?.ok && pr.stream) {
              const aud = bd.querySelector("#ecoHuAud");
              aud.hidden = false; aud.src = pr.stream; aud.play().catch(() => {});
              btn.textContent = "▶";
            } else { btn.textContent = "Yok"; }
          };
        });
        list.querySelectorAll("[data-huadd]").forEach((btn) => {
          btn.onclick = async () => {
            const it = items[Number(btn.dataset.huadd)];
            const res = await api.add_url(it.url);
            btn.textContent = res && res.ok ? "✓" : "Hata";
          };
        });
        list.querySelectorAll("[data-huarc]").forEach((btn) => {
          btn.onclick = async () => {
            const it = items[Number(btn.dataset.huarc)];
            if (!it?.url || !api.hunter_archive) return;
            btn.textContent = "...";
            const r = await api.hunter_archive(it.url, it.title || "", "", "", "").catch((e) => ({ ok: false, error: String(e) }));
            btn.textContent = r && r.ok ? "✓ Arşiv" : "Hata";
            msg.textContent = r && r.ok ? `Arşivlendi: ${r.path || ""}` : ((r && r.error) || "Arşivlenemedi");
          };
        });
      };
    } else if (activeTab === "mod") {
      const [mods, steam] = await Promise.all([ld(api.mod_list?.(), []), ld(api.mod_steam_games?.(), [], 10000)]);
      if (seq !== renderSeq) return;
      bd.innerHTML = `
        <div class="eco-card">
          <strong>Kami Mod (1-Tık Mod / Türkçe Yama Kurucu & Rollback)</strong>
          <div class="eco-hint">.zip mod arşivini aynı diskte hardlink ile anında kurar; Steam oyunlarını libraryfolders.vdf'den otomatik bulur.</div>
          <div class="eco-row">
            <select class="eco-in" id="ecoMdSteam" style="max-width:220px"><option value="">Steam oyunu seç (${steam.length})...</option>${steam.map((g) => `<option value="${esc(g.dir)}">${esc(g.name)}</option>`).join("")}</select>
            <input class="eco-in" id="ecoMdArch" placeholder="Mod .zip veya profil .json yolu (C:\\...\\yama.zip)">
            <input class="eco-in" id="ecoMdGame" placeholder="Oyun klasörü (C:\\Games\\...)">
            <button class="eco-btn sec" id="ecoMdPrev">🔍 Ön İzle</button>
            <button class="eco-btn" id="ecoMdGo">Yedekle & Kur</button>
            <button class="eco-btn sec" id="ecoMdExp">💾 Profil Dışa Aktar</button>
            <button class="eco-btn sec" id="ecoMdImp">📥 Profil Kontrol</button>
          </div>
          <div id="ecoMdMsg" class="eco-hint"></div>
          <div class="eco-list" id="ecoMdList">${mods.map((m) => `
            <div class="eco-item">
              <span class="eco-tag">${esc(m.name)}</span>
              <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(m.game_dir)}</span>
              <button class="eco-btn sec" data-rollback="${esc(m.id)}" style="padding:4px 8px">Geri Al</button>
            </div>`).join("") || `<div class="eco-item eco-hint">Kurulu mod yedeği yok.</div>`}</div>
        </div>`;
      bd.querySelector("#ecoMdSteam").onchange = (e) => { if (e.target.value) bd.querySelector("#ecoMdGame").value = e.target.value; };
      bd.querySelector("#ecoMdPrev").onclick = async () => {
        const a = bd.querySelector("#ecoMdArch").value.trim();
        const g = bd.querySelector("#ecoMdGame").value.trim();
        const msg = bd.querySelector("#ecoMdMsg");
        if (!a || !g) return;
        const r = await api.mod_preview_diff(a, g);
        if (seq !== renderSeq) return;
        msg.innerHTML = r && r.ok
          ? `<span class="eco-ok">Ön İzleme (${r.total_files} dosya):</span> ${(r.added || []).length} yeni · ${(r.overwrite || []).length} üzerine yazılacak · ${(r.conflicts || []).length} çakışma`
          : `<span class="eco-err">Hata:</span> ${esc((r && r.error) || "bilinmiyor")}`;
      };
      bd.querySelector("#ecoMdGo").onclick = async () => {
        const a = bd.querySelector("#ecoMdArch").value.trim();
        const g = bd.querySelector("#ecoMdGame").value.trim();
        const msg = bd.querySelector("#ecoMdMsg");
        if (!a || !g) return;
        msg.textContent = "Yedeklenip kuruluyor...";
        const r = await api.mod_install(a, g);
        if (seq !== renderSeq) return;
        if (r.ok) { msg.innerHTML = `<span class="eco-ok">Kuruldu:</span> ${esc(r.name)} (${(r.backed_up || []).length} yedek, ${(r.added || []).length} yeni)`; renderTab(); }
        else msg.innerHTML = `<span class="eco-err">Hata:</span> ${esc(r.error || "bilinmiyor")}`;
      };
      bd.querySelector("#ecoMdExp").onclick = async () => {
        const g = bd.querySelector("#ecoMdGame").value.trim();
        const msg = bd.querySelector("#ecoMdMsg");
        if (!g) return;
        const r = await api.mod_export_profile(g, "");
        if (seq !== renderSeq) return;
        msg.innerHTML = r && r.ok
          ? `<span class="eco-ok">Profil kaydedildi:</span> ${esc(r.path)} (${r.mods_count} mod)`
          : `<span class="eco-err">Hata:</span> ${esc((r && r.error) || "bilinmiyor")}`;
      };
      bd.querySelector("#ecoMdImp").onclick = async () => {
        const a = bd.querySelector("#ecoMdArch").value.trim();
        const msg = bd.querySelector("#ecoMdMsg");
        if (!a) return;
        const r = await api.mod_import_profile(a);
        if (seq !== renderSeq) return;
        msg.innerHTML = r && r.ok
          ? `<span class="eco-ok">Profil (${r.total} mod):</span> ${(r.present || []).length} kurulu · ${(r.missing || []).length} eksik${(r.missing || []).length ? ` (${esc(r.missing.join(", "))})` : ""}`
          : `<span class="eco-err">Hata:</span> ${esc((r && r.error) || "bilinmiyor")}`;
      };
      bd.querySelectorAll("[data-rollback]").forEach((btn) => {
        btn.onclick = async () => {
          const r = await api.mod_rollback(btn.dataset.rollback);
          bd.querySelector("#ecoMdMsg").textContent = r.ok ? `Geri alındı (${r.restored} dosya geri yüklendi, ${r.removed} dosya silindi) ✓` : (r.error || "Hata");
          renderTab();
        };
      });
    } else if (activeTab === "bridge") {
      const br = await ld(api.phone_bridge_url?.(), {});
      if (seq !== renderSeq) return;
      const curCos = window.kamiSfx?.getCostume?.() || "default";
      const sfxOn = window.kamiSfx?.isOn?.() !== false;
      const bestUrl = br.tunnel_url || br.url || "http://localhost:47322/bridge";
      bd.innerHTML = `
        <div class="eco-card">
          <strong>Kami Booth / Pad / Snap (iPhone & iPad Köprüsü)</strong>
          <div class="eco-hint">Canlı 48kHz mikrofon kaydı (Booth) için Kami Oda tünelinden gelen HTTPS adresini kullan (anahtar URL'de otomatik gelir):</div>
          <div class="eco-hint">HTTPS Tünel (Önerilen): <code>${esc(br.tunnel_url || "(Kami Oda açık değil — sadece yerel ağ)")}</code></div>
          <div class="eco-hint">Yerel Ağ: <code>${esc(br.url || "http://localhost:47322/bridge")}</code> · Anahtar: <code>${esc(br.key || "(Ayarlar > Telefon)")}</code></div>
          <div class="eco-row"><button class="eco-btn sec" id="ecoBrCopy">Bağlantıyı Kopyala</button></div>
        </div>
        <div class="eco-card">
          <strong>Sunak Kostümü & Arayüz Ses Efektleri</strong>
          <div class="eco-row">
            <select class="eco-in" id="ecoCosSel" style="max-width:220px">
              ${(window.kamiSfx?.costumes || ["default", "oni", "ice", "gold", "cyber"]).map((c) => `<option value="${c}" ${c === curCos ? "selected" : ""}>${c.toUpperCase()}</option>`).join("")}
            </select>
            <label class="eco-hint" style="display:flex;align-items:center;gap:6px"><input type="checkbox" id="ecoSfxChk" ${sfxOn ? "checked" : ""}> Özel Ses Efektleri (SFX)</label>
          </div>
        </div>`;
      bd.querySelector("#ecoBrCopy").onclick = () => { navigator.clipboard?.writeText(bestUrl); bd.querySelector("#ecoBrCopy").textContent = "Kopyalandı ✓"; };
      bd.querySelector("#ecoCosSel").onchange = (e) => window.kamiSfx?.setCostume(e.target.value);
      bd.querySelector("#ecoSfxChk").onchange = (e) => { window.kamiSfx?.setOn(e.target.checked); if (e.target.checked) window.kamiSfx?.play("done"); };
    } else if (activeTab === "jobs") {
      const list = await ld(api.jobs_list?.(), []);
      if (seq !== renderSeq) return;
      bd.innerHTML = `
        <div class="eco-card">
          <div class="eco-row" style="justify-content:space-between">
            <strong>Tek İşler Merkezi (Hardsub, Ghost, Beat, PDF OCR)</strong>
            <button class="eco-btn sec" id="ecoJbRef">Yenile</button>
          </div>
          <div class="eco-list">${list.map((j) => `
            <div class="eco-item">
              <span class="eco-tag">${esc(j.status)} (${Number(j.pct) || 0}%)</span>
              <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"><strong>${esc(j.title)}</strong> — ${esc(j.msg)}</span>
              ${j.status === "running" ? `<button class="eco-btn sec" data-jcan="${esc(j.id)}" style="padding:3px 8px">İptal</button>` : ""}
            </div>`).join("") || `<div class="eco-item eco-hint">Henüz arka plan işi yok.</div>`}</div>
        </div>`;
      bd.querySelector("#ecoJbRef").onclick = () => renderTab();
      bd.querySelectorAll("[data-jcan]").forEach((b) => { b.onclick = async () => { await api.job_cancel?.(b.dataset.jcan); renderTab(); }; });
      if (list.some((j) => j.status === "running")) grabTimer = setTimeout(() => { if (!root.hidden && activeTab === "jobs") renderTab(); }, 1500);
    }
  }

  function topButton() {
    const st = document.querySelector("#sunak .sk-status");
    if (!st) { setTimeout(topButton, 700); return; }
    if (st.querySelector(".sk-eco")) return;
    const b = document.createElement("button");
    b.className = "sk-room sk-eco";
    b.title = "Kami Ekosistem: Kaydedici, Bypass, Sezon Kazıyıcı, Grab-All (Alt+E)";
    b.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 2l8 4.5v9L12 20l-8-4.5v-9z"/><path d="M12 11l8-4.5M12 11v9M12 11L4 6.5"/></svg><span>Ekosistem</span><i></i>`;
    b.onclick = () => openModal("rec");
    st.prepend(b);
  }

  window.addEventListener("pywebviewready", () => topButton());
  window.KPAL = window.KPAL || [];
  window.KPAL.push(() => [
    { ic: "🎥", t: "Ekran Kaydedici", sub: "kayıt / son 30sn klip", run: () => openModal("rec") },
    { ic: "🔓", t: "Kami Bypass", sub: "kısa / reklamlı link çöz", run: () => openModal("bypass") },
    { ic: "📺", t: "Tam Sezon Kazıyıcı", sub: "dizi bölümleri toplu indir", run: () => openModal("season") },
    { ic: "📦", t: "Kami Grab-All", sub: "IG / X / Pinterest / Reddit arşivi", run: () => openModal("grab") },
    { ic: "🔤", t: "Kami Hardsub", sub: "gömülü altyazıyı OCR ile Türkçe'ye çevir", run: () => openModal("hardsub") },
    { ic: "👻", t: "Kami Ghost", sub: "metadata sil + Content-ID kalkanı", run: () => openModal("ghost") },
    { ic: "🎵", t: "Kami Beat", sub: "vokal + beat BPM eşle & mashup", run: () => openModal("beat") },
    { ic: "🕵", t: "Kami Hunter", sub: "kayıp medya & yeraltı arşiv arama", run: () => openModal("hunter") },
    { ic: "🧩", t: "Kami Mod", sub: "1-tık mod kurucu & rollback", run: () => openModal("mod") },
    { ic: "📱", t: "Mobil Köprü & Sunak", sub: "Booth/Pad/Snap + Kostüm & SFX", run: () => openModal("bridge") },
  ]);
})();
