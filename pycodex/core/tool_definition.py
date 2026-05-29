"""Tool definition metadata helpers ported from Codex tools."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

JsonValue = Any


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: JsonValue
    output_schema: JsonValue | None = None
    defer_loading: bool = False

    def __post_init__(self) -> None:
        _ensure_str(self.name, "name")
        _ensure_str(self.description, "description")
        _ensure_bool(self.defer_loading, "defer_loading")
        object.__setattr__(self, "input_schema", copy.deepcopy(self.input_schema))
        object.__setattr__(self, "output_schema", copy.deepcopy(self.output_schema))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ToolDefinition":
        if not isinstance(value, Mapping):
            raise TypeError("value must be a mapping")
        return cls(
            name=_required_str(value, "name"),
            description=_required_str(value, "description"),
            input_schema=copy.deepcopy(value["input_schema"]),
            output_schema=copy.deepcopy(value.get("output_schema")),
            defer_loading=_optional_bool(value, "defer_loading", False),
        )

    def renamed(self, name: str) -> "ToolDefinition":
        _ensure_str(name, "name")
        return ToolDefinition(
            name=name,
            description=self.description,
            input_schema=self.input_schema,
            output_schema=self.output_schema,
            defer_loading=self.defer_loading,
        )

    def into_deferred(self) -> "ToolDefinition":
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
            output_schema=None,
            defer_loading=True,
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "name": self.name,
            "description": self.description,
            "input_schema": copy.deepcopy(self.input_schema),
            "defer_loading": self.defer_loading,
        }
        if self.output_schema is not None:
            data["output_schema"] = copy.deepcopy(self.output_schema)
        return data


def _ensure_str(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")


def _ensure_bool(value: object, name: str) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a bool")


def _required_str(value: Mapping[str, JsonValue], key: str) -> str:
    raw = value[key]
    _ensure_str(raw, key)
    return raw


def _optional_bool(value: Mapping[str, JsonValue], key: str, default: bool) -> bool:
    raw = value.get(key, default)
    _ensure_bool(raw, key)
    return raw


__all__ = ["ToolDefinition"]
