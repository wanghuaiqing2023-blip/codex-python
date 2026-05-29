"""Attestation provider boundary.

Ported from ``codex/codex-rs/core/src/attestation.rs``.

Rust models this as a host integration trait that returns a future resolving to
an optional ``HeaderValue``.  The Python port keeps the same boundary: policy
and generation live with the provider, while core code only constructs request
context and conditionally asks for an ``x-oai-attestation`` header value.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pycodex.protocol import ThreadId

X_OAI_ATTESTATION_HEADER = "x-oai-attestation"
AttestationHeaderValue = str
GenerateAttestationResult = AttestationHeaderValue | Awaitable[AttestationHeaderValue | None] | None


@dataclass(frozen=True)
class AttestationContext:
    thread_id: ThreadId

    def __post_init__(self) -> None:
        if not isinstance(self.thread_id, ThreadId):
            raise TypeError("thread_id must be a ThreadId")


@runtime_checkable
class AttestationProvider(Protocol):
    def header_for_request(self, context: AttestationContext) -> GenerateAttestationResult:
        ...


async def generate_attestation_header_for_request(
    *,
    include_attestation: bool,
    attestation_provider: AttestationProvider | None,
    thread_id: ThreadId,
) -> AttestationHeaderValue | None:
    if not isinstance(include_attestation, bool):
        raise TypeError("include_attestation must be a bool")
    if not isinstance(thread_id, ThreadId):
        raise TypeError("thread_id must be a ThreadId")
    if not include_attestation or attestation_provider is None:
        return None
    if not hasattr(attestation_provider, "header_for_request"):
        raise TypeError("attestation_provider must provide header_for_request")

    result = attestation_provider.header_for_request(AttestationContext(thread_id=thread_id))
    if inspect.isawaitable(result):
        result = await result
    return normalize_attestation_header_value(result)


def normalize_attestation_header_value(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("attestation header value must be a string")
    if "\r" in value or "\n" in value:
        raise ValueError("attestation header value must not contain CR or LF")
    return value


__all__ = [
    "AttestationContext",
    "AttestationHeaderValue",
    "AttestationProvider",
    "GenerateAttestationResult",
    "X_OAI_ATTESTATION_HEADER",
    "generate_attestation_header_for_request",
    "normalize_attestation_header_value",
]
