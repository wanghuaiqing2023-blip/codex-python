from __future__ import annotations

from dataclasses import dataclass

from .fragment import ContextualUserFragmentBase


@dataclass(frozen=True)
class ModelSwitchInstructions(ContextualUserFragmentBase):
    model_instructions: str

    @classmethod
    def new(cls, model_instructions: str) -> "ModelSwitchInstructions":
        return cls(model_instructions)

    @classmethod
    def role(cls) -> str:
        return "developer"

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return "<model_switch>", "</model_switch>"

    def body(self) -> str:
        return (
            "\nThe user was previously using a different model. Please continue the conversation "
            "according to the following instructions:\n\n"
            f"{self.model_instructions}\n"
        )


__all__ = ["ModelSwitchInstructions"]
