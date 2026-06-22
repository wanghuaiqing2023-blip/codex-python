"""Thread-spawn graph types.

Python port of ``codex/codex-rs/agent-graph-store/src/types.rs``.
"""

from __future__ import annotations

from enum import Enum


class ThreadSpawnEdgeStatus(str, Enum):
    """Lifecycle status attached to a directional thread-spawn edge."""

    Open = "open"
    Closed = "closed"

    @classmethod
    def from_json(cls, value: str) -> "ThreadSpawnEdgeStatus":
        if not isinstance(value, str):
            raise TypeError("thread spawn edge status must be a string")
        try:
            return cls(value)
        except ValueError as exc:
            raise ValueError(f"unknown thread spawn edge status: {value}") from exc

    def to_json(self) -> str:
        return self.value

    def __str__(self) -> str:
        return self.value


__all__ = ["ThreadSpawnEdgeStatus"]
