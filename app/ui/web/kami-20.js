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
    /* A3: Birlesik Arka Plan Islem & Kuyruk HUD (is yokken display:none) */
    #k20JobHud {
      position: fixed; right: 64px; bottom: 18px; z-index: 82;
      background: rgba(15, 11, 24, .95); border: 1px solid #2EE6A6;
      border-radius: 999px; padding: 6px 13px; color: #EDE9F6;
      font: 600 12px "Chakra Petch", system-ui, sans-serif;
      display: inline-flex; align-items: center; gap: 9px;
      box-shadow: 0 10px 28px rgba(0,0,0,.6), 0 0 18px rgba(46,230,166,.22);
      cursor: pointer; transition: transform .15s ease;
    }
    #k20JobHud:hover { transform: translateY(-2px); }
    #k20JobHud .spin {
      width: 12px; height: 12px; border-radius: 50%;
      border: 2px solid rgba(46,230,166,.25); border-top-color: #2EE6A6;
      animation: k20Spin .85s linear infinite;
    }
    @keyframes k20Spin { to { transform: rotate(360deg); } }
    #k20JobPop {
      position: fixed; right: 64px; bottom: 56px; z-index: 83;
      width: 310px; background: rgba(16, 12, 26, .98); border: 1px solid rgba(157,107,255,.45);
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

    /* #13: Fitts's Law 8-Dilimli Radyal Halka */
    #k20Radial {
      position: fixed; inset: 0; z-index: 9995; pointer-events: auto;
    }
    .k20-rnode {
      position: fixed; width: 84px; height: 34px; margin-left: -42px; margin-top: -17px;
      background: rgba(18, 13, 30, .96); border: 1px solid #9D6BFF; border-radius: 99px;
      color: #EDE9F6; font: 600 11.5px "Chakra Petch", sans-serif;
      display: grid; place-items: center; cursor: pointer;
      box-shadow: 0 8px 22px rgba(0,0,0,.65); transition: transform .12s, border-color .12s, background .12s;
    }
    .k20-rnode:hover { transform: scale(1.1); border-color: #2EE6A6; background: #2A1C4B; color: #2EE6A6; }
  `;
  document.head.appendChild(st);

  // ---- 1. A3: Birlesik Arka Plan Islem & Kuyruk HUD'u (ORTADA IS YOKKEN TAMAMEN GIZLI) ----
  const hud = document.createElement("div");
  hud.id = "k20JobHud";
  hud.hidden = true;
  const pop = document.createElement("div");
  pop.id = "k20JobPop";
  pop.hidden = true;
  document.body.append(hud, pop);

  let popOpen = false;
  hud.onclick = () => {
    popOpen = !popOpen;
    pop.hidden = !popOpen;
  };

  async function pollActiveJobs() {
    if (document.hidden) return;
    const r = await callApi()?.active_jobs_hud?.().catch(() => null);
    const cnt = Number(r?.count || 0);
    if (!r?.ok || cnt <= 0) {
      // KURAL: Ortada is yokken orada bulunmaya devam etmemeli!
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
    setInterval(pollActiveJobs, 1800);
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
    const cx = Math.max(130, Math.min(window.innerWidth - 130, e.clientX));
    const cy = Math.max(130, Math.min(window.innerHeight - 130, e.clientY));
    const actions = [
      ["▶ Player", () => callApi()?.player_show?.({ library: true })],
      ["🎬 Studio", () => callApi()?.studio_show?.("")],
      ["🖼 Picture", () => callApi()?.picture_open?.("")],
      ["📖 Reader", () => callApi()?.reader_show?.("")],
      ["🎮 Games", () => callApi()?.games_open?.()],
      ["♪ Kamify", () => callApi()?.music_open?.()],
      ["🧹 Cleaner", () => callApi()?.cleaner_open?.()],
      ["📝 Not", () => toggleScratchpad()],
    ];
    radialEl = document.createElement("div");
    radialEl.id = "k20Radial";
    const R = 96;
    radialEl.innerHTML = actions.map(([lbl], i) => {
      const ang = (i / actions.length) * Math.PI * 2 - Math.PI / 2;
      const x = Math.round(cx + Math.cos(ang) * R);
      const y = Math.round(cy + Math.sin(ang) * R);
      return `<button type="button" class="k20-rnode" data-ri="${i}" style="left:${x}px;top:${y}px">${lbl}</button>`;
    }).join("");
    document.body.appendChild(radialEl);
    radialEl.onclick = (ev) => {
      const b = ev.target.closest("[data-ri]");
      const idx = b ? +b.dataset.ri : -1;
      closeRadial();
      if (idx >= 0) actions[idx][1]();
    };
  });
})();
