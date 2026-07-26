from __future__ import annotations

from dataclasses import dataclass

from .fragment import ContextualUserFragmentBase


@dataclass(frozen=True)
class SkillInstructions(ContextualUserFragmentBase):
    name: str
    path: str
    contents: str

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return "<skill>", "</skill>"

    def body(self) -> str:
        return f"\n<name>{self.name}</name>\n<path>{self.path}</path>\n{self.contents}\n"


__all__ = ["SkillInstructions"]
