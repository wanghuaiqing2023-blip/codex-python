"""Python interface for Rust ``codex-code-mode``.

The Rust crate is anchored at ``codex/codex-rs/code-mode``.  This module
mirrors the public interface shape used by ``codex-core`` while keeping the
actual V8 runtime as an explicit unported boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from typing import Any


PUBLIC_TOOL_NAME = "exec"
WAIT_TOOL_NAME = "wait"
CODE_MODE_PRAGMA_PREFIX = "// @exec:"
DEFAULT_EXEC_YIELD_TIME_MS = 10_000
DEFAULT_WAIT_YIELD_TIME_MS = 10_000
DEFAULT_MAX_OUTPUT_TOKENS_PER_EXEC_CALL = 10_000
_MAX_JS_SAFE_INTEGER = (1 << 53) - 1


class CodeModeToolKind(str, Enum):
    FUNCTION = "function"
    FREEFORM = "freeform"


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    tool_name: Any
    description: str
    kind: CodeModeToolKind
    input_schema: Any | None = None
    output_schema: Any | None = None


@dataclass(frozen=True)
class ToolNamespaceDescription:
    name: str
    description: str


@dataclass(frozen=True)
class ParsedExecSource:
    code: str
    yield_time_ms: int | None = None
    max_output_tokens: int | None = None


def parse_exec_source(input: str) -> ParsedExecSource:
    if not input.strip():
        raise ValueError(
            'exec expects raw JavaScript source text (non-empty). Provide JS only, optionally with first-line `// @exec: {"yield_time_ms": 10000, "max_output_tokens": 1000}`.'
        )
    lines = input.split("\n", 1)
    first_line = lines[0]
    rest = lines[1] if len(lines) == 2 else ""
    trimmed = first_line.lstrip()
    if not trimmed.startswith(CODE_MODE_PRAGMA_PREFIX):
        return ParsedExecSource(code=input)
    if not rest.strip():
        raise ValueError("exec pragma must be followed by JavaScript source on subsequent lines")

    directive = trimmed[len(CODE_MODE_PRAGMA_PREFIX) :].strip()
    if not directive:
        raise ValueError(
            "exec pragma must be a JSON object with supported fields `yield_time_ms` and `max_output_tokens`"
        )
    try:
        value = json.loads(directive)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "exec pragma must be valid JSON with supported fields `yield_time_ms` and `max_output_tokens`: "
            + str(exc)
        ) from exc
    if not isinstance(value, dict):
        raise ValueError(
            "exec pragma must be a JSON object with supported fields `yield_time_ms` and `max_output_tokens`"
        )
    for key in value:
        if key not in {"yield_time_ms", "max_output_tokens"}:
            raise ValueError(
                f"exec pragma only supports `yield_time_ms` and `max_output_tokens`; got `{key}`"
            )

    yield_time_ms = _safe_optional_int(value.get("yield_time_ms"), "yield_time_ms")
    max_output_tokens = _safe_optional_int(value.get("max_output_tokens"), "max_output_tokens")
    return ParsedExecSource(
        code=rest,
        yield_time_ms=yield_time_ms,
        max_output_tokens=max_output_tokens,
    )


def _safe_optional_int(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > _MAX_JS_SAFE_INTEGER:
        raise ValueError(f"exec pragma field `{field}` must be a non-negative safe integer")
    return value


def is_code_mode_nested_tool(tool_name: str) -> bool:
    return tool_name not in {PUBLIC_TOOL_NAME, WAIT_TOOL_NAME}


def normalize_code_mode_identifier(tool_key: str) -> str:
    chars: list[str] = []
    for index, ch in enumerate(tool_key):
        if index == 0:
            valid = ch in {"_", "$"} or ch.isascii() and ch.isalpha()
        else:
            valid = ch in {"_", "$"} or ch.isascii() and ch.isalnum()
        chars.append(ch if valid else "_")
    return "".join(chars) or "_"


def augment_tool_definition(definition: ToolDefinition) -> ToolDefinition:
    if definition.name == PUBLIC_TOOL_NAME:
        return definition
    return ToolDefinition(
        name=definition.name,
        tool_name=definition.tool_name,
        description=render_code_mode_sample(definition),
        kind=definition.kind,
        input_schema=definition.input_schema,
        output_schema=definition.output_schema,
    )


def build_exec_tool_description(
    enabled_tools: list[ToolDefinition] | tuple[ToolDefinition, ...] = (),
    namespace_descriptions: dict[str, ToolNamespaceDescription] | None = None,
    code_mode_only: bool = False,
    deferred_tools_available: bool = False,
) -> str:
    description = "Run JavaScript code to orchestrate/compose tool calls"
    if deferred_tools_available:
        description += "\n\nSome nested MCP/app tools may be omitted from this description."
    if code_mode_only and enabled_tools:
        description += "\n\n" + "\n\n".join(render_code_mode_sample(tool) for tool in enabled_tools)
    return description


def build_wait_tool_description() -> str:
    return "- Use `wait` only after `exec` returns `Script running with cell ID ...`."


def render_code_mode_sample(definition: ToolDefinition) -> str:
    global_name = normalize_code_mode_identifier(definition.name)
    if definition.kind is CodeModeToolKind.FREEFORM:
        return f"await tools.{global_name}(...)"
    return f"await tools.{global_name}({{ ... }})"


def render_json_schema_to_typescript(schema: Any) -> str:
    if isinstance(schema, dict) and schema.get("type") == "object":
        properties = schema.get("properties") or {}
        if isinstance(properties, dict):
            body = "\n".join(f"  {name}: unknown;" for name in properties)
            return "{\n" + body + "\n}"
    return "unknown"


class ImageDetail(str, Enum):
    AUTO = "auto"
    LOW = "low"
    HIGH = "high"
    ORIGINAL = "original"


DEFAULT_IMAGE_DETAIL = ImageDetail.HIGH


@dataclass(frozen=True)
class FunctionCallOutputContentItem:
    type: str
    text: str | None = None
    image_url: str | None = None
    detail: ImageDetail | None = None


@dataclass(frozen=True)
class ExecuteRequest:
    code: str
    yield_time_ms: int = DEFAULT_EXEC_YIELD_TIME_MS
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS_PER_EXEC_CALL


@dataclass(frozen=True)
class WaitRequest:
    cell_id: str
    yield_time_ms: int = DEFAULT_WAIT_YIELD_TIME_MS
    max_tokens: int | None = None
    terminate: bool = False


@dataclass(frozen=True)
class WaitToPendingRequest:
    cell_id: str


@dataclass(frozen=True)
class CodeModeNestedToolCall:
    name: str
    input: Any


@dataclass(frozen=True)
class RuntimeResponse:
    content: tuple[FunctionCallOutputContentItem, ...] = ()
    pending_cell_id: str | None = None


class WaitOutcome(str, Enum):
    COMPLETE = "complete"
    YIELDED = "yielded"
    TERMINATED = "terminated"


class ExecuteToPendingOutcome(str, Enum):
    COMPLETE = "complete"
    PENDING = "pending"


class WaitToPendingOutcome(str, Enum):
    COMPLETE = "complete"
    PENDING = "pending"


class CodeModeService:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs

    async def execute(self, request: ExecuteRequest) -> RuntimeResponse:
        raise NotImplementedError("codex-code-mode V8 runtime is not ported")


class CodeModeTurnHost:
    pass


class CodeModeTurnWorker:
    pass
