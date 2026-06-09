"""Port of Rust ``codex-model-provider`` public API surface.

Rust sources:
- ``codex/codex-rs/model-provider/src/lib.rs``
- ``codex/codex-rs/model-provider/src/provider.rs``
- ``codex/codex-rs/model-provider/src/bearer_auth_provider.rs``
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Protocol

from pycodex.model_provider_info import ModelProviderInfo
from pycodex.protocol import ProviderAccount
from .bearer_auth_provider import BearerAuthProvider


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


CoreAuthProvider = BearerAuthProvider


@dataclass
class ConfiguredModelProvider:
    provider_info: ModelProviderInfo
    provider_auth_manager: Any = None

    def info(self) -> ModelProviderInfo:
        return self.provider_info

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    def approval_review_preferred_model(self) -> str:
        return DEFAULT_APPROVAL_REVIEW_PREFERRED_MODEL

    def supports_attestation(self) -> bool:
        auth_cached = getattr(self.provider_auth_manager, "auth_cached", None)
        auth = auth_cached() if callable(auth_cached) else None
        is_chatgpt_auth = getattr(auth, "is_chatgpt_auth", None)
        return bool(is_chatgpt_auth()) if callable(is_chatgpt_auth) else False

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
        if hasattr(result, "__await__"):
            result = await result
        return result

    def account_state(self) -> ProviderAccountState:
        return ProviderAccountState(
            account=None,
            requires_openai_auth=self.provider_info.requires_openai_auth,
        )

    async def api_provider(self) -> Any:
        auth = await self.auth()
        auth_mode = getattr(auth, "auth_mode", None)
        auth_mode = auth_mode() if callable(auth_mode) else auth_mode
        return self.provider_info.to_api_provider(auth_mode)

    async def runtime_base_url(self) -> str | None:
        return self.provider_info.base_url

    async def api_auth(self) -> Any:
        return auth_provider_from_auth(await self.auth())

    def models_manager(self, codex_home: Path, config_model_catalog: Any = None) -> Any:
        return {
            "codex_home": Path(codex_home),
            "config_model_catalog": config_model_catalog,
            "auth_manager": self.provider_auth_manager,
        }


def create_model_provider(
    provider_info: ModelProviderInfo,
    auth_manager: Any = None,
) -> SharedModelProvider:
    return ConfiguredModelProvider(provider_info, auth_manager)


from .auth import AgentIdentityAuthProvider as AgentIdentityAuthProvider
from .auth import UnauthenticatedAuthProvider as UnauthenticatedAuthProvider
from .auth import auth_manager_for_provider as auth_manager_for_provider
from .auth import auth_provider_from_auth as auth_provider_from_auth
from .auth import bearer_auth_for_provider as bearer_auth_for_provider
from .auth import resolve_provider_auth as resolve_provider_auth
from .auth import unauthenticated_auth_provider as unauthenticated_auth_provider
from .bearer_auth_provider import BearerAuthProvider as BearerAuthProvider


__all__ = [
    "BearerAuthProvider",
    "ConfiguredModelProvider",
    "CoreAuthProvider",
    "DEFAULT_APPROVAL_REVIEW_PREFERRED_MODEL",
    "ModelProvider",
    "ProviderAccountError",
    "ProviderAccountResult",
    "ProviderAccountState",
    "ProviderCapabilities",
    "ProviderAccount",
    "SharedModelProvider",
    "AgentIdentityAuthProvider",
    "UnauthenticatedAuthProvider",
    "auth_manager_for_provider",
    "auth_provider_from_auth",
    "bearer_auth_for_provider",
    "create_model_provider",
    "resolve_provider_auth",
    "unauthenticated_auth_provider",
]
