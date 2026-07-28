"""Event processors for non-interactive ``codex exec`` output.

This is a standard-library port of the dependency-free behavior in
``codex/codex-rs/exec/src/event_processor.rs`` plus the testable state-machine
pieces of the human and JSONL processors.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
import json
from pathlib import Path
import sys
from typing import Any, Protocol, TextIO

from pycodex.protocol import (
    NetworkSandboxPolicy,
    PermissionProfile,
    SandboxPolicy,
    SessionConfiguredEvent,
    TurnItem,
    approval_policy_display_value,
    turn_completed_notification as protocol_turn_completed_notification,
    turn_started_notification as protocol_turn_started_notification,
)

from .events import (
    ExecThreadItem,
    ThreadErrorEvent,
    ThreadEvent,
    Usage,
    agent_message_item,
    collab_tool_call_item,
    command_execution_item,
    error_item,
    exec_item_from_turn_item,
    final_message_from_turn_items,
    reasoning_item,
    todo_list_item,
    web_search_item,
)

JsonValue = Any
DEFAULT_CODEX_VERSION = "0.0.0"
_EXEC_JSON_TURN_ITEM_TYPES = {
    "AgentMessage",
    "Reasoning",
    "CommandExecution",
    "FileChange",
    "McpToolCall",
    "CollabAgentToolCall",
    "WebSearch",
}


class CodexStatus(str, Enum):
    RUNNING = "running"
    INITIATE_SHUTDOWN = "initiate_shutdown"

    @property
    def status(self) -> "CodexStatus":
        return self


class EventProcessor(Protocol):
    def print_config_summary(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def process_server_notification(self, notification: JsonValue, *args: Any, **kwargs: Any) -> CodexStatus:
        ...

    def process_warning(self, message: str, *args: Any, **kwargs: Any) -> CodexStatus:
        ...

    def print_final_output(self, *args: Any, **kwargs: Any) -> Any:
        ...


def exec_turn_started_notification(
    thread_id: str,
    turn_id: str,
    items: tuple[TurnItem, ...] | list[TurnItem] = (),
    *,
    started_at: int | float | None = None,
) -> dict[str, JsonValue]:
    return protocol_turn_started_notification(thread_id, turn_id, items, started_at=started_at)


def exec_turn_completed_notification(
    thread_id: str,
    turn_id: str,
    items: tuple[TurnItem, ...] | list[TurnItem],
    *,
    status: str = "completed",
    started_at: int | float | None = None,
    completed_at: int | float | None = None,
    duration_ms: int | float | None = None,
    error: JsonValue = None,
) -> dict[str, JsonValue]:
    return protocol_turn_completed_notification(
        thread_id,
        turn_id,
        items,
        status=status,
        error=error,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=duration_ms,
    )


def handle_last_message(
    last_agent_message: str | None,
    output_file: str | Path,
    *,
    stderr: TextIO | None = None,
) -> None:
    path = Path(output_file)
    err = sys.stderr if stderr is None else stderr
    try:
        path.write_text(last_agent_message or "", encoding="utf-8")
    except OSError as exc:
        print(f"Failed to write last message file {json.dumps(str(path))}: {exc}", file=err)
    if last_agent_message is None:
        print(f"Warning: no last agent message; wrote empty content to {path}", file=err)








def notification_method(notification: JsonValue) -> str | None:
    raw = _field(notification, "method", "type", "kind")
    if raw is None:
        return None
    raw = str(raw)
    aliases = {
        "AccountLoginCompleted": "account/login/completed",
        "account_login_completed": "account/login/completed",
        "AccountRateLimitsUpdated": "account/rateLimits/updated",
        "account_rate_limits_updated": "account/rateLimits/updated",
        "AccountUpdated": "account/updated",
        "account_updated": "account/updated",
        "AgentMessageDelta": "item/agentMessage/delta",
        "agent_message_delta": "item/agentMessage/delta",
        "AppListUpdated": "app/list/updated",
        "app_list_updated": "app/list/updated",
        "CommandExecOutputDelta": "command/exec/outputDelta",
        "command_exec_output_delta": "command/exec/outputDelta",
        "CommandExecutionOutputDelta": "item/commandExecution/outputDelta",
        "command_execution_output_delta": "item/commandExecution/outputDelta",
        "ConfigWarning": "configWarning",
        "config_warning": "configWarning",
        "ContextCompacted": "thread/compacted",
        "context_compacted": "thread/compacted",
        "DeprecationNotice": "deprecationNotice",
        "deprecation_notice": "deprecationNotice",
        "Error": "error",
        "ExternalAgentConfigImportCompleted": "externalAgentConfig/import/completed",
        "external_agent_config_import_completed": "externalAgentConfig/import/completed",
        "FileChangeOutputDelta": "item/fileChange/outputDelta",
        "file_change_output_delta": "item/fileChange/outputDelta",
        "FileChangePatchUpdated": "item/fileChange/patchUpdated",
        "file_change_patch_updated": "item/fileChange/patchUpdated",
        "FsChanged": "fs/changed",
        "fs_changed": "fs/changed",
        "FuzzyFileSearchSessionCompleted": "fuzzyFileSearch/sessionCompleted",
        "fuzzy_file_search_session_completed": "fuzzyFileSearch/sessionCompleted",
        "FuzzyFileSearchSessionUpdated": "fuzzyFileSearch/sessionUpdated",
        "fuzzy_file_search_session_updated": "fuzzyFileSearch/sessionUpdated",
        "GuardianWarning": "guardianWarning",
        "guardian_warning": "guardianWarning",
        "HookStarted": "hook/started",
        "hook_started": "hook/started",
        "HookCompleted": "hook/completed",
        "hook_completed": "hook/completed",
        "ItemStarted": "item/started",
        "item_started": "item/started",
        "ItemGuardianApprovalReviewStarted": "item/autoApprovalReview/started",
        "item_guardian_approval_review_started": "item/autoApprovalReview/started",
        "ItemGuardianApprovalReviewCompleted": "item/autoApprovalReview/completed",
        "item_guardian_approval_review_completed": "item/autoApprovalReview/completed",
        "ItemCompleted": "item/completed",
        "item_completed": "item/completed",
        "ModelRerouted": "model/rerouted",
        "model_rerouted": "model/rerouted",
        "ModelVerification": "model/verification",
        "model_verification": "model/verification",
        "McpServerOauthLoginCompleted": "mcpServer/oauthLogin/completed",
        "mcp_server_oauth_login_completed": "mcpServer/oauthLogin/completed",
        "McpServerStatusUpdated": "mcpServer/startupStatus/updated",
        "mcp_server_status_updated": "mcpServer/startupStatus/updated",
        "McpToolCallProgress": "item/mcpToolCall/progress",
        "mcp_tool_call_progress": "item/mcpToolCall/progress",
        "PlanDelta": "item/plan/delta",
        "plan_delta": "item/plan/delta",
        "ProcessExited": "process/exited",
        "process_exited": "process/exited",
        "ProcessOutputDelta": "process/outputDelta",
        "process_output_delta": "process/outputDelta",
        "RawResponseItemCompleted": "rawResponseItem/completed",
        "raw_response_item_completed": "rawResponseItem/completed",
        "ReasoningSummaryPartAdded": "item/reasoning/summaryPartAdded",
        "reasoning_summary_part_added": "item/reasoning/summaryPartAdded",
        "ReasoningSummaryTextDelta": "item/reasoning/summaryTextDelta",
        "reasoning_summary_text_delta": "item/reasoning/summaryTextDelta",
        "ReasoningTextDelta": "item/reasoning/textDelta",
        "reasoning_text_delta": "item/reasoning/textDelta",
        "RemoteControlStatusChanged": "remoteControl/status/changed",
        "remote_control_status_changed": "remoteControl/status/changed",
        "ServerRequestResolved": "serverRequest/resolved",
        "server_request_resolved": "serverRequest/resolved",
        "SkillsChanged": "skills/changed",
        "skills_changed": "skills/changed",
        "TerminalInteraction": "item/commandExecution/terminalInteraction",
        "terminal_interaction": "item/commandExecution/terminalInteraction",
        "ThreadArchived": "thread/archived",
        "thread_archived": "thread/archived",
        "ThreadUnarchived": "thread/unarchived",
        "thread_unarchived": "thread/unarchived",
        "ThreadClosed": "thread/closed",
        "thread_closed": "thread/closed",
        "ThreadGoalCleared": "thread/goal/cleared",
        "thread_goal_cleared": "thread/goal/cleared",
        "ThreadGoalUpdated": "thread/goal/updated",
        "thread_goal_updated": "thread/goal/updated",
        "ThreadNameUpdated": "thread/name/updated",
        "thread_name_updated": "thread/name/updated",
        "ThreadSettingsUpdated": "thread/settings/updated",
        "thread_settings_updated": "thread/settings/updated",
        "ThreadStarted": "thread/started",
        "thread_started": "thread/started",
        "ThreadStatusChanged": "thread/status/changed",
        "thread_status_changed": "thread/status/changed",
        "ThreadTokenUsageUpdated": "thread/tokenUsage/updated",
        "thread_token_usage_updated": "thread/tokenUsage/updated",
        "ThreadRealtimeClosed": "thread/realtime/closed",
        "thread_realtime_closed": "thread/realtime/closed",
        "ThreadRealtimeError": "thread/realtime/error",
        "thread_realtime_error": "thread/realtime/error",
        "ThreadRealtimeItemAdded": "thread/realtime/itemAdded",
        "thread_realtime_item_added": "thread/realtime/itemAdded",
        "ThreadRealtimeOutputAudioDelta": "thread/realtime/outputAudio/delta",
        "thread_realtime_output_audio_delta": "thread/realtime/outputAudio/delta",
        "ThreadRealtimeSdp": "thread/realtime/sdp",
        "thread_realtime_sdp": "thread/realtime/sdp",
        "ThreadRealtimeStarted": "thread/realtime/started",
        "thread_realtime_started": "thread/realtime/started",
        "ThreadRealtimeTranscriptDelta": "thread/realtime/transcript/delta",
        "thread_realtime_transcript_delta": "thread/realtime/transcript/delta",
        "ThreadRealtimeTranscriptDone": "thread/realtime/transcript/done",
        "thread_realtime_transcript_done": "thread/realtime/transcript/done",
        "TurnCompleted": "turn/completed",
        "turn_completed": "turn/completed",
        "TurnDiffUpdated": "turn/diff/updated",
        "turn_diff_updated": "turn/diff/updated",
        "TurnPlanUpdated": "turn/plan/updated",
        "turn_plan_updated": "turn/plan/updated",
        "TurnStarted": "turn/started",
        "turn_started": "turn/started",
        "Warning": "warning",
        "WindowsSandboxSetupCompleted": "windowsSandbox/setupCompleted",
        "windows_sandbox_setup_completed": "windowsSandbox/setupCompleted",
        "WindowsWorldWritableWarning": "windows/worldWritableWarning",
        "windows_world_writable_warning": "windows/worldWritableWarning",
    }
    return aliases.get(raw, raw)


def notification_params(notification: JsonValue) -> JsonValue:
    params = _field(notification, "params", "payload")
    return notification if params is None else params


def usage_from_notification(value: JsonValue) -> Usage:
    token_usage = _field(value, "tokenUsage", "token_usage")
    if token_usage is None:
        token_usage = value
    total = _field(token_usage, "total")
    if total is None:
        total = token_usage
    return Usage(
        input_tokens=_int_field(total, "inputTokens", "input_tokens"),
        cached_input_tokens=_int_field(total, "cachedInputTokens", "cached_input_tokens"),
        output_tokens=_int_field(total, "outputTokens", "output_tokens"),
        reasoning_output_tokens=_int_field(total, "reasoningOutputTokens", "reasoning_output_tokens"),
    )


def map_todo_items(plan: JsonValue) -> tuple[tuple[str, bool], ...]:
    if not isinstance(plan, list | tuple):
        return ()
    return tuple(
        (
            str(_field(step, "step") or ""),
            _normalized_status(_field(step, "status")) == "completed",
        )
        for step in plan
    )


def exec_item_from_app_server_item(item: JsonValue, make_id: Any) -> ExecThreadItem | None:
    if isinstance(item, Mapping):
        item_type = _normalized_item_type(_field(item, "type"))
        if item_type == "web_search":
            return web_search_item(
                make_id(),
                type(
                    "WebSearchNotificationItem",
                    (),
                    {
                        "id": str(_field(item, "id") or ""),
                        "query": str(_field(item, "query") or ""),
                        "action": _field(item, "action"),
                    },
                )(),
            )
        if item_type == "collab_agent_tool_call":
            return collab_tool_call_item(
                make_id(),
                tool=_field(item, "tool"),
                sender_thread_id=str(_field(item, "senderThreadId", "sender_thread_id") or ""),
                receiver_thread_ids=tuple(str(thread_id) for thread_id in (_field(item, "receiverThreadIds", "receiver_thread_ids") or ())),
                prompt=_optional_str(_field(item, "prompt")),
                agents_states=_field(item, "agentsStates", "agents_states") or {},
                status=_field(item, "status"),
            )
        if item_type == "mcp_tool_call":
            payload = {
                "server": _field(item, "server") or "",
                "tool": _field(item, "tool") or "",
                "arguments": _field(item, "arguments"),
                "result": _mcp_result_mapping(_field(item, "result")),
                "status": _mcp_status_text(_field(item, "status")),
            }
            if "error" in item:
                payload["error"] = _mcp_error_mapping(_field(item, "error"))
            return ExecThreadItem(make_id(), "mcp_tool_call", payload)
        if item_type == "file_change":
            return ExecThreadItem(
                make_id(),
                "file_change",
                {
                    "changes": _file_change_entries(_field(item, "changes") or ()),
                    "status": _patch_status_for_exec_json(_field(item, "status")),
                },
            )

    turn_item = _turn_item_from_value(item)
    if turn_item is not None:
        if not _turn_item_emits_exec_json(turn_item):
            return None
        return exec_item_from_turn_item(turn_item, make_id())

    item_type = _normalized_item_type(_field(item, "type"))
    if item_type == "agent_message":
        return agent_message_item(make_id(), agent_message_text_from_notification_item(item) or "")

    if item_type == "reasoning":
        text = "\n".join(str(entry) for entry in (_field(item, "summary", "summary_text") or ()))
        if text.strip() == "":
            return None
        return reasoning_item(make_id(), text)

    if item_type == "command_execution":
        return command_execution_item(
            make_id(),
            command=str(_field(item, "command") or ""),
            cwd=_field(item, "cwd"),
            process_id=_optional_str(_field(item, "processId", "process_id")),
            source=_optional_str(_field(item, "source")),
            command_actions=_command_actions(_field(item, "commandActions", "command_actions")),
            aggregated_output=str(_field(item, "aggregatedOutput", "aggregated_output") or ""),
            exit_code=_optional_int(_field(item, "exitCode", "exit_code")),
            duration_ms=_optional_int(_field(item, "durationMs", "duration_ms")),
            status=_field(item, "status"),
        )

    if item_type == "file_change":
        return ExecThreadItem(
            make_id(),
            "file_change",
            {
                "changes": _file_change_entries(_field(item, "changes") or ()),
                "status": _patch_status_for_exec_json(_field(item, "status")),
            },
        )

    if item_type == "mcp_tool_call":
        error = _mcp_error_mapping(_field(item, "error"))
        payload = {
            "server": _field(item, "server") or "",
            "tool": _field(item, "tool") or "",
            "arguments": _field(item, "arguments"),
            "result": _mcp_result_mapping(_field(item, "result")),
            "status": _mcp_status_text(_field(item, "status")),
        }
        if not isinstance(item, Mapping) or "error" in item:
            payload["error"] = error
        return ExecThreadItem(
            make_id(),
            "mcp_tool_call",
            payload,
        )

    if item_type == "collab_agent_tool_call":
        return collab_tool_call_item(
            make_id(),
            tool=_field(item, "tool"),
            sender_thread_id=str(_field(item, "senderThreadId", "sender_thread_id") or ""),
            receiver_thread_ids=tuple(str(thread_id) for thread_id in (_field(item, "receiverThreadIds", "receiver_thread_ids") or ())),
            prompt=_optional_str(_field(item, "prompt")),
            agents_states=_field(item, "agentsStates", "agents_states") or {},
            status=_field(item, "status"),
        )

    if item_type == "web_search":
        return web_search_item(
            make_id(),
            type(
                "WebSearchNotificationItem",
                (),
                {
                    "id": str(_field(item, "id") or ""),
                    "query": str(_field(item, "query") or ""),
                    "action": _field(item, "action"),
                },
            )(),
        )

    return None


def final_message_from_notification_items(items: tuple[JsonValue, ...] | list[JsonValue]) -> str | None:
    turn_items: list[TurnItem] = []
    all_turn_items = True
    for item in items:
        turn_item = _turn_item_from_value(item)
        if turn_item is None:
            all_turn_items = False
            break
        turn_items.append(turn_item)
    if all_turn_items:
        return final_message_from_turn_items(tuple(turn_items))

    for item in reversed(tuple(items)):
        text = agent_message_text_from_notification_item(item)
        if text is not None:
            return text
    for item in reversed(tuple(items)):
        if _normalized_item_type(_field(item, "type")) == "plan":
            text = _field(item, "text")
            if text is not None:
                return str(text)
    return None


def agent_message_text_from_notification_item(item: JsonValue) -> str | None:
    turn_item = _turn_item_from_value(item)
    if turn_item is not None:
        return final_message_from_turn_items((turn_item,))
    if _normalized_item_type(_field(item, "type")) != "agent_message":
        return None
    text = _field(item, "text")
    if text is not None:
        return str(text)
    content = _field(item, "content")
    if isinstance(content, list | tuple):
        return "".join(str(_field(entry, "text") or "") for entry in content)
    return ""


def _turn_item_emits_exec_json(item: TurnItem) -> bool:
    if item.type not in _EXEC_JSON_TURN_ITEM_TYPES:
        return False
    if item.type == "Reasoning":
        text = "\n".join(str(entry) for entry in getattr(item.item, "summary_text", ()))
        return bool(text.strip())
    return True




def _permission_profile_from_config(config: JsonValue, session_configured: JsonValue) -> PermissionProfile:
    profile = _field(config, "permission_profile", "permissionProfile")
    if profile is None:
        profile = _field(session_configured, "permission_profile", "permissionProfile")
    if isinstance(profile, PermissionProfile):
        return profile
    if profile is not None:
        return PermissionProfile.from_mapping(profile)
    return PermissionProfile.read_only()


def _uses_responses_wire_api(config: JsonValue) -> bool:
    raw = _field(config, "wire_api", "wireApi")
    provider = _field(config, "model_provider", "modelProvider")
    if raw is None and provider is not None:
        raw = _field(provider, "wire_api", "wireApi")
    return raw is None or str(_enum_value(raw)).lower() == "responses"


def _optional_reasoning(value: JsonValue) -> str:
    if value is None:
        return "none"
    return str(_enum_value(value))


def _with_network_suffix(summary: str, network_policy: NetworkSandboxPolicy | JsonValue) -> str:
    policy = network_policy if isinstance(network_policy, NetworkSandboxPolicy) else NetworkSandboxPolicy(str(network_policy))
    return f"{summary} (network access enabled)" if policy.is_enabled() else summary


def _session_configured_thread_id(session_configured: JsonValue) -> str:
    value = _field(session_configured, "thread_id", "threadId")
    if value is None:
        value = _field(session_configured, "session_id", "sessionId")
    return _id_to_string(value)


def _session_configured_session_id(session_configured: JsonValue) -> str:
    return _id_to_string(_field(session_configured, "session_id", "sessionId"))


def _id_to_string(value: JsonValue) -> str:
    if hasattr(value, "to_json") and callable(value.to_json):
        return str(value.to_json())
    return "" if value is None else str(value)


def _enum_value(value: JsonValue) -> JsonValue:
    return value.value if isinstance(value, Enum) else value


def _field(value: JsonValue, *names: str) -> JsonValue:
    if value is None:
        return None
    if isinstance(value, Mapping):
        for name in names:
            if name in value:
                return value[name]
        return None
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return None


def _int_field(value: JsonValue, *names: str) -> int:
    return _optional_int(_field(value, *names)) or 0


def _optional_int(value: JsonValue) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: JsonValue) -> str | None:
    if value is None:
        return None
    return str(value)


def _command_actions(value: JsonValue) -> tuple[JsonValue, ...] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return None


def _message_with_details(summary: JsonValue, details: JsonValue) -> str:
    summary_text = str(summary)
    if details:
        return f"{summary_text} ({details})"
    return summary_text


def _warning_summary(params: JsonValue) -> str:
    return str(_field(params, "summary", "message") or "")


def _notification_details(params: JsonValue) -> JsonValue:
    return _field(params, "details", "additionalDetails", "additional_details")


def _turn_error_message(error: JsonValue) -> str | None:
    if error is None:
        return None
    if isinstance(error, str):
        return error
    message = _field(error, "message")
    if message is None:
        return str(error)
    return _message_with_details(message, _field(error, "additionalDetails", "additional_details"))


def _model_rerouted_message(params: JsonValue, *, include_reason: bool) -> str:
    message = f"model rerouted: {_field(params, 'fromModel', 'from_model')} -> {_field(params, 'toModel', 'to_model')}"
    reason = _field(params, "reason")
    if include_reason:
        message = f"{message} ({_model_reroute_reason_debug(reason)})"
    return message


def _model_reroute_reason_debug(reason: JsonValue) -> str:
    value = _enum_value(reason)
    if value is None:
        return "None"
    text = str(value)
    if "_" in text:
        return "".join(part[:1].upper() + part[1:] for part in text.split("_") if part)
    return text[:1].upper() + text[1:] if text else text


def _turn_items(turn: JsonValue) -> tuple[JsonValue, ...]:
    items = _field(turn, "items")
    return tuple(items) if isinstance(items, list | tuple) else ()


def _turn_item_from_value(value: JsonValue) -> TurnItem | None:
    if isinstance(value, TurnItem):
        return value
    if not isinstance(value, Mapping):
        return None
    try:
        return TurnItem.from_mapping(value)
    except (KeyError, TypeError, ValueError):
        return None


def _item_id(item: JsonValue) -> str | None:
    turn_item = item if isinstance(item, TurnItem) else None
    if turn_item is not None:
        try:
            return turn_item.id()
        except AttributeError:
            return None
    raw = _field(item, "id")
    return None if raw is None else str(raw)


def _normalized_status(value: JsonValue) -> str:
    raw = str(_enum_value(value) or "")
    aliases = {
        "Completed": "completed",
        "completed": "completed",
        "Failed": "failed",
        "failed": "failed",
        "Interrupted": "interrupted",
        "interrupted": "interrupted",
        "InProgress": "in_progress",
        "inProgress": "in_progress",
        "in_progress": "in_progress",
        "Pending": "pending",
        "pending": "pending",
        "Declined": "declined",
        "declined": "declined",
    }
    return aliases.get(raw, raw)


def _normalized_item_type(value: JsonValue) -> str:
    raw = str(_enum_value(value) or "")
    aliases = {
        "AgentMessage": "agent_message",
        "agentMessage": "agent_message",
        "Reasoning": "reasoning",
        "reasoning": "reasoning",
        "CommandExecution": "command_execution",
        "commandExecution": "command_execution",
        "FileChange": "file_change",
        "fileChange": "file_change",
        "McpToolCall": "mcp_tool_call",
        "mcpToolCall": "mcp_tool_call",
        "CollabAgentToolCall": "collab_agent_tool_call",
        "collabAgentToolCall": "collab_agent_tool_call",
        "WebSearch": "web_search",
        "webSearch": "web_search",
        "ContextCompaction": "context_compaction",
        "contextCompaction": "context_compaction",
        "Plan": "plan",
        "plan": "plan",
    }
    return aliases.get(raw, raw)


def _uses_raw_exec_notification_boundary(item: JsonValue) -> bool:
    if not isinstance(item, Mapping):
        return False
    return _normalized_item_type(_field(item, "type")) in {
        "collab_agent_tool_call",
        "file_change",
        "web_search",
    }


def _turn_item_to_app_server_like_mapping(item: TurnItem) -> dict[str, JsonValue]:
    try:
        return item.to_app_server_mapping()
    except ValueError:
        pass
    return {"type": item.type, "id": item.id()}


def _file_change_entries(changes: JsonValue) -> list[dict[str, str]]:
    if isinstance(changes, Mapping):
        return [
            {
                "path": Path(str(path)).as_posix(),
                "kind": _patch_kind_text(_patch_kind_value(change)),
            }
            for path, change in changes.items()
        ]
    if isinstance(changes, list | tuple):
        return [
            {
                "path": Path(str(_field(change, "path") or "")).as_posix(),
                "kind": _patch_kind_text(_patch_kind_value(_field(change, "kind"))),
            }
            for change in changes
        ]
    return []


def _patch_kind_value(value: JsonValue) -> JsonValue:
    if isinstance(value, Mapping):
        kind = _field(value, "kind")
        if kind is not None:
            return _patch_kind_value(kind)
        return _field(value, "type")
    return value


def _patch_kind_text(value: JsonValue) -> str:
    raw = str(_enum_value(value) or "")
    if raw in {"add", "Add"}:
        return "add"
    if raw in {"delete", "Delete"}:
        return "delete"
    if raw in {"update", "Update", ""}:
        return "update"
    return raw


def _patch_status_text(value: JsonValue) -> str:
    status = _normalized_status(value)
    if status == "completed":
        return "completed"
    if status in {"failed", "declined"}:
        return status
    if status in {"in_progress", ""}:
        return "in_progress"
    return status


def _patch_status_for_exec_json(value: JsonValue) -> str:
    status = _patch_status_text(value)
    if status == "declined":
        return "failed"
    return status


def _mcp_status_text(value: JsonValue) -> str:
    status = _normalized_status(value)
    if status == "completed":
        return "completed"
    if status == "failed":
        return "failed"
    if status in {"in_progress", ""}:
        return "in_progress"
    return status


def _mcp_result_mapping(value: JsonValue) -> JsonValue:
    if value is None:
        return None
    if hasattr(value, "to_mapping") and callable(value.to_mapping):
        return value.to_mapping()
    if not isinstance(value, Mapping):
        return value
    data: dict[str, JsonValue] = {
        "content": list(value.get("content", ())),
        "structured_content": value.get("structuredContent", value.get("structured_content")),
    }
    meta = value.get("_meta")
    if meta is not None:
        data["_meta"] = meta
    return data


def _mcp_error_mapping(value: JsonValue) -> JsonValue:
    if value is None:
        return None
    message = _field(value, "message")
    return {"message": str(message)} if message is not None else value


def _command_completion_line(item: JsonValue) -> str:
    status = _normalized_status(_field(item, "status"))
    suffix = _duration_suffix(_field(item, "durationMs", "duration_ms"))
    if status == "completed":
        return f" succeeded{suffix}:"
    if status == "failed":
        return f" exited {_optional_int(_field(item, 'exitCode', 'exit_code')) or 1}{suffix}:"
    if status == "declined":
        return f" declined{suffix}:"
    return f" in progress{suffix}:"


def _duration_suffix(value: JsonValue) -> str:
    duration = _optional_int(value)
    return f" in {duration}ms" if duration is not None else ""


def _collab_tool_debug(value: JsonValue) -> str:
    raw = str(_enum_value(value) or "")
    aliases = {
        "spawnAgent": "SpawnAgent",
        "spawn_agent": "SpawnAgent",
        "SpawnAgent": "SpawnAgent",
        "sendInput": "SendInput",
        "send_input": "SendInput",
        "SendInput": "SendInput",
        "resumeAgent": "ResumeAgent",
        "resume_agent": "ResumeAgent",
        "ResumeAgent": "ResumeAgent",
        "wait": "Wait",
        "Wait": "Wait",
        "closeAgent": "CloseAgent",
        "close_agent": "CloseAgent",
        "CloseAgent": "CloseAgent",
    }
    return aliases.get(raw, raw)


def _is_terminal(stream: TextIO, explicit: bool | None) -> bool:
    if explicit is not None:
        return explicit
    isatty = getattr(stream, "isatty", None)
    return bool(isatty()) if callable(isatty) else False


__all__ = [
    "CodexStatus",
    "EventProcessor",
    "agent_message_text_from_notification_item",
    "exec_turn_completed_notification",
    "exec_turn_started_notification",
    "exec_item_from_app_server_item",
    "handle_last_message",
    "map_todo_items",
    "notification_method",
    "notification_params",
    "usage_from_notification",
]
