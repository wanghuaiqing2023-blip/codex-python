"""Request-plugin-install helpers ported from Codex.

This module combines the dependency-free portions of
``codex-rs/tools/src/request_plugin_install.rs`` with the pure tool-spec and
handler behavior from the adjacent core handlers. The full upstream install
flow depends on session services and app-server elicitation; the Python port
keeps that boundary explicit through a callback.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from os import PathLike
from pathlib import Path
from typing import Any

from pycodex.core.config_edit import ConfigEditsBuilder, ToolSuggestDisabledTool
from pycodex.core.function_tool import FunctionCallError
from pycodex.core.tool_context import FunctionToolOutput, ToolPayload
from pycodex.core.tool_discovery import (
    LIST_AVAILABLE_PLUGINS_TO_INSTALL_TOOL_NAME,
    REQUEST_PLUGIN_INSTALL_TOOL_NAME,
    TUI_CLIENT_NAME,
    AppInfo,
    DiscoverableTool,
    DiscoverableToolAction,
    DiscoverableToolType,
    ListAvailablePluginsToInstallResult,
    RequestPluginInstallEntry,
    collect_request_plugin_install_entries,
    filter_request_plugin_install_discoverable_tools_for_client,
)
from pycodex.core.tool_search_handler import TOOL_SEARCH_TOOL_NAME
from pycodex.protocol import ElicitationRequestEvent, EventMsg, ToolName
from pycodex.protocol.mcp_approval_meta import (
    APPROVAL_KIND_KEY,
    APPROVAL_KIND_TOOL_SUGGESTION,
    TOOL_NAME_KEY,
)

JsonValue = Any

CODEX_APPS_MCP_SERVER_NAME = "codex-apps"
MAX_LIST_AVAILABLE_PLUGINS_TO_INSTALL_DESCRIPTION_CHARS = 240
REQUEST_PLUGIN_INSTALL_APPROVAL_KIND_VALUE = "tool_suggestion"
REQUEST_PLUGIN_INSTALL_PERSIST_KEY = "persist"
REQUEST_PLUGIN_INSTALL_PERSIST_ALWAYS_VALUE = "always"
REQUEST_PLUGIN_INSTALL_SUGGEST_TYPE_KEY = "suggest_type"
REQUEST_PLUGIN_INSTALL_TOOL_ID_KEY = "tool_id"
REQUEST_PLUGIN_INSTALL_TOOL_TYPE_KEY = "tool_type"


@dataclass(frozen=True)
class RequestPluginInstallArgs:
    tool_type: DiscoverableToolType
    action_type: DiscoverableToolAction
    tool_id: str
    suggest_reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_type", _coerce_tool_type(self.tool_type))
        object.__setattr__(self, "action_type", _coerce_action_type(self.action_type))
        object.__setattr__(self, "tool_id", _ensure_str(self.tool_id, "tool_id"))
        object.__setattr__(self, "suggest_reason", _ensure_str(self.suggest_reason, "suggest_reason"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "RequestPluginInstallArgs":
        _ensure_mapping(value, "RequestPluginInstallArgs")
        return cls(
            tool_type=_coerce_tool_type(value["tool_type"]),
            action_type=_coerce_action_type(value["action_type"]),
            tool_id=_ensure_str(value["tool_id"], "tool_id"),
            suggest_reason=_ensure_str(value["suggest_reason"], "suggest_reason"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "tool_type": self.tool_type.value,
            "action_type": self.action_type.value,
            "tool_id": self.tool_id,
            "suggest_reason": self.suggest_reason,
        }


@dataclass(frozen=True)
class RequestPluginInstallResult:
    completed: bool
    user_confirmed: bool
    tool_type: DiscoverableToolType
    action_type: DiscoverableToolAction
    tool_id: str
    tool_name: str
    suggest_reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "completed", _ensure_bool(self.completed, "completed"))
        object.__setattr__(self, "user_confirmed", _ensure_bool(self.user_confirmed, "user_confirmed"))
        object.__setattr__(self, "tool_type", _coerce_tool_type(self.tool_type))
        object.__setattr__(self, "action_type", _coerce_action_type(self.action_type))
        object.__setattr__(self, "tool_id", _ensure_str(self.tool_id, "tool_id"))
        object.__setattr__(self, "tool_name", _ensure_str(self.tool_name, "tool_name"))
        object.__setattr__(self, "suggest_reason", _ensure_str(self.suggest_reason, "suggest_reason"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "RequestPluginInstallResult":
        _ensure_mapping(value, "RequestPluginInstallResult")
        return cls(
            completed=_ensure_bool(value["completed"], "completed"),
            user_confirmed=_ensure_bool(value["user_confirmed"], "user_confirmed"),
            tool_type=_coerce_tool_type(value["tool_type"]),
            action_type=_coerce_action_type(value["action_type"]),
            tool_id=_ensure_str(value["tool_id"], "tool_id"),
            tool_name=_ensure_str(value["tool_name"], "tool_name"),
            suggest_reason=_ensure_str(value["suggest_reason"], "suggest_reason"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "completed": self.completed,
            "user_confirmed": self.user_confirmed,
            "tool_type": self.tool_type.value,
            "action_type": self.action_type.value,
            "tool_id": self.tool_id,
            "tool_name": self.tool_name,
            "suggest_reason": self.suggest_reason,
        }


@dataclass(frozen=True)
class RequestPluginInstallMeta:
    tool_type: DiscoverableToolType
    suggest_type: DiscoverableToolAction
    suggest_reason: str
    tool_id: str
    tool_name: str
    install_url: str | None = None
    codex_approval_kind: str = REQUEST_PLUGIN_INSTALL_APPROVAL_KIND_VALUE
    persist: str = REQUEST_PLUGIN_INSTALL_PERSIST_ALWAYS_VALUE

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_type", _coerce_tool_type(self.tool_type))
        object.__setattr__(self, "suggest_type", _coerce_action_type(self.suggest_type))
        object.__setattr__(self, "suggest_reason", _ensure_str(self.suggest_reason, "suggest_reason"))
        object.__setattr__(self, "tool_id", _ensure_str(self.tool_id, "tool_id"))
        object.__setattr__(self, "tool_name", _ensure_str(self.tool_name, "tool_name"))
        object.__setattr__(
            self,
            "install_url",
            _optional_str(self.install_url, "install_url"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "codex_approval_kind": self.codex_approval_kind,
            "persist": self.persist,
            "tool_type": self.tool_type.value,
            "suggest_type": self.suggest_type.value,
            "suggest_reason": self.suggest_reason,
            "tool_id": self.tool_id,
            "tool_name": self.tool_name,
        }
        if self.install_url is not None:
            data["install_url"] = self.install_url
        return data


@dataclass(frozen=True)
class PluginInstallElicitationTelemetryMetadata:
    tool_type: str
    tool_id: str
    tool_name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_type", _ensure_str(self.tool_type, "tool_type"))
        object.__setattr__(self, "tool_id", _ensure_str(self.tool_id, "tool_id"))
        object.__setattr__(self, "tool_name", _ensure_str(self.tool_name, "tool_name"))


@dataclass(frozen=True)
class McpElicitationSchema:
    schema_uri: str | None = None
    type_: str = "object"
    properties: Mapping[str, JsonValue] = field(default_factory=dict)
    required: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "schema_uri",
            _optional_str(self.schema_uri, "schema_uri"),
        )
        object.__setattr__(self, "type_", _ensure_str(self.type_, "type_"))
        if not isinstance(self.properties, Mapping):
            raise TypeError("properties must be a mapping")
        object.__setattr__(self, "properties", copy.deepcopy(dict(self.properties)))
        if self.required is not None:
            object.__setattr__(self, "required", _string_tuple(self.required, "required"))

    @classmethod
    def empty_object(cls) -> "McpElicitationSchema":
        return cls()

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "type": self.type_,
            "properties": copy.deepcopy(dict(self.properties)),
        }
        if self.schema_uri is not None:
            data["$schema"] = self.schema_uri
        if self.required is not None:
            data["required"] = list(self.required)
        return data


@dataclass(frozen=True)
class McpServerElicitationRequest:
    mode: str
    message: str
    meta: JsonValue | None = None
    requested_schema: McpElicitationSchema | None = None
    url: str | None = None
    elicitation_id: str | None = None

    @classmethod
    def form(
        cls,
        message: str,
        requested_schema: McpElicitationSchema,
        meta: JsonValue | None = None,
    ) -> "McpServerElicitationRequest":
        return cls(
            mode="form",
            message=message,
            requested_schema=requested_schema,
            meta=meta,
        )

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", _ensure_str(self.mode, "mode"))
        object.__setattr__(self, "message", _ensure_str(self.message, "message"))
        object.__setattr__(self, "url", _optional_str(self.url, "url"))
        object.__setattr__(self, "elicitation_id", _optional_str(self.elicitation_id, "elicitation_id"))
        if self.requested_schema is not None and not isinstance(self.requested_schema, McpElicitationSchema):
            raise TypeError("requested_schema must be McpElicitationSchema")

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "mode": self.mode,
            "_meta": copy.deepcopy(self.meta),
            "message": self.message,
        }
        if self.mode == "form":
            if self.requested_schema is None:
                raise ValueError("form elicitation request requires requested_schema")
            data["requestedSchema"] = self.requested_schema.to_mapping()
        elif self.mode == "url":
            data["url"] = self.url
            data["elicitationId"] = self.elicitation_id
        else:
            raise ValueError(f"unknown elicitation request mode: {self.mode}")
        return data


@dataclass(frozen=True)
class McpServerElicitationRequestParams:
    thread_id: str
    turn_id: str | None
    server_name: str
    request: McpServerElicitationRequest

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "turn_id", _optional_str(self.turn_id, "turn_id"))
        object.__setattr__(self, "server_name", _ensure_str(self.server_name, "server_name"))
        if not isinstance(self.request, McpServerElicitationRequest):
            raise TypeError("request must be McpServerElicitationRequest")

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "threadId": self.thread_id,
            "turnId": self.turn_id,
            "serverName": self.server_name,
        }
        data.update(self.request.to_mapping())
        return data


def build_request_plugin_install_elicitation_request(
    server_name: str,
    thread_id: str,
    turn_id: str,
    args: RequestPluginInstallArgs | Mapping[str, JsonValue],
    suggest_reason: str,
    tool: DiscoverableTool | Mapping[str, JsonValue],
) -> McpServerElicitationRequestParams:
    request_args = args if isinstance(args, RequestPluginInstallArgs) else RequestPluginInstallArgs.from_mapping(args)
    discoverable_tool = tool if isinstance(tool, DiscoverableTool) else DiscoverableTool.from_mapping(tool)
    server_name = _ensure_str(server_name, "server_name")
    thread_id = _ensure_str(thread_id, "thread_id")
    turn_id = _ensure_str(turn_id, "turn_id")
    suggest_reason = _ensure_str(suggest_reason, "suggest_reason")
    tool_name = discoverable_tool.name()
    meta = build_request_plugin_install_meta(
        request_args.tool_type,
        request_args.action_type,
        suggest_reason,
        discoverable_tool.id(),
        tool_name,
        discoverable_tool.install_url(),
    ).to_mapping()
    return McpServerElicitationRequestParams(
        thread_id=thread_id,
        turn_id=turn_id,
        server_name=server_name,
        request=McpServerElicitationRequest.form(
            message=suggest_reason,
            requested_schema=McpElicitationSchema.empty_object(),
            meta=meta,
        ),
    )


def build_request_plugin_install_meta(
    tool_type: DiscoverableToolType | str,
    action_type: DiscoverableToolAction | str,
    suggest_reason: str,
    tool_id: str,
    tool_name: str,
    install_url: str | None,
) -> RequestPluginInstallMeta:
    return RequestPluginInstallMeta(
        tool_type=_coerce_tool_type(tool_type),
        suggest_type=_coerce_action_type(action_type),
        suggest_reason=suggest_reason,
        tool_id=tool_id,
        tool_name=tool_name,
        install_url=install_url,
    )


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


def all_requested_connectors_picked_up(
    expected_connector_ids: Iterable[str],
    accessible_connectors: Iterable[AppInfo | Mapping[str, JsonValue]],
) -> bool:
    expected_ids = _string_tuple(expected_connector_ids, "expected_connector_ids")
    connectors = [_coerce_app_info(connector) for connector in accessible_connectors]
    return all(
        verified_connector_install_completed(connector_id, connectors)
        for connector_id in expected_ids
    )


def verified_connector_install_completed(
    tool_id: str,
    accessible_connectors: Iterable[AppInfo | Mapping[str, JsonValue]],
) -> bool:
    tool_id = _ensure_str(tool_id, "tool_id")
    for connector in accessible_connectors:
        info = _coerce_app_info(connector)
        if info.id == tool_id and info.is_accessible:
            return True
    return False


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


def _coerce_tool_type(value: DiscoverableToolType | str) -> DiscoverableToolType:
    if isinstance(value, DiscoverableToolType):
        return value
    if isinstance(value, str):
        return DiscoverableToolType(value)
    raise TypeError("tool_type must be DiscoverableToolType or string")


def _coerce_action_type(value: DiscoverableToolAction | str) -> DiscoverableToolAction:
    if isinstance(value, DiscoverableToolAction):
        return value
    if isinstance(value, str):
        return DiscoverableToolAction(value)
    raise TypeError("action_type must be DiscoverableToolAction or string")


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
    "REQUEST_PLUGIN_INSTALL_APPROVAL_KIND_VALUE",
    "REQUEST_PLUGIN_INSTALL_PERSIST_ALWAYS_VALUE",
    "REQUEST_PLUGIN_INSTALL_PERSIST_KEY",
    "REQUEST_PLUGIN_INSTALL_SUGGEST_TYPE_KEY",
    "REQUEST_PLUGIN_INSTALL_TOOL_ID_KEY",
    "REQUEST_PLUGIN_INSTALL_TOOL_TYPE_KEY",
    "ConnectorRefreshCallback",
    "ListAvailablePluginsToInstallHandler",
    "McpElicitationSchema",
    "McpServerElicitationRequest",
    "McpServerElicitationRequestParams",
    "PluginInstallElicitationTelemetryMetadata",
    "RequestPluginInstallArgs",
    "RequestPluginInstallCallback",
    "RequestPluginInstallHandler",
    "RequestPluginInstallMeta",
    "RequestPluginInstallResult",
    "all_requested_connectors_picked_up",
    "build_request_plugin_install_elicitation_request",
    "build_request_plugin_install_meta",
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
    "verified_connector_install_completed",
    "verified_plugin_install_completed",
    "verify_request_plugin_install_completed",
]
