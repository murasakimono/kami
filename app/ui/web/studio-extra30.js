// Kami Studio v1.30: Studio ici ses kaydi (seslendirme), bolumler + YouTube aciklamasi, kanal/proje sablonlari, coklu kamera kesme ekrani.
(() => {
  AI_TOOLS.push(
    ["voicerec", "🎙 Seslendirme Kaydı", "Oynatma kafasından kayda başla: video oynarken üstüne konuş, bitince yeni ses izine yerleşir (48 kHz WAV). Gürültü bastırma ve yankı engelleme açık."],
    ["chapters", "📑 Bölümler + Açıklama", "Konuşmadan bölüm önerir (ya da işaretlerini kullanır), adlarını düzelt; YouTube açıklaması (00:00 listesi) hazır kopyalanır, istersen bölüm grafiği ekler."],
    ["ptemplates", "🧩 Kanal / Proje Şablonları", "Intro, outro, logo, alt bant, altyazı stili, müzik yatağı, marka: kaydet, sonra tek tıkla aynı düzende yeni proje aç."],
    ["multicamcut", "🎥 Çoklu Kamera Kesme Ekranı", "Eşitlenmiş kameraları yan yana izle; oynarken 1-9 tuşlarıyla kamera değiştir, kesimler ana ize yazılır."],
  );
  const _ai = aiAction;
  aiAction = async (kind, c) => {
    const f = { voicerec, chapters, ptemplates, multicamcut }[kind];
    return f ? f(c) : _ai(kind, c);
  };

  // ---------------------------------------------------------------- seslendirme kaydi
  async function voicerec() {
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1, sampleRate: 48000 } });
    } catch (e) { toast("Mikrofona erişilemedi: " + e.message, 5000); return; }
    const t0 = ST.t;
    const mute = await modal(`<h3>🎙 Seslendirme kaydı</h3><div class="hint">Kayıt ${fmt(t0)} anından başlar; video oynar, sen konuşursun. <b>Boşluk</b> ya da Durdur ile biter.</div>
      <label><input id="vrMute" type="checkbox"> Kayıt sırasında projenin sesini kıs (kulaklık yoksa işaretle)</label>
      <div class="row"><button class="tb" data-v="no">Vazgeç</button><button class="tb pri" data-v="ok">3 sn sonra başla</button></div>`, { collect: () => document.getElementById("vrMute").checked });
    if (mute === null || mute === "" ) { stream.getTracks().forEach((t) => t.stop()); return; }
    for (const n of [3, 2, 1]) { busy(`Kayıt ${n}…`); await new Promise((r) => setTimeout(r, 700)); }
    busy(null);
    const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/webm";
    const rec = new MediaRecorder(stream, { mimeType: mime, audioBitsPerSecond: 192000 }), chunks = [];
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    const oldVol = ST.p.masterVol;
    if (mute) { ST.muteRec = true; document.querySelectorAll("video, audio").forEach((m) => { m.dataset.vrv = m.volume; m.volume = 0; }); }
    const hud = document.createElement("div");
    hud.style.cssText = "position:fixed;left:50%;top:70px;transform:translateX(-50%);z-index:999;background:#B91C1C;color:#fff;font-weight:700;padding:8px 16px;border-radius:999px;display:flex;gap:10px;align-items:center";
    hud.innerHTML = `● KAYIT <span id="vrT">0:00</span> <button class="tb" id="vrStop">Durdur</button>`;
    document.body.appendChild(hud);
    const start = performance.now();
    const timer = setInterval(() => { const s = (performance.now() - start) / 1000; document.getElementById("vrT").textContent = `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`; }, 250);
    rec.start(500); if (!ST.playing) play(true);
    await new Promise((res) => {
      const stop = () => { document.removeEventListener("keydown", kd, true); res(); };
      const kd = (e) => { if (e.key === " " || e.key === "Escape") { e.preventDefault(); e.stopPropagation(); stop(); } };
      document.addEventListener("keydown", kd, true);
      hud.querySelector("#vrStop").onclick = stop;
    });
    const dur = (performance.now() - start) / 1000;
    await new Promise((res) => { rec.onstop = res; rec.stop(); });
    clearInterval(timer); hud.remove(); stream.getTracks().forEach((t) => t.stop());
    if (ST.playing) play(false);
    if (mute) { document.querySelectorAll("video, audio").forEach((m) => { if (m.dataset.vrv) m.volume = +m.dataset.vrv; }); ST.muteRec = false; ST.p.masterVol = oldVol; }
    if (dur < 0.5) { toast("Kayıt çok kısa"); return; }
    busy("Kayıt kaydediliyor…");
    const b64 = await new Promise((res) => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.readAsDataURL(new Blob(chunks, { type: mime })); });
    const r = await api.studio_save_recording(b64, "webm");
    busy(null);
    if (!r?.ok) { toast("Kaydedilemedi"); return; }
    const [aid] = await importPaths([r.path], false);
    if (!aid) return;
    snap();
    const tr = addTrack("audio", "Seslendirme");
    addClip({ asset: aid, track: tr, start: t0, dur: ST.p.assets[aid].dur || dur, in: 0 });
    changed(); toast("Seslendirme eklendi: " + r.path.split(/[\\/]/).pop(), 4000);
  }

  // ---------------------------------------------------------------- bolumler + aciklama
  const hms = (t) => { t = Math.max(0, Math.round(t)); const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60; return (h ? h + ":" + String(m).padStart(2, "0") : String(m).padStart(2, "0")) + ":" + String(s).padStart(2, "0"); };
  async function chapters() {
    let list = (ST.p.markers || []).filter((m) => m.kind === "chapter").sort((a, b) => a.t - b.t).map((m) => ({ t: m.t, title: m.label || "" }));
    if (!list.length) {
      const words = ST.p.clips.filter((c) => c.words?.length).flatMap((c) => c.words.map((w) => ({ w: w.w, s: c.start + w.s, e: c.start + w.e }))).sort((a, b) => a.s - b.s);
      const ph = [];
      for (const w of words) { const l = ph[ph.length - 1]; if (l && w.s - l.e < 0.6) { l.e = w.e; l.text += " " + w.w; } else ph.push({ s: w.s, e: w.e, text: w.w }); }
      const total = Math.max(...ST.p.clips.map((c) => c.start + c.dur), 0);
      if (ph.length) list = (await api.studio_chapters(ph, Math.max(30, total / 12))).chapters;
      else list = [{ t: 0, title: "Giriş" }];
    }
    const draw = () => `<div class="sf-list" id="chL">${list.map((c, i) => `<div class="sf-item" style="display:flex;gap:6px;align-items:center"><input class="in" style="width:80px" data-ct="${i}" value="${hms(c.t)}"><input class="in" style="flex:1" data-cn="${i}" value="${esc(c.title)}"><button class="tb" data-cx="${i}">✕</button></div>`).join("")}</div>`;
    const parse = (s) => s.split(":").map(Number).reduce((a, b) => a * 60 + b, 0);
    const collect = () => { document.querySelectorAll("#chL [data-ct]").forEach((el) => { const i = +el.dataset.ct; list[i].t = parse(el.value) || 0; list[i].title = document.querySelector(`#chL [data-cn="${i}"]`).value.trim(); }); list.sort((a, b) => a.t - b.t); };
    const desc = () => { collect(); const title = ST.p.name || ""; return `${title}\n\n${list.map((c) => `${hms(c.t)} ${c.title}`).join("\n")}\n`; };
    const v = await modal(`<h3>📑 Bölümler</h3><div class="hint">YouTube için ilk bölüm 00:00 olmalı, en az 3 bölüm ve her biri en az 10 sn. Oynatma kafasındaki anı eklemek için “+ Şu an”.</div>${draw()}
      <div class="row"><button class="tb" data-v="add">+ Şu an (${fmt(ST.t)})</button></div>
      <textarea class="in" id="chDesc" style="width:100%;min-height:110px;margin-top:8px" readonly></textarea>
      <label><input type="checkbox" id="chGfx"> Her bölüme bölüm başlığı grafiği ekle</label>
      <div class="row"><button class="tb" data-v="no">Kapat</button><button class="tb" data-v="copy">Açıklamayı kopyala</button><button class="tb pri" data-v="ok">İşaretlere kaydet</button></div>`, {
      init: (m) => {
        const upd = () => { const t = document.getElementById("chDesc"); if (t) t.value = desc(); };
        upd(); m.addEventListener("input", upd);
        m.addEventListener("click", (e) => {
          const x = e.target.closest("[data-cx]"); if (x) { e.stopPropagation(); collect(); list.splice(+x.dataset.cx, 1); document.getElementById("chL").outerHTML = draw(); upd(); }
          const a = e.target.closest('[data-v="add"]'); if (a) { e.stopPropagation(); collect(); list.push({ t: ST.t, title: "Yeni bölüm" }); list.sort((p, q) => p.t - q.t); document.getElementById("chL").outerHTML = draw(); upd(); }
          const cp = e.target.closest('[data-v="copy"]'); if (cp) { e.stopPropagation(); navigator.clipboard?.writeText(desc()).then(() => toast("Açıklama kopyalandı")); }
        }, true);
      }, collect: () => { collect(); return { gfx: document.getElementById("chGfx").checked }; } });
    if (!v || typeof v !== "object") return;
    const bad = list.length < 3 || list[0].t !== 0 || list.some((c, i) => i && c.t - list[i - 1].t < 10);
    snap();
    ST.p.markers = (ST.p.markers || []).filter((m) => m.kind !== "chapter").concat(list.map((c) => ({ t: c.t, kind: "chapter", label: c.title, color: "#2EE6A6" })));
    if (v.gfx) list.forEach((c, i) => addClip({ track: trackFor("text"), start: c.t, dur: 2.6, graphic: "chapter", style: { num: String(i + 1).padStart(2, "0"), title: c.title.toLocaleUpperCase("tr") } }));
    changed(); toast(bad ? "Kaydedildi — YouTube kuralına uymuyor (00:00, en az 3, ≥10 sn)" : "Bölümler kaydedildi", 4000);
  }

  // ---------------------------------------------------------------- sablonlar
  async function ptemplates() {
    const list = (await api.studio_ptpl_list()) || [];
    const v = await modal(`<h3>🧩 Kanal / proje şablonları</h3><div class="hint">Şablon; boyut, izler, intro/outro görselleri, logo, alt bant, yazılar, altyazı stili, müzik yatağı ve markayı saklar. Ana video izindeki videolar şablona girmez (her bölümde değişen içerik).</div>
      <div class="sf-list">${list.map((t) => `<div class="sf-item"><b>${esc(t.name)}</b> <small>${t.w}×${t.h} · ${t.clips} öğe</small> <button class="tb pri" data-v="new:${esc(t.id)}">Yeni proje</button> <button class="tb" data-v="del:${esc(t.id)}">Sil</button></div>`).join("") || `<div class="hint">Henüz şablon yok.</div>`}</div>
      <div class="row"><button class="tb" data-v="no">Kapat</button><button class="tb" data-v="save">Bu projeyi şablon yap</button></div>`);
    if (!v) return;
    if (v === "save") {
      const name = await promptText("Şablon adı", ST.p.name || "Kanalım", "Örn. 'YouTube bölüm', 'Shorts', 'Podcast'"); if (!name) return;
      const p = clone(ST.p); for (const a of Object.values(p.assets)) delete a.url;
      await api.studio_ptpl_save(name, p); toast("Şablon kaydedildi: " + name);
    } else if (v.startsWith("del:")) { if (await ask("Silinsin mi?", "Şablon silinecek.", "Sil")) { await api.studio_ptpl_delete(v.slice(4)); ptemplates(); } }
    else if (v.startsWith("new:")) {
      if (ST.dirty) await save();
      const r = await api.studio_ptpl_new(v.slice(4)); if (!r?.ok) { toast("Açılamadı"); return; }
      stopAll(); ST.p = r.project; ST.path = ""; ST.undo = []; ST.redo = []; ST.compoundStack = []; ST.t = 0; ST.p.markers ||= []; renderCompCrumb?.();
      afterLoad(); ST.dirty = true; toast("Şablondan yeni proje — ana videoyu içe aktar", 4000);
    }
  }

  // ---------------------------------------------------------------- coklu kamera kesme ekrani
  async function multicamcut() {
    const sel = selClips().filter((c) => clipKind(c) === "video");
    if (sel.length < 2) { toast("Önce eşitlenmiş 2-9 kamera klibini seç (Akıllı > Çoklu Kamera Eşitle ile hizala)", 5000); return; }
    const cams = sel.slice(0, 9).sort((a, b) => a.track.localeCompare(b.track));
    const t0 = Math.min(...cams.map((c) => c.start)), t1 = Math.max(...cams.map((c) => c.start + c.dur));
    const cuts = [{ t: Math.max(t0, ST.t), cam: 0 }];
    const box = document.createElement("div");
    box.style.cssText = "position:fixed;inset:0;z-index:998;background:#07060Bf2;display:flex;flex-direction:column;padding:16px;gap:10px";
    const cols = cams.length <= 4 ? 2 : 3;
    box.innerHTML = `<div style="display:flex;gap:10px;align-items:center;color:#EDE9F6"><b>🎥 Çoklu kamera</b><span style="color:#8E86A3">Boşluk oynat/duraklat · 1-${cams.length} kamera değiştir (kesim yazılır) · Enter bitir · Esc vazgeç</span><span style="flex:1"></span><span id="mcT"></span><button class="tb" id="mcPlay">⏯</button><button class="tb pri" id="mcDone">Bitir ve uygula</button><button class="tb" id="mcX">Vazgeç</button></div>
      <div id="mcG" style="flex:1;display:grid;grid-template-columns:repeat(${cols},1fr);gap:8px;min-height:0">${cams.map((c, i) => `<div data-cam="${i}" style="position:relative;background:#000;border:3px solid ${i ? "#2A2140" : "#2EE6A6"};border-radius:8px;overflow:hidden;cursor:pointer">
        <video muted playsinline style="width:100%;height:100%;object-fit:contain"></video><b style="position:absolute;left:8px;top:6px;background:#000a;color:#fff;padding:2px 8px;border-radius:6px">${i + 1}</b></div>`).join("")}</div>
      <div id="mcBar" style="height:26px;position:relative;background:#110D19;border-radius:6px"></div>`;
    document.body.appendChild(box);
    const vids = [...box.querySelectorAll("video")];
    vids.forEach((v, i) => { v.src = ST.p.assets[cams[i].asset]?.url || ""; });
    let cur = 0, playing = false, last = performance.now(), t = cuts[0].t, raf = 0;
    const seekAll = () => vids.forEach((v, i) => { const c = cams[i], local = (c.in || 0) + (t - c.start) * (c.speed || 1); if (local >= 0 && Math.abs(v.currentTime - local) > 0.25) v.currentTime = Math.max(0, local); });
    const colors = ["#2EE6A6", "#8B5CF6", "#F59E0B", "#3B82F6", "#EF4444", "#EC4899", "#14B8A6", "#A3E635", "#F97316"];
    const drawBar = () => {
      const bar = box.querySelector("#mcBar"), W = bar.clientWidth, span = t1 - t0 || 1;
      bar.innerHTML = cuts.map((k, i) => { const e = cuts[i + 1]?.t ?? t1; return `<i style="position:absolute;top:0;bottom:0;left:${((k.t - t0) / span) * W}px;width:${Math.max(1, ((e - k.t) / span) * W)}px;background:${colors[k.cam]};opacity:.75"></i>`; }).join("") +
        `<i style="position:absolute;top:-3px;bottom:-3px;width:2px;background:#fff;left:${((t - t0) / span) * W}px"></i>`;
      box.querySelector("#mcT").textContent = fmt(t);
    };
    const setCam = (i) => {
      if (i >= cams.length) return;
      cur = i; box.querySelectorAll("[data-cam]").forEach((d, k) => d.style.borderColor = k === i ? colors[i] : "#2A2140");
      while (cuts.length > 1 && cuts[cuts.length - 1].t > t) cuts.pop();   // geri sarip yeniden kesince sonrasi silinir
      const lc = cuts[cuts.length - 1];
      if (Math.abs(lc.t - t) < 0.15) lc.cam = i; else if (lc.cam !== i) cuts.push({ t, cam: i });
      drawBar();
    };
    const loop = (now) => {
      if (playing) { t = Math.min(t1, t + (now - last) / 1000); if (t >= t1) { playing = false; vids.forEach((v) => v.pause()); } }
      last = now; drawBar(); raf = requestAnimationFrame(loop);
    };
    const togglePlay = () => { playing = !playing; last = performance.now(); seekAll(); vids.forEach((v) => (playing ? v.play().catch(() => {}) : v.pause())); };
    const close = (apply) => {
      cancelAnimationFrame(raf); document.removeEventListener("keydown", kd, true); vids.forEach((v) => { v.pause(); v.removeAttribute("src"); }); box.remove();
      if (!apply) return;
      snap();
      const tr = addTrack("video", "Çoklu kamera");
      cuts.forEach((k, i) => {
        const e = cuts[i + 1]?.t ?? t1, c = cams[k.cam]; if (e - k.t < 0.05) return;
        const s = Math.max(k.t, c.start), en = Math.min(e, c.start + c.dur); if (en - s < 0.05) return;
        addClip({ asset: c.asset, track: tr, start: s, dur: en - s, in: (c.in || 0) + (s - c.start) * (c.speed || 1), speed: c.speed || 1, fit: c.fit || "cover", vol: 0 });
      });
      for (const c of cams) c.vol = c === cams[0] ? (c.vol ?? 1) : 0;   // ses: ilk kameradan (genelde en iyi mikrofon), digerleri sessiz
      for (const c of cams) { const T = ST.p.tracks.find((x) => x.id === c.track); if (T && T.kind === "video") T.hide = true; }   // goruntu yeni izden, ses ilk kameradan
      changed(); toast(`Çoklu kamera: ${cuts.length} çekim yeni ize yazıldı (kaynak izler gizlendi)`, 5000);
    };
    const kd = (e) => {
      if (/^[1-9]$/.test(e.key)) { setCam(+e.key - 1); e.preventDefault(); }
      else if (e.key === " ") { togglePlay(); e.preventDefault(); }
      else if (e.key === "Enter") close(true); else if (e.key === "Escape") close(false); else return;
      e.stopPropagation();
    };
    document.addEventListener("keydown", kd, true);
    box.querySelector("#mcPlay").onclick = togglePlay; box.querySelector("#mcDone").onclick = () => close(true); box.querySelector("#mcX").onclick = () => close(false);
    box.querySelectorAll("[data-cam]").forEach((d) => d.onclick = () => setCam(+d.dataset.cam));
    box.querySelector("#mcBar").onclick = (e) => { const r = e.currentTarget.getBoundingClientRect(); t = t0 + ((e.clientX - r.left) / r.width) * (t1 - t0); seekAll(); };
    seekAll(); raf = requestAnimationFrame(loop);
  }
})();
