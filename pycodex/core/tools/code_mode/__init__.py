"""Core code-mode integration ported from ``core/src/tools/code_mode/mod.rs``."""
from __future__ import annotations
import copy
import json
from collections.abc import Iterable, Mapping
from typing import Any, Callable
from pycodex.protocol import ToolName
from pycodex.code_mode import *
from pycodex.code_mode import (
    DEFAULT_WAIT_YIELD_TIME_MS,
    PUBLIC_TOOL_NAME,
    WAIT_TOOL_NAME,
    CodeModeService as _CodeModeService,
)
from pycodex.code_mode.description import CodeModeToolDefinition, CodeModeToolKind, EnabledToolMetadata, ParsedExecSource, ToolNamespaceDescription, _coerce_code_mode_tool_definition, _coerce_kind, augment_tool_definition, code_mode_namespace_name, is_code_mode_nested_tool, sort_code_mode_tool_definitions
from pycodex.code_mode.runtime import *
from pycodex.code_mode.runtime import _coerce_runtime_response
from pycodex.code_mode.runtime.callbacks import CodeModeRuntimeStore, RUNTIME_TOOL_CALL_ID_PREFIX, U64_MAX, build_runtime_image_event, build_runtime_notify_event, build_runtime_text_event, build_runtime_tool_call_event, build_runtime_yield_event, completion_state_from_exit, next_runtime_tool_call_sequence, normalize_notify_text, normalize_runtime_tool_input, normalize_store_key, runtime_exit_exception, runtime_tool_call_id, runtime_tool_index_from_callback_data, serialize_stored_value
from pycodex.code_mode.runtime.globals import RUNTIME_GLOBAL_HELPERS, RUNTIME_REMOVED_GLOBALS, build_all_tools_metadata, build_runtime_globals_projection
from pycodex.code_mode.runtime.module_loader import EXIT_SENTINEL, UNSUPPORTED_DYNAMIC_IMPORT_ERROR, completion_state_from_rejection, is_exit_exception, is_exit_sentinel, unsupported_dynamic_import_error, unsupported_static_import_error
from pycodex.code_mode.runtime.timers import clear_timeout_id_from_value, normalize_timeout_delay_ms
from pycodex.code_mode.runtime.value import CODEX_IMAGE_DETAIL_META_KEY, IMAGE_HELPER_EXPECTS_MESSAGE, normalize_output_image, serialize_output_text, value_to_error_text
from pycodex.code_mode.service import CodeModeExecuteCallback, CodeModeExecuteToPendingCallback, CodeModeWaitCallback, CodeModeWaitToPendingCallback, PendingResult, missing_cell_response, pending_result_response
JsonValue = Any
CellIdAllocator = Callable[[], str]


class CodeModeService(_CodeModeService):
    def allocate_cell_id(self) -> str:
        return super().allocate_cell_id()

    def execute(self, request: Any) -> Any:
        return super().execute(request)

    def wait(self, request: Any) -> Any:
        return super().wait(request)


def is_exec_tool_name(tool_name: ToolName) -> bool:
    return tool_name.namespace is None and tool_name.name == PUBLIC_TOOL_NAME


def build_nested_tool_payload(
    tool_kind: CodeModeToolKind | str,
    tool_name: ToolName,
    input: JsonValue | None,
) -> Any:
    kind = _coerce_kind(tool_kind)
    if kind is CodeModeToolKind.FUNCTION:
        return _build_function_tool_payload(tool_name, input)
    return _build_freeform_tool_payload(tool_name, input)


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


def _build_function_tool_payload(tool_name: ToolName, input: JsonValue | None) -> Any:
    from pycodex.core.tools.context import ToolPayload

    arguments = _serialize_function_tool_arguments(tool_name, input)
    return ToolPayload.function(arguments)


def _serialize_function_tool_arguments(tool_name: ToolName, input: JsonValue | None) -> str:
    if input is None:
        return "{}"
    if isinstance(input, Mapping):
        return json.dumps(input, ensure_ascii=False, separators=(",", ":"))
    raise ValueError(f"tool `{tool_name}` expects a JSON object for arguments")


def _build_freeform_tool_payload(tool_name: ToolName, input: JsonValue | None) -> Any:
    from pycodex.core.tools.context import ToolPayload

    if isinstance(input, str):
        return ToolPayload.custom(input)
    raise ValueError(f"tool `{tool_name}` expects a string input")


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


from .execute_spec import CODE_MODE_FREEFORM_GRAMMAR, create_code_mode_tool
from .wait_handler import CodeModeWaitHandler, ExecWaitArgs, parse_wait_arguments
from .wait_spec import create_wait_tool
from .response_adapter import format_script_status, handle_runtime_response, into_function_call_output_content_items, script_status_header, truncate_code_mode_result
from .execute_handler import CodeModeExecuteHandler

__all__ = [name for name in globals() if not name.startswith("_") and name not in {"Any", "Callable", "Iterable", "Mapping", "copy", "json"}]
