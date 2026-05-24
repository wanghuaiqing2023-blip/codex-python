"""Tool name protocol helper.

Ported from ``codex/codex-rs/protocol/src/tool_name.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolName:
    name: str
    namespace: str | None = None

    @classmethod
    def new(cls, namespace: str | None, name: str) -> "ToolName":
        return cls(name=name, namespace=namespace)

    @classmethod
    def plain(cls, name: str) -> "ToolName":
        return cls(name=name, namespace=None)

    @classmethod
    def namespaced(cls, namespace: str, name: str) -> "ToolName":
        return cls(name=name, namespace=namespace)

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
