"""Auth subpackage for the Python port of Rust ``codex-login::auth``."""

from __future__ import annotations

from .agent_identity import (
    AgentIdentityAuth,
    AgentIdentityAuthRecord,
    AgentIdentityKey,
    AgentTaskRegistrar,
    CODEX_AGENT_IDENTITY_AUTHAPI_BASE_URL_ENV_VAR,
    PROD_AGENT_IDENTITY_AUTHAPI_BASE_URL,
    agent_identity_authapi_base_url,
)
from .error import RefreshTokenFailedError, RefreshTokenFailedReason
from .external_bearer import (
    BearerTokenRefresher,
    ExternalAuthRefreshContext,
    ExternalAuthTokens,
    resolve_provider_auth_program,
    run_provider_auth_command,
)
from .util import try_parse_error_message


__all__ = [
    "AgentIdentityAuth",
    "AgentIdentityAuthRecord",
    "AgentIdentityKey",
    "AgentTaskRegistrar",
    "CODEX_AGENT_IDENTITY_AUTHAPI_BASE_URL_ENV_VAR",
    "PROD_AGENT_IDENTITY_AUTHAPI_BASE_URL",
    "agent_identity_authapi_base_url",
    "RefreshTokenFailedError",
    "RefreshTokenFailedReason",
    "BearerTokenRefresher",
    "ExternalAuthRefreshContext",
    "ExternalAuthTokens",
    "resolve_provider_auth_program",
    "run_provider_auth_command",
    "try_parse_error_message",
]
