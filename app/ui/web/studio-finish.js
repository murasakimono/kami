// Kami Studio v1.25: Yayın Öncesi Kontrol, kapak karesi, referans videodan stil, onaylı konuşma temizliği,
// Real-ESRGAN netleştirme, RIFE akıcı ağır çekim, hareket takibi. Görsel cila Antigravity'de; burada işlev.
(() => {
  const PLAT = { youtube: "YouTube", shorts: "Shorts / Reels / TikTok", podcast: "Podcast", tv: "TV (EBU)" };
  AI_TOOLS.push(
    ["qc", "✅ Yayın Öncesi Kontrol", "Siyah/donuk kare, sessizlik, ses yüksekliği ve tepe, siyah ilk kare (kapak), tekrar eden geçiş, güvenli alan; “dinlemen gereken 5 an”."],
    ["speech", "🧹 Konuşma Temizliği (onaylı)", "Dolgu, tekrar (“ben ben”), yarım başlangıç ve uzun duraklamaları listeler; sen işaretlersin, keser. Güvenli olanlar hazır işaretli."],
    ["refstyle", "🎯 Referans Videodan Stil", "Beğendiğin bir videonun kesim temposunu, ses yüksekliğini, BPM'ini ve renk karakterini ölçer; rengi LUT olarak kliplerine uygular."],
    ["upscale", "🔍 Netleştir / Büyüt (Real-ESRGAN)", "Düşük çözünürlüklü veya bulanık klibi yapay zekayla 2-4x netleştirir (ekran kartı, ilk kullanımda ~45 MB iner)."],
    ["interp", "🐢 Akıcı Ağır Çekim (RIFE)", "Ara kare üretir: 2x/4x pürüzsüz ağır çekim ya da 60 fps akıcılık (ilk kullanımda bir kez indirilir)."],
    ["track", "📍 Hareket Takibi", "Yazı/çıkartma/görseli videodaki bir nesneye yapıştırır: kutuyu çiz, nesne nereye giderse o da gider."],
    ["poster", "🖼 Kapak Karesini Göm", "Dışa aktardığın videonun 0. karesine en canlı kareyi (ya da oynatma kafasını) yazar; akışta siyah kapak çıkmaz."],
    ["speedramp", "🏎️ Hız Eğrisi (Speed Ramp)", "CapCut Pro / Spunkram tarzı hazır hız eğrileri: Montage, Hero, Bullet, Jump Cut, Flash In/Out, Araba/Futbol Velocity."],
    ["audioreact", "🔊 Ses-Tepkili Zoom (Audio-Reactive)", "Müzik/oyun bas ve tepe vuruşlarına göre klibe otomatik nabız zoom anahtar kareleri yazar."],
    ["reframe916", "📱 Akıllı Oto-Reframe (16:9 → 9:16)", "Yatay videodaki yüz/özneyi takip ederek dikey kadraja otomatik odaklar."],
    ["aivision", "👁️ AI Görüş Paketi (Kare Şeridi)", "Tasarımcı Dayı / Video Use yöntemi: 2 sn'de bir kare şeridi ve ses enerji haritası çıkarır."],
  );
  const _ai = aiAction;
  aiAction = async (kind, c) => {
    const f = { qc, speech, refstyle, upscale: c2 => enhance("upscale", c2), interp: c2 => enhance("interp", c2), track, poster, speedramp, audioreact, reframe916, aivision }[kind];
    return f ? f(c) : _ai(kind, c);
  };

  const lastOut = () => (window.DV?.queue || []).find(q => q.state === "done")?.out || "";
  const pickOne = async () => (await api.studio_pick_media())?.[0] || "";
  const tl = t => (t == null ? "" : `<a href="#" class="sf-seek" data-seek="${t}">${fmt(+t)}</a>`);

  async function sjob(r, label) {
    if (r?.error === "need_tool") {
      const nm = { esrgan: "Real-ESRGAN (~45 MB)", rife: "RIFE (~430 MB indirilir, açılınca ~30 MB kalır)", track: "hareket takibi ortamı (OpenCV, ~150 MB)" }[r.tool] || r.tool;
      if (!await ask("Araç kurulsun mu?", `Bunun için ${nm} gerekli. Bir kez kurulur.`, "Kur")) return null;
      const j = await api.studio_ncnn_install(r.tool);
      try { await waitStudioJob(j.job, "Kuruluyor"); toast("Kuruldu, tekrar başlatıyorum"); } catch (e) { toast("Kurulamadı: " + e.message, 5000); return null; }
      return "retry";
    }
    if (!r?.ok) { toast(r?.error || "olmadı", 4000); return null; }
    return (await waitStudioJob(r.job, label)).result;
  }

  // ---------------------------------------------------------------- yayın öncesi kontrol
  async function qc() {
    const plat = await modal(`<h3>Yayın Öncesi Kontrol</h3><div class="hint">Nereye yükleyeceksin? Ses hedefi buna göre ölçülür.</div>
      <div class="row">${Object.entries(PLAT).map(([k, v]) => `<button class="tb" data-v="${k}">${v}</button>`).join("")}</div>`);
    if (!plat) return;
    let path = lastOut();
    const how = await modal(`<h3>Hangi dosya?</h3><div class="hint">Kurgu kontrolü projeden yapılır. Ses/görüntü kontrolü için dışa aktarılmış dosya gerekir.${path ? `<br>Son çıktı: <b>${esc(path.split(/[\\/]/).pop())}</b>` : ""}</div>
      <div class="row"><button class="tb" data-v="proj">Yalnız proje</button><button class="tb" data-v="pick">Dosya seç…</button>${path ? `<button class="tb pri" data-v="last">Son çıktı</button>` : ""}</div>`);
    if (!how) return;
    if (how === "pick") path = await pickOne();
    if (how === "proj") path = "";
    busy("Kontrol ediliyor…");
    let r;
    try { r = await job("studio_qc", [path, plat, ST.p]); } catch (e) { busy(null); toast("Olmadı: " + e.message); return; }
    busy(null);
    const lv = { err: "⛔", warn: "⚠️", info: "ℹ️" };
    const all = [...(r.issues || []), ...(r.edit || [])];
    const L = r.loudness || {};
    const v = await modal(`<h3>✅ Yayın Öncesi Kontrol</h3>
      ${r.duration ? `<div class="sf-stats">
        <div class="sf-stat"><small>Süre</small><b>${fmt(r.duration)}</b></div>
        <div class="sf-stat"><small>Ses (LUFS)</small><b>${L.i != null ? L.i.toFixed(1) : "—"}</b></div>
        <div class="sf-stat"><small>Tepe (dBTP)</small><b>${L.tp != null ? L.tp.toFixed(1) : "—"}</b></div>
        <div class="sf-stat"><small>Hedef</small><b>${r.target?.lufs ?? "—"} LUFS</b></div>
      </div>` : ""}
      ${all.length ? `<div class="sf-list">${all.map(i => `<div class="sf-item ${esc(i.level || "info")}"><span>${lv[i.level] || "•"}</span><span style="flex:1">${esc(i.msg)}</span>${tl(i.t)}</div>`).join("")}</div>` : `<div class="sf-ok">Sorun bulunmadı — yayına hazır ✔</div>`}
      ${r.listen?.length ? `<div class="sec">Dinlemen gereken 5 an</div><div class="sf-list">${r.listen.map(x => `<div class="sf-item info"><span style="flex:1">${esc(x.why)}</span>${tl(x.t)}</div>`).join("")}</div>` : ""}
      <div class="row">${all.some(i => i.fix === "poster") && path ? `<button class="tb" data-v="poster">🖼 Kapak karesini göm</button>` : ""}
      ${all.some(i => i.fix === "loudness") ? `<button class="tb" data-v="loud">🔊 Hedefi ${r.target?.lufs} LUFS yap</button>` : ""}
      <button class="tb pri" data-v="no">Tamam</button></div>`, { init: m => m.addEventListener("click", e => { const a = e.target.closest("[data-seek]"); if (a) { e.preventDefault(); seek(+a.dataset.seek); } }) });
    if (v === "poster") return poster(null, path);
    if (v === "loud") { snap(); ST.p.master = { ...(ST.p.master || {}), lufs: r.target.lufs }; changed(); toast("Ana çıkış hedefi ayarlandı; yeniden dışa aktar"); }
  }

  async function poster(_c, path) {
    path = path || lastOut() || await pickOne(); if (!path) return;
    const w = await modal(`<h3>Kapak karesi</h3><div class="hint">${esc(path.split(/[\\/]/).pop())}<br>Videonun 0. karesine yazılacak kare (akış/önizleme kapağı). Yeni kopya <b>_kapak</b> adıyla kaydedilir, orijinal değişmez.</div>
      <div class="row"><button class="tb" data-v="head">Oynatma kafasındaki kare (${fmt(ST.t)})</button><button class="tb pri" data-v="auto">En canlı kareyi bul</button></div>`);
    if (!w) return;
    busy("Kapak gömülüyor…");
    try { const r = await job("studio_poster", [path, w === "head" ? ST.t : -1]); busy(null); toast(r.ok ? "Hazır: " + r.path.split(/[\\/]/).pop() : "Olmadı: " + r.error, 5000); }
    catch (e) { busy(null); toast("Olmadı: " + e.message); }
  }

  // ---------------------------------------------------------------- konuşma temizliği
  async function speech(c) {
    c = c && ["video", "audio"].includes(clipKind(c)) ? c : needSel(["video", "audio"]); if (!c) return;
    const c1 = c.start + c.dur;
    const caps = ST.p.clips.filter(x => x.words?.length && x.start < c1 && x.start + x.dur > c.start);
    if (!caps.length) { toast("Önce bu klibe otomatik altyazı oluştur; öneriler kelime zamanlarından çıkar", true); return; }
    const words = caps.flatMap(tc => tc.words.map(w => ({ w: w.w, s: tc.start + w.s, e: tc.start + w.e }))).filter(w => w.s >= c.start && w.e <= c1).sort((a, b) => a.s - b.s);
    const sug = await api.studio_speech_suggest(words);
    if (!sug?.length) { toast("Temizlenecek bir şey bulunamadı"); return; }
    const picked = await modal(`<h3>🧹 Konuşma Temizliği</h3><div class="hint">İşaretliler kesilir. İşaretsizler ifadenin ortasında: önce dinleyip kontrol et.</div>
      <div class="sf-list">${sug.map((s, i) => `<label class="sf-item sf-chk"><input type="checkbox" data-i="${i}" ${s.safe ? "checked" : ""}><b style="color:#C4B5FD">${esc(s.label)}</b><span style="flex:1;color:#A39BB5">“${esc(s.text)}”</span>${tl(s.s)}</label>`).join("")}</div>
      <div class="row"><button class="tb" data-v="no">Vazgeç</button><button class="tb pri" data-v="ok">Seçilenleri kes</button></div>`,
      { init: m => m.addEventListener("click", e => { const a = e.target.closest("[data-seek]"); if (a) { e.preventDefault(); seek(+a.dataset.seek); } }),
        collect: () => [...document.querySelectorAll("#modal [data-i]:checked")].map(x => sug[+x.dataset.i]) });
    if (!picked?.length) return;
    snap();
    const n = cutTimeline(c, picked.map(s => [s.s, s.e]), caps);
    changed(); toast(n ? `${n} parça kesildi` : "Kesilecek kadar uzun parça yok");
  }
  function cutTimeline(c, ranges, caps) {
    const sp = c.speed || 1, src0 = c.in || 0; let n = 0;
    for (const [t0, t1] of ranges.sort((a, b) => b[0] - a[0])) {   // sondan başa: önceki zamanlar kaymaz
      if (t1 - t0 < .12 || !removeRanges(c, [[src0 + (t0 - c.start) * sp, src0 + (t1 - c.start) * sp]], 0)) continue;
      const d = t1 - t0; n++;
      for (const tc of caps) {
        if (tc.start + tc.dur <= t0) continue;
        tc.words = tc.words.filter(x => !(tc.start + x.s >= t0 - 1e-3 && tc.start + x.e <= t1 + 1e-3));
        for (const x of tc.words) if (tc.start + x.s >= t1 - 1e-6) { x.s = +(x.s - d).toFixed(3); x.e = +(x.e - d).toFixed(3); }
        tc.dur = Math.max(.2, +(tc.dur - d).toFixed(3));
      }
      const capTracks = new Set(caps.map(x => x.track));
      for (const o of ST.p.clips) if (!caps.includes(o) && capTracks.has(o.track) && o.start >= t1 - 1e-6) o.start = +(o.start - d).toFixed(4);
    }
    return n;
  }

  // ---------------------------------------------------------------- referans videodan stil
  async function refstyle() {
    const ref = await pickOne(); if (!ref) return;
    busy("Referans ölçülüyor (tempo, ses, renk)…");
    let p;
    try { p = await job("studio_ref_profile", [ref]); } catch (e) { busy(null); toast("Olmadı: " + e.message); return; }
    busy(null);
    if (!p?.ok) { toast(p?.error || "olmadı"); return; }
    const pc = p.pacing || {};
    const mine = ST.p.clips.filter(x => x.track === "v1");
    const myAvg = mine.length ? mine.reduce((a, x) => a + x.dur, 0) / mine.length : 0;
    const vids = selClips().filter(x => clipKind(x) === "video" || clipKind(x) === "image");
    const v = await modal(`<h3>🎯 Referans: ${esc(ref.split(/[\\/]/).pop())}</h3>
      <div class="sf-stats">
        <div class="sf-stat"><small>Kesim Ort.</small><b>${pc.avg ?? "—"} sn</b></div>
        <div class="sf-stat"><small>Dakikada</small><b>${pc.per_min ?? "—"} kesim</b></div>
        <div class="sf-stat"><small>Ses (LUFS)</small><b>${p.lufs != null ? p.lufs.toFixed(1) : "—"}</b></div>
        <div class="sf-stat"><small>Tempo</small><b>${p.bpm ? Math.round(p.bpm) + " BPM" : "—"}</b></div>
        <div class="sf-stat"><small>Doygunluk</small><b>%${Math.round((p.color?.sat || 0) * 100)}</b></div>
      </div>
      <div class="hint">${myAvg ? `Senin projenin çekim ortalaması: <b>${myAvg.toFixed(2)} sn</b> · ` : ""}${p.vertical ? "Dikey (9:16)" : "Yatay (16:9)"}</div>
      <div class="row">${vids.length ? `<button class="tb pri" data-v="color">🎨 Rengini seçili ${vids.length} klibe uygula</button>` : `<span class="hint">Rengini uygulamak için önce klipleri seç.</span>`}
      ${p.lufs != null ? `<button class="tb" data-v="loud">🔊 Ses hedefini ${Math.round(Math.max(-23, Math.min(-9, p.lufs)))} LUFS yap</button>` : ""}
      <button class="tb" data-v="no">Kapat</button></div>`);
    if (v === "loud") { snap(); ST.p.master = { ...(ST.p.master || {}), lufs: Math.round(Math.max(-23, Math.min(-9, p.lufs))) }; changed(); toast("Ana çıkış hedefi ayarlandı"); }
    if (v === "color") {
      busy("Renk eşleştiriliyor…");
      try {
        const src = assetOf(vids[0])?.path;
        const r = await job("studio_ref_lut", [ref, src, .8, ""]);
        busy(null); if (!r?.ok) { toast(r?.error || "olmadı"); return; }
        snap(); for (const x of vids) x.grade = { ...(x.grade || {}), lut: r.lut, lutMix: .85 };
        changed(); toast("LUT uygulandı: " + r.lut + " (yoğunluğu Renk panelinden ayarla)");
      } catch (e) { busy(null); toast("Olmadı: " + e.message); }
    }
  }

  // ---------------------------------------------------------------- Real-ESRGAN / RIFE
  async function enhance(kind, c) {
    c = c && clipKind(c) === "video" ? c : needSel(["video"]); if (!c) return;
    const a = assetOf(c), sp = c.speed || 1, len = c.dur * sp;
    let o;
    if (kind === "upscale") {
      const m = await modal(`<h3>Netleştir / Büyüt</h3><div class="hint">Yalnız seçili klibin görünen kısmı (${fmt(len)}) işlenir; sonuç yeni dosya olarak klibin yerine geçer, orijinal değişmez. Kaynak ${a?.w || "?"}×${a?.h || "?"}.</div>
        <div class="row"><button class="tb" data-v="anime">Hızlı 2x (video/çizgi)</button><button class="tb pri" data-v="anime4">Hızlı 4x</button><button class="tb" data-v="photo">Fotogerçekçi 4x (yavaş)</button></div>`);
      if (!m) return;
      o = { model: m === "photo" ? "photo" : "anime", scale: m === "anime" ? 2 : 4 };
    } else {
      const m = await modal(`<h3>Akıcı ağır çekim (RIFE)</h3><div class="hint">Ara kareler yapay zekayla üretilir; ffmpeg'in “optik akış”ından çok daha temiz. Ağır çekimde ses düşer.</div>
        <div class="row"><button class="tb pri" data-v="s2">2x ağır çekim</button><button class="tb" data-v="s4">4x ağır çekim</button><button class="tb" data-v="m2">Akıcı (fps x2, aynı hız)</button></div>`);
      if (!m) return;
      o = { factor: m === "s4" ? 4 : 2, mode: m[0] === "s" ? "slow" : "smooth" };
    }
    for (let k = 0; k < 2; k++) {
      let res;
      try { res = await sjob(await api.studio_enhance(kind, a.path, c.in || 0, len, o), kind === "upscale" ? "Netleştiriliyor" : "Ara kareler"); }
      catch (e) { toast("Olmadı: " + e.message, 5000); return; }
      if (res === "retry") continue;
      if (!res) return;
      let infos = [];
      try { infos = await job("studio_info", [[res.path]]); } catch { }
      const i = infos[0]; if (!i?.ok) { toast("Çıktı okunamadı"); return; }
      snap();
      let aid = "a1", n = 1; while (ST.p.assets[aid]) aid = "a" + (++n);
      ST.p.assets[aid] = { path: i.path, kind: "video", dur: i.dur, w: i.w, h: i.h, audio: i.audio, name: i.name, url: i.url };
      prepAsset(ST.p.assets[aid]);
      c.asset = aid; c.in = 0; delete c.speed;
      if (kind === "interp" && o.mode === "slow") { const old = c.dur; c.dur = +(i.dur || len * o.factor).toFixed(3); rippleOpen(c.track, c.start + old, c.dur - old); }
      changed(); toast(kind === "upscale" ? `Netleştirildi: ${i.w}×${i.h}` : "Ara kareler eklendi"); return;
    }
  }

  // ---------------------------------------------------------------- hareket takibi
  async function track(o) {
    o = o && !["video", "audio"].includes(clipKind(o)) ? o : firstSel();
    if (!o || ["video", "audio"].includes(clipKind(o))) { toast("Önce yapıştırılacak yazı/çıkartma/görsel klibini seç, oynatma kafasını nesnenin göründüğü yere getir"); return; }
    if (o.trackPath || (o.kf?.length > 8 && o._tracked)) {
      const w = await modal(`<h3>Bu klip zaten takipli</h3><div class="row"><button class="tb" data-v="off">Takibi kaldır</button><button class="tb pri" data-v="re">Yeniden izle</button></div>`);
      if (!w) return;
      if (w === "off") { snap(); delete o.trackPath; if (o._tracked) { delete o.kf; delete o._tracked; } changed(); toast("Takip kaldırıldı"); return; }
    }
    const v = ST.p.clips.filter(x => clipKind(x) === "video" && x.start <= ST.t && x.start + x.dur > ST.t && x !== o).sort((a, b) => (parseInt(String(b.track).slice(1), 10) || 0) - (parseInt(String(a.track).slice(1), 10) || 0))[0];
    if (!v) { toast("Oynatma kafasının altında video yok"); return; }
    const sp = v.speed || 1, srcT = (v.in || 0) + (ST.t - v.start) * sp;
    const end = Math.min(o.start + o.dur, v.start + v.dur), dur = Math.max(.2, (end - ST.t) * sp);
    const fr = await api.studio_src_frame(assetOf(v).path, srcT);
    if (!fr?.ok) { toast("Kare alınamadı"); return; }
    let box = null;
    const ok = await modal(`<h3>📍 Takip Edilecek Nesne</h3><div class="hint">Nesnenin etrafına kutu çiz (sürükle). ${fmt(ST.t)} → ${fmt(end)} arası izlenir.</div>
      <div class="sf-tk-wrap" id="tkW"><img src="${fr.url}" draggable="false"><i id="tkB" class="sf-tk-box"></i></div>
      <div class="row"><button class="tb" data-v="no">Vazgeç</button><button class="tb pri" data-v="ok">İzle</button></div>`, {
      init: m => {
        const w = $("#tkW", m), b = $("#tkB", m); let s = null;
        w.onpointerdown = e => { const r = w.getBoundingClientRect(); s = [(e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height]; w.setPointerCapture(e.pointerId); };
        w.onpointermove = e => {
          if (!s) return; const r = w.getBoundingClientRect();
          const x = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), y = Math.min(1, Math.max(0, (e.clientY - r.top) / r.height));
          box = [Math.min(s[0], x), Math.min(s[1], y), Math.abs(x - s[0]), Math.abs(y - s[1])];
          Object.assign(b.style, { display: "block", left: box[0] * 100 + "%", top: box[1] * 100 + "%", width: box[2] * 100 + "%", height: box[3] * 100 + "%" });
        };
        w.onpointerup = () => { s = null; };
      }, collect: () => box });
    if (!ok || !box || box[2] < .01 || box[3] < .01) return;
    for (let k = 0; k < 2; k++) {
      let res;
      try { res = await sjob(await api.studio_track(assetOf(v).path, srcT, dur, box), "Takip ediliyor"); } catch (e) { toast("Olmadı: " + e.message, 5000); return; }
      if (res === "retry") continue;
      if (!res?.kf?.length) { if (res) toast("Nesne izlenemedi"); return; }
      snap();
      const c0 = res.kf[0];
      // nesnenin ilk konumuna göre göreli: klibin şimdiki yeri korunur, nesneyle birlikte kayar (video kadrajı doldurduğu varsayılır)
      const bx = +(o.x || 0), by = +(o.y || 0), sx = (v.scale || 1), toTl = t => v.start + (t - (v.in || 0)) / sp;
      const rel = res.kf.map(q => ({ t: +(toTl(q.t) - o.start).toFixed(3), dx: +((q.cx - c0.cx) * sx).toFixed(4), dy: +((q.cy - c0.cy) * sx).toFixed(4) })).filter(q => q.t >= 0);
      if (trackOf(o).kind === "text") o.trackPath = rel;   // yazı/çıkartma ASS'te: parça parça \move
      else { o.kf = rel.map(q => ({ t: q.t, x: +(bx + q.dx).toFixed(4), y: +(by + q.dy).toFixed(4) })); o._tracked = true; }
      changed(); toast(res.lost?.length ? `Takip edildi (${res.lost.length} karede nesne kayboldu, oralar yumuşatıldı)` : "Takip edildi — klip artık nesneyle birlikte hareket ediyor"); return;
    }
  }

  // ---------------------------------------------------------------- v1.26 Pro Araclari
  async function speedramp(c) {
    c = c && clipKind(c) === "video" ? c : needSel(["video"]); if (!c) return;
    const pre = await api.studio_speed_ramp_presets();
    const pick = await modal(`<h3>🏎️ Hız Eğrisi (Speed Ramp)</h3>
      <div class="hint">Seçili klibe CapCut Pro / Spunkram tarzı hız eğrisi uygular.</div>
      <div class="sf-list">${Object.entries(pre || {}).map(([k, v]) => `<button class="tb" data-v="${esc(k)}" style="justify-content:flex-start">${esc(v.name)}</button>`).join("")}</div>
      <div class="row">${c.ramp ? `<button class="tb" data-v="__off">Eğriyi kaldır</button>` : ""}<button class="tb" data-v="">Vazgeç</button></div>`);
    if (!pick) return;
    snap();
    if (pick === "__off") { delete c.ramp; changed(); toast("Hız eğrisi kaldırıldı"); return; }
    if (pre?.[pick]?.pts) { c.ramp = pre[pick].pts; changed(); toast("Hız eğrisi uygulandı: " + pre[pick].name); }
  }

  async function audioreact(c) {
    c = c && ["video", "image"].includes(clipKind(c)) ? c : needSel(["video", "image"]); if (!c) return;
    const srcC = ST.p.clips.find(x => (clipKind(x) === "audio" || assetOf(x)?.audio) && x.start < c.start + c.dur && x.start + x.dur > c.start) || c;
    const a = assetOf(srcC); if (!a?.path) { toast("Sesli bir klip bulunamadı"); return; }
    const str = await modal(`<h3>🔊 Ses-Tepkili Zoom</h3><div class="hint">Bas/tepe enerjisine göre otomatik nabız zoom uygulanır.</div>
      <div class="row"><button class="tb" data-v="0.08">Hafif (%8)</button><button class="tb pri" data-v="0.15">Orta (%15)</button><button class="tb" data-v="0.26">Sert (%26)</button></div>`);
    if (!str) return;
    busy("Ses enerjisi ölçülüyor…");
    let r;
    try { r = await api.studio_audio_reactive(a.path, srcC.in || 0, c.dur * (srcC.speed || 1), c.dur, +str); } finally { busy(null); }
    if (!r?.ok || !r.kf?.length) { toast("Ses anahtar karesi üretilemedi"); return; }
    snap(); c.zoom = r.kf; changed();
    toast(`${r.kf.length} ses-tepkili zoom anahtar karesi eklendi`);
  }

  async function reframe916(c) {
    c = c && clipKind(c) === "video" ? c : needSel(["video"]); if (!c) return;
    const a = assetOf(c); if (!a?.path) return;
    busy("Özne / yüz konumu izleniyor…");
    let r;
    try { r = await api.studio_auto_reframe(a.path, c.in || 0, c.dur * (c.speed || 1)); } finally { busy(null); }
    if (!r?.ok || !r.kf?.length) { toast("Oto-Reframe başarısız"); return; }
    snap(); c.kf = r.kf; changed();
    toast(`Oto-Reframe (${r.method}) uygulandı: ${r.kf.length} nokta`);
  }

  async function aivision(c) {
    c = c && clipKind(c) === "video" ? c : (selClips()[0] || ST.p.clips.find(x => clipKind(x) === "video"));
    const path = (c && assetOf(c)?.path) || await pickOne(); if (!path) return;
    busy("Kare şeridi & ses haritası hazırlanıyor…");
    let r;
    try { r = await api.studio_inspect_ai(path, 2.0); } finally { busy(null); }
    if (!r?.ok) { toast("Analiz başarısız"); return; }
    const es = r.energy_summary || {};
    await modal(`<h3>👁️ AI Görüş Paketi</h3>
      <div class="sf-stats">
        <div class="sf-stat"><small>Süre</small><b>${fmt(r.duration)}</b></div>
        <div class="sf-stat"><small>Boyut</small><b>${r.w}×${r.h}</b></div>
        <div class="sf-stat"><small>Sessiz Sn</small><b>${(es.quiet_secs || []).length}</b></div>
        <div class="sf-stat"><small>Zirve Sn</small><b>${(es.peak_secs || []).length}</b></div>
      </div>
      ${r.sheet_url ? `<img src="${esc(r.sheet_url)}" style="width:100%;max-height:46vh;object-fit:contain;border-radius:6px;border:1px solid #2A2140;background:#000">` : ""}
      <div class="row"><button class="tb pri" data-v="ok">Tamam</button></div>`);
  }
})();
