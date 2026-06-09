"""Port of Rust ``codex-login::auth::agent_identity``.

Rust source:
- ``codex/codex-rs/login/src/auth/agent_identity.rs``
"""

from __future__ import annotations

import inspect
import os
from dataclasses import dataclass
from typing import Any, Protocol


PROD_AGENT_IDENTITY_AUTHAPI_BASE_URL = "https://auth.openai.com/api/accounts"
CODEX_AGENT_IDENTITY_AUTHAPI_BASE_URL_ENV_VAR = "CODEX_AGENT_IDENTITY_AUTHAPI_BASE_URL"


@dataclass(frozen=True)
class AgentIdentityAuthRecord:
    agent_runtime_id: str
    agent_private_key: str
    account_id: str
    chatgpt_user_id: str
    email: str
    plan_type: Any
    chatgpt_account_is_fedramp: bool


@dataclass(frozen=True)
class AgentIdentityKey:
    agent_runtime_id: str
    private_key_pkcs8_base64: str


class AgentTaskRegistrar(Protocol):
    def register_agent_task(self, authapi_base_url: str, key: AgentIdentityKey) -> str:
        ...


@dataclass(frozen=True)
class AgentIdentityAuth:
    record_value: AgentIdentityAuthRecord
    process_task_id_value: str

    @classmethod
    async def load(
        cls,
        record: AgentIdentityAuthRecord,
        registrar: AgentTaskRegistrar | Any | None = None,
        *,
        authapi_base_url: str | None = None,
    ) -> "AgentIdentityAuth":
        if registrar is None:
            raise NotImplementedError("Agent identity task registration backend is not configured")
        base_url = authapi_base_url if authapi_base_url is not None else agent_identity_authapi_base_url()
        process_task_id = _call_registrar(registrar, base_url, key(record))
        if inspect.isawaitable(process_task_id):
            process_task_id = await process_task_id
        return cls(record_value=record, process_task_id_value=str(process_task_id))

    def record(self) -> AgentIdentityAuthRecord:
        return self.record_value

    def process_task_id(self) -> str:
        return self.process_task_id_value

    def account_id(self) -> str:
        return self.record_value.account_id

    def chatgpt_user_id(self) -> str:
        return self.record_value.chatgpt_user_id

    def email(self) -> str:
        return self.record_value.email

    def plan_type(self) -> Any:
        return self.record_value.plan_type

    def is_fedramp_account(self) -> bool:
        return self.record_value.chatgpt_account_is_fedramp


def agent_identity_authapi_base_url(env: dict[str, str] | None = None) -> str:
    env_map = os.environ if env is None else env
    base_url = env_map.get(CODEX_AGENT_IDENTITY_AUTHAPI_BASE_URL_ENV_VAR)
    if base_url is not None:
        trimmed = base_url.strip().rstrip("/")
        if trimmed:
            return trimmed
    return PROD_AGENT_IDENTITY_AUTHAPI_BASE_URL


def key(record: AgentIdentityAuthRecord) -> AgentIdentityKey:
    return AgentIdentityKey(
        agent_runtime_id=record.agent_runtime_id,
        private_key_pkcs8_base64=record.agent_private_key,
    )


def _call_registrar(registrar: Any, authapi_base_url: str, identity_key: AgentIdentityKey) -> Any:
    method = getattr(registrar, "register_agent_task", None)
    if callable(method):
        return method(authapi_base_url, identity_key)
    if callable(registrar):
        return registrar(authapi_base_url, identity_key)
    raise TypeError("registrar must be callable or expose register_agent_task")


__all__ = [
    "AgentIdentityAuth",
    "AgentIdentityAuthRecord",
    "AgentIdentityKey",
    "AgentTaskRegistrar",
    "CODEX_AGENT_IDENTITY_AUTHAPI_BASE_URL_ENV_VAR",
    "PROD_AGENT_IDENTITY_AUTHAPI_BASE_URL",
    "agent_identity_authapi_base_url",
    "key",
]
