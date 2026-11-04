"use strict";
const t = (k) => chrome.i18n.getMessage(k);
const ask = (payload) => chrome.runtime.sendMessage({ type: "popup", payload });

document.getElementById("captureLabel").textContent = t("popup_capture");
document.getElementById("open").textContent = t("popup_open");
document.getElementById("hint").textContent = t("popup_alt_hint");

async function refresh() {
  const res = await ask({ type: "ping" });
  const status = document.getElementById("status");
  const text = document.getElementById("statusText");
  const capture = document.getElementById("capture");
  const open = document.getElementById("open");
  if (res && res.ok) {
    status.className = "status on";
    text.textContent = t("popup_connected") + (res.version ? ` (${res.version})` : "");
    capture.disabled = false;
    capture.checked = !!res.capture_enabled;
    open.disabled = false;
  } else {
    status.className = "status off";
    text.textContent = res && res.error === "nohost" ? t("popup_nohost") : t("popup_offline");
    capture.disabled = true;
    open.disabled = true;
  }
}

document.getElementById("capture").addEventListener("change", async (e) => {
  const res = await ask({ type: "set_capture", enabled: e.target.checked });
  if (!res || !res.ok) refresh();
});
document.getElementById("open").addEventListener("click", async () => {
  await ask({ type: "show" });
  window.close();
});

refresh();
