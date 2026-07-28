from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path

import pytest

from pycodex.app_server_transport.transport.auth import AppServerWebsocketAuthArgs
from pycodex.app_server_transport.transport.auth import AppServerWebsocketAuthConfig
from pycodex.app_server_transport.transport.auth import AppServerWebsocketAuthSettings
from pycodex.app_server_transport.transport.auth import AppServerWebsocketCapabilityTokenSource
from pycodex.app_server_transport.transport.auth import WebsocketAuthCliMode
from pycodex.app_server_transport.transport.auth import WebsocketAuthError
from pycodex.app_server_transport.transport.auth import WebsocketAuthPolicy
from pycodex.app_server_transport.transport.auth import authorize_upgrade
from pycodex.app_server_transport.transport.auth import (
    is_unauthenticated_non_loopback_listener,
)
from pycodex.app_server_transport.transport.auth import policy_from_settings


def test_capability_token_args_require_a_source() -> None:
    with pytest.raises(ValueError, match="--ws-token-file"):
        AppServerWebsocketAuthArgs(
            ws_auth=WebsocketAuthCliMode.CAPABILITY_TOKEN
        ).try_into_settings()


def test_capability_token_hash_policy_authorizes_only_matching_token() -> None:
    digest = hashlib.sha256(b"super-secret-token").digest()
    settings = AppServerWebsocketAuthSettings(
        AppServerWebsocketAuthConfig.capability_token(
            AppServerWebsocketCapabilityTokenSource.from_sha256(digest)
        )
    )
    policy = policy_from_settings(settings)

    authorize_upgrade(
        {"Authorization": "Bearer super-secret-token"},
        policy,
    )
    with pytest.raises(WebsocketAuthError, match="invalid websocket bearer token"):
        authorize_upgrade({"Authorization": "Bearer wrong-token"}, policy)


def test_signed_bearer_args_trim_claims_and_default_skew(tmp_path: Path) -> None:
    secret = tmp_path / "secret"

    settings = AppServerWebsocketAuthArgs(
        ws_auth=WebsocketAuthCliMode.SIGNED_BEARER_TOKEN,
        ws_shared_secret_file=secret,
        ws_issuer=" issuer ",
        ws_audience="   ",
    ).try_into_settings()

    assert settings.config is not None
    assert settings.config.issuer == "issuer"
    assert settings.config.audience is None
    assert settings.config.max_clock_skew_seconds == 30


def test_signed_bearer_policy_rejects_short_secret(tmp_path: Path) -> None:
    secret = tmp_path / "secret"
    secret.write_text("too-short", encoding="utf-8")
    settings = AppServerWebsocketAuthSettings(
        AppServerWebsocketAuthConfig.signed_bearer_token(secret)
    )

    with pytest.raises(ValueError, match="at least 32 bytes"):
        policy_from_settings(settings)


def test_signed_bearer_authorizes_valid_hs256_token(tmp_path: Path) -> None:
    secret_value = b"0123456789abcdef0123456789abcdef"
    secret = tmp_path / "secret"
    secret.write_bytes(secret_value)
    policy = policy_from_settings(
        AppServerWebsocketAuthSettings(
            AppServerWebsocketAuthConfig.signed_bearer_token(
                secret,
                issuer="issuer",
                audience="audience",
            )
        )
    )
    token = _signed_token(
        secret_value,
        {"exp": int(time.time()) + 60, "iss": "issuer", "aud": ["audience"]},
    )

    authorize_upgrade({"authorization": f"Bearer {token}"}, policy)


def test_detects_unauthenticated_non_loopback_listener() -> None:
    policy = WebsocketAuthPolicy()

    assert is_unauthenticated_non_loopback_listener("0.0.0.0:8765", policy)
    assert not is_unauthenticated_non_loopback_listener("127.0.0.1:8765", policy)


def _signed_token(secret: bytes, claims: dict[str, object]) -> str:
    header = _encode(b'{"alg":"HS256","typ":"JWT"}')
    payload = _encode(json.dumps(claims, separators=(",", ":")).encode())
    signed = f"{header}.{payload}".encode()
    signature = _encode(hmac.new(secret, signed, hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")
