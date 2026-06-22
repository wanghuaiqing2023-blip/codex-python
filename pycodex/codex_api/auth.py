"""Auth contracts for the Rust ``codex-api`` port.

Rust source:
- ``codex/codex-rs/codex-api/src/auth.rs``
"""

from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass
from typing import Protocol
from typing import TypeAlias

from pycodex.codex_client import Request
from pycodex.codex_client import TransportError


AUTHORIZATION = "authorization"


@dataclass(frozen=True)
class AuthError(Exception):
    kind: str
    message: str

    @classmethod
    def build(cls, message: str) -> "AuthError":
        return cls("build", message)

    @classmethod
    def transient(cls, message: str) -> "AuthError":
        return cls("transient", message)

    def __str__(self) -> str:
        if self.kind == "build":
            return f"request auth build error: {self.message}"
        if self.kind == "transient":
            return f"transient auth error: {self.message}"
        return self.message

    def to_transport_error(self) -> TransportError:
        if self.kind == "build":
            return TransportError.build(self.message)
        if self.kind == "transient":
            return TransportError.network(self.message)
        return TransportError.network(self.message)


class AuthProvider(Protocol):
    """Applies authentication to API requests.

    Header-only providers implement ``add_auth_headers``. Request-signing
    providers may override ``apply_auth`` by subclassing ``HeaderAuthProvider``
    or by exposing an async method with the same contract.
    """

    def add_auth_headers(self, headers: MutableMapping[str, str]) -> None:
        ...

    def to_auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        self.add_auth_headers(headers)
        return _case_insensitive_header_map(headers)

    async def apply_auth(self, request: Request) -> Request:
        headers = dict(request.headers or {})
        self.add_auth_headers(headers)
        return request.with_headers(_case_insensitive_header_map(headers))


SharedAuthProvider: TypeAlias = AuthProvider


@dataclass(frozen=True)
class AuthHeaderTelemetry:
    attached: bool = False
    name: str | None = None


def auth_header_telemetry(auth: AuthProvider) -> AuthHeaderTelemetry:
    headers: dict[str, str] = {}
    auth.add_auth_headers(headers)
    name = "authorization" if _contains_header(headers, AUTHORIZATION) else None
    return AuthHeaderTelemetry(attached=name is not None, name=name)


def _contains_header(headers: MutableMapping[str, str], name: str) -> bool:
    wanted = name.lower()
    return any(key.lower() == wanted for key in headers)


def _case_insensitive_header_map(headers: MutableMapping[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in headers.items():
        wanted = key.lower()
        for existing in list(normalized):
            if existing.lower() == wanted:
                del normalized[existing]
        normalized[key] = value
    return normalized
