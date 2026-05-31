"""Pure helpers for remote compaction v2.

Ported from the standalone retained-history helpers in
``codex/codex-rs/core/src/compact_remote_v2.rs``. The async model request,
hook, session, tracing, and websocket retry orchestration remain outside this
stdlib-only slice.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Sequence

from pycodex.core.client_common import Prompt
from pycodex.core.compact import InitialContextInjection
from pycodex.core.compact_remote import process_compacted_history
from pycodex.core.compact_remote import should_keep_compacted_history_item
from pycodex.core.features import Feature
from pycodex.core.responses_retry import ResponsesStreamRequest, RetryableResponseStreamDecision, response_stream_retry_decision
from pycodex.core.string_utils import approx_token_count
from pycodex.core.tool_context import truncate_text
from pycodex.protocol import BaseInstructions, CodexErr, CompactedItem, ContentItem, Personality, ResponseItem, TruncationPolicyConfig, TurnContextItem


RETAINED_MESSAGE_TOKEN_BUDGET = 64_000
MAX_REMOTE_COMPACTION_V2_STREAM_RETRIES = 2


class RemoteCompactionV2StreamError(RuntimeError):
    """Remote compaction v2 stream closed before a completed response."""


class RemoteCompactionV2OutputError(RuntimeError):
    """Remote compaction v2 produced the wrong number of compaction outputs."""


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
        raise RemoteCompactionV2StreamError(
            "remote compaction v2 stream closed before response.completed"
        )
    if compaction_count != 1:
        raise RemoteCompactionV2OutputError(
            "remote compaction v2 expected exactly one compaction output item, "
            f"got {compaction_count} from {output_item_count} output items"
        )
    if compaction_output is None:
        raise RemoteCompactionV2OutputError("compaction output missing")
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
    "is_retained_for_remote_compaction_v2",
    "message_text_token_count",
    "remote_compaction_v2_max_stream_retries",
    "remote_compaction_v2_request_outcome",
    "remote_compaction_v2_retry_decision",
    "remote_compaction_v2_trace_attempt_payload",
    "response_processed_request_for_remote_compaction_v2",
    "truncate_message_text_to_token_budget",
    "truncate_retained_messages_for_remote_compaction",
]
