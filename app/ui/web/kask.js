"use strict";
// tarayici confirm() yerine uygulama ici soru (adres cubugu "127.0.0.1 şunu diyor" gorunmesin)
function kAsk(msg, yes, no, danger = false) {
  const en = (document.documentElement.lang || "").startsWith("en");
  yes ||= en ? "OK" : "Tamam"; no ||= en ? "Cancel" : "Vazgeç";
  return new Promise(res => {
    if (!document.getElementById("kAskCss")) {
      const st = document.createElement("style"); st.id = "kAskCss";
      st.textContent = `.k-ask{position:fixed;inset:0;z-index:9999;display:grid;place-items:center;background:rgba(5,4,8,.62);backdrop-filter:blur(6px);animation:kaIn .14s ease}
.k-ask .box{min-width:320px;max-width:440px;background:#120E1A;border:1px solid #2A2140;border-radius:16px;padding:22px 22px 16px;box-shadow:0 24px 70px rgba(0,0,0,.6);font:500 14px "Chakra Petch",sans-serif;color:#EDE9F6}
.k-ask p{margin:0 0 18px;line-height:1.45;white-space:pre-line}.k-ask .row{display:flex;gap:8px;justify-content:flex-end}
.k-ask button{border:1px solid #2A2140;background:#1A1426;color:#EDE9F6;border-radius:10px;padding:8px 16px;font:inherit;cursor:pointer}
.k-ask button:hover{border-color:#8B5CF6}.k-ask button.go{background:#6D28D9;border-color:#8B5CF6}.k-ask button.go.red{background:#B4235A;border-color:#FF4F8B}
@keyframes kaIn{from{opacity:0}to{opacity:1}}`;
      document.head.appendChild(st);
    }
    const d = document.createElement("div"); d.className = "k-ask";
    d.innerHTML = `<div class="box"><p></p><div class="row"><button class="no"></button><button class="go${danger ? " red" : ""}"></button></div></div>`;
    d.querySelector("p").textContent = msg; d.querySelector(".no").textContent = no; d.querySelector(".go").textContent = yes;
    const done = v => { d.remove(); document.removeEventListener("keydown", key, true); res(v); };
    const key = e => { if (e.key === "Escape") { e.stopPropagation(); done(false); } else if (e.key === "Enter") { e.stopPropagation(); done(true); } };
    d.querySelector(".no").onclick = () => done(false); d.querySelector(".go").onclick = () => done(true);
    d.onclick = e => { if (e.target === d) done(false); };
    document.addEventListener("keydown", key, true);
    document.body.appendChild(d); d.querySelector(".go").focus();
  });
}
window.kAsk = kAsk;
function kAlert(msg, ok) {
  return kAsk(msg, ok || ((document.documentElement.lang || "").startsWith("en") ? "OK" : "Tamam"), " ").then(() => {
    // Tek tus gorunumu icin .no gizlenmisti
  });
}
function kPrompt(msg, defVal = "", yes, no) {
  const en = (document.documentElement.lang || "").startsWith("en");
  yes ||= en ? "OK" : "Tamam"; no ||= en ? "Cancel" : "Vazgeç";
  return new Promise(res => {
    kAsk(msg, yes, no).then(() => {});
    const box = document.querySelector(".k-ask:last-of-type .box");
    if (!box) { res(""); return; }
    const inp = document.createElement("input");
    inp.value = defVal;
    inp.style.cssText = "width:100%;box-sizing:border-box;margin:-8px 0 14px;padding:9px 12px;border-radius:9px;border:1px solid #2A2140;background:#09070F;color:#EDE9F6;font:inherit;outline:none";
    box.querySelector("p").after(inp);
    const d = box.closest(".k-ask");
    const go = d.querySelector(".go"), cancel = d.querySelector(".no");
    const finish = (v) => { d.remove(); document.removeEventListener("keydown", key, true); res(v); };
    const key = (e) => { if (e.key === "Escape") { e.stopPropagation(); finish(""); } else if (e.key === "Enter") { e.stopPropagation(); finish(inp.value.trim()); } };
    go.onclick = () => finish(inp.value.trim());
    cancel.onclick = () => finish("");
    d.onclick = (e) => { if (e.target === d) finish(""); };
    document.addEventListener("keydown", key, true);
    setTimeout(() => { inp.focus(); inp.select(); }, 20);
  });
}
window.kAlert = kAlert;
window.kPrompt = kPrompt;
