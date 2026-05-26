"""Code-mode tool definition helpers ported from Codex core."""

from __future__ import annotations

import copy
import json
import math
import time
import uuid
from collections.abc import Iterable, Mapping
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pycodex.protocol import FunctionCallOutputContentItem, ImageDetail, ToolName
from pycodex.protocol import DEFAULT_IMAGE_DETAIL

JsonValue = Any
CellIdAllocator = Callable[[], str]
CODEX_IMAGE_DETAIL_META_KEY = "codex/imageDetail"
IMAGE_HELPER_EXPECTS_MESSAGE = (
    "image expects a non-empty image URL string, an object with image_url and optional detail, "
    "or a raw MCP image block"
)

PUBLIC_TOOL_NAME = "exec"
WAIT_TOOL_NAME = "wait"
CODE_MODE_PRAGMA_PREFIX = "// @exec:"
MAX_JS_SAFE_INTEGER = (1 << 53) - 1
DEFAULT_EXEC_YIELD_TIME_MS = 10_000
DEFAULT_WAIT_YIELD_TIME_MS = 10_000
DEFAULT_MAX_OUTPUT_TOKENS_PER_EXEC_CALL = 10_000
U64_MAX = (1 << 64) - 1
EXIT_SENTINEL = "__codex_code_mode_exit__"
EXEC_MAIN_MODULE_NAME = "exec_main.mjs"
UNSUPPORTED_DYNAMIC_IMPORT_ERROR = "unsupported import in exec"
RUNTIME_TOOL_CALL_ID_PREFIX = "tool-"
_COMMAND_STREAM_DISCONNECTED = object()

CODE_MODE_FREEFORM_GRAMMAR = """
start: pragma_source | plain_source
pragma_source: PRAGMA_LINE NEWLINE SOURCE
plain_source: SOURCE

PRAGMA_LINE: /[ \\t]*\\/\\/ @exec:[^\\r\\n]*/
NEWLINE: /\\r?\\n/
SOURCE: /[\\s\\S]+/
"""

DEFERRED_NESTED_TOOLS_GUIDANCE = (
    "Some nested MCP/app tools may be omitted from this description. They are "
    "still available on the global `tools` object and listed in `ALL_TOOLS`.\n"
    "To find one, filter `ALL_TOOLS` by `name` and `description`."
)

EXEC_DESCRIPTION_TEMPLATE = """Run JavaScript code to orchestrate/compose tool calls
- Evaluates the provided JavaScript code in a fresh V8 isolate as an async module.
- All nested tools are available on the global `tools` object.
- Nested tool methods take either a string or an object as their input argument.
- Nested tools return either an object or a string, based on the description.
- Runs raw JavaScript -- no Node, no file system, no network access, no console.
- Accepts raw JavaScript source text, not JSON, quoted strings, or markdown code fences.
- You may optionally start the tool input with a first-line pragma like `// @exec: {"yield_time_ms": 10000, "max_output_tokens": 1000}`.
- `yield_time_ms` asks `exec` to yield early after that many milliseconds if the script is still running.
- `max_output_tokens` sets the token budget for direct `exec` results.
- `setTimeout(callback: () => void, delayMs?: number)`: schedules a callback to run later and returns a timeout id. Pending timeouts do not keep `exec` alive by themselves; await an explicit promise if you need to wait for one.
- `clearTimeout(timeoutId?: number)`: cancels a timeout created by `setTimeout`.
- `ALL_TOOLS`: metadata for the enabled nested tools as `{ name, description }` entries.
- `yield_control()`: yields the accumulated output to the model immediately while the script keeps running."""

WAIT_DESCRIPTION_TEMPLATE = """- Use `wait` only after `exec` returns `Script running with cell ID ...`.
- `cell_id` identifies the running `exec` cell to resume.
- `yield_time_ms` controls how long to wait for more output before yielding again.
- `max_tokens` limits how much new output this wait call returns.
- `terminate: true` stops the running cell instead of waiting for more output.
- `wait` returns only the new output since the last yield, or the final completion or termination result for that cell.
- If the cell is still running, `wait` may yield again with the same `cell_id`.
- If the cell has already finished, `wait` returns the completed result and closes the cell."""

MCP_TYPESCRIPT_PREAMBLE = """type Role = "user" | "assistant";
type MetaObject = Record<string, unknown>;
type ContentBlock = { type: string; [key: string]: unknown };
type CallToolResult<TStructured = { [key: string]: unknown }> = {
  _meta?: MetaObject;
  content: ContentBlock[];
  isError?: boolean;
  structuredContent?: TStructured;
  [key: string]: unknown;
};"""


class CodeModeToolKind(str, Enum):
    FUNCTION = "function"
    FREEFORM = "freeform"


@dataclass(frozen=True)
class CodeModeToolDefinition:
    name: str
    tool_name: ToolName
    description: str
    kind: CodeModeToolKind
    input_schema: JsonValue | None = None
    output_schema: JsonValue | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", str(self.name))
        object.__setattr__(self, "tool_name", _coerce_tool_name(self.tool_name))
        object.__setattr__(self, "description", str(self.description))
        object.__setattr__(self, "kind", _coerce_kind(self.kind))
        object.__setattr__(self, "input_schema", copy.deepcopy(self.input_schema))
        object.__setattr__(self, "output_schema", copy.deepcopy(self.output_schema))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "name": self.name,
            "tool_name": {
                "namespace": self.tool_name.namespace,
                "name": self.tool_name.name,
            },
            "description": self.description,
            "kind": self.kind.value,
            "input_schema": copy.deepcopy(self.input_schema),
            "output_schema": copy.deepcopy(self.output_schema),
        }


@dataclass(frozen=True)
class ToolNamespaceDescription:
    name: str
    description: str


@dataclass(frozen=True)
class EnabledToolMetadata:
    tool_name: ToolName
    global_name: str
    description: str
    kind: CodeModeToolKind

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_name", _coerce_tool_name(self.tool_name))
        object.__setattr__(self, "global_name", str(self.global_name))
        object.__setattr__(self, "description", str(self.description))
        object.__setattr__(self, "kind", _coerce_kind(self.kind))


@dataclass(frozen=True)
class ParsedExecSource:
    code: str
    yield_time_ms: int | None = None
    max_output_tokens: int | None = None


@dataclass(frozen=True)
class ExecWaitArgs:
    cell_id: str
    yield_time_ms: int = DEFAULT_WAIT_YIELD_TIME_MS
    max_tokens: int | None = None
    terminate: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "cell_id", str(self.cell_id))
        object.__setattr__(self, "yield_time_ms", _non_negative_int(self.yield_time_ms))
        object.__setattr__(self, "max_tokens", _optional_non_negative_int(self.max_tokens))
        object.__setattr__(self, "terminate", bool(self.terminate))


@dataclass(frozen=True)
class ExecuteRequest:
    cell_id: str
    tool_call_id: str
    enabled_tools: tuple[CodeModeToolDefinition, ...]
    source: str
    yield_time_ms: int | None = None
    max_output_tokens: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "cell_id", str(self.cell_id))
        object.__setattr__(self, "tool_call_id", str(self.tool_call_id))
        object.__setattr__(
            self,
            "enabled_tools",
            tuple(_coerce_code_mode_tool_definition(tool) for tool in self.enabled_tools),
        )
        object.__setattr__(self, "source", str(self.source))
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
        object.__setattr__(self, "cell_id", str(self.cell_id))
        object.__setattr__(self, "yield_time_ms", _non_negative_int(self.yield_time_ms))
        object.__setattr__(self, "terminate", bool(self.terminate))


@dataclass(frozen=True)
class WaitToPendingRequest:
    cell_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "cell_id", str(self.cell_id))


@dataclass(frozen=True)
class RuntimeResponse:
    type: str
    cell_id: str
    content_items: tuple[FunctionCallOutputContentItem, ...] = ()
    error_text: str | None = None

    def __post_init__(self) -> None:
        response_type = str(self.type)
        if response_type not in {"yielded", "terminated", "result"}:
            raise ValueError(f"unsupported runtime response type: {self.type}")
        object.__setattr__(self, "type", response_type)
        object.__setattr__(self, "cell_id", str(self.cell_id))
        object.__setattr__(
            self,
            "content_items",
            tuple(FunctionCallOutputContentItem.from_mapping(item) for item in self.content_items),
        )
        if self.error_text is not None:
            object.__setattr__(self, "error_text", str(self.error_text))
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
class PendingResult:
    content_items: tuple[FunctionCallOutputContentItem, ...] = ()
    error_text: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "content_items",
            tuple(FunctionCallOutputContentItem.from_mapping(item) for item in self.content_items),
        )
        if self.error_text is not None:
            object.__setattr__(self, "error_text", str(self.error_text))


@dataclass(frozen=True)
class WaitOutcome:
    type: str
    response: RuntimeResponse

    def __post_init__(self) -> None:
        outcome_type = str(self.type)
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
        outcome_type = str(self.type)
        if outcome_type not in {"pending", "completed"}:
            raise ValueError(f"unsupported execute-to-pending outcome type: {self.type}")
        object.__setattr__(self, "type", outcome_type)
        if self.cell_id is not None:
            object.__setattr__(self, "cell_id", str(self.cell_id))
        object.__setattr__(
            self,
            "content_items",
            tuple(FunctionCallOutputContentItem.from_mapping(item) for item in self.content_items),
        )
        object.__setattr__(
            self,
            "pending_tool_call_ids",
            tuple(str(call_id) for call_id in self.pending_tool_call_ids),
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
        outcome_type = str(self.type)
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
        object.__setattr__(self, "runtime_tool_call_id", str(self.runtime_tool_call_id))
        object.__setattr__(self, "tool_name", _coerce_tool_name(self.tool_name))
        object.__setattr__(self, "tool_kind", _coerce_kind(self.tool_kind))
        object.__setattr__(self, "input", copy.deepcopy(self.input))


@dataclass
class CodeModeRuntimeStore:
    stored_values: dict[str, JsonValue] = field(default_factory=dict)
    stored_value_writes: dict[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.stored_values = {
            str(key): _json_round_trip(value) for key, value in self.stored_values.items()
        }
        self.stored_value_writes = {
            str(key): _json_round_trip(value) for key, value in self.stored_value_writes.items()
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


CodeModeExecuteCallback = Callable[[ExecuteRequest], RuntimeResponse | Mapping[str, JsonValue]]
CodeModeWaitCallback = Callable[[WaitRequest], WaitOutcome | RuntimeResponse | Mapping[str, JsonValue]]
CodeModeExecuteToPendingCallback = Callable[
    [ExecuteRequest],
    ExecuteToPendingOutcome | RuntimeResponse | Mapping[str, JsonValue],
]
CodeModeWaitToPendingCallback = Callable[
    [WaitToPendingRequest],
    WaitToPendingOutcome | ExecuteToPendingOutcome | RuntimeResponse | Mapping[str, JsonValue],
]


def parse_exec_source(input: str) -> ParsedExecSource:
    if input.strip() == "":
        raise ValueError(
            "exec expects raw JavaScript source text (non-empty). Provide JS only, "
            "optionally with first-line `// @exec: {\"yield_time_ms\": 10000, "
            "\"max_output_tokens\": 1000}`."
        )

    first_line, separator, rest = input.partition("\n")
    trimmed = first_line.lstrip()
    if not trimmed.startswith(CODE_MODE_PRAGMA_PREFIX):
        return ParsedExecSource(code=input)

    if separator == "" or rest.strip() == "":
        raise ValueError("exec pragma must be followed by JavaScript source on subsequent lines")

    directive = trimmed[len(CODE_MODE_PRAGMA_PREFIX) :].strip()
    if directive == "":
        raise ValueError(
            "exec pragma must be a JSON object with supported fields `yield_time_ms` "
            "and `max_output_tokens`"
        )

    try:
        value = json.loads(directive)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "exec pragma must be valid JSON with supported fields `yield_time_ms` "
            f"and `max_output_tokens`: {exc}"
        ) from exc

    if not isinstance(value, dict):
        raise ValueError(
            "exec pragma must be a JSON object with supported fields `yield_time_ms` "
            "and `max_output_tokens`"
        )

    for key in value:
        if key not in {"yield_time_ms", "max_output_tokens"}:
            raise ValueError(
                "exec pragma only supports `yield_time_ms` and `max_output_tokens`; "
                f"got `{key}`"
            )

    yield_time_ms = _safe_integer_pragma_field(value, "yield_time_ms")
    max_output_tokens = _safe_integer_pragma_field(value, "max_output_tokens")
    return ParsedExecSource(
        code=rest,
        yield_time_ms=yield_time_ms,
        max_output_tokens=max_output_tokens,
    )


def parse_wait_arguments(arguments: str) -> ExecWaitArgs:
    try:
        value = json.loads(arguments)
    except json.JSONDecodeError as exc:
        raise ValueError(f"failed to parse function arguments: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ValueError("failed to parse function arguments: expected JSON object")
    if "cell_id" not in value:
        raise ValueError("failed to parse function arguments: missing field `cell_id`")
    return ExecWaitArgs(
        cell_id=str(value["cell_id"]),
        yield_time_ms=_wait_argument_int(value, "yield_time_ms", DEFAULT_WAIT_YIELD_TIME_MS),
        max_tokens=(
            None
            if value.get("max_tokens") is None
            else _wait_argument_int(value, "max_tokens", DEFAULT_WAIT_YIELD_TIME_MS)
        ),
        terminate=bool(value.get("terminate", False)),
    )


def missing_cell_response(cell_id: str) -> RuntimeResponse:
    return RuntimeResponse.result(
        cell_id=str(cell_id),
        error_text=f"exec cell {cell_id} not found",
    )


def pending_result_response(cell_id: str, result: PendingResult | Mapping[str, JsonValue]) -> RuntimeResponse:
    pending_result = _coerce_pending_result(result)
    return RuntimeResponse.result(
        cell_id=str(cell_id),
        content_items=pending_result.content_items,
        error_text=pending_result.error_text,
    )


def serialize_output_text(value: JsonValue) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float | str):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(value)


def normalize_output_image(
    value: JsonValue,
    detail_override: str | ImageDetail | None = None,
) -> FunctionCallOutputContentItem:
    image_url, detail = _parse_output_image(value)
    if image_url == "":
        raise ValueError(IMAGE_HELPER_EXPECTS_MESSAGE)
    lower = image_url.lower()
    if not (lower.startswith("http://") or lower.startswith("https://") or lower.startswith("data:")):
        raise ValueError("image expects an http(s) or data URL")

    normalized_detail = _normalize_image_detail(detail_override if detail_override is not None else detail)
    return FunctionCallOutputContentItem.input_image(
        image_url,
        normalized_detail or DEFAULT_IMAGE_DETAIL,
    )


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


def normalize_timeout_delay_ms(value: JsonValue | None = None) -> int:
    number = _js_number_value(value)
    if number is None or not math.isfinite(number) or number <= 0.0:
        return 0
    return min(math.trunc(number), U64_MAX)


def clear_timeout_id_from_value(value: JsonValue | None = None) -> int | None:
    if value is None:
        return None
    number = _js_number_value(value)
    if number is None:
        raise ValueError("clearTimeout expects a numeric timeout id")
    if not math.isfinite(number) or number <= 0.0:
        return None
    return min(math.trunc(number), U64_MAX)


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


def is_exit_sentinel(value: JsonValue) -> bool:
    return isinstance(value, str) and value == EXIT_SENTINEL


def is_exit_exception(exit_requested: bool, exception: JsonValue) -> bool:
    return bool(exit_requested) and is_exit_sentinel(exception)


def value_to_error_text(value: JsonValue) -> str:
    if isinstance(value, Mapping):
        stack = value.get("stack")
        if isinstance(stack, str):
            return stack
    return serialize_output_text(value)


def completion_state_from_rejection(
    exception: JsonValue,
    *,
    exit_requested: bool,
    stored_value_writes: Mapping[str, JsonValue] | None = None,
) -> CompletionState:
    return CompletionState.completed(
        stored_value_writes=stored_value_writes,
        error_text=(
            None
            if is_exit_exception(exit_requested, exception)
            else value_to_error_text(exception)
        ),
    )


def unsupported_static_import_error(specifier: str) -> str:
    return f"Unsupported import in exec: {specifier}"


def unsupported_dynamic_import_error() -> str:
    return UNSUPPORTED_DYNAMIC_IMPORT_ERROR


def runtime_tool_index_from_callback_data(value: JsonValue) -> int:
    text = str(value)
    if text == "" or not text.isdecimal():
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


def is_code_mode_nested_tool(tool_name: str) -> bool:
    return tool_name not in {PUBLIC_TOOL_NAME, WAIT_TOOL_NAME}


def is_exec_tool_name(tool_name: ToolName) -> bool:
    return tool_name.namespace is None and tool_name.name == PUBLIC_TOOL_NAME


def format_script_status(response: RuntimeResponse | Mapping[str, JsonValue]) -> str:
    runtime_response = _coerce_runtime_response(response)
    if runtime_response.type == "yielded":
        return f"Script running with cell ID {runtime_response.cell_id}"
    if runtime_response.type == "terminated":
        return "Script terminated"
    if runtime_response.error_text is None:
        return "Script completed"
    return "Script failed"


def script_status_header(status: str, wall_time_seconds: float) -> str:
    rounded_seconds = round(float(wall_time_seconds), 1)
    return f"{status}\nWall time {rounded_seconds:.1f} seconds\nOutput:\n"


def build_nested_tool_payload(
    tool_kind: CodeModeToolKind | str,
    tool_name: ToolName,
    input: JsonValue | None,
) -> Any:
    kind = _coerce_kind(tool_kind)
    if kind is CodeModeToolKind.FUNCTION:
        return _build_function_tool_payload(tool_name, input)
    return _build_freeform_tool_payload(tool_name, input)


def create_code_mode_tool(
    enabled_tools: Iterable[CodeModeToolDefinition | Mapping[str, JsonValue]] = (),
    namespace_descriptions: Mapping[str, ToolNamespaceDescription | Mapping[str, str]] | None = None,
    *,
    code_mode_only: bool,
    deferred_tools_available: bool,
) -> Any:
    from pycodex.core.hosted_spec import FreeformToolFormat, ToolSpec

    definitions = tuple(_coerce_code_mode_tool_definition(tool) for tool in enabled_tools)
    return ToolSpec.freeform(
        name=PUBLIC_TOOL_NAME,
        description=build_exec_tool_description(
            definitions,
            namespace_descriptions,
            code_mode_only=code_mode_only,
            deferred_tools_available=deferred_tools_available,
        ),
        format=FreeformToolFormat.grammar(
            syntax="lark",
            definition=CODE_MODE_FREEFORM_GRAMMAR,
        ),
    )


def create_wait_tool() -> dict[str, JsonValue]:
    return {
        "type": "function",
        "name": WAIT_TOOL_NAME,
        "description": (
            f"Waits on a yielded `{PUBLIC_TOOL_NAME}` cell and returns new output or completion.\n"
            f"{build_wait_tool_description().strip()}"
        ),
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "cell_id": {
                    "type": "string",
                    "description": "Identifier of the running exec cell.",
                },
                "yield_time_ms": {
                    "type": "number",
                    "description": (
                        "How long to wait (in milliseconds) for more output before yielding again."
                    ),
                },
                "max_tokens": {
                    "type": "number",
                    "description": "Maximum number of output tokens to return for this wait call.",
                },
                "terminate": {
                    "type": "boolean",
                    "description": "Whether to terminate the running exec cell.",
                },
            },
            "required": ["cell_id"],
            "additionalProperties": False,
        },
    }


def into_function_call_output_content_items(
    items: Iterable[FunctionCallOutputContentItem | Mapping[str, JsonValue]],
) -> tuple[FunctionCallOutputContentItem, ...]:
    return tuple(_into_function_call_output_content_item(item) for item in items)


def handle_runtime_response(
    response: RuntimeResponse | Mapping[str, JsonValue],
    *,
    max_output_tokens: int | None,
    wall_time_seconds: float,
    can_request_original_detail: bool = True,
) -> Any:
    from pycodex.core.original_image_detail import sanitize_original_image_detail
    from pycodex.core.tool_context import FunctionToolOutput

    runtime_response = _coerce_runtime_response(response)
    script_status = format_script_status(runtime_response)
    content_items = into_function_call_output_content_items(runtime_response.content_items)
    content_items = sanitize_original_image_detail(can_request_original_detail, content_items)

    if runtime_response.type == "result":
        success = runtime_response.error_text is None
        if runtime_response.error_text is not None:
            content_items = (
                *content_items,
                FunctionCallOutputContentItem.input_text(
                    f"Script error:\n{runtime_response.error_text}"
                ),
            )
    else:
        success = True

    content_items = truncate_code_mode_result(content_items, max_output_tokens)
    content_items = (
        FunctionCallOutputContentItem.input_text(
            script_status_header(script_status, wall_time_seconds)
        ),
        *content_items,
    )
    return FunctionToolOutput.from_content(content_items, success)


def truncate_code_mode_result(
    items: Iterable[FunctionCallOutputContentItem | Mapping[str, JsonValue]],
    max_output_tokens: int | None,
) -> tuple[FunctionCallOutputContentItem, ...]:
    from pycodex.core.tool_context import (
        formatted_truncate_text_content_items_with_policy,
        truncate_function_output_items_with_policy,
    )
    from pycodex.core.unified_exec import resolve_max_tokens
    from pycodex.protocol import TruncationPolicyConfig

    content_items = tuple(FunctionCallOutputContentItem.from_mapping(item) for item in items)
    policy = TruncationPolicyConfig.tokens(resolve_max_tokens(max_output_tokens))
    if all(item.type == "input_text" for item in content_items):
        truncated_items, _original_token_count = formatted_truncate_text_content_items_with_policy(
            content_items,
            policy,
        )
        return truncated_items
    return truncate_function_output_items_with_policy(content_items, policy)


class CodeModeService:
    def __init__(
        self,
        *,
        execute_callback: CodeModeExecuteCallback | None = None,
        wait_callback: CodeModeWaitCallback | None = None,
        execute_to_pending_callback: CodeModeExecuteToPendingCallback | None = None,
        wait_to_pending_callback: CodeModeWaitToPendingCallback | None = None,
    ) -> None:
        self._next_cell_id = 1
        self.execute_callback = execute_callback
        self.wait_callback = wait_callback
        self.execute_to_pending_callback = execute_to_pending_callback
        self.wait_to_pending_callback = wait_to_pending_callback

    def allocate_cell_id(self) -> str:
        cell_id = str(self._next_cell_id)
        self._next_cell_id += 1
        return cell_id

    def execute(self, request: ExecuteRequest | Mapping[str, JsonValue]) -> RuntimeResponse:
        if self.execute_callback is None:
            raise ValueError("code-mode execute callback is not configured")
        return _coerce_runtime_response(self.execute_callback(_coerce_execute_request(request)))

    def execute_to_pending(
        self,
        request: ExecuteRequest | Mapping[str, JsonValue],
    ) -> ExecuteToPendingOutcome:
        if self.execute_to_pending_callback is not None:
            return _coerce_execute_to_pending_outcome(
                self.execute_to_pending_callback(_coerce_execute_request(request))
            )
        return ExecuteToPendingOutcome.completed(self.execute(_coerce_execute_request(request)))

    def wait(self, request: WaitRequest | Mapping[str, JsonValue]) -> WaitOutcome:
        wait_request = _coerce_wait_request(request)
        if self.wait_callback is None:
            return WaitOutcome.missing_cell(missing_cell_response(wait_request.cell_id))
        return _coerce_wait_outcome(self.wait_callback(wait_request))

    def wait_to_pending(
        self,
        request: WaitToPendingRequest | Mapping[str, JsonValue],
    ) -> WaitToPendingOutcome:
        wait_request = _coerce_wait_to_pending_request(request)
        if self.wait_to_pending_callback is None:
            return WaitToPendingOutcome.missing_cell(missing_cell_response(wait_request.cell_id))
        return _coerce_wait_to_pending_outcome(self.wait_to_pending_callback(wait_request))


@dataclass(frozen=True)
class CodeModeExecuteHandler:
    nested_tool_specs: tuple[Mapping[str, JsonValue] | Any, ...] = ()
    namespace_descriptions: Mapping[str, ToolNamespaceDescription | Mapping[str, str]] | None = None
    code_mode_only: bool = False
    deferred_tools_available: bool = False
    execute_callback: CodeModeExecuteCallback | None = None
    cell_id_allocator: CellIdAllocator | None = None
    can_request_original_detail: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "nested_tool_specs", tuple(self.nested_tool_specs))

    def tool_name(self) -> ToolName:
        return ToolName.plain(PUBLIC_TOOL_NAME)

    def spec(self) -> Any:
        enabled_tools = sort_code_mode_tool_definitions(
            collect_code_mode_tool_definitions(self.nested_tool_specs),
            self.namespace_descriptions,
        )
        return create_code_mode_tool(
            enabled_tools,
            self.namespace_descriptions,
            code_mode_only=self.code_mode_only,
            deferred_tools_available=self.deferred_tools_available,
        )

    def matches_kind(self, payload: Any) -> bool:
        return getattr(payload, "type", None) == "custom"

    def handle(self, invocation_or_payload: Any) -> Any:
        from pycodex.core.tool_context import ToolPayload

        payload = getattr(invocation_or_payload, "payload", invocation_or_payload)
        tool_name = getattr(invocation_or_payload, "tool_name", self.tool_name())
        call_id = str(getattr(invocation_or_payload, "call_id", ""))
        if (
            not isinstance(payload, ToolPayload)
            or payload.type != "custom"
            or not is_exec_tool_name(tool_name)
            or payload.input is None
        ):
            raise ValueError(f"{PUBLIC_TOOL_NAME} expects raw JavaScript source text")
        if self.execute_callback is None:
            raise ValueError("code-mode execute callback is not configured")

        parsed = parse_exec_source(payload.input)
        request = ExecuteRequest(
            cell_id=self._allocate_cell_id(),
            tool_call_id=call_id,
            enabled_tools=collect_code_mode_tool_definitions(self.nested_tool_specs),
            source=parsed.code,
            yield_time_ms=parsed.yield_time_ms,
            max_output_tokens=parsed.max_output_tokens,
        )
        started_at = time.perf_counter()
        response = _coerce_runtime_response(self.execute_callback(request))
        return handle_runtime_response(
            response,
            max_output_tokens=parsed.max_output_tokens,
            wall_time_seconds=time.perf_counter() - started_at,
            can_request_original_detail=self.can_request_original_detail,
        )

    def _allocate_cell_id(self) -> str:
        if self.cell_id_allocator is not None:
            return str(self.cell_id_allocator())
        return str(uuid.uuid4())


@dataclass(frozen=True)
class CodeModeWaitHandler:
    wait_callback: CodeModeWaitCallback | None = None
    can_request_original_detail: bool = True

    def tool_name(self) -> ToolName:
        return ToolName.plain(WAIT_TOOL_NAME)

    def spec(self) -> dict[str, JsonValue]:
        return copy.deepcopy(create_wait_tool())

    def matches_kind(self, payload: Any) -> bool:
        return getattr(payload, "type", None) == "function"

    def pre_tool_use_payload(self, _invocation: Any) -> None:
        return None

    def post_tool_use_payload(self, _invocation: Any, _result: Any) -> None:
        return None

    def handle(self, invocation_or_payload: Any) -> Any:
        from pycodex.core.tool_context import ToolPayload

        payload = getattr(invocation_or_payload, "payload", invocation_or_payload)
        tool_name = getattr(invocation_or_payload, "tool_name", self.tool_name())
        if (
            not isinstance(payload, ToolPayload)
            or payload.type != "function"
            or tool_name.namespace is not None
            or tool_name.name != WAIT_TOOL_NAME
            or payload.arguments is None
        ):
            raise ValueError(f"{WAIT_TOOL_NAME} expects JSON arguments")
        if self.wait_callback is None:
            raise ValueError("code-mode wait callback is not configured")

        args = parse_wait_arguments(payload.arguments)
        request = WaitRequest(
            cell_id=args.cell_id,
            yield_time_ms=args.yield_time_ms,
            terminate=args.terminate,
        )
        started_at = time.perf_counter()
        response = _coerce_wait_callback_response(self.wait_callback(request))
        return handle_runtime_response(
            response,
            max_output_tokens=args.max_tokens,
            wall_time_seconds=time.perf_counter() - started_at,
            can_request_original_detail=self.can_request_original_detail,
        )


def normalize_code_mode_identifier(tool_key: str) -> str:
    identifier = []
    for index, char in enumerate(tool_key):
        if index == 0:
            is_valid = char == "_" or char == "$" or char.isascii() and char.isalpha()
        else:
            is_valid = char == "_" or char == "$" or char.isascii() and char.isalnum()
        identifier.append(char if is_valid else "_")
    return "".join(identifier) or "_"


def augment_tool_definition(definition: CodeModeToolDefinition) -> CodeModeToolDefinition:
    if definition.name == PUBLIC_TOOL_NAME:
        return definition
    return CodeModeToolDefinition(
        name=definition.name,
        tool_name=definition.tool_name,
        description=_render_code_mode_sample_for_definition(definition),
        kind=definition.kind,
        input_schema=definition.input_schema,
        output_schema=definition.output_schema,
    )


def enabled_tool_metadata(definition: CodeModeToolDefinition) -> EnabledToolMetadata:
    return EnabledToolMetadata(
        tool_name=definition.tool_name,
        global_name=normalize_code_mode_identifier(definition.name),
        description=definition.description,
        kind=definition.kind,
    )


def build_all_tools_metadata(
    enabled_tools: Iterable[
        CodeModeToolDefinition | EnabledToolMetadata | Mapping[str, JsonValue]
    ],
) -> tuple[dict[str, str], ...]:
    return tuple(
        {"name": metadata.global_name, "description": metadata.description}
        for metadata in (_coerce_enabled_tool_metadata(tool) for tool in enabled_tools)
    )


def code_mode_namespace_name(
    tool: CodeModeToolDefinition | Mapping[str, JsonValue],
    namespace_descriptions: Mapping[str, ToolNamespaceDescription | Mapping[str, str]] | None,
) -> str | None:
    definition = _coerce_code_mode_tool_definition(tool)
    namespace = definition.tool_name.namespace
    if namespace is None:
        return None
    if namespace_descriptions is None or namespace not in namespace_descriptions:
        return None
    return _coerce_namespace_description(namespace_descriptions[namespace]).name


def sort_code_mode_tool_definitions(
    definitions: Iterable[CodeModeToolDefinition | Mapping[str, JsonValue]],
    namespace_descriptions: Mapping[str, ToolNamespaceDescription | Mapping[str, str]] | None = None,
) -> tuple[CodeModeToolDefinition, ...]:
    descriptions = namespace_descriptions or {}

    def sort_key(definition: CodeModeToolDefinition) -> tuple[int, str, str, str]:
        namespace = code_mode_namespace_name(definition, descriptions)
        return (
            0 if namespace is None else 1,
            namespace or "",
            definition.tool_name.name,
            definition.name,
        )

    return tuple(
        sorted(
            (_coerce_code_mode_tool_definition(definition) for definition in definitions),
            key=sort_key,
        )
    )


def render_code_mode_sample(
    description: str,
    tool_name: str,
    input_name: str,
    input_type: str,
    output_type: str,
) -> str:
    declaration = (
        "declare const tools: { "
        f"{_render_code_mode_tool_declaration(tool_name, input_name, input_type, output_type)}"
        " };"
    )
    return f"{description}\n\nexec tool declaration:\n```ts\n{declaration}\n```"


def render_json_schema_to_typescript(schema: JsonValue) -> str:
    return _render_json_schema_to_typescript_inner(schema)


def build_exec_tool_description(
    enabled_tools: Iterable[CodeModeToolDefinition],
    namespace_descriptions: Mapping[str, ToolNamespaceDescription | Mapping[str, str]] | None = None,
    *,
    code_mode_only: bool,
    deferred_tools_available: bool,
) -> str:
    sections = [EXEC_DESCRIPTION_TEMPLATE]
    if deferred_tools_available:
        sections.append(DEFERRED_NESTED_TOOLS_GUIDANCE)
    if not code_mode_only:
        return "\n\n".join(sections)

    descriptions = namespace_descriptions or {}
    tools = tuple(enabled_tools)
    if tools:
        current_namespace: str | None = None
        nested_sections: list[str] = []
        has_mcp_tools = any(
            _mcp_structured_content_schema(tool.output_schema) is not None for tool in tools
        )

        for tool in tools:
            namespace_description = (
                _coerce_namespace_description(descriptions.get(tool.tool_name.namespace))
                if tool.tool_name.namespace is not None
                else None
            )
            next_namespace = namespace_description.name if namespace_description is not None else None
            if next_namespace != current_namespace:
                if namespace_description is not None:
                    text = namespace_description.description.strip()
                    if text:
                        nested_sections.append(f"## {namespace_description.name}\n{text}")
                current_namespace = next_namespace

            global_name = normalize_code_mode_identifier(tool.name)
            nested_description = _render_code_mode_sample_for_definition(tool).strip()
            heading = _render_tool_heading(global_name, tool.name)
            nested_sections.append(
                heading if not nested_description else f"{heading}\n{nested_description}"
            )

        if has_mcp_tools:
            sections.append(f"Shared MCP Types:\n```ts\n{MCP_TYPESCRIPT_PREAMBLE}\n```")
        sections.append("\n\n".join(nested_sections))

    return "\n\n".join(sections)


def build_wait_tool_description() -> str:
    return WAIT_DESCRIPTION_TEMPLATE


def code_mode_name_for_tool_name(tool_name: ToolName) -> str:
    if tool_name.namespace is None:
        return tool_name.name
    if tool_name.namespace.endswith("_") or tool_name.name.startswith("_"):
        return f"{tool_name.namespace}{tool_name.name}"
    return f"{tool_name.namespace}_{tool_name.name}"


def augment_tool_spec_for_code_mode(spec: Mapping[str, JsonValue] | Any) -> dict[str, JsonValue]:
    data = copy.deepcopy(_spec_mapping(spec))
    spec_type = data.get("type")
    if spec_type in {"function", "custom", "freeform"}:
        description = _augmented_description_for_spec(data)
        if description is not None:
            data["description"] = description
        return data

    if spec_type == "namespace":
        namespace = str(data.get("name", ""))
        tools = data.get("tools", ())
        if isinstance(tools, list):
            for tool in tools:
                if not isinstance(tool, dict) or tool.get("type") != "function":
                    continue
                tool_name = ToolName.namespaced(namespace, str(tool.get("name", "")))
                definition = CodeModeToolDefinition(
                    name=code_mode_name_for_tool_name(tool_name),
                    tool_name=tool_name,
                    description=str(tool.get("description", "")),
                    kind=CodeModeToolKind.FUNCTION,
                    input_schema=copy.deepcopy(tool.get("parameters")),
                    output_schema=copy.deepcopy(tool.get("output_schema")),
                )
                tool["description"] = augment_tool_definition(definition).description
        return data

    return data


def tool_spec_to_code_mode_tool_definition(
    spec: Mapping[str, JsonValue] | Any,
) -> CodeModeToolDefinition | None:
    definition = _code_mode_tool_definition_for_spec(spec)
    if definition is None or not is_code_mode_nested_tool(definition.name):
        return None
    return augment_tool_definition(definition)


def collect_code_mode_tool_definitions(
    specs: Iterable[Mapping[str, JsonValue] | Any],
) -> tuple[CodeModeToolDefinition, ...]:
    definitions = (
        augment_tool_definition(definition)
        for spec in specs
        for definition in code_mode_tool_definitions_for_spec(spec)
        if is_code_mode_nested_tool(definition.name)
    )
    return _sort_and_dedup_tool_definitions(definitions)


def collect_code_mode_exec_prompt_tool_definitions(
    specs: Iterable[Mapping[str, JsonValue] | Any],
) -> tuple[CodeModeToolDefinition, ...]:
    definitions = (
        definition
        for spec in specs
        for definition in code_mode_tool_definitions_for_spec(spec)
        if is_code_mode_nested_tool(definition.name)
    )
    return _sort_and_dedup_tool_definitions(definitions)


def code_mode_tool_definitions_for_spec(
    spec: Mapping[str, JsonValue] | Any,
) -> tuple[CodeModeToolDefinition, ...]:
    data = _spec_mapping(spec)
    spec_type = data.get("type")
    if spec_type == "function":
        name = str(data.get("name", ""))
        return (
            CodeModeToolDefinition(
                tool_name=ToolName.plain(name),
                name=name,
                description=str(data.get("description", "")),
                kind=CodeModeToolKind.FUNCTION,
                input_schema=copy.deepcopy(data.get("parameters")),
                output_schema=copy.deepcopy(data.get("output_schema")),
            ),
        )

    if spec_type in {"custom", "freeform"}:
        name = str(data.get("name", ""))
        return (
            CodeModeToolDefinition(
                tool_name=ToolName.plain(name),
                name=name,
                description=str(data.get("description", "")),
                kind=CodeModeToolKind.FREEFORM,
            ),
        )

    if spec_type == "namespace":
        namespace = str(data.get("name", ""))
        definitions = []
        for tool in data.get("tools", ()):
            if not isinstance(tool, Mapping) or tool.get("type") != "function":
                continue
            tool_name = ToolName.namespaced(namespace, str(tool.get("name", "")))
            definitions.append(
                CodeModeToolDefinition(
                    name=code_mode_name_for_tool_name(tool_name),
                    tool_name=tool_name,
                    description=str(tool.get("description", "")),
                    kind=CodeModeToolKind.FUNCTION,
                    input_schema=copy.deepcopy(tool.get("parameters")),
                    output_schema=copy.deepcopy(tool.get("output_schema")),
                )
            )
        return tuple(definitions)

    return ()


def _safe_integer_pragma_field(value: Mapping[str, JsonValue], field: str) -> int | None:
    if field not in value or value[field] is None:
        return None
    raw = value[field]
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError(
            "exec pragma fields `yield_time_ms` and `max_output_tokens` must be "
            "non-negative safe integers"
        )
    if raw < 0 or raw > MAX_JS_SAFE_INTEGER:
        raise ValueError(f"exec pragma field `{field}` must be a non-negative safe integer")
    return raw


def _wait_argument_int(
    value: Mapping[str, JsonValue],
    field: str,
    default: int,
) -> int:
    if field not in value:
        return default
    raw = value[field]
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise ValueError(f"failed to parse function arguments: field `{field}` must be a number")
    if int(raw) != raw:
        raise ValueError(f"failed to parse function arguments: field `{field}` must be an integer")
    try:
        return _non_negative_int(int(raw))
    except ValueError as exc:
        raise ValueError(
            f"failed to parse function arguments: field `{field}` must be non-negative"
        ) from exc


def _non_negative_int(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("value must be a non-negative integer")
    return value


def _optional_non_negative_int(value: int | None) -> int | None:
    if value is None:
        return None
    return _non_negative_int(value)


def _coerce_code_mode_tool_definition(
    value: CodeModeToolDefinition | Mapping[str, JsonValue],
) -> CodeModeToolDefinition:
    if isinstance(value, CodeModeToolDefinition):
        return value
    if isinstance(value, Mapping):
        return CodeModeToolDefinition(
            name=str(value["name"]),
            tool_name=_coerce_tool_name(value.get("tool_name", value["name"])),
            description=str(value.get("description", "")),
            kind=_coerce_kind(value.get("kind", CodeModeToolKind.FUNCTION)),
            input_schema=copy.deepcopy(value.get("input_schema")),
            output_schema=copy.deepcopy(value.get("output_schema")),
        )
    raise TypeError("code-mode tool definition must be a mapping")


def _coerce_enabled_tool_metadata(
    value: CodeModeToolDefinition | EnabledToolMetadata | Mapping[str, JsonValue],
) -> EnabledToolMetadata:
    if isinstance(value, EnabledToolMetadata):
        return value
    if isinstance(value, CodeModeToolDefinition):
        return enabled_tool_metadata(value)
    if isinstance(value, Mapping):
        return EnabledToolMetadata(
            tool_name=value["tool_name"],
            global_name=str(value["global_name"]),
            description=str(value.get("description", "")),
            kind=_coerce_kind(value["kind"]),
        )
    raise TypeError(
        "enabled tool metadata must be a CodeModeToolDefinition, EnabledToolMetadata, or mapping"
    )


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


def _coerce_pending_result(value: PendingResult | Mapping[str, JsonValue]) -> PendingResult:
    if isinstance(value, PendingResult):
        return value
    if isinstance(value, Mapping):
        return PendingResult(
            content_items=tuple(value.get("content_items", ())),
            error_text=None if value.get("error_text") is None else str(value.get("error_text")),
        )
    raise TypeError("pending result must be a PendingResult or mapping")


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
    normalized = str(value)
    for candidate in RuntimeControlCommand:
        if normalized == candidate.value or normalized == candidate.name:
            return candidate
    raise ValueError(f"unsupported runtime control command: {value}")


def _coerce_pending_runtime_mode(value: PendingRuntimeMode | str) -> PendingRuntimeMode:
    if isinstance(value, PendingRuntimeMode):
        return value
    normalized = str(value)
    for candidate in PendingRuntimeMode:
        if normalized == candidate.value or normalized == candidate.name:
            return candidate
    raise ValueError(f"unsupported pending runtime mode: {value}")


def _coerce_kind(value: CodeModeToolKind | str) -> CodeModeToolKind:
    if isinstance(value, CodeModeToolKind):
        return value
    raw = str(value).lower()
    if raw == "function":
        return CodeModeToolKind.FUNCTION
    if raw == "freeform":
        return CodeModeToolKind.FREEFORM
    raise ValueError(f"unsupported code-mode tool kind: {value}")


def _coerce_tool_name(value: ToolName | Mapping[str, JsonValue] | str) -> ToolName:
    if isinstance(value, ToolName):
        return value
    if isinstance(value, Mapping):
        namespace = value.get("namespace")
        return ToolName.new(None if namespace is None else str(namespace), str(value["name"]))
    return ToolName.plain(str(value))


def _parse_output_image(value: JsonValue) -> tuple[str, str | ImageDetail | None]:
    if isinstance(value, str):
        return value, None
    if isinstance(value, Mapping):
        parsed = _parse_non_mcp_output_image(value)
        if parsed is not None:
            return parsed
        return _parse_mcp_output_image(value)
    raise ValueError(IMAGE_HELPER_EXPECTS_MESSAGE)


def _parse_non_mcp_output_image(
    value: Mapping[str, JsonValue],
) -> tuple[str, str | ImageDetail | None] | None:
    if "image_url" not in value:
        return None
    image_url = value["image_url"]
    if not isinstance(image_url, str):
        raise ValueError(IMAGE_HELPER_EXPECTS_MESSAGE)
    detail = _parse_image_detail_value(value.get("detail"))
    return image_url, detail


def _parse_mcp_output_image(value: Mapping[str, JsonValue]) -> tuple[str, str | None]:
    item_type = value.get("type")
    if not isinstance(item_type, str):
        raise ValueError(IMAGE_HELPER_EXPECTS_MESSAGE)
    if item_type != "image":
        raise ValueError(f'image only accepts MCP image blocks, got "{item_type}"')

    data = value.get("data")
    if not isinstance(data, str) or data == "":
        raise ValueError("image expected MCP image data")

    if data.lower().startswith("data:"):
        image_url = data
    else:
        mime_type = value.get("mimeType", value.get("mime_type"))
        if not isinstance(mime_type, str) or mime_type == "":
            mime_type = "application/octet-stream"
        image_url = f"data:{mime_type};base64,{data}"

    meta = value.get("_meta")
    detail = None
    if isinstance(meta, Mapping):
        raw_detail = meta.get(CODEX_IMAGE_DETAIL_META_KEY)
        if isinstance(raw_detail, str) and raw_detail in {"high", "original"}:
            detail = raw_detail
    return image_url, detail


def _parse_image_detail_value(value: JsonValue) -> str | ImageDetail | None:
    if value is None:
        return None
    if isinstance(value, ImageDetail):
        return value
    if isinstance(value, str):
        return value
    raise ValueError("image detail must be a string when provided")


def _normalize_image_detail(value: str | ImageDetail | None) -> ImageDetail | None:
    if value is None:
        return None
    if isinstance(value, ImageDetail):
        return value
    normalized = value.lower()
    if normalized == "high":
        return ImageDetail.HIGH
    if normalized == "original":
        return ImageDetail.ORIGINAL
    raise ValueError("image detail must be one of: high, original")


def _js_number_value(value: JsonValue | None) -> float | None:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            return 0.0
        try:
            return float(text)
        except ValueError:
            return math.nan
    return None


def _json_round_trip(value: JsonValue) -> JsonValue:
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")))


def _into_function_call_output_content_item(
    item: FunctionCallOutputContentItem | Mapping[str, JsonValue],
) -> FunctionCallOutputContentItem:
    content_item = FunctionCallOutputContentItem.from_mapping(item)
    if content_item.type == "input_image":
        return FunctionCallOutputContentItem.input_image(
            content_item.image_url or "",
            content_item.detail or DEFAULT_IMAGE_DETAIL,
        )
    return content_item


def _build_function_tool_payload(tool_name: ToolName, input: JsonValue | None) -> Any:
    from pycodex.core.tool_context import ToolPayload

    arguments = _serialize_function_tool_arguments(tool_name, input)
    return ToolPayload.function(arguments)


def _serialize_function_tool_arguments(tool_name: ToolName, input: JsonValue | None) -> str:
    if input is None:
        return "{}"
    if isinstance(input, Mapping):
        return json.dumps(input, ensure_ascii=False, separators=(",", ":"))
    raise ValueError(f"tool `{tool_name}` expects a JSON object for arguments")


def _build_freeform_tool_payload(tool_name: ToolName, input: JsonValue | None) -> Any:
    from pycodex.core.tool_context import ToolPayload

    if isinstance(input, str):
        return ToolPayload.custom(input)
    raise ValueError(f"tool `{tool_name}` expects a string input")


def _coerce_namespace_description(
    value: ToolNamespaceDescription | Mapping[str, str] | None,
) -> ToolNamespaceDescription | None:
    if value is None:
        return None
    if isinstance(value, ToolNamespaceDescription):
        return value
    return ToolNamespaceDescription(
        name=str(value.get("name", "")),
        description=str(value.get("description", "")),
    )


def _spec_mapping(spec: Mapping[str, JsonValue] | Any) -> Mapping[str, JsonValue]:
    if isinstance(spec, Mapping):
        return spec
    to_mapping = getattr(spec, "to_mapping", None)
    if callable(to_mapping):
        value = to_mapping()
        if isinstance(value, Mapping):
            return value
    raise TypeError("tool spec must be a mapping or expose to_mapping()")


def _augmented_description_for_spec(spec: Mapping[str, JsonValue] | Any) -> str | None:
    definition = _code_mode_tool_definition_for_spec(spec)
    if definition is None:
        return None
    return augment_tool_definition(definition).description


def _code_mode_tool_definition_for_spec(
    spec: Mapping[str, JsonValue] | Any,
) -> CodeModeToolDefinition | None:
    definitions = code_mode_tool_definitions_for_spec(spec)
    return definitions[0] if definitions else None


def _sort_and_dedup_tool_definitions(
    definitions: Iterable[CodeModeToolDefinition],
) -> tuple[CodeModeToolDefinition, ...]:
    sorted_definitions = sorted(definitions, key=lambda definition: definition.name)
    deduped: list[CodeModeToolDefinition] = []
    seen: set[str] = set()
    for definition in sorted_definitions:
        if definition.name in seen:
            continue
        deduped.append(definition)
        seen.add(definition.name)
    return tuple(deduped)


def _render_code_mode_sample_for_definition(definition: CodeModeToolDefinition) -> str:
    input_name = "args" if definition.kind is CodeModeToolKind.FUNCTION else "input"
    if definition.kind is CodeModeToolKind.FUNCTION:
        input_type = (
            render_json_schema_to_typescript(definition.input_schema)
            if definition.input_schema is not None
            else "unknown"
        )
    else:
        input_type = "string"

    structured_content_schema = _mcp_structured_content_schema(definition.output_schema)
    if structured_content_schema is not None:
        structured_content_type = render_json_schema_to_typescript(structured_content_schema)
        output_type = (
            "CallToolResult"
            if structured_content_type == "unknown"
            else f"CallToolResult<{structured_content_type}>"
        )
    elif definition.output_schema is not None:
        output_type = render_json_schema_to_typescript(definition.output_schema)
    else:
        output_type = "unknown"

    return render_code_mode_sample(
        definition.description,
        definition.name,
        input_name,
        input_type,
        output_type,
    )


def _render_code_mode_tool_declaration(
    tool_name: str,
    input_name: str,
    input_type: str,
    output_type: str,
) -> str:
    name = normalize_code_mode_identifier(tool_name)
    return f"{name}({input_name}: {input_type}): Promise<{output_type}>;"


def _render_tool_heading(global_name: str, raw_name: str) -> str:
    if global_name == raw_name:
        return f"### `{global_name}`"
    return f"### `{global_name}` (`{raw_name}`)"


def _mcp_structured_content_schema(output_schema: JsonValue | None) -> JsonValue | None:
    if not isinstance(output_schema, Mapping):
        return None
    properties = output_schema.get("properties")
    if not isinstance(properties, Mapping):
        return None
    content_schema = properties.get("content")
    if not isinstance(content_schema, Mapping) or content_schema.get("type") != "array":
        return None
    items = content_schema.get("items")
    if not isinstance(items, Mapping) or items.get("type") != "object":
        return None
    is_error_schema = properties.get("isError")
    if not isinstance(is_error_schema, Mapping) or is_error_schema.get("type") != "boolean":
        return None
    meta_schema = properties.get("_meta")
    if not isinstance(meta_schema, Mapping) or meta_schema.get("type") != "object":
        return None
    return properties.get("structuredContent", True)


def _render_json_schema_to_typescript_inner(schema: JsonValue) -> str:
    if schema is True:
        return "unknown"
    if schema is False:
        return "never"
    if not isinstance(schema, Mapping):
        return "unknown"

    if "const" in schema:
        return _render_json_schema_literal(schema["const"])

    enum_values = schema.get("enum")
    if isinstance(enum_values, list):
        if not enum_values:
            return "never"
        return " | ".join(_render_json_schema_literal(value) for value in enum_values)

    for key, separator in (("anyOf", " | "), ("oneOf", " | "), ("allOf", " & ")):
        values = schema.get(key)
        if isinstance(values, list):
            rendered = [_render_json_schema_to_typescript_inner(value) for value in values]
            if rendered:
                return separator.join(rendered)

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        rendered_types = [
            _render_json_schema_type_keyword(schema, value)
            for value in schema_type
            if isinstance(value, str)
        ]
        return " | ".join(rendered_types) if rendered_types else "unknown"
    if isinstance(schema_type, str):
        return _render_json_schema_type_keyword(schema, schema_type)

    if "properties" in schema or "additionalProperties" in schema:
        return _render_json_schema_object(schema)
    if "items" in schema or "prefixItems" in schema:
        return _render_json_schema_array(schema)
    return "unknown"


def _render_json_schema_type_keyword(schema: Mapping[str, JsonValue], schema_type: str) -> str:
    if schema_type == "string":
        return "string"
    if schema_type in {"number", "integer"}:
        return "number"
    if schema_type == "boolean":
        return "boolean"
    if schema_type == "null":
        return "null"
    if schema_type == "array":
        return _render_json_schema_array(schema)
    if schema_type == "object":
        return _render_json_schema_object(schema)
    return "unknown"


def _render_json_schema_array(schema: Mapping[str, JsonValue]) -> str:
    if "items" in schema:
        item_type = _render_json_schema_to_typescript_inner(schema["items"])
        return f"Array<{item_type}>"

    prefix_items = schema.get("prefixItems")
    if isinstance(prefix_items, list):
        item_types = [_render_json_schema_to_typescript_inner(item) for item in prefix_items]
        if item_types:
            return f"[{', '.join(item_types)}]"

    return "unknown[]"


def _append_additional_properties_line(
    lines: list[str],
    schema: Mapping[str, JsonValue],
    properties: Mapping[str, JsonValue],
    line_prefix: str,
) -> None:
    if "additionalProperties" in schema:
        additional_properties = schema["additionalProperties"]
        if additional_properties is True:
            property_type = "unknown"
        elif additional_properties is False:
            property_type = None
        else:
            property_type = _render_json_schema_to_typescript_inner(additional_properties)
        if property_type is not None:
            lines.append(f"{line_prefix}[key: string]: {property_type};")
    elif not properties:
        lines.append(f"{line_prefix}[key: string]: unknown;")


def _has_property_description(value: JsonValue) -> bool:
    return (
        isinstance(value, Mapping)
        and isinstance(value.get("description"), str)
        and value.get("description") != ""
    )


def _render_json_schema_object_property(
    name: str,
    value: JsonValue,
    required: Iterable[str],
) -> str:
    required_names = tuple(required)
    optional = "" if name in required_names else "?"
    property_name = _render_json_schema_property_name(name)
    property_type = _render_json_schema_to_typescript_inner(value)
    return f"{property_name}{optional}: {property_type};"


def _render_json_schema_object(schema: Mapping[str, JsonValue]) -> str:
    raw_required = schema.get("required")
    required = (
        tuple(value for value in raw_required if isinstance(value, str))
        if isinstance(raw_required, list)
        else ()
    )
    raw_properties = schema.get("properties")
    properties: Mapping[str, JsonValue] = raw_properties if isinstance(raw_properties, Mapping) else {}
    sorted_properties = sorted(properties.items(), key=lambda item: str(item[0]))

    if any(_has_property_description(value) for _, value in sorted_properties):
        lines = ["{"]
        for name, value in sorted_properties:
            if isinstance(value, Mapping) and isinstance(value.get("description"), str):
                for description_line in (
                    line.strip() for line in value["description"].splitlines()
                ):
                    if description_line:
                        lines.append(f"  // {description_line}")
            lines.append(f"  {_render_json_schema_object_property(str(name), value, required)}")
        _append_additional_properties_line(lines, schema, properties, "  ")
        lines.append("}")
        return "\n".join(lines)

    lines = [
        _render_json_schema_object_property(str(name), value, required)
        for name, value in sorted_properties
    ]
    _append_additional_properties_line(lines, schema, properties, "")
    if not lines:
        return "{}"
    return f"{{ {' '.join(lines)} }}"


def _render_json_schema_property_name(name: str) -> str:
    if normalize_code_mode_identifier(name) == name:
        return name
    return _render_json_schema_literal(name)


def _render_json_schema_literal(value: JsonValue) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


__all__ = [
    "CODE_MODE_PRAGMA_PREFIX",
    "CODE_MODE_FREEFORM_GRAMMAR",
    "CODEX_IMAGE_DETAIL_META_KEY",
    "CodeModeToolDefinition",
    "CodeModeToolKind",
    "CodeModeNestedToolCall",
    "CodeModeExecuteCallback",
    "CodeModeExecuteToPendingCallback",
    "CodeModeExecuteHandler",
    "CodeModeRuntimeStore",
    "CodeModeService",
    "CodeModeWaitCallback",
    "CodeModeWaitHandler",
    "CodeModeWaitToPendingCallback",
    "CompletionState",
    "CodeModeRuntimeToolState",
    "DEFAULT_EXEC_YIELD_TIME_MS",
    "DEFAULT_MAX_OUTPUT_TOKENS_PER_EXEC_CALL",
    "DEFAULT_WAIT_YIELD_TIME_MS",
    "EnabledToolMetadata",
    "ExecWaitArgs",
    "ExecuteRequest",
    "ExecuteToPendingOutcome",
    "EXEC_MAIN_MODULE_NAME",
    "EXIT_SENTINEL",
    "IMAGE_HELPER_EXPECTS_MESSAGE",
    "NextRuntimeCommandResult",
    "PendingResult",
    "PendingRuntimeMode",
    "ParsedExecSource",
    "PUBLIC_TOOL_NAME",
    "RuntimeCommand",
    "RuntimeControlCommand",
    "RuntimeEvent",
    "RuntimeResponse",
    "RUNTIME_TOOL_CALL_ID_PREFIX",
    "ToolNamespaceDescription",
    "WAIT_TOOL_NAME",
    "U64_MAX",
    "UNSUPPORTED_DYNAMIC_IMPORT_ERROR",
    "WaitOutcome",
    "WaitRequest",
    "WaitToPendingOutcome",
    "WaitToPendingRequest",
    "augment_tool_definition",
    "augment_tool_spec_for_code_mode",
    "build_all_tools_metadata",
    "build_exec_tool_description",
    "build_nested_tool_payload",
    "build_runtime_image_event",
    "build_runtime_notify_event",
    "build_runtime_text_event",
    "build_runtime_tool_call_event",
    "build_runtime_yield_event",
    "build_wait_tool_description",
    "code_mode_namespace_name",
    "code_mode_name_for_tool_name",
    "code_mode_tool_definitions_for_spec",
    "collect_code_mode_exec_prompt_tool_definitions",
    "collect_code_mode_tool_definitions",
    "clear_timeout_id_from_value",
    "completion_state_from_exit",
    "completion_state_from_rejection",
    "create_code_mode_tool",
    "create_wait_tool",
    "enabled_tool_metadata",
    "is_code_mode_nested_tool",
    "is_exec_tool_name",
    "is_exit_exception",
    "is_exit_sentinel",
    "format_script_status",
    "handle_runtime_response",
    "into_function_call_output_content_items",
    "missing_cell_response",
    "next_runtime_command",
    "next_runtime_tool_call_sequence",
    "normalize_code_mode_identifier",
    "normalize_output_image",
    "normalize_notify_text",
    "normalize_runtime_tool_input",
    "normalize_store_key",
    "normalize_timeout_delay_ms",
    "pending_result_response",
    "parse_exec_source",
    "parse_wait_arguments",
    "render_code_mode_sample",
    "render_json_schema_to_typescript",
    "runtime_tool_call_id",
    "runtime_tool_index_from_callback_data",
    "runtime_exit_exception",
    "script_status_header",
    "serialize_output_text",
    "serialize_stored_value",
    "sort_code_mode_tool_definitions",
    "unsupported_dynamic_import_error",
    "unsupported_static_import_error",
    "value_to_error_text",
    "tool_spec_to_code_mode_tool_definition",
    "truncate_code_mode_result",
]
