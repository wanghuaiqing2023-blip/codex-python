"""Runtime global installation projection ported from ``runtime/globals.rs``."""
from __future__ import annotations
from collections.abc import Iterable, Mapping
from typing import Any
from ..description import CodeModeToolDefinition, EnabledToolMetadata, _coerce_enabled_tool_metadata
JsonValue = Any

RUNTIME_REMOVED_GLOBALS = ("console", "Atomics", "SharedArrayBuffer", "WebAssembly")


RUNTIME_GLOBAL_HELPERS = (
    "clearTimeout",
    "setTimeout",
    "text",
    "image",
    "store",
    "load",
    "notify",
    "yield_control",
    "exit",
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


def build_runtime_globals_projection(
    enabled_tools: Iterable[
        CodeModeToolDefinition | EnabledToolMetadata | Mapping[str, JsonValue]
    ],
) -> dict[str, JsonValue]:
    tools = tuple(_coerce_enabled_tool_metadata(tool) for tool in enabled_tools)
    return {
        "removed_globals": RUNTIME_REMOVED_GLOBALS,
        "helpers": RUNTIME_GLOBAL_HELPERS,
        "tools": {metadata.global_name: str(index) for index, metadata in enumerate(tools)},
        "ALL_TOOLS": build_all_tools_metadata(tools),
    }


def install_globals(
    enabled_tools: Iterable[
        CodeModeToolDefinition | EnabledToolMetadata | Mapping[str, JsonValue]
    ],
) -> dict[str, JsonValue]:
    """Build the isolated global namespace installed by the Rust runtime."""
    return build_runtime_globals_projection(enabled_tools)


__all__ = [
    "RUNTIME_GLOBAL_HELPERS",
    "RUNTIME_REMOVED_GLOBALS",
    "build_all_tools_metadata",
    "build_runtime_globals_projection",
    "install_globals",
]
