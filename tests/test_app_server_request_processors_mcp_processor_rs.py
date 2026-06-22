"""Rust parity tests for ``request_processors/mcp_processor.rs``."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from pycodex.app_server.request_processors_mcp_processor import (
    McpRequestProcessor,
    McpRequestProcessorError,
    McpServerStatusSnapshot,
    list_mcp_server_status_response,
    resolve_oauth_scopes,
    send_mcp_resource_read_response,
    with_mcp_tool_call_thread_id_meta,
)
from pycodex.app_server.error_code import internal_error
from pycodex.app_server_protocol import (
    JSONRPCErrorError,
    ListMcpServerStatusParams,
    McpAuthStatus,
    McpResourceReadParams,
    McpResourceReadResponse,
    McpServerOauthLoginParams,
    McpServerToolCallParams,
    McpServerToolCallResponse,
)


THREAD_ID = "11111111-1111-4111-8111-111111111111"


class Outgoing:
    def __init__(self) -> None:
        self.results = []
        self.notifications = []

    def send_result(self, request_id, result):
        self.results.append((request_id, result))

    def send_server_notification(self, notification):
        self.notifications.append(notification)


class ConfigManager:
    def __init__(self, config=None, error: Exception | None = None) -> None:
        self.config = config or Config()
        self.error = error
        self.latest_calls = []

    def load_latest_config(self):
        self.latest_calls.append(None)
        if self.error is not None:
            raise self.error
        return self.config

    def load_latest_config_for_thread(self, thread_config):
        self.latest_calls.append(thread_config)
        return self.config


class Config:
    cwd = Path("C:/repo")
    mcp_oauth_credentials_store_mode = "chatgpt"
    mcp_oauth_callback_port = 12345
    mcp_oauth_callback_url = None

    def to_mcp_config(self, plugins_manager):
        return {"plugins_manager": plugins_manager, "cwd": self.cwd}


class AuthManager:
    def auth(self):
        return {"user": "u"}


class McpManager:
    def __init__(self, servers=None) -> None:
        self.servers = servers or {}

    def configured_servers(self, _config):
        return self.servers


class ThreadManager:
    def __init__(self, threads=None, servers=None) -> None:
        self.threads = threads or {}
        self.mcp = McpManager(servers)
        self.plugins = object()
        self.environment = object()

    def get_thread(self, thread_id):
        try:
            return self.threads[thread_id]
        except KeyError as exc:
            raise KeyError("missing") from exc

    def mcp_manager(self):
        return self.mcp

    def plugins_manager(self):
        return self.plugins

    def environment_manager(self):
        return self.environment


class Thread:
    def __init__(self) -> None:
        self.tool_calls = []

    def config(self):
        return {"thread": THREAD_ID}

    def read_mcp_resource(self, server, uri):
        return {"contents": [{"uri": uri, "server": server}]}

    def call_mcp_tool(self, server, tool, arguments, meta):
        self.tool_calls.append((server, tool, arguments, meta))
        return {"content": [{"type": "text", "text": "ok"}], "isError": False}


def _processor(**kwargs):
    outgoing = kwargs.pop("outgoing", Outgoing())
    thread_manager = kwargs.pop("thread_manager", ThreadManager())
    config_manager = kwargs.pop("config_manager", ConfigManager())
    return McpRequestProcessor.new(AuthManager(), thread_manager, outgoing, config_manager, **kwargs), outgoing


def test_with_mcp_tool_call_thread_id_meta_matches_rust_object_and_none_branches() -> None:
    # Rust source: with_mcp_tool_call_thread_id_meta inserts "threadId" into object meta.
    assert with_mcp_tool_call_thread_id_meta(None, THREAD_ID) == {"threadId": THREAD_ID}
    assert with_mcp_tool_call_thread_id_meta({"x": 1}, THREAD_ID) == {"x": 1, "threadId": THREAD_ID}
    assert with_mcp_tool_call_thread_id_meta(["not", "object"], THREAD_ID) == ["not", "object"]


def test_list_mcp_server_status_response_sorts_unions_paginates_and_defaults_auth() -> None:
    # Rust source: server_names extends auth/resources/templates, sorts, dedups, then paginates.
    snapshot = McpServerStatusSnapshot(
        tools_by_server={"beta": {"tool": {"description": "b"}}},
        resources={"alpha": ({"uri": "alpha://r"},)},
        resource_templates={"gamma": ({"uriTemplate": "gamma://{id}"},)},
        auth_statuses={"beta": McpAuthStatus.OAUTH},
        server_names=("beta",),
    )

    response = list_mcp_server_status_response(
        "req-1",
        ListMcpServerStatusParams(limit=2),
        snapshot,
    )

    assert [item.name for item in response.data] == ["alpha", "beta"]
    assert response.next_cursor == "2"
    assert response.data[0].auth_status == McpAuthStatus.UNSUPPORTED
    assert response.data[1].auth_status == McpAuthStatus.OAUTH


def test_list_mcp_server_status_response_rejects_invalid_cursor_like_rust() -> None:
    with pytest.raises(McpRequestProcessorError) as caught:
        list_mcp_server_status_response("req", ListMcpServerStatusParams(cursor="bad"), {})

    assert caught.value.error.code == -32600
    assert caught.value.error.message == "invalid cursor: bad"


def test_mcp_server_refresh_maps_queue_failure_to_internal_error() -> None:
    # Rust source: mcp_server_refresh_response maps queue_strict_refresh failure to internal_error.
    def queue_refresh(_thread_manager, _config_manager):
        raise RuntimeError("offline")

    processor, _outgoing = _processor(queue_refresh=queue_refresh)

    with pytest.raises(McpRequestProcessorError) as caught:
        asyncio.run(processor.mcp_server_refresh())

    assert caught.value.error.code == -32603
    assert caught.value.error.message == "failed to refresh MCP servers: offline"


def test_load_thread_maps_parse_and_missing_thread_errors() -> None:
    thread = Thread()
    processor, _outgoing = _processor(thread_manager=ThreadManager({THREAD_ID: thread}))

    assert asyncio.run(processor.load_thread(THREAD_ID)) == (THREAD_ID, thread)

    with pytest.raises(McpRequestProcessorError) as invalid:
        asyncio.run(processor.load_thread("not-a-uuid"))
    assert invalid.value.error.code == -32600
    assert invalid.value.error.message.startswith("invalid thread id:")

    with pytest.raises(McpRequestProcessorError) as missing:
        asyncio.run(processor.load_thread("22222222-2222-4222-8222-222222222222"))
    assert missing.value.error.message == "thread not found: 22222222-2222-4222-8222-222222222222"


def test_send_mcp_resource_read_response_deserializes_or_internal_errors() -> None:
    outgoing = Outgoing()

    asyncio.run(send_mcp_resource_read_response(outgoing, "req", {"contents": [{"text": "ok"}]}))
    asyncio.run(send_mcp_resource_read_response(outgoing, "bad", {"wrong": []}))
    original_error = internal_error("already mapped")
    asyncio.run(send_mcp_resource_read_response(outgoing, "err", original_error))

    assert outgoing.results[0] == ("req", McpResourceReadResponse(contents=({"text": "ok"},)))
    assert isinstance(outgoing.results[1][1], JSONRPCErrorError)
    assert outgoing.results[1][1].code == -32603
    assert outgoing.results[1][1].message.startswith("failed to deserialize MCP resource read response:")
    assert outgoing.results[2] == ("err", original_error)


def test_mcp_resource_read_with_thread_sends_thread_result() -> None:
    thread = Thread()
    processor, outgoing = _processor(thread_manager=ThreadManager({THREAD_ID: thread}))

    asyncio.run(
        processor.mcp_resource_read(
            "req",
            McpResourceReadParams(thread_id=THREAD_ID, server="srv", uri="file://a"),
        )
    )

    assert outgoing.results == [
        ("req", McpResourceReadResponse(contents=({"uri": "file://a", "server": "srv"},)))
    ]


def test_mcp_server_tool_call_loads_thread_injects_meta_and_sends_response() -> None:
    thread = Thread()
    processor, outgoing = _processor(thread_manager=ThreadManager({THREAD_ID: thread}))

    asyncio.run(
        processor.mcp_server_tool_call(
            "req",
            McpServerToolCallParams(
                thread_id=THREAD_ID,
                server="srv",
                tool="lookup",
                arguments={"q": "hi"},
                meta={"caller": "app"},
            ),
        )
    )

    assert thread.tool_calls == [("srv", "lookup", {"q": "hi"}, {"caller": "app", "threadId": THREAD_ID})]
    assert outgoing.results == [
        ("req", McpServerToolCallResponse(content=({"type": "text", "text": "ok"},), is_error=False))
    ]


def test_mcp_server_oauth_login_rejects_missing_or_non_http_server() -> None:
    processor, _outgoing = _processor(thread_manager=ThreadManager(servers={}))

    with pytest.raises(McpRequestProcessorError) as missing:
        asyncio.run(processor.mcp_server_oauth_login(McpServerOauthLoginParams(name="docs")))
    assert missing.value.error.message == "No MCP server named 'docs' found."

    server = SimpleNamespace(transport={"type": "stdio"}, scopes=None)
    processor, _outgoing = _processor(thread_manager=ThreadManager(servers={"docs": server}))

    with pytest.raises(McpRequestProcessorError) as unsupported:
        asyncio.run(processor.mcp_server_oauth_login({"name": "docs"}))
    assert unsupported.value.error.message == "OAuth login is only supported for streamable HTTP servers."


def test_resolve_oauth_scopes_prefers_request_then_server_then_discovered() -> None:
    assert resolve_oauth_scopes(("a",), ("b",), ("c",)) == ("a",)
    assert resolve_oauth_scopes(None, ("b",), ("c",)) == ("b",)
    assert resolve_oauth_scopes(None, None, ("c",)) == ("c",)
    assert resolve_oauth_scopes(None, None, None) == ()
