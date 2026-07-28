from __future__ import annotations

import json
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from pycodex.config.types import OAuthCredentialsStoreMode
from pycodex.rmcp_client.oauth import load_oauth_tokens
from pycodex.rmcp_client.perform_oauth_login import (
    CallbackOutcome,
    OAuthProviderError,
    append_callback_id_to_redirect_uri,
    append_query_param,
    callback_id_from_server_url,
    callback_path_from_redirect_uri,
    parse_oauth_callback,
    perform_oauth_login_return_url,
)


def test_oauth_provider_error_display() -> None:
    assert (
        str(OAuthProviderError("access_denied", "No access"))
        == "OAuth provider returned `access_denied`: No access"
    )
    assert str(OAuthProviderError("access_denied", None)) == "OAuth provider returned `access_denied`"
    assert str(OAuthProviderError(None, "No access")) == "OAuth error: No access"


def test_callback_helpers_match_rust_contract() -> None:
    callback_id = callback_id_from_server_url("https://example.test/mcp#fragment")
    assert callback_id == callback_id_from_server_url("https://example.test/mcp")
    redirect = append_callback_id_to_redirect_uri(
        "http://127.0.0.1:1234/callback?source=test",
        callback_id,
    )
    assert callback_path_from_redirect_uri(redirect) == f"/callback/{callback_id}"
    assert "source=test" in redirect
    assert append_query_param("https://example.test/auth", "resource", "mcp://one").endswith(
        "resource=mcp%3A%2F%2Fone"
    )


def test_parse_oauth_callback_success_error_and_invalid() -> None:
    success = parse_oauth_callback(
        "/callback/server?code=abc%20123&state=state",
        "/callback/server",
    )
    assert success.kind == "success"
    assert success.code == "abc 123"
    assert success.state == "state"

    error = parse_oauth_callback(
        "/callback/server?error=access_denied&error_description=No%20access",
        "/callback/server",
    )
    assert error.kind == "error"
    assert isinstance(error.error, OAuthProviderError)
    assert parse_oauth_callback("/wrong?code=x&state=y", "/callback/server") == CallbackOutcome.invalid()


class _OAuthHandler(BaseHTTPRequestHandler):
    server: "_OAuthServer"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:
        if ".well-known/oauth-authorization-server" not in self.path:
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(
            {
                "authorization_endpoint": f"{self.server.base_url}/authorize",
                "token_endpoint": f"{self.server.base_url}/token",
                "scopes_supported": ["profile"],
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path != "/token":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", "0"))
        self.server.token_request = urllib.parse.parse_qs(
            self.rfile.read(length).decode()
        )
        body = json.dumps(
            {
                "access_token": "oauth-access",
                "refresh_token": "oauth-refresh",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "profile",
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _OAuthServer(ThreadingHTTPServer):
    token_request: dict[str, list[str]] | None = None

    @property
    def base_url(self) -> str:
        host, port = self.server_address
        return f"http://{host}:{port}"


@pytest.mark.asyncio
async def test_oauth_return_url_completes_callback_and_persists_tokens(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    server = _OAuthServer(("127.0.0.1", 0), _OAuthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        handle = await perform_oauth_login_return_url(
            server_name="fixture",
            server_url=f"{server.base_url}/mcp",
            store_mode=OAuthCredentialsStoreMode.FILE,
            http_headers=None,
            env_http_headers=None,
            scopes=("profile",),
            oauth_client_id="configured-client",
            oauth_resource="mcp://fixture",
            timeout_secs=5,
            callback_port=None,
            callback_url=None,
        )
        query = urllib.parse.parse_qs(
            urllib.parse.urlsplit(handle.authorization_url()).query
        )
        redirect_uri = query["redirect_uri"][0]
        state = query["state"][0]
        await __import__("asyncio").to_thread(
            urllib.request.urlopen,
            f"{redirect_uri}?code=code-1&state={urllib.parse.quote(state)}",
        )
        await handle.wait()

        stored = load_oauth_tokens(
            "fixture",
            f"{server.base_url}/mcp",
            OAuthCredentialsStoreMode.FILE,
        )
        assert stored is not None
        assert stored.token_response.response.access_token == "oauth-access"
        assert server.token_request is not None
        assert server.token_request["code"] == ["code-1"]
        assert server.token_request["client_id"] == ["configured-client"]
        assert query["resource"] == ["mcp://fixture"]
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

