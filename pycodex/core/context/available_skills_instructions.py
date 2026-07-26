from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from pycodex.protocol import SKILLS_INSTRUCTIONS_CLOSE_TAG, SKILLS_INSTRUCTIONS_OPEN_TAG

from .fragment import ContextualUserFragmentBase


def _field_value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


@dataclass(frozen=True)
class AvailableSkillsInstructions(ContextualUserFragmentBase):
    skill_root_lines: tuple[str, ...] = ()
    skill_lines: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "skill_root_lines", tuple(str(line) for line in self.skill_root_lines))
        object.__setattr__(self, "skill_lines", tuple(str(line) for line in self.skill_lines))

    @classmethod
    def from_available_skills(cls, available_skills: Any) -> "AvailableSkillsInstructions":
        return cls(
            tuple(str(line) for line in _field_value(available_skills, "skill_root_lines", ())),
            tuple(str(line) for line in _field_value(available_skills, "skill_lines", ())),
        )

    @classmethod
    def role(cls) -> str:
        return "developer"

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return SKILLS_INSTRUCTIONS_OPEN_TAG, SKILLS_INSTRUCTIONS_CLOSE_TAG

    def body(self) -> str:
        from pycodex.core_skills.rendering import render_available_skills_body

        return render_available_skills_body(self.skill_root_lines, self.skill_lines)


__all__ = ["AvailableSkillsInstructions"]
