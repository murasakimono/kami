"""Faz 18.2 — LiteGraph.js Uyumlu Gorsel Dugum Akis Zinciri Motoru."""
from __future__ import annotations

import json
import re
from collections import deque
from pathlib import Path
from typing import Any, Callable

from app import paths

FLOWS_DIR = paths.DATA_DIR / "flows"

NODE_CATALOG: dict[str, dict[str, Any]] = {
    "input/file": {
        "title": "Kaynak Dosya",
        "inputs": [],
        "outputs": ["path"],
        "defaults": {"path": ""},
    },
    "studio/cut_silences": {
        "title": "Sessizligi Kes",
        "inputs": ["path"],
        "outputs": ["clip"],
        "defaults": {"db": -35, "min_len": 0.45},
    },
    "studio/auto_captions": {
        "title": "Oto Altyazi",
        "inputs": ["clip"],
        "outputs": ["clip"],
        "defaults": {"lang": "auto"},
    },
    "clip/vertical_reframe": {
        "title": "9:16 Dikey Kirp",
        "inputs": ["path"],
        "outputs": ["path"],
        "defaults": {"platform": "tiktok"},
    },
    "doc/pdf_to_markdown": {
        "title": "PDF -> Markdown",
        "inputs": ["path"],
        "outputs": ["markdown"],
        "defaults": {},
    },
    "output/export": {
        "title": "Disa Aktar",
        "inputs": ["in"],
        "outputs": ["result"],
        "defaults": {"quality": "high"},
    },
}


def validate_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """Dugum grafini topolojik siralar; dongu veya bilinmeyen dugum varsa hata doner."""
    nodes = graph.get("nodes") or []
    links = graph.get("links") or []
    by_id: dict[int, dict[str, Any]] = {}
    for n in nodes:
        nid = int(n["id"])
        ntype = str(n.get("type") or "")
        if ntype not in NODE_CATALOG:
            return {"ok": False, "error": f"Bilinmeyen dugum tipi: {ntype}"}
        by_id[nid] = n

    adj: dict[int, list[int]] = {nid: [] for nid in by_id}
    indeg: dict[int, int] = {nid: 0 for nid in by_id}
    for lk in links:
        # LiteGraph link formati: [id, origin_id, origin_slot, target_id, target_slot, type]
        if len(lk) < 5:
            continue
        src = int(lk[1])
        dst = int(lk[3])
        if src not in by_id or dst not in by_id:
            return {"ok": False, "error": f"Gecersiz baglanti: {src} -> {dst}"}
        adj[src].append(dst)
        indeg[dst] += 1

    q = deque([nid for nid, deg in indeg.items() if deg == 0])
    order: list[int] = []
    while q:
        cur = q.popleft()
        order.append(cur)
        for nxt in adj[cur]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                q.append(nxt)

    if len(order) != len(by_id):
        return {"ok": False, "error": "Akis grafi dongu (cycle) iceriyor"}

    return {"ok": True, "order": order, "nodes": by_id}


def _default_node_runner(node: dict[str, Any], inputs: dict[int, Any]) -> dict[str, Any]:
    ntype = str(node.get("type") or "")
    props = node.get("properties") or {}
    first_in = inputs.get(0)

    if ntype == "input/file":
        return {"ok": True, "outputs": {0: props.get("path", "")}}
    if ntype == "studio/cut_silences":
        from app.core import studio_mcp
        clip_id = str(first_in or props.get("clip", ""))
        if not clip_id:
            return {"ok": False, "error": "Klip ID eksik"}
        res = studio_mcp.t_sil(clip=clip_id, db=float(props.get("db", -35)), min_len=float(props.get("min_len", 0.45)))
        return {"ok": True, "outputs": {0: clip_id}, "detail": res}
    if ntype == "studio/auto_captions":
        from app.core import studio_mcp
        clip_id = str(first_in or props.get("clip", ""))
        if not clip_id:
            return {"ok": False, "error": "Klip ID eksik"}
        res = studio_mcp.t_caps(clip=clip_id, lang=str(props.get("lang", "auto")))
        return {"ok": True, "outputs": {0: clip_id}, "detail": res}
    if ntype == "doc/pdf_to_markdown":
        from app.core.doc_studio import pdf_to_markdown
        res = pdf_to_markdown(first_in or props.get("path", ""))
        return {"ok": bool(res.get("ok")), "outputs": {0: res.get("markdown", "")}, "detail": res}
    if ntype == "clip/vertical_reframe":
        from app.core.clip_factory import vertical_reframe
        src = str(first_in or props.get("path", ""))
        out = str(Path(src).with_name(f"{Path(src).stem}_9x16.mp4")) if src else ""
        res = vertical_reframe(src, out, platform=props.get("platform", "tiktok")) if src else {"ok": False, "error": "Kaynak yok"}
        return {"ok": bool(res.get("ok")), "outputs": {0: res.get("path", out)}, "detail": res}
    if ntype == "output/export":
        return {"ok": True, "outputs": {0: first_in}, "quality": props.get("quality", "high")}
    return {"ok": True, "outputs": {0: first_in}, "props": props}


def execute_graph(
    graph: dict[str, Any],
    *,
    runner: Callable[[dict[str, Any], dict[int, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Akis grafini topolojik sirada calistirir."""
    v = validate_graph(graph)
    if not v.get("ok"):
        return v

    by_id: dict[int, dict[str, Any]] = v["nodes"]
    links = graph.get("links") or []
    incoming: dict[int, list[tuple[int, int, int]]] = {nid: [] for nid in by_id}
    for lk in links:
        if len(lk) >= 5:
            incoming[int(lk[3])].append((int(lk[1]), int(lk[2]), int(lk[4])))

    exec_fn = runner or _default_node_runner
    node_outputs: dict[int, dict[int, Any]] = {}
    results: list[dict[str, Any]] = []

    for nid in v["order"]:
        node = by_id[nid]
        in_vals: dict[int, Any] = {}
        for src_id, src_slot, dst_slot in incoming[nid]:
            in_vals[dst_slot] = node_outputs.get(src_id, {}).get(src_slot)
        res = exec_fn(node, in_vals)
        node_outputs[nid] = res.get("outputs") or {}
        results.append({"id": nid, "type": node.get("type"), "ok": bool(res.get("ok", True)), "result": res})
        if not res.get("ok", True):
            return {"ok": False, "error": f"Dugum #{nid} basarisiz", "steps": results}

    return {"ok": True, "order": v["order"], "steps": results}


def _safe_flow_name(name: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9._-]+", "_", (name or "akis").strip()).strip("._")
    return clean or "akis"


def save_flow(name: str, graph: dict[str, Any]) -> dict[str, Any]:
    v = validate_graph(graph)
    if not v.get("ok"):
        return v
    FLOWS_DIR.mkdir(parents=True, exist_ok=True)
    p = FLOWS_DIR / f"{_safe_flow_name(name)}.json"
    p.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "path": str(p), "name": p.stem}


def load_flow(name: str) -> dict[str, Any]:
    p = FLOWS_DIR / f"{_safe_flow_name(name)}.json"
    if not p.is_file():
        return {"ok": False, "error": "Akis bulunamadi"}
    return {"ok": True, "name": p.stem, "graph": json.loads(p.read_text(encoding="utf-8"))}


def list_flows() -> list[str]:
    if not FLOWS_DIR.is_dir():
        return []
    return sorted(p.stem for p in FLOWS_DIR.glob("*.json"))
