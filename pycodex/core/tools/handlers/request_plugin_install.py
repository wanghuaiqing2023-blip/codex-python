"""Request-plugin-install helpers ported from Codex.

This module combines the dependency-free portions of
``codex-rs/tools/src/request_plugin_install.rs`` with the pure tool-spec and
handler behavior from the adjacent core handlers. The full upstream install
flow depends on session services and app-server elicitation; the Python port
keeps that boundary explicit through a callback.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from os import PathLike
from pathlib import Path
from typing import Any

from pycodex.core.config.edit import ConfigEditsBuilder, ToolSuggestDisabledTool
from pycodex.core.function_tool import FunctionCallError
from pycodex.core.tools.context import FunctionToolOutput, ToolPayload
from pycodex.app_server_protocol.apps import AppInfo
from pycodex.app_server_protocol.elicitation import McpServerElicitationRequestParams
from pycodex.tools.request_plugin_install import (
    REQUEST_PLUGIN_INSTALL_APPROVAL_KIND_VALUE,
    REQUEST_PLUGIN_INSTALL_PERSIST_ALWAYS_VALUE,
    REQUEST_PLUGIN_INSTALL_PERSIST_KEY,
    REQUEST_PLUGIN_INSTALL_SUGGEST_TYPE_KEY,
    REQUEST_PLUGIN_INSTALL_TOOL_ID_KEY,
    REQUEST_PLUGIN_INSTALL_TOOL_TYPE_KEY,
    RequestPluginInstallArgs,
    RequestPluginInstallMeta,
    RequestPluginInstallResult,
    all_requested_connectors_picked_up,
    build_request_plugin_install_elicitation_request,
    build_request_plugin_install_meta,
    verified_connector_install_completed,
)
from pycodex.tools.tool_discovery import (
    LIST_AVAILABLE_PLUGINS_TO_INSTALL_TOOL_NAME,
    REQUEST_PLUGIN_INSTALL_TOOL_NAME,
    TUI_CLIENT_NAME,
    DiscoverableTool,
    DiscoverableToolAction,
    DiscoverableToolType,
    ListAvailablePluginsToInstallResult,
    RequestPluginInstallEntry,
    collect_request_plugin_install_entries,
    filter_request_plugin_install_discoverable_tools_for_client,
)
from pycodex.core.tools.handlers.tool_search import TOOL_SEARCH_TOOL_NAME
from pycodex.protocol import ElicitationRequestEvent, EventMsg, ToolName
from pycodex.protocol.mcp_approval_meta import (
    APPROVAL_KIND_KEY,
    APPROVAL_KIND_TOOL_SUGGESTION,
    TOOL_NAME_KEY,
)

JsonValue = Any

CODEX_APPS_MCP_SERVER_NAME = "codex-apps"
MAX_LIST_AVAILABLE_PLUGINS_TO_INSTALL_DESCRIPTION_CHARS = 240








@dataclass(frozen=True)
class PluginInstallElicitationTelemetryMetadata:
    tool_type: str
    tool_id: str
    tool_name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_type", _ensure_str(self.tool_type, "tool_type"))
        object.__setattr__(self, "tool_id", _ensure_str(self.tool_id, "tool_id"))
        object.__setattr__(self, "tool_name", _ensure_str(self.tool_name, "tool_name"))












def plugin_install_elicitation_telemetry_metadata(
    event: EventMsg | ElicitationRequestEvent | Mapping[str, JsonValue],
) -> PluginInstallElicitationTelemetryMetadata | None:
    request_event = _coerce_elicitation_request_event(event)
    if request_event is None:
        return None

    request = request_event.request
    if request.mode != "form" or not isinstance(request.meta, Mapping):
        return None
    meta = request.meta
    if (
        _metadata_str(meta, APPROVAL_KIND_KEY) != APPROVAL_KIND_TOOL_SUGGESTION
        or _metadata_str(meta, REQUEST_PLUGIN_INSTALL_SUGGEST_TYPE_KEY)
        != DiscoverableToolAction.INSTALL.value
    ):
        return None

    tool_type = _metadata_owned_string(meta, REQUEST_PLUGIN_INSTALL_TOOL_TYPE_KEY)
    tool_id = _metadata_owned_string(meta, REQUEST_PLUGIN_INSTALL_TOOL_ID_KEY)
    tool_name = _metadata_owned_string(meta, TOOL_NAME_KEY)
    if tool_type is None or tool_id is None or tool_name is None:
        return None

    return PluginInstallElicitationTelemetryMetadata(
        tool_type=tool_type,
        tool_id=tool_id,
        tool_name=tool_name,
    )






def verified_plugin_install_completed(
    tool_id: str,
    marketplaces_or_plugins: Iterable[Mapping[str, JsonValue] | Any],
) -> bool:
    target_id = _ensure_str(tool_id, "tool_id")
    for plugin in _iter_plugin_records(marketplaces_or_plugins):
        plugin_id = _get_field(plugin, "id")
        if (
            isinstance(plugin_id, str)
            and plugin_id == target_id
            and _get_field(plugin, "installed") is True
        ):
            return True
    return False


def refresh_missing_requested_connectors(
    expected_connector_ids: Iterable[str],
    accessible_connectors: Iterable[AppInfo | Mapping[str, JsonValue]],
    refresh_callback: ConnectorRefreshCallback | None = None,
) -> tuple[AppInfo, ...] | None:
    expected_ids = _string_tuple(expected_connector_ids, "expected_connector_ids")
    if not expected_ids:
        return ()

    connectors = tuple(_coerce_app_info(connector) for connector in accessible_connectors)
    if all_requested_connectors_picked_up(expected_ids, connectors):
        return connectors
    if refresh_callback is None:
        return None
    try:
        refreshed = refresh_callback()
    except Exception:
        return None
    return tuple(_coerce_app_info(connector) for connector in refreshed)


def verify_request_plugin_install_completed(
    tool: DiscoverableTool | Mapping[str, JsonValue],
    accessible_connectors: Iterable[AppInfo | Mapping[str, JsonValue]] = (),
    plugin_marketplaces_or_plugins: Iterable[Mapping[str, JsonValue] | Any] = (),
    connector_refresh_callback: ConnectorRefreshCallback | None = None,
) -> bool:
    discoverable_tool = (
        tool
        if isinstance(tool, DiscoverableTool)
        else DiscoverableTool.from_mapping(tool)
    )
    if discoverable_tool.tool_type() == DiscoverableToolType.CONNECTOR:
        connector_id = discoverable_tool.id()
        refreshed_connectors = refresh_missing_requested_connectors(
            (connector_id,),
            accessible_connectors,
            connector_refresh_callback,
        )
        return refreshed_connectors is not None and verified_connector_install_completed(
            connector_id,
            refreshed_connectors,
        )

    completed = verified_plugin_install_completed(
        discoverable_tool.id(),
        plugin_marketplaces_or_plugins,
    )
    plugin = discoverable_tool.plugin_info
    if plugin is not None:
        refresh_missing_requested_connectors(
            plugin.app_connector_ids,
            accessible_connectors,
            connector_refresh_callback,
        )
    return completed


def create_list_available_plugins_to_install_tool() -> dict[str, JsonValue]:
    description = (
        "# List plugin/connector install candidates\n\n"
        "Use this tool only when both are true:\n"
        "- The user explicitly asks to use a specific plugin or connector that is not already available in the current context or active `tools` list.\n"
        f"- `{TOOL_SEARCH_TOOL_NAME}` is not available, or it has already been called and did not find or make the requested tool callable.\n\n"
        f"Returns known plugins and connectors that can be passed to `{REQUEST_PLUGIN_INSTALL_TOOL_NAME}`. "
        "When both a plugin and a connector match, prefer the plugin; use the connector only when its corresponding plugin is already installed.\n"
    )
    return {
        "type": "function",
        "name": LIST_AVAILABLE_PLUGINS_TO_INSTALL_TOOL_NAME,
        "description": description,
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    }


def create_request_plugin_install_tool() -> dict[str, JsonValue]:
    description = (
        "# Request plugin/connector install\n\n"
        f"Use this tool only after `{LIST_AVAILABLE_PLUGINS_TO_INSTALL_TOOL_NAME}` returns a plugin or connector that exactly matches the user's explicit request.\n\n"
        "Do not use it for adjacent capabilities, broad recommendations, or tools that merely seem useful. "
        "Pass the returned `tool_type` through directly, and pass the returned `id` as `tool_id`.\n\n"
        "IMPORTANT: DO NOT call this tool in parallel with other tools."
    )
    return {
        "type": "function",
        "name": REQUEST_PLUGIN_INSTALL_TOOL_NAME,
        "description": description,
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "tool_type": {
                    "type": "string",
                    "description": 'Type of discoverable tool to suggest. Use "connector" or "plugin".',
                },
                "action_type": {
                    "type": "string",
                    "description": 'Suggested action for the tool. Use "install".',
                },
                "tool_id": {
                    "type": "string",
                    "description": "Connector or plugin id to suggest.",
                },
                "suggest_reason": {
                    "type": "string",
                    "description": "Concise one-line user-facing reason why this plugin or connector can help with the current request.",
                },
            },
            "required": [
                "tool_type",
                "action_type",
                "tool_id",
                "suggest_reason",
            ],
            "additionalProperties": False,
        },
    }


@dataclass(frozen=True)
class ListAvailablePluginsToInstallHandler:
    tools: tuple[RequestPluginInstallEntry, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        entries = _install_entries_tuple(self.tools)
        object.__setattr__(
            self,
            "tools",
            tuple(sorted(entries, key=lambda tool: (tool.name, tool.id))),
        )

    @classmethod
    def new(
        cls,
        tools: Iterable[RequestPluginInstallEntry | Mapping[str, JsonValue]],
    ) -> "ListAvailablePluginsToInstallHandler":
        return cls(_install_entries_tuple(tools))

    def tool_name(self) -> ToolName:
        return ToolName.plain(LIST_AVAILABLE_PLUGINS_TO_INSTALL_TOOL_NAME)

    def spec(self) -> dict[str, JsonValue]:
        return create_list_available_plugins_to_install_tool()

    def supports_parallel_tool_calls(self) -> bool:
        return False

    def matches_kind(self, payload: ToolPayload) -> bool:
        if not isinstance(payload, ToolPayload):
            raise TypeError("payload must be ToolPayload")
        return payload.type in {"function", "tool_search"}

    def result(self) -> ListAvailablePluginsToInstallResult:
        return ListAvailablePluginsToInstallResult(
            tuple(
                RequestPluginInstallEntry(
                    id=tool.id,
                    name=tool.name,
                    description=(
                        None
                        if tool.description is None
                        else truncate_to_char_boundary(
                            tool.description,
                            MAX_LIST_AVAILABLE_PLUGINS_TO_INSTALL_DESCRIPTION_CHARS,
                        )
                    ),
                    tool_type=tool.tool_type,
                    has_skills=tool.has_skills,
                    mcp_server_names=tool.mcp_server_names,
                    app_connector_ids=tool.app_connector_ids,
                )
                for tool in self.tools
            )
        )

    def handle(self, invocation_or_payload: Any) -> FunctionToolOutput:
        payload = getattr(invocation_or_payload, "payload", invocation_or_payload)
        if not isinstance(payload, ToolPayload) or payload.type != "function":
            raise FunctionCallError.fatal(
                f"{LIST_AVAILABLE_PLUGINS_TO_INSTALL_TOOL_NAME} handler received unsupported payload"
            )
        content = json.dumps(self.result().to_mapping(), separators=(",", ":"))
        return FunctionToolOutput.from_text(content, True)


RequestPluginInstallCallback = Callable[
    [RequestPluginInstallArgs, DiscoverableTool, McpServerElicitationRequestParams],
    RequestPluginInstallResult | Mapping[str, JsonValue],
]
ConnectorRefreshCallback = Callable[
    [],
    Iterable[AppInfo | Mapping[str, JsonValue] | Any],
]


@dataclass(frozen=True)
class RequestPluginInstallHandler:
    discoverable_tools: tuple[DiscoverableTool, ...] = field(default_factory=tuple)
    request_callback: RequestPluginInstallCallback | None = None
    app_server_client_name: str | None = None
    server_name: str = CODEX_APPS_MCP_SERVER_NAME
    thread_id: str = ""
    turn_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "discoverable_tools",
            tuple(
                tool
                if isinstance(tool, DiscoverableTool)
                else DiscoverableTool.from_mapping(tool)
                for tool in self.discoverable_tools
            ),
        )
        object.__setattr__(self, "app_server_client_name", _optional_str(self.app_server_client_name, "app_server_client_name"))
        object.__setattr__(self, "server_name", _ensure_str(self.server_name, "server_name"))
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "turn_id", _ensure_str(self.turn_id, "turn_id"))

    def tool_name(self) -> ToolName:
        return ToolName.plain(REQUEST_PLUGIN_INSTALL_TOOL_NAME)

    def spec(self) -> dict[str, JsonValue]:
        return create_request_plugin_install_tool()

    def supports_parallel_tool_calls(self) -> bool:
        return True

    def matches_kind(self, payload: ToolPayload) -> bool:
        if not isinstance(payload, ToolPayload):
            raise TypeError("payload must be ToolPayload")
        return payload.type in {"function", "tool_search"}

    def handle(self, invocation_or_payload: Any) -> FunctionToolOutput:
        payload = getattr(invocation_or_payload, "payload", invocation_or_payload)
        if not isinstance(payload, ToolPayload) or payload.type != "function":
            raise FunctionCallError.fatal(
                f"{REQUEST_PLUGIN_INSTALL_TOOL_NAME} handler received unsupported payload"
            )
        if payload.arguments is None:
            raise FunctionCallError.fatal(
                f"{REQUEST_PLUGIN_INSTALL_TOOL_NAME} handler received unsupported payload"
            )
        try:
            raw_arguments = json.loads(payload.arguments) if payload.arguments.strip() else {}
            args = RequestPluginInstallArgs.from_mapping(raw_arguments)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as err:
            raise FunctionCallError.respond_to_model(
                f"failed to parse function arguments: {err}"
            ) from err
        suggest_reason = args.suggest_reason.strip()
        if not suggest_reason:
            raise FunctionCallError.respond_to_model("suggest_reason must not be empty")
        if args.action_type != DiscoverableToolAction.INSTALL:
            raise FunctionCallError.respond_to_model(
                'plugin install requests currently support only action_type="install"'
            )
        if args.tool_type == DiscoverableToolType.PLUGIN and self.app_server_client_name == TUI_CLIENT_NAME:
            raise FunctionCallError.respond_to_model(
                "plugin install requests are not available in codex-tui yet"
            )

        tool = self._find_discoverable_tool(args)
        if tool is None:
            raise FunctionCallError.respond_to_model(
                f"tool_id must match one of the discoverable tools returned by {LIST_AVAILABLE_PLUGINS_TO_INSTALL_TOOL_NAME}"
            )

        params = build_request_plugin_install_elicitation_request(
            self.server_name,
            self.thread_id,
            self.turn_id,
            args,
            suggest_reason,
            tool,
        )
        if self.request_callback is None:
            raise FunctionCallError.respond_to_model(
                "request_plugin_install handler requires a request callback in the Python port"
            )
        result = self.request_callback(args, tool, params)
        if not isinstance(result, RequestPluginInstallResult):
            result = RequestPluginInstallResult.from_mapping(result)
        response = RequestPluginInstallResult(
            completed=result.completed,
            user_confirmed=result.user_confirmed,
            tool_type=args.tool_type,
            action_type=args.action_type,
            tool_id=tool.id(),
            tool_name=tool.name(),
            suggest_reason=suggest_reason,
        )
        content = json.dumps(response.to_mapping(), separators=(",", ":"))
        return FunctionToolOutput.from_text(content, True)

    def _find_discoverable_tool(self, args: RequestPluginInstallArgs) -> DiscoverableTool | None:
        tools = filter_request_plugin_install_discoverable_tools_for_client(
            self.discoverable_tools,
            self.app_server_client_name,
        )
        return next(
            (
                tool
                for tool in tools
                if tool.tool_type() == args.tool_type and tool.id() == args.tool_id
            ),
            None,
        )


def request_plugin_install_response_requests_persistent_disable(
    response: Mapping[str, JsonValue] | Any,
) -> bool:
    action = _get_field(response, "action")
    meta = _get_field(response, "meta")
    if meta is None:
        meta = _get_field(response, "_meta")
    return (
        str(action).lower() == "decline"
        and isinstance(meta, Mapping)
        and meta.get(REQUEST_PLUGIN_INSTALL_PERSIST_KEY)
        == REQUEST_PLUGIN_INSTALL_PERSIST_ALWAYS_VALUE
    )


def disabled_install_request(
    tool: DiscoverableTool | Mapping[str, JsonValue],
) -> ToolSuggestDisabledTool:
    discoverable_tool = (
        tool
        if isinstance(tool, DiscoverableTool)
        else DiscoverableTool.from_mapping(tool)
    )
    if discoverable_tool.tool_type() == DiscoverableToolType.CONNECTOR:
        return ToolSuggestDisabledTool.connector(discoverable_tool.id())
    return ToolSuggestDisabledTool.plugin(discoverable_tool.id())


def persist_disabled_install_request(
    codex_home: str | PathLike[str],
    tool: DiscoverableTool | Mapping[str, JsonValue],
) -> bool:
    return (
        ConfigEditsBuilder.new(Path(codex_home))
        .add_tool_suggest_disabled_tool(disabled_install_request(tool))
        .apply_blocking()
    )


def maybe_persist_disabled_install_request(
    codex_home: str | PathLike[str],
    tool: DiscoverableTool | Mapping[str, JsonValue],
    response: Mapping[str, JsonValue] | Any,
) -> bool:
    if not request_plugin_install_response_requests_persistent_disable(response):
        return False
    return persist_disabled_install_request(codex_home, tool)


def truncate_to_char_boundary(value: str, max_chars: int) -> str:
    value = _ensure_str(value, "value")
    max_chars = _ensure_usize(max_chars, "max_chars")
    return value[:max_chars]


def _install_entries_tuple(
    values: Iterable[RequestPluginInstallEntry | Mapping[str, JsonValue]],
) -> tuple[RequestPluginInstallEntry, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise TypeError("install entries must be an iterable of RequestPluginInstallEntry values")
    return tuple(_coerce_install_entry(tool) for tool in values)


def _coerce_install_entry(value: RequestPluginInstallEntry | Mapping[str, JsonValue]) -> RequestPluginInstallEntry:
    if isinstance(value, RequestPluginInstallEntry):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("install entry must be RequestPluginInstallEntry or mapping")
    return RequestPluginInstallEntry.from_mapping(value)






def _coerce_app_info(value: AppInfo | Mapping[str, JsonValue]) -> AppInfo:
    if isinstance(value, AppInfo):
        return value
    if isinstance(value, Mapping):
        return AppInfo.from_mapping(value)
    raise TypeError("connector must be AppInfo or mapping")


def _iter_plugin_records(
    values: Iterable[Mapping[str, JsonValue] | Any],
) -> Iterable[Mapping[str, JsonValue] | Any]:
    for value in values:
        plugins = _get_field(value, "plugins")
        if plugins is None:
            yield value
            continue
        if isinstance(plugins, Iterable) and not isinstance(plugins, (str, bytes, Mapping)):
            yield from plugins


def _coerce_elicitation_request_event(
    event: EventMsg | ElicitationRequestEvent | Mapping[str, JsonValue],
) -> ElicitationRequestEvent | None:
    if isinstance(event, ElicitationRequestEvent):
        return event
    if isinstance(event, EventMsg):
        return event.payload if event.type == "elicitation_request" and isinstance(event.payload, ElicitationRequestEvent) else None
    if isinstance(event, Mapping):
        if event.get("type") is not None:
            return _coerce_elicitation_request_event(EventMsg.from_mapping(event))
        return ElicitationRequestEvent.from_mapping(event)
    return None


def _metadata_str(meta: Mapping[str, JsonValue], key: str) -> str | None:
    value = meta.get(key)
    return value if isinstance(value, str) else None


def _metadata_owned_string(meta: Mapping[str, JsonValue], key: str) -> str | None:
    value = _metadata_str(meta, key)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _get_field(value: Mapping[str, JsonValue] | Any, name: str) -> JsonValue:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _ensure_mapping(value: JsonValue, field_name: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return value


def _ensure_str(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _optional_str(value: JsonValue, field_name: str) -> str | None:
    if value is None:
        return None
    return _ensure_str(value, field_name)


def _ensure_bool(value: JsonValue, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")
    return value


def _ensure_usize(value: JsonValue, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")
    return value


def _string_tuple(values: Iterable[JsonValue], field_name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise TypeError(f"{field_name} must be an iterable of strings")
    result: list[str] = []
    for value in values:
        result.append(_ensure_str(value, field_name))
    return tuple(result)


__all__ = [
    "CODEX_APPS_MCP_SERVER_NAME",
    "MAX_LIST_AVAILABLE_PLUGINS_TO_INSTALL_DESCRIPTION_CHARS",
    "ConnectorRefreshCallback",
    "ListAvailablePluginsToInstallHandler",
    "PluginInstallElicitationTelemetryMetadata",
    "RequestPluginInstallCallback",
    "RequestPluginInstallHandler",
    "collect_request_plugin_install_entries",
    "create_list_available_plugins_to_install_tool",
    "create_request_plugin_install_tool",
    "disabled_install_request",
    "maybe_persist_disabled_install_request",
    "persist_disabled_install_request",
    "plugin_install_elicitation_telemetry_metadata",
    "refresh_missing_requested_connectors",
    "request_plugin_install_response_requests_persistent_disable",
    "truncate_to_char_boundary",
    "verified_plugin_install_completed",
    "verify_request_plugin_install_completed",
]

