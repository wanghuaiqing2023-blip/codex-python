"""Public re-exports for ``codex-model-provider``."""

from pycodex.protocol import ProviderAccount

from .auth import auth_provider_from_auth, unauthenticated_auth_provider
from .bearer_auth_provider import BearerAuthProvider
from .provider import (
    ModelProvider,
    ProviderAccountError,
    ProviderAccountResult,
    ProviderAccountState,
    ProviderCapabilities,
    SharedModelProvider,
    create_model_provider,
)

CoreAuthProvider = BearerAuthProvider

__all__ = [
    "BearerAuthProvider",
    "CoreAuthProvider",
    "ModelProvider",
    "ProviderAccount",
    "ProviderAccountError",
    "ProviderAccountResult",
    "ProviderAccountState",
    "ProviderCapabilities",
    "SharedModelProvider",
    "auth_provider_from_auth",
    "create_model_provider",
    "unauthenticated_auth_provider",
]
