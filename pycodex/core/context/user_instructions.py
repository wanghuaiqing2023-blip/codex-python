from __future__ import annotations

from dataclasses import dataclass

from .fragment import ContextualUserFragmentBase


@dataclass(frozen=True)
class UserInstructions(ContextualUserFragmentBase):
    directory: str
    text: str

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return "# AGENTS.md instructions for ", "</INSTRUCTIONS>"

    def body(self) -> str:
        return f"{self.directory}\n\n<INSTRUCTIONS>\n{self.text}\n"


__all__ = ["UserInstructions"]
