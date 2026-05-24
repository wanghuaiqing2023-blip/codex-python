"""Shell command summary protocol types.

Ported from ``codex/codex-rs/protocol/src/parse_command.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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


def _optional_str(value: dict[str, JsonValue], key: str) -> str | None:
    raw = value.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


@dataclass(frozen=True)
class ParsedCommand:
    type: str
    cmd: str
    name: str | None = None
    path: Path | str | None = None
    query: str | None = None

    @classmethod
    def read(cls, cmd: str, name: str, path: Path | str) -> "ParsedCommand":
        return cls("read", cmd=cmd, name=name, path=Path(path))

    @classmethod
    def list_files(cls, cmd: str, path: str | None = None) -> "ParsedCommand":
        return cls("list_files", cmd=cmd, path=path)

    @classmethod
    def search(cls, cmd: str, query: str | None = None, path: str | None = None) -> "ParsedCommand":
        return cls("search", cmd=cmd, query=query, path=path)

    @classmethod
    def unknown(cls, cmd: str) -> "ParsedCommand":
        return cls("unknown", cmd=cmd)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ParsedCommand":
        data = _mapping(value, "parsed command")
        command_type = _required_str(data, "type")
        if command_type == "read":
            return cls.read(
                cmd=_required_str(data, "cmd"),
                name=_required_str(data, "name"),
                path=Path(_required_str(data, "path")),
            )
        if command_type == "list_files":
            return cls.list_files(cmd=_required_str(data, "cmd"), path=_optional_str(data, "path"))
        if command_type == "search":
            return cls.search(
                cmd=_required_str(data, "cmd"),
                query=_optional_str(data, "query"),
                path=_optional_str(data, "path"),
            )
        if command_type == "unknown":
            return cls.unknown(cmd=_required_str(data, "cmd"))
        raise ValueError(f"unknown parsed command type: {command_type}")

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"type": self.type, "cmd": self.cmd}
        if self.type == "read":
            data["name"] = self.name or ""
            data["path"] = str(self.path or "")
        elif self.type == "list_files":
            if self.path is not None:
                data["path"] = str(self.path)
        elif self.type == "search":
            if self.query is not None:
                data["query"] = self.query
            if self.path is not None:
                data["path"] = str(self.path)
        elif self.type != "unknown":
            raise ValueError(f"unknown parsed command type: {self.type}")
        return data
