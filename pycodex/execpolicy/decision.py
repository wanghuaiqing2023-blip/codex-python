"""Rust-aligned codex-execpolicy module."""

from __future__ import annotations

from enum import Enum

from .error import InvalidDecisionError

class Decision(str, Enum):
    ALLOW = "allow"
    PROMPT = "prompt"
    FORBIDDEN = "forbidden"

    @classmethod
    def parse(cls, raw: object) -> "Decision":
        if isinstance(raw, cls):
            return raw
        try:
            return cls(str(raw))
        except ValueError as exc:
            raise InvalidDecisionError(f"invalid decision: {raw}") from exc

    def _rank(self) -> int:
        return (Decision.ALLOW, Decision.PROMPT, Decision.FORBIDDEN).index(self)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Decision):
            return NotImplemented
        return self._rank() < other._rank()

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Decision):
            return NotImplemented
        return self._rank() <= other._rank()

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Decision):
            return NotImplemented
        return self._rank() > other._rank()

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Decision):
            return NotImplemented
        return self._rank() >= other._rank()

__all__ = ['Decision']
