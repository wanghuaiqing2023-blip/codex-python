"""Server side of the Unix execve escalation protocol."""

from __future__ import annotations

import asyncio
import os
import socket as _socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .escalate_protocol import (
    ESCALATE_SOCKET_ENV_VAR,
    EXEC_WRAPPER_ENV_VAR,
    EscalateAction,
    EscalateRequest,
    EscalateResponse,
    EscalationExecution,
    SuperExecMessage,
    SuperExecResult,
)
from .escalation_policy import EscalationPolicy
from .socket import AsyncDatagramSocket, AsyncSocket
from .stopwatch import CancellationToken


@dataclass(frozen=True)
class ExecParams:
    command: str
    workdir: str
    timeout_ms: int | None = None
    login: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.command, str):
            raise TypeError("command must be a string")
        if not isinstance(self.workdir, str):
            object.__setattr__(self, "workdir", str(self.workdir))
        if self.timeout_ms is not None and self.timeout_ms < 0:
            raise ValueError("timeout_ms must be non-negative")


@dataclass(frozen=True)
class ExecResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    output: str = ""
    duration: float = 0.0
    timed_out: bool = False


@dataclass(frozen=True)
class PreparedExec:
    command: tuple[str, ...]
    cwd: Path
    env: dict[str, str] = field(default_factory=dict)
    arg0: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.command, tuple):
            object.__setattr__(self, "command", tuple(self.command))
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(self.cwd))
        if not isinstance(self.env, dict):
            object.__setattr__(self, "env", dict(self.env))


class ShellCommandExecutor:
    async def run(
        self,
        command: list[str],
        cwd: Path,
        env_overlay: dict[str, str],
        cancel_rx: CancellationToken,
        after_spawn: Any | None = None,
    ) -> ExecResult:
        raise NotImplementedError(
            "codex-shell-escalation command execution is not ported"
        )

    async def prepare_escalated_exec(
        self,
        program: Path,
        argv: list[str],
        workdir: Path,
        env: dict[str, str],
        execution: EscalationExecution | Any,
    ) -> PreparedExec:
        raise NotImplementedError(
            "codex-shell-escalation escalated exec preparation is not ported"
        )


class EscalationSession:
    def __init__(
        self,
        env: dict[str, str],
        task: asyncio.Task[Any],
        client_socket: _socket.socket,
        cancellation_token: CancellationToken,
    ) -> None:
        self._env = env
        self.task = task
        self.client_socket = client_socket
        self.cancellation_token = cancellation_token

    def env(self) -> dict[str, str]:
        return self._env

    def close_client_socket(self) -> None:
        if self.client_socket is not None:
            sock = self.client_socket
            self.client_socket = None  # type: ignore[assignment]
            sock.close()

    def close(self) -> None:
        self.close_client_socket()
        self.cancellation_token.cancel()
        self.task.cancel()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


class EscalateServer:
    def __init__(
        self,
        shell_path: Path | str,
        execve_wrapper: Path | str,
        policy: EscalationPolicy,
    ) -> None:
        self.shell_path = Path(shell_path)
        self.execve_wrapper = Path(execve_wrapper)
        self.policy = policy

    async def exec(
        self,
        params: ExecParams,
        cancel_rx: CancellationToken,
        command_executor: ShellCommandExecutor,
    ) -> ExecResult:
        session = self.start_session(cancel_rx, command_executor)
        client_socket = session.client_socket

        def after_spawn() -> None:
            if client_socket is not None:
                session.close_client_socket()

        command = [
            self.shell_path.as_posix(),
            "-c" if params.login is False else "-lc",
            params.command,
        ]
        return await command_executor.run(
            command,
            Path(params.workdir),
            dict(session.env()),
            cancel_rx,
            after_spawn,
        )

    def start_session(
        self,
        parent_cancellation_token: CancellationToken,
        command_executor: ShellCommandExecutor,
    ) -> EscalationSession:
        session_token = CancellationToken()
        server, client = AsyncDatagramSocket.pair()
        client_socket = client.into_inner()
        task = asyncio.create_task(
            escalate_task(
                server,
                self.policy,
                command_executor,
                parent_cancellation_token,
                session_token,
            )
        )
        return EscalationSession(
            {
                ESCALATE_SOCKET_ENV_VAR: str(client_socket.fileno()),
                EXEC_WRAPPER_ENV_VAR: self.execve_wrapper.as_posix(),
            },
            task,
            client_socket,
            session_token,
        )


async def escalate_task(
    socket: AsyncDatagramSocket,
    policy: EscalationPolicy,
    command_executor: ShellCommandExecutor,
    parent_cancellation_token: CancellationToken,
    session_cancellation_token: CancellationToken,
) -> None:
    while (
        not parent_cancellation_token.is_cancelled()
        and not session_cancellation_token.is_cancelled()
    ):
        receive = asyncio.create_task(socket.receive_with_fds())
        parent_wait = asyncio.create_task(
            parent_cancellation_token.cancelled()
        )
        session_wait = asyncio.create_task(
            session_cancellation_token.cancelled()
        )
        done, pending = await asyncio.wait(
            {receive, parent_wait, session_wait},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        if receive not in done:
            return
        _data, fds = receive.result()
        if len(fds) != 1:
            continue
        asyncio.create_task(
            handle_escalate_session_with_policy(
                AsyncSocket.from_fd(fds[0]),
                policy,
                command_executor,
                parent_cancellation_token,
                session_cancellation_token,
            )
        )


async def handle_escalate_session_with_policy(
    socket: AsyncSocket,
    policy: EscalationPolicy,
    command_executor: ShellCommandExecutor,
    parent_cancellation_token: CancellationToken,
    session_cancellation_token: CancellationToken,
) -> None:
    if (
        parent_cancellation_token.is_cancelled()
        or session_cancellation_token.is_cancelled()
    ):
        return
    request = await socket.receive(EscalateRequest)
    program = (
        request.file
        if request.file.is_absolute()
        else request.workdir / request.file
    )
    decision = await policy.determine_action(
        program,
        list(request.argv),
        request.workdir,
    )
    if decision.kind == "run":
        await socket.send(EscalateResponse(EscalateAction.run()))
        return
    if decision.kind == "deny":
        await socket.send(
            EscalateResponse(EscalateAction.deny(decision.reason))
        )
        return
    if decision.kind != "escalate":
        raise ValueError(
            f"unknown escalation decision kind: {decision.kind}"
        )

    await socket.send(EscalateResponse(EscalateAction.escalate()))
    message, fds = await socket.receive_with_fds(SuperExecMessage)
    if len(fds) != len(message.fds):
        raise ValueError(
            "mismatched number of fds in SuperExecMessage: "
            f"{len(message.fds)} in the message, {len(fds)} from the control message"
        )
    prepared = await command_executor.prepare_escalated_exec(
        program,
        list(request.argv),
        request.workdir,
        dict(request.env),
        decision.execution,
    )
    if not prepared.command:
        raise ValueError("prepared escalated command must not be empty")
    process_env = os.environ.copy()
    process_env.update(prepared.env)
    process = await asyncio.create_subprocess_exec(
        *prepared.command,
        cwd=prepared.cwd,
        env=process_env,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await socket.send(SuperExecResult(await process.wait()))


__all__ = [
    "EscalateServer",
    "EscalationSession",
    "ExecParams",
    "ExecResult",
    "PreparedExec",
    "ShellCommandExecutor",
    "escalate_task",
    "handle_escalate_session_with_policy",
]
