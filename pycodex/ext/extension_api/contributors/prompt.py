"""Prompt fragments owned by ``codex-extension-api::contributors::prompt``."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PromptSlot(str, Enum):
    DEVELOPER_POLICY = "developer_policy"
    DEVELOPER_CAPABILITIES = "developer_capabilities"
    CONTEXTUAL_USER = "contextual_user"
    SEPARATE_DEVELOPER = "separate_developer"


@dataclass(frozen=True)
class PromptFragment:
    slot: PromptSlot
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.slot, PromptSlot):
            raise TypeError("slot must be a PromptSlot")
        if not isinstance(self.text, str):
            raise TypeError("text must be a string")

    @classmethod
    def developer_policy(cls, text: str) -> "PromptFragment":
        return cls(PromptSlot.DEVELOPER_POLICY, text)

    @classmethod
    def developer_capability(cls, text: str) -> "PromptFragment":
        return cls(PromptSlot.DEVELOPER_CAPABILITIES, text)

    @classmethod
    def separate_developer(cls, text: str) -> "PromptFragment":
        return cls(PromptSlot.SEPARATE_DEVELOPER, text)


__all__ = ["PromptFragment", "PromptSlot"]
