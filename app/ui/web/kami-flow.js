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

  global.KamiFlowGraph = KamiFlowGraph;
})(window);
