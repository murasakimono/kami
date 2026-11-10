// Kami Sunak ekleri (B10): son kullanilan indirme klasorleri (ayarlarda hizli secim)
"use strict";
(() => {
  const KEY = "kami.recentDirs";
  const get = () => { try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch { return []; } };
  const put = (d) => { if (!d) return; const l = [d, ...get().filter((x) => x !== d)].slice(0, 6); try { localStorage.setItem(KEY, JSON.stringify(l)); } catch { /* yok */ } render(); };
  let sel = null;
  function render() {
    const path = document.getElementById("dirPath"); if (!path) return;
    if (!sel) {
      sel = document.createElement("select"); sel.id = "dirRecent"; sel.className = "dir-recent";
      sel.style.cssText = "margin-left:6px;max-width:200px;background:#16101F;color:#C4B5FD;border:1px solid #3A2E52;border-radius:6px;height:30px;font:600 12px 'Chakra Petch',sans-serif;";
      (document.getElementById("dirReset") || path).after(sel);
      sel.addEventListener("change", async () => {
        const d = sel.value; if (!d) return;
        try { await api.set_setting("download_dir", d); path.textContent = d; put(d); } catch { /* yok */ }
      });
    }
    const l = get().filter((x) => x !== path.textContent.trim());
    sel.innerHTML = `<option value="">${(typeof state !== "undefined" && state.lang === "en") ? "Recent folders" : "Son klasörler"} (${l.length})</option>` + l.map((d) => `<option value="${d.replace(/"/g, "&quot;")}">${d.replace(/[<>&]/g, "")}</option>`).join("");
    sel.hidden = !l.length;
  }
  const watch = () => {
    const path = document.getElementById("dirPath");
    if (!path) return setTimeout(watch, 800);
    let last = path.textContent.trim();
    if (last) put(last);
    new MutationObserver(() => { const t = path.textContent.trim(); if (t && t !== last) { last = t; put(t); } }).observe(path, { childList: true, characterData: true, subtree: true });
    render();
  };
  watch();
})();
