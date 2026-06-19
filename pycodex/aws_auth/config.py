"""AWS SDK config helpers for request signing.

Python port of ``codex/codex-rs/aws-auth/src/config.rs``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


class AwsAuthError(Exception):
    """Base class for AWS auth config errors."""

    retryable = False


class EmptyService(AwsAuthError):
    def __str__(self) -> str:
        return "AWS service name must not be empty"


class MissingCredentialsProvider(AwsAuthError):
    def __str__(self) -> str:
        return "AWS SDK config did not resolve a credentials provider"


class MissingRegion(AwsAuthError):
    def __str__(self) -> str:
        return "AWS SDK config did not resolve a region"


@dataclass(frozen=True)
class AwsAuthConfig:
    """AWS auth configuration used to resolve credentials and sign requests."""

    profile: str | None
    region: str | None
    service: str


@dataclass(frozen=True)
class AwsCredentials:
    access_key_id: str
    secret_access_key: str
    session_token: str | None = None


@dataclass(frozen=True)
class SharedCredentialsProvider:
    credentials: AwsCredentials


@dataclass(frozen=True)
class AwsSdkConfig:
    """Dependency-light stand-in for Rust AWS SDK ``SdkConfig``."""

    profile: str | None = None
    region: str | None = None
    credentials_provider: SharedCredentialsProvider | None = None


async def load_sdk_config(
    config: AwsAuthConfig,
    *,
    env: Mapping[str, str] | None = None,
) -> AwsSdkConfig:
    """Load a small SDK-config equivalent for the selected profile/region."""

    if config.service.strip() == "":
        raise EmptyService()
    env = os.environ if env is None else env
    return AwsSdkConfig(
        profile=config.profile,
        region=config.region or env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION"),
        credentials_provider=_credentials_provider_from_env(env),
    )


def credentials_provider(sdk_config: AwsSdkConfig) -> SharedCredentialsProvider:
    provider = getattr(sdk_config, "credentials_provider", None)
    if provider is None:
        raise MissingCredentialsProvider()
    return provider


def resolved_region(sdk_config: AwsSdkConfig) -> str:
    region = getattr(sdk_config, "region", None)
    if region is None:
        raise MissingRegion()
    return str(region)


def _credentials_provider_from_env(env: Mapping[str, str]) -> SharedCredentialsProvider | None:
    access_key_id = env.get("AWS_ACCESS_KEY_ID")
    secret_access_key = env.get("AWS_SECRET_ACCESS_KEY")
    if not access_key_id or not secret_access_key:
        return None
    return SharedCredentialsProvider(
        AwsCredentials(
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            session_token=env.get("AWS_SESSION_TOKEN"),
        )
    )


__all__ = [
    "AwsAuthConfig",
    "AwsAuthError",
    "AwsCredentials",
    "AwsSdkConfig",
    "EmptyService",
    "MissingCredentialsProvider",
    "MissingRegion",
    "SharedCredentialsProvider",
    "credentials_provider",
    "load_sdk_config",
    "resolved_region",
]
