from pycodex.login.auth_env_telemetry import (
    AuthEnvTelemetry,
    AuthEnvTelemetryMetadata,
    CODEX_API_KEY_ENV_VAR,
    OPENAI_API_KEY_ENV_VAR,
    REFRESH_TOKEN_URL_OVERRIDE_ENV_VAR,
    collect_auth_env_telemetry,
    env_var_present,
)
from pycodex.model_provider_info import ModelProviderInfo


def test_env_var_present_matches_rust_presence_rules() -> None:
    # Rust crate/module: codex-login::auth_env_telemetry::env_var_present
    assert env_var_present("MISSING", {}) is False
    assert env_var_present("EMPTY", {"EMPTY": ""}) is False
    assert env_var_present("BLANK", {"BLANK": "  \t"}) is False
    assert env_var_present("SET", {"SET": "value"}) is True


def test_collect_auth_env_telemetry_buckets_provider_env_key_name() -> None:
    # Rust test: collect_auth_env_telemetry_buckets_provider_env_key_name.
    provider = ModelProviderInfo(name="Custom", env_key="sk-should-not-leak")
    telemetry = collect_auth_env_telemetry(
        provider,
        codex_api_key_env_enabled=False,
        env={
            OPENAI_API_KEY_ENV_VAR: "openai",
            CODEX_API_KEY_ENV_VAR: "",
            "sk-should-not-leak": "provider-key",
            REFRESH_TOKEN_URL_OVERRIDE_ENV_VAR: "https://refresh.example",
        },
    )

    assert telemetry == AuthEnvTelemetry(
        openai_api_key_env_present=True,
        codex_api_key_env_present=False,
        codex_api_key_env_enabled=False,
        provider_env_key_name="configured",
        provider_env_key_present=True,
        refresh_token_url_override_present=True,
    )


def test_collect_auth_env_telemetry_without_provider_key() -> None:
    # Rust behavior: provider env key fields are None when no provider env key is configured.
    telemetry = collect_auth_env_telemetry(
        ModelProviderInfo(),
        codex_api_key_env_enabled=True,
        env={CODEX_API_KEY_ENV_VAR: "codex"},
    )

    assert telemetry.provider_env_key_name is None
    assert telemetry.provider_env_key_present is None
    assert telemetry.codex_api_key_env_present is True
    assert telemetry.codex_api_key_env_enabled is True


def test_auth_env_telemetry_to_otel_metadata_preserves_fields() -> None:
    # Rust crate/module: codex-login::auth_env_telemetry::to_otel_metadata
    telemetry = AuthEnvTelemetry(
        openai_api_key_env_present=True,
        codex_api_key_env_present=True,
        codex_api_key_env_enabled=True,
        provider_env_key_name="configured",
        provider_env_key_present=False,
        refresh_token_url_override_present=True,
    )

    assert telemetry.to_otel_metadata() == AuthEnvTelemetryMetadata(
        openai_api_key_env_present=True,
        codex_api_key_env_present=True,
        codex_api_key_env_enabled=True,
        provider_env_key_name="configured",
        provider_env_key_present=False,
        refresh_token_url_override_present=True,
    )
