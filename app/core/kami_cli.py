"""Faz 18.4 — kami-cli Bassiz SDK & Komut Satiri Araci."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def sdk_status() -> dict[str, Any]:
    """Kami yerel copilot, akis ve Studio MCP yetenek ozetini doner."""
    from app.core.flow_chain import NODE_CATALOG, list_flows
    from app.core.local_copilot import copilot_status, list_studio_tools

    return {
        "ok": True,
        "copilot": copilot_status(timeout=1.0),
        "mcp_tool_count": len(list_studio_tools()),
        "node_types": sorted(NODE_CATALOG.keys()),
        "saved_flows": list_flows(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kami-cli", description="Kami bassiz SDK & otomasyon araci")
    parser.add_argument("--json", action="store_true", help="Ciktilari JSON olarak yazdir")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Copilot, MCP ve akis durumunu goster")
    sub.add_parser("mcp-tools", help="Kullanilabilir Studio MCP araclarini listele")

    p_cop = sub.add_parser("copilot", help="Yerel Ollama Qwen2.5 Copilot calistir")
    p_cop.add_argument("prompt", help="Dogal dil komutu")
    p_cop.add_argument("--model", default="qwen2.5:7b")
    p_cop.add_argument("--dry-run", action="store_true")

    p_flow = sub.add_parser("flow", help="Dugum akis zincirlerini yonet")
    p_flow.add_argument("action", choices=["list", "run"])
    p_flow.add_argument("target", nargs="?", default="", help="Akis JSON dosyasi veya kayitli ad")

    p_pack = sub.add_parser("pack", help=".kamipack paketlerini disa/ice aktar")
    p_pack.add_argument("action", choices=["inspect", "export", "import"])
    p_pack.add_argument("path", help=".kamipack dosya yolu")
    p_pack.add_argument("--src-json", default="", help="export icin kaynak akis/recete JSON")
    p_pack.add_argument("--name", default="kami-pack")
    p_pack.add_argument("--dest", default="", help="import icin asset cikti klasoru")

    args = parser.parse_args(argv)
    out: Any = {"ok": False, "error": "Bilinmeyen komut"}

    if args.cmd == "status":
        out = sdk_status()
    elif args.cmd == "mcp-tools":
        from app.core.local_copilot import list_studio_tools
        tools = list_studio_tools()
        out = {"ok": True, "count": len(tools), "tools": [t["function"]["name"] for t in tools]}
    elif args.cmd == "copilot":
        from app.core.local_copilot import run_copilot
        out = run_copilot(args.prompt, model=args.model, execute_tools=not args.dry_run)
    elif args.cmd == "flow":
        from app.core import flow_chain
        if args.action == "list":
            out = {"ok": True, "flows": flow_chain.list_flows()}
        else:
            p = Path(args.target)
            if p.is_file():
                graph = json.loads(p.read_text(encoding="utf-8"))
            else:
                loaded = flow_chain.load_flow(args.target)
                if not loaded.get("ok"):
                    out = loaded
                    graph = None
                else:
                    graph = loaded["graph"]
            if graph is not None:
                out = flow_chain.execute_graph(graph)
    elif args.cmd == "pack":
        from app.core import kamipack
        if args.action == "inspect":
            out = kamipack.inspect_kamipack(args.path)
        elif args.action == "import":
            out = kamipack.import_kamipack(args.path, dest_dir=args.dest or None)
        elif args.action == "export":
            src = Path(args.src_json)
            if not src.is_file():
                out = {"ok": False, "error": "Kaynak JSON dosyasi bulunamadi"}
            else:
                payload = json.loads(src.read_text(encoding="utf-8"))
                out = kamipack.export_kamipack(args.name, payload, args.path)

    print(json.dumps(out, ensure_ascii=False, indent=2 if not args.json else None, default=str))
    return 0 if out.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
