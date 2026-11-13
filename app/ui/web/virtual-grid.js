// Faz 13.2 — 50.000+ oge icin DOM geri donusumlu yuksek hizli VirtualGrid
"use strict";
(() => {
  class KamiVirtualGrid {
    constructor(container, { itemHeight = 160, columns = 4, overscan = 2, renderItem } = {}) {
      this.root = container;
      this.itemHeight = itemHeight;
      this.columns = Math.max(1, columns);
      this.overscan = overscan;
      this.renderItem = renderItem || ((it) => {
        const el = document.createElement("div");
        el.textContent = it?.title || String(it || "");
        return el;
      });
      this.items = [];
      this.spacer = document.createElement("div");
      this.spacer.style.position = "relative";
      this.spacer.style.width = "100%";
      this.viewport = document.createElement("div");
      this.viewport.style.position = "absolute";
      this.viewport.style.left = "0";
      this.viewport.style.right = "0";
      this.viewport.style.display = "grid";
      this.viewport.style.gap = "10px";
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
      this.spacer.style.height = `${totalRows * this.itemHeight}px`;
      this.viewport.style.gridTemplateColumns = `repeat(${this.columns}, minmax(0, 1fr))`;
      this.render();
    }

    render() {
      if (!this.root) return { startIdx: 0, endIdx: 0 };
      const scrollTop = this.root.scrollTop || 0;
      const viewH = this.root.clientHeight || 640;
      const startRow = Math.max(0, Math.floor(scrollTop / this.itemHeight) - this.overscan);
      const visibleRows = Math.ceil(viewH / this.itemHeight) + this.overscan * 2;
      const endRow = Math.min(Math.ceil(this.items.length / this.columns), startRow + visibleRows);
      const startIdx = startRow * this.columns;
      const endIdx = Math.min(this.items.length, endRow * this.columns);

      this.viewport.style.top = `${startRow * this.itemHeight}px`;
      const frag = document.createDocumentFragment();
      for (let i = startIdx; i < endIdx; i++) {
        frag.appendChild(this.renderItem(this.items[i], i));
      }
      this.viewport.replaceChildren(frag);
      return { startIdx, endIdx };
    }
  }

  window.KamiVirtualGrid = KamiVirtualGrid;
})();
