"""Code-mode helpers for the ``codex-rs/tools/src/code_mode.rs`` boundary."""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from typing import Any

from pycodex.core.tools.code_mode import (
    CodeModeToolDefinition,
    CodeModeToolKind,
    augment_tool_definition,
    is_code_mode_nested_tool,
)
from pycodex.protocol import ToolName

JsonValue = Any


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
        definitions: list[CodeModeToolDefinition] = []
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


def code_mode_name_for_tool_name(tool_name: ToolName) -> str:
    if tool_name.namespace is None:
        return tool_name.name
    if tool_name.namespace.endswith("_") or tool_name.name.startswith("_"):
        return f"{tool_name.namespace}{tool_name.name}"
    return f"{tool_name.namespace}__{tool_name.name}"


def _augmented_description_for_spec(spec: Mapping[str, JsonValue]) -> str | None:
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
    deduped: list[CodeModeToolDefinition] = []
    seen: set[str] = set()
    for definition in sorted(definitions, key=lambda item: item.name):
        if definition.name in seen:
            continue
        deduped.append(definition)
        seen.add(definition.name)
    return tuple(deduped)


def _spec_mapping(spec: Mapping[str, JsonValue] | Any) -> dict[str, JsonValue]:
    if hasattr(spec, "to_mapping"):
        spec = spec.to_mapping()
    if not isinstance(spec, Mapping):
        raise TypeError("tool spec must be a mapping or expose to_mapping()")
    return dict(spec)


__all__ = [
    "augment_tool_spec_for_code_mode",
    "code_mode_name_for_tool_name",
    "code_mode_tool_definitions_for_spec",
    "collect_code_mode_exec_prompt_tool_definitions",
    "collect_code_mode_tool_definitions",
    "tool_spec_to_code_mode_tool_definition",
]
