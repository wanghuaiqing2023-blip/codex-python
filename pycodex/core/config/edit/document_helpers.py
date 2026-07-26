"""TOML document helpers from ``config::edit::document_helpers``."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from enum import Enum
from typing import Any


def ensure_table_for_write(item: Any) -> MutableMapping[str, Any] | None:
    """Return a mutable table when the Python TOML item is table-shaped."""

    return item if isinstance(item, MutableMapping) else None


def ensure_table_for_read(item: Any) -> MutableMapping[str, Any] | None:
    """Return an existing mutable table without replacing scalar values."""

    return item if isinstance(item, MutableMapping) else None


def serialize_mcp_server(config: Any) -> dict[str, Any]:
    """Serialize an MCP server using the same omission rules as Rust."""

    transport = _field(config, "transport")
    kind = str(_field(transport, "kind", "")).lower()
    entry: dict[str, Any] = {}
    if kind == "stdio":
        command = _field(transport, "command")
        if command is not None:
            entry["command"] = str(command)
        args = tuple(_field(transport, "args", ()) or ())
        if args:
            entry["args"] = [str(arg) for arg in args]
        env = _field(transport, "env")
        if isinstance(env, Mapping) and env:
            entry["env"] = _sorted_string_mapping(env)
        env_vars = tuple(_field(transport, "env_vars", ()) or ())
        if env_vars:
            entry["env_vars"] = [_serialize_env_var(value) for value in env_vars]
        cwd = _field(transport, "cwd")
        if cwd is not None:
            entry["cwd"] = str(cwd)
    elif kind in {"streamable_http", "streamablehttp"}:
        url = _field(transport, "url")
        if url is not None:
            entry["url"] = str(url)
        bearer = _field(transport, "bearer_token_env_var")
        if bearer is not None:
            entry["bearer_token_env_var"] = str(bearer)
        http_headers = _field(transport, "http_headers")
        if isinstance(http_headers, Mapping) and http_headers:
            entry["http_headers"] = _sorted_string_mapping(http_headers)
        env_http_headers = _field(transport, "env_http_headers")
        if isinstance(env_http_headers, Mapping) and env_http_headers:
            entry["env_http_headers"] = _sorted_string_mapping(env_http_headers)
    else:
        from . import ConfigEditError

        raise ConfigEditError(f"unsupported MCP server transport kind: {kind!r}")

    if not bool(_field(config, "enabled", True)):
        entry["enabled"] = False
    environment_id = _field(config, "environment_id", "local")
    if environment_id not in (None, "local"):
        entry["environment_id"] = str(environment_id)
    if bool(_field(config, "required", False)):
        entry["required"] = True
    if bool(_field(config, "supports_parallel_tool_calls", False)):
        entry["supports_parallel_tool_calls"] = True
    for key in ("startup_timeout_sec", "tool_timeout_sec"):
        value = _field(config, key)
        if value is not None:
            entry[key] = float(value)
    approval_mode = _field(config, "default_tools_approval_mode")
    if approval_mode is not None:
        entry["default_tools_approval_mode"] = _string_value(approval_mode)
    for key in ("enabled_tools", "disabled_tools", "scopes"):
        values = tuple(_field(config, key, ()) or ())
        if values:
            entry[key] = [str(value) for value in values]
    oauth = _field(config, "oauth")
    client_id = _field(oauth, "client_id") if oauth is not None else None
    if client_id:
        entry["oauth"] = {"client_id": str(client_id)}
    oauth_resource = _field(config, "oauth_resource")
    if oauth_resource:
        entry["oauth_resource"] = str(oauth_resource)
    tools = _field(config, "tools", {}) or {}
    if isinstance(tools, Mapping) and tools:
        entry["tools"] = {
            str(name): _serialize_mcp_server_tool(tool_config)
            for name, tool_config in sorted(tools.items(), key=lambda item: str(item[0]))
        }
    return entry


def serialize_mcp_server_inline(config: Any) -> dict[str, Any]:
    """Return the mapping representation used for an inline TOML table."""

    return serialize_mcp_server(config)


def merge_inline_table(existing: MutableMapping[str, Any], replacement: Mapping[str, Any]) -> None:
    """Replace an inline table while preserving its object identity."""

    for key in tuple(existing):
        if key not in replacement:
            del existing[key]
    for key, value in replacement.items():
        existing[key] = value


def new_implicit_table() -> dict[str, Any]:
    """Create the Python representation of an implicit TOML table."""

    return {}


def parse_tool_suggest_disabled_tool(value: Any) -> Any | None:
    """Parse an inline disabled-tool entry."""

    if not isinstance(value, Mapping):
        return None
    from . import ToolSuggestDisabledTool

    return ToolSuggestDisabledTool.from_mapping(value)


def parse_tool_suggest_disabled_tool_table(table: Any) -> Any | None:
    """Parse a table-form disabled-tool entry."""

    return parse_tool_suggest_disabled_tool(table)


def tool_suggest_disabled_tools_value(disabled_tools: Sequence[Any]) -> list[dict[str, str]]:
    """Serialize disabled tools as the array-of-inline-tables representation."""

    return [tool.to_mapping() for tool in disabled_tools]


def _serialize_mcp_server_tool(config: Any) -> dict[str, Any]:
    approval_mode = _field(config, "approval_mode")
    return {} if approval_mode is None else {"approval_mode": _string_value(approval_mode)}


def _serialize_env_var(value: Any) -> Any:
    if isinstance(value, str):
        return value
    name = _field(value, "name")
    if name is None:
        return str(value)
    result = {"name": str(name)}
    source = _field(value, "source")
    if source is not None:
        result["source"] = str(source)
    return result


def _sorted_string_mapping(value: Mapping[Any, Any]) -> dict[str, str]:
    return {
        str(key): str(item)
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
    }


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _string_value(value: object) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


__all__ = [
    "ensure_table_for_read",
    "ensure_table_for_write",
    "merge_inline_table",
    "new_implicit_table",
    "parse_tool_suggest_disabled_tool",
    "parse_tool_suggest_disabled_tool_table",
    "serialize_mcp_server",
    "serialize_mcp_server_inline",
    "tool_suggest_disabled_tools_value",
]
