"""Contributor contracts aligned with ``codex-extension-api::contributors``."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from .state import ExtensionData


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
    def contextual_user(cls, text: str) -> "PromptFragment":
        return cls(PromptSlot.CONTEXTUAL_USER, text)

    @classmethod
    def separate_developer(cls, text: str) -> "PromptFragment":
        return cls(PromptSlot.SEPARATE_DEVELOPER, text)


@dataclass(frozen=True)
class ThreadStartInput:
    config: Any
    session_source: Any
    persistent_thread_state_available: bool
    session_store: ExtensionData
    thread_store: ExtensionData


@dataclass(frozen=True)
class ThreadResumeInput:
    session_store: ExtensionData
    thread_store: ExtensionData


@dataclass(frozen=True)
class ThreadStopInput:
    session_store: ExtensionData
    thread_store: ExtensionData


@dataclass(frozen=True)
class ThreadIdleInput:
    session_store: ExtensionData
    thread_store: ExtensionData


@dataclass(frozen=True)
class TurnStartInput:
    turn_id: str
    collaboration_mode: Any
    token_usage_at_turn_start: Any
    session_store: ExtensionData
    thread_store: ExtensionData
    turn_store: ExtensionData


@dataclass(frozen=True)
class TurnStopInput:
    session_store: ExtensionData
    thread_store: ExtensionData
    turn_store: ExtensionData


@dataclass(frozen=True)
class TurnAbortInput:
    reason: Any
    session_store: ExtensionData
    thread_store: ExtensionData
    turn_store: ExtensionData


@dataclass(frozen=True)
class TurnErrorInput:
    turn_id: str
    error: Any
    session_store: ExtensionData
    thread_store: ExtensionData
    turn_store: ExtensionData


class ToolCallSource(str, Enum):
    DIRECT = "direct"
    CODE_MODE = "code_mode"


@dataclass(frozen=True)
class ToolCallOutcome:
    type: str
    success: bool | None = None
    handler_executed: bool | None = None


@dataclass(frozen=True)
class ToolStartInput:
    session_store: ExtensionData
    thread_store: ExtensionData
    turn_store: ExtensionData
    turn_id: str
    call_id: str
    tool_name: Any
    source: Any


@dataclass(frozen=True)
class ToolFinishInput:
    session_store: ExtensionData
    thread_store: ExtensionData
    turn_store: ExtensionData
    turn_id: str
    call_id: str
    tool_name: Any
    source: Any
    outcome: Any


class ConfigContributor(Protocol):
    def on_config_changed(
        self,
        session_store: ExtensionData,
        thread_store: ExtensionData,
        previous_config: Any,
        new_config: Any,
    ) -> None: ...


class ContextContributor(Protocol):
    async def contribute(
        self,
        session_store: ExtensionData,
        thread_store: ExtensionData,
    ) -> list[PromptFragment]: ...


class TurnItemContributor(Protocol):
    async def contribute(self, thread_store: ExtensionData, turn_store: ExtensionData, item: Any) -> Any: ...


class TurnLifecycleContributor(Protocol):
    async def on_turn_start(self, input: TurnStartInput) -> None: ...


class ThreadLifecycleContributor(Protocol):
    async def on_thread_start(self, input: ThreadStartInput) -> None: ...


class ToolLifecycleContributor(Protocol):
    async def on_tool_start(self, input: ToolStartInput) -> None: ...


class ToolContributor(Protocol):
    def tools(self, session_store: ExtensionData, thread_store: ExtensionData) -> list[Any]: ...


class TokenUsageContributor(Protocol):
    async def on_token_usage(
        self,
        session_store: ExtensionData,
        thread_store: ExtensionData,
        turn_store: ExtensionData,
        token_usage: Any,
    ) -> None: ...


class ApprovalReviewContributor(Protocol):
    async def contribute(
        self,
        session_store: ExtensionData,
        thread_store: ExtensionData,
        prompt: str,
    ) -> Any | None: ...


ToolLifecycleFuture = Any


__all__ = [name for name in globals() if not name.startswith("_")]
