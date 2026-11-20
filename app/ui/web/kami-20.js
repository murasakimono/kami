// Kami 2.0 (v2.0.0) OS Katmani:
// - A2: Zaman/Sayfa Damgali Yuzen Karalama Karti (Scratchpad, Alt+N veya ust dugme)
// - A3: Birlesik Arka Plan Islem & Kuyruk HUD'u (ORTADA IS YOKKEN TAMAMEN GIZLENIR — active_jobs == 0 => hidden)
// - A4: Basili Tutunca Acilan Baglamsal Kisayol Kopya Kagidi (Turkce Q klavye uyumlu: F1 basili tutunca veya Shift+* (?) veya Alt+K)
// - #13: Fitts's Law 8-Dilimli Radyal Hizli Eylem Halkasi (Orta tus veya Alt+Sag Tik)
// - #14: Implicit Input Pano Niyet Chip'i (Odak calmadan 4 sn gorunen akilli aksiyon)
// - #16: Oturum Snapshot (Kaydet / Geri Yukle)
"use strict";
(() => {
  const callApi = () => window.pywebview?.api;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const st = document.createElement("style");
  st.id = "kami20Style";
  st.textContent = `
    [hidden] { display: none !important; }
    /* A3: Birlesik Arka Plan Islem & Kuyruk HUD (is yokken display:none — ust-orta dinamik hap) */
    #k20JobHud {
      position: fixed; top: 10px; left: 0; right: 0; bottom: auto; margin-inline: auto; width: fit-content; z-index: 82;
      background: rgba(15, 11, 24, .95); border: 1px solid #2EE6A6;
      border-radius: 999px; padding: 6px 14px; color: #EDE9F6;
      font: 600 12px "Chakra Petch", system-ui, sans-serif;
      display: inline-flex; align-items: center; gap: 9px;
      box-shadow: 0 10px 28px rgba(0,0,0,.6), 0 0 18px rgba(46,230,166,.22);
      cursor: pointer; transition: transform .15s ease;
    }
    #k20JobHud:hover { transform: translateY(1px); }
    #k20JobHud .spin {
      width: 12px; height: 12px; border-radius: 50%;
      border: 2px solid rgba(46,230,166,.25); border-top-color: #2EE6A6;
      animation: k20Spin .85s linear infinite;
    }
    @keyframes k20Spin { to { transform: rotate(360deg); } }
    #k20JobPop {
      position: fixed; top: 48px; left: 0; right: 0; bottom: auto; margin-inline: auto; z-index: 83;
      width: 310px; max-height: 280px; overflow-y: auto;
      background: rgba(16, 12, 26, .98); border: 1px solid rgba(157,107,255,.45);
      border-radius: 12px; padding: 11px 13px; color: #EDE9F6;
      box-shadow: 0 16px 40px rgba(0,0,0,.68); font: 500 12px "Chakra Petch", sans-serif;
    }
    .k20-jrow { display:flex; flex-direction:column; gap:3px; padding:6px 0; border-bottom:1px solid rgba(255,255,255,.06); }
    .k20-jbar { height:4px; background:#231A38; border-radius:99px; overflow:hidden; }
    .k20-jbar i { display:block; height:100%; background:linear-gradient(90deg,#9D6BFF,#2EE6A6); }

    /* A2: Zaman/Sayfa Damgali Yuzen Karalama Karti (Scratchpad) */
    #k20Scratch {
      position: fixed; right: 68px; top: 68px; z-index: 84;
      width: 325px; background: rgba(17, 13, 28, .97); border: 1px solid #9D6BFF;
      border-radius: 13px; padding: 12px 14px; color: #EDE9F6;
      box-shadow: 0 18px 46px rgba(0,0,0,.7); font: 500 12px "Chakra Petch", system-ui, sans-serif;
      display: flex; flex-direction: column; gap: 8px;
    }
    #k20Scratch textarea {
      width: 100%; background: #0A0810; border: 1px solid #2D2246; border-radius: 8px;
      color: #fff; padding: 8px; font: inherit; resize: vertical; min-height: 54px; outline: none;
    }
    #k20Scratch textarea:focus { border-color: #2EE6A6; }
    .k20-nlist { max-height: 210px; overflow-y: auto; display: flex; flex-direction: column; gap: 6px; }
    .k20-ncard { background: #161124; border: 1px solid rgba(157,107,255,.24); border-radius: 8px; padding: 7px 9px; position: relative; }
    .k20-ncard small { color: #2EE6A6; font-size: 10.5px; display: block; margin-bottom: 3px; }
    .k20-ncard button { position: absolute; top: 5px; right: 6px; border: 0; background: none; color: #8E86A3; cursor: pointer; }

    /* A4: Basili Tutunca Acilan Baglamsal Kisayol Kopya Kagidi (F1 / Alt+K / Shift+*) */
    #k20Cheat {
      position: fixed; inset: 0; z-index: 9998; background: rgba(6, 4, 12, .82);
      backdrop-filter: blur(8px); display: grid; place-items: center; padding: 24px;
    }
    .k20-cbox {
      width: min(680px, 92vw); background: #120E1E; border: 1px solid #9D6BFF;
      border-radius: 15px; padding: 18px 22px; color: #EDE9F6;
      box-shadow: 0 24px 64px rgba(0,0,0,.75); font: 500 12.5px "Chakra Petch", system-ui, sans-serif;
    }
    .k20-cgrid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px 18px; margin-top: 12px; }
    .k20-crow { display: flex; justify-content: space-between; align-items: center; padding: 5px 8px; background: rgba(255,255,255,.03); border-radius: 7px; }
    .k20-crow kbd { background: #231A3A; border: 1px solid #9D6BFF; color: #2EE6A6; border-radius: 5px; padding: 2px 7px; font: 700 11px Consolas, monospace; }

    /* #13: Fitts's Law 8-Dilimli Radyal Halka (Tam Simetrik Dairesel) */
    #k20Radial {
      position: fixed; inset: 0; z-index: 9995; pointer-events: auto;
      background: rgba(6, 4, 12, .28);
    }
    .k20-rsvg {
      position: fixed; width: 280px; height: 280px; margin-left: -140px; margin-top: -140px;
      pointer-events: none;
    }
    .k20-rhub {
      position: fixed; width: 44px; height: 44px; margin-left: -22px; margin-top: -22px;
      border-radius: 50%; background: rgba(18, 13, 30, .96); border: 1.5px solid rgba(46,230,166,.65);
      color: #2EE6A6; font: 700 14px "Chakra Petch", sans-serif;
      display: grid; place-items: center; cursor: pointer;
      box-shadow: 0 0 22px rgba(46,230,166,.28); transition: transform .14s ease, background .14s ease;
    }
    .k20-rhub:hover { transform: scale(1.1); background: #231A38; }
    .k20-rnode {
      position: fixed; width: 68px; height: 68px; margin-left: -34px; margin-top: -34px;
      box-sizing: border-box; padding: 0;
      background: rgba(18, 13, 30, .96); border: 1.5px solid rgba(157,107,255,.65); border-radius: 50%;
      color: #EDE9F6; font: 600 11px "Chakra Petch", sans-serif;
      display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 3px;
      cursor: pointer;
      box-shadow: 0 10px 26px rgba(0,0,0,.72); transition: transform .14s cubic-bezier(.22,1,.36,1), border-color .14s, background .14s, color .14s;
    }
    .k20-rnode svg { width: 18px; height: 18px; stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
    .k20-rnode:hover { transform: scale(1.13); border-color: #2EE6A6; background: #261942; color: #2EE6A6; box-shadow: 0 0 20px rgba(46,230,166,.35); }
    /* AI MP3 Whisper + UVR5 Surukle-Birak Studyosu */
    #k20AiModal {
      position: fixed; inset: 0; z-index: 9100; background: rgba(6, 4, 12, .82);
      backdrop-filter: blur(8px); display: grid; place-items: center; padding: 18px;
    }
    .k20-aibox {
      width: min(680px, 94vw); max-height: 88vh; overflow-y: auto;
      background: #120E1D; border: 1px solid rgba(157,107,255,.5); border-radius: 14px;
      padding: 18px 20px; color: #EDE9F6; font: 500 13px "Chakra Petch", system-ui, sans-serif;
      display: flex; flex-direction: column; gap: 12px; box-shadow: 0 24px 64px rgba(0,0,0,.75);
    }
    .k20-aidrop {
      border: 1.5px dashed rgba(157,107,255,.55); border-radius: 12px; padding: 24px 18px;
      background: rgba(24, 18, 38, .75); text-align: center; cursor: pointer;
      transition: border-color .16s, background .16s;
    }
    .k20-aidrop:hover, .k20-aidrop.drag { border-color: #2EE6A6; background: rgba(46,230,166,.08); }
    .k20-airow {
      display: flex; align-items: center; justify-content: space-between; gap: 10px;
      background: #181226; border: 1px solid rgba(157,107,255,.26); border-radius: 10px; padding: 10px 12px;
    }
  `;
  document.head.appendChild(st);

  // ---- 1. A3: Birlesik Arka Plan Islem & Kuyruk HUD'u (ORTADA IS YOKKEN TAMAMEN GIZLI) ----
  const hud = document.createElement("div");
  hud.id = "k20JobHud";
  hud.hidden = true;
  const pop = document.createElement("div");
  pop.id = "k20JobPop";
  pop.className = "km-pop-origin";
  pop.style.setProperty("--km-ox", "center");
  pop.style.setProperty("--km-oy", "top");
  pop.hidden = true;
  document.body.append(hud, pop);

  let popOpen = false;
  hud.onclick = (e) => {
    e.stopPropagation();
    popOpen = !popOpen;
    pop.hidden = !popOpen;
  };
  document.addEventListener("click", (e) => {
    if (popOpen && !e.target.closest?.("#k20JobHud, #k20JobPop")) {
      popOpen = false;
      pop.hidden = true;
    }
  });

  async function pollActiveJobs() {
    if (document.hidden) return;
    const r = await callApi()?.active_jobs_hud?.().catch(() => null);
    const cnt = Number(r?.count || 0);
    if (true) {
      // HUD ana arayüzde KALDIRILDI (kullanıcı: indirme kartı zaten ilerlemeyi gösteriyor).
      // İş listesi Ekosistem > İşler'de; active_jobs_hud API'si AI LRC akışında (aşağıda) kullanılmaya devam eder.
      hud.hidden = true;
      pop.hidden = true;
      popOpen = false;
      return;
    }
    const items = r.items || [];
    const avgPct = Math.round(items.reduce((a, b) => a + Number(b.pct || 0), 0) / Math.max(1, items.length));
    hud.hidden = false;
    hud.innerHTML = `<span class="spin"></span><span>${cnt} Aktif İş · %${avgPct}</span>`;
    if (popOpen) {
      pop.innerHTML = `<b style="display:block;margin-bottom:6px;color:#2EE6A6">Aktif Arka Plan İşleri (${cnt})</b>` +
        items.map((it) => `
          <div class="k20-jrow">
            <div style="display:flex;justify-content:space-between"><b>${esc(it.kind)}</b><span>%${it.pct}</span></div>
            <small style="color:#9A90AB;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(it.title)}</small>
            <div class="k20-jbar"><i style="width:${Math.min(100, Math.max(4, it.pct))}%"></i></div>
          </div>
        `).join("");
    }
  }
  if (!location.pathname.endsWith("mini-island.html") && !location.pathname.endsWith("pin.html")) {
    // HUD kaldırıldığı için periyodik yoklama da kaldırıldı.
  }

  // ---- 2. A2: Zaman/Sayfa Damgali Yuzen Karalama Karti (Alt+N) ----
  const scBox = document.createElement("div");
  scBox.id = "k20Scratch";
  scBox.hidden = true;
  scBox.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center">
      <b style="color:#C4B5FD">📝 Damgalı Karalama Kartı (Alt+N)</b>
      <div style="display:flex;gap:5px">
        <button class="btn" id="k20SnapSave" title="Açık Oturumu Kaydet (Snapshot)" style="padding:2px 7px;font-size:10.5px">📸 Oturum</button>
        <button class="btn" id="k20ScClose" style="padding:2px 7px;font-size:11px">✕</button>
      </div>
    </div>
    <textarea id="k20ScIn" placeholder="Notunu yaz… (Aktif video saniyesi / PDF sayfası otomatik damgalanır)"></textarea>
    <div style="display:flex;justify-content:space-between;align-items:center">
      <small id="k20ScCtx" style="color:#2EE6A6"></small>
      <button class="btn pri" id="k20ScAdd" style="padding:4px 11px;font-size:11.5px">+ Damgala &amp; Kaydet</button>
    </div>
    <div class="k20-nlist" id="k20ScList"></div>
  `;
  document.body.appendChild(scBox);

  function detectCurrentStamp() {
    const pageTitle = document.title || "Kami";
    const vid = document.getElementById("plVideo");
    if (vid && vid.currentTime > 0) {
      const s = Math.floor(vid.currentTime);
      return { context: "Kami Player", path: window.PL?.info?.path || "", stamp: `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}` };
    }
    if (window.RD?.doc) {
      return { context: "Kami Reader", path: window.RD.doc.path || "", stamp: `Sayfa ${(window.RD.page || 0) + 1}` };
    }
    if (window.ST?.p) {
      return { context: "Kami Studio", path: window.ST.p.name || "", stamp: `${Number(window.ST.t || 0).toFixed(1)} sn` };
    }
    return { context: pageTitle, path: "", stamp: new Date().toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" }) };
  }

  async function refreshScratchpad() {
    const info = detectCurrentStamp();
    const ctxEl = scBox.querySelector("#k20ScCtx");
    if (ctxEl) ctxEl.textContent = `${info.context} · ${info.stamp}`;
    const r = await callApi()?.scratchpad_load?.().catch(() => null);
    const notes = r?.notes || [];
    const listEl = scBox.querySelector("#k20ScList");
    if (!listEl) return;
    listEl.innerHTML = notes.map((n) => `
      <div class="k20-ncard">
        <small>${esc(n.context)} · <b>${esc(n.stamp)}</b></small>
        <div>${esc(n.text)}</div>
        <button data-ndel="${n.id}" title="Sil">✕</button>
      </div>
    `).join("") || `<small style="color:#8E86A3">Henüz damgalı not yok.</small>`;
    listEl.querySelectorAll("[data-ndel]").forEach((b) => {
      b.onclick = async () => {
        await callApi()?.scratchpad_delete?.(+b.dataset.ndel);
        refreshScratchpad();
      };
    });
  }

  scBox.querySelector("#k20ScClose").onclick = () => { scBox.hidden = true; };
  scBox.querySelector("#k20ScAdd").onclick = async () => {
    const inp = scBox.querySelector("#k20ScIn");
    const txt = inp.value.trim();
    if (!txt) return;
    const info = detectCurrentStamp();
    await callApi()?.scratchpad_add?.(txt, info.context, info.path, info.stamp);
    inp.value = "";
    refreshScratchpad();
  };
  scBox.querySelector("#k20SnapSave").onclick = async () => {
    const r = await callApi()?.session_snapshot_save?.("Hızlı Oturum").catch(() => null);
    if (r?.ok) scBox.querySelector("#k20ScCtx").textContent = "✓ Oturum Snapshot kaydedildi";
  };

  function toggleScratchpad() {
    scBox.hidden = !scBox.hidden;
    if (!scBox.hidden) {
      refreshScratchpad();
      scBox.querySelector("#k20ScIn")?.focus();
    }
  }
  window.toggleKamiScratchpad = toggleScratchpad;

  // ---- 3. A4: Basili Tutunca Acilan Baglamsal Kisayol Kopya Kagidi (F1 basili tutunca / Alt+K / Shift+*) ----
  const cheat = document.createElement("div");
  cheat.id = "k20Cheat";
  cheat.hidden = true;
  document.body.appendChild(cheat);

  const CHEAT_MAP = {
    Kami: [
      ["F1 (Basılı Tut) / Alt+K", "Kısayol Kopya Kâğıdı"],
      ["Ctrl + K", "Omnisearch & Komut Paleti"],
      ["Alt + N", "Damgalı Karalama Kartı"],
      ["Alt + E", "Kami Ekosistem & Araçlar"],
      ["Ctrl + Shift + S", "Bu Şarkı Ne? (10 sn Anlık)"],
      ["Ctrl + Shift + G", "Arka Plan Şarkı Günlüğü"],
      ["Ctrl + Shift + L", "Kami Lens Hızlı Yakala"],
      ["Alt + F9 / Alt + F10", "Ekran Kaydı / 30 sn Replay"],
      ["F2 / Delete", "İndirmeyi Yeniden Adlandır / Sil"],
      ["Alt + Sağ Tık", "8-Dilimli Radyal Hızlı Halka"],
    ],
    "Kami Studio": [
      ["Space", "Oynat / Duraklat"],
      ["S", "Klibi Böl (Split)"],
      ["Q / W", "Sol / Sağ Kırp (Ripple Trim)"],
      ["I / O / L", "Döngü Giriş / Çıkış / Aç-Kapat"],
      ["M", "Zaman Çizelgesi İşareti Ekle"],
      ["Ctrl + Tekerlek", "İmleç Odaklı Hassas Zoom"],
      ["Orta Tuş Sürükle", "Zaman Çizelgesini Kaydır (Pan)"],
      ["Shift + F", "Kare Dondur (Freeze Frame)"],
    ],
    "Kami Reader": [
      ["← / → veya Space", "Önceki / Sonraki Sayfa (3D Kıvrım)"],
      ["A / [ / ]", "Otomatik Kaydırma Aç & Hız Ayarla"],
      ["N / F / R", "Gece Modu / Sığdır / Manga Yönü"],
      ["T / O", "Sesli Oku (Piper TTS) / Sayfa OCR"],
      ["🧠 Sınav / 📌 Pano", "Bulanık Recall Modu / LiquidText Pano"],
      [", / .", "E-Kitap Yazı Boyutu Küçült / Büyüt"],
    ],
    Kamify: [
      ["Doğrudan Harf Yaz", "Anlık Kütüphane Süzgeci (Tauon)"],
      ["A / B", "A-B Kesintisiz Döngü Aralığı"],
      ["F8 (LRC Editörde)", "Aktif Şarkı Satırına Zaman Damgası Vur"],
      ["Ctrl + Shift + G", "Sistem Sesi Şarkı Günlüğüne Kaydet"],
    ],
    "Kami Cleaner": [
      ["Space", "Seçili Dosyayı Anında Önizle (QuickLook)"],
      ["Çift Tık (Treemap)", "Klasörün İçine Gir"],
      ["Kami Dust Sekmesi", "Kaldırılan Programların Yetim Artıkları"],
      ["Klasör Bekçisi", "Yaşlanmış Dosyaları Otomatik Düzenle"],
    ],
  };

  function renderCheatSheet() {
    const title = document.title || "Kami";
    const key = Object.keys(CHEAT_MAP).find((k) => title.includes(k)) || "Kami";
    const rows = [...(CHEAT_MAP[key] || []), ...(key !== "Kami" ? CHEAT_MAP.Kami.slice(0, 4) : [])];
    cheat.innerHTML = `
      <div class="k20-cbox">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <b style="font-size:15px;color:#2EE6A6">⌨ ${esc(key)} — Bağlamsal Kısayol Kopya Kâğıdı</b>
          <small style="color:#9A90AB">F1'i bırakınca veya Esc ile kapanır</small>
        </div>
        <div class="k20-cgrid">
          ${rows.map(([k, d]) => `<div class="k20-crow"><span>${esc(d)}</span><kbd>${esc(k)}</kbd></div>`).join("")}
        </div>
      </div>
    `;
  }
  cheat.onclick = () => { cheat.hidden = true; };

  let f1Held = false;
  document.addEventListener("keydown", (e) => {
    const inField = e.target?.matches?.("input, textarea, select") || e.target?.isContentEditable;
    if (e.key === "F1") {
      e.preventDefault();
      if (!f1Held) {
        f1Held = true;
        renderCheatSheet();
        cheat.hidden = false;
      }
      return;
    }
    if (e.altKey && (e.key === "k" || e.key === "K")) {
      e.preventDefault();
      renderCheatSheet();
      cheat.hidden = !cheat.hidden;
      return;
    }
    if (e.altKey && (e.key === "n" || e.key === "N")) {
      e.preventDefault();
      toggleScratchpad();
      return;
    }
    if (!inField && e.key === "?") {
      e.preventDefault();
      renderCheatSheet();
      cheat.hidden = !cheat.hidden;
    } else if (e.key === "Escape" && !cheat.hidden) {
      cheat.hidden = true;
    }
  }, true);

  document.addEventListener("keyup", (e) => {
    if (e.key === "F1") {
      f1Held = false;
      cheat.hidden = true;
    }
  }, true);

  // ---- 4. #13: Fitts's Law 8-Dilimli Radyal Hizli Eylem Halkasi (Alt + Sag Tik) ----
  let radialEl = null;
  function closeRadial() { radialEl?.remove(); radialEl = null; }
  document.addEventListener("contextmenu", (e) => {
    if (!e.altKey) return;
    e.preventDefault();
    closeRadial();
    const cx = Math.max(155, Math.min(window.innerWidth - 155, e.clientX));
    const cy = Math.max(155, Math.min(window.innerHeight - 155, e.clientY));
    const actions = [
      ["Player", '<svg viewBox="0 0 24 24"><polygon points="7 4 20 12 7 20 7 4"/></svg>', () => callApi()?.player_show?.({ library: true })],
      ["Studio", '<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 9h18M8 5v4M16 5v4"/></svg>', () => callApi()?.studio_show?.("")],
      ["Picture", '<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-9 9"/></svg>', () => callApi()?.picture_open?.("")],
      ["Reader", '<svg viewBox="0 0 24 24"><path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 19V5"/></svg>', () => callApi()?.reader_show?.("")],
      ["Games", '<svg viewBox="0 0 24 24"><rect x="2" y="7" width="20" height="10" rx="5"/><path d="M7 10v4M5 12h4M15.5 11h.01M18 13h.01"/></svg>', () => callApi()?.games_open?.()],
      ["Kamify", '<svg viewBox="0 0 24 24"><path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/></svg>', () => callApi()?.music_open?.()],
      ["Cleaner", '<svg viewBox="0 0 24 24"><path d="M3 5h18l-7 8v6l-4 2v-8z"/></svg>', () => callApi()?.cleaner_open?.()],
      ["AI Söz", '<svg viewBox="0 0 24 24"><path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z"/><path d="M19 11a7 7 0 0 1-14 0M12 18v3"/></svg>', () => window.openKamiAiLyricsStudio?.()],
    ];
    radialEl = document.createElement("div");
    radialEl.id = "k20Radial";
    const R = 112;
    const ringSvg = `<svg class="k20-rsvg" style="left:${cx}px;top:${cy}px" viewBox="0 0 280 280">
      <circle cx="140" cy="140" r="${R}" fill="none" stroke="rgba(157,107,255,0.28)" stroke-width="1.5" stroke-dasharray="4 6"/>
      <circle cx="140" cy="140" r="36" fill="none" stroke="rgba(46,230,166,0.18)" stroke-width="1"/>
    </svg>`;
    const hubHtml = `<button type="button" class="k20-rhub" style="left:${cx}px;top:${cy}px" title="Kapat">✕</button>`;
    radialEl.innerHTML = ringSvg + hubHtml + actions.map(([lbl, ico], i) => {
      const ang = (i / actions.length) * Math.PI * 2 - Math.PI / 2;
      const x = Math.round(cx + Math.cos(ang) * R);
      const y = Math.round(cy + Math.sin(ang) * R);
      return `<button type="button" class="k20-rnode" data-ri="${i}" style="left:${x}px;top:${y}px">${ico}<span>${lbl}</span></button>`;
    }).join("");
    document.body.appendChild(radialEl);
    radialEl.onclick = (ev) => {
      const b = ev.target.closest("[data-ri]");
      const idx = b ? +b.dataset.ri : -1;
      closeRadial();
      if (idx >= 0) actions[idx][2]();
    };
  });

  // ---- 5. Donusturucu Tarzi Surukle-Birak AI Altyazi · Vokal · MP3 Zaman Damgali Lirik Studyosu ----
  let aiModal = null, aiDropPoll = 0;
  const aiFiles = [];

  async function processAiAudioFile(path, strong = true) {
    if (!path) return;
    let entry = aiFiles.find((x) => x.path === path);
    if (!entry) {
      entry = { path, name: path.split(/[\\/]/).pop() || path, status: "running", msg: strong ? "UVR5 Vokal Ayırma + Whisper Güçlü Mod başlatıldı…" : "Whisper başlatıldı…" };
      aiFiles.unshift(entry);
    } else {
      entry.status = "running";
      entry.msg = strong ? "UVR5 Vokal Ayırma + Whisper Güçlü Mod çalışıyor…" : "Whisper çalışıyor…";
    }
    renderAiFileList();
    const r = await (callApi()?.music_whisper_lrc || callApi()?.music_lrc_whisper)?.(path, "tr", strong).catch((e) => ({ ok: false, error: String(e) }));
    if (!r?.ok) {
      entry.status = "error";
      entry.toolMissing = r?.error === "tool_missing" ? (r.tool || "whisper") : "";
      entry.msg = r?.error === "tool_missing"
        ? `Önce ${r.tool === "uvr" ? "UVR5" : "Whisper"} ortamı kurulmalı`
        : (`Hata: ${r?.error || "başlatılamadı"}`);
      renderAiFileList();
      return;
    }
    entry.toolMissing = "";
    // Arka plan isini yokla (.lrc olusana veya is bitene kadar)
    for (let step = 0; step < 300; step++) {
      await new Promise((res) => setTimeout(res, 1500));
      if (r.job_id && callApi()?.music_lrc_job_status) {
        const jst = await callApi().music_lrc_job_status(r.job_id).catch(() => null);
        if (jst?.ok) {
          if (jst.state === "running") {
            entry.msg = `${jst.msg || "İşleniyor…"} · %${Math.round((jst.p || 0) * 100)}`;
            renderAiFileList();
            continue;
          }
          if (jst.state === "error" || (jst.result && jst.result.ok === false)) {
            entry.status = "error";
            entry.toolMissing = jst.result?.error === "tool_missing" ? (jst.result.tool || "whisper") : "";
            entry.msg = `Hata: ${jst.result?.error || jst.error || "işlem başarısız"}`;
            renderAiFileList();
            return;
          }
          if (jst.state === "done") {
            const cnt = jst.result?.lines?.length || 0;
            entry.status = "done";
            entry.msg = cnt ? `✓ ${cnt} satır zaman damgalı (.lrc + MP3 USLT) hazır` : "İşlem tamamlandı — Söz Düzenle ile kontrol edebilirsin";
            renderAiFileList();
            return;
          }
        }
      }
      const hudSt = await callApi()?.active_jobs_hud?.().catch(() => null);
      const running = (hudSt?.items || []).find((it) => it.kind === "AI" || it.title?.includes("LRC") || it.title?.includes("Whisper"));
      if (running) {
        entry.msg = `${running.title} · %${running.pct || 0}`;
        renderAiFileList();
      }
      const lrc = await callApi()?.music_lrc_read?.(path).catch(() => null);
      if (lrc?.ok && lrc.lines?.length && !running) {
        entry.status = "done";
        entry.msg = `✓ ${lrc.lines.length} satır zaman damgalı (.lrc + MP3 USLT) hazır`;
        renderAiFileList();
        return;
      }
    }
    entry.status = "done";
    entry.msg = "İşlem tamamlandı — Söz Düzenle ile kontrol edebilirsin";
    renderAiFileList();
  }

  function renderAiFileList() {
    const box = aiModal?.querySelector("#k20AiList");
    if (!box) return;
    if (!aiFiles.length) {
      box.innerHTML = `<div style="color:#8E86A3;font-size:12px;text-align:center;padding:8px">Henüz dosya bırakılmadı. Yukarıya MP3/WAV/FLAC/MP4 sürükleyip bırakabilirsin.</div>`;
      return;
    }
    box.innerHTML = aiFiles.map((f, idx) => `
      <div class="k20-airow">
        <div style="min-width:0;flex:1">
          <b style="display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(f.name)}</b>
          <small style="color:${f.status === "done" ? "#2EE6A6" : f.status === "error" ? "#FF6B8B" : "#C4B5FD"}">${esc(f.msg)}</small>
        </div>
        <div style="display:flex;gap:6px;flex:none">
          ${f.toolMissing ? `<button type="button" class="btn pri" data-aiinst="${idx}">⬇ ${f.toolMissing === "uvr" ? "UVR5" : "Whisper"} Kur</button>` : ""}
          <button type="button" class="btn" data-airetry="${idx}" title="Yeniden Çalıştır">↻</button>
          <button type="button" class="btn pri" data-aiedit="${idx}">✎ Söz Düzenle</button>
          <button type="button" class="btn" data-aiplay="${idx}" title="Kami Player'da Oynat">▶</button>
        </div>
      </div>
    `).join("");
    box.querySelectorAll("[data-aiinst]").forEach((b) => {
      b.onclick = async () => {
        const f = aiFiles[+b.dataset.aiinst];
        if (!f) return;
        f.status = "running";
        f.toolMissing = "";
        f.msg = "Whisper / AI ortamı kuruluyor (Ayarlar > AI Araçları)…";
        renderAiFileList();
        const ir = await callApi()?.ai_install?.("whisper").catch((e) => ({ ok: false, error: String(e) }));
        if (ir?.ok) {
          f.msg = "Kurulum başlatıldı — hazır olduğunda ↻ ile tekrar dene";
        } else {
          f.status = "error";
          f.msg = `Kurulum hatası: ${ir?.error || "başlatılamadı"}`;
        }
        renderAiFileList();
      };
    });
    box.querySelectorAll("[data-airetry]").forEach((b) => {
      b.onclick = () => {
        const f = aiFiles[+b.dataset.airetry];
        const strong = aiModal?.querySelector("#k20AiStrong")?.checked !== false;
        if (f) processAiAudioFile(f.path, strong);
      };
    });
    box.querySelectorAll("[data-aiedit]").forEach((b) => {
      b.onclick = () => {
        const f = aiFiles[+b.dataset.aiedit];
        if (f) openQuickLrcModal(f.path, f.name);
      };
    });
    box.querySelectorAll("[data-aiplay]").forEach((b) => {
      b.onclick = () => {
        const f = aiFiles[+b.dataset.aiplay];
        if (f) callApi()?.player_show?.({ path: f.path });
      };
    });
  }

  // ---- Paylasilan DP LCS Kelime Seviyesi LRC Hizalayici (Kami LRC Soz Eslestirici) ----
  window.KamiLrcAlign = function alignWhisperWithRealLyrics(rawLrc, trueLyrics) {
    const rawStr = String(rawLrc || "").trim();
    const trueStr = String(trueLyrics || "").trim();
    if (!rawStr || !trueStr) return rawStr;
    const tsToSec = (ts) => {
      const [m, s] = String(ts).replace(":", ".").split(/[.:]/).length === 3
        ? [ts.split(":")[0], ts.split(":")[1] + "." + ts.split(":")[2]]
        : ts.split(":");
      return parseInt(m, 10) * 60 + parseFloat(s);
    };
    const secToTs = (sec) => {
      const safe = Math.max(0, Number(sec) || 0);
      return `${String(Math.floor(safe / 60)).padStart(2, "0")}:${(safe % 60).toFixed(2).padStart(5, "0")}`;
    };
    const norm = (w) => String(w || "").toLocaleLowerCase("tr").replace(/[^\w\sçğıöşüâîû]/g, "");

    const headers = [], seenHead = new Set(), tokens = [];
    rawStr.split(/\r?\n/).forEach((line) => {
      line = line.trim();
      if (!line) return;
      const m = line.match(/^\[(\d{1,3}:\d{2}(?:[.:]\d{1,3})?)\](.*)$/);
      if (!m) {
        if (line.startsWith("[")) {
          const hk = line.split(":")[0].toLowerCase();
          if (!seenHead.has(hk)) { seenHead.add(hk); headers.push(line); }
        }
        return;
      }
      const [, lineTs, content] = m;
      const wMatches = [...content.matchAll(/<(\d{1,3}:\d{2}(?:[.:]\d{1,3})?)>([^<]+)/g)];
      if (wMatches.length) {
        wMatches.forEach((wm) => {
          const w = wm[2].trim();
          if (w) tokens.push({ sec: tsToSec(wm[1]), norm: norm(w) });
        });
      } else {
        const words = content.split(/\s+/).filter(Boolean);
        const baseSec = tsToSec(lineTs);
        words.forEach((w, wi) => tokens.push({ sec: baseSec + wi * 0.25, norm: norm(w) }));
      }
    });

    const trueLines = trueStr.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    const trueWords = [], lineBounds = [];
    trueLines.forEach((line) => {
      const words = line.split(/\s+/).filter(Boolean);
      const start = trueWords.length;
      words.forEach((w) => trueWords.push({ raw: w, norm: norm(w) }));
      lineBounds.push([start, trueWords.length]);
    });

    const n = tokens.length, m = trueWords.length;
    if (!n || !m) return rawStr;
    const isMatch = (a, b) => a === b || (a.length > 2 && b.length > 2 && a.slice(0, 3) === b.slice(0, 3));
    const dp = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
    for (let i = n - 1; i >= 0; i--) {
      for (let j = m - 1; j >= 0; j--) {
        if (isMatch(tokens[i].norm, trueWords[j].norm)) dp[i][j] = 1 + dp[i + 1][j + 1];
        else dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }

    const alignedSec = new Array(m).fill(null);
    let i = 0, j = 0;
    while (i < n && j < m) {
      if (isMatch(tokens[i].norm, trueWords[j].norm)) { alignedSec[j] = tokens[i].sec; i++; j++; }
      else if (dp[i + 1][j] >= dp[i][j + 1]) i++;
      else j++;
    }

    for (let k = 0; k < m; k++) {
      if (alignedSec[k] === null) {
        let prevIdx = k - 1; while (prevIdx >= 0 && alignedSec[prevIdx] === null) prevIdx--;
        let nextIdx = k + 1; while (nextIdx < m && alignedSec[nextIdx] === null) nextIdx++;
        const startT = prevIdx >= 0 ? alignedSec[prevIdx] : (tokens[0]?.sec || 0);
        const endT = nextIdx < m ? alignedSec[nextIdx] : Math.max(startT + 0.5, tokens[tokens.length - 1]?.sec || startT + 1);
        alignedSec[k] = startT + ((endT - startT) * ((k - prevIdx) / (nextIdx - prevIdx)));
      }
    }

    const out = [...headers];
    lineBounds.forEach(([start, end]) => {
      if (start >= end) return;
      const parts = [];
      for (let k = start; k < end; k++) parts.push(`<${secToTs(alignedSec[k])}>${trueWords[k].raw}`);
      out.push(`[${secToTs(alignedSec[start])}]` + parts.join(" "));
    });
    return out.join("\n");
  };

  async function openQuickLrcModal(path, titleHint) {
    const cleanTitle = String(titleHint || "").replace(/\.(mp3|wav|flac|m4a|ogg|opus)$/i, "").trim();
    const r = await callApi()?.music_lrc_read?.(path).catch(() => null);
    const rawInit = r?.raw || (r?.lines || []).map((ln) => {
      const t = Number(ln.t ?? -1);
      if (t < 0) return ln.text || "";
      const mm = String(Math.floor(t / 60)).padStart(2, "0");
      const ss = (t % 60).toFixed(2).padStart(5, "0");
      return `[${mm}:${ss}]${ln.text || ""}`;
    }).join("\n");
    const ed = document.createElement("div");
    ed.id = "k20LrcQuick";
    ed.style.cssText = "position:fixed;inset:0;z-index:9300;background:rgba(5,4,10,.86);display:grid;place-items:center;padding:18px";
    ed.innerHTML = `
      <div class="k20-aibox" style="width:min(740px,95vw)">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <b>✎ Zaman Damgalı .LRC Düzenleyici · <span style="color:#2EE6A6">${esc(cleanTitle || path.split(/[\\/]/).pop())}</span></b>
          <button type="button" class="btn" id="k20LqClose">✕</button>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button type="button" class="btn" id="k20LqAlignToggle">🎯 Gerçek Sözlerle Hizala</button>
          <button type="button" class="btn" id="k20LqOllama">✨ Ollama (qwen2.5:3b) ile Yazım Hatalarını Düzelt</button>
          <span id="k20LqMsg" style="font-size:12px;color:#2EE6A6;align-self:center"></span>
        </div>
        <div id="k20LqAlignBox" hidden style="background:#0C0915;border:1px solid rgba(46,230,166,.35);border-radius:10px;padding:10px;display:flex;flex-direction:column;gap:8px">
          <small style="color:#C4B5FD">Gerçek şarkı sözlerini aşağıya yapıştır — Whisper'ın kelime zaman damgalarıyla otomatik eşlenip LRC güncellenir:</small>
          <textarea id="k20LqTrue" rows="6" placeholder="Gerçek şarkı sözlerini satır satır buraya yapıştır…" style="width:100%;box-sizing:border-box;background:#08060D;border:1px solid #2D2246;border-radius:8px;color:#EDE9F6;padding:8px;font:12.5px Consolas,monospace"></textarea>
          <div style="display:flex;justify-content:flex-end;gap:8px">
            <button type="button" class="btn pri" id="k20LqAlignRun">⚡ Hizala &amp; Uygula</button>
          </div>
        </div>
        <textarea id="k20LqText" rows="13" style="width:100%;box-sizing:border-box;background:#09070F;border:1px solid #35294D;border-radius:10px;color:#EDE9F6;padding:10px;font:12.5px Consolas,monospace">${esc(rawInit)}</textarea>
        <div style="display:flex;justify-content:flex-end;gap:8px">
          <button type="button" class="btn pri" id="k20LqSave">💾 .LRC + MP3 USLT Kaydet</button>
        </div>
      </div>
    `;
    document.body.appendChild(ed);
    ed.querySelector("#k20LqClose").onclick = () => ed.remove();
    const alignBox = ed.querySelector("#k20LqAlignBox");
    ed.querySelector("#k20LqAlignToggle").onclick = () => {
      alignBox.hidden = !alignBox.hidden;
      if (!alignBox.hidden) ed.querySelector("#k20LqTrue")?.focus();
    };
    ed.querySelector("#k20LqAlignRun").onclick = () => {
      const ta = ed.querySelector("#k20LqText");
      const trueTa = ed.querySelector("#k20LqTrue");
      const msg = ed.querySelector("#k20LqMsg");
      if (!ta.value.trim() || !trueTa.value.trim()) {
        msg.textContent = "Hem zaman damgalı LRC hem gerçek sözler gerekli";
        return;
      }
      const aligned = window.KamiLrcAlign(ta.value, trueTa.value);
      ta.value = aligned;
      navigator.clipboard?.writeText?.(aligned).catch?.(() => {});
      alignBox.hidden = true;
      msg.textContent = "✓ Sözler kelime zamanlarıyla hizalandı! Kaydetmek için Kaydet'e bas.";
    };
    ed.querySelector("#k20LqOllama").onclick = async () => {
      const ta = ed.querySelector("#k20LqText");
      const msg = ed.querySelector("#k20LqMsg");
      if (!ta.value.trim()) return;
      msg.textContent = "Ollama düzeltiyor…";
      const res = await (callApi()?.music_lrc_polish_ollama || callApi()?.music_lrc_ollama_polish)?.(ta.value, cleanTitle, "").catch(() => null);
      if (res?.ok && res.text) { ta.value = res.text; msg.textContent = "✓ Ollama ile düzeltildi"; }
      else msg.textContent = res?.error || "Ollama kapalı (Kami Doktor'dan başlat)";
    };
    ed.querySelector("#k20LqSave").onclick = async () => {
      const saveBtn = ed.querySelector("#k20LqSave");
      const ta = ed.querySelector("#k20LqText");
      const msg = ed.querySelector("#k20LqMsg");
      const res = await callApi()?.music_lrc_save?.(path, ta.value, "", cleanTitle).catch(() => null);
      if (res?.ok) {
        msg.textContent = "✓ Kaydedildi (.lrc + MP3 USLT) · Player güncellendi";
        window.KamiMotion?.morphDone?.(saveBtn, "Kaydedildi");
      } else {
        msg.textContent = res?.error || "Kaydedilemedi";
        window.KamiMotion?.shake?.(saveBtn);
      }
    };
  }

  window.openKamiAiLyricsStudio = function openKamiAiLyricsStudio(selDownloadItem = null) {
    if (aiModal) { aiModal.remove(); aiModal = null; }
    clearInterval(aiDropPoll);
    callApi()?.ai_drop_view?.(true);
    aiModal = document.createElement("div");
    aiModal.id = "k20AiModal";
    aiModal.innerHTML = `
      <div class="k20-aibox">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <div>
            <b style="font-size:15px">🎙 AI Altyazı · Vokal Ayırma · MP3 Zaman Damgalı Lirik Stüdyosu</b>
            <div style="font-size:11.5px;color:#9A90AB;margin-top:2px">Dönüştürücü gibi MP3/Ses/Video dosyanı sürükleyip bırak; otomatik UVR5 ile vokali ayırıp Whisper ile zaman damgalı <code>.lrc</code> üretir.</div>
          </div>
          <button type="button" class="btn" id="k20AiClose">Kapat (Esc)</button>
        </div>
        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;background:#171226;padding:8px 12px;border-radius:10px;border:1px solid rgba(157,107,255,.25)">
          <label style="display:flex;align-items:center;gap:7px;font-size:12px;cursor:pointer">
            <input type="checkbox" id="k20AiStrong" checked>
            <span><b>Güçlü Şarkı Modu:</b> Önce UVR5 ile vokali arka plan müziğinden ayır, sonra Whisper ile tam zaman damgalı <code>.lrc</code> çıkar</span>
          </label>
        </div>
        <div class="k20-aidrop" id="k20AiDropZone">
          <div style="font-size:24px;margin-bottom:6px">🎵 ⬇ 🎙</div>
          <b style="font-size:14px;color:#EDE9F6">MP3 / WAV / FLAC / MP4 dosyasını buraya sürükleyip bırak</b>
          <div style="font-size:12px;color:#9A90AB;margin-top:4px">veya bilgisayarından dosya seçmek için buraya tıkla (bırakınca otomatik başlar)</div>
        </div>
        ${selDownloadItem ? `
          <div style="display:flex;align-items:center;justify-content:space-between;background:#1A142B;padding:8px 12px;border-radius:10px;border:1px solid rgba(46,230,166,.35)">
            <span style="font-size:12px">Seçili İndirme: <b style="color:#2EE6A6">${esc(selDownloadItem.filename || selDownloadItem.url || "")}</b></span>
            <button type="button" class="btn" id="k20AiOpenLegacy">Klasik Medya Araçlarını Aç</button>
          </div>
        ` : ""}
        <div id="k20AiList" style="display:flex;flex-direction:column;gap:8px"></div>
      </div>
    `;
    document.body.appendChild(aiModal);
    renderAiFileList();

    const closeAi = () => {
      clearInterval(aiDropPoll);
      callApi()?.ai_drop_view?.(false);
      aiModal?.remove();
      aiModal = null;
    };
    aiModal.querySelector("#k20AiClose").onclick = closeAi;
    aiModal.onclick = (e) => { if (e.target === aiModal) closeAi(); };
    if (selDownloadItem && aiModal.querySelector("#k20AiOpenLegacy")) {
      aiModal.querySelector("#k20AiOpenLegacy").onclick = () => {
        closeAi();
        if (typeof window.openMediaTools === "function") window.openMediaTools(selDownloadItem.id);
      };
    }

    const dz = aiModal.querySelector("#k20AiDropZone");
    dz.onclick = async () => {
      const picked = await callApi()?.ai_drop_pick?.().catch(() => []) || [];
      const strong = aiModal?.querySelector("#k20AiStrong")?.checked !== false;
      for (const p of picked) processAiAudioFile(p, strong);
    };
    dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("drag"); });
    dz.addEventListener("dragleave", () => dz.classList.remove("drag"));
    dz.addEventListener("drop", () => dz.classList.remove("drag"));

    // Python DOMEventHandler on_drop ile gelen tam dosya yollarini (pywebviewFullPath) yokla
    aiDropPoll = setInterval(async () => {
      if (!aiModal) return;
      const got = await callApi()?.ai_drop_inbox?.().catch(() => []) || [];
      if (got.length) {
        const strong = aiModal?.querySelector("#k20AiStrong")?.checked !== false;
        for (const p of got) processAiAudioFile(p, strong);
      }
    }, 350);
  };
})();
