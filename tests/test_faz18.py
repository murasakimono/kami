"""Faz 18 — Yerel Ollama Copilot, Akis Zinciri, .kamipack ve kami-cli SDK testleri."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from app.core import flow_chain, kami_cli, kamipack, local_copilot


def test_local_copilot_tool_calling_loop():
    tools = local_copilot.list_studio_tools()
    names = {t["function"]["name"] for t in tools}
    assert "catalog" in names
    assert "get_project" in names

    turns = {"n": 0}

    def _fake_chat(messages, _tools, _model):
        turns["n"] += 1
        if turns["n"] == 1:
            return {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"function": {"name": "catalog", "arguments": {}}}],
                }
            }
        return {"message": {"role": "assistant", "content": "Katalog listelendi."}}

    res = local_copilot.run_copilot("Studio katalogunu goster", chat_fn=_fake_chat)
    assert res["ok"] is True
    assert res["reply"] == "Katalog listelendi."
    assert len(res["tool_calls"]) == 1
    assert res["tool_calls"][0]["tool"] == "catalog"
    assert "fx" in res["tool_calls"][0]["result"]


def test_kamipack_export_verify_and_security_blocks(tmp_path):
    pack = tmp_path / "ornek.kamipack"
    payload = {"nodes": [{"id": 1, "type": "input/file"}], "links": []}
    exp = kamipack.export_kamipack("Ornek Akis", payload, pack, author="Metehan")
    assert exp["ok"] is True
    assert pack.is_file()

    imp = kamipack.import_kamipack(pack)
    assert imp["ok"] is True
    assert imp["payload"] == payload

    # Zararli uzanti engelleme
    bad_pack = tmp_path / "bad.kamipack"
    with zipfile.ZipFile(bad_pack, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"format": kamipack.PACK_FORMAT, "sha256": {}}))
        zf.writestr("payload.json", "{}")
        zf.writestr("evil.bat", "echo pwn")
    bad_res = kamipack.inspect_kamipack(bad_pack)
    assert bad_res["ok"] is False
    assert "engellenen uzanti" in bad_res["error"]

    # SHA-256 bozulmasi yakalama
    tampered = tmp_path / "tampered.kamipack"
    with zipfile.ZipFile(pack, "r") as src_z, zipfile.ZipFile(tampered, "w") as dst_z:
        for item in src_z.infolist():
            data = b'{"tampered": true}' if item.filename == "payload.json" else src_z.read(item.filename)
            dst_z.writestr(item.filename, data)
    tamp_res = kamipack.inspect_kamipack(tampered)
    assert tamp_res["ok"] is False
    assert "SHA-256" in tamp_res["error"]


def test_flow_chain_cycle_detection_and_execution():
    bad_graph = {
        "nodes": [
            {"id": 1, "type": "studio/cut_silences"},
            {"id": 2, "type": "studio/auto_captions"},
        ],
        "links": [
            [1, 1, 0, 2, 0, "clip"],
            [2, 2, 0, 1, 0, "clip"],
        ],
    }
    assert flow_chain.validate_graph(bad_graph)["ok"] is False

    good_graph = {
        "nodes": [
            {"id": 1, "type": "input/file", "properties": {"path": "demo.mp4"}},
            {"id": 2, "type": "output/export", "properties": {"quality": "high"}},
        ],
        "links": [[1, 1, 0, 2, 0, "path"]],
    }
    exec_res = flow_chain.execute_graph(good_graph)
    assert exec_res["ok"] is True
    assert exec_res["order"] == [1, 2]
    assert exec_res["steps"][1]["result"]["outputs"][0] == "demo.mp4"


def test_kami_cli_and_flow_js_contract(capsys):
    rc = kami_cli.main(["--json", "mcp-tools"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is True
    assert data["count"] >= 20

    flow_js = (Path(__file__).resolve().parent.parent / "app" / "ui" / "web" / "kami-flow.js").read_text(encoding="utf-8")
    assert "KamiFlowGraph" in flow_js
