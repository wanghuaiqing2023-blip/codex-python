"""Graph model types ported from ``codex-state/src/model/graph.rs``."""

from __future__ import annotations

from enum import Enum


class DirectionalThreadSpawnEdgeStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"

    def __str__(self) -> str:
        return self.value

    def as_ref(self) -> str:
        return self.value

    @classmethod
    def parse(cls, value: str) -> "DirectionalThreadSpawnEdgeStatus":
        try:
            return cls(value)
        except ValueError as exc:
            raise ValueError(f"invalid directional thread spawn edge status: {value}") from exc


__all__ = ["DirectionalThreadSpawnEdgeStatus"]
