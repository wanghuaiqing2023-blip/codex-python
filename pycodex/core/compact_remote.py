"""Pure remote-compaction post-processing helpers.

Ported from the standalone helper portions of
``codex/codex-rs/core/src/compact_remote.rs``.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from pycodex.core.client_common import Prompt
from pycodex.core.compact import (
    COMPACTION_STRATEGY_MEMENTO,
    CompactionAnalyticsAttempt,
    CompactionPhase,
    CompactionReason,
    CompactionStatus,
    CompactionTrigger,
    InitialContextInjection,
    compaction_status_from_result,
    insert_initial_context_before_last_real_user_or_summary,
)
from pycodex.core.context_manager.history import (
    TotalTokenUsageBreakdown,
    estimate_response_item_model_visible_bytes,
)
from pycodex.core.context_manager.normalize import (
    IMAGE_CONTENT_OMITTED_PLACEHOLDER,
    ensure_call_outputs_present,
    normalize_call_outputs,
    remove_corresponding_for as _normalize_remove_corresponding_for,
    remove_orphan_outputs,
    strip_images_when_unsupported,
)
from pycodex.core.event_mapping import parse_turn_item
from pycodex.core.turn_metadata import CompactionTurnMetadata
from pycodex.protocol import (
    BaseInstructions,
    CompactedItem,
    ContextCompactionItem,
    EventMsg,
    ResponseItem,
    TurnContextItem,
    TurnItem,
    TurnStartedEvent,
)


def should_keep_compacted_history_item(item: ResponseItem) -> bool:
    if not isinstance(item, ResponseItem):
        raise TypeError("item must be a ResponseItem")
    if item.type == "message":
        if item.role == "developer":
            return False
        if item.role == "user":
            turn_item = parse_turn_item(item)
            return turn_item is not None and turn_item.type in {"UserMessage", "HookPrompt"}
        if item.role == "assistant":
            return True
        return False
    if item.type in {"compaction", "context_compaction"}:
        return True
    if item.type == "compaction_trigger":
        return False
    return False


def process_compacted_history(
    compacted_history: Sequence[ResponseItem],
    initial_context_injection: InitialContextInjection,
    initial_context: Sequence[ResponseItem] = (),
) -> list[ResponseItem]:
    injection = InitialContextInjection(initial_context_injection)
    filtered = [item for item in _response_items(compacted_history, "compacted_history") if should_keep_compacted_history_item(item)]
    context = _response_items(initial_context, "initial_context") if injection is InitialContextInjection.BEFORE_LAST_USER_MESSAGE else []
    return insert_initial_context_before_last_real_user_or_summary(filtered, context)


async def run_inline_remote_auto_compact_task(
    sess: Any,
    turn_context: Any,
    initial_context_injection: InitialContextInjection,
    reason: CompactionReason | str = CompactionReason.CONTEXT_LIMIT,
    phase: CompactionPhase | str = CompactionPhase.MID_TURN,
) -> None:
    await run_remote_compact_task_inner(
        sess,
        turn_context,
        initial_context_injection,
        CompactionTrigger.AUTO,
        reason,
        phase,
    )


async def run_remote_compact_task(sess: Any, turn_context: Any) -> None:
    await _send_event(
        sess,
        turn_context,
        EventMsg.with_payload(
            "task_started",
            TurnStartedEvent(
                turn_id=str(_field(turn_context, "sub_id")),
                trace_id=_field(turn_context, "trace_id"),
                started_at=await _started_at(turn_context),
                model_context_window=_model_context_window(turn_context),
                collaboration_mode_kind=_collaboration_mode_kind(turn_context),
            ),
        ),
    )
    await run_remote_compact_task_inner(
        sess,
        turn_context,
        InitialContextInjection.DO_NOT_INJECT,
        CompactionTrigger.MANUAL,
        CompactionReason.USER_REQUESTED,
        CompactionPhase.STANDALONE_TURN,
    )


async def run_remote_compact_task_inner(
    sess: Any,
    turn_context: Any,
    initial_context_injection: InitialContextInjection | str,
    trigger: CompactionTrigger | str,
    reason: CompactionReason | str,
    phase: CompactionPhase | str,
) -> None:
    metadata = CompactionTurnMetadata(
        trigger=_enum_value(trigger),
        reason=_enum_value(reason),
        implementation="responses_compact",
        phase=_enum_value(phase),
        strategy=COMPACTION_STRATEGY_MEMENTO,
    )
    attempt = await CompactionAnalyticsAttempt.begin(
        sess,
        turn_context,
        trigger,
        reason,
        "responses_compact",
        phase,
    )
    pre = await _run_compact_hook(sess, turn_context, "run_pre_compact_hooks", trigger)
    if _hook_stopped(pre):
        error = _hook_reason(pre) or "PreCompact hook stopped execution"
        await attempt.track(sess, CompactionStatus.INTERRUPTED, error)
        raise RuntimeError(error)
    try:
        await run_remote_compact_task_inner_impl(
            sess,
            turn_context,
            InitialContextInjection(initial_context_injection),
            metadata,
        )
    except Exception as exc:
        await attempt.track(sess, compaction_status_from_result(exc), str(exc))
        await _send_error(sess, turn_context, exc)
        raise
    post = await _run_compact_hook(sess, turn_context, "run_post_compact_hooks", trigger)
    if _hook_stopped(post):
        await attempt.track(sess, CompactionStatus.INTERRUPTED, "PostCompact hook stopped execution")
        raise RuntimeError("PostCompact hook stopped execution")
    await attempt.track(sess, CompactionStatus.COMPLETED, None)


async def run_remote_compact_task_inner_impl(
    sess: Any,
    turn_context: Any,
    initial_context_injection: InitialContextInjection,
    compaction_metadata: CompactionTurnMetadata,
) -> None:
    context_compaction_item = ContextCompactionItem.new()
    compaction_item = TurnItem.context_compaction(context_compaction_item)
    await _call_required(sess, "emit_turn_item_started", turn_context, compaction_item)

    history = await _clone_history(sess)
    base_instructions = await _base_instructions(sess)
    trace_input_history = list(_history_raw_items(history))
    trimmed = _trim_history_for_context_window(history, turn_context, base_instructions)
    prompt_input = _history_for_prompt(trimmed, _input_modalities(turn_context))
    tool_router = await _built_tools(sess, turn_context)
    prompt = Prompt(
        input=prompt_input,
        tools=list(_model_visible_specs(tool_router)),
        parallel_tool_calls=bool(_field(_field(turn_context, "model_info"), "supports_parallel_tool_calls", False)),
        base_instructions=base_instructions,
        personality=_field(turn_context, "personality"),
        output_schema=None,
        output_schema_strict=True,
    )
    header = _compaction_metadata_header(sess, turn_context, compaction_metadata)
    try:
        compacted_history = await run_remote_compaction_request(sess, turn_context, prompt, header)
    except Exception as exc:
        await log_remote_compaction_request_failure(sess, turn_context, prompt, exc)
        raise

    initial_context: Sequence[ResponseItem] = ()
    reference_context_item = None
    if initial_context_injection is InitialContextInjection.BEFORE_LAST_USER_MESSAGE:
        initial_context = await _build_initial_context(sess, turn_context)
        to_context_item = getattr(turn_context, "to_turn_context_item", None)
        if callable(to_context_item):
            reference_context_item = to_context_item()
    plan = build_remote_compaction_success_plan(
        trace_input_history,
        compacted_history,
        initial_context_injection,
        initial_context,
        reference_context_item,
    )
    await apply_remote_compaction_install_plan(sess, plan)
    await _call_required(sess, "recompute_token_usage", turn_context)
    await _call_required(sess, "emit_turn_item_completed", turn_context, compaction_item)


async def run_remote_compaction_request(
    sess: Any,
    turn_context: Any,
    prompt: Prompt,
    turn_metadata_header: str | None,
) -> list[ResponseItem]:
    model_client = _field(_field(sess, "services"), "model_client")
    compact = getattr(model_client, "compact_conversation_history", None)
    if not callable(compact):
        raise TypeError("remote compaction requires services.model_client.compact_conversation_history()")
    settings = {
        "effort": _field(turn_context, "reasoning_effort"),
        "summary": _field(turn_context, "reasoning_summary"),
        "service_tier": _service_tier_for_remote_compaction(sess, turn_context),
    }
    result = await _maybe_await(
        compact(
            prompt,
            _field(turn_context, "model_info"),
            settings,
            _field(turn_context, "session_telemetry"),
            _compaction_trace(sess, turn_context),
            turn_metadata_header,
        )
    )
    return list(_response_items(result, "remote compact result"))


def normalize_history_for_prompt(
    history: Sequence[ResponseItem],
    input_modalities: Sequence[Any] | None = None,
) -> tuple[ResponseItem, ...]:
    return strip_images_when_unsupported(input_modalities, normalize_call_outputs(history))


@dataclass(frozen=True)
class RemoteCompactionInstallPlan:
    new_history: tuple[ResponseItem, ...]
    reference_context_item: TurnContextItem | None
    compacted_item: CompactedItem
    checkpoint_payload: dict[str, list[dict[str, Any]]]

    def __post_init__(self) -> None:
        object.__setattr__(self, "new_history", tuple(_response_items(self.new_history, "new_history")))
        if self.reference_context_item is not None and not isinstance(self.reference_context_item, TurnContextItem):
            raise TypeError("reference_context_item must be a TurnContextItem or None")
        if not isinstance(self.compacted_item, CompactedItem):
            raise TypeError("compacted_item must be a CompactedItem")
        if not isinstance(self.checkpoint_payload, dict):
            raise TypeError("checkpoint_payload must be a dict")


def build_remote_compaction_install_plan(
    trace_input_history: Sequence[ResponseItem],
    new_history: Sequence[ResponseItem],
    initial_context_injection: InitialContextInjection,
    reference_context_item: TurnContextItem | None = None,
) -> RemoteCompactionInstallPlan:
    trace_items = _response_items(trace_input_history, "trace_input_history")
    replacement_history = _response_items(new_history, "new_history")
    injection = InitialContextInjection(initial_context_injection)
    if injection is InitialContextInjection.BEFORE_LAST_USER_MESSAGE:
        if not isinstance(reference_context_item, TurnContextItem):
            raise TypeError("reference_context_item must be provided for before-last-user-message injection")
    else:
        reference_context_item = None
    replacement_history_json = tuple(item.to_mapping() for item in replacement_history)
    return RemoteCompactionInstallPlan(
        new_history=tuple(replacement_history),
        reference_context_item=reference_context_item,
        compacted_item=CompactedItem(message="", replacement_history=replacement_history_json),
        checkpoint_payload={
            "input_history": [item.to_mapping() for item in trace_items],
            "replacement_history": [item.to_mapping() for item in replacement_history],
        },
    )


def build_remote_compaction_success_plan(
    trace_input_history: Sequence[ResponseItem],
    compacted_history: Sequence[ResponseItem],
    initial_context_injection: InitialContextInjection,
    initial_context: Sequence[ResponseItem] = (),
    reference_context_item: TurnContextItem | None = None,
) -> RemoteCompactionInstallPlan:
    new_history = process_compacted_history(
        compacted_history,
        initial_context_injection,
        initial_context,
    )
    return build_remote_compaction_install_plan(
        trace_input_history,
        new_history,
        initial_context_injection,
        reference_context_item,
    )


async def apply_remote_compaction_install_plan(session: Any, plan: RemoteCompactionInstallPlan) -> None:
    if not isinstance(plan, RemoteCompactionInstallPlan):
        raise TypeError("plan must be a RemoteCompactionInstallPlan")
    replace = getattr(session, "replace_compacted_history", None)
    if not callable(replace):
        raise TypeError("session must expose replace_compacted_history")
    result = replace(plan.new_history, plan.reference_context_item, plan.compacted_item)
    if inspect.isawaitable(result):
        await result


@dataclass(frozen=True)
class CompactRequestLogData:
    failing_compaction_request_model_visible_bytes: int

    def __post_init__(self) -> None:
        if isinstance(self.failing_compaction_request_model_visible_bytes, bool) or not isinstance(
            self.failing_compaction_request_model_visible_bytes,
            int,
        ):
            raise TypeError("failing_compaction_request_model_visible_bytes must be an integer")
        if self.failing_compaction_request_model_visible_bytes < 0:
            raise ValueError("failing_compaction_request_model_visible_bytes must be non-negative")


@dataclass(frozen=True)
class RemoteCompactFailureLogData:
    turn_id: str
    last_api_response_total_tokens: int
    all_history_items_model_visible_bytes: int
    estimated_tokens_of_items_added_since_last_successful_api_response: int
    estimated_bytes_of_items_added_since_last_successful_api_response: int
    model_context_window_tokens: int | None
    failing_compaction_request_model_visible_bytes: int
    compact_error: str
    message: str = "remote compaction failed"

    def __post_init__(self) -> None:
        if not isinstance(self.turn_id, str):
            raise TypeError("turn_id must be a string")
        if not isinstance(self.compact_error, str):
            raise TypeError("compact_error must be a string")
        if self.model_context_window_tokens is not None:
            _ensure_non_negative_int(self.model_context_window_tokens, "model_context_window_tokens")
        for name in (
            "last_api_response_total_tokens",
            "all_history_items_model_visible_bytes",
            "estimated_tokens_of_items_added_since_last_successful_api_response",
            "estimated_bytes_of_items_added_since_last_successful_api_response",
            "failing_compaction_request_model_visible_bytes",
        ):
            _ensure_non_negative_int(getattr(self, name), name)


@dataclass(frozen=True)
class TrimFunctionCallHistoryResult:
    items: tuple[ResponseItem, ...]
    deleted_items: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "items", tuple(_response_items(self.items, "items")))
        if isinstance(self.deleted_items, bool) or not isinstance(self.deleted_items, int):
            raise TypeError("deleted_items must be an integer")
        if self.deleted_items < 0:
            raise ValueError("deleted_items must be non-negative")


def build_compact_request_log_data(
    input: Sequence[ResponseItem],
    instructions: str,
    *,
    estimate_item_bytes: Callable[[ResponseItem], int] | None = None,
) -> CompactRequestLogData:
    if not isinstance(instructions, str):
        raise TypeError("instructions must be a string")
    items = _response_items(input, "input")
    estimator = estimate_item_bytes or estimate_response_item_model_visible_bytes
    total = len(instructions.encode("utf-8"))
    for item in items:
        item_bytes = estimator(item)
        if isinstance(item_bytes, bool) or not isinstance(item_bytes, int):
            raise TypeError("estimate_item_bytes must return an integer")
        if item_bytes < 0:
            raise ValueError("estimate_item_bytes must return a non-negative integer")
        total = min(total + item_bytes, 2**63 - 1)
    return CompactRequestLogData(total)


def build_remote_compact_failure_log_data(
    turn_id: str,
    compact_request_log_data: CompactRequestLogData,
    total_usage_breakdown: TotalTokenUsageBreakdown,
    compact_error: object,
    *,
    model_context_window_tokens: int | None = None,
) -> RemoteCompactFailureLogData:
    if not isinstance(compact_request_log_data, CompactRequestLogData):
        raise TypeError("compact_request_log_data must be CompactRequestLogData")
    if not isinstance(total_usage_breakdown, TotalTokenUsageBreakdown):
        raise TypeError("total_usage_breakdown must be TotalTokenUsageBreakdown")
    return RemoteCompactFailureLogData(
        turn_id=turn_id,
        last_api_response_total_tokens=total_usage_breakdown.last_api_response_total_tokens,
        all_history_items_model_visible_bytes=total_usage_breakdown.all_history_items_model_visible_bytes,
        estimated_tokens_of_items_added_since_last_successful_api_response=(
            total_usage_breakdown.estimated_tokens_of_items_added_since_last_successful_api_response
        ),
        estimated_bytes_of_items_added_since_last_successful_api_response=(
            total_usage_breakdown.estimated_bytes_of_items_added_since_last_successful_api_response
        ),
        model_context_window_tokens=model_context_window_tokens,
        failing_compaction_request_model_visible_bytes=compact_request_log_data.failing_compaction_request_model_visible_bytes,
        compact_error=str(compact_error),
    )


async def log_remote_compaction_request_failure(sess: Any, turn_context: Any, prompt: Prompt, err: Exception) -> None:
    breakdown_getter = getattr(sess, "get_total_token_usage_breakdown", None)
    breakdown = await _maybe_await(breakdown_getter()) if callable(breakdown_getter) else None
    if breakdown is None:
        return
    data = build_compact_request_log_data(prompt.input, prompt.base_instructions.text)
    log_remote_compact_failure(turn_context, data, breakdown, err)


def log_remote_compact_failure(
    turn_context: Any,
    log_data: CompactRequestLogData,
    total_usage_breakdown: TotalTokenUsageBreakdown,
    err: Exception,
) -> RemoteCompactFailureLogData:
    return build_remote_compact_failure_log_data(
        str(_field(turn_context, "sub_id", "")),
        log_data,
        total_usage_breakdown,
        err,
        model_context_window_tokens=_model_context_window(turn_context),
    )


def is_codex_generated_item(item: ResponseItem) -> bool:
    if not isinstance(item, ResponseItem):
        raise TypeError("item must be a ResponseItem")
    if item.type in {"function_call_output", "tool_search_output", "custom_tool_call_output"}:
        return True
    return item.type == "message" and item.role == "developer"


def trim_function_call_history_to_fit_context_window(
    history: Sequence[ResponseItem],
    context_window: int | None,
    base_instructions: BaseInstructions | str,
    estimate_token_count_with_base_instructions: Callable[[Sequence[ResponseItem], BaseInstructions | str], int | None],
) -> TrimFunctionCallHistoryResult:
    items = _response_items(history, "history")
    if context_window is None:
        return TrimFunctionCallHistoryResult(tuple(items), 0)
    if isinstance(context_window, bool) or not isinstance(context_window, int):
        raise TypeError("context_window must be an integer or None")
    if context_window < 0:
        raise ValueError("context_window must be non-negative")
    if not callable(estimate_token_count_with_base_instructions):
        raise TypeError("estimate_token_count_with_base_instructions must be callable")

    deleted_items = 0
    while True:
        estimated_tokens = estimate_token_count_with_base_instructions(tuple(items), base_instructions)
        if estimated_tokens is None:
            break
        if isinstance(estimated_tokens, bool) or not isinstance(estimated_tokens, int):
            raise TypeError("estimate_token_count_with_base_instructions must return an integer or None")
        if estimated_tokens <= context_window:
            break
        if not items:
            break
        last_item = items[-1]
        if not is_codex_generated_item(last_item):
            break
        removed = items.pop()
        _remove_corresponding_for(items, removed)
        deleted_items += 1
    return TrimFunctionCallHistoryResult(tuple(items), deleted_items)


def _remove_corresponding_for(items: list[ResponseItem], removed: ResponseItem) -> None:
    _normalize_remove_corresponding_for(items, removed)


def _response_items(value: Sequence[ResponseItem], label: str) -> list[ResponseItem]:
    if isinstance(value, ResponseItem) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence of ResponseItem")
    if not all(isinstance(item, ResponseItem) for item in value):
        raise TypeError(f"{label} must contain ResponseItem values")
    return list(value)


def _ensure_non_negative_int(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


async def _clone_history(sess: Any) -> Any:
    clone_history = getattr(sess, "clone_history", None)
    if not callable(clone_history):
        raise TypeError("remote compaction requires session.clone_history()")
    return await _maybe_await(clone_history())


def _history_raw_items(history: Any) -> Sequence[ResponseItem]:
    raw_items = getattr(history, "raw_items", None)
    if callable(raw_items):
        return raw_items()
    if isinstance(history, Sequence):
        return history
    raise TypeError("remote compaction history must expose raw_items()")


def _history_for_prompt(history: Any, input_modalities: Any) -> list[ResponseItem]:
    for_prompt = getattr(history, "for_prompt", None)
    if callable(for_prompt):
        return list(for_prompt(input_modalities))
    return list(_history_raw_items(history))


async def _base_instructions(sess: Any) -> BaseInstructions:
    getter = getattr(sess, "get_base_instructions", None)
    if not callable(getter):
        raise TypeError("remote compaction requires session.get_base_instructions()")
    value = await _maybe_await(getter())
    if isinstance(value, BaseInstructions):
        return value
    if isinstance(value, str):
        return BaseInstructions(value)
    raise TypeError("session.get_base_instructions() must return BaseInstructions or str")


def _trim_history_for_context_window(history: Any, turn_context: Any, base_instructions: BaseInstructions) -> Sequence[ResponseItem]:
    raw = list(_history_raw_items(history))
    estimator = getattr(history, "estimate_token_count_with_base_instructions", None)
    if not callable(estimator):
        return raw
    result = trim_function_call_history_to_fit_context_window(
        raw,
        _model_context_window(turn_context),
        base_instructions,
        lambda items, instructions: estimator(instructions, items)
        if _estimator_accepts_instructions_first(estimator)
        else estimator(items, instructions),
    )
    return result.items


def _estimator_accepts_instructions_first(estimator: Callable[..., Any]) -> bool:
    try:
        params = list(inspect.signature(estimator).parameters)
    except (TypeError, ValueError):
        return False
    return bool(params and "instruction" in params[0])


def _input_modalities(turn_context: Any) -> Any:
    return _field(_field(turn_context, "model_info"), "input_modalities")


async def _built_tools(sess: Any, turn_context: Any) -> Any:
    builder = getattr(sess, "built_tools", None)
    if callable(builder):
        return await _maybe_await(builder(turn_context))
    router = getattr(turn_context, "tool_router", None)
    if router is not None:
        return router
    return ()


def _model_visible_specs(tool_router: Any) -> Sequence[Any]:
    specs = getattr(tool_router, "model_visible_specs", None)
    if callable(specs):
        return specs()
    if isinstance(tool_router, Sequence) and not isinstance(tool_router, (str, bytes)):
        return tool_router
    return ()


def _compaction_metadata_header(sess: Any, turn_context: Any, metadata: CompactionTurnMetadata) -> str | None:
    state = _field(turn_context, "turn_metadata_state")
    current = getattr(state, "current_header_value_for_compaction", None)
    if not callable(current):
        return None
    model_client = _field(_field(sess, "services"), "model_client")
    window = getattr(model_client, "current_window_id", None)
    window_id = window() if callable(window) else None
    return current(window_id, metadata)


def _service_tier_for_remote_compaction(sess: Any, turn_context: Any) -> Any:
    auth = _field(_field(sess, "services"), "auth_manager")
    auth_mode = getattr(auth, "auth_mode", None)
    mode = auth_mode() if callable(auth_mode) else None
    if str(mode).lower().endswith("apikey") or str(mode).lower() == "api_key":
        return None
    return _field(_field(turn_context, "config"), "service_tier")


def _compaction_trace(sess: Any, turn_context: Any) -> Any:
    trace = _field(_field(sess, "services"), "rollout_thread_trace")
    context = getattr(trace, "compaction_trace_context", None)
    if callable(context):
        return context(
            str(_field(turn_context, "sub_id", "")),
            "",
            str(_field(_field(turn_context, "model_info"), "slug", "")),
            str(_field(_provider_info(turn_context), "name", "")),
        )
    return None


def _provider_info(turn_context: Any) -> Any:
    provider = _field(turn_context, "provider")
    info = getattr(provider, "info", None)
    return info() if callable(info) else info if info is not None else provider


async def _build_initial_context(sess: Any, turn_context: Any) -> list[ResponseItem]:
    builder = getattr(sess, "build_initial_context", None)
    if not callable(builder):
        raise TypeError("remote compaction requires session.build_initial_context()")
    return list(await _maybe_await(builder(turn_context)))


async def _run_compact_hook(sess: Any, turn_context: Any, name: str, trigger: Any) -> Any:
    hook = getattr(sess, name, None)
    if callable(hook):
        return await _maybe_await(hook(turn_context, trigger))
    hooks = _field(_field(sess, "services"), "hook_runtime")
    hook = getattr(hooks, name, None)
    if callable(hook):
        return await _maybe_await(hook(sess, turn_context, trigger))
    return "continue"


def _hook_stopped(outcome: Any) -> bool:
    if outcome is None:
        return False
    if isinstance(outcome, str):
        return outcome.lower() in {"stopped", "stop"}
    return str(_field(outcome, "type", _field(outcome, "kind", ""))).lower() in {"stopped", "stop"}


def _hook_reason(outcome: Any) -> str | None:
    reason = _field(outcome, "reason")
    return reason if isinstance(reason, str) else None


async def _send_event(sess: Any, turn_context: Any, event: EventMsg) -> None:
    await _call_required(sess, "send_event", turn_context, event)


async def _send_error(sess: Any, turn_context: Any, exc: Exception) -> None:
    to_error_event = getattr(exc, "to_error_event", None)
    if callable(to_error_event):
        await _send_event(sess, turn_context, EventMsg.with_payload("error", to_error_event("Error running remote compact task")))


async def _call_required(target: Any, name: str, *args: Any) -> Any:
    method = getattr(target, name, None)
    if not callable(method):
        raise TypeError(f"remote compaction requires {name}()")
    return await _maybe_await(method(*args))


async def _started_at(turn_context: Any) -> int | None:
    timing = _field(turn_context, "turn_timing_state")
    getter = getattr(timing, "started_at_unix_secs", None)
    if callable(getter):
        return await _maybe_await(getter())
    return None


def _model_context_window(turn_context: Any) -> int | None:
    getter = getattr(turn_context, "model_context_window", None)
    return getter() if callable(getter) else _field(turn_context, "model_context_window_value")


def _collaboration_mode_kind(turn_context: Any) -> Any:
    return _field(_field(turn_context, "collaboration_mode"), "mode")


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _field(value: Any, name: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "CompactRequestLogData",
    "IMAGE_CONTENT_OMITTED_PLACEHOLDER",
    "RemoteCompactionInstallPlan",
    "RemoteCompactFailureLogData",
    "TrimFunctionCallHistoryResult",
    "apply_remote_compaction_install_plan",
    "build_compact_request_log_data",
    "build_remote_compact_failure_log_data",
    "build_remote_compaction_install_plan",
    "build_remote_compaction_success_plan",
    "ensure_call_outputs_present",
    "estimate_response_item_model_visible_bytes",
    "is_codex_generated_item",
    "log_remote_compact_failure",
    "log_remote_compaction_request_failure",
    "normalize_call_outputs",
    "normalize_history_for_prompt",
    "process_compacted_history",
    "remove_orphan_outputs",
    "run_inline_remote_auto_compact_task",
    "run_remote_compact_task",
    "run_remote_compact_task_inner",
    "run_remote_compact_task_inner_impl",
    "run_remote_compaction_request",
    "should_keep_compacted_history_item",
    "strip_images_when_unsupported",
    "trim_function_call_history_to_fit_context_window",
]
