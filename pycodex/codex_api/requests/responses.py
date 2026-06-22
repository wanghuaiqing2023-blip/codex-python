"""Response request helpers from Rust ``codex-api/src/requests/responses.rs``."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pycodex.protocol import ResponseItem


JsonValue = Any


class Compression(str, Enum):
    NONE = "none"
    ZSTD = "zstd"


_ID_CARRYING_RESPONSE_TYPES = {
    "reasoning",
    "message",
    "web_search_call",
    "function_call",
    "tool_search_call",
    "local_shell_call",
    "custom_tool_call",
}


def attach_item_ids(payload_json: dict[str, JsonValue], original_items: list[ResponseItem] | tuple[ResponseItem, ...]) -> None:
    input_value = payload_json.get("input")
    if not isinstance(input_value, list):
        return

    for value, item in zip(input_value, original_items, strict=False):
        if not isinstance(value, dict):
            continue
        if item.type not in _ID_CARRYING_RESPONSE_TYPES:
            continue
        if not item.id:
            continue
        value["id"] = item.id


__all__ = ["Compression", "attach_item_ids"]
