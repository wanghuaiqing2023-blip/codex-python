from __future__ import annotations

from dataclasses import dataclass

from .fragment import ContextualUserFragmentBase


@dataclass(frozen=True)
class PersonalitySpecInstructions(ContextualUserFragmentBase):
    spec: str

    @classmethod
    def new(cls, spec: str) -> "PersonalitySpecInstructions":
        return cls(spec)

    @classmethod
    def role(cls) -> str:
        return "developer"

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return "<personality_spec>", "</personality_spec>"

    def body(self) -> str:
        return (
            " The user has requested a new communication style. Future messages should adhere to the "
            f"following personality: \n{self.spec} "
        )


__all__ = ["PersonalitySpecInstructions"]
