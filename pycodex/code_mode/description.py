"""Tool descriptions ported from ``code-mode/src/description.rs``."""
from __future__ import annotations
import copy
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any
from pycodex.protocol import ToolName
JsonValue = Any
_PUBLIC_TOOL_NAME = "exec"
_WAIT_TOOL_NAME = "wait"

def _ensure_str(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    return value


def _ensure_optional_str(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _ensure_str(value, field)


def _ensure_json_like(value: JsonValue, field: str) -> JsonValue:
    try:
        return _json_round_trip(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{field} must be JSON-serializable") from exc


CODE_MODE_PRAGMA_PREFIX = "// @exec:"


MAX_JS_SAFE_INTEGER = (1 << 53) - 1


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
        object.__setattr__(self, "name", _ensure_str(self.name, "name"))
        object.__setattr__(self, "tool_name", _coerce_tool_name(self.tool_name))
        object.__setattr__(self, "description", _ensure_str(self.description, "description"))
        object.__setattr__(self, "kind", _coerce_kind(self.kind))
        object.__setattr__(self, "input_schema", None if self.input_schema is None else _ensure_json_like(self.input_schema, "input_schema"))
        object.__setattr__(self, "output_schema", None if self.output_schema is None else _ensure_json_like(self.output_schema, "output_schema"))

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


# Rust names the public type ``ToolDefinition``.
ToolDefinition = CodeModeToolDefinition


@dataclass(frozen=True)
class ToolNamespaceDescription:
    name: str
    description: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _ensure_str(self.name, "name"))
        object.__setattr__(self, "description", _ensure_str(self.description, "description"))


@dataclass(frozen=True)
class EnabledToolMetadata:
    tool_name: ToolName
    global_name: str
    description: str
    kind: CodeModeToolKind

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_name", _coerce_tool_name(self.tool_name))
        object.__setattr__(self, "global_name", _ensure_str(self.global_name, "global_name"))
        object.__setattr__(self, "description", _ensure_str(self.description, "description"))
        object.__setattr__(self, "kind", _coerce_kind(self.kind))


@dataclass(frozen=True)
class ParsedExecSource:
    code: str
    yield_time_ms: int | None = None
    max_output_tokens: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _ensure_str(self.code, "code"))
        object.__setattr__(self, "yield_time_ms", _optional_non_negative_int(self.yield_time_ms))
        object.__setattr__(self, "max_output_tokens", _optional_non_negative_int(self.max_output_tokens))


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


def is_code_mode_nested_tool(tool_name: str) -> bool:
    return tool_name not in {_PUBLIC_TOOL_NAME, _WAIT_TOOL_NAME}


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
    if definition.name == _PUBLIC_TOOL_NAME:
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


def _coerce_kind(value: CodeModeToolKind | str) -> CodeModeToolKind:
    if isinstance(value, CodeModeToolKind):
        return value
    raw = _ensure_str(value, "code-mode tool kind")
    if raw == "function":
        return CodeModeToolKind.FUNCTION
    if raw == "freeform":
        return CodeModeToolKind.FREEFORM
    raise ValueError(f"unsupported code-mode tool kind: {value}")


def _coerce_tool_name(value: ToolName | Mapping[str, JsonValue] | str) -> ToolName:
    if isinstance(value, Mapping):
        return ToolName.from_mapping(value)
    return ToolName.from_value(value)


def _json_round_trip(value: JsonValue) -> JsonValue:
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")))


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
