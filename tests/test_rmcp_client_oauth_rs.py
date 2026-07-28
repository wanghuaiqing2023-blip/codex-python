from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from pycodex.config.types import OAuthCredentialsStoreMode
from pycodex.rmcp_client.oauth import (
    OAuthPersistor,
    OAuthTokenResponse,
    StoredOAuthTokens,
    WrappedOAuthTokenResponse,
    compute_expires_at_millis,
    compute_store_key,
    delete_oauth_tokens,
    has_oauth_tokens,
    load_oauth_tokens,
    save_oauth_tokens,
)


def _tokens(expires_in: int | None = 3600) -> StoredOAuthTokens:
    response = OAuthTokenResponse(
        access_token="access",
        refresh_token="refresh",
        expires_in=expires_in,
        scopes=("profile", "email"),
    )
    return StoredOAuthTokens(
        server_name="fixture",
        url="https://example.test/mcp",
        client_id="client-id",
        token_response=WrappedOAuthTokenResponse(response),
        expires_at=compute_expires_at_millis(response),
    )


def test_file_store_round_trip_and_delete(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Rust: save/load/delete_oauth_tokens file mode.
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    tokens = _tokens()

    save_oauth_tokens("fixture", tokens, OAuthCredentialsStoreMode.FILE)
    loaded = load_oauth_tokens(
        "fixture",
        "https://example.test/mcp",
        OAuthCredentialsStoreMode.FILE,
    )

    assert loaded is not None
    assert loaded.server_name == tokens.server_name
    assert loaded.client_id == tokens.client_id
    assert loaded.token_response.response.access_token == "access"
    assert loaded.token_response.response.refresh_token == "refresh"
    assert loaded.token_response.response.scopes == ("profile", "email")
    assert loaded.token_response.response.expires_in is not None
    assert has_oauth_tokens(
        "fixture",
        "https://example.test/mcp",
        OAuthCredentialsStoreMode.FILE,
    )
    assert delete_oauth_tokens(
        "fixture",
        "https://example.test/mcp",
        OAuthCredentialsStoreMode.FILE,
    )
    assert not (tmp_path / ".credentials.json").exists()


def test_store_key_is_url_bound_and_stable() -> None:
    first = compute_store_key("fixture", "https://example.test/mcp")
    assert first == compute_store_key("fixture", "https://example.test/mcp")
    assert first != compute_store_key("fixture", "https://other.test/mcp")
    assert first.startswith("fixture|")
    assert len(first.rsplit("|", 1)[1]) == 16


def test_expired_tokens_clear_expires_in(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    tokens = _tokens(expires_in=None)
    tokens = StoredOAuthTokens(
        tokens.server_name,
        tokens.url,
        tokens.client_id,
        tokens.token_response,
        int(time.time() * 1000) - 1,
    )
    save_oauth_tokens("fixture", tokens, OAuthCredentialsStoreMode.FILE)
    loaded = load_oauth_tokens(
        "fixture",
        tokens.url,
        OAuthCredentialsStoreMode.FILE,
    )
    assert loaded is not None
    assert loaded.token_response.response.expires_in is None


class _AuthorizationManager:
    def __init__(self) -> None:
        self.credentials: OAuthTokenResponse | None = OAuthTokenResponse(
            "access",
            refresh_token="refresh",
            expires_in=1,
        )
        self.refreshes = 0

    async def get_credentials(self) -> tuple[str, OAuthTokenResponse | None]:
        return "client-id", self.credentials

    async def refresh_token(self) -> None:
        self.refreshes += 1
        self.credentials = OAuthTokenResponse(
            "refreshed",
            refresh_token="refresh",
            expires_in=3600,
        )


@pytest.mark.asyncio
async def test_oauth_persistor_refreshes_and_saves(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    manager = _AuthorizationManager()
    initial = StoredOAuthTokens(
        "fixture",
        "https://example.test/mcp",
        "client-id",
        WrappedOAuthTokenResponse(manager.credentials),
        int(time.time() * 1000),
    )
    persistor = OAuthPersistor(
        "fixture",
        initial.url,
        manager,
        OAuthCredentialsStoreMode.FILE,
        initial,
    )
    await persistor.refresh_if_needed()

    loaded = load_oauth_tokens(
        "fixture",
        initial.url,
        OAuthCredentialsStoreMode.FILE,
    )
    assert manager.refreshes == 1
    assert loaded is not None
    assert loaded.token_response.response.access_token == "refreshed"

