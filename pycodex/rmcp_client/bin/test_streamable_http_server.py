"""Streamable HTTP MCP integration fixture matching the Rust test binary."""

from __future__ import annotations

import json
import os
import sys
import threading
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

MEMO_URI = "memo://codex/example-note"
MEMO_CONTENT = "This is a sample MCP resource served by the rmcp test server."
MCP_SESSION_ID_HEADER = "mcp-session-id"
SESSION_POST_FAILURE_CONTROL_PATH = "/test/control/session-post-failure"


@dataclass
class ArmedFailure:
    status: int
    remaining: int
    www_authenticate_headers: tuple[str, ...] = ()


@dataclass
class SessionFailureState:
    armed_failure: ArmedFailure | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def arm(self, payload: dict[str, Any]) -> None:
        status = int(payload["status"])
        remaining = int(payload["remaining"])
        if not 100 <= status <= 599:
            raise ValueError("invalid HTTP status")
        headers = tuple(str(item) for item in payload.get("www_authenticate_headers", ()))
        with self.lock:
            self.armed_failure = (
                None
                if remaining == 0
                else ArmedFailure(status, remaining, headers)
            )

    def take_failure(self) -> ArmedFailure | None:
        with self.lock:
            failure = self.armed_failure
            if failure is None or failure.remaining <= 0:
                return None
            failure.remaining -= 1
            result = ArmedFailure(
                failure.status,
                failure.remaining,
                failure.www_authenticate_headers,
            )
            if failure.remaining == 0:
                self.armed_failure = None
            return result


class TestToolServer:
    @staticmethod
    def info() -> dict[str, Any]:
        return {
            "protocolVersion": "2025-06-18",
            "capabilities": {
                "tools": {"listChanged": True},
                "resources": {},
            },
            "serverInfo": {
                "name": "test-streamable-http-server",
                "version": "0.1.0",
            },
        }

    @staticmethod
    def tools() -> list[dict[str, Any]]:
        return [
            {
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
                "annotations": {"readOnlyHint": True},
            }
        ]

    def handle(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "initialize":
            return self.info()
        if method == "tools/list":
            return {"tools": self.tools()}
        if method == "resources/list":
            return {
                "resources": [
                    {
                        "uri": MEMO_URI,
                        "name": "example-note",
                        "title": "Example Note",
                        "description": "A sample MCP resource exposed for integration tests.",
                        "mimeType": "text/plain",
                    }
                ]
            }
        if method == "resources/templates/list":
            return {
                "resourceTemplates": [
                    {
                        "uriTemplate": "memo://codex/{slug}",
                        "name": "codex-memo",
                        "title": "Codex Memo",
                        "description": "Template for memo resources used in tests.",
                        "mimeType": "text/plain",
                    }
                ]
            }
        if method == "resources/read":
            uri = str(params.get("uri", ""))
            if uri != MEMO_URI:
                raise LookupError("resource_not_found")
            return {
                "contents": [
                    {"uri": uri, "mimeType": "text/plain", "text": MEMO_CONTENT}
                ]
            }
        if method == "tools/call":
            if params.get("name") != "echo":
                raise ValueError(f"unknown tool: {params.get('name')}")
            arguments = params.get("arguments")
            if not isinstance(arguments, dict) or "message" not in arguments:
                raise ValueError("missing arguments for echo tool")
            return {
                "content": [],
                "structuredContent": {
                    "echo": f"ECHOING: {arguments['message']}",
                    "env": os.environ.get("MCP_TEST_VALUE"),
                },
                "isError": False,
            }
        return {}


class _Server(ThreadingHTTPServer):
    failure_state: SessionFailureState
    fixture: TestToolServer
    sessions: set[str]
    sessions_lock: threading.Lock


class _Handler(BaseHTTPRequestHandler):
    server: _Server

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _authorized(self) -> bool:
        if "/.well-known/" in self.path:
            return True
        token = os.environ.get("MCP_EXPECT_BEARER")
        return token is None or self.headers.get("Authorization") == f"Bearer {token}"

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        value = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(value, dict):
            raise ValueError("request body must be an object")
        return value

    def _send(
        self,
        status: int,
        value: Any = None,
        headers: tuple[tuple[str, str], ...] = (),
    ) -> None:
        body = b"" if value is None else json.dumps(value, separators=(",", ":")).encode()
        self.send_response(status)
        if body:
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
        for name, header_value in headers:
            self.send_header(name, header_value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.startswith("/.well-known/oauth-authorization-server/mcp"):
            host = self.headers.get("Host") or str(self.server.server_address)
            base = f"http://{host}"
            self._send(
                200,
                {
                    "authorization_endpoint": f"{base}/oauth/authorize",
                    "token_endpoint": f"{base}/oauth/token",
                    "scopes_supported": [""],
                },
            )
            return
        self._send(404)

    def do_DELETE(self) -> None:
        if not self._authorized():
            self._send(401)
            return
        session_id = self.headers.get(MCP_SESSION_ID_HEADER)
        with self.server.sessions_lock:
            self.server.sessions.discard(session_id or "")
        self._send(204)

    def do_POST(self) -> None:
        if not self._authorized():
            self._send(401)
            return
        try:
            payload = self._body()
            if urlsplit(self.path).path == SESSION_POST_FAILURE_CONTROL_PATH:
                self.server.failure_state.arm(payload)
                self._send(204)
                return
            if urlsplit(self.path).path != "/mcp":
                self._send(404)
                return
            session_id = self.headers.get(MCP_SESSION_ID_HEADER)
            if session_id:
                failure = self.server.failure_state.take_failure()
                if failure is not None:
                    self._send(
                        failure.status,
                        {
                            "error": (
                                f"forced session failure with status "
                                f"{failure.status}"
                            )
                        },
                        tuple(
                            ("WWW-Authenticate", value)
                            for value in failure.www_authenticate_headers
                        ),
                    )
                    return
                with self.server.sessions_lock:
                    if session_id not in self.server.sessions:
                        self._send(404)
                        return
            request_id = payload.get("id")
            if request_id is None:
                self._send(202)
                return
            method = str(payload.get("method", ""))
            result = self.server.fixture.handle(
                method,
                payload.get("params") or {},
            )
            response_headers: tuple[tuple[str, str], ...] = ()
            if method == "initialize":
                session_id = uuid.uuid4().hex
                with self.server.sessions_lock:
                    self.server.sessions.add(session_id)
                response_headers = ((MCP_SESSION_ID_HEADER, session_id),)
            self._send(
                200,
                {"jsonrpc": "2.0", "id": request_id, "result": result},
                response_headers,
            )
        except (KeyError, TypeError, ValueError) as exc:
            self._send(400, {"error": str(exc)})
        except Exception as exc:
            self._send(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": payload.get("id"),
                    "error": {"code": -32602, "message": str(exc)},
                },
            )


def parse_bind_addr() -> tuple[str, int]:
    value = (
        os.environ.get("MCP_STREAMABLE_HTTP_BIND_ADDR")
        or os.environ.get("BIND_ADDR")
        or "127.0.0.1:3920"
    )
    host, port = value.rsplit(":", 1)
    return host, int(port)


def main() -> int:
    server = _Server(parse_bind_addr(), _Handler)
    server.failure_state = SessionFailureState()
    server.fixture = TestToolServer()
    server.sessions = set()
    server.sessions_lock = threading.Lock()
    host, port = server.server_address[:2]
    actual = f"{host}:{port}"
    bound_file = os.environ.get("MCP_STREAMABLE_HTTP_BOUND_ADDR_FILE")
    if bound_file:
        Path(bound_file).write_text(actual, encoding="utf-8")
    print(
        f"starting rmcp streamable http test server on http://{actual}/mcp",
        file=sys.stderr,
        flush=True,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
