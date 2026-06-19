"""Port of Rust ``codex-model-provider-info`` public API.

Rust source:
- ``codex/codex-rs/model-provider-info/src/lib.rs``
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from pycodex.protocol.config_types import ModelProviderAuthInfo


DEFAULT_STREAM_IDLE_TIMEOUT_MS = 300_000
DEFAULT_STREAM_MAX_RETRIES = 5
DEFAULT_REQUEST_MAX_RETRIES = 4
DEFAULT_WEBSOCKET_CONNECT_TIMEOUT_MS = 15_000
MAX_STREAM_MAX_RETRIES = 100
MAX_REQUEST_MAX_RETRIES = 100

OPENAI_PROVIDER_ID = "openai"
CHATGPT_CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
AMAZON_BEDROCK_PROVIDER_ID = "amazon-bedrock"
AMAZON_BEDROCK_GPT_5_4_MODEL_ID = "openai.gpt-5.4"
AMAZON_BEDROCK_DEFAULT_BASE_URL = "https://bedrock-mantle.us-east-1.api.aws/openai/v1"
LEGACY_OLLAMA_CHAT_PROVIDER_ID = "ollama-chat"
OLLAMA_CHAT_PROVIDER_REMOVED_ERROR = (
    "`ollama-chat` is no longer supported.\n"
    "How to fix: replace `ollama-chat` with `ollama` in `model_provider`, "
    "`oss_provider`, or `--local-provider`.\n"
    "More info: https://github.com/openai/codex/discussions/7782"
)
CHAT_WIRE_API_REMOVED_ERROR = (
    '`wire_api = "chat"` is no longer supported.\n'
    'How to fix: set `wire_api = "responses"` in your provider config.\n'
    "More info: https://github.com/openai/codex/discussions/7782"
)
DEFAULT_LMSTUDIO_PORT = 1234
DEFAULT_OLLAMA_PORT = 11434
LMSTUDIO_OSS_PROVIDER_ID = "lmstudio"
OLLAMA_OSS_PROVIDER_ID = "ollama"


class WireApi(str, Enum):
    RESPONSES = "responses"

    @classmethod
    def parse(cls, value: str) -> "WireApi":
        if value == "chat":
            raise ValueError(CHAT_WIRE_API_REMOVED_ERROR)
        try:
            return cls(value)
        except ValueError as exc:
            raise ValueError(f"unknown wire api: {value}") from exc


@dataclass(frozen=True)
class ModelProviderAwsAuthInfo:
    profile: str | None = None
    region: str | None = None


@dataclass(frozen=True)
class ApiProvider:
    """Small Python stand-in for ``codex_api::Provider``."""

    name: str
    base_url: str
    query_params: Mapping[str, str] | None = None
    headers: Mapping[str, str] = field(default_factory=dict)
    request_max_retries: int = DEFAULT_REQUEST_MAX_RETRIES
    stream_idle_timeout_ms: int = DEFAULT_STREAM_IDLE_TIMEOUT_MS


@dataclass(frozen=True)
class ModelProviderInfo:
    name: str = ""
    base_url: str | None = None
    env_key: str | None = None
    env_key_instructions: str | None = None
    experimental_bearer_token: str | None = None
    auth: Any = None
    aws: ModelProviderAwsAuthInfo | None = None
    wire_api: WireApi = WireApi.RESPONSES
    query_params: Mapping[str, str] | None = None
    http_headers: Mapping[str, str] | None = None
    env_http_headers: Mapping[str, str] | None = None
    request_max_retries_value: int | None = None
    stream_max_retries_value: int | None = None
    stream_idle_timeout_ms: int | None = None
    websocket_connect_timeout_ms: int | None = None
    requires_openai_auth: bool = False
    supports_websockets: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "wire_api", self.wire_api if isinstance(self.wire_api, WireApi) else WireApi.parse(str(self.wire_api)))
        if self.aws is not None and not isinstance(self.aws, ModelProviderAwsAuthInfo):
            object.__setattr__(self, "aws", ModelProviderAwsAuthInfo(**dict(self.aws)))
        if self.auth is not None and isinstance(self.auth, Mapping):
            object.__setattr__(self, "auth", _auth_info_from_mapping(self.auth))
        for field_name in ("requires_openai_auth", "supports_websockets"):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be a bool")

    @classmethod
    def from_toml(cls, contents: str) -> "ModelProviderInfo":
        return cls.from_mapping(tomllib.loads(contents))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ModelProviderInfo":
        data = dict(value)
        unknown = set(data) - {
            "name",
            "base_url",
            "env_key",
            "env_key_instructions",
            "experimental_bearer_token",
            "auth",
            "aws",
            "wire_api",
            "query_params",
            "http_headers",
            "env_http_headers",
            "request_max_retries",
            "stream_max_retries",
            "stream_idle_timeout_ms",
            "websocket_connect_timeout_ms",
            "requires_openai_auth",
            "supports_websockets",
        }
        if unknown:
            raise ValueError(f"unknown ModelProviderInfo fields: {', '.join(sorted(unknown))}")
        aws = data.get("aws")
        if aws is not None and not isinstance(aws, Mapping):
            raise TypeError("aws must be a mapping")
        auth = data.get("auth")
        if auth is not None and not isinstance(auth, Mapping) and not isinstance(auth, ModelProviderAuthInfo):
            raise TypeError("auth must be a mapping")
        return cls(
            name=_optional_str(data.get("name")) or "",
            base_url=_optional_str(data.get("base_url")),
            env_key=_optional_str(data.get("env_key")),
            env_key_instructions=_optional_str(data.get("env_key_instructions")),
            experimental_bearer_token=_optional_str(data.get("experimental_bearer_token")),
            auth=auth,
            aws=ModelProviderAwsAuthInfo(**dict(aws)) if isinstance(aws, Mapping) else None,
            wire_api=_optional_str(data.get("wire_api")) or WireApi.RESPONSES,
            query_params=_optional_str_mapping(data.get("query_params"), "query_params"),
            http_headers=_optional_str_mapping(data.get("http_headers"), "http_headers"),
            env_http_headers=_optional_str_mapping(data.get("env_http_headers"), "env_http_headers"),
            request_max_retries_value=_optional_non_negative_int(data.get("request_max_retries"), "request_max_retries"),
            stream_max_retries_value=_optional_non_negative_int(data.get("stream_max_retries"), "stream_max_retries"),
            stream_idle_timeout_ms=_optional_non_negative_int(data.get("stream_idle_timeout_ms"), "stream_idle_timeout_ms"),
            websocket_connect_timeout_ms=_optional_non_negative_int(data.get("websocket_connect_timeout_ms"), "websocket_connect_timeout_ms"),
            requires_openai_auth=_optional_bool(data.get("requires_openai_auth"), "requires_openai_auth", False),
            supports_websockets=_optional_bool(data.get("supports_websockets"), "supports_websockets", False),
        )

    def validate(self) -> None:
        if self.aws is not None:
            if self.supports_websockets:
                raise ValueError("provider aws cannot be combined with supports_websockets")
            conflicts = []
            if self.env_key is not None:
                conflicts.append("env_key")
            if self.experimental_bearer_token is not None:
                conflicts.append("experimental_bearer_token")
            if self.auth is not None:
                conflicts.append("auth")
            if self.requires_openai_auth:
                conflicts.append("requires_openai_auth")
            if conflicts:
                raise ValueError(f"provider aws cannot be combined with {', '.join(conflicts)}")

        if self.auth is None:
            return
        command = getattr(self.auth, "command", None)
        if command is None and isinstance(self.auth, Mapping):
            command = self.auth.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ValueError("provider auth.command must not be empty")
        conflicts = []
        if self.env_key is not None:
            conflicts.append("env_key")
        if self.experimental_bearer_token is not None:
            conflicts.append("experimental_bearer_token")
        if self.requires_openai_auth:
            conflicts.append("requires_openai_auth")
        if conflicts:
            raise ValueError(f"provider auth cannot be combined with {', '.join(conflicts)}")

    def api_key(self, env: Mapping[str, str] | None = None) -> str | None:
        if self.env_key is None:
            return None
        value = (env or os.environ).get(self.env_key)
        if value is None or not value.strip():
            raise OSError(self.env_key)
        return value

    def request_max_retries(self) -> int:
        return min(self.request_max_retries_value if self.request_max_retries_value is not None else DEFAULT_REQUEST_MAX_RETRIES, MAX_REQUEST_MAX_RETRIES)

    def stream_max_retries(self) -> int:
        return min(self.stream_max_retries_value if self.stream_max_retries_value is not None else DEFAULT_STREAM_MAX_RETRIES, MAX_STREAM_MAX_RETRIES)

    def stream_idle_timeout(self) -> int:
        return self.stream_idle_timeout_ms if self.stream_idle_timeout_ms is not None else DEFAULT_STREAM_IDLE_TIMEOUT_MS

    def websocket_connect_timeout(self) -> int:
        return self.websocket_connect_timeout_ms if self.websocket_connect_timeout_ms is not None else DEFAULT_WEBSOCKET_CONNECT_TIMEOUT_MS

    def to_api_provider(self, auth_mode: Any = None, env: Mapping[str, str] | None = None) -> ApiProvider:
        default_base_url = (
            CHATGPT_CODEX_BASE_URL
            if _is_chatgpt_auth_mode(auth_mode)
            else "https://api.openai.com/v1"
        )
        headers = _build_header_map(self.http_headers, self.env_http_headers, env or os.environ)
        return ApiProvider(
            name=self.name,
            base_url=self.base_url or default_base_url,
            query_params=self.query_params,
            headers=headers,
            request_max_retries=self.request_max_retries(),
            stream_idle_timeout_ms=self.stream_idle_timeout(),
        )

    @classmethod
    def create_openai_provider(cls, base_url: str | None = None) -> "ModelProviderInfo":
        return cls(
            name="OpenAI",
            base_url=base_url,
            http_headers={"version": ""},
            env_http_headers={
                "OpenAI-Organization": "OPENAI_ORGANIZATION",
                "OpenAI-Project": "OPENAI_PROJECT",
            },
            requires_openai_auth=True,
            supports_websockets=True,
        )

    @classmethod
    def create_amazon_bedrock_provider(
        cls,
        aws: ModelProviderAwsAuthInfo | None = None,
    ) -> "ModelProviderInfo":
        return cls(
            name="Amazon Bedrock",
            base_url=AMAZON_BEDROCK_DEFAULT_BASE_URL,
            aws=aws or ModelProviderAwsAuthInfo(),
            http_headers={"x-amzn-mantle-client-agent": "codex"},
        )

    def is_openai(self) -> bool:
        return self.name == "OpenAI"

    def is_amazon_bedrock(self) -> bool:
        return self.name == "Amazon Bedrock"

    def supports_remote_compaction(self) -> bool:
        return self.is_openai() or _is_azure_responses_provider(self.name, self.base_url)

    def has_command_auth(self) -> bool:
        return self.auth is not None


def built_in_model_providers(openai_base_url: str | None = None) -> dict[str, ModelProviderInfo]:
    return {
        OPENAI_PROVIDER_ID: ModelProviderInfo.create_openai_provider(openai_base_url),
        AMAZON_BEDROCK_PROVIDER_ID: ModelProviderInfo.create_amazon_bedrock_provider(),
        OLLAMA_OSS_PROVIDER_ID: create_oss_provider(DEFAULT_OLLAMA_PORT, WireApi.RESPONSES),
        LMSTUDIO_OSS_PROVIDER_ID: create_oss_provider(DEFAULT_LMSTUDIO_PORT, WireApi.RESPONSES),
    }


def merge_configured_model_providers(
    model_providers: Mapping[str, ModelProviderInfo],
    configured_model_providers: Mapping[str, ModelProviderInfo],
) -> dict[str, ModelProviderInfo]:
    merged = dict(model_providers)
    for key, provider in configured_model_providers.items():
        if key == AMAZON_BEDROCK_PROVIDER_ID:
            aws_override = provider.aws
            default_without_aws = replace(provider, aws=None)
            if default_without_aws != ModelProviderInfo():
                raise ValueError(
                    f"model_providers.{AMAZON_BEDROCK_PROVIDER_ID} only supports changing "
                    "`aws.profile` and `aws.region`; other non-default provider fields are not supported"
                )
            built_in = merged.get(AMAZON_BEDROCK_PROVIDER_ID)
            if built_in is not None and built_in.aws is not None and aws_override is not None:
                merged[AMAZON_BEDROCK_PROVIDER_ID] = replace(
                    built_in,
                    aws=ModelProviderAwsAuthInfo(
                        profile=aws_override.profile or built_in.aws.profile,
                        region=aws_override.region or built_in.aws.region,
                    ),
                )
        else:
            merged.setdefault(key, provider)
    return merged


def create_oss_provider(default_provider_port: int, wire_api: WireApi) -> ModelProviderInfo:
    port = _env_port("CODEX_OSS_PORT", default_provider_port)
    base_url = os.environ.get("CODEX_OSS_BASE_URL") or f"http://localhost:{port}/v1"
    if not base_url.strip():
        base_url = f"http://localhost:{port}/v1"
    return create_oss_provider_with_base_url(base_url, wire_api)


def create_oss_provider_with_base_url(base_url: str, wire_api: WireApi) -> ModelProviderInfo:
    return ModelProviderInfo(name="gpt-oss", base_url=base_url, wire_api=wire_api)


def _build_header_map(
    headers: Mapping[str, str] | None,
    env_headers: Mapping[str, str] | None,
    env: Mapping[str, str],
) -> dict[str, str]:
    result = {str(key): str(value) for key, value in dict(headers or {}).items()}
    for header, env_var in dict(env_headers or {}).items():
        value = env.get(env_var)
        if value is not None and value.strip():
            result[str(header)] = value
    return result


def _is_chatgpt_auth_mode(auth_mode: Any) -> bool:
    if auth_mode is None:
        return False
    value = getattr(auth_mode, "value", auth_mode)
    value = getattr(value, "name", value)
    return str(value).lower() in {"chatgpt", "chatgptauthtokens", "chatgpt_auth_tokens", "agentidentity", "agent_identity"}


def _is_azure_responses_provider(name: str, base_url: str | None) -> bool:
    return "azure" in name.lower() or (base_url is not None and "azure" in base_url.lower())


def _env_port(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _auth_info_from_mapping(value: Mapping[str, Any]) -> ModelProviderAuthInfo:
    data = dict(value)
    unknown = set(data) - {"command", "args", "timeout_ms", "refresh_interval_ms", "cwd"}
    if unknown:
        raise ValueError(f"unknown ModelProviderAuthInfo fields: {', '.join(sorted(unknown))}")
    command = data.get("command")
    if not isinstance(command, str):
        raise TypeError("auth.command must be a string")
    args = data.get("args", ())
    if not isinstance(args, (list, tuple)) or not all(isinstance(item, str) for item in args):
        raise TypeError("auth.args must be a list of strings")
    cwd_raw = data.get("cwd", ".")
    if not isinstance(cwd_raw, str):
        raise TypeError("auth.cwd must be a string")
    refresh_interval_ms = _optional_non_negative_int(data.get("refresh_interval_ms"), "refresh_interval_ms")
    return ModelProviderAuthInfo(
        command=command,
        args=tuple(args),
        timeout_ms=_optional_positive_int(data.get("timeout_ms"), "timeout_ms") or 5_000,
        refresh_interval_ms=300_000 if refresh_interval_ms is None else refresh_interval_ms,
        cwd=Path(cwd_raw).resolve(strict=False),
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("expected a string")
    return value


def _optional_str_mapping(value: Any, field_name: str) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise TypeError(f"{field_name} must map strings to strings")
        result[key] = item
    return result


def _optional_non_negative_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _optional_positive_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _optional_bool(value: Any, field_name: str, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")
    return value


__all__ = [
    "AMAZON_BEDROCK_DEFAULT_BASE_URL",
    "AMAZON_BEDROCK_GPT_5_4_MODEL_ID",
    "AMAZON_BEDROCK_PROVIDER_ID",
    "CHATGPT_CODEX_BASE_URL",
    "DEFAULT_LMSTUDIO_PORT",
    "DEFAULT_OLLAMA_PORT",
    "DEFAULT_WEBSOCKET_CONNECT_TIMEOUT_MS",
    "LEGACY_OLLAMA_CHAT_PROVIDER_ID",
    "LMSTUDIO_OSS_PROVIDER_ID",
    "ModelProviderAwsAuthInfo",
    "ModelProviderAuthInfo",
    "ModelProviderInfo",
    "OLLAMA_CHAT_PROVIDER_REMOVED_ERROR",
    "OLLAMA_OSS_PROVIDER_ID",
    "OPENAI_PROVIDER_ID",
    "WireApi",
    "built_in_model_providers",
    "create_oss_provider",
    "create_oss_provider_with_base_url",
    "merge_configured_model_providers",
]
