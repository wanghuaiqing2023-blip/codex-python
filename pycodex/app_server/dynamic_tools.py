"""Dynamic tool response handling for ``codex-app-server/src/dynamic_tools.rs``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pycodex.app_server.server_request_error import is_turn_transition_server_request_error
from pycodex.app_server_protocol.item import (
    DynamicToolCallOutputContentItem,
    DynamicToolCallResponse,
)
from pycodex.protocol.dynamic_tools import (
    DynamicToolCallOutputContentItem as CoreDynamicToolCallOutputContentItem,
)
from pycodex.protocol.dynamic_tools import DynamicToolResponse as CoreDynamicToolResponse
from pycodex.protocol.protocol import Op

JsonValue = Any

DYNAMIC_TOOL_REQUEST_FAILED_MESSAGE = "dynamic tool request failed"
DYNAMIC_TOOL_INVALID_RESPONSE_MESSAGE = "dynamic tool response was invalid"


@dataclass(frozen=True)
class DynamicToolCallResponseProjection:
    """Deterministic projection of Rust's async ``on_call_response`` branch."""

    ignored_turn_transition: bool
    app_server_response: DynamicToolCallResponse | None
    core_response: CoreDynamicToolResponse | None
    op: Op | None
    fallback_error: str | None = None
    log_error: str | None = None

    @property
    def should_submit(self) -> bool:
        return self.op is not None


def on_call_response_projection(
    call_id: str,
    result: JsonValue,
    *,
    receiver_canceled: bool = False,
) -> DynamicToolCallResponseProjection:
    """Mirror Rust's response decoding and submit-op shaping without I/O."""

    if receiver_canceled:
        response, fallback_error = fallback_response(DYNAMIC_TOOL_REQUEST_FAILED_MESSAGE)
        return _submitted_projection(call_id, response, fallback_error, log_error="request failed")

    if _is_ok_result(result):
        response, fallback_error = decode_response(_field(result, "value"))
        return _submitted_projection(call_id, response, fallback_error)

    error = _field(result, "error")
    if is_turn_transition_server_request_error(error):
        return DynamicToolCallResponseProjection(
            ignored_turn_transition=True,
            app_server_response=None,
            core_response=None,
            op=None,
        )

    response, fallback_error = fallback_response(DYNAMIC_TOOL_REQUEST_FAILED_MESSAGE)
    return _submitted_projection(
        call_id,
        response,
        fallback_error,
        log_error="request failed with client error",
    )


def decode_response(value: JsonValue) -> tuple[DynamicToolCallResponse, str | None]:
    """Decode app-server protocol JSON like Rust's ``serde_json::from_value``."""

    if isinstance(value, DynamicToolCallResponse):
        return value, None
    try:
        return _dynamic_tool_call_response_from_mapping(value), None
    except (KeyError, TypeError, ValueError):
        return fallback_response(DYNAMIC_TOOL_INVALID_RESPONSE_MESSAGE)


def fallback_response(message: str) -> tuple[DynamicToolCallResponse, str]:
    """Return Rust's failure response shape with one ``inputText`` item."""

    response = DynamicToolCallResponse(
        content_items=(DynamicToolCallOutputContentItem.input_text(message),),
        success=False,
    )
    return response, message


def core_response_from_app_server_response(response: DynamicToolCallResponse) -> CoreDynamicToolResponse:
    return CoreDynamicToolResponse(
        content_items=tuple(_core_content_item(item) for item in response.content_items),
        success=response.success,
    )


def _submitted_projection(
    call_id: str,
    response: DynamicToolCallResponse,
    fallback_error: str | None,
    *,
    log_error: str | None = None,
) -> DynamicToolCallResponseProjection:
    core_response = core_response_from_app_server_response(response)
    return DynamicToolCallResponseProjection(
        ignored_turn_transition=False,
        app_server_response=response,
        core_response=core_response,
        op=Op.dynamic_tool_response(id=call_id, response=core_response),
        fallback_error=fallback_error,
        log_error=log_error,
    )


def _dynamic_tool_call_response_from_mapping(value: JsonValue) -> DynamicToolCallResponse:
    if not isinstance(value, Mapping):
        raise TypeError("dynamic tool call response must be a mapping")
    raw_items = _pick(value, "content_items", "contentItems")
    if not isinstance(raw_items, list | tuple):
        raise TypeError("contentItems must be a list")
    success = _pick(value, "success")
    if not isinstance(success, bool):
        raise TypeError("success must be a bool")
    return DynamicToolCallResponse(
        content_items=tuple(DynamicToolCallOutputContentItem.from_mapping(item) for item in raw_items),
        success=success,
    )


def _core_content_item(item: DynamicToolCallOutputContentItem) -> CoreDynamicToolCallOutputContentItem:
    if item.type == "inputText":
        text = item.fields.get("text") if item.fields is not None else None
        if not isinstance(text, str):
            raise TypeError("inputText item requires text")
        return CoreDynamicToolCallOutputContentItem.input_text(text)
    if item.type == "inputImage":
        image_url = item.fields.get("imageUrl") if item.fields is not None else None
        if not isinstance(image_url, str):
            raise TypeError("inputImage item requires imageUrl")
        return CoreDynamicToolCallOutputContentItem.input_image(image_url)
    raise ValueError(f"unknown dynamic tool output content type: {item.type}")


def _is_ok_result(value: JsonValue) -> bool:
    if isinstance(value, Mapping):
        return "value" in value and "error" not in value
    return hasattr(value, "value") and not hasattr(value, "error")


def _field(value: JsonValue, name: str) -> JsonValue:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _pick(value: Mapping[str, JsonValue], *names: str) -> JsonValue:
    for name in names:
        if name in value:
            return value[name]
    raise KeyError(names[0])


__all__ = [
    "DYNAMIC_TOOL_INVALID_RESPONSE_MESSAGE",
    "DYNAMIC_TOOL_REQUEST_FAILED_MESSAGE",
    "DynamicToolCallResponseProjection",
    "core_response_from_app_server_response",
    "decode_response",
    "fallback_response",
    "on_call_response_projection",
]
