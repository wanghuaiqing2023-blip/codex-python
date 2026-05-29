"""Lightweight in-memory core session runtime.

This module provides a minimal session object that implements the session-like
methods used by the core user-turn runtime. It is intentionally small and
transport-agnostic: richer persistence, rollout, UI events, and tool execution
can be layered on later without changing the request/sampling path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pycodex.protocol import BaseInstructions, ResponseItem


@dataclass(frozen=True)
class InMemoryTurnContext:
    """Turn context needed by prompt assembly."""

    cwd: Path
    model_info: Any = None
    user_instructions: str | None = None


@dataclass
class InMemoryHistory:
    """Prompt-visible conversation history."""

    items: list[ResponseItem] = field(default_factory=list)

    def for_prompt(self, _modalities: object = None) -> list[ResponseItem]:
        return list(self.items)


@dataclass
class InMemoryCodexSession:
    """Minimal session-like runtime for core user turns."""

    cwd: Path | str
    model_info: Any = None
    user_instructions: str | None = None
    base_instructions: BaseInstructions | str = field(default_factory=BaseInstructions.default)
    history: list[ResponseItem] = field(default_factory=list)
    context_updates_recorded: int = 0
    recorded_batches: list[tuple[ResponseItem, ...]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.cwd = Path(self.cwd)
        if not isinstance(self.base_instructions, BaseInstructions):
            self.base_instructions = BaseInstructions(str(self.base_instructions))
        self.history = list(self.history)

    async def new_default_turn(self) -> InMemoryTurnContext:
        return InMemoryTurnContext(
            cwd=self.cwd,
            model_info=self.model_info,
            user_instructions=self.user_instructions,
        )

    async def record_context_updates_and_set_reference_context_item(self, _turn_context: InMemoryTurnContext) -> None:
        self.context_updates_recorded += 1

    async def record_conversation_items(
        self,
        _turn_context: InMemoryTurnContext,
        items: tuple[ResponseItem, ...],
    ) -> None:
        batch = tuple(items)
        self.recorded_batches.append(batch)
        self.history.extend(batch)

    async def clone_history(self) -> InMemoryHistory:
        return InMemoryHistory(list(self.history))

    async def get_base_instructions(self) -> BaseInstructions:
        return self.base_instructions


__all__ = [
    "InMemoryCodexSession",
    "InMemoryHistory",
    "InMemoryTurnContext",
]
