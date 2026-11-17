// v1.29 "Tumunu indir": sayfadaki tum indirilebilir adresleri listeler; tur/uzanti/metin filtresi, sec, Kami'ye gonder.
(() => {
  "use strict";
  const EN = !/^tr/i.test(navigator.language || "");
  const L = (tr, en) => (EN ? en : tr);
  const $ = (id) => document.getElementById(id);
  const KINDS = [
    ["video", L("Video", "Video"), /^(mp4|mkv|webm|mov|avi|m4v|flv|wmv|ts|mpg|mpeg|m3u8)$/],
    ["audio", L("Ses", "Audio"), /^(mp3|m4a|flac|wav|ogg|opus|aac|wma)$/],
    ["archive", L("Arşiv", "Archive"), /^(zip|7z|rar|tar|gz|tgz|xz|bz2|iso|001|r\d\d|part\d+)$/],
    ["image", L("Resim", "Image"), /^(jpg|jpeg|png|webp|gif|bmp|avif|tif|tiff|heic|svg)$/],
    ["doc", L("Belge", "Document"), /^(pdf|epub|mobi|cbz|cbr|docx?|xlsx?|pptx?|txt|srt|ass)$/],
    ["program", L("Program", "Program"), /^(exe|msi|apk|dmg|appimage|deb|rpm|msix|zipx)$/],
    ["torrent", "Torrent", /^(torrent)$/],
  ];
  const KIND_IC = { video: "🎬", audio: "🎵", archive: "📦", image: "🖼", doc: "📄", program: "⚙", torrent: "🧲", other: "🔗" };
  const S = { links: [], kind: "", sel: new Set(), page: "", title: "", tab: 0, lastIdx: -1, cap: 300 };

  function info(l) {
    if (/^magnet:/i.test(l.url)) {
      const dn = /[?&]dn=([^&]+)/i.exec(l.url);
      let name = l.text; try { if (dn) name = decodeURIComponent(dn[1].replace(/\+/g, " ")); } catch (_) {}
      return { name: name || "magnet", ext: "torrent", host: "magnet", kind: "torrent" };
    }
    let u; try { u = new URL(l.url); } catch (_) { return { name: l.url, ext: "", host: "", kind: "other" }; }
    let file = decodeURIComponent(u.pathname.split("/").pop() || "");
    const m = /\.([a-z0-9]{1,9})$/i.exec(file);
    const ext = m ? m[1].toLowerCase() : "";
    const kind = (KINDS.find(([, , rx]) => rx.test(ext)) || ["other"])[0];
    return { name: l.text && l.text.length > 2 && !/^https?:/.test(l.text) ? l.text : (file || u.hostname), file, ext, host: u.hostname, kind };
  }

  function visible() {
    const q = $("q").value.trim();
    let rx = null, words = [];
    if (q.length > 2 && q.startsWith("/") && q.endsWith("/")) { try { rx = new RegExp(q.slice(1, -1), "i"); } catch (_) {} }
    else words = q.toLowerCase().split(/\s+/).filter(Boolean);
    const host = (() => { try { return new URL(S.page).hostname.replace(/^www\./, ""); } catch (_) { return ""; } })();
    return S.links.filter((l) => {
      if (S.kind && l.i.kind !== S.kind) return false;
      if ($("hideHtml").checked && l.i.kind === "other" && (!l.i.ext || /^(html?|php|aspx?|jsp)$/.test(l.i.ext))) return false;
      if ($("sameHost").checked && host && !l.i.host.replace(/^www\./, "").endsWith(host)) return false;
      const hay = (l.i.name + " " + l.url).toLowerCase();
      if (rx && !rx.test(hay)) return false;
      if (words.length && !words.every((w) => hay.includes(w))) return false;
      return true;
    });
  }

  function render() {
    const counts = {};
    for (const l of S.links) counts[l.i.kind] = (counts[l.i.kind] || 0) + 1;
    $("kinds").innerHTML = [["", L("Hepsi", "All")], ...KINDS.map(([k, n]) => [k, n]), ["other", L("Diğer", "Other")]]
      .filter(([k]) => !k || counts[k]).map(([k, n]) => `<button class="chip ${S.kind === k ? "on" : ""}" data-k="${k}">${n}<b>${k ? counts[k] : S.links.length}</b></button>`).join("");
    const vis = visible();
    const tb = $("list"); tb.textContent = "";
    const slice = vis.slice(0, S.cap);
    const frag = document.createDocumentFragment();
    slice.forEach((l, idx) => {
      const tr = document.createElement("tr");
      if (S.sel.has(l.url)) tr.className = "sel";
      const c = document.createElement("input"); c.type = "checkbox"; c.checked = S.sel.has(l.url);
      const toggle = (checked, shift) => {
        if (shift && S.lastIdx >= 0) {
          const a = Math.min(S.lastIdx, idx), b = Math.max(S.lastIdx, idx);
          for (let k = a; k <= b; k++) {
            const u = vis[k]?.url; if (!u) continue;
            checked ? S.sel.add(u) : S.sel.delete(u);
          }
          render();
        } else {
          checked ? S.sel.add(l.url) : S.sel.delete(l.url);
          tr.classList.toggle("sel", checked);
          count();
        }
        S.lastIdx = idx;
      };
      c.onclick = (e) => { e.stopPropagation(); toggle(c.checked, e.shiftKey); };
      const td0 = document.createElement("td"); td0.appendChild(c);
      const tdK = document.createElement("td"); tdK.className = "kd"; tdK.textContent = KIND_IC[l.i.kind] || "🔗";
      const td1 = document.createElement("td"); td1.className = "nm"; td1.textContent = l.i.name; const sm = document.createElement("small"); sm.textContent = l.url; td1.appendChild(sm);
      const td2 = document.createElement("td"); td2.className = "ext"; td2.textContent = l.i.ext ? "." + l.i.ext : "";
      const td3 = document.createElement("td"); td3.className = "host"; td3.textContent = l.i.host;
      tr.append(td0, tdK, td1, td2, td3);
      tr.onclick = (e) => { if (e.target === c) return; c.checked = !c.checked; toggle(c.checked, e.shiftKey); };
      frag.appendChild(tr);
    });
    if (vis.length > S.cap) {
      const more = document.createElement("tr");
      more.innerHTML = `<td colspan="5" style="text-align:center;padding:12px"><button type="button" class="sec" id="grabMore">${L(`Daha fazla göster (${vis.length - S.cap} kaldı)`, `Show more (${vis.length - S.cap} left)`)}</button></td>`;
      more.querySelector("#grabMore").onclick = () => { S.cap += 400; render(); };
      frag.appendChild(more);
    }
    tb.appendChild(frag);
    $("empty").hidden = vis.length > 0;
    count();
  }
  function count() {
    const n = S.sel.size;
    $("count").textContent = L(`${visible().length} görünür · ${n} seçili`, `${visible().length} shown · ${n} selected`);
    $("send").disabled = !n;
    $("send").textContent = n ? L(`Kami ile indir (${n})`, `Download with Kami (${n})`) : L("Kami ile indir", "Download with Kami");
  }

  $("kinds").onclick = (e) => { const b = e.target.closest("[data-k]"); if (!b) return; S.kind = b.dataset.k; render(); };
  for (const id of ["q", "sameHost", "hideHtml"]) $(id).addEventListener("input", render);
  $("all").onclick = () => { for (const l of visible()) S.sel.add(l.url); render(); };
  $("none").onclick = () => { for (const l of visible()) S.sel.delete(l.url); render(); };
  $("send").onclick = async () => {
    const links = S.links.filter((l) => S.sel.has(l.url)).map((l) => ({ url: l.url, filename: "" }));
    $("send").disabled = true; $("msg").textContent = L("Gönderiliyor…", "Sending…");
    const r = await chrome.runtime.sendMessage({ type: "grab-send", links, pageUrl: S.page, title: S.title }).catch(() => null);
    $("msg").textContent = r ? L(`✓ ${r.ok} gönderildi${r.fail ? `, ${r.fail} olmadı` : ""}`, `✓ ${r.ok} sent${r.fail ? `, ${r.fail} failed` : ""}`) : L("✕ Kami'ye ulaşılamadı", "✕ Kami not reachable");
    if (r && r.ok) { S.sel.clear(); render(); }
    $("send").disabled = !S.sel.size;
  };

  $("t1").textContent = L("Tümünü indir", "Download all");
  $("t2").textContent = L("Yalnız bu siteden", "Only this site");
  $("t3").textContent = L("Sayfa linklerini gizle", "Hide page links");
  $("all").textContent = L("Görünenleri seç", "Select shown");
  $("none").textContent = L("Seçimi kaldır", "Clear shown");
  $("q").placeholder = L("Süz: kelimeler ya da /regex/ (ör. 1080p  ·  /bolum-\\d+/)", "Filter: words or /regex/ (e.g. 1080p · /episode-\\d+/)");
  $("empty").textContent = L("Bu süzgeçle eşleşen yok.", "Nothing matches this filter.");

  S.tab = +new URLSearchParams(location.search).get("tab");
  chrome.tabs.sendMessage(S.tab, { type: "grab-all" }).then((r) => {
    if (!r) throw new Error("yok");
    S.page = r.page; S.title = r.title;
    $("pageName").textContent = r.title || r.page;
    document.title = "Kami — " + (r.title || "");
    S.links = r.links.map((l) => ({ ...l, i: info(l) }));
    const pref = ["video", "archive", "audio", "torrent", "doc", "program"].find((k) => S.links.some((l) => l.i.kind === k));
    S.kind = pref || "";
    render();
  }).catch(() => {
    $("empty").hidden = false;
    $("empty").textContent = L("Sayfa okunamadı. Sayfayı yenileyip tekrar dene (tarayıcı sayfalarında çalışmaz).", "Could not read the page. Reload it and try again (does not work on browser pages).");
  });
})();
