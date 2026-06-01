"""Pure remote-compaction post-processing helpers.

Ported from the standalone helper portions of
``codex/codex-rs/core/src/compact_remote.rs``.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, replace
from typing import Any, Callable, Sequence

from pycodex.core.compact import (
    InitialContextInjection,
    insert_initial_context_before_last_real_user_or_summary,
)
from pycodex.core.event_mapping import parse_turn_item
from pycodex.protocol import (
    BaseInstructions,
    CompactedItem,
    ContentItem,
    FunctionCallOutputContentItem,
    FunctionCallOutputPayload,
    ResponseItem,
    TurnContextItem,
)


IMAGE_CONTENT_OMITTED_PLACEHOLDER = "image content omitted because you do not support image input"


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


def ensure_call_outputs_present(history: Sequence[ResponseItem]) -> tuple[ResponseItem, ...]:
    items = _response_items(history, "history")
    missing: list[tuple[int, ResponseItem]] = []
    for index, item in enumerate(items):
        call_id = item.call_id
        if item.type == "function_call" and isinstance(call_id, str):
            if not any(candidate.type == "function_call_output" and candidate.call_id == call_id for candidate in items):
                missing.append((index, _function_call_output(call_id)))
        elif item.type == "tool_search_call" and isinstance(call_id, str):
            if not any(candidate.type == "tool_search_output" and candidate.call_id == call_id for candidate in items):
                missing.append((index, _tool_search_output(call_id)))
        elif item.type == "custom_tool_call" and isinstance(call_id, str):
            if not any(candidate.type == "custom_tool_call_output" and candidate.call_id == call_id for candidate in items):
                missing.append((index, _custom_tool_call_output(call_id)))
        elif item.type == "local_shell_call" and isinstance(call_id, str):
            if not any(candidate.type == "function_call_output" and candidate.call_id == call_id for candidate in items):
                missing.append((index, _function_call_output(call_id)))
    for index, output in reversed(missing):
        items.insert(index + 1, output)
    return tuple(items)


def remove_orphan_outputs(history: Sequence[ResponseItem]) -> tuple[ResponseItem, ...]:
    items = _response_items(history, "history")
    function_call_ids = {item.call_id for item in items if item.type == "function_call" and isinstance(item.call_id, str)}
    local_shell_call_ids = {item.call_id for item in items if item.type == "local_shell_call" and isinstance(item.call_id, str)}
    tool_search_call_ids = {item.call_id for item in items if item.type == "tool_search_call" and isinstance(item.call_id, str)}
    custom_tool_call_ids = {item.call_id for item in items if item.type == "custom_tool_call" and isinstance(item.call_id, str)}
    kept: list[ResponseItem] = []
    for item in items:
        call_id = item.call_id
        if item.type == "function_call_output":
            if call_id == "" or call_id in function_call_ids or call_id in local_shell_call_ids:
                kept.append(item)
            continue
        if item.type == "custom_tool_call_output":
            if call_id in custom_tool_call_ids:
                kept.append(item)
            continue
        if item.type == "tool_search_output":
            if item.execution == "server" or call_id is None or call_id in tool_search_call_ids:
                kept.append(item)
            continue
        kept.append(item)
    return tuple(kept)


def normalize_call_outputs(history: Sequence[ResponseItem]) -> tuple[ResponseItem, ...]:
    return remove_orphan_outputs(ensure_call_outputs_present(history))


def normalize_history_for_prompt(
    history: Sequence[ResponseItem],
    input_modalities: Sequence[Any] | None = None,
) -> tuple[ResponseItem, ...]:
    return strip_images_when_unsupported(input_modalities, normalize_call_outputs(history))


def strip_images_when_unsupported(
    input_modalities: Sequence[Any] | None,
    history: Sequence[ResponseItem],
) -> tuple[ResponseItem, ...]:
    items = _response_items(history, "history")
    if _input_modalities_support_images(input_modalities):
        return tuple(items)
    return tuple(_strip_images_from_item(item) for item in items)


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


def _function_call_output(call_id: str) -> ResponseItem:
    return ResponseItem(
        type="function_call_output",
        call_id=call_id,
        output=FunctionCallOutputPayload.from_text("aborted"),
    )


def _custom_tool_call_output(call_id: str) -> ResponseItem:
    return ResponseItem(
        type="custom_tool_call_output",
        call_id=call_id,
        output=FunctionCallOutputPayload.from_text("aborted"),
    )


def _tool_search_output(call_id: str) -> ResponseItem:
    return ResponseItem(
        type="tool_search_output",
        call_id=call_id,
        status="completed",
        execution="client",
        tools=(),
    )


def _input_modalities_support_images(input_modalities: Sequence[Any] | None) -> bool:
    if input_modalities is None:
        return False
    return any(getattr(modality, "value", modality) == "image" for modality in input_modalities)


def _strip_images_from_item(item: ResponseItem) -> ResponseItem:
    if item.type == "message":
        content = tuple(_strip_message_content_image(content_item) for content_item in item.content)
        return replace(item, content=content)
    if item.type in {"function_call_output", "custom_tool_call_output"} and isinstance(item.output, FunctionCallOutputPayload):
        output = _strip_function_output_images(item.output)
        return replace(item, output=output)
    if item.type == "image_generation_call":
        return replace(item, result="")
    return item


def _strip_message_content_image(item: ContentItem) -> ContentItem:
    if item.type == "input_image":
        return ContentItem.input_text(IMAGE_CONTENT_OMITTED_PLACEHOLDER)
    return item


def _strip_function_output_images(output: FunctionCallOutputPayload) -> FunctionCallOutputPayload:
    content_items = output.content_items
    if content_items is None:
        return output
    normalized = tuple(_strip_function_output_content_image(item) for item in content_items)
    return FunctionCallOutputPayload.from_content_items(normalized, success=output.success)


def _strip_function_output_content_image(item: FunctionCallOutputContentItem) -> FunctionCallOutputContentItem:
    if item.type == "input_image":
        return FunctionCallOutputContentItem.input_text(IMAGE_CONTENT_OMITTED_PLACEHOLDER)
    return item


def _response_items(value: Sequence[ResponseItem], label: str) -> list[ResponseItem]:
    if isinstance(value, ResponseItem) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence of ResponseItem")
    if not all(isinstance(item, ResponseItem) for item in value):
        raise TypeError(f"{label} must contain ResponseItem values")
    return list(value)


__all__ = [
    "CompactRequestLogData",
    "IMAGE_CONTENT_OMITTED_PLACEHOLDER",
    "RemoteCompactionInstallPlan",
    "TrimFunctionCallHistoryResult",
    "apply_remote_compaction_install_plan",
    "build_compact_request_log_data",
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
