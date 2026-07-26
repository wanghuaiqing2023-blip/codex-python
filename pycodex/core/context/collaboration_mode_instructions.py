from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from pycodex.protocol import (
    COLLABORATION_MODE_CLOSE_TAG,
    COLLABORATION_MODE_OPEN_TAG,
    CollaborationMode,
)

from .fragment import ContextualUserFragmentBase


def _field_value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


@dataclass(frozen=True)
class CollaborationModeInstructions(ContextualUserFragmentBase):
    instructions: str

    @classmethod
    def from_collaboration_mode(
        cls,
        collaboration_mode: CollaborationMode | Any,
    ) -> "CollaborationModeInstructions | None":
        settings = _field_value(collaboration_mode, "settings", None)
        instructions = _field_value(settings, "developer_instructions", None)
        return cls(str(instructions)) if instructions else None

    @classmethod
    def role(cls) -> str:
        return "developer"

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return COLLABORATION_MODE_OPEN_TAG, COLLABORATION_MODE_CLOSE_TAG

    def body(self) -> str:
        return self.instructions


__all__ = ["CollaborationModeInstructions"]
