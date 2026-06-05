"""Request-plugin-install protocol helpers ported from `codex-rs/tools`."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from pycodex.app_server_protocol.apps import AppInfo
from pycodex.app_server_protocol.elicitation import (
    McpElicitationSchema,
    McpServerElicitationRequest,
    McpServerElicitationRequestParams,
)
from pycodex.tools.tool_discovery import (
    DiscoverableTool,
    DiscoverableToolAction,
    DiscoverableToolType,
)

JsonValue = Any

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


def _string_tuple(values: Iterable[JsonValue], field_name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise TypeError(f"{field_name} must be an iterable of strings")
    result: list[str] = []
    for value in values:
        result.append(_ensure_str(value, field_name))
    return tuple(result)



__all__ = [
    "REQUEST_PLUGIN_INSTALL_APPROVAL_KIND_VALUE",
    "REQUEST_PLUGIN_INSTALL_PERSIST_ALWAYS_VALUE",
    "REQUEST_PLUGIN_INSTALL_PERSIST_KEY",
    "REQUEST_PLUGIN_INSTALL_SUGGEST_TYPE_KEY",
    "REQUEST_PLUGIN_INSTALL_TOOL_ID_KEY",
    "REQUEST_PLUGIN_INSTALL_TOOL_TYPE_KEY",
    "RequestPluginInstallArgs",
    "RequestPluginInstallMeta",
    "RequestPluginInstallResult",
    "all_requested_connectors_picked_up",
    "build_request_plugin_install_elicitation_request",
    "build_request_plugin_install_meta",
    "verified_connector_install_completed",
]
