"""Shared builders for app-server ``ThreadItem`` values.

Ported from ``codex-rs/app-server-protocol/src/protocol/item_builders.rs``.
The Rust module projects core approval, exec, patch, and guardian events into
presentation-oriented v2 ``ThreadItem`` values. Python keeps the same public
builder surface and accepts either the already-ported core event dataclasses or
mapping/duck-typed payloads from neighboring modules.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from pycodex.protocol.approvals import FileChange
from pycodex.protocol.parse_command import ParsedCommand
from pycodex.shell_command.parse_command import parse_command, shlex_join

from .item import (
    AutoReviewDecisionSource,
    CommandAction,
    CommandExecutionSource,
    CommandExecutionStatus,
    FileUpdateChange,
    GuardianApprovalReview,
    GuardianApprovalReviewAction,
    GuardianApprovalReviewStatus,
    ItemGuardianApprovalReviewCompletedNotification,
    ItemGuardianApprovalReviewStartedNotification,
    PatchApplyStatus,
    PatchChangeKind,
    ThreadItem,
)

JsonValue = Any


@dataclass(frozen=True)
class ServerNotification:
    """Small compatibility facade for ``protocol/common.rs::ServerNotification``.

    The full notification enum belongs to ``common.rs``. This facade preserves
    typed notification payloads emitted by builder/event-mapping modules while
    delegating wire method lookup to the common module when it is available.
    """

    type: str
    payload: JsonValue

    def to_mapping(self) -> dict[str, JsonValue]:
        method = _server_notification_method(self.type)
        payload = _to_json(self.payload)
        return {"type": self.type, "method": method, "params": payload}


def _server_notification_method(type_name: str) -> str:
    try:
        from .common import SERVER_NOTIFICATION_METHODS
    except Exception:
        return {
            "ItemGuardianApprovalReviewStarted": "item/autoApprovalReview/started",
            "ItemGuardianApprovalReviewCompleted": "item/autoApprovalReview/completed",
        }.get(type_name, type_name)
    return SERVER_NOTIFICATION_METHODS.get(type_name, type_name)


def build_file_change_approval_request_item(payload: JsonValue) -> ThreadItem:
    return _file_change_item(payload, PatchApplyStatus.IN_PROGRESS)


def build_file_change_begin_item(payload: JsonValue) -> ThreadItem:
    return _file_change_item(payload, PatchApplyStatus.IN_PROGRESS)


def build_file_change_end_item(payload: JsonValue) -> ThreadItem:
    return _file_change_item(payload, _patch_status(_get(payload, "status")))


def build_command_execution_approval_request_item(payload: JsonValue) -> ThreadItem:
    return _command_execution_item(
        payload,
        source=CommandExecutionSource.AGENT,
        status=CommandExecutionStatus.IN_PROGRESS,
        process_id=None,
        aggregated_output=None,
        exit_code=None,
        duration_ms=None,
    )


def build_command_execution_begin_item(payload: JsonValue) -> ThreadItem:
    return _command_execution_item(
        payload,
        source=_command_source(_get(payload, "source", default=CommandExecutionSource.AGENT)),
        status=CommandExecutionStatus.IN_PROGRESS,
        process_id=_optional_str(_get(payload, "process_id", "processId", default=None), "process_id"),
        aggregated_output=None,
        exit_code=None,
        duration_ms=None,
    )


def build_command_execution_end_item(payload: JsonValue) -> ThreadItem:
    output = _optional_str(_get(payload, "aggregated_output", "aggregatedOutput", default=""), "aggregated_output")
    return _command_execution_item(
        payload,
        source=_command_source(_get(payload, "source", default=CommandExecutionSource.AGENT)),
        status=_command_status(_get(payload, "status")),
        process_id=_optional_str(_get(payload, "process_id", "processId", default=None), "process_id"),
        aggregated_output=output or None,
        exit_code=_optional_int(_get(payload, "exit_code", "exitCode", default=None), "exit_code"),
        duration_ms=_duration_ms(_get(payload, "duration", default=None)),
    )


def build_item_from_guardian_event(
    assessment: JsonValue,
    status: CommandExecutionStatus | str,
) -> ThreadItem | None:
    action = _get(assessment, "action")
    action_type = _variant_type(action)
    target_item_id = _optional_str(_get(assessment, "target_item_id", "targetItemId", default=None), "target_item_id")
    if target_item_id is None:
        return None

    if action_type == "command":
        command = _str(_get(action, "command"), "command")
        cwd = _path(_get(action, "cwd"), "cwd")
        command_actions = [CommandAction.unknown(command)]
        return _command_execution_thread_item(
            id=target_item_id,
            command=command,
            cwd=cwd,
            process_id=None,
            source=CommandExecutionSource.AGENT,
            status=_command_status(status),
            command_actions=command_actions,
            aggregated_output=None,
            exit_code=None,
            duration_ms=None,
        )

    if action_type == "execve":
        program = _str(_get(action, "program"), "program")
        argv = _string_sequence(_get(action, "argv", default=()), "argv")
        cwd = _path(_get(action, "cwd"), "cwd")
        command_argv = [program] if not argv else [program, *argv[1:]]
        command = shlex_join(command_argv)
        parsed = parse_command(command_argv)
        command_actions = _command_actions(parsed, cwd) or [CommandAction.unknown(command)]
        return _command_execution_thread_item(
            id=target_item_id,
            command=command,
            cwd=cwd,
            process_id=None,
            source=CommandExecutionSource.AGENT,
            status=_command_status(status),
            command_actions=command_actions,
            aggregated_output=None,
            exit_code=None,
            duration_ms=None,
        )

    if action_type in {"apply_patch", "network_access", "mcp_tool_call", "request_permissions"}:
        return None
    return None


def guardian_auto_approval_review_notification(
    conversation_id: str,
    event_turn_id: str,
    assessment: JsonValue,
) -> ServerNotification:
    turn_id = _optional_str(_get(assessment, "turn_id", "turnId", default=""), "turn_id") or event_turn_id
    status = _guardian_status(_get(assessment, "status"))
    review = GuardianApprovalReview(
        status=status,
        risk_level=_enum_value(_get(assessment, "risk_level", "riskLevel", default=None)),
        user_authorization=_enum_value(_get(assessment, "user_authorization", "userAuthorization", default=None)),
        rationale=_optional_str(_get(assessment, "rationale", default=None), "rationale"),
    )
    action = _guardian_action(_get(assessment, "action"))
    if status is GuardianApprovalReviewStatus.IN_PROGRESS:
        payload = ItemGuardianApprovalReviewStartedNotification(
            thread_id=str(conversation_id),
            turn_id=turn_id,
            review_id=_str(_get(assessment, "id"), "id"),
            started_at_ms=_int(_get(assessment, "started_at_ms", "startedAtMs", default=0), "started_at_ms"),
            target_item_id=_optional_str(_get(assessment, "target_item_id", "targetItemId", default=None), "target_item_id"),
            review=review,
            action=action,
        )
        return ServerNotification("ItemGuardianApprovalReviewStarted", payload)

    started_at_ms = _int(_get(assessment, "started_at_ms", "startedAtMs", default=0), "started_at_ms")
    completed_at_ms = _get(assessment, "completed_at_ms", "completedAtMs", default=None)
    payload = ItemGuardianApprovalReviewCompletedNotification(
        thread_id=str(conversation_id),
        turn_id=turn_id,
        review_id=_str(_get(assessment, "id"), "id"),
        started_at_ms=started_at_ms,
        completed_at_ms=_int(completed_at_ms, "completed_at_ms") if completed_at_ms is not None else started_at_ms,
        target_item_id=_optional_str(_get(assessment, "target_item_id", "targetItemId", default=None), "target_item_id"),
        decision_source=_auto_review_source(_get(assessment, "decision_source", "decisionSource", default=None)),
        review=review,
        action=action,
    )
    return ServerNotification("ItemGuardianApprovalReviewCompleted", payload)


def convert_patch_changes(changes: Mapping[Path | str, FileChange | Mapping[str, JsonValue]]) -> list[FileUpdateChange]:
    converted = [
        FileUpdateChange(path=str(path), kind=map_patch_change_kind(change).to_mapping(), diff=format_file_change_diff(change))
        for path, change in changes.items()
    ]
    return sorted(converted, key=lambda item: item.path)


def map_patch_change_kind(change: FileChange | Mapping[str, JsonValue]) -> PatchChangeKind:
    change_type = _file_change_type(change)
    if change_type == "add":
        return PatchChangeKind.add()
    if change_type == "delete":
        return PatchChangeKind.delete()
    if change_type == "update":
        move_path = _get(change, "move_path", "movePath", default=None)
        return PatchChangeKind.update(str(move_path) if move_path is not None else None)
    raise ValueError(f"unknown file change type: {change_type}")


def format_file_change_diff(change: FileChange | Mapping[str, JsonValue]) -> str:
    change_type = _file_change_type(change)
    if change_type in {"add", "delete"}:
        return _str(_get(change, "content"), "content")
    if change_type == "update":
        unified_diff = _str(_get(change, "unified_diff", "unifiedDiff"), "unified_diff")
        move_path = _get(change, "move_path", "movePath", default=None)
        if move_path is None:
            return unified_diff
        return f"{unified_diff}\n\nMoved to: {move_path}"
    raise ValueError(f"unknown file change type: {change_type}")


def _file_change_item(payload: JsonValue, status: PatchApplyStatus | str) -> ThreadItem:
    return ThreadItem(
        "fileChange",
        {
            "id": _str(_get(payload, "call_id", "callId"), "call_id"),
            "changes": [change.to_mapping() for change in convert_patch_changes(_changes(payload))],
            "status": _patch_status(status).value,
        },
    )


def _command_execution_item(
    payload: JsonValue,
    *,
    source: CommandExecutionSource,
    status: CommandExecutionStatus,
    process_id: str | None,
    aggregated_output: str | None,
    exit_code: int | None,
    duration_ms: int | None,
) -> ThreadItem:
    cwd = _path(_get(payload, "cwd"), "cwd")
    command_tokens = _string_sequence(_get(payload, "command"), "command")
    parsed_cmd = _get(payload, "parsed_cmd", "parsedCmd", default=())
    return _command_execution_thread_item(
        id=_str(_get(payload, "call_id", "callId"), "call_id"),
        command=shlex_join(command_tokens),
        cwd=cwd,
        process_id=process_id,
        source=source,
        status=status,
        command_actions=_command_actions(parsed_cmd, cwd),
        aggregated_output=aggregated_output,
        exit_code=exit_code,
        duration_ms=duration_ms,
    )


def _command_execution_thread_item(
    *,
    id: str,
    command: str,
    cwd: str,
    process_id: str | None,
    source: CommandExecutionSource,
    status: CommandExecutionStatus,
    command_actions: Sequence[CommandAction],
    aggregated_output: str | None,
    exit_code: int | None,
    duration_ms: int | None,
) -> ThreadItem:
    return ThreadItem(
        "commandExecution",
        {
            "id": id,
            "command": command,
            "cwd": cwd,
            "processId": process_id,
            "source": source.value,
            "status": status.value,
            "commandActions": [action.to_mapping() for action in command_actions],
            "aggregatedOutput": aggregated_output,
            "exitCode": exit_code,
            "durationMs": duration_ms,
        },
    )


def _command_actions(parsed_cmd: JsonValue, cwd: str) -> list[CommandAction]:
    result: list[CommandAction] = []
    for parsed in _sequence(parsed_cmd):
        command = parsed if isinstance(parsed, ParsedCommand) else ParsedCommand.from_mapping(parsed)
        if command.type == "read":
            result.append(CommandAction.read(command.cmd, command.name or "", Path(cwd) / Path(command.path or "")))
        elif command.type == "list_files":
            result.append(CommandAction.list_files(command.cmd, _optional_str(command.path, "path")))
        elif command.type == "search":
            result.append(CommandAction.search(command.cmd, command.query, command.path))
        elif command.type == "unknown":
            result.append(CommandAction.unknown(command.cmd))
        else:
            raise ValueError(f"unknown parsed command type: {command.type}")
    return result


def _changes(payload: JsonValue) -> Mapping[Path | str, FileChange | Mapping[str, JsonValue]]:
    changes = _get(payload, "changes", default={})
    if not isinstance(changes, Mapping):
        raise TypeError("changes must be a mapping")
    return changes


def _file_change_type(change: FileChange | Mapping[str, JsonValue]) -> str:
    return _str(_get(change, "type"), "type")


def _patch_status(value: JsonValue) -> PatchApplyStatus:
    raw = _enum_value(value)
    if raw == "in_progress":
        raw = "inProgress"
    return PatchApplyStatus.parse(raw)


def _command_status(value: JsonValue) -> CommandExecutionStatus:
    raw = _enum_value(value)
    if raw == "in_progress":
        raw = "inProgress"
    return CommandExecutionStatus.parse(raw)


def _command_source(value: JsonValue) -> CommandExecutionSource:
    raw = _enum_value(value)
    aliases = {
        "user_shell": "userShell",
        "unified_exec_startup": "unifiedExecStartup",
        "unified_exec_interaction": "unifiedExecInteraction",
    }
    return CommandExecutionSource.parse(aliases.get(raw, raw))


def _guardian_status(value: JsonValue) -> GuardianApprovalReviewStatus:
    raw = _enum_value(value)
    aliases = {"in_progress": "inProgress", "timed_out": "timedOut"}
    return GuardianApprovalReviewStatus.parse(aliases.get(raw, raw))


def _auto_review_source(value: JsonValue) -> AutoReviewDecisionSource:
    if value is None:
        return AutoReviewDecisionSource.AGENT
    return AutoReviewDecisionSource.parse(_enum_value(value))


def _guardian_action(action: JsonValue) -> GuardianApprovalReviewAction:
    action_type = _variant_type(action)
    if action_type == "command":
        return GuardianApprovalReviewAction(
            "command",
            {
                "source": _guardian_command_source(_get(action, "source", default="shell")),
                "command": _str(_get(action, "command"), "command"),
                "cwd": _path(_get(action, "cwd"), "cwd"),
            },
        )
    if action_type == "execve":
        return GuardianApprovalReviewAction(
            "execve",
            {
                "source": _guardian_command_source(_get(action, "source", default="shell")),
                "program": _str(_get(action, "program"), "program"),
                "argv": _string_sequence(_get(action, "argv", default=()), "argv"),
                "cwd": _path(_get(action, "cwd"), "cwd"),
            },
        )
    if action_type == "apply_patch":
        return GuardianApprovalReviewAction(
            "applyPatch",
            {
                "cwd": _path(_get(action, "cwd"), "cwd"),
                "files": [_path(file, "files") for file in _sequence(_get(action, "files", default=()))],
            },
        )
    if action_type == "network_access":
        return GuardianApprovalReviewAction(
            "networkAccess",
            {
                "target": _str(_get(action, "target"), "target"),
                "host": _str(_get(action, "host"), "host"),
                "protocol": _enum_value(_get(action, "protocol")),
                "port": _int(_get(action, "port"), "port"),
            },
        )
    if action_type == "mcp_tool_call":
        return GuardianApprovalReviewAction(
            "mcpToolCall",
            {
                "server": _str(_get(action, "server"), "server"),
                "toolName": _str(_get(action, "tool_name", "toolName"), "tool_name"),
                "connectorId": _optional_str(_get(action, "connector_id", "connectorId", default=None), "connector_id"),
                "connectorName": _optional_str(_get(action, "connector_name", "connectorName", default=None), "connector_name"),
                "toolTitle": _optional_str(_get(action, "tool_title", "toolTitle", default=None), "tool_title"),
            },
        )
    if action_type == "request_permissions":
        return GuardianApprovalReviewAction(
            "requestPermissions",
            {
                "reason": _optional_str(_get(action, "reason", default=None), "reason"),
                "permissions": _to_json(_get(action, "permissions")),
            },
        )
    raise ValueError(f"unknown guardian action type: {action_type}")


def _guardian_command_source(value: JsonValue) -> str:
    raw = _enum_value(value)
    return {"unified_exec": "unifiedExec"}.get(raw, raw)


def _duration_ms(value: JsonValue) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise TypeError("duration must not be bool")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, timedelta):
        return int(value.total_seconds() * 1000)
    if isinstance(value, Mapping):
        if "millis" in value:
            return _int(value["millis"], "duration.millis")
        if "ms" in value:
            return _int(value["ms"], "duration.ms")
    total_milliseconds = getattr(value, "total_milliseconds", None)
    if callable(total_milliseconds):
        return int(total_milliseconds())
    total_seconds = getattr(value, "total_seconds", None)
    if callable(total_seconds):
        return int(total_seconds() * 1000)
    raise TypeError("duration must be milliseconds, timedelta, or expose total_seconds")


def _variant_type(value: JsonValue) -> str:
    raw = _get(value, "type")
    aliases = {
        "Command": "command",
        "Execve": "execve",
        "ApplyPatch": "apply_patch",
        "NetworkAccess": "network_access",
        "McpToolCall": "mcp_tool_call",
        "RequestPermissions": "request_permissions",
    }
    return aliases.get(_enum_value(raw), _enum_value(raw))


def _get(value: JsonValue, *keys: str, default: JsonValue = None) -> JsonValue:
    if isinstance(value, Mapping):
        for key in keys:
            if key in value:
                return value[key]
        return default
    for key in keys:
        if hasattr(value, key):
            return getattr(value, key)
    return default


def _enum_value(value: JsonValue) -> JsonValue:
    return getattr(value, "value", value)


def _sequence(value: JsonValue) -> tuple[JsonValue, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError("value must be a sequence")
    return tuple(value)


def _string_sequence(value: JsonValue, field_name: str) -> list[str]:
    result = list(_sequence(value))
    if not all(isinstance(item, str) for item in result):
        raise TypeError(f"{field_name} must be a sequence of strings")
    return result


def _path(value: JsonValue, field_name: str) -> str:
    if isinstance(value, Path):
        return str(value)
    return _str(value, field_name)


def _str(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _optional_str(value: JsonValue, field_name: str) -> str | None:
    if value is None:
        return None
    return _str(value, field_name)


def _int(value: JsonValue, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    return value


def _optional_int(value: JsonValue, field_name: str) -> int | None:
    if value is None:
        return None
    return _int(value, field_name)


def _to_json(value: JsonValue) -> JsonValue:
    if hasattr(value, "to_camel_mapping"):
        return value.to_camel_mapping()
    if hasattr(value, "to_mapping"):
        return value.to_mapping()
    if isinstance(value, Mapping):
        return {str(key): _to_json(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json(child) for child in value]
    if isinstance(value, Path):
        return str(value)
    return _enum_value(value)


__all__ = [
    "ServerNotification",
    "build_command_execution_approval_request_item",
    "build_command_execution_begin_item",
    "build_command_execution_end_item",
    "build_file_change_approval_request_item",
    "build_file_change_begin_item",
    "build_file_change_end_item",
    "build_item_from_guardian_event",
    "convert_patch_changes",
    "format_file_change_diff",
    "guardian_auto_approval_review_notification",
    "map_patch_change_kind",
]
