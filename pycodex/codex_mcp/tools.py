"""MCP tool metadata and schema shaping from ``codex-mcp/src/tools.rs``."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from typing import Any, Iterable, Mapping

from pycodex.protocol import Tool, ToolName


META_OPENAI_FILE_PARAMS = "openai/fileParams"
MAX_TOOL_NAME_BYTES = 64


@dataclass(frozen=True)
class ToolInfo:
    server_name: str
    callable_name: str
    callable_namespace: str
    tool: Any
    supports_parallel_tool_calls: bool = False
    server_origin: str | None = None
    namespace_description: str | None = None
    connector_id: str | None = None
    connector_name: str | None = None
    plugin_display_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.tool, Tool):
            object.__setattr__(self, "tool", Tool.from_mcp_value(self.tool))
        if not isinstance(self.plugin_display_names, tuple):
            object.__setattr__(
                self,
                "plugin_display_names",
                tuple(self.plugin_display_names),
            )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ToolInfo":
        return cls(
            server_name=str(value["server_name"]),
            supports_parallel_tool_calls=bool(
                value.get("supports_parallel_tool_calls", False)
            ),
            server_origin=_optional_str(value.get("server_origin")),
            callable_name=str(value["callable_name"]),
            callable_namespace=str(value["callable_namespace"]),
            namespace_description=_optional_str(value.get("namespace_description")),
            connector_id=_optional_str(value.get("connector_id")),
            connector_name=_optional_str(value.get("connector_name")),
            plugin_display_names=tuple(
                str(name) for name in value.get("plugin_display_names", ())
            ),
            tool=Tool.from_mcp_value(value["tool"]),
        )

    def canonical_tool_name(self) -> ToolName:
        return ToolName.namespaced(self.callable_namespace, self.callable_name)


def declared_openai_file_input_param_names(
    meta: Mapping[str, Any] | None,
) -> tuple[str, ...]:
    if not isinstance(meta, Mapping):
        return ()
    values = meta.get(META_OPENAI_FILE_PARAMS)
    if not isinstance(values, list):
        return ()
    return tuple(value for value in values if isinstance(value, str) and value)


@dataclass(frozen=True)
class ToolFilter:
    enabled: frozenset[str] | None = None
    disabled: frozenset[str] = frozenset()

    @classmethod
    def from_config(cls, config: Any) -> "ToolFilter":
        enabled_tools = getattr(config, "enabled_tools", None)
        disabled_tools = getattr(config, "disabled_tools", None)
        return cls(
            frozenset(enabled_tools) if enabled_tools is not None else None,
            frozenset(disabled_tools or ()),
        )

    def allows(self, tool_name: str) -> bool:
        return (
            (self.enabled is None or tool_name in self.enabled)
            and tool_name not in self.disabled
        )


def filter_tools(tools: Iterable[ToolInfo], tool_filter: ToolFilter) -> tuple[ToolInfo, ...]:
    return tuple(tool for tool in tools if tool_filter.allows(_raw_tool_name(tool.tool)))


def sanitize_responses_api_tool_name(name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_]", "_", name)
    return sanitized or "_"


def normalize_tools_for_model_with_prefix(
    tools: Iterable[ToolInfo],
    prefix_mcp_tool_names: bool,
) -> tuple[ToolInfo, ...]:
    seen_raw: set[str] = set()
    seen_callable: set[tuple[str, str]] = set()
    normalized: list[ToolInfo] = []
    for tool in tools:
        raw_identity = "\0".join(
            (
                tool.server_name,
                tool.callable_namespace,
                tool.connector_id or "",
                tool.callable_name,
                _raw_tool_name(tool.tool),
            )
        )
        if raw_identity in seen_raw:
            continue
        seen_raw.add(raw_identity)

        namespace = sanitize_responses_api_tool_name(tool.callable_namespace)
        if prefix_mcp_tool_names:
            namespace = f"mcp__{namespace}"
        callable_name = sanitize_responses_api_tool_name(tool.callable_name)
        namespace, callable_name = _fit_callable_parts(namespace, callable_name, raw_identity)
        identity = (namespace, callable_name)
        if identity in seen_callable:
            suffix = hashlib.sha1(raw_identity.encode("utf-8")).hexdigest()[:8]
            callable_name = _truncate_utf8(f"{callable_name}_{suffix}", MAX_TOOL_NAME_BYTES)
            identity = (namespace, callable_name)
        seen_callable.add(identity)
        normalized.append(
            replace(
                tool,
                callable_namespace=namespace,
                callable_name=callable_name,
            )
        )
    return tuple(normalized)


def tool_with_model_visible_input_schema(tool: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(tool)
    meta = result.get("_meta")
    file_params = declared_openai_file_input_param_names(
        meta if isinstance(meta, Mapping) else None
    )
    if not file_params:
        return result
    schema = result.get("inputSchema")
    if not isinstance(schema, Mapping):
        return result
    copied = _copy_mapping(schema)
    properties = copied.get("properties")
    if isinstance(properties, dict):
        for name in file_params:
            if name in properties:
                properties[name] = {
                    "type": "string",
                    "description": "Path to a local file.",
                }
    result["inputSchema"] = copied
    return result


def _copy_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _copy_mapping(item) if isinstance(item, Mapping) else list(item) if isinstance(item, list) else item
        for key, item in value.items()
    }


def _raw_tool_name(tool: Any) -> str:
    if isinstance(tool, Mapping):
        return str(tool.get("name", ""))
    return str(getattr(tool, "name", ""))


def _fit_callable_parts(namespace: str, name: str, raw_identity: str) -> tuple[str, str]:
    if len(namespace.encode()) <= MAX_TOOL_NAME_BYTES and len(name.encode()) <= MAX_TOOL_NAME_BYTES:
        return namespace, name
    suffix = hashlib.sha1(raw_identity.encode("utf-8")).hexdigest()[:8]
    return (
        _truncate_utf8(f"{namespace}_{suffix}", MAX_TOOL_NAME_BYTES),
        _truncate_utf8(f"{name}_{suffix}", MAX_TOOL_NAME_BYTES),
    )


def _truncate_utf8(value: str, limit: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value
    return encoded[:limit].decode("utf-8", errors="ignore")


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


__all__ = [
    "ToolFilter",
    "ToolInfo",
    "declared_openai_file_input_param_names",
    "filter_tools",
    "normalize_tools_for_model_with_prefix",
    "sanitize_responses_api_tool_name",
    "tool_with_model_visible_input_schema",
]
