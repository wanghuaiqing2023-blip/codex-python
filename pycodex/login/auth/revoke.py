"""Port of Rust ``codex-login::auth::revoke``.

Rust source:
- ``codex/codex-rs/login/src/auth/revoke.rs``
"""

from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from pycodex.login.auth.storage import AuthDotJson
from pycodex.login.auth.util import try_parse_error_message
from pycodex.login.token_data import TokenData


CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
REFRESH_TOKEN_URL_OVERRIDE_ENV_VAR = "CODEX_REFRESH_TOKEN_URL_OVERRIDE"
REVOKE_TOKEN_URL = "https://auth.openai.com/oauth/revoke"
REVOKE_TOKEN_URL_OVERRIDE_ENV_VAR = "CODEX_REVOKE_TOKEN_URL_OVERRIDE"
REVOKE_HTTP_TIMEOUT_SECONDS = 10.0


class RevokeTokenKind(Enum):
    ACCESS = "access_token"
    REFRESH = "refresh_token"

    def as_str(self) -> str:
        return self.value

    def client_id(self) -> str | None:
        if self is RevokeTokenKind.REFRESH:
            return CLIENT_ID
        return None


@dataclass(frozen=True)
class RevokeTokenRequest:
    token: str
    token_type_hint: str
    client_id: str | None = None

    @classmethod
    def from_token(cls, token: str, kind: RevokeTokenKind) -> "RevokeTokenRequest":
        return cls(token=token, token_type_hint=kind.as_str(), client_id=kind.client_id())

    def to_json_dict(self) -> dict[str, str]:
        result = {"token": self.token, "token_type_hint": self.token_type_hint}
        if self.client_id is not None:
            result["client_id"] = self.client_id
        return result


class RevokeHttpClient(Protocol):
    async def post_json(self, endpoint: str, payload: dict[str, str], timeout: float) -> "RevokeHttpResponse":
        ...


@dataclass(frozen=True)
class RevokeHttpResponse:
    status: int
    body: str = ""

    def is_success(self) -> bool:
        return 200 <= self.status <= 299


async def revoke_auth_tokens(
    auth_dot_json: AuthDotJson | None,
    *,
    client: RevokeHttpClient | None = None,
) -> None:
    revocable = revocable_token(auth_dot_json)
    if revocable is None:
        return
    token, kind = revocable
    await revoke_oauth_token(
        revoke_token_endpoint(),
        token,
        kind,
        REVOKE_HTTP_TIMEOUT_SECONDS,
        client=client,
    )


def should_revoke_auth_tokens(auth_dot_json: AuthDotJson | None, replacement_auth: AuthDotJson) -> bool:
    revocable = revocable_token(auth_dot_json)
    if revocable is None:
        return False
    token, kind = revocable
    replacement_tokens = managed_chatgpt_tokens(replacement_auth)
    if replacement_tokens is None:
        return True
    if kind is RevokeTokenKind.ACCESS:
        return replacement_tokens.access_token != token
    return replacement_tokens.refresh_token != token


def revocable_token(auth_dot_json: AuthDotJson | None) -> tuple[str, RevokeTokenKind] | None:
    if auth_dot_json is None:
        return None
    tokens = managed_chatgpt_tokens(auth_dot_json)
    if tokens is None:
        return None
    if tokens.refresh_token:
        return tokens.refresh_token, RevokeTokenKind.REFRESH
    if tokens.access_token:
        return tokens.access_token, RevokeTokenKind.ACCESS
    return None


def managed_chatgpt_tokens(auth_dot_json: AuthDotJson) -> TokenData | None:
    if resolved_auth_mode(auth_dot_json) == "chatgpt":
        return auth_dot_json.tokens
    return None


def resolved_auth_mode(auth_dot_json: AuthDotJson) -> str:
    if auth_dot_json.auth_mode is not None:
        return _auth_mode_value(auth_dot_json.auth_mode)
    if auth_dot_json.openai_api_key is not None:
        return "api_key"
    return "chatgpt"


async def revoke_oauth_token(
    endpoint: str,
    token: str,
    kind: RevokeTokenKind,
    timeout: float = REVOKE_HTTP_TIMEOUT_SECONDS,
    *,
    client: RevokeHttpClient | None = None,
) -> None:
    request = RevokeTokenRequest.from_token(token, kind)
    payload = request.to_json_dict()
    if client is None:
        response = await _post_json_with_urllib(endpoint, payload, timeout)
    else:
        response = await client.post_json(endpoint, payload, timeout)
    if response.is_success():
        return
    message = try_parse_error_message(response.body)
    raise OSError(f"failed to revoke {kind.as_str()}: {response.status}: {message}")


def revoke_token_endpoint(env: dict[str, str] | None = None) -> str:
    env_map = os.environ if env is None else env
    endpoint = env_map.get(REVOKE_TOKEN_URL_OVERRIDE_ENV_VAR)
    if endpoint is not None:
        return endpoint
    refresh_endpoint = env_map.get(REFRESH_TOKEN_URL_OVERRIDE_ENV_VAR)
    if refresh_endpoint is not None:
        derived = derive_revoke_token_endpoint(refresh_endpoint)
        if derived is not None:
            return derived
    return REVOKE_TOKEN_URL


def derive_revoke_token_endpoint(refresh_endpoint: str) -> str | None:
    parsed = urllib.parse.urlsplit(refresh_endpoint)
    if not parsed.scheme or not parsed.netloc:
        return None
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "/oauth/revoke", "", ""))


async def _post_json_with_urllib(endpoint: str, payload: dict[str, str], timeout: float) -> RevokeHttpResponse:
    return await asyncio.to_thread(_post_json_with_urllib_sync, endpoint, payload, timeout)


def _post_json_with_urllib_sync(endpoint: str, payload: dict[str, str], timeout: float) -> RevokeHttpResponse:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return RevokeHttpResponse(response.status, response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as error:
        return RevokeHttpResponse(error.code, error.read().decode("utf-8", "replace"))
    except Exception as exc:
        raise OSError(exc) from exc


def _auth_mode_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    raw = getattr(value, "value", None)
    if isinstance(raw, str):
        return raw
    return str(value)


__all__ = [
    "CLIENT_ID",
    "REFRESH_TOKEN_URL_OVERRIDE_ENV_VAR",
    "REVOKE_HTTP_TIMEOUT_SECONDS",
    "REVOKE_TOKEN_URL",
    "REVOKE_TOKEN_URL_OVERRIDE_ENV_VAR",
    "RevokeHttpResponse",
    "RevokeTokenKind",
    "RevokeTokenRequest",
    "derive_revoke_token_endpoint",
    "managed_chatgpt_tokens",
    "resolved_auth_mode",
    "revocable_token",
    "revoke_auth_tokens",
    "revoke_oauth_token",
    "revoke_token_endpoint",
    "should_revoke_auth_tokens",
]
