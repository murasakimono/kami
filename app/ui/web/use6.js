// Asama 6c arayuzu: Gecmis, Toplu link, bitince KAPAT, inerken izle, uyarilar, Ayarlar > Kullanim / Telefon.
"use strict";

Object.assign(I18N.tr, {
  v_history: "Geçmiş", v_batch: "Toplu link",
  hs_ph: "Ara (ad ya da link)", hs_empty: "Kayıt yok.", hs_clear: "Geçmişi temizle", hs_gone: "dosya yok",
  hs_again: "Tekrar indir", hs_show: "Göster",
  bt_hint: "Link ya da metin yapıştır (kendiliğinden listelenir) veya sayfa adresi gir → \"Sayfadan çek\". YouTube kanal/liste/arama linkinde videolar listelenir. Süzgeçle seç, \"Kuyruğa at\". dosya[001-100].jpg deseni de olur.",
  bt_k_all: "Tümü", bt_k_video: "Videolar", bt_k_music: "Müzik", bt_k_archive: "Arşivler", bt_k_doc: "Belgeler", bt_k_image: "Resimler",
  bt_info_page: (n, h) => `${n} link` + (h ? ` · ${h} sayfa kaynağı (js/css/ikon) gizlendi` : ""),
  bt_info_yt: (t, n) => `${t}: ${n} video (yt-dlp)`,
  bt_ph: "Linkleri ya da herhangi bir metni yapıştır", bt_page_ph: "…ya da sayfa adresi (sayfadaki tüm linkler)",
  bt_fetch: "Sayfadan çek", bt_parse: "Linkleri çıkar", bt_filter_ph: "Süz: .mp4 .zip ya da kelime (boşlukla birden çok)",
  bt_all: "Tümü", bt_none: "Hiçbiri", bt_add: "Kuyruğa at", bt_count: (s, n) => `${s} / ${n} seçili`,
  bt_added: (a, n) => `${a}/${n} link kuyruğa eklendi`,
  sd_title: "Kuyruk bitince bilgisayarı kapat", sd_off: "Bitince kapat: kapalı", sd_on: "Bitince KAPAT ✓",
  sd_count: (n) => `Kuyruk bitti — bilgisayar ${n} sn sonra KAPANACAK`, sd_cancel: "İptal",
  watch_btn: "İnerken izle", w_buf: (p) => `İzle: tampon %${Math.round(p * 100)}`, w_play: "Oynatılıyor ▶",
  err_watch_unsupported: "Bu indirme izlenemez (sadece doğrudan/RD/torrent videosu).", err_watch_failed: "Sıra modu açılamadı.",
  warn_dup: (n, d) => `Bunu daha önce indirdin: ${n} (${d})`, warn_dup_gone: " — dosya artık yok",
  warn_disk: (n, need, free) => `Disk dolacak: ${n} (${need} gerekli, ${free} boş)`, rule_used: (n) => `Kural: ${n}`,
  s_use: "Kullanım", s_rules: "Site kuralları", s_rules_hint: "İlk eşleşen kural uygulanır. Klasör: kategori ya da tam yol.",
  s_rule_add: "Kural ekle", r_name: "Ad", r_host: "site (youtube.com)", r_music: "şarkı", r_auto: "sormadan",
  r_fmt_any: "biçim: aynı", r_folder: "klasör", r_del: "Sil", r_ext: "uzantı (zip,rar)",
  s_extract: "Arşiv inince aç (7-Zip; yoksa sadece .zip)", s_extract_del: "Açıldıysa arşivi sil",
  s_music_move: "Müziği müzik kütüphanesi klasörüne taşı (Dopamine)", s_disk_warn: "Disk dolacaksa önceden uyar",
  s_link_refresh: "Süresi dolan linki yenileyip kaldığı yerden devam et (RD / bulut)",
  s_history: "Geçmişi tut", s_history_warn: "Daha önce indirilen linkte uyar",
  s_watch_mb: "İnerken izle: oynatmadan önce baştan inecek MB", s_watch_player: "İnerken izle oynatıcısı", s_player_default: "Windows varsayılanı",
  s_phone: "Telefon", s_phone_on: "Telefondan gönder (aynı Wi-Fi)", s_phone_port: "Port",
  s_phone_hint: "Anahtarı sadece kendi telefonuna yaz. Windows güvenlik duvarı ilk açılışta izin sorabilir (Özel ağ).",
  s_phone_newkey: "Yeni anahtar",
  phone_off: "Kapalı.", phone_how: (ips, host, port, key) =>
    `<b>Adresler</b> (telefon hangisine ulaşıyorsa; önce Safari'de <code>/test</code> ile dene):<br>` +
    ips.map((ip) => `<code>http://${ip}:${port}/send</code> · <a href="#" data-test="http://${ip}:${port}/test">test</a>`).join("<br>") +
    `<br><code>http://${host}:${port}/send</code> <span class="hint">(bilgisayar adı; IP değişse de çalışabilir)</span><br>` +
    `<b>Anahtar:</b> <code>${key}</code><br><br>` +
    `<b>iPhone Kestirme (adım adım)</b><ol>` +
    `<li>Kestirmeler (Shortcuts) → <b>+</b> → ad: "Kami'ye gönder".</li>` +
    `<li>Ayrıntılar (ⓘ) → <b>Paylaşım Sayfasında Göster</b> (Show in Share Sheet) aç; girdi türü: URL'ler + Metin.</li>` +
    `<li>Eylem ekle: <b>Girdideki URL'leri Al</b> (Get URLs from Input) — girdi: Kestirme Girdisi.</li>` +
    `<li>Eylem ekle: <b>URL'nin İçeriğini Al</b> (Get Contents of URL): URL = yukarıdaki /send adresi. ` +
    `"Daha Fazla Göster": Yöntem <b>POST</b>; Üstbilgiler: <code>X-Kami-Key</code> = anahtar; İstek Gövdesi <b>JSON</b>: ` +
    `alan <code>text</code> (Metin) = önceki adımın <b>URL'ler</b> çıktısı.</li>` +
    `<li>(İsteğe bağlı) Bu adımdan ÖNCE <b>Menüden Seç</b> (Choose from Menu): "Video (MP4)" / "Ses (MP3)"; her seçenekte ` +
    `<b>Metin</b> eylemi ile <code>mp4</code> ya da <code>mp3</code> yaz ve JSON gövdesine ikinci alan <code>format</code> = o metin ekle. ` +
    `<code>format</code> yoksa ya da <code>sor</code> ise Kami bilgisayarda MP4/MP3 seçim penceresini açar.</li>` +
    `<li>Eylem ekle: <b>Sonucu Göster</b> (Show Result) — Kami'nin cevabı ("✓ Kuyruğa eklendi …") görünür.</li>` +
    `<li>İlk çalıştırmada iOS "yerel ağdaki aygıtlara bağlan" izni sorarsa <b>İzin Ver</b>.</li></ol>` +
    `Kestirmesiz: Safari'de <code>http://${ips[0]}:${port}/</code> (gönderme + indirme durumu).`,
  phone_last: (t, ok, msg) => `Son istek ${t}: ${ok ? "✓" : "✕"} ${msg}`,
  phone_last_none: "Henüz telefondan istek gelmedi.",
  s_ntfy: "Telefona bildirim (ntfy)", s_ntfy_server: "ntfy sunucusu", s_ntfy_topic: "Konu (gizli)",
  s_ntfy_ph: "uzun, tahmin edilemez bir ad", s_ntfy_test: "Test", s_ntfy_ok: "kayıtlı ✓", s_ntfy_none: "yok",
  s_ntfy_each: "Her indirme bitince", s_ntfy_queue: "Kuyruk bitince", s_ntfy_errors: "Hata olunca",
  ntfy_sent: "Test bildirimi gönderildi ✓", ntfy_fail: "Gönderilemedi (konu/sunucu?)", err_ntfy_topic: "Konu 8-64 karakter: harf, rakam, - _",
});
Object.assign(I18N.en, {
  v_history: "History", v_batch: "Link list",
  hs_ph: "Search (name or link)", hs_empty: "No records.", hs_clear: "Clear history", hs_gone: "file missing",
  hs_again: "Download again", hs_show: "Show",
  bt_hint: "Paste links or text (listed automatically) or enter a page address → \"Fetch page\". YouTube channel/playlist/search links list their videos. Pick with the filters, then \"Queue\". Patterns like file[001-100].jpg work too.",
  bt_k_all: "All", bt_k_video: "Videos", bt_k_music: "Music", bt_k_archive: "Archives", bt_k_doc: "Documents", bt_k_image: "Images",
  bt_info_page: (n, h) => `${n} links` + (h ? ` · ${h} page resources (js/css/icons) hidden` : ""),
  bt_info_yt: (t, n) => `${t}: ${n} videos (yt-dlp)`,
  bt_ph: "Paste links or any text", bt_page_ph: "…or a page address (all links on it)",
  bt_fetch: "Fetch page", bt_parse: "Extract links", bt_filter_ph: "Filter: .mp4 .zip or words (space = several)",
  bt_all: "All", bt_none: "None", bt_add: "Queue", bt_count: (s, n) => `${s} / ${n} selected`,
  bt_added: (a, n) => `${a}/${n} links queued`,
  sd_title: "Shut down the PC when the queue finishes", sd_off: "Shut down when done: off", sd_on: "SHUT DOWN when done ✓",
  sd_count: (n) => `Queue finished — PC will SHUT DOWN in ${n} s`, sd_cancel: "Cancel",
  watch_btn: "Watch while downloading", w_buf: (p) => `Watch: buffer ${Math.round(p * 100)}%`, w_play: "Playing ▶",
  err_watch_unsupported: "This download can't be watched (direct/RD/torrent video only).", err_watch_failed: "Couldn't enable sequential mode.",
  warn_dup: (n, d) => `You already downloaded this: ${n} (${d})`, warn_dup_gone: " — file no longer exists",
  warn_disk: (n, need, free) => `Disk will fill up: ${n} (${need} needed, ${free} free)`, rule_used: (n) => `Rule: ${n}`,
  s_use: "Usage", s_rules: "Site rules", s_rules_hint: "First matching rule wins. Folder: a category or a full path.",
  s_rule_add: "Add rule", r_name: "Name", r_host: "site (youtube.com)", r_music: "song", r_auto: "no prompt",
  r_fmt_any: "format: same", r_folder: "folder", r_del: "Remove", r_ext: "extensions (zip,rar)",
  s_extract: "Extract archives when done (7-Zip; otherwise .zip only)", s_extract_del: "Delete the archive after extracting",
  s_music_move: "Move music to the music library folder (Dopamine)", s_disk_warn: "Warn early if the disk will fill up",
  s_link_refresh: "Refresh expired links and resume (RD / cloud)",
  s_history: "Keep history", s_history_warn: "Warn on links downloaded before",
  s_watch_mb: "Watch while downloading: MB from the start before playing", s_watch_player: "Player for watching", s_player_default: "Windows default",
  s_phone: "Phone", s_phone_on: "Send from phone (same Wi-Fi)", s_phone_port: "Port",
  s_phone_hint: "Only enter the key on your own phone. Windows Firewall may ask once (Private network).",
  s_phone_newkey: "New key",
  phone_off: "Off.", phone_how: (ips, host, port, key) =>
    `<b>Addresses</b> (whichever the phone can reach; try <code>/test</code> in Safari first):<br>` +
    ips.map((ip) => `<code>http://${ip}:${port}/send</code> · <a href="#" data-test="http://${ip}:${port}/test">test</a>`).join("<br>") +
    `<br><code>http://${host}:${port}/send</code> <span class="hint">(computer name; may work even if the IP changes)</span><br>` +
    `<b>Key:</b> <code>${key}</code><br><br>` +
    `<b>iPhone Shortcut (step by step)</b><ol>` +
    `<li>Shortcuts → <b>+</b> → name: "Send to Kami".</li>` +
    `<li>Details (ⓘ) → turn on <b>Show in Share Sheet</b>; input types: URLs + Text.</li>` +
    `<li>Add action: <b>Get URLs from Input</b> — input: Shortcut Input.</li>` +
    `<li>Add action: <b>Get Contents of URL</b>: URL = the /send address above. "Show More": Method <b>POST</b>; ` +
    `Headers: <code>X-Kami-Key</code> = key; Request Body <b>JSON</b>: field <code>text</code> (Text) = the <b>URLs</b> from the previous step.</li>` +
    `<li>(Optional) BEFORE that step add <b>Choose from Menu</b>: "Video (MP4)" / "Audio (MP3)"; in each branch a <b>Text</b> action ` +
    `with <code>mp4</code> or <code>mp3</code>, and add a second JSON field <code>format</code> = that text. ` +
    `Without <code>format</code> (or with <code>ask</code>) Kami opens the MP4/MP3 chooser on the computer.</li>` +
    `<li>Add action: <b>Show Result</b> — Kami's reply ("✓ Queued …") appears.</li>` +
    `<li>If iOS asks to connect to devices on the local network the first time, tap <b>Allow</b>.</li></ol>` +
    `Without a shortcut: Safari at <code>http://${ips[0]}:${port}/</code> (send + download status).`,
  phone_last: (t, ok, msg) => `Last request ${t}: ${ok ? "✓" : "✕"} ${msg}`,
  phone_last_none: "No request from the phone yet.",
  s_ntfy: "Phone notifications (ntfy)", s_ntfy_server: "ntfy server", s_ntfy_topic: "Topic (secret)",
  s_ntfy_ph: "a long, unguessable name", s_ntfy_test: "Test", s_ntfy_ok: "saved ✓", s_ntfy_none: "none",
  s_ntfy_each: "Every finished download", s_ntfy_queue: "When the queue finishes", s_ntfy_errors: "On errors",
  ntfy_sent: "Test notification sent ✓", ntfy_fail: "Couldn't send (topic/server?)", err_ntfy_topic: "Topic: 8-64 chars, letters, digits, - _",
});

// ---------- inerken izle ----------
function canWatch(d) {
  if (d.kind === "media" || d.status !== "active") return false;
  return d.category === "video" || (d.kind === "torrent") || /\.(mp4|mkv|webm|avi|mov|m4v|ts)$/i.test(d.filename || "");
}
async function startWatch(id) {
  const r = await api.watch(id);
  if (!r.ok) toast(T("err_" + r.error), true);
}
const _badges6b = extraBadges;
extraBadges = function (d) {   // eslint-disable-line no-global-assign
  const x = d.extra || {}, out = [_badges6b(d)];
  if (x.watch === "buffering") out.push(`<span class="badge prog">${T("w_buf", x.watch_p || 0)}</span>`);
  else if (x.watch === "playing") out.push(`<span class="badge ok">${T("w_play")}</span>`);
  if (x.extracted) out.push(`<span class="badge ok">${state.lang === "tr" ? "Açıldı ✓" : "Extracted ✓"}</span>`);
  return out.join("");
};

// ---------- bitince kapat ----------
function syncShutdown(sd) {
  const armed = sd ? sd.armed : !!state.settings.shutdown_when_done;
  const b = $("#shutdownToggle");
  b.textContent = T(armed ? "sd_on" : "sd_off");
  b.classList.toggle("on", armed);
  const bar = $("#sdBar");
  if (sd && sd.countdown !== null && sd.countdown !== undefined) {
    bar.hidden = false;
    $("#sdText").textContent = T("sd_count", sd.countdown);
  } else bar.hidden = true;
}

// ---------- uyarilar ----------
function onWarns(ws) {
  for (const w of ws || []) {
    if (w.kind === "dup") {
      const when = w.when ? new Date(w.when * 1000).toLocaleDateString(state.lang) : "";
      toast(T("warn_dup", w.name, when) + (w.exists ? "" : T("warn_dup_gone")), true);
    } else if (w.kind === "disk") toast(T("warn_disk", w.name, fmtBytes(w.need), fmtBytes(w.free)), true);
  }
}

// ---------- gecmis ----------
let hsTimer = null;
async function historyRefresh() {
  const rows = await api.history_search($("#historyQ").value || "");
  $("#historyEmpty").hidden = rows.length > 0;
  $("#historyList").innerHTML = rows.map((h, i) => rdRow(h.filename || h.url,
    `<span>${new Date(h.finished * 1000).toLocaleString(state.lang)}</span>${h.size ? `<span>${fmtBytes(h.size)}</span>` : ""}` +
    (h.exists ? "" : `<span class="st-error">${T("hs_gone")}</span>`),
    (h.exists ? `<button type="button" class="btn ghost" data-hs="show" data-i="${i}">${T("hs_show")}</button>` : "") +
    `<button type="button" class="btn ghost" data-hs="again" data-i="${i}">${T("hs_again")}</button>`)).join("");
  historyRefresh.rows = rows;
}
VIEW_OPEN.history = historyRefresh;

// ---------- toplu link ----------
const bt = { links: [], sel: new Set(), kind: "all", titles: {}, yt: false };
const BT_EXT = {
  video: /\.(mp4|mkv|webm|mov|avi|m4v|ts|flv|wmv|m3u8|mpd)(\?|$)/i,
  music: /\.(mp3|m4a|flac|ogg|opus|wav|aac|wma)(\?|$)/i,
  archive: /\.(zip|rar|7z|tar|gz|bz2|xz|iso|r\d\d|\d{3})(\?|$)/i,
  doc: /\.(pdf|epub|mobi|docx?|xlsx?|pptx?|txt|cbz|cbr)(\?|$)/i,
  image: /\.(jpe?g|png|gif|webp|avif|bmp|tiff?)(\?|$)/i,
};
const BT_VIDEO_SITE = /(youtube\.com\/(watch|shorts)|youtu\.be\/|vimeo\.com\/\d|dailymotion\.com\/video|tiktok\.com\/.+\/video)/i;
function btKind(l) {
  if (bt.yt || BT_VIDEO_SITE.test(l)) return "video";
  for (const [k, re] of Object.entries(BT_EXT)) if (re.test(l)) return k;
  return "";
}
function batchShown() {
  const terms = ($("#batchFilter").value || "").toLowerCase().split(/\s+/).filter(Boolean);
  return bt.links.filter((l) => (bt.kind === "all" || btKind(l) === bt.kind) &&
    (!terms.length || terms.some((t) => l.toLowerCase().includes(t) || (bt.titles[l] || "").toLowerCase().includes(t))));
}
function batchRender() {
  const shown = batchShown();
  $("#batchList").innerHTML = shown.slice(0, 2000).map((l) =>
    `<li><label><input type="checkbox" data-l="${escapeHtml(l)}"${bt.sel.has(l) ? " checked" : ""}><span title="${escapeHtml(l)}">${escapeHtml(bt.titles[l] ? bt.titles[l] + "  —  " + l : l)}</span></label></li>`).join("");
  $("#batchCount").textContent = T("bt_count", shown.filter((l) => bt.sel.has(l)).length, shown.length);
}
function batchSet(links, r) {
  r = r || {};
  bt.links = links; bt.sel = new Set(links); bt.titles = r.titles || {}; bt.yt = r.source === "ytdlp";
  $("#batchInfo").textContent = r.source === "ytdlp" ? T("bt_info_yt", r.title || "", links.length)
    : r.source === "page" ? T("bt_info_page", links.length, r.hidden || 0) : "";
  batchRender();
}

// ---------- Ayarlar: kurallar, telefon, ntfy ----------
const CATS = ["music", "video", "archive", "program", "document", "other"];
let rulesCache = [];
function rulesRender() {
  $("#rulesBox").innerHTML = rulesCache.map((r, i) => {
    const folderOpts = [`<option value="">${T("r_folder")}: —</option>`, ...CATS.map((c) => `<option value="${c}"${r.folder === c ? " selected" : ""}>${T("cat_" + c)}</option>`)];
    if (r.folder && !CATS.includes(r.folder)) folderOpts.push(`<option value="${escapeHtml(r.folder)}" selected>${escapeHtml(r.folder)}</option>`);
    folderOpts.push(`<option value="__pick">…</option>`);
    return `<div class="rule" data-i="${i}">
      <input type="text" data-k="name" value="${escapeHtml(r.name)}" placeholder="${T("r_name")}">
      <input type="text" data-k="host" value="${escapeHtml(r.host)}" placeholder="${T("r_host")}">
      <label class="check"><input type="checkbox" data-k="music"${r.music ? " checked" : ""}>${T("r_music")}</label>
      <select data-k="format"><option value="">${T("r_fmt_any")}</option><option value="mp3"${r.format === "mp3" ? " selected" : ""}>MP3 ${r.audio_kbps || 320}</option><option value="mp4"${r.format === "mp4" ? " selected" : ""}>MP4</option></select>
      <label class="check"><input type="checkbox" data-k="auto"${r.auto ? " checked" : ""}>${T("r_auto")}</label>
      <select data-k="folder">${folderOpts.join("")}</select>
      <label class="check"><input type="checkbox" data-k="enabled"${r.enabled ? " checked" : ""}>✓</label>
      <button type="button" class="btn ghost danger" data-k="del">${T("r_del")}</button></div>`;
  }).join("");
}
async function rulesSave() {
  const r = await api.rules_set(rulesCache);
  if (r.ok) rulesCache = r.rules; else toast(r.error, true);
  rulesRender();
}

async function refreshUseSettings() {
  rulesCache = await api.rules_get();
  rulesRender();
  const p = await api.phone_info();
  const last = p.last || {};
  const lastTxt = last.t ? T("phone_last", new Date(last.t * 1000).toLocaleTimeString(), last.ok,
    escapeHtml(last.ok ? (last.link || "") : last.error === "no_link" ? (state.lang === "tr" ? "link bulunamadı" : "no link") : (last.error || ""))) : T("phone_last_none");
  $("#phoneBox").innerHTML = p.enabled && p.key
    ? T("phone_how", p.ips || [p.ip], escapeHtml(p.host || ""), p.port, escapeHtml(p.key)) + `<p class="hint">${lastTxt}</p>` : T("phone_off");
  const n = await api.ntfy_status();
  $("#ntfyState").textContent = T(n.has_topic ? "s_ntfy_ok" : "s_ntfy_none");
}

function bindUse() {
  $("#shutdownToggle").addEventListener("click", async () => {
    const r = await api.shutdown_arm(!state.settings.shutdown_when_done);
    state.settings.shutdown_when_done = !!r.armed;
    syncShutdown(r);
  });
  $("#sdCancel").addEventListener("click", async () => { await api.shutdown_cancel(); state.settings.shutdown_when_done = false; syncShutdown(null); });

  $("#historyQ").addEventListener("input", () => { clearTimeout(hsTimer); hsTimer = setTimeout(historyRefresh, 250); });
  $("#historyClear").addEventListener("click", async () => { if (confirm(T("hs_clear") + "?")) { await api.history_clear(); historyRefresh(); } });
  $("#historyList").addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-hs]");
    if (!b) return;
    const h = historyRefresh.rows[Number(b.dataset.i)];
    if (b.dataset.hs === "show") api.history_open(h.path);
    else { const r = await slow("add_url", h.page_url || h.url); if (dispatchAdd(r, h.page_url || h.url, {}) === "plain") toast(T("added")); }
  });

  $("#batchParse").addEventListener("click", async () => batchSet((await api.batch_parse($("#batchText").value)).links));
  $("#batchFetch").addEventListener("click", async (e) => {
    e.target.disabled = true;
    try {
      const r = await slow("batch_from_page", $("#batchPage").value);
      if (r.ok) batchSet(r.links, r); else toast(T("err_" + r.error), true);
    } finally { e.target.disabled = false; }
  });
  $("#batchFilter").addEventListener("input", batchRender);
  $("#batchChips").addEventListener("click", (e) => {
    const c = e.target.closest("[data-k]"); if (!c) return;
    bt.kind = c.dataset.k;
    $$("#batchChips .chip").forEach((x) => x.classList.toggle("on", x === c));
    batchRender();
  });
  let btTimer = 0;   // yapistirinca / yazinca "Linkleri cikar"a basmadan listele
  $("#batchText").addEventListener("input", () => {
    clearTimeout(btTimer);
    btTimer = setTimeout(async () => batchSet((await api.batch_parse($("#batchText").value)).links), 350);
  });
  $("#batchPage").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); $("#batchFetch").click(); } });
  $("#batchAll").addEventListener("click", () => { batchShown().forEach((l) => bt.sel.add(l)); batchRender(); });
  $("#batchNone").addEventListener("click", () => { batchShown().forEach((l) => bt.sel.delete(l)); batchRender(); });
  $("#batchList").addEventListener("change", (e) => {
    const c = e.target.closest("input[data-l]");
    if (c) { c.checked ? bt.sel.add(c.dataset.l) : bt.sel.delete(c.dataset.l); batchRender(); }
  });
  $("#batchAdd").addEventListener("click", async (e) => {
    const links = batchShown().filter((l) => bt.sel.has(l));
    if (!links.length) return;
    e.target.disabled = true;
    try { const r = await slow("batch_add", links); toast(T("bt_added", r.added || 0, links.length), !r.ok); tick(); }
    finally { e.target.disabled = false; }
  });

  $("#settingsBtn").addEventListener("click", () => setTimeout(refreshUseSettings, 60));
  $("#settingsForm").addEventListener("change", (e) => {
    if (["phone_enabled", "phone_port"].includes(e.target.name)) setTimeout(refreshUseSettings, 400);
  });
  $("#ruleAdd").addEventListener("click", () => {
    rulesCache.push({ name: "", enabled: true, host: "", music: false, ext: "", format: "", audio_kbps: 320, quality: "", folder: "", auto: false });
    rulesRender();
  });
  $("#rulesBox").addEventListener("change", async (e) => {
    e.stopPropagation();   // genel ayar formuna gitmesin (name yok zaten)
    const row = e.target.closest(".rule"); const k = e.target.dataset.k;
    if (!row || !k) return;
    const r = rulesCache[Number(row.dataset.i)];
    if (k === "folder" && e.target.value === "__pick") {
      const dir = await api.choose_folder();
      r.folder = dir || r.folder;
    } else r[k] = e.target.type === "checkbox" ? e.target.checked : e.target.value;
    rulesSave();
  });
  $("#rulesBox").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-k=del]");
    if (b) { rulesCache.splice(Number(b.closest(".rule").dataset.i), 1); rulesSave(); }
  });
  $("#phoneNewKey").addEventListener("click", async () => { await api.phone_new_key(); refreshUseSettings(); });
  $("#phoneBox").addEventListener("click", async (e) => {
    const a = e.target.closest("[data-test]"); if (!a) return;
    e.preventDefault();
    const r = await slow("phone_test", a.dataset.test);
    toast((r.ok ? "✓ " : "✕ ") + (r.message || a.dataset.test), !r.ok);
  });
  $("#ntfySave").addEventListener("click", async () => {
    const r = await slow("ntfy_set_topic", $("#ntfyTopic").value);
    $("#ntfyTopic").value = "";
    if (!r.ok) toast(T("err_" + r.error), true);
    refreshUseSettings();
  });
  $("#ntfyTest").addEventListener("click", async () => { const r = await slow("ntfy_test"); toast(T(r.ok ? "ntfy_sent" : "ntfy_fail"), !r.ok); });
  syncShutdown(null);
}

STATE_HOOKS.push((s) => {
  if ((s.warns || []).length) onWarns(s.warns);
  if (s.shutdown) { state.settings.shutdown_when_done = s.shutdown.armed; syncShutdown(s.shutdown); }
});

// kural ile dogrudan indirilen medya: kisa not
const _dispatch6 = dispatchAdd;
dispatchAdd = function (r, url, ctx) {   // eslint-disable-line no-global-assign
  if (r && r.ok && r.rule && r.ids) toast(T("rule_used", r.rule));
  return _dispatch6(r, url, ctx);
};

window.addEventListener("pywebviewready", () => bindUse());
