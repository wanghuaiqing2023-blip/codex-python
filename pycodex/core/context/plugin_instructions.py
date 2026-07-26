from __future__ import annotations

from dataclasses import dataclass

from .fragment import ContextualUserFragmentBase


@dataclass(frozen=True)
class PluginInstructions(ContextualUserFragmentBase):
    text: str

    @classmethod
    def new(cls, text: str) -> "PluginInstructions":
        return cls(text)

    @classmethod
    def role(cls) -> str:
        return "developer"

    def body(self) -> str:
        return self.text


__all__ = ["PluginInstructions"]
