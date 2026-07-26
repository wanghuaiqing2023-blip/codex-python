from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from pycodex.core.codex_delegate import CancellationToken
from pycodex.core.exec import ExecExpirationKind
from pycodex.core.state import TaskKind
from pycodex.core.tasks.user_shell import (
    UserShellCommandMode,
    UserShellCommandTask,
    execute_user_shell_command,
)
from pycodex.protocol import (
    ExecCommandSource,
    ExecCommandStatus,
    ExecToolCallOutput,
    StreamOutput,
    TruncationPolicyConfig,
)
from pycodex.sandboxing import SandboxType


class _Shell:
    def derive_exec_args(self, command: str, use_login_shell: bool) -> list[str]:
        assert use_login_shell is True
        return ["test-shell", "-lc", command]


class _Telemetry:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, list[object]]] = []

    def counter(self, name: str, increment: int, tags: list[object]) -> None:
        self.calls.append((name, increment, tags))


class _Session:
    def __init__(self) -> None:
        self.events: list[object] = []
        self.recorded: list[tuple[object, tuple[object, ...]]] = []
        self.injected: list[tuple[list[object], object]] = []
        self.materialized = 0
        self.services = SimpleNamespace(session_telemetry=_Telemetry(), user_shell=_Shell())
        self.conversation_id = None

    def user_shell(self) -> _Shell:
        return self.services.user_shell

    async def send_event(self, turn_context: object, event: object) -> None:
        self.events.append(event)

    async def record_conversation_items(self, turn_context: object, items: tuple[object, ...]) -> None:
        self.recorded.append((turn_context, items))

    async def ensure_rollout_materialized(self) -> None:
        self.materialized += 1

    async def inject_no_new_turn(self, items: list[object], turn_context: object) -> None:
        self.injected.append((items, turn_context))


def _turn_context(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        sub_id="turn-1",
        trace_id="trace-1",
        cwd=tmp_path,
        shell_environment_policy=object(),
        windows_sandbox_level="disabled",
        config=SimpleNamespace(permissions=SimpleNamespace(windows_sandbox_private_desktop=False)),
        truncation_policy=TruncationPolicyConfig.bytes(4096),
        collaboration_mode=SimpleNamespace(mode="default"),
        model_context_window=lambda: 128_000,
        turn_timing_state=SimpleNamespace(started_at_unix_secs=AsyncMock(return_value=123)),
    )


def _output(text: str = "ok\n", exit_code: int = 0) -> ExecToolCallOutput:
    return ExecToolCallOutput(
        exit_code=exit_code,
        stdout=StreamOutput.new(text),
        stderr=StreamOutput.new(""),
        aggregated_output=StreamOutput.new(text),
        duration=timedelta(milliseconds=25),
        timed_out=False,
    )


def test_user_shell_task_identity_matches_rust_module() -> None:
    task = UserShellCommandTask.new("echo ok")

    assert task == UserShellCommandTask("echo ok")
    assert task.kind() is TaskKind.REGULAR
    assert task.span_name() == "session_task.user_shell"


@pytest.mark.asyncio
async def test_standalone_user_shell_emits_lifecycle_exec_events_and_persists(tmp_path: Path) -> None:
    session = _Session()
    turn_context = _turn_context(tmp_path)
    execute = AsyncMock(return_value=_output())

    with (
        patch("pycodex.core.tasks.user_shell.create_env", return_value={"PATH": "kept"}),
        patch(
            "pycodex.core.tasks.user_shell.maybe_wrap_shell_lc_with_snapshot",
            return_value=("test-shell", "-lc", "echo ok"),
        ),
        patch("pycodex.core.tasks.user_shell.execute_env", execute),
    ):
        await execute_user_shell_command(
            session,
            turn_context,
            "echo ok",
            CancellationToken(),
            UserShellCommandMode.STANDALONE_TURN,
        )

    assert [event.type for event in session.events] == [
        "task_started",
        "exec_command_begin",
        "exec_command_end",
    ]
    assert session.events[1].payload.source is ExecCommandSource.USER_SHELL
    assert session.events[2].payload.status is ExecCommandStatus.COMPLETED
    assert len(session.recorded) == 1
    assert session.materialized == 1
    assert session.injected == []
    request = execute.await_args.args[0]
    assert request.network is None
    assert request.permission_profile.type == "disabled"
    assert request.sandbox is SandboxType.NONE
    assert request.expiration.kind is ExecExpirationKind.TIMEOUT
    assert request.expiration.timeout == timedelta(hours=1)
    assert session.services.session_telemetry.calls == [("codex.task.user_shell", 1, [])]


@pytest.mark.asyncio
async def test_auxiliary_user_shell_uses_existing_turn_without_duplicate_lifecycle(tmp_path: Path) -> None:
    session = _Session()
    turn_context = _turn_context(tmp_path)

    with (
        patch("pycodex.core.tasks.user_shell.create_env", return_value={}),
        patch(
            "pycodex.core.tasks.user_shell.maybe_wrap_shell_lc_with_snapshot",
            return_value=("test-shell", "-lc", "echo ok"),
        ),
        patch("pycodex.core.tasks.user_shell.execute_env", AsyncMock(return_value=_output())),
    ):
        await execute_user_shell_command(
            session,
            turn_context,
            "echo ok",
            CancellationToken(),
            UserShellCommandMode.ACTIVE_TURN_AUXILIARY,
        )

    assert [event.type for event in session.events] == ["exec_command_begin", "exec_command_end"]
    assert session.recorded == []
    assert session.materialized == 0
    assert len(session.injected) == 1
