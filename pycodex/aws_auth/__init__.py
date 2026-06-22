"""Python alignment surface for Rust crate ``codex-aws-auth``."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from .config import (
    AwsAuthConfig,
    AwsAuthError,
    AwsCredentials,
    AwsSdkConfig,
    EmptyService,
    MissingCredentialsProvider,
    MissingRegion,
    SharedCredentialsProvider,
    credentials_provider,
    load_sdk_config,
    resolved_region,
)
from .signing import (
    AwsRequestToSign,
    AwsSignedRequest,
    BuildHttpRequest,
    InvalidHeaderValue,
    InvalidUri,
    SigningFailure,
    SigningParams,
    SigningRequest,
    header_value,
    sign_request,
)


CredentialsErrorKind = Literal[
    "provider_error",
    "provider_timed_out",
    "not_loaded_no_source",
    "invalid_configuration",
    "unhandled",
]


@dataclass(frozen=True)
class Credentials(AwsAuthError):
    """Credential-loading error wrapper used by ``AwsAuthError::Credentials``."""

    kind: CredentialsErrorKind
    message: str

    @classmethod
    def provider_error(cls, message: str) -> "Credentials":
        return cls("provider_error", message)

    @classmethod
    def provider_timed_out(cls, seconds: int | float | None = None) -> "Credentials":
        detail = "operation timed out" if seconds is None else f"operation timed out after {seconds}s"
        return cls("provider_timed_out", detail)

    @classmethod
    def not_loaded_no_source(cls) -> "Credentials":
        return cls("not_loaded_no_source", "no credentials source was configured")

    @classmethod
    def invalid_configuration(cls, message: str) -> "Credentials":
        return cls("invalid_configuration", message)

    @classmethod
    def unhandled(cls, message: str) -> "Credentials":
        return cls("unhandled", message)

    def __str__(self) -> str:
        return f"failed to load AWS credentials: {self.message}"


def is_retryable(error: BaseException) -> bool:
    """Return whether retrying could reasonably recover from this auth error."""

    return isinstance(error, Credentials) and error.kind in {
        "provider_error",
        "provider_timed_out",
    }


@dataclass(frozen=True)
class AwsAuthContext:
    """Loaded AWS auth context that can sign outbound HTTP requests."""

    credentials_provider: SharedCredentialsProvider
    _region: str
    _service: str

    @classmethod
    async def load(
        cls,
        config: AwsAuthConfig,
        *,
        env: dict[str, str] | None = None,
    ) -> "AwsAuthContext":
        sdk_config = await load_sdk_config(config, env=env)
        provider = credentials_provider(sdk_config)
        region = resolved_region(sdk_config)
        return cls(provider, region, config.service.strip())

    def region(self) -> str:
        return self._region

    def service(self) -> str:
        return self._service

    async def sign(self, request: AwsRequestToSign) -> AwsSignedRequest:
        return await self.sign_at(request, datetime.now(tz=UTC))

    async def sign_at(
        self,
        request: AwsRequestToSign,
        time: datetime | int | float,
    ) -> AwsSignedRequest:
        return sign_request(
            self.credentials_provider.credentials,
            self._region,
            self._service,
            request,
            time,
        )

    def __repr__(self) -> str:
        return (
            "AwsAuthContext("
            f"region={self._region!r}, service={self._service!r}, ..)"
        )


AwsAuthError.is_retryable = lambda self: is_retryable(self)  # type: ignore[attr-defined]

__all__ = [
    "AwsAuthConfig",
    "AwsAuthContext",
    "AwsAuthError",
    "AwsCredentials",
    "AwsRequestToSign",
    "AwsSignedRequest",
    "AwsSdkConfig",
    "BuildHttpRequest",
    "Credentials",
    "EmptyService",
    "InvalidHeaderValue",
    "InvalidUri",
    "MissingCredentialsProvider",
    "MissingRegion",
    "SigningFailure",
    "SigningParams",
    "SigningRequest",
    "SharedCredentialsProvider",
    "credentials_provider",
    "header_value",
    "is_retryable",
    "load_sdk_config",
    "resolved_region",
    "sign_request",
]
