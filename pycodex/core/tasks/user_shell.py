"""User shell task aligned with ``codex-core::tasks::user_shell``."""

from __future__ import annotations

import asyncio
import inspect
import sys
import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.core.exec import ExecCapturePolicy, ExecExpiration, ExecRequest
from pycodex.core.exec_env import create_env
from pycodex.core.sandboxing import execute_env
from pycodex.core.shell import default_user_shell
from pycodex.core.state import TaskKind
from pycodex.core.tools.runtimes import maybe_wrap_shell_lc_with_snapshot
from pycodex.core.turn_timing import now_unix_timestamp_ms
from pycodex.core.user_shell_command import (
    env_for_user_shell_command,
    format_exec_output_str,
    user_shell_command_record_item,
)
from pycodex.protocol import (
    EventMsg,
    ExecCommandBeginEvent,
    ExecCommandEndEvent,
    ExecCommandOutputDeltaEvent,
    ExecCommandSource,
    ExecCommandStatus,
    ExecOutputStream,
    ExecToolCallOutput,
    PermissionProfile,
    StreamOutput,
    TurnStartedEvent,
)
from pycodex.sandboxing import SandboxType
from pycodex.shell_command.parse_command import parse_command


USER_SHELL_TIMEOUT_MS = 60 * 60 * 1000


class UserShellCommandMode(str, Enum):
    STANDALONE_TURN = "standalone_turn"
    ACTIVE_TURN_AUXILIARY = "active_turn_auxiliary"


@dataclass(frozen=True)
class UserShellCommandTask:
    command: str

    @classmethod
    def new(cls, command: str) -> "UserShellCommandTask":
        return cls(command)

    def kind(self) -> TaskKind:
        return TaskKind.REGULAR

    def span_name(self) -> str:
        return "session_task.user_shell"

    async def run(
        self,
        session_context: Any,
        turn_context: Any,
        _input: list[Any],
        cancellation_token: Any,
    ) -> None:
        clone_session = getattr(session_context, "clone_session", None)
        session = clone_session() if callable(clone_session) else getattr(session_context, "session", session_context)
        await execute_user_shell_command(
            session,
            turn_context,
            self.command,
            cancellation_token,
            UserShellCommandMode.STANDALONE_TURN,
        )
        return None


async def execute_user_shell_command(
    session: Any,
    turn_context: Any,
    command: str,
    cancellation_token: Any,
    mode: UserShellCommandMode | str,
) -> None:
    mode = UserShellCommandMode(mode)
    _emit_metric(session)

    if mode is UserShellCommandMode.STANDALONE_TURN:
        await _send_event(
            session,
            turn_context,
            EventMsg.with_payload(
                "task_started",
                TurnStartedEvent(
                    turn_id=str(_field(turn_context, "sub_id", "")),
                    trace_id=_field(turn_context, "trace_id"),
                    started_at=await _started_at(turn_context),
                    model_context_window=_model_context_window(turn_context),
                    collaboration_mode_kind=_collaboration_mode_kind(turn_context),
                ),
            ),
        )

    session_shell = _user_shell(session)
    display_command = tuple(session_shell.derive_exec_args(command, True))
    env = create_env(
        _field(turn_context, "shell_environment_policy"),
        _field(session, "conversation_id"),
    )
    env = env_for_user_shell_command(env)
    cwd = Path(_field(turn_context, "cwd"))
    exec_command = maybe_wrap_shell_lc_with_snapshot(
        display_command,
        session_shell,
        cwd,
        _shell_environment_overrides(turn_context),
        env,
        is_windows=sys.platform == "win32",
    )

    call_id = str(uuid.uuid4())
    parsed_cmd = tuple(_parsed_command_mapping(item) for item in parse_command(display_command))
    await _send_event(
        session,
        turn_context,
        EventMsg.with_payload(
            "exec_command_begin",
            ExecCommandBeginEvent(
                call_id=call_id,
                process_id=None,
                turn_id=str(_field(turn_context, "sub_id", "")),
                started_at_ms=now_unix_timestamp_ms(),
                command=display_command,
                cwd=cwd,
                parsed_cmd=parsed_cmd,
                source=ExecCommandSource.USER_SHELL,
                interaction_input=None,
            ),
        ),
    )

    permission_profile = PermissionProfile.disabled()
    request = ExecRequest(
        command=tuple(exec_command),
        cwd=cwd,
        env=env,
        exec_server_env_config=None,
        network=None,
        expiration=ExecExpiration.timeout_after(timedelta(milliseconds=USER_SHELL_TIMEOUT_MS)),
        capture_policy=ExecCapturePolicy.SHELL_TOOL,
        sandbox=SandboxType.NONE,
        windows_sandbox_policy_cwd=cwd,
        windows_sandbox_level=_field(turn_context, "windows_sandbox_level", "disabled"),
        windows_sandbox_private_desktop=_windows_private_desktop(turn_context),
        permission_profile=permission_profile,
        file_system_sandbox_policy=permission_profile.file_system_sandbox_policy(),
        network_sandbox_policy=permission_profile.network_sandbox_policy(),
        windows_sandbox_filesystem_overrides=None,
        arg0=None,
    )

    try:
        output = await _execute_or_cancel(
            request,
            _stdout_stream(session, turn_context, call_id),
            cancellation_token,
        )
    except _CommandCancelled:
        output = _failed_output("command aborted by user")
        await persist_user_shell_output(session, turn_context, command, output, mode)
        await _send_exec_end(session, turn_context, call_id, display_command, cwd, parsed_cmd, output)
        return
    except Exception as exc:  # noqa: BLE001 - Rust reports execution errors as failed command output.
        output = _failed_output(f"execution error: {exc!r}")

    await _send_exec_end(session, turn_context, call_id, display_command, cwd, parsed_cmd, output)
    await persist_user_shell_output(session, turn_context, command, output, mode)


async def persist_user_shell_output(
    session: Any,
    turn_context: Any,
    raw_command: str,
    exec_output: ExecToolCallOutput,
    mode: UserShellCommandMode | str,
) -> None:
    mode = UserShellCommandMode(mode)
    output_item = user_shell_command_record_item(
        raw_command,
        exec_output,
        _field(turn_context, "truncation_policy"),
    )
    if mode is UserShellCommandMode.STANDALONE_TURN:
        await _maybe_await(session.record_conversation_items(turn_context, (output_item,)))
        await _maybe_await(session.ensure_rollout_materialized())
        return
    await _maybe_await(session.inject_no_new_turn([output_item], turn_context))


class _CommandCancelled(Exception):
    pass


async def _execute_or_cancel(request: ExecRequest, stdout_stream: Any, cancellation_token: Any) -> ExecToolCallOutput:
    execute_task = asyncio.create_task(execute_env(request, stdout_stream))
    cancelled = getattr(cancellation_token, "cancelled", None)
    if not callable(cancelled):
        return await execute_task
    cancel_task = asyncio.create_task(cancelled())
    try:
        done, _pending = await asyncio.wait(
            (execute_task, cancel_task),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if cancel_task in done and execute_task not in done:
            execute_task.cancel()
            with suppress(asyncio.CancelledError):
                await execute_task
            raise _CommandCancelled
        return await execute_task
    finally:
        if not cancel_task.done():
            cancel_task.cancel()
        with suppress(asyncio.CancelledError):
            await cancel_task


async def _send_exec_end(
    session: Any,
    turn_context: Any,
    call_id: str,
    display_command: tuple[str, ...],
    cwd: Path,
    parsed_cmd: tuple[Any, ...],
    output: ExecToolCallOutput,
) -> None:
    await _send_event(
        session,
        turn_context,
        EventMsg.with_payload(
            "exec_command_end",
            ExecCommandEndEvent(
                call_id=call_id,
                process_id=None,
                turn_id=str(_field(turn_context, "sub_id", "")),
                completed_at_ms=now_unix_timestamp_ms(),
                command=display_command,
                cwd=cwd,
                parsed_cmd=parsed_cmd,
                source=ExecCommandSource.USER_SHELL,
                interaction_input=None,
                stdout=output.stdout.text,
                stderr=output.stderr.text,
                aggregated_output=output.aggregated_output.text,
                exit_code=output.exit_code,
                duration=output.duration,
                formatted_output=format_exec_output_str(output, _field(turn_context, "truncation_policy")),
                status=ExecCommandStatus.COMPLETED if output.exit_code == 0 else ExecCommandStatus.FAILED,
            ),
        ),
    )


def _stdout_stream(session: Any, turn_context: Any, call_id: str) -> Any:
    async def stream(data: bytes | str, is_stderr: bool) -> None:
        chunk = data if isinstance(data, bytes) else data.encode("utf-8", errors="replace")
        await _send_event(
            session,
            turn_context,
            EventMsg.with_payload(
                "exec_command_output_delta",
                ExecCommandOutputDeltaEvent(
                    call_id=call_id,
                    stream=ExecOutputStream.STDERR if is_stderr else ExecOutputStream.STDOUT,
                    chunk=chunk,
                ),
            ),
        )

    return stream


def _failed_output(message: str) -> ExecToolCallOutput:
    return ExecToolCallOutput(
        exit_code=-1,
        stdout=StreamOutput.new(""),
        stderr=StreamOutput.new(message),
        aggregated_output=StreamOutput.new(message),
        duration=timedelta(0),
        timed_out=False,
    )


def _emit_metric(session: Any) -> None:
    telemetry = _field(_field(session, "services"), "session_telemetry")
    counter = getattr(telemetry, "counter", None)
    if callable(counter):
        counter("codex.task.user_shell", 1, [])


def _user_shell(session: Any) -> Any:
    getter = getattr(session, "user_shell", None)
    if callable(getter):
        return getter()
    shell = _field(_field(session, "services"), "user_shell")
    return shell if shell is not None else default_user_shell()


def _shell_environment_overrides(turn_context: Any) -> dict[str, str]:
    policy = _field(turn_context, "shell_environment_policy")
    values = _field(policy, "set", {})
    return dict(values or {})


def _windows_private_desktop(turn_context: Any) -> bool:
    permissions = _field(_field(turn_context, "config"), "permissions")
    return bool(_field(permissions, "windows_sandbox_private_desktop", False))


async def _started_at(turn_context: Any) -> int | None:
    getter = getattr(_field(turn_context, "turn_timing_state"), "started_at_unix_secs", None)
    return await _maybe_await(getter()) if callable(getter) else _field(turn_context, "started_at")


def _model_context_window(turn_context: Any) -> int | None:
    getter = getattr(turn_context, "model_context_window", None)
    return getter() if callable(getter) else _field(turn_context, "model_context_window_value")


def _collaboration_mode_kind(turn_context: Any) -> Any:
    mode = _field(_field(turn_context, "collaboration_mode"), "mode", "default")
    return getattr(mode, "value", mode)


def _parsed_command_mapping(item: Any) -> Any:
    to_mapping = getattr(item, "to_mapping", None)
    return to_mapping() if callable(to_mapping) else item


async def _send_event(session: Any, turn_context: Any, event: EventMsg) -> None:
    await _maybe_await(session.send_event(turn_context, event))


def _field(value: Any, name: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "USER_SHELL_TIMEOUT_MS",
    "UserShellCommandMode",
    "UserShellCommandTask",
    "execute_user_shell_command",
    "persist_user_shell_output",
]
