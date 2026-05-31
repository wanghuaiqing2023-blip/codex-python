"""Tool-call routing helpers ported from Codex core.

This module starts with the pure ``ToolRouter::build_tool_call`` logic from
``codex/codex-rs/core/src/tools/router.rs``.
"""

from __future__ import annotations

import json
import inspect
import logging
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from pycodex.core.function_tool import FunctionCallError
from pycodex.core.memory_usage import emit_metric_for_tool_read
from pycodex.core.tool_context import FunctionToolOutput, PostToolUseFeedbackOutput, ToolPayload
from pycodex.core.tool_dispatch_trace import ToolDispatchTrace
from pycodex.core.hook_runtime import (
    PostToolUseHookOutcome,
    PreToolUseHookResult,
    additional_context_messages,
    post_tool_use_replacement_text,
)
from pycodex.core.tool_lifecycle import ToolCallOutcome, notify_tool_finish, notify_tool_start
from pycodex.core.tool_registry import (
    PostToolUsePayload,
    PreToolUsePayload,
    ToolCallSource,
    ToolInvocation,
    ToolRegistry,
    flat_tool_name,
    unsupported_tool_call_message,
    with_updated_hook_input,
)
from pycodex.protocol import ResponseItem, SearchToolCallParams, ToolName, TruncationPolicyConfig

JsonValue = Any
LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConversationHistory:
    items: tuple[ResponseItem, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.items, (str, bytes)):
            raise TypeError("items must be an iterable of ResponseItem values")
        object.__setattr__(
            self,
            "items",
            tuple(
                item if isinstance(item, ResponseItem) else ResponseItem.from_mapping(item)
                for item in self.items
            ),
        )


@dataclass(frozen=True)
class ToolCall:
    tool_name: ToolName
    call_id: str
    payload: ToolPayload
    turn_id: str = ""
    truncation_policy: TruncationPolicyConfig | None = None
    conversation_history: ConversationHistory = field(default_factory=ConversationHistory)

    def __post_init__(self) -> None:
        if not isinstance(self.tool_name, ToolName):
            raise TypeError("tool_name must be ToolName")
        if not isinstance(self.call_id, str):
            raise TypeError("call_id must be a string")
        if not isinstance(self.payload, ToolPayload):
            raise TypeError("payload must be ToolPayload")
        if not isinstance(self.turn_id, str):
            raise TypeError("turn_id must be a string")
        if self.truncation_policy is not None and not isinstance(self.truncation_policy, TruncationPolicyConfig):
            raise TypeError("truncation_policy must be TruncationPolicyConfig or None")
        if not isinstance(self.conversation_history, ConversationHistory):
            raise TypeError("conversation_history must be ConversationHistory")

    def function_arguments(self) -> str:
        if self.payload.type == "function":
            if self.payload.arguments is None:
                raise FunctionCallError.fatal(
                    f"tool {self.tool_name} invoked with malformed function payload"
                )
            return self.payload.arguments
        raise FunctionCallError.fatal(
            f"tool {self.tool_name} invoked with incompatible payload"
        )


class ToolRouter:
    def __init__(
        self,
        model_visible_specs: tuple[JsonValue, ...] = (),
        registry: ToolRegistry | None = None,
    ) -> None:
        if not isinstance(model_visible_specs, tuple):
            raise TypeError("model_visible_specs must be a tuple")
        if registry is not None and not isinstance(registry, ToolRegistry):
            raise TypeError("registry must be ToolRegistry or None")
        self._model_visible_specs = tuple(model_visible_specs)
        self._registry = registry or ToolRegistry.empty()

    @classmethod
    def from_parts(
        cls,
        registry_or_specs: ToolRegistry | tuple[JsonValue, ...] | list[JsonValue],
        model_visible_specs: tuple[JsonValue, ...] | list[JsonValue] | None = None,
    ) -> "ToolRouter":
        if model_visible_specs is None:
            if not isinstance(registry_or_specs, (list, tuple)):
                raise TypeError("ToolRouter.from_parts(specs) requires a list or tuple")
            return cls(tuple(registry_or_specs))  # type: ignore[arg-type]
        if not isinstance(registry_or_specs, ToolRegistry):
            raise TypeError("ToolRouter.from_parts(registry, specs) requires a ToolRegistry")
        if not isinstance(model_visible_specs, (list, tuple)):
            raise TypeError("model_visible_specs must be a list or tuple")
        return cls(tuple(model_visible_specs), registry_or_specs)

    def model_visible_specs(self) -> tuple[JsonValue, ...]:
        return self._model_visible_specs

    def registered_tool_names_for_test(self) -> tuple[ToolName, ...]:
        return self._registry.tool_names_for_test()

    def tool_exposure_for_test(self, name: ToolName) -> Any:
        return self._registry.tool_exposure(name)

    def tool_supports_parallel(self, call: ToolCall) -> bool:
        return self._registry.supports_parallel_tool_calls(call.tool_name) or False

    def tool_waits_for_runtime_cancellation(self, call: ToolCall) -> bool:
        return self._registry.waits_for_runtime_cancellation(call.tool_name) or False

    def create_diff_consumer(self, tool_name: ToolName) -> Any:
        return self._registry.create_diff_consumer(tool_name)

    async def dispatch_tool_call_with_code_mode_result(
        self,
        call: ToolCall,
        *,
        source: ToolCallSource | None = None,
        lifecycle_contributors: Any = (),
        pre_tool_use_hook: Any = None,
        post_tool_use_hook: Any = None,
        terminal_outcome_reached: Any = None,
        **stores: Any,
    ) -> Any:
        return await self.dispatch_tool_call_with_terminal_outcome(
            call,
            source=source,
            lifecycle_contributors=lifecycle_contributors,
            pre_tool_use_hook=pre_tool_use_hook,
            post_tool_use_hook=post_tool_use_hook,
            terminal_outcome_reached=terminal_outcome_reached,
            **stores,
        )

    async def dispatch_tool_call_with_terminal_outcome(
        self,
        call: ToolCall,
        *,
        source: ToolCallSource | None = None,
        lifecycle_contributors: Any = (),
        pre_tool_use_hook: Any = None,
        post_tool_use_hook: Any = None,
        terminal_outcome_reached: Any = None,
        **stores: Any,
    ) -> Any:
        if not isinstance(call, ToolCall):
            raise TypeError("call must be ToolCall")
        invocation = ToolInvocation(
            call_id=call.call_id,
            tool_name=call.tool_name,
            source=source or ToolCallSource.direct(),
            payload=call.payload,
            session=stores.get("session"),
            turn=stores.get("turn"),
            cancellation_token=stores.get("cancellation_token"),
            tracker=stores.get("tracker"),
        )
        lifecycle_stores = _lifecycle_stores(stores)
        return await dispatch_tool_call_with_terminal_outcome(
            self._registry,
            invocation,
            lifecycle_contributors=lifecycle_contributors,
            pre_tool_use_hook=pre_tool_use_hook,
            post_tool_use_hook=post_tool_use_hook,
            terminal_outcome_reached=terminal_outcome_reached,
            **lifecycle_stores,
        )

    @staticmethod
    def build_tool_call(item: ResponseItem) -> ToolCall | None:
        return build_tool_call(item)


def build_tool_call(item: ResponseItem) -> ToolCall | None:
    if not isinstance(item, ResponseItem):
        raise TypeError("item must be ResponseItem")
    if item.type == "function_call":
        return ToolCall(
            tool_name=ToolName.new(item.namespace, item.name or ""),
            call_id=item.call_id or "",
            payload=ToolPayload.function(_function_arguments(item.arguments)),
        )

    if item.type == "tool_search_call":
        if item.call_id is None or item.execution != "client":
            return None
        return ToolCall(
            tool_name=ToolName.plain("tool_search"),
            call_id=item.call_id,
            payload=ToolPayload.tool_search(_search_arguments(item.arguments)),
        )

    if item.type == "custom_tool_call":
        return ToolCall(
            tool_name=ToolName.plain(item.name or ""),
            call_id=item.call_id or "",
            payload=ToolPayload.custom(item.input or ""),
        )

    return None


def _function_arguments(arguments: str | JsonValue | None) -> str:
    if isinstance(arguments, str):
        return arguments
    if arguments is None:
        return ""
    return json.dumps(arguments, separators=(",", ":"))


def _search_arguments(arguments: str | JsonValue | None) -> SearchToolCallParams:
    try:
        if isinstance(arguments, SearchToolCallParams):
            return arguments
        if isinstance(arguments, str):
            decoded = json.loads(arguments)
        elif arguments is None:
            decoded = {}
        else:
            decoded = arguments
        return SearchToolCallParams.from_mapping(decoded)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as err:
        raise FunctionCallError.respond_to_model(
            f"failed to parse tool_search arguments: {err}"
        ) from err


def _ensure_str(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _lifecycle_stores(stores: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in stores.items()
        if key not in {"session", "turn", "cancellation_token", "tracker"}
    }


async def dispatch_tool_call(
    registry: ToolRegistry,
    invocation: ToolInvocation,
    *,
    lifecycle_contributors: Any = (),
    pre_tool_use_hook: Any = None,
    post_tool_use_hook: Any = None,
    **stores: Any,
) -> Any:
    return await dispatch_tool_call_with_terminal_outcome(
        registry,
        invocation,
        lifecycle_contributors=lifecycle_contributors,
        pre_tool_use_hook=pre_tool_use_hook,
        post_tool_use_hook=post_tool_use_hook,
        terminal_outcome_reached=None,
        **stores,
    )


async def dispatch_tool_call_with_terminal_outcome(
    registry: ToolRegistry,
    invocation: ToolInvocation,
    *,
    lifecycle_contributors: Any = (),
    pre_tool_use_hook: Any = None,
    post_tool_use_hook: Any = None,
    terminal_outcome_reached: Any = None,
    **stores: Any,
) -> Any:
    if not isinstance(registry, ToolRegistry):
        raise TypeError("registry must be ToolRegistry")
    if not isinstance(invocation, ToolInvocation):
        raise TypeError("invocation must be ToolInvocation")
    _increment_active_turn_tool_calls(invocation, **stores)
    dispatch_trace = _tool_dispatch_trace(invocation, **stores)
    tool = registry.tool(invocation.tool_name)
    if tool is None:
        err = FunctionCallError.respond_to_model(
            unsupported_tool_call_message(invocation.payload, invocation.tool_name)
        )
        await _record_tool_result_telemetry(
            invocation,
            success=False,
            output=None,
            error=err,
            telemetry_tags=(),
            extra_trace_fields=(),
            duration_seconds=0.0,
            **stores,
        )
        dispatch_trace.record_failed(err)
        raise err
    telemetry_tags, extra_trace_fields = await _tool_telemetry_fields(tool, invocation)
    if not (registry.matches_kind(invocation.tool_name, invocation.payload) or False):
        err = FunctionCallError.fatal(
            f"tool {invocation.tool_name} invoked with incompatible payload"
        )
        await _record_tool_result_telemetry(
            invocation,
            success=False,
            output=None,
            error=err,
            telemetry_tags=telemetry_tags,
            extra_trace_fields=extra_trace_fields,
            duration_seconds=0.0,
            **stores,
        )
        dispatch_trace.record_failed(err)
        raise err

    await notify_tool_start(lifecycle_contributors, invocation, **stores)
    try:
        invocation = await _apply_pre_tool_use_hook(
            tool,
            invocation,
            pre_tool_use_hook,
            dispatch_trace=dispatch_trace,
            lifecycle_contributors=lifecycle_contributors,
            terminal_outcome_reached=terminal_outcome_reached,
            **stores,
        )
    except FunctionCallError:
        raise
    handler_executed = False
    try:
        handler_executed = True
        handler_start = time.perf_counter()
        output = await _handle_tool(tool, invocation)
    except FunctionCallError as err:
        handler_duration = time.perf_counter() - handler_start if handler_executed else 0.0
        finished = await notify_tool_finish_if_unclaimed(
            lifecycle_contributors,
            invocation,
            terminal_outcome_reached,
            ToolCallOutcome.failed(handler_executed),
            **stores,
        )
        await _apply_tool_completed_goal_runtime(invocation, finished, **stores)
        await _record_tool_result_telemetry(
            invocation,
            success=False,
            output=None,
            error=err,
            telemetry_tags=telemetry_tags,
            extra_trace_fields=extra_trace_fields,
            duration_seconds=handler_duration,
            **stores,
        )
        await _emit_metric_for_tool_read(invocation, False, **stores)
        dispatch_trace.record_failed(err)
        raise err
    except Exception as err:
        handler_duration = time.perf_counter() - handler_start if handler_executed else 0.0
        fatal = FunctionCallError.fatal(str(err))
        finished = await notify_tool_finish_if_unclaimed(
            lifecycle_contributors,
            invocation,
            terminal_outcome_reached,
            ToolCallOutcome.failed(handler_executed),
            **stores,
        )
        await _apply_tool_completed_goal_runtime(invocation, finished, **stores)
        await _record_tool_result_telemetry(
            invocation,
            success=False,
            output=None,
            error=fatal,
            telemetry_tags=telemetry_tags,
            extra_trace_fields=extra_trace_fields,
            duration_seconds=handler_duration,
            **stores,
        )
        await _emit_metric_for_tool_read(invocation, False, **stores)
        dispatch_trace.record_failed(fatal)
        raise fatal from err

    from pycodex.core.tool_parallel import ToolCallResult

    output_success = _success_for_logging(output)
    handler_duration = time.perf_counter() - handler_start if handler_executed else 0.0
    await _record_tool_result_telemetry(
        invocation,
        success=output_success,
        output=output,
        error=None,
        telemetry_tags=telemetry_tags,
        extra_trace_fields=extra_trace_fields,
        duration_seconds=handler_duration,
        **stores,
    )
    await _emit_metric_for_tool_read(invocation, output_success, **stores)
    try:
        result = ToolCallResult(
            call_id=invocation.call_id,
            payload=invocation.payload,
            result=output,
            post_tool_use_payload=_tool_post_tool_use_payload(tool, invocation, output) if output_success else None,
        )
        result = await _apply_post_tool_use_hook(result, post_tool_use_hook, invocation=invocation, **stores)
    except FunctionCallError as err:
        finished = await notify_tool_finish_if_unclaimed(
            lifecycle_contributors,
            invocation,
            terminal_outcome_reached,
            ToolCallOutcome.failed(True),
            **stores,
        )
        await _apply_tool_completed_goal_runtime(invocation, finished, **stores)
        dispatch_trace.record_failed(err)
        raise
    except Exception as err:
        fatal = FunctionCallError.fatal(str(err))
        finished = await notify_tool_finish_if_unclaimed(
            lifecycle_contributors,
            invocation,
            terminal_outcome_reached,
            ToolCallOutcome.failed(True),
            **stores,
        )
        await _apply_tool_completed_goal_runtime(invocation, finished, **stores)
        dispatch_trace.record_failed(fatal)
        raise fatal from err
    finished = await notify_tool_finish_if_unclaimed(
        lifecycle_contributors,
        invocation,
        terminal_outcome_reached,
        ToolCallOutcome.completed(_success_for_logging(result.result)),
        **stores,
    )
    await _apply_tool_completed_goal_runtime(invocation, finished, **stores)
    dispatch_trace.record_completed(invocation, result.call_id, result.payload, result.result)
    return result


async def _apply_pre_tool_use_hook(
    tool: Any,
    invocation: ToolInvocation,
    pre_tool_use_hook: Any,
    *,
    dispatch_trace: ToolDispatchTrace,
    lifecycle_contributors: Any,
    terminal_outcome_reached: Any,
    **stores: Any,
) -> ToolInvocation:
    if pre_tool_use_hook is None:
        return invocation
    hook_payload = _tool_pre_tool_use_payload(tool, invocation)
    if hook_payload is None:
        return invocation
    try:
        raw_result = pre_tool_use_hook(hook_payload, invocation)
        if inspect.isawaitable(raw_result):
            raw_result = await raw_result
    except FunctionCallError as err:
        dispatch_trace.record_failed(err)
        await notify_tool_finish_if_unclaimed(
            lifecycle_contributors,
            invocation,
            terminal_outcome_reached,
            ToolCallOutcome.failed(False),
            **stores,
        )
        raise
    except Exception as err:
        fatal = FunctionCallError.fatal(str(err))
        dispatch_trace.record_failed(fatal)
        await notify_tool_finish_if_unclaimed(
            lifecycle_contributors,
            invocation,
            terminal_outcome_reached,
            ToolCallOutcome.failed(False),
            **stores,
        )
        raise fatal from err
    try:
        result = _coerce_pre_tool_use_result(raw_result)
    except FunctionCallError as err:
        dispatch_trace.record_failed(err)
        await notify_tool_finish_if_unclaimed(
            lifecycle_contributors,
            invocation,
            terminal_outcome_reached,
            ToolCallOutcome.failed(False),
            **stores,
        )
        raise
    except Exception as err:
        fatal = FunctionCallError.fatal(str(err))
        dispatch_trace.record_failed(fatal)
        await notify_tool_finish_if_unclaimed(
            lifecycle_contributors,
            invocation,
            terminal_outcome_reached,
            ToolCallOutcome.failed(False),
            **stores,
        )
        raise fatal from err
    if result.type == "blocked":
        err = FunctionCallError.respond_to_model(result.message or "")
        dispatch_trace.record_failed(err)
        await notify_tool_finish_if_unclaimed(
            lifecycle_contributors,
            invocation,
            terminal_outcome_reached,
            ToolCallOutcome.blocked(),
            **stores,
        )
        raise err
    if result.updated_input is None:
        return invocation
    try:
        return with_updated_hook_input(invocation, result.updated_input)
    except FunctionCallError as err:
        dispatch_trace.record_failed(err)
        await notify_tool_finish_if_unclaimed(
            lifecycle_contributors,
            invocation,
            terminal_outcome_reached,
            ToolCallOutcome.failed(False),
            **stores,
        )
        raise
    except Exception as err:
        fatal = FunctionCallError.fatal(str(err))
        dispatch_trace.record_failed(fatal)
        await notify_tool_finish_if_unclaimed(
            lifecycle_contributors,
            invocation,
            terminal_outcome_reached,
            ToolCallOutcome.failed(False),
            **stores,
        )
        raise fatal from err


async def _apply_post_tool_use_hook(
    result: Any,
    post_tool_use_hook: Any,
    *,
    invocation: ToolInvocation,
    **stores: Any,
) -> Any:
    if post_tool_use_hook is None or result.post_tool_use_payload is None:
        return result
    raw_outcome = post_tool_use_hook(result.post_tool_use_payload, result)
    if inspect.isawaitable(raw_outcome):
        raw_outcome = await raw_outcome
    outcome = _coerce_post_tool_use_outcome(raw_outcome)
    await _record_post_tool_use_additional_contexts(outcome, invocation=invocation, **stores)
    return apply_post_tool_use_feedback(result, post_tool_use_replacement_text(outcome))


async def _record_post_tool_use_additional_contexts(
    outcome: PostToolUseHookOutcome,
    *,
    invocation: ToolInvocation,
    **stores: Any,
) -> None:
    if not outcome.additional_contexts:
        return
    messages = additional_context_messages(outcome.additional_contexts)
    recorder = stores.get("additional_context_recorder")
    if recorder is not None:
        await _call_additional_context_recorder(recorder, messages)
        return
    for target in (
        invocation.session,
        invocation.turn,
        stores.get("session"),
        stores.get("turn"),
    ):
        if target is None:
            continue
        for method_name in (
            "record_additional_contexts",
            "record_additional_context_messages",
            "add_additional_context_messages",
        ):
            method = _field_or_attr(target, method_name)
            if method is not None:
                await _call_additional_context_recorder(method, messages)
                return


async def _call_additional_context_recorder(recorder: Any, messages: tuple[ResponseItem, ...]) -> None:
    if not callable(recorder):
        raise TypeError("additional_context_recorder must be callable")
    result = recorder(messages)
    if inspect.isawaitable(result):
        await result


async def _apply_tool_completed_goal_runtime(
    invocation: ToolInvocation,
    finished: bool,
    **stores: Any,
) -> None:
    if not finished:
        return
    session = invocation.session if invocation.session is not None else stores.get("session")
    if session is None:
        return
    apply = _field_or_attr(session, "goal_runtime_apply")
    if apply is None:
        return
    if not callable(apply):
        LOG.warning("failed to account thread goal progress after tool call: session.goal_runtime_apply is not callable")
        return
    turn = invocation.turn if invocation.turn is not None else stores.get("turn")
    event = {
        "type": "tool_completed",
        "turn_context": turn,
        "tool_name": invocation.tool_name.name,
    }
    try:
        result = apply(event)
        if inspect.isawaitable(result):
            await result
    except Exception as err:
        LOG.warning("failed to account thread goal progress after tool call: %s", err)


def _tool_dispatch_trace(invocation: ToolInvocation, **stores: Any) -> ToolDispatchTrace:
    trace_context = stores.get("tool_dispatch_trace_context")
    if trace_context is None:
        trace_context = stores.get("rollout_thread_trace")
    session = invocation.session if invocation.session is not None else stores.get("session")
    if trace_context is None and session is not None:
        services = _field_or_attr(session, "services")
        trace_context = _field_or_attr(services, "rollout_thread_trace")
    turn = invocation.turn if invocation.turn is not None else stores.get("turn")
    return ToolDispatchTrace.start(
        invocation,
        trace_context,
        thread_id=_trace_thread_id(session),
        codex_turn_id=_trace_turn_id(turn),
    )


async def _tool_telemetry_fields(tool: Any, invocation: ToolInvocation) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
    method = getattr(tool, "telemetry_tags", None)
    if method is None:
        return (), ()
    try:
        raw_tags = method(invocation)
    except TypeError:
        raw_tags = method()
    if inspect.isawaitable(raw_tags):
        raw_tags = await raw_tags
    tags = _coerce_telemetry_tags(raw_tags)
    normal_tags: list[tuple[str, str]] = []
    extra_trace_fields: list[tuple[str, str]] = []
    for key, value in tags:
        if key in {"mcp_server", "mcp_server_origin"}:
            extra_trace_fields.append((key, value))
        else:
            normal_tags.append((key, value))
    return tuple(normal_tags), tuple(extra_trace_fields)


def _coerce_telemetry_tags(value: Any) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        raise TypeError("telemetry_tags must be an iterable of (str, str) pairs")
    result = []
    for entry in value:
        if not isinstance(entry, (tuple, list)) or len(entry) != 2:
            raise TypeError("telemetry_tags must be an iterable of (str, str) pairs")
        key, tag_value = entry
        if not isinstance(key, str) or not isinstance(tag_value, str):
            raise TypeError("telemetry_tags entries must contain string key/value pairs")
        result.append((key, tag_value))
    return tuple(result)


async def _record_tool_result_telemetry(
    invocation: ToolInvocation,
    *,
    success: bool,
    output: Any,
    error: Any,
    telemetry_tags: tuple[tuple[str, str], ...],
    extra_trace_fields: tuple[tuple[str, str], ...],
    duration_seconds: float,
    **stores: Any,
) -> None:
    recorder = stores.get("tool_result_telemetry_recorder")
    if recorder is None:
        session = invocation.session if invocation.session is not None else stores.get("session")
        recorder = _field_or_attr(session, "tool_result_with_tags") if session is not None else None
    if recorder is None:
        return
    if not callable(recorder):
        raise TypeError("tool_result_telemetry_recorder must be callable")
    event = {
        "tool_name": flat_tool_name(invocation.tool_name),
        "call_id": invocation.call_id,
        "log_payload": invocation.payload.log_payload(),
        "log_preview": _log_preview_for_telemetry(output),
        "duration_seconds": duration_seconds,
        "success": success,
        "telemetry_tags": _tool_result_base_tags(invocation, **stores) + telemetry_tags,
        "extra_trace_fields": extra_trace_fields,
        "output": output,
        "error": error,
        "error_message": _error_message_for_telemetry(error),
    }
    result = recorder(event)
    if inspect.isawaitable(result):
        await result


def _increment_active_turn_tool_calls(invocation: ToolInvocation, **stores: Any) -> None:
    session = invocation.session if invocation.session is not None else stores.get("session")
    if session is None:
        return
    active_turn = _unwrap_optional_holder(_field_or_attr(session, "active_turn"))
    if active_turn is None:
        return
    turn_state = _unwrap_optional_holder(_field_or_attr(active_turn, "turn_state"))
    if turn_state is None:
        return
    current = _field_or_attr(turn_state, "tool_calls")
    if not isinstance(current, int) or isinstance(current, bool):
        return
    next_value = current + 1 if current < ((1 << 64) - 1) else current
    if isinstance(turn_state, dict):
        turn_state["tool_calls"] = next_value
    else:
        try:
            setattr(turn_state, "tool_calls", next_value)
        except (AttributeError, TypeError):
            return


def _unwrap_optional_holder(value: Any) -> Any:
    if callable(value):
        value = value()
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def _field_or_attr(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _call_or_value(value: Any) -> Any:
    return value() if callable(value) else value


def _log_preview_for_telemetry(output: Any) -> str | None:
    if output is None:
        return None
    method = getattr(output, "log_preview", None)
    if method is None:
        return None
    preview = method()
    if not isinstance(preview, str):
        raise TypeError("log_preview must return a string")
    return preview


def _error_message_for_telemetry(error: Any) -> str | None:
    if error is None:
        return None
    message = getattr(error, "message", None)
    return message if isinstance(message, str) else str(error)


def _tool_result_base_tags(invocation: ToolInvocation, **stores: Any) -> tuple[tuple[str, str], ...]:
    turn = invocation.turn if invocation.turn is not None else stores.get("turn")
    profile = stores.get("permission_profile")
    if profile is None:
        profile = _call_or_value(_field_or_attr(turn, "permission_profile"))
    if profile is None:
        config = _field_or_attr(turn, "config")
        profile = _call_or_value(_field_or_attr(config, "permission_profile"))
    if profile is None:
        return ()
    cwd = stores.get("cwd") or _field_or_attr(turn, "cwd") or _field_or_attr(_field_or_attr(turn, "config"), "cwd") or "."
    network = stores.get("network")
    if network is None:
        network = _field_or_attr(turn, "network")
    windows_sandbox_level = stores.get("windows_sandbox_level")
    if windows_sandbox_level is None:
        windows_sandbox_level = _field_or_attr(turn, "windows_sandbox_level")
    return (
        ("sandbox", _permission_profile_sandbox_tag(profile, windows_sandbox_level, network is not None)),
        ("sandbox_policy", _permission_profile_policy_tag(profile, cwd)),
    )


def _permission_profile_sandbox_tag(profile: Any, windows_sandbox_level: Any, enforce_managed_network: bool) -> str:
    profile_type = _field_or_attr(profile, "type")
    if profile_type == "disabled":
        return "none"
    if profile_type == "external":
        return "external"
    file_system_policy = _call_method(profile, "file_system_sandbox_policy")
    network_policy = _call_method(profile, "network_sandbox_policy")
    if file_system_policy is not None:
        full_write = bool(_call_method(file_system_policy, "has_full_disk_write_access"))
        network_enabled = bool(_call_method(network_policy, "is_enabled")) if network_policy is not None else False
        if full_write and (network_enabled or not enforce_managed_network):
            return "none"
    if sys.platform == "win32":
        level = getattr(windows_sandbox_level, "value", windows_sandbox_level)
        if str(level).lower() == "elevated":
            return "windows_elevated"
        if str(level).lower() == "disabled":
            return "none"
        return "windows_sandbox"
    if sys.platform == "darwin":
        return "seatbelt"
    if sys.platform.startswith("linux"):
        return "seccomp"
    return "none"


def _permission_profile_policy_tag(profile: Any, cwd: Any) -> str:
    profile_type = _field_or_attr(profile, "type")
    if profile_type == "disabled":
        return "danger-full-access"
    if profile_type == "external":
        return "external-sandbox"
    file_system_policy = _call_method(profile, "file_system_sandbox_policy")
    if file_system_policy is None:
        return "read-only"
    if bool(_call_method(file_system_policy, "has_full_disk_write_access")):
        return "danger-full-access"
    writable_roots = _call_method(file_system_policy, "get_writable_roots_with_cwd", cwd)
    return "read-only" if not writable_roots else "workspace-write"


def _call_method(value: Any, name: str, *args: Any) -> Any:
    method = _field_or_attr(value, name)
    if not callable(method):
        return None
    return method(*args)


def _trace_thread_id(session: Any) -> str:
    if session is None:
        return ""
    for name in ("conversation_id", "thread_id", "session_id"):
        value = _field_or_attr(session, name)
        if value is not None:
            return str(value)
    return ""


def _trace_turn_id(turn: Any) -> str:
    if turn is None:
        return ""
    for name in ("sub_id", "turn_id", "id"):
        value = _field_or_attr(turn, name)
        if value is not None:
            return str(value)
    return ""


def apply_post_tool_use_feedback(result: Any, replacement_text: str | None) -> Any:
    if replacement_text is None:
        return result
    if not isinstance(replacement_text, str):
        raise TypeError("replacement_text must be a string or None")
    from pycodex.core.tool_parallel import ToolCallResult

    if not isinstance(result, ToolCallResult):
        raise TypeError("result must be ToolCallResult")
    return ToolCallResult(
        call_id=result.call_id,
        payload=result.payload,
        result=PostToolUseFeedbackOutput(
            original=result.result,
            model_visible=FunctionToolOutput.from_text(replacement_text, None),
        ),
        post_tool_use_payload=result.post_tool_use_payload,
    )


def _coerce_pre_tool_use_result(value: Any) -> PreToolUseHookResult:
    if isinstance(value, PreToolUseHookResult):
        return value
    if isinstance(value, dict):
        result_type = value.get("type")
        if result_type == "continue":
            return PreToolUseHookResult.continue_(value.get("updated_input"))
        if result_type == "blocked":
            return PreToolUseHookResult.blocked(value.get("message", ""))
    raise TypeError("pre_tool_use_hook must return PreToolUseHookResult")


def _coerce_post_tool_use_outcome(value: Any) -> PostToolUseHookOutcome:
    if isinstance(value, PostToolUseHookOutcome):
        return value
    if isinstance(value, dict):
        should_stop = value.get("should_stop", False)
        if not isinstance(should_stop, bool):
            raise TypeError("should_stop must be a bool")
        additional_contexts = value.get("additional_contexts", ())
        if isinstance(additional_contexts, (str, bytes)) or not isinstance(additional_contexts, (tuple, list)):
            raise TypeError("additional_contexts must be a tuple or list of strings")
        additional_contexts = tuple(additional_contexts)
        if not all(isinstance(item, str) for item in additional_contexts):
            raise TypeError("additional_contexts must contain only strings")
        return PostToolUseHookOutcome(
            should_stop=should_stop,
            feedback_message=value.get("feedback_message"),
            stop_reason=value.get("stop_reason"),
            additional_contexts=additional_contexts,
        )
    raise TypeError("post_tool_use_hook must return PostToolUseHookOutcome")


def _tool_pre_tool_use_payload(tool: Any, invocation: ToolInvocation) -> Any:
    method = getattr(tool, "pre_tool_use_payload", None)
    if method is None:
        from pycodex.core.tool_registry import pre_tool_use_payload

        value = pre_tool_use_payload(invocation)
    else:
        value = method(invocation)
    if value is not None and not isinstance(value, PreToolUsePayload):
        raise TypeError("pre_tool_use_payload must return PreToolUsePayload or None")
    return value


def _tool_post_tool_use_payload(tool: Any, invocation: ToolInvocation, output: Any) -> Any:
    method = getattr(tool, "post_tool_use_payload", None)
    if method is None:
        from pycodex.core.tool_registry import post_tool_use_payload

        value = post_tool_use_payload(invocation, output)
    else:
        value = method(invocation, output)
    if value is not None and not isinstance(value, PostToolUsePayload):
        raise TypeError("post_tool_use_payload must return PostToolUsePayload or None")
    return value


async def notify_tool_finish_if_unclaimed(
    lifecycle_contributors: Any,
    invocation: ToolInvocation,
    terminal_outcome_reached: Any,
    outcome: ToolCallOutcome,
    **stores: Any,
) -> bool:
    if terminal_outcome_reached is not None:
        swap = getattr(terminal_outcome_reached, "swap", None)
        if swap is None:
            raise TypeError("terminal_outcome_reached must expose swap(bool)")
        if swap(True):
            return False
    await notify_tool_finish(lifecycle_contributors, invocation, outcome, **stores)
    return True


async def _handle_tool(tool: Any, invocation: ToolInvocation) -> Any:
    handle = getattr(tool, "handle", None)
    if handle is None:
        raise FunctionCallError.fatal(f"tool {invocation.tool_name} has no handle method")
    result = handle(invocation)
    if inspect.isawaitable(result):
        result = await result
    return result


def _success_for_logging(output: Any) -> bool:
    method = getattr(output, "success_for_logging", None)
    if method is None:
        return True
    value = method()
    if not isinstance(value, bool):
        raise TypeError("success_for_logging must return a bool")
    return value


async def _emit_metric_for_tool_read(invocation: ToolInvocation, success: bool, **stores: Any) -> None:
    telemetry = stores.get("session_telemetry") or stores.get("telemetry")
    session = invocation.session if invocation.session is not None else stores.get("session")
    turn = invocation.turn if invocation.turn is not None else stores.get("turn")
    if telemetry is None:
        telemetry = _field_or_attr(turn, "session_telemetry") or _field_or_attr(session, "session_telemetry")
    if telemetry is None:
        return

    session_shell = stores.get("session_shell")
    if session_shell is None:
        user_shell = _field_or_attr(session, "user_shell")
        if callable(user_shell):
            session_shell = user_shell()
        elif user_shell is not None:
            session_shell = user_shell

    allow_login_shell = stores.get("allow_login_shell")
    if allow_login_shell is None:
        permissions = _field_or_attr(_field_or_attr(_field_or_attr(turn, "config"), "permissions"), "allow_login_shell")
        allow_login_shell = permissions if isinstance(permissions, bool) else False

    unified_exec_shell_mode = stores.get("unified_exec_shell_mode") or _field_or_attr(turn, "unified_exec_shell_mode")
    resolve_path = stores.get("resolve_path")
    if resolve_path is None:
        turn_resolver = _field_or_attr(turn, "resolve_path")
        resolve_path = turn_resolver if callable(turn_resolver) else None

    try:
        emit_metric_for_tool_read(
            invocation,
            success,
            telemetry,
            session_shell=session_shell,
            allow_login_shell=allow_login_shell,
            unified_exec_shell_mode=unified_exec_shell_mode,
            resolve_path=resolve_path,
        )
    except Exception as err:
        LOG.warning("failed to emit tool read memory metric: %s", err)


__all__ = [
    "ConversationHistory",
    "FunctionCallError",
    "ToolCall",
    "ToolRouter",
    "build_tool_call",
    "dispatch_tool_call",
    "dispatch_tool_call_with_terminal_outcome",
    "apply_post_tool_use_feedback",
    "notify_tool_finish_if_unclaimed",
]
