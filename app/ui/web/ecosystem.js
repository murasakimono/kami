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
          <button class="eco-tab on" data-tab="rec">Ekran Kaydedici & Geçiş</button>
          <button class="eco-tab" data-tab="bypass">Kami Bypass</button>
          <button class="eco-tab" data-tab="season">Sezon Kazıyıcı</button>
          <button class="eco-tab" data-tab="grab">Kami Grab-All</button>
          <button class="eco-tab" data-tab="hardsub">Kami Hardsub</button>
          <button class="eco-tab" data-tab="ghost">Kami Ghost</button>
        </div>
        <div class="eco-bd"></div>
      </div>`;
    document.body.appendChild(root);
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
    renderTab();
  }
  function closeModal() {
    stopGrabPoll();
    if (root) root.hidden = true;
  }

  async function renderTab() {
    const seq = ++renderSeq;
    stopGrabPoll();
    const bd = root.querySelector(".eco-bd");
    root.querySelectorAll(".eco-tab").forEach((b) => b.classList.toggle("on", b.dataset.tab === activeTab));

    if (activeTab === "rec") {
      const st = await api.rec_status().catch(() => ({}));
      if (seq !== renderSeq) return;
      bd.innerHTML = `
        <div class="eco-card">
          <div class="eco-row" style="justify-content:space-between">
            <strong>Ekran Kaydedici (ddagrab + WASAPI)</strong>
            <span class="eco-tag">${st.recording ? "KAYITTA" : (st.replay ? "REPLAY AÇIK" : "HAZIR")}</span>
          </div>
          <div class="eco-hint">Tüm ekranı düşük gecikmeli NVENC ile kaydeder. Kısayollar: Alt+F9 (Başlat/Durdur), Alt+F10 (Son 30sn Klip).</div>
          <div class="eco-row">
            <button class="eco-btn" id="ecoRecToggle">${st.recording ? "Kaydı Durdur (Alt+F9)" : "Kaydı Başlat (Alt+F9)"}</button>
            <button class="eco-btn sec" id="ecoRecReplay">Son 30sn Klip (Alt+F10)</button>
            <button class="eco-btn sec" id="ecoRecBuf">${st.replay ? "Replay Kapat" : "Replay Aç"}</button>
            <button class="eco-btn sec" id="ecoRecDir">Klipler Klasörü</button>
          </div>
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
      bd.querySelector("#ecoRecToggle").onclick = async () => {
        const r = await api.rec_toggle();
        recMsg = r.recording ? "Kayıt başlatıldı..." : (r.path ? `Kaydedildi: ${r.path}` : (r.error || "Tamamlandı"));
        renderTab();
      };
      bd.querySelector("#ecoRecReplay").onclick = async () => {
        const r = await api.rec_save_replay();
        recMsg = r.ok ? `Klip kaydedildi: ${r.path}` : `Hata: ${r.error || "Replay kapalı"}`;
        bd.querySelector("#ecoRecMsg").textContent = recMsg;
      };
      bd.querySelector("#ecoRecBuf").onclick = async () => { await api.rec_replay(!st.replay); renderTab(); };
      bd.querySelector("#ecoRecDir").onclick = () => api.rec_open_folder();
      bd.querySelector("#ecoGoStudio").onclick = () => { closeModal(); api.studio_show(""); };
      bd.querySelector("#ecoGoRoom").onclick = () => { closeModal(); api.room_open?.(true); };
      bd.querySelector("#ecoGoPic").onclick = () => { closeModal(); api.picture_open_editor?.(); };
    } else if (activeTab === "bypass") {
      bd.innerHTML = `
        <div class="eco-card">
          <strong>Kami Bypass (Kısaltma & Reklamlı Ara Link Çözücü)</strong>
          <div class="eco-hint">Desteklenenler: ouo.io, tr.link, ay.link, linkvertise, cuty.io, bc.vc, pastebin, rentry.</div>
          <div class="eco-row">
            <input class="eco-in" id="ecoByUrl" placeholder="https://ouo.io/... veya https://tr.link/...">
            <button class="eco-btn" id="ecoByGo">Çöz</button>
          </div>
          <div id="ecoByRes" class="eco-hint"></div>
        </div>`;
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
      let st = await api.grab_all_status().catch(() => ({}));
      if (seq !== renderSeq) return;
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
          <div class="eco-hint">Instagram, X (Twitter), TikTok, Pinterest ve Reddit profillerini / panolarını klasörleyip meta verisiyle indirir.<br>Hedef: <code>${esc(st.dest || "İndirilenler/Grab-All")}</code></div>
          <div class="eco-row">
            <input class="eco-in" id="ecoGrUrl" placeholder="https://www.instagram.com/kullanici/ veya x.com/...">
            <input class="eco-in" id="ecoGrLim" type="number" min="0" placeholder="Limit (0=tümü)" style="max-width:130px;flex:0">
            <button class="eco-btn" id="ecoGrGo">Arşivi Başlat</button>
          </div>
          <div id="ecoGrMsg" class="eco-hint">${formatGrabMsg(st)}</div>
        </div>`;
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
        const msg = bd.querySelector("#ecoGrMsg");
        if (!u) return;
        msg.textContent = st.installed
          ? "Başlatılıyor..."
          : "gallery-dl aracı kuruluyor (ilk seferde ~1-3 dk sürebilir)...";
        const r = await api.grab_all_start(u, lim);
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
          <div class="eco-hint">Videodaki gömülü yabancı altyazıyı alt banttan okur, Türkçe .srt üretir ve isteğe bağlı maskeli bantla videoya gömer.</div>
          <div class="eco-row">
            <input class="eco-in" id="ecoHsPath" placeholder="C:\\Users\\...\\video.mp4">
            <input class="eco-in" id="ecoHsLang" placeholder="Dil (boş=oto, en, ja)" style="max-width:160px;flex:0">
          </div>
          <div class="eco-row">
            <label class="eco-hint" style="display:flex;align-items:center;gap:6px"><input type="checkbox" id="ecoHsBurn"> Eski altyazıyı karartıp Türkçe altyazıyı videoya göm</label>
            <button class="eco-btn" id="ecoHsGo" style="margin-left:auto">Çöz & Çevir</button>
          </div>
          <div id="ecoHsMsg" class="eco-hint"></div>
        </div>`;
      bd.querySelector("#ecoHsGo").onclick = async () => {
        const p = bd.querySelector("#ecoHsPath").value.trim();
        const lang = bd.querySelector("#ecoHsLang").value.trim();
        const burn = bd.querySelector("#ecoHsBurn").checked;
        const msg = bd.querySelector("#ecoHsMsg");
        if (!p) return;
        msg.textContent = "Kareler çıkarılıp OCR ile okunuyor (video uzunluğuna göre 10-60 sn sürebilir)...";
        const r = await api.hardsub_extract(p, lang, burn);
        if (seq !== renderSeq) return;
        msg.innerHTML = r.ok
          ? `<span class="eco-ok">Tamamlandı (${Number(r.cues) || 0} satır):</span> <code>${esc(r.srt)}</code>${r.video ? `<br>Video: <code>${esc(r.video)}</code>` : ""}`
          : `<span class="eco-err">Hata:</span> ${esc(r.error || "bilinmiyor")}`;
      };
    } else if (activeTab === "ghost") {
      bd.innerHTML = `
        <div class="eco-card">
          <strong>Kami Ghost (Metadata Temizleyici & Content-ID Kalkanı)</strong>
          <div class="eco-hint">Görsel, ses ve videodan tüm EXIF/ID3/FFmpeg parmak izlerini siler. Kalkan açıksa algılanmaz mikro pitch/tempo & piksel değişimi uygular.</div>
          <div class="eco-row">
            <input class="eco-in" id="ecoGhPath" placeholder="C:\\Users\\...\\dosya.mp4 / .mp3 / .png">
          </div>
          <div class="eco-row">
            <label class="eco-hint" style="display:flex;align-items:center;gap:6px"><input type="checkbox" id="ecoGhShield"> Content-ID Kalkanı (mikro pitch/piksel)</label>
            <button class="eco-btn" id="ecoGhGo" style="margin-left:auto">Temizle</button>
          </div>
          <div id="ecoGhMsg" class="eco-hint"></div>
        </div>`;
      bd.querySelector("#ecoGhGo").onclick = async () => {
        const p = bd.querySelector("#ecoGhPath").value.trim();
        const shield = bd.querySelector("#ecoGhShield").checked;
        const msg = bd.querySelector("#ecoGhMsg");
        if (!p) return;
        msg.textContent = "İşleniyor...";
        const r = await api.ghost_process(p, shield);
        if (seq !== renderSeq) return;
        msg.innerHTML = r.ok
          ? `<span class="eco-ok">Hazır:</span> <code>${esc(r.out)}</code>`
          : `<span class="eco-err">Hata:</span> ${esc(r.error || "bilinmiyor")}`;
      };
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
  ]);
})();
