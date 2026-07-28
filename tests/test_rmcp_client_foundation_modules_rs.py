from __future__ import annotations

import asyncio
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from pycodex.config.mcp_types import McpServerEnvVar
from pycodex.protocol import McpAuthStatus as ProtocolMcpAuthStatus
from pycodex.rmcp_client import (
    InProcessTransportFactory,
    McpAuthStatus,
    StreamableHttpOAuthDiscovery,
    determine_streamable_http_auth_status,
    discover_streamable_http_oauth,
    supports_oauth_login,
)
from pycodex.rmcp_client.utils import (
    build_default_headers,
    create_env_for_mcp_server,
    create_env_overlay_for_remote_mcp_server,
    remote_mcp_env_var_names,
)


class _DiscoveryHandler(BaseHTTPRequestHandler):
    response_body = (
        b'{"authorization_endpoint":"https://example.com/authorize",'
        b'"token_endpoint":"https://example.com/token",'
        b'"scopes_supported":["profile"," email ","profile","","   "]}'
    )

    def do_GET(self) -> None:
        if self.path == "/.well-known/oauth-authorization-server/mcp":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(self.response_body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, _format: str, *_args: object) -> None:
        return


@pytest.fixture
def discovery_server() -> str:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _DiscoveryHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/mcp"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_foundation_items_use_rust_module_owners() -> None:
    assert StreamableHttpOAuthDiscovery.__module__ == "pycodex.rmcp_client.auth_status"
    assert determine_streamable_http_auth_status.__module__ == "pycodex.rmcp_client.auth_status"
    assert InProcessTransportFactory.__module__ == "pycodex.rmcp_client.in_process_transport"
    assert McpAuthStatus is ProtocolMcpAuthStatus


def test_discover_streamable_http_oauth_normalizes_scopes(
    discovery_server: str,
) -> None:
    discovery = asyncio.run(discover_streamable_http_oauth(discovery_server))
    assert discovery == StreamableHttpOAuthDiscovery(
        scopes_supported=("profile", "email")
    )
    assert asyncio.run(supports_oauth_login(discovery_server))


def test_determine_auth_status_prefers_static_and_environment_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    static = asyncio.run(
        determine_streamable_http_auth_status(
            "server",
            "not-a-url",
            http_headers={"Authorization": "Bearer token"},
        )
    )
    assert static is McpAuthStatus.BEARER_TOKEN

    monkeypatch.setenv("CODEX_RMCP_CLIENT_AUTH_STATUS_TEST_TOKEN", "Bearer token")
    from_env = asyncio.run(
        determine_streamable_http_auth_status(
            "server",
            "not-a-url",
            env_http_headers={
                "Authorization": "CODEX_RMCP_CLIENT_AUTH_STATUS_TEST_TOKEN"
            },
        )
    )
    assert from_env is McpAuthStatus.BEARER_TOKEN


def test_rmcp_utils_preserve_local_remote_environment_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXTRA_RMCP_ENV", "from-env")
    monkeypatch.setenv("REMOTE_ONLY_RMCP_ENV", "must-not-cross")
    monkeypatch.setenv("LOCAL_RMCP_ENV", "from-local")

    local = create_env_for_mcp_server(
        {"TZ": "custom"},
        (McpServerEnvVar("EXTRA_RMCP_ENV"),),
    )
    assert local["TZ"] == "custom"
    assert local["EXTRA_RMCP_ENV"] == "from-env"

    env_vars = (
        McpServerEnvVar("REMOTE_ONLY_RMCP_ENV", "remote"),
        McpServerEnvVar("LOCAL_RMCP_ENV", "local"),
    )
    remote = create_env_overlay_for_remote_mcp_server(None, env_vars)
    assert remote == {"LOCAL_RMCP_ENV": "from-local"}
    assert remote_mcp_env_var_names(env_vars) == ("REMOTE_ONLY_RMCP_ENV",)

    with pytest.raises(ValueError, match="requires remote MCP stdio"):
        create_env_for_mcp_server(None, env_vars)


def test_build_default_headers_skips_invalid_and_empty_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RMCP_HEADER", "Bearer env")
    monkeypatch.setenv("RMCP_EMPTY_HEADER", "   ")
    headers = build_default_headers(
        {"X-Static": "value", "bad header": "ignored"},
        {
            "Authorization": "RMCP_HEADER",
            "X-Empty": "RMCP_EMPTY_HEADER",
            "X-Missing": "RMCP_MISSING_HEADER",
        },
    )
    assert headers == {
        "x-static": "value",
        "authorization": "Bearer env",
    }
    assert "RMCP_MISSING_HEADER" not in os.environ

