"""Pure compaction helpers.

Ported from the standalone helper portions of
``codex/codex-rs/core/src/compact.rs``.
"""

from __future__ import annotations

import asyncio
import inspect
from enum import Enum
from pathlib import Path
from typing import Any, Sequence

from pycodex.core.event_mapping import parse_turn_item
from pycodex.core.tools.context import truncate_text
from pycodex.core.turn_metadata import CompactionTurnMetadata
from pycodex.utils.string import approx_token_count
from pycodex.protocol import (
    CompactedItem,
    ContentItem,
    ContextCompactionItem,
    EventMsg,
    ResponseItem,
    TruncationPolicyConfig,
    TurnItem,
    TurnStartedEvent,
    UserInput,
    WarningEvent,
)

_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
_RUST_CORE_ROOT = _WORKSPACE_ROOT / "codex" / "codex-rs" / "core"


def _include_rust_str(relative_path: str) -> str:
    return (_RUST_CORE_ROOT / relative_path).read_text(encoding="utf-8")


SUMMARIZATION_PROMPT = _include_rust_str("templates/compact/prompt.md")
SUMMARY_PREFIX = _include_rust_str("templates/compact/summary_prefix.md")
COMPACT_USER_MESSAGE_MAX_TOKENS = 20_000


class InitialContextInjection(str, Enum):
    BEFORE_LAST_USER_MESSAGE = "before_last_user_message"
    DO_NOT_INJECT = "do_not_inject"


class CompactionStatus(str, Enum):
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


class CompactionTrigger(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"


class CompactionReason(str, Enum):
    CONTEXT_LIMIT = "context_limit"
    USER_REQUESTED = "user_requested"


class CompactionPhase(str, Enum):
    MID_TURN = "mid_turn"
    STANDALONE_TURN = "standalone_turn"


COMPACTION_IMPLEMENTATION_RESPONSES = "responses"
COMPACTION_STRATEGY_MEMENTO = "memento"


def should_use_remote_compact_task(provider: object) -> bool:
    method = getattr(provider, "supports_remote_compaction", None)
    if not callable(method):
        raise TypeError("provider must expose supports_remote_compaction()")
    result = method()
    if not isinstance(result, bool):
        raise TypeError("supports_remote_compaction() must return a bool")
    return result


def compaction_status_from_result(result: object) -> CompactionStatus:
    if isinstance(result, BaseException):
        kind = getattr(result, "kind", None)
        if kind in {"interrupted", "turn_aborted"}:
            return CompactionStatus.INTERRUPTED
        return CompactionStatus.FAILED
    return CompactionStatus.COMPLETED


async def run_inline_auto_compact_task(
    sess: Any,
    turn_context: Any,
    initial_context_injection: InitialContextInjection,
    reason: CompactionReason | str = CompactionReason.CONTEXT_LIMIT,
    phase: CompactionPhase | str = CompactionPhase.MID_TURN,
) -> None:
    prompt = _compact_prompt(turn_context)
    await run_compact_task_inner(
        sess,
        turn_context,
        [UserInput.text_input(prompt)],
        initial_context_injection,
        CompactionTrigger.AUTO,
        reason,
        phase,
    )


async def run_compact_task(
    sess: Any,
    turn_context: Any,
    input: Sequence[UserInput],
) -> None:
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
    await run_compact_task_inner(
        sess,
        turn_context,
        list(input),
        InitialContextInjection.DO_NOT_INJECT,
        CompactionTrigger.MANUAL,
        CompactionReason.USER_REQUESTED,
        CompactionPhase.STANDALONE_TURN,
    )


async def run_compact_task_inner(
    sess: Any,
    turn_context: Any,
    input: Sequence[UserInput],
    initial_context_injection: InitialContextInjection | str,
    trigger: CompactionTrigger | str,
    reason: CompactionReason | str,
    phase: CompactionPhase | str,
) -> str:
    metadata = CompactionTurnMetadata(
        trigger=_enum_value(trigger),
        reason=_enum_value(reason),
        implementation=COMPACTION_IMPLEMENTATION_RESPONSES,
        phase=_enum_value(phase),
        strategy=COMPACTION_STRATEGY_MEMENTO,
    )
    attempt = await CompactionAnalyticsAttempt.begin(
        sess,
        turn_context,
        trigger,
        reason,
        COMPACTION_IMPLEMENTATION_RESPONSES,
        phase,
    )
    pre = await _run_compact_hook(sess, turn_context, "run_pre_compact_hooks", trigger)
    if _hook_stopped(pre):
        error = _hook_reason(pre) or "PreCompact hook stopped execution"
        await attempt.track(sess, CompactionStatus.INTERRUPTED, error)
        raise RuntimeError(error)
    try:
        summary = await run_compact_task_inner_impl(
            sess,
            turn_context,
            list(input),
            InitialContextInjection(initial_context_injection),
            metadata,
        )
    except Exception as exc:
        await attempt.track(sess, compaction_status_from_result(exc), str(exc))
        raise
    post = await _run_compact_hook(sess, turn_context, "run_post_compact_hooks", trigger)
    if _hook_stopped(post):
        await attempt.track(sess, CompactionStatus.INTERRUPTED, "PostCompact hook stopped execution")
        raise RuntimeError("PostCompact hook stopped execution")
    await attempt.track(sess, CompactionStatus.COMPLETED, None)
    return summary


async def run_compact_task_inner_impl(
    sess: Any,
    turn_context: Any,
    input: Sequence[UserInput],
    initial_context_injection: InitialContextInjection,
    compaction_metadata: CompactionTurnMetadata,
) -> str:
    compaction_item = TurnItem.context_compaction(ContextCompactionItem.new())
    await _call_required(sess, "emit_turn_item_started", turn_context, compaction_item)

    history = await _clone_history(sess)
    _history_record_items(history, [_response_item_from_user_inputs(input)], _field(turn_context, "truncation_policy"))

    max_retries = _stream_max_retries(turn_context)
    retries = 0
    client_session = _new_model_client_session(sess)
    while True:
        turn_input = _history_for_prompt(history, _input_modalities(turn_context))
        turn_input_len = len(turn_input)
        prompt = {
            "input": turn_input,
            "base_instructions": await _base_instructions(sess),
            "personality": _field(turn_context, "personality"),
        }
        header = _compaction_metadata_header(sess, turn_context, compaction_metadata)
        try:
            await drain_to_completed(sess, turn_context, client_session, header, prompt)
            break
        except Exception as exc:
            if _error_kind(exc) == "interrupted":
                raise
            if _error_kind(exc) == "context_window_exceeded" and turn_input_len > 1:
                _history_remove_first_item(history)
                retries = 0
                continue
            if retries < max_retries:
                retries += 1
                notifier = getattr(sess, "notify_stream_error", None)
                if callable(notifier):
                    await _maybe_await(notifier(turn_context, f"Reconnecting... {retries}/{max_retries}", exc))
                await asyncio.sleep(_backoff_delay(retries))
                continue
            await _send_error(sess, turn_context, exc)
            raise

    history_snapshot = await _clone_history(sess)
    history_items = list(_history_raw_items(history_snapshot))
    summary_suffix = _last_assistant_message(history_items)
    summary_text = f"{SUMMARY_PREFIX}\n{summary_suffix}"
    user_messages = collect_user_messages(history_items)
    new_history = build_compacted_history([], user_messages, summary_text)

    reference_context_item = None
    if initial_context_injection is InitialContextInjection.BEFORE_LAST_USER_MESSAGE:
        initial_context = await _build_initial_context(sess, turn_context)
        new_history = insert_initial_context_before_last_real_user_or_summary(new_history, initial_context)
        to_context_item = getattr(turn_context, "to_turn_context_item", None)
        if callable(to_context_item):
            reference_context_item = to_context_item()

    compacted_item = CompactedItem(
        message=summary_text,
        replacement_history=tuple(_response_item_json(item) for item in new_history),
    )
    await _call_required(sess, "replace_compacted_history", new_history, reference_context_item, compacted_item)
    await _call_required(sess, "recompute_token_usage", turn_context)
    await _call_required(sess, "emit_turn_item_completed", turn_context, compaction_item)
    await _send_event(
        sess,
        turn_context,
        EventMsg.with_payload(
            "warning",
            WarningEvent(
                "Heads up: Long threads and multiple compactions can cause the model to be less accurate. Start a new thread when possible to keep threads small and targeted."
            ),
        ),
    )
    return summary_suffix


async def drain_to_completed(
    sess: Any,
    turn_context: Any,
    client_session: Any,
    turn_metadata_header: str | None,
    prompt: Any,
) -> None:
    stream_method = getattr(client_session, "stream", None)
    if not callable(stream_method):
        raise TypeError("compact client session must expose stream()")
    stream = await _maybe_await(
        stream_method(
            prompt,
            _field(turn_context, "model_info"),
            _field(turn_context, "session_telemetry"),
            _field(turn_context, "reasoning_effort"),
            _field(turn_context, "reasoning_summary"),
            _field(_field(turn_context, "config"), "service_tier"),
            turn_metadata_header,
        )
    )
    async for event in _aiter_stream(stream):
        kind = _event_kind(event)
        payload = _event_payload(event)
        if kind in {"output_item_done", "OutputItemDone"}:
            item = payload if isinstance(payload, ResponseItem) else _field(payload, "item", payload)
            await _call_required(sess, "record_conversation_items", turn_context, [item])
        elif kind in {"server_reasoning_included", "ServerReasoningIncluded"}:
            await _call_required(sess, "set_server_reasoning_included", bool(_field(payload, "included", payload)))
        elif kind in {"rate_limits", "RateLimits"}:
            await _call_optional(sess, "update_rate_limits", turn_context, payload)
        elif kind in {"completed", "Completed"}:
            usage = _field(payload, "token_usage", _field(payload, "usage"))
            await _call_optional(sess, "update_token_usage_info", turn_context, usage)
            return
        elif kind in {"error", "Error"}:
            raise RuntimeError(str(payload))
    raise RuntimeError("stream closed before response.completed")


def content_items_to_text(content: Sequence[ContentItem]) -> str | None:
    if isinstance(content, ContentItem) or not isinstance(content, Sequence):
        raise TypeError("content must be a sequence of ContentItem")
    pieces: list[str] = []
    for item in content:
        if not isinstance(item, ContentItem):
            raise TypeError("content must contain ContentItem values")
        if item.type in {"input_text", "output_text"} and item.text:
            pieces.append(item.text)
    return "\n".join(pieces) if pieces else None


def collect_user_messages(items: Sequence[ResponseItem]) -> list[str]:
    if isinstance(items, ResponseItem) or not isinstance(items, Sequence):
        raise TypeError("items must be a sequence of ResponseItem")
    collected: list[str] = []
    for item in items:
        if not isinstance(item, ResponseItem):
            raise TypeError("items must contain ResponseItem values")
        turn_item = parse_turn_item(item)
        if turn_item is None or turn_item.type != "UserMessage":
            continue
        message = turn_item.item.message()
        if not is_summary_message(message):
            collected.append(message)
    return collected


def is_summary_message(message: str) -> bool:
    if not isinstance(message, str):
        raise TypeError("message must be a string")
    return message.startswith(f"{SUMMARY_PREFIX}\n")


def insert_initial_context_before_last_real_user_or_summary(
    compacted_history: Sequence[ResponseItem],
    initial_context: Sequence[ResponseItem],
) -> list[ResponseItem]:
    history = _response_items(compacted_history, "compacted_history")
    context = _response_items(initial_context, "initial_context")

    last_user_or_summary_index: int | None = None
    last_real_user_index: int | None = None
    for index in range(len(history) - 1, -1, -1):
        turn_item = parse_turn_item(history[index])
        if turn_item is None or turn_item.type != "UserMessage":
            continue
        if last_user_or_summary_index is None:
            last_user_or_summary_index = index
        if not is_summary_message(turn_item.item.message()):
            last_real_user_index = index
            break

    last_compaction_index = None
    for index in range(len(history) - 1, -1, -1):
        if history[index].type in {"compaction", "context_compaction"}:
            last_compaction_index = index
            break

    insertion_index = (
        last_real_user_index
        if last_real_user_index is not None
        else last_user_or_summary_index
        if last_user_or_summary_index is not None
        else last_compaction_index
    )
    if insertion_index is None:
        return [*history, *context]
    return [*history[:insertion_index], *context, *history[insertion_index:]]


def build_compacted_history(
    initial_context: Sequence[ResponseItem],
    user_messages: Sequence[str],
    summary_text: str,
) -> list[ResponseItem]:
    return build_compacted_history_with_limit(
        initial_context,
        user_messages,
        summary_text,
        COMPACT_USER_MESSAGE_MAX_TOKENS,
    )


def build_compacted_history_with_limit(
    initial_context: Sequence[ResponseItem],
    user_messages: Sequence[str],
    summary_text: str,
    max_tokens: int,
) -> list[ResponseItem]:
    history = _response_items(initial_context, "initial_context")
    messages = _string_sequence(user_messages, "user_messages")
    if not isinstance(summary_text, str):
        raise TypeError("summary_text must be a string")
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int):
        raise TypeError("max_tokens must be an integer")
    if max_tokens < 0:
        raise ValueError("max_tokens must be non-negative")

    selected_messages: list[str] = []
    if max_tokens > 0:
        remaining = max_tokens
        for message in reversed(messages):
            if remaining == 0:
                break
            tokens = approx_token_count(message)
            if tokens <= remaining:
                selected_messages.append(message)
                remaining = max(remaining - tokens, 0)
            else:
                selected_messages.append(truncate_text(message, TruncationPolicyConfig.tokens(remaining)))
                break
        selected_messages.reverse()

    for message in selected_messages:
        history.append(_user_message_response_item(message))
    history.append(_user_message_response_item(summary_text if summary_text else "(no summary available)"))
    return history


def _user_message_response_item(text: str) -> ResponseItem:
    return ResponseItem.message("user", (ContentItem.input_text(text),))


def _response_items(value: Sequence[ResponseItem], label: str) -> list[ResponseItem]:
    if isinstance(value, ResponseItem) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence of ResponseItem")
    if not all(isinstance(item, ResponseItem) for item in value):
        raise TypeError(f"{label} must contain ResponseItem values")
    return list(value)


def _string_sequence(value: Sequence[str], label: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence of strings")
    if not all(isinstance(item, str) for item in value):
        raise TypeError(f"{label} must be a sequence of strings")
    return tuple(value)


class CompactionAnalyticsAttempt:
    def __init__(
        self,
        thread_id: str,
        turn_id: str,
        trigger: Any,
        reason: Any,
        implementation: str,
        phase: Any,
        active_context_tokens_before: int,
    ) -> None:
        self.thread_id = thread_id
        self.turn_id = turn_id
        self.trigger = _enum_value(trigger)
        self.reason = _enum_value(reason)
        self.implementation = implementation
        self.phase = _enum_value(phase)
        self.active_context_tokens_before = int(active_context_tokens_before)

    @classmethod
    async def begin(
        cls,
        sess: Any,
        turn_context: Any,
        trigger: Any,
        reason: Any,
        implementation: str,
        phase: Any,
    ) -> "CompactionAnalyticsAttempt":
        return cls(
            thread_id=str(_field(sess, "conversation_id", "")),
            turn_id=str(_field(turn_context, "sub_id", "")),
            trigger=trigger,
            reason=reason,
            implementation=implementation,
            phase=phase,
            active_context_tokens_before=await _total_token_usage(sess),
        )

    async def track(self, sess: Any, status: CompactionStatus, error: str | None) -> None:
        analytics = _field(_field(sess, "services"), "analytics_events_client")
        tracker = getattr(analytics, "track_compaction", None)
        if callable(tracker):
            await _maybe_await(
                tracker(
                    {
                        "thread_id": self.thread_id,
                        "turn_id": self.turn_id,
                        "trigger": self.trigger,
                        "reason": self.reason,
                        "implementation": self.implementation,
                        "phase": self.phase,
                        "strategy": COMPACTION_STRATEGY_MEMENTO,
                        "status": status.value,
                        "error": error,
                        "active_context_tokens_before": self.active_context_tokens_before,
                        "active_context_tokens_after": await _total_token_usage(sess),
                    }
                )
            )


async def _clone_history(sess: Any) -> Any:
    clone_history = getattr(sess, "clone_history", None)
    if not callable(clone_history):
        raise TypeError("compact runtime requires session.clone_history()")
    return await _maybe_await(clone_history())


def _history_record_items(history: Any, items: Sequence[Any], truncation_policy: Any) -> None:
    recorder = getattr(history, "record_items", None)
    if callable(recorder):
        recorder(list(items), truncation_policy)
    elif isinstance(history, list):
        history.extend(items)
    else:
        raise TypeError("compact history must expose record_items()")


def _history_for_prompt(history: Any, input_modalities: Any) -> list[Any]:
    for_prompt = getattr(history, "for_prompt", None)
    if callable(for_prompt):
        return list(for_prompt(input_modalities))
    raw_items = getattr(history, "raw_items", None)
    if callable(raw_items):
        return list(raw_items())
    if isinstance(history, list):
        return list(history)
    raise TypeError("compact history must expose for_prompt() or raw_items()")


def _history_raw_items(history: Any) -> Sequence[ResponseItem]:
    raw_items = getattr(history, "raw_items", None)
    if callable(raw_items):
        return raw_items()
    if isinstance(history, Sequence):
        return history
    raise TypeError("compact history must expose raw_items()")


def _history_remove_first_item(history: Any) -> None:
    remover = getattr(history, "remove_first_item", None)
    if callable(remover):
        remover()
    elif isinstance(history, list) and history:
        history.pop(0)
    else:
        raise TypeError("compact history must expose remove_first_item()")


def _new_model_client_session(sess: Any) -> Any:
    model_client = _field(_field(sess, "services"), "model_client")
    new_session = getattr(model_client, "new_session", None)
    if not callable(new_session):
        raise TypeError("compact runtime requires services.model_client.new_session()")
    return new_session()


def _compaction_metadata_header(sess: Any, turn_context: Any, metadata: CompactionTurnMetadata) -> str | None:
    state = _field(turn_context, "turn_metadata_state")
    current = getattr(state, "current_header_value_for_compaction", None)
    if not callable(current):
        return None
    model_client = _field(_field(sess, "services"), "model_client")
    window = getattr(model_client, "current_window_id", None)
    window_id = window() if callable(window) else None
    return current(window_id, metadata)


async def _base_instructions(sess: Any) -> str | None:
    getter = getattr(sess, "get_base_instructions", None)
    if callable(getter):
        return await _maybe_await(getter())
    return None


def _input_modalities(turn_context: Any) -> Any:
    return _field(_field(turn_context, "model_info"), "input_modalities")


def _stream_max_retries(turn_context: Any) -> int:
    provider_info = _field(_field(turn_context, "provider"), "info")
    if callable(provider_info):
        provider_info = provider_info()
    getter = getattr(provider_info, "stream_max_retries", None)
    if callable(getter):
        return int(getter())
    return int(_field(provider_info, "stream_max_retries", 0) or 0)


def _compact_prompt(turn_context: Any) -> str:
    prompt = getattr(turn_context, "compact_prompt", None)
    value = prompt() if callable(prompt) else prompt
    if not isinstance(value, str):
        raise TypeError("turn_context.compact_prompt must be a string or callable returning a string")
    return value


async def _build_initial_context(sess: Any, turn_context: Any) -> list[ResponseItem]:
    builder = getattr(sess, "build_initial_context", None)
    if not callable(builder):
        raise TypeError("compact runtime requires session.build_initial_context()")
    return list(await _maybe_await(builder(turn_context)))


def _response_item_from_user_inputs(input: Sequence[UserInput]) -> ResponseItem:
    text_parts: list[str] = []
    for item in input:
        text = getattr(item, "text", None)
        if text is None:
            text = getattr(item, "content", None)
        if isinstance(text, str) and text:
            text_parts.append(text)
    return ResponseItem.message("user", (ContentItem.input_text("\n".join(text_parts)),))


def _last_assistant_message(items: Sequence[ResponseItem]) -> str:
    for item in reversed(tuple(items)):
        if isinstance(item, ResponseItem) and item.type == "message" and item.role == "assistant":
            text = content_items_to_text(item.content)
            if text:
                return text
    return ""


def _response_item_json(item: ResponseItem) -> Any:
    mapper = getattr(item, "to_mapping", None)
    return mapper() if callable(mapper) else item


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


async def _aiter_stream(stream: Any):
    if hasattr(stream, "__aiter__"):
        async for event in stream:
            yield event
        return
    while True:
        next_event = getattr(stream, "next", None)
        if not callable(next_event):
            raise TypeError("compact stream must be async iterable or expose next()")
        event = await _maybe_await(next_event())
        if event is None:
            return
        yield event


def _event_kind(event: Any) -> str:
    if isinstance(event, tuple) and event:
        return str(event[0])
    return str(_field(event, "type", _field(event, "kind", "")))


def _event_payload(event: Any) -> Any:
    if isinstance(event, tuple) and len(event) > 1:
        return event[1]
    return _field(event, "payload", event)


async def _send_event(sess: Any, turn_context: Any, event: EventMsg) -> None:
    await _call_required(sess, "send_event", turn_context, event)


async def _send_error(sess: Any, turn_context: Any, exc: Exception) -> None:
    to_error_event = getattr(exc, "to_error_event", None)
    if callable(to_error_event):
        await _send_event(sess, turn_context, EventMsg.with_payload("error", to_error_event(None)))


async def _call_required(target: Any, name: str, *args: Any) -> Any:
    method = getattr(target, name, None)
    if not callable(method):
        raise TypeError(f"compact runtime requires {name}()")
    return await _maybe_await(method(*args))


async def _call_optional(target: Any, name: str, *args: Any) -> Any:
    method = getattr(target, name, None)
    if callable(method):
        return await _maybe_await(method(*args))
    return None


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
    mode = _field(_field(turn_context, "collaboration_mode"), "mode")
    return mode


async def _total_token_usage(sess: Any) -> int:
    getter = getattr(sess, "get_total_token_usage", None)
    if callable(getter):
        value = await _maybe_await(getter())
        return int(value or 0)
    getter = getattr(sess, "total_token_usage", None)
    if callable(getter):
        usage = await _maybe_await(getter())
        return int(_field(usage, "total_tokens", 0) or 0)
    return 0


def _error_kind(exc: Exception) -> str:
    return str(_field(exc, "kind", exc.__class__.__name__)).lower()


def _backoff_delay(retries: int) -> float:
    return min(0.1 * (2 ** max(0, retries - 1)), 2.0)


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
    "COMPACT_USER_MESSAGE_MAX_TOKENS",
    "COMPACTION_IMPLEMENTATION_RESPONSES",
    "COMPACTION_STRATEGY_MEMENTO",
    "CompactionAnalyticsAttempt",
    "CompactionPhase",
    "CompactionReason",
    "CompactionStatus",
    "CompactionTrigger",
    "InitialContextInjection",
    "SUMMARIZATION_PROMPT",
    "SUMMARY_PREFIX",
    "build_compacted_history",
    "build_compacted_history_with_limit",
    "collect_user_messages",
    "compaction_status_from_result",
    "content_items_to_text",
    "drain_to_completed",
    "insert_initial_context_before_last_real_user_or_summary",
    "is_summary_message",
    "run_compact_task",
    "run_compact_task_inner",
    "run_compact_task_inner_impl",
    "run_inline_auto_compact_task",
    "should_use_remote_compact_task",
]
