"""Agent graph store error types.

Python port of ``codex/codex-rs/agent-graph-store/src/error.rs``.
"""

from __future__ import annotations

from typing import TypeAlias, TypeVar


T = TypeVar("T")
AgentGraphStoreResult: TypeAlias = T


class AgentGraphStoreError(Exception):
    """Base class for agent graph store errors."""

    variant: str

    def __init__(self, message: str) -> None:
        if not isinstance(message, str):
            raise TypeError("message must be a string")
        self.message = message
        super().__init__(str(self))


class InvalidRequest(AgentGraphStoreError):
    """The caller supplied invalid request data."""

    variant = "invalid_request"

    def __str__(self) -> str:
        return f"invalid agent graph store request: {self.message}"


class Internal(AgentGraphStoreError):
    """Implementation failure that does not fit a more specific category."""

    variant = "internal"

    def __str__(self) -> str:
        return f"agent graph store internal error: {self.message}"


def invalid_request(message: str) -> InvalidRequest:
    return InvalidRequest(message)


def internal(message: str) -> Internal:
    return Internal(message)


__all__ = [
    "AgentGraphStoreError",
    "AgentGraphStoreResult",
    "Internal",
    "InvalidRequest",
    "internal",
    "invalid_request",
]
