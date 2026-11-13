// Kami Faz 18.2 — LiteGraph.js Uyumlu Gorsel Dugum Akis Zinciri Arayuzu
"use strict";

(function (global) {
  class KamiFlowGraph {
    constructor(canvas) {
      this.canvas = canvas;
      this.ctx = canvas.getContext("2d");
      this.nodes = [];
      this.links = [];
      this.nextNodeId = 1;
      this.nextLinkId = 1;
      this.dragNode = null;
      this.dragOff = { x: 0, y: 0 };
      this.connectingFrom = null;
      this.pointer = { x: 0, y: 0 };
      this._bind();
      this.draw();
    }

    addNode(type, title, x = 80, y = 80, inputs = [], outputs = [], properties = {}) {
      const node = {
        id: this.nextNodeId++,
        type,
        title: title || type,
        pos: [x, y],
        size: [190, Math.max(72, 38 + Math.max(inputs.length, outputs.length) * 22)],
        inputs: inputs.map((name) => ({ name })),
        outputs: outputs.map((name) => ({ name })),
        properties: { ...properties },
      };
      this.nodes.push(node);
      this.draw();
      return node;
    }

    connect(srcId, srcSlot, dstId, dstSlot) {
      const id = this.nextLinkId++;
      this.links = this.links.filter((l) => !(l[3] === dstId && l[4] === dstSlot));
      this.links.push([id, srcId, srcSlot, dstId, dstSlot, "any"]);
      this.draw();
      return id;
    }

    serialize() {
      return {
        version: 1,
        nodes: this.nodes.map((n) => ({ ...n })),
        links: this.links.map((l) => [...l]),
      };
    }

    configure(data) {
      this.nodes = Array.isArray(data?.nodes) ? data.nodes.map((n) => ({ ...n })) : [];
      this.links = Array.isArray(data?.links) ? data.links.map((l) => [...l]) : [];
      this.nextNodeId = this.nodes.reduce((m, n) => Math.max(m, (n.id || 0) + 1), 1);
      this.nextLinkId = this.links.reduce((m, l) => Math.max(m, (l[0] || 0) + 1), 1);
      this.draw();
    }

    _portPos(node, isOut, idx) {
      const [x, y] = node.pos;
      const [w] = node.size;
      return {
        x: isOut ? x + w : x,
        y: y + 36 + idx * 22,
      };
    }

    _hitPort(px, py) {
      for (const n of this.nodes) {
        for (let i = 0; i < n.outputs.length; i++) {
          const p = this._portPos(n, true, i);
          if (Math.hypot(px - p.x, py - p.y) <= 9) return { node: n, isOut: true, slot: i };
        }
        for (let i = 0; i < n.inputs.length; i++) {
          const p = this._portPos(n, false, i);
          if (Math.hypot(px - p.x, py - p.y) <= 9) return { node: n, isOut: false, slot: i };
        }
      }
      return null;
    }

    _bind() {
      const coords = (e) => {
        const r = this.canvas.getBoundingClientRect();
        return { x: e.clientX - r.left, y: e.clientY - r.top };
      };
      this.canvas.addEventListener("pointerdown", (e) => {
        const pt = coords(e);
        const hitP = this._hitPort(pt.x, pt.y);
        if (hitP && hitP.isOut) {
          this.connectingFrom = hitP;
          this.pointer = pt;
          return;
        }
        for (let i = this.nodes.length - 1; i >= 0; i--) {
          const n = this.nodes[i];
          if (pt.x >= n.pos[0] && pt.x <= n.pos[0] + n.size[0] && pt.y >= n.pos[1] && pt.y <= n.pos[1] + n.size[1]) {
            this.dragNode = n;
            this.dragOff = { x: pt.x - n.pos[0], y: pt.y - n.pos[1] };
            break;
          }
        }
      });
      this.canvas.addEventListener("pointermove", (e) => {
        const pt = coords(e);
        this.pointer = pt;
        if (this.dragNode) {
          this.dragNode.pos[0] = pt.x - this.dragOff.x;
          this.dragNode.pos[1] = pt.y - this.dragOff.y;
          this.draw();
        } else if (this.connectingFrom) {
          this.draw();
        }
      });
      this.canvas.addEventListener("pointerup", (e) => {
        const pt = coords(e);
        if (this.connectingFrom) {
          const hitP = this._hitPort(pt.x, pt.y);
          if (hitP && !hitP.isOut && hitP.node.id !== this.connectingFrom.node.id) {
            this.connect(this.connectingFrom.node.id, this.connectingFrom.slot, hitP.node.id, hitP.slot);
          }
          this.connectingFrom = null;
          this.draw();
        }
        this.dragNode = null;
      });
    }

    draw() {
      const ctx = this.ctx;
      const w = this.canvas.width;
      const h = this.canvas.height;
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = "#08070C";
      ctx.fillRect(0, 0, w, h);

      // Izgara
      ctx.strokeStyle = "rgba(74, 61, 99, 0.25)";
      ctx.lineWidth = 1;
      for (let x = 0; x < w; x += 24) {
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
      }
      for (let y = 0; y < h; y += 24) {
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
      }

      // Baglantilar
      for (const l of this.links) {
        const src = this.nodes.find((n) => n.id === l[1]);
        const dst = this.nodes.find((n) => n.id === l[3]);
        if (!src || !dst) continue;
        const p1 = this._portPos(src, true, l[2]);
        const p2 = this._portPos(dst, false, l[4]);
        ctx.strokeStyle = "#2EE6A6";
        ctx.lineWidth = 2.2;
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.bezierCurveTo(p1.x + 60, p1.y, p2.x - 60, p2.y, p2.x, p2.y);
        ctx.stroke();
      }

      if (this.connectingFrom) {
        const p1 = this._portPos(this.connectingFrom.node, true, this.connectingFrom.slot);
        ctx.strokeStyle = "#C4B5FD";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(this.pointer.x, this.pointer.y);
        ctx.stroke();
      }

      // Dugumler (keskin kose, Kami Sunak paleti)
      for (const n of this.nodes) {
        const [x, y] = n.pos;
        const [nw, nh] = n.size;
        ctx.fillStyle = "#110E17";
        ctx.fillRect(x, y, nw, nh);
        ctx.fillStyle = "#2A1650";
        ctx.fillRect(x, y, nw, 24);
        ctx.strokeStyle = "#6D28D9";
        ctx.lineWidth = 1.4;
        ctx.strokeRect(x, y, nw, nh);

        ctx.fillStyle = "#EDE9F6";
        ctx.font = "600 12px 'Chakra Petch', sans-serif";
        ctx.fillText(n.title, x + 8, y + 16);

        ctx.font = "500 11px 'Chakra Petch', sans-serif";
        n.inputs.forEach((inp, idx) => {
          const p = this._portPos(n, false, idx);
          ctx.fillStyle = "#8B5CF6";
          ctx.beginPath(); ctx.arc(p.x, p.y, 5, 0, Math.PI * 2); ctx.fill();
          ctx.fillStyle = "#A39BB5";
          ctx.fillText(inp.name, p.x + 9, p.y + 4);
        });
        n.outputs.forEach((out, idx) => {
          const p = this._portPos(n, true, idx);
          ctx.fillStyle = "#2EE6A6";
          ctx.beginPath(); ctx.arc(p.x, p.y, 5, 0, Math.PI * 2); ctx.fill();
          ctx.fillStyle = "#C4B5FD";
          const tw = ctx.measureText(out.name).width;
          ctx.fillText(out.name, p.x - tw - 9, p.y + 4);
        });
      }
    }
  }

  const KamiFlowUI = {
    overlay: null,
    graph: null,
    open() {
      if (this.overlay) {
        this.overlay.hidden = false;
        this.refreshStatus();
        return;
      }
      const ov = document.createElement("div");
      ov.id = "kamiFlowModal";
      ov.style.cssText =
        "position:fixed;inset:24px;z-index:9995;background:#0D0A13;border:1px solid #6D28D9;display:flex;flex-direction:column;color:#EDE9F6;font-family:'Chakra Petch',sans-serif;box-shadow:0 24px 80px rgba(0,0,0,.75);";
      ov.innerHTML = `
        <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;background:#16101F;border-bottom:1px solid #3A2E52;">
          <strong style="color:#C4B5FD;letter-spacing:.5px;">KAMI AKIŞ & YEREL COPILOT</strong>
          <button id="kfTabFlow" class="btn primary">Akış & Copilot</button>
          <button id="kfTabTools" class="btn">Araçlar (Faz 14–16)</button>
          <span id="kfCopilotBadge" style="font-size:12px;color:#A39BB5;">Ollama kontrol ediliyor…</span>
          <div style="flex:1"></div>
          <button id="kfAddIn" class="btn">+ Dosya</button>
          <button id="kfAddReframe" class="btn">+ 9:16</button>
          <button id="kfAddOut" class="btn">+ Çıktı</button>
          <button id="kfSave" class="btn">Kaydet</button>
          <button id="kfRun" class="btn primary">Çalıştır</button>
          <button id="kfClose" class="btn">Kapat</button>
        </div>
        <div id="kfFlowPane" style="display:flex;flex-direction:column;flex:1;min-height:0;">
          <div style="display:flex;gap:8px;padding:8px 14px;background:#110E17;border-bottom:1px solid #2A1F3B;">
            <input id="kfPrompt" type="text" placeholder="Yerel Qwen2.5 Copilot'a Studio komutu yaz…" style="flex:1;background:#08070C;color:#EDE9F6;border:1px solid #4A3D63;padding:6px 10px;font:inherit;">
            <button id="kfAsk" class="btn">Copilot</button>
          </div>
          <canvas id="kfCanvas" width="960" height="460" style="flex:1;width:100%;height:100%;display:block;"></canvas>
        </div>
        <div id="kfToolsPane" hidden style="flex:1;overflow:auto;padding:14px;display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;background:#0B0910;">
          <div style="border:1px solid #3A2E52;padding:10px;background:#110E17;display:grid;gap:6px;">
            <strong style="color:#C4B5FD;">Faz 14 — Klip & Oyun Vurgu</strong>
            <input id="ktClipSrc" type="text" placeholder="Video yolu" style="background:#08070C;color:#EDE9F6;border:1px solid #4A3D63;padding:5px 8px;font:inherit;">
            <div style="display:flex;gap:6px;flex-wrap:wrap;">
              <button id="ktReframe" class="btn">9:16 Dikey</button>
              <button id="ktUgc" class="btn">UGC Matris</button>
              <button id="ktHlStart" class="btn">Vurgu Başlat</button>
              <button id="ktHlStop" class="btn">Durdur</button>
              <button id="ktVcam" class="btn">Sanal Cam</button>
            </div>
          </div>
          <div style="border:1px solid #3A2E52;padding:10px;background:#110E17;display:grid;gap:6px;">
            <strong style="color:#C4B5FD;">Faz 15 — Belge & Manga Çeviri</strong>
            <input id="ktDocSrc" type="text" placeholder="PDF / Belge / Manga görsel yolu" style="background:#08070C;color:#EDE9F6;border:1px solid #4A3D63;padding:5px 8px;font:inherit;">
            <div style="display:flex;gap:6px;flex-wrap:wrap;">
              <button id="ktPdfMd" class="btn">PDF → MD</button>
              <button id="ktDocConv" class="btn">HTML Çevir</button>
              <button id="ktManga" class="btn">Manga Çevir</button>
            </div>
          </div>
          <div style="border:1px solid #3A2E52;padding:10px;background:#110E17;display:grid;gap:6px;">
            <strong style="color:#C4B5FD;">Faz 16 — Köprü, LAN & Ses</strong>
            <input id="ktSharePath" type="text" placeholder="LAN paylaşım dosyası veya ses komutu" style="background:#08070C;color:#EDE9F6;border:1px solid #4A3D63;padding:5px 8px;font:inherit;">
            <div style="display:flex;gap:6px;flex-wrap:wrap;">
              <button id="ktBridgeSt" class="btn">Köprü Durumu</button>
              <button id="ktScrcpy" class="btn">Android</button>
              <button id="ktUxplay" class="btn">AirPlay</button>
              <button id="ktLanShare" class="btn">LAN Paylaş</button>
              <button id="ktVoiceSt" class="btn">Ses Durum</button>
              <button id="ktVoiceCmd" class="btn">Komut Test</button>
            </div>
          </div>
        </div>
        <div id="kfLog" style="height:82px;overflow:auto;padding:8px 14px;background:#08070C;border-top:1px solid #2A1F3B;font-size:12px;color:#2EE6A6;white-space:pre-wrap;"></div>
      `;
      document.body.appendChild(ov);
      this.overlay = ov;

      const cv = ov.querySelector("#kfCanvas");
      this.graph = new KamiFlowGraph(cv);
      const n1 = this.graph.addNode("input/file", "Kaynak Dosya", 40, 80, [], ["path"], { path: "" });
      const n2 = this.graph.addNode("output/export", "Dışa Aktar", 360, 80, ["in"], ["result"], { quality: "high" });
      this.graph.connect(n1.id, 0, n2.id, 0);

      const log = (txt) => {
        ov.querySelector("#kfLog").textContent = typeof txt === "string" ? txt : JSON.stringify(txt, null, 2);
      };
      const flowPane = ov.querySelector("#kfFlowPane");
      const toolsPane = ov.querySelector("#kfToolsPane");
      ov.querySelector("#kfTabFlow").onclick = () => { flowPane.hidden = false; toolsPane.hidden = true; };
      ov.querySelector("#kfTabTools").onclick = () => { flowPane.hidden = true; toolsPane.hidden = false; };
      ov.querySelector("#kfClose").onclick = () => { ov.hidden = true; };
      ov.querySelector("#kfAddIn").onclick = () => this.graph.addNode("input/file", "Kaynak Dosya", 60, 140, [], ["path"], { path: "" });
      ov.querySelector("#kfAddReframe").onclick = () => this.graph.addNode("clip/vertical_reframe", "9:16 Dikey Kırp", 260, 140, ["path"], ["path"], { platform: "tiktok" });
      ov.querySelector("#kfAddOut").onclick = () => this.graph.addNode("output/export", "Dışa Aktar", 480, 140, ["in"], ["result"], { quality: "high" });
      ov.querySelector("#kfRun").onclick = async () => {
        if (!global.api?.flow_execute) return log("API hazır değil");
        log("Akış çalıştırılıyor…");
        log(await global.api.flow_execute(this.graph.serialize()));
      };
      ov.querySelector("#kfSave").onclick = async () => {
        if (!global.api?.flow_save) return log("API hazır değil");
        log(await global.api.flow_save("varsayilan_akis", this.graph.serialize()));
      };
      ov.querySelector("#kfAsk").onclick = async () => {
        const p = ov.querySelector("#kfPrompt").value.trim();
        if (!p || !global.api?.copilot_run) return;
        log("Yerel Copilot düşünüyor…");
        log(await global.api.copilot_run(p));
      };
      const callApi = async (fn, ...args) => {
        if (!global.api?.[fn]) return log(`API yok: ${fn}`);
        log(await global.api[fn](...args));
      };
      ov.querySelector("#ktReframe").onclick = () => { const p = ov.querySelector("#ktClipSrc").value.trim(); if (p) callApi("clip_vertical_reframe", p, p.replace(/\.[^.]+$/, "_9x16.mp4")); };
      ov.querySelector("#ktUgc").onclick = () => { const p = ov.querySelector("#ktClipSrc").value.trim(); if (p) callApi("clip_ugc_matrix", [p], p, [p], p.replace(/[^\\/]+$/, "ugc_out")); };
      ov.querySelector("#ktHlStart").onclick = () => callApi("highlight_watcher_start");
      ov.querySelector("#ktHlStop").onclick = () => callApi("highlight_watcher_stop");
      ov.querySelector("#ktVcam").onclick = () => callApi("vcam_status");
      ov.querySelector("#ktPdfMd").onclick = () => { const p = ov.querySelector("#ktDocSrc").value.trim(); if (p) callApi("doc_pdf_to_markdown", p); };
      ov.querySelector("#ktDocConv").onclick = () => { const p = ov.querySelector("#ktDocSrc").value.trim(); if (p) callApi("doc_convert", p, "html"); };
      ov.querySelector("#ktManga").onclick = () => { const p = ov.querySelector("#ktDocSrc").value.trim(); if (p) callApi("manga_translate_page", p); };
      ov.querySelector("#ktBridgeSt").onclick = () => callApi("screen_bridge_status");
      ov.querySelector("#ktScrcpy").onclick = () => callApi("scrcpy_start");
      ov.querySelector("#ktUxplay").onclick = () => callApi("uxplay_start");
      ov.querySelector("#ktLanShare").onclick = () => { const p = ov.querySelector("#ktSharePath").value.trim(); if (p) callApi("lan_share_file", p); };
      ov.querySelector("#ktVoiceSt").onclick = () => callApi("voice_status");
      ov.querySelector("#ktVoiceCmd").onclick = () => callApi("voice_parse_command", ov.querySelector("#ktSharePath").value.trim() || "Hey Kami klip al");
      this.refreshStatus();
    },
    async refreshStatus() {
      const badge = this.overlay?.querySelector("#kfCopilotBadge");
      if (!badge || !global.api?.copilot_status) return;
      try {
        const st = await global.api.copilot_status();
        badge.textContent = st.ollama_running
          ? (st.qwen_ready ? "Ollama + Qwen2.5 hazır" : `Ollama açık (${st.models.length} model)`)
          : "Ollama çevrimdışı";
        badge.style.color = st.ollama_running ? "#2EE6A6" : "#F5B94A";
      } catch {
        badge.textContent = "Durum alınamadı";
      }
    },
  };

  function mountDockButton() {
    const dock = document.getElementById("skDock");
    if (!dock || document.getElementById("kfDockBtn")) return;
    const btn = document.createElement("button");
    btn.id = "kfDockBtn";
    btn.title = "Akış Zinciri & Yerel Copilot (Ctrl+Shift+F)";
    btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="6" height="6"/><rect x="15" y="14" width="6" height="6"/><path d="M9 7h4v10h2"/></svg>';
    btn.onclick = () => KamiFlowUI.open();
    dock.appendChild(btn);
  }

  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === "f") {
      e.preventDefault();
      KamiFlowUI.open();
    }
  });
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => setTimeout(mountDockButton, 300));
  } else {
    setTimeout(mountDockButton, 300);
  }

  global.KamiFlowGraph = KamiFlowGraph;
  global.KamiFlowUI = KamiFlowUI;
})(window);
