"""Pure tool event helpers ported from ``core/src/tools/events.rs``.

The Rust module also performs async session emission. This Python slice keeps
the same event-shaping and state-transition rules while leaving the concrete
session/runtime delivery as an injected boundary.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Mapping

from pycodex.core.function_tool import FunctionCallError
from pycodex.core.turn_diff_tracker import AppliedPatchDelta, TurnDiffTracker
from pycodex.core.user_shell_command import format_exec_output_str
from pycodex.protocol import (
    EventMsg,
    ExecCommandBeginEvent,
    ExecCommandEndEvent,
    ExecCommandSource,
    ExecCommandStatus,
    ExecToolCallOutput,
    FileChange,
    FileChangeItem,
    PatchApplyStatus,
    TruncationPolicyConfig,
    TurnDiffEvent,
    TurnItem,
)

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


@dataclass(frozen=True)
class ToolEventStage:
    type: str
    output: ExecToolCallOutput | None = None
    applied_patch_delta: AppliedPatchDelta | None = None
    failure: ToolEventFailure | None = None

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
        parsed_cmd: tuple[JsonValue, ...] | list[JsonValue] = (),
    ) -> "ToolEmitter":
        return cls("shell", tuple(command), Path(cwd), source, tuple(parsed_cmd))

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
        parsed_cmd: tuple[JsonValue, ...] | list[JsonValue] = (),
    ) -> "ToolEmitter":
        return cls("unified_exec", tuple(command), Path(cwd), source, tuple(parsed_cmd), process_id=process_id)

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

    def finish(
        self,
        ctx: ToolEventCtx,
        out: ExecToolCallOutput | ToolEventFailure,
        applied_patch_delta: AppliedPatchDelta | None = None,
    ) -> tuple[str | FunctionCallError, tuple[EventMsg | TurnItem, ...]]:
        if isinstance(out, ExecToolCallOutput):
            stage = ToolEventStage.success(out, applied_patch_delta)
            result: str | FunctionCallError = format_exec_output_str(out, ctx.truncation_policy)
            if out.exit_code != 0:
                result = FunctionCallError.respond_to_model(result)
        elif isinstance(out, ToolEventFailure):
            failure = out
            if failure.type == "rejected" and failure.message == "rejected by user":
                normalized = "patch rejected by user" if self.type == "apply_patch" else "exec command rejected by user"
                failure = ToolEventFailure.rejected(normalized, applied_patch_delta)
            stage = ToolEventStage.failure(failure)
            message = failure.message if failure.message is not None else format_exec_output_str(failure.output, ctx.truncation_policy)
            result = FunctionCallError.respond_to_model(message)
        else:
            raise TypeError("out must be ExecToolCallOutput or ToolEventFailure")
        return result, self.emit(ctx, stage)


def _ensure_ctx_and_input(ctx: ToolEventCtx, exec_input: ExecCommandInput) -> None:
    if not isinstance(ctx, ToolEventCtx):
        raise TypeError("ctx must be ToolEventCtx")
    if not isinstance(exec_input, ExecCommandInput):
        raise TypeError("exec_input must be ExecCommandInput")


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
    "build_exec_command_begin_event",
    "build_exec_command_end_event",
    "build_exec_stage_events",
    "build_patch_begin_item",
    "build_patch_end",
    "build_patch_end_for_stage",
    "exec_command_result_for_stage",
    "exec_command_result_from_message",
    "exec_command_result_from_output",
    "now_unix_timestamp_ms",
    "patch_status_for_failure",
    "patch_status_for_output",
    "tracker_update_for_known_delta",
]
