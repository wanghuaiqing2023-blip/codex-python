"""Client side of the Unix execve escalation protocol."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Mapping

from .escalate_protocol import (
    ESCALATE_SOCKET_ENV_VAR,
    EXEC_WRAPPER_ENV_VAR,
    EscalateRequest,
    EscalateResponse,
    SuperExecMessage,
    SuperExecResult,
)
from .socket import AsyncDatagramSocket, AsyncSocket


def get_escalate_client(
    env: Mapping[str, str] | None = None,
) -> AsyncDatagramSocket:
    source = os.environ if env is None else env
    fd = int(source[ESCALATE_SOCKET_ENV_VAR])
    if fd < 0:
        raise ValueError(
            f"{ESCALATE_SOCKET_ENV_VAR} is not a valid file descriptor: {fd}"
        )
    return AsyncDatagramSocket.from_raw_fd(fd)


def duplicate_fd_for_transfer(fd: int, name: str = "fd") -> int:
    if isinstance(fd, bool) or not isinstance(fd, int):
        raise TypeError(f"{name} must be an integer file descriptor")
    try:
        return os.dup(fd)
    except OSError as exc:
        raise OSError(
            f"failed to duplicate {name} for escalation transfer"
        ) from exc


def shell_escalation_request_env(
    env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    source = os.environ if env is None else env
    result: dict[str, str] = {}
    for key, value in source.items():
        if key in {ESCALATE_SOCKET_ENV_VAR, EXEC_WRAPPER_ENV_VAR}:
            continue
        if not isinstance(key, str) or not isinstance(value, str):
            raise TypeError("environment must map strings to strings")
        result[key] = value
    return result


async def run_shell_escalation_execve_wrapper(
    file: str,
    argv: list[str] | tuple[str, ...],
    *,
    env: Mapping[str, str] | None = None,
    cwd: Path | str | None = None,
) -> int:
    handshake_client = get_escalate_client(env)
    server, client = AsyncSocket.pair()
    server_socket = server.into_inner()
    try:
        await handshake_client.send_with_fds(
            b"\x00",
            [server_socket.fileno()],
        )
    finally:
        server_socket.close()

    await client.send(
        EscalateRequest(
            file=Path(file),
            argv=tuple(argv),
            workdir=Path.cwd() if cwd is None else Path(cwd),
            env=shell_escalation_request_env(env),
        )
    )
    response = await client.receive(EscalateResponse)
    if response.action.type == "escalate":
        destination_fds = (0, 1, 2)
        fds_to_send = tuple(
            duplicate_fd_for_transfer(fd, name)
            for fd, name in zip(
                destination_fds,
                ("stdin", "stdout", "stderr"),
            )
        )
        try:
            await client.send_with_fds(
                SuperExecMessage(destination_fds),
                fds_to_send,
            )
        finally:
            for fd in fds_to_send:
                try:
                    os.close(fd)
                except OSError:
                    pass
        return (await client.receive(SuperExecResult)).exit_code
    if response.action.type == "run":
        os.execv(file, list(argv))
        raise OSError("execv unexpectedly returned")
    if response.action.type == "deny":
        suffix = (
            ""
            if response.action.reason is None
            else f": {response.action.reason}"
        )
        print(f"Execution denied{suffix}", file=sys.stderr)
        return 1
    raise ValueError(f"unknown escalate action type: {response.action.type}")


__all__ = [
    "duplicate_fd_for_transfer",
    "get_escalate_client",
    "run_shell_escalation_execve_wrapper",
    "shell_escalation_request_env",
]
