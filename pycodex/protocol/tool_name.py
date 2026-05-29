"""Tool name protocol helper.

Ported from ``codex/codex-rs/protocol/src/tool_name.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ToolName:
    name: str
    namespace: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError("name must be a string")
        if self.namespace is not None and not isinstance(self.namespace, str):
            raise TypeError("namespace must be a string or None")

    @classmethod
    def new(cls, namespace: str | None, name: str) -> "ToolName":
        return cls(name=name, namespace=namespace)

    @classmethod
    def plain(cls, name: str) -> "ToolName":
        return cls(name=name, namespace=None)

    @classmethod
    def namespaced(cls, namespace: str, name: str) -> "ToolName":
        return cls(name=name, namespace=namespace)

    @classmethod
    def from_value(cls, value: "ToolName | str") -> "ToolName":
        if isinstance(value, ToolName):
            return value
        if isinstance(value, str):
            return cls.plain(value)
        raise TypeError("ToolName value must be ToolName or string")

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ToolName":
        if not isinstance(data, Mapping):
            raise TypeError("ToolName must be decoded from an object")
        name = data.get("name")
        if not isinstance(name, str):
            raise TypeError("name must be a string")
        namespace = data.get("namespace")
        if namespace is not None and not isinstance(namespace, str):
            raise TypeError("namespace must be a string or None")
        return cls(name=name, namespace=namespace)

    def to_mapping(self) -> dict[str, str | None]:
        return {"name": self.name, "namespace": self.namespace}

    def sort_key(self) -> tuple[str, int, str]:
        if self.namespace is None:
            return self.name, 0, ""
        return self.namespace, 1, self.name

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, ToolName):
            return NotImplemented
        return self.sort_key() < other.sort_key()

    def __str__(self) -> str:
        if self.namespace is None:
            return self.name
        return f"{self.namespace}{self.name}"
