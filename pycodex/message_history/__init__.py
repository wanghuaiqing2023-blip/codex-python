"""Python API boundary for Rust crate ``codex-message-history``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


class MessageHistoryNotImplementedError(NotImplementedError):
    """Raised when message history persistence behavior is not ported yet."""


@dataclass(frozen=True)
class HistoryEntry:
    session_id: str
    ts: int
    text: str


@dataclass(frozen=True)
class HistoryConfig:
    codex_home: Path
    persistence: Any
    max_bytes: int | None = None

    @classmethod
    def new(cls, codex_home: str | Path, history: Any) -> "HistoryConfig":
        return cls(
            codex_home=Path(codex_home),
            persistence=getattr(history, "persistence", history),
            max_bytes=getattr(history, "max_bytes", None),
        )


async def append_entry(text: str, conversation_id: Any, config: HistoryConfig) -> None:
    raise MessageHistoryNotImplementedError("append_entry is not ported yet")


async def history_metadata(config: HistoryConfig) -> tuple[int, int]:
    raise MessageHistoryNotImplementedError("history_metadata is not ported yet")


def lookup(log_id: int, offset: int, config: HistoryConfig) -> HistoryEntry | None:
    raise MessageHistoryNotImplementedError("lookup is not ported yet")


__all__ = [
    "HistoryConfig",
    "HistoryEntry",
    "MessageHistoryNotImplementedError",
    "append_entry",
    "history_metadata",
    "lookup",
]
