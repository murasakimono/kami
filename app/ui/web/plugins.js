// Ayarlar > Eklentiler: ac/kapat, yeniden yukle, plugin.json "settings" semasindan OTOMATIK cizilen ayarlar.
// Yeni eklenti icin bu dosyaya dokunmak GEREKMEZ (docs/EKLENTI-REHBERI.md).
"use strict";
Object.assign(I18N.tr, {
  s_plugins: "Eklentiler", pl_hint: "Kami'nin özellik eklentileri (plugins klasörü). Yeni eklenti: plugins içine klasör koy + Yeniden yükle ya da Kami'yi yeniden aç.",
  pl_on: "Açık", pl_off: "Kapalı", pl_reload: "Yeniden yükle", pl_reloaded: (n) => `${n} yeniden yüklendi ✓`,
  pl_error: "Hata", pl_sites: "Siteler", pl_secret_set: "kayıtlı ✓", pl_secret_none: "yok", pl_save: "Kaydet",
  pl_saved: "Kaydedildi ✓", pl_empty: "Eklenti bulunamadı.",
});
Object.assign(I18N.en, {
  s_plugins: "Plugins", pl_hint: "Kami's feature plugins (plugins folder). New plugin: drop a folder into plugins + Reload, or restart Kami.",
  pl_on: "On", pl_off: "Off", pl_reload: "Reload", pl_reloaded: (n) => `${n} reloaded ✓`,
  pl_error: "Error", pl_sites: "Sites", pl_secret_set: "saved ✓", pl_secret_none: "none", pl_save: "Save",
  pl_saved: "Saved ✓", pl_empty: "No plugins found.",
});

const plText = (v) => (v && typeof v === "object") ? (v[state.lang] || v.en || v.tr || "") : (v || "");

function plField(p, f) {
  const id = `pl-${p.id}-${f.key}`;
  const attrs = `id="${id}" data-p="${escapeHtml(p.id)}" data-k="${escapeHtml(f.key)}"`;
  const help = f.help ? `<div class="hint">${escapeHtml(plText(f.help))}</div>` : "";
  const label = escapeHtml(plText(f.label) || f.key);
  if (f.type === "bool") {
    return `<label class="check"><input type="checkbox" ${attrs}${f.value ? " checked" : ""}><span>${label}</span></label>${help}`;
  }
  let input;
  if (f.type === "choice") {
    input = `<select ${attrs}>${(f.choices || []).map((c) => `<option value="${escapeHtml(String(c))}"${String(c) === String(f.value) ? " selected" : ""}>${escapeHtml(String(c))}</option>`).join("")}</select>`;
  } else if (f.type === "int") {
    input = `<input type="number" ${attrs} value="${escapeHtml(String(f.value ?? ""))}"${f.min != null ? ` min="${f.min}"` : ""}${f.max != null ? ` max="${f.max}"` : ""}>`;
  } else if (f.type === "secret") {
    input = `<span class="hint">${T(f.has_value ? "pl_secret_set" : "pl_secret_none")}</span>` +
      `<input type="password" autocomplete="off" spellcheck="false" ${attrs}><button type="button" class="btn ghost" data-save="${id}">${T("pl_save")}</button>`;
  } else {
    input = `<input type="text" spellcheck="false" ${attrs} value="${escapeHtml(String(f.value ?? ""))}">`;
  }
  return `<div class="row"><span>${label}</span><span class="pl-in">${input}</span></div>${help}`;
}

async function refreshPlugins() {
  const list = await api.plugins();
  const box = $("#pluginList");
  if (!list.length) { box.innerHTML = `<p class="hint">${T("pl_empty")}</p>`; return; }
  box.innerHTML = list.map((p) => `<div class="pl-card${p.enabled ? "" : " off"}">
    <div class="pl-head"><b>${escapeHtml(p.name)}</b> <span class="hint">v${escapeHtml(p.version)}${p.author ? " · " + escapeHtml(p.author) : ""}</span>
      <span class="pl-act"><label class="check"><input type="checkbox" data-toggle="${escapeHtml(p.id)}"${p.enabled ? " checked" : ""}><span>${T(p.enabled ? "pl_on" : "pl_off")}</span></label>
      <button type="button" class="btn ghost" data-reload="${escapeHtml(p.id)}">${T("pl_reload")}</button></span></div>
    ${p.description ? `<div class="hint">${escapeHtml(p.description)}</div>` : ""}
    ${p.sites.length ? `<div class="hint">${T("pl_sites")}: ${p.sites.map(escapeHtml).join(", ")}</div>` : ""}
    ${p.error ? `<div class="st-error">${T("pl_error")}: ${escapeHtml(p.error)}</div>` : ""}
    ${p.enabled ? p.settings.map((f) => plField(p, f)).join("") : ""}
  </div>`).join("");
}

function bindPlugins() {
  const box = $("#pluginList");
  $("#settingsBtn").addEventListener("click", () => setTimeout(refreshPlugins, 80));
  // name ozniteligi yok: genel ayar kaydedicisi (settingsForm change) bunlara dokunmaz
  box.addEventListener("change", async (e) => {
    const el = e.target;
    if (el.dataset.toggle) {
      const r = await api.plugin_set_enabled(el.dataset.toggle, el.checked);
      if (!r.ok && r.error) toast(r.error, true);
      refreshPlugins();
      return;
    }
    if (!el.dataset.p || el.type === "password") return;
    const v = el.type === "checkbox" ? el.checked : el.type === "number" ? Number(el.value) : el.value;
    const r = await api.plugin_set(el.dataset.p, el.dataset.k, v);
    if (!r.ok) toast(r.error, true); else if (el.type === "number") el.value = r.value;
  });
  box.addEventListener("click", async (e) => {
    const rl = e.target.closest("[data-reload]");
    if (rl) {
      const r = await api.plugin_reload(rl.dataset.reload);
      toast(r.ok ? T("pl_reloaded", rl.dataset.reload) : `${T("pl_error")}: ${r.error}`, !r.ok);
      refreshPlugins();
      return;
    }
    const sv = e.target.closest("[data-save]");
    if (sv) {
      const inp = document.getElementById(sv.dataset.save);
      const r = await api.plugin_set(inp.dataset.p, inp.dataset.k, inp.value);
      inp.value = "";
      toast(r.ok ? T("pl_saved") : r.error, !r.ok);
      refreshPlugins();
    }
  });
}
window.addEventListener("pywebviewready", () => bindPlugins());
