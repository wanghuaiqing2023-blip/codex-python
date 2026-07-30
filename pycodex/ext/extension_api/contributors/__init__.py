"""Contributor contracts owned by ``codex-extension-api::contributors``."""

from __future__ import annotations

from typing import Any, Protocol

from ..state import ExtensionData
from .prompt import PromptFragment, PromptSlot
from .thread_lifecycle import ThreadIdleInput, ThreadResumeInput, ThreadStartInput, ThreadStopInput
from .tool_lifecycle import (
    ToolCallOutcome,
    ToolCallSource,
    ToolFinishInput,
    ToolLifecycleFuture,
    ToolStartInput,
)
from .turn_lifecycle import TurnAbortInput, TurnErrorInput, TurnStartInput, TurnStopInput


class ContextContributor(Protocol):
    async def contribute(
        self,
        session_store: ExtensionData,
        thread_store: ExtensionData,
    ) -> list[PromptFragment]: ...


class ThreadLifecycleContributor(Protocol):
    async def on_thread_start(self, input: ThreadStartInput) -> None: ...


class TurnLifecycleContributor(Protocol):
    async def on_turn_start(self, input: TurnStartInput) -> None: ...


class ConfigContributor(Protocol):
    def on_config_changed(
        self,
        session_store: ExtensionData,
        thread_store: ExtensionData,
        previous_config: Any,
        new_config: Any,
    ) -> None: ...


class TokenUsageContributor(Protocol):
    async def on_token_usage(
        self,
        session_store: ExtensionData,
        thread_store: ExtensionData,
        turn_store: ExtensionData,
        token_usage: Any,
    ) -> None: ...


class ToolContributor(Protocol):
    def tools(self, session_store: ExtensionData, thread_store: ExtensionData) -> list[Any]: ...


class ToolLifecycleContributor(Protocol):
    async def on_tool_start(self, input: ToolStartInput) -> None: ...


class ApprovalReviewContributor(Protocol):
    async def contribute(
        self,
        session_store: ExtensionData,
        thread_store: ExtensionData,
        prompt: str,
    ) -> Any | None: ...


class TurnItemContributor(Protocol):
    async def contribute(
        self,
        thread_store: ExtensionData,
        turn_store: ExtensionData,
        item: Any,
    ) -> Any: ...


__all__ = [name for name in globals() if not name.startswith("_")]
