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
          <button class="eco-tab" data-tab="beat">Kami Beat</button>
          <button class="eco-tab" data-tab="hunter">Kami Hunter</button>
          <button class="eco-tab" data-tab="mod">Kami Mod</button>
          <button class="eco-tab" data-tab="bridge">Köprü & Sunak</button>
          <button class="eco-tab" data-tab="jobs">İşler</button>
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
      const [st, ch] = await Promise.all([api.rec_status().catch(() => ({})), api.chain_get?.().catch(() => ({})) || {}]);
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
            <input class="eco-in" id="ecoRecWin" placeholder="Pencere başlığı (opsiyonel, boş=tam ekran)" style="max-width:240px">
            <button class="eco-btn sec" id="ecoRecWinGo">Pencere/Bölge Kaydet</button>
          </div>
          <div class="eco-row">
            <input class="eco-in" id="ecoRecFile" placeholder="Son kayıt veya klip yolu (GIF / Discord için)">
            <button class="eco-btn sec" id="ecoRecGif">GIF Yap</button>
            <button class="eco-btn sec" id="ecoRecDisc">Discord'a Sığdır</button>
          </div>
          <label class="eco-hint" style="display:flex;align-items:center;gap:6px"><input type="checkbox" id="ecoChRecStu" ${ch.chain_rec_studio ? "checked" : ""}> Zincir: Kayıt bitince otomatik Studio'da aç</label>
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
      bd.querySelector("#ecoGoStudio").onclick = () => { closeModal(); api.studio_show(""); };
      bd.querySelector("#ecoGoRoom").onclick = () => { closeModal(); api.room_open?.(true); };
      bd.querySelector("#ecoGoPic").onclick = () => { closeModal(); api.picture_open_editor?.(); };
    } else if (activeTab === "bypass") {
      const ch = await api.chain_get?.().catch(() => ({})) || {};
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
      let [st, ch] = await Promise.all([api.grab_all_status().catch(() => ({})), api.chain_get?.().catch(() => ({})) || {}]);
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
        bd.querySelector("#ecoBtMsg").innerHTML = r?.ok ? `<span class="eco-ok">4-Kanal ayrıştırma başlatıldı (${esc(r.job_id)}) ✓</span>` : (r?.error || "Hata");
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
            <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(it.url)}">${esc(it.title)}</span>
            <button class="eco-btn sec" data-huprev="${idx}" style="padding:4px 8px">▶ Dinle</button>
            <button class="eco-btn sec" data-huadd="${idx}" style="padding:4px 8px">İndir</button>
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
      };
    } else if (activeTab === "mod") {
      const [mods, steam] = await Promise.all([api.mod_list().catch(() => []), api.mod_steam_games?.().catch(() => []) || []]);
      if (seq !== renderSeq) return;
      bd.innerHTML = `
        <div class="eco-card">
          <strong>Kami Mod (1-Tık Mod / Türkçe Yama Kurucu & Rollback)</strong>
          <div class="eco-hint">.zip mod arşivini aynı diskte hardlink ile anında kurar; Steam oyunlarını libraryfolders.vdf'den otomatik bulur.</div>
          <div class="eco-row">
            <select class="eco-in" id="ecoMdSteam" style="max-width:220px"><option value="">Steam oyunu seç (${steam.length})...</option>${steam.map((g) => `<option value="${esc(g.dir)}">${esc(g.name)}</option>`).join("")}</select>
            <input class="eco-in" id="ecoMdArch" placeholder="Mod .zip yolu (C:\\...\\yama.zip)">
            <input class="eco-in" id="ecoMdGame" placeholder="Oyun klasörü (C:\\Games\\...)">
            <button class="eco-btn" id="ecoMdGo">Yedekle & Kur</button>
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
      bd.querySelectorAll("[data-rollback]").forEach((btn) => {
        btn.onclick = async () => {
          const r = await api.mod_rollback(btn.dataset.rollback);
          bd.querySelector("#ecoMdMsg").textContent = r.ok ? `Geri alındı (${r.restored} dosya geri yüklendi, ${r.removed} dosya silindi) ✓` : (r.error || "Hata");
          renderTab();
        };
      });
    } else if (activeTab === "bridge") {
      const br = await api.phone_bridge_url().catch(() => ({}));
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
      const list = await api.jobs_list?.().catch(() => []) || [];
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
