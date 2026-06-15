"""Runtime provider facade ported from ``codex-model-provider::provider``."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from pycodex.model_provider_info import ModelProviderInfo
from pycodex.models_manager import OpenAiModelsManager, StaticModelsManager
from pycodex.protocol import ProviderAccount
from pycodex.protocol.account import PlanType

from .auth import auth_manager_for_provider, resolve_provider_auth


DEFAULT_APPROVAL_REVIEW_PREFERRED_MODEL = "codex-auto-review"


@dataclass(frozen=True)
class ProviderCapabilities:
    namespace_tools: bool = True
    image_generation: bool = True
    web_search: bool = True


@dataclass(frozen=True)
class ProviderAccountState:
    account: ProviderAccount | None
    requires_openai_auth: bool


class ProviderAccountError(str, Enum):
    MISSING_CHATGPT_ACCOUNT_DETAILS = "missing_chatgpt_account_details"

    def __str__(self) -> str:
        if self is ProviderAccountError.MISSING_CHATGPT_ACCOUNT_DETAILS:
            return "email and plan type are required for chatgpt authentication"
        return self.value


ProviderAccountResult = ProviderAccountState | ProviderAccountError


class ModelProvider(Protocol):
    def info(self) -> ModelProviderInfo:
        ...

    def capabilities(self) -> ProviderCapabilities:
        ...

    def approval_review_preferred_model(self) -> str:
        ...

    def supports_attestation(self) -> bool:
        ...

    def auth_manager(self) -> Any:
        ...

    async def auth(self) -> Any:
        ...

    def account_state(self) -> ProviderAccountResult:
        ...

    async def api_provider(self) -> Any:
        ...

    async def runtime_base_url(self) -> str | None:
        ...

    async def api_auth(self) -> Any:
        ...

    def models_manager(self, codex_home: Path, config_model_catalog: Any = None) -> Any:
        ...


SharedModelProvider = ModelProvider


@dataclass
class ConfiguredModelProvider:
    provider_info: ModelProviderInfo
    provider_auth_manager: Any = None

    def __post_init__(self) -> None:
        self.provider_auth_manager = auth_manager_for_provider(self.provider_auth_manager, self.provider_info)

    def info(self) -> ModelProviderInfo:
        return self.provider_info

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    def approval_review_preferred_model(self) -> str:
        return DEFAULT_APPROVAL_REVIEW_PREFERRED_MODEL

    def supports_attestation(self) -> bool:
        auth_cached = getattr(self.provider_auth_manager, "auth_cached", None)
        auth = auth_cached() if callable(auth_cached) else None
        return _is_chatgpt_auth(auth)

    def auth_manager(self) -> Any:
        return self.provider_auth_manager

    async def auth(self) -> Any:
        manager = self.provider_auth_manager
        if manager is None:
            return None
        method = getattr(manager, "auth", None)
        if not callable(method):
            return None
        result = method()
        if inspect.isawaitable(result):
            result = await result
        return result

    def account_state(self) -> ProviderAccountResult:
        account = None
        if self.provider_info.requires_openai_auth:
            auth = _auth_cached_without_refresh_failure(self.provider_auth_manager)
            if auth is not None:
                account = _provider_account_from_auth(auth)
                if account is ProviderAccountError.MISSING_CHATGPT_ACCOUNT_DETAILS:
                    return account
        return ProviderAccountState(
            account=account,
            requires_openai_auth=self.provider_info.requires_openai_auth,
        )

    async def api_provider(self) -> Any:
        auth = await self.auth()
        auth_mode = _call_optional(auth, "auth_mode")
        return self.provider_info.to_api_provider(auth_mode)

    async def runtime_base_url(self) -> str | None:
        return self.provider_info.base_url

    async def api_auth(self) -> Any:
        return resolve_provider_auth(await self.auth(), self.provider_info)

    def models_manager(self, codex_home: Path, config_model_catalog: Any = None) -> Any:
        if config_model_catalog is not None:
            return StaticModelsManager(self.provider_auth_manager, config_model_catalog)
        from .models_endpoint import OpenAiModelsEndpoint

        return OpenAiModelsManager(
            codex_home,
            OpenAiModelsEndpoint(self.provider_info, self.provider_auth_manager),
            self.provider_auth_manager,
        )


def create_model_provider(
    provider_info: ModelProviderInfo,
    auth_manager: Any = None,
) -> SharedModelProvider:
    if provider_info.is_amazon_bedrock():
        from .amazon_bedrock import AmazonBedrockModelProvider

        return AmazonBedrockModelProvider.new(provider_info)
    return ConfiguredModelProvider(provider_info, auth_manager)


def _auth_cached_without_refresh_failure(auth_manager: Any) -> Any:
    if auth_manager is None:
        return None
    auth = _call_optional(auth_manager, "auth_cached")
    if auth is None:
        return None
    refresh_failure = getattr(auth_manager, "refresh_failure_for_auth", None)
    if callable(refresh_failure) and refresh_failure(auth) is not None:
        return None
    return auth


def _provider_account_from_auth(auth: Any) -> ProviderAccount | ProviderAccountError:
    if _is_api_key_auth(auth):
        return ProviderAccount.api_key()
    if _is_chatgpt_auth(auth):
        email = _call_optional(auth, "get_account_email")
        if email is None:
            email = _call_optional(auth, "account_email")
        plan_type = _call_optional(auth, "account_plan_type")
        if email is None or plan_type is None:
            return ProviderAccountError.MISSING_CHATGPT_ACCOUNT_DETAILS
        if not isinstance(plan_type, PlanType):
            plan_type = PlanType.parse(str(getattr(plan_type, "value", plan_type)))
        return ProviderAccount.chatgpt(str(email), plan_type)
    return ProviderAccountError.MISSING_CHATGPT_ACCOUNT_DETAILS


def _is_api_key_auth(auth: Any) -> bool:
    if auth is None:
        return False
    method = getattr(auth, "is_api_key_auth", None)
    if callable(method):
        return bool(method())
    mode = _call_optional(auth, "auth_mode")
    if mode is None:
        mode = getattr(auth, "kind", None)
    return str(getattr(mode, "value", mode)).lower() in {"apikey", "api_key"}


def _is_chatgpt_auth(auth: Any) -> bool:
    if auth is None:
        return False
    method = getattr(auth, "is_chatgpt_auth", None)
    if callable(method):
        return bool(method())
    mode = _call_optional(auth, "auth_mode")
    if mode is None:
        mode = getattr(auth, "kind", None)
    return str(getattr(mode, "value", mode)).lower() in {
        "chatgpt",
        "chatgptauthtokens",
        "chatgpt_auth_tokens",
        "agentidentity",
        "agent_identity",
    }


def _call_optional(value: Any, name: str) -> Any:
    if value is None:
        return None
    method = getattr(value, name, None)
    if callable(method):
        return method()
    return method


__all__ = [
    "ConfiguredModelProvider",
    "DEFAULT_APPROVAL_REVIEW_PREFERRED_MODEL",
    "ModelProvider",
    "ProviderAccountError",
    "ProviderAccountResult",
    "ProviderAccountState",
    "ProviderCapabilities",
    "SharedModelProvider",
    "create_model_provider",
]
