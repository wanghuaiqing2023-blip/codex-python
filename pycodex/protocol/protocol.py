"""Codex session protocol primitives.

Ported in slices from ``codex/codex-rs/protocol/src/protocol.rs``.  This module
starts with transport-safe SQ/EQ wrappers and independent data models that are
used by rollout, app-server, and agent orchestration ports.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .account import PlanType as AccountPlanType
from .agent_path import AgentPath
from .approvals import (
    ApplyPatchApprovalRequestEvent,
    ElicitationAction,
    ElicitationRequestEvent,
    ExecApprovalRequestEvent,
    ExecPolicyAmendment,
    FileChange,
    GuardianAssessmentEvent,
    NetworkApprovalContext,
    NetworkApprovalProtocol,
    NetworkPolicyAmendment,
    ReviewDecision,
)
from .config_types import (
    ApprovalsReviewer,
    AskForApproval,
    CollaborationMode,
    ModeKind,
    Personality,
    ReasoningEffort,
    ReasoningSummary,
    Settings,
    WindowsSandboxLevel,
)
from .ids import SessionId, ThreadId
from .dynamic_tools import DynamicToolCallOutputContentItem, DynamicToolCallRequest, DynamicToolResponse
from .mcp import CallToolResult, RequestId
from .memory_citation import MemoryCitation
from .models import (
    ActivePermissionProfile,
    AdditionalPermissionProfile,
    ContentItem,
    FileSystemSandboxPolicy,
    MessagePhase,
    PermissionProfile,
    ResponseInputItem,
    SandboxEnforcement,
    SandboxPolicy,
)
from .num_format import format_with_separators
from .parse_command import ParsedCommand
from .plan_tool import UpdatePlanArgs
from .request_permissions import RequestPermissionProfile, RequestPermissionsEvent, RequestPermissionsResponse
from .request_user_input import RequestUserInputEvent, RequestUserInputResponse
from .user_input import TextElement, UserInput

JsonValue = Any
_OPTION_UNSET = object()

USER_INSTRUCTIONS_OPEN_TAG = "<user_instructions>"
USER_INSTRUCTIONS_CLOSE_TAG = "</user_instructions>"
ENVIRONMENT_CONTEXT_OPEN_TAG = "<environment_context>"
ENVIRONMENT_CONTEXT_CLOSE_TAG = "</environment_context>"
APPS_INSTRUCTIONS_OPEN_TAG = "<apps_instructions>"
APPS_INSTRUCTIONS_CLOSE_TAG = "</apps_instructions>"
SKILLS_INSTRUCTIONS_OPEN_TAG = "<skills_instructions>"
SKILLS_INSTRUCTIONS_CLOSE_TAG = "</skills_instructions>"
PLUGINS_INSTRUCTIONS_OPEN_TAG = "<plugins_instructions>"
PLUGINS_INSTRUCTIONS_CLOSE_TAG = "</plugins_instructions>"
COLLABORATION_MODE_OPEN_TAG = "<collaboration_mode>"
COLLABORATION_MODE_CLOSE_TAG = "</collaboration_mode>"
REALTIME_CONVERSATION_OPEN_TAG = "<realtime_conversation>"
REALTIME_CONVERSATION_CLOSE_TAG = "</realtime_conversation>"
USER_MESSAGE_BEGIN = "## My request for Codex:"

MAX_THREAD_GOAL_OBJECTIVE_CHARS = 4000
BASELINE_TOKENS = 12000


def _mapping(value: JsonValue, label: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return value


def _required_str(value: Mapping[str, JsonValue], key: str) -> str:
    if key not in value:
        raise KeyError(key)
    raw = value[key]
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


def _optional_str(value: Mapping[str, JsonValue], key: str) -> str | None:
    raw = value.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


def _required_int(value: Mapping[str, JsonValue], key: str) -> int:
    if key not in value:
        raise KeyError(key)
    raw = value[key]
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise TypeError(f"{key} must be an integer")
    return raw


def _required_u32(value: Mapping[str, JsonValue], key: str) -> int:
    raw = _required_int(value, key)
    if raw < 0 or raw > 0xFFFF_FFFF:
        raise ValueError(f"{key} must be an unsigned 32-bit integer")
    return raw


def _required_number(value: Mapping[str, JsonValue], key: str) -> float:
    if key not in value:
        raise KeyError(key)
    raw = value[key]
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise TypeError(f"{key} must be a number")
    return float(raw)


def _optional_int(value: Mapping[str, JsonValue], key: str) -> int | None:
    raw = value.get(key)
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise TypeError(f"{key} must be an integer")
    return raw


def _str_tuple(value: JsonValue, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Iterable):
        raise TypeError(f"{label} must be a list of strings")
    items = tuple(value)
    if not all(isinstance(item, str) for item in items):
        raise TypeError(f"{label} must be a list of strings")
    return items


def _path_tuple(value: JsonValue, label: str) -> tuple[Path, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Iterable):
        raise TypeError(f"{label} must be a list of paths")
    return tuple(Path(str(item)) for item in value)


def _is_absolute_protocol_path(path: Path) -> bool:
    raw = str(path)
    return (
        Path(raw).is_absolute()
        or PurePosixPath(raw).is_absolute()
        or PureWindowsPath(raw).is_absolute()
        or raw.startswith(("/", "\\"))
    )


def _required_absolute_path(value: Mapping[str, JsonValue], key: str) -> Path:
    path = Path(_required_str(value, key))
    if not _is_absolute_protocol_path(path):
        raise ValueError(f"{key} must be an absolute path")
    return path


def _required_bool(value: Mapping[str, JsonValue], key: str, default: bool | None = None) -> bool:
    raw = value.get(key, default)
    if raw is None:
        raise KeyError(key)
    if not isinstance(raw, bool):
        raise TypeError(f"{key} must be a bool")
    return raw


def _snake_to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


def _to_json(value: JsonValue) -> JsonValue:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, AgentPath):
        return str(value)
    if isinstance(value, GitSha):
        return value.to_json()
    if isinstance(value, ThreadId | SessionId | RequestId):
        return value.to_json()
    if is_dataclass(value):
        to_mapping = getattr(value, "to_mapping", None)
        if callable(to_mapping):
            return to_mapping()
        return {
            field.name: _to_json(getattr(value, field.name))
            for field in fields(value)
            if getattr(value, field.name) is not None
        }
    if isinstance(value, Mapping):
        return {str(key): _to_json(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_to_json(item) for item in value]
    return value


def _payload_to_mapping(payload: JsonValue) -> dict[str, JsonValue]:
    if payload is None:
        return {}
    data = _to_json(payload)
    if not isinstance(data, Mapping):
        raise TypeError("payload must serialize to a mapping")
    return dict(data)


@dataclass(frozen=True)
class TurnEnvironmentSelection:
    environment_id: str
    cwd: Path

    def __post_init__(self) -> None:
        if not isinstance(self.environment_id, str):
            raise TypeError("environment_id must be a string")
        cwd = self.cwd if isinstance(self.cwd, Path) else Path(str(self.cwd))
        if not _is_absolute_protocol_path(cwd):
            raise ValueError("cwd must be an absolute path")
        object.__setattr__(self, "cwd", cwd)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "TurnEnvironmentSelection":
        data = _mapping(value, "turn environment selection")
        return cls(environment_id=_required_str(data, "environment_id"), cwd=_required_absolute_path(data, "cwd"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"environment_id": self.environment_id, "cwd": str(self.cwd)}


@dataclass(frozen=True)
class GitSha:
    value: str

    @classmethod
    def new(cls, sha: str) -> "GitSha":
        return cls(sha)

    def to_json(self) -> str:
        return self.value

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class W3cTraceContext:
    traceparent: str | None = None
    tracestate: str | None = None

    def __post_init__(self) -> None:
        if self.traceparent is not None and not isinstance(self.traceparent, str):
            raise TypeError("traceparent must be a string")
        if self.tracestate is not None and not isinstance(self.tracestate, str):
            raise TypeError("tracestate must be a string")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "W3cTraceContext":
        data = _mapping(value, "w3c trace context")
        return cls(
            traceparent=_optional_str(data, "traceparent"),
            tracestate=_optional_str(data, "tracestate"),
        )

    def to_mapping(self) -> dict[str, str]:
        data: dict[str, str] = {}
        if self.traceparent is not None:
            data["traceparent"] = self.traceparent
        if self.tracestate is not None:
            data["tracestate"] = self.tracestate
        return data


@dataclass(frozen=True)
class McpServerRefreshConfig:
    mcp_servers: JsonValue
    mcp_oauth_credentials_store_mode: JsonValue

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "McpServerRefreshConfig":
        data = _mapping(value, "mcp server refresh config")
        return cls(
            mcp_servers=data["mcp_servers"],
            mcp_oauth_credentials_store_mode=data["mcp_oauth_credentials_store_mode"],
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "mcp_servers": self.mcp_servers,
            "mcp_oauth_credentials_store_mode": self.mcp_oauth_credentials_store_mode,
        }


class ThreadMemoryMode(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"


@dataclass(frozen=True)
class InterAgentCommunication:
    author: AgentPath
    recipient: AgentPath
    content: str
    trigger_turn: bool
    other_recipients: tuple[AgentPath, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.author, AgentPath):
            object.__setattr__(self, "author", AgentPath.from_string(str(self.author)))
        if not isinstance(self.recipient, AgentPath):
            object.__setattr__(self, "recipient", AgentPath.from_string(str(self.recipient)))
        if not isinstance(self.other_recipients, tuple):
            object.__setattr__(self, "other_recipients", tuple(self.other_recipients))
        object.__setattr__(
            self,
            "other_recipients",
            tuple(
                recipient if isinstance(recipient, AgentPath) else AgentPath.from_string(str(recipient))
                for recipient in self.other_recipients
            ),
        )

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "InterAgentCommunication":
        data = _mapping(value, "inter-agent communication")
        other_recipients = data.get("other_recipients", ())
        if isinstance(other_recipients, str) or not isinstance(other_recipients, Iterable) or isinstance(other_recipients, Mapping):
            raise TypeError("other_recipients must be a list")
        return cls(
            author=AgentPath.from_string(_required_str(data, "author")),
            recipient=AgentPath.from_string(_required_str(data, "recipient")),
            other_recipients=tuple(AgentPath.from_string(str(recipient)) for recipient in other_recipients),
            content=_required_str(data, "content"),
            trigger_turn=_required_bool(data, "trigger_turn"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "author": str(self.author),
            "recipient": str(self.recipient),
            "other_recipients": [str(recipient) for recipient in self.other_recipients],
            "content": self.content,
            "trigger_turn": self.trigger_turn,
        }

    def to_response_input_item(self) -> ResponseInputItem:
        return ResponseInputItem.message(
            "assistant",
            (
                ContentItem.output_text(
                    json.dumps(
                        self.to_mapping(),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                ),
            ),
            phase=MessagePhase.COMMENTARY,
        )

    @classmethod
    def is_message_content(cls, content: Iterable[ContentItem | JsonValue]) -> bool:
        return cls.from_message_content(content) is not None

    @classmethod
    def from_message_content(cls, content: Iterable[ContentItem | JsonValue]) -> "InterAgentCommunication | None":
        try:
            items = tuple(
                item if isinstance(item, ContentItem) else ContentItem.from_mapping(item)
                for item in content
            )
        except (TypeError, ValueError):
            return None
        if len(items) != 1 or items[0].type not in {"input_text", "output_text"}:
            return None
        try:
            return cls.from_mapping(json.loads(items[0].text or ""))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None


@dataclass(frozen=True)
class Submission:
    id: str
    op: "Op"
    trace: W3cTraceContext | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "Submission":
        data = _mapping(value, "submission")
        trace = data.get("trace")
        return cls(
            id=_required_str(data, "id"),
            op=Op.from_mapping(data["op"]),
            trace=W3cTraceContext.from_mapping(trace) if trace is not None else None,
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"id": self.id, "op": self.op.to_mapping()}
        if self.trace is not None:
            data["trace"] = self.trace.to_mapping()
        return data


class AdditionalContextKind(str, Enum):
    UNTRUSTED = "untrusted"
    APPLICATION = "application"


@dataclass(frozen=True)
class AdditionalContextEntry:
    value: str
    kind: AdditionalContextKind

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError("value must be a string")
        if not isinstance(self.kind, AdditionalContextKind):
            object.__setattr__(self, "kind", AdditionalContextKind(str(self.kind)))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "AdditionalContextEntry":
        if isinstance(value, cls):
            return value
        data = _mapping(value, "additional_context entry")
        return cls(
            value=_required_str(data, "value"),
            kind=AdditionalContextKind(_required_str(data, "kind")),
        )

    @classmethod
    def from_value(cls, value: "AdditionalContextEntry | Mapping[str, Any] | Any") -> "AdditionalContextEntry":
        if isinstance(value, cls):
            return value
        if isinstance(value, Mapping):
            return cls.from_mapping(value)
        return cls(
            value=_required_str({"value": getattr(value, "value")}, "value"),
            kind=AdditionalContextKind(str(getattr(value, "kind"))),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"value": self.value, "kind": self.kind.value}


@dataclass(frozen=True)
class Op:
    type: str
    fields: Mapping[str, JsonValue] | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "Op":
        data = dict(_mapping(value, "op"))
        op_type = _required_str(data, "type")
        data.pop("type")
        if op_type == "request_user_input_response":
            op_type = "user_input_answer"
        if op_type == "realtime_conversation_start":
            return cls.realtime_conversation_start(ConversationStartParams.from_mapping(data))
        if op_type == "realtime_conversation_audio":
            return cls.realtime_conversation_audio(ConversationAudioParams.from_mapping(data))
        if op_type == "realtime_conversation_text":
            return cls.realtime_conversation_text(ConversationTextParams.from_mapping(data))
        if op_type == "realtime_conversation_close":
            return cls.realtime_conversation_close()
        if op_type == "realtime_conversation_list_voices":
            return cls.realtime_conversation_list_voices()
        if op_type == "user_input":
            return cls.user_input(
                items=data.get("items", ()),
                environments=(
                    tuple(TurnEnvironmentSelection.from_mapping(item) for item in data["environments"])
                    if data.get("environments") is not None
                    else None
                ),
                final_output_json_schema=data.get("final_output_json_schema"),
                responsesapi_client_metadata=_parse_client_metadata(data.get("responsesapi_client_metadata")),
                additional_context=(
                    _parse_additional_context_mapping(data["additional_context"])
                    if data.get("additional_context") is not None
                    else None
                ),
                thread_settings=ThreadSettingsOverrides.from_mapping(data),
            )
        if op_type == "thread_settings":
            return cls.thread_settings(ThreadSettingsOverrides.from_mapping(data))
        if op_type == "inter_agent_communication":
            return cls.inter_agent_communication(InterAgentCommunication.from_mapping(data["communication"]))
        if op_type == "exec_approval":
            return cls.exec_approval(
                id=_required_str(data, "id"),
                decision=ReviewDecision.from_mapping(data["decision"]),
                turn_id=_optional_str(data, "turn_id"),
            )
        if op_type == "patch_approval":
            return cls.patch_approval(
                id=_required_str(data, "id"),
                decision=ReviewDecision.from_mapping(data["decision"]),
            )
        if op_type == "resolve_elicitation":
            return cls.resolve_elicitation(
                server_name=_required_str(data, "server_name"),
                request_id=RequestId.from_value(data["request_id"]),
                decision=ElicitationAction(_required_str(data, "decision")),
                content=data.get("content"),
                meta=data.get("meta"),
            )
        if op_type == "user_input_answer":
            return cls.user_input_answer(
                id=_required_str(data, "id"),
                response=RequestUserInputResponse.from_mapping(data["response"]),
            )
        if op_type == "request_permissions_response":
            return cls.request_permissions_response(
                id=_required_str(data, "id"),
                response=RequestPermissionsResponse.from_mapping(data["response"]),
            )
        if op_type == "dynamic_tool_response":
            return cls.dynamic_tool_response(
                id=_required_str(data, "id"),
                response=DynamicToolResponse.from_mapping(data["response"]),
            )
        if op_type == "refresh_mcp_servers":
            return cls.refresh_mcp_servers(McpServerRefreshConfig.from_mapping(data["config"]))
        if op_type == "set_thread_memory_mode":
            return cls.set_thread_memory_mode(ThreadMemoryMode(_required_str(data, "mode")))
        if op_type == "thread_rollback":
            return cls.thread_rollback(_required_int(data, "num_turns"))
        if op_type == "approve_guardian_denied_action":
            return cls.approve_guardian_denied_action(GuardianAssessmentEvent.from_mapping(data["event"]))
        if op_type == "run_user_shell_command":
            return cls.run_user_shell_command(_required_str(data, "command"))
        if op_type in {
            "interrupt",
            "clean_background_terminals",
            "reload_user_config",
            "compact",
            "shutdown",
        }:
            return cls.simple(op_type)
        return cls(op_type, data)

    @classmethod
    def simple(cls, op_type: str) -> "Op":
        return cls(op_type)

    @classmethod
    def user_input(
        cls,
        items: Iterable[JsonValue],
        environments: Iterable[TurnEnvironmentSelection | JsonValue] | None = None,
        final_output_json_schema: JsonValue | None = None,
        responsesapi_client_metadata: Mapping[str, str] | None = None,
        additional_context: Mapping[str, JsonValue] | None = None,
        thread_settings: "ThreadSettingsOverrides | None" = None,
        **thread_setting_overrides: JsonValue,
    ) -> "Op":
        parsed_items = tuple(item if isinstance(item, UserInput) else UserInput.from_mapping(item) for item in items)
        fields: dict[str, JsonValue] = {
            "items": parsed_items,
            "thread_settings": thread_settings
            if thread_settings is not None
            else ThreadSettingsOverrides.from_mapping(thread_setting_overrides),
        }
        if environments is not None:
            fields["environments"] = tuple(
                item if isinstance(item, TurnEnvironmentSelection) else TurnEnvironmentSelection.from_mapping(item)
                for item in environments
            )
        if final_output_json_schema is not None:
            fields["final_output_json_schema"] = final_output_json_schema
        if responsesapi_client_metadata is not None:
            fields["responsesapi_client_metadata"] = dict(responsesapi_client_metadata)
        if additional_context is not None:
            fields["additional_context"] = _parse_additional_context_mapping(additional_context)
        return cls("user_input", fields)

    @classmethod
    def thread_settings(cls, thread_settings: "ThreadSettingsOverrides") -> "Op":
        return cls("thread_settings", {"thread_settings": thread_settings})

    @classmethod
    def inter_agent_communication(cls, communication: InterAgentCommunication) -> "Op":
        return cls("inter_agent_communication", {"communication": communication})

    @classmethod
    def exec_approval(cls, id: str, decision: ReviewDecision, turn_id: str | None = None) -> "Op":
        fields: dict[str, JsonValue] = {"id": id, "decision": decision}
        if turn_id is not None:
            fields["turn_id"] = turn_id
        return cls("exec_approval", fields)

    @classmethod
    def patch_approval(cls, id: str, decision: ReviewDecision) -> "Op":
        return cls("patch_approval", {"id": id, "decision": decision})

    @classmethod
    def user_input_answer(cls, id: str, response: RequestUserInputResponse) -> "Op":
        return cls("user_input_answer", {"id": id, "response": response})

    @classmethod
    def request_permissions_response(cls, id: str, response: RequestPermissionsResponse) -> "Op":
        return cls("request_permissions_response", {"id": id, "response": response})

    @classmethod
    def dynamic_tool_response(cls, id: str, response: DynamicToolResponse) -> "Op":
        return cls("dynamic_tool_response", {"id": id, "response": response})

    @classmethod
    def refresh_mcp_servers(cls, config: McpServerRefreshConfig) -> "Op":
        return cls("refresh_mcp_servers", {"config": config})

    @classmethod
    def set_thread_memory_mode(cls, mode: ThreadMemoryMode | str) -> "Op":
        return cls("set_thread_memory_mode", {"mode": mode if isinstance(mode, ThreadMemoryMode) else ThreadMemoryMode(str(mode))})

    @classmethod
    def thread_rollback(cls, num_turns: int) -> "Op":
        return cls("thread_rollback", {"num_turns": num_turns})

    @classmethod
    def approve_guardian_denied_action(cls, event: GuardianAssessmentEvent) -> "Op":
        return cls("approve_guardian_denied_action", {"event": event})

    @classmethod
    def run_user_shell_command(cls, command: str) -> "Op":
        return cls("run_user_shell_command", {"command": command})

    @classmethod
    def realtime_conversation_start(cls, params: "ConversationStartParams") -> "Op":
        return cls("realtime_conversation_start", params.to_mapping())

    @classmethod
    def realtime_conversation_audio(cls, params: "ConversationAudioParams") -> "Op":
        return cls("realtime_conversation_audio", params.to_mapping())

    @classmethod
    def realtime_conversation_text(cls, params: "ConversationTextParams") -> "Op":
        return cls("realtime_conversation_text", params.to_mapping())

    @classmethod
    def realtime_conversation_close(cls) -> "Op":
        return cls.simple("realtime_conversation_close")

    @classmethod
    def realtime_conversation_list_voices(cls) -> "Op":
        return cls.simple("realtime_conversation_list_voices")

    @classmethod
    def resolve_elicitation(
        cls,
        server_name: str,
        request_id: RequestId | str | int,
        decision: ElicitationAction | str,
        content: JsonValue | None = None,
        meta: JsonValue | None = None,
    ) -> "Op":
        fields: dict[str, JsonValue] = {
            "server_name": server_name,
            "request_id": RequestId.from_value(request_id),
            "decision": decision if isinstance(decision, ElicitationAction) else ElicitationAction(str(decision)),
        }
        if content is not None:
            fields["content"] = content
        if meta is not None:
            fields["meta"] = meta
        return cls("resolve_elicitation", fields)

    def kind(self) -> str:
        return self.type

    def to_mapping(self) -> dict[str, JsonValue]:
        if self.type == "user_input":
            return _user_input_op_to_mapping(self.fields or {})
        if self.type == "thread_settings":
            thread_settings = (self.fields or {}).get("thread_settings", ThreadSettingsOverrides.default())
            if not isinstance(thread_settings, ThreadSettingsOverrides):
                thread_settings = ThreadSettingsOverrides.from_mapping(thread_settings)
            data = {"type": self.type}
            data.update(thread_settings.to_mapping())
            return data
        data = {"type": self.type}
        for key, value in dict(self.fields or {}).items():
            data[key] = _to_json(value)
        return data


def _parse_client_metadata(value: JsonValue) -> dict[str, str] | None:
    if value is None:
        return None
    data = _mapping(value, "responsesapi_client_metadata")
    parsed: dict[str, str] = {}
    for key, item in data.items():
        if not isinstance(item, str):
            raise TypeError("responsesapi_client_metadata values must be strings")
        parsed[str(key)] = item
    return parsed


def _user_input_op_to_mapping(fields: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    thread_settings = fields.get("thread_settings", ThreadSettingsOverrides.default())
    if not isinstance(thread_settings, ThreadSettingsOverrides):
        thread_settings = ThreadSettingsOverrides.from_mapping(thread_settings)
    data: dict[str, JsonValue] = {
        "type": "user_input",
        "items": [
            item.to_mapping() if isinstance(item, UserInput) else UserInput.from_mapping(item).to_mapping()
            for item in fields.get("items", ())
        ],
    }
    if fields.get("environments") is not None:
        data["environments"] = [
            item.to_mapping()
            if isinstance(item, TurnEnvironmentSelection)
            else TurnEnvironmentSelection.from_mapping(item).to_mapping()
            for item in fields["environments"]
        ]
    if fields.get("final_output_json_schema") is not None:
        data["final_output_json_schema"] = _to_json(fields["final_output_json_schema"])
    if fields.get("responsesapi_client_metadata") is not None:
        data["responsesapi_client_metadata"] = _parse_client_metadata(fields["responsesapi_client_metadata"])
    if fields.get("additional_context") is not None:
        data["additional_context"] = _additional_context_mapping(fields["additional_context"])
    data.update(thread_settings.to_mapping())
    return data


def _additional_context_mapping(value: JsonValue) -> dict[str, JsonValue]:
    data = _mapping(value, "additional_context")
    parsed: dict[str, JsonValue] = {}
    for key, item in data.items():
        if not isinstance(key, str):
            raise TypeError("additional_context keys must be strings")
        parsed[key] = AdditionalContextEntry.from_value(item).to_mapping()
    return parsed


def _parse_additional_context_mapping(value: JsonValue) -> dict[str, AdditionalContextEntry]:
    data = _mapping(value, "additional_context")
    parsed: dict[str, AdditionalContextEntry] = {}
    for key, item in data.items():
        if not isinstance(key, str):
            raise TypeError("additional_context keys must be strings")
        parsed[key] = AdditionalContextEntry.from_value(item)
    return parsed


@dataclass(frozen=True)
class Event:
    id: str
    msg: "EventMsg"

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "Event":
        data = _mapping(value, "event")
        return cls(id=_required_str(data, "id"), msg=EventMsg.from_mapping(data["msg"]))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"id": self.id, "msg": self.msg.to_mapping()}


@dataclass(frozen=True)
class EventMsg:
    type: str
    payload: JsonValue = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "EventMsg":
        data = dict(_mapping(value, "event msg"))
        event_type = _required_str(data, "type")
        data.pop("type")
        if event_type == "turn_started":
            event_type = "task_started"
        elif event_type == "turn_complete":
            event_type = "task_complete"
        payload_parser = _EVENT_PAYLOAD_PARSERS.get(event_type)
        payload: JsonValue = payload_parser(data) if payload_parser is not None else data
        return cls(event_type, payload)

    @classmethod
    def with_payload(cls, event_type: str, payload: JsonValue = None) -> "EventMsg":
        return cls(event_type, payload)

    def kind(self) -> str:
        return self.type

    def to_mapping(self) -> dict[str, JsonValue]:
        data = {"type": self.type}
        data.update(_payload_to_mapping(self.payload))
        return data

    def as_legacy_events(self, show_raw_agent_reasoning: bool = False) -> list["EventMsg"]:
        legacy = getattr(self.payload, "as_legacy_events", None)
        if callable(legacy):
            return list(legacy(show_raw_agent_reasoning))
        return []


class Product(str, Enum):
    CHATGPT = "chatgpt"
    CODEX = "codex"
    ATLAS = "atlas"

    @classmethod
    def parse(cls, value: str) -> "Product":
        normalized = value.strip().lower()
        return cls(normalized)

    @classmethod
    def from_session_source_name(cls, value: str) -> "Product | None":
        normalized = value.strip().lower()
        try:
            return cls(normalized)
        except ValueError:
            return None

    def to_app_platform(self) -> str:
        return {
            Product.CHATGPT: "chat",
            Product.CODEX: "codex",
            Product.ATLAS: "atlas",
        }[self]

    def matches_product_restriction(self, products: Iterable["Product"]) -> bool:
        products_tuple = tuple(products)
        return not products_tuple or self in products_tuple


class ThreadSource(str, Enum):
    USER = "user"
    SUBAGENT = "subagent"
    MEMORY_CONSOLIDATION = "memory_consolidation"

    @classmethod
    def parse(cls, value: str) -> "ThreadSource":
        try:
            return cls(value)
        except ValueError as exc:
            raise ValueError(f"unknown thread source: {value}") from exc

    def __str__(self) -> str:
        return self.value


class InternalSessionSource(str, Enum):
    MEMORY_CONSOLIDATION = "memory_consolidation"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class SubAgentSource:
    type: str
    parent_thread_id: ThreadId | None = None
    depth: int | None = None
    agent_path: AgentPath | None = None
    agent_nickname: str | None = None
    agent_role: str | None = None
    other: str | None = None

    @classmethod
    def review(cls) -> "SubAgentSource":
        return cls("review")

    @classmethod
    def compact(cls) -> "SubAgentSource":
        return cls("compact")

    @classmethod
    def memory_consolidation(cls) -> "SubAgentSource":
        return cls("memory_consolidation")

    @classmethod
    def thread_spawn(
        cls,
        parent_thread_id: ThreadId,
        depth: int,
        agent_path: AgentPath | None = None,
        agent_nickname: str | None = None,
        agent_role: str | None = None,
    ) -> "SubAgentSource":
        return cls(
            "thread_spawn",
            parent_thread_id=parent_thread_id,
            depth=depth,
            agent_path=agent_path,
            agent_nickname=agent_nickname,
            agent_role=agent_role,
        )

    @classmethod
    def other_source(cls, value: str) -> "SubAgentSource":
        return cls("other", other=value)

    def __str__(self) -> str:
        if self.type == "thread_spawn":
            return f"thread_spawn_{self.parent_thread_id}_d{self.depth}"
        if self.type == "other":
            return self.other or ""
        return self.type


@dataclass(frozen=True)
class SessionSource:
    type: str
    custom: str | None = None
    internal_source: InternalSessionSource | None = None
    subagent_source: SubAgentSource | None = None

    @classmethod
    def cli(cls) -> "SessionSource":
        return cls("cli")

    @classmethod
    def vscode(cls) -> "SessionSource":
        return cls("vscode")

    @classmethod
    def exec(cls) -> "SessionSource":
        return cls("exec")

    @classmethod
    def mcp(cls) -> "SessionSource":
        return cls("mcp")

    @classmethod
    def custom_source(cls, source: str) -> "SessionSource":
        return cls("custom", custom=source)

    @classmethod
    def internal(cls, source: InternalSessionSource) -> "SessionSource":
        return cls("internal", internal_source=source)

    @classmethod
    def subagent(cls, source: SubAgentSource) -> "SessionSource":
        return cls("subagent", subagent_source=source)

    @classmethod
    def unknown(cls) -> "SessionSource":
        return cls("unknown")

    @classmethod
    def default(cls) -> "SessionSource":
        return cls.vscode()

    @classmethod
    def from_startup_arg(cls, value: str) -> "SessionSource":
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("session source must not be empty")
        normalized = trimmed.lower()
        if normalized == "cli":
            return cls.cli()
        if normalized == "vscode":
            return cls.vscode()
        if normalized == "exec":
            return cls.exec()
        if normalized in {"mcp", "appserver", "app-server", "app_server"}:
            return cls.mcp()
        if normalized == "unknown":
            return cls.unknown()
        return cls.custom_source(normalized)

    def is_internal(self) -> bool:
        return self.type == "internal"

    def is_non_root_agent(self) -> bool:
        return self.type in {"internal", "subagent"}

    def get_nickname(self) -> str | None:
        if self.subagent_source is not None and self.subagent_source.type == "thread_spawn":
            return self.subagent_source.agent_nickname
        return None

    def get_agent_role(self) -> str | None:
        if self.subagent_source is not None and self.subagent_source.type == "thread_spawn":
            return self.subagent_source.agent_role
        return None

    def get_agent_path(self) -> AgentPath | None:
        if self.subagent_source is not None and self.subagent_source.type == "thread_spawn":
            return self.subagent_source.agent_path
        return None

    def restriction_product(self) -> Product | None:
        if self.type == "custom" and self.custom is not None:
            return Product.from_session_source_name(self.custom)
        if self.type in {"cli", "vscode", "exec", "mcp", "unknown"}:
            return Product.CODEX
        return None

    def matches_product_restriction(self, products: Iterable[Product]) -> bool:
        products_tuple = tuple(products)
        product = self.restriction_product()
        return not products_tuple or (product is not None and product.matches_product_restriction(products_tuple))

    def __str__(self) -> str:
        if self.type == "custom":
            return self.custom or ""
        if self.type == "internal":
            return f"internal_{self.internal_source}"
        if self.type == "subagent":
            return f"subagent_{self.subagent_source}"
        return self.type


def _parse_session_source(value: JsonValue) -> SessionSource:
    if isinstance(value, SessionSource):
        return value
    if isinstance(value, str):
        return SessionSource.from_startup_arg(value)
    data = _mapping(value, "session source")
    if len(data) != 1:
        raise ValueError("session source must have exactly one variant")
    variant, payload = next(iter(data.items()))
    if variant == "custom":
        if not isinstance(payload, str):
            raise TypeError("custom session source payload must be a string")
        return SessionSource.custom_source(payload)
    if variant == "internal":
        return SessionSource.internal(InternalSessionSource(str(payload)))
    if variant == "subagent":
        return SessionSource.subagent(_parse_subagent_source(payload))
    return SessionSource.from_startup_arg(str(variant))


def _parse_subagent_source(value: JsonValue) -> SubAgentSource:
    if isinstance(value, SubAgentSource):
        return value
    if isinstance(value, str):
        if value == "review":
            return SubAgentSource.review()
        if value == "compact":
            return SubAgentSource.compact()
        if value == "memory_consolidation":
            return SubAgentSource.memory_consolidation()
        return SubAgentSource.other_source(value)
    data = _mapping(value, "subagent source")
    if len(data) != 1:
        raise ValueError("subagent source must have exactly one variant")
    variant, payload = next(iter(data.items()))
    if variant == "thread_spawn":
        payload_data = _mapping(payload, "thread spawn source")
        agent_path = payload_data.get("agent_path")
        return SubAgentSource.thread_spawn(
            parent_thread_id=_parse_thread_id(payload_data["parent_thread_id"]),
            depth=_required_int(payload_data, "depth"),
            agent_path=AgentPath.from_string(agent_path) if isinstance(agent_path, str) else None,
            agent_nickname=_optional_str(payload_data, "agent_nickname"),
            agent_role=_optional_str(payload_data, "agent_role") or _optional_str(payload_data, "agent_type"),
        )
    return _parse_subagent_source(str(variant))


def _subagent_source_to_json(value: SubAgentSource) -> JsonValue:
    if value.type == "thread_spawn":
        data: dict[str, JsonValue] = {
            "parent_thread_id": value.parent_thread_id.to_json() if value.parent_thread_id is not None else None,
            "depth": value.depth,
        }
        if value.agent_path is not None:
            data["agent_path"] = str(value.agent_path)
        if value.agent_nickname is not None:
            data["agent_nickname"] = value.agent_nickname
        if value.agent_role is not None:
            data["agent_role"] = value.agent_role
        return {"thread_spawn": data}
    if value.type == "other":
        return {"other": value.other or ""}
    return value.type


def _session_source_to_json(value: SessionSource) -> JsonValue:
    if value.type == "custom":
        return {"custom": value.custom or ""}
    if value.type == "internal":
        return {"internal": value.internal_source.value if value.internal_source is not None else None}
    if value.type == "subagent":
        return {"subagent": _subagent_source_to_json(value.subagent_source)} if value.subagent_source is not None else {"subagent": None}
    return value.type


@dataclass(frozen=True)
class GranularApprovalConfig:
    sandbox_approval: bool
    rules: bool
    mcp_elicitations: bool
    skill_approval: bool = False
    request_permissions: bool = False

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "GranularApprovalConfig":
        data = _mapping(value, "granular approval config")
        return cls(
            sandbox_approval=_required_bool(data, "sandbox_approval"),
            rules=_required_bool(data, "rules"),
            skill_approval=_required_bool(data, "skill_approval", False),
            request_permissions=_required_bool(data, "request_permissions", False),
            mcp_elicitations=_required_bool(data, "mcp_elicitations"),
        )

    def allows_sandbox_approval(self) -> bool:
        return self.sandbox_approval

    def allows_rules_approval(self) -> bool:
        return self.rules

    def allows_skill_approval(self) -> bool:
        return self.skill_approval

    def allows_request_permissions(self) -> bool:
        return self.request_permissions

    def allows_mcp_elicitations(self) -> bool:
        return self.mcp_elicitations

    def to_mapping(self) -> dict[str, bool]:
        return {
            "sandbox_approval": self.sandbox_approval,
            "rules": self.rules,
            "skill_approval": self.skill_approval,
            "request_permissions": self.request_permissions,
            "mcp_elicitations": self.mcp_elicitations,
        }


def _parse_approval_policy_value(value: JsonValue) -> AskForApproval | GranularApprovalConfig:
    if isinstance(value, str):
        return AskForApproval.parse(value)
    data = _mapping(value, "approval policy")
    if len(data) == 1 and "granular" in data:
        return GranularApprovalConfig.from_mapping(data["granular"])
    raise ValueError("approval policy must be a string or {'granular': {...}}")


def _approval_policy_to_json(value: AskForApproval | GranularApprovalConfig) -> JsonValue:
    if isinstance(value, GranularApprovalConfig):
        return {"granular": value.to_mapping()}
    if not isinstance(value, AskForApproval):
        raise TypeError("approval_policy must be AskForApproval or GranularApprovalConfig")
    return value.value


def approval_policy_display_value(value: AskForApproval | GranularApprovalConfig | str | JsonValue) -> str:
    """Return the Rust-style human label for an approval policy."""

    if isinstance(value, GranularApprovalConfig):
        return "granular"
    if isinstance(value, AskForApproval):
        return value.value
    if isinstance(value, Mapping):
        if "granular" in value:
            return "granular"
        raise ValueError("approval policy must be a string or {'granular': {...}}")
    return AskForApproval.parse(str(value)).value


class NetworkAccess(str, Enum):
    RESTRICTED = "restricted"
    ENABLED = "enabled"

    @classmethod
    def default(cls) -> "NetworkAccess":
        return cls.RESTRICTED

    def is_enabled(self) -> bool:
        return self is NetworkAccess.ENABLED


@dataclass(frozen=True)
class TurnContextNetworkItem:
    allowed_domains: tuple[str, ...] = ()
    denied_domains: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.allowed_domains, tuple):
            object.__setattr__(self, "allowed_domains", tuple(self.allowed_domains))
        if not isinstance(self.denied_domains, tuple):
            object.__setattr__(self, "denied_domains", tuple(self.denied_domains))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "TurnContextNetworkItem":
        data = _mapping(value, "turn context network")
        return cls(
            allowed_domains=_str_tuple(data.get("allowed_domains"), "allowed_domains"),
            denied_domains=_str_tuple(data.get("denied_domains"), "denied_domains"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "allowed_domains": list(self.allowed_domains),
            "denied_domains": list(self.denied_domains),
        }


@dataclass(frozen=True)
class SessionNetworkProxyRuntime:
    env_var: str
    value: str

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "SessionNetworkProxyRuntime":
        data = _mapping(value, "session network proxy")
        return cls(env_var=_required_str(data, "env_var"), value=_required_str(data, "value"))

    def to_mapping(self) -> dict[str, str]:
        return {"env_var": self.env_var, "value": self.value}


@dataclass(frozen=True)
class TurnContextItem:
    cwd: Path
    approval_policy: AskForApproval | GranularApprovalConfig
    sandbox_policy: SandboxPolicy
    model: str
    turn_id: str | None = None
    current_date: str | None = None
    timezone: str | None = None
    permission_profile_value: PermissionProfile | None = None
    network: TurnContextNetworkItem | None = None
    file_system_sandbox_policy: FileSystemSandboxPolicy | None = None
    personality: Personality | None = None
    collaboration_mode: JsonValue | None = None
    realtime_active: bool | None = None
    effort: JsonValue | None = None
    summary: str = "auto"

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "TurnContextItem":
        data = _mapping(value, "turn context item")
        return cls(
            turn_id=_optional_str(data, "turn_id"),
            cwd=Path(_required_str(data, "cwd")),
            current_date=_optional_str(data, "current_date"),
            timezone=_optional_str(data, "timezone"),
            approval_policy=_parse_approval_policy_value(data["approval_policy"]),
            sandbox_policy=SandboxPolicy.from_mapping(data["sandbox_policy"]),
            permission_profile_value=(
                PermissionProfile.from_mapping(data["permission_profile"])
                if data.get("permission_profile") is not None
                else None
            ),
            network=TurnContextNetworkItem.from_mapping(data["network"]) if data.get("network") is not None else None,
            file_system_sandbox_policy=(
                FileSystemSandboxPolicy.from_mapping(data["file_system_sandbox_policy"])
                if data.get("file_system_sandbox_policy") is not None
                else None
            ),
            model=_required_str(data, "model"),
            personality=Personality.parse(data["personality"]) if isinstance(data.get("personality"), str) else None,
            collaboration_mode=data.get("collaboration_mode"),
            realtime_active=data.get("realtime_active"),
            effort=data.get("effort"),
            summary=str(data.get("summary", "auto")),
        )

    def permission_profile(self) -> PermissionProfile:
        if self.permission_profile_value is not None:
            return self.permission_profile_value
        file_system_sandbox_policy = self.file_system_sandbox_policy
        if file_system_sandbox_policy is None:
            file_system_sandbox_policy = FileSystemSandboxPolicy.from_legacy_sandbox_policy_for_cwd(
                self.sandbox_policy,
                self.cwd,
            )
        return PermissionProfile.from_runtime_permissions_with_enforcement(
            self.sandbox_policy_enforcement(),
            file_system_sandbox_policy,
            self.sandbox_policy.network_sandbox_policy(),
        )

    def sandbox_policy_enforcement(self) -> SandboxEnforcement:
        return SandboxEnforcement.from_legacy_sandbox_policy(self.sandbox_policy)

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "cwd": str(self.cwd),
            "approval_policy": _approval_policy_to_json(self.approval_policy),
            "sandbox_policy": self.sandbox_policy.to_mapping(),
            "model": self.model,
            "summary": self.summary,
        }
        if self.turn_id is not None:
            data["turn_id"] = self.turn_id
        if self.current_date is not None:
            data["current_date"] = self.current_date
        if self.timezone is not None:
            data["timezone"] = self.timezone
        if self.permission_profile_value is not None:
            data["permission_profile"] = self.permission_profile_value.to_mapping()
        if self.network is not None:
            data["network"] = self.network.to_mapping()
        if self.file_system_sandbox_policy is not None:
            data["file_system_sandbox_policy"] = self.file_system_sandbox_policy.to_mapping()
        if self.personality is not None:
            data["personality"] = self.personality.value
        if self.collaboration_mode is not None:
            data["collaboration_mode"] = _to_json(self.collaboration_mode)
        if self.realtime_active is not None:
            data["realtime_active"] = self.realtime_active
        if self.effort is not None:
            data["effort"] = _to_json(self.effort)
        return data


@dataclass(frozen=True)
class SessionConfiguredEvent:
    session_id: SessionId
    model: str
    model_provider_id: str
    approval_policy: AskForApproval | GranularApprovalConfig
    permission_profile: PermissionProfile
    cwd: Path
    thread_id: ThreadId | None = None
    forked_from_id: ThreadId | None = None
    thread_source: JsonValue | None = None
    thread_name: str | None = None
    service_tier: str | None = None
    approvals_reviewer: ApprovalsReviewer = ApprovalsReviewer.USER
    active_permission_profile: ActivePermissionProfile | None = None
    reasoning_effort: JsonValue | None = None
    initial_messages: JsonValue | None = None
    network_proxy: SessionNetworkProxyRuntime | None = None
    rollout_path: Path | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "SessionConfiguredEvent":
        data = _mapping(value, "session configured event")
        session_id = _parse_session_id(data["session_id"])
        thread_id = _parse_thread_id(data["thread_id"]) if isinstance(data.get("thread_id"), str) else session_id.to_thread_id()
        if data.get("permission_profile") is not None:
            permission_profile = PermissionProfile.from_mapping(data["permission_profile"])
        elif data.get("sandbox_policy") is not None:
            permission_profile = PermissionProfile.from_legacy_sandbox_policy_for_cwd(
                SandboxPolicy.from_mapping(data["sandbox_policy"]),
                Path(_required_str(data, "cwd")),
            )
        else:
            raise KeyError("permission_profile")
        return cls(
            session_id=session_id,
            thread_id=thread_id,
            forked_from_id=_parse_thread_id(data["forked_from_id"]) if isinstance(data.get("forked_from_id"), str) else None,
            thread_source=data.get("thread_source"),
            thread_name=_optional_str(data, "thread_name"),
            model=_required_str(data, "model"),
            model_provider_id=_required_str(data, "model_provider_id"),
            service_tier=_optional_str(data, "service_tier"),
            approval_policy=_parse_approval_policy_value(data["approval_policy"]),
            approvals_reviewer=ApprovalsReviewer.parse(str(data.get("approvals_reviewer", ApprovalsReviewer.USER.value))),
            permission_profile=permission_profile,
            active_permission_profile=_parse_active_permission_profile(data.get("active_permission_profile")),
            cwd=Path(_required_str(data, "cwd")),
            reasoning_effort=data.get("reasoning_effort"),
            initial_messages=data.get("initial_messages"),
            network_proxy=SessionNetworkProxyRuntime.from_mapping(data["network_proxy"]) if data.get("network_proxy") is not None else None,
            rollout_path=Path(data["rollout_path"]) if isinstance(data.get("rollout_path"), str) else None,
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "session_id": self.session_id.to_json(),
            "thread_id": self.thread_id.to_json() if self.thread_id is not None else self.session_id.to_json(),
            "model": self.model,
            "model_provider_id": self.model_provider_id,
            "approval_policy": _approval_policy_to_json(self.approval_policy),
            "approvals_reviewer": self.approvals_reviewer.value,
            "permission_profile": self.permission_profile.to_mapping(),
            "cwd": str(self.cwd),
        }
        if self.forked_from_id is not None:
            data["forked_from_id"] = self.forked_from_id.to_json()
        if self.thread_source is not None:
            data["thread_source"] = _to_json(self.thread_source)
        if self.thread_name is not None:
            data["thread_name"] = self.thread_name
        if self.service_tier is not None:
            data["service_tier"] = self.service_tier
        if self.active_permission_profile is not None:
            data["active_permission_profile"] = self.active_permission_profile.to_mapping()
        if self.reasoning_effort is not None:
            data["reasoning_effort"] = _to_json(self.reasoning_effort)
        if self.initial_messages is not None:
            data["initial_messages"] = _to_json(self.initial_messages)
        if self.network_proxy is not None:
            data["network_proxy"] = self.network_proxy.to_mapping()
        if self.rollout_path is not None:
            data["rollout_path"] = str(self.rollout_path)
        return data


class NonSteerableTurnKind(str, Enum):
    REVIEW = "review"
    COMPACT = "compact"


@dataclass(frozen=True)
class CodexErrorInfo:
    type: str
    http_status_code: int | None = None
    turn_kind: NonSteerableTurnKind | None = None

    @classmethod
    def context_window_exceeded(cls) -> "CodexErrorInfo":
        return cls("context_window_exceeded")

    @classmethod
    def usage_limit_exceeded(cls) -> "CodexErrorInfo":
        return cls("usage_limit_exceeded")

    @classmethod
    def server_overloaded(cls) -> "CodexErrorInfo":
        return cls("server_overloaded")

    @classmethod
    def cyber_policy(cls) -> "CodexErrorInfo":
        return cls("cyber_policy")

    @classmethod
    def http_connection_failed(cls, http_status_code: int | None = None) -> "CodexErrorInfo":
        return cls("http_connection_failed", http_status_code=http_status_code)

    @classmethod
    def response_stream_connection_failed(cls, http_status_code: int | None = None) -> "CodexErrorInfo":
        return cls("response_stream_connection_failed", http_status_code=http_status_code)

    @classmethod
    def internal_server_error(cls) -> "CodexErrorInfo":
        return cls("internal_server_error")

    @classmethod
    def unauthorized(cls) -> "CodexErrorInfo":
        return cls("unauthorized")

    @classmethod
    def bad_request(cls) -> "CodexErrorInfo":
        return cls("bad_request")

    @classmethod
    def sandbox_error(cls) -> "CodexErrorInfo":
        return cls("sandbox_error")

    @classmethod
    def response_stream_disconnected(cls, http_status_code: int | None = None) -> "CodexErrorInfo":
        return cls("response_stream_disconnected", http_status_code=http_status_code)

    @classmethod
    def response_too_many_failed_attempts(cls, http_status_code: int | None = None) -> "CodexErrorInfo":
        return cls("response_too_many_failed_attempts", http_status_code=http_status_code)

    @classmethod
    def active_turn_not_steerable(cls, turn_kind: NonSteerableTurnKind | str) -> "CodexErrorInfo":
        parsed = turn_kind if isinstance(turn_kind, NonSteerableTurnKind) else NonSteerableTurnKind(str(turn_kind))
        return cls("active_turn_not_steerable", turn_kind=parsed)

    @classmethod
    def thread_rollback_failed(cls) -> "CodexErrorInfo":
        return cls("thread_rollback_failed")

    @classmethod
    def other(cls) -> "CodexErrorInfo":
        return cls("other")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "CodexErrorInfo":
        if isinstance(value, CodexErrorInfo):
            return value
        if isinstance(value, str):
            return cls(_camel_to_snake(value))
        data = _mapping(value, "codex error info")
        if len(data) != 1:
            raise ValueError("codex error info must have exactly one variant")
        variant, payload = next(iter(data.items()))
        variant = _camel_to_snake(str(variant))
        if variant in {
            "http_connection_failed",
            "response_stream_connection_failed",
            "response_stream_disconnected",
            "response_too_many_failed_attempts",
        }:
            payload_data = _mapping(payload or {}, variant)
            status = payload_data.get("http_status_code", payload_data.get("httpStatusCode"))
            if status is not None and (isinstance(status, bool) or not isinstance(status, int)):
                raise TypeError("http_status_code must be an integer")
            return cls(variant, http_status_code=status)
        if variant == "active_turn_not_steerable":
            payload_data = _mapping(payload or {}, variant)
            turn_kind = payload_data.get("turn_kind", payload_data.get("turnKind"))
            if not isinstance(turn_kind, str):
                raise TypeError("turn_kind must be a string")
            return cls.active_turn_not_steerable(turn_kind)
        return cls(variant)

    def affects_turn_status(self) -> bool:
        return self.type not in {"thread_rollback_failed", "active_turn_not_steerable"}

    def to_mapping(self) -> JsonValue:
        if self.type in {
            "http_connection_failed",
            "response_stream_connection_failed",
            "response_stream_disconnected",
            "response_too_many_failed_attempts",
        }:
            return {self.type: {"http_status_code": self.http_status_code}}
        if self.type == "active_turn_not_steerable":
            if self.turn_kind is None:
                raise ValueError("active_turn_not_steerable requires turn_kind")
            return {self.type: {"turn_kind": self.turn_kind.value}}
        return self.type


def _camel_to_snake(value: str) -> str:
    if "_" in value:
        return value
    chars: list[str] = []
    for index, char in enumerate(value):
        if char.isupper() and index > 0:
            chars.append("_")
        chars.append(char.lower())
    return "".join(chars)


def _parse_codex_error_info(value: JsonValue) -> CodexErrorInfo | None:
    return CodexErrorInfo.from_mapping(value) if value is not None else None


@dataclass(frozen=True)
class ErrorEvent:
    message: str
    codex_error_info: CodexErrorInfo | None = None

    def __post_init__(self) -> None:
        if self.codex_error_info is not None and not isinstance(self.codex_error_info, CodexErrorInfo):
            object.__setattr__(self, "codex_error_info", CodexErrorInfo.from_mapping(self.codex_error_info))

    def affects_turn_status(self) -> bool:
        if self.codex_error_info is None:
            return True
        return self.codex_error_info.affects_turn_status()

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"message": self.message}
        if self.codex_error_info is not None:
            data["codex_error_info"] = _to_json(self.codex_error_info)
        return data


@dataclass(frozen=True)
class WarningEvent:
    message: str


class ModelRerouteReason(str, Enum):
    HIGH_RISK_CYBER_ACTIVITY = "high_risk_cyber_activity"


@dataclass(frozen=True)
class ModelRerouteEvent:
    from_model: str
    to_model: str
    reason: ModelRerouteReason


class ModelVerification(str, Enum):
    TRUSTED_ACCESS_FOR_CYBER = "trusted_access_for_cyber"


@dataclass(frozen=True)
class ModelVerificationEvent:
    verifications: tuple[ModelVerification, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.verifications, tuple):
            object.__setattr__(self, "verifications", tuple(self.verifications))


@dataclass(frozen=True)
class ContextCompactedEvent:
    pass


@dataclass(frozen=True)
class TurnCompleteEvent:
    turn_id: str
    last_agent_message: str | None
    completed_at: int | None = None
    duration_ms: int | None = None
    time_to_first_token_ms: int | None = None


@dataclass(frozen=True)
class TurnStartedEvent:
    turn_id: str
    model_context_window: int | None
    trace_id: str | None = None
    started_at: int | None = None
    collaboration_mode_kind: JsonValue = "default"


def _parse_reasoning_effort(value: JsonValue) -> ReasoningEffort | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("reasoning_effort must be a string")
    return ReasoningEffort.parse(value)


def _parse_reasoning_summary(value: JsonValue) -> ReasoningSummary | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("reasoning_summary must be a string")
    return ReasoningSummary.parse(value)


def _parse_personality(value: JsonValue) -> Personality | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("personality must be a string")
    return Personality.parse(value)


def _parse_active_permission_profile(value: JsonValue) -> ActivePermissionProfile | None:
    if value is None:
        return None
    if isinstance(value, ActivePermissionProfile):
        return value
    return ActivePermissionProfile.from_mapping(value)


def _parse_collaboration_mode(value: JsonValue) -> CollaborationMode:
    if isinstance(value, CollaborationMode):
        return value
    data = _mapping(value, "collaboration mode")
    settings_data = _mapping(data["settings"], "collaboration mode settings")
    return CollaborationMode(
        mode=ModeKind.parse(_required_str(data, "mode")),
        settings=Settings(
            model=_required_str(settings_data, "model"),
            reasoning_effort=_parse_reasoning_effort(settings_data.get("reasoning_effort")),
            developer_instructions=_optional_str(settings_data, "developer_instructions"),
        ),
    )


def _collaboration_mode_to_mapping(value: CollaborationMode) -> dict[str, JsonValue]:
    return {
        "mode": value.mode.value,
        "settings": {
            "model": value.settings.model,
            "reasoning_effort": value.settings.reasoning_effort.value
            if value.settings.reasoning_effort is not None
            else None,
            "developer_instructions": value.settings.developer_instructions,
        },
    }


@dataclass(frozen=True)
class ThreadSettingsOverrides:
    cwd: Path | None = None
    workspace_roots: tuple[Path, ...] | None = None
    profile_workspace_roots: tuple[Path, ...] | None = None
    approval_policy: AskForApproval | GranularApprovalConfig | None = None
    approvals_reviewer: ApprovalsReviewer | None = None
    sandbox_policy: SandboxPolicy | None = None
    permission_profile: PermissionProfile | None = None
    active_permission_profile: ActivePermissionProfile | None = None
    windows_sandbox_level: WindowsSandboxLevel | None = None
    model: str | None = None
    effort: ReasoningEffort | None | object = _OPTION_UNSET
    summary: ReasoningSummary | None = None
    service_tier: str | None | object = _OPTION_UNSET
    collaboration_mode: CollaborationMode | None = None
    personality: Personality | None = None

    def __post_init__(self) -> None:
        if self.workspace_roots is not None and not isinstance(self.workspace_roots, tuple):
            object.__setattr__(self, "workspace_roots", tuple(Path(path) for path in self.workspace_roots))
        if self.profile_workspace_roots is not None and not isinstance(self.profile_workspace_roots, tuple):
            object.__setattr__(self, "profile_workspace_roots", tuple(Path(path) for path in self.profile_workspace_roots))

    @classmethod
    def default(cls) -> "ThreadSettingsOverrides":
        return cls()

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ThreadSettingsOverrides":
        data = _mapping(value, "thread settings overrides")
        raw_effort: ReasoningEffort | None | object = _OPTION_UNSET
        if "effort" in data:
            raw_effort = _parse_reasoning_effort(data.get("effort"))
        raw_service_tier: str | None | object = _OPTION_UNSET
        if "service_tier" in data:
            raw_service_tier = _optional_str(data, "service_tier")
        return cls(
            cwd=Path(_required_str(data, "cwd")) if data.get("cwd") is not None else None,
            workspace_roots=_path_tuple(data["workspace_roots"], "workspace_roots") if data.get("workspace_roots") is not None else None,
            profile_workspace_roots=(
                _path_tuple(data["profile_workspace_roots"], "profile_workspace_roots")
                if data.get("profile_workspace_roots") is not None
                else None
            ),
            approval_policy=(
                _parse_approval_policy_value(data["approval_policy"])
                if data.get("approval_policy") is not None
                else None
            ),
            approvals_reviewer=(
                ApprovalsReviewer.parse(_required_str(data, "approvals_reviewer"))
                if data.get("approvals_reviewer") is not None
                else None
            ),
            sandbox_policy=SandboxPolicy.from_mapping(data["sandbox_policy"]) if data.get("sandbox_policy") is not None else None,
            permission_profile=(
                PermissionProfile.from_mapping(data["permission_profile"])
                if data.get("permission_profile") is not None
                else None
            ),
            active_permission_profile=_parse_active_permission_profile(data.get("active_permission_profile")),
            windows_sandbox_level=(
                WindowsSandboxLevel.parse(_required_str(data, "windows_sandbox_level"))
                if data.get("windows_sandbox_level") is not None
                else None
            ),
            model=_optional_str(data, "model"),
            effort=raw_effort,
            summary=_parse_reasoning_summary(data.get("summary")),
            service_tier=raw_service_tier,
            collaboration_mode=(
                _parse_collaboration_mode(data["collaboration_mode"])
                if data.get("collaboration_mode") is not None
                else None
            ),
            personality=_parse_personality(data.get("personality")),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {}
        if self.cwd is not None:
            data["cwd"] = str(self.cwd)
        if self.workspace_roots is not None:
            data["workspace_roots"] = [str(path) for path in self.workspace_roots]
        if self.profile_workspace_roots is not None:
            data["profile_workspace_roots"] = [str(path) for path in self.profile_workspace_roots]
        if self.approval_policy is not None:
            data["approval_policy"] = _approval_policy_to_json(self.approval_policy)
        if self.approvals_reviewer is not None:
            data["approvals_reviewer"] = self.approvals_reviewer.value
        if self.sandbox_policy is not None:
            data["sandbox_policy"] = self.sandbox_policy.to_mapping()
        if self.permission_profile is not None:
            data["permission_profile"] = self.permission_profile.to_mapping()
        if self.active_permission_profile is not None:
            data["active_permission_profile"] = self.active_permission_profile.to_mapping()
        if self.windows_sandbox_level is not None:
            data["windows_sandbox_level"] = self.windows_sandbox_level.value
        if self.model is not None:
            data["model"] = self.model
        if self.effort is not _OPTION_UNSET:
            data["effort"] = self.effort.value if isinstance(self.effort, ReasoningEffort) else None
        if self.summary is not None:
            data["summary"] = self.summary.value
        if self.service_tier is not _OPTION_UNSET:
            data["service_tier"] = self.service_tier
        if self.collaboration_mode is not None:
            data["collaboration_mode"] = _collaboration_mode_to_mapping(self.collaboration_mode)
        if self.personality is not None:
            data["personality"] = self.personality.value
        return data


@dataclass(frozen=True)
class ThreadSettingsSnapshot:
    model: str
    model_provider_id: str
    approval_policy: AskForApproval | GranularApprovalConfig
    approvals_reviewer: ApprovalsReviewer
    permission_profile: PermissionProfile
    cwd: Path
    collaboration_mode: CollaborationMode
    service_tier: str | None = None
    active_permission_profile: ActivePermissionProfile | None = None
    reasoning_effort: ReasoningEffort | None = None
    reasoning_summary: ReasoningSummary | None = None
    personality: Personality | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ThreadSettingsSnapshot":
        data = _mapping(value, "thread settings snapshot")
        return cls(
            model=_required_str(data, "model"),
            model_provider_id=_required_str(data, "model_provider_id"),
            service_tier=_optional_str(data, "service_tier"),
            approval_policy=_parse_approval_policy_value(data["approval_policy"]),
            approvals_reviewer=ApprovalsReviewer.parse(_required_str(data, "approvals_reviewer")),
            permission_profile=PermissionProfile.from_mapping(data["permission_profile"]),
            active_permission_profile=_parse_active_permission_profile(data.get("active_permission_profile")),
            cwd=Path(_required_str(data, "cwd")),
            reasoning_effort=_parse_reasoning_effort(data.get("reasoning_effort")),
            reasoning_summary=_parse_reasoning_summary(data.get("reasoning_summary")),
            personality=_parse_personality(data.get("personality")),
            collaboration_mode=_parse_collaboration_mode(data["collaboration_mode"]),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "model": self.model,
            "model_provider_id": self.model_provider_id,
            "approval_policy": _approval_policy_to_json(self.approval_policy),
            "approvals_reviewer": self.approvals_reviewer.value,
            "permission_profile": self.permission_profile.to_mapping(),
            "cwd": str(self.cwd),
            "collaboration_mode": _collaboration_mode_to_mapping(self.collaboration_mode),
        }
        if self.service_tier is not None:
            data["service_tier"] = self.service_tier
        if self.active_permission_profile is not None:
            data["active_permission_profile"] = self.active_permission_profile.to_mapping()
        if self.reasoning_effort is not None:
            data["reasoning_effort"] = self.reasoning_effort.value
        if self.reasoning_summary is not None:
            data["reasoning_summary"] = self.reasoning_summary.value
        if self.personality is not None:
            data["personality"] = self.personality.value
        return data


@dataclass(frozen=True)
class ThreadSettingsAppliedEvent:
    thread_settings: ThreadSettingsSnapshot

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ThreadSettingsAppliedEvent":
        data = _mapping(value, "thread settings applied event")
        return cls(thread_settings=ThreadSettingsSnapshot.from_mapping(data["thread_settings"]))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"thread_settings": self.thread_settings.to_mapping()}


class HookEventName(str, Enum):
    PRE_TOOL_USE = "pre_tool_use"
    PERMISSION_REQUEST = "permission_request"
    POST_TOOL_USE = "post_tool_use"
    PRE_COMPACT = "pre_compact"
    POST_COMPACT = "post_compact"
    SESSION_START = "session_start"
    USER_PROMPT_SUBMIT = "user_prompt_submit"
    SUBAGENT_START = "subagent_start"
    SUBAGENT_STOP = "subagent_stop"
    STOP = "stop"


class HookHandlerType(str, Enum):
    COMMAND = "command"
    PROMPT = "prompt"
    AGENT = "agent"


class HookExecutionMode(str, Enum):
    SYNC = "sync"
    ASYNC = "async"


class HookScope(str, Enum):
    THREAD = "thread"
    TURN = "turn"


class HookSource(str, Enum):
    SYSTEM = "system"
    USER = "user"
    PROJECT = "project"
    MDM = "mdm"
    SESSION_FLAGS = "session_flags"
    PLUGIN = "plugin"
    CLOUD_REQUIREMENTS = "cloud_requirements"
    LEGACY_MANAGED_CONFIG_FILE = "legacy_managed_config_file"
    LEGACY_MANAGED_CONFIG_MDM = "legacy_managed_config_mdm"
    UNKNOWN = "unknown"


class HookTrustStatus(str, Enum):
    MANAGED = "managed"
    UNTRUSTED = "untrusted"
    TRUSTED = "trusted"
    MODIFIED = "modified"


class HookRunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    STOPPED = "stopped"


class HookOutputEntryKind(str, Enum):
    WARNING = "warning"
    STOP = "stop"
    FEEDBACK = "feedback"
    CONTEXT = "context"
    ERROR = "error"


@dataclass(frozen=True)
class HookOutputEntry:
    kind: HookOutputEntryKind
    text: str

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "HookOutputEntry":
        data = _mapping(value, "hook output entry")
        return cls(kind=HookOutputEntryKind(_required_str(data, "kind")), text=_required_str(data, "text"))

    def to_mapping(self) -> dict[str, str]:
        return {"kind": self.kind.value, "text": self.text}


@dataclass(frozen=True)
class HookRunSummary:
    id: str
    event_name: HookEventName
    handler_type: HookHandlerType
    execution_mode: HookExecutionMode
    scope: HookScope
    source_path: Path
    display_order: int
    status: HookRunStatus
    started_at: int
    source: HookSource = HookSource.UNKNOWN
    status_message: str | None = None
    completed_at: int | None = None
    duration_ms: int | None = None
    entries: tuple[HookOutputEntry, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.entries, tuple):
            object.__setattr__(self, "entries", tuple(self.entries))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "HookRunSummary":
        data = _mapping(value, "hook run summary")
        return cls(
            id=_required_str(data, "id"),
            event_name=HookEventName(_required_str(data, "event_name")),
            handler_type=HookHandlerType(_required_str(data, "handler_type")),
            execution_mode=HookExecutionMode(_required_str(data, "execution_mode")),
            scope=HookScope(_required_str(data, "scope")),
            source_path=Path(_required_str(data, "source_path")),
            source=HookSource(str(data.get("source", HookSource.UNKNOWN.value))),
            display_order=_required_int(data, "display_order"),
            status=HookRunStatus(_required_str(data, "status")),
            status_message=_optional_str(data, "status_message"),
            started_at=_required_int(data, "started_at"),
            completed_at=_optional_int(data, "completed_at"),
            duration_ms=_optional_int(data, "duration_ms"),
            entries=tuple(HookOutputEntry.from_mapping(item) for item in data.get("entries", ())),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "id": self.id,
            "event_name": self.event_name.value,
            "handler_type": self.handler_type.value,
            "execution_mode": self.execution_mode.value,
            "scope": self.scope.value,
            "source_path": str(self.source_path),
            "source": self.source.value,
            "display_order": self.display_order,
            "status": self.status.value,
            "status_message": self.status_message,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "entries": [entry.to_mapping() for entry in self.entries],
        }


@dataclass(frozen=True)
class HookStartedEvent:
    turn_id: str | None
    run: HookRunSummary

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "HookStartedEvent":
        data = _mapping(value, "hook started event")
        return cls(turn_id=_optional_str(data, "turn_id"), run=HookRunSummary.from_mapping(data["run"]))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"turn_id": self.turn_id, "run": self.run.to_mapping()}


@dataclass(frozen=True)
class HookCompletedEvent:
    turn_id: str | None
    run: HookRunSummary

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "HookCompletedEvent":
        data = _mapping(value, "hook completed event")
        return cls(turn_id=_optional_str(data, "turn_id"), run=HookRunSummary.from_mapping(data["run"]))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"turn_id": self.turn_id, "run": self.run.to_mapping()}


class RealtimeConversationVersion(str, Enum):
    V1 = "v1"
    V2 = "v2"

    @classmethod
    def default(cls) -> "RealtimeConversationVersion":
        return cls.V2


class RealtimeOutputModality(str, Enum):
    TEXT = "text"
    AUDIO = "audio"


@dataclass(frozen=True)
class ConversationStartTransport:
    type: str
    sdp: str | None = None

    def __post_init__(self) -> None:
        if self.type == "websocket":
            if self.sdp is not None:
                raise ValueError("websocket transport must not include sdp")
            return
        if self.type == "webrtc":
            if not isinstance(self.sdp, str):
                raise TypeError("webrtc transport sdp must be a string")
            return
        raise ValueError(f"unknown conversation start transport type: {self.type}")

    @classmethod
    def websocket(cls) -> "ConversationStartTransport":
        return cls("websocket")

    @classmethod
    def webrtc(cls, sdp: str) -> "ConversationStartTransport":
        return cls("webrtc", sdp)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ConversationStartTransport":
        data = _mapping(value, "conversation start transport")
        transport_type = _required_str(data, "type")
        if transport_type == "websocket":
            return cls.websocket()
        if transport_type == "webrtc":
            return cls.webrtc(_required_str(data, "sdp"))
        raise ValueError(f"unknown conversation start transport type: {transport_type}")

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"type": self.type}
        if self.type == "webrtc":
            data["sdp"] = self.sdp
        return data


class RealtimeVoice(str, Enum):
    ALLOY = "alloy"
    ARBOR = "arbor"
    ASH = "ash"
    BALLAD = "ballad"
    BREEZE = "breeze"
    CEDAR = "cedar"
    CORAL = "coral"
    COVE = "cove"
    ECHO = "echo"
    EMBER = "ember"
    JUNIPER = "juniper"
    MAPLE = "maple"
    MARIN = "marin"
    SAGE = "sage"
    SHIMMER = "shimmer"
    SOL = "sol"
    SPRUCE = "spruce"
    VALE = "vale"
    VERSE = "verse"

    def wire_name(self) -> str:
        return self.value


_PROMPT_UNSET = object()


@dataclass(frozen=True)
class ConversationStartParams:
    output_modality: RealtimeOutputModality
    prompt: str | None | object = _PROMPT_UNSET
    realtime_session_id: str | None = None
    transport: ConversationStartTransport | None = None
    voice: RealtimeVoice | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ConversationStartParams":
        data = _mapping(value, "conversation start params")
        prompt: str | None | object = _PROMPT_UNSET
        if "prompt" in data:
            prompt = data["prompt"]
            if prompt is not None and not isinstance(prompt, str):
                raise TypeError("prompt must be a string or null")
        return cls(
            output_modality=RealtimeOutputModality(_required_str(data, "output_modality")),
            prompt=prompt,
            realtime_session_id=_optional_str(data, "realtime_session_id"),
            transport=(
                ConversationStartTransport.from_mapping(data["transport"])
                if data.get("transport") is not None
                else None
            ),
            voice=RealtimeVoice(data["voice"]) if isinstance(data.get("voice"), str) else None,
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"output_modality": self.output_modality.value}
        if self.prompt is not _PROMPT_UNSET:
            data["prompt"] = self.prompt
        if self.realtime_session_id is not None:
            data["realtime_session_id"] = self.realtime_session_id
        if self.transport is not None:
            data["transport"] = self.transport.to_mapping()
        if self.voice is not None:
            data["voice"] = self.voice.value
        return data


@dataclass(frozen=True)
class RealtimeAudioFrame:
    data: str
    sample_rate: int
    num_channels: int
    samples_per_channel: int | None = None
    item_id: str | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "RealtimeAudioFrame":
        data = _mapping(value, "realtime audio frame")
        return cls(
            data=_required_str(data, "data"),
            sample_rate=_required_int(data, "sample_rate"),
            num_channels=_required_int(data, "num_channels"),
            samples_per_channel=_optional_int(data, "samples_per_channel"),
            item_id=_optional_str(data, "item_id"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "data": self.data,
            "sample_rate": self.sample_rate,
            "num_channels": self.num_channels,
        }
        if self.samples_per_channel is not None:
            data["samples_per_channel"] = self.samples_per_channel
        if self.item_id is not None:
            data["item_id"] = self.item_id
        return data


@dataclass(frozen=True)
class ConversationAudioParams:
    frame: RealtimeAudioFrame

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ConversationAudioParams":
        data = _mapping(value, "conversation audio params")
        return cls(frame=RealtimeAudioFrame.from_mapping(data["frame"]))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"frame": self.frame.to_mapping()}


@dataclass(frozen=True)
class ConversationTextParams:
    text: str

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ConversationTextParams":
        data = _mapping(value, "conversation text params")
        return cls(text=_required_str(data, "text"))

    def to_mapping(self) -> dict[str, str]:
        return {"text": self.text}


@dataclass(frozen=True)
class RealtimeVoicesList:
    v1: tuple[RealtimeVoice, ...]
    v2: tuple[RealtimeVoice, ...]
    default_v1: RealtimeVoice
    default_v2: RealtimeVoice

    def __post_init__(self) -> None:
        if not isinstance(self.v1, tuple):
            object.__setattr__(self, "v1", tuple(self.v1))
        if not isinstance(self.v2, tuple):
            object.__setattr__(self, "v2", tuple(self.v2))

    @classmethod
    def builtin(cls) -> "RealtimeVoicesList":
        return cls(
            v1=(
                RealtimeVoice.JUNIPER,
                RealtimeVoice.MAPLE,
                RealtimeVoice.SPRUCE,
                RealtimeVoice.EMBER,
                RealtimeVoice.VALE,
                RealtimeVoice.BREEZE,
                RealtimeVoice.ARBOR,
                RealtimeVoice.SOL,
                RealtimeVoice.COVE,
            ),
            v2=(
                RealtimeVoice.ALLOY,
                RealtimeVoice.ASH,
                RealtimeVoice.BALLAD,
                RealtimeVoice.CORAL,
                RealtimeVoice.ECHO,
                RealtimeVoice.SAGE,
                RealtimeVoice.SHIMMER,
                RealtimeVoice.VERSE,
                RealtimeVoice.MARIN,
                RealtimeVoice.CEDAR,
            ),
            default_v1=RealtimeVoice.COVE,
            default_v2=RealtimeVoice.MARIN,
        )

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "RealtimeVoicesList":
        data = _mapping(value, "realtime voices list")
        raw_default_v1 = data.get("defaultV1", data.get("default_v1"))
        raw_default_v2 = data.get("defaultV2", data.get("default_v2"))
        if not isinstance(raw_default_v1, str):
            raise TypeError("defaultV1 must be a string")
        if not isinstance(raw_default_v2, str):
            raise TypeError("defaultV2 must be a string")
        return cls(
            v1=tuple(RealtimeVoice(str(voice)) for voice in data.get("v1", ())),
            v2=tuple(RealtimeVoice(str(voice)) for voice in data.get("v2", ())),
            default_v1=RealtimeVoice(raw_default_v1),
            default_v2=RealtimeVoice(raw_default_v2),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "v1": [voice.value for voice in self.v1],
            "v2": [voice.value for voice in self.v2],
            "defaultV1": self.default_v1.value,
            "defaultV2": self.default_v2.value,
        }


@dataclass(frozen=True)
class RealtimeConversationStartedEvent:
    realtime_session_id: str | None
    version: RealtimeConversationVersion = RealtimeConversationVersion.V2

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "RealtimeConversationStartedEvent":
        data = _mapping(value, "realtime conversation started event")
        return cls(
            realtime_session_id=_optional_str(data, "realtime_session_id"),
            version=RealtimeConversationVersion(_required_str(data, "version")),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"realtime_session_id": self.realtime_session_id, "version": self.version.value}


@dataclass(frozen=True)
class RealtimeConversationRealtimeEvent:
    payload: JsonValue

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "RealtimeConversationRealtimeEvent":
        data = _mapping(value, "realtime conversation realtime event")
        return cls(payload=data["payload"])

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"payload": _to_json(self.payload)}


@dataclass(frozen=True)
class RealtimeConversationClosedEvent:
    reason: str | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "RealtimeConversationClosedEvent":
        data = _mapping(value, "realtime conversation closed event")
        return cls(reason=_optional_str(data, "reason"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {} if self.reason is None else {"reason": self.reason}


@dataclass(frozen=True)
class RealtimeConversationSdpEvent:
    sdp: str

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "RealtimeConversationSdpEvent":
        data = _mapping(value, "realtime conversation sdp event")
        return cls(sdp=_required_str(data, "sdp"))

    def to_mapping(self) -> dict[str, str]:
        return {"sdp": self.sdp}


@dataclass(frozen=True)
class RealtimeConversationListVoicesResponseEvent:
    voices: RealtimeVoicesList

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "RealtimeConversationListVoicesResponseEvent":
        data = _mapping(value, "realtime conversation list voices response event")
        return cls(voices=RealtimeVoicesList.from_mapping(data["voices"]))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"voices": self.voices.to_mapping()}


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "TokenUsage":
        data = _mapping(value, "token usage")
        return cls(
            input_tokens=_required_int(data, "input_tokens"),
            cached_input_tokens=_required_int(data, "cached_input_tokens"),
            output_tokens=_required_int(data, "output_tokens"),
            reasoning_output_tokens=_required_int(data, "reasoning_output_tokens"),
            total_tokens=_required_int(data, "total_tokens"),
        )

    def is_zero(self) -> bool:
        return self.total_tokens == 0

    def cached_input(self) -> int:
        return max(self.cached_input_tokens, 0)

    def non_cached_input(self) -> int:
        return max(self.input_tokens - self.cached_input(), 0)

    def blended_total(self) -> int:
        return max(self.non_cached_input() + max(self.output_tokens, 0), 0)

    def __str__(self) -> str:
        from pycodex.protocol.num_format import format_with_separators

        cached = self.cached_input()
        cached_suffix = f" (+ {format_with_separators(cached)} cached)" if cached > 0 else ""
        reasoning = self.reasoning_output_tokens
        reasoning_suffix = f" (reasoning {format_with_separators(reasoning)})" if reasoning > 0 else ""
        return (
            f"Token usage: total={format_with_separators(self.blended_total())} "
            f"input={format_with_separators(self.non_cached_input())}{cached_suffix} "
            f"output={format_with_separators(self.output_tokens)}{reasoning_suffix}"
        )

    def tokens_in_context_window(self) -> int:
        return self.total_tokens

    def percent_of_context_window_remaining(self, context_window: int) -> int:
        if context_window <= BASELINE_TOKENS:
            return 0
        effective_window = context_window - BASELINE_TOKENS
        used = max(self.tokens_in_context_window() - BASELINE_TOKENS, 0)
        remaining = max(effective_window - used, 0)
        return round(min(max((remaining / effective_window) * 100.0, 0.0), 100.0))

    def add(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            cached_input_tokens=self.cached_input_tokens + other.cached_input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            reasoning_output_tokens=self.reasoning_output_tokens + other.reasoning_output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )

    def to_mapping(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_output_tokens": self.reasoning_output_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(frozen=True)
class TokenUsageInfo:
    total_token_usage: TokenUsage
    last_token_usage: TokenUsage
    model_context_window: int | None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "TokenUsageInfo":
        data = _mapping(value, "token usage info")
        return cls(
            total_token_usage=TokenUsage.from_mapping(data["total_token_usage"]),
            last_token_usage=TokenUsage.from_mapping(data["last_token_usage"]),
            model_context_window=_optional_int(data, "model_context_window"),
        )

    @classmethod
    def new_or_append(
        cls,
        info: "TokenUsageInfo | None",
        last: TokenUsage | None,
        model_context_window: int | None,
    ) -> "TokenUsageInfo | None":
        if info is None and last is None:
            return None
        current = info or cls(TokenUsage(), TokenUsage(), model_context_window)
        if last is not None:
            current = cls(current.total_token_usage.add(last), last, current.model_context_window)
        if model_context_window is not None:
            current = cls(current.total_token_usage, current.last_token_usage, model_context_window)
        return current

    @classmethod
    def full_context_window(cls, context_window: int) -> "TokenUsageInfo":
        return cls(TokenUsage(total_tokens=context_window), TokenUsage(total_tokens=context_window), context_window)

    def fill_to_context_window(self, context_window: int) -> "TokenUsageInfo":
        previous_total = self.total_token_usage.total_tokens
        delta = max(context_window - previous_total, 0)
        return TokenUsageInfo(
            TokenUsage(total_tokens=context_window),
            TokenUsage(total_tokens=delta),
            context_window,
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "total_token_usage": self.total_token_usage.to_mapping(),
            "last_token_usage": self.last_token_usage.to_mapping(),
            "model_context_window": self.model_context_window,
        }


class RateLimitReachedType(str, Enum):
    RATE_LIMIT_REACHED = "rate_limit_reached"
    WORKSPACE_OWNER_CREDITS_DEPLETED = "workspace_owner_credits_depleted"
    WORKSPACE_MEMBER_CREDITS_DEPLETED = "workspace_member_credits_depleted"
    WORKSPACE_OWNER_USAGE_LIMIT_REACHED = "workspace_owner_usage_limit_reached"
    WORKSPACE_MEMBER_USAGE_LIMIT_REACHED = "workspace_member_usage_limit_reached"

    @classmethod
    def parse(cls, value: str) -> "RateLimitReachedType":
        try:
            return cls(value)
        except ValueError:
            raise ValueError(f"unknown rate limit reached type: {value}") from None


@dataclass(frozen=True)
class RateLimitWindow:
    used_percent: float
    window_minutes: int | None = None
    resets_at: int | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "RateLimitWindow":
        data = _mapping(value, "rate limit window")
        return cls(
            used_percent=_required_number(data, "used_percent"),
            window_minutes=_optional_int(data, "window_minutes"),
            resets_at=_optional_int(data, "resets_at"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "used_percent": self.used_percent,
            "window_minutes": self.window_minutes,
            "resets_at": self.resets_at,
        }


@dataclass(frozen=True)
class CreditsSnapshot:
    has_credits: bool
    unlimited: bool
    balance: str | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "CreditsSnapshot":
        data = _mapping(value, "credits snapshot")
        return cls(
            has_credits=_required_bool(data, "has_credits"),
            unlimited=_required_bool(data, "unlimited"),
            balance=_optional_str(data, "balance"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "has_credits": self.has_credits,
            "unlimited": self.unlimited,
            "balance": self.balance,
        }


@dataclass(frozen=True)
class RateLimitSnapshot:
    limit_id: str | None = None
    limit_name: str | None = None
    primary: RateLimitWindow | None = None
    secondary: RateLimitWindow | None = None
    credits: CreditsSnapshot | None = None
    plan_type: AccountPlanType | None = None
    rate_limit_reached_type: RateLimitReachedType | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "RateLimitSnapshot":
        data = _mapping(value, "rate limit snapshot")
        plan_type = data.get("plan_type")
        if plan_type is not None and not isinstance(plan_type, str):
            raise TypeError("plan_type must be a string")
        reached_type = data.get("rate_limit_reached_type")
        if reached_type is not None and not isinstance(reached_type, str):
            raise TypeError("rate_limit_reached_type must be a string")
        return cls(
            limit_id=_optional_str(data, "limit_id"),
            limit_name=_optional_str(data, "limit_name"),
            primary=RateLimitWindow.from_mapping(data["primary"]) if data.get("primary") is not None else None,
            secondary=RateLimitWindow.from_mapping(data["secondary"]) if data.get("secondary") is not None else None,
            credits=CreditsSnapshot.from_mapping(data["credits"]) if data.get("credits") is not None else None,
            plan_type=AccountPlanType.parse(plan_type) if plan_type is not None else None,
            rate_limit_reached_type=(
                RateLimitReachedType.parse(reached_type)
                if reached_type is not None
                else None
            ),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "limit_id": self.limit_id,
            "limit_name": self.limit_name,
            "primary": self.primary.to_mapping() if self.primary is not None else None,
            "secondary": self.secondary.to_mapping() if self.secondary is not None else None,
            "credits": self.credits.to_mapping() if self.credits is not None else None,
            "plan_type": self.plan_type.value if self.plan_type is not None else None,
            "rate_limit_reached_type": (
                self.rate_limit_reached_type.value if self.rate_limit_reached_type is not None else None
            ),
        }


@dataclass(frozen=True)
class TokenCountEvent:
    info: TokenUsageInfo | None
    rate_limits: RateLimitSnapshot | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "TokenCountEvent":
        data = _mapping(value, "token count event")
        return cls(
            info=TokenUsageInfo.from_mapping(data["info"]) if data.get("info") is not None else None,
            rate_limits=(
                RateLimitSnapshot.from_mapping(data["rate_limits"])
                if data.get("rate_limits") is not None
                else None
            ),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "info": self.info.to_mapping() if self.info is not None else None,
            "rate_limits": self.rate_limits.to_mapping() if self.rate_limits is not None else None,
        }


@dataclass(frozen=True)
class FinalOutput:
    token_usage: TokenUsage

    def __str__(self) -> str:
        usage = self.token_usage
        cached = f" (+ {_format_with_separators(usage.cached_input())} cached)" if usage.cached_input() > 0 else ""
        reasoning = (
            f" (reasoning {_format_with_separators(usage.reasoning_output_tokens)})"
            if usage.reasoning_output_tokens > 0
            else ""
        )
        return (
            "Token usage: "
            f"total={_format_with_separators(usage.blended_total())} "
            f"input={_format_with_separators(usage.non_cached_input())}{cached} "
            f"output={_format_with_separators(usage.output_tokens)}{reasoning}"
        )


@dataclass(frozen=True)
class AgentMessageEvent:
    message: str
    phase: MessagePhase | None = None
    memory_citation: MemoryCitation | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.message, str):
            raise TypeError("message must be a string")
        if self.phase is not None and not isinstance(self.phase, MessagePhase):
            if not isinstance(self.phase, str):
                raise TypeError("phase must be a string")
            object.__setattr__(self, "phase", MessagePhase(self.phase))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "message": self.message,
            "phase": self.phase.value if self.phase is not None else None,
            "memory_citation": (
                self.memory_citation.to_mapping()
                if self.memory_citation is not None
                else None
            ),
        }


def _sequence_tuple(value: object, field_name: str, *, allow_none: bool = False) -> tuple[object, ...] | None:
    if value is None:
        if allow_none:
            return None
        raise TypeError(f"{field_name} must be a list")
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise TypeError(f"{field_name} must be a list")
    return tuple(value)


def _optional_str_tuple(value: object, field_name: str) -> tuple[str, ...] | None:
    values = _sequence_tuple(value, field_name, allow_none=True)
    if values is None:
        return None
    normalized: list[str] = []
    for item in values:
        if not isinstance(item, str):
            raise TypeError(f"{field_name} entries must be strings")
        normalized.append(item)
    return tuple(normalized)


def _optional_image_detail_tuple(value: object, field_name: str) -> tuple[JsonValue | None, ...]:
    values = _sequence_tuple(value, field_name)
    assert values is not None
    normalized: list[JsonValue | None] = []
    for item in values:
        if item is None:
            normalized.append(None)
        elif isinstance(item, str):
            normalized.append(item)
        elif isinstance(getattr(item, "value", None), str):
            normalized.append(getattr(item, "value"))
        else:
            raise TypeError(f"{field_name} entries must be strings or None")
    return tuple(normalized)


def _path_tuple(value: object, field_name: str) -> tuple[Path, ...]:
    values = _sequence_tuple(value, field_name)
    assert values is not None
    paths: list[Path] = []
    for item in values:
        if not isinstance(item, (str, Path)):
            raise TypeError(f"{field_name} entries must be paths")
        paths.append(Path(item))
    return tuple(paths)


def _text_element_tuple(value: object, field_name: str) -> tuple[TextElement, ...]:
    values = _sequence_tuple(value, field_name)
    assert values is not None
    elements: list[TextElement] = []
    for item in values:
        if isinstance(item, TextElement):
            elements.append(item)
        else:
            elements.append(TextElement.from_mapping(item))
    return tuple(elements)


def _parse_agent_reasoning_section_break(data: Mapping[str, JsonValue]) -> "AgentReasoningSectionBreakEvent":
    return AgentReasoningSectionBreakEvent(
        item_id=_required_str(data, "item_id") if "item_id" in data else "",
        summary_index=_required_int(data, "summary_index") if "summary_index" in data else 0,
    )


def _parse_reasoning_content_delta(data: Mapping[str, JsonValue]) -> "ReasoningContentDeltaEvent":
    return ReasoningContentDeltaEvent(
        thread_id=_required_str(data, "thread_id"),
        turn_id=_required_str(data, "turn_id"),
        item_id=_required_str(data, "item_id"),
        delta=_required_str(data, "delta"),
        summary_index=_required_int(data, "summary_index") if "summary_index" in data else 0,
    )


def _parse_reasoning_raw_content_delta(data: Mapping[str, JsonValue]) -> "ReasoningRawContentDeltaEvent":
    return ReasoningRawContentDeltaEvent(
        thread_id=_required_str(data, "thread_id"),
        turn_id=_required_str(data, "turn_id"),
        item_id=_required_str(data, "item_id"),
        delta=_required_str(data, "delta"),
        content_index=_required_int(data, "content_index") if "content_index" in data else 0,
    )


def _parse_patch_apply_begin(data: Mapping[str, JsonValue]) -> "PatchApplyBeginEvent":
    return PatchApplyBeginEvent(
        call_id=_required_str(data, "call_id"),
        turn_id=_required_str(data, "turn_id") if "turn_id" in data else "",
        auto_approved=_required_bool(data, "auto_approved"),
        changes=_file_changes_from_mapping(data["changes"]),
    )


def _parse_patch_apply_end(data: Mapping[str, JsonValue]) -> "PatchApplyEndEvent":
    return PatchApplyEndEvent(
        call_id=_required_str(data, "call_id"),
        turn_id=_required_str(data, "turn_id") if "turn_id" in data else "",
        stdout=_required_str(data, "stdout"),
        stderr=_required_str(data, "stderr"),
        success=_required_bool(data, "success"),
        changes=_file_changes_from_mapping(data.get("changes", {})),
        status=PatchApplyStatus(_required_str(data, "status")),
    )


@dataclass(frozen=True)
class UserMessageEvent:
    message: str
    images: tuple[str, ...] | None = None
    image_details: tuple[JsonValue | None, ...] = ()
    local_images: tuple[Path, ...] = ()
    local_image_details: tuple[JsonValue | None, ...] = ()
    text_elements: tuple[TextElement, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.message, str):
            raise TypeError("message must be a string")
        object.__setattr__(self, "images", _optional_str_tuple(self.images, "images"))
        object.__setattr__(self, "image_details", _optional_image_detail_tuple(self.image_details, "image_details"))
        object.__setattr__(self, "local_images", _path_tuple(self.local_images, "local_images"))
        object.__setattr__(
            self,
            "local_image_details",
            _optional_image_detail_tuple(self.local_image_details, "local_image_details"),
        )
        object.__setattr__(self, "text_elements", _text_element_tuple(self.text_elements, "text_elements"))

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"message": self.message}
        if self.images is not None:
            data["images"] = list(self.images)
        if self.image_details:
            data["image_details"] = _to_json(self.image_details)
        data["local_images"] = [str(path) for path in self.local_images]
        if self.local_image_details:
            data["local_image_details"] = _to_json(self.local_image_details)
        data["text_elements"] = [
            {
                "byte_range": {
                    "start": element.byte_range.start,
                    "end": element.byte_range.end,
                },
                "placeholder": element.placeholder_for_conversion_only(),
            }
            for element in self.text_elements
        ]
        return data


@dataclass(frozen=True)
class AgentReasoningEvent:
    text: str


@dataclass(frozen=True)
class AgentReasoningRawContentEvent:
    text: str


@dataclass(frozen=True)
class AgentReasoningSectionBreakEvent:
    item_id: str = ""
    summary_index: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.item_id, str):
            raise TypeError("item_id must be a string")
        if isinstance(self.summary_index, bool) or not isinstance(self.summary_index, int):
            raise TypeError("summary_index must be an integer")


@dataclass(frozen=True)
class RawResponseItemEvent:
    item: JsonValue


@dataclass(frozen=True)
class ItemStartedEvent:
    thread_id: ThreadId
    turn_id: str
    item: JsonValue
    started_at_ms: int

    def as_legacy_events(self, show_raw_agent_reasoning: bool = False) -> list["EventMsg"]:
        from .items import TurnItem

        item = self.item if isinstance(self.item, TurnItem) else TurnItem.from_mapping(self.item)
        if item.type == "WebSearch":
            return [EventMsg.with_payload("web_search_begin", WebSearchBeginEvent(item.item.id))]
        if item.type == "ImageView":
            return []
        if item.type == "ImageGeneration":
            return [EventMsg.with_payload("image_generation_begin", ImageGenerationBeginEvent(item.item.id))]
        if item.type == "FileChange":
            return [item.item.as_legacy_begin_event(self.turn_id)]
        if item.type == "McpToolCall":
            return [item.item.as_legacy_begin_event()]
        return []


@dataclass(frozen=True)
class ItemCompletedEvent:
    thread_id: ThreadId
    turn_id: str
    item: JsonValue
    completed_at_ms: int = 0

    def as_legacy_events(self, show_raw_agent_reasoning: bool = False) -> list["EventMsg"]:
        from .items import TurnItem

        item = self.item if isinstance(self.item, TurnItem) else TurnItem.from_mapping(self.item)
        if item.type == "FileChange":
            event = item.item.as_legacy_end_event(self.turn_id)
            return [event] if event is not None else []
        return item.as_legacy_events(show_raw_agent_reasoning)


@dataclass(frozen=True)
class AgentMessageContentDeltaEvent:
    thread_id: str
    turn_id: str
    item_id: str
    delta: str

    def as_legacy_events(self, show_raw_agent_reasoning: bool = False) -> list["EventMsg"]:
        return []


@dataclass(frozen=True)
class PlanDeltaEvent:
    thread_id: str
    turn_id: str
    item_id: str
    delta: str


@dataclass(frozen=True)
class ReasoningContentDeltaEvent:
    thread_id: str
    turn_id: str
    item_id: str
    delta: str
    summary_index: int = 0

    def __post_init__(self) -> None:
        for field_name in ("thread_id", "turn_id", "item_id", "delta"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string")
        if isinstance(self.summary_index, bool) or not isinstance(self.summary_index, int):
            raise TypeError("summary_index must be an integer")

    def as_legacy_events(self, show_raw_agent_reasoning: bool = False) -> list["EventMsg"]:
        return []


@dataclass(frozen=True)
class ReasoningRawContentDeltaEvent:
    thread_id: str
    turn_id: str
    item_id: str
    delta: str
    content_index: int = 0

    def __post_init__(self) -> None:
        for field_name in ("thread_id", "turn_id", "item_id", "delta"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string")
        if isinstance(self.content_index, bool) or not isinstance(self.content_index, int):
            raise TypeError("content_index must be an integer")

    def as_legacy_events(self, show_raw_agent_reasoning: bool = False) -> list["EventMsg"]:
        return []


@dataclass(frozen=True)
class DynamicToolCallResponseEvent:
    call_id: str
    turn_id: str
    tool: str
    arguments: JsonValue
    content_items: tuple[JsonValue, ...]
    completed_at_ms: int = 0
    namespace: str | None = None
    success: bool = False
    error: str | None = None
    duration: JsonValue | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.content_items, tuple):
            object.__setattr__(self, "content_items", tuple(self.content_items))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "call_id": self.call_id,
            "turn_id": self.turn_id,
            "completed_at_ms": self.completed_at_ms,
            "namespace": self.namespace,
            "tool": self.tool,
            "arguments": self.arguments,
            "content_items": _to_json(self.content_items),
            "success": self.success,
            "error": self.error,
            "duration": self.duration,
        }


@dataclass(frozen=True)
class GitInfo:
    commit_hash: GitSha | str | None = None
    branch: str | None = None
    repository_url: str | None = None

    def __post_init__(self) -> None:
        if self.commit_hash is not None and not isinstance(self.commit_hash, GitSha):
            object.__setattr__(self, "commit_hash", GitSha.new(str(self.commit_hash)))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "GitInfo":
        data = _mapping(value, "git info")
        commit_hash = data.get("commit_hash")
        return cls(
            commit_hash=GitSha.new(commit_hash) if isinstance(commit_hash, str) else None,
            branch=_optional_str(data, "branch"),
            repository_url=_optional_str(data, "repository_url"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {}
        if self.commit_hash is not None:
            data["commit_hash"] = self.commit_hash.to_json()
        if self.branch is not None:
            data["branch"] = self.branch
        if self.repository_url is not None:
            data["repository_url"] = self.repository_url
        return data


@dataclass(frozen=True)
class SessionMeta:
    id: ThreadId
    timestamp: str
    cwd: Path
    originator: str
    cli_version: str
    source: SessionSource = None  # type: ignore[assignment]
    forked_from_id: ThreadId | None = None
    thread_source: ThreadSource | None = None
    agent_nickname: str | None = None
    agent_role: str | None = None
    agent_path: str | None = None
    model_provider: str | None = None
    base_instructions: JsonValue | None = None
    dynamic_tools: JsonValue | None = None
    memory_mode: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, ThreadId):
            object.__setattr__(self, "id", _parse_thread_id(self.id))
        if self.forked_from_id is not None and not isinstance(self.forked_from_id, ThreadId):
            object.__setattr__(self, "forked_from_id", _parse_thread_id(self.forked_from_id))
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(str(self.cwd)))
        if self.source is None:
            object.__setattr__(self, "source", SessionSource.default())
        elif not isinstance(self.source, SessionSource):
            object.__setattr__(self, "source", SessionSource.from_startup_arg(str(self.source)))
        if self.thread_source is not None and not isinstance(self.thread_source, ThreadSource):
            object.__setattr__(self, "thread_source", ThreadSource.parse(str(self.thread_source)))

    @classmethod
    def default(cls) -> "SessionMeta":
        return cls(
            id=ThreadId.default(),
            timestamp="",
            cwd=Path(),
            originator="",
            cli_version="",
            source=SessionSource.default(),
        )

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "SessionMeta":
        data = _mapping(value, "session meta")
        return cls(
            id=_parse_thread_id(data["id"]),
            forked_from_id=_parse_thread_id(data["forked_from_id"]) if data.get("forked_from_id") is not None else None,
            timestamp=_required_str(data, "timestamp"),
            cwd=Path(_required_str(data, "cwd")),
            originator=_required_str(data, "originator"),
            cli_version=_required_str(data, "cli_version"),
            source=_parse_session_source(data.get("source", "vscode")),
            thread_source=ThreadSource.parse(data["thread_source"]) if data.get("thread_source") is not None else None,
            agent_nickname=_optional_str(data, "agent_nickname"),
            agent_role=_optional_str(data, "agent_role") or _optional_str(data, "agent_type"),
            agent_path=_optional_str(data, "agent_path"),
            model_provider=_optional_str(data, "model_provider"),
            base_instructions=data.get("base_instructions"),
            dynamic_tools=data.get("dynamic_tools"),
            memory_mode=_optional_str(data, "memory_mode"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "id": self.id.to_json(),
            "timestamp": self.timestamp,
            "cwd": str(self.cwd),
            "originator": self.originator,
            "cli_version": self.cli_version,
            "source": _session_source_to_json(self.source),
            "model_provider": self.model_provider,
            "base_instructions": self.base_instructions,
        }
        if self.forked_from_id is not None:
            data["forked_from_id"] = self.forked_from_id.to_json()
        if self.thread_source is not None:
            data["thread_source"] = self.thread_source.value
        if self.agent_nickname is not None:
            data["agent_nickname"] = self.agent_nickname
        if self.agent_role is not None:
            data["agent_role"] = self.agent_role
        if self.agent_path is not None:
            data["agent_path"] = self.agent_path
        if self.dynamic_tools is not None:
            data["dynamic_tools"] = _to_json(self.dynamic_tools)
        if self.memory_mode is not None:
            data["memory_mode"] = self.memory_mode
        return data


@dataclass(frozen=True)
class SessionMetaLine:
    meta: SessionMeta
    git: GitInfo | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "SessionMetaLine":
        data = dict(_mapping(value, "session meta line"))
        git = GitInfo.from_mapping(data.pop("git")) if data.get("git") is not None else None
        return cls(meta=SessionMeta.from_mapping(data), git=git)

    def to_mapping(self) -> dict[str, JsonValue]:
        data = self.meta.to_mapping()
        if self.git is not None:
            data["git"] = self.git.to_mapping()
        return data


@dataclass(frozen=True)
class CompactedItem:
    message: str
    replacement_history: tuple[JsonValue, ...] | None = None

    def __post_init__(self) -> None:
        if self.replacement_history is not None:
            object.__setattr__(self, "replacement_history", tuple(self.replacement_history))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "CompactedItem":
        data = _mapping(value, "compacted item")
        replacement_history = data.get("replacement_history")
        if replacement_history is not None:
            if isinstance(replacement_history, str) or not isinstance(replacement_history, Iterable) or isinstance(replacement_history, Mapping):
                raise TypeError("replacement_history must be a list")
            replacement_history = tuple(
                item
                for item in replacement_history
                if not (isinstance(item, Mapping) and item.get("type") == "ghost_snapshot")
            )
        return cls(message=_required_str(data, "message"), replacement_history=replacement_history)

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"message": self.message}
        if self.replacement_history is not None:
            data["replacement_history"] = _to_json(self.replacement_history)
        return data


@dataclass(frozen=True)
class RolloutItem:
    type: str
    payload: JsonValue

    @classmethod
    def session_meta(cls, meta: SessionMetaLine) -> "RolloutItem":
        return cls("session_meta", meta)

    @classmethod
    def response_item(cls, item: JsonValue) -> "RolloutItem":
        return cls("response_item", item)

    @classmethod
    def compacted(cls, item: CompactedItem) -> "RolloutItem":
        return cls("compacted", item)

    @classmethod
    def turn_context(cls, item: TurnContextItem) -> "RolloutItem":
        return cls("turn_context", item)

    @classmethod
    def event_msg(cls, msg: EventMsg) -> "RolloutItem":
        return cls("event_msg", msg)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "RolloutItem":
        if isinstance(value, RolloutItem):
            return value
        data = _mapping(value, "rollout item")
        item_type = _required_str(data, "type")
        payload = data["payload"]
        if item_type == "session_meta":
            return cls.session_meta(SessionMetaLine.from_mapping(payload))
        if item_type == "response_item":
            return cls.response_item(payload)
        if item_type == "compacted":
            return cls.compacted(CompactedItem.from_mapping(payload))
        if item_type == "turn_context":
            return cls.turn_context(TurnContextItem.from_mapping(payload))
        if item_type == "event_msg":
            return cls.event_msg(EventMsg.from_mapping(payload))
        raise ValueError(f"unknown rollout item type: {item_type}")

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"type": self.type, "payload": _to_json(self.payload)}


def _rollout_items(value: JsonValue, label: str = "rollout items") -> tuple[JsonValue, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Iterable) or isinstance(value, Mapping):
        raise TypeError(f"{label} must be a list")
    return tuple(RolloutItem.from_mapping(item) for item in value)


def _rollout_item_payload(item: JsonValue, item_type: str) -> JsonValue | None:
    if isinstance(item, RolloutItem):
        return item.payload if item.type == item_type else None
    if not isinstance(item, Mapping) or item.get("type") != item_type:
        return None
    return item.get("payload")


@dataclass(frozen=True)
class ConversationPathResponseEvent:
    conversation_id: ThreadId
    path: Path

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ConversationPathResponseEvent":
        data = _mapping(value, "conversation path response event")
        return cls(conversation_id=_parse_thread_id(data["conversation_id"]), path=Path(_required_str(data, "path")))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"conversation_id": self.conversation_id.to_json(), "path": str(self.path)}


@dataclass(frozen=True)
class ResumedHistory:
    conversation_id: ThreadId
    history: tuple[JsonValue, ...]
    rollout_path: Path | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.conversation_id, ThreadId):
            object.__setattr__(self, "conversation_id", _parse_thread_id(self.conversation_id))
        object.__setattr__(self, "history", _rollout_items(self.history, "history"))
        if self.rollout_path is not None and not isinstance(self.rollout_path, Path):
            object.__setattr__(self, "rollout_path", Path(str(self.rollout_path)))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ResumedHistory":
        data = _mapping(value, "resumed history")
        rollout_path = data.get("rollout_path")
        if rollout_path is not None and not isinstance(rollout_path, str):
            raise TypeError("rollout_path must be a string")
        return cls(
            conversation_id=_parse_thread_id(data["conversation_id"]),
            history=_rollout_items(data["history"], "history"),
            rollout_path=Path(rollout_path) if rollout_path is not None else None,
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "conversation_id": self.conversation_id.to_json(),
            "history": _to_json(self.history),
        }
        if self.rollout_path is not None:
            data["rollout_path"] = str(self.rollout_path)
        else:
            data["rollout_path"] = None
        return data


@dataclass(frozen=True)
class InitialHistory:
    type: str
    resumed: ResumedHistory | None = None
    items: tuple[RolloutItem, ...] = ()

    @classmethod
    def new(cls) -> "InitialHistory":
        return cls("New")

    @classmethod
    def cleared(cls) -> "InitialHistory":
        return cls("Cleared")

    @classmethod
    def resumed_history(cls, resumed: ResumedHistory) -> "InitialHistory":
        return cls("Resumed", resumed=resumed)

    @classmethod
    def forked(cls, items: Iterable[JsonValue]) -> "InitialHistory":
        return cls("Forked", items=_rollout_items(tuple(items), "forked history"))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "InitialHistory":
        if isinstance(value, InitialHistory):
            return value
        if isinstance(value, str):
            if value in {"New", "new"}:
                return cls.new()
            if value in {"Cleared", "cleared"}:
                return cls.cleared()
            raise ValueError(f"unknown initial history variant: {value}")
        data = _mapping(value, "initial history")
        if len(data) != 1:
            raise ValueError("initial history must have exactly one variant")
        variant, payload = next(iter(data.items()))
        if variant in {"Resumed", "resumed"}:
            return cls.resumed_history(ResumedHistory.from_mapping(payload))
        if variant in {"Forked", "forked"}:
            return cls.forked(_rollout_items(payload, "forked history"))
        return cls.from_mapping(str(variant))

    def to_mapping(self) -> JsonValue:
        if self.type in {"New", "Cleared"}:
            return self.type
        if self.type == "Resumed":
            if self.resumed is None:
                raise ValueError("Resumed initial history requires resumed payload")
            return {"Resumed": self.resumed.to_mapping()}
        if self.type == "Forked":
            return {"Forked": _to_json(self.items)}
        raise ValueError(f"unknown initial history variant: {self.type}")

    def scan_rollout_items(self, predicate) -> bool:
        return any(predicate(item) for item in self.get_rollout_items())

    def get_rollout_items(self) -> tuple[JsonValue, ...]:
        if self.type == "Resumed" and self.resumed is not None:
            return self.resumed.history
        if self.type == "Forked":
            return self.items
        return ()

    def get_event_msgs(self) -> tuple[EventMsg, ...] | None:
        if self.type in {"New", "Cleared"}:
            return None
        messages: list[EventMsg] = []
        for item in self.get_rollout_items():
            payload = _rollout_item_payload(item, "event_msg")
            if payload is not None:
                messages.append(payload if isinstance(payload, EventMsg) else EventMsg.from_mapping(payload))
        return tuple(messages)

    def forked_from_id(self) -> ThreadId | None:
        for item in self.get_rollout_items():
            payload = _rollout_item_payload(item, "session_meta")
            meta = _session_meta_from_rollout_payload(payload)
            if meta is None:
                continue
            if self.type == "Forked":
                return meta.id
            if self.type == "Resumed" and meta.forked_from_id is not None:
                return meta.forked_from_id
        return None

    def session_cwd(self) -> Path | None:
        for item in self.get_rollout_items():
            payload = _rollout_item_payload(item, "session_meta")
            meta = _session_meta_from_rollout_payload(payload)
            if meta is not None:
                return meta.cwd
        return None

    def get_base_instructions(self) -> JsonValue | None:
        return self._first_session_meta_value("base_instructions")

    def get_dynamic_tools(self) -> JsonValue | None:
        return self._first_session_meta_value("dynamic_tools")

    def get_resumed_thread_source(self) -> ThreadSource | None:
        if self.type != "Resumed":
            return None
        value = self._first_session_meta_value("thread_source")
        return ThreadSource.parse(value) if isinstance(value, str) else None

    def _first_session_meta_value(self, key: str) -> JsonValue | None:
        for item in self.get_rollout_items():
            payload = _rollout_item_payload(item, "session_meta")
            meta = _session_meta_from_rollout_payload(payload)
            if meta is not None:
                value = getattr(meta, key)
                if value is not None:
                    return value
        return None


def _session_meta_from_rollout_payload(payload: JsonValue) -> SessionMeta | None:
    if isinstance(payload, SessionMetaLine):
        return payload.meta
    if isinstance(payload, Mapping):
        return SessionMetaLine.from_mapping(payload).meta
    return None


class ReviewDelivery(str, Enum):
    INLINE = "inline"
    DETACHED = "detached"


@dataclass(frozen=True)
class ReviewTarget:
    type: str
    branch: str | None = None
    sha: str | None = None
    title: str | None = None
    instructions: str | None = None

    @classmethod
    def uncommitted_changes(cls) -> "ReviewTarget":
        return cls("uncommittedChanges")

    @classmethod
    def base_branch(cls, branch: str) -> "ReviewTarget":
        return cls("baseBranch", branch=branch)

    @classmethod
    def commit(cls, sha: str, title: str | None = None) -> "ReviewTarget":
        return cls("commit", sha=sha, title=title)

    @classmethod
    def custom(cls, instructions: str) -> "ReviewTarget":
        return cls("custom", instructions=instructions)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ReviewTarget":
        data = _mapping(value, "review target")
        target_type = _required_str(data, "type")
        if target_type == "uncommittedChanges":
            return cls.uncommitted_changes()
        if target_type == "baseBranch":
            return cls.base_branch(_required_str(data, "branch"))
        if target_type == "commit":
            return cls.commit(_required_str(data, "sha"), _optional_str(data, "title"))
        if target_type == "custom":
            return cls.custom(_required_str(data, "instructions"))
        raise ValueError(f"unknown review target type: {target_type}")

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"type": self.type}
        if self.branch is not None:
            data["branch"] = self.branch
        if self.sha is not None:
            data["sha"] = self.sha
        if self.title is not None:
            data["title"] = self.title
        if self.instructions is not None:
            data["instructions"] = self.instructions
        return data


@dataclass(frozen=True)
class ReviewRequest:
    target: ReviewTarget
    user_facing_hint: str | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ReviewRequest":
        data = _mapping(value, "review request")
        return cls(
            target=ReviewTarget.from_mapping(data["target"]),
            user_facing_hint=_optional_str(data, "user_facing_hint"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"target": self.target.to_mapping()}
        if self.user_facing_hint is not None:
            data["user_facing_hint"] = self.user_facing_hint
        return data


@dataclass(frozen=True)
class ReviewLineRange:
    start: int
    end: int

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ReviewLineRange":
        data = _mapping(value, "review line range")
        return cls(start=_required_int(data, "start"), end=_required_int(data, "end"))


@dataclass(frozen=True)
class ReviewCodeLocation:
    absolute_file_path: Path
    line_range: ReviewLineRange

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ReviewCodeLocation":
        data = _mapping(value, "review code location")
        return cls(
            absolute_file_path=Path(_required_str(data, "absolute_file_path")),
            line_range=ReviewLineRange.from_mapping(data["line_range"]),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"absolute_file_path": str(self.absolute_file_path), "line_range": _to_json(self.line_range)}


@dataclass(frozen=True)
class ReviewFinding:
    title: str
    body: str
    confidence_score: float
    priority: int
    code_location: ReviewCodeLocation

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ReviewFinding":
        data = _mapping(value, "review finding")
        return cls(
            title=_required_str(data, "title"),
            body=_required_str(data, "body"),
            confidence_score=_required_number(data, "confidence_score"),
            priority=_required_int(data, "priority"),
            code_location=ReviewCodeLocation.from_mapping(data["code_location"]),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "title": self.title,
            "body": self.body,
            "confidence_score": self.confidence_score,
            "priority": self.priority,
            "code_location": self.code_location.to_mapping(),
        }


@dataclass(frozen=True)
class ReviewOutputEvent:
    findings: tuple[ReviewFinding, ...] = ()
    overall_correctness: str = ""
    overall_explanation: str = ""
    overall_confidence_score: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.findings, tuple):
            object.__setattr__(self, "findings", tuple(self.findings))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ReviewOutputEvent":
        data = _mapping(value, "review output event")
        return cls(
            findings=tuple(ReviewFinding.from_mapping(item) for item in data.get("findings", ())),
            overall_correctness=_required_str(data, "overall_correctness"),
            overall_explanation=_required_str(data, "overall_explanation"),
            overall_confidence_score=_required_number(data, "overall_confidence_score"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "findings": [finding.to_mapping() for finding in self.findings],
            "overall_correctness": self.overall_correctness,
            "overall_explanation": self.overall_explanation,
            "overall_confidence_score": self.overall_confidence_score,
        }


@dataclass(frozen=True)
class ExitedReviewModeEvent:
    review_output: ReviewOutputEvent | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ExitedReviewModeEvent":
        data = _mapping(value, "exited review mode event")
        return cls(
            review_output=(
                ReviewOutputEvent.from_mapping(data["review_output"])
                if data.get("review_output") is not None
                else None
            )
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"review_output": self.review_output.to_mapping() if self.review_output is not None else None}


class TurnAbortReason(str, Enum):
    INTERRUPTED = "interrupted"
    REPLACED = "replaced"
    REVIEW_ENDED = "review_ended"
    BUDGET_LIMITED = "budget_limited"


@dataclass(frozen=True)
class TurnAbortedEvent:
    turn_id: str | None
    reason: TurnAbortReason
    completed_at: int | None = None
    duration_ms: int | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "TurnAbortedEvent":
        data = _mapping(value, "turn aborted event")
        return cls(
            turn_id=_optional_str(data, "turn_id"),
            reason=TurnAbortReason(_required_str(data, "reason")),
            completed_at=_optional_int(data, "completed_at"),
            duration_ms=_optional_int(data, "duration_ms"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "turn_id": self.turn_id,
            "reason": self.reason.value,
        }
        if self.completed_at is not None:
            data["completed_at"] = self.completed_at
        if self.duration_ms is not None:
            data["duration_ms"] = self.duration_ms
        return data


@dataclass(frozen=True)
class AgentStatus:
    type: str
    message: str | None = None

    @classmethod
    def pending_init(cls) -> "AgentStatus":
        return cls("pending_init")

    @classmethod
    def running(cls) -> "AgentStatus":
        return cls("running")

    @classmethod
    def interrupted(cls) -> "AgentStatus":
        return cls("interrupted")

    @classmethod
    def completed(cls, message: str | None = None) -> "AgentStatus":
        return cls("completed", message)

    @classmethod
    def errored(cls, message: str) -> "AgentStatus":
        return cls("errored", message)

    @classmethod
    def shutdown(cls) -> "AgentStatus":
        return cls("shutdown")

    @classmethod
    def not_found(cls) -> "AgentStatus":
        return cls("not_found")

    @classmethod
    def default(cls) -> "AgentStatus":
        return cls.pending_init()

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "AgentStatus":
        if isinstance(value, AgentStatus):
            return value
        if isinstance(value, str):
            if value in {"pending_init", "running", "interrupted", "shutdown", "not_found"}:
                return cls(value)
            raise ValueError(f"unknown agent status: {value}")
        data = _mapping(value, "agent status")
        if len(data) != 1:
            raise ValueError("agent status must have exactly one variant")
        status_type, payload = next(iter(data.items()))
        if status_type == "completed":
            if payload is not None and not isinstance(payload, str):
                raise TypeError("completed status payload must be a string or null")
            return cls.completed(payload)
        if status_type == "errored":
            if not isinstance(payload, str):
                raise TypeError("errored status payload must be a string")
            return cls.errored(payload)
        return cls.from_mapping(str(status_type))

    def to_mapping(self) -> JsonValue:
        if self.type == "completed":
            return {"completed": self.message}
        if self.type == "errored":
            return {"errored": self.message or ""}
        return self.type


@dataclass(frozen=True)
class CollabAgentRef:
    thread_id: ThreadId
    agent_nickname: str | None = None
    agent_role: str | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "CollabAgentRef":
        data = _mapping(value, "collab agent ref")
        return cls(
            thread_id=_parse_thread_id(data["thread_id"]),
            agent_nickname=_optional_str(data, "agent_nickname"),
            agent_role=_optional_str(data, "agent_role") or _optional_str(data, "agent_type"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"thread_id": self.thread_id.to_json()}
        if self.agent_nickname is not None:
            data["agent_nickname"] = self.agent_nickname
        if self.agent_role is not None:
            data["agent_role"] = self.agent_role
        return data


@dataclass(frozen=True)
class CollabAgentStatusEntry:
    thread_id: ThreadId
    status: AgentStatus
    agent_nickname: str | None = None
    agent_role: str | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "CollabAgentStatusEntry":
        data = _mapping(value, "collab agent status entry")
        return cls(
            thread_id=_parse_thread_id(data["thread_id"]),
            agent_nickname=_optional_str(data, "agent_nickname"),
            agent_role=_optional_str(data, "agent_role") or _optional_str(data, "agent_type"),
            status=AgentStatus.from_mapping(data["status"]),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "thread_id": self.thread_id.to_json(),
            "status": self.status.to_mapping(),
        }
        if self.agent_nickname is not None:
            data["agent_nickname"] = self.agent_nickname
        if self.agent_role is not None:
            data["agent_role"] = self.agent_role
        return data


def _parse_reasoning_effort_required(value: JsonValue) -> ReasoningEffort:
    if not isinstance(value, str):
        raise TypeError("reasoning_effort must be a string")
    return ReasoningEffort.parse(value)


def _parse_thread_ids(value: JsonValue, label: str) -> tuple[ThreadId, ...]:
    if isinstance(value, str) or not isinstance(value, Iterable) or isinstance(value, Mapping):
        raise TypeError(f"{label} must be a list")
    return tuple(_parse_thread_id(item) for item in value)


def _parse_agent_refs(value: JsonValue) -> tuple[CollabAgentRef, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Iterable) or isinstance(value, Mapping):
        raise TypeError("receiver_agents must be a list")
    return tuple(CollabAgentRef.from_mapping(item) for item in value)


def _parse_agent_status_entries(value: JsonValue) -> tuple[CollabAgentStatusEntry, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Iterable) or isinstance(value, Mapping):
        raise TypeError("agent_statuses must be a list")
    return tuple(CollabAgentStatusEntry.from_mapping(item) for item in value)


def _parse_status_map(value: JsonValue) -> dict[ThreadId, AgentStatus]:
    data = _mapping(value, "collab status map")
    return {ThreadId.from_string(str(thread_id)): AgentStatus.from_mapping(status) for thread_id, status in data.items()}


def _status_map_to_mapping(value: Mapping[ThreadId, AgentStatus]) -> dict[str, JsonValue]:
    return {thread_id.to_json(): status.to_mapping() for thread_id, status in value.items()}


@dataclass(frozen=True)
class CollabAgentSpawnBeginEvent:
    call_id: str
    sender_thread_id: ThreadId
    prompt: str
    model: str
    reasoning_effort: ReasoningEffort
    started_at_ms: int = 0

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "CollabAgentSpawnBeginEvent":
        data = _mapping(value, "collab agent spawn begin event")
        return cls(
            call_id=_required_str(data, "call_id"),
            started_at_ms=int(data.get("started_at_ms", 0)),
            sender_thread_id=_parse_thread_id(data["sender_thread_id"]),
            prompt=_required_str(data, "prompt"),
            model=_required_str(data, "model"),
            reasoning_effort=_parse_reasoning_effort_required(data["reasoning_effort"]),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "call_id": self.call_id,
            "started_at_ms": self.started_at_ms,
            "sender_thread_id": self.sender_thread_id.to_json(),
            "prompt": self.prompt,
            "model": self.model,
            "reasoning_effort": self.reasoning_effort.value,
        }


@dataclass(frozen=True)
class CollabAgentSpawnEndEvent:
    call_id: str
    sender_thread_id: ThreadId
    new_thread_id: ThreadId | None
    prompt: str
    model: str
    reasoning_effort: ReasoningEffort
    status: AgentStatus
    completed_at_ms: int = 0
    new_agent_nickname: str | None = None
    new_agent_role: str | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "CollabAgentSpawnEndEvent":
        data = _mapping(value, "collab agent spawn end event")
        return cls(
            call_id=_required_str(data, "call_id"),
            completed_at_ms=int(data.get("completed_at_ms", 0)),
            sender_thread_id=_parse_thread_id(data["sender_thread_id"]),
            new_thread_id=_parse_thread_id(data["new_thread_id"]) if data.get("new_thread_id") is not None else None,
            new_agent_nickname=_optional_str(data, "new_agent_nickname"),
            new_agent_role=_optional_str(data, "new_agent_role"),
            prompt=_required_str(data, "prompt"),
            model=_required_str(data, "model"),
            reasoning_effort=_parse_reasoning_effort_required(data["reasoning_effort"]),
            status=AgentStatus.from_mapping(data["status"]),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "call_id": self.call_id,
            "completed_at_ms": self.completed_at_ms,
            "sender_thread_id": self.sender_thread_id.to_json(),
            "new_thread_id": self.new_thread_id.to_json() if self.new_thread_id is not None else None,
            "prompt": self.prompt,
            "model": self.model,
            "reasoning_effort": self.reasoning_effort.value,
            "status": self.status.to_mapping(),
        }
        if self.new_agent_nickname is not None:
            data["new_agent_nickname"] = self.new_agent_nickname
        if self.new_agent_role is not None:
            data["new_agent_role"] = self.new_agent_role
        return data


@dataclass(frozen=True)
class CollabAgentInteractionBeginEvent:
    call_id: str
    sender_thread_id: ThreadId
    receiver_thread_id: ThreadId
    prompt: str
    started_at_ms: int = 0

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "CollabAgentInteractionBeginEvent":
        data = _mapping(value, "collab agent interaction begin event")
        return cls(
            call_id=_required_str(data, "call_id"),
            started_at_ms=int(data.get("started_at_ms", 0)),
            sender_thread_id=_parse_thread_id(data["sender_thread_id"]),
            receiver_thread_id=_parse_thread_id(data["receiver_thread_id"]),
            prompt=_required_str(data, "prompt"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "call_id": self.call_id,
            "started_at_ms": self.started_at_ms,
            "sender_thread_id": self.sender_thread_id.to_json(),
            "receiver_thread_id": self.receiver_thread_id.to_json(),
            "prompt": self.prompt,
        }


@dataclass(frozen=True)
class CollabAgentInteractionEndEvent:
    call_id: str
    sender_thread_id: ThreadId
    receiver_thread_id: ThreadId
    prompt: str
    status: AgentStatus
    completed_at_ms: int = 0
    receiver_agent_nickname: str | None = None
    receiver_agent_role: str | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "CollabAgentInteractionEndEvent":
        data = _mapping(value, "collab agent interaction end event")
        return cls(
            call_id=_required_str(data, "call_id"),
            completed_at_ms=int(data.get("completed_at_ms", 0)),
            sender_thread_id=_parse_thread_id(data["sender_thread_id"]),
            receiver_thread_id=_parse_thread_id(data["receiver_thread_id"]),
            receiver_agent_nickname=_optional_str(data, "receiver_agent_nickname"),
            receiver_agent_role=_optional_str(data, "receiver_agent_role"),
            prompt=_required_str(data, "prompt"),
            status=AgentStatus.from_mapping(data["status"]),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "call_id": self.call_id,
            "completed_at_ms": self.completed_at_ms,
            "sender_thread_id": self.sender_thread_id.to_json(),
            "receiver_thread_id": self.receiver_thread_id.to_json(),
            "prompt": self.prompt,
            "status": self.status.to_mapping(),
        }
        if self.receiver_agent_nickname is not None:
            data["receiver_agent_nickname"] = self.receiver_agent_nickname
        if self.receiver_agent_role is not None:
            data["receiver_agent_role"] = self.receiver_agent_role
        return data


@dataclass(frozen=True)
class CollabWaitingBeginEvent:
    sender_thread_id: ThreadId
    receiver_thread_ids: tuple[ThreadId, ...]
    call_id: str
    started_at_ms: int = 0
    receiver_agents: tuple[CollabAgentRef, ...] = ()

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "CollabWaitingBeginEvent":
        data = _mapping(value, "collab waiting begin event")
        return cls(
            started_at_ms=int(data.get("started_at_ms", 0)),
            sender_thread_id=_parse_thread_id(data["sender_thread_id"]),
            receiver_thread_ids=_parse_thread_ids(data["receiver_thread_ids"], "receiver_thread_ids"),
            receiver_agents=_parse_agent_refs(data.get("receiver_agents")),
            call_id=_required_str(data, "call_id"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "started_at_ms": self.started_at_ms,
            "sender_thread_id": self.sender_thread_id.to_json(),
            "receiver_thread_ids": [thread_id.to_json() for thread_id in self.receiver_thread_ids],
            "call_id": self.call_id,
        }
        if self.receiver_agents:
            data["receiver_agents"] = [agent.to_mapping() for agent in self.receiver_agents]
        return data


@dataclass(frozen=True)
class CollabWaitingEndEvent:
    sender_thread_id: ThreadId
    call_id: str
    statuses: dict[ThreadId, AgentStatus]
    completed_at_ms: int = 0
    agent_statuses: tuple[CollabAgentStatusEntry, ...] = ()

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "CollabWaitingEndEvent":
        data = _mapping(value, "collab waiting end event")
        return cls(
            sender_thread_id=_parse_thread_id(data["sender_thread_id"]),
            call_id=_required_str(data, "call_id"),
            completed_at_ms=int(data.get("completed_at_ms", 0)),
            agent_statuses=_parse_agent_status_entries(data.get("agent_statuses")),
            statuses=_parse_status_map(data["statuses"]),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "sender_thread_id": self.sender_thread_id.to_json(),
            "call_id": self.call_id,
            "completed_at_ms": self.completed_at_ms,
            "statuses": _status_map_to_mapping(self.statuses),
        }
        if self.agent_statuses:
            data["agent_statuses"] = [entry.to_mapping() for entry in self.agent_statuses]
        return data


@dataclass(frozen=True)
class CollabCloseBeginEvent:
    call_id: str
    sender_thread_id: ThreadId
    receiver_thread_id: ThreadId
    started_at_ms: int = 0

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "CollabCloseBeginEvent":
        data = _mapping(value, "collab close begin event")
        return cls(
            call_id=_required_str(data, "call_id"),
            started_at_ms=int(data.get("started_at_ms", 0)),
            sender_thread_id=_parse_thread_id(data["sender_thread_id"]),
            receiver_thread_id=_parse_thread_id(data["receiver_thread_id"]),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "call_id": self.call_id,
            "started_at_ms": self.started_at_ms,
            "sender_thread_id": self.sender_thread_id.to_json(),
            "receiver_thread_id": self.receiver_thread_id.to_json(),
        }


@dataclass(frozen=True)
class CollabCloseEndEvent:
    call_id: str
    sender_thread_id: ThreadId
    receiver_thread_id: ThreadId
    status: AgentStatus
    completed_at_ms: int = 0
    receiver_agent_nickname: str | None = None
    receiver_agent_role: str | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "CollabCloseEndEvent":
        data = _mapping(value, "collab close end event")
        return cls(
            call_id=_required_str(data, "call_id"),
            completed_at_ms=int(data.get("completed_at_ms", 0)),
            sender_thread_id=_parse_thread_id(data["sender_thread_id"]),
            receiver_thread_id=_parse_thread_id(data["receiver_thread_id"]),
            receiver_agent_nickname=_optional_str(data, "receiver_agent_nickname"),
            receiver_agent_role=_optional_str(data, "receiver_agent_role"),
            status=AgentStatus.from_mapping(data["status"]),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "call_id": self.call_id,
            "completed_at_ms": self.completed_at_ms,
            "sender_thread_id": self.sender_thread_id.to_json(),
            "receiver_thread_id": self.receiver_thread_id.to_json(),
            "status": self.status.to_mapping(),
        }
        if self.receiver_agent_nickname is not None:
            data["receiver_agent_nickname"] = self.receiver_agent_nickname
        if self.receiver_agent_role is not None:
            data["receiver_agent_role"] = self.receiver_agent_role
        return data


@dataclass(frozen=True)
class CollabResumeBeginEvent:
    call_id: str
    sender_thread_id: ThreadId
    receiver_thread_id: ThreadId
    started_at_ms: int = 0
    receiver_agent_nickname: str | None = None
    receiver_agent_role: str | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "CollabResumeBeginEvent":
        data = _mapping(value, "collab resume begin event")
        return cls(
            call_id=_required_str(data, "call_id"),
            started_at_ms=int(data.get("started_at_ms", 0)),
            sender_thread_id=_parse_thread_id(data["sender_thread_id"]),
            receiver_thread_id=_parse_thread_id(data["receiver_thread_id"]),
            receiver_agent_nickname=_optional_str(data, "receiver_agent_nickname"),
            receiver_agent_role=_optional_str(data, "receiver_agent_role"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "call_id": self.call_id,
            "started_at_ms": self.started_at_ms,
            "sender_thread_id": self.sender_thread_id.to_json(),
            "receiver_thread_id": self.receiver_thread_id.to_json(),
        }
        if self.receiver_agent_nickname is not None:
            data["receiver_agent_nickname"] = self.receiver_agent_nickname
        if self.receiver_agent_role is not None:
            data["receiver_agent_role"] = self.receiver_agent_role
        return data


@dataclass(frozen=True)
class CollabResumeEndEvent:
    call_id: str
    sender_thread_id: ThreadId
    receiver_thread_id: ThreadId
    status: AgentStatus
    completed_at_ms: int = 0
    receiver_agent_nickname: str | None = None
    receiver_agent_role: str | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "CollabResumeEndEvent":
        data = _mapping(value, "collab resume end event")
        return cls(
            call_id=_required_str(data, "call_id"),
            completed_at_ms=int(data.get("completed_at_ms", 0)),
            sender_thread_id=_parse_thread_id(data["sender_thread_id"]),
            receiver_thread_id=_parse_thread_id(data["receiver_thread_id"]),
            receiver_agent_nickname=_optional_str(data, "receiver_agent_nickname"),
            receiver_agent_role=_optional_str(data, "receiver_agent_role"),
            status=AgentStatus.from_mapping(data["status"]),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "call_id": self.call_id,
            "completed_at_ms": self.completed_at_ms,
            "sender_thread_id": self.sender_thread_id.to_json(),
            "receiver_thread_id": self.receiver_thread_id.to_json(),
            "status": self.status.to_mapping(),
        }
        if self.receiver_agent_nickname is not None:
            data["receiver_agent_nickname"] = self.receiver_agent_nickname
        if self.receiver_agent_role is not None:
            data["receiver_agent_role"] = self.receiver_agent_role
        return data


class ExecCommandSource(str, Enum):
    AGENT = "agent"
    USER_SHELL = "user_shell"
    UNIFIED_EXEC_STARTUP = "unified_exec_startup"
    UNIFIED_EXEC_INTERACTION = "unified_exec_interaction"

    @classmethod
    def default(cls) -> "ExecCommandSource":
        return cls.AGENT


class ExecCommandStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    DECLINED = "declined"


@dataclass(frozen=True)
class ExecCommandBeginEvent:
    call_id: str
    turn_id: str
    command: tuple[str, ...]
    cwd: Path
    parsed_cmd: tuple[JsonValue, ...] = ()
    started_at_ms: int = 0
    process_id: str | None = None
    source: ExecCommandSource = ExecCommandSource.AGENT
    interaction_input: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.command, tuple):
            object.__setattr__(self, "command", tuple(self.command))
        if not isinstance(self.parsed_cmd, tuple):
            object.__setattr__(self, "parsed_cmd", tuple(self.parsed_cmd))

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "call_id": self.call_id,
            "turn_id": self.turn_id,
            "started_at_ms": self.started_at_ms,
            "command": list(self.command),
            "cwd": str(self.cwd),
            "parsed_cmd": _to_json(self.parsed_cmd),
            "source": self.source.value,
        }
        if self.process_id is not None:
            data["process_id"] = self.process_id
        if self.interaction_input is not None:
            data["interaction_input"] = self.interaction_input
        return data


@dataclass(frozen=True)
class ExecCommandEndEvent:
    call_id: str
    turn_id: str
    command: tuple[str, ...]
    cwd: Path
    parsed_cmd: tuple[JsonValue, ...]
    stdout: str
    stderr: str
    exit_code: int
    duration: JsonValue
    formatted_output: str
    status: ExecCommandStatus
    completed_at_ms: int = 0
    process_id: str | None = None
    source: ExecCommandSource = ExecCommandSource.AGENT
    interaction_input: str | None = None
    aggregated_output: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.command, tuple):
            object.__setattr__(self, "command", tuple(self.command))
        if not isinstance(self.parsed_cmd, tuple):
            object.__setattr__(self, "parsed_cmd", tuple(self.parsed_cmd))

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "call_id": self.call_id,
            "turn_id": self.turn_id,
            "completed_at_ms": self.completed_at_ms,
            "command": list(self.command),
            "cwd": str(self.cwd),
            "parsed_cmd": _to_json(self.parsed_cmd),
            "source": self.source.value,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "aggregated_output": self.aggregated_output,
            "exit_code": self.exit_code,
            "duration": self.duration,
            "formatted_output": self.formatted_output,
            "status": self.status.value,
        }
        if self.process_id is not None:
            data["process_id"] = self.process_id
        if self.interaction_input is not None:
            data["interaction_input"] = self.interaction_input
        return data


@dataclass(frozen=True)
class ViewImageToolCallEvent:
    call_id: str
    path: Path

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"call_id": self.call_id, "path": str(self.path)}


class ExecOutputStream(str, Enum):
    STDOUT = "stdout"
    STDERR = "stderr"


def _decode_base64_chunk(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except binascii.Error as exc:
        raise ValueError("chunk must be valid base64") from exc


@dataclass(frozen=True)
class ExecCommandOutputDeltaEvent:
    call_id: str
    stream: ExecOutputStream
    chunk: bytes

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ExecCommandOutputDeltaEvent":
        data = _mapping(value, "exec command output delta event")
        return cls(
            call_id=_required_str(data, "call_id"),
            stream=ExecOutputStream(_required_str(data, "stream")),
            chunk=_decode_base64_chunk(_required_str(data, "chunk")),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "call_id": self.call_id,
            "stream": self.stream.value,
            "chunk": base64.b64encode(self.chunk).decode("ascii"),
        }


@dataclass(frozen=True)
class TerminalInteractionEvent:
    call_id: str
    process_id: str
    stdin: str

    def __post_init__(self) -> None:
        for field_name in ("call_id", "process_id", "stdin"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string")


@dataclass(frozen=True)
class DeprecationNoticeEvent:
    summary: str
    details: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.summary, str):
            raise TypeError("summary must be a string")
        if self.details is not None and not isinstance(self.details, str):
            raise TypeError("details must be a string or None")


@dataclass(frozen=True)
class ThreadRolledBackEvent:
    num_turns: int

    def __post_init__(self) -> None:
        if isinstance(self.num_turns, bool) or not isinstance(self.num_turns, int):
            raise TypeError("num_turns must be an integer")
        if self.num_turns < 0 or self.num_turns > 0xFFFF_FFFF:
            raise ValueError("num_turns must be an unsigned 32-bit integer")


@dataclass(frozen=True)
class StreamErrorEvent:
    message: str
    codex_error_info: CodexErrorInfo | None = None
    additional_details: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.message, str):
            raise TypeError("message must be a string")
        if self.codex_error_info is not None and not isinstance(self.codex_error_info, CodexErrorInfo):
            object.__setattr__(self, "codex_error_info", CodexErrorInfo.from_mapping(self.codex_error_info))
        if self.additional_details is not None and not isinstance(self.additional_details, str):
            raise TypeError("additional_details must be a string or None")

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "message": self.message,
            "codex_error_info": _to_json(self.codex_error_info),
            "additional_details": self.additional_details,
        }


@dataclass(frozen=True)
class StreamInfoEvent:
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.message, str):
            raise TypeError("message must be a string")


class PatchApplyStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    DECLINED = "declined"


@dataclass(frozen=True)
class PatchApplyBeginEvent:
    call_id: str
    auto_approved: bool
    changes: dict[Path, FileChange]
    turn_id: str = ""

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "call_id": self.call_id,
            "turn_id": self.turn_id,
            "auto_approved": self.auto_approved,
            "changes": _file_changes_to_mapping(self.changes),
        }


@dataclass(frozen=True)
class PatchApplyUpdatedEvent:
    call_id: str
    changes: dict[Path, FileChange]

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"call_id": self.call_id, "changes": _file_changes_to_mapping(self.changes)}


@dataclass(frozen=True)
class PatchApplyEndEvent:
    call_id: str
    stdout: str
    stderr: str
    success: bool
    status: PatchApplyStatus
    turn_id: str = ""
    changes: dict[Path, FileChange] | None = None

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "call_id": self.call_id,
            "turn_id": self.turn_id,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "success": self.success,
            "changes": _file_changes_to_mapping(self.changes or {}),
            "status": self.status.value,
        }


@dataclass(frozen=True)
class TurnDiffEvent:
    unified_diff: str

    def __post_init__(self) -> None:
        if not isinstance(self.unified_diff, str):
            raise TypeError("unified_diff must be a string")


@dataclass(frozen=True)
class McpInvocation:
    server: str
    tool: str
    arguments: JsonValue | None = None

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"server": self.server, "tool": self.tool, "arguments": self.arguments}


@dataclass(frozen=True)
class McpToolCallBeginEvent:
    call_id: str
    invocation: McpInvocation
    mcp_app_resource_uri: str | None = None
    plugin_id: str | None = None

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"call_id": self.call_id, "invocation": self.invocation.to_mapping()}
        if self.mcp_app_resource_uri is not None:
            data["mcp_app_resource_uri"] = self.mcp_app_resource_uri
        if self.plugin_id is not None:
            data["plugin_id"] = self.plugin_id
        return data


@dataclass(frozen=True)
class McpToolCallEndEvent:
    call_id: str
    invocation: McpInvocation
    duration: JsonValue
    result: CallToolResult | str
    mcp_app_resource_uri: str | None = None
    plugin_id: str | None = None

    def is_success(self) -> bool:
        return isinstance(self.result, CallToolResult) and self.result.is_error is not True

    def to_mapping(self) -> dict[str, JsonValue]:
        if isinstance(self.result, CallToolResult):
            result: JsonValue = {"Ok": self.result.to_mapping()}
        else:
            result = {"Err": self.result}
        data: dict[str, JsonValue] = {
            "call_id": self.call_id,
            "invocation": self.invocation.to_mapping(),
            "duration": self.duration,
            "result": result,
        }
        if self.mcp_app_resource_uri is not None:
            data["mcp_app_resource_uri"] = self.mcp_app_resource_uri
        if self.plugin_id is not None:
            data["plugin_id"] = self.plugin_id
        return data


@dataclass(frozen=True)
class WebSearchBeginEvent:
    call_id: str


@dataclass(frozen=True)
class WebSearchEndEvent:
    call_id: str
    query: str
    action: JsonValue


@dataclass(frozen=True)
class ImageGenerationBeginEvent:
    call_id: str


@dataclass(frozen=True)
class ImageGenerationEndEvent:
    call_id: str
    status: str
    result: str
    revised_prompt: str | None = None
    saved_path: Path | None = None


@dataclass(frozen=True)
class McpStartupStatus:
    state: str
    error: str | None = None

    @classmethod
    def starting(cls) -> "McpStartupStatus":
        return cls("starting")

    @classmethod
    def ready(cls) -> "McpStartupStatus":
        return cls("ready")

    @classmethod
    def failed(cls, error: str) -> "McpStartupStatus":
        return cls("failed", error=error)

    @classmethod
    def cancelled(cls) -> "McpStartupStatus":
        return cls("cancelled")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "McpStartupStatus":
        data = _mapping(value, "mcp startup status")
        state = _required_str(data, "state")
        if state == "failed":
            return cls.failed(_required_str(data, "error"))
        if state == "starting":
            return cls.starting()
        if state == "ready":
            return cls.ready()
        if state == "cancelled":
            return cls.cancelled()
        raise ValueError(f"unknown MCP startup status: {state}")

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"state": self.state}
        if self.error is not None:
            data["error"] = self.error
        return data


@dataclass(frozen=True)
class McpStartupUpdateEvent:
    server: str
    status: McpStartupStatus

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"server": self.server, "status": self.status.to_mapping()}


@dataclass(frozen=True)
class McpStartupFailure:
    server: str
    error: str


@dataclass(frozen=True)
class McpStartupCompleteEvent:
    ready: tuple[str, ...] = ()
    failed: tuple[McpStartupFailure, ...] = ()
    cancelled: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("ready", "failed", "cancelled"):
            value = getattr(self, field_name)
            if not isinstance(value, tuple):
                object.__setattr__(self, field_name, tuple(value))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "ready": list(self.ready),
            "failed": [_to_json(failure) for failure in self.failed],
            "cancelled": list(self.cancelled),
        }


class McpAuthStatus(str, Enum):
    UNSUPPORTED = "unsupported"
    NOT_LOGGED_IN = "not_logged_in"
    BEARER_TOKEN = "bearer_token"
    OAUTH = "oauth"

    def __str__(self) -> str:
        return {
            McpAuthStatus.UNSUPPORTED: "Unsupported",
            McpAuthStatus.NOT_LOGGED_IN: "Not logged in",
            McpAuthStatus.BEARER_TOKEN: "Bearer token",
            McpAuthStatus.OAUTH: "OAuth",
        }[self]


class ThreadGoalStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    BLOCKED = "blocked"
    USAGE_LIMITED = "usageLimited"
    BUDGET_LIMITED = "budgetLimited"
    COMPLETE = "complete"


def validate_thread_goal_objective(value: str) -> None:
    if value == "":
        raise ValueError("goal objective must not be empty")
    if len(value) > MAX_THREAD_GOAL_OBJECTIVE_CHARS:
        raise ValueError(f"goal objective must be at most {MAX_THREAD_GOAL_OBJECTIVE_CHARS} characters")


@dataclass(frozen=True)
class ThreadGoal:
    thread_id: ThreadId
    objective: str
    status: ThreadGoalStatus
    tokens_used: int
    time_used_seconds: int
    created_at: int
    updated_at: int
    token_budget: int | None = None

    def __post_init__(self) -> None:
        validate_thread_goal_objective(self.objective)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ThreadGoal":
        data = _mapping(value, "thread goal")
        return cls(
            thread_id=_parse_thread_id(data["threadId"]),
            objective=_required_str(data, "objective"),
            status=ThreadGoalStatus(_required_str(data, "status")),
            tokens_used=_required_int(data, "tokensUsed"),
            time_used_seconds=_required_int(data, "timeUsedSeconds"),
            created_at=_required_int(data, "createdAt"),
            updated_at=_required_int(data, "updatedAt"),
            token_budget=_optional_int(data, "tokenBudget"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "threadId": self.thread_id.to_json(),
            "objective": self.objective,
            "status": self.status.value,
            "tokensUsed": self.tokens_used,
            "timeUsedSeconds": self.time_used_seconds,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }
        if self.token_budget is not None:
            data["tokenBudget"] = self.token_budget
        return data


@dataclass(frozen=True)
class ThreadGoalUpdatedEvent:
    thread_id: ThreadId
    goal: ThreadGoal
    turn_id: str | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ThreadGoalUpdatedEvent":
        data = _mapping(value, "thread goal updated event")
        return cls(
            thread_id=_parse_thread_id(data["threadId"]),
            goal=ThreadGoal.from_mapping(data["goal"]),
            turn_id=_optional_str(data, "turnId"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"threadId": self.thread_id.to_json(), "goal": self.goal.to_mapping()}
        if self.turn_id is not None:
            data["turnId"] = self.turn_id
        return data


def _format_with_separators(value: int) -> str:
    return format_with_separators(value)


def _file_change_to_mapping(change: FileChange) -> dict[str, JsonValue]:
    data: dict[str, JsonValue] = {"type": change.type}
    if change.content is not None:
        data["content"] = change.content
    if change.unified_diff is not None:
        data["unified_diff"] = change.unified_diff
    if change.move_path is not None:
        data["move_path"] = str(change.move_path)
    return data


def _file_change_from_mapping(value: JsonValue) -> FileChange:
    data = _mapping(value, "file change")
    change_type = _required_str(data, "type")
    if change_type == "add":
        return FileChange.add(_required_str(data, "content"))
    if change_type == "delete":
        return FileChange.delete(_required_str(data, "content"))
    if change_type == "update":
        move_path = data.get("move_path")
        return FileChange.update(
            _required_str(data, "unified_diff"),
            move_path=Path(move_path) if isinstance(move_path, str) else None,
        )
    raise ValueError(f"unknown file change type: {change_type}")


def _file_changes_to_mapping(changes: Mapping[Path, FileChange]) -> dict[str, JsonValue]:
    return {str(path): _file_change_to_mapping(change) for path, change in changes.items()}


def _file_changes_from_mapping(value: JsonValue) -> dict[Path, FileChange]:
    data = _mapping(value, "file changes")
    return {Path(str(path)): _file_change_from_mapping(change) for path, change in data.items()}


def _optional_sequence(value: JsonValue, label: str) -> tuple[JsonValue, ...] | None:
    if value is None:
        return None
    if isinstance(value, str) or not isinstance(value, Iterable) or isinstance(value, Mapping):
        raise TypeError(f"{label} must be a list")
    return tuple(value)


def _parse_network_approval_context(value: JsonValue) -> NetworkApprovalContext | None:
    if value is None:
        return None
    data = _mapping(value, "network approval context")
    return NetworkApprovalContext(
        host=_required_str(data, "host"),
        protocol=NetworkApprovalProtocol.parse(_required_str(data, "protocol")),
    )


def _alias_value(data: Mapping[str, JsonValue], *keys: str, default: JsonValue = None) -> JsonValue:
    for key in keys:
        if key in data:
            return data[key]
    return default


def _optional_str_alias(data: Mapping[str, JsonValue], *keys: str) -> str | None:
    value = _alias_value(data, *keys)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{keys[0]} must be a string")
    return value


def _required_str_alias(data: Mapping[str, JsonValue], *keys: str) -> str:
    value = _alias_value(data, *keys)
    if not isinstance(value, str):
        raise TypeError(f"{keys[0]} must be a string")
    return value


def _required_int_alias(data: Mapping[str, JsonValue], *keys: str) -> int:
    value = _alias_value(data, *keys)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{keys[0]} must be an integer")
    return value


def _command_tuple(value: JsonValue) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return _str_tuple(value, "command")


def _parse_command_actions(value: JsonValue) -> tuple[ParsedCommand, ...]:
    if value is None:
        return ()
    actions = _optional_sequence(value, "commandActions")
    if actions is None:
        return ()
    parsed: list[ParsedCommand] = []
    for action in actions:
        data = _mapping(action, "command action")
        action_type = _required_str(data, "type")
        if action_type == "read":
            parsed.append(
                ParsedCommand.read(
                    cmd=_required_str(data, "command"),
                    name=_required_str(data, "name"),
                    path=Path(_required_str(data, "path")),
                )
            )
        elif action_type == "listFiles":
            parsed.append(ParsedCommand.list_files(cmd=_required_str(data, "command"), path=_optional_str(data, "path")))
        elif action_type == "search":
            parsed.append(
                ParsedCommand.search(
                    cmd=_required_str(data, "command"),
                    query=_optional_str(data, "query"),
                    path=_optional_str(data, "path"),
                )
            )
        elif action_type == "unknown":
            parsed.append(ParsedCommand.unknown(cmd=_required_str(data, "command")))
        else:
            raise ValueError(f"unknown command action type: {action_type}")
    return tuple(parsed)


def _parse_exec_approval_request(data: Mapping[str, JsonValue]) -> ExecApprovalRequestEvent:
    network_amendments = _optional_sequence(
        _alias_value(data, "proposed_network_policy_amendments", "proposedNetworkPolicyAmendments"),
        "proposed network policy amendments",
    )
    available_decisions = _optional_sequence(_alias_value(data, "available_decisions", "availableDecisions"), "available decisions")
    parsed_cmd = (
        _parse_parsed_commands(data["parsed_cmd"])
        if "parsed_cmd" in data
        else _parse_command_actions(_alias_value(data, "command_actions", "commandActions"))
    )
    return ExecApprovalRequestEvent(
        call_id=_required_str_alias(data, "call_id", "itemId"),
        approval_id=_optional_str_alias(data, "approval_id", "approvalId"),
        turn_id=str(_alias_value(data, "turn_id", "turnId", default="")),
        started_at_ms=_required_int_alias(data, "started_at_ms", "startedAtMs"),
        command=_command_tuple(data.get("command")),
        cwd=Path(_optional_str(data, "cwd") or "."),
        reason=_optional_str(data, "reason"),
        network_approval_context=_parse_network_approval_context(_alias_value(data, "network_approval_context", "networkApprovalContext")),
        proposed_execpolicy_amendment=(
            ExecPolicyAmendment.from_mapping(_alias_value(data, "proposed_execpolicy_amendment", "proposedExecpolicyAmendment"))
            if _alias_value(data, "proposed_execpolicy_amendment", "proposedExecpolicyAmendment") is not None
            else None
        ),
        proposed_network_policy_amendments=(
            tuple(NetworkPolicyAmendment.from_mapping(item) for item in network_amendments)
            if network_amendments is not None
            else None
        ),
        additional_permissions=(
            AdditionalPermissionProfile.from_mapping(_alias_value(data, "additional_permissions", "additionalPermissions"))
            if _alias_value(data, "additional_permissions", "additionalPermissions") is not None
            else None
        ),
        available_decisions=(
            tuple(ReviewDecision.from_mapping(item) for item in available_decisions)
            if available_decisions is not None
            else None
        ),
        parsed_cmd=parsed_cmd,
    )


def _parse_apply_patch_approval_request(data: Mapping[str, JsonValue]) -> ApplyPatchApprovalRequestEvent:
    grant_root = _alias_value(data, "grant_root", "grantRoot")
    return ApplyPatchApprovalRequestEvent(
        call_id=_required_str_alias(data, "call_id", "itemId"),
        turn_id=str(_alias_value(data, "turn_id", "turnId", default="")),
        started_at_ms=_required_int_alias(data, "started_at_ms", "startedAtMs"),
        changes=_file_changes_from_mapping(data.get("changes", {})),
        reason=_optional_str(data, "reason"),
        grant_root=Path(grant_root) if isinstance(grant_root, str) else None,
    )


def _parse_dynamic_tool_response_event(data: Mapping[str, JsonValue]) -> DynamicToolCallResponseEvent:
    raw_items = _optional_sequence(data.get("content_items"), "content_items")
    if raw_items is None:
        raise KeyError("content_items")
    return DynamicToolCallResponseEvent(
        call_id=_required_str(data, "call_id"),
        turn_id=_required_str(data, "turn_id"),
        completed_at_ms=int(data.get("completed_at_ms", 0)),
        namespace=_optional_str(data, "namespace"),
        tool=_required_str(data, "tool"),
        arguments=data["arguments"],
        content_items=tuple(DynamicToolCallOutputContentItem.from_mapping(item) for item in raw_items),
        success=_required_bool(data, "success"),
        error=_optional_str(data, "error"),
        duration=data.get("duration"),
    )


def _parse_model_reroute(data: Mapping[str, JsonValue]) -> ModelRerouteEvent:
    return ModelRerouteEvent(
        from_model=_required_str(data, "from_model"),
        to_model=_required_str(data, "to_model"),
        reason=ModelRerouteReason(_required_str(data, "reason")),
    )


def _parse_model_verification(data: Mapping[str, JsonValue]) -> ModelVerificationEvent:
    raw_verifications = _optional_sequence(data.get("verifications"), "verifications")
    if raw_verifications is None:
        raise KeyError("verifications")
    return ModelVerificationEvent(tuple(ModelVerification(str(item)) for item in raw_verifications))


def _event_from(cls: type, data: Mapping[str, JsonValue]) -> JsonValue:
    names = {field.name for field in fields(cls)}
    kwargs = {name: data[name] for name in names if name in data}
    return cls(**kwargs)


def _parse_exec_begin(data: Mapping[str, JsonValue]) -> ExecCommandBeginEvent:
    return ExecCommandBeginEvent(
        call_id=_required_str(data, "call_id"),
        process_id=_optional_str(data, "process_id"),
        turn_id=_required_str(data, "turn_id"),
        started_at_ms=int(data.get("started_at_ms", 0)),
        command=tuple(data.get("command", ())),
        cwd=Path(_required_str(data, "cwd")),
        parsed_cmd=_parse_parsed_commands(data.get("parsed_cmd", ())),
        source=ExecCommandSource(data.get("source", ExecCommandSource.AGENT.value)),
        interaction_input=_optional_str(data, "interaction_input"),
    )


def _parse_exec_end(data: Mapping[str, JsonValue]) -> ExecCommandEndEvent:
    return ExecCommandEndEvent(
        call_id=_required_str(data, "call_id"),
        process_id=_optional_str(data, "process_id"),
        turn_id=_required_str(data, "turn_id"),
        completed_at_ms=int(data.get("completed_at_ms", 0)),
        command=tuple(data.get("command", ())),
        cwd=Path(_required_str(data, "cwd")),
        parsed_cmd=_parse_parsed_commands(data.get("parsed_cmd", ())),
        source=ExecCommandSource(data.get("source", ExecCommandSource.AGENT.value)),
        interaction_input=_optional_str(data, "interaction_input"),
        stdout=_required_str(data, "stdout"),
        stderr=_required_str(data, "stderr"),
        aggregated_output=str(data.get("aggregated_output", "")),
        exit_code=_required_int(data, "exit_code"),
        duration=data["duration"],
        formatted_output=_required_str(data, "formatted_output"),
        status=ExecCommandStatus(_required_str(data, "status")),
    )


def _parse_mcp_invocation(value: JsonValue) -> McpInvocation:
    data = _mapping(value, "mcp invocation")
    return McpInvocation(
        server=_required_str(data, "server"),
        tool=_required_str(data, "tool"),
        arguments=data.get("arguments"),
    )


def _parse_mcp_tool_call_begin(data: Mapping[str, JsonValue]) -> McpToolCallBeginEvent:
    return McpToolCallBeginEvent(
        call_id=_required_str(data, "call_id"),
        invocation=_parse_mcp_invocation(data["invocation"]),
        mcp_app_resource_uri=_optional_str(data, "mcp_app_resource_uri"),
        plugin_id=_optional_str(data, "plugin_id"),
    )


def _parse_mcp_result(value: JsonValue) -> CallToolResult | str:
    data = _mapping(value, "mcp tool result")
    if "Ok" in data:
        return CallToolResult.from_mapping(data["Ok"])
    if "Err" in data:
        return str(data["Err"])
    raise KeyError("Ok or Err")


def _parse_mcp_tool_call_end(data: Mapping[str, JsonValue]) -> McpToolCallEndEvent:
    return McpToolCallEndEvent(
        call_id=_required_str(data, "call_id"),
        invocation=_parse_mcp_invocation(data["invocation"]),
        mcp_app_resource_uri=_optional_str(data, "mcp_app_resource_uri"),
        plugin_id=_optional_str(data, "plugin_id"),
        duration=data["duration"],
        result=_parse_mcp_result(data["result"]),
    )


def _parse_mcp_startup_complete(data: Mapping[str, JsonValue]) -> McpStartupCompleteEvent:
    return McpStartupCompleteEvent(
        ready=tuple(data.get("ready", ())),
        failed=tuple(McpStartupFailure(**failure) for failure in data.get("failed", ())),
        cancelled=tuple(data.get("cancelled", ())),
    )


def _parse_thread_id(value: JsonValue) -> ThreadId:
    if isinstance(value, ThreadId):
        return value
    if not isinstance(value, str):
        raise TypeError("thread_id must be a string")
    return ThreadId.from_string(value)


def _parse_session_id(value: JsonValue) -> SessionId:
    if isinstance(value, SessionId):
        return value
    if not isinstance(value, str):
        raise TypeError("session_id must be a string")
    return SessionId.from_string(value)


def _parse_turn_item(value: JsonValue) -> JsonValue:
    from .items import TurnItem

    return value if isinstance(value, TurnItem) else TurnItem.from_mapping(value)


def _parse_memory_citation(value: JsonValue) -> MemoryCitation | None:
    if value is None:
        return None
    if isinstance(value, MemoryCitation):
        return value
    return MemoryCitation.from_mapping(value)


def _parse_message_phase_field(data: Mapping[str, JsonValue], key: str) -> MessagePhase | None:
    raw = data.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return MessagePhase(raw)


def _parse_parsed_commands(value: JsonValue) -> tuple[JsonValue, ...]:
    if value is None:
        return ()
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, Mapping)):
        raise TypeError("parsed_cmd must be a list")
    return tuple(
        ParsedCommand.from_mapping(item)
        if isinstance(item, Mapping) and isinstance(item.get("type"), str)
        else item
        for item in value
    )


_EVENT_PAYLOAD_PARSERS = {
    "session_configured": SessionConfiguredEvent.from_mapping,
    "thread_settings_applied": ThreadSettingsAppliedEvent.from_mapping,
    "token_count": TokenCountEvent.from_mapping,
    "realtime_conversation_started": RealtimeConversationStartedEvent.from_mapping,
    "realtime_conversation_realtime": RealtimeConversationRealtimeEvent.from_mapping,
    "realtime_conversation_closed": RealtimeConversationClosedEvent.from_mapping,
    "realtime_conversation_sdp": RealtimeConversationSdpEvent.from_mapping,
    "realtime_conversation_list_voices_response": RealtimeConversationListVoicesResponseEvent.from_mapping,
    "error": lambda data: ErrorEvent(message=_required_str(data, "message"), codex_error_info=data.get("codex_error_info")),
    "warning": lambda data: WarningEvent(message=_required_str(data, "message")),
    "guardian_warning": lambda data: WarningEvent(message=_required_str(data, "message")),
    "model_reroute": _parse_model_reroute,
    "model_verification": _parse_model_verification,
    "context_compacted": lambda data: ContextCompactedEvent(),
    "task_started": lambda data: TurnStartedEvent(
        turn_id=_required_str(data, "turn_id"),
        trace_id=_optional_str(data, "trace_id"),
        started_at=_optional_int(data, "started_at"),
        model_context_window=data.get("model_context_window"),
        collaboration_mode_kind=data.get("collaboration_mode_kind", "default"),
    ),
    "task_complete": lambda data: TurnCompleteEvent(
        turn_id=_required_str(data, "turn_id"),
        last_agent_message=data.get("last_agent_message"),
        completed_at=_optional_int(data, "completed_at"),
        duration_ms=_optional_int(data, "duration_ms"),
        time_to_first_token_ms=_optional_int(data, "time_to_first_token_ms"),
    ),
    "agent_message": lambda data: AgentMessageEvent(
        message=_required_str(data, "message"),
        phase=_parse_message_phase_field(data, "phase"),
        memory_citation=_parse_memory_citation(data.get("memory_citation")),
    ),
    "user_message": lambda data: UserMessageEvent(
        message=_required_str(data, "message"),
        images=data.get("images"),
        image_details=data.get("image_details", ()),
        local_images=data.get("local_images", ()),
        local_image_details=data.get("local_image_details", ()),
        text_elements=data.get("text_elements", ()),
    ),
    "agent_reasoning": lambda data: AgentReasoningEvent(text=_required_str(data, "text")),
    "agent_reasoning_raw_content": lambda data: AgentReasoningRawContentEvent(text=_required_str(data, "text")),
    "agent_reasoning_section_break": _parse_agent_reasoning_section_break,
    "raw_response_item": lambda data: RawResponseItemEvent(item=data["item"]),
    "item_started": lambda data: ItemStartedEvent(
        thread_id=_parse_thread_id(data["thread_id"]),
        turn_id=_required_str(data, "turn_id"),
        item=_parse_turn_item(data["item"]),
        started_at_ms=_required_int(data, "started_at_ms"),
    ),
    "item_completed": lambda data: ItemCompletedEvent(
        thread_id=_parse_thread_id(data["thread_id"]),
        turn_id=_required_str(data, "turn_id"),
        item=_parse_turn_item(data["item"]),
        completed_at_ms=int(data.get("completed_at_ms", 0)),
    ),
    "agent_message_content_delta": lambda data: AgentMessageContentDeltaEvent(
        thread_id=_required_str(data, "thread_id"),
        turn_id=_required_str(data, "turn_id"),
        item_id=_required_str(data, "item_id"),
        delta=_required_str(data, "delta"),
    ),
    "plan_delta": lambda data: PlanDeltaEvent(
        thread_id=_required_str(data, "thread_id"),
        turn_id=_required_str(data, "turn_id"),
        item_id=_required_str(data, "item_id"),
        delta=_required_str(data, "delta"),
    ),
    "plan_update": lambda data: UpdatePlanArgs.from_mapping(data),
    "turn_aborted": TurnAbortedEvent.from_mapping,
    "shutdown_complete": lambda data: None,
    "collab_agent_spawn_begin": CollabAgentSpawnBeginEvent.from_mapping,
    "collab_agent_spawn_end": CollabAgentSpawnEndEvent.from_mapping,
    "collab_agent_interaction_begin": CollabAgentInteractionBeginEvent.from_mapping,
    "collab_agent_interaction_end": CollabAgentInteractionEndEvent.from_mapping,
    "collab_waiting_begin": CollabWaitingBeginEvent.from_mapping,
    "collab_waiting_end": CollabWaitingEndEvent.from_mapping,
    "collab_close_begin": CollabCloseBeginEvent.from_mapping,
    "collab_close_end": CollabCloseEndEvent.from_mapping,
    "collab_resume_begin": CollabResumeBeginEvent.from_mapping,
    "collab_resume_end": CollabResumeEndEvent.from_mapping,
    "entered_review_mode": ReviewRequest.from_mapping,
    "exited_review_mode": ExitedReviewModeEvent.from_mapping,
    "hook_started": HookStartedEvent.from_mapping,
    "hook_completed": HookCompletedEvent.from_mapping,
    "reasoning_content_delta": _parse_reasoning_content_delta,
    "reasoning_raw_content_delta": _parse_reasoning_raw_content_delta,
    "exec_command_begin": _parse_exec_begin,
    "exec_command_end": _parse_exec_end,
    "exec_command_output_delta": ExecCommandOutputDeltaEvent.from_mapping,
    "terminal_interaction": lambda data: TerminalInteractionEvent(
        call_id=_required_str(data, "call_id"),
        process_id=_required_str(data, "process_id"),
        stdin=_required_str(data, "stdin"),
    ),
    "exec_approval_request": _parse_exec_approval_request,
    "request_permissions": RequestPermissionsEvent.from_mapping,
    "request_user_input": RequestUserInputEvent.from_mapping,
    "dynamic_tool_call_request": DynamicToolCallRequest.from_mapping,
    "dynamic_tool_call_response": _parse_dynamic_tool_response_event,
    "elicitation_request": ElicitationRequestEvent.from_mapping,
    "apply_patch_approval_request": _parse_apply_patch_approval_request,
    "guardian_assessment": GuardianAssessmentEvent.from_mapping,
    "thread_goal_updated": ThreadGoalUpdatedEvent.from_mapping,
    "view_image_tool_call": lambda data: ViewImageToolCallEvent(
        call_id=_required_str(data, "call_id"),
        path=Path(_required_str(data, "path")),
    ),
    "patch_apply_begin": _parse_patch_apply_begin,
    "patch_apply_updated": lambda data: PatchApplyUpdatedEvent(
        call_id=_required_str(data, "call_id"),
        changes=_file_changes_from_mapping(data["changes"]),
    ),
    "patch_apply_end": _parse_patch_apply_end,
    "mcp_tool_call_begin": _parse_mcp_tool_call_begin,
    "mcp_tool_call_end": _parse_mcp_tool_call_end,
    "mcp_startup_update": lambda data: McpStartupUpdateEvent(
        server=_required_str(data, "server"),
        status=McpStartupStatus.from_mapping(data["status"]),
    ),
    "mcp_startup_complete": _parse_mcp_startup_complete,
    "web_search_begin": lambda data: WebSearchBeginEvent(call_id=_required_str(data, "call_id")),
    "web_search_end": lambda data: WebSearchEndEvent(
        call_id=_required_str(data, "call_id"),
        query=_required_str(data, "query"),
        action=data["action"],
    ),
    "image_generation_begin": lambda data: ImageGenerationBeginEvent(call_id=_required_str(data, "call_id")),
    "image_generation_end": lambda data: ImageGenerationEndEvent(
        call_id=_required_str(data, "call_id"),
        status=_required_str(data, "status"),
        revised_prompt=_optional_str(data, "revised_prompt"),
        result=_required_str(data, "result"),
        saved_path=Path(data["saved_path"]) if isinstance(data.get("saved_path"), str) else None,
    ),
    "deprecation_notice": lambda data: DeprecationNoticeEvent(
        summary=_required_str(data, "summary"),
        details=_optional_str(data, "details"),
    ),
    "thread_rolled_back": lambda data: ThreadRolledBackEvent(num_turns=_required_u32(data, "num_turns")),
    "stream_error": lambda data: StreamErrorEvent(
        message=_required_str(data, "message"),
        codex_error_info=data.get("codex_error_info"),
        additional_details=_optional_str(data, "additional_details"),
    ),
    "stream_info": lambda data: StreamInfoEvent(message=_required_str(data, "message")),
    "turn_diff": lambda data: TurnDiffEvent(unified_diff=_required_str(data, "unified_diff")),
}
