"""History normalization helpers aligned with ``codex-rs/core/src/context_manager/normalize.rs``."""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable, Sequence

from pycodex.protocol import ContentItem, FunctionCallOutputContentItem, FunctionCallOutputPayload, ResponseItem


IMAGE_CONTENT_OMITTED_PLACEHOLDER = "image content omitted because you do not support image input"


def ensure_call_outputs_present(history: Sequence[ResponseItem]) -> tuple[ResponseItem, ...]:
    items = list(_response_items(history, "history"))
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
    for index, output_item in reversed(missing):
        items.insert(index + 1, output_item)
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
            if call_id in function_call_ids or call_id in local_shell_call_ids:
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


def strip_images_when_unsupported(
    input_modalities: Sequence[object] | None,
    history: Sequence[ResponseItem],
) -> tuple[ResponseItem, ...]:
    items = _response_items(history, "history")
    if _input_modalities_support_images(input_modalities):
        return tuple(items)
    return tuple(_strip_images_from_item(item) for item in items)


def remove_corresponding_for(items: list[ResponseItem], item: ResponseItem) -> None:
    """Remove the first matching call/output counterpart for a removed history item."""

    if not isinstance(item, ResponseItem):
        raise TypeError("item must be a ResponseItem")
    call_id = item.call_id
    if not isinstance(call_id, str):
        return
    if item.type == "function_call":
        _remove_first_matching(items, call_id, ("function_call_output",))
    elif item.type == "function_call_output":
        if not _remove_first_matching(items, call_id, ("function_call",)):
            _remove_first_matching(items, call_id, ("local_shell_call",))
    elif item.type == "tool_search_call":
        _remove_first_matching(items, call_id, ("tool_search_output",))
    elif item.type == "tool_search_output":
        _remove_first_matching(items, call_id, ("tool_search_call",))
    elif item.type == "custom_tool_call":
        _remove_first_matching(items, call_id, ("custom_tool_call_output",))
    elif item.type == "custom_tool_call_output":
        _remove_first_matching(items, call_id, ("custom_tool_call",))
    elif item.type == "local_shell_call":
        _remove_first_matching(items, call_id, ("function_call_output",))


def _input_modalities_support_images(input_modalities: Sequence[object] | None) -> bool:
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


def _response_items(items: Iterable[ResponseItem], label: str) -> tuple[ResponseItem, ...]:
    if isinstance(items, ResponseItem) or isinstance(items, (str, bytes)):
        raise TypeError(f"{label} must be an iterable of ResponseItem")
    result: list[ResponseItem] = []
    for item in items:
        if not isinstance(item, ResponseItem):
            raise TypeError(f"{label} must contain ResponseItem values")
        result.append(item)
    return tuple(result)


def _remove_first_matching(items: list[ResponseItem], call_id: str, item_types: tuple[str, ...]) -> bool:
    for index, candidate in enumerate(items):
        if candidate.type in item_types and candidate.call_id == call_id:
            del items[index]
            return True
    return False


def _function_call_output(call_id: str) -> ResponseItem:
    return ResponseItem(type="function_call_output", call_id=call_id, output=FunctionCallOutputPayload.from_text("aborted"))


def _custom_tool_call_output(call_id: str) -> ResponseItem:
    return ResponseItem(
        type="custom_tool_call_output",
        call_id=call_id,
        output=FunctionCallOutputPayload.from_text("aborted"),
    )


def _tool_search_output(call_id: str) -> ResponseItem:
    return ResponseItem(type="tool_search_output", call_id=call_id, status="completed", execution="client", tools=())


__all__ = [
    "IMAGE_CONTENT_OMITTED_PLACEHOLDER",
    "ensure_call_outputs_present",
    "normalize_call_outputs",
    "remove_corresponding_for",
    "remove_orphan_outputs",
    "strip_images_when_unsupported",
]
