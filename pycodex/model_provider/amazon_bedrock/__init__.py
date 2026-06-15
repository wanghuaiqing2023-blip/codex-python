"""Amazon Bedrock model-provider helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from pycodex.model_provider import ProviderAccountState, ProviderCapabilities
from pycodex.model_provider_info import AMAZON_BEDROCK_GPT_5_4_MODEL_ID, ModelProviderAwsAuthInfo, ModelProviderInfo
from pycodex.models_manager import StaticModelsManager
from pycodex.protocol import ProviderAccount

from .mantle import (
    BEDROCK_MANTLE_SERVICE_NAME,
    BEDROCK_MANTLE_SUPPORTED_REGIONS,
    AwsAuthConfig,
    aws_auth_config,
    base_url,
    region_from_config,
    runtime_base_url,
)
from .catalog import (
    GPT_5_4_CONTEXT_WINDOW,
    GPT_5_4_MAX_CONTEXT_WINDOW,
    GPT_OSS_CONTEXT_WINDOW,
    bedrock_oss_model,
    gpt_5_4_cmb_bedrock_model,
    gpt_5_4_cmb_reasoning_levels,
    reasoning_effort_preset,
    static_model_catalog,
)
from .auth import (
    AWS_BEARER_TOKEN_BEDROCK_ENV_VAR,
    AwsSdkAuth,
    BedrockMantleSigV4AuthProvider,
    EnvBearerToken,
    bearer_token_from_env,
    bearer_token_region_from_config,
    remove_headers_not_preserved_by_bedrock_mantle,
    resolve_auth_method,
    resolve_provider_auth,
)

@dataclass
class AmazonBedrockModelProvider:
    info_value: ModelProviderInfo
    aws_context_loader: Any = None

    def __post_init__(self) -> None:
        aws = self.info_value.aws
        if aws is None:
            aws = ModelProviderAwsAuthInfo(profile=None, region=None)
        self.aws = aws

    @classmethod
    def new(cls, provider_info: ModelProviderInfo, aws_context_loader: Any = None) -> "AmazonBedrockModelProvider":
        return cls(provider_info, aws_context_loader=aws_context_loader)

    def info(self) -> ModelProviderInfo:
        return self.info_value

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            namespace_tools=True,
            image_generation=False,
            web_search=False,
        )

    def approval_review_preferred_model(self) -> str:
        return AMAZON_BEDROCK_GPT_5_4_MODEL_ID

    def auth_manager(self) -> None:
        return None

    async def auth(self) -> None:
        return None

    def account_state(self) -> ProviderAccountState:
        return ProviderAccountState(
            account=ProviderAccount.amazon_bedrock(),
            requires_openai_auth=False,
        )

    async def api_provider(self) -> Any:
        base = await runtime_base_url(self.aws, resolve_auth_method=self._resolve_auth_method)
        info = replace(self.info_value, base_url=base)
        return info.to_api_provider(None)

    async def runtime_base_url(self) -> str:
        return await runtime_base_url(self.aws, resolve_auth_method=self._resolve_auth_method)

    async def api_auth(self) -> Any:
        return await resolve_provider_auth(self.aws, aws_context_loader=self.aws_context_loader)

    def models_manager(self, codex_home: str | Path, config_model_catalog: Any = None) -> StaticModelsManager:
        del codex_home
        return StaticModelsManager(
            auth_manager=None,
            model_catalog=config_model_catalog if config_model_catalog is not None else static_model_catalog(),
        )

    async def _resolve_auth_method(self, aws: Any) -> Any:
        return await resolve_auth_method(aws, aws_context_loader=self.aws_context_loader)


__all__ = [
    "BEDROCK_MANTLE_SERVICE_NAME",
    "BEDROCK_MANTLE_SUPPORTED_REGIONS",
    "AwsAuthConfig",
    "aws_auth_config",
    "base_url",
    "region_from_config",
    "runtime_base_url",
    "AmazonBedrockModelProvider",
    "StaticModelsManager",
    "GPT_5_4_CONTEXT_WINDOW",
    "GPT_5_4_MAX_CONTEXT_WINDOW",
    "GPT_OSS_CONTEXT_WINDOW",
    "bedrock_oss_model",
    "gpt_5_4_cmb_bedrock_model",
    "gpt_5_4_cmb_reasoning_levels",
    "reasoning_effort_preset",
    "static_model_catalog",
    "AWS_BEARER_TOKEN_BEDROCK_ENV_VAR",
    "AwsSdkAuth",
    "BedrockMantleSigV4AuthProvider",
    "EnvBearerToken",
    "bearer_token_from_env",
    "bearer_token_region_from_config",
    "remove_headers_not_preserved_by_bedrock_mantle",
    "resolve_auth_method",
    "resolve_provider_auth",
]
