"""Response conversion owned by ``core/src/tools/code_mode``."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from pycodex.code_mode import DEFAULT_IMAGE_DETAIL
from pycodex.code_mode import FunctionCallOutputContentItem
from pycodex.code_mode import RuntimeResponse


def into_function_call_output_content_items(
    items: Iterable[FunctionCallOutputContentItem | Mapping[str, Any]],
) -> tuple[FunctionCallOutputContentItem, ...]:
    converted = tuple(
        item
        if isinstance(item, FunctionCallOutputContentItem)
        else FunctionCallOutputContentItem.from_mapping(item)
        for item in items
    )
    return tuple(
        FunctionCallOutputContentItem.input_image(
            item.image_url or "",
            item.detail or DEFAULT_IMAGE_DETAIL,
        )
        if item.type == "input_image"
        else item
        for item in converted
    )


def format_script_status(response: RuntimeResponse) -> str:
    if response.type == "yielded":
        return f"Script running with cell ID {response.cell_id}"
    if response.type == "terminated":
        return "Script terminated"
    return "Script completed" if response.error_text is None else "Script failed"


def script_status_header(status: str, wall_time_seconds: float) -> str:
    return f"{status}\nWall time {round(float(wall_time_seconds), 1):.1f} seconds\nOutput:\n"


def handle_runtime_response(
    response: RuntimeResponse,
    *,
    max_output_tokens: int | None,
    wall_time_seconds: float,
    can_request_original_detail: bool = True,
) -> Any:
    from pycodex.core.original_image_detail import sanitize_original_image_detail
    from pycodex.core.tools.context import FunctionToolOutput

    content_items = into_function_call_output_content_items(response.content_items)
    content_items = sanitize_original_image_detail(can_request_original_detail, content_items)
    success = response.type != "result" or response.error_text is None
    if response.type == "result" and response.error_text is not None:
        content_items = (
            *content_items,
            FunctionCallOutputContentItem.input_text(f"Script error:\n{response.error_text}"),
        )
    content_items = truncate_code_mode_result(content_items, max_output_tokens)
    content_items = (
        FunctionCallOutputContentItem.input_text(
            script_status_header(format_script_status(response), wall_time_seconds)
        ),
        *content_items,
    )
    return FunctionToolOutput.from_content(content_items, success)


def truncate_code_mode_result(
    items: Iterable[FunctionCallOutputContentItem | Mapping[str, Any]],
    max_output_tokens: int | None,
) -> tuple[FunctionCallOutputContentItem, ...]:
    from pycodex.core.tools.context import (
        formatted_truncate_text_content_items_with_policy,
        truncate_function_output_items_with_policy,
    )
    from pycodex.core.unified_exec import resolve_max_tokens
    from pycodex.protocol import TruncationPolicyConfig

    content_items = into_function_call_output_content_items(items)
    policy = TruncationPolicyConfig.tokens(resolve_max_tokens(max_output_tokens))
    if all(item.type == "input_text" for item in content_items):
        truncated_items, _ = formatted_truncate_text_content_items_with_policy(
            content_items,
            policy,
        )
        return truncated_items
    return truncate_function_output_items_with_policy(content_items, policy)


__all__ = [
    "format_script_status",
    "handle_runtime_response",
    "into_function_call_output_content_items",
    "script_status_header",
    "truncate_code_mode_result",
]
