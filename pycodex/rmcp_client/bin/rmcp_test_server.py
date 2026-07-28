"""Small stdio MCP server matching the Rust rmcp test binary."""

from __future__ import annotations

import json
import os
import sys
from typing import Any


def stdio() -> tuple[Any, Any]:
    return sys.stdin, sys.stdout


class TestToolServer:
    @staticmethod
    def echo_tool() -> dict[str, Any]:
        return {
            "name": "echo",
            "description": (
                "Echo back the provided message and include environment data."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "env_var": {"type": "string"},
                },
                "required": ["message"],
                "additionalProperties": False,
            },
            "outputSchema": {
                "type": "object",
                "properties": {
                    "echo": {"type": "string"},
                    "env": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                },
                "required": ["echo", "env"],
                "additionalProperties": False,
            },
        }

    def handle(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "initialize":
            return {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": {"name": "rmcp-test-server", "version": "0.1.0"},
            }
        if method == "tools/list":
            return {"tools": [self.echo_tool()]}
        if method == "tools/call":
            if params.get("name") != "echo":
                raise ValueError(f"unknown tool: {params.get('name')}")
            arguments = params.get("arguments")
            if not isinstance(arguments, dict) or "message" not in arguments:
                raise ValueError("missing arguments for echo tool")
            env_name = str(arguments.get("env_var") or "MCP_TEST_VALUE")
            return {
                "content": [],
                "structuredContent": {
                    "echo": str(arguments["message"]),
                    "env": os.environ.get(env_name),
                },
                "isError": False,
            }
        return {}


def main() -> int:
    print("starting rmcp test server", file=sys.stderr, flush=True)
    source, sink = stdio()
    server = TestToolServer()
    for line in source:
        try:
            message = json.loads(line)
            request_id = message.get("id")
            if request_id is None:
                continue
            result = server.handle(
                str(message.get("method", "")),
                message.get("params") or {},
            )
            response = {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as exc:
            response = {
                "jsonrpc": "2.0",
                "id": message.get("id") if isinstance(message, dict) else None,
                "error": {"code": -32602, "message": str(exc)},
            }
        sink.write(json.dumps(response, separators=(",", ":")) + "\n")
        sink.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
