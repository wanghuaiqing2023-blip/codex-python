"""Runtime protocol and command loop ported from ``code-mode/src/runtime/mod.rs``."""
from __future__ import annotations
import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from pycodex.protocol import ToolName
from ..description import CodeModeToolDefinition, CodeModeToolKind, EnabledToolMetadata, _coerce_code_mode_tool_definition, _coerce_enabled_tool_metadata, _coerce_kind, _coerce_tool_name
from ..response import FunctionCallOutputContentItem
from .value import _json_round_trip
JsonValue = Any
def _ensure_str(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    return value


def _ensure_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field} must be a bool")
    return value


def _ensure_json_like(value: JsonValue, field: str) -> JsonValue:
    try:
        return _json_round_trip(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{field} must be JSON-serializable") from exc


DEFAULT_EXEC_YIELD_TIME_MS = 10_000


DEFAULT_WAIT_YIELD_TIME_MS = 10_000


DEFAULT_MAX_OUTPUT_TOKENS_PER_EXEC_CALL = 10_000


EXEC_MAIN_MODULE_NAME = "exec_main.mjs"


_COMMAND_STREAM_DISCONNECTED = object()


@dataclass(frozen=True)
class ExecuteRequest:
    cell_id: str
    tool_call_id: str
    enabled_tools: tuple[CodeModeToolDefinition, ...]
    source: str
    yield_time_ms: int | None = None
    max_output_tokens: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "cell_id", _ensure_str(self.cell_id, "cell_id"))
        object.__setattr__(self, "tool_call_id", _ensure_str(self.tool_call_id, "tool_call_id"))
        object.__setattr__(
            self,
            "enabled_tools",
            tuple(_coerce_code_mode_tool_definition(tool) for tool in self.enabled_tools),
        )
        object.__setattr__(self, "source", _ensure_str(self.source, "source"))
        object.__setattr__(self, "yield_time_ms", _optional_non_negative_int(self.yield_time_ms))
        object.__setattr__(
            self,
            "max_output_tokens",
            _optional_non_negative_int(self.max_output_tokens),
        )


@dataclass(frozen=True)
class WaitRequest:
    cell_id: str
    yield_time_ms: int = DEFAULT_WAIT_YIELD_TIME_MS
    terminate: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "cell_id", _ensure_str(self.cell_id, "cell_id"))
        object.__setattr__(self, "yield_time_ms", _non_negative_int(self.yield_time_ms))
        object.__setattr__(self, "terminate", _ensure_bool(self.terminate, "terminate"))


@dataclass(frozen=True)
class WaitToPendingRequest:
    cell_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "cell_id", _ensure_str(self.cell_id, "cell_id"))


@dataclass(frozen=True)
class RuntimeResponse:
    type: str
    cell_id: str
    content_items: tuple[FunctionCallOutputContentItem, ...] = ()
    error_text: str | None = None

    def __post_init__(self) -> None:
        response_type = _ensure_str(self.type, "type")
        if response_type not in {"yielded", "terminated", "result"}:
            raise ValueError(f"unsupported runtime response type: {self.type}")
        object.__setattr__(self, "type", response_type)
        object.__setattr__(self, "cell_id", _ensure_str(self.cell_id, "cell_id"))
        object.__setattr__(
            self,
            "content_items",
            tuple(FunctionCallOutputContentItem.from_mapping(item) for item in self.content_items),
        )
        if self.error_text is not None:
            object.__setattr__(self, "error_text", _ensure_str(self.error_text, "error_text"))
        elif response_type != "result":
            object.__setattr__(self, "error_text", None)

    @classmethod
    def yielded(
        cls,
        *,
        cell_id: str,
        content_items: Iterable[FunctionCallOutputContentItem | Mapping[str, JsonValue]] = (),
    ) -> "RuntimeResponse":
        return cls("yielded", cell_id=cell_id, content_items=tuple(content_items))

    @classmethod
    def terminated(
        cls,
        *,
        cell_id: str,
        content_items: Iterable[FunctionCallOutputContentItem | Mapping[str, JsonValue]] = (),
    ) -> "RuntimeResponse":
        return cls("terminated", cell_id=cell_id, content_items=tuple(content_items))

    @classmethod
    def result(
        cls,
        *,
        cell_id: str,
        content_items: Iterable[FunctionCallOutputContentItem | Mapping[str, JsonValue]] = (),
        error_text: str | None = None,
    ) -> "RuntimeResponse":
        return cls(
            "result",
            cell_id=cell_id,
            content_items=tuple(content_items),
            error_text=error_text,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "RuntimeResponse":
        variant = _external_variant(value, {"Yielded", "Terminated", "Result"})
        if variant is not None:
            name, payload = variant
            return cls._from_payload(name.lower(), payload)
        return cls._from_payload(str(value["type"]), value)

    @classmethod
    def _from_payload(cls, response_type: str, payload: Mapping[str, JsonValue]) -> "RuntimeResponse":
        return cls(
            response_type,
            cell_id=str(payload["cell_id"]),
            content_items=tuple(payload.get("content_items", ())),
            error_text=None if payload.get("error_text") is None else str(payload.get("error_text")),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "type": self.type,
            "cell_id": self.cell_id,
            "content_items": [item.to_mapping() for item in self.content_items],
        }
        if self.type == "result":
            data["error_text"] = self.error_text
        return data


@dataclass(frozen=True)
class WaitOutcome:
    type: str
    response: RuntimeResponse

    def __post_init__(self) -> None:
        outcome_type = _ensure_str(self.type, "type")
        if outcome_type not in {"live_cell", "missing_cell"}:
            raise ValueError(f"unsupported wait outcome type: {self.type}")
        object.__setattr__(self, "type", outcome_type)
        object.__setattr__(self, "response", _coerce_runtime_response(self.response))

    @classmethod
    def live_cell(cls, response: RuntimeResponse | Mapping[str, JsonValue]) -> "WaitOutcome":
        return cls("live_cell", _coerce_runtime_response(response))

    @classmethod
    def missing_cell(cls, response: RuntimeResponse | Mapping[str, JsonValue]) -> "WaitOutcome":
        return cls("missing_cell", _coerce_runtime_response(response))

    def into_runtime_response(self) -> RuntimeResponse:
        return self.response


@dataclass(frozen=True)
class ExecuteToPendingOutcome:
    type: str
    cell_id: str | None = None
    content_items: tuple[FunctionCallOutputContentItem, ...] = ()
    pending_tool_call_ids: tuple[str, ...] = ()
    response: RuntimeResponse | None = None

    def __post_init__(self) -> None:
        outcome_type = _ensure_str(self.type, "type")
        if outcome_type not in {"pending", "completed"}:
            raise ValueError(f"unsupported execute-to-pending outcome type: {self.type}")
        object.__setattr__(self, "type", outcome_type)
        if self.cell_id is not None:
            object.__setattr__(self, "cell_id", _ensure_str(self.cell_id, "cell_id"))
        object.__setattr__(
            self,
            "content_items",
            tuple(FunctionCallOutputContentItem.from_mapping(item) for item in self.content_items),
        )
        object.__setattr__(
            self,
            "pending_tool_call_ids",
            tuple(_ensure_str(call_id, "pending_tool_call_ids") for call_id in self.pending_tool_call_ids),
        )
        if self.response is not None:
            object.__setattr__(self, "response", _coerce_runtime_response(self.response))

    @classmethod
    def pending(
        cls,
        *,
        cell_id: str,
        content_items: Iterable[FunctionCallOutputContentItem | Mapping[str, JsonValue]] = (),
        pending_tool_call_ids: Iterable[str] = (),
    ) -> "ExecuteToPendingOutcome":
        return cls(
            "pending",
            cell_id=cell_id,
            content_items=tuple(content_items),
            pending_tool_call_ids=tuple(pending_tool_call_ids),
        )

    @classmethod
    def completed(
        cls,
        response: RuntimeResponse | Mapping[str, JsonValue],
    ) -> "ExecuteToPendingOutcome":
        return cls("completed", response=_coerce_runtime_response(response))


@dataclass(frozen=True)
class WaitToPendingOutcome:
    type: str
    outcome: ExecuteToPendingOutcome | None = None
    response: RuntimeResponse | None = None

    def __post_init__(self) -> None:
        outcome_type = _ensure_str(self.type, "type")
        if outcome_type not in {"live_cell", "missing_cell"}:
            raise ValueError(f"unsupported wait-to-pending outcome type: {self.type}")
        object.__setattr__(self, "type", outcome_type)
        if self.outcome is not None:
            object.__setattr__(self, "outcome", _coerce_execute_to_pending_outcome(self.outcome))
        if self.response is not None:
            object.__setattr__(self, "response", _coerce_runtime_response(self.response))

    @classmethod
    def live_cell(
        cls,
        outcome: ExecuteToPendingOutcome | Mapping[str, JsonValue],
    ) -> "WaitToPendingOutcome":
        return cls("live_cell", outcome=_coerce_execute_to_pending_outcome(outcome))

    @classmethod
    def missing_cell(
        cls,
        response: RuntimeResponse | Mapping[str, JsonValue],
    ) -> "WaitToPendingOutcome":
        return cls("missing_cell", response=_coerce_runtime_response(response))


@dataclass(frozen=True)
class CodeModeNestedToolCall:
    cell_id: str
    runtime_tool_call_id: str
    tool_name: ToolName
    tool_kind: CodeModeToolKind
    input: JsonValue | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "cell_id", str(self.cell_id))
        object.__setattr__(self, "runtime_tool_call_id", _ensure_str(self.runtime_tool_call_id, "runtime_tool_call_id"))
        object.__setattr__(self, "tool_name", _coerce_tool_name(self.tool_name))
        object.__setattr__(self, "tool_kind", _coerce_kind(self.tool_kind))
        object.__setattr__(self, "input", copy.deepcopy(self.input))


class PendingRuntimeMode(str, Enum):
    CONTINUE = "continue"
    PAUSE_UNTIL_RESUMED = "pause_until_resumed"


class RuntimeControlCommand(str, Enum):
    RESUME = "resume"
    TERMINATE = "terminate"


@dataclass(frozen=True)
class RuntimeCommand:
    type: str
    id: str | int | None = None
    result: JsonValue | None = None
    error_text: str | None = None

    def __post_init__(self) -> None:
        command_type = str(self.type)
        if command_type not in {"tool_response", "tool_error", "timeout_fired", "terminate"}:
            raise ValueError(f"unsupported runtime command type: {self.type}")
        object.__setattr__(self, "type", command_type)
        if command_type in {"tool_response", "tool_error"}:
            if self.id is None:
                raise ValueError(f"{command_type} requires an id")
            object.__setattr__(self, "id", str(self.id))
        elif command_type == "timeout_fired":
            if self.id is None:
                raise ValueError("timeout_fired requires an id")
            object.__setattr__(self, "id", _non_negative_int(int(self.id)))
        else:
            object.__setattr__(self, "id", None)
        if self.error_text is not None:
            object.__setattr__(self, "error_text", str(self.error_text))
        object.__setattr__(self, "result", copy.deepcopy(self.result))

    @classmethod
    def tool_response(cls, id: str, result: JsonValue) -> "RuntimeCommand":
        return cls("tool_response", id=id, result=result)

    @classmethod
    def tool_error(cls, id: str, error_text: str) -> "RuntimeCommand":
        return cls("tool_error", id=id, error_text=error_text)

    @classmethod
    def timeout_fired(cls, id: int) -> "RuntimeCommand":
        return cls("timeout_fired", id=id)

    @classmethod
    def terminate(cls) -> "RuntimeCommand":
        return cls("terminate")

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "RuntimeCommand":
        variant = _external_variant(value, {"ToolResponse", "ToolError", "TimeoutFired", "Terminate"})
        if variant is not None:
            name, payload = variant
            if name == "ToolResponse":
                return cls.tool_response(str(payload["id"]), payload.get("result"))
            if name == "ToolError":
                return cls.tool_error(str(payload["id"]), str(payload.get("error_text", "")))
            if name == "TimeoutFired":
                return cls.timeout_fired(int(payload["id"]))
            return cls.terminate()
        command_type = str(value["type"])
        return cls(
            command_type,
            id=value.get("id"),
            result=value.get("result"),
            error_text=None if value.get("error_text") is None else str(value.get("error_text")),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"type": self.type}
        if self.id is not None:
            data["id"] = self.id
        if self.type == "tool_response":
            data["result"] = copy.deepcopy(self.result)
        if self.type == "tool_error":
            data["error_text"] = self.error_text
        return data


@dataclass(frozen=True)
class NextRuntimeCommandResult:
    command: RuntimeCommand | None
    events: tuple["RuntimeEvent", ...] = ()
    consumed_controls: tuple[RuntimeControlCommand, ...] = ()


@dataclass
class CodeModeRuntimeToolState:
    cell_id: str
    enabled_tools: tuple[EnabledToolMetadata, ...] = ()
    next_tool_call_id: int = 1
    pending_tool_call_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.cell_id = str(self.cell_id)
        self.enabled_tools = tuple(
            _coerce_enabled_tool_metadata(tool) for tool in self.enabled_tools
        )
        self.next_tool_call_id = _non_negative_int(self.next_tool_call_id)
        self.pending_tool_call_ids = [str(call_id) for call_id in self.pending_tool_call_ids]

    def emit_tool_call(self, tool_index: int | str, input: JsonValue | None = None) -> "RuntimeEvent":
        event, next_id = build_runtime_tool_call_event(
            cell_id=self.cell_id,
            tool_index=tool_index,
            enabled_tools=self.enabled_tools,
            input=input,
            next_tool_call_id=self.next_tool_call_id,
        )
        self.next_tool_call_id = next_id
        if event.nested_tool_call is not None:
            self.pending_tool_call_ids.append(event.nested_tool_call.runtime_tool_call_id)
        return event


@dataclass(frozen=True)
class RuntimeEvent:
    type: str
    item: FunctionCallOutputContentItem | None = None
    nested_tool_call: CodeModeNestedToolCall | None = None
    call_id: str | None = None
    text: str | None = None
    stored_value_writes: Mapping[str, JsonValue] | None = None
    error_text: str | None = None

    def __post_init__(self) -> None:
        event_type = str(self.type)
        if event_type not in {
            "started",
            "pending",
            "content_item",
            "yield_requested",
            "tool_call",
            "notify",
            "result",
        }:
            raise ValueError(f"unsupported runtime event type: {self.type}")
        object.__setattr__(self, "type", event_type)
        if self.item is not None:
            object.__setattr__(
                self,
                "item",
                FunctionCallOutputContentItem.from_mapping(self.item),
            )
        if self.nested_tool_call is not None:
            object.__setattr__(
                self,
                "nested_tool_call",
                _coerce_nested_tool_call(self.nested_tool_call),
            )
        if self.call_id is not None:
            object.__setattr__(self, "call_id", str(self.call_id))
        if self.text is not None:
            object.__setattr__(self, "text", str(self.text))
        writes = self.stored_value_writes or {}
        object.__setattr__(
            self,
            "stored_value_writes",
            {str(key): _json_round_trip(value) for key, value in writes.items()},
        )
        if self.error_text is not None:
            object.__setattr__(self, "error_text", str(self.error_text))

    @classmethod
    def started(cls) -> "RuntimeEvent":
        return cls("started")

    @classmethod
    def pending(cls) -> "RuntimeEvent":
        return cls("pending")

    @classmethod
    def yield_requested(cls) -> "RuntimeEvent":
        return cls("yield_requested")

    @classmethod
    def content_item(
        cls,
        item: FunctionCallOutputContentItem | Mapping[str, JsonValue],
    ) -> "RuntimeEvent":
        return cls("content_item", item=FunctionCallOutputContentItem.from_mapping(item))

    @classmethod
    def tool_call(cls, call: CodeModeNestedToolCall | Mapping[str, JsonValue]) -> "RuntimeEvent":
        return cls("tool_call", nested_tool_call=_coerce_nested_tool_call(call))

    @classmethod
    def notify(cls, *, call_id: str, text: str) -> "RuntimeEvent":
        return cls("notify", call_id=call_id, text=text)

    @classmethod
    def result(
        cls,
        *,
        stored_value_writes: Mapping[str, JsonValue] | None = None,
        error_text: str | None = None,
    ) -> "RuntimeEvent":
        return cls("result", stored_value_writes=stored_value_writes, error_text=error_text)

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "RuntimeEvent":
        variant = _external_variant(
            value,
            {"Started", "Pending", "ContentItem", "YieldRequested", "ToolCall", "Notify", "Result"},
        )
        if variant is not None:
            name, payload = variant
            if name == "Started":
                return cls.started()
            if name == "Pending":
                return cls.pending()
            if name == "ContentItem":
                return cls.content_item(payload["item"])
            if name == "YieldRequested":
                return cls.yield_requested()
            if name == "ToolCall":
                return cls.tool_call(payload)
            if name == "Notify":
                return cls.notify(call_id=str(payload["call_id"]), text=str(payload["text"]))
            return cls.result(
                stored_value_writes=payload.get("stored_value_writes"),
                error_text=None if payload.get("error_text") is None else str(payload["error_text"]),
            )
        event_type = str(value["type"])
        return cls(
            event_type,
            item=value.get("content_item"),
            nested_tool_call=value.get("tool_call"),
            call_id=None if value.get("call_id") is None else str(value.get("call_id")),
            text=None if value.get("text") is None else str(value.get("text")),
            stored_value_writes=value.get("stored_value_writes"),
            error_text=None if value.get("error_text") is None else str(value.get("error_text")),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"type": self.type}
        if self.item is not None:
            data["content_item"] = self.item.to_mapping()
        if self.nested_tool_call is not None:
            data["tool_call"] = _nested_tool_call_to_mapping(self.nested_tool_call)
        if self.call_id is not None:
            data["call_id"] = self.call_id
        if self.text is not None:
            data["text"] = self.text
        if self.type == "result":
            data["stored_value_writes"] = copy.deepcopy(dict(self.stored_value_writes or {}))
            data["error_text"] = self.error_text
        return data


@dataclass(frozen=True)
class CompletionState:
    type: str
    stored_value_writes: Mapping[str, JsonValue] | None = None
    error_text: str | None = None

    def __post_init__(self) -> None:
        state_type = str(self.type)
        if state_type not in {"pending", "completed"}:
            raise ValueError(f"unsupported completion state type: {self.type}")
        object.__setattr__(self, "type", state_type)
        writes = self.stored_value_writes or {}
        object.__setattr__(
            self,
            "stored_value_writes",
            {str(key): _json_round_trip(value) for key, value in writes.items()},
        )
        if self.error_text is not None:
            object.__setattr__(self, "error_text", str(self.error_text))

    @classmethod
    def pending(cls) -> "CompletionState":
        return cls("pending")

    @classmethod
    def completed(
        cls,
        *,
        stored_value_writes: Mapping[str, JsonValue] | None = None,
        error_text: str | None = None,
    ) -> "CompletionState":
        return cls("completed", stored_value_writes=stored_value_writes, error_text=error_text)

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "CompletionState":
        variant = _external_variant(value, {"Pending", "Completed"})
        if variant is not None:
            name, payload = variant
            if name == "Pending":
                return cls.pending()
            return cls.completed(
                stored_value_writes=payload.get("stored_value_writes"),
                error_text=None if payload.get("error_text") is None else str(payload["error_text"]),
            )
        if value.get("type") == "pending":
            return cls.pending()
        if value.get("type") == "completed":
            return cls.completed(
                stored_value_writes=value.get("stored_value_writes"),
                error_text=None if value.get("error_text") is None else str(value["error_text"]),
            )
        raise ValueError(f"unsupported completion state type: {value.get('type')}")

    def to_mapping(self) -> dict[str, JsonValue]:
        if self.type == "pending":
            return {"type": "pending"}
        return {
            "type": "completed",
            "stored_value_writes": copy.deepcopy(dict(self.stored_value_writes or {})),
            "error_text": self.error_text,
        }


def next_runtime_command(
    command_stream: Iterable[RuntimeCommand | Mapping[str, JsonValue] | None],
    control_stream: Iterable[RuntimeControlCommand | str | None] = (),
    *,
    pending_mode: PendingRuntimeMode | str = PendingRuntimeMode.CONTINUE,
) -> NextRuntimeCommandResult:
    mode = _coerce_pending_runtime_mode(pending_mode)
    commands = iter(command_stream)
    controls = iter(control_stream)
    events: list[RuntimeEvent] = []
    consumed_controls: list[RuntimeControlCommand] = []

    while True:
        command_token = next(commands, _COMMAND_STREAM_DISCONNECTED)
        if command_token is _COMMAND_STREAM_DISCONNECTED:
            return NextRuntimeCommandResult(None, tuple(events), tuple(consumed_controls))
        if command_token is not None:
            return NextRuntimeCommandResult(
                _coerce_runtime_command(command_token),
                tuple(events),
                tuple(consumed_controls),
            )

        events.append(RuntimeEvent.pending())
        if mode is PendingRuntimeMode.CONTINUE:
            command_token = next(commands, _COMMAND_STREAM_DISCONNECTED)
            if command_token is _COMMAND_STREAM_DISCONNECTED or command_token is None:
                return NextRuntimeCommandResult(None, tuple(events), tuple(consumed_controls))
            return NextRuntimeCommandResult(
                _coerce_runtime_command(command_token),
                tuple(events),
                tuple(consumed_controls),
            )

        control_token = next(controls, None)
        if control_token is None:
            return NextRuntimeCommandResult(None, tuple(events), tuple(consumed_controls))
        control = _coerce_runtime_control_command(control_token)
        consumed_controls.append(control)
        if control is RuntimeControlCommand.RESUME:
            continue
        return NextRuntimeCommandResult(
            RuntimeCommand.terminate(),
            tuple(events),
            tuple(consumed_controls),
        )


def _non_negative_int(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("value must be an integer")
    if value < 0:
        raise ValueError("value must be non-negative")
    return value


def _optional_non_negative_int(value: int | None) -> int | None:
    if value is None:
        return None
    return _non_negative_int(value)


def _coerce_nested_tool_call(
    value: CodeModeNestedToolCall | Mapping[str, JsonValue],
) -> CodeModeNestedToolCall:
    if isinstance(value, CodeModeNestedToolCall):
        return value
    if isinstance(value, Mapping):
        return CodeModeNestedToolCall(
            cell_id=str(value["cell_id"]),
            runtime_tool_call_id=str(value.get("runtime_tool_call_id", value.get("id", ""))),
            tool_name=_coerce_tool_name(value.get("tool_name", value.get("name", ""))),
            tool_kind=_coerce_kind(value.get("tool_kind", value.get("kind", CodeModeToolKind.FUNCTION))),
            input=copy.deepcopy(value.get("input")),
        )
    raise TypeError("nested tool call must be a CodeModeNestedToolCall or mapping")


def _nested_tool_call_to_mapping(call: CodeModeNestedToolCall) -> dict[str, JsonValue]:
    return {
        "cell_id": call.cell_id,
        "runtime_tool_call_id": call.runtime_tool_call_id,
        "tool_name": {
            "namespace": call.tool_name.namespace,
            "name": call.tool_name.name,
        },
        "tool_kind": call.tool_kind.value,
        "input": copy.deepcopy(call.input),
    }


def _coerce_execute_request(value: ExecuteRequest | Mapping[str, JsonValue]) -> ExecuteRequest:
    if isinstance(value, ExecuteRequest):
        return value
    if isinstance(value, Mapping):
        return ExecuteRequest(
            cell_id=str(value["cell_id"]),
            tool_call_id=str(value["tool_call_id"]),
            enabled_tools=tuple(value.get("enabled_tools", ())),
            source=str(value["source"]),
            yield_time_ms=(
                None if value.get("yield_time_ms") is None else int(value["yield_time_ms"])
            ),
            max_output_tokens=(
                None
                if value.get("max_output_tokens") is None
                else int(value["max_output_tokens"])
            ),
        )
    raise TypeError("execute request must be an ExecuteRequest or mapping")


def _coerce_wait_request(value: WaitRequest | Mapping[str, JsonValue]) -> WaitRequest:
    if isinstance(value, WaitRequest):
        return value
    if isinstance(value, Mapping):
        return WaitRequest(
            cell_id=str(value["cell_id"]),
            yield_time_ms=(
                DEFAULT_WAIT_YIELD_TIME_MS
                if value.get("yield_time_ms") is None
                else int(value["yield_time_ms"])
            ),
            terminate=bool(value.get("terminate", False)),
        )
    raise TypeError("wait request must be a WaitRequest or mapping")


def _coerce_wait_to_pending_request(
    value: WaitToPendingRequest | Mapping[str, JsonValue],
) -> WaitToPendingRequest:
    if isinstance(value, WaitToPendingRequest):
        return value
    if isinstance(value, Mapping):
        return WaitToPendingRequest(cell_id=str(value["cell_id"]))
    raise TypeError("wait-to-pending request must be a WaitToPendingRequest or mapping")


def _coerce_runtime_response(value: RuntimeResponse | Mapping[str, JsonValue]) -> RuntimeResponse:
    if isinstance(value, RuntimeResponse):
        return value
    if isinstance(value, Mapping):
        return RuntimeResponse.from_mapping(value)
    raise TypeError("runtime response must be a RuntimeResponse or mapping")


def _coerce_wait_outcome(value: WaitOutcome | RuntimeResponse | Mapping[str, JsonValue]) -> WaitOutcome:
    if isinstance(value, WaitOutcome):
        return value
    if isinstance(value, RuntimeResponse):
        return WaitOutcome.live_cell(value)
    if isinstance(value, Mapping):
        variant = _external_variant(value, {"LiveCell", "MissingCell"})
        if variant is not None:
            name, payload = variant
            if name == "LiveCell":
                return WaitOutcome.live_cell(payload)
            return WaitOutcome.missing_cell(payload)
        if value.get("type") == "live_cell":
            return WaitOutcome.live_cell(value["response"])
        if value.get("type") == "missing_cell":
            return WaitOutcome.missing_cell(value["response"])
        return WaitOutcome.live_cell(RuntimeResponse.from_mapping(value))
    raise TypeError("wait outcome must be a WaitOutcome or runtime response")


def _coerce_wait_callback_response(
    value: WaitOutcome | RuntimeResponse | Mapping[str, JsonValue],
) -> RuntimeResponse:
    if isinstance(value, WaitOutcome):
        return value.into_runtime_response()
    if isinstance(value, RuntimeResponse):
        return value
    if isinstance(value, Mapping):
        variant = _external_variant(value, {"LiveCell", "MissingCell"})
        if variant is not None:
            _name, payload = variant
            return _coerce_runtime_response(payload)
        if value.get("type") in {"live_cell", "missing_cell"} and "response" in value:
            return _coerce_runtime_response(value["response"])
        return RuntimeResponse.from_mapping(value)
    raise TypeError("wait callback response must be a wait outcome or runtime response")


def _coerce_execute_to_pending_outcome(
    value: ExecuteToPendingOutcome | Mapping[str, JsonValue],
) -> ExecuteToPendingOutcome:
    if isinstance(value, ExecuteToPendingOutcome):
        return value
    if isinstance(value, Mapping):
        variant = _external_variant(value, {"Pending", "Completed"})
        if variant is not None:
            name, payload = variant
            if name == "Pending":
                return ExecuteToPendingOutcome.pending(
                    cell_id=str(payload["cell_id"]),
                    content_items=tuple(payload.get("content_items", ())),
                    pending_tool_call_ids=tuple(payload.get("pending_tool_call_ids", ())),
                )
            return ExecuteToPendingOutcome.completed(payload)
        if value.get("type") == "pending":
            return ExecuteToPendingOutcome.pending(
                cell_id=str(value["cell_id"]),
                content_items=tuple(value.get("content_items", ())),
                pending_tool_call_ids=tuple(value.get("pending_tool_call_ids", ())),
            )
        if value.get("type") == "completed":
            return ExecuteToPendingOutcome.completed(value["response"])
    raise TypeError("execute-to-pending outcome must be an outcome or mapping")


def _coerce_wait_to_pending_outcome(
    value: WaitToPendingOutcome | ExecuteToPendingOutcome | RuntimeResponse | Mapping[str, JsonValue],
) -> WaitToPendingOutcome:
    if isinstance(value, WaitToPendingOutcome):
        return value
    if isinstance(value, ExecuteToPendingOutcome):
        return WaitToPendingOutcome.live_cell(value)
    if isinstance(value, RuntimeResponse):
        return WaitToPendingOutcome.live_cell(ExecuteToPendingOutcome.completed(value))
    if isinstance(value, Mapping):
        variant = _external_variant(value, {"LiveCell", "MissingCell"})
        if variant is not None:
            name, payload = variant
            if name == "LiveCell":
                return WaitToPendingOutcome.live_cell(payload)
            return WaitToPendingOutcome.missing_cell(payload)
        if value.get("type") == "live_cell":
            return WaitToPendingOutcome.live_cell(value["outcome"])
        if value.get("type") == "missing_cell":
            return WaitToPendingOutcome.missing_cell(value["response"])
        return WaitToPendingOutcome.live_cell(_coerce_execute_to_pending_outcome(value))
    raise TypeError("wait-to-pending outcome must be an outcome or mapping")


def _external_variant(
    value: Mapping[str, JsonValue],
    variants: set[str],
) -> tuple[str, Mapping[str, JsonValue]] | None:
    if len(value) != 1:
        return None
    name, payload = next(iter(value.items()))
    if name not in variants or not isinstance(payload, Mapping):
        return None
    return name, payload


def _coerce_runtime_command(value: RuntimeCommand | Mapping[str, JsonValue]) -> RuntimeCommand:
    if isinstance(value, RuntimeCommand):
        return value
    if isinstance(value, Mapping):
        return RuntimeCommand.from_mapping(value)
    raise TypeError("runtime command must be a RuntimeCommand or mapping")


def _coerce_runtime_control_command(value: RuntimeControlCommand | str) -> RuntimeControlCommand:
    if isinstance(value, RuntimeControlCommand):
        return value
    raw = _ensure_str(value, "runtime control command")
    for candidate in RuntimeControlCommand:
        if raw == candidate.value or raw == candidate.name:
            return candidate
    raise ValueError(f"unsupported runtime control command: {value}")


def _coerce_pending_runtime_mode(value: PendingRuntimeMode | str) -> PendingRuntimeMode:
    if isinstance(value, PendingRuntimeMode):
        return value
    raw = _ensure_str(value, "pending runtime mode")
    for candidate in PendingRuntimeMode:
        if raw == candidate.value or raw == candidate.name:
            return candidate
    raise ValueError(f"unsupported pending runtime mode: {value}")

from .callbacks import build_runtime_tool_call_event

__all__ = [
    "CodeModeNestedToolCall", "CodeModeRuntimeToolState", "CompletionState",
    "DEFAULT_EXEC_YIELD_TIME_MS", "DEFAULT_MAX_OUTPUT_TOKENS_PER_EXEC_CALL",
    "DEFAULT_WAIT_YIELD_TIME_MS", "EXEC_MAIN_MODULE_NAME", "ExecuteRequest",
    "ExecuteToPendingOutcome", "NextRuntimeCommandResult", "PendingRuntimeMode",
    "RuntimeCommand", "RuntimeControlCommand", "RuntimeEvent", "RuntimeResponse",
    "WaitOutcome", "WaitRequest", "WaitToPendingOutcome", "WaitToPendingRequest",
    "next_runtime_command",
]
