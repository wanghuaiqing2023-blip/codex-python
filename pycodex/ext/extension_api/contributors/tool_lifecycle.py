"""Tool lifecycle inputs owned by the Rust extension API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable

from pycodex.protocol import ToolName

from ..state import ExtensionData


def _string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


@dataclass(frozen=True)
class ToolCallSource:
    type: str
    cell_id: str | None = None
    runtime_tool_call_id: str | None = None

    def __post_init__(self) -> None:
        source_type = _string(self.type, "type")
        if source_type == "direct":
            object.__setattr__(self, "cell_id", None)
            object.__setattr__(self, "runtime_tool_call_id", None)
        elif source_type == "code_mode":
            object.__setattr__(self, "cell_id", _string(self.cell_id, "cell_id"))
            object.__setattr__(
                self,
                "runtime_tool_call_id",
                _string(self.runtime_tool_call_id, "runtime_tool_call_id"),
            )
        else:
            raise ValueError(f"unsupported tool call source type: {source_type}")

    @classmethod
    def direct(cls) -> "ToolCallSource":
        return cls("direct")

    @classmethod
    def code_mode(cls, cell_id: str, runtime_tool_call_id: str) -> "ToolCallSource":
        return cls("code_mode", cell_id, runtime_tool_call_id)


@dataclass(frozen=True)
class ToolCallOutcome:
    type: str
    success: bool | None = None
    handler_executed: bool | None = None

    def __post_init__(self) -> None:
        if self.type == "completed":
            if not isinstance(self.success, bool):
                raise TypeError("success must be a bool")
            object.__setattr__(self, "handler_executed", None)
        elif self.type == "failed":
            if not isinstance(self.handler_executed, bool):
                raise TypeError("handler_executed must be a bool")
            object.__setattr__(self, "success", None)
        elif self.type in {"blocked", "aborted"}:
            object.__setattr__(self, "success", None)
            object.__setattr__(self, "handler_executed", None)
        else:
            raise ValueError(f"unsupported tool call outcome type: {self.type}")

    @classmethod
    def completed(cls, success: bool) -> "ToolCallOutcome":
        return cls("completed", success=success)

    @classmethod
    def blocked(cls) -> "ToolCallOutcome":
        return cls("blocked")

    @classmethod
    def failed(cls, handler_executed: bool) -> "ToolCallOutcome":
        return cls("failed", handler_executed=handler_executed)

    @classmethod
    def aborted(cls) -> "ToolCallOutcome":
        return cls("aborted")


@dataclass(frozen=True)
class ToolStartInput:
    session_store: ExtensionData
    thread_store: ExtensionData
    turn_store: ExtensionData
    turn_id: str
    call_id: str
    tool_name: ToolName
    source: ToolCallSource

    def __post_init__(self) -> None:
        _string(self.turn_id, "turn_id")
        _string(self.call_id, "call_id")
        if not isinstance(self.tool_name, ToolName):
            raise TypeError("tool_name must be a ToolName")
        if not isinstance(self.source, ToolCallSource):
            raise TypeError("source must be a ToolCallSource")


@dataclass(frozen=True)
class ToolFinishInput:
    session_store: ExtensionData
    thread_store: ExtensionData
    turn_store: ExtensionData
    turn_id: str
    call_id: str
    tool_name: ToolName
    source: ToolCallSource
    outcome: ToolCallOutcome

    def __post_init__(self) -> None:
        _string(self.turn_id, "turn_id")
        _string(self.call_id, "call_id")
        if not isinstance(self.tool_name, ToolName):
            raise TypeError("tool_name must be a ToolName")
        if not isinstance(self.source, ToolCallSource):
            raise TypeError("source must be a ToolCallSource")
        if not isinstance(self.outcome, ToolCallOutcome):
            raise TypeError("outcome must be a ToolCallOutcome")


ToolLifecycleFuture = Awaitable[None]

__all__ = [
    "ToolCallOutcome",
    "ToolCallSource",
    "ToolFinishInput",
    "ToolLifecycleFuture",
    "ToolStartInput",
]
