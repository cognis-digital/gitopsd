"""gitopsd MCP server — stdio JSON-RPC 2.0. Standard library only.

    {"command": "python", "args": ["-m", "gitopsd", "mcp"]}
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, Optional

from gitopsd import TOOL_NAME, TOOL_VERSION
from gitopsd.core import GitopsError, detect_drift

PROTOCOL_VERSION = "2024-11-05"

_TOOLS = [
    {
        "name": "diff",
        "description": "Detect GitOps drift between declared manifests and live "
                       "cluster state; returns missing/extra/drifted resources.",
        "inputSchema": {
            "type": "object",
            "properties": {"desired": {"type": "string"},
                           "live": {"type": "string"},
                           "prune": {"type": "boolean"}},
            "required": ["desired", "live"], "additionalProperties": False,
        },
    },
    {
        "name": "plan",
        "description": "Return the reconcile plan (apply/delete) to bring a "
                       "cluster back to the declared state.",
        "inputSchema": {
            "type": "object",
            "properties": {"desired": {"type": "string"},
                           "live": {"type": "string"},
                           "prune": {"type": "boolean"}},
            "required": ["desired", "live"], "additionalProperties": False,
        },
    },
]


def _result(req_id, result): return {"jsonrpc": "2.0", "id": req_id, "result": result}
def _error(req_id, code, msg): return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": msg}}


def _call_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    desired, live = args.get("desired"), args.get("live")
    if not isinstance(desired, str) or not isinstance(live, str):
        raise ValueError("`desired` and `live` (strings) are required")
    report = detect_drift(desired, live, prune=bool(args.get("prune", False)))
    if name == "plan":
        payload = {"plan": report["plan"]}
    elif name == "diff":
        payload = report
    else:
        raise ValueError(f"unknown tool: {name}")
    return {"content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
            "isError": not report["synced"] and name == "diff"}


def handle_request(req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    method = req.get("method")
    req_id = req.get("id")
    params = req.get("params") or {}
    is_notification = "id" not in req
    if method == "initialize":
        res = _result(req_id, {"protocolVersion": PROTOCOL_VERSION,
                               "capabilities": {"tools": {"listChanged": False}},
                               "serverInfo": {"name": TOOL_NAME, "version": TOOL_VERSION}})
        return None if is_notification else res
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "ping":
        return None if is_notification else _result(req_id, {})
    if method == "tools/list":
        return _result(req_id, {"tools": _TOOLS})
    if method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments") or {}
        try:
            return _result(req_id, _call_tool(name, args))
        except (ValueError, OSError, GitopsError) as exc:
            return _error(req_id, -32602, str(exc))
        except Exception as exc:  # pragma: no cover
            return _error(req_id, -32603, f"internal error: {exc}")
    if is_notification:
        return None
    return _error(req_id, -32601, f"method not found: {method}")


def run_mcp_server(stdin=None, stdout=None) -> None:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            stdout.write(json.dumps(_error(None, -32700, "parse error")) + "\n")
            stdout.flush()
            continue
        response = handle_request(req)
        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()


if __name__ == "__main__":
    run_mcp_server()
