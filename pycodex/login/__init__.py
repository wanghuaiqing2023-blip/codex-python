"""Public login module for the Python port.

The upstream project exposes login functionality under ``codex-rs/login``.
In this port, the concrete implementation currently lives in
``pycodex.cli.login``; this module provides the expected
``pycodex.login`` import surface while the dedicated package is built out.
"""

from __future__ import annotations

from pycodex.cli import login as _login_impl
from pycodex.login.auth_env_telemetry import (
    AuthEnvTelemetry,
    AuthEnvTelemetryMetadata,
    CODEX_API_KEY_ENV_VAR,
    OPENAI_API_KEY_ENV_VAR,
    REFRESH_TOKEN_URL_OVERRIDE_ENV_VAR,
    collect_auth_env_telemetry,
    env_var_present,
)
from pycodex.login.auth.error import RefreshTokenFailedError, RefreshTokenFailedReason
from pycodex.login.auth.agent_identity import (
    AgentIdentityAuth,
    AgentIdentityAuthRecord,
    AgentIdentityKey,
    CODEX_AGENT_IDENTITY_AUTHAPI_BASE_URL_ENV_VAR,
    PROD_AGENT_IDENTITY_AUTHAPI_BASE_URL,
    agent_identity_authapi_base_url,
)
from pycodex.login.auth.external_bearer import (
    BearerTokenRefresher,
    ExternalAuthRefreshContext,
    ExternalAuthTokens,
    resolve_provider_auth_program,
    run_provider_auth_command,
)
from pycodex.login.auth.util import try_parse_error_message

__all__ = [
    "AUTH_FILE",
    "AUTH_MODE_API_KEY",
    "AUTH_MODE_CHATGPT",
    "AUTH_MODE_CHATGPT_AUTH_TOKENS",
    "AUTH_MODE_AGENT_IDENTITY",
    "AuthDotJson",
    "auth_file_path",
    "delete_auth_file",
    "read_auth_json",
    "resolve_auth_mode",
    "run_chatgpt_login",
    "safe_format_key",
    "write_auth_json",
    "AuthEnvTelemetry",
    "AuthEnvTelemetryMetadata",
    "CODEX_API_KEY_ENV_VAR",
    "OPENAI_API_KEY_ENV_VAR",
    "REFRESH_TOKEN_URL_OVERRIDE_ENV_VAR",
    "collect_auth_env_telemetry",
    "env_var_present",
    "RefreshTokenFailedError",
    "RefreshTokenFailedReason",
    "AgentIdentityAuth",
    "AgentIdentityAuthRecord",
    "AgentIdentityKey",
    "CODEX_AGENT_IDENTITY_AUTHAPI_BASE_URL_ENV_VAR",
    "PROD_AGENT_IDENTITY_AUTHAPI_BASE_URL",
    "agent_identity_authapi_base_url",
    "BearerTokenRefresher",
    "ExternalAuthRefreshContext",
    "ExternalAuthTokens",
    "resolve_provider_auth_program",
    "run_provider_auth_command",
    "try_parse_error_message",
]


def __getattr__(name: str):
    if name in {
        "AuthEnvTelemetry",
        "AuthEnvTelemetryMetadata",
        "CODEX_API_KEY_ENV_VAR",
        "OPENAI_API_KEY_ENV_VAR",
        "REFRESH_TOKEN_URL_OVERRIDE_ENV_VAR",
        "collect_auth_env_telemetry",
        "env_var_present",
        "RefreshTokenFailedError",
        "RefreshTokenFailedReason",
        "AgentIdentityAuth",
        "AgentIdentityAuthRecord",
        "AgentIdentityKey",
        "CODEX_AGENT_IDENTITY_AUTHAPI_BASE_URL_ENV_VAR",
        "PROD_AGENT_IDENTITY_AUTHAPI_BASE_URL",
        "agent_identity_authapi_base_url",
        "BearerTokenRefresher",
        "ExternalAuthRefreshContext",
        "ExternalAuthTokens",
        "resolve_provider_auth_program",
        "run_provider_auth_command",
        "try_parse_error_message",
    }:
        return globals()[name]
    if name not in __all__:
        raise AttributeError(name)
    return getattr(_login_impl, name)


def __dir__() -> list[str]:
    return sorted(__all__)
