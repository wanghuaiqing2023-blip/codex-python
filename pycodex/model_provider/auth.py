"""Port of Rust ``codex-model-provider::auth``.

Rust source:
- ``codex/codex-rs/model-provider/src/auth.rs``
"""

from __future__ import annotations

from typing import Any

from pycodex.agent_identity import (
    AgentIdentityKey,
    AgentTaskAuthorizationTarget,
    authorization_header_for_agent_task,
)
from pycodex.login.auth.agent_identity import AgentIdentityAuth
from pycodex.login.auth.external_bearer import BearerTokenRefresher
from pycodex.model_provider.bearer_auth_provider import BearerAuthProvider, _valid_header_value
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentIdentityAuthProvider:
    auth: AgentIdentityAuth
    signer: Any | None = None

    def add_auth_headers(self, headers: dict[str, str]) -> None:
        record = self.auth.record()
        identity_key = AgentIdentityKey(
            agent_runtime_id=record.agent_runtime_id,
            private_key_pkcs8_base64=record.agent_private_key,
        )
        target = AgentTaskAuthorizationTarget(
            agent_runtime_id=record.agent_runtime_id,
            task_id=self.auth.process_task_id(),
        )
        signer = self.signer or authorization_header_for_agent_task
        try:
            header_value = signer(identity_key, target)
        except Exception:
            header_value = None
        if header_value is not None and _valid_header_value(str(header_value)):
            headers["Authorization"] = str(header_value)
        account_id = self.auth.account_id()
        if _valid_header_value(account_id):
            headers["ChatGPT-Account-ID"] = account_id
        if self.auth.is_fedramp_account():
            headers["X-OpenAI-Fedramp"] = "true"

    def to_auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        self.add_auth_headers(headers)
        return headers


@dataclass(frozen=True)
class UnauthenticatedAuthProvider:
    def add_auth_headers(self, headers: dict[str, str]) -> None:
        return None

    def to_auth_headers(self) -> dict[str, str]:
        return {}


def unauthenticated_auth_provider() -> UnauthenticatedAuthProvider:
    return UnauthenticatedAuthProvider()


def auth_manager_for_provider(auth_manager: Any | None, provider: Any) -> Any | None:
    config = _get(provider, "auth")
    if config is not None:
        return BearerTokenRefresher.new(config)
    return auth_manager


def resolve_provider_auth(auth: Any | None, provider: Any) -> Any:
    bearer = bearer_auth_for_provider(provider)
    if bearer is not None:
        return bearer
    if auth is not None:
        return auth_provider_from_auth(auth)
    return unauthenticated_auth_provider()


def bearer_auth_for_provider(provider: Any) -> BearerAuthProvider | None:
    api_key_method = getattr(provider, "api_key", None)
    if callable(api_key_method):
        api_key = api_key_method()
        if api_key is not None:
            return BearerAuthProvider.new(api_key)

    experimental_bearer_token = _get(provider, "experimental_bearer_token")
    if experimental_bearer_token is not None:
        return BearerAuthProvider.new(str(experimental_bearer_token))
    return None


def auth_provider_from_auth(auth: Any) -> Any:
    if isinstance(auth, AgentIdentityAuth):
        return AgentIdentityAuthProvider(auth=auth)

    token_method = getattr(auth, "get_token", None)
    token = token_method() if callable(token_method) else _get(auth, "token")
    account_method = getattr(auth, "get_account_id", None)
    account_id = account_method() if callable(account_method) else _get(auth, "account_id")
    tokens = _get(auth, "tokens")
    if isinstance(tokens, dict):
        token = token or tokens.get("access_token")
        account_id = account_id or tokens.get("account_id")
    fedramp_method = getattr(auth, "is_fedramp_account", None)
    is_fedramp_account = (
        bool(fedramp_method()) if callable(fedramp_method) else bool(_get(auth, "is_fedramp_account", False))
    )
    if isinstance(auth, str):
        token = auth
    return BearerAuthProvider(
        token=token,
        account_id=account_id,
        is_fedramp_account=is_fedramp_account,
    )


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


__all__ = [
    "AgentIdentityAuthProvider",
    "BearerAuthProvider",
    "UnauthenticatedAuthProvider",
    "auth_manager_for_provider",
    "auth_provider_from_auth",
    "bearer_auth_for_provider",
    "resolve_provider_auth",
    "unauthenticated_auth_provider",
]
