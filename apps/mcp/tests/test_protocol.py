"""JSON-RPC stdio surface — initialize, list, call, unknown method."""
from __future__ import annotations

import io
import json
from pathlib import Path

from alignment_mcp.server import handle_message, serve
from alignment_mcp.tools import ToolContext, list_tools


def test_initialize_and_tools_list():
    ctx = ToolContext(data_root=Path("/tmp"), product_root=Path("/tmp"))
    init = handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, ctx)
    assert init["result"]["serverInfo"]["name"] == "alignment-mcp"
    listed = handle_message(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, ctx)
    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert "get_site_signals" in names
    assert "run_alignment_technique" in names
    for tool in listed["result"]["tools"]:
        assert tool["description"].startswith("[")
        assert tool["classification"] in {"READ", "DRY_RUN", "COMMIT"}


def test_unknown_method_is_a_jsonrpc_error():
    ctx = ToolContext(data_root=Path("/tmp"), product_root=Path("/tmp"))
    reply = handle_message({"jsonrpc": "2.0", "id": 3, "method": "nope"}, ctx)
    assert reply["error"]["code"] == -32601


def test_unknown_tool_is_an_isError_result():
    ctx = ToolContext(data_root=Path("/tmp"), product_root=Path("/tmp"))
    reply = handle_message({
        "jsonrpc": "2.0", "id": 4, "method": "tools/call",
        "params": {"name": "explode", "arguments": {}},
    }, ctx)
    assert reply["result"]["isError"] is True


def test_notifications_have_no_reply():
    ctx = ToolContext(data_root=Path("/tmp"), product_root=Path("/tmp"))
    assert handle_message(
        {"jsonrpc": "2.0", "method": "notifications/initialized"}, ctx) is None


def test_stdio_round_trip_lists_tools():
    stdin = io.StringIO(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/list",
    }) + "\n")
    stdout = io.StringIO()
    serve(stdin, stdout, ToolContext(Path("/tmp"), Path("/tmp")))
    reply = json.loads(stdout.getvalue())
    assert {t["name"] for t in reply["result"]["tools"]} == {
        t["name"] for t in list_tools()
    }
