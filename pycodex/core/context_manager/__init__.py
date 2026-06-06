"""Context manager modules aligned with ``codex-rs/core/src/context_manager``."""

from .history import (
    ContextManager,
    estimate_item_token_count,
    estimate_response_item_model_visible_bytes,
    estimate_token_count_with_base_instructions,
    is_api_message,
    is_user_turn_boundary,
    process_history_item,
    process_history_items,
    truncate_function_output_payload,
)
from .normalize import (
    IMAGE_CONTENT_OMITTED_PLACEHOLDER,
    ensure_call_outputs_present,
    normalize_call_outputs,
    remove_corresponding_for,
    remove_orphan_outputs,
    strip_images_when_unsupported,
)

__all__ = [
    "ContextManager",
    "IMAGE_CONTENT_OMITTED_PLACEHOLDER",
    "ensure_call_outputs_present",
    "estimate_item_token_count",
    "estimate_response_item_model_visible_bytes",
    "estimate_token_count_with_base_instructions",
    "is_api_message",
    "is_user_turn_boundary",
    "normalize_call_outputs",
    "process_history_item",
    "process_history_items",
    "remove_corresponding_for",
    "remove_orphan_outputs",
    "strip_images_when_unsupported",
    "truncate_function_output_payload",
]
