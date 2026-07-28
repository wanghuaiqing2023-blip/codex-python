from __future__ import annotations

import json
from typing import Any

import pytest

from pycodex.exec_server.client.http_client.response_body_stream import HttpResponseBodyStream
from pycodex.exec_server.protocol import (
    ByteChunk,
    HttpHeader,
    HttpRequestParams,
    HttpRequestResponse,
)
from pycodex.rmcp_client.http_client_adapter import (
    StreamableHttpClientAdapter,
    StreamableHttpClientAdapterError,
)
from pycodex.rmcp_client.http_client_adapter.www_authenticate import (
    InsufficientScopeChallenge,
    insufficient_scope_challenge,
    parse_bearer_insufficient_scope,
)
from pycodex.rmcp_client.rmcp_client import RmcpClient


@pytest.mark.parametrize(
    ("header", "scope"),
    [
        ('Bearer error="insufficient_scope", scope="files:read files:write"', "files:read files:write"),
        ('Bearer error="insufficient_scope", ScOpE = "files:read"', "files:read"),
        ('Bearer scope="read:data", error="insufficient_scope"', "read:data"),
        ('Bearer error="insufficient_scope", scope=read', "read"),
        ('Bearer error="insufficient_scope", scope="files:read\\ files:write"', "files:read files:write"),
        (
            'Bearer error="insufficient_scope", error_description="request scope=admin, not \\"root\\"", scope="files:read"',
            "files:read",
        ),
        ('Basic realm="example", Bearer error="insufficient_scope", scope="files:read"', "files:read"),
    ],
)
def test_extracts_scope_from_bearer_challenges(header: str, scope: str) -> None:
    parsed = parse_bearer_insufficient_scope(header)
    assert parsed is not None
    assert parsed.required_scope == scope


@pytest.mark.parametrize(
    "header",
    [
        'Bearer error="insufficient_scope", scope=',
        'Bearer error="insufficient_scope", scope="read\\"write"',
        'Bearer error="insufficient_scope", scope="read\\\\write"',
        'Bearer error="insufficient_scope", scope="read  write"',
        'Bearer error="insufficient_scope", scope=read:data',
        'Bearer error="insufficient_scope", scope=files:read files:write',
        'Bearer error="insufficient_scope", scope=read=value',
        'Bearer error="insufficient_scope", scope="read", scope="write"',
    ],
)
def test_invalid_or_ambiguous_scope_is_omitted(header: str) -> None:
    parsed = parse_bearer_insufficient_scope(header)
    assert parsed is not None
    assert parsed.required_scope is None


def test_insufficient_scope_selects_later_header() -> None:
    headers = [
        HttpHeader("www-authenticate", 'Basic realm="example"'),
        HttpHeader(
            "WWW-Authenticate",
            'Bearer error="insufficient_scope", scope="files:read"',
        ),
    ]
    assert insufficient_scope_challenge(headers) == InsufficientScopeChallenge(
        headers[1].value,
        "files:read",
    )


class _HttpClient:
    def __init__(
        self,
        response: HttpRequestResponse,
        chunks: tuple[bytes, ...] = (),
    ) -> None:
        self.response = response
        self.chunks = chunks
        self.requests: list[HttpRequestParams] = []

    async def http_request_stream(
        self,
        params: HttpRequestParams,
    ) -> tuple[HttpRequestResponse, HttpResponseBodyStream]:
        self.requests.append(params)
        return self.response, HttpResponseBodyStream.local(self.chunks)

    async def http_request(self, params: HttpRequestParams) -> HttpRequestResponse:
        self.requests.append(params)
        return self.response


def _response(
    status: int,
    headers: list[HttpHeader] | None = None,
    body: bytes = b"",
) -> HttpRequestResponse:
    return HttpRequestResponse(status, headers or [], ByteChunk(body))


@pytest.mark.asyncio
async def test_post_message_builds_headers_and_decodes_json() -> None:
    message = {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
    client = _HttpClient(
        _response(
            200,
            [
                HttpHeader("content-type", "application/json; charset=utf-8"),
                HttpHeader("mcp-session-id", "session-1"),
            ],
        ),
        (json.dumps(message).encode(),),
    )
    adapter = StreamableHttpClientAdapter(
        client,
        {"x-default": "yes"},
        None,
    )
    result = await adapter.post_message(
        "https://example.test/mcp",
        {"jsonrpc": "2.0", "id": 1, "method": "ping"},
        None,
        "secret",
        {"x-custom": "value"},
    )

    assert result.kind == "json"
    assert result.message == message
    assert result.session_id == "session-1"
    request = client.requests[0]
    headers = {item.name.lower(): item.value for item in request.headers}
    assert request.method == "POST"
    assert headers["accept"] == "text/event-stream, application/json"
    assert headers["content-type"] == "application/json"
    assert headers["authorization"] == "Bearer secret"
    assert headers["x-default"] == "yes"
    assert headers["x-custom"] == "value"


@pytest.mark.asyncio
async def test_post_message_maps_protocol_statuses() -> None:
    accepted = StreamableHttpClientAdapter(_HttpClient(_response(202)), {}, None)
    assert (
        await accepted.post_message("https://example.test", {}, None, None, {})
    ).kind == "accepted"

    expired = StreamableHttpClientAdapter(_HttpClient(_response(404)), {}, None)
    with pytest.raises(StreamableHttpClientAdapterError) as expired_error:
        await expired.post_message("https://example.test", {}, "session", None, {})
    assert expired_error.value.kind == "session_expired_404"

    auth = StreamableHttpClientAdapter(
        _HttpClient(
            _response(401, [HttpHeader("WWW-Authenticate", "Bearer realm=test")])
        ),
        {},
        None,
    )
    with pytest.raises(StreamableHttpClientAdapterError) as auth_error:
        await auth.post_message("https://example.test", {}, None, None, {})
    assert auth_error.value.kind == "auth_required"

    scope = StreamableHttpClientAdapter(
        _HttpClient(
            _response(
                403,
                [
                    HttpHeader(
                        "WWW-Authenticate",
                        'Bearer error="insufficient_scope", scope="files:read"',
                    )
                ],
            )
        ),
        {},
        None,
    )
    with pytest.raises(StreamableHttpClientAdapterError) as scope_error:
        await scope.post_message("https://example.test", {}, None, None, {})
    assert scope_error.value.kind == "insufficient_scope"
    assert scope_error.value.required_scope == "files:read"


@pytest.mark.asyncio
async def test_delete_and_get_stream_match_streamable_http_contract() -> None:
    delete_client = _HttpClient(_response(405))
    adapter = StreamableHttpClientAdapter(delete_client, {}, None)
    await adapter.delete_session("https://example.test", "session", None, {})

    get_client = _HttpClient(
        _response(200, [HttpHeader("content-type", "text/event-stream")]),
        (b"event: message\ndata: {\"ok\":true}\n\n",),
    )
    stream = await StreamableHttpClientAdapter(get_client, {}, None).get_stream(
        "https://example.test",
        "session",
        "event-1",
        None,
        {},
    )
    events = [event async for event in stream]
    assert events == [{"event": "message", "data": '{"ok":true}'}]
    headers = {item.name.lower(): item.value for item in get_client.requests[0].headers}
    assert headers["mcp-session-id"] == "session"
    assert headers["last-event-id"] == "event-1"


class _McpHttpClient:
    def __init__(self) -> None:
        self.requests: list[HttpRequestParams] = []

    async def http_request_stream(
        self,
        params: HttpRequestParams,
    ) -> tuple[HttpRequestResponse, HttpResponseBodyStream]:
        self.requests.append(params)
        request = json.loads(params.body.into_inner()) if params.body else {}
        method = request.get("method")
        if method == "initialize":
            result: Any = {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "http-fixture", "version": "1"},
            }
        elif method == "tools/list":
            result = {"tools": [{"name": "http-tool", "inputSchema": {}}]}
        else:
            result = {}
        response = {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": result,
        }
        headers = [HttpHeader("content-type", "application/json")]
        if method == "initialize":
            headers.append(HttpHeader("mcp-session-id", "http-session"))
        return (
            _response(200, headers),
            HttpResponseBodyStream.local((json.dumps(response).encode(),)),
        )

    async def http_request(self, params: HttpRequestParams) -> HttpRequestResponse:
        self.requests.append(params)
        return _response(204)


@pytest.mark.asyncio
async def test_rmcp_client_streamable_http_uses_shared_http_client() -> None:
    # Rust: RmcpClient::new_streamable_http_client -> StreamableHttpClientAdapter.
    http_client = _McpHttpClient()
    client = await RmcpClient.new_streamable_http_client(
        server_name="fixture",
        url="https://example.test/mcp",
        bearer_token="token",
        http_headers={"x-static": "yes"},
        env_http_headers=None,
        store_mode="file",
        http_client=http_client,
        auth_provider=None,
    )
    initialized = await client.initialize(
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "pycodex-test", "version": "1"},
        },
        timeout=5,
    )
    tools = await client.list_tools(timeout=5)
    await client.shutdown()

    assert initialized["serverInfo"]["name"] == "http-fixture"
    assert tools["tools"][0]["name"] == "http-tool"
    assert [request.method for request in http_client.requests] == [
        "POST",
        "POST",
        "POST",
        "DELETE",
    ]
    list_headers = {
        item.name.lower(): item.value
        for item in http_client.requests[2].headers
    }
    assert list_headers["mcp-session-id"] == "http-session"
    assert list_headers["authorization"] == "Bearer token"
