"""Runtime callbacks ported from ``runtime/callbacks.rs``."""
from __future__ import annotations
import copy
import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any
from ..description import CodeModeToolDefinition, EnabledToolMetadata, _coerce_enabled_tool_metadata
from ..response import FunctionCallOutputContentItem, ImageDetail
from . import (
    CodeModeNestedToolCall,
    CompletionState,
    RuntimeEvent,
    _ensure_json_like,
    _ensure_str,
    _non_negative_int,
)
from .module_loader import EXIT_SENTINEL
from .value import normalize_output_image, serialize_output_text, _json_round_trip
JsonValue = Any

U64_MAX = (1 << 64) - 1


RUNTIME_TOOL_CALL_ID_PREFIX = "tool-"


@dataclass
class CodeModeRuntimeStore:
    stored_values: dict[str, JsonValue] = field(default_factory=dict)
    stored_value_writes: dict[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.stored_values = {
            _ensure_str(key, "stored_values key"): _ensure_json_like(value, "stored_values value")
            for key, value in self.stored_values.items()
        }
        self.stored_value_writes = {
            _ensure_str(key, "stored_value_writes key"): _ensure_json_like(value, "stored_value_writes value")
            for key, value in self.stored_value_writes.items()
        }

    def store(self, key: JsonValue, value: JsonValue) -> None:
        normalized_key = normalize_store_key(key)
        serialized = serialize_stored_value(normalized_key, value)
        self.stored_values[normalized_key] = copy.deepcopy(serialized)
        self.stored_value_writes[normalized_key] = copy.deepcopy(serialized)

    def load(self, key: JsonValue) -> JsonValue | None:
        normalized_key = normalize_store_key(key)
        if normalized_key not in self.stored_values:
            return None
        return copy.deepcopy(self.stored_values[normalized_key])

    def writes(self) -> dict[str, JsonValue]:
        return copy.deepcopy(self.stored_value_writes)


def build_runtime_text_event(value: JsonValue | None = None) -> RuntimeEvent:
    return RuntimeEvent.content_item(
        FunctionCallOutputContentItem.input_text(serialize_output_text(value))
    )


def build_runtime_image_event(
    value: JsonValue,
    detail_override: str | ImageDetail | None = None,
) -> RuntimeEvent:
    return RuntimeEvent.content_item(normalize_output_image(value, detail_override))


def build_runtime_notify_event(call_id: str, value: JsonValue) -> RuntimeEvent:
    return RuntimeEvent.notify(call_id=str(call_id), text=normalize_notify_text(value))


def build_runtime_yield_event() -> RuntimeEvent:
    return RuntimeEvent.yield_requested()


def runtime_exit_exception() -> str:
    return EXIT_SENTINEL


def completion_state_from_exit(
    stored_value_writes: Mapping[str, JsonValue] | None = None,
) -> CompletionState:
    return CompletionState.completed(stored_value_writes=stored_value_writes)


def normalize_store_key(value: JsonValue | None = None) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        number = float(value)
        if math.isnan(number):
            return "NaN"
        if math.isinf(number):
            return "Infinity" if number > 0 else "-Infinity"
        if number == math.trunc(number):
            return str(math.trunc(number))
        return str(value)
    return str(value)


def serialize_stored_value(key: str, value: JsonValue) -> JsonValue:
    try:
        return _json_round_trip(value)
    except (TypeError, ValueError) as exc:
        quoted_key = json.dumps(str(key), ensure_ascii=False)
        raise ValueError(
            f"Unable to store {quoted_key}. Only plain serializable objects can be stored."
        ) from exc


def normalize_notify_text(value: JsonValue) -> str:
    text = serialize_output_text(value)
    if text.strip() == "":
        raise ValueError("notify expects non-empty text")
    return text


def runtime_tool_index_from_callback_data(value: JsonValue) -> int:
    text = str(value)
    if text == "" or not all("0" <= char <= "9" for char in text):
        raise ValueError("invalid tool callback data")
    return int(text)


def runtime_tool_call_id(sequence: int) -> str:
    return f"{RUNTIME_TOOL_CALL_ID_PREFIX}{_non_negative_int(sequence)}"


def next_runtime_tool_call_sequence(sequence: int) -> int:
    current = _non_negative_int(sequence)
    return current if current >= U64_MAX else current + 1


def normalize_runtime_tool_input(value: JsonValue | None = None) -> JsonValue | None:
    if value is None:
        return None
    try:
        return _json_round_trip(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"failed to serialize JavaScript value: {exc}") from exc


def build_runtime_tool_call_event(
    *,
    cell_id: str,
    tool_index: int | str,
    enabled_tools: Iterable[
        CodeModeToolDefinition | EnabledToolMetadata | Mapping[str, JsonValue]
    ],
    input: JsonValue | None = None,
    next_tool_call_id: int = 1,
) -> tuple[RuntimeEvent, int]:
    index = runtime_tool_index_from_callback_data(tool_index)
    tools = tuple(_coerce_enabled_tool_metadata(tool) for tool in enabled_tools)
    if index >= len(tools):
        raise ValueError("tool callback data is out of range")

    tool = tools[index]
    sequence = _non_negative_int(next_tool_call_id)
    call_id = runtime_tool_call_id(sequence)
    event = RuntimeEvent.tool_call(
        CodeModeNestedToolCall(
            cell_id=str(cell_id),
            runtime_tool_call_id=call_id,
            tool_name=tool.tool_name,
            tool_kind=tool.kind,
            input=normalize_runtime_tool_input(input),
        )
    )
    return event, next_runtime_tool_call_sequence(sequence)


def tool_callback(
    *,
    cell_id: str,
    tool_index: int | str,
    enabled_tools: Iterable[
        CodeModeToolDefinition | EnabledToolMetadata | Mapping[str, JsonValue]
    ],
    input: JsonValue | None = None,
    next_tool_call_id: int = 1,
) -> tuple[RuntimeEvent, int]:
    return build_runtime_tool_call_event(
        cell_id=cell_id,
        tool_index=tool_index,
        enabled_tools=enabled_tools,
        input=input,
        next_tool_call_id=next_tool_call_id,
    )


def text_callback(value: JsonValue | None = None) -> RuntimeEvent:
    return build_runtime_text_event(value)


def image_callback(
    value: JsonValue,
    detail: str | ImageDetail | None = None,
) -> RuntimeEvent:
    return build_runtime_image_event(value, detail)


def store_callback(store: CodeModeRuntimeStore, key: JsonValue, value: JsonValue) -> None:
    store.store(key, value)


def load_callback(store: CodeModeRuntimeStore, key: JsonValue) -> JsonValue | None:
    return store.load(key)


def notify_callback(call_id: str, value: JsonValue) -> RuntimeEvent:
    return build_runtime_notify_event(call_id, value)


def set_timeout_callback(
    scheduler: Any,
    callback: Any,
    delay_ms: JsonValue | None = None,
) -> int:
    return int(scheduler.schedule_timeout(callback, delay_ms))


def clear_timeout_callback(scheduler: Any, timeout_id: JsonValue | None = None) -> bool:
    return bool(scheduler.clear_timeout(timeout_id))


def yield_control_callback() -> RuntimeEvent:
    return build_runtime_yield_event()


def exit_callback() -> str:
    return runtime_exit_exception()


__all__ = [
    "CodeModeRuntimeStore",
    "RUNTIME_TOOL_CALL_ID_PREFIX",
    "U64_MAX",
    "build_runtime_image_event",
    "build_runtime_notify_event",
    "build_runtime_text_event",
    "build_runtime_tool_call_event",
    "build_runtime_yield_event",
    "clear_timeout_callback",
    "completion_state_from_exit",
    "exit_callback",
    "image_callback",
    "load_callback",
    "next_runtime_tool_call_sequence",
    "normalize_notify_text",
    "normalize_runtime_tool_input",
    "normalize_store_key",
    "notify_callback",
    "runtime_exit_exception",
    "runtime_tool_call_id",
    "runtime_tool_index_from_callback_data",
    "serialize_stored_value",
    "set_timeout_callback",
    "store_callback",
    "text_callback",
    "tool_callback",
    "yield_control_callback",
]
