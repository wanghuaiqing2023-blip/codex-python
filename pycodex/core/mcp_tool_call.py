"""Pure MCP tool-call policy helpers ported from Codex core.

This module contains the dependency-free portions of
``core/src/mcp_tool_call.rs``: MCP approval decisions, approval cache keys,
tool-annotation approval requirements, and configured custom MCP approval-mode
selection.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pycodex.core.connectors import (
    CODEX_APPS_MCP_SERVER_NAME,
    AppToolApproval,
    ToolAnnotations,
)
from pycodex.core.mcp_tool_handler import ToolInfo
from pycodex.core.string_utils import sanitize_metric_tag_value
from pycodex.core.tool_sandboxing import ApprovalStore
from pycodex.protocol import CallToolResult, ElicitationAction, ElicitationRequestEvent
from pycodex.protocol.approvals import ReviewDecision
from pycodex.protocol.config_types import ApprovalsReviewer
from pycodex.protocol.mcp_approval_meta import (
    APPROVALS_REVIEWER_KEY,
    APPROVAL_KIND_KEY,
    APPROVAL_KIND_MCP_TOOL_CALL,
    CONNECTOR_DESCRIPTION_KEY,
    CONNECTOR_ID_KEY,
    CONNECTOR_NAME_KEY,
    PERSIST_ALWAYS,
    PERSIST_KEY,
    PERSIST_SESSION,
    REQUEST_TYPE_APPROVAL_REQUEST,
    REQUEST_TYPE_KEY,
    SOURCE_CONNECTOR,
    SOURCE_KEY,
    TOOL_DESCRIPTION_KEY,
    TOOL_NAME_KEY,
    TOOL_PARAMS_DISPLAY_KEY,
    TOOL_PARAMS_KEY,
    TOOL_TITLE_KEY,
)
from pycodex.protocol.request_user_input import (
    RequestUserInputAnswer,
    RequestUserInputQuestion,
    RequestUserInputQuestionOption,
    RequestUserInputResponse,
)

JsonValue = Any

MCP_TOOL_APPROVAL_QUESTION_ID_PREFIX = "mcp_tool_call_approval"
MCP_TOOL_APPROVAL_ACCEPT = "Allow"
MCP_TOOL_APPROVAL_ACCEPT_FOR_SESSION = "Allow for this session"
MCP_TOOL_APPROVAL_DECLINE_SYNTHETIC = "__codex_mcp_decline__"
MCP_TOOL_APPROVAL_ACCEPT_AND_REMEMBER = "Allow and don't ask me again"
MCP_TOOL_APPROVAL_CANCEL = "Cancel"
MCP_TOOL_CALL_EVENT_RESULT_MAX_BYTES = 1024 * 1024
MCP_IMAGE_CONTENT_OMITTED_TEXT = (
    "<image content omitted because you do not support image input>"
)
MCP_TOOL_CODEX_APPS_META_KEY = "_codex_apps"
MCP_TOOL_OPENAI_OUTPUT_TEMPLATE_META_KEY = "openai/outputTemplate"
MCP_TOOL_UI_RESOURCE_URI_META_KEY = "ui/resourceUri"
MCP_TOOL_PLUGIN_ID_META_KEY = "plugin_id"
MCP_TOOL_THREAD_ID_META_KEY = "threadId"
MCP_TOOL_OPENAI_FILE_PARAMS_META_KEY = "openai/fileParams"
X_CODEX_TURN_METADATA_HEADER = "x-codex-turn-metadata"
MCP_ELICITATION_DECLINE_MESSAGE_KEY = "message"
MCP_TOOL_APPROVAL_PERSIST_VALUE = "approve"
MCP_CALL_COUNT_METRIC = "codex.mcp.call"
MCP_CALL_DURATION_METRIC = "codex.mcp.call.duration_ms"
MCP_RESULT_TELEMETRY_META_KEY = "codex/telemetry"
MCP_RESULT_TELEMETRY_SPAN_KEY = "span"
MCP_RESULT_TELEMETRY_TARGET_ID_KEY = "target_id"
MCP_RESULT_TELEMETRY_DID_TRIGGER_SERVER_USER_FLOW_KEY = "did_trigger_server_user_flow"
MCP_RESULT_TELEMETRY_TARGET_ID_SPAN_ATTR = "codex.mcp.target.id"
MCP_RESULT_TELEMETRY_SERVER_USER_FLOW_SPAN_ATTR = (
    "codex.mcp.server_user_flow.triggered"
)
MCP_RESULT_TELEMETRY_TARGET_ID_MAX_CHARS = 256
GUARDIAN_REJECTION_INSTRUCTIONS = (
    "The agent must not attempt to achieve the same outcome via workaround, "
    "indirect execution, or policy circumvention. "
    "Proceed only with a materially safer alternative, "
    "or if the user explicitly approves the action after being informed of the risk. "
    "Otherwise, stop and request user input."
)
GUARDIAN_TIMEOUT_INSTRUCTIONS = (
    "The automatic permission approval review did not finish before its deadline. "
    "Do not assume the action is unsafe based on the timeout alone. "
    "You may retry once, or ask the user for guidance or explicit approval."
)


@dataclass(frozen=True)
class McpInvocation:
    server: str
    tool: str
    arguments: JsonValue | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "McpInvocation":
        return cls(
            server=str(value["server"]),
            tool=str(value.get("tool", value.get("tool_name"))),
            arguments=value.get("arguments"),
        )


@dataclass(frozen=True)
class McpToolApprovalMetadata:
    annotations: ToolAnnotations | None = None
    connector_id: str | None = None
    connector_name: str | None = None
    connector_description: str | None = None
    plugin_id: str | None = None
    tool_title: str | None = None
    tool_description: str | None = None
    mcp_app_resource_uri: str | None = None
    codex_apps_meta: Mapping[str, JsonValue] | None = None
    openai_file_input_params: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "annotations", ToolAnnotations.from_value(self.annotations))
        object.__setattr__(self, "connector_id", _optional_str(self.connector_id))
        object.__setattr__(self, "connector_name", _optional_str(self.connector_name))
        object.__setattr__(
            self,
            "connector_description",
            _optional_str(self.connector_description),
        )
        object.__setattr__(self, "plugin_id", _optional_str(self.plugin_id))
        object.__setattr__(self, "tool_title", _optional_str(self.tool_title))
        object.__setattr__(self, "tool_description", _optional_str(self.tool_description))
        object.__setattr__(self, "mcp_app_resource_uri", _optional_str(self.mcp_app_resource_uri))
        if self.openai_file_input_params is not None and not isinstance(
            self.openai_file_input_params, tuple
        ):
            object.__setattr__(
                self,
                "openai_file_input_params",
                tuple(str(param) for param in self.openai_file_input_params),
            )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None) -> "McpToolApprovalMetadata | None":
        if value is None:
            return None
        return cls(
            annotations=ToolAnnotations.from_value(value.get("annotations")),
            connector_id=_optional_str(value.get("connector_id")),
            connector_name=_optional_str(value.get("connector_name")),
            connector_description=_optional_str(value.get("connector_description")),
            plugin_id=_optional_str(value.get("plugin_id")),
            tool_title=_optional_str(value.get("tool_title")),
            tool_description=_optional_str(value.get("tool_description")),
            mcp_app_resource_uri=_optional_str(value.get("mcp_app_resource_uri")),
            codex_apps_meta=value.get("codex_apps_meta")
            if isinstance(value.get("codex_apps_meta"), Mapping)
            else None,
            openai_file_input_params=_optional_string_tuple(
                value.get("openai_file_input_params")
            ),
        )


@dataclass(frozen=True)
class McpToolApprovalKey:
    server: str
    connector_id: str | None
    tool_name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "server", str(self.server))
        object.__setattr__(self, "connector_id", _optional_str(self.connector_id))
        object.__setattr__(self, "tool_name", str(self.tool_name))


class McpAppInvocationType(str, Enum):
    EXPLICIT = "explicit"
    IMPLICIT = "implicit"


@dataclass(frozen=True)
class McpAppUsageMetadata:
    connector_id: str | None = None
    app_name: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "connector_id", _optional_str(self.connector_id))
        object.__setattr__(self, "app_name", _optional_str(self.app_name))


@dataclass(frozen=True)
class McpAppInvocation:
    connector_id: str | None = None
    app_name: str | None = None
    invocation_type: McpAppInvocationType | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "connector_id", _optional_str(self.connector_id))
        object.__setattr__(self, "app_name", _optional_str(self.app_name))
        if self.invocation_type is not None:
            object.__setattr__(
                self,
                "invocation_type",
                McpAppInvocationType(self.invocation_type),
            )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "connector_id": self.connector_id,
            "app_name": self.app_name,
            "invocation_type": self.invocation_type.value
            if self.invocation_type is not None
            else None,
        }


class McpToolApprovalDecisionKind(str, Enum):
    ACCEPT = "accept"
    ACCEPT_FOR_SESSION = "accept_for_session"
    ACCEPT_AND_REMEMBER = "accept_and_remember"
    DECLINE = "decline"
    CANCEL = "cancel"


@dataclass(frozen=True)
class McpToolApprovalDecision:
    kind: McpToolApprovalDecisionKind
    message: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", McpToolApprovalDecisionKind(self.kind))
        object.__setattr__(self, "message", _optional_str(self.message))

    @classmethod
    def accept(cls) -> "McpToolApprovalDecision":
        return cls(McpToolApprovalDecisionKind.ACCEPT)

    @classmethod
    def accept_for_session(cls) -> "McpToolApprovalDecision":
        return cls(McpToolApprovalDecisionKind.ACCEPT_FOR_SESSION)

    @classmethod
    def accept_and_remember(cls) -> "McpToolApprovalDecision":
        return cls(McpToolApprovalDecisionKind.ACCEPT_AND_REMEMBER)

    @classmethod
    def decline(cls, message: str | None = None) -> "McpToolApprovalDecision":
        return cls(McpToolApprovalDecisionKind.DECLINE, message)

    @classmethod
    def cancel(cls) -> "McpToolApprovalDecision":
        return cls(McpToolApprovalDecisionKind.CANCEL)


@dataclass(frozen=True)
class McpToolApprovalPromptOptions:
    allow_session_remember: bool
    allow_persistent_approval: bool


@dataclass(frozen=True)
class McpToolApprovalConfigEdit:
    segments: tuple[str, ...]
    value: JsonValue = MCP_TOOL_APPROVAL_PERSIST_VALUE

    def __post_init__(self) -> None:
        object.__setattr__(self, "segments", tuple(str(segment) for segment in self.segments))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"segments": list(self.segments), "value": self.value}


@dataclass(frozen=True)
class RenderedMcpToolApprovalParam:
    name: str
    value: JsonValue
    display_name: str

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "name": self.name,
            "value": self.value,
            "display_name": self.display_name,
        }


@dataclass(frozen=True)
class ElicitationResponse:
    action: ElicitationAction
    content: JsonValue | None = None
    meta: Mapping[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "action", ElicitationAction(self.action))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ElicitationResponse":
        meta = value.get("meta")
        return cls(
            action=ElicitationAction(str(value["action"])),
            content=value.get("content"),
            meta=meta if isinstance(meta, Mapping) else None,
        )


@dataclass(frozen=True)
class GuardianMcpAnnotations:
    destructive_hint: bool | None = None
    open_world_hint: bool | None = None
    read_only_hint: bool | None = None

    @classmethod
    def from_tool_annotations(
        cls,
        annotations: ToolAnnotations | Mapping[str, JsonValue] | None,
    ) -> "GuardianMcpAnnotations | None":
        annotations = ToolAnnotations.from_value(annotations)
        if annotations is None:
            return None
        return cls(
            destructive_hint=annotations.destructive_hint,
            open_world_hint=annotations.open_world_hint,
            read_only_hint=annotations.read_only_hint,
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {}
        if self.destructive_hint is not None:
            data["destructive_hint"] = self.destructive_hint
        if self.open_world_hint is not None:
            data["open_world_hint"] = self.open_world_hint
        if self.read_only_hint is not None:
            data["read_only_hint"] = self.read_only_hint
        return data


@dataclass(frozen=True)
class GuardianMcpToolReviewRequest:
    id: str
    server: str
    tool_name: str
    arguments: JsonValue | None = None
    connector_id: str | None = None
    connector_name: str | None = None
    connector_description: str | None = None
    tool_title: str | None = None
    tool_description: str | None = None
    annotations: GuardianMcpAnnotations | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", str(self.id))
        object.__setattr__(self, "server", str(self.server))
        object.__setattr__(self, "tool_name", str(self.tool_name))
        object.__setattr__(self, "connector_id", _optional_str(self.connector_id))
        object.__setattr__(self, "connector_name", _optional_str(self.connector_name))
        object.__setattr__(
            self,
            "connector_description",
            _optional_str(self.connector_description),
        )
        object.__setattr__(self, "tool_title", _optional_str(self.tool_title))
        object.__setattr__(self, "tool_description", _optional_str(self.tool_description))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "type": "mcp_tool_call",
            "id": self.id,
            "server": self.server,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "connector_id": self.connector_id,
            "connector_name": self.connector_name,
            "connector_description": self.connector_description,
            "tool_title": self.tool_title,
            "tool_description": self.tool_description,
            "annotations": self.annotations.to_mapping()
            if self.annotations is not None
            else None,
        }


class GuardianElicitationReviewKind(str, Enum):
    NOT_REQUESTED = "not_requested"
    DECLINE = "decline"
    APPROVAL_REQUEST = "approval_request"


@dataclass(frozen=True)
class GuardianElicitationReview:
    kind: GuardianElicitationReviewKind
    reason: str | None = None
    approval_request: GuardianMcpToolReviewRequest | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", GuardianElicitationReviewKind(self.kind))
        object.__setattr__(self, "reason", _optional_str(self.reason))

    @classmethod
    def not_requested(cls) -> "GuardianElicitationReview":
        return cls(GuardianElicitationReviewKind.NOT_REQUESTED)

    @classmethod
    def decline(cls, reason: str) -> "GuardianElicitationReview":
        return cls(GuardianElicitationReviewKind.DECLINE, reason=reason)

    @classmethod
    def approval_request(
        cls,
        approval_request: GuardianMcpToolReviewRequest,
    ) -> "GuardianElicitationReview":
        return cls(
            GuardianElicitationReviewKind.APPROVAL_REQUEST,
            approval_request=approval_request,
        )


@dataclass(frozen=True)
class McpServerToolConfig:
    approval_mode: AppToolApproval | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "approval_mode",
            _optional_app_tool_approval(self.approval_mode),
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None) -> "McpServerToolConfig":
        if value is None:
            return cls()
        return cls(approval_mode=_optional_app_tool_approval(value.get("approval_mode")))


@dataclass(frozen=True)
class McpServerApprovalConfig:
    default_tools_approval_mode: AppToolApproval | None = None
    tools: Mapping[str, McpServerToolConfig] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "default_tools_approval_mode",
            _optional_app_tool_approval(self.default_tools_approval_mode),
        )
        object.__setattr__(
            self,
            "tools",
            {
                str(name): tool
                if isinstance(tool, McpServerToolConfig)
                else McpServerToolConfig.from_mapping(tool)
                for name, tool in self.tools.items()
                if isinstance(tool, Mapping | McpServerToolConfig)
            },
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None) -> "McpServerApprovalConfig":
        if value is None:
            return cls()
        raw_tools = value.get("tools", {})
        if not isinstance(raw_tools, Mapping):
            raw_tools = {}
        return cls(
            default_tools_approval_mode=_optional_app_tool_approval(
                value.get("default_tools_approval_mode")
            ),
            tools={
                str(name): McpServerToolConfig.from_mapping(tool)
                for name, tool in raw_tools.items()
                if isinstance(tool, Mapping)
            },
        )

    def approval_mode_for_tool(self, tool_name: str) -> AppToolApproval:
        tool_config = self.tools.get(tool_name)
        return (
            (tool_config.approval_mode if tool_config is not None else None)
            or self.default_tools_approval_mode
            or AppToolApproval.AUTO
        )


def session_mcp_tool_approval_key(
    invocation: McpInvocation | Mapping[str, JsonValue],
    metadata: McpToolApprovalMetadata | Mapping[str, JsonValue] | None,
    approval_mode: AppToolApproval | str,
) -> McpToolApprovalKey | None:
    approval = AppToolApproval(approval_mode)
    if approval is not AppToolApproval.AUTO:
        return None

    invocation = invocation if isinstance(invocation, McpInvocation) else McpInvocation.from_mapping(invocation)
    metadata = (
        metadata
        if isinstance(metadata, McpToolApprovalMetadata) or metadata is None
        else McpToolApprovalMetadata.from_mapping(metadata)
    )
    connector_id = metadata.connector_id if metadata is not None else None
    if invocation.server == CODEX_APPS_MCP_SERVER_NAME and connector_id is None:
        return None

    return McpToolApprovalKey(
        server=invocation.server,
        connector_id=connector_id,
        tool_name=invocation.tool,
    )


def persistent_mcp_tool_approval_key(
    invocation: McpInvocation | Mapping[str, JsonValue],
    metadata: McpToolApprovalMetadata | Mapping[str, JsonValue] | None,
    approval_mode: AppToolApproval | str,
) -> McpToolApprovalKey | None:
    return session_mcp_tool_approval_key(invocation, metadata, approval_mode)


def codex_app_tool_approval_config_edit(
    connector_id: str,
    tool_name: str,
) -> McpToolApprovalConfigEdit:
    return McpToolApprovalConfigEdit(
        (
            "apps",
            str(connector_id),
            "tools",
            str(tool_name),
            "approval_mode",
        )
    )


def custom_mcp_tool_approval_config_edit(
    server: str,
    tool_name: str,
) -> McpToolApprovalConfigEdit:
    return McpToolApprovalConfigEdit(
        (
            "mcp_servers",
            str(server),
            "tools",
            str(tool_name),
            "approval_mode",
        )
    )


def plugin_mcp_tool_approval_config_edit(
    plugin_config_name: str,
    server: str,
    tool_name: str,
) -> McpToolApprovalConfigEdit:
    return McpToolApprovalConfigEdit(
        (
            "plugins",
            str(plugin_config_name),
            "mcp_servers",
            str(server),
            "tools",
            str(tool_name),
            "approval_mode",
        )
    )


def mcp_tool_approval_config_edit_for_key(
    key: McpToolApprovalKey | Mapping[str, JsonValue],
    plugin_config_name: str | None = None,
) -> McpToolApprovalConfigEdit | None:
    key = key if isinstance(key, McpToolApprovalKey) else McpToolApprovalKey(
        server=str(key["server"]),
        connector_id=_optional_str(key.get("connector_id")),
        tool_name=str(key["tool_name"]),
    )
    if key.server == CODEX_APPS_MCP_SERVER_NAME:
        if key.connector_id is None:
            return None
        return codex_app_tool_approval_config_edit(key.connector_id, key.tool_name)
    if plugin_config_name is not None:
        return plugin_mcp_tool_approval_config_edit(
            plugin_config_name,
            key.server,
            key.tool_name,
        )
    return custom_mcp_tool_approval_config_edit(key.server, key.tool_name)


def lookup_mcp_tool_metadata(
    tools: Iterable[ToolInfo | Mapping[str, JsonValue]],
    server: str,
    tool_name: str,
    plugin_id: str | None = None,
    accessible_connectors: Iterable[Mapping[str, JsonValue] | object] | None = None,
) -> McpToolApprovalMetadata | None:
    info = next(
        (
            tool_info
            for raw_tool_info in tools
            for tool_info in (
                raw_tool_info
                if isinstance(raw_tool_info, ToolInfo)
                else ToolInfo.from_mapping(raw_tool_info),
            )
            if tool_info.server_name == server and tool_info.tool.name == tool_name
        ),
        None,
    )
    if info is None:
        return None

    connector_description = None
    if server == CODEX_APPS_MCP_SERVER_NAME and info.connector_id is not None:
        connector_description = _connector_description(
            accessible_connectors,
            info.connector_id,
        )

    tool_meta = info.tool.meta if isinstance(info.tool.meta, Mapping) else None
    return McpToolApprovalMetadata(
        annotations=info.tool.annotations,
        connector_id=info.connector_id,
        connector_name=info.connector_name,
        connector_description=connector_description,
        plugin_id=plugin_id,
        tool_title=info.tool.title,
        tool_description=info.tool.description,
        mcp_app_resource_uri=get_mcp_app_resource_uri(tool_meta),
        codex_apps_meta=codex_apps_meta_from_tool_meta(tool_meta),
        openai_file_input_params=openai_file_input_params_for_server(server, tool_meta),
    )


def lookup_mcp_app_usage_metadata(
    tools: Iterable[ToolInfo | Mapping[str, JsonValue]],
    server: str,
    tool_name: str,
) -> McpAppUsageMetadata | None:
    for raw_tool_info in tools:
        tool_info = (
            raw_tool_info
            if isinstance(raw_tool_info, ToolInfo)
            else ToolInfo.from_mapping(raw_tool_info)
        )
        if tool_info.server_name == server and tool_info.tool.name == tool_name:
            return McpAppUsageMetadata(
                connector_id=tool_info.connector_id,
                app_name=tool_info.connector_name,
            )
    return None


def mcp_app_invocation_type(
    connector_id: str | None,
    mentioned_connector_ids: Iterable[str],
) -> McpAppInvocationType:
    if connector_id is not None and connector_id in {str(value) for value in mentioned_connector_ids}:
        return McpAppInvocationType.EXPLICIT
    return McpAppInvocationType.IMPLICIT


def build_mcp_app_used_invocation(
    tools: Iterable[ToolInfo | Mapping[str, JsonValue]],
    server: str,
    tool_name: str,
    mentioned_connector_ids: Iterable[str] = (),
) -> McpAppInvocation | None:
    if server != CODEX_APPS_MCP_SERVER_NAME:
        return None
    metadata = lookup_mcp_app_usage_metadata(tools, server, tool_name) or McpAppUsageMetadata()
    return McpAppInvocation(
        connector_id=metadata.connector_id,
        app_name=metadata.app_name,
        invocation_type=mcp_app_invocation_type(
            metadata.connector_id,
            mentioned_connector_ids,
        ),
    )


def mcp_call_metric_tags(
    status: str,
    tool_name: str,
    connector_id: str | None = None,
    connector_name: str | None = None,
) -> tuple[tuple[str, str], ...]:
    tags: list[tuple[str, str]] = [
        ("status", sanitize_metric_tag_value(status)),
        ("tool", sanitize_metric_tag_value(tool_name)),
    ]
    if connector_id:
        tags.append(("connector_id", sanitize_metric_tag_value(connector_id)))
    if connector_name:
        tags.append(("connector_name", sanitize_metric_tag_value(connector_name)))
    return tuple(tags)


def truncate_str_to_char_boundary(value: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    return str(value)[:max_chars]


def mcp_result_span_telemetry_attributes(
    result: CallToolResult | Mapping[str, JsonValue] | None,
) -> dict[str, JsonValue]:
    if result is None:
        return {}
    call_tool_result = (
        result
        if isinstance(result, CallToolResult)
        else CallToolResult.from_mapping(result)
    )
    meta = call_tool_result.meta
    if not isinstance(meta, Mapping):
        return {}
    telemetry = meta.get(MCP_RESULT_TELEMETRY_META_KEY)
    if not isinstance(telemetry, Mapping):
        return {}
    span_telemetry = telemetry.get(MCP_RESULT_TELEMETRY_SPAN_KEY)
    if not isinstance(span_telemetry, Mapping):
        return {}

    attributes: dict[str, JsonValue] = {}
    target_id = span_telemetry.get(MCP_RESULT_TELEMETRY_TARGET_ID_KEY)
    if isinstance(target_id, str) and target_id:
        attributes[MCP_RESULT_TELEMETRY_TARGET_ID_SPAN_ATTR] = (
            truncate_str_to_char_boundary(
                target_id,
                MCP_RESULT_TELEMETRY_TARGET_ID_MAX_CHARS,
            )
        )

    did_trigger_server_user_flow = span_telemetry.get(
        MCP_RESULT_TELEMETRY_DID_TRIGGER_SERVER_USER_FLOW_KEY
    )
    if isinstance(did_trigger_server_user_flow, bool):
        attributes[MCP_RESULT_TELEMETRY_SERVER_USER_FLOW_SPAN_ATTR] = (
            did_trigger_server_user_flow
        )
    return attributes


def build_guardian_mcp_tool_review_request(
    call_id: str,
    invocation: McpInvocation | Mapping[str, JsonValue],
    metadata: McpToolApprovalMetadata | Mapping[str, JsonValue] | None = None,
) -> GuardianMcpToolReviewRequest:
    invocation = invocation if isinstance(invocation, McpInvocation) else McpInvocation.from_mapping(invocation)
    metadata = (
        metadata
        if isinstance(metadata, McpToolApprovalMetadata) or metadata is None
        else McpToolApprovalMetadata.from_mapping(metadata)
    )
    annotations = (
        GuardianMcpAnnotations.from_tool_annotations(metadata.annotations)
        if metadata is not None
        else None
    )
    return GuardianMcpToolReviewRequest(
        id=call_id,
        server=invocation.server,
        tool_name=invocation.tool,
        arguments=invocation.arguments,
        connector_id=metadata.connector_id if metadata is not None else None,
        connector_name=metadata.connector_name if metadata is not None else None,
        connector_description=metadata.connector_description if metadata is not None else None,
        tool_title=metadata.tool_title if metadata is not None else None,
        tool_description=metadata.tool_description if metadata is not None else None,
        annotations=annotations,
    )


def guardian_elicitation_review_request(
    request: ElicitationRequestEvent | Mapping[str, JsonValue],
) -> GuardianElicitationReview:
    request = (
        request
        if isinstance(request, ElicitationRequestEvent)
        else ElicitationRequestEvent.from_mapping(request)
    )
    elicitation = request.request
    meta = elicitation.meta
    if elicitation.mode == "url":
        if _meta_requests_approval_request(meta):
            return GuardianElicitationReview.decline(
                "guardian MCP elicitation review only supports form elicitations"
            )
        return GuardianElicitationReview.not_requested()

    if elicitation.mode != "form" or not isinstance(meta, Mapping):
        return GuardianElicitationReview.not_requested()
    if _metadata_str(meta, REQUEST_TYPE_KEY) != REQUEST_TYPE_APPROVAL_REQUEST:
        return GuardianElicitationReview.not_requested()
    if _metadata_str(meta, APPROVAL_KIND_KEY) != APPROVAL_KIND_MCP_TOOL_CALL:
        return GuardianElicitationReview.decline(
            "guardian MCP elicitation metadata must declare mcp_tool_call approval kind"
        )
    if _requested_schema_has_properties(elicitation.requested_schema):
        return GuardianElicitationReview.decline(
            "guardian MCP elicitation review only supports empty form schemas"
        )

    tool_name = _metadata_owned_string(meta, TOOL_NAME_KEY)
    if tool_name is None:
        return GuardianElicitationReview.decline(
            "guardian MCP elicitation metadata must include a non-empty tool_name"
        )

    raw_arguments = meta.get(TOOL_PARAMS_KEY)
    if raw_arguments is None:
        arguments: JsonValue = {}
    elif isinstance(raw_arguments, Mapping):
        arguments = dict(raw_arguments)
    else:
        return GuardianElicitationReview.decline(
            "guardian MCP elicitation tool_params must be an object"
        )

    return GuardianElicitationReview.approval_request(
        GuardianMcpToolReviewRequest(
            id=f"mcp_elicitation:{request.server_name}:{mcp_elicitation_request_id(request.id)}",
            server=request.server_name,
            tool_name=tool_name,
            arguments=arguments,
            connector_id=_metadata_owned_string(meta, CONNECTOR_ID_KEY),
            connector_name=_metadata_owned_string(meta, CONNECTOR_NAME_KEY),
            connector_description=_metadata_owned_string(meta, CONNECTOR_DESCRIPTION_KEY),
            tool_title=_metadata_owned_string(meta, TOOL_TITLE_KEY),
            tool_description=_metadata_owned_string(meta, TOOL_DESCRIPTION_KEY),
        )
    )


def mcp_elicitation_request_id(request_id: JsonValue) -> str:
    return str(request_id)


def mcp_tool_approval_prompt_options(
    session_approval_key: McpToolApprovalKey | None,
    persistent_approval_key: McpToolApprovalKey | None,
    tool_call_mcp_elicitation_enabled: bool,
) -> McpToolApprovalPromptOptions:
    return McpToolApprovalPromptOptions(
        allow_session_remember=session_approval_key is not None,
        allow_persistent_approval=bool(tool_call_mcp_elicitation_enabled)
        and persistent_approval_key is not None,
    )


def is_mcp_tool_approval_question_id(question_id: str) -> bool:
    suffix = str(question_id).removeprefix(MCP_TOOL_APPROVAL_QUESTION_ID_PREFIX)
    return suffix != question_id and suffix.startswith("_")


def build_mcp_tool_approval_question(
    question_id: str,
    server: str,
    tool_name: str,
    connector_name: str | None,
    prompt_options: McpToolApprovalPromptOptions,
    question_override: str | None = None,
) -> RequestUserInputQuestion:
    question = question_override or build_mcp_tool_approval_fallback_message(
        server,
        tool_name,
        connector_name,
    )
    question = f"{question.rstrip('?')}?"

    options = [
        RequestUserInputQuestionOption(
            label=MCP_TOOL_APPROVAL_ACCEPT,
            description="Run the tool and continue.",
        )
    ]
    if prompt_options.allow_session_remember:
        options.append(
            RequestUserInputQuestionOption(
                label=MCP_TOOL_APPROVAL_ACCEPT_FOR_SESSION,
                description="Run the tool and remember this choice for this session.",
            )
        )
    if prompt_options.allow_persistent_approval:
        options.append(
            RequestUserInputQuestionOption(
                label=MCP_TOOL_APPROVAL_ACCEPT_AND_REMEMBER,
                description="Run the tool and remember this choice for future tool calls.",
            )
        )
    options.append(
        RequestUserInputQuestionOption(
            label=MCP_TOOL_APPROVAL_CANCEL,
            description="Cancel this tool call.",
        )
    )
    return RequestUserInputQuestion(
        id=str(question_id),
        header="Approve app tool call?",
        question=question,
        is_other=False,
        is_secret=False,
        options=tuple(options),
    )


def build_mcp_tool_approval_fallback_message(
    server: str,
    tool_name: str,
    connector_name: str | None,
) -> str:
    actor = _trimmed(connector_name)
    if actor is None:
        actor = "this app" if server == CODEX_APPS_MCP_SERVER_NAME else f"the {server} MCP server"
    return f'Allow {actor} to run tool "{tool_name}"?'


def build_mcp_tool_approval_display_params(
    tool_params: JsonValue | None,
) -> tuple[RenderedMcpToolApprovalParam, ...] | None:
    if not isinstance(tool_params, Mapping):
        return None
    return tuple(
        RenderedMcpToolApprovalParam(name=str(name), value=value, display_name=str(name))
        for name, value in sorted(tool_params.items(), key=lambda item: str(item[0]))
    )


def build_mcp_tool_approval_elicitation_meta(
    server: str,
    metadata: McpToolApprovalMetadata | Mapping[str, JsonValue] | None,
    tool_params: JsonValue | None,
    tool_params_display: Iterable[RenderedMcpToolApprovalParam | Mapping[str, JsonValue]]
    | None,
    prompt_options: McpToolApprovalPromptOptions,
) -> dict[str, JsonValue] | None:
    metadata = (
        metadata
        if isinstance(metadata, McpToolApprovalMetadata) or metadata is None
        else McpToolApprovalMetadata.from_mapping(metadata)
    )
    meta: dict[str, JsonValue] = {
        APPROVAL_KIND_KEY: APPROVAL_KIND_MCP_TOOL_CALL,
    }
    if prompt_options.allow_session_remember and prompt_options.allow_persistent_approval:
        meta[PERSIST_KEY] = [PERSIST_SESSION, PERSIST_ALWAYS]
    elif prompt_options.allow_session_remember:
        meta[PERSIST_KEY] = PERSIST_SESSION
    elif prompt_options.allow_persistent_approval:
        meta[PERSIST_KEY] = PERSIST_ALWAYS

    if metadata is not None:
        if metadata.tool_title is not None:
            meta[TOOL_TITLE_KEY] = metadata.tool_title
        if metadata.tool_description is not None:
            meta[TOOL_DESCRIPTION_KEY] = metadata.tool_description
        if server == CODEX_APPS_MCP_SERVER_NAME and (
            metadata.connector_id is not None
            or metadata.connector_name is not None
            or metadata.connector_description is not None
        ):
            meta[SOURCE_KEY] = SOURCE_CONNECTOR
            if metadata.connector_id is not None:
                meta[CONNECTOR_ID_KEY] = metadata.connector_id
            if metadata.connector_name is not None:
                meta[CONNECTOR_NAME_KEY] = metadata.connector_name
            if metadata.connector_description is not None:
                meta[CONNECTOR_DESCRIPTION_KEY] = metadata.connector_description

    if tool_params is not None:
        meta[TOOL_PARAMS_KEY] = tool_params
    if tool_params_display is not None:
        meta[TOOL_PARAMS_DISPLAY_KEY] = [
            param.to_mapping()
            if isinstance(param, RenderedMcpToolApprovalParam)
            else dict(param)
            for param in tool_params_display
        ]

    return meta or None


def requires_mcp_tool_approval(
    annotations: ToolAnnotations | Mapping[str, JsonValue] | None,
) -> bool:
    annotations = ToolAnnotations.from_value(annotations)
    destructive_hint = annotations.destructive_hint if annotations is not None else None
    if destructive_hint is True:
        return True

    read_only_hint = annotations.read_only_hint if annotations is not None else None
    if read_only_hint is True:
        return False

    open_world_hint = annotations.open_world_hint if annotations is not None else None
    return (destructive_hint if destructive_hint is not None else True) or (
        open_world_hint if open_world_hint is not None else True
    )


def normalize_approval_decision_for_mode(
    decision: McpToolApprovalDecision,
    approval_mode: AppToolApproval | str,
) -> McpToolApprovalDecision:
    approval = AppToolApproval(approval_mode)
    if approval is AppToolApproval.PROMPT and decision.kind in {
        McpToolApprovalDecisionKind.ACCEPT_FOR_SESSION,
        McpToolApprovalDecisionKind.ACCEPT_AND_REMEMBER,
    }:
        return McpToolApprovalDecision.accept()
    return decision


def mcp_tool_approval_is_remembered(
    store: ApprovalStore,
    key: McpToolApprovalKey | Mapping[str, JsonValue],
) -> bool:
    return store.get(key) == ReviewDecision.approved_for_session()


def remember_mcp_tool_approval(
    store: ApprovalStore,
    key: McpToolApprovalKey | Mapping[str, JsonValue],
) -> None:
    store.put(key, ReviewDecision.approved_for_session())


def apply_mcp_tool_approval_decision(
    store: ApprovalStore,
    decision: McpToolApprovalDecision,
    session_approval_key: McpToolApprovalKey | Mapping[str, JsonValue] | None = None,
    persistent_approval_key: McpToolApprovalKey | Mapping[str, JsonValue] | None = None,
    persist_persistent_approval: Callable[[McpToolApprovalKey | Mapping[str, JsonValue]], object]
    | None = None,
) -> None:
    if decision.kind is McpToolApprovalDecisionKind.ACCEPT_FOR_SESSION:
        if session_approval_key is not None:
            remember_mcp_tool_approval(store, session_approval_key)
        return

    if decision.kind is McpToolApprovalDecisionKind.ACCEPT_AND_REMEMBER:
        if persistent_approval_key is not None:
            if persist_persistent_approval is not None:
                try:
                    persist_persistent_approval(persistent_approval_key)
                except Exception:
                    pass
            remember_mcp_tool_approval(store, persistent_approval_key)
        elif session_approval_key is not None:
            remember_mcp_tool_approval(store, session_approval_key)


def guardian_rejection_message(rationale: str | None = None) -> str:
    rationale = (rationale or "").strip()
    if rationale == "":
        rationale = "Auto-reviewer denied the action without a specific rationale."
    return (
        "This action was rejected due to unacceptable risk.\n"
        f"Reason: {rationale}\n"
        f"{GUARDIAN_REJECTION_INSTRUCTIONS}"
    )


def guardian_timeout_message() -> str:
    return GUARDIAN_TIMEOUT_INSTRUCTIONS


def mcp_tool_approval_decision_from_guardian(
    decision: ReviewDecision | Mapping[str, JsonValue] | str,
    rejection_rationale: str | None = None,
) -> McpToolApprovalDecision:
    decision = ReviewDecision.from_mapping(decision)
    if decision.type in {
        "approved",
        "approved_execpolicy_amendment",
        "network_policy_amendment",
    }:
        return McpToolApprovalDecision.accept()
    if decision.type == "approved_for_session":
        return McpToolApprovalDecision.accept_for_session()
    if decision.type == "denied":
        return McpToolApprovalDecision.decline(guardian_rejection_message(rejection_rationale))
    if decision.type == "timed_out":
        return McpToolApprovalDecision.decline(guardian_timeout_message())
    if decision.type == "abort":
        return McpToolApprovalDecision.decline()
    raise ValueError(f"unknown review decision: {decision.type}")


def mcp_elicitation_response_from_guardian_decision_parts(
    decision: ReviewDecision | Mapping[str, JsonValue] | str,
    denial_message: str | None = None,
) -> ElicitationResponse:
    decision = ReviewDecision.from_mapping(decision)
    if decision.type in {
        "approved",
        "approved_for_session",
        "approved_execpolicy_amendment",
        "network_policy_amendment",
    }:
        return ElicitationResponse(
            action=ElicitationAction.ACCEPT,
            content={},
            meta=mcp_elicitation_auto_meta(),
        )
    if decision.type == "denied":
        return mcp_elicitation_decline_with_message(
            denial_message or "Guardian denied this request."
        )
    if decision.type == "timed_out":
        return mcp_elicitation_decline_with_message(guardian_timeout_message())
    if decision.type == "abort":
        return ElicitationResponse(
            action=ElicitationAction.CANCEL,
            meta=mcp_elicitation_auto_meta(),
        )
    raise ValueError(f"unknown review decision: {decision.type}")


def mcp_elicitation_decline_with_message(message: str) -> ElicitationResponse:
    meta = mcp_elicitation_auto_meta()
    meta[MCP_ELICITATION_DECLINE_MESSAGE_KEY] = str(message)
    return ElicitationResponse(
        action=ElicitationAction.DECLINE,
        meta=meta,
    )


def mcp_elicitation_decline_without_message() -> ElicitationResponse:
    return ElicitationResponse(
        action=ElicitationAction.DECLINE,
        meta=mcp_elicitation_auto_meta(),
    )


def mcp_elicitation_auto_meta() -> dict[str, JsonValue]:
    return {APPROVALS_REVIEWER_KEY: ApprovalsReviewer.AUTO_REVIEW.value}


def request_user_input_response_from_elicitation_content(
    content: JsonValue | None,
) -> RequestUserInputResponse | None:
    if content is None:
        return RequestUserInputResponse(answers={})
    if not isinstance(content, Mapping):
        return None
    answers = {}
    for question_id, value in content.items():
        if isinstance(value, str):
            raw_answers = (value,)
        elif isinstance(value, list | tuple):
            raw_answers = tuple(item for item in value if isinstance(item, str))
        else:
            continue
        answers[str(question_id)] = RequestUserInputAnswer(raw_answers)
    return RequestUserInputResponse(answers)


def parse_mcp_tool_approval_response(
    response: RequestUserInputResponse | Mapping[str, JsonValue] | None,
    question_id: str,
) -> McpToolApprovalDecision:
    if response is None:
        return McpToolApprovalDecision.cancel()
    if not isinstance(response, RequestUserInputResponse):
        response = RequestUserInputResponse.from_mapping(response)

    answer = response.answers.get(question_id)
    if answer is None:
        return McpToolApprovalDecision.cancel()
    answers = answer.answers
    if any(value == MCP_TOOL_APPROVAL_DECLINE_SYNTHETIC for value in answers):
        return McpToolApprovalDecision.decline()
    if any(value == MCP_TOOL_APPROVAL_ACCEPT_FOR_SESSION for value in answers):
        return McpToolApprovalDecision.accept_for_session()
    if any(value == MCP_TOOL_APPROVAL_ACCEPT_AND_REMEMBER for value in answers):
        return McpToolApprovalDecision.accept_and_remember()
    if any(value == MCP_TOOL_APPROVAL_ACCEPT for value in answers):
        return McpToolApprovalDecision.accept()
    return McpToolApprovalDecision.cancel()


def parse_mcp_tool_approval_elicitation_response(
    response: ElicitationResponse | Mapping[str, JsonValue] | None,
    question_id: str,
) -> McpToolApprovalDecision:
    if response is None:
        return McpToolApprovalDecision.cancel()
    if not isinstance(response, ElicitationResponse):
        response = ElicitationResponse.from_mapping(response)

    if response.action is ElicitationAction.ACCEPT:
        persist = response.meta.get(PERSIST_KEY) if response.meta is not None else None
        if persist == PERSIST_SESSION:
            return McpToolApprovalDecision.accept_for_session()
        if persist == PERSIST_ALWAYS:
            return McpToolApprovalDecision.accept_and_remember()

        decision = parse_mcp_tool_approval_response(
            request_user_input_response_from_elicitation_content(response.content),
            question_id,
        )
        return McpToolApprovalDecision.accept() if decision.kind is McpToolApprovalDecisionKind.CANCEL else decision
    if response.action is ElicitationAction.DECLINE:
        return McpToolApprovalDecision.decline()
    return McpToolApprovalDecision.cancel()


def declared_openai_file_input_param_names(
    meta: Mapping[str, JsonValue] | None,
) -> tuple[str, ...]:
    if meta is None:
        return ()
    raw = meta.get(MCP_TOOL_OPENAI_FILE_PARAMS_META_KEY)
    if not isinstance(raw, list | tuple):
        return ()
    return tuple(value for value in raw if isinstance(value, str) and value != "")


def openai_file_input_params_for_server(
    server: str,
    meta: Mapping[str, JsonValue] | None,
) -> tuple[str, ...] | None:
    if server != CODEX_APPS_MCP_SERVER_NAME:
        return None
    params = declared_openai_file_input_param_names(meta)
    return params or None


def get_mcp_app_resource_uri(meta: Mapping[str, JsonValue] | None) -> str | None:
    if meta is None:
        return None
    ui = meta.get("ui")
    if isinstance(ui, Mapping):
        resource_uri = ui.get("resourceUri")
        if isinstance(resource_uri, str):
            return resource_uri
    resource_uri = meta.get(MCP_TOOL_UI_RESOURCE_URI_META_KEY)
    if isinstance(resource_uri, str):
        return resource_uri
    output_template = meta.get(MCP_TOOL_OPENAI_OUTPUT_TEMPLATE_META_KEY)
    return output_template if isinstance(output_template, str) else None


def codex_apps_meta_from_tool_meta(
    meta: Mapping[str, JsonValue] | None,
) -> dict[str, JsonValue] | None:
    if meta is None:
        return None
    codex_apps_meta = meta.get(MCP_TOOL_CODEX_APPS_META_KEY)
    return dict(codex_apps_meta) if isinstance(codex_apps_meta, Mapping) else None


def build_mcp_tool_call_request_meta(
    server: str,
    call_id: str,
    metadata: McpToolApprovalMetadata | Mapping[str, JsonValue] | None = None,
    turn_metadata: Mapping[str, JsonValue] | None = None,
) -> dict[str, JsonValue] | None:
    metadata = (
        metadata
        if isinstance(metadata, McpToolApprovalMetadata) or metadata is None
        else McpToolApprovalMetadata.from_mapping(metadata)
    )
    request_meta: dict[str, JsonValue] = {}
    if turn_metadata is not None:
        request_meta[X_CODEX_TURN_METADATA_HEADER] = dict(turn_metadata)

    if server == CODEX_APPS_MCP_SERVER_NAME:
        codex_apps_meta = dict(metadata.codex_apps_meta or {}) if metadata is not None else {}
        codex_apps_meta["call_id"] = str(call_id)
        request_meta[MCP_TOOL_CODEX_APPS_META_KEY] = codex_apps_meta

    if metadata is not None and metadata.plugin_id is not None:
        request_meta[MCP_TOOL_PLUGIN_ID_META_KEY] = metadata.plugin_id

    return request_meta or None


def with_mcp_tool_call_thread_id_meta(
    meta: Mapping[str, JsonValue] | JsonValue | None,
    thread_id: str,
) -> JsonValue:
    if meta is None:
        return {MCP_TOOL_THREAD_ID_META_KEY: str(thread_id)}
    if isinstance(meta, Mapping):
        updated = dict(meta)
        updated[MCP_TOOL_THREAD_ID_META_KEY] = str(thread_id)
        return updated
    return meta


def sanitize_mcp_tool_result_for_model(
    supports_image_input: bool,
    result: CallToolResult | Mapping[str, JsonValue] | str,
) -> CallToolResult | str:
    if isinstance(result, str):
        return result
    call_tool_result = result if isinstance(result, CallToolResult) else CallToolResult.from_mapping(result)
    if supports_image_input:
        return call_tool_result

    return CallToolResult(
        content=tuple(_sanitize_mcp_content_block_for_model(block) for block in call_tool_result.content),
        structured_content=call_tool_result.structured_content,
        is_error=call_tool_result.is_error,
        meta=call_tool_result.meta,
    )


def truncate_mcp_tool_result_for_event(
    result: CallToolResult | Mapping[str, JsonValue] | str,
    max_bytes: int = MCP_TOOL_CALL_EVENT_RESULT_MAX_BYTES,
) -> CallToolResult | str:
    if isinstance(result, str):
        return _truncate_middle_chars_by_bytes(result, max_bytes)

    call_tool_result = result if isinstance(result, CallToolResult) else CallToolResult.from_mapping(result)
    try:
        serialized = json.dumps(
            call_tool_result.to_mapping(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        return call_tool_result

    if len(serialized.encode("utf-8")) <= max_bytes:
        return call_tool_result

    return CallToolResult(
        content=({"type": "text", "text": _truncate_middle_chars_by_bytes(serialized, max_bytes)},),
        structured_content=None,
        is_error=call_tool_result.is_error,
        meta=None,
    )


def custom_mcp_tool_approval_mode(
    user_mcp_servers_config: Mapping[str, McpServerApprovalConfig | Mapping[str, JsonValue]] | None,
    active_plugin_mcp_servers_configs: Iterable[
        Mapping[str, McpServerApprovalConfig | Mapping[str, JsonValue]]
    ]
    | None,
    server: str,
    tool_name: str,
) -> AppToolApproval:
    user_configured_mode = custom_mcp_tool_approval_mode_from_config(
        user_mcp_servers_config,
        server,
        tool_name,
    )
    if user_configured_mode is not None:
        return user_configured_mode

    for plugin_mcp_servers_config in active_plugin_mcp_servers_configs or ():
        plugin_configured_mode = custom_mcp_tool_approval_mode_from_config(
            plugin_mcp_servers_config,
            server,
            tool_name,
        )
        if plugin_configured_mode is not None:
            return plugin_configured_mode

    return AppToolApproval.AUTO


def custom_mcp_tool_approval_mode_from_config(
    mcp_servers_config: Mapping[str, McpServerApprovalConfig | Mapping[str, JsonValue]] | None,
    server: str,
    tool_name: str,
) -> AppToolApproval | None:
    if mcp_servers_config is None:
        return None
    server_config = mcp_servers_config.get(server)
    if server_config is None:
        return None
    parsed = (
        server_config
        if isinstance(server_config, McpServerApprovalConfig)
        else McpServerApprovalConfig.from_mapping(server_config)
    )
    return parsed.approval_mode_for_tool(tool_name)


def _optional_app_tool_approval(value: JsonValue) -> AppToolApproval | None:
    if value is None:
        return None
    if isinstance(value, AppToolApproval):
        return value
    return AppToolApproval(str(value))


def _optional_str(value: JsonValue) -> str | None:
    return None if value is None else str(value)


def _trimmed(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _metadata_str(meta: Mapping[str, JsonValue], key: str) -> str | None:
    value = meta.get(key)
    return value if isinstance(value, str) else None


def _metadata_owned_string(meta: Mapping[str, JsonValue], key: str) -> str | None:
    return _trimmed(_metadata_str(meta, key))


def _meta_requests_approval_request(meta: JsonValue | None) -> bool:
    return isinstance(meta, Mapping) and _metadata_str(meta, REQUEST_TYPE_KEY) == REQUEST_TYPE_APPROVAL_REQUEST


def _requested_schema_has_properties(schema: JsonValue | None) -> bool:
    if not isinstance(schema, Mapping):
        return False
    properties = schema.get("properties")
    return isinstance(properties, Mapping) and bool(properties)


def _connector_description(
    accessible_connectors: Iterable[Mapping[str, JsonValue] | object] | None,
    connector_id: str,
) -> str | None:
    for connector in accessible_connectors or ():
        if isinstance(connector, Mapping):
            candidate_id = connector.get("id")
            description = connector.get("description")
        else:
            candidate_id = getattr(connector, "id", None)
            description = getattr(connector, "description", None)
        if candidate_id == connector_id and description is not None:
            return str(description)
    return None


def _optional_string_tuple(value: JsonValue) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


def _sanitize_mcp_content_block_for_model(block: JsonValue) -> JsonValue:
    if isinstance(block, Mapping) and block.get("type") == "image":
        return {"type": "text", "text": MCP_IMAGE_CONTENT_OMITTED_TEXT}
    return block


def _truncate_middle_chars_by_bytes(text: str, max_bytes: int) -> str:
    if max_bytes <= 0:
        return f"...{len(text)} chars truncated..."
    if len(text.encode("utf-8")) <= max_bytes:
        return text

    left_budget = max_bytes // 2
    right_budget = max_bytes - left_budget
    left = _take_utf8_prefix(text, left_budget)
    right = _take_utf8_suffix(text, right_budget)
    removed_chars = max(len(text) - len(left) - len(right), 0)
    if right and len(left) + len(right) > len(text):
        right = ""
        removed_chars = max(len(text) - len(left), 0)
    return f"{left}...{removed_chars} chars truncated...{right}"


def _take_utf8_prefix(text: str, max_bytes: int) -> str:
    if max_bytes <= 0:
        return ""
    return text.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")


def _take_utf8_suffix(text: str, max_bytes: int) -> str:
    if max_bytes <= 0:
        return ""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[-max_bytes:].decode("utf-8", errors="ignore")


__all__ = [
    "ElicitationResponse",
    "GUARDIAN_REJECTION_INSTRUCTIONS",
    "GUARDIAN_TIMEOUT_INSTRUCTIONS",
    "GuardianElicitationReview",
    "GuardianElicitationReviewKind",
    "GuardianMcpAnnotations",
    "GuardianMcpToolReviewRequest",
    "MCP_CALL_COUNT_METRIC",
    "MCP_CALL_DURATION_METRIC",
    "MCP_IMAGE_CONTENT_OMITTED_TEXT",
    "MCP_RESULT_TELEMETRY_DID_TRIGGER_SERVER_USER_FLOW_KEY",
    "MCP_RESULT_TELEMETRY_META_KEY",
    "MCP_RESULT_TELEMETRY_SERVER_USER_FLOW_SPAN_ATTR",
    "MCP_RESULT_TELEMETRY_SPAN_KEY",
    "MCP_RESULT_TELEMETRY_TARGET_ID_KEY",
    "MCP_RESULT_TELEMETRY_TARGET_ID_MAX_CHARS",
    "MCP_RESULT_TELEMETRY_TARGET_ID_SPAN_ATTR",
    "MCP_TOOL_CALL_EVENT_RESULT_MAX_BYTES",
    "MCP_TOOL_CODEX_APPS_META_KEY",
    "MCP_TOOL_OPENAI_FILE_PARAMS_META_KEY",
    "MCP_TOOL_OPENAI_OUTPUT_TEMPLATE_META_KEY",
    "MCP_TOOL_PLUGIN_ID_META_KEY",
    "MCP_TOOL_THREAD_ID_META_KEY",
    "MCP_TOOL_UI_RESOURCE_URI_META_KEY",
    "MCP_TOOL_APPROVAL_ACCEPT",
    "MCP_TOOL_APPROVAL_ACCEPT_AND_REMEMBER",
    "MCP_TOOL_APPROVAL_ACCEPT_FOR_SESSION",
    "MCP_TOOL_APPROVAL_CANCEL",
    "MCP_TOOL_APPROVAL_DECLINE_SYNTHETIC",
    "MCP_TOOL_APPROVAL_QUESTION_ID_PREFIX",
    "MCP_TOOL_APPROVAL_PERSIST_VALUE",
    "MCP_ELICITATION_DECLINE_MESSAGE_KEY",
    "McpAppInvocation",
    "McpAppInvocationType",
    "McpAppUsageMetadata",
    "McpInvocation",
    "McpServerApprovalConfig",
    "McpServerToolConfig",
    "McpToolApprovalDecision",
    "McpToolApprovalDecisionKind",
    "McpToolApprovalConfigEdit",
    "McpToolApprovalKey",
    "McpToolApprovalMetadata",
    "McpToolApprovalPromptOptions",
    "RenderedMcpToolApprovalParam",
    "apply_mcp_tool_approval_decision",
    "build_guardian_mcp_tool_review_request",
    "build_mcp_app_used_invocation",
    "build_mcp_tool_approval_display_params",
    "build_mcp_tool_approval_elicitation_meta",
    "build_mcp_tool_approval_fallback_message",
    "build_mcp_tool_approval_question",
    "build_mcp_tool_call_request_meta",
    "codex_apps_meta_from_tool_meta",
    "codex_app_tool_approval_config_edit",
    "custom_mcp_tool_approval_mode",
    "custom_mcp_tool_approval_config_edit",
    "custom_mcp_tool_approval_mode_from_config",
    "declared_openai_file_input_param_names",
    "get_mcp_app_resource_uri",
    "guardian_elicitation_review_request",
    "guardian_rejection_message",
    "guardian_timeout_message",
    "is_mcp_tool_approval_question_id",
    "lookup_mcp_app_usage_metadata",
    "lookup_mcp_tool_metadata",
    "mcp_app_invocation_type",
    "mcp_call_metric_tags",
    "mcp_elicitation_auto_meta",
    "mcp_elicitation_decline_with_message",
    "mcp_elicitation_decline_without_message",
    "mcp_elicitation_request_id",
    "mcp_elicitation_response_from_guardian_decision_parts",
    "mcp_result_span_telemetry_attributes",
    "mcp_tool_approval_decision_from_guardian",
    "mcp_tool_approval_config_edit_for_key",
    "mcp_tool_approval_is_remembered",
    "mcp_tool_approval_prompt_options",
    "normalize_approval_decision_for_mode",
    "openai_file_input_params_for_server",
    "parse_mcp_tool_approval_elicitation_response",
    "parse_mcp_tool_approval_response",
    "persistent_mcp_tool_approval_key",
    "plugin_mcp_tool_approval_config_edit",
    "remember_mcp_tool_approval",
    "request_user_input_response_from_elicitation_content",
    "requires_mcp_tool_approval",
    "sanitize_metric_tag_value",
    "sanitize_mcp_tool_result_for_model",
    "session_mcp_tool_approval_key",
    "truncate_str_to_char_boundary",
    "truncate_mcp_tool_result_for_event",
    "with_mcp_tool_call_thread_id_meta",
    "X_CODEX_TURN_METADATA_HEADER",
]
