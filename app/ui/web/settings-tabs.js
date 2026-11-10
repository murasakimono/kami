// Ayarlar penceresi: uzun kaydirma yerine solda kategori listesi + arama. Var olan fieldset'lere dokunmaz;
// pencere her acildiginda (sonradan eklenen eklenti / ntfy bolumleri dahil) listeyi yeniden kurar.
"use strict";

(() => {
  const GROUPS = [   // legend data-i18n anahtari -> kategori (bilinmeyenler "Diger")
    ["genel", "Genel", "General", ["s_general", "s_app", "s_about"]],
    ["indirme", "İndirme", "Downloads", ["s_downloads", "s_schedule", "s_browser"]],
    ["rd", "Real-Debrid ve torrent", "Real-Debrid & torrent", ["realdebrid", "s_torrent"]],
    ["medya", "Medya ve yapay zekâ", "Media & AI", ["s_mx"]],
    ["kullanim", "Oynatıcı ve kullanım", "Player & usage", ["s_use"]],
    ["telefon", "Telefon ve bildirim", "Phone & notifications", ["s_phone", "s_ntfy"]],
    ["guvenlik", "Güvenlik", "Security", ["s_security"]],
    ["eklenti", "Eklentiler", "Plugins", ["s_plugins"]],
  ];
  const tr = () => (typeof state === "undefined" || state.lang !== "en");
  let current = "genel";

  function keyOf(fs) {
    const lg = fs.querySelector(":scope > legend");
    if (!lg) return "";
    return lg.dataset.i18n || lg.textContent.trim().toLowerCase().replace(/[^a-z]/g, "");
  }
  function groupOf(fs) {
    const k = keyOf(fs);
    const g = GROUPS.find((x) => x[3].includes(k));
    return g ? g[0] : "diger";
  }

  function build() {
    const dlg = document.getElementById("settings");
    const form = document.getElementById("settingsForm");
    if (!dlg || !form) return;
    dlg.classList.add("st-tabs");
    let nav = form.querySelector(".st-nav");
    if (!nav) {
      nav = document.createElement("nav");
      nav.className = "st-nav";
      form.querySelector(".dialog-head").after(nav);
      nav.addEventListener("click", (e) => {
        const b = e.target.closest("[data-g]");
        if (b) { current = b.dataset.g; const inp = nav.querySelector("input"); if (inp) inp.value = ""; apply(); }
      });
    }
    let q = nav.querySelector("input");
    const fsets = [...form.querySelectorAll(":scope > fieldset")];
    const present = new Set(fsets.map(groupOf));
    const groups = GROUPS.filter((g) => present.has(g[0]));
    if (present.has("diger")) groups.push(["diger", "Diğer", "Other", []]);
    const val = q ? q.value : "";
    nav.innerHTML = `<input type="search" class="st-search" placeholder="${tr() ? "Ayar ara…" : "Search settings…"}" value="${val.replace(/"/g, "&quot;")}">` +
      groups.map((g) => `<button type="button" data-g="${g[0]}">${tr() ? g[1] : g[2]}</button>`).join("");
    nav.querySelector("input").addEventListener("input", apply);
    if (!groups.some((g) => g[0] === current)) current = groups[0]?.[0] || "genel";
    apply();
  }

  function apply() {
    const form = document.getElementById("settingsForm");
    const nav = form.querySelector(".st-nav");
    const q = (nav.querySelector("input")?.value || "").trim().toLocaleLowerCase("tr");
    nav.querySelectorAll("[data-g]").forEach((b) => b.classList.toggle("on", !q && b.dataset.g === current));
    for (const fs of form.querySelectorAll(":scope > fieldset")) {
      if (q) {   // aramada tum kategoriler: eslesen satirlar gorunur
        let any = false;
        for (const row of fs.querySelectorAll(":scope > label, :scope > .row, :scope > div, :scope > p")) {
          const hit = row.textContent.toLocaleLowerCase("tr").includes(q);
          row.classList.toggle("st-miss", !hit);
          any = any || hit;
        }
        fs.hidden = !any && !(fs.querySelector("legend")?.textContent.toLocaleLowerCase("tr").includes(q));
      } else {
        fs.querySelectorAll(".st-miss").forEach((r) => r.classList.remove("st-miss"));
        fs.hidden = groupOf(fs) !== current;
      }
    }
    form.scrollTop = 0;
  }

  // pencere her acildiginda yeniden kur (showModal sarmalanir)
  const dlg = document.getElementById("settings");
  if (dlg) {
    const orig = dlg.showModal.bind(dlg);
    dlg.showModal = () => { orig(); try { build(); } catch (e) { console.warn("ayar sekmeleri", e); } };
  }
})();
