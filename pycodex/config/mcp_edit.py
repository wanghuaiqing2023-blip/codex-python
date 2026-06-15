"""Global MCP server config edits ported from ``codex-config``."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import toml_compat as _toml
from .mcp_types import (
    DEFAULT_MCP_SERVER_ENVIRONMENT_ID,
    AppToolApproval,
    McpServerConfig,
    McpServerEnvVar,
    McpServerTransportConfig,
)
from .plugin_edit import CONFIG_TOML_FILE, _quote_key


JsonValue = Any


def load_global_mcp_servers_blocking(codex_home: Path | str) -> dict[str, McpServerConfig]:
    config_path = Path(codex_home) / CONFIG_TOML_FILE
    if not config_path.exists():
        return {}
    raw = config_path.read_text(encoding="utf-8")
    try:
        parsed = dict(_toml.loads(raw))
    except _toml.TOMLDecodeError as exc:
        raise ValueError(str(exc)) from exc

    servers_value = parsed.get("mcp_servers")
    if servers_value is None:
        return {}
    if not isinstance(servers_value, Mapping):
        raise ValueError("mcp_servers must be a table")

    _ensure_no_inline_bearer_tokens(servers_value)
    return {
        name: McpServerConfig.from_mapping(_server_mapping(name, value))
        for name, value in sorted(servers_value.items())
    }


async def load_global_mcp_servers(codex_home: Path | str) -> dict[str, McpServerConfig]:
    return await asyncio.to_thread(load_global_mcp_servers_blocking, codex_home)


@dataclass(frozen=True)
class ConfigEditsBuilder:
    codex_home: Path
    mcp_servers: dict[str, McpServerConfig] | None = None

    @classmethod
    def new(cls, codex_home: Path | str) -> "ConfigEditsBuilder":
        return cls(Path(codex_home))

    def replace_mcp_servers(self, servers: Mapping[str, McpServerConfig]) -> "ConfigEditsBuilder":
        return ConfigEditsBuilder(self.codex_home, dict(servers))

    def apply_blocking(self) -> None:
        config_path = self.codex_home / CONFIG_TOML_FILE
        document = _read_or_create_document(config_path)
        if self.mcp_servers is not None:
            _replace_mcp_servers(document, self.mcp_servers)
        self.codex_home.mkdir(parents=True, exist_ok=True)
        config_path.write_text(_serialize_config(document), encoding="utf-8", newline="\n")

    async def apply(self) -> None:
        await asyncio.to_thread(self.apply_blocking)


def _server_mapping(name: object, value: object) -> Mapping[str, Any]:
    if not isinstance(name, str):
        raise ValueError("mcp server names must be strings")
    if not isinstance(value, Mapping):
        raise ValueError(f"mcp_servers.{name} must be a table")
    return value


def _ensure_no_inline_bearer_tokens(servers: Mapping[str, Any]) -> None:
    for server_name, server_value in servers.items():
        if isinstance(server_value, Mapping) and "bearer_token" in server_value:
            raise ValueError(
                f"mcp_servers.{server_name} uses unsupported `bearer_token`; "
                "set `bearer_token_env_var`."
            )


def _read_or_create_document(config_path: Path) -> dict[str, JsonValue]:
    if not config_path.exists():
        return {}
    try:
        return dict(_toml.loads(config_path.read_text(encoding="utf-8")))
    except _toml.TOMLDecodeError as exc:
        raise ValueError(str(exc)) from exc


def _replace_mcp_servers(document: dict[str, JsonValue], servers: Mapping[str, McpServerConfig]) -> None:
    if not servers:
        document.pop("mcp_servers", None)
        return
    document["mcp_servers"] = {name: _mcp_server_to_mapping(config) for name, config in sorted(servers.items())}


def _mcp_server_to_mapping(config: McpServerConfig) -> dict[str, JsonValue]:
    entry: dict[str, JsonValue] = {}
    transport = config.transport
    if transport.kind == "stdio":
        entry["command"] = transport.command
        if transport.args:
            entry["args"] = list(transport.args)
        if transport.env:
            entry["env"] = dict(sorted(transport.env.items()))
        if transport.env_vars:
            entry["env_vars"] = [_env_var_to_value(env_var) for env_var in transport.env_vars]
        if transport.cwd is not None:
            entry["cwd"] = str(transport.cwd)
    else:
        entry["url"] = transport.url
        if transport.bearer_token_env_var is not None:
            entry["bearer_token_env_var"] = transport.bearer_token_env_var
        if transport.http_headers:
            entry["http_headers"] = dict(sorted(transport.http_headers.items()))
        if transport.env_http_headers:
            entry["env_http_headers"] = dict(sorted(transport.env_http_headers.items()))

    if not config.enabled:
        entry["enabled"] = False
    if config.environment_id != DEFAULT_MCP_SERVER_ENVIRONMENT_ID:
        entry["environment_id"] = config.environment_id
    if config.required:
        entry["required"] = True
    if config.supports_parallel_tool_calls:
        entry["supports_parallel_tool_calls"] = True
    if config.startup_timeout_sec is not None:
        entry["startup_timeout_sec"] = config.startup_timeout_sec
    if config.tool_timeout_sec is not None:
        entry["tool_timeout_sec"] = config.tool_timeout_sec
    if config.default_tools_approval_mode is not None:
        entry["default_tools_approval_mode"] = _approval_value(config.default_tools_approval_mode)
    if config.enabled_tools:
        entry["enabled_tools"] = list(config.enabled_tools)
    if config.disabled_tools:
        entry["disabled_tools"] = list(config.disabled_tools)
    if config.scopes:
        entry["scopes"] = list(config.scopes)
    if config.oauth is not None and config.oauth.client_id:
        entry["oauth"] = {"client_id": config.oauth.client_id}
    if config.oauth_resource:
        entry["oauth_resource"] = config.oauth_resource
    if config.tools:
        entry["tools"] = {
            name: _tool_config_to_mapping(tool_config)
            for name, tool_config in sorted(config.tools.items())
        }
    return entry


def _tool_config_to_mapping(tool_config: Any) -> dict[str, JsonValue]:
    approval_mode = getattr(tool_config, "approval_mode", None)
    if approval_mode is None:
        return {}
    return {"approval_mode": _approval_value(approval_mode)}


def _env_var_to_value(env_var: McpServerEnvVar) -> str | dict[str, str]:
    if env_var.source() is None:
        return env_var.name()
    return {"name": env_var.name(), "source": env_var.source() or ""}


def _approval_value(value: AppToolApproval | None) -> str:
    if value is None:
        raise ValueError("approval value is absent")
    return value.value


def _serialize_config(document: Mapping[str, JsonValue]) -> str:
    if not document:
        return ""
    lines: list[str] = []
    for key, value in document.items():
        if key == "mcp_servers" and isinstance(value, Mapping):
            _serialize_mcp_servers(value, lines)
            continue
        lines.append(f"{_quote_key(str(key))} = {_format_toml_value(value)}")
    return "\n".join(lines) + ("\n" if lines else "")


def _serialize_mcp_servers(servers: Mapping[str, JsonValue], lines: list[str]) -> None:
    for server_name, server_value in servers.items():
        if not isinstance(server_value, Mapping):
            continue
        if lines and lines[-1] != "":
            lines.append("")
        table_prefix = f"mcp_servers.{_quote_key(str(server_name))}"
        lines.append(f"[{table_prefix}]")
        _serialize_server_fields(table_prefix, server_value, lines)


def _serialize_server_fields(table_prefix: str, server: Mapping[str, JsonValue], lines: list[str]) -> None:
    nested: list[tuple[str, Mapping[str, JsonValue]]] = []
    for field_name, field_value in server.items():
        if isinstance(field_value, Mapping):
            nested.append((str(field_name), field_value))
            continue
        lines.append(f"{_quote_key(str(field_name))} = {_format_toml_value(field_value)}")

    for field_name, table_value in nested:
        if lines and lines[-1] != "":
            lines.append("")
        nested_prefix = f"{table_prefix}.{_quote_key(field_name)}"
        lines.append(f"[{nested_prefix}]")
        if field_name == "tools":
            _serialize_tools_table(nested_prefix, table_value, lines)
        else:
            for nested_name, nested_value in table_value.items():
                lines.append(f"{_quote_key(str(nested_name))} = {_format_toml_value(nested_value)}")


def _serialize_tools_table(table_prefix: str, tools: Mapping[str, JsonValue], lines: list[str]) -> None:
    for tool_name, tool_value in tools.items():
        if not isinstance(tool_value, Mapping):
            continue
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(f"[{table_prefix}.{_quote_key(str(tool_name))}]")
        for field_name, field_value in tool_value.items():
            lines.append(f"{_quote_key(str(field_name))} = {_format_toml_value(field_value)}")


def _format_toml_value(value: JsonValue) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, list | tuple):
        return "[" + ", ".join(_format_toml_value(item) for item in value) + "]"
    if isinstance(value, Mapping):
        return "{ " + ", ".join(
            f"{_quote_key(str(key))} = {_format_toml_value(item_value)}"
            for key, item_value in value.items()
        ) + " }"
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


__all__ = [
    "ConfigEditsBuilder",
    "load_global_mcp_servers",
    "load_global_mcp_servers_blocking",
]
