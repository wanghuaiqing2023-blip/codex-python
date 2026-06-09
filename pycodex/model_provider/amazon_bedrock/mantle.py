"""Port of Rust ``codex-model-provider::amazon_bedrock::mantle``.

Rust source:
- ``codex/codex-rs/model-provider/src/amazon_bedrock/mantle.rs``
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable


BEDROCK_MANTLE_SERVICE_NAME = "bedrock-mantle"
BEDROCK_MANTLE_SUPPORTED_REGIONS = (
    "us-east-2",
    "us-east-1",
    "us-west-2",
    "ap-southeast-3",
    "ap-south-1",
    "ap-northeast-1",
    "eu-central-1",
    "eu-west-1",
    "eu-west-2",
    "eu-south-1",
    "eu-north-1",
    "sa-east-1",
)


class CodexFatalError(RuntimeError):
    def __str__(self) -> str:
        return f"Fatal error: {self.args[0]}" if self.args else "Fatal error"


@dataclass(frozen=True)
class AwsAuthConfig:
    profile: str | None
    region: str | None
    service: str


def aws_auth_config(aws: Any) -> AwsAuthConfig:
    return AwsAuthConfig(
        profile=_get(aws, "profile"),
        region=region_from_config(aws),
        service=BEDROCK_MANTLE_SERVICE_NAME,
    )


def region_from_config(aws: Any) -> str | None:
    region = _get(aws, "region")
    if region is None:
        return None
    trimmed = str(region).strip()
    return trimmed or None


def base_url(region: str) -> str:
    if region in BEDROCK_MANTLE_SUPPORTED_REGIONS:
        return f"https://bedrock-mantle.{region}.api.aws/openai/v1"
    raise CodexFatalError(f"Amazon Bedrock Mantle does not support region `{region}`")


async def runtime_base_url(aws: Any, resolve_auth_method: Callable[[Any], Any] | None = None) -> str:
    region = await resolve_region(aws, resolve_auth_method=resolve_auth_method)
    return base_url(region)


async def resolve_region(aws: Any, resolve_auth_method: Callable[[Any], Any] | None = None) -> str:
    if resolve_auth_method is None:
        raise NotImplementedError("Amazon Bedrock auth method resolver is not configured")
    result = resolve_auth_method(aws)
    if inspect.isawaitable(result):
        result = await result

    region = _get(result, "region")
    if region is not None:
        return str(region)

    context = _get(result, "context")
    if context is not None:
        region_method = getattr(context, "region", None)
        if callable(region_method):
            return str(region_method())
        context_region = _get(context, "region")
        if context_region is not None:
            return str(context_region)

    raise CodexFatalError("Amazon Bedrock auth method did not provide a region")


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


__all__ = [
    "BEDROCK_MANTLE_SERVICE_NAME",
    "BEDROCK_MANTLE_SUPPORTED_REGIONS",
    "AwsAuthConfig",
    "CodexFatalError",
    "aws_auth_config",
    "base_url",
    "region_from_config",
    "resolve_region",
    "runtime_base_url",
]
