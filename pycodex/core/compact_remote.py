"""Pure remote-compaction post-processing helpers.

Ported from the standalone helper portions of
``codex/codex-rs/core/src/compact_remote.rs``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Sequence

from pycodex.core.compact import (
    InitialContextInjection,
    insert_initial_context_before_last_real_user_or_summary,
)
from pycodex.core.event_mapping import parse_turn_item
from pycodex.protocol import BaseInstructions, ResponseItem


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


def estimate_response_item_model_visible_bytes(item: ResponseItem) -> int:
    if not isinstance(item, ResponseItem):
        raise TypeError("item must be a ResponseItem")
    return len(json.dumps(item.to_mapping(), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


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
    call_id = removed.call_id
    if not isinstance(call_id, str):
        return
    if removed.type in {"function_call_output", "tool_search_output", "custom_tool_call_output"}:
        counterpart_types = {"function_call", "tool_search_call", "custom_tool_call", "local_shell_call"}
    elif removed.type in {"function_call", "tool_search_call", "custom_tool_call", "local_shell_call"}:
        counterpart_types = {"function_call_output", "tool_search_output", "custom_tool_call_output"}
    else:
        return
    for index, item in enumerate(items):
        if item.type in counterpart_types and item.call_id == call_id:
            del items[index]
            return


def _response_items(value: Sequence[ResponseItem], label: str) -> list[ResponseItem]:
    if isinstance(value, ResponseItem) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence of ResponseItem")
    if not all(isinstance(item, ResponseItem) for item in value):
        raise TypeError(f"{label} must contain ResponseItem values")
    return list(value)


__all__ = [
    "CompactRequestLogData",
    "TrimFunctionCallHistoryResult",
    "build_compact_request_log_data",
    "estimate_response_item_model_visible_bytes",
    "is_codex_generated_item",
    "process_compacted_history",
    "should_keep_compacted_history_item",
    "trim_function_call_history_to_fit_context_window",
]
