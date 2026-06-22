from __future__ import annotations

import base64
import json
from datetime import datetime, timezone

import pytest

from pycodex.login.auth.external_bearer import ExternalAuthTokens
from pycodex.login.auth.manager import (
    AUTH_MODE_API_KEY,
    AUTH_MODE_CHATGPT,
    AUTH_MODE_CHATGPT_AUTH_TOKENS,
    AuthConfig,
    AuthManager,
    CodexAuth,
    ExternalAuthChatgptMetadata,
    ManagerExternalAuthTokens,
    auth_dot_json_from_external_tokens,
    classify_refresh_token_failure,
    enforce_login_restrictions,
    extract_refresh_token_error_code,
    load_auth,
    login_with_api_key,
    read_codex_access_token_from_env,
    read_codex_api_key_from_env,
    read_openai_api_key_from_env,
    refresh_token_endpoint,
    resolved_mode,
    storage_mode,
)
from pycodex.login.auth.storage import AuthDotJson, FileAuthStorage
from pycodex.login.token_data import TokenData
from pycodex.protocol.auth import RefreshTokenFailedReason


def _jwt(payload: dict[str, object]) -> str:
    def encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

    return ".".join(
        [
            encode(b'{"alg":"none","typ":"JWT"}'),
            encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
            "sig",
        ]
    )


def _chatgpt_jwt(account_id: str = "acct") -> str:
    return _jwt(
        {
            "email": "user@example.com",
            "https://api.openai.com/auth": {
                "chatgpt_plan_type": "plus",
                "chatgpt_user_id": "user-id",
                "chatgpt_account_id": account_id,
            },
        }
    )


def test_env_key_readers_trim_and_ignore_blank_values() -> None:
    # Source: codex/codex-rs/login/src/auth/manager.rs
    # Rust crate: codex-login
    # Rust module: src/auth/manager.rs
    # Contract: read_*_from_env trims Unicode strings and treats empty values as unset.
    env = {
        "OPENAI_API_KEY": "  sk-openai  ",
        "CODEX_API_KEY": " \t ",
        "CODEX_ACCESS_TOKEN": " token ",
    }

    assert read_openai_api_key_from_env(env) == "sk-openai"
    assert read_codex_api_key_from_env(env) is None
    assert read_codex_access_token_from_env(env) == "token"


def test_resolved_and_storage_mode_match_auth_dot_json_rules() -> None:
    # Rust tests: resolved_mode/storage_mode source-contract coverage.
    assert resolved_mode(AuthDotJson(openai_api_key="sk-test")) == AUTH_MODE_API_KEY
    assert resolved_mode(AuthDotJson(tokens=TokenData())) == AUTH_MODE_CHATGPT
    external = AuthDotJson(auth_mode=AUTH_MODE_CHATGPT_AUTH_TOKENS)
    assert storage_mode(external, "file") == "ephemeral"


def test_login_with_api_key_overwrites_file_auth(tmp_path) -> None:
    # Rust contract: login_with_api_key saves API-key auth through the selected storage backend.
    FileAuthStorage(tmp_path).save(AuthDotJson(auth_mode=AUTH_MODE_CHATGPT, tokens=TokenData()))

    login_with_api_key(tmp_path, "sk-new", "file")

    assert FileAuthStorage(tmp_path).load() == AuthDotJson(auth_mode=AUTH_MODE_API_KEY, openai_api_key="sk-new")


def test_refresh_token_error_classification_matches_rust_codes() -> None:
    # Rust tests: refresh token failure classification branches in auth/manager.rs.
    expired = classify_refresh_token_failure('{"error":{"code":"refresh_token_expired"}}')
    reused = classify_refresh_token_failure('{"error":"refresh_token_reused"}')
    invalidated = classify_refresh_token_failure('{"code":"refresh_token_invalidated"}')
    other = classify_refresh_token_failure("not json")

    assert expired.reason is RefreshTokenFailedReason.EXPIRED
    assert reused.reason is RefreshTokenFailedReason.EXHAUSTED
    assert invalidated.reason is RefreshTokenFailedReason.REVOKED
    assert other.reason is RefreshTokenFailedReason.OTHER
    assert extract_refresh_token_error_code('{"error":{"code":"refresh_token_expired"}}') == "refresh_token_expired"


def test_refresh_token_endpoint_prefers_override() -> None:
    # Rust contract: refresh_token_endpoint honors CODEX_REFRESH_TOKEN_URL_OVERRIDE.
    assert refresh_token_endpoint({"CODEX_REFRESH_TOKEN_URL_OVERRIDE": "https://example.invalid/token"}) == "https://example.invalid/token"


def test_external_chatgpt_tokens_require_metadata_and_build_auth_json() -> None:
    # Rust contract: AuthDotJson::from(ExternalAuthTokens) requires ChatGPT metadata.
    access_token = _chatgpt_jwt("jwt-acct")
    auth = auth_dot_json_from_external_tokens(
        ManagerExternalAuthTokens(access_token, ExternalAuthChatgptMetadata(account_id="metadata-acct"))
    )

    assert auth.auth_mode == AUTH_MODE_CHATGPT_AUTH_TOKENS
    assert auth.tokens is not None
    assert auth.tokens.access_token == access_token
    assert auth.tokens.account_id == "metadata-acct"

    with pytest.raises(OSError, match="missing ChatGPT metadata"):
        auth_dot_json_from_external_tokens(ExternalAuthTokens.access_token_only(access_token))


@pytest.mark.asyncio
async def test_load_auth_prefers_codex_api_key_env_over_storage(tmp_path, monkeypatch) -> None:
    # Rust contract: load_auth checks CODEX_API_KEY before persisted auth when enabled.
    FileAuthStorage(tmp_path).save(AuthDotJson(auth_mode=AUTH_MODE_CHATGPT, tokens=TokenData()))
    monkeypatch.setenv("CODEX_API_KEY", "sk-env")

    auth = await load_auth(tmp_path, True, "file")

    assert auth == CodexAuth.from_api_key("sk-env")


@pytest.mark.asyncio
async def test_auth_manager_reload_tracks_changed_auth(tmp_path) -> None:
    # Rust contract: AuthManager::reload updates cached auth and reports whether it changed.
    login_with_api_key(tmp_path, "sk-one", "file")
    manager = await AuthManager.new(tmp_path, False, "file")
    assert manager.auth_cached() == CodexAuth.from_api_key("sk-one")

    login_with_api_key(tmp_path, "sk-two", "file")

    assert await manager.reload() is True
    assert manager.auth_cached() == CodexAuth.from_api_key("sk-two")
    assert await manager.reload() is False


@pytest.mark.asyncio
async def test_enforce_login_restrictions_logs_out_wrong_mode(tmp_path) -> None:
    # Rust contract: enforce_login_restrictions removes invalid persisted credentials before erroring.
    login_with_api_key(tmp_path, "sk-test", "file")

    with pytest.raises(OSError, match="ChatGPT login is required"):
        await enforce_login_restrictions(
            AuthConfig(
                codex_home=tmp_path,
                auth_credentials_store_mode="file",
                forced_login_method="chatgpt",
            )
        )

    assert FileAuthStorage(tmp_path).load() is None


def test_codex_auth_chatgpt_accessors() -> None:
    # Rust contract: CodexAuth exposes token/account metadata for ChatGPT auth variants.
    tokens = TokenData.from_mapping(
        {
            "id_token": _chatgpt_jwt("acct"),
            "access_token": _jwt({"exp": int(datetime.now(timezone.utc).timestamp()) + 3600}),
            "refresh_token": "refresh",
            "account_id": "acct",
        }
    )
    auth = CodexAuth.from_chatgpt(AuthDotJson(auth_mode=AUTH_MODE_CHATGPT, tokens=tokens, last_refresh=datetime.now(timezone.utc)), FileAuthStorage("."))

    assert auth.auth_mode() == AUTH_MODE_CHATGPT
    assert auth.api_auth_mode() == AUTH_MODE_CHATGPT
    assert auth.uses_codex_backend() is True
    assert auth.get_token() == tokens.access_token
    assert auth.get_account_id() == "acct"
    assert auth.get_account_email() == "user@example.com"
    assert auth.get_chatgpt_user_id() == "user-id"
    assert auth.is_workspace_account() is False
