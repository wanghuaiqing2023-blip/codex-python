"""Tool lifecycle contributor payloads ported from Codex core.

The Rust implementation forwards tool start/finish notifications to extension
contributors.  This module mirrors the pure data boundary and a small
stdlib-only notification facade so registry code can construct the same inputs
without depending on the Rust extension runtime.
"""

from __future__ import annotations

import contextlib
import contextvars
import inspect
from collections.abc import Mapping
from typing import Any

from pycodex.core.tools.registry import ToolCallSource, ToolInvocation
from pycodex.ext.extension_api import (
    ToolCallOutcome,
    ToolCallSource as ExtensionToolCallSource,
    ToolFinishInput,
    ToolStartInput,
)
from pycodex.protocol import ToolName

_LIFECYCLE_STORE_KEYS = ("session_store", "thread_store", "turn_store", "turn_id")
_current_lifecycle_stores: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "pycodex_current_lifecycle_stores",
    default={},
)


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
    start_input = tool_start_input(invocation, **_lifecycle_store_kwargs(stores))
    for contributor in tuple(contributors or ()):
        callback = _field_or_attr(contributor, "on_tool_start", None)
        if callback is None:
            continue
        result = await _call_lifecycle_callback(callback, start_input, first_name="input")
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
        **_lifecycle_store_kwargs(stores),
    )
    for contributor in tuple(contributors or ()):
        callback = _field_or_attr(contributor, "on_tool_finish", None)
        if callback is None:
            continue
        result = await _call_lifecycle_callback(callback, finish_input, first_name="input")
        if inspect.isawaitable(result):
            await result


async def notify_tool_finish(
    contributors: Any,
    invocation: ToolInvocation,
    outcome: ToolCallOutcome,
    **stores: Any,
) -> None:
    finish_input = tool_finish_input(invocation, outcome, **_lifecycle_store_kwargs(stores))
    for contributor in tuple(contributors or ()):
        callback = _field_or_attr(contributor, "on_tool_finish", None)
        if callback is None:
            continue
        result = await _call_lifecycle_callback(callback, finish_input, first_name="input")
        if inspect.isawaitable(result):
            await result


async def _call_lifecycle_callback(callback: Any, value: Any, *, first_name: str) -> Any:
    if not callable(callback):
        raise TypeError(f"{callback!r} is not callable")
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        signature = None

    if signature is not None:
        candidates: tuple[tuple[tuple[Any, ...], dict[str, Any]], ...] = (
            ((value,), {}),
            ((), {first_name: value}),
            ((), {}),
        )
        for args, kwargs in candidates:
            try:
                signature.bind_partial(*args, **kwargs)
            except TypeError:
                continue
            result = callback(*args, **kwargs)
            return await result if inspect.isawaitable(result) else result
        raise TypeError("callback signature does not accept supported arguments")

    result = callback(value)
    return await result if inspect.isawaitable(result) else result


@contextlib.contextmanager
def lifecycle_store_context(stores: Mapping[str, Any]):
    lifecycle_stores = _explicit_lifecycle_store_kwargs(stores)
    if not lifecycle_stores:
        yield
        return
    merged = dict(_current_lifecycle_stores.get())
    merged.update(lifecycle_stores)
    token = _current_lifecycle_stores.set(merged)
    try:
        yield
    finally:
        _current_lifecycle_stores.reset(token)


def _lifecycle_store_kwargs(stores: Mapping[str, Any]) -> dict[str, Any]:
    lifecycle_stores = dict(_current_lifecycle_stores.get())
    lifecycle_stores.update(_explicit_lifecycle_store_kwargs(stores))
    return lifecycle_stores


def _explicit_lifecycle_store_kwargs(stores: Mapping[str, Any]) -> dict[str, Any]:
    return {key: stores[key] for key in _LIFECYCLE_STORE_KEYS if key in stores}


def _field_or_attr(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping) and name in value:
        return value[name]
    return getattr(value, name, default)


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
    "extension_tool_call_source",
    "lifecycle_store_context",
    "notify_tool_aborted",
    "notify_tool_aborted_parts",
    "notify_tool_finish",
    "notify_tool_finish_parts",
    "notify_tool_start",
    "tool_finish_input",
    "tool_finish_input_parts",
    "tool_start_input",
]
