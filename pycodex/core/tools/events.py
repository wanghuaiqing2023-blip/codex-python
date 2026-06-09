"""Pure tool event helpers ported from ``core/src/tools/events.rs``.

The Rust module also performs async session emission. This Python slice keeps
the same event-shaping and state-transition rules while leaving the concrete
session/runtime delivery as an injected boundary.
"""

from __future__ import annotations

import shlex
import inspect
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Mapping

from pycodex.core.function_tool import FunctionCallError
from pycodex.core.tools.sandboxing import ToolError
from pycodex.core.turn_diff_tracker import AppliedPatchDelta, TurnDiffTracker
from pycodex.core.user_shell_command import format_exec_output_for_model, format_exec_output_str
from pycodex.protocol import (
    CommandExecutionItem,
    EventMsg,
    ExecCommandBeginEvent,
    ExecCommandEndEvent,
    ExecCommandOutputDeltaEvent,
    ExecCommandSource,
    ExecCommandStatus,
    ExecToolCallOutput,
    FileChange,
    FileChangeItem,
    GuardianAssessmentDecisionSource,
    GuardianAssessmentEvent,
    GuardianAssessmentStatus,
    PatchApplyStatus,
    TruncationPolicyConfig,
    TurnDiffEvent,
    TurnItem,
)
from pycodex.protocol.parse_command import ParsedCommand
from pycodex.shell_command import parse_command

JsonValue = Any


def now_unix_timestamp_ms() -> int:
    return int(time.time() * 1000)


@dataclass(frozen=True)
class ToolEventCtx:
    session: Any
    turn: Any
    call_id: str
    turn_diff_tracker: TurnDiffTracker | None = None

    @classmethod
    def new(
        cls,
        session: Any,
        turn: Any,
        call_id: str,
        turn_diff_tracker: TurnDiffTracker | None = None,
    ) -> "ToolEventCtx":
        return cls(session, turn, call_id, turn_diff_tracker)

    def __post_init__(self) -> None:
        if not isinstance(self.call_id, str) or not self.call_id:
            raise TypeError("call_id must be a non-empty string")
        if self.turn_diff_tracker is not None and not isinstance(self.turn_diff_tracker, TurnDiffTracker):
            raise TypeError("turn_diff_tracker must be TurnDiffTracker or None")

    @property
    def turn_id(self) -> str:
        value = getattr(self.turn, "sub_id", None)
        if value is None:
            value = getattr(self.turn, "turn_id", "")
        return str(value)

    @property
    def truncation_policy(self) -> TruncationPolicyConfig:
        policy = getattr(self.turn, "truncation_policy", None)
        if isinstance(policy, TruncationPolicyConfig):
            return policy
        return TruncationPolicyConfig.tokens(4096)


@dataclass(frozen=True)
class ToolEventFailure:
    type: str
    output: ExecToolCallOutput | None = None
    message: str | None = None
    applied_patch_delta: AppliedPatchDelta | None = None

    def __post_init__(self) -> None:
        if self.type == "output":
            if not isinstance(self.output, ExecToolCallOutput):
                raise TypeError("output failure requires ExecToolCallOutput")
            if self.message is not None or self.applied_patch_delta is not None:
                raise ValueError("output failure must not include message or patch delta")
        elif self.type == "message":
            if not isinstance(self.message, str):
                raise TypeError("message failure requires a string message")
            if self.output is not None or self.applied_patch_delta is not None:
                raise ValueError("message failure must not include output or patch delta")
        elif self.type == "rejected":
            if not isinstance(self.message, str):
                raise TypeError("rejected failure requires a string message")
            if self.output is not None:
                raise ValueError("rejected failure must not include output")
            if self.applied_patch_delta is not None and not isinstance(self.applied_patch_delta, AppliedPatchDelta):
                raise TypeError("applied_patch_delta must be AppliedPatchDelta or None")
        else:
            raise ValueError(f"unsupported tool event failure type: {self.type}")

    @classmethod
    def output_failure(cls, output: ExecToolCallOutput) -> "ToolEventFailure":
        return cls("output", output=output)

    @classmethod
    def message_failure(cls, message: str) -> "ToolEventFailure":
        return cls("message", message=message)

    @classmethod
    def rejected(
        cls,
        message: str,
        applied_patch_delta: AppliedPatchDelta | None = None,
    ) -> "ToolEventFailure":
        return cls("rejected", message=message, applied_patch_delta=applied_patch_delta)


@dataclass(frozen=True, init=False)
class ToolEventStage:
    type: str
    output: ExecToolCallOutput | None = None
    applied_patch_delta: AppliedPatchDelta | None = None
    failure: ToolEventFailure | None = None

    def __init__(
        self,
        type: str,
        output: ExecToolCallOutput | None = None,
        applied_patch_delta: AppliedPatchDelta | None = None,
        failure: ToolEventFailure | None = None,
    ) -> None:
        object.__setattr__(self, "type", type)
        object.__setattr__(self, "output", output)
        object.__setattr__(self, "applied_patch_delta", applied_patch_delta)
        object.__setattr__(self, "failure", failure)
        self.__post_init__()

    def __post_init__(self) -> None:
        if self.type == "begin":
            if self.output is not None or self.applied_patch_delta is not None or self.failure is not None:
                raise ValueError("begin stage must not include output, patch delta, or failure")
        elif self.type == "success":
            if not isinstance(self.output, ExecToolCallOutput):
                raise TypeError("success stage requires ExecToolCallOutput")
            if self.applied_patch_delta is not None and not isinstance(self.applied_patch_delta, AppliedPatchDelta):
                raise TypeError("applied_patch_delta must be AppliedPatchDelta or None")
            if self.failure is not None:
                raise ValueError("success stage must not include failure")
        elif self.type == "failure":
            if not isinstance(self.failure, ToolEventFailure):
                raise TypeError("failure stage requires ToolEventFailure")
            if self.output is not None or self.applied_patch_delta is not None:
                raise ValueError("failure stage must not include direct output or patch delta")
        else:
            raise ValueError(f"unsupported tool event stage type: {self.type}")

    @classmethod
    def begin(cls) -> "ToolEventStage":
        return cls("begin")

    @classmethod
    def success(
        cls,
        output: ExecToolCallOutput,
        applied_patch_delta: AppliedPatchDelta | None = None,
    ) -> "ToolEventStage":
        return cls("success", output=output, applied_patch_delta=applied_patch_delta)

    @classmethod
    def failure(cls, failure: ToolEventFailure) -> "ToolEventStage":
        return cls("failure", failure=failure)


@dataclass(frozen=True)
class TurnDiffTrackerUpdate:
    type: str
    delta: AppliedPatchDelta | None = None

    def __post_init__(self) -> None:
        if self.type == "track":
            if not isinstance(self.delta, AppliedPatchDelta):
                raise TypeError("track update requires AppliedPatchDelta")
        elif self.type in ("invalidate", "none"):
            if self.delta is not None:
                raise ValueError(f"{self.type} update must not include a delta")
        else:
            raise ValueError(f"unsupported turn diff tracker update type: {self.type}")

    @classmethod
    def track(cls, delta: AppliedPatchDelta) -> "TurnDiffTrackerUpdate":
        return cls("track", delta)

    @classmethod
    def invalidate(cls) -> "TurnDiffTrackerUpdate":
        return cls("invalidate")

    @classmethod
    def none(cls) -> "TurnDiffTrackerUpdate":
        return cls("none")


def tracker_update_for_known_delta(delta: AppliedPatchDelta) -> TurnDiffTrackerUpdate:
    if not isinstance(delta, AppliedPatchDelta):
        raise TypeError("delta must be AppliedPatchDelta")
    if delta.is_exact() and delta.is_empty():
        return TurnDiffTrackerUpdate.none()
    return TurnDiffTrackerUpdate.track(delta)


@dataclass(frozen=True)
class ExecCommandInput:
    command: tuple[str, ...]
    cwd: Path
    parsed_cmd: tuple[JsonValue, ...] = ()
    source: ExecCommandSource = ExecCommandSource.AGENT
    interaction_input: str | None = None
    process_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", _string_tuple(self.command, "command"))
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(self.cwd))
        if not isinstance(self.parsed_cmd, tuple):
            object.__setattr__(self, "parsed_cmd", tuple(self.parsed_cmd))
        if not isinstance(self.source, ExecCommandSource):
            object.__setattr__(self, "source", ExecCommandSource(self.source))
        if self.interaction_input is not None and not isinstance(self.interaction_input, str):
            raise TypeError("interaction_input must be a string or None")
        if self.process_id is not None and not isinstance(self.process_id, str):
            raise TypeError("process_id must be a string or None")

    @classmethod
    def new(
        cls,
        command: tuple[str, ...] | list[str],
        cwd: str | Path,
        parsed_cmd: tuple[JsonValue, ...] | list[JsonValue] = (),
        source: ExecCommandSource = ExecCommandSource.AGENT,
        interaction_input: str | None = None,
        process_id: str | None = None,
    ) -> "ExecCommandInput":
        return cls(tuple(command), Path(cwd), tuple(parsed_cmd), source, interaction_input, process_id)


@dataclass(frozen=True)
class ExecCommandResult:
    stdout: str
    stderr: str
    aggregated_output: str
    exit_code: int
    duration: timedelta
    formatted_output: str
    status: ExecCommandStatus

    def __post_init__(self) -> None:
        for field_name in ("stdout", "stderr", "aggregated_output", "formatted_output"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string")
        if isinstance(self.exit_code, bool) or not isinstance(self.exit_code, int):
            raise TypeError("exit_code must be an int")
        if not isinstance(self.duration, timedelta):
            raise TypeError("duration must be a timedelta")
        if not isinstance(self.status, ExecCommandStatus):
            object.__setattr__(self, "status", ExecCommandStatus(self.status))


def build_exec_command_begin_event(
    ctx: ToolEventCtx,
    exec_input: ExecCommandInput,
    *,
    started_at_ms: int | None = None,
) -> EventMsg:
    _ensure_ctx_and_input(ctx, exec_input)
    return EventMsg.with_payload(
        "exec_command_begin",
        ExecCommandBeginEvent(
            call_id=ctx.call_id,
            process_id=exec_input.process_id,
            turn_id=ctx.turn_id,
            started_at_ms=now_unix_timestamp_ms() if started_at_ms is None else _int_ms(started_at_ms),
            command=exec_input.command,
            cwd=exec_input.cwd,
            parsed_cmd=exec_input.parsed_cmd,
            source=exec_input.source,
            interaction_input=exec_input.interaction_input,
        ),
    )


def exec_command_result_from_output(
    output: ExecToolCallOutput,
    truncation_policy: TruncationPolicyConfig,
) -> ExecCommandResult:
    if not isinstance(output, ExecToolCallOutput):
        raise TypeError("output must be ExecToolCallOutput")
    if not isinstance(truncation_policy, TruncationPolicyConfig):
        raise TypeError("truncation_policy must be TruncationPolicyConfig")
    return ExecCommandResult(
        stdout=output.stdout.text,
        stderr=output.stderr.text,
        aggregated_output=output.aggregated_output.text,
        exit_code=output.exit_code,
        duration=output.duration,
        formatted_output=format_exec_output_str(output, truncation_policy),
        status=ExecCommandStatus.COMPLETED if output.exit_code == 0 else ExecCommandStatus.FAILED,
    )


def exec_command_result_from_message(message: str, status: ExecCommandStatus) -> ExecCommandResult:
    if not isinstance(message, str):
        raise TypeError("message must be a string")
    if not isinstance(status, ExecCommandStatus):
        status = ExecCommandStatus(status)
    return ExecCommandResult("", message, message, -1, timedelta(0), message, status)


def exec_command_result_for_stage(
    stage: ToolEventStage,
    truncation_policy: TruncationPolicyConfig,
) -> ExecCommandResult | None:
    if not isinstance(stage, ToolEventStage):
        raise TypeError("stage must be ToolEventStage")
    if stage.type == "begin":
        return None
    if stage.type == "success" and stage.output is not None:
        return exec_command_result_from_output(stage.output, truncation_policy)
    failure = stage.failure
    if failure is None:
        raise TypeError("failure stage requires failure")
    if failure.type == "output" and failure.output is not None:
        return exec_command_result_from_output(failure.output, truncation_policy)
    if failure.type == "message" and failure.message is not None:
        return exec_command_result_from_message(failure.message, ExecCommandStatus.FAILED)
    if failure.type == "rejected" and failure.message is not None:
        return exec_command_result_from_message(failure.message, ExecCommandStatus.DECLINED)
    raise TypeError("invalid failure stage")


def build_exec_command_end_event(
    ctx: ToolEventCtx,
    exec_input: ExecCommandInput,
    exec_result: ExecCommandResult,
    *,
    completed_at_ms: int | None = None,
) -> EventMsg:
    _ensure_ctx_and_input(ctx, exec_input)
    if not isinstance(exec_result, ExecCommandResult):
        raise TypeError("exec_result must be ExecCommandResult")
    return EventMsg.with_payload(
        "exec_command_end",
        ExecCommandEndEvent(
            call_id=ctx.call_id,
            process_id=exec_input.process_id,
            turn_id=ctx.turn_id,
            completed_at_ms=now_unix_timestamp_ms() if completed_at_ms is None else _int_ms(completed_at_ms),
            command=exec_input.command,
            cwd=exec_input.cwd,
            parsed_cmd=exec_input.parsed_cmd,
            source=exec_input.source,
            interaction_input=exec_input.interaction_input,
            stdout=exec_result.stdout,
            stderr=exec_result.stderr,
            aggregated_output=exec_result.aggregated_output,
            exit_code=exec_result.exit_code,
            duration=exec_result.duration,
            formatted_output=exec_result.formatted_output,
            status=exec_result.status,
        ),
    )


def build_command_execution_begin_item(payload: ExecCommandBeginEvent) -> TurnItem:
    if not isinstance(payload, ExecCommandBeginEvent):
        raise TypeError("payload must be ExecCommandBeginEvent")
    return TurnItem.command_execution(
        CommandExecutionItem(
            id=payload.call_id,
            command=shlex.join(payload.command),
            cwd=payload.cwd,
            process_id=payload.process_id,
            source=_command_execution_source(payload.source),
            status="inProgress",
            command_actions=_command_actions_from_parsed_commands(payload.parsed_cmd, payload.cwd),
            aggregated_output=None,
            exit_code=None,
            duration_ms=None,
        )
    )


def build_command_execution_end_item(payload: ExecCommandEndEvent) -> TurnItem:
    if not isinstance(payload, ExecCommandEndEvent):
        raise TypeError("payload must be ExecCommandEndEvent")
    return TurnItem.command_execution(
        CommandExecutionItem(
            id=payload.call_id,
            command=shlex.join(payload.command),
            cwd=payload.cwd,
            process_id=payload.process_id,
            source=_command_execution_source(payload.source),
            status=_command_execution_status(payload.status),
            command_actions=_command_actions_from_parsed_commands(payload.parsed_cmd, payload.cwd),
            aggregated_output=payload.aggregated_output or None,
            exit_code=payload.exit_code,
            duration_ms=_duration_ms(payload.duration),
        )
    )


def build_command_execution_item_from_guardian_event(
    assessment: GuardianAssessmentEvent,
    status: str,
) -> TurnItem | None:
    if not isinstance(assessment, GuardianAssessmentEvent):
        raise TypeError("assessment must be GuardianAssessmentEvent")
    if assessment.target_item_id is None:
        return None

    action = assessment.action
    if action.type == "command":
        command = action.command or ""
        return TurnItem.command_execution(
            CommandExecutionItem(
                id=assessment.target_item_id,
                command=command,
                cwd=action.cwd or Path("."),
                process_id=None,
                source="agent",
                status=status,
                command_actions=({"type": "unknown", "command": command},),
                aggregated_output=None,
                exit_code=None,
                duration_ms=None,
            )
        )

    if action.type == "execve":
        argv = (action.program or "",) if not action.argv else (action.program or "", *action.argv[1:])
        command = shlex.join(tuple(part for part in argv if part != ""))
        parsed_cmd = parse_command(argv)
        command_actions = (
            tuple(_command_action_from_parsed(parsed, action.cwd or Path(".")) for parsed in parsed_cmd)
            if parsed_cmd
            else ({"type": "unknown", "command": command},)
        )
        return TurnItem.command_execution(
            CommandExecutionItem(
                id=assessment.target_item_id,
                command=command,
                cwd=action.cwd or Path("."),
                process_id=None,
                source="agent",
                status=status,
                command_actions=command_actions,
                aggregated_output=None,
                exit_code=None,
                duration_ms=None,
            )
        )

    return None


def build_command_execution_item_mapping_from_guardian_event(
    assessment: GuardianAssessmentEvent,
) -> dict[str, JsonValue] | None:
    status = command_execution_status_from_guardian_status(assessment.status)
    if status is None:
        return None
    item = build_command_execution_item_from_guardian_event(assessment, status)
    if item is None:
        return None
    return _command_execution_notification_item_mapping(item)


def guardian_auto_approval_review_notification(
    thread_id: str,
    event_turn_id: str,
    assessment: GuardianAssessmentEvent,
) -> dict[str, JsonValue]:
    if not isinstance(assessment, GuardianAssessmentEvent):
        raise TypeError("assessment must be GuardianAssessmentEvent")
    params: dict[str, JsonValue] = {
        "threadId": str(thread_id),
        "turnId": assessment.turn_id or str(event_turn_id),
        "startedAtMs": assessment.started_at_ms,
        "reviewId": assessment.id,
        "targetItemId": assessment.target_item_id,
        "review": {
            "status": _guardian_review_status(assessment.status),
            "riskLevel": assessment.risk_level.value if assessment.risk_level is not None else None,
            "userAuthorization": assessment.user_authorization.value if assessment.user_authorization is not None else None,
            "rationale": assessment.rationale,
        },
        "action": _guardian_review_action_mapping(assessment.action),
    }
    if assessment.status == GuardianAssessmentStatus.IN_PROGRESS:
        return {"method": "item/autoApprovalReview/started", "params": params}
    params["completedAtMs"] = assessment.completed_at_ms if assessment.completed_at_ms is not None else assessment.started_at_ms
    params["decisionSource"] = _auto_review_decision_source(assessment.decision_source)
    return {"method": "item/autoApprovalReview/completed", "params": params}


def command_execution_status_from_guardian_status(status: GuardianAssessmentStatus) -> str | None:
    if not isinstance(status, GuardianAssessmentStatus):
        status = GuardianAssessmentStatus(status)
    if status == GuardianAssessmentStatus.IN_PROGRESS:
        return "inProgress"
    if status in {GuardianAssessmentStatus.DENIED, GuardianAssessmentStatus.ABORTED}:
        return "declined"
    if status == GuardianAssessmentStatus.TIMED_OUT:
        return "failed"
    return None


def _guardian_review_status(status: GuardianAssessmentStatus) -> str:
    if not isinstance(status, GuardianAssessmentStatus):
        status = GuardianAssessmentStatus(status)
    return {
        GuardianAssessmentStatus.IN_PROGRESS: "inProgress",
        GuardianAssessmentStatus.APPROVED: "approved",
        GuardianAssessmentStatus.DENIED: "denied",
        GuardianAssessmentStatus.TIMED_OUT: "timedOut",
        GuardianAssessmentStatus.ABORTED: "aborted",
    }[status]


def _auto_review_decision_source(source: GuardianAssessmentDecisionSource | None) -> str:
    if source is None:
        return "agent"
    if not isinstance(source, GuardianAssessmentDecisionSource):
        source = GuardianAssessmentDecisionSource(source)
    return source.value


def _guardian_command_source(source: JsonValue) -> str:
    raw = getattr(source, "value", source)
    if raw == "unified_exec":
        return "unifiedExec"
    return str(raw or "shell")


def _guardian_review_action_mapping(action: JsonValue) -> dict[str, JsonValue]:
    action_type = getattr(action, "type", None)
    if action_type == "command":
        return {"type": "command", "source": _guardian_command_source(getattr(action, "source", None)), "command": getattr(action, "command", None), "cwd": str(getattr(action, "cwd", ""))}
    if action_type == "execve":
        return {"type": "execve", "source": _guardian_command_source(getattr(action, "source", None)), "program": getattr(action, "program", None), "argv": list(getattr(action, "argv", ())), "cwd": str(getattr(action, "cwd", ""))}
    if action_type == "apply_patch":
        return {"type": "applyPatch", "cwd": str(getattr(action, "cwd", "")), "files": [str(file) for file in getattr(action, "files", ())]}
    if action_type == "network_access":
        protocol = getattr(action, "protocol", None)
        return {"type": "networkAccess", "target": getattr(action, "target", None), "host": getattr(action, "host", None), "protocol": getattr(protocol, "value", protocol), "port": getattr(action, "port", None)}
    if action_type == "mcp_tool_call":
        return {"type": "mcpToolCall", "server": getattr(action, "server", None), "toolName": getattr(action, "tool_name", None), "connectorId": getattr(action, "connector_id", None), "connectorName": getattr(action, "connector_name", None), "toolTitle": getattr(action, "tool_title", None)}
    if action_type == "request_permissions":
        permissions = getattr(action, "permissions", None)
        return {"type": "requestPermissions", "reason": getattr(action, "reason", None), "permissions": permissions.to_mapping() if permissions is not None else None}
    raise ValueError(f"unknown guardian assessment action type: {action_type}")


def build_exec_stage_events(
    ctx: ToolEventCtx,
    exec_input: ExecCommandInput,
    stage: ToolEventStage,
    *,
    timestamp_ms: int | None = None,
) -> tuple[EventMsg, ...]:
    if stage.type == "begin":
        return (build_exec_command_begin_event(ctx, exec_input, started_at_ms=timestamp_ms),)
    result = exec_command_result_for_stage(stage, ctx.truncation_policy)
    if result is None:
        return ()
    return (build_exec_command_end_event(ctx, exec_input, result, completed_at_ms=timestamp_ms),)


def command_execution_notification_from_event_msg(
    thread_id: str,
    turn_id: str,
    msg: EventMsg,
) -> dict[str, JsonValue]:
    if not isinstance(msg, EventMsg):
        raise TypeError("msg must be EventMsg")

    if msg.type == "exec_command_begin" and isinstance(msg.payload, ExecCommandBeginEvent):
        return {
            "method": "item/started",
            "params": {
                "threadId": str(thread_id),
                "turnId": str(turn_id),
                "item": build_command_execution_begin_item(msg.payload).to_app_server_mapping(),
                "startedAtMs": msg.payload.started_at_ms,
            },
        }

    if msg.type == "exec_command_end" and isinstance(msg.payload, ExecCommandEndEvent):
        return {
            "method": "item/completed",
            "params": {
                "threadId": str(thread_id),
                "turnId": str(turn_id),
                "item": build_command_execution_end_item(msg.payload).to_app_server_mapping(),
                "completedAtMs": msg.payload.completed_at_ms,
            },
        }

    if msg.type == "exec_command_output_delta" and isinstance(msg.payload, ExecCommandOutputDeltaEvent):
        return {
            "method": "item/commandExecution/outputDelta",
            "params": {
                "threadId": str(thread_id),
                "turnId": str(turn_id),
                "itemId": msg.payload.call_id,
                "delta": msg.payload.chunk.decode("utf-8", errors="replace"),
            },
        }

    raise ValueError(f"unsupported command execution event: {msg.type}")


def turn_item_lifecycle_notification(
    thread_id: str,
    turn_id: str,
    item: TurnItem,
    *,
    timestamp_ms: int | None = None,
) -> dict[str, JsonValue]:
    if not isinstance(item, TurnItem):
        raise TypeError("item must be a TurnItem")
    timestamp = now_unix_timestamp_ms() if timestamp_ms is None else _int_ms(timestamp_ms)
    params: dict[str, JsonValue] = {
        "threadId": str(thread_id),
        "turnId": str(turn_id),
        "item": item.to_app_server_mapping(),
    }
    if _turn_item_is_in_progress(item):
        params["startedAtMs"] = timestamp
        return {"method": "item/started", "params": params}
    params["completedAtMs"] = timestamp
    return {"method": "item/completed", "params": params}


def file_change_notification_from_turn_item(
    thread_id: str,
    turn_id: str,
    item: TurnItem,
    *,
    timestamp_ms: int | None = None,
) -> dict[str, JsonValue]:
    if not isinstance(item, TurnItem):
        raise TypeError("item must be a TurnItem")
    if item.type != "FileChange" or not isinstance(item.item, FileChangeItem):
        raise TypeError("item must be a FileChange TurnItem")
    return turn_item_lifecycle_notification(thread_id, turn_id, item, timestamp_ms=timestamp_ms)


@dataclass(frozen=True)
class PatchEndResult:
    completed_item: TurnItem
    turn_diff_event: EventMsg | None = None


def build_patch_begin_item(
    ctx: ToolEventCtx,
    changes: Mapping[str | Path, FileChange],
    auto_approved: bool,
) -> TurnItem:
    if not isinstance(ctx, ToolEventCtx):
        raise TypeError("ctx must be ToolEventCtx")
    if not isinstance(auto_approved, bool):
        raise TypeError("auto_approved must be a bool")
    return TurnItem.file_change(
        FileChangeItem(
            id=ctx.call_id,
            changes=_normalize_changes(changes),
            status=None,
            auto_approved=auto_approved,
            stdout=None,
            stderr=None,
        )
    )


def patch_status_for_output(output: ExecToolCallOutput) -> PatchApplyStatus:
    if not isinstance(output, ExecToolCallOutput):
        raise TypeError("output must be ExecToolCallOutput")
    return PatchApplyStatus.COMPLETED if output.exit_code == 0 else PatchApplyStatus.FAILED


def patch_status_for_failure(failure: ToolEventFailure) -> PatchApplyStatus:
    if not isinstance(failure, ToolEventFailure):
        raise TypeError("failure must be ToolEventFailure")
    if failure.type == "rejected":
        return PatchApplyStatus.DECLINED
    if failure.type == "output" and failure.output is not None:
        return patch_status_for_output(failure.output)
    return PatchApplyStatus.FAILED


def build_patch_end(
    ctx: ToolEventCtx,
    changes: Mapping[str | Path, FileChange],
    stdout: str,
    stderr: str,
    status: PatchApplyStatus,
    tracker_update: TurnDiffTrackerUpdate,
) -> PatchEndResult:
    if not isinstance(ctx, ToolEventCtx):
        raise TypeError("ctx must be ToolEventCtx")
    if not isinstance(stdout, str) or not isinstance(stderr, str):
        raise TypeError("stdout and stderr must be strings")
    if not isinstance(status, PatchApplyStatus):
        status = PatchApplyStatus(status)
    if not isinstance(tracker_update, TurnDiffTrackerUpdate):
        raise TypeError("tracker_update must be TurnDiffTrackerUpdate")
    completed_item = TurnItem.file_change(
        FileChangeItem(
            id=ctx.call_id,
            changes=_normalize_changes(changes),
            status=status,
            auto_approved=None,
            stdout=stdout,
            stderr=stderr,
        )
    )
    return PatchEndResult(completed_item, apply_turn_diff_tracker_update(ctx.turn_diff_tracker, tracker_update))


def build_patch_end_for_stage(
    ctx: ToolEventCtx,
    changes: Mapping[str | Path, FileChange],
    stage: ToolEventStage,
) -> PatchEndResult | TurnItem:
    if stage.type == "begin":
        return build_patch_begin_item(ctx, changes, auto_approved=False)
    if stage.type == "success" and stage.output is not None:
        tracker_update = (
            tracker_update_for_known_delta(stage.applied_patch_delta)
            if stage.applied_patch_delta is not None
            else TurnDiffTrackerUpdate.invalidate()
        )
        return build_patch_end(
            ctx,
            changes,
            stage.output.stdout.text,
            stage.output.stderr.text,
            patch_status_for_output(stage.output),
            tracker_update,
        )
    failure = stage.failure
    if failure is None:
        raise TypeError("failure stage requires failure")
    if failure.type == "output" and failure.output is not None:
        return build_patch_end(
            ctx,
            changes,
            failure.output.stdout.text,
            failure.output.stderr.text,
            patch_status_for_output(failure.output),
            TurnDiffTrackerUpdate.invalidate(),
        )
    if failure.type == "message" and failure.message is not None:
        return build_patch_end(ctx, changes, "", failure.message, PatchApplyStatus.FAILED, TurnDiffTrackerUpdate.none())
    if failure.type == "rejected" and failure.message is not None:
        tracker_update = (
            tracker_update_for_known_delta(failure.applied_patch_delta)
            if failure.applied_patch_delta is not None
            else TurnDiffTrackerUpdate.none()
        )
        return build_patch_end(ctx, changes, "", failure.message, PatchApplyStatus.DECLINED, tracker_update)
    raise TypeError("invalid patch stage")


def apply_turn_diff_tracker_update(
    tracker: TurnDiffTracker | None,
    update: TurnDiffTrackerUpdate,
) -> EventMsg | None:
    if tracker is None:
        return None
    if not isinstance(tracker, TurnDiffTracker):
        raise TypeError("tracker must be TurnDiffTracker or None")
    if not isinstance(update, TurnDiffTrackerUpdate):
        raise TypeError("update must be TurnDiffTrackerUpdate")
    previous_diff = tracker.get_unified_diff()
    tracker_changed = False
    if update.type == "track" and update.delta is not None:
        tracker.track_delta(update.delta)
        tracker_changed = True
    elif update.type == "invalidate":
        tracker.invalidate()
        tracker_changed = True
    unified_diff = tracker.get_unified_diff() or ""
    if tracker_changed and (previous_diff is not None or unified_diff):
        return EventMsg.with_payload("turn_diff", TurnDiffEvent(unified_diff))
    return None


@dataclass(frozen=True)
class ToolEmitter:
    type: str
    command: tuple[str, ...] = ()
    cwd: Path | None = None
    source: ExecCommandSource = ExecCommandSource.AGENT
    parsed_cmd: tuple[JsonValue, ...] = ()
    changes: dict[Path, FileChange] | None = None
    auto_approved: bool = False
    process_id: str | None = None

    @classmethod
    def shell(
        cls,
        command: tuple[str, ...] | list[str],
        cwd: str | Path,
        source: ExecCommandSource = ExecCommandSource.AGENT,
        parsed_cmd: tuple[JsonValue, ...] | list[JsonValue] | None = None,
    ) -> "ToolEmitter":
        command_tuple = tuple(command)
        return cls(
            "shell",
            command_tuple,
            Path(cwd),
            source,
            tuple(parse_command(command_tuple) if parsed_cmd is None else parsed_cmd),
        )

    @classmethod
    def apply_patch(cls, changes: Mapping[str | Path, FileChange], auto_approved: bool) -> "ToolEmitter":
        return cls("apply_patch", changes=_normalize_changes(changes), auto_approved=auto_approved)

    @classmethod
    def unified_exec(
        cls,
        command: tuple[str, ...] | list[str],
        cwd: str | Path,
        source: ExecCommandSource = ExecCommandSource.AGENT,
        process_id: str | None = None,
        parsed_cmd: tuple[JsonValue, ...] | list[JsonValue] | None = None,
    ) -> "ToolEmitter":
        command_tuple = tuple(command)
        return cls(
            "unified_exec",
            command_tuple,
            Path(cwd),
            source,
            tuple(parse_command(command_tuple) if parsed_cmd is None else parsed_cmd),
            process_id=process_id,
        )

    def __post_init__(self) -> None:
        if self.type in ("shell", "unified_exec"):
            object.__setattr__(self, "command", _string_tuple(self.command, "command"))
            if self.cwd is None:
                raise TypeError("cwd is required for exec emitters")
            if not isinstance(self.cwd, Path):
                object.__setattr__(self, "cwd", Path(self.cwd))
            if not isinstance(self.source, ExecCommandSource):
                object.__setattr__(self, "source", ExecCommandSource(self.source))
            if not isinstance(self.parsed_cmd, tuple):
                object.__setattr__(self, "parsed_cmd", tuple(self.parsed_cmd))
            if self.process_id is not None and not isinstance(self.process_id, str):
                raise TypeError("process_id must be a string or None")
        elif self.type == "apply_patch":
            object.__setattr__(self, "changes", _normalize_changes(self.changes or {}))
            if not isinstance(self.auto_approved, bool):
                raise TypeError("auto_approved must be a bool")
        else:
            raise ValueError(f"unsupported tool emitter type: {self.type}")

    def exec_input(self) -> ExecCommandInput:
        if self.type not in ("shell", "unified_exec") or self.cwd is None:
            raise TypeError("exec_input is only available for exec emitters")
        return ExecCommandInput(
            self.command,
            self.cwd,
            self.parsed_cmd,
            self.source,
            None,
            self.process_id if self.type == "unified_exec" else None,
        )

    def emit(self, ctx: ToolEventCtx, stage: ToolEventStage) -> tuple[EventMsg | TurnItem, ...]:
        if self.type in ("shell", "unified_exec"):
            return build_exec_stage_events(ctx, self.exec_input(), stage)
        if self.type == "apply_patch":
            if stage.type == "begin":
                return (build_patch_begin_item(ctx, self.changes or {}, self.auto_approved),)
            result = build_patch_end_for_stage(ctx, self.changes or {}, stage)
            if isinstance(result, PatchEndResult):
                items: list[EventMsg | TurnItem] = [result.completed_item]
                if result.turn_diff_event is not None:
                    items.append(result.turn_diff_event)
                return tuple(items)
            return (result,)
        raise ValueError(f"unsupported tool emitter type: {self.type}")

    async def emit_to_session(self, ctx: ToolEventCtx, stage: ToolEventStage) -> None:
        for item in self.emit(ctx, stage):
            await _send_emitted_item(ctx, item)

    async def begin(self, ctx: ToolEventCtx) -> None:
        await self.emit_to_session(ctx, ToolEventStage.begin())

    def finish(
        self,
        ctx: ToolEventCtx,
        out: ExecToolCallOutput | ToolEventFailure | ToolError,
        applied_patch_delta: AppliedPatchDelta | None = None,
    ) -> tuple[str | FunctionCallError, tuple[EventMsg | TurnItem, ...]]:
        result, stage = self._finish_result_and_stage(ctx, out, applied_patch_delta)
        return result, self.emit(ctx, stage)

    async def finish_and_emit(
        self,
        ctx: ToolEventCtx,
        out: ExecToolCallOutput | ToolEventFailure | ToolError,
        applied_patch_delta: AppliedPatchDelta | None = None,
    ) -> str | FunctionCallError:
        result, stage = self._finish_result_and_stage(ctx, out, applied_patch_delta)
        await self.emit_to_session(ctx, stage)
        return result

    def _finish_result_and_stage(
        self,
        ctx: ToolEventCtx,
        out: ExecToolCallOutput | ToolEventFailure | ToolError,
        applied_patch_delta: AppliedPatchDelta | None,
    ) -> tuple[str | FunctionCallError, ToolEventStage]:
        if isinstance(out, ExecToolCallOutput):
            content = format_exec_output_for_model(out, ctx.truncation_policy)
            result: str | FunctionCallError = content
            if out.exit_code != 0:
                result = FunctionCallError.respond_to_model(content)
            return result, ToolEventStage.success(out, applied_patch_delta)

        if isinstance(out, ToolError):
            converted = self._stage_for_tool_error(ctx, out, applied_patch_delta)
            return converted

        if isinstance(out, ToolEventFailure):
            failure = _normalize_rejection_failure(self.type, out, applied_patch_delta)
            message = (
                failure.message
                if failure.message is not None
                else format_exec_output_for_model(failure.output, ctx.truncation_policy)
            )
            return FunctionCallError.respond_to_model(message), ToolEventStage.failure(failure)

        raise TypeError("out must be ExecToolCallOutput, ToolEventFailure, or ToolError")

    def _stage_for_tool_error(
        self,
        ctx: ToolEventCtx,
        error: ToolError,
        applied_patch_delta: AppliedPatchDelta | None,
    ) -> tuple[str | FunctionCallError, ToolEventStage]:
        if error.type == "rejected":
            failure = _normalize_rejection_failure(
                self.type,
                ToolEventFailure.rejected(error.message or ""),
                applied_patch_delta,
            )
            return FunctionCallError.respond_to_model(failure.message or ""), ToolEventStage.failure(failure)

        if error.type != "codex":
            raise ValueError(f"unsupported tool error type: {error.type}")

        sandbox_kind, output = _sandbox_error_output(error.error)
        if sandbox_kind in {"timeout", "denied"} and output is not None:
            response = format_exec_output_for_model(output, ctx.truncation_policy)
            if self.type == "apply_patch" and sandbox_kind == "denied" and applied_patch_delta is not None:
                return (
                    FunctionCallError.respond_to_model(response),
                    ToolEventStage.success(output, applied_patch_delta),
                )
            return (
                FunctionCallError.respond_to_model(response),
                ToolEventStage.failure(ToolEventFailure.output_failure(output)),
            )

        message = f"execution error: {error.error!r}"
        return (
            FunctionCallError.respond_to_model(message),
            ToolEventStage.failure(ToolEventFailure.message_failure(message)),
        )


def _ensure_ctx_and_input(ctx: ToolEventCtx, exec_input: ExecCommandInput) -> None:
    if not isinstance(ctx, ToolEventCtx):
        raise TypeError("ctx must be ToolEventCtx")
    if not isinstance(exec_input, ExecCommandInput):
        raise TypeError("exec_input must be ExecCommandInput")


async def _send_emitted_item(ctx: ToolEventCtx, item: EventMsg | TurnItem) -> None:
    if isinstance(item, EventMsg):
        sender = getattr(ctx.session, "send_event", None)
        if not callable(sender):
            raise TypeError("session must expose send_event(turn, event) for EventMsg delivery")
        await _maybe_await(sender(ctx.turn, item))
        return

    if not isinstance(item, TurnItem):
        raise TypeError("emitted item must be EventMsg or TurnItem")
    if _turn_item_is_in_progress(item):
        sender = getattr(ctx.session, "emit_turn_item_started", None)
        if not callable(sender):
            raise TypeError("session must expose emit_turn_item_started(turn, item)")
        await _maybe_await(sender(ctx.turn, item))
        return
    sender = getattr(ctx.session, "emit_turn_item_completed", None)
    if not callable(sender):
        raise TypeError("session must expose emit_turn_item_completed(turn, item)")
    await _maybe_await(sender(ctx.turn, item))


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _normalize_rejection_failure(
    emitter_type: str,
    failure: ToolEventFailure,
    applied_patch_delta: AppliedPatchDelta | None,
) -> ToolEventFailure:
    if failure.type != "rejected" or failure.message != "rejected by user":
        return failure
    normalized = "patch rejected by user" if emitter_type == "apply_patch" else "exec command rejected by user"
    return ToolEventFailure.rejected(normalized, applied_patch_delta)


def _sandbox_error_output(error: Any) -> tuple[str | None, ExecToolCallOutput | None]:
    if isinstance(error, Mapping):
        sandbox_kind = error.get("sandbox")
        output = error.get("output")
    else:
        sandbox_kind = getattr(error, "sandbox", None)
        output = getattr(error, "output", None)
    if sandbox_kind not in {"timeout", "denied"}:
        return None, None
    if not isinstance(output, ExecToolCallOutput):
        raise TypeError("sandbox tool error output must be ExecToolCallOutput")
    return sandbox_kind, output


def _int_ms(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("timestamp must be an int")
    if value < 0:
        raise ValueError("timestamp must be non-negative")
    return value


def _string_tuple(value: tuple[str, ...] | list[str], field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise TypeError(f"{field_name} must be a tuple or list")
    result = tuple(value)
    for item in result:
        if not isinstance(item, str):
            raise TypeError(f"{field_name} items must be strings")
    return result


def _normalize_changes(changes: Mapping[str | Path, FileChange]) -> dict[Path, FileChange]:
    if not isinstance(changes, Mapping):
        raise TypeError("changes must be a mapping")
    result: dict[Path, FileChange] = {}
    for path, change in changes.items():
        if not isinstance(path, (str, Path)):
            raise TypeError("changes keys must be strings or Path")
        if not isinstance(change, FileChange):
            raise TypeError("changes values must be FileChange")
        result[Path(path)] = change
    return result


def _command_execution_source(source: ExecCommandSource) -> str:
    if not isinstance(source, ExecCommandSource):
        source = ExecCommandSource(source)
    aliases = {
        ExecCommandSource.AGENT: "agent",
        ExecCommandSource.USER_SHELL: "userShell",
        ExecCommandSource.UNIFIED_EXEC_STARTUP: "unifiedExecStartup",
        ExecCommandSource.UNIFIED_EXEC_INTERACTION: "unifiedExecInteraction",
    }
    return aliases[source]


def _command_execution_status(status: ExecCommandStatus) -> str:
    if not isinstance(status, ExecCommandStatus):
        status = ExecCommandStatus(status)
    return status.value


def _command_execution_notification_item_mapping(item: TurnItem) -> dict[str, JsonValue]:
    if item.type != "CommandExecution" or not isinstance(item.item, CommandExecutionItem):
        raise TypeError("item must be a CommandExecution TurnItem")
    return item.to_app_server_mapping()


def _turn_item_is_in_progress(item: TurnItem) -> bool:
    if item.type == "CommandExecution" and isinstance(item.item, CommandExecutionItem):
        return item.item.status == "inProgress"
    if item.type == "FileChange" and isinstance(item.item, FileChangeItem):
        return item.item.status is None
    raise ValueError(f"app-server lifecycle notification is not implemented for {item.type}")


def _command_actions_from_parsed_commands(parsed_cmd: tuple[JsonValue, ...], cwd: Path) -> tuple[dict[str, JsonValue], ...]:
    return tuple(_command_action_from_parsed(_parsed_command(command), cwd) for command in parsed_cmd)


def command_actions_from_argv(command: tuple[str, ...] | list[str], cwd: Path) -> tuple[dict[str, JsonValue], ...]:
    """Return app-server command actions for a shell argv using Rust's parse-command path."""

    parsed_cmd = parse_command(command)
    if not parsed_cmd:
        return ({"type": "unknown", "command": shlex.join(tuple(command))},)
    return _command_actions_from_parsed_commands(tuple(parsed_cmd), cwd)


def _parsed_command(value: JsonValue) -> ParsedCommand:
    if isinstance(value, ParsedCommand):
        return value
    if isinstance(value, Mapping):
        return ParsedCommand.from_mapping(value)
    raise TypeError("parsed command must be ParsedCommand or mapping")


def _command_action_from_parsed(parsed: ParsedCommand, cwd: Path) -> dict[str, JsonValue]:
    if not isinstance(parsed, ParsedCommand):
        raise TypeError("parsed must be ParsedCommand")
    if parsed.type == "read":
        return {
            "type": "read",
            "command": parsed.cmd,
            "name": parsed.name or "",
            "path": str(Path(cwd) / Path(parsed.path or "")),
        }
    if parsed.type == "list_files":
        return {"type": "listFiles", "command": parsed.cmd, "path": parsed.path}
    if parsed.type == "search":
        return {"type": "search", "command": parsed.cmd, "query": parsed.query, "path": parsed.path}
    if parsed.type == "unknown":
        return {"type": "unknown", "command": parsed.cmd}
    raise ValueError(f"unknown parsed command type: {parsed.type}")


def _duration_ms(duration: Any) -> int:
    if isinstance(duration, timedelta):
        return max(0, int(duration.total_seconds() * 1000))
    if isinstance(duration, Mapping):
        secs = duration.get("secs", 0)
        nanos = duration.get("nanos", 0)
        return max(0, int(secs) * 1000 + int(nanos) // 1_000_000)
    if isinstance(duration, (int, float)) and not isinstance(duration, bool):
        return max(0, int(duration))
    raise TypeError("duration must be timedelta, mapping, or number")


__all__ = [
    "ExecCommandInput",
    "ExecCommandResult",
    "PatchEndResult",
    "ToolEmitter",
    "ToolEventCtx",
    "ToolEventFailure",
    "ToolEventStage",
    "TurnDiffTrackerUpdate",
    "apply_turn_diff_tracker_update",
    "build_command_execution_begin_item",
    "build_command_execution_end_item",
    "build_command_execution_item_from_guardian_event",
    "build_command_execution_item_mapping_from_guardian_event",
    "command_actions_from_argv",
    "build_exec_command_begin_event",
    "build_exec_command_end_event",
    "build_exec_stage_events",
    "build_patch_begin_item",
    "build_patch_end",
    "build_patch_end_for_stage",
    "command_execution_notification_from_event_msg",
    "command_execution_status_from_guardian_status",
    "exec_command_result_for_stage",
    "exec_command_result_from_message",
    "exec_command_result_from_output",
    "file_change_notification_from_turn_item",
    "guardian_auto_approval_review_notification",
    "now_unix_timestamp_ms",
    "patch_status_for_failure",
    "patch_status_for_output",
    "tracker_update_for_known_delta",
    "turn_item_lifecycle_notification",
]
