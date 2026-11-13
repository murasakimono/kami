// Faz 13.2 — 50.000+ oge icin gercek DOM havuzlu (node-recycling) yuksek hizli VirtualGrid
"use strict";
(() => {
  class KamiVirtualGrid {
    constructor(container, { itemHeight = 160, gap = 10, columns = 4, overscan = 2, renderItem } = {}) {
      this.root = container;
      this.itemHeight = itemHeight;
      this.gap = gap;
      this.rowStride = itemHeight + gap;
      this.columns = Math.max(1, columns);
      this.overscan = overscan;
      this.renderItem = renderItem || ((it, el) => {
        const node = el || document.createElement("div");
        node.textContent = it?.title || String(it || "");
        return node;
      });
      this.items = [];
      this.pool = [];
      this.spacer = document.createElement("div");
      this.spacer.style.position = "relative";
      this.spacer.style.width = "100%";
      this.viewport = document.createElement("div");
      this.viewport.style.position = "absolute";
      this.viewport.style.left = "0";
      this.viewport.style.right = "0";
      this.viewport.style.display = "grid";
      this.viewport.style.gap = `${this.gap}px`;
      this.spacer.appendChild(this.viewport);
      if (this.root) {
        this.root.style.overflowY = "auto";
        this.root.innerHTML = "";
        this.root.appendChild(this.spacer);
        this.root.addEventListener("scroll", () => this.render());
      }
    }

    setItems(items) {
      this.items = Array.isArray(items) ? items : [];
      const totalRows = Math.ceil(this.items.length / this.columns);
      this.spacer.style.height = `${Math.max(0, totalRows * this.rowStride - this.gap)}px`;
      this.viewport.style.gridTemplateColumns = `repeat(${this.columns}, minmax(0, 1fr))`;
      this.render();
    }

    render() {
      if (!this.root) return { startIdx: 0, endIdx: 0 };
      const scrollTop = this.root.scrollTop || 0;
      const viewH = this.root.clientHeight || 640;
      const startRow = Math.max(0, Math.floor(scrollTop / this.rowStride) - this.overscan);
      const visibleRows = Math.ceil(viewH / this.rowStride) + this.overscan * 2;
      const endRow = Math.min(Math.ceil(this.items.length / this.columns), startRow + visibleRows);
      const startIdx = startRow * this.columns;
      const endIdx = Math.min(this.items.length, endRow * this.columns);
      const needed = Math.max(0, endIdx - startIdx);

      this.viewport.style.top = `${startRow * this.rowStride}px`;
      while (this.pool.length < needed) {
        const slot = document.createElement("div");
        this.pool.push(slot);
        this.viewport.appendChild(slot);
      }
      for (let k = 0; k < this.pool.length; k++) {
        const node = this.pool[k];
        if (k < needed) {
          node.style.display = "";
          node.style.height = `${this.itemHeight}px`;
          const rendered = this.renderItem(this.items[startIdx + k], node);
          if (rendered && rendered !== node) {
            node.replaceChildren(rendered);
          }
        } else {
          node.style.display = "none";
        }
      }
      return { startIdx, endIdx };
    }
  }

  window.KamiVirtualGrid = KamiVirtualGrid;
})();
