from __future__ import annotations

import pytest

from pycodex.login.auth.revoke import (
    CLIENT_ID,
    REFRESH_TOKEN_URL_OVERRIDE_ENV_VAR,
    REVOKE_TOKEN_URL,
    REVOKE_TOKEN_URL_OVERRIDE_ENV_VAR,
    RevokeHttpResponse,
    RevokeTokenKind,
    derive_revoke_token_endpoint,
    managed_chatgpt_tokens,
    resolved_auth_mode,
    revocable_token,
    revoke_auth_tokens,
    revoke_oauth_token,
    revoke_token_endpoint,
    should_revoke_auth_tokens,
)
from pycodex.login.auth.storage import AuthDotJson
from pycodex.login.token_data import TokenData


class FakeRevokeClient:
    def __init__(self, response: RevokeHttpResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, str], float]] = []

    async def post_json(self, endpoint: str, payload: dict[str, str], timeout: float) -> RevokeHttpResponse:
        self.calls.append((endpoint, payload, timeout))
        return self.response


def _tokens(access: str = "access-token", refresh: str = "refresh-token") -> TokenData:
    return TokenData(access_token=access, refresh_token=refresh)


def test_resolved_auth_mode_matches_rust_defaulting_rules():
    # Rust crate: codex-login
    # Rust module: src/auth/revoke.rs
    # Contract: resolved_auth_mode defaults to ChatGPT, but API key wins.
    assert resolved_auth_mode(AuthDotJson(tokens=_tokens())) == "chatgpt"
    assert resolved_auth_mode(AuthDotJson(auth_mode="api_key", tokens=_tokens())) == "api_key"
    assert resolved_auth_mode(AuthDotJson(openai_api_key="sk-test", tokens=_tokens())) == "api_key"


def test_managed_chatgpt_tokens_filters_non_chatgpt_auth():
    # Rust contract: managed_chatgpt_tokens only returns tokens for ChatGPT auth.
    auth = AuthDotJson(auth_mode="chatgpt", tokens=_tokens())
    assert managed_chatgpt_tokens(auth) is auth.tokens
    assert managed_chatgpt_tokens(AuthDotJson(auth_mode="api_key", tokens=_tokens())) is None


def test_revocable_token_prefers_refresh_then_access():
    # Rust contract: revocable_token prefers refresh token over access token.
    assert revocable_token(None) is None
    assert revocable_token(AuthDotJson(tokens=_tokens("access", "refresh"))) == (
        "refresh",
        RevokeTokenKind.REFRESH,
    )
    assert revocable_token(AuthDotJson(tokens=_tokens("access", ""))) == ("access", RevokeTokenKind.ACCESS)
    assert revocable_token(AuthDotJson(tokens=_tokens("", ""))) is None
    assert revocable_token(AuthDotJson(auth_mode="api_key", tokens=_tokens("access", "refresh"))) is None


def test_should_revoke_auth_tokens_matches_replacement_rules():
    # Rust contract: should_revoke_auth_tokens compares the token selected from old auth.
    old_refresh = AuthDotJson(tokens=_tokens("old-access", "old-refresh"))
    same_refresh = AuthDotJson(tokens=_tokens("new-access", "old-refresh"))
    new_refresh = AuthDotJson(tokens=_tokens("new-access", "new-refresh"))
    no_managed_replacement = AuthDotJson(auth_mode="api_key", tokens=_tokens("old-access", "old-refresh"))

    assert should_revoke_auth_tokens(None, new_refresh) is False
    assert should_revoke_auth_tokens(old_refresh, same_refresh) is False
    assert should_revoke_auth_tokens(old_refresh, new_refresh) is True
    assert should_revoke_auth_tokens(old_refresh, no_managed_replacement) is True

    old_access = AuthDotJson(tokens=_tokens("old-access", ""))
    same_access = AuthDotJson(tokens=_tokens("old-access", "replacement-refresh"))
    new_access = AuthDotJson(tokens=_tokens("new-access", "replacement-refresh"))
    assert should_revoke_auth_tokens(old_access, same_access) is False
    assert should_revoke_auth_tokens(old_access, new_access) is True


def test_derive_revoke_url_from_refresh_token_override():
    # Rust test: derives_revoke_url_from_refresh_token_override
    assert (
        derive_revoke_token_endpoint("http://127.0.0.1:1234/oauth/token?unified=true")
        == "http://127.0.0.1:1234/oauth/revoke"
    )
    assert derive_revoke_token_endpoint("not a url") is None


def test_revoke_token_endpoint_override_precedence():
    # Rust contract: revoke override wins, then derived refresh override, then default.
    assert (
        revoke_token_endpoint(
            {
                REVOKE_TOKEN_URL_OVERRIDE_ENV_VAR: "http://localhost/revoke",
                REFRESH_TOKEN_URL_OVERRIDE_ENV_VAR: "http://localhost/oauth/token",
            }
        )
        == "http://localhost/revoke"
    )
    assert (
        revoke_token_endpoint({REFRESH_TOKEN_URL_OVERRIDE_ENV_VAR: "http://localhost/oauth/token?x=1"})
        == "http://localhost/oauth/revoke"
    )
    assert revoke_token_endpoint({}) == REVOKE_TOKEN_URL


@pytest.mark.asyncio
async def test_revoke_oauth_token_sends_refresh_payload_with_client_id():
    # Rust contract: refresh revoke requests include client_id and refresh token hint.
    client = FakeRevokeClient(RevokeHttpResponse(200))

    await revoke_oauth_token(
        "http://localhost/oauth/revoke",
        "refresh-token",
        RevokeTokenKind.REFRESH,
        1.5,
        client=client,
    )

    assert client.calls == [
        (
            "http://localhost/oauth/revoke",
            {
                "token": "refresh-token",
                "token_type_hint": "refresh_token",
                "client_id": CLIENT_ID,
            },
            1.5,
        )
    ]


@pytest.mark.asyncio
async def test_revoke_oauth_token_sends_access_payload_without_client_id():
    # Rust contract: access revoke requests omit client_id.
    client = FakeRevokeClient(RevokeHttpResponse(200))

    await revoke_oauth_token(
        "http://localhost/oauth/revoke",
        "access-token",
        RevokeTokenKind.ACCESS,
        client=client,
    )

    assert client.calls[0][1] == {"token": "access-token", "token_type_hint": "access_token"}


@pytest.mark.asyncio
async def test_revoke_oauth_token_wraps_error_message():
    # Rust contract: failed revoke parses nested OpenAI error messages.
    client = FakeRevokeClient(RevokeHttpResponse(400, '{"error":{"message":"bad token"}}'))

    with pytest.raises(OSError, match="failed to revoke refresh_token: 400: bad token"):
        await revoke_oauth_token(
            "http://localhost/oauth/revoke",
            "refresh-token",
            RevokeTokenKind.REFRESH,
            client=client,
        )


@pytest.mark.asyncio
async def test_revoke_auth_tokens_is_noop_without_revocable_token():
    # Rust contract: revoke_auth_tokens returns Ok for missing or empty managed tokens.
    client = FakeRevokeClient(RevokeHttpResponse(200))

    await revoke_auth_tokens(None, client=client)
    await revoke_auth_tokens(AuthDotJson(tokens=_tokens("", "")), client=client)

    assert client.calls == []


@pytest.mark.asyncio
async def test_revoke_auth_tokens_uses_selected_refresh_token(monkeypatch):
    # Rust contract: revoke_auth_tokens selects revocable_token and revoke_token_endpoint.
    client = FakeRevokeClient(RevokeHttpResponse(200))
    monkeypatch.setenv(REVOKE_TOKEN_URL_OVERRIDE_ENV_VAR, "http://localhost/oauth/revoke")

    await revoke_auth_tokens(AuthDotJson(tokens=_tokens("access-token", "refresh-token")), client=client)

    assert client.calls[0][0] == "http://localhost/oauth/revoke"
    assert client.calls[0][1]["token"] == "refresh-token"
