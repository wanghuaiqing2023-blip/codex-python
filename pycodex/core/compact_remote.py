"""Pure remote-compaction post-processing helpers.

Ported from the standalone helper portions of
``codex/codex-rs/core/src/compact_remote.rs``.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from pycodex.core.compact import (
    InitialContextInjection,
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
from pycodex.protocol import (
    BaseInstructions,
    CompactedItem,
    ResponseItem,
    TurnContextItem,
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
    "normalize_call_outputs",
    "normalize_history_for_prompt",
    "process_compacted_history",
    "remove_orphan_outputs",
    "should_keep_compacted_history_item",
    "strip_images_when_unsupported",
    "trim_function_call_history_to_fit_context_window",
]
