"""API error contracts for the Rust ``codex-api`` port.

Rust source:
- ``codex/codex-rs/codex-api/src/error.rs``
"""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

from pycodex.codex_client import TransportError


@dataclass(frozen=True)
class ApiError(Exception):
    kind: str
    message: str | None = None
    status: int | str | None = None
    delay: float | None = None
    transport: TransportError | None = None

    @classmethod
    def transport_error(cls, error: TransportError) -> "ApiError":
        return cls("transport", transport=error)

    @classmethod
    def api(cls, status: int | str, message: str) -> "ApiError":
        return cls("api", status=status, message=message)

    @classmethod
    def stream(cls, message: str) -> "ApiError":
        return cls("stream", message=message)

    @classmethod
    def context_window_exceeded(cls) -> "ApiError":
        return cls("context_window_exceeded")

    @classmethod
    def quota_exceeded(cls) -> "ApiError":
        return cls("quota_exceeded")

    @classmethod
    def usage_not_included(cls) -> "ApiError":
        return cls("usage_not_included")

    @classmethod
    def retryable(cls, message: str, delay: float | None = None) -> "ApiError":
        return cls("retryable", message=message, delay=delay)

    @classmethod
    def rate_limit(cls, message: str) -> "ApiError":
        return cls("rate_limit", message=message)

    @classmethod
    def invalid_request(cls, message: str) -> "ApiError":
        return cls("invalid_request", message=message)

    @classmethod
    def cyber_policy(cls, message: str) -> "ApiError":
        return cls("cyber_policy", message=message)

    @classmethod
    def server_overloaded(cls) -> "ApiError":
        return cls("server_overloaded")

    @classmethod
    def from_rate_limit_error(cls, error: Any) -> "ApiError":
        return cls.rate_limit(str(error))

    def __str__(self) -> str:
        if self.kind == "transport":
            return str(self.transport)
        if self.kind == "api":
            return f"api error {_format_status(self.status)}: {self.message}"
        if self.kind == "stream":
            return f"stream error: {self.message}"
        if self.kind == "context_window_exceeded":
            return "context window exceeded"
        if self.kind == "quota_exceeded":
            return "quota exceeded"
        if self.kind == "usage_not_included":
            return "usage not included"
        if self.kind == "retryable":
            return f"retryable error: {self.message}"
        if self.kind == "rate_limit":
            return f"rate limit: {self.message}"
        if self.kind == "invalid_request":
            return f"invalid request: {self.message}"
        if self.kind == "cyber_policy":
            return f"cyber policy: {self.message}"
        if self.kind == "server_overloaded":
            return "server overloaded"
        return self.kind


def _format_status(status: int | str | None) -> str:
    if isinstance(status, int):
        try:
            http_status = HTTPStatus(status)
        except ValueError:
            return str(status)
        return f"{http_status.value} {http_status.phrase}"
    return str(status)
