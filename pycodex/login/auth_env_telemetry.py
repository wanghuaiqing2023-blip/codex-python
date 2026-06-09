"""Port of Rust ``codex-login::auth_env_telemetry``.

Rust source:
- ``codex/codex-rs/login/src/auth_env_telemetry.rs``
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping


OPENAI_API_KEY_ENV_VAR = "OPENAI_API_KEY"
CODEX_API_KEY_ENV_VAR = "CODEX_API_KEY"
REFRESH_TOKEN_URL_OVERRIDE_ENV_VAR = "CODEX_REFRESH_TOKEN_URL_OVERRIDE"


@dataclass(frozen=True)
class AuthEnvTelemetry:
    openai_api_key_env_present: bool = False
    codex_api_key_env_present: bool = False
    codex_api_key_env_enabled: bool = False
    provider_env_key_name: str | None = None
    provider_env_key_present: bool | None = None
    refresh_token_url_override_present: bool = False

    def to_otel_metadata(self) -> "AuthEnvTelemetryMetadata":
        return AuthEnvTelemetryMetadata(
            openai_api_key_env_present=self.openai_api_key_env_present,
            codex_api_key_env_present=self.codex_api_key_env_present,
            codex_api_key_env_enabled=self.codex_api_key_env_enabled,
            provider_env_key_name=self.provider_env_key_name,
            provider_env_key_present=self.provider_env_key_present,
            refresh_token_url_override_present=self.refresh_token_url_override_present,
        )


@dataclass(frozen=True)
class AuthEnvTelemetryMetadata:
    openai_api_key_env_present: bool = False
    codex_api_key_env_present: bool = False
    codex_api_key_env_enabled: bool = False
    provider_env_key_name: str | None = None
    provider_env_key_present: bool | None = None
    refresh_token_url_override_present: bool = False


def collect_auth_env_telemetry(
    provider: Any,
    codex_api_key_env_enabled: bool,
    env: Mapping[str, str] | None = None,
) -> AuthEnvTelemetry:
    env_map = os.environ if env is None else env
    provider_env_key = _get(provider, "env_key")
    return AuthEnvTelemetry(
        openai_api_key_env_present=env_var_present(OPENAI_API_KEY_ENV_VAR, env_map),
        codex_api_key_env_present=env_var_present(CODEX_API_KEY_ENV_VAR, env_map),
        codex_api_key_env_enabled=codex_api_key_env_enabled,
        provider_env_key_name="configured" if provider_env_key is not None else None,
        provider_env_key_present=env_var_present(provider_env_key, env_map) if provider_env_key is not None else None,
        refresh_token_url_override_present=env_var_present(REFRESH_TOKEN_URL_OVERRIDE_ENV_VAR, env_map),
    )


def env_var_present(name: str, env: Mapping[str, str] | None = None) -> bool:
    env_map = os.environ if env is None else env
    try:
        value = env_map[name]
    except KeyError:
        return False
    except UnicodeError:
        return True
    return bool(str(value).strip())


def _get(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


__all__ = [
    "AuthEnvTelemetry",
    "AuthEnvTelemetryMetadata",
    "CODEX_API_KEY_ENV_VAR",
    "OPENAI_API_KEY_ENV_VAR",
    "REFRESH_TOKEN_URL_OVERRIDE_ENV_VAR",
    "collect_auth_env_telemetry",
    "env_var_present",
]
