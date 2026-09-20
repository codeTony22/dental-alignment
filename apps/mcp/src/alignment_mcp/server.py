"""Hand-rolled JSON-RPC 2.0 MCP server over stdio.

Implements the subset an MCP client needs: ``initialize``, ``tools/list``,
``tools/call``, ``ping``. Notifications (``notifications/initialized``) are
acknowledged by silence. No SDK — the boundary tests pin that this package
does not import ``bff`` or ``case_prep.server``.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, TextIO

from .tools import ToolContext, ToolError, call_tool, list_tools

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "alignment-mcp", "version": "0.1.0"}


def default_context() -> ToolContext:
    repo = Path(__file__).resolve().parents[4]
    return ToolContext(
        data_root=repo / "apps" / "worker" / "data" / "real",
        product_root=repo / "apps" / "worker" / "reports" / "product",
    )


def _result(message_id: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _error(message_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


def handle_message(message: Dict[str, Any], ctx: ToolContext) -> Optional[Dict[str, Any]]:
    if message.get("jsonrpc") != "2.0":
        return _error(message.get("id"), -32600, "jsonrpc must be 2.0")
    method = message.get("method")
    message_id = message.get("id")
    params = message.get("params") if isinstance(message.get("params"), dict) else {}
    if message_id is None:
        return None
    if method == "initialize":
        return _result(message_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
        })
    if method == "ping":
        return _result(message_id, {})
    if method == "tools/list":
        return _result(message_id, {"tools": list_tools()})
    if method == "tools/call":
        name = str(params.get("name") or "")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        try:
            payload = call_tool(name, arguments, ctx)
        except ToolError as exc:
            return _result(message_id, {
                "content": [{"type": "text", "text": str(exc)}],
                "isError": True,
                "code": exc.code,
            })
        return _result(message_id, {
            "content": [{"type": "text", "text": json.dumps(payload, default=str)}],
            "structuredContent": payload,
            "isError": False,
        })
    return _error(message_id, -32601, f"unknown method {method!r}")


def serve(stdin: TextIO, stdout: TextIO, ctx: Optional[ToolContext] = None) -> None:
    context = ctx or default_context()
    for line in stdin:
        raw = line.strip()
        if not raw:
            continue
        try:
            message = json.loads(raw)
        except json.JSONDecodeError as exc:
            stdout.write(json.dumps(_error(None, -32700, f"parse error: {exc}")) + "\n")
            stdout.flush()
            continue
        if not isinstance(message, dict):
            stdout.write(json.dumps(_error(None, -32600, "message must be an object")) + "\n")
            stdout.flush()
            continue
        reply = handle_message(message, context)
        if reply is not None:
            stdout.write(json.dumps(reply, default=str) + "\n")
            stdout.flush()


def main() -> None:
    serve(sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
