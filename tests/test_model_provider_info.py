import pytest

from pathlib import Path

from pycodex.model_provider_info import (
    AMAZON_BEDROCK_DEFAULT_BASE_URL,
    AMAZON_BEDROCK_GPT_5_4_MODEL_ID,
    AMAZON_BEDROCK_PROVIDER_ID,
    CHATGPT_CODEX_BASE_URL,
    CHAT_WIRE_API_REMOVED_ERROR,
    DEFAULT_LMSTUDIO_PORT,
    DEFAULT_OLLAMA_PORT,
    DEFAULT_REQUEST_MAX_RETRIES,
    DEFAULT_STREAM_IDLE_TIMEOUT_MS,
    DEFAULT_STREAM_MAX_RETRIES,
    DEFAULT_WEBSOCKET_CONNECT_TIMEOUT_MS,
    LMSTUDIO_OSS_PROVIDER_ID,
    MAX_REQUEST_MAX_RETRIES,
    MAX_STREAM_MAX_RETRIES,
    ModelProviderAwsAuthInfo,
    ModelProviderAuthInfo,
    ModelProviderInfo,
    OLLAMA_OSS_PROVIDER_ID,
    OPENAI_PROVIDER_ID,
    WireApi,
    built_in_model_providers,
    create_oss_provider,
    create_oss_provider_with_base_url,
    merge_configured_model_providers,
)


def test_deserialize_ollama_model_provider_toml() -> None:
    # Rust source: test_deserialize_ollama_model_provider_toml.
    provider = ModelProviderInfo.from_toml(
        """
        name = "Ollama"
        base_url = "http://localhost:11434/v1"
        """
    )
    assert provider == ModelProviderInfo(name="Ollama", base_url="http://localhost:11434/v1")


def test_deserialize_azure_model_provider_toml() -> None:
    # Rust source: test_deserialize_azure_model_provider_toml.
    provider = ModelProviderInfo.from_toml(
        """
        name = "Azure"
        base_url = "https://xxxxx.openai.azure.com/openai"
        env_key = "AZURE_OPENAI_API_KEY"
        query_params = { api-version = "2025-04-01-preview" }
        """
    )
    assert provider.name == "Azure"
    assert provider.base_url == "https://xxxxx.openai.azure.com/openai"
    assert provider.env_key == "AZURE_OPENAI_API_KEY"
    assert provider.query_params == {"api-version": "2025-04-01-preview"}


def test_deserialize_example_model_provider_headers_toml() -> None:
    # Rust source: test_deserialize_example_model_provider_toml.
    provider = ModelProviderInfo.from_toml(
        """
        name = "Example"
        base_url = "https://example.com"
        env_key = "API_KEY"
        http_headers = { "X-Example-Header" = "example-value" }
        env_http_headers = { "X-Example-Env-Header" = "EXAMPLE_ENV_VAR" }
        """
    )
    assert provider.http_headers == {"X-Example-Header": "example-value"}
    assert provider.env_http_headers == {"X-Example-Env-Header": "EXAMPLE_ENV_VAR"}


def test_wire_api_rejects_removed_chat_protocol() -> None:
    # Rust crate/module: codex-model-provider-info::WireApi deserialize.
    with pytest.raises(ValueError, match="wire_api"):
        WireApi.parse("chat")

    assert CHAT_WIRE_API_REMOVED_ERROR in str(pytest.raises(ValueError, WireApi.parse, "chat").value)

    with pytest.raises(ValueError) as excinfo:
        ModelProviderInfo.from_toml(
            """
            name = "OpenAI using Chat Completions"
            base_url = "https://api.openai.com/v1"
            env_key = "OPENAI_API_KEY"
            wire_api = "chat"
            """
        )
    assert CHAT_WIRE_API_REMOVED_ERROR in str(excinfo.value)


def test_create_openai_provider_defaults_and_api_provider_projection(monkeypatch) -> None:
    # Rust crate/module: codex-model-provider-info::ModelProviderInfo::create_openai_provider.
    monkeypatch.setenv("OPENAI_ORGANIZATION", "org-1")
    monkeypatch.setenv("OPENAI_PROJECT", "project-1")
    provider = ModelProviderInfo.create_openai_provider(None)

    assert provider.name == "OpenAI"
    assert provider.requires_openai_auth is True
    assert provider.supports_websockets is True
    assert provider.request_max_retries() == DEFAULT_REQUEST_MAX_RETRIES
    assert provider.stream_max_retries() == DEFAULT_STREAM_MAX_RETRIES
    assert provider.stream_idle_timeout() == DEFAULT_STREAM_IDLE_TIMEOUT_MS
    assert provider.websocket_connect_timeout() == DEFAULT_WEBSOCKET_CONNECT_TIMEOUT_MS

    api = provider.to_api_provider("chatgpt")
    assert api.base_url == CHATGPT_CODEX_BASE_URL
    assert api.headers["OpenAI-Organization"] == "org-1"
    assert api.headers["OpenAI-Project"] == "project-1"

    assert provider.to_api_provider("api_key").base_url == "https://api.openai.com/v1"


def test_retry_and_timeout_values_are_capped_or_defaulted() -> None:
    # Rust crate/module: codex-model-provider-info retry/timeout helpers.
    provider = ModelProviderInfo(
        request_max_retries_value=MAX_REQUEST_MAX_RETRIES + 1,
        stream_max_retries_value=MAX_STREAM_MAX_RETRIES + 1,
        stream_idle_timeout_ms=123,
        websocket_connect_timeout_ms=456,
    )

    assert provider.request_max_retries() == MAX_REQUEST_MAX_RETRIES
    assert provider.stream_max_retries() == MAX_STREAM_MAX_RETRIES
    assert provider.stream_idle_timeout() == 123
    assert provider.websocket_connect_timeout() == 456


def test_deserialize_websocket_connect_timeout() -> None:
    # Rust source: test_deserialize_websocket_connect_timeout.
    provider = ModelProviderInfo.from_toml(
        """
        name = "OpenAI"
        base_url = "https://api.openai.com/v1"
        websocket_connect_timeout_ms = 15000
        supports_websockets = true
        """
    )
    assert provider.websocket_connect_timeout_ms == 15_000
    assert provider.supports_websockets is True


def test_api_key_reads_non_empty_env_or_raises(monkeypatch) -> None:
    # Rust crate/module: codex-model-provider-info::ModelProviderInfo::api_key.
    provider = ModelProviderInfo(env_key="MODEL_PROVIDER_TOKEN", env_key_instructions="set it")

    monkeypatch.setenv("MODEL_PROVIDER_TOKEN", "  ")
    with pytest.raises(OSError):
        provider.api_key()

    monkeypatch.setenv("MODEL_PROVIDER_TOKEN", "secret")
    assert provider.api_key() == "secret"


def test_validate_rejects_aws_and_command_auth_conflicts() -> None:
    # Rust tests: test_validate_provider_aws_rejects_* and auth conflict validation.
    with pytest.raises(ValueError, match="provider aws cannot be combined with supports_websockets"):
        ModelProviderInfo(aws=ModelProviderAwsAuthInfo(), supports_websockets=True).validate()

    with pytest.raises(ValueError, match="provider aws cannot be combined with env_key"):
        ModelProviderInfo(aws=ModelProviderAwsAuthInfo(), env_key="TOKEN").validate()

    with pytest.raises(ValueError, match="provider auth.command must not be empty"):
        ModelProviderInfo(auth={"command": "  "}).validate()

    with pytest.raises(ValueError, match="provider auth cannot be combined with env_key"):
        ModelProviderInfo(auth={"command": "print-token"}, env_key="TOKEN").validate()


def test_create_amazon_bedrock_provider_and_headers() -> None:
    # Rust tests: test_create_amazon_bedrock_provider and mantle client-agent header.
    provider = ModelProviderInfo.create_amazon_bedrock_provider()

    assert provider.name == "Amazon Bedrock"
    assert provider.base_url == AMAZON_BEDROCK_DEFAULT_BASE_URL
    assert provider.aws == ModelProviderAwsAuthInfo()
    assert provider.requires_openai_auth is False
    assert provider.supports_websockets is False
    assert provider.is_amazon_bedrock() is True
    assert provider.to_api_provider(None).headers["x-amzn-mantle-client-agent"] == "codex"
    assert AMAZON_BEDROCK_GPT_5_4_MODEL_ID == "openai.gpt-5.4"


def test_deserialize_provider_aws_config() -> None:
    # Rust source: test_deserialize_provider_aws_config.
    provider = ModelProviderInfo.from_toml(
        """
        name = "Amazon Bedrock"
        base_url = "https://bedrock.example.com/v1"

        [aws]
        profile = "codex-bedrock"
        region = "us-west-2"
        """
    )
    assert provider.aws == ModelProviderAwsAuthInfo(profile="codex-bedrock", region="us-west-2")


def test_deserialize_provider_auth_config_defaults(tmp_path, monkeypatch) -> None:
    # Rust source: test_deserialize_provider_auth_config_defaults.
    monkeypatch.chdir(tmp_path)
    provider = ModelProviderInfo.from_toml(
        """
        name = "Corp"

        [auth]
        command = "./scripts/print-token"
        args = ["--format=text"]
        """
    )
    assert provider.auth == ModelProviderAuthInfo(
        command="./scripts/print-token",
        args=("--format=text",),
        timeout_ms=5_000,
        refresh_interval_ms=300_000,
        cwd=Path(".").resolve(strict=False),
    )


def test_deserialize_provider_auth_config_allows_zero_refresh_interval(tmp_path, monkeypatch) -> None:
    # Rust source: test_deserialize_provider_auth_config_allows_zero_refresh_interval.
    monkeypatch.chdir(tmp_path)
    provider = ModelProviderInfo.from_toml(
        """
        name = "Corp"

        [auth]
        command = "./scripts/print-token"
        refresh_interval_ms = 0
        """
    )
    assert provider.auth is not None
    assert provider.auth.refresh_interval_ms == 0
    assert provider.auth.refresh_interval() is None


def test_built_in_model_providers_include_openai_bedrock_and_oss(monkeypatch) -> None:
    # Rust crate/module: codex-model-provider-info::built_in_model_providers.
    monkeypatch.delenv("CODEX_OSS_PORT", raising=False)
    monkeypatch.delenv("CODEX_OSS_BASE_URL", raising=False)

    providers = built_in_model_providers("https://openai.example/v1")

    assert providers[OPENAI_PROVIDER_ID].base_url == "https://openai.example/v1"
    assert providers[AMAZON_BEDROCK_PROVIDER_ID].is_amazon_bedrock()
    assert providers[OLLAMA_OSS_PROVIDER_ID].base_url == f"http://localhost:{DEFAULT_OLLAMA_PORT}/v1"
    assert providers[LMSTUDIO_OSS_PROVIDER_ID].base_url == f"http://localhost:{DEFAULT_LMSTUDIO_PORT}/v1"


def test_create_oss_provider_uses_env_overrides(monkeypatch) -> None:
    # Rust crate/module: codex-model-provider-info::create_oss_provider.
    monkeypatch.setenv("CODEX_OSS_PORT", "9999")
    assert create_oss_provider(11434, WireApi.RESPONSES).base_url == "http://localhost:9999/v1"

    monkeypatch.setenv("CODEX_OSS_BASE_URL", "http://localhost:7777/v1")
    assert create_oss_provider(11434, WireApi.RESPONSES).base_url == "http://localhost:7777/v1"
    assert create_oss_provider_with_base_url("http://example/v1", WireApi.RESPONSES).name == "gpt-oss"


def test_merge_configured_model_providers_adds_custom_and_allows_bedrock_aws_override() -> None:
    # Rust tests: merge configured providers custom and Bedrock override.
    providers = built_in_model_providers(None)
    custom = ModelProviderInfo(name="Custom", base_url="https://example.com/v1")

    merged = merge_configured_model_providers(providers, {"custom": custom})
    assert merged["custom"] is custom

    merged = merge_configured_model_providers(
        providers,
        {
            AMAZON_BEDROCK_PROVIDER_ID: ModelProviderInfo(
                aws=ModelProviderAwsAuthInfo(profile="codex-bedrock", region="us-west-2")
            )
        },
    )
    assert merged[AMAZON_BEDROCK_PROVIDER_ID].aws == ModelProviderAwsAuthInfo(
        profile="codex-bedrock",
        region="us-west-2",
    )


def test_merge_configured_model_providers_rejects_bedrock_non_default_fields() -> None:
    # Rust test: test_merge_configured_model_providers_rejects_amazon_bedrock_non_default_fields.
    with pytest.raises(ValueError, match="only supports changing"):
        merge_configured_model_providers(
            built_in_model_providers(None),
            {
                AMAZON_BEDROCK_PROVIDER_ID: ModelProviderInfo(
                    name="Custom Bedrock",
                    aws=ModelProviderAwsAuthInfo(profile="codex-bedrock"),
                )
            },
        )


def test_supports_remote_compaction_for_openai_and_azure_only() -> None:
    # Rust tests: supports_remote_compaction_*.
    assert ModelProviderInfo.create_openai_provider(None).supports_remote_compaction() is True
    assert ModelProviderInfo(name="Azure", base_url="https://example.com/openai").supports_remote_compaction() is True
    assert ModelProviderInfo(name="Example", base_url="https://example.com/v1").supports_remote_compaction() is False
