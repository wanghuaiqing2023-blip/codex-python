"""Port of Rust ``codex-model-provider::amazon_bedrock::auth``.

Rust source:
- ``codex/codex-rs/model-provider/src/amazon_bedrock/auth.rs``
"""

from __future__ import annotations

import inspect
import os
from dataclasses import dataclass
from typing import Any, Callable

from pycodex.model_provider.bearer_auth_provider import BearerAuthProvider

from .mantle import CodexFatalError, aws_auth_config, region_from_config


AWS_BEARER_TOKEN_BEDROCK_ENV_VAR = "AWS_BEARER_TOKEN_BEDROCK"


@dataclass(frozen=True)
class EnvBearerToken:
    token: str
    region: str


@dataclass(frozen=True)
class AwsSdkAuth:
    context: Any


BedrockAuthMethod = EnvBearerToken | AwsSdkAuth


async def resolve_auth_method(
    aws: Any,
    *,
    env: dict[str, str] | None = None,
    aws_context_loader: Callable[[Any], Any] | None = None,
) -> BedrockAuthMethod:
    token = bearer_token_from_env(env)
    if token is not None:
        return EnvBearerToken(token=token, region=bearer_token_region_from_config(aws))

    if aws_context_loader is None:
        raise NotImplementedError("Amazon Bedrock AWS auth context loader is not configured")
    result = aws_context_loader(aws_auth_config(aws))
    if inspect.isawaitable(result):
        result = await result
    return AwsSdkAuth(context=result)


async def resolve_provider_auth(
    aws: Any,
    *,
    env: dict[str, str] | None = None,
    aws_context_loader: Callable[[Any], Any] | None = None,
) -> Any:
    method = await resolve_auth_method(aws, env=env, aws_context_loader=aws_context_loader)
    if isinstance(method, EnvBearerToken):
        return BearerAuthProvider(token=method.token, account_id=None, is_fedramp_account=False)
    return BedrockMantleSigV4AuthProvider.new(method.context)


def bearer_token_from_env(env: dict[str, str] | None = None) -> str | None:
    env_map = os.environ if env is None else env
    token = env_map.get(AWS_BEARER_TOKEN_BEDROCK_ENV_VAR)
    if token is None:
        return None
    trimmed = token.strip()
    return trimmed or None


def bearer_token_region_from_config(aws: Any) -> str:
    region = region_from_config(aws)
    if region is None:
        raise CodexFatalError(
            "Amazon Bedrock bearer token auth requires "
            "`model_providers.amazon-bedrock.aws.region`"
        )
    return region


def aws_auth_error_to_codex_error(error: BaseException | str) -> CodexFatalError:
    return CodexFatalError(f"failed to resolve Amazon Bedrock auth: {error}")


def aws_auth_error_to_auth_error(error: BaseException | str) -> OSError:
    return OSError(str(error))


def remove_headers_not_preserved_by_bedrock_mantle(headers: dict[str, str]) -> None:
    for name in [name for name in headers if "_" in str(name)]:
        headers.pop(name, None)


@dataclass(frozen=True)
class BedrockMantleSigV4AuthProvider:
    context: Any

    @classmethod
    def new(cls, context: Any) -> "BedrockMantleSigV4AuthProvider":
        return cls(context=context)

    def add_auth_headers(self, headers: dict[str, str]) -> None:
        return None

    async def apply_auth(self, request: Any) -> Any:
        headers = _headers(request)
        remove_headers_not_preserved_by_bedrock_mantle(headers)
        signer = getattr(self.context, "sign", None)
        if not callable(signer):
            raise NotImplementedError("Amazon Bedrock SigV4 signing context is not configured")
        result = signer(request)
        if inspect.isawaitable(result):
            result = await result
        return result


def _headers(request: Any) -> dict[str, str]:
    if isinstance(request, dict):
        headers = request.setdefault("headers", {})
        return headers
    headers = getattr(request, "headers", None)
    if headers is None:
        headers = {}
        setattr(request, "headers", headers)
    return headers


__all__ = [
    "AWS_BEARER_TOKEN_BEDROCK_ENV_VAR",
    "AwsSdkAuth",
    "BedrockAuthMethod",
    "BedrockMantleSigV4AuthProvider",
    "EnvBearerToken",
    "aws_auth_error_to_auth_error",
    "aws_auth_error_to_codex_error",
    "bearer_token_from_env",
    "bearer_token_region_from_config",
    "remove_headers_not_preserved_by_bedrock_mantle",
    "resolve_auth_method",
    "resolve_provider_auth",
]
