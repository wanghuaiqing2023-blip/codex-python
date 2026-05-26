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
        object.__setattr__(self, "name", str(self.name))
        object.__setattr__(self, "description", str(self.description))
        object.__setattr__(self, "input_schema", copy.deepcopy(self.input_schema))
        object.__setattr__(self, "output_schema", copy.deepcopy(self.output_schema))
        object.__setattr__(self, "defer_loading", bool(self.defer_loading))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ToolDefinition":
        return cls(
            name=str(value["name"]),
            description=str(value["description"]),
            input_schema=copy.deepcopy(value["input_schema"]),
            output_schema=copy.deepcopy(value.get("output_schema")),
            defer_loading=bool(value.get("defer_loading", False)),
        )

    def renamed(self, name: str) -> "ToolDefinition":
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


__all__ = ["ToolDefinition"]
