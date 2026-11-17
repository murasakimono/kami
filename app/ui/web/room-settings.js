// Ayarlar > Kami Oda: odayi ac, baglantiyla katil, Cloudflare TURN anahtari.
"use strict";
(function () {
  async function turnState() {
    const s = await api.room_turn_status();
    $("#turnState").textContent = s.has ? "· kayıtlı" : "· yok";
    $("#turnClear").hidden = !s.has;
  }
  async function linkState() {
    const r = await api.room_status();
    $("#roomLinkState").textContent = r.stable ? "· bağlı" : r.on ? (r.tunnel === "on" ? "· geçici link (sabit adres bağlanamadı)" : "· tünel açılıyor…") : "· oda kapalı";
    $("#roomLinkCopy").dataset.url = r.url || "";
  }
  function bind() {
    if (!$("#roomOpenBtn")) return;
    $("#roomRelink").onclick = async () => { $("#roomLinkState").textContent = "· bağlanıyor…"; await slow("room_relink"); setTimeout(linkState, 2500); };
    $("#roomLinkCopy").onclick = async () => { await linkState(); const u = $("#roomLinkCopy").dataset.url; if (u) { navigator.clipboard?.writeText(u).catch(() => api.copy_text(u)); toast("Oda linki kopyalandı"); } else toast("Önce odayı aç", true); };
    $("#settingsBtn")?.addEventListener("click", () => setTimeout(linkState, 80));
    $("#roomOpenBtn").onclick = () => slow("room_open", true);
    const pwState = async () => { const st = await api.get_settings(); $("#roomPwState").textContent = st.room_password_hash ? "· açık" : "· yok"; };
    $("#settingsBtn")?.addEventListener("click", () => setTimeout(pwState, 80));
    $("#roomPwSave").onclick = async () => {
      const r = await api.room_set_password($("#roomPw").value);
      if (!r.ok) { toast("Şifre en az 4 karakter olmalı", true); return; }
      $("#roomPw").value = ""; pwState();
      toast(r.locked ? "Oda şifrelendi: davet edilenler girişte şifreyi yazacak" : "Oda şifresi kaldırıldı");
    };
    $("#roomJoinBtn").onclick = async () => {
      const r = await api.room_join($("#roomJoinUrl").value.trim());
      if (!r.ok) toast("Geçersiz oda bağlantısı", true);
    };
    $("#turnSave").onclick = async () => {
      const id = $("#turnId").value.trim(), tok = $("#turnTok").value.trim();
      if (!id || !tok) return;
      $("#turnSave").disabled = true;
      const r = await slow("room_turn_set", id, tok);
      $("#turnSave").disabled = false; $("#turnTok").value = "";
      toast(r.ok ? "TURN anahtarı doğrulandı ve kaydedildi" : r.error === "bad_format" ? "Anahtar biçimi hatalı" : "Cloudflare anahtarı kabul etmedi", !r.ok);
      if (r.ok) $("#turnId").value = "";
      turnState();
    };
    $("#turnClear").onclick = async () => { await api.room_turn_clear(); turnState(); };
    $("#settingsBtn")?.addEventListener("click", () => setTimeout(turnState, 80));
  }
  // ust bardaki Oda sekmesine canli kisi rozetini yaz (cift dugme olmasin)
  function syncRoomTab() {
    const tab = document.querySelector('#skTabs .sk-tab[data-mod="room"]');
    if (!tab) { setTimeout(syncRoomTab, 600); return; }
    setInterval(async () => {
      try {
        const r = await api.room_status();
        tab.classList.toggle("live", !!r.on);
        const badge = document.getElementById("skRoomN");
        if (badge) badge.textContent = r.people?.length ? String(r.people.length) : "";
        tab.title = r.people?.length ? "Odada: " + r.people.join(", ") : "Kami Oda: sesli oda, ekran paylaşımı, oynatıcı yayını";
      } catch { /* yok */ }
    }, 4000);
  }
  window.addEventListener("pywebviewready", () => { setTimeout(bind, 300); syncRoomTab(); });
  window.KPAL = window.KPAL || [];
  window.KPAL.push(() => [
    { ic: "🎙", t: "Kami Oda", sub: "sesli oda, ekran paylaşımı", run: () => slow("room_open", true) },
    { ic: "🔗", t: "Panodaki bağlantıyla odaya katıl", sub: "trycloudflare davet linki", run: async () => { const u = (await api.read_clipboard()) || ""; const r = await api.room_join(u.trim()); if (!r.ok) toast("Panoda oda bağlantısı yok", true); } },
  ]);
})();
