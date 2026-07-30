"""Host-owned app MCP cache support from ``codex-mcp/src/codex_apps.rs``."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from pycodex.utils.plugins.mcp_connector import (
    is_connector_id_allowed,
    sanitize_name,
)

from .mcp import CODEX_APPS_MCP_SERVER_NAME
from .tools import ToolInfo


CODEX_APPS_TOOLS_CACHE_SCHEMA_VERSION = 3
CODEX_APPS_TOOLS_CACHE_DIR = Path("cache") / "codex_apps_tools"


@dataclass(frozen=True)
class CodexAppsToolsCacheKey:
    account_id: str | None
    chatgpt_user_id: str | None
    is_workspace_account: bool


@dataclass(frozen=True)
class CodexAppsToolsCacheContext:
    codex_home: Path
    user_key: CodexAppsToolsCacheKey

    def cache_path(self) -> Path:
        payload = json.dumps(
            asdict(self.user_key),
            separators=(",", ":"),
            sort_keys=True,
        )
        digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
        return self.codex_home / CODEX_APPS_TOOLS_CACHE_DIR / f"{digest}.json"


class CachedCodexAppsToolsLoadKind(str, Enum):
    HIT = "hit"
    MISSING = "missing"
    INVALID = "invalid"


@dataclass(frozen=True)
class CachedCodexAppsToolsLoad:
    kind: CachedCodexAppsToolsLoadKind
    tools: tuple[ToolInfo, ...] = ()


def codex_apps_tools_cache_key(auth: Any | None) -> CodexAppsToolsCacheKey:
    return CodexAppsToolsCacheKey(
        _auth_value(auth, "get_account_id"),
        _auth_value(auth, "get_chatgpt_user_id"),
        bool(_auth_value(auth, "is_workspace_account", False)),
    )


def normalize_codex_apps_tool_title(
    server_name: str,
    connector_name: str | None,
    value: str,
) -> str:
    if server_name != CODEX_APPS_MCP_SERVER_NAME or not (connector_name or "").strip():
        return value
    prefix = f"{connector_name.strip()}_"
    stripped = value.removeprefix(prefix)
    return stripped or value


def normalize_codex_apps_callable_name(
    server_name: str,
    tool_name: str,
    connector_id: str | None,
    connector_name: str | None,
) -> str:
    if server_name != CODEX_APPS_MCP_SERVER_NAME:
        return tool_name
    normalized = sanitize_name(tool_name)
    for prefix in (connector_name, connector_id):
        if prefix and (candidate := normalized.removeprefix(sanitize_name(prefix))):
            return candidate
    return normalized


def normalize_codex_apps_callable_namespace(
    server_name: str,
    connector_name: str | None,
) -> str:
    if server_name == CODEX_APPS_MCP_SERVER_NAME and connector_name is not None:
        return f"{server_name}__{sanitize_name(connector_name)}"
    return server_name


def write_cached_codex_apps_tools_if_needed(
    server_name: str,
    cache_context: CodexAppsToolsCacheContext | None,
    tools: tuple[ToolInfo, ...] | list[ToolInfo],
) -> None:
    if server_name == CODEX_APPS_MCP_SERVER_NAME and cache_context is not None:
        write_cached_codex_apps_tools(cache_context, tools)


def load_startup_cached_codex_apps_tools_snapshot(
    server_name: str,
    cache_context: CodexAppsToolsCacheContext | None,
) -> tuple[ToolInfo, ...] | None:
    if server_name != CODEX_APPS_MCP_SERVER_NAME or cache_context is None:
        return None
    loaded = load_cached_codex_apps_tools(cache_context)
    return loaded.tools if loaded.kind is CachedCodexAppsToolsLoadKind.HIT else None


def load_cached_codex_apps_tools(
    cache_context: CodexAppsToolsCacheContext,
) -> CachedCodexAppsToolsLoad:
    try:
        payload = json.loads(cache_context.cache_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return CachedCodexAppsToolsLoad(CachedCodexAppsToolsLoadKind.MISSING)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return CachedCodexAppsToolsLoad(CachedCodexAppsToolsLoadKind.INVALID)
    if (
        not isinstance(payload, Mapping)
        or payload.get("schema_version") != CODEX_APPS_TOOLS_CACHE_SCHEMA_VERSION
        or not isinstance(payload.get("tools"), list)
    ):
        return CachedCodexAppsToolsLoad(CachedCodexAppsToolsLoadKind.INVALID)
    try:
        tools = tuple(_tool_info_from_mapping(item) for item in payload["tools"])
    except (TypeError, ValueError):
        return CachedCodexAppsToolsLoad(CachedCodexAppsToolsLoadKind.INVALID)
    return CachedCodexAppsToolsLoad(
        CachedCodexAppsToolsLoadKind.HIT,
        filter_disallowed_codex_apps_tools(tools),
    )


def write_cached_codex_apps_tools(
    cache_context: CodexAppsToolsCacheContext,
    tools: tuple[ToolInfo, ...] | list[ToolInfo],
) -> None:
    path = cache_context.cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": CODEX_APPS_TOOLS_CACHE_SCHEMA_VERSION,
            "tools": [
                _json_value(tool)
                for tool in filter_disallowed_codex_apps_tools(tuple(tools))
            ],
        }
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except (OSError, TypeError, ValueError):
        return


def filter_disallowed_codex_apps_tools(
    tools: tuple[ToolInfo, ...] | list[ToolInfo],
) -> tuple[ToolInfo, ...]:
    return tuple(
        tool
        for tool in tools
        if tool.connector_id is None
        or is_connector_id_allowed(tool.connector_id)
    )


def _tool_info_from_mapping(value: Any) -> ToolInfo:
    if not isinstance(value, Mapping):
        raise TypeError("cached MCP tool must be an object")
    return ToolInfo(
        server_name=str(value["server_name"]),
        callable_name=str(value.get("callable_name", value.get("tool_name", ""))),
        callable_namespace=str(
            value.get("callable_namespace", value.get("tool_namespace", ""))
        ),
        tool=value.get("tool"),
        supports_parallel_tool_calls=bool(
            value.get("supports_parallel_tool_calls", False)
        ),
        server_origin=value.get("server_origin"),
        namespace_description=value.get("namespace_description"),
        connector_id=value.get("connector_id"),
        connector_name=value.get("connector_name"),
        plugin_display_names=tuple(value.get("plugin_display_names", ())),
    )


def _json_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _json_value(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _auth_value(auth: Any | None, name: str, default: Any = None) -> Any:
    if auth is None:
        return default
    value = getattr(auth, name, default)
    return value() if callable(value) else value


__all__ = [
    "CODEX_APPS_TOOLS_CACHE_SCHEMA_VERSION",
    "CachedCodexAppsToolsLoad",
    "CachedCodexAppsToolsLoadKind",
    "CodexAppsToolsCacheContext",
    "CodexAppsToolsCacheKey",
    "codex_apps_tools_cache_key",
    "filter_disallowed_codex_apps_tools",
    "load_cached_codex_apps_tools",
    "load_startup_cached_codex_apps_tools_snapshot",
    "normalize_codex_apps_callable_name",
    "normalize_codex_apps_callable_namespace",
    "normalize_codex_apps_tool_title",
    "write_cached_codex_apps_tools",
    "write_cached_codex_apps_tools_if_needed",
]
