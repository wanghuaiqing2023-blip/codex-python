"""Pure helpers for remote compaction v2.

Ported from the standalone retained-history helpers in
``codex/codex-rs/core/src/compact_remote_v2.rs``. The async model request,
hook, session, tracing, and websocket retry orchestration remain outside this
stdlib-only slice.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from typing import Any, Sequence

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
)
from pycodex.core.compact_remote import process_compacted_history
from pycodex.core.compact_remote import should_keep_compacted_history_item
from pycodex.core.compact_remote import build_compact_request_log_data, log_remote_compact_failure
from pycodex.core.compact_remote import trim_function_call_history_to_fit_context_window
from pycodex.core.turn_metadata import CompactionTurnMetadata
from pycodex.features import Feature
from pycodex.core.responses_retry import ResponsesStreamRequest, RetryableResponseStreamDecision, response_stream_retry_decision
from pycodex.utils.string import approx_token_count
from pycodex.core.tools.context import truncate_text
from pycodex.protocol import (
    BaseInstructions,
    CodexErr,
    CompactedItem,
    ContentItem,
    ContextCompactionItem,
    EventMsg,
    Personality,
    ResponseItem,
    TruncationPolicyConfig,
    TurnContextItem,
    TurnItem,
    TurnStartedEvent,
)


RETAINED_MESSAGE_TOKEN_BUDGET = 64_000
MAX_REMOTE_COMPACTION_V2_STREAM_RETRIES = 2


class RemoteCompactionV2StreamError(RuntimeError):
    """Remote compaction v2 stream closed before a completed response."""


class RemoteCompactionV2OutputError(RuntimeError):
    """Remote compaction v2 produced the wrong number of compaction outputs."""


async def run_inline_remote_auto_compact_task(
    sess: Any,
    turn_context: Any,
    client_session: Any,
    initial_context_injection: InitialContextInjection,
    reason: CompactionReason | str = CompactionReason.CONTEXT_LIMIT,
    phase: CompactionPhase | str = CompactionPhase.MID_TURN,
) -> None:
    await run_remote_compact_task_inner(
        sess,
        turn_context,
        client_session,
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
        None,
        InitialContextInjection.DO_NOT_INJECT,
        CompactionTrigger.MANUAL,
        CompactionReason.USER_REQUESTED,
        CompactionPhase.STANDALONE_TURN,
    )


async def run_remote_compact_task_inner(
    sess: Any,
    turn_context: Any,
    client_session: Any | None,
    initial_context_injection: InitialContextInjection | str,
    trigger: CompactionTrigger | str,
    reason: CompactionReason | str,
    phase: CompactionPhase | str,
) -> None:
    metadata = CompactionTurnMetadata(
        trigger=_enum_value(trigger),
        reason=_enum_value(reason),
        implementation="responses_compaction_v2",
        phase=_enum_value(phase),
        strategy=COMPACTION_STRATEGY_MEMENTO,
    )
    attempt = await CompactionAnalyticsAttempt.begin(
        sess,
        turn_context,
        trigger,
        reason,
        "responses_compaction_v2",
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
            client_session,
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
    client_session: Any | None,
    initial_context_injection: InitialContextInjection,
    compaction_metadata: CompactionTurnMetadata,
) -> None:
    context_compaction_item = ContextCompactionItem.new()
    compaction_item = TurnItem.context_compaction(context_compaction_item)
    await _call_required(sess, "emit_turn_item_started", turn_context, compaction_item)

    history = await _clone_history(sess)
    base_instructions = await _base_instructions(sess)
    trimmer = globals().get("trim_function_call_history_to_fit_context_window")
    if callable(trimmer):
        result = trimmer(history, turn_context, base_instructions)
        if hasattr(result, "items"):
            history = list(result.items)

    trace_input_history = list(_history_raw_items(history))
    prompt_input = _history_for_prompt(history, _input_modalities(turn_context))
    tool_router = await _built_tools(sess, turn_context)
    prompt = build_remote_compaction_v2_prompt(
        prompt_input,
        _model_visible_specs(tool_router),
        parallel_tool_calls=bool(_field(_field(turn_context, "model_info"), "supports_parallel_tool_calls", False)),
        base_instructions=base_instructions,
        personality=_field(turn_context, "personality"),
    )
    header = _compaction_metadata_header(sess, turn_context, compaction_metadata)
    client_session = client_session or _new_model_client_session(sess)
    compaction_output, response_id = await run_remote_compaction_request_v2(
        sess,
        turn_context,
        client_session,
        prompt,
        header,
    )
    compacted_history = build_v2_compacted_history(prompt_input, compaction_output)
    initial_context: Sequence[ResponseItem] = ()
    reference_context_item = None
    if initial_context_injection is InitialContextInjection.BEFORE_LAST_USER_MESSAGE:
        initial_context = await _build_initial_context(sess, turn_context)
        to_context_item = getattr(turn_context, "to_turn_context_item", None)
        if callable(to_context_item):
            reference_context_item = to_context_item()
    plan = build_remote_compaction_v2_success_plan(
        trace_input_history,
        compacted_history,
        initial_context_injection,
        initial_context,
        reference_context_item,
    )
    await apply_remote_compaction_v2_install_plan(sess, plan)
    await _call_required(sess, "recompute_token_usage", turn_context)
    await _call_required(sess, "emit_turn_item_completed", turn_context, compaction_item)
    if response_processed_request_for_remote_compaction_v2(_field(turn_context, "features"), response_id):
        sender = getattr(client_session, "send_response_processed", None)
        if callable(sender):
            await _maybe_await(sender(response_id))


async def run_remote_compaction_request_v2(
    sess: Any,
    turn_context: Any,
    client_session: Any,
    prompt: Prompt,
    turn_metadata_header: str | None,
) -> tuple[ResponseItem, str]:
    max_retries = remote_compaction_v2_max_stream_retries(_provider_info(turn_context))
    retries = 0
    while True:
        try:
            stream = await _stream_compaction_request(client_session, turn_context, prompt, turn_metadata_header)
            return await collect_compaction_output_async(stream)
        except Exception as exc:
            if not _is_retryable(exc):
                await log_remote_compaction_request_failure(sess, turn_context, prompt, exc)
                raise
            if retries >= max_retries:
                await log_remote_compaction_request_failure(sess, turn_context, prompt, exc)
                raise
            retries += 1
            retry_handler = getattr(client_session, "handle_retryable_response_stream_error", None)
            if callable(retry_handler):
                await _maybe_await(retry_handler(retries, max_retries, exc, ResponsesStreamRequest.REMOTE_COMPACTION_V2))
            else:
                await asyncio.sleep(min(0.1 * (2 ** (retries - 1)), 2.0))


async def collect_compaction_output_async(stream: Any) -> tuple[ResponseItem, str]:
    events: list[Any] = []
    async for event in _aiter_stream(stream):
        events.append(_normalize_stream_event(event))
        if _event_type(events[-1]) == "completed":
            break
    return collect_compaction_output(events)


async def log_remote_compaction_request_failure(sess: Any, turn_context: Any, prompt: Prompt, err: Exception) -> None:
    breakdown_getter = getattr(sess, "get_total_token_usage_breakdown", None)
    breakdown = await _maybe_await(breakdown_getter()) if callable(breakdown_getter) else None
    data = build_compact_request_log_data(prompt.input, prompt.base_instructions.text)
    logger = globals().get("log_remote_compact_failure")
    if callable(logger):
        logger(turn_context, data, breakdown, err)


@dataclass(frozen=True)
class RemoteCompactionV2InstallPlan:
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


@dataclass(frozen=True)
class RemoteCompactionV2RequestOutcome:
    action: str
    result: tuple[ResponseItem, str] | None = None
    retry_decision: RetryableResponseStreamDecision | None = None
    error: CodexErr | None = None

    def __post_init__(self) -> None:
        if self.action not in {"success", "retry_or_fallback", "fail"}:
            raise ValueError("unsupported remote compaction v2 request outcome action")
        if self.action == "success":
            if not _is_compaction_result(self.result):
                raise TypeError("success outcome requires a (ResponseItem, response_id) result")
            if self.retry_decision is not None or self.error is not None:
                raise ValueError("success outcome must not include retry_decision or error")
        elif self.action == "retry_or_fallback":
            if not isinstance(self.retry_decision, RetryableResponseStreamDecision):
                raise TypeError("retry_or_fallback outcome requires a retry_decision")
            if self.result is not None or self.error is not None:
                raise ValueError("retry_or_fallback outcome must not include result or error")
        else:
            if not isinstance(self.error, CodexErr):
                raise TypeError("fail outcome requires a CodexErr error")
            if self.result is not None or self.retry_decision is not None:
                raise ValueError("fail outcome must not include result or retry_decision")


def build_remote_compaction_v2_prompt(
    prompt_input: Sequence[ResponseItem],
    tools: Sequence[Any],
    *,
    parallel_tool_calls: bool,
    base_instructions: BaseInstructions,
    personality: Personality | None = None,
) -> Prompt:
    input_items = _response_items(prompt_input, "prompt_input")
    input_items.append(ResponseItem.compaction_trigger())
    if isinstance(tools, (str, bytes)) or not isinstance(tools, Sequence):
        raise TypeError("tools must be a sequence")
    return Prompt(
        input=input_items,
        tools=list(tools),
        parallel_tool_calls=parallel_tool_calls,
        base_instructions=base_instructions,
        personality=personality,
        output_schema=None,
        output_schema_strict=True,
    )


def remote_compaction_v2_trace_attempt_payload(model: str, prompt: Prompt) -> dict[str, Any]:
    if not isinstance(model, str):
        raise TypeError("model must be a string")
    if not isinstance(prompt, Prompt):
        raise TypeError("prompt must be a Prompt")
    return {
        "model": model,
        "instructions": prompt.base_instructions.text,
        "input": [item.to_mapping() for item in prompt.input],
        "parallel_tool_calls": prompt.parallel_tool_calls,
    }


def collect_compaction_output(events: Sequence[Any]) -> tuple[ResponseItem, str]:
    output_item_count = 0
    compaction_count = 0
    compaction_output: ResponseItem | None = None
    completed_response_id: str | None = None
    for event in events:
        if isinstance(event, CodexErr):
            raise event
        event_type = _event_type(event)
        if event_type == "output_item_done":
            output_item_count += 1
            item = _event_item(event)
            if item.type == "compaction":
                compaction_count += 1
                if compaction_output is None:
                    compaction_output = item
        elif event_type == "completed":
            completed_response_id = _event_response_id(event)
            break

    if completed_response_id is None:
        raise CodexErr.stream(
            "remote compaction v2 stream closed before response.completed"
        )
    if compaction_count != 1:
        raise CodexErr.fatal(
            "remote compaction v2 expected exactly one compaction output item, "
            f"got {compaction_count} from {output_item_count} output items"
        )
    if compaction_output is None:
        raise CodexErr.fatal("compaction output missing")
    return compaction_output, completed_response_id


def response_processed_request_for_remote_compaction_v2(features: Any, response_id: str) -> dict[str, str] | None:
    if not isinstance(response_id, str):
        raise TypeError("response_id must be a string")
    enabled = getattr(features, "enabled", None)
    if not callable(enabled):
        raise TypeError("features must expose enabled(feature)")
    if not enabled(Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED):
        return None
    return {"type": "response.processed", "response_id": response_id}


def remote_compaction_v2_max_stream_retries(provider_info: Any) -> int:
    method = getattr(provider_info, "stream_max_retries", None)
    if not callable(method):
        raise TypeError("provider_info must expose stream_max_retries()")
    value = method()
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("stream_max_retries() must return an integer")
    if value < 0:
        raise ValueError("stream_max_retries() must be non-negative")
    return min(value, MAX_REMOTE_COMPACTION_V2_STREAM_RETRIES)


def remote_compaction_v2_retry_decision(
    *,
    retries: int,
    provider_info: Any,
    err: Any,
    fallback_transport_available: bool,
    responses_websocket_enabled: bool,
    debug_assertions: bool = __debug__,
) -> RetryableResponseStreamDecision:
    return response_stream_retry_decision(
        retries=retries,
        max_retries=remote_compaction_v2_max_stream_retries(provider_info),
        err=err,
        request=ResponsesStreamRequest.REMOTE_COMPACTION_V2,
        fallback_transport_available=fallback_transport_available,
        responses_websocket_enabled=responses_websocket_enabled,
        debug_assertions=debug_assertions,
    )


def remote_compaction_v2_request_outcome(
    result: tuple[ResponseItem, str] | CodexErr,
    *,
    retries: int,
    provider_info: Any,
    fallback_transport_available: bool,
    responses_websocket_enabled: bool,
    debug_assertions: bool = __debug__,
) -> RemoteCompactionV2RequestOutcome:
    if _is_compaction_result(result):
        return RemoteCompactionV2RequestOutcome(action="success", result=result)
    if not isinstance(result, CodexErr):
        raise TypeError("result must be a compaction result tuple or CodexErr")
    if not result.is_retryable():
        return RemoteCompactionV2RequestOutcome(action="fail", error=result)
    decision = remote_compaction_v2_retry_decision(
        retries=retries,
        provider_info=provider_info,
        err=result,
        fallback_transport_available=fallback_transport_available,
        responses_websocket_enabled=responses_websocket_enabled,
        debug_assertions=debug_assertions,
    )
    return RemoteCompactionV2RequestOutcome(action="retry_or_fallback", retry_decision=decision)


def build_remote_compaction_v2_install_plan(
    trace_input_history: Sequence[ResponseItem],
    new_history: Sequence[ResponseItem],
    initial_context_injection: InitialContextInjection,
    reference_context_item: TurnContextItem | None = None,
) -> RemoteCompactionV2InstallPlan:
    trace_items = _response_items(trace_input_history, "trace_input_history")
    replacement_history = _response_items(new_history, "new_history")
    injection = InitialContextInjection(initial_context_injection)
    if injection is InitialContextInjection.BEFORE_LAST_USER_MESSAGE:
        if not isinstance(reference_context_item, TurnContextItem):
            raise TypeError("reference_context_item must be provided for before-last-user-message injection")
    else:
        reference_context_item = None
    replacement_history_json = tuple(item.to_mapping() for item in replacement_history)
    return RemoteCompactionV2InstallPlan(
        new_history=tuple(replacement_history),
        reference_context_item=reference_context_item,
        compacted_item=CompactedItem(message="", replacement_history=replacement_history_json),
        checkpoint_payload={
            "input_history": [item.to_mapping() for item in trace_items],
            "replacement_history": [item.to_mapping() for item in replacement_history],
        },
    )


async def apply_remote_compaction_v2_install_plan(session: Any, plan: RemoteCompactionV2InstallPlan) -> None:
    if not isinstance(plan, RemoteCompactionV2InstallPlan):
        raise TypeError("plan must be a RemoteCompactionV2InstallPlan")
    replace = getattr(session, "replace_compacted_history", None)
    if not callable(replace):
        raise TypeError("session must expose replace_compacted_history")
    result = replace(plan.new_history, plan.reference_context_item, plan.compacted_item)
    if inspect.isawaitable(result):
        await result


def build_remote_compaction_v2_success_plan(
    trace_input_history: Sequence[ResponseItem],
    prompt_input: Sequence[ResponseItem],
    compaction_output: ResponseItem,
    initial_context_injection: InitialContextInjection,
    initial_context: Sequence[ResponseItem] = (),
    reference_context_item: TurnContextItem | None = None,
) -> RemoteCompactionV2InstallPlan:
    compacted_history = build_v2_compacted_history(prompt_input, compaction_output)
    new_history = process_compacted_history(
        compacted_history,
        initial_context_injection,
        initial_context,
    )
    return build_remote_compaction_v2_install_plan(
        trace_input_history,
        new_history,
        initial_context_injection,
        reference_context_item,
    )


def build_v2_compacted_history(
    prompt_input: Sequence[ResponseItem],
    compaction_output: ResponseItem,
) -> list[ResponseItem]:
    if not isinstance(compaction_output, ResponseItem):
        raise TypeError("compaction_output must be a ResponseItem")
    retained = [
        item
        for item in _response_items(prompt_input, "prompt_input")
        if is_retained_for_remote_compaction_v2(item)
        and should_keep_compacted_history_item(item)
    ]
    truncated = truncate_retained_messages_for_remote_compaction(
        retained,
        RETAINED_MESSAGE_TOKEN_BUDGET,
    )
    truncated.append(compaction_output)
    return truncated


def is_retained_for_remote_compaction_v2(item: ResponseItem) -> bool:
    if not isinstance(item, ResponseItem):
        raise TypeError("item must be a ResponseItem")
    return item.type == "message" and item.role in {"user", "developer", "system"}


def truncate_retained_messages_for_remote_compaction(
    items: Sequence[ResponseItem],
    max_tokens: int,
) -> list[ResponseItem]:
    max_tokens = _usize(max_tokens, "max_tokens")
    remaining = max_tokens
    truncated_reversed: list[ResponseItem] = []
    for item in reversed(_response_items(items, "items")):
        if remaining == 0:
            continue
        token_count = max(message_text_token_count(item), 1)
        if token_count <= remaining:
            truncated_reversed.append(item)
            remaining = max(remaining - token_count, 0)
        else:
            truncated_item = truncate_message_text_to_token_budget(item, remaining)
            if truncated_item is not None:
                truncated_reversed.append(truncated_item)
                remaining = 0
    truncated_reversed.reverse()
    return truncated_reversed


def message_text_token_count(item: ResponseItem) -> int:
    if not isinstance(item, ResponseItem):
        raise TypeError("item must be a ResponseItem")
    if item.type != "message":
        return 0
    total = 0
    for content_item in item.content:
        if content_item.type in {"input_text", "output_text"}:
            total += approx_token_count(content_item.text or "")
    return total


def truncate_message_text_to_token_budget(
    item: ResponseItem,
    max_tokens: int,
) -> ResponseItem | None:
    max_tokens = _usize(max_tokens, "max_tokens")
    if not isinstance(item, ResponseItem):
        raise TypeError("item must be a ResponseItem")
    if item.type != "message":
        return item

    remaining = max_tokens
    truncated_content: list[ContentItem] = []
    for content_item in item.content:
        if content_item.type in {"input_text", "output_text"}:
            if remaining == 0:
                continue
            text = content_item.text or ""
            token_count = approx_token_count(text)
            if token_count <= remaining:
                remaining = max(remaining - token_count, 0)
            else:
                text = truncate_text(text, TruncationPolicyConfig.tokens(remaining))
                remaining = 0
            if text:
                truncated_content.append(_text_content_item(content_item, text))
        elif content_item.type == "input_image":
            truncated_content.append(content_item)

    if not truncated_content:
        return None
    return ResponseItem.message(
        item.role or "",
        tuple(truncated_content),
        id=item.id,
        phase=item.phase,
    )


def _text_content_item(item: ContentItem, text: str) -> ContentItem:
    if item.type == "input_text":
        return ContentItem.input_text(text)
    if item.type == "output_text":
        return ContentItem.output_text(text)
    raise TypeError("item must be a text content item")


def _event_type(event: Any) -> str:
    if isinstance(event, dict):
        value = event.get("type")
    else:
        value = getattr(event, "type", None)
    if not isinstance(value, str):
        raise TypeError("event type must be a string")
    return value


def _event_item(event: Any) -> ResponseItem:
    if isinstance(event, dict):
        item = event.get("item")
    else:
        item = getattr(event, "item", None)
    if not isinstance(item, ResponseItem):
        raise TypeError("output_item_done event requires a ResponseItem item")
    return item


def _event_response_id(event: Any) -> str:
    if isinstance(event, dict):
        response_id = event.get("response_id")
    else:
        response_id = getattr(event, "response_id", None)
    if not isinstance(response_id, str):
        raise TypeError("completed event requires a string response_id")
    return response_id


def _is_compaction_result(value: Any) -> bool:
    return (
        isinstance(value, tuple)
        and len(value) == 2
        and isinstance(value[0], ResponseItem)
        and value[0].type == "compaction"
        and isinstance(value[1], str)
    )


def _response_items(value: Sequence[ResponseItem], label: str) -> list[ResponseItem]:
    if isinstance(value, ResponseItem) or isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence of ResponseItem")
    if not all(isinstance(item, ResponseItem) for item in value):
        raise TypeError(f"{label} must contain ResponseItem values")
    return list(value)


def _usize(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 0:
        raise ValueError(f"{label} must be non-negative")
    return value


async def _clone_history(sess: Any) -> Any:
    clone_history = getattr(sess, "clone_history", None)
    if not callable(clone_history):
        raise TypeError("remote compaction v2 requires session.clone_history()")
    return await _maybe_await(clone_history())


def _history_raw_items(history: Any) -> Sequence[ResponseItem]:
    raw_items = getattr(history, "raw_items", None)
    if callable(raw_items):
        return raw_items()
    if isinstance(history, Sequence):
        return history
    raise TypeError("remote compaction v2 history must expose raw_items()")


def _history_for_prompt(history: Any, input_modalities: Any) -> list[ResponseItem]:
    for_prompt = getattr(history, "for_prompt", None)
    if callable(for_prompt):
        return list(for_prompt(input_modalities))
    return list(_history_raw_items(history))


async def _base_instructions(sess: Any) -> BaseInstructions:
    getter = getattr(sess, "get_base_instructions", None)
    if not callable(getter):
        raise TypeError("remote compaction v2 requires session.get_base_instructions()")
    value = await _maybe_await(getter())
    if isinstance(value, BaseInstructions):
        return value
    if isinstance(value, str):
        return BaseInstructions(value)
    raise TypeError("session.get_base_instructions() must return BaseInstructions or str")


def _input_modalities(turn_context: Any) -> Any:
    return _field(_field(turn_context, "model_info"), "input_modalities")


async def _built_tools(sess: Any, turn_context: Any) -> Any:
    builder = getattr(sess, "built_tools", None)
    if callable(builder):
        return await _maybe_await(builder(turn_context))
    builder = getattr(turn_context, "built_tools", None)
    if callable(builder):
        return await _maybe_await(builder(sess))
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


def _new_model_client_session(sess: Any) -> Any:
    model_client = _field(_field(sess, "services"), "model_client")
    new_session = getattr(model_client, "new_session", None)
    if not callable(new_session):
        raise TypeError("remote compaction v2 requires services.model_client.new_session()")
    return new_session()


async def _build_initial_context(sess: Any, turn_context: Any) -> list[ResponseItem]:
    builder = getattr(sess, "build_initial_context", None)
    if not callable(builder):
        raise TypeError("remote compaction v2 requires session.build_initial_context()")
    return list(await _maybe_await(builder(turn_context)))


async def _stream_compaction_request(client_session: Any, turn_context: Any, prompt: Prompt, header: str | None) -> Any:
    stream = getattr(client_session, "stream", None)
    if not callable(stream):
        raise TypeError("remote compaction v2 requires client_session.stream()")
    return await _maybe_await(
        stream(
            prompt,
            _field(turn_context, "model_info"),
            _field(turn_context, "session_telemetry"),
            _field(turn_context, "reasoning_effort"),
            _field(turn_context, "reasoning_summary"),
            _field(_field(turn_context, "config"), "service_tier"),
            header,
        )
    )


async def _aiter_stream(stream: Any):
    if hasattr(stream, "__aiter__"):
        async for event in stream:
            yield event
        return
    while True:
        next_event = getattr(stream, "next", None)
        if not callable(next_event):
            raise TypeError("remote compaction v2 stream must be async iterable or expose next()")
        event = await _maybe_await(next_event())
        if event is None:
            return
        yield event


def _normalize_stream_event(event: Any) -> Any:
    if isinstance(event, tuple):
        return {"type": event[0], **({"item": event[1]} if len(event) > 1 and event[0] == "output_item_done" else {"response_id": event[1]} if len(event) > 1 and event[0] == "completed" else {})}
    kind = getattr(event, "type", None) or getattr(event, "kind", None)
    if kind in {"output_item_done", "OutputItemDone"}:
        return {"type": "output_item_done", "item": getattr(event, "item", getattr(event, "payload", None))}
    if kind in {"completed", "Completed"}:
        return {"type": "completed", "response_id": getattr(event, "response_id", _field(getattr(event, "payload", None), "response_id"))}
    return event


def _provider_info(turn_context: Any) -> Any:
    provider = _field(turn_context, "provider")
    info = getattr(provider, "info", None)
    return info() if callable(info) else info if info is not None else provider


def _is_retryable(exc: Exception) -> bool:
    retryable = getattr(exc, "is_retryable", None)
    if callable(retryable):
        return bool(retryable())
    return bool(getattr(exc, "retryable", False))


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
        raise TypeError(f"remote compaction v2 requires {name}()")
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
    "MAX_REMOTE_COMPACTION_V2_STREAM_RETRIES",
    "RETAINED_MESSAGE_TOKEN_BUDGET",
    "RemoteCompactionV2OutputError",
    "RemoteCompactionV2StreamError",
    "RemoteCompactionV2InstallPlan",
    "RemoteCompactionV2RequestOutcome",
    "apply_remote_compaction_v2_install_plan",
    "build_remote_compaction_v2_prompt",
    "build_remote_compaction_v2_install_plan",
    "build_remote_compaction_v2_success_plan",
    "build_v2_compacted_history",
    "collect_compaction_output",
    "collect_compaction_output_async",
    "is_retained_for_remote_compaction_v2",
    "log_remote_compaction_request_failure",
    "message_text_token_count",
    "remote_compaction_v2_max_stream_retries",
    "remote_compaction_v2_request_outcome",
    "remote_compaction_v2_retry_decision",
    "remote_compaction_v2_trace_attempt_payload",
    "response_processed_request_for_remote_compaction_v2",
    "run_inline_remote_auto_compact_task",
    "run_remote_compact_task",
    "run_remote_compact_task_inner",
    "run_remote_compact_task_inner_impl",
    "run_remote_compaction_request_v2",
    "truncate_message_text_to_token_budget",
    "truncate_retained_messages_for_remote_compaction",
]
