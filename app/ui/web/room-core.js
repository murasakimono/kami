// Kami Oda cekirdegi: sinyal (uzun yoklama), WebRTC mesh, yerel izler, kalite istekleri.
// Hem oda sayfasi (room.js) hem Kami Player (yayinci) kullanir.
"use strict";
(function () {
  const QUALITY = {   // izleyicinin istedigi kalite -> yayincinin gonderim ayari
    src: { h: 0, fps: 60, br: 14_000_000 },
    "1080": { h: 1080, fps: 60, br: 8_000_000 },
    "1080_30": { h: 1080, fps: 30, br: 5_000_000 },
    "720": { h: 720, fps: 30, br: 3_000_000 },
    "480": { h: 480, fps: 30, br: 1_200_000 },
  };
  const rid = () => Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);

  function mungeOpus(sdp) {   // stereo, yuksek bit hizi, kayip duzeltme; DTX kapali (kayipsiza yakin ses)
    const m = sdp.match(/a=rtpmap:(\d+) opus\/48000\/2/i);
    if (!m) return sdp;
    const pt = m[1], extra = "stereo=1;sprop-stereo=1;maxaveragebitrate=256000;maxplaybackrate=48000;useinbandfec=1;usedtx=0;cbr=0";
    const re = new RegExp(`a=fmtp:${pt} ([^\\r\\n]*)`);
    if (re.test(sdp)) return sdp.replace(re, (all, p) => `a=fmtp:${pt} ${p.split(";").filter((x) => !/^(stereo|sprop-stereo|maxaveragebitrate|maxplaybackrate|useinbandfec|usedtx|cbr)=/.test(x)).concat(extra.split(";")).join(";")}`);
    return sdp.replace(m[0], `${m[0]}\r\na=fmtp:${pt} ${extra}`);
  }

  class KamiRoom {
    constructor(o) {
      this.base = o.base.endsWith("/") ? o.base : o.base + "/";
      this.name = o.name || "Misafir";
      this.kind = o.kind || "user";               // user | stream
      this.id = o.id || rid();
      this.on = o.on || {};                       // roster, events, track, trackgone, peerstate, quality, error
      this.peers = new Map();                     // id -> {pc, polite, making, ignore, meta:{streamId:kind}, q}
      this.local = new Map();                     // streamId -> {kind, stream}
      this.roster = []; this.n = 0; this.rv = ""; this.alive = false; this.ice = [];
      this.myQ = o.quality || "src";              // aldigim yayinlar icin istedigim kalite
    }
    url(p) { return this.base + p; }
    async post(p, body) {
      try { const r = await fetch(this.url(p), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: this.id, ...body }) }); return r.ok ? r.json() : null; } catch { return null; }
    }
    async join() {
      try { this.ice = (await (await fetch(this.url("ice"), { cache: "no-store" })).json()).iceServers || []; } catch { this.ice = []; }
      this.alive = true;
      this._loop();
      this._beat = setInterval(() => this.post("me", {}), 15000);
      window.addEventListener("pagehide", () => this.leave());
    }
    async leave() {
      if (!this.alive) return;
      this.alive = false; clearInterval(this._beat);
      for (const id of [...this.peers.keys()]) this._drop(id);
      navigator.sendBeacon?.(this.url("leave"), new Blob([JSON.stringify({ id: this.id })], { type: "application/json" })) || this.post("leave", {});
    }
    setMe(st) { this.post("me", st); }
    chat(text) { this.post("chat", { text }); }

    async _loop() {
      let fails = 0;
      while (this.alive) {
        try {
          const q = `poll?id=${this.id}&name=${encodeURIComponent(this.name)}&kind=${this.kind}&n=${this.n}&rv=${this.rv}`;
          const r = await (await fetch(this.url(q), { cache: "no-store" })).json();
          fails = 0;
          if (r.rv !== this.rv) { this.rv = r.rv; this.roster = r.roster; this._sync(); this.on.roster?.(r.roster, r.host); }
          if (r.events?.length) { this.n = Math.max(this.n, ...r.events.map((e) => e.n)); this.on.events?.(r.events); }
          for (const s of r.signals || []) await this._signal(s.from, s.data);
        } catch (e) {
          if (++fails > 3) this.on.error?.("offline");
          await new Promise((ok) => setTimeout(ok, Math.min(5000, 600 * fails)));
        }
      }
    }
    // kiminle baglanmali: yayinci yalnizca kullanicilara; kullanici herkese
    _wants(p) { return p.id !== this.id && !(this.kind === "stream" && p.kind === "stream"); }
    _sync() {
      const ids = new Set(this.roster.filter((p) => this._wants(p)).map((p) => p.id));
      for (const id of ids) if (!this.peers.has(id)) this._peer(id);
      for (const id of [...this.peers.keys()]) if (!ids.has(id)) this._drop(id);
    }
    _peer(id) {
      const pc = new RTCPeerConnection({ iceServers: this.ice, bundlePolicy: "max-bundle" });
      const P = { pc, polite: this.id > id, making: false, ignore: false, meta: {}, q: "src", senders: new Map() };
      this.peers.set(id, P);
      pc.onicecandidate = (e) => e.candidate && this.post("sig", { to: id, data: { t: "ice", c: e.candidate } });
      pc.onnegotiationneeded = async () => {
        try {
          P.making = true;
          const offer = await pc.createOffer();
          if (pc.signalingState !== "stable") return;
          offer.sdp = mungeOpus(offer.sdp);
          await pc.setLocalDescription(offer);
          this.post("sig", { to: id, data: { t: "sdp", d: pc.localDescription, meta: this._meta() } });
        } catch (e) { console.warn("teklif", e); } finally { P.making = false; }
      };
      pc.ontrack = (e) => {
        const st = e.streams[0] || new MediaStream([e.track]);
        const kind = P.meta[st.id] || (e.track.kind === "audio" ? "mic" : "screen");
        this.on.track?.(id, st, kind, e.track);
        e.track.addEventListener("ended", () => this.on.trackgone?.(id, st, e.track));
        st.addEventListener("removetrack", () => { if (!st.getTracks().length) this.on.trackgone?.(id, st); });
      };
      pc.onconnectionstatechange = () => {
        this.on.peerstate?.(id, pc.connectionState);
        if (pc.connectionState === "failed") pc.restartIce?.();
      };
      for (const [sid, L] of this.local) this._addTo(P, sid, L);
      return P;
    }
    _drop(id) {
      const P = this.peers.get(id); if (!P) return;
      try { P.pc.close(); } catch { /* kapali */ }
      this.peers.delete(id);
      this.on.peergone?.(id);
    }
    _meta() { const m = {}; for (const [sid, L] of this.local) m[sid] = L.kind; return m; }
    async _signal(from, d) {
      let P = this.peers.get(from);
      if (!P) { if (!this.roster.find((p) => p.id === from)) return; P = this._peer(from); }
      const pc = P.pc;
      try {
        if (d.meta) Object.assign(P.meta, d.meta);
        if (d.t === "sdp") {
          const offer = d.d.type === "offer";
          const collision = offer && (P.making || pc.signalingState !== "stable");
          P.ignore = !P.polite && collision;
          if (P.ignore) return;
          await pc.setRemoteDescription(d.d);
          if (offer) {
            const ans = await pc.createAnswer();
            ans.sdp = mungeOpus(ans.sdp);
            await pc.setLocalDescription(ans);
            this.post("sig", { to: from, data: { t: "sdp", d: pc.localDescription, meta: this._meta() } });
          }
          if (P.wantQ) { this.post("sig", { to: from, data: { t: "q", q: P.wantQ } }); }
        } else if (d.t === "ice") {
          try { await pc.addIceCandidate(d.c); } catch (e) { if (!P.ignore) console.warn("ice", e); }
        } else if (d.t === "q") {
          P.q = d.q; this._applyQ(P); this.on.quality?.(from, d.q);
        } else if (d.t === "meta") {
          Object.assign(P.meta, d.meta);
        } else if (d.t === "app") {
          this.on.msg?.(from, d.m);
        }
      } catch (e) { console.warn("sinyal", e); }
    }
    // ---- yerel izler
    addLocal(kind, stream) {
      const sid = stream.id;
      this.local.set(sid, { kind, stream });
      for (const [id, P] of this.peers) { this.post("sig", { to: id, data: { t: "meta", meta: { [sid]: kind } } }); this._addTo(P, sid, this.local.get(sid)); }
      return sid;
    }
    removeLocal(sid) {
      const L = this.local.get(sid); if (!L) return;
      this.local.delete(sid);
      for (const P of this.peers.values()) {
        for (const [tr, snd] of P.senders) if (L.stream.getTracks().includes(tr)) { try { P.pc.removeTrack(snd); } catch { /* yok */ } P.senders.delete(tr); }
      }
    }
    replaceTrack(sid, oldT, newT) {   // video ogesinin kaynagi degisince (Player'da ileri sarma) izi yenile
      for (const P of this.peers.values()) {
        const snd = P.senders.get(oldT);
        if (snd) { snd.replaceTrack(newT); P.senders.delete(oldT); P.senders.set(newT, snd); this._applyQ(P); }
      }
    }
    _addTo(P, sid, L) {
      for (const tr of L.stream.getTracks()) {
        if (P.senders.has(tr)) continue;
        const snd = P.pc.addTrack(tr, L.stream);
        P.senders.set(tr, snd);
        if (tr.kind === "video") {
          try {   // donanim kodlamasi ve iPhone uyumu icin once H.264
            const tc = P.pc.getTransceivers().find((t) => t.sender === snd);
            const caps = RTCRtpSender.getCapabilities?.("video")?.codecs || [];
            const pref = [...caps.filter((c) => /h264/i.test(c.mimeType)), ...caps.filter((c) => !/h264/i.test(c.mimeType))];
            if (tc && pref.length) tc.setCodecPreferences(pref);
          } catch { /* desteklenmiyor */ }
          tr.contentHint = L.kind === "player" || L.kind === "cam" ? "motion" : "detail";
        }
        this._applyQ(P);
      }
    }
    async _applyQ(P) {
      for (const [tr, snd] of P.senders) {
        try {
          const p = snd.getParameters();
          if (!p.encodings || !p.encodings.length) p.encodings = [{}];
          if (tr.kind === "audio") { p.encodings[0].maxBitrate = 256000; p.encodings[0].priority = "high"; p.encodings[0].networkPriority = "high"; }
          else {
            const Q = QUALITY[P.q] || QUALITY.src, h = tr.getSettings?.().height || 1080;
            p.encodings[0].scaleResolutionDownBy = Q.h && h > Q.h ? h / Q.h : 1;
            p.encodings[0].maxFramerate = Q.fps;
            p.encodings[0].maxBitrate = Q.br;
            p.degradationPreference = "maintain-framerate";
          }
          await snd.setParameters(p);
        } catch { /* ilk muzakereden once olabilir */ }
      }
    }
    // uygulama mesaji (oynatici durumu, kontrol komutlari)
    send(to, m) { this.post("sig", { to, data: { t: "app", m } }); }
    broadcast(m) { for (const id of this.peers.keys()) this.send(id, m); }
    // izleyici: belli bir yayincidan (ya da hepsinden) istedigim kalite
    requestQuality(q, to) {
      this.myQ = q;
      for (const [id, P] of this.peers) if (!to || id === to) { P.wantQ = q; this.post("sig", { to: id, data: { t: "q", q } }); }
    }
    async stats(id) {   // baglanti bilgisi: rtt, kayip, gelen cozunurluk
      const P = this.peers.get(id); if (!P) return null;
      const out = { rtt: 0, loss: 0, w: 0, h: 0, fps: 0, relay: false };
      (await P.pc.getStats()).forEach((s) => {
        if (s.type === "candidate-pair" && s.nominated) out.rtt = Math.round((s.currentRoundTripTime || 0) * 1000);
        if (s.type === "inbound-rtp" && s.kind === "video") { out.w = s.frameWidth || 0; out.h = s.frameHeight || 0; out.fps = Math.round(s.framesPerSecond || 0); out.loss = s.packetsLost || 0; }
        if (s.type === "local-candidate" && s.candidateType === "relay") out.relay = true;
      });
      return out;
    }
  }
  window.KamiRoom = KamiRoom;
  window.KamiRoomQuality = QUALITY;
})();
