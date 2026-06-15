"""Parity tests for Rust ``codex-login::auth::agent_identity``.

Rust source:
- ``codex/codex-rs/login/src/auth/agent_identity.rs``
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from pycodex.login.auth.agent_identity import (
    CODEX_AGENT_IDENTITY_AUTHAPI_BASE_URL_ENV_VAR,
    PROD_AGENT_IDENTITY_AUTHAPI_BASE_URL,
    AgentIdentityAuth,
    AgentIdentityAuthRecord,
    AgentIdentityKey,
    agent_identity_authapi_base_url,
    key,
)


def _run(coro):
    return asyncio.run(coro)


def _record() -> AgentIdentityAuthRecord:
    return AgentIdentityAuthRecord(
        agent_runtime_id="runtime-123",
        agent_private_key="private-key",
        account_id="account-123",
        chatgpt_user_id="user-123",
        email="user@example.com",
        plan_type="enterprise",
        chatgpt_account_is_fedramp=True,
    )


def test_agent_identity_authapi_base_url_prefers_trimmed_env_value() -> None:
    env = {
        CODEX_AGENT_IDENTITY_AUTHAPI_BASE_URL_ENV_VAR: "  https://authapi.example.test/api/accounts/  "
    }

    assert agent_identity_authapi_base_url(env) == "https://authapi.example.test/api/accounts"


def test_agent_identity_authapi_base_url_uses_prod_by_default() -> None:
    assert agent_identity_authapi_base_url({}) == PROD_AGENT_IDENTITY_AUTHAPI_BASE_URL
    assert (
        agent_identity_authapi_base_url({CODEX_AGENT_IDENTITY_AUTHAPI_BASE_URL_ENV_VAR: "   "})
        == PROD_AGENT_IDENTITY_AUTHAPI_BASE_URL
    )


def test_key_maps_record_runtime_id_and_private_key() -> None:
    assert key(_record()) == AgentIdentityKey(
        agent_runtime_id="runtime-123",
        private_key_pkcs8_base64="private-key",
    )


def test_agent_identity_auth_load_uses_callable_registrar_and_exposes_record_fields() -> None:
    calls: list[tuple[str, AgentIdentityKey]] = []

    def registrar(base_url: str, identity_key: AgentIdentityKey) -> str:
        calls.append((base_url, identity_key))
        return "task-123"

    record = _record()
    auth = _run(
        AgentIdentityAuth.load(
            record,
            registrar,
            authapi_base_url="https://authapi.example.test/api/accounts",
        )
    )

    assert calls == [
        (
            "https://authapi.example.test/api/accounts",
            AgentIdentityKey("runtime-123", "private-key"),
        )
    ]
    assert auth.record() == record
    assert auth.process_task_id() == "task-123"
    assert auth.account_id() == "account-123"
    assert auth.chatgpt_user_id() == "user-123"
    assert auth.email() == "user@example.com"
    assert auth.plan_type() == "enterprise"
    assert auth.is_fedramp_account() is True


def test_agent_identity_auth_load_accepts_method_registrar_and_awaitable_result() -> None:
    @dataclass
    class Registrar:
        async def register_agent_task(self, base_url: str, identity_key: AgentIdentityKey) -> str:
            assert base_url == PROD_AGENT_IDENTITY_AUTHAPI_BASE_URL
            assert identity_key == AgentIdentityKey("runtime-123", "private-key")
            return "task-async"

    auth = _run(AgentIdentityAuth.load(_record(), Registrar(), authapi_base_url=None))

    assert auth.process_task_id() == "task-async"


def test_agent_identity_auth_load_requires_registration_backend() -> None:
    with pytest.raises(NotImplementedError, match="registration backend is not configured"):
        _run(AgentIdentityAuth.load(_record()))


def test_agent_identity_auth_load_rejects_invalid_registrar() -> None:
    with pytest.raises(TypeError, match="registrar must be callable"):
        _run(AgentIdentityAuth.load(_record(), object()))
