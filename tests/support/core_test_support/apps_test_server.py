"""ChatGPT apps fixture server derived from ``apps_test_server.rs``."""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

CALENDAR_EXTRACT_TEXT_TOOL_NAME = "calendar_extract_text"
DIRECT_CALENDAR_CREATE_EVENT_TOOL = "mcp__codex_apps__calendar__create_event"
DIRECT_CALENDAR_LIST_EVENTS_TOOL = "mcp__codex_apps__calendar__list_events"
DIRECT_CALENDAR_EXTRACT_TEXT_TOOL = "mcp__codex_apps__calendar__extract_text"
SEARCH_CALENDAR_NAMESPACE = "mcp__codex_apps__calendar"
SEARCH_CALENDAR_CREATE_TOOL = "_create_event"
SEARCH_CALENDAR_EXTRACT_TEXT_TOOL = "_extract_text"
SEARCH_CALENDAR_LIST_TOOL = "_list_events"
CALENDAR_CREATE_EVENT_RESOURCE_URI = "connector://calendar/tools/calendar_create_event"
CALENDAR_CREATE_EVENT_MCP_APP_RESOURCE_URI = "ui://widget/calendar-create-event.html"
DOCUMENT_EXTRACT_TEXT_RESOURCE_URI = "connector://calendar/tools/calendar_extract_text"


class AppsTestServer:
    def __init__(
        self,
        server: ThreadingHTTPServer,
        thread: threading.Thread,
        calls: list[dict[str, Any]],
        lock: threading.Lock,
    ) -> None:
        self._server = server
        self._thread = thread
        self._calls = calls
        self._lock = lock
        host, port = server.server_address[:2]
        self.chatgpt_base_url = f"http://{host}:{port}"

    @classmethod
    async def mount(cls) -> "AppsTestServer":
        return await cls.mount_with_tools(
            (
                {
                    "name": "calendar_create_event",
                    "description": "Create a calendar event",
                    "inputSchema": {"type": "object"},
                },
                {
                    "name": "calendar_list_events",
                    "description": "List calendar events",
                    "inputSchema": {"type": "object"},
                },
            )
        )

    @classmethod
    async def mount_with_tools(
        cls,
        tools: tuple[dict[str, Any], ...] | list[dict[str, Any]],
        *,
        apps: tuple[dict[str, Any], ...] | list[dict[str, Any]] | None = None,
        tool_call_result: dict[str, Any] | None = None,
    ) -> "AppsTestServer":
        calls: list[dict[str, Any]] = []
        lock = threading.Lock()
        listed_tools = [dict(tool) for tool in tools]
        directory_apps = [
            dict(app)
            for app in (
                apps
                if apps is not None
                else (
                    {
                        "id": "connector_2128aebfecb84f64a069897515042a44",
                        "name": "Google Calendar",
                        "description": "Plan events and schedules.",
                    },
                )
            )
        ]
        configured_tool_call_result = (
            dict(tool_call_result)
            if tool_call_result is not None
            else {"content": [{"type": "text", "text": "ok"}], "isError": False}
        )
        sessions: set[str] = set()

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _json(
                self,
                value: Any = None,
                *,
                status: int = 200,
                headers: tuple[tuple[str, str], ...] = (),
            ) -> None:
                body = (
                    b""
                    if value is None
                    else json.dumps(value, separators=(",", ":")).encode()
                )
                self.send_response(status)
                if body:
                    self.send_header("content-type", "application/json")
                    self.send_header("content-length", str(len(body)))
                for name, header_value in headers:
                    self.send_header(name, header_value)
                self.end_headers()
                if body:
                    self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802
                if self.path.startswith("/.well-known/oauth-authorization-server/mcp"):
                    self._json(
                        {
                            "authorization_endpoint": "/oauth/authorize",
                            "token_endpoint": "/oauth/token",
                            "scopes_supported": [""],
                        }
                    )
                    return
                if self.path.startswith("/connectors/directory/list"):
                    self._json(
                        {
                            "apps": directory_apps,
                            "nextToken": None,
                        }
                    )
                    return
                self.send_error(404)

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("content-length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                with lock:
                    calls.append(body)
                request_id = body.get("id")
                if request_id is None:
                    self._json(status=202)
                    return
                method = body.get("method")
                response_headers: tuple[tuple[str, str], ...] = ()
                if method == "initialize":
                    session_id = uuid.uuid4().hex
                    with lock:
                        sessions.add(session_id)
                    response_headers = (("mcp-session-id", session_id),)
                    result = {
                        "protocolVersion": "2025-11-25",
                        "serverInfo": {"name": "codex-apps-test", "version": "1.0.0"},
                        "capabilities": {"tools": {}},
                    }
                elif method == "tools/list":
                    result = {"tools": listed_tools}
                elif method == "tools/call":
                    result = configured_tool_call_result
                else:
                    result = {}
                self._json(
                    {"jsonrpc": "2.0", "id": request_id, "result": result},
                    headers=response_headers,
                )

            def do_DELETE(self) -> None:  # noqa: N802
                session_id = self.headers.get("mcp-session-id")
                with lock:
                    sessions.discard(session_id or "")
                self._json(status=204)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, name="core-test-apps", daemon=True)
        thread.start()
        return cls(server, thread, calls, lock)

    @classmethod
    async def mount_searchable(cls) -> "AppsTestServer":
        return await cls.mount()

    @classmethod
    async def mount_with_connector_name(cls, _connector_name: str) -> "AppsTestServer":
        return await cls.mount()

    async def recorded_calls(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._calls)

    async def recorded_apps_tool_call_by_call_id(self, call_id: str) -> dict[str, Any]:
        matches = [
            call
            for call in await self.recorded_calls()
            if call.get("params", {}).get("_meta", {}).get("_codex_apps", {}).get("call_id") == call_id
        ]
        if len(matches) != 1:
            raise AssertionError(f"expected exactly one apps tools/call request for call_id {call_id}")
        return matches[0]

    async def shutdown(self) -> None:
        await asyncio.to_thread(self._server.shutdown)
        await asyncio.to_thread(self._server.server_close)
        await asyncio.to_thread(self._thread.join, 5.0)


__all__ = [
    "AppsTestServer",
    "CALENDAR_CREATE_EVENT_MCP_APP_RESOURCE_URI",
    "CALENDAR_CREATE_EVENT_RESOURCE_URI",
    "CALENDAR_EXTRACT_TEXT_TOOL_NAME",
    "DIRECT_CALENDAR_CREATE_EVENT_TOOL",
    "DIRECT_CALENDAR_EXTRACT_TEXT_TOOL",
    "DIRECT_CALENDAR_LIST_EVENTS_TOOL",
    "DOCUMENT_EXTRACT_TEXT_RESOURCE_URI",
    "SEARCH_CALENDAR_CREATE_TOOL",
    "SEARCH_CALENDAR_EXTRACT_TEXT_TOOL",
    "SEARCH_CALENDAR_LIST_TOOL",
    "SEARCH_CALENDAR_NAMESPACE",
]
