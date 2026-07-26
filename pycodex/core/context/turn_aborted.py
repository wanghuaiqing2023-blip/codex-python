from __future__ import annotations

from dataclasses import dataclass

from .fragment import ContextualUserFragmentBase


@dataclass(frozen=True)
class TurnAborted(ContextualUserFragmentBase):
    guidance: str

    INTERRUPTED_GUIDANCE = (
        "The user interrupted the previous turn on purpose. Any running unified exec processes may still be "
        "running in the background. If any tools/commands were aborted, they may have partially executed."
    )
    INTERRUPTED_DEVELOPER_GUIDANCE = (
        "The previous turn was interrupted on purpose. Any running unified exec processes may still be "
        "running in the background. If any tools/commands were aborted, they may have partially executed."
    )

    @classmethod
    def new(cls, guidance: str) -> "TurnAborted":
        return cls(guidance)

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return "<turn_aborted>", "</turn_aborted>"

    def body(self) -> str:
        return f"\n{self.guidance}\n"


__all__ = ["TurnAborted"]
