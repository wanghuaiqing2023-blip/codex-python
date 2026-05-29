"""Memory citation protocol models.

Ported from ``codex/codex-rs/protocol/src/memory_citation.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


JsonValue = Any
U32_MAX = 2**32 - 1


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
    if raw < 0 or raw > U32_MAX:
        raise ValueError(f"{key} must fit in u32")
    return raw


@dataclass(frozen=True)
class MemoryCitationEntry:
    path: str
    line_start: int
    line_end: int
    note: str

    def __post_init__(self) -> None:
        if not isinstance(self.path, str):
            raise TypeError("path must be a string")
        if isinstance(self.line_start, bool) or not isinstance(self.line_start, int):
            raise TypeError("line_start must be an integer")
        if isinstance(self.line_end, bool) or not isinstance(self.line_end, int):
            raise TypeError("line_end must be an integer")
        if self.line_start < 0 or self.line_start > U32_MAX:
            raise ValueError("line_start must fit in u32")
        if self.line_end < 0 or self.line_end > U32_MAX:
            raise ValueError("line_end must fit in u32")
        if not isinstance(self.note, str):
            raise TypeError("note must be a string")

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
        if isinstance(self.entries, MemoryCitationEntry) or not isinstance(self.entries, (list, tuple)):
            raise TypeError("entries must be a list or tuple")
        if isinstance(self.rollout_ids, str) or not isinstance(self.rollout_ids, (list, tuple)):
            raise TypeError("rollout_ids must be a list or tuple")
        if not isinstance(self.entries, tuple):
            object.__setattr__(self, "entries", tuple(self.entries))
        if not isinstance(self.rollout_ids, tuple):
            object.__setattr__(self, "rollout_ids", tuple(self.rollout_ids))
        if not all(isinstance(entry, MemoryCitationEntry) for entry in self.entries):
            raise TypeError("entries must contain MemoryCitationEntry")
        if not all(isinstance(rollout_id, str) for rollout_id in self.rollout_ids):
            raise TypeError("rollout_ids must contain strings")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "MemoryCitation":
        data = _mapping(value, "memory citation")
        entries = data.get("entries", [])
        rollout_ids = data.get("rolloutIds", [])
        if not isinstance(entries, list):
            raise TypeError("entries must be a list")
        if not isinstance(rollout_ids, list):
            raise TypeError("rolloutIds must be a list")
        if not all(isinstance(item, str) for item in rollout_ids):
            raise TypeError("rolloutIds must contain strings")
        return cls(
            entries=tuple(MemoryCitationEntry.from_mapping(item) for item in entries),
            rollout_ids=tuple(rollout_ids),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "entries": [entry.to_mapping() for entry in self.entries],
            "rolloutIds": list(self.rollout_ids),
        }
