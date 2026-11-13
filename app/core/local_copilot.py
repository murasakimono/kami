"""Faz 18.1 — Yerel Ollama (Qwen2.5:7b) Studio Copilot (studio_mcp araclariyla)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable

DEFAULT_MODEL = "qwen2.5:7b"
SYSTEM_PROMPT = (
    "Sen Kami Studio yerel Copilot asistanisin. Kullanicinin video/ses duzenleme "
    "isteklerini verilen Studio araclarini cagirarak yerine getir. Turkce ve kisa yanit ver."
)


def _ollama_host() -> str:
    return (os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip("/")


def copilot_status(timeout: float = 2.0) -> dict[str, Any]:
    """Yerel Ollama sunucusunun ve kurulu modellerin durumunu doner."""
    url = f"{_ollama_host()}/api/tags"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        return {
            "ok": True,
            "ollama_running": True,
            "host": _ollama_host(),
            "models": models,
            "qwen_ready": any("qwen2.5" in m.lower() for m in models),
        }
    except Exception as exc:
        return {
            "ok": True,
            "ollama_running": False,
            "host": _ollama_host(),
            "models": [],
            "qwen_ready": False,
            "error": str(exc),
        }


def list_studio_tools() -> list[dict[str, Any]]:
    """studio_mcp.TOOLS icindeki tum araclari Ollama tool semasi formatinda doner."""
    from app.core import studio_mcp

    out: list[dict[str, Any]] = []
    for name, entry in studio_mcp.TOOLS.items():
        schema = entry.get("schema", {})
        out.append({
            "type": "function",
            "function": {
                "name": name,
                "description": schema.get("description", ""),
                "parameters": schema.get("inputSchema", {"type": "object", "properties": {}}),
            },
        })
    return out


def _default_ollama_chat(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    model: str,
) -> dict[str, Any]:
    url = f"{_ollama_host()}/api/chat"
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "tools": tools,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def run_copilot(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    max_steps: int = 6,
    execute_tools: bool = True,
    chat_fn: Callable[[list[dict[str, Any]], list[dict[str, Any]], str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Kullanici istemini yerel Qwen2.5:7b ile cozer ve studio_mcp araclarini calistirir."""
    text = (prompt or "").strip()
    if not text:
        return {"ok": False, "error": "Bos istem gonderilemez", "tool_calls": []}

    from app.core import studio_mcp

    tools = list_studio_tools()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    caller = chat_fn or _default_ollama_chat
    executed: list[dict[str, Any]] = []
    final_reply = ""

    for _ in range(max(1, int(max_steps))):
        try:
            resp = caller(messages, tools, model)
        except Exception as exc:
            return {
                "ok": False,
                "error": f"Ollama baglanti hatasi: {exc}",
                "model": model,
                "tool_calls": executed,
            }

        msg = resp.get("message") or {}
        messages.append(msg)
        calls = msg.get("tool_calls") or []
        final_reply = (msg.get("content") or "").strip()

        if not calls:
            break

        for tc in calls:
            fn_obj = tc.get("function") or {}
            tname = str(fn_obj.get("name") or "")
            raw_args = fn_obj.get("arguments") or {}
            if isinstance(raw_args, str):
                try:
                    raw_args = json.loads(raw_args)
                except ValueError:
                    raw_args = {}
            if not isinstance(raw_args, dict):
                raw_args = {}

            if tname not in studio_mcp.TOOLS:
                res_obj: Any = {"ok": False, "error": f"Bilinmeyen arac: {tname}"}
            elif not execute_tools:
                res_obj = {"ok": True, "dry_run": True, "tool": tname, "args": raw_args}
            else:
                try:
                    res_obj = studio_mcp.TOOLS[tname]["fn"](**raw_args)
                except Exception as exc:
                    res_obj = {"ok": False, "error": str(exc)}

            executed.append({"tool": tname, "args": raw_args, "result": res_obj})
            messages.append({
                "role": "tool",
                "content": json.dumps(res_obj, ensure_ascii=False, default=str),
            })

    return {
        "ok": True,
        "model": model,
        "reply": final_reply,
        "tool_calls": executed,
    }
