"""Tool lifecycle contributor payloads ported from Codex core.

The Rust implementation forwards tool start/finish notifications to extension
contributors.  This module mirrors the pure data boundary and a small
stdlib-only notification facade so registry code can construct the same inputs
without depending on the Rust extension runtime.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

from pycodex.core.tool_registry import ToolCallSource, ToolInvocation
from pycodex.protocol import ToolName


def _ensure_str(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    return value


def _ensure_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field} must be a bool")
    return value


@dataclass(frozen=True)
class ExtensionToolCallSource:
    type: str
    cell_id: str | None = None
    runtime_tool_call_id: str | None = None

    def __post_init__(self) -> None:
        source_type = _ensure_str(self.type, "type")
        if source_type == "direct":
            object.__setattr__(self, "cell_id", None)
            object.__setattr__(self, "runtime_tool_call_id", None)
            return
        if source_type == "code_mode":
            object.__setattr__(self, "cell_id", _ensure_str(self.cell_id, "cell_id"))
            object.__setattr__(
                self,
                "runtime_tool_call_id",
                _ensure_str(self.runtime_tool_call_id, "runtime_tool_call_id"),
            )
            return
        raise ValueError(f"unsupported extension tool call source type: {source_type}")

    @classmethod
    def direct(cls) -> "ExtensionToolCallSource":
        return cls("direct")

    @classmethod
    def code_mode(cls, cell_id: str, runtime_tool_call_id: str) -> "ExtensionToolCallSource":
        return cls("code_mode", cell_id=cell_id, runtime_tool_call_id=runtime_tool_call_id)


@dataclass(frozen=True)
class ToolCallOutcome:
    type: str
    success: bool | None = None
    handler_executed: bool | None = None

    def __post_init__(self) -> None:
        outcome_type = _ensure_str(self.type, "type")
        if outcome_type == "completed":
            object.__setattr__(self, "success", _ensure_bool(self.success, "success"))
            object.__setattr__(self, "handler_executed", None)
            return
        if outcome_type == "failed":
            object.__setattr__(
                self,
                "handler_executed",
                _ensure_bool(self.handler_executed, "handler_executed"),
            )
            object.__setattr__(self, "success", None)
            return
        if outcome_type in {"blocked", "aborted"}:
            object.__setattr__(self, "success", None)
            object.__setattr__(self, "handler_executed", None)
            return
        raise ValueError(f"unsupported tool call outcome type: {outcome_type}")

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
    session_store: Any
    thread_store: Any
    turn_store: Any
    turn_id: str
    call_id: str
    tool_name: ToolName
    source: ExtensionToolCallSource

    def __post_init__(self) -> None:
        object.__setattr__(self, "turn_id", _ensure_str(self.turn_id, "turn_id"))
        object.__setattr__(self, "call_id", _ensure_str(self.call_id, "call_id"))
        if not isinstance(self.tool_name, ToolName):
            raise TypeError("tool_name must be a ToolName")
        if not isinstance(self.source, ExtensionToolCallSource):
            raise TypeError("source must be an ExtensionToolCallSource")


@dataclass(frozen=True)
class ToolFinishInput:
    session_store: Any
    thread_store: Any
    turn_store: Any
    turn_id: str
    call_id: str
    tool_name: ToolName
    source: ExtensionToolCallSource
    outcome: ToolCallOutcome

    def __post_init__(self) -> None:
        object.__setattr__(self, "turn_id", _ensure_str(self.turn_id, "turn_id"))
        object.__setattr__(self, "call_id", _ensure_str(self.call_id, "call_id"))
        if not isinstance(self.tool_name, ToolName):
            raise TypeError("tool_name must be a ToolName")
        if not isinstance(self.source, ExtensionToolCallSource):
            raise TypeError("source must be an ExtensionToolCallSource")
        if not isinstance(self.outcome, ToolCallOutcome):
            raise TypeError("outcome must be a ToolCallOutcome")


def extension_tool_call_source(source: ToolCallSource) -> ExtensionToolCallSource:
    if not isinstance(source, ToolCallSource):
        raise TypeError("source must be a ToolCallSource")
    if source.type == "code_mode":
        return ExtensionToolCallSource.code_mode(
            cell_id=source.cell_id or "",
            runtime_tool_call_id=source.runtime_tool_call_id or "",
        )
    return ExtensionToolCallSource.direct()


def tool_start_input(
    invocation: ToolInvocation,
    *,
    session_store: Any = None,
    thread_store: Any = None,
    turn_store: Any = None,
    turn_id: str = "",
) -> ToolStartInput:
    if not isinstance(invocation, ToolInvocation):
        raise TypeError("invocation must be ToolInvocation")
    return ToolStartInput(
        session_store=session_store,
        thread_store=thread_store,
        turn_store=turn_store,
        turn_id=turn_id,
        call_id=invocation.call_id,
        tool_name=invocation.tool_name,
        source=extension_tool_call_source(invocation.source),
    )


def tool_finish_input(
    invocation: ToolInvocation,
    outcome: ToolCallOutcome,
    *,
    session_store: Any = None,
    thread_store: Any = None,
    turn_store: Any = None,
    turn_id: str = "",
) -> ToolFinishInput:
    if not isinstance(invocation, ToolInvocation):
        raise TypeError("invocation must be ToolInvocation")
    return ToolFinishInput(
        session_store=session_store,
        thread_store=thread_store,
        turn_store=turn_store,
        turn_id=turn_id,
        call_id=invocation.call_id,
        tool_name=invocation.tool_name,
        source=extension_tool_call_source(invocation.source),
        outcome=outcome,
    )


def tool_finish_input_parts(
    *,
    call_id: str,
    tool_name: ToolName,
    source: ToolCallSource,
    outcome: ToolCallOutcome,
    session_store: Any = None,
    thread_store: Any = None,
    turn_store: Any = None,
    turn_id: str = "",
) -> ToolFinishInput:
    if not isinstance(tool_name, ToolName):
        raise TypeError("tool_name must be a ToolName")
    if not isinstance(source, ToolCallSource):
        raise TypeError("source must be ToolCallSource")
    if not isinstance(outcome, ToolCallOutcome):
        raise TypeError("outcome must be ToolCallOutcome")
    return ToolFinishInput(
        session_store=session_store,
        thread_store=thread_store,
        turn_store=turn_store,
        turn_id=turn_id,
        call_id=call_id,
        tool_name=tool_name,
        source=extension_tool_call_source(source),
        outcome=outcome,
    )


async def notify_tool_start(contributors: Any, invocation: ToolInvocation, **stores: Any) -> None:
    start_input = tool_start_input(invocation, **stores)
    for contributor in tuple(contributors or ()):
        callback = getattr(contributor, "on_tool_start", None)
        if callback is None:
            continue
        result = callback(start_input)
        if inspect.isawaitable(result):
            await result


async def notify_tool_finish_parts(
    contributors: Any,
    *,
    call_id: str,
    tool_name: ToolName,
    source: ToolCallSource,
    outcome: ToolCallOutcome,
    **stores: Any,
) -> None:
    finish_input = tool_finish_input_parts(
        call_id=call_id,
        tool_name=tool_name,
        source=source,
        outcome=outcome,
        **stores,
    )
    for contributor in tuple(contributors or ()):
        callback = getattr(contributor, "on_tool_finish", None)
        if callback is None:
            continue
        result = callback(finish_input)
        if inspect.isawaitable(result):
            await result


async def notify_tool_finish(
    contributors: Any,
    invocation: ToolInvocation,
    outcome: ToolCallOutcome,
    **stores: Any,
) -> None:
    finish_input = tool_finish_input(invocation, outcome, **stores)
    for contributor in tuple(contributors or ()):
        callback = getattr(contributor, "on_tool_finish", None)
        if callback is None:
            continue
        result = callback(finish_input)
        if inspect.isawaitable(result):
            await result


async def notify_tool_aborted(contributors: Any, invocation: ToolInvocation, **stores: Any) -> None:
    await notify_tool_finish(contributors, invocation, ToolCallOutcome.aborted(), **stores)


async def notify_tool_aborted_parts(
    contributors: Any,
    *,
    call_id: str,
    tool_name: ToolName,
    source: ToolCallSource,
    **stores: Any,
) -> None:
    await notify_tool_finish_parts(
        contributors,
        call_id=call_id,
        tool_name=tool_name,
        source=source,
        outcome=ToolCallOutcome.aborted(),
        **stores,
    )


__all__ = [
    "ExtensionToolCallSource",
    "ToolCallOutcome",
    "ToolFinishInput",
    "ToolStartInput",
    "extension_tool_call_source",
    "notify_tool_aborted",
    "notify_tool_aborted_parts",
    "notify_tool_finish",
    "notify_tool_finish_parts",
    "notify_tool_start",
    "tool_finish_input",
    "tool_finish_input_parts",
    "tool_start_input",
]
