"""Errors for the readiness flag."""

from __future__ import annotations


class ReadinessError(Exception):
    pass


class TokenLockFailed(ReadinessError):
    def __init__(self) -> None:
        super().__init__("Failed to acquire readiness token lock")


class FlagAlreadyReady(ReadinessError):
    def __init__(self) -> None:
        super().__init__("Flag is already ready. Impossible to subscribe")


__all__ = ["FlagAlreadyReady", "ReadinessError", "TokenLockFailed"]
