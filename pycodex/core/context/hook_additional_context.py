from __future__ import annotations

from dataclasses import dataclass

from .fragment import ContextualUserFragmentBase


@dataclass(frozen=True)
class HookAdditionalContext(ContextualUserFragmentBase):
    text: str

    @classmethod
    def new(cls, text: str) -> "HookAdditionalContext":
        return cls(text)

    @classmethod
    def role(cls) -> str:
        return "developer"

    def body(self) -> str:
        return self.text


__all__ = ["HookAdditionalContext"]
