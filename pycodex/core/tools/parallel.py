"""Parallel tool-call orchestration helpers ported from Codex core.

This module mirrors the pure decision and response-shaping pieces from
``core/src/tools/parallel.rs``.  The Rust implementation also owns Tokio task
spawning and cancellation selection; Python keeps that runtime integration
outside this stdlib slice while preserving the observable helper behavior.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import threading
from dataclasses import dataclass
from time import monotonic as _monotonic
from typing import Any

from pycodex.core.tools.network_approval import CancellationToken
from pycodex.core.tools.context import AbortedToolOutput, ToolPayload, response_input_to_code_mode_result
from pycodex.core.tools.lifecycle import lifecycle_store_context, notify_tool_aborted_parts
from pycodex.core.tools.registry import PostToolUsePayload, ToolCallSource
from pycodex.core.tools.router import FunctionCallError, ToolCall, ToolPostHookTypeError, ToolRouter
from pycodex.protocol import FunctionCallOutputPayload, ResponseInputItem

JsonValue = Any


@dataclass(frozen=True)
class ToolCallResult:
    call_id: str
    payload: ToolPayload
    result: Any
    post_tool_use_payload: PostToolUsePayload | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.call_id, str):
            raise TypeError("call_id must be a string")
        if not isinstance(self.payload, ToolPayload):
            raise TypeError("payload must be ToolPayload")
        if self.post_tool_use_payload is not None and not isinstance(
            self.post_tool_use_payload,
            PostToolUsePayload,
        ):
            raise TypeError("post_tool_use_payload must be PostToolUsePayload or None")

    def to_response_item(self) -> ResponseInputItem:
        method = getattr(self.result, "to_response_item", None)
        if method is None:
            raise TypeError("tool result must expose to_response_item(call_id, payload)")
        response = method(self.call_id, self.payload)
        if not isinstance(response, ResponseInputItem):
            raise TypeError("to_response_item must return ResponseInputItem")
        return response

    def code_mode_result(self) -> JsonValue:
        method = getattr(self.result, "code_mode_result", None)
        if method is None:
            return response_input_to_code_mode_result(self.to_response_item())
        return method(self.payload)


@dataclass(frozen=True)
class ToolCallRuntimeDecision:
    supports_parallel: bool
    waits_for_runtime_cancellation: bool

    def __post_init__(self) -> None:
        if not isinstance(self.supports_parallel, bool):
            raise TypeError("supports_parallel must be a bool")
        if not isinstance(self.waits_for_runtime_cancellation, bool):
            raise TypeError("waits_for_runtime_cancellation must be a bool")


class TerminalOutcomeFlag:
    """Small thread-safe equivalent of Rust's ``AtomicBool`` outcome marker."""

    def __init__(self, value: bool = False) -> None:
        if not isinstance(value, bool):
            raise TypeError("value must be a bool")
        self._value = value
        self._lock = threading.Lock()

    def load(self) -> bool:
        with self._lock:
            return self._value

    def store(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise TypeError("value must be a bool")
        with self._lock:
            self._value = value

    def swap(self, value: bool) -> bool:
        if not isinstance(value, bool):
            raise TypeError("value must be a bool")
        with self._lock:
            old = self._value
            self._value = value
            return old


class ToolCallRuntime:
    """Callback-friendly facade for Rust ``ToolCallRuntime`` helper behavior."""

    def __init__(
        self,
        router: ToolRouter,
        *,
        lifecycle_contributors: Any = (),
    ) -> None:
        if not isinstance(router, ToolRouter):
            raise TypeError("router must be ToolRouter")
        self.router = router
        self.lifecycle_contributors = lifecycle_contributors
        self._parallel_execution = _AsyncToolExecutionGate()

    def create_diff_consumer(self, tool_name: Any) -> Any:
        method = getattr(self.router, "create_diff_consumer", None)
        if method is None:
            return None
        return method(tool_name)

    def decision_for_call(self, call: ToolCall) -> ToolCallRuntimeDecision:
        if not isinstance(call, ToolCall):
            raise TypeError("call must be ToolCall")
        return ToolCallRuntimeDecision(
            supports_parallel=self.router.tool_supports_parallel(call),
            waits_for_runtime_cancellation=self.router.tool_waits_for_runtime_cancellation(call),
        )

    async def notify_aborted(
        self,
        call: ToolCall,
        *,
        source: ToolCallSource | None = None,
        **stores: Any,
    ) -> None:
        if not isinstance(call, ToolCall):
            raise TypeError("call must be ToolCall")
        await notify_tool_aborted_parts(
            self.lifecycle_contributors,
            call_id=call.call_id,
            tool_name=call.tool_name,
            source=source or ToolCallSource.direct(),
            **stores,
        )

    async def handle_pre_cancelled_tool_call(
        self,
        call: ToolCall,
        cancellation_token: CancellationToken,
        *,
        elapsed_seconds: float = 0.1,
        source: ToolCallSource | None = None,
        **stores: Any,
    ) -> ToolCallResult | None:
        if not isinstance(cancellation_token, CancellationToken):
            raise TypeError("cancellation_token must be a CancellationToken")
        if not cancellation_token.is_cancelled():
            return None
        result = aborted_tool_result(call, _runtime_abort_elapsed_seconds(elapsed_seconds))
        await self.notify_aborted(call, source=source, **stores)
        return result

    async def handle_tool_call_with_source(
        self,
        call: ToolCall,
        dispatch: Any,
        *,
        source: ToolCallSource | None = None,
        cancellation_token: CancellationToken | None = None,
        elapsed_seconds: float | None = None,
        terminal_outcome_reached: TerminalOutcomeFlag | None = None,
        **stores: Any,
    ) -> ToolCallResult:
        token = cancellation_token or CancellationToken()
        terminal_outcome = terminal_outcome_reached or TerminalOutcomeFlag()
        pre_cancelled = await self.handle_pre_cancelled_tool_call(
            call,
            token,
            elapsed_seconds=elapsed_seconds if elapsed_seconds is not None else 0.1,
            source=source,
            **stores,
        )
        if pre_cancelled is not None:
            return pre_cancelled
        supports_parallel = self.router.tool_supports_parallel(call)
        started = _monotonic()

        async def run_dispatch() -> ToolCallResult:
            async with self._parallel_execution.acquire(supports_parallel):
                result = dispatch(call, source or ToolCallSource.direct(), token)
                if inspect.isawaitable(result):
                    result = await result
                return result

        task = _ensure_task(run_dispatch())
        cancel_task = _ensure_task(token.cancelled())
        done, pending = await asyncio_wait_first(task, cancel_task)
        if task in done:
            cancel_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await cancel_task
            if (
                token.is_cancelled()
                and self.decision_for_call(call).waits_for_runtime_cancellation
                and not terminal_outcome.load()
            ):
                with contextlib.suppress(asyncio.CancelledError, FunctionCallError):
                    await task
                result = aborted_tool_result(
                    call,
                    _runtime_abort_elapsed_seconds(_runtime_elapsed_seconds(started, elapsed_seconds)),
                )
                await self.notify_aborted(call, source=source, **stores)
            else:
                result = await task
        else:
            result = await self._handle_inflight_cancellation(
                call,
                task,
                elapsed_seconds=_runtime_elapsed_seconds(started, elapsed_seconds),
                source=source,
                terminal_outcome_reached=terminal_outcome,
                **stores,
            )
        if not isinstance(result, ToolCallResult):
            raise TypeError("dispatch must return ToolCallResult")
        return result

    async def _handle_inflight_cancellation(
        self,
        call: ToolCall,
        task: Any,
        *,
        elapsed_seconds: float,
        source: ToolCallSource | None,
        terminal_outcome_reached: TerminalOutcomeFlag,
        **stores: Any,
    ) -> ToolCallResult:
        if should_return_completed_after_cancellation(
            terminal_outcome_reached,
            handle_finished=task.done(),
        ):
            return await task
        decision = self.decision_for_call(call)
        if decision.waits_for_runtime_cancellation:
            if terminal_outcome_reached.swap(True):
                return await task
            with contextlib.suppress(asyncio.CancelledError, FunctionCallError):
                await task
        else:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                result = await task
                if isinstance(result, ToolCallResult):
                    return result
        result = aborted_tool_result(call, _runtime_abort_elapsed_seconds(elapsed_seconds))
        await self.notify_aborted(call, source=source, **stores)
        return result

    async def handle_tool_call(
        self,
        call: ToolCall,
        cancellation_token: CancellationToken | None = None,
        *,
        source: ToolCallSource | None = None,
        elapsed_seconds: float | None = None,
        result_observer: Any = None,
        **stores: Any,
    ) -> ResponseInputItem:
        if not isinstance(call, ToolCall):
            raise TypeError("call must be ToolCall")
        terminal_outcome_reached = TerminalOutcomeFlag()

        async def dispatch(received_call: ToolCall, received_source: ToolCallSource, token: CancellationToken) -> ToolCallResult:
            result = await self._dispatch_router_tool_call(
                received_call,
                received_source,
                token,
                terminal_outcome_reached=terminal_outcome_reached,
                **stores,
            )
            return _coerce_tool_call_result(received_call, result)

        try:
            result = await self.handle_tool_call_with_source(
                call,
                dispatch,
                source=source,
                cancellation_token=cancellation_token,
                elapsed_seconds=elapsed_seconds,
                terminal_outcome_reached=terminal_outcome_reached,
                **stores,
            )
        except FunctionCallError as err:
            if getattr(err, "kind", None) == "fatal":
                raise RuntimeError(err.message) from err
            return failure_response(call, err)
        except ToolPostHookTypeError as err:
            raise RuntimeError(str(err)) from err
        if callable(result_observer):
            observed = result_observer(call, result)
            if inspect.isawaitable(observed):
                await observed
        return result.to_response_item()

    async def _dispatch_router_tool_call(
        self,
        call: ToolCall,
        source: ToolCallSource,
        cancellation_token: CancellationToken,
        terminal_outcome_reached: TerminalOutcomeFlag | None = None,
        **stores: Any,
    ) -> Any:
        dispatch = getattr(self.router, "dispatch_tool_call_with_terminal_outcome", None)
        if not callable(dispatch):
            raise FunctionCallError.respond_to_model(f"unsupported tool call: {call.tool_name}")
        dispatch_stores = dict(stores)
        dispatch_stores.pop("lifecycle_contributors", None)
        with lifecycle_store_context(dispatch_stores):
            result = dispatch(
                call,
                source=source,
                cancellation_token=cancellation_token,
                lifecycle_contributors=self.lifecycle_contributors,
                terminal_outcome_reached=terminal_outcome_reached,
                **dispatch_stores,
            )
            if inspect.isawaitable(result):
                result = await result
        return result


def tool_runtime_decision(router: ToolRouter, call: ToolCall) -> ToolCallRuntimeDecision:
    return ToolCallRuntime(router).decision_for_call(call)


def should_return_completed_after_cancellation(
    terminal_outcome_reached: TerminalOutcomeFlag | bool,
    *,
    handle_finished: bool,
) -> bool:
    if not isinstance(handle_finished, bool):
        raise TypeError("handle_finished must be a bool")
    if isinstance(terminal_outcome_reached, TerminalOutcomeFlag):
        terminal = terminal_outcome_reached.load()
    elif isinstance(terminal_outcome_reached, bool):
        terminal = terminal_outcome_reached
    else:
        raise TypeError("terminal_outcome_reached must be TerminalOutcomeFlag or bool")
    return terminal or handle_finished


def aborted_tool_result(call: ToolCall, elapsed_seconds: float) -> ToolCallResult:
    if not isinstance(call, ToolCall):
        raise TypeError("call must be ToolCall")
    return ToolCallResult(
        call_id=call.call_id,
        payload=call.payload,
        result=AbortedToolOutput(abort_message(call, elapsed_seconds)),
        post_tool_use_payload=None,
    )


def abort_message(call: ToolCall, elapsed_seconds: float) -> str:
    if not isinstance(call, ToolCall):
        raise TypeError("call must be ToolCall")
    seconds = float(elapsed_seconds)
    if call.tool_name.namespace is None and call.tool_name.name in {"shell_command", "unified_exec"}:
        return f"Wall time: {seconds:.1f} seconds\naborted by user"
    return f"aborted by user after {seconds:.1f}s"


def _runtime_abort_elapsed_seconds(elapsed_seconds: float) -> float:
    return max(float(elapsed_seconds), 0.1)


def _runtime_elapsed_seconds(started: float, explicit_elapsed_seconds: float | None) -> float:
    if explicit_elapsed_seconds is not None:
        return float(explicit_elapsed_seconds)
    return _monotonic() - started


def failure_response(call: ToolCall, err: FunctionCallError | Exception | str) -> ResponseInputItem:
    if not isinstance(call, ToolCall):
        raise TypeError("call must be ToolCall")
    message = str(err)
    if call.payload.type == "tool_search":
        return ResponseInputItem.tool_search_output(call.call_id, "completed", "client", ())
    output = FunctionCallOutputPayload.from_text(message, success=False)
    if call.payload.type == "custom":
        return ResponseInputItem.custom_tool_call_output(call.call_id, output)
    return ResponseInputItem.function_call_output(call.call_id, output)


def _coerce_tool_call_result(call: ToolCall, result: Any) -> ToolCallResult:
    if isinstance(result, ToolCallResult):
        return result
    if hasattr(result, "to_response_item"):
        return ToolCallResult(call_id=call.call_id, payload=call.payload, result=result)
    into_response = getattr(result, "into_response", None)
    if callable(into_response):
        response = into_response()
        if isinstance(response, ResponseInputItem):
            return ToolCallResult(
                call_id=call.call_id,
                payload=call.payload,
                result=_ResponseInputItemToolOutput(response),
            )
    raise TypeError("router dispatch must return ToolCallResult or tool output")


def _ensure_task(awaitable: Any) -> asyncio.Task[Any]:
    if isinstance(awaitable, asyncio.Task):
        return awaitable
    return asyncio.create_task(awaitable)


async def asyncio_wait_first(*tasks: asyncio.Task[Any]) -> tuple[set[asyncio.Task[Any]], set[asyncio.Task[Any]]]:
    return await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)


@dataclass(frozen=True)
class _ResponseInputItemToolOutput:
    response: ResponseInputItem

    def to_response_item(self, call_id: str, payload: ToolPayload) -> ResponseInputItem:
        return self.response


class _AsyncToolExecutionGate:
    """Small async read/write gate for Rust-style parallel tool scheduling."""

    def __init__(self) -> None:
        self._condition = asyncio.Condition()
        self._readers = 0
        self._writer = False
        self._waiting_writers = 0

    @contextlib.asynccontextmanager
    async def acquire(self, supports_parallel: bool) -> Any:
        if not isinstance(supports_parallel, bool):
            raise TypeError("supports_parallel must be a bool")
        if supports_parallel:
            await self._acquire_parallel()
            try:
                yield
            finally:
                await self._release_parallel()
        else:
            await self._acquire_exclusive()
            try:
                yield
            finally:
                await self._release_exclusive()

    async def _acquire_parallel(self) -> None:
        async with self._condition:
            while self._writer or self._waiting_writers:
                await self._condition.wait()
            self._readers += 1

    async def _release_parallel(self) -> None:
        async with self._condition:
            self._readers -= 1
            if self._readers == 0:
                self._condition.notify_all()

    async def _acquire_exclusive(self) -> None:
        async with self._condition:
            self._waiting_writers += 1
            try:
                while self._writer or self._readers:
                    await self._condition.wait()
                self._writer = True
            finally:
                self._waiting_writers -= 1
                self._condition.notify_all()

    async def _release_exclusive(self) -> None:
        async with self._condition:
            self._writer = False
            self._condition.notify_all()


__all__ = [
    "TerminalOutcomeFlag",
    "ToolCallResult",
    "ToolCallRuntime",
    "ToolCallRuntimeDecision",
    "abort_message",
    "aborted_tool_result",
    "failure_response",
    "should_return_completed_after_cancellation",
    "tool_runtime_decision",
]
