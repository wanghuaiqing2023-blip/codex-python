from __future__ import annotations

from dataclasses import dataclass

from pycodex.protocol import REALTIME_CONVERSATION_CLOSE_TAG, REALTIME_CONVERSATION_OPEN_TAG

from .fragment import ContextualUserFragmentBase


@dataclass(frozen=True)
class RealtimeStartWithInstructions(ContextualUserFragmentBase):
    instructions: str

    @classmethod
    def new(cls, instructions: str) -> "RealtimeStartWithInstructions":
        return cls(instructions)

    @classmethod
    def role(cls) -> str:
        return "developer"

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return REALTIME_CONVERSATION_OPEN_TAG, REALTIME_CONVERSATION_CLOSE_TAG

    def body(self) -> str:
        return f"\n{self.instructions}\n"


__all__ = ["RealtimeStartWithInstructions"]
