"""Memory citation protocol models.

Ported from ``codex/codex-rs/protocol/src/memory_citation.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


JsonValue = Any


def _mapping(value: JsonValue, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a mapping")
    return value


def _required_str(value: dict[str, JsonValue], key: str) -> str:
    if key not in value:
        raise KeyError(key)
    raw = value[key]
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


def _required_int(value: dict[str, JsonValue], key: str) -> int:
    if key not in value:
        raise KeyError(key)
    raw = value[key]
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise TypeError(f"{key} must be an integer")
    if raw < 0:
        raise ValueError(f"{key} must be non-negative")
    return raw


@dataclass(frozen=True)
class MemoryCitationEntry:
    path: str
    line_start: int
    line_end: int
    note: str

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "MemoryCitationEntry":
        data = _mapping(value, "memory citation entry")
        return cls(
            path=_required_str(data, "path"),
            line_start=_required_int(data, "lineStart"),
            line_end=_required_int(data, "lineEnd"),
            note=_required_str(data, "note"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "path": self.path,
            "lineStart": self.line_start,
            "lineEnd": self.line_end,
            "note": self.note,
        }


@dataclass(frozen=True)
class MemoryCitation:
    entries: tuple[MemoryCitationEntry, ...] = ()
    rollout_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.entries, tuple):
            object.__setattr__(self, "entries", tuple(self.entries))
        if not isinstance(self.rollout_ids, tuple):
            object.__setattr__(self, "rollout_ids", tuple(self.rollout_ids))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "MemoryCitation":
        data = _mapping(value, "memory citation")
        entries = data.get("entries", [])
        rollout_ids = data.get("rolloutIds", [])
        if not isinstance(entries, list):
            raise TypeError("entries must be a list")
        if not isinstance(rollout_ids, list):
            raise TypeError("rolloutIds must be a list")
        return cls(
            entries=tuple(MemoryCitationEntry.from_mapping(item) for item in entries),
            rollout_ids=tuple(str(item) for item in rollout_ids),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "entries": [entry.to_mapping() for entry in self.entries],
            "rolloutIds": list(self.rollout_ids),
        }
