"""Error contracts for the Rust ``codex-client`` port.

Rust source:
- ``codex/codex-rs/codex-client/src/error.rs``
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class TransportError(Exception):
    """Python representation of Rust ``TransportError`` variants."""

    kind: str
    message: str | None = None
    status: int | None = None
    url: str | None = None
    headers: Mapping[str, str] | None = None
    body: str | None = None

    @classmethod
    def http(
        cls,
        status: int,
        *,
        url: str | None = None,
        headers: Mapping[str, str] | None = None,
        body: str | None = None,
    ) -> "TransportError":
        return cls("http", status=status, url=url, headers=headers, body=body)

    @classmethod
    def retry_limit(cls) -> "TransportError":
        return cls("retry_limit")

    @classmethod
    def timeout(cls) -> "TransportError":
        return cls("timeout")

    @classmethod
    def network(cls, message: str) -> "TransportError":
        return cls("network", message=message)

    @classmethod
    def build(cls, message: str) -> "TransportError":
        return cls("build", message=message)

    def __str__(self) -> str:
        if self.kind == "http":
            return f"http {self.status}: {self.body!r}"
        if self.kind == "retry_limit":
            return "retry limit reached"
        if self.kind == "timeout":
            return "timeout"
        if self.kind == "network":
            return f"network error: {self.message}"
        if self.kind == "build":
            return f"request build error: {self.message}"
        return self.kind


@dataclass(frozen=True)
class StreamError(Exception):
    """Python representation of Rust ``StreamError`` variants."""

    kind: str
    message: str | None = None

    @classmethod
    def stream(cls, message: str) -> "StreamError":
        return cls("stream", message)

    @classmethod
    def timeout(cls) -> "StreamError":
        return cls("timeout")

    def __str__(self) -> str:
        if self.kind == "stream":
            return f"stream failed: {self.message}"
        if self.kind == "timeout":
            return "timeout"
        return self.kind
